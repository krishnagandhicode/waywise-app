import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import polyline
from haversine import haversine, Unit
from flask_cors import CORS

# Load environment variables
load_dotenv()

# Initialize Flask App
app = Flask(__name__)
CORS(app)

# API Configuration
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
DISTANCE_MATRIX_API_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

# --- HELPER FUNCTIONS ---

# --- CHANGE #1: Update this function to return directions ---
def get_decoded_route(origin, destination):
    """Fetches and decodes the route, and also extracts direction steps."""
    params = {"origin": origin, "destination": destination, "key": API_KEY}
    response = requests.get(DIRECTIONS_API_URL, params=params)
    response.raise_for_status()
    data = response.json()
    if data['status'] == 'OK' and data.get('routes'):
        route = data['routes'][0]['legs'][0]
        
        encoded_polyline = data['routes'][0]['overview_polyline']['points']
        decoded_coordinates = polyline.decode(encoded_polyline)

        # This new part gets the turn-by-turn steps
        direction_steps = [step['html_instructions'] for step in route['steps']]
        
        # Now it returns BOTH the coordinates and the steps
        return decoded_coordinates, direction_steps
        
    return None, None # Return None for both if it fails

def is_on_route(place_location, route_coordinates, max_distance_meters=1500):
    """Checks if a place is within a max distance from any point on the route."""
    place_coords = (place_location['lat'], place_location['lng'])
    for route_point in route_coordinates:
        route_point_coords = (route_point[0], route_point[1])
        distance = haversine(place_coords, route_point_coords, unit=Unit.METERS)
        if distance <= max_distance_meters:
            return True
    return False

# --- MAIN APPLICATION ENDPOINT ---
@app.route('/find_stops', methods=['GET'])
def find_stops():
    """Main endpoint to find on-route stops for a given journey."""
    origin = request.args.get('origin')
    destination = request.args.get('destination')
    place_query = request.args.get('query')
    live_lat = request.args.get('live_lat')
    live_lng = request.args.get('live_lng')

    if not all([origin, destination, place_query]):
        return jsonify({"error": "Missing required parameters: origin, destination, query"}), 400

    try:
        # --- CHANGE #2: Unpack BOTH values from the updated function ---
        route_coordinates, direction_steps = get_decoded_route(origin, destination)
        
        if not route_coordinates:
            return jsonify({"error": "Could not find a route between the specified locations"}), 404

        # Step 3: Gather candidates (This part is unchanged)
        all_candidates = {}
        search_interval = 50
        for i in range(0, len(route_coordinates), search_interval):
            midpoint = route_coordinates[i]
            places_params = {
                "location": f"{midpoint[0]},{midpoint[1]}", "radius": 15000,
                "keyword": place_query, "key": API_KEY
            }
            places_response = requests.get(PLACES_API_URL, params=places_params)
            places_data = places_response.json()
            if places_data['status'] == 'OK':
                for place in places_data['results']:
                    all_candidates[place['place_id']] = place

        # Step 4: Filter candidates (This part is unchanged)
        on_route_stops = []
        for place in all_candidates.values():
            place_loc = place.get('geometry', {}).get('location')
            if place_loc and is_on_route(place_loc, route_coordinates):
                on_route_stops.append({
                    "name": place.get('name'), "rating": place.get('rating', 'N/A'),
                    "place_id": place.get('place_id'), "location": place_loc
                })
        
        # Step 5: Rank Stops (This part is unchanged)
        if on_route_stops:
            ranking_origin = f"{live_lat},{live_lng}" if (live_lat and live_lng) else origin
            destination_coords = "|".join([f"{stop['location']['lat']},{stop['location']['lng']}" for stop in on_route_stops])
            matrix_params = { "origins": ranking_origin, "destinations": destination_coords, "key": API_KEY, "units": "metric" }
            matrix_response = requests.get(DISTANCE_MATRIX_API_URL, params=matrix_params)
            matrix_data = matrix_response.json()

            if matrix_data['status'] == 'OK' and matrix_data['rows'][0]['elements']:
                for i, stop in enumerate(on_route_stops):
                    element = matrix_data['rows'][0]['elements'][i]
                    if element['status'] == 'OK':
                        stop['distance'] = element['distance']['text']
                        stop['duration'] = element['duration']['text']
                        stop['duration_seconds'] = element['duration']['value']
            
            on_route_stops.sort(key=lambda x: x.get('duration_seconds', 99999))
        
        # --- CHANGE #3: Add the new directions list to the final response ---
        return jsonify({
            "status": "success",
            "search_query": place_query,
            "on_route_stops_found": len(on_route_stops),
            "stops": on_route_stops,
            "route_coordinates": route_coordinates,
            "directions": direction_steps # <-- Add this new key-value pair
        })

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"An external API error occurred: {e}"}), 502
    except Exception as e:
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)