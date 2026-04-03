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

export function renderCurrentTurn(panelElement, turnInfo) {
    if (!turnInfo) {
        panelElement.innerHTML = '';
        return;
    }

    panelElement.innerHTML = `
        <p class="turn-instruction">${turnInfo.currentInstruction}</p>
        <p class="next-turn-info">Next: ${turnInfo.nextInstruction}</p>
    `;
}
