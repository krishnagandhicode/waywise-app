let googleMapsLoadPromise = null;

function callbackToPromise(executor) {
    return new Promise((resolve, reject) => {
        executor(resolve, reject);
    });
}

export function loadGoogleMapsApi(apiKey) {
    if (!apiKey) {
        return Promise.reject(new Error('Missing Google Maps API key.'));
    }

    if (window.google?.maps) {
        return Promise.resolve(window.google.maps);
    }

    if (googleMapsLoadPromise) {
        return googleMapsLoadPromise;
    }

    googleMapsLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places`;
        script.async = true;
        script.defer = true;

        script.onload = () => {
            if (window.google?.maps) {
                resolve(window.google.maps);
            } else {
                reject(new Error('Google Maps loaded, but window.google.maps is unavailable.'));
            }
        };

        script.onerror = () => {
            reject(new Error('Failed to load Google Maps JavaScript API.'));
        };

        document.head.appendChild(script);
    });

    return googleMapsLoadPromise;
}

export function createGoogleMap({ mapElementId, center = { lat: 28.6139, lng: 77.2090 }, zoom = 7 }) {
    const mapElement = document.getElementById(mapElementId);
    if (!mapElement) {
        throw new Error(`Map element not found: ${mapElementId}`);
    }

    const map = new google.maps.Map(mapElement, {
        center,
        zoom,
        mapTypeControl: false,
        streetViewControl: false,
    });

    return map;
}

export async function renderGoogleRoute({ map, origin, destination }) {
    const directionsService = new google.maps.DirectionsService();
    const directionsRenderer = new google.maps.DirectionsRenderer({
        map,
        suppressMarkers: false,
        preserveViewport: false,
        polylineOptions: {
            strokeColor: '#0b5be0',
            strokeOpacity: 0.9,
            strokeWeight: 6,
        },
    });

    const result = await callbackToPromise((resolve, reject) => {
        directionsService.route(
            {
                origin,
                destination,
                travelMode: google.maps.TravelMode.DRIVING,
                provideRouteAlternatives: false,
            },
            (response, status) => {
                if (status === google.maps.DirectionsStatus.OK && response) {
                    resolve(response);
                } else {
                    reject(new Error(`Directions failed: ${status}`));
                }
            },
        );
    });

    directionsRenderer.setDirections(result);

    const leg = result.routes?.[0]?.legs?.[0] || null;
    const overviewPath = result.routes?.[0]?.overview_path || [];

    return {
        directionsRenderer,
        routeResponse: result,
        overviewPath,
        summary: {
            startAddress: leg?.start_address || '',
            endAddress: leg?.end_address || '',
            distance: leg?.distance?.text || 'N/A',
            duration: leg?.duration?.text || 'N/A',
        },
    };
}

function sampleRoutePoints(path, maxPoints = 5) {
    if (!Array.isArray(path) || path.length === 0) {
        return [];
    }

    if (path.length <= maxPoints) {
        return path;
    }

    const points = [];
    const step = Math.max(Math.floor(path.length / maxPoints), 1);
    for (let i = 0; i < path.length && points.length < maxPoints; i += step) {
        points.push(path[i]);
    }

    const last = path[path.length - 1];
    const alreadyHasLast = points.some((p) => p.lat() === last.lat() && p.lng() === last.lng());
    if (!alreadyHasLast && points.length < maxPoints + 1) {
        points.push(last);
    }

    return points;
}

function nearbySearch(service, location, keyword, radius) {
    return callbackToPromise((resolve, reject) => {
        service.nearbySearch(
            {
                location,
                radius,
                keyword,
            },
            (results, status) => {
                if (
                    status === google.maps.places.PlacesServiceStatus.OK
                    || status === google.maps.places.PlacesServiceStatus.ZERO_RESULTS
                ) {
                    resolve(results || []);
                } else {
                    reject(new Error(`Places search failed: ${status}`));
                }
            },
        );
    });
}

export async function searchPlacesAlongGoogleRoute({
    map,
    overviewPath,
    query,
    radius = 5000,
    samplePoints = 5,
    maxResults = 12,
}) {
    if (!query) {
        throw new Error('Search query is required.');
    }
    if (!overviewPath || overviewPath.length === 0) {
        throw new Error('Route path is unavailable. Render route first.');
    }

    const placesService = new google.maps.places.PlacesService(map);
    const points = sampleRoutePoints(overviewPath, samplePoints);
    const resultGroups = await Promise.all(
        points.map((point) => nearbySearch(placesService, point, query, radius)),
    );

    const unique = new Map();
    resultGroups.flat().forEach((place) => {
        if (place?.place_id && !unique.has(place.place_id)) {
            unique.set(place.place_id, place);
        }
    });

    return Array.from(unique.values()).slice(0, maxResults);
}

export function renderPlacesList({ places, listElement }) {
    listElement.innerHTML = '';

    if (!places.length) {
        const li = document.createElement('li');
        li.textContent = 'No places found for this route query.';
        listElement.appendChild(li);
        return;
    }

    places.forEach((place) => {
        const li = document.createElement('li');
        const vicinity = place.vicinity ? ` - ${place.vicinity}` : '';
        li.textContent = `${place.name || 'Unnamed place'}${vicinity}`;
        listElement.appendChild(li);
    });
}

export function renderPlaceMarkers({ map, places, existingMarkers = [] }) {
    existingMarkers.forEach((marker) => marker.setMap(null));

    const markers = places
        .filter((place) => place?.geometry?.location)
        .map((place) => {
            const marker = new google.maps.Marker({
                map,
                position: place.geometry.location,
                title: place.name || 'Place',
            });
            return marker;
        });

    return markers;
}
