# WayWise AI - Real-Time Intelligent Navigation Assistant
<img width="1280" height="720" alt="image" src="https://github.com/user-attachments/assets/cbab8ea5-ac10-4b8e-a6e7-ed18387f86ec" />

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
* **(Future Scope):** Integrated conversational AI assistant (using Gemini AI API) for contextual, on-the-go recommendations. ## Demo



## Tech Stack

* **Backend:** Python, Flask, Flask-CORS
* **Frontend:** JavaScript, HTML5, CSS3 (Grid Layout), Leaflet.js
* **APIs:**
    * Google Maps Platform (Directions, Places, Distance Matrix)
    * Browser Geolocation API (getCurrentPosition, watchPosition)
    * OpenStreetMap Nominatim (Reverse Geocoding)
    * [Optional: Gemini AI API - if implementing chatbot]
* **Environment:** Git, GitHub, Virtualenv

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YourUsername/WayWise-AI.git](https://github.com/krishnaGandhi11/WayWise---Real-Time-Intelligent-Navigation-Assistant-)
    cd WayWise-AI
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
    pip install Flask Flask-CORS requests python-dotenv polyline haversine
    # Optional, if using the ML part:
    # pip install pandas scikit-learn surprise
    ```
4.  **Set up API Key:**
    * Create a `.env` file in the project root.
    * Add your Google Maps API key: `Maps_API_KEY="YOUR_API_KEY_HERE"`
    * Ensure you have enabled the Directions, Places, and Distance Matrix APIs in your Google Cloud Console.
5.  **Run the Backend Server:**
    ```bash
    flask --app app run
    ```
    *(Keep this terminal running)*
6.  **Run the Frontend Server:**
    * Open a **new terminal**.
    * Activate the virtual environment again (`venv\Scripts\activate` or `source venv/bin/activate`).
    * Start the simple Python HTTP server:
        ```bash
        python -m http.server 8000
        ```
7.  **Access the application:** Open your web browser and go to `http://localhost:8000`.

## Usage

1.  Enter your starting point (Origin) and destination. You can optionally click the "📍" button to use your current location.
2.  Click "Start Navigation".
3.  Allow the browser to access your location when prompted.
4.  The map will display the route, your live location (blue dot), and the current turn instruction at the top.
5.  Use the buttons ("Petrol", "Restaurant", etc.) or the search bar under "Find on my way..." to find relevant stops.
6.  Results will be displayed as pins on the map and as a ranked list in the sidebar.

## Future Scope

The Future Roadmap: Convoy & AI (See Diagram) Building this foundation has opened the door for two major features I plan to develop next:
1. Live Convoy Mode: Solving the logistics of group road trips. Instead of constant status calls, you will see your friends' vehicles moving in real-time on a shared trip map via WebSockets.
2. Conversational AI Assistant: Driving requires focus. I am designing a voice-enabled interface where you can command, "Find a highly-rated restaurant in the next 30km," and the AI handles the complex querying without manual input.

<img width="1280" height="698" alt="image" src="https://github.com/user-attachments/assets/99bb7e55-0410-4143-a5cf-b35051aa6b64" />

