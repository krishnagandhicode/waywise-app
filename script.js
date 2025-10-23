document.addEventListener('DOMContentLoaded', () => {
    // --- MAP AND ELEMENT REFERENCES ---
    const map = L.map('map').setView([28.6139, 77.2090], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    let routeCoordinates = [];
    let directionSteps = [];
    let routeLayer = null;
    let markersLayer = new L.LayerGroup().addTo(map);
    let positionMarker = null;
    let watchId = null;
    let lastKnownPosition = null;

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

    // --- MAIN FUNCTIONS ---

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
        if (!lastKnownPosition) return alert("Acquiring your location, please try again in a moment.");

        stopsUl.innerHTML = `<li>Searching for '${query}'...</li>`;
        markersLayer.clearLayers();
        customQueryInput.value = ''; // Clear input after search

        const origin = originInput.value;
        const destination = destinationInput.value;
        const { latitude, longitude } = lastKnownPosition.coords;

        try {
            let apiUrl = `http://127.0.0.1:5000/find_stops?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&query=${encodeURIComponent(query)}&live_lat=${latitude}&live_lng=${longitude}`;
            const response = await fetch(apiUrl);
            if (!response.ok) throw new Error('Network response was not ok.');
            const data = await response.json();

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
            stopsUl.innerHTML = '<li>An error occurred while finding stops.</li>';
        }
    }

    function startLiveTracking() {
        if (!navigator.geolocation) return;
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
        const apiUrl = `http://127.0.0.1:5000/find_stops?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&query=none`;
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
        if (watchId) {
            navigator.geolocation.clearWatch(watchId);
            watchId = null;
        }
        inTripControls.classList.add('hidden');
    }
});