// Every map call in the app goes through the object createMap returns, so the
// rendering library can be swapped without touching script.js or convoy.js.
// Coordinates are always [lat, lng] arrays.

export const HEADING_ARROW_HTML = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 2 4 21l8-4 8 4z"/></svg>';

const POSITION_DOT_STYLE = { radius: 8, color: '#1d4ed8', fillColor: '#3498db', fillOpacity: 1, weight: 2 };
const ROUTE_STYLE = { color: '#007bff', weight: 5 };

export function convoyMarkerStyle(isMe) {
    return {
        radius: isMe ? 10 : 8,
        color: isMe ? '#1d4ed8' : '#9a3412',
        fillColor: isMe ? '#2563eb' : '#f97316',
        fillOpacity: 0.95,
        weight: 2,
    };
}

export function createMap({ mapId, initialCenter, zoom }) {
    const map = L.map(mapId).setView(initialCenter, zoom);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const stopsLayer = new L.LayerGroup().addTo(map);
    const convoyLayer = new L.LayerGroup().addTo(map);
    const convoyMarkers = new Map();
    let routeLayer = null;
    let positionMarker = null;
    let positionMarkerIsArrow = false;

    function createHeadingArrowIcon(heading) {
        return L.divIcon({
            className: 'nav-arrow-icon',
            html: `<div class="nav-arrow-rot" style="transform: rotate(${heading}deg)">${HEADING_ARROW_HTML}</div>`,
            iconSize: [36, 36],
            iconAnchor: [18, 18],
        });
    }

    return {
        setView(latLng, zoomLevel) {
            map.setView(latLng, zoomLevel, { animate: true });
        },
        panTo(latLng) {
            map.panTo(latLng);
        },
        flyTo(latLng, zoomLevel) {
            map.flyTo(latLng, zoomLevel);
        },
        invalidateSize() {
            map.invalidateSize();
        },

        showRoute(coordinates, { bottomPadding = 0 } = {}) {
            if (routeLayer) map.removeLayer(routeLayer);
            routeLayer = L.polyline(coordinates, ROUTE_STYLE).addTo(map);
            map.fitBounds(routeLayer.getBounds(), {
                paddingBottomRight: [0, bottomPadding],
                paddingTopLeft: [0, 0],
            });
            setTimeout(() => map.invalidateSize(), 120);
        },
        clearRoute() {
            if (routeLayer) map.removeLayer(routeLayer);
            routeLayer = null;
        },

        addStopMarker(latLng, popupHtml) {
            const marker = L.marker(latLng).addTo(stopsLayer);
            marker.bindPopup(popupHtml);
            return { openPopup: () => marker.openPopup() };
        },
        clearStopMarkers() {
            stopsLayer.clearLayers();
        },

        hasPositionMarker() {
            return positionMarker !== null;
        },
        // Show a plain dot until the device reports a real heading, then a rotating arrow.
        // Once upgraded to an arrow we keep it to avoid flicker when stationary.
        updatePositionMarker(latLng, heading) {
            const hasHeading = typeof heading === 'number' && !Number.isNaN(heading);

            if (hasHeading) {
                if (!positionMarker || !positionMarkerIsArrow) {
                    if (positionMarker) map.removeLayer(positionMarker);
                    positionMarker = L.marker(latLng, { icon: createHeadingArrowIcon(heading), zIndexOffset: 1000 }).addTo(map);
                    positionMarker.bindPopup('<b>You are here</b>');
                    positionMarkerIsArrow = true;
                } else {
                    positionMarker.setLatLng(latLng);
                    const rot = positionMarker.getElement()?.querySelector('.nav-arrow-rot');
                    if (rot) rot.style.transform = `rotate(${heading}deg)`;
                }
                return;
            }

            if (!positionMarker) {
                positionMarker = L.circleMarker(latLng, POSITION_DOT_STYLE).addTo(map);
                positionMarker.bindPopup('<b>You are here</b>').openPopup();
                positionMarkerIsArrow = false;
            } else {
                // No fresh heading: just move whatever marker we already have (dot or last arrow).
                positionMarker.setLatLng(latLng);
            }
        },
        clearPositionMarker() {
            if (positionMarker) map.removeLayer(positionMarker);
            positionMarker = null;
            positionMarkerIsArrow = false;
        },

        // label and popupHtml must already be escaped.
        upsertConvoyMarker(memberId, latLng, { isMe, label, popupHtml }) {
            let marker = convoyMarkers.get(memberId);
            if (!marker) {
                marker = L.circleMarker(latLng, convoyMarkerStyle(isMe)).addTo(convoyLayer);
                convoyMarkers.set(memberId, marker);
            } else {
                marker.setLatLng(latLng);
                marker.setStyle(convoyMarkerStyle(isMe));
            }
            marker.bindPopup(popupHtml);
            marker.bindTooltip(label, {
                permanent: true,
                direction: 'top',
                offset: [0, -12],
                className: 'convoy-label',
            });
            marker.bringToFront();
        },
        removeConvoyMarkersExcept(activeMemberIds) {
            for (const [memberId, marker] of convoyMarkers.entries()) {
                if (!activeMemberIds.has(memberId)) {
                    convoyLayer.removeLayer(marker);
                    convoyMarkers.delete(memberId);
                }
            }
        },
        clearConvoyMarkers() {
            convoyLayer.clearLayers();
            convoyMarkers.clear();
        },
    };
}

// Great-circle distance in meters between two [lat, lng] points.
export function distanceMeters(a, b) {
    const toRad = (deg) => (deg * Math.PI) / 180;
    const dLat = toRad(b[0] - a[0]);
    const dLng = toRad(b[1] - a[1]);
    const h = Math.sin(dLat / 2) ** 2
        + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

export function getCurrentTurnInfo(routeCoordinates, directionSteps, currentLatLng) {
    if (routeCoordinates.length === 0 || directionSteps.length === 0) {
        return null;
    }

    let closestPointIndex = 0;
    let minDistance = Infinity;
    routeCoordinates.forEach((point, index) => {
        const distance = distanceMeters(point, currentLatLng);
        if (distance < minDistance) {
            minDistance = distance;
            closestPointIndex = index;
        }
    });

    const progress = closestPointIndex / routeCoordinates.length;
    let currentStepIndex = Math.floor(progress * directionSteps.length);
    currentStepIndex = Math.min(currentStepIndex, directionSteps.length - 1);

    return {
        currentInstruction: directionSteps[currentStepIndex],
        nextInstruction: directionSteps[currentStepIndex + 1] || 'You are nearing your destination.',
    };
}

const TURN_ARROWS = {
    left: '<path d="M11 5 4 12l7 7"/><path d="M4 12h12a4 4 0 0 1 4 4v2"/>',
    right: '<path d="m13 5 7 7-7 7"/><path d="M20 12H8a4 4 0 0 0-4 4v2"/>',
    destination: '<path d="M12 21s-6-5.7-6-10a6 6 0 0 1 12 0c0 4.3-6 10-6 10Z"/><circle cx="12" cy="11" r="2"/>',
    straight: '<path d="M12 19V5"/><path d="m6 11 6-6 6 6"/>',
};

function pickArrow(instruction) {
    const text = (instruction || '').toLowerCase();
    if (text.includes('arriv') || text.includes('destination') || text.includes('nearing')) {
        return TURN_ARROWS.destination;
    }
    if (text.includes('left')) return TURN_ARROWS.left;
    if (text.includes('right')) return TURN_ARROWS.right;
    return TURN_ARROWS.straight;
}

export function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

export function renderTurnStatus(panelElement, message, { busy = false } = {}) {
    const icon = busy
        ? '<span class="hud-spinner"></span>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v4h1"/></svg>';
    panelElement.innerHTML = `
        <span class="turn-arrow turn-arrow-muted" aria-hidden="true">${icon}</span>
        <span class="turn-text">
            <p class="turn-status">${escapeHtml(message)}</p>
        </span>
    `;
}

export function renderCurrentTurn(panelElement, turnInfo) {
    if (!turnInfo) {
        panelElement.innerHTML = '';
        return;
    }

    const arrowPaths = pickArrow(turnInfo.currentInstruction);
    panelElement.innerHTML = `
        <span class="turn-arrow" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${arrowPaths}</svg>
        </span>
        <span class="turn-text">
            <p class="turn-instruction">${escapeHtml(turnInfo.currentInstruction)}</p>
            <p class="next-turn-info">Next: ${escapeHtml(turnInfo.nextInstruction)}</p>
        </span>
    `;
}
