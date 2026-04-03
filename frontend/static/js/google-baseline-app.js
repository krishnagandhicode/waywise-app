import {
    loadGoogleMapsApi,
    createGoogleMap,
    renderGoogleRoute,
    searchPlacesAlongGoogleRoute,
    renderPlacesList,
    renderPlaceMarkers,
} from './modules/google-baseline.js';

document.addEventListener('DOMContentLoaded', async () => {
    const statusEl = document.getElementById('gb-status');
    const originInput = document.getElementById('gb-origin');
    const destinationInput = document.getElementById('gb-destination');
    const queryInput = document.getElementById('gb-query');
    const routeBtn = document.getElementById('gb-route-btn');
    const searchBtn = document.getElementById('gb-search-btn');
    const resultsEl = document.getElementById('gb-results');
    const summaryEl = document.getElementById('gb-summary');
    const apiKeyInput = document.getElementById('gb-api-key');

    let map = null;
    let currentOverviewPath = [];
    let currentRouteRenderer = null;
    let placeMarkers = [];

    function setStatus(message, type = 'info') {
        statusEl.textContent = message;
        statusEl.className = `gb-status gb-status-${type}`;
    }

    async function ensureMapReady() {
        const apiKey = apiKeyInput.value.trim();
        if (!apiKey) {
            throw new Error('Add a Google Maps API key first.');
        }

        if (!map) {
            await loadGoogleMapsApi(apiKey);
            map = createGoogleMap({ mapElementId: 'gb-map' });
        }
    }

    routeBtn.addEventListener('click', async () => {
        const origin = originInput.value.trim();
        const destination = destinationInput.value.trim();

        if (!origin || !destination) {
            setStatus('Enter both origin and destination.', 'error');
            return;
        }

        routeBtn.disabled = true;
        setStatus('Rendering route...', 'info');

        try {
            await ensureMapReady();

            if (currentRouteRenderer) {
                currentRouteRenderer.setMap(null);
            }

            const routeData = await renderGoogleRoute({
                map,
                origin,
                destination,
            });

            currentRouteRenderer = routeData.directionsRenderer;
            currentOverviewPath = routeData.overviewPath;
            summaryEl.textContent = `${routeData.summary.distance} | ${routeData.summary.duration}`;
            setStatus('Route ready. You can search places along this route.', 'success');
        } catch (error) {
            setStatus(error.message || 'Failed to render route.', 'error');
        } finally {
            routeBtn.disabled = false;
        }
    });

    searchBtn.addEventListener('click', async () => {
        const query = queryInput.value.trim();
        if (!query) {
            setStatus('Enter a place query (for example: petrol pump, food).', 'error');
            return;
        }

        searchBtn.disabled = true;
        setStatus('Searching places along route...', 'info');

        try {
            await ensureMapReady();
            const places = await searchPlacesAlongGoogleRoute({
                map,
                overviewPath: currentOverviewPath,
                query,
            });

            renderPlacesList({ places, listElement: resultsEl });
            placeMarkers = renderPlaceMarkers({
                map,
                places,
                existingMarkers: placeMarkers,
            });

            setStatus(`Found ${places.length} place(s).`, 'success');
        } catch (error) {
            setStatus(error.message || 'Places search failed.', 'error');
        } finally {
            searchBtn.disabled = false;
        }
    });

    setStatus('Ready. Add key, then render route.', 'info');
});
