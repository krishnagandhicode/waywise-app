# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the dev server (serves both backend API and frontend)
python app.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_convoy.py

# Run a single test by name
pytest tests/test_health.py::test_health_endpoint_returns_ok

# Install runtime dependencies
pip install -r requirements.txt

# Install dev/test dependencies
pip install -r requirements-dev.txt
```

The app runs at `http://127.0.0.1:5000` by default. Override with `PORT` env var.

## Architecture

### Entry points

`app.py` (root) is a thin launcher that imports and runs `backend/app.py`. The root launcher exists so `gunicorn app:app` works simply in production (Render). All logic lives in `backend/app.py`.

Flask serves the frontend directly — there is no separate frontend build step. Templates are in `frontend/templates/`, static assets in `frontend/static/`. The frontend uses native ES modules (`import`/`export`) — no bundler.

### Provider system

The single most important design concept is the **dual-provider architecture**. Set via `WAYWISE_MAP_PROVIDER` env var:

- `free` (default): OSRM (routing) + Nominatim (geocoding) + Overpass API (POI search) + OSRM Table (ranking)
- `google`: Google Directions + Google Places + Google Distance Matrix

`get_provider_chain()` in `backend/app.py` returns an ordered list like `["google", "free"]`. Every major operation iterates this chain and falls back on failure when `WAYWISE_ENABLE_GOOGLE_FALLBACK=true`. The free Overpass endpoints themselves have their own rotation via `OVERPASS_API_URLS` and `OVERPASS_PREFERRED_INDEX`.

### Stop-finding pipeline

`/find_stops` is the core endpoint. It chains these stages:

1. **Route** — `get_decoded_route()` → polyline coordinates + direction steps
2. **Candidate discovery** — the free path calls `find_places_with_overpass()`; the Google path is written inline in `find_stops()` and hits Places Nearby Search. Both sample the route at intervals (capped by `FREE_MAX_SEARCH_POINTS` / `GOOGLE_MAX_SEARCH_POINTS`, both 8) and query POIs around each sample point
3. **On-route filtering** — `is_on_route()` uses haversine distance to keep only stops within `max_distance_meters` (defaults to 1500m) of any route point
4. **Backtrack penalty** — stops behind the user's current route index get `BACKTRACK_PENALTY_SECONDS` (900s) added to their score
5. **Ranking** — the free path calls `rank_stops_with_osrm_table()`, falling back to `rank_stops_with_fallback()` (pure haversine ETA at 40 km/h) when OSRM is unreachable. The Google path builds its Distance Matrix request inline in `find_stops()`
6. **Truncation** — top `STOPS_RESPONSE_LIMIT` (8) returned

A `route_only` query (via `query=route_only`) skips stages 2–6, used for the initial navigation bootstrap.

### Caching

Four in-memory dicts with TTL checks:

| Cache | Key structure | TTL env var |
|---|---|---|
| `route_cache` | `provider::origin::destination` | `ROUTE_CACHE_TTL_SECONDS` (900s) |
| `stop_candidate_cache` | `provider::origin::destination::query` | `STOP_CACHE_TTL_SECONDS` (240s) |
| `ranked_stops_cache` | stop key + lat/lng bucket | `RANKED_STOPS_CACHE_TTL_SECONDS` (45s) |
| `geocode_cache` | normalized location text | `GEOCODE_CACHE_TTL_SECONDS` (1800s) |

### Convoy mode

Convoy rooms live in the `convoy_rooms` dict protected by `convoy_lock` (threading.Lock). Each room has a short hex room code and a `members` dict keyed by member UUID. Location updates come in via `POST /convoy/update`. The frontend polls `GET /convoy/state` on an interval. `cleanup_stale_convoys()` evicts members inactive for `CONVOY_MEMBER_TTL_SECONDS` (300s) and rooms older than `CONVOY_ROOM_TTL_SECONDS` (86400s). **State is in-memory only — it resets on server restart.**

### Frontend modules

- `script.js` — orchestrates all user interactions, geolocation watch, convoy lifecycle
- `modules/api.js` — `buildApiUrl()` and `fetchJson()` helpers
- `modules/map.js` — Leaflet map init, `getCurrentTurnInfo()` (maps GPS position → nearest route index → current direction step)
- `modules/convoy.js` — renders convoy member list and map markers

### Mock mode

`WAYWISE_MOCK_MODE=true` bypasses all external API calls and returns deterministic fixtures. Useful when no API keys are available. Route is a linear interpolation between hardcoded city coordinates defined in `MOCK_LOCATION_HINTS`.

## Key environment variables

```env
WAYWISE_MAP_PROVIDER=free          # or "google"
WAYWISE_MOCK_MODE=false
WAYWISE_ENABLE_GOOGLE_FALLBACK=true
GOOGLE_MAPS_API_KEY=...
DISTANCE_MATRIX_MAX_DESTINATIONS=25
FREE_MAX_SEARCH_POINTS=8
GOOGLE_MAX_SEARCH_POINTS=8
```

`FREE_MAX_SEARCH_POINTS` / `GOOGLE_MAX_SEARCH_POINTS` cap how many points along the
route get a POI query, and `DISTANCE_MATRIX_MAX_DESTINATIONS` caps destinations per
Distance Matrix request. All three bound billed call volume on the Google path — lower
them before pointing a public deployment at `WAYWISE_MAP_PROVIDER=google`.

See README for the full list.

## Testing

Tests use Flask's test client via `conftest.py` which imports `backend.app:app` directly. There are no recorded HTTP fixtures — tests either exercise endpoints that make no external calls (health, convoy lifecycle), rely on `WAYWISE_MOCK_MODE`, or `monkeypatch` the module-level provider functions on `backend.app` directly (see `tests/test_provider_fallback.py`, which swaps out `get_route_with_google` / `get_route_with_osrm`).

Because config like `MAP_PROVIDER` and `MOCK_MODE` is read into module-level constants at import time, tests that need different settings must `monkeypatch.setattr(backend.app, "MOCK_MODE", True)` rather than setting the env var after import.
