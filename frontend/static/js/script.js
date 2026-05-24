import { buildApiUrl, fetchJson } from './modules/api.js';
import { createMap, getCurrentTurnInfo, renderCurrentTurn, renderTurnStatus } from './modules/map.js';
import { renderConvoyMembersUI } from './modules/convoy.js';
import { showToast } from './modules/toast.js';

document.addEventListener('DOMContentLoaded', () => {

    // --- THEME ---
    const THEME_KEY = 'waywise-theme';
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = themeToggle?.querySelector('.theme-toggle-icon');

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        if (themeIcon) themeIcon.textContent = theme === 'dark' ? '☀️' : '🌙';
        if (themeToggle) {
            themeToggle.title = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
        }
    }

    const storedTheme = localStorage.getItem(THEME_KEY);
    const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
    applyTheme(storedTheme || (prefersDark ? 'dark' : 'light'));

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            localStorage.setItem(THEME_KEY, next);
        });
    }

    function setStopSearchLoading(isLoading) {
        const stopBtns = document.querySelectorAll('.stop-btn');
        stopBtns.forEach((btn) => {
            btn.disabled = isLoading;
        });
        customQueryBtn.disabled = isLoading;
    }

    function renderStopSearchRetry(message, query) {
        stopsUl.innerHTML = '';
        const item = document.createElement('li');
        const text = document.createElement('div');
        text.textContent = message;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'stop-btn stop-retry-btn';
        button.dataset.query = query;
        button.textContent = 'Retry';
        item.appendChild(text);
        item.appendChild(button);
        stopsUl.appendChild(item);
    }

    // --- MAP AND ELEMENT REFERENCES ---
    const { map, markersLayer, convoyLayer } = createMap({
        mapId: 'map',
        initialCenter: [28.6139, 77.2090],
        zoom: 7,
    });

    let routeCoordinates = [];
    let directionSteps = [];
    let routeLayer = null;
    let positionMarker = null;
    let watchId = null;
    let lastKnownPosition = null;
    let convoyRoomId = null;
    let convoyMemberId = null;
    let convoySharedDestination = null;
    let convoyAutoRouteInFlight = false;
    let convoyPollTimer = null;
    const convoyMarkers = new Map();

    const startNavBtn = document.getElementById('start-nav-btn');
    const originInput = document.getElementById('origin');
    const destinationInput = document.getElementById('destination');
    const inTripControls = document.getElementById('in-trip-controls');
    const stopButtonsContainer = document.querySelector('.stop-buttons');
    const stopsUl = document.getElementById('stops-ul');
    const currentTurnPanel = document.getElementById('current-turn-panel');
    const currentLocationOriginBtn = document.getElementById('current-location-origin');
    const currentLocationDestBtn = document.getElementById('current-location-dest');
    const customQueryInput = document.getElementById('custom-query-input');
    const customQueryBtn = document.getElementById('custom-query-btn');
    const backendStatus = document.getElementById('backend-status');
    const convoyNameInput = document.getElementById('convoy-name');
    const convoyRoomInput = document.getElementById('convoy-room-id');
    const convoyCreateBtn = document.getElementById('convoy-create-btn');
    const convoyJoinBtn = document.getElementById('convoy-join-btn');
    const convoyLeaveBtn = document.getElementById('convoy-leave-btn');
    const convoySession = document.getElementById('convoy-session');
    const convoyActiveRoom = document.getElementById('convoy-active-room');
    const convoyMembersUl = document.getElementById('convoy-members-ul');
    const convoyToggleBtn = document.getElementById('convoy-toggle-btn');
    const convoyBody = document.getElementById('convoy-body');
    const sheetHandle = document.getElementById('sheet-handle');
    const controlPanel = document.querySelector('.control-panel');

    // --- EVENT LISTENERS ---

    currentLocationOriginBtn.addEventListener('click', () => setInputToCurrentLocation(originInput));
    currentLocationDestBtn.addEventListener('click', () => setInputToCurrentLocation(destinationInput));
    startNavBtn.addEventListener('click', () => startNavigation());

    stopButtonsContainer.addEventListener('click', (event) => {
        const clickedButton = event.target.closest('.stop-btn');
        if (clickedButton) {
            findAndDisplayStops(clickedButton.dataset.query);
        }
    });

    customQueryBtn.addEventListener('click', () => {
        const query = customQueryInput.value;
        if (query) {
            findAndDisplayStops(query);
        } else {
            showToast('Please enter something to search for.', 'error');
        }
    });

    customQueryInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            customQueryBtn.click();
        }
    });

    stopsUl.addEventListener('click', (event) => {
        const retryBtn = event.target.closest('.stop-retry-btn');
        if (retryBtn) {
            findAndDisplayStops(retryBtn.dataset.query || '');
        }
    });

    convoyCreateBtn.addEventListener('click', createConvoy);
    convoyJoinBtn.addEventListener('click', joinConvoy);
    convoyLeaveBtn.addEventListener('click', leaveConvoy);

    convoyToggleBtn.addEventListener('click', () => {
        const isExpanded = convoyToggleBtn.getAttribute('aria-expanded') === 'true';
        convoyToggleBtn.setAttribute('aria-expanded', String(!isExpanded));
        convoyBody.classList.toggle('section-collapsed', isExpanded);
    });

    if (sheetHandle) {
        sheetHandle.addEventListener('click', () => {
            controlPanel.classList.toggle('sheet-expanded');
        });
    }

    // On mobile, start with convoy section collapsed to keep the sheet tidy
    if (window.innerWidth <= 640) {
        convoyToggleBtn.setAttribute('aria-expanded', 'false');
        convoyBody.classList.add('section-collapsed');
    }

    convoyRoomInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            convoyJoinBtn.click();
        }
    });

    updateBackendStatus();
    setInterval(updateBackendStatus, 20000);
    window.addEventListener('resize', () => {
        map.invalidateSize();
    });

    // --- MAIN FUNCTIONS ---

    async function updateBackendStatus() {
        try {
            const { response, data } = await fetchJson(buildApiUrl('/health'));
            if (!response.ok) {
                throw new Error('Health check failed');
            }
            backendStatus.classList.remove('status-bad');
            backendStatus.classList.add('status-good');
            const full = `Backend: online | Provider: ${data.provider} | Mock: ${data.mock_mode ? 'yes' : 'no'}`;
            setBackendStatusText(full, 'Online');
        } catch (error) {
            backendStatus.classList.remove('status-good');
            backendStatus.classList.add('status-bad');
            setBackendStatusText('Backend: offline or unreachable', 'Offline');
        }
    }

    function setBackendStatusText(full, compact) {
        backendStatus.innerHTML = '';
        const fullSpan = document.createElement('span');
        fullSpan.className = 'status-full';
        fullSpan.textContent = full;
        const compactSpan = document.createElement('span');
        compactSpan.className = 'status-compact';
        compactSpan.textContent = compact;
        backendStatus.append(fullSpan, compactSpan);
    }

    async function startNavigation(options = {}) {
        const { suppressConvoySync = false } = options;
        const origin = originInput.value;
        const destination = destinationInput.value;
        if (!origin || !destination) {
            showToast('Please fill out both Origin and Destination.', 'error');
            return;
        }

        if (convoyRoomId && convoyMemberId && !suppressConvoySync) {
            syncConvoyDestination(destination).catch((error) => {
                console.error('Failed to sync convoy destination:', error);
            });
        }

        startNavBtn.textContent = 'Calculating Route...';
        startNavBtn.disabled = true;
        resetUI();

        try {
            const routeData = await getRouteAndDirections(origin, destination);
            if (routeData.route_coordinates) {
                displayRoute(routeData.route_coordinates);
                inTripControls.classList.remove('hidden');
                currentTurnPanel.classList.remove('hidden');
                renderTurnStatus(currentTurnPanel, 'Acquiring your location…', { busy: true });
                controlPanel.classList.add('navigating');
                // On mobile, collapse the bottom sheet so the map is fully visible
                if (window.innerWidth <= 640) {
                    controlPanel.classList.remove('sheet-expanded');
                }
                startLiveTracking();
                showToast('Route ready — navigation started.', 'success');
            } else {
                showToast('Could not find a route between those locations.', 'error');
            }
        } catch (error) {
            console.error('Error starting navigation:', error);
            showToast('Could not start navigation. Please try again.', 'error');
        } finally {
            startNavBtn.textContent = 'Start Navigation';
            startNavBtn.disabled = false;
        }
    }

    async function findAndDisplayStops(query) {
        stopsUl.innerHTML = '';
        const loadingItem = document.createElement('li');
        loadingItem.className = 'stops-status';
        const spinner = document.createElement('span');
        spinner.className = 'stops-spinner';
        spinner.setAttribute('aria-hidden', 'true');
        loadingItem.appendChild(spinner);
        loadingItem.appendChild(document.createTextNode(`Searching for "${query}"...`));
        stopsUl.appendChild(loadingItem);
        markersLayer.clearLayers();
        customQueryInput.value = ''; // Clear input after search
        setStopSearchLoading(true);

        const origin = originInput.value;
        const destination = destinationInput.value;
        const latitude = lastKnownPosition?.coords?.latitude;
        const longitude = lastKnownPosition?.coords?.longitude;

        try {
            const apiUrl = buildApiUrl('/find_stops', {
                origin,
                destination,
                query,
                live_lat: latitude ?? undefined,
                live_lng: longitude ?? undefined,
            });
            const { response, data } = await fetchJson(apiUrl);
            if (!response.ok) throw new Error(data.error || 'Stop search failed.');

            stopsUl.innerHTML = '';
            if (data.provider_notice) {
                const noticeItem = document.createElement('li');
                noticeItem.textContent = data.provider_notice;
                stopsUl.appendChild(noticeItem);
            }
            if (data.stops && data.stops.length > 0) {
                data.stops.forEach(stop => {
                    const marker = L.marker([stop.location.lat, stop.location.lng]).addTo(markersLayer);
                    marker.bindPopup(`<b>${stop.name}</b><br>Rating: ${stop.rating || 'N/A'}<br>${stop.distance} · ${stop.duration}`);

                    const li = document.createElement('li');
                    li.className = 'stop-item';
                    li.innerHTML = `<span class="stop-item-name">${stop.name}</span><span class="stop-item-meta">⭐ ${stop.rating || 'N/A'} · ${stop.distance} · ${stop.duration}</span>`;
                    li.addEventListener('click', () => {
                        map.flyTo([stop.location.lat, stop.location.lng], 16);
                        marker.openPopup();
                        // On mobile, collapse the sheet so the map is fully visible
                        if (window.innerWidth <= 640) {
                            controlPanel.classList.remove('sheet-expanded');
                        }
                    });
                    stopsUl.appendChild(li);
                });
            } else {
                const emptyItem = document.createElement('li');
                emptyItem.textContent = `No on-route results found for '${query}'.`;
                stopsUl.appendChild(emptyItem);
            }
        } catch (error) {
            console.error("Error finding stops:", error);
            renderStopSearchRetry(error.message || 'Stop search is temporarily unavailable.', query);
        } finally {
            setStopSearchLoading(false);
        }
    }

    function startLiveTracking() {
        if (!navigator.geolocation) {
            renderTurnStatus(currentTurnPanel, 'Live tracking unavailable — your browser does not support location.');
            return;
        }
        if (watchId !== null) {
            navigator.geolocation.clearWatch(watchId);
        }
        watchId = navigator.geolocation.watchPosition(
            (position) => {
                lastKnownPosition = position;
                const latLng = [position.coords.latitude, position.coords.longitude];

                if (!positionMarker) {
                    positionMarker = L.circleMarker(latLng, { radius: 8, color: 'blue', fillColor: '#3498db', fillOpacity: 1 }).addTo(map);
                    positionMarker.bindPopup("<b>You are here</b>").openPopup();
                    // Zoom into user position when GPS first locks in
                    map.setView(latLng, 15, { animate: true });
                } else {
                    positionMarker.setLatLng(latLng);
                    map.panTo(latLng);
                }
                updateCurrentTurn(latLng);

                if (convoyRoomId && convoyMemberId) {
                    sendConvoyUpdate(position.coords.latitude, position.coords.longitude).catch((error) => {
                        console.error('Failed to push convoy update:', error);
                    });
                }
            },
            () => {
                showToast('Could not get your location. Live tracking failed.', 'error');
                renderTurnStatus(currentTurnPanel, 'Live tracking unavailable — enable location access for turn-by-turn.');
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    function updateCurrentTurn(currentLatLng) {
        const turnInfo = getCurrentTurnInfo(routeCoordinates, directionSteps, currentLatLng);
        renderCurrentTurn(currentTurnPanel, turnInfo);
    }

    function setInputToCurrentLocation(inputElement, options = {}) {
        const { silent = false } = options;
        if (!navigator.geolocation) {
            if (!silent) showToast('Geolocation is not supported by your browser.', 'error');
            return Promise.reject(new Error('Geolocation is not supported by your browser.'));
        }

        inputElement.placeholder = "Getting location...";

        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(async (position) => {
                const { latitude, longitude } = position.coords;
                const reverseGeocodeUrl = `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`;
                try {
                    const response = await fetch(reverseGeocodeUrl);
                    const data = await response.json();
                    inputElement.value = data.display_name || `${latitude}, ${longitude}`;
                } catch (error) {
                    inputElement.value = `${latitude}, ${longitude}`;
                }
                resolve(inputElement.value);
            }, () => {
                if (!silent) showToast('Unable to retrieve your location.', 'error');
                inputElement.placeholder = "Enter Origin";
                reject(new Error('Unable to retrieve current location.'));
            });
        });
    }

    async function getRouteAndDirections(origin, destination) {
        const apiUrl = buildApiUrl('/find_stops', { origin, destination, query: 'none' });
        const response = await fetch(apiUrl);
        if (!response.ok) throw new Error('Failed to fetch route data.');
        const data = await response.json();

        if (data.route_coordinates) routeCoordinates = data.route_coordinates;
        if (data.directions) directionSteps = data.directions;
        return data;
    }

    function displayRoute(coordinates) {
        routeLayer = L.polyline(coordinates, { color: '#007bff', weight: 5 }).addTo(map);
        const sheetHeight = window.innerWidth <= 640 ? 260 : 0;
        map.fitBounds(routeLayer.getBounds(), {
            paddingBottomRight: [0, sheetHeight],
            paddingTopLeft: [0, 0],
        });
        setTimeout(() => map.invalidateSize(), 120);
    }

    function resetUI() {
        // Intentionally does NOT clear stops/markers — those persist until a new search runs.
        currentTurnPanel.innerHTML = '';
        currentTurnPanel.classList.add('hidden');
        if (routeLayer) map.removeLayer(routeLayer);
        if (positionMarker) {
            map.removeLayer(positionMarker);
            positionMarker = null;
        }
        if (watchId !== null) {
            navigator.geolocation.clearWatch(watchId);
            watchId = null;
        }
        inTripControls.classList.add('hidden');
        controlPanel.classList.remove('navigating');
    }

    async function createConvoy() {
        const destination = destinationInput.value.trim();
        try {
            const { response, data } = await fetchJson(buildApiUrl('/convoy/create'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: convoyNameInput.value.trim() || 'Leader',
                    destination: destination || undefined,
                }),
            });
            if (!response.ok) throw new Error(data.error || 'Unable to create convoy.');
            activateConvoy(data.room_id, data.member_id, data.members || [], data.destination || null);
            showToast(`Convoy created — room ${data.room_id}.`, 'success');
        } catch (error) {
            showToast(error.message || 'Unable to create convoy.', 'error');
        }
    }

    async function joinConvoy() {
        const roomId = convoyRoomInput.value.trim().toUpperCase();
        if (!roomId) {
            showToast('Enter a room code first.', 'error');
            return;
        }
        try {
            const { response, data } = await fetchJson(buildApiUrl('/convoy/join'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    room_id: roomId,
                    name: convoyNameInput.value.trim() || 'Member',
                }),
            });
            if (!response.ok) throw new Error(data.error || 'Unable to join convoy.');
            activateConvoy(data.room_id, data.member_id, data.members || [], data.destination || null);
            showToast(`Joined convoy ${data.room_id}.`, 'success');
        } catch (error) {
            showToast(error.message || 'Unable to join convoy.', 'error');
        }
    }

    function activateConvoy(roomId, memberId, members, destination) {
        convoyRoomId = roomId;
        convoyMemberId = memberId;
        convoySharedDestination = destination || null;
        convoyRoomInput.value = roomId;
        convoySession.classList.remove('hidden');
        convoyActiveRoom.textContent = `Active Room: ${roomId}`;
        renderConvoyMembers(members);

        // Always expand the convoy section when a session is active
        convoyToggleBtn.setAttribute('aria-expanded', 'true');
        convoyBody.classList.remove('section-collapsed');
        // On mobile, expand the sheet so the user can see the convoy info
        if (window.innerWidth <= 640) {
            controlPanel.classList.add('sheet-expanded');
        }

        if (convoySharedDestination) {
            applySharedDestination(convoySharedDestination);
        }

        // Push a first location update immediately if location access is available.
        ensureCurrentLocationForConvoy();

        if (convoyPollTimer) {
            clearInterval(convoyPollTimer);
        }
        convoyPollTimer = setInterval(refreshConvoyState, 5000);
        refreshConvoyState();
    }

    function ensureCurrentLocationForConvoy() {
        if (!convoyRoomId || !convoyMemberId || !navigator.geolocation) {
            return;
        }

        if (lastKnownPosition?.coords) {
            sendConvoyUpdate(lastKnownPosition.coords.latitude, lastKnownPosition.coords.longitude).catch((error) => {
                console.error('Failed to send cached convoy location:', error);
            });
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (position) => {
                lastKnownPosition = position;
                sendConvoyUpdate(position.coords.latitude, position.coords.longitude).catch((error) => {
                    console.error('Failed to send initial convoy location:', error);
                });
            },
            (error) => {
                console.error('Initial convoy geolocation unavailable:', error);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 15000 }
        );
    }

    async function leaveConvoy() {
        if (!convoyRoomId || !convoyMemberId) {
            clearConvoySession();
            return;
        }
        try {
            await fetch(buildApiUrl('/convoy/leave'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ room_id: convoyRoomId, member_id: convoyMemberId }),
            });
        } finally {
            clearConvoySession();
        }
    }

    function clearConvoySession() {
        convoyRoomId = null;
        convoyMemberId = null;
        convoySession.classList.add('hidden');
        convoyActiveRoom.textContent = '';
        convoyMembersUl.innerHTML = '';
        convoyLayer.clearLayers();
        convoyMarkers.clear();
        convoySharedDestination = null;
        convoyAutoRouteInFlight = false;
        if (convoyPollTimer) {
            clearInterval(convoyPollTimer);
            convoyPollTimer = null;
        }
    }

    async function refreshConvoyState() {
        if (!convoyRoomId) {
            return;
        }
        try {
            const { response, data } = await fetchJson(buildApiUrl('/convoy/state', { room_id: convoyRoomId }));
            if (!response.ok) throw new Error(data.error || 'Unable to fetch convoy state.');
            if (data.destination) {
                applySharedDestination(data.destination);
            }
            renderConvoyMembers(data.members || []);
        } catch (error) {
            console.error('Convoy refresh failed:', error);
        }
    }

    async function syncConvoyDestination(destination) {
        const cleanDestination = (destination || '').trim();
        if (!convoyRoomId || !convoyMemberId || !cleanDestination) {
            return;
        }

        convoySharedDestination = cleanDestination;
        await fetchJson(buildApiUrl('/convoy/destination'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                room_id: convoyRoomId,
                member_id: convoyMemberId,
                destination: cleanDestination,
            }),
        });
    }

    function applySharedDestination(sharedDestination) {
        const nextDestination = (sharedDestination || '').trim();
        if (!nextDestination) {
            return;
        }

        const currentDestination = (destinationInput.value || '').trim();
        const isChanged = currentDestination.toLowerCase() !== nextDestination.toLowerCase();
        destinationInput.value = nextDestination;
        convoySharedDestination = nextDestination;

        if (isChanged || routeCoordinates.length === 0) {
            autoStartSharedRouteFromCurrentLocation(nextDestination).catch((error) => {
                console.error('Unable to auto-start shared convoy route:', error);
            });
        }
    }

    async function autoStartSharedRouteFromCurrentLocation(sharedDestination) {
        if (convoyAutoRouteInFlight) {
            return;
        }
        convoyAutoRouteInFlight = true;
        try {
            destinationInput.value = sharedDestination;
            await setInputToCurrentLocation(originInput, { silent: true });
            await startNavigation({ suppressConvoySync: true });
        } finally {
            convoyAutoRouteInFlight = false;
        }
    }

    async function sendConvoyUpdate(lat, lng) {
        if (!convoyRoomId || !convoyMemberId) {
            return;
        }
        await fetch(buildApiUrl('/convoy/update'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                room_id: convoyRoomId,
                member_id: convoyMemberId,
                name: convoyNameInput.value.trim() || 'Member',
                lat,
                lng,
            }),
        });
    }

    function renderConvoyMembers(members) {
        renderConvoyMembersUI({
            members,
            convoyMemberId,
            convoyMembersUl,
            convoyMarkers,
            convoyLayer,
        });
    }
});