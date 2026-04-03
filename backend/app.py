import os
import time
import requests
import re
import copy
from pathlib import Path
from threading import Lock
from uuid import uuid4
from flask import Flask, request, jsonify, send_from_directory, render_template
from dotenv import load_dotenv
import polyline
from haversine import haversine, Unit
from flask_cors import CORS

# Path configuration
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# Initialize Flask App
app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
CORS(app)

# API Configuration
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
DISTANCE_MATRIX_API_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
MAP_PROVIDER = os.getenv("WAYWISE_MAP_PROVIDER", "free").strip().lower()
NOMINATIM_SEARCH_URL = os.getenv("NOMINATIM_SEARCH_URL", "https://nominatim.openstreetmap.org/search")
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
OVERPASS_API_URL = os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_API_URLS = [
    endpoint.strip()
    for endpoint in os.getenv(
        "OVERPASS_API_URLS",
        f"{OVERPASS_API_URL},https://overpass.kumi.systems/api/interpreter,https://overpass.openstreetmap.fr/api/interpreter",
    ).split(",")
    if endpoint.strip()
]
FREE_ROUTE_SEARCH_INTERVAL = int(os.getenv("FREE_ROUTE_SEARCH_INTERVAL", "220"))
FREE_STOP_SEARCH_RADIUS_METERS = int(os.getenv("FREE_STOP_SEARCH_RADIUS_METERS", "1200"))
FREE_MAX_SEARCH_POINTS = int(os.getenv("FREE_MAX_SEARCH_POINTS", "8"))
FREE_OVERPASS_QUERY_TIMEOUT_SECONDS = int(os.getenv("FREE_OVERPASS_QUERY_TIMEOUT_SECONDS", "8"))
FREE_OVERPASS_HTTP_TIMEOUT_SECONDS = int(os.getenv("FREE_OVERPASS_HTTP_TIMEOUT_SECONDS", "7"))
FREE_OVERPASS_ELEMENT_LIMIT = int(os.getenv("FREE_OVERPASS_ELEMENT_LIMIT", "25"))
FREE_MAX_CANDIDATES = int(os.getenv("FREE_MAX_CANDIDATES", "180"))
FREE_MAX_RANK_DESTINATIONS = int(os.getenv("FREE_MAX_RANK_DESTINATIONS", "8"))
STOPS_RESPONSE_LIMIT = int(os.getenv("STOPS_RESPONSE_LIMIT", "8"))
STOP_CACHE_TTL_SECONDS = int(os.getenv("STOP_CACHE_TTL_SECONDS", "240"))
RANKED_STOPS_CACHE_TTL_SECONDS = int(os.getenv("RANKED_STOPS_CACHE_TTL_SECONDS", "45"))
GEOCODE_CACHE_TTL_SECONDS = int(os.getenv("GEOCODE_CACHE_TTL_SECONDS", "1800"))
MOCK_MODE = os.getenv("WAYWISE_MOCK_MODE", "false").lower() in ("1", "true", "yes", "on")
ROUTE_CACHE_TTL_SECONDS = int(os.getenv("ROUTE_CACHE_TTL_SECONDS", "900"))
DISTANCE_MATRIX_MAX_DESTINATIONS = int(os.getenv("DISTANCE_MATRIX_MAX_DESTINATIONS", "25"))
BACKTRACK_PENALTY_SECONDS = int(os.getenv("BACKTRACK_PENALTY_SECONDS", "900"))
ROUTE_ONLY_QUERIES = {"none", "route_only", "__route_only__"}

route_cache = {}
stop_candidate_cache = {}
ranked_stops_cache = {}
geocode_cache = {}
OVERPASS_PREFERRED_INDEX = 0
HTTP_HEADERS = {"User-Agent": "WayWise/1.0 (educational testing)"}
CONVOY_MEMBER_TTL_SECONDS = int(os.getenv("CONVOY_MEMBER_TTL_SECONDS", "300"))
CONVOY_ROOM_TTL_SECONDS = int(os.getenv("CONVOY_ROOM_TTL_SECONDS", "86400"))
convoy_rooms = {}
convoy_lock = Lock()
MOCK_LOCATION_HINTS = {
    "chandigarh": (30.7333, 76.7794),
    "s.a.s. nagar": (30.7046, 76.7179),
    "sas nagar": (30.7046, 76.7179),
    "mohali": (30.7046, 76.7179),
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "gurgaon": (28.4595, 77.0266),
    "noida": (28.5355, 77.3910),
    "shimla": (31.1048, 77.1734),
}

# --- HELPER FUNCTIONS ---

def is_free_provider_enabled():
    return MAP_PROVIDER in {"free", "osm", "osrm"}

def cleanup_stop_candidate_cache(now=None):
    current_time = now or time.time()
    stale_keys = [
        key
        for key, value in stop_candidate_cache.items()
        if current_time - value.get("timestamp", 0) > STOP_CACHE_TTL_SECONDS
    ]
    for key in stale_keys:
        stop_candidate_cache.pop(key, None)

    stale_ranked_keys = [
        key
        for key, value in ranked_stops_cache.items()
        if current_time - value.get("timestamp", 0) > RANKED_STOPS_CACHE_TTL_SECONDS
    ]
    for key in stale_ranked_keys:
        ranked_stops_cache.pop(key, None)

def cleanup_geocode_cache(now=None):
    current_time = now or time.time()
    stale_keys = [
        key
        for key, value in geocode_cache.items()
        if current_time - value.get("timestamp", 0) > GEOCODE_CACHE_TTL_SECONDS
    ]
    for key in stale_keys:
        geocode_cache.pop(key, None)

def get_stop_cache_key(origin, destination, place_query):
    return f"{MAP_PROVIDER}::{origin.strip().lower()}::{destination.strip().lower()}::{(place_query or '').strip().lower()}"

def get_ranked_stops_cache_key(origin, destination, place_query, live_lat, live_lng):
    lat_bucket = "none"
    lng_bucket = "none"
    if live_lat is not None and live_lng is not None:
        try:
            lat_bucket = f"{float(live_lat):.3f}"
            lng_bucket = f"{float(live_lng):.3f}"
        except (TypeError, ValueError):
            pass
    return f"{get_stop_cache_key(origin, destination, place_query)}::{lat_bucket}::{lng_bucket}"

def get_free_search_point_limit(place_query):
    q = (place_query or "").lower()
    if "petrol" in q or "fuel" in q or "atm" in q or "bank" in q:
        return min(FREE_MAX_SEARCH_POINTS, 4)
    if "restaurant" in q or "dhaba" in q or "food" in q:
        return min(FREE_MAX_SEARCH_POINTS, 5)
    return FREE_MAX_SEARCH_POINTS

def parse_live_coordinates(raw_lat, raw_lng):
    if raw_lat is None and raw_lng is None:
        return None, None
    if raw_lat is None or raw_lng is None:
        raise ValueError("Both live_lat and live_lng are required together")

    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
    except (TypeError, ValueError) as exc:
        raise ValueError("live_lat and live_lng must be valid numbers") from exc

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("live_lat/live_lng out of range")
    return lat, lng

def parse_ranking_origin_coords(ranking_origin):
    try:
        lng_text, lat_text = ranking_origin.split(",")
        return float(lat_text), float(lng_text)
    except (ValueError, AttributeError):
        return None, None

def cleanup_stale_convoys(now=None):
    """Evicts stale members/rooms from in-memory convoy storage."""
    current_time = now or time.time()
    with convoy_lock:
        rooms_to_delete = []
        for room_id, room in convoy_rooms.items():
            stale_members = []
            for member_id, member in room["members"].items():
                if current_time - member["updated_at"] > CONVOY_MEMBER_TTL_SECONDS:
                    stale_members.append(member_id)
            for member_id in stale_members:
                room["members"].pop(member_id, None)

            room_age = current_time - room["created_at"]
            if not room["members"] or room_age > CONVOY_ROOM_TTL_SECONDS:
                rooms_to_delete.append(room_id)

        for room_id in rooms_to_delete:
            convoy_rooms.pop(room_id, None)

def serialize_room_members(room):
    return [
        {
            "member_id": member_id,
            "name": member.get("name") or "Member",
            "lat": member.get("lat"),
            "lng": member.get("lng"),
            "updated_at": member.get("updated_at"),
        }
        for member_id, member in room["members"].items()
    ]

def strip_html_tags(text):
    return re.sub(r"<[^>]*>", "", text or "")

def format_duration(seconds):
    seconds = int(max(seconds, 0))
    mins = seconds // 60
    if mins < 60:
        return f"{mins} mins"
    hours = mins // 60
    rem_mins = mins % 60
    if rem_mins == 0:
        return f"{hours} hr"
    return f"{hours} hr {rem_mins} mins"

def format_distance(meters):
    meters = float(max(meters, 0))
    if meters < 1000:
        return f"{int(round(meters))} m"
    return f"{meters / 1000:.1f} km"

def geocode_with_nominatim(location_text):
    normalized = (location_text or "").strip().lower()
    if not normalized:
        return None

    cached = geocode_cache.get(normalized)
    if cached and (time.time() - cached["timestamp"] <= GEOCODE_CACHE_TTL_SECONDS):
        return dict(cached["value"])

    params = {
        "q": location_text,
        "format": "jsonv2",
        "limit": 1,
    }
    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params=params,
        headers=HTTP_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not data:
        return None

    result = {
        "lat": float(data[0]["lat"]),
        "lng": float(data[0]["lon"]),
    }
    geocode_cache[normalized] = {
        "timestamp": time.time(),
        "value": result,
    }
    return dict(result)

def get_route_with_google(origin, destination):
    params = {"origin": origin, "destination": destination, "key": API_KEY}
    response = requests.get(DIRECTIONS_API_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    if data['status'] == 'OK' and data.get('routes'):
        route = data['routes'][0]['legs'][0]
        encoded_polyline = data['routes'][0]['overview_polyline']['points']
        decoded_coordinates = polyline.decode(encoded_polyline)
        direction_steps = [strip_html_tags(step.get('html_instructions')) for step in route.get('steps', [])]
        return decoded_coordinates, direction_steps
    return None, None

def get_route_with_osrm(origin, destination):
    origin_geo = geocode_with_nominatim(origin)
    destination_geo = geocode_with_nominatim(destination)
    if not origin_geo or not destination_geo:
        return None, None

    coords = f"{origin_geo['lng']},{origin_geo['lat']};{destination_geo['lng']},{destination_geo['lat']}"
    route_url = f"{OSRM_BASE_URL}/route/v1/driving/{coords}"
    params = {
        "overview": "full",
        "geometries": "polyline",
        "steps": "true",
    }
    response = requests.get(route_url, params=params, headers=HTTP_HEADERS, timeout=15)
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        return None, None

    encoded = data["routes"][0].get("geometry")
    if not encoded:
        return None, None

    decoded_coordinates = polyline.decode(encoded)
    direction_steps = []
    for leg in data["routes"][0].get("legs", []):
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {}).get("type", "continue")
            road = step.get("name")
            if road:
                direction_steps.append(f"{maneuver.title()} on {road}")
            else:
                direction_steps.append(maneuver.title())

    if not direction_steps:
        direction_steps = ["Proceed on the route", "Continue towards destination"]

    return decoded_coordinates, direction_steps

def get_overpass_filter_for_query(place_query):
    q = (place_query or "").lower()
    if "petrol" in q or "fuel" in q:
        return '["amenity"="fuel"]'
    if "atm" in q or "bank" in q:
        return '["amenity"="atm"]'
    if "hospital" in q:
        return '["amenity"="hospital"]'
    if "hotel" in q:
        return '["tourism"="hotel"]'
    if "dhaba" in q or "restaurant" in q or "food" in q:
        return '["amenity"~"restaurant|fast_food|cafe"]'
    return '["amenity"~"restaurant|fast_food|cafe|fuel|atm"]'

def find_places_with_overpass(route_coordinates, place_query):
    global OVERPASS_PREFERRED_INDEX

    if not route_coordinates:
        return {}, False

    all_candidates = {}
    any_successful_response = False
    overpass_filter = get_overpass_filter_for_query(place_query)

    sampled_indices = list(range(0, len(route_coordinates), FREE_ROUTE_SEARCH_INTERVAL))
    if sampled_indices and sampled_indices[-1] != len(route_coordinates) - 1:
        sampled_indices.append(len(route_coordinates) - 1)
    sampled_indices = sampled_indices[:get_free_search_point_limit(place_query)]

    for i in sampled_indices:
        point = route_coordinates[i]
        lat, lng = point[0], point[1]
        overpass_query = f"""
        [out:json][timeout:{FREE_OVERPASS_QUERY_TIMEOUT_SECONDS}];
        (
          node(around:{FREE_STOP_SEARCH_RADIUS_METERS},{lat},{lng}){overpass_filter};
          way(around:{FREE_STOP_SEARCH_RADIUS_METERS},{lat},{lng}){overpass_filter};
        );
        out center {FREE_OVERPASS_ELEMENT_LIMIT};
        """
        data = None
        if OVERPASS_API_URLS:
            ordered_urls = OVERPASS_API_URLS[OVERPASS_PREFERRED_INDEX:] + OVERPASS_API_URLS[:OVERPASS_PREFERRED_INDEX]
        else:
            ordered_urls = []

        for offset, overpass_url in enumerate(ordered_urls):
            try:
                response = requests.get(
                    overpass_url,
                    params={"data": overpass_query},
                    headers=HTTP_HEADERS,
                    timeout=FREE_OVERPASS_HTTP_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                data = response.json()
                any_successful_response = True
                if OVERPASS_API_URLS:
                    OVERPASS_PREFERRED_INDEX = (OVERPASS_PREFERRED_INDEX + offset) % len(OVERPASS_API_URLS)
                break
            except (requests.exceptions.RequestException, ValueError):
                continue

        if not data:
            continue

        for element in data.get("elements", []):
            element_id = f"{element.get('type', 'node')}_{element.get('id')}"
            tags = element.get("tags", {})
            center = element.get("center", {})
            lat_v = element.get("lat", center.get("lat"))
            lng_v = element.get("lon", center.get("lon"))
            if lat_v is None or lng_v is None:
                continue

            all_candidates[element_id] = {
                "name": tags.get("name", "Unnamed place"),
                "rating": "N/A",
                "place_id": element_id,
                "location": {"lat": lat_v, "lng": lng_v},
            }

            if len(all_candidates) >= FREE_MAX_CANDIDATES:
                return all_candidates, (not any_successful_response)

        if len(all_candidates) >= STOPS_RESPONSE_LIMIT * 6:
            return all_candidates, (not any_successful_response)

    return all_candidates, (not any_successful_response)

def rank_stops_with_osrm_table(stops, ranking_origin):
    if not stops:
        return stops

    destinations = [f"{stop['location']['lng']},{stop['location']['lat']}" for stop in stops]
    all_coords = ";".join([ranking_origin] + destinations)
    table_url = f"{OSRM_BASE_URL}/table/v1/driving/{all_coords}"
    params = {
        "sources": "0",
        "annotations": "duration,distance",
    }

    response = requests.get(table_url, params=params, headers=HTTP_HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok":
        return stops

    durations = data.get("durations", [[]])[0]
    distances = data.get("distances", [[]])[0]

    for i, stop in enumerate(stops, start=1):
        duration_seconds = durations[i] if i < len(durations) and durations[i] is not None else None
        distance_meters = distances[i] if i < len(distances) and distances[i] is not None else None
        if duration_seconds is not None:
            stop['duration_seconds'] = int(duration_seconds)
            stop['duration'] = format_duration(duration_seconds)
        if distance_meters is not None:
            stop['distance'] = format_distance(distance_meters)
        stop['score_seconds'] = stop.get('duration_seconds', 99999) + stop.get('backtrack_penalty_seconds', 0)

    stops.sort(key=lambda x: x.get('score_seconds', x.get('duration_seconds', 99999)))
    return stops

def rank_stops_with_fallback(stops, ranking_origin):
    """Fallback ranking when external matrix APIs fail."""
    if not stops:
        return stops

    origin_lat, origin_lng = parse_ranking_origin_coords(ranking_origin)
    if origin_lat is None or origin_lng is None:
        for stop in stops:
            stop['score_seconds'] = stop.get('duration_seconds', 99999) + stop.get('backtrack_penalty_seconds', 0)
        stops.sort(key=lambda x: x.get('score_seconds', x.get('duration_seconds', 99999)))
        return stops

    origin_coords = (origin_lat, origin_lng)
    # Approximate local-road effective speed for fallback ETA.
    avg_speed_mps = 11.11  # ~40 km/h
    for stop in stops:
        stop_coords = (stop['location']['lat'], stop['location']['lng'])
        distance_meters = haversine(origin_coords, stop_coords, unit=Unit.METERS)
        duration_seconds = int(max(distance_meters / avg_speed_mps, 60))
        stop['distance'] = format_distance(distance_meters)
        stop['duration_seconds'] = duration_seconds
        stop['duration'] = format_duration(duration_seconds)
        stop['score_seconds'] = duration_seconds + stop.get('backtrack_penalty_seconds', 0)

    stops.sort(key=lambda x: x.get('score_seconds', x.get('duration_seconds', 99999)))
    return stops

def get_decoded_route(origin, destination):
    """Fetches and decodes the route, and also extracts direction steps."""
    cache_key = f"{MAP_PROVIDER}::{origin.strip().lower()}::{destination.strip().lower()}"
    cached = route_cache.get(cache_key)
    if cached and (time.time() - cached["timestamp"] <= ROUTE_CACHE_TTL_SECONDS):
        return cached["coordinates"], cached["direction_steps"]

    if is_free_provider_enabled():
        decoded_coordinates, direction_steps = get_route_with_osrm(origin, destination)
    else:
        decoded_coordinates, direction_steps = get_route_with_google(origin, destination)

    if decoded_coordinates and direction_steps:
        route_cache[cache_key] = {
            "timestamp": time.time(),
            "coordinates": decoded_coordinates,
            "direction_steps": direction_steps,
        }
        return decoded_coordinates, direction_steps

    return None, None

def resolve_mock_location(location_text, fallback):
    """Resolves common city/location text to a mock coordinate."""
    if not location_text:
        return fallback
    normalized = location_text.strip().lower()
    for hint, coords in MOCK_LOCATION_HINTS.items():
        if hint in normalized:
            return coords
    return fallback

def interpolate_mock_route(start_coords, end_coords, steps=16):
    """Builds a simple interpolated route between two coordinates."""
    route = []
    for i in range(steps + 1):
        t = i / steps
        lat = start_coords[0] + (end_coords[0] - start_coords[0]) * t
        lng = start_coords[1] + (end_coords[1] - start_coords[1]) * t
        route.append((round(lat, 6), round(lng, 6)))
    return route

def get_mock_route_and_directions(origin, destination):
    """Returns route-like mock data aligned to input origin/destination."""
    start = resolve_mock_location(origin, (30.7333, 76.7794))
    end = resolve_mock_location(destination, (28.6139, 77.2090))
    route_coordinates = interpolate_mock_route(start, end)

    lat_diff = end[0] - start[0]
    lng_diff = end[1] - start[1]
    primary_ns = "south" if lat_diff < 0 else "north"
    primary_ew = "east" if lng_diff > 0 else "west"
    direction_steps = [
        f"Head {primary_ew} from origin",
        f"Continue {primary_ns}-{primary_ew} on the main corridor",
        "Stay on the suggested route",
        "Keep following signs toward destination",
        "You are nearing your destination",
    ]
    return route_coordinates, direction_steps

def get_mock_stops(place_query):
    """Returns deterministic mock places sorted by mock detour duration."""
    q = place_query.lower()
    if "dhaba" in q:
        return [
            {"name": "Pind Punjab Dhaba", "rating": 4.3, "distance": "2.8 km", "duration": "6 mins", "duration_seconds": 360, "place_id": "mock_dhaba_1", "location": {"lat": 31.0842, "lng": 76.9716}},
            {"name": "Highway King Dhaba", "rating": 4.1, "distance": "4.1 km", "duration": "9 mins", "duration_seconds": 540, "place_id": "mock_dhaba_2", "location": {"lat": 31.2758, "lng": 77.1094}},
        ]
    if "petrol" in q:
        return [
            {"name": "FuelX Petrol Pump", "rating": 4.0, "distance": "1.6 km", "duration": "4 mins", "duration_seconds": 240, "place_id": "mock_petrol_1", "location": {"lat": 31.0842, "lng": 76.9716}},
            {"name": "HP Highway Fuel", "rating": 3.9, "distance": "3.4 km", "duration": "7 mins", "duration_seconds": 420, "place_id": "mock_petrol_2", "location": {"lat": 31.4687, "lng": 77.2292}},
        ]
    if "atm" in q:
        return [
            {"name": "SBI ATM", "rating": "N/A", "distance": "1.2 km", "duration": "3 mins", "duration_seconds": 180, "place_id": "mock_atm_1", "location": {"lat": 30.9021, "lng": 76.8457}},
            {"name": "HDFC ATM", "rating": "N/A", "distance": "2.5 km", "duration": "5 mins", "duration_seconds": 300, "place_id": "mock_atm_2", "location": {"lat": 31.6535, "lng": 77.3220}},
        ]
    return [
        {"name": "Route Cafe", "rating": 4.2, "distance": "2.1 km", "duration": "5 mins", "duration_seconds": 300, "place_id": "mock_generic_1", "location": {"lat": 31.2758, "lng": 77.1094}},
        {"name": "Traveler's Stop", "rating": 4.0, "distance": "3.0 km", "duration": "7 mins", "duration_seconds": 420, "place_id": "mock_generic_2", "location": {"lat": 31.4687, "lng": 77.2292}},
    ]

def is_on_route(place_location, route_coordinates, max_distance_meters=1500):
    """Checks if a place is within a max distance from any point on the route."""
    place_coords = (place_location['lat'], place_location['lng'])
    for route_point in route_coordinates:
        route_point_coords = (route_point[0], route_point[1])
        distance = haversine(place_coords, route_point_coords, unit=Unit.METERS)
        if distance <= max_distance_meters:
            return True
    return False

def get_closest_route_index(place_location, route_coordinates):
    """Finds the nearest polyline index for a lat/lng point."""
    place_coords = (place_location['lat'], place_location['lng'])
    min_distance = float('inf')
    closest_index = 0
    for idx, route_point in enumerate(route_coordinates):
        route_point_coords = (route_point[0], route_point[1])
        distance = haversine(place_coords, route_point_coords, unit=Unit.METERS)
        if distance < min_distance:
            min_distance = distance
            closest_index = idx
    return closest_index

# --- STATIC/STATUS ENDPOINTS ---

@app.route('/', methods=['GET'])
def serve_index():
    return render_template('index.html')

@app.route('/google-baseline', methods=['GET'])
def serve_google_baseline():
    js_api_key = os.getenv("GOOGLE_MAPS_JS_API_KEY", API_KEY)
    return render_template('google-baseline.html', google_maps_js_api_key=js_api_key)

@app.route('/script.js', methods=['GET'])
def serve_script():
    return send_from_directory(str(STATIC_DIR / 'js'), 'script.js')

@app.route('/style.css', methods=['GET'])
def serve_style():
    return send_from_directory(str(STATIC_DIR / 'css'), 'style.css')

@app.route('/health', methods=['GET'])
def health():
    cleanup_geocode_cache()
    cleanup_stop_candidate_cache()
    cleanup_stale_convoys()
    with convoy_lock:
        active_convoy_rooms = len(convoy_rooms)
    return jsonify({
        "status": "ok",
        "provider": MAP_PROVIDER,
        "mock_mode": MOCK_MODE,
        "route_cache_entries": len(route_cache),
        "stop_cache_entries": len(stop_candidate_cache),
        "ranked_stop_cache_entries": len(ranked_stops_cache),
        "geocode_cache_entries": len(geocode_cache),
        "active_convoy_rooms": active_convoy_rooms,
        "timestamp": int(time.time()),
    })

# --- API ENDPOINTS ---

@app.route('/find_stops', methods=['GET'])
def find_stops():
    """Main endpoint to find on-route stops for a given journey."""
    origin = request.args.get('origin')
    destination = request.args.get('destination')
    place_query = (request.args.get('query') or '').strip()
    live_lat_raw = request.args.get('live_lat')
    live_lng_raw = request.args.get('live_lng')
    route_only = place_query.lower() in ROUTE_ONLY_QUERIES

    if not all([origin, destination]):
        return jsonify({"error": "Missing required parameters: origin, destination"}), 400
    if not route_only and not place_query:
        return jsonify({"error": "Missing required parameter: query"}), 400

    try:
        live_lat, live_lng = parse_live_coordinates(live_lat_raw, live_lng_raw)
        cleanup_geocode_cache()
        cleanup_stop_candidate_cache()

        if MOCK_MODE:
            route_coordinates, direction_steps = get_mock_route_and_directions(origin, destination)
            mock_stops = [] if route_only else get_mock_stops(place_query)

            if mock_stops and live_lat and live_lng:
                current_route_index = get_closest_route_index(
                    {"lat": live_lat, "lng": live_lng},
                    route_coordinates,
                )
                for stop in mock_stops:
                    stop_route_index = get_closest_route_index(stop["location"], route_coordinates)
                    backtrack_penalty_seconds = BACKTRACK_PENALTY_SECONDS if stop_route_index < current_route_index else 0
                    stop["ahead_of_user"] = backtrack_penalty_seconds == 0
                    stop["backtrack_penalty_seconds"] = backtrack_penalty_seconds
                    stop["score_seconds"] = stop.get("duration_seconds", 99999) + backtrack_penalty_seconds

            return jsonify({
                "status": "success",
                "mock_mode": True,
                "search_query": place_query,
                "on_route_stops_found": len(mock_stops),
                "stops": sorted(mock_stops, key=lambda x: x.get('score_seconds', x.get('duration_seconds', 99999))),
                "route_coordinates": route_coordinates,
                "directions": direction_steps
            })

        route_coordinates, direction_steps = get_decoded_route(origin, destination)

        if not route_coordinates:
            if route_only:
                # Keep baseline navigation testable even if live Directions fails.
                mock_route_coordinates, mock_direction_steps = get_mock_route_and_directions(origin, destination)
                return jsonify({
                    "status": "success",
                    "mock_mode": True,
                    "fallback_mock_route": True,
                    "search_query": place_query,
                    "on_route_stops_found": 0,
                    "stops": [],
                    "route_coordinates": mock_route_coordinates,
                    "directions": mock_direction_steps,
                })
            return jsonify({"error": "Could not find a route between the specified locations"}), 404

        # Route bootstrap requests should never trigger Places or Matrix calls.
        if route_only:
            return jsonify({
                "status": "success",
                "search_query": place_query,
                "on_route_stops_found": 0,
                "stops": [],
                "route_coordinates": route_coordinates,
                "directions": direction_steps
            })

        ranked_cache_key = None
        if is_free_provider_enabled():
            ranked_cache_key = get_ranked_stops_cache_key(origin, destination, place_query, live_lat, live_lng)
            ranked_cached = ranked_stops_cache.get(ranked_cache_key)
            if ranked_cached and (time.time() - ranked_cached.get("timestamp", 0) <= RANKED_STOPS_CACHE_TTL_SECONDS):
                return jsonify({
                    "status": "success",
                    "search_query": place_query,
                    "on_route_stops_found": len(ranked_cached.get("stops", [])),
                    "stops": copy.deepcopy(ranked_cached.get("stops", [])),
                    "route_coordinates": route_coordinates,
                    "directions": direction_steps
                })

        # Gather + filter candidates
        on_route_stops = []
        provider_notice = None
        if is_free_provider_enabled():
            stop_cache_key = get_stop_cache_key(origin, destination, place_query)
            cached_stop_data = stop_candidate_cache.get(stop_cache_key)
            if cached_stop_data and (time.time() - cached_stop_data["timestamp"] <= STOP_CACHE_TTL_SECONDS):
                on_route_stops = copy.deepcopy(cached_stop_data.get("stops", []))
            else:
                all_candidates, overpass_unavailable = find_places_with_overpass(route_coordinates, place_query)
                for place in all_candidates.values():
                    place_loc = place.get('location')
                    if place_loc and is_on_route(place_loc, route_coordinates):
                        on_route_stops.append({
                            "name": place.get('name'),
                            "rating": place.get('rating', 'N/A'),
                            "place_id": place.get('place_id'),
                            "location": place_loc
                        })
                # Avoid caching transient outage empties so retries can recover quickly.
                if on_route_stops or not overpass_unavailable:
                    stop_candidate_cache[stop_cache_key] = {
                        "timestamp": time.time(),
                        "stops": copy.deepcopy(on_route_stops),
                    }
                if overpass_unavailable:
                    provider_notice = "Free stop search provider is temporarily rate-limited. Please retry in a few seconds."
        else:
            all_candidates = {}
            search_interval = 50
            for i in range(0, len(route_coordinates), search_interval):
                midpoint = route_coordinates[i]
                places_params = {
                    "location": f"{midpoint[0]},{midpoint[1]}", "radius": 15000,
                    "keyword": place_query, "key": API_KEY
                }
                places_response = requests.get(PLACES_API_URL, params=places_params, timeout=15)
                places_data = places_response.json()
                if places_data['status'] == 'OK':
                    for place in places_data['results']:
                        all_candidates[place['place_id']] = place

            for place in all_candidates.values():
                place_loc = place.get('geometry', {}).get('location')
                if place_loc and is_on_route(place_loc, route_coordinates):
                    on_route_stops.append({
                        "name": place.get('name'), "rating": place.get('rating', 'N/A'),
                        "place_id": place.get('place_id'), "location": place_loc
                    })

        current_route_index = None
        if live_lat and live_lng and on_route_stops:
            current_route_index = get_closest_route_index(
                {"lat": live_lat, "lng": live_lng},
                route_coordinates,
            )
            for stop in on_route_stops:
                stop_route_index = get_closest_route_index(stop['location'], route_coordinates)
                backtrack_penalty_seconds = BACKTRACK_PENALTY_SECONDS if stop_route_index < current_route_index else 0
                stop['ahead_of_user'] = backtrack_penalty_seconds == 0
                stop['backtrack_penalty_seconds'] = backtrack_penalty_seconds

        # Rank Stops
        if on_route_stops:
            if is_free_provider_enabled():
                on_route_stops = on_route_stops[:min(DISTANCE_MATRIX_MAX_DESTINATIONS, FREE_MAX_RANK_DESTINATIONS)]
                if live_lat and live_lng:
                    ranking_origin = f"{live_lng},{live_lat}"
                else:
                    origin_geo = geocode_with_nominatim(origin)
                    if not origin_geo:
                        raise ValueError("Could not geocode origin for ranking")
                    ranking_origin = f"{origin_geo['lng']},{origin_geo['lat']}"
                try:
                    on_route_stops = rank_stops_with_osrm_table(on_route_stops, ranking_origin)
                except requests.exceptions.RequestException:
                    on_route_stops = rank_stops_with_fallback(on_route_stops, ranking_origin)
            else:
                ranking_origin = f"{live_lat},{live_lng}" if (live_lat and live_lng) else origin
                destination_coords = "|".join([f"{stop['location']['lat']},{stop['location']['lng']}" for stop in on_route_stops])
                matrix_params = { "origins": ranking_origin, "destinations": destination_coords, "key": API_KEY, "units": "metric" }
                try:
                    matrix_response = requests.get(DISTANCE_MATRIX_API_URL, params=matrix_params, timeout=15)
                    matrix_data = matrix_response.json()

                    if matrix_data['status'] == 'OK' and matrix_data['rows'][0]['elements']:
                        for i, stop in enumerate(on_route_stops):
                            element = matrix_data['rows'][0]['elements'][i]
                            if element['status'] == 'OK':
                                stop['distance'] = element['distance']['text']
                                stop['duration'] = element['duration']['text']
                                stop['duration_seconds'] = element['duration']['value']
                            stop['score_seconds'] = stop.get('duration_seconds', 99999) + stop.get('backtrack_penalty_seconds', 0)

                        on_route_stops.sort(key=lambda x: x.get('score_seconds', x.get('duration_seconds', 99999)))
                except requests.exceptions.RequestException:
                    pass

            on_route_stops = on_route_stops[:STOPS_RESPONSE_LIMIT]

        if is_free_provider_enabled() and ranked_cache_key:
            ranked_stops_cache[ranked_cache_key] = {
                "timestamp": time.time(),
                "stops": copy.deepcopy(on_route_stops),
            }

        response_payload = {
            "status": "success",
            "search_query": place_query,
            "on_route_stops_found": len(on_route_stops),
            "stops": on_route_stops,
            "route_coordinates": route_coordinates,
            "directions": direction_steps
        }

        if provider_notice:
            response_payload["provider_notice"] = provider_notice

        return jsonify(response_payload)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"An external API error occurred: {e}"}), 502
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

# --- NEW CHAT ENDPOINT ---
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message', '').lower()

    response_text = ""
    action = None
    action_data = {}

    # 1. Navigation Intent
    if "navigate to" in user_message or "go to" in user_message:
        response_text = "Starting navigation. Please confirm your destination."
        action = "navigate"
        parts = user_message.split(" to ")
        if len(parts) > 1:
            action_data['destination'] = parts[1].strip()

    # 2. Find Stops Intent
    elif "find" in user_message or "near me" in user_message:
        response_text = "Searching for stops along your route..."
        action = "find_stops"
        if "dhaba" in user_message:
            action_data['query'] = "dhaba"
        elif "petrol" in user_message:
            action_data['query'] = "petrol pump"
        else:
            action_data['query'] = "restaurant"

    # 3. Weather Intent
    elif "weather" in user_message:
        response_text = "I can't check real-time weather yet, but it's always sunny in the cloud! ☀️"

    # 4. Music Intent
    elif "music" in user_message or "song" in user_message:
        response_text = "Opening your music recommendations..."
        action = "music"

    # 5. General / Greeting
    else:
        response_text = "I can help you navigate, find food, or check route info. Just ask!"

    return jsonify({
        "reply": response_text,
        "action": action,
        "data": action_data
    })

# --- CONVOY ENDPOINTS ---

@app.route('/convoy/create', methods=['POST'])
def convoy_create():
    cleanup_stale_convoys()
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or 'Leader').strip()[:40]
    destination = (body.get('destination') or '').strip()[:180] or None

    with convoy_lock:
        room_id = None
        for _ in range(5):
            candidate = uuid4().hex[:6].upper()
            if candidate not in convoy_rooms:
                room_id = candidate
                break
        room_id = room_id or uuid4().hex[:8].upper()

        member_id = uuid4().hex[:10]
        now = time.time()
        room = {
            "created_at": now,
            "destination": destination,
            "members": {
                member_id: {
                    "name": name,
                    "lat": None,
                    "lng": None,
                    "updated_at": now,
                }
            }
        }
        convoy_rooms[room_id] = room

    return jsonify({
        "status": "success",
        "room_id": room_id,
        "member_id": member_id,
        "destination": room.get("destination"),
        "members": serialize_room_members(room),
    })

@app.route('/convoy/join', methods=['POST'])
def convoy_join():
    cleanup_stale_convoys()
    body = request.get_json(silent=True) or {}
    room_id = (body.get('room_id') or '').strip().upper()
    name = (body.get('name') or 'Member').strip()[:40]
    if not room_id:
        return jsonify({"error": "Missing required field: room_id"}), 400

    with convoy_lock:
        room = convoy_rooms.get(room_id)
        if not room:
            return jsonify({"error": "Convoy room not found"}), 404
        member_id = uuid4().hex[:10]
        room["members"][member_id] = {
            "name": name,
            "lat": None,
            "lng": None,
            "updated_at": time.time(),
        }
        members = serialize_room_members(room)

    return jsonify({
        "status": "success",
        "room_id": room_id,
        "member_id": member_id,
        "destination": room.get("destination"),
        "members": members,
    })

@app.route('/convoy/destination', methods=['POST'])
def convoy_destination():
    cleanup_stale_convoys()
    body = request.get_json(silent=True) or {}
    room_id = (body.get('room_id') or '').strip().upper()
    member_id = (body.get('member_id') or '').strip()
    destination = (body.get('destination') or '').strip()[:180]

    if not room_id or not member_id or not destination:
        return jsonify({"error": "Missing required fields: room_id, member_id, destination"}), 400

    with convoy_lock:
        room = convoy_rooms.get(room_id)
        if not room:
            return jsonify({"error": "Convoy room not found"}), 404
        if member_id not in room["members"]:
            return jsonify({"error": "Convoy member not found"}), 404

        room["destination"] = destination

    return jsonify({
        "status": "success",
        "room_id": room_id,
        "destination": destination,
    })

@app.route('/convoy/update', methods=['POST'])
def convoy_update():
    cleanup_stale_convoys()
    body = request.get_json(silent=True) or {}
    room_id = (body.get('room_id') or '').strip().upper()
    member_id = (body.get('member_id') or '').strip()
    if not room_id or not member_id:
        return jsonify({"error": "Missing required fields: room_id, member_id"}), 400

    try:
        lat = float(body.get('lat'))
        lng = float(body.get('lng'))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid lat/lng values"}), 400

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error": "lat/lng out of range"}), 400

    with convoy_lock:
        room = convoy_rooms.get(room_id)
        if not room:
            return jsonify({"error": "Convoy room not found"}), 404
        member = room["members"].get(member_id)
        if not member:
            return jsonify({"error": "Convoy member not found"}), 404

        member["lat"] = lat
        member["lng"] = lng
        member["updated_at"] = time.time()
        new_name = body.get('name')
        if isinstance(new_name, str) and new_name.strip():
            member["name"] = new_name.strip()[:40]

        members = serialize_room_members(room)

    return jsonify({
        "status": "success",
        "room_id": room_id,
        "destination": room.get("destination"),
        "members": members,
    })

@app.route('/convoy/state', methods=['GET'])
def convoy_state():
    cleanup_stale_convoys()
    room_id = (request.args.get('room_id') or '').strip().upper()
    if not room_id:
        return jsonify({"error": "Missing required parameter: room_id"}), 400

    with convoy_lock:
        room = convoy_rooms.get(room_id)
        if not room:
            return jsonify({"error": "Convoy room not found"}), 404
        members = serialize_room_members(room)

    return jsonify({
        "status": "success",
        "room_id": room_id,
        "destination": room.get("destination"),
        "members": members,
    })

@app.route('/convoy/leave', methods=['POST'])
def convoy_leave():
    cleanup_stale_convoys()
    body = request.get_json(silent=True) or {}
    room_id = (body.get('room_id') or '').strip().upper()
    member_id = (body.get('member_id') or '').strip()
    if not room_id or not member_id:
        return jsonify({"error": "Missing required fields: room_id, member_id"}), 400

    with convoy_lock:
        room = convoy_rooms.get(room_id)
        if not room:
            return jsonify({"error": "Convoy room not found"}), 404
        room["members"].pop(member_id, None)
        if not room["members"]:
            convoy_rooms.pop(room_id, None)
            members = []
        else:
            members = serialize_room_members(room)

    return jsonify({
        "status": "success",
        "room_id": room_id,
        "members": members,
    })

if __name__ == '__main__':
    run_host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    run_port = int(os.getenv("PORT", os.getenv("FLASK_RUN_PORT", "5000")))
    debug_mode = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes", "on")
    app.run(host=run_host, port=run_port, debug=debug_mode)