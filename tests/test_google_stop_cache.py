"""Google provider path: a transient Places failure must not poison the cache."""
from importlib import import_module

import pytest
import requests

backend_app_module = import_module("backend.app")

ROUTE = [(30.7333, 76.7794), (30.75, 76.80), (30.77, 76.82)]
STEPS = ["Head north"]

PLACE = {
    "id": "abc123",
    "displayName": {"text": "Test Pharmacy", "languageCode": "en"},
    "rating": 4.5,
    "location": {"latitude": 30.75, "longitude": 76.80},
}
MATRIX = [{"status": {}, "condition": "ROUTE_EXISTS", "distanceMeters": 2000, "duration": "300s"}]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error", response=self)


@pytest.fixture
def google_provider(monkeypatch):
    """Puts the app on the Google path with empty caches and a canned route."""
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", "google")
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", False)
    monkeypatch.setattr(backend_app_module, "API_KEY", "test-key")
    monkeypatch.setattr(backend_app_module, "stop_candidate_cache", {})
    monkeypatch.setattr(backend_app_module, "ranked_stops_cache", {})
    monkeypatch.setattr(
        backend_app_module,
        "get_decoded_route",
        lambda origin, destination: (ROUTE, STEPS, "google"),
    )
    # Tests opt in to the free fallback explicitly; by default it is off and
    # must never reach the real Overpass endpoints.
    monkeypatch.setattr(backend_app_module, "GOOGLE_FALLBACK_ENABLED", False)

    def no_overpass(*args, **kwargs):
        raise AssertionError("unexpected Overpass call")

    monkeypatch.setattr(backend_app_module, "find_places_with_overpass", no_overpass)


OSM_PLACE = {
    "node_1": {
        "name": "OSM Pharmacy",
        "rating": "N/A",
        "place_id": "node_1",
        "location": {"lat": 30.751, "lng": 76.801},
    }
}


def enable_free_fallback(monkeypatch, candidates=OSM_PLACE, unavailable=False):
    calls = []

    def fake_overpass(route_coordinates, place_query):
        calls.append(place_query)
        return dict(candidates), unavailable

    monkeypatch.setattr(backend_app_module, "GOOGLE_FALLBACK_ENABLED", True)
    monkeypatch.setattr(backend_app_module, "find_places_with_overpass", fake_overpass)
    return calls


def answer_places_with(monkeypatch, places_response):
    def fake_post(url, *args, **kwargs):
        if url == backend_app_module.ROUTE_MATRIX_API_URL:
            return FakeResponse(MATRIX)
        return places_response

    monkeypatch.setattr(backend_app_module.requests, "post", fake_post)


def search(client):
    return client.get(
        "/find_stops",
        query_string={"origin": "Chandigarh", "destination": "Shimla", "query": "pharmacy"},
    )


def test_transient_places_failure_is_not_cached(client, google_provider, monkeypatch):
    """A 5xx is retryable. Caching the empty result would hide stops for
    STOP_CACHE_TTL_SECONDS after Google recovers."""
    answer_places_with(monkeypatch, FakeResponse({"error": {"status": "UNAVAILABLE"}}, 503))

    response = search(client)

    assert response.status_code == 200
    assert response.get_json()["stops"] == []
    assert backend_app_module.stop_candidate_cache == {}
    assert "provider_notice" in response.get_json()


def test_network_failure_is_not_cached(client, google_provider, monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(backend_app_module.requests, "post", timeout)

    response = search(client)

    assert response.status_code == 200
    assert backend_app_module.stop_candidate_cache == {}
    assert "provider_notice" in response.get_json()


def test_zero_results_is_cached_as_a_real_answer(client, google_provider, monkeypatch):
    """Places (New) answers an empty area with {} rather than a status. It must
    cache, or every request re-bills Places."""
    answer_places_with(monkeypatch, FakeResponse({}))

    response = search(client)

    assert response.status_code == 200
    assert response.get_json()["stops"] == []
    assert len(backend_app_module.stop_candidate_cache) == 1


def test_rejected_key_is_reported_not_cached(client, google_provider, monkeypatch):
    answer_places_with(monkeypatch, FakeResponse({"error": {"status": "PERMISSION_DENIED"}}, 403))

    response = search(client)

    assert response.status_code == 400
    assert "403" in response.get_json()["error"]
    assert backend_app_module.stop_candidate_cache == {}


def test_successful_search_is_cached(client, google_provider, monkeypatch):
    answer_places_with(monkeypatch, FakeResponse({"places": [PLACE]}))

    response = search(client)
    stops = response.get_json()["stops"]

    assert response.status_code == 200
    assert [stop["name"] for stop in stops] == ["Test Pharmacy"]
    assert stops[0]["place_id"] == "abc123"
    assert stops[0]["rating"] == 4.5
    assert stops[0]["location"] == {"lat": 30.75, "lng": 76.80}
    assert len(backend_app_module.stop_candidate_cache) == 1


def test_places_request_uses_text_search_with_a_field_mask(client, google_provider, monkeypatch):
    calls = []

    def fake_post(url, *args, **kwargs):
        calls.append({"url": url, **kwargs})
        if url == backend_app_module.ROUTE_MATRIX_API_URL:
            return FakeResponse(MATRIX)
        return FakeResponse({"places": [PLACE]})

    monkeypatch.setattr(backend_app_module.requests, "post", fake_post)

    search(client)

    places_calls = [c for c in calls if c["url"] == backend_app_module.PLACES_TEXT_SEARCH_URL]
    assert places_calls
    first = places_calls[0]
    assert first["headers"]["X-Goog-FieldMask"] == backend_app_module.PLACES_FIELD_MASK
    assert first["headers"]["X-Goog-Api-Key"] == "test-key"
    assert first["json"]["textQuery"] == "pharmacy"
    # A bias circle would let far-away results through; the restriction
    # rectangle is a hard limit, like the legacy Nearby Search radius.
    assert "locationBias" not in first["json"]
    box = first["json"]["locationRestriction"]["rectangle"]
    assert box["low"]["latitude"] < ROUTE[0][0] < box["high"]["latitude"]
    assert box["low"]["longitude"] < ROUTE[0][1] < box["high"]["longitude"]


def test_search_box_spans_the_search_radius_each_way():
    from haversine import Unit, haversine

    box = backend_app_module.search_box_around((30.7, 76.8), 15000)

    north = haversine((30.7, 76.8), (box["high"]["latitude"], 76.8), unit=Unit.METERS)
    east = haversine((30.7, 76.8), (30.7, box["high"]["longitude"]), unit=Unit.METERS)
    assert north == pytest.approx(15000, rel=0.01)
    assert east == pytest.approx(15000, rel=0.01)


def test_places_far_from_the_route_are_dropped(client, google_provider, monkeypatch):
    """Sample-point boxes are wider than the on-route distance, so Places can
    still return stops that are not actually near the route."""
    far_place = dict(PLACE, id="far", location={"latitude": 28.61, "longitude": 77.20})
    answer_places_with(monkeypatch, FakeResponse({"places": [PLACE, far_place]}))

    response = search(client)

    assert [stop["place_id"] for stop in response.get_json()["stops"]] == ["abc123"]


# --- free fallback ------------------------------------------------------------

@pytest.mark.parametrize("status_code", [403, 429, 503])
def test_places_failure_falls_back_to_openstreetmap(client, google_provider, monkeypatch, status_code):
    """A rejected key, an exhausted daily quota or an outage must still leave
    the user with stops when the free fallback is enabled."""
    overpass_calls = enable_free_fallback(monkeypatch)
    answer_places_with(monkeypatch, FakeResponse({"error": {}}, status_code))

    response = search(client)
    payload = response.get_json()

    assert response.status_code == 200
    assert [stop["name"] for stop in payload["stops"]] == ["OSM Pharmacy"]
    assert "OpenStreetMap" in payload["provider_notice"]
    assert overpass_calls == ["pharmacy"]


def test_fallback_results_are_not_cached(client, google_provider, monkeypatch):
    """The next search should try Google again rather than serve OSM results
    for STOP_CACHE_TTL_SECONDS."""
    enable_free_fallback(monkeypatch)
    answer_places_with(monkeypatch, FakeResponse({"error": {}}, 429))

    search(client)

    assert backend_app_module.stop_candidate_cache == {}


def test_empty_fallback_reports_a_retryable_notice(client, google_provider, monkeypatch):
    enable_free_fallback(monkeypatch, candidates={}, unavailable=True)
    answer_places_with(monkeypatch, FakeResponse({"error": {}}, 503))

    response = search(client)

    assert response.status_code == 200
    assert response.get_json()["stops"] == []
    assert "retry" in response.get_json()["provider_notice"].lower()


def test_successful_google_search_does_not_touch_overpass(client, google_provider, monkeypatch):
    overpass_calls = enable_free_fallback(monkeypatch)
    answer_places_with(monkeypatch, FakeResponse({}))

    search(client)

    assert overpass_calls == []


def test_places_calls_run_concurrently(client, google_provider, monkeypatch):
    """Sample points are independent, so total latency should be about one
    call, not the sum of all of them."""
    import threading
    import time as time_module

    long_route = [(30.70 + i * 0.001, 76.70 + i * 0.001) for i in range(400)]
    monkeypatch.setattr(
        backend_app_module, "get_decoded_route", lambda o, d: (long_route, STEPS, "google")
    )
    monkeypatch.setattr(backend_app_module, "GOOGLE_MAX_SEARCH_POINTS", 4)
    monkeypatch.setattr(backend_app_module, "GOOGLE_PLACES_MAX_PARALLEL", 4)
    state = {"active": 0, "peak": 0}
    lock = threading.Lock()

    def slow_post(url, *args, **kwargs):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time_module.sleep(0.2)
        with lock:
            state["active"] -= 1
        return FakeResponse({})

    monkeypatch.setattr(backend_app_module.requests, "post", slow_post)

    started = time_module.perf_counter()
    response = search(client)
    elapsed = time_module.perf_counter() - started

    assert response.status_code == 200
    assert state["peak"] == 4
    assert elapsed < 0.6


def test_places_request_asks_for_english_names(client, google_provider, monkeypatch):
    calls = []

    def fake_post(url, *args, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(MATRIX if url == backend_app_module.ROUTE_MATRIX_API_URL else {})

    monkeypatch.setattr(backend_app_module.requests, "post", fake_post)

    search(client)

    places_calls = [c for c in calls if c["url"] == backend_app_module.PLACES_TEXT_SEARCH_URL]
    assert places_calls and all(c["json"]["languageCode"] == "en" for c in places_calls)
