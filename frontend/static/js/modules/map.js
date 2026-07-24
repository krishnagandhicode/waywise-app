export function createMap({ mapId, initialCenter, zoom }) {
    const map = L.map(mapId).setView(initialCenter, zoom);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    return {
        map,
        markersLayer: new L.LayerGroup().addTo(map),
        convoyLayer: new L.LayerGroup().addTo(map),
    };
}

export function getCurrentTurnInfo(routeCoordinates, directionSteps, currentLatLng) {
    if (routeCoordinates.length === 0 || directionSteps.length === 0) {
        return null;
    }

    let closestPointIndex = 0;
    let minDistance = Infinity;
    routeCoordinates.forEach((point, index) => {
        const distance = L.latLng(point).distanceTo(currentLatLng);
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
