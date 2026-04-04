# WayWise AI - Real-Time Intelligent Navigation Assistant
<img width="1280" height="720" alt="image" src="https://github.com/user-attachments/assets/cbab8ea5-ac10-4b8e-a6e7-ed18387f86ec" />

## Live App

https://www.waywiseapp.tech

## Introduction

WayWise AI is a full-stack web application designed to enhance long-distance driving by providing intelligent, on-route stop suggestions and simulating a real-time navigation experience. Unlike standard GPS tools that often suggest inconvenient detours, WayWise AI analyzes routes dynamically, considering the user's live location to recommend stops (restaurants, petrol pumps, etc.) that minimize extra travel time. It also features a live "current turn" display for a more intuitive navigation feel.

This project was born out of the common frustration of finding convenient stops during road trips and aims to provide a smarter, more user-centric solution.

## Features

* **Live Navigation Simulation:** Tracks user's real-time GPS via the Geolocation API and displays it as a moving marker on an interactive Leaflet.js map.
* **Dynamic "Current Turn" Display:** Shows the current navigation instruction in a top-bar overlay, updating automatically as the user progresses along the route.
* **Intelligent On-Route Stop Finding:**
    * Finds potential stops (restaurants, petrol pumps, ATMs, custom queries) along the calculated route.
    * Uses the Haversine formula for geospatial filtering to identify stops requiring minimal deviation.
    * Ranks suggested stops based on the shortest real-time detour duration calculated via the Google Distance Matrix API, using the user's live location as the origin.
* **"Use My Location":** Allows users to instantly populate origin/destination fields with their current address using reverse geocoding (OpenStreetMap Nominatim).
* **Interactive UI:** Responsive two-column layout built with HTML, CSS (Grid), and JavaScript, featuring map markers, route display, and dynamic results lists.
* **Backend Health Indicator:** Frontend shows whether backend is reachable and which provider mode is active.
* **Convoy Mode (MVP):** Create or join a room and share live locations among members during a trip.
* **(Future Scope):** Integrated conversational AI assistant (using Gemini AI API) for contextual, on-the-go recommendations. ## Demo



## Tech Stack

* **Backend:** Python, Flask, Flask-CORS
* **Frontend:** JavaScript, HTML5, CSS3 (Grid Layout), Leaflet.js
* **APIs:**
    * Google Maps Platform (Directions, Places, Distance Matrix)
    * Free map stack for testing (OSRM + OpenStreetMap Nominatim + Overpass)
    * Browser Geolocation API (getCurrentPosition, watchPosition)
    * OpenStreetMap Nominatim (Reverse Geocoding)
    * [Optional: Gemini AI API - if implementing chatbot]
* **Environment:** Git, GitHub, Virtualenv

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/krishnagandhicode/waywise-app.git
    cd waywise-app
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    # On Windows:
    venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set up configuration:**
    * Create a `.env` file in the project root.
    * For Google provider, add your API key: `GOOGLE_MAPS_API_KEY="YOUR_API_KEY_HERE"`
    * To run with free APIs for real-world testing, set: `WAYWISE_MAP_PROVIDER="free"`
    * Optional testing flags:
        * `WAYWISE_MOCK_MODE="false"` (use live free APIs)
        * `DISTANCE_MATRIX_MAX_DESTINATIONS="10"` (safer cap for public endpoints)
    * Ensure you have enabled the Directions, Places, and Distance Matrix APIs in your Google Cloud Console only if you are using Google provider.
5.  **Run the App (single server):**
    ```bash
    python app.py
    ```
    *(Keep this terminal running)*
6.  **Access the application:** Open your web browser and go to `http://127.0.0.1:5000`.

## Usage

1.  Enter your starting point (Origin) and destination. You can optionally click the "📍" button to use your current location.
2.  Click "Start Navigation".
3.  Allow the browser to access your location when prompted.
4.  The map will display the route, your live location (blue dot), and the current turn instruction at the top.
5.  Use the buttons ("Petrol", "Restaurant", etc.) or the search bar under "Find on my way..." to find relevant stops.
6.  Results will be displayed as pins on the map and as a ranked list in the sidebar.

## Project Architecture

```text
waywise-app/
|- app.py                      # Root launcher (keeps run command simple)
|- requirements.txt
|- backend/
|  |- __init__.py
|  |- app.py                   # Flask API + routing + provider logic
|- frontend/
|  |- templates/
|  |  |- index.html            # Main UI shell
|  |- static/
|     |- css/
|     |  |- style.css          # App styling
|     |- js/
|        |- script.js          # Frontend app entry (module)
|        |- modules/
|           |- api.js          # URL building and JSON fetch helpers
|           |- map.js          # Map and turn-panel helpers
|           |- convoy.js       # Convoy marker/member rendering
|- Some-Screnshots/
```

Flask serves frontend files from `frontend/templates` and `frontend/static`.

## Tests

Install dev dependencies and run tests:

```bash
pip install -r requirements-dev.txt
pytest
```

### Convoy Quick Start

1. Enter your name in the Convoy section.
2. Click **Create** to create a room, or enter a room code and click **Join**.
3. Start navigation and allow location permission.
4. Members in the same room can see each other's live markers on the map.
5. Click **Leave Convoy** when done.

## Provider Modes

WayWise supports two map providers through environment variables:

* `WAYWISE_MAP_PROVIDER="google"`:
    * Routing: Google Directions
    * Stops: Google Places
    * Ranking: Google Distance Matrix

* `WAYWISE_MAP_PROVIDER="free"` (default):
    * Routing: OSRM public API
    * Geocoding: OpenStreetMap Nominatim
    * Stops: Overpass API
    * Ranking: OSRM Table API

Recommended for efficient testing:

```env
WAYWISE_MOCK_MODE=false
WAYWISE_MAP_PROVIDER=free
DISTANCE_MATRIX_MAX_DESTINATIONS=10
FREE_MAX_SEARCH_POINTS=8
```

Note: Public free endpoints are rate-limited and shared. Use moderate request frequency and keep caps low during testing.
If one Overpass endpoint is rate-limited, WayWise automatically tries fallback endpoints.

## Google Baseline Reference Page

To explore a direct Google Maps JavaScript baseline (map init + route render + places search), open:

```text
http://127.0.0.1:5000/google-baseline
```

Set a browser-restricted API key in `.env`:

```env
GOOGLE_MAPS_JS_API_KEY="YOUR_BROWSER_KEY"
```

If `GOOGLE_MAPS_JS_API_KEY` is not set, the page falls back to `GOOGLE_MAPS_API_KEY`.

## Troubleshooting

* If startup fails because port 5000 is busy, close old Python processes or run with a different port:

```bash
set PORT=5001
python app.py
```

* Health check endpoint:

```bash
http://127.0.0.1:5000/health
```

## Future Scope

* Integrate a conversational AI chatbot (using Gemini API) for hands-free interaction and smarter suggestions based on context (weather, time of day).
* Implement proactive notifications (e.g., warnings about upcoming long stretches without petrol stations).
* Add real-time data integration (e.g., petrol prices).

### Future Roadmap: Convoy and AI

Building this foundation opens the door for two major feature tracks:

1. Live Convoy Mode:
    * Real-time group trip visibility via shared map sessions and low-latency location updates.
2. Conversational AI Assistant:
    * Voice-first trip actions such as finding highly-rated stops along route without manual searching.

<img width="1280" height="698" alt="image" src="https://github.com/user-attachments/assets/99bb7e55-0410-4143-a5cf-b35051aa6b64" />

## Legal and Ownership

Copyright (c) 2026 Krishna Gandhi. All rights reserved.

WayWise is a trademark of Krishna Gandhi.

This repository includes a custom `All Rights Reserved` license in [LICENSE](LICENSE). No permission is granted for reuse, redistribution, or derivative work without explicit written approval.

### Repository Privacy Recommendation

If you want to keep implementation details private while building, keep the GitHub repository private and deploy from the private repository.

## Deployment Recommendation

For this codebase, the simplest and most reliable setup is a single Render web service for both backend and frontend.

Why this is recommended first:

* Flask already serves the frontend templates and static files.
* No cross-origin issues between Netlify frontend and Render backend.
* No extra proxy rules or split environment variables needed.

### Render Deployment (Recommended)

1. Push repository to GitHub.
2. Create a new Web Service on Render from the repository.
3. Use build command: `pip install -r requirements.txt`
4. Use start command: `gunicorn app:app`
5. Set environment variables on Render:
    * `WAYWISE_MAP_PROVIDER=free`
    * `WAYWISE_MOCK_MODE=false`
    * `DISTANCE_MATRIX_MAX_DESTINATIONS=10`
    * `FREE_MAX_SEARCH_POINTS=8`
6. Deploy and open the Render URL.

### When to Use Netlify + Render Split

Use split deployment only if you later move to a separate frontend framework build (for example React/Vite) and want independent frontend hosting/CDN optimization.
