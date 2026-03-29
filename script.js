document.addEventListener('DOMContentLoaded', () => {
    const API_BASE = window.location.origin;

    function buildApiUrl(path, params = {}) {
        const url = new URL(path, API_BASE);
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                url.searchParams.set(key, value);
            }
        });
        return url.toString();
    }

    function setStopSearchLoading(isLoading) {
        const stopBtns = document.querySelectorAll('.stop-btn');
        stopBtns.forEach((btn) => {
            btn.disabled = isLoading;
        });
        customQueryBtn.disabled = isLoading;
    }

    // --- MAP AND ELEMENT REFERENCES ---
    const map = L.map('map').setView([28.6139, 77.2090], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    let routeCoordinates = [];
    let directionSteps = [];
    let routeLayer = null;
    let markersLayer = new L.LayerGroup().addTo(map);
    let convoyLayer = new L.LayerGroup().addTo(map);
    let positionMarker = null;
    let watchId = null;
    let lastKnownPosition = null;
    let convoyRoomId = null;
    let convoyMemberId = null;
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

    // --- EVENT LISTENERS ---

    currentLocationOriginBtn.addEventListener('click', () => setInputToCurrentLocation(originInput));
    currentLocationDestBtn.addEventListener('click', () => setInputToCurrentLocation(destinationInput));
    startNavBtn.addEventListener('click', startNavigation);

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
            alert('Please enter something to search for.');
        }
    });

    customQueryInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            customQueryBtn.click();
        }
    });

    convoyCreateBtn.addEventListener('click', createConvoy);
    convoyJoinBtn.addEventListener('click', joinConvoy);
    convoyLeaveBtn.addEventListener('click', leaveConvoy);

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
            const response = await fetch(buildApiUrl('/health'));
            if (!response.ok) {
                throw new Error('Health check failed');
            }
            const data = await response.json();
            backendStatus.classList.remove('status-bad');
            backendStatus.classList.add('status-good');
            backendStatus.textContent = `Backend: online | Provider: ${data.provider} | Mock: ${data.mock_mode ? 'yes' : 'no'}`;
        } catch (error) {
            backendStatus.classList.remove('status-good');
            backendStatus.classList.add('status-bad');
            backendStatus.textContent = 'Backend: offline or unreachable';
        }
    }

    async function startNavigation() {
        const origin = originInput.value;
        const destination = destinationInput.value;
        if (!origin || !destination) return alert('Please fill out Origin and Destination.');

        startNavBtn.textContent = 'Calculating Route...';
        startNavBtn.disabled = true;
        resetUI();

        try {
            const routeData = await getRouteAndDirections(origin, destination);
            if (routeData.route_coordinates) {
                displayRoute(routeData.route_coordinates);
                inTripControls.classList.remove('hidden');
                currentTurnPanel.classList.remove('hidden');
                startLiveTracking();
            } else {
                alert('Could not find a route.');
            }
        } catch (error) {
            console.error('Error starting navigation:', error);
            alert('Could not start navigation. Please try again.');
        } finally {
            startNavBtn.textContent = 'Start Navigation';
            startNavBtn.disabled = false;
        }
    }

    async function findAndDisplayStops(query) {
        stopsUl.innerHTML = `<li>Searching for '${query}'...</li>`;
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
            const response = await fetch(apiUrl);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Stop search failed.');

            stopsUl.innerHTML = '';
            if (data.stops && data.stops.length > 0) {
                data.stops.forEach(stop => {
                    const marker = L.marker([stop.location.lat, stop.location.lng]).addTo(markersLayer);
                    marker.bindPopup(`<b>${stop.name}</b><br>Rating: ${stop.rating}<br>Distance: ${stop.distance}<br>Duration: ${stop.duration}`);
                    const li = document.createElement('li');
                    li.innerHTML = `<strong>${stop.name}</strong><br>Rating: ${stop.rating || 'N/A'}<br>Distance: ${stop.distance} | Duration: ${stop.duration}`;
                    stopsUl.appendChild(li);
                });
            } else {
                stopsUl.innerHTML = `<li>No on-route results found for '${query}'.</li>`;
            }
        } catch (error) {
            console.error("Error finding stops:", error);
            stopsUl.innerHTML = `<li>${error.message || 'An error occurred while finding stops.'}</li>`;
        } finally {
            setStopSearchLoading(false);
        }
    }

    function startLiveTracking() {
        if (!navigator.geolocation) return;
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
                } else {
                    positionMarker.setLatLng(latLng);
                }
                map.panTo(latLng);
                updateCurrentTurn(latLng);

                if (convoyRoomId && convoyMemberId) {
                    sendConvoyUpdate(position.coords.latitude, position.coords.longitude).catch((error) => {
                        console.error('Failed to push convoy update:', error);
                    });
                }
            },
            () => { alert("Could not get your location. Live tracking failed."); },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    function updateCurrentTurn(currentLatLng) {
        if (routeCoordinates.length === 0 || directionSteps.length === 0) return;

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

        const currentInstruction = directionSteps[currentStepIndex];
        const nextInstruction = directionSteps[currentStepIndex + 1] || "You are nearing your destination.";

        currentTurnPanel.innerHTML = `
            <p class="turn-instruction">${currentInstruction}</p>
            <p class="next-turn-info">Next: ${nextInstruction}</p>
        `;
    }

    function setInputToCurrentLocation(inputElement) {
        if (!navigator.geolocation) return alert("Geolocation is not supported by your browser.");
        inputElement.placeholder = "Getting location...";
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
        }, () => {
            alert("Unable to retrieve your location.");
            inputElement.placeholder = "Enter Origin";
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
        map.fitBounds(routeLayer.getBounds());
        setTimeout(() => map.invalidateSize(), 120);
    }

    function resetUI() {
        stopsUl.innerHTML = '';
        currentTurnPanel.innerHTML = '';
        currentTurnPanel.classList.add('hidden');
        if (routeLayer) map.removeLayer(routeLayer);
        markersLayer.clearLayers();
        if (positionMarker) {
            map.removeLayer(positionMarker);
            positionMarker = null;
        }
        if (watchId !== null) {
            navigator.geolocation.clearWatch(watchId);
            watchId = null;
        }
        inTripControls.classList.add('hidden');
    }

    async function createConvoy() {
        try {
            const response = await fetch(buildApiUrl('/convoy/create'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: convoyNameInput.value.trim() || 'Leader' }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Unable to create convoy.');
            activateConvoy(data.room_id, data.member_id, data.members || []);
        } catch (error) {
            alert(error.message || 'Unable to create convoy.');
        }
    }

    async function joinConvoy() {
        const roomId = convoyRoomInput.value.trim().toUpperCase();
        if (!roomId) {
            alert('Enter a room code first.');
            return;
        }
        try {
            const response = await fetch(buildApiUrl('/convoy/join'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    room_id: roomId,
                    name: convoyNameInput.value.trim() || 'Member',
                }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Unable to join convoy.');
            activateConvoy(data.room_id, data.member_id, data.members || []);
        } catch (error) {
            alert(error.message || 'Unable to join convoy.');
        }
    }

    function activateConvoy(roomId, memberId, members) {
        convoyRoomId = roomId;
        convoyMemberId = memberId;
        convoyRoomInput.value = roomId;
        convoySession.classList.remove('hidden');
        convoyActiveRoom.textContent = `Active Room: ${roomId}`;
        renderConvoyMembers(members);

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
            const response = await fetch(buildApiUrl('/convoy/state', { room_id: convoyRoomId }));
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Unable to fetch convoy state.');
            renderConvoyMembers(data.members || []);
        } catch (error) {
            console.error('Convoy refresh failed:', error);
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

    function getMemberJitter(memberId) {
        let hash = 0;
        for (let i = 0; i < memberId.length; i += 1) {
            hash = ((hash << 5) - hash) + memberId.charCodeAt(i);
            hash |= 0;
        }
        const latOffset = ((hash % 7) - 3) * 0.00004;
        const lngOffset = (((Math.floor(hash / 7)) % 7) - 3) * 0.00004;
        return [latOffset, lngOffset];
    }

    function renderConvoyMembers(members) {
        convoyMembersUl.innerHTML = '';
        const activeMemberIds = new Set();

        members.forEach((member) => {
            const isMe = member.member_id === convoyMemberId;
            const name = member.name || 'Member';
            const label = isMe ? `${name} (You)` : name;

            const item = document.createElement('li');
            if (member.lat == null || member.lng == null) {
                item.textContent = `${label}: waiting for location...`;
            } else {
                const baseLat = Number(member.lat);
                const baseLng = Number(member.lng);
                const [latOffset, lngOffset] = getMemberJitter(member.member_id);
                const markerLatLng = isMe ? [baseLat, baseLng] : [baseLat + latOffset, baseLng + lngOffset];

                item.textContent = `${label}: ${baseLat.toFixed(5)}, ${baseLng.toFixed(5)}`;

                let marker = convoyMarkers.get(member.member_id);
                if (!marker) {
                    marker = L.circleMarker(markerLatLng, {
                        radius: isMe ? 10 : 8,
                        color: isMe ? '#1d4ed8' : '#9a3412',
                        fillColor: isMe ? '#2563eb' : '#f97316',
                        fillOpacity: 0.95,
                        weight: 2,
                    }).addTo(convoyLayer);
                    convoyMarkers.set(member.member_id, marker);
                } else {
                    marker.setLatLng(markerLatLng);
                    marker.setStyle({
                        radius: isMe ? 10 : 8,
                        color: isMe ? '#1d4ed8' : '#9a3412',
                        fillColor: isMe ? '#2563eb' : '#f97316',
                        fillOpacity: 0.95,
                        weight: 2,
                    });
                }

                marker.bindPopup(`<b>${label}</b><br>${baseLat.toFixed(5)}, ${baseLng.toFixed(5)}`);
                marker.bindTooltip(label, {
                    permanent: true,
                    direction: 'top',
                    offset: [0, -12],
                    className: 'convoy-label',
                });
                marker.bringToFront();
                activeMemberIds.add(member.member_id);
            }
            convoyMembersUl.appendChild(item);
        });

        for (const [memberId, marker] of convoyMarkers.entries()) {
            if (!activeMemberIds.has(memberId)) {
                convoyLayer.removeLayer(marker);
                convoyMarkers.delete(memberId);
            }
        }
    }
});