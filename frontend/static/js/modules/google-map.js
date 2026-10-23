// Google Maps renderer for the map view interface defined in map.js. Used when
// the backend runs on the google provider, because Google route and place
// results may only be displayed on a Google map.
import { HEADING_ARROW_HTML, convoyMarkerStyle } from './map.js';

const ROUTE_STYLE = { strokeColor: '#007bff', strokeOpacity: 1, strokeWeight: 5 };
const POSITION_DOT_STYLE = { radius: 8, color: '#1d4ed8', fillColor: '#3498db' };

let loadPromise = null;

function loadMapsApi(apiKey) {
    if (window.google?.maps?.importLibrary) {
        return Promise.resolve();
    }
    if (loadPromise) {
        return loadPromise;
    }

    loadPromise = new Promise((resolve, reject) => {
        const callbackName = '__waywiseMapsReady';
        window[callbackName] = () => {
            delete window[callbackName];
            resolve();
        };
        // Called by the Maps API when the key is rejected (bad key, wrong
        // referrer, billing disabled), which otherwise fails silently.
        window.gm_authFailure = () => reject(new Error('Google Maps rejected the API key.'));

        const params = new URLSearchParams({
            key: apiKey,
            v: 'weekly',
            loading: 'async',
            callback: callbackName,
        });
        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
        script.async = true;
        script.onerror = () => reject(new Error('Failed to load the Google Maps JavaScript API.'));
        document.head.appendChild(script);
    });
    return loadPromise;
}

function toLatLng([lat, lng]) {
    return { lat, lng };
}

function circleElement({ radius, color, fillColor }) {
    const dot = document.createElement('div');
    dot.className = 'gmap-dot';
    dot.style.width = `${radius * 2}px`;
    dot.style.height = `${radius * 2}px`;
    dot.style.background = fillColor;
    dot.style.borderColor = color;
    return dot;
}

function arrowElement(heading) {
    const wrapper = document.createElement('div');
    wrapper.className = 'nav-arrow-icon gmap-centered';
    wrapper.innerHTML = `<div class="nav-arrow-rot" style="transform: rotate(${heading}deg)">${HEADING_ARROW_HTML}</div>`;
    return wrapper;
}

function convoyElement(isMe, label) {
    const wrapper = document.createElement('div');
    wrapper.className = 'gmap-convoy';
    const style = convoyMarkerStyle(isMe);
    // Markers anchor at the content's bottom edge; shift down so the dot,
    // not the label above it, sits on the member's position.
    wrapper.style.transform = `translateY(${style.radius}px)`;
    const tag = document.createElement('div');
    tag.className = 'convoy-label gmap-convoy-label';
    tag.innerHTML = label;
    wrapper.append(tag, circleElement(style));
    return wrapper;
}

export async function createGoogleMap({ mapId, initialCenter, zoom, apiKey, googleMapId }) {
    if (!apiKey) {
        throw new Error('GOOGLE_MAPS_JS_API_KEY is not configured.');
    }
    await loadMapsApi(apiKey);
    const { Map: GoogleMap, Polyline, InfoWindow } = await google.maps.importLibrary('maps');
    const { LatLngBounds } = await google.maps.importLibrary('core');
    const { AdvancedMarkerElement } = await google.maps.importLibrary('marker');

    const map = new GoogleMap(document.getElementById(mapId), {
        center: toLatLng(initialCenter),
        zoom,
        mapId: googleMapId,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: false,
        colorScheme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'DARK' : 'LIGHT',
    });

    // One shared window, so opening a popup closes the previous one as Leaflet does.
    const infoWindow = new InfoWindow();
    const stopMarkers = [];
    const convoyMarkers = new Map();
    let routeLine = null;
    let positionMarker = null;
    let positionMarkerIsArrow = false;

    function addMarker(latLng, content, popupHtml, zIndex) {
        const marker = new AdvancedMarkerElement({
            map,
            position: toLatLng(latLng),
            content,
            zIndex,
            gmpClickable: Boolean(popupHtml),
        });
        marker.popupHtml = popupHtml;
        if (popupHtml) {
            marker.addEventListener('gmp-click', () => openPopup(marker));
        }
        return marker;
    }

    function openPopup(marker) {
        infoWindow.setContent(marker.popupHtml);
        infoWindow.open({ anchor: marker, map });
    }

    function removeMarker(marker) {
        marker.map = null;
    }

    return {
        setView(latLng, zoomLevel) {
            map.setCenter(toLatLng(latLng));
            map.setZoom(zoomLevel);
        },
        panTo(latLng) {
            map.panTo(toLatLng(latLng));
        },
        flyTo(latLng, zoomLevel) {
            map.panTo(toLatLng(latLng));
            map.setZoom(zoomLevel);
        },
        invalidateSize() {
            // The Maps API tracks its container size itself.
        },

        showRoute(coordinates, { bottomPadding = 0 } = {}) {
            if (routeLine) routeLine.setMap(null);
            const path = coordinates.map(toLatLng);
            routeLine = new Polyline({ ...ROUTE_STYLE, path, map });
            const bounds = new LatLngBounds();
            path.forEach((point) => bounds.extend(point));
            map.fitBounds(bounds, { top: 0, right: 0, bottom: bottomPadding, left: 0 });
        },
        clearRoute() {
            if (routeLine) routeLine.setMap(null);
            routeLine = null;
        },

        addStopMarker(latLng, popupHtml) {
            const marker = addMarker(latLng, undefined, popupHtml);
            stopMarkers.push(marker);
            return { openPopup: () => openPopup(marker) };
        },
        clearStopMarkers() {
            stopMarkers.splice(0).forEach(removeMarker);
            infoWindow.close();
        },

        hasPositionMarker() {
            return positionMarker !== null;
        },
        updatePositionMarker(latLng, heading) {
            const hasHeading = typeof heading === 'number' && !Number.isNaN(heading);

            if (hasHeading) {
                if (!positionMarker || !positionMarkerIsArrow) {
                    if (positionMarker) removeMarker(positionMarker);
                    positionMarker = addMarker(latLng, arrowElement(heading), '<b>You are here</b>', 1000);
                    positionMarkerIsArrow = true;
                } else {
                    positionMarker.position = toLatLng(latLng);
                    const rot = positionMarker.content?.querySelector('.nav-arrow-rot');
                    if (rot) rot.style.transform = `rotate(${heading}deg)`;
                }
                return;
            }

            if (!positionMarker) {
                const dot = circleElement(POSITION_DOT_STYLE);
                dot.classList.add('gmap-centered');
                positionMarker = addMarker(latLng, dot, '<b>You are here</b>', 1000);
                positionMarkerIsArrow = false;
                openPopup(positionMarker);
            } else {
                positionMarker.position = toLatLng(latLng);
            }
        },
        clearPositionMarker() {
            if (positionMarker) removeMarker(positionMarker);
            positionMarker = null;
            positionMarkerIsArrow = false;
        },

        // label and popupHtml must already be escaped.
        upsertConvoyMarker(memberId, latLng, { isMe, label, popupHtml }) {
            let marker = convoyMarkers.get(memberId);
            if (!marker) {
                marker = addMarker(latLng, convoyElement(isMe, label), popupHtml, 900);
                convoyMarkers.set(memberId, marker);
            } else {
                marker.position = toLatLng(latLng);
                marker.content = convoyElement(isMe, label);
                marker.popupHtml = popupHtml;
            }
        },
        removeConvoyMarkersExcept(activeMemberIds) {
            for (const [memberId, marker] of convoyMarkers.entries()) {
                if (!activeMemberIds.has(memberId)) {
                    removeMarker(marker);
                    convoyMarkers.delete(memberId);
                }
            }
        },
        clearConvoyMarkers() {
            convoyMarkers.forEach(removeMarker);
            convoyMarkers.clear();
        },
    };
}
