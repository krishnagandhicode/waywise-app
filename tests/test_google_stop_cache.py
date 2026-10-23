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
    assert first["json"]["locationBias"]["circle"]["center"] == {"latitude": ROUTE[0][0], "longitude": ROUTE[0][1]}


def test_places_far_from_the_route_are_dropped(client, google_provider, monkeypatch):
    """locationBias only biases results, so off-route places can come back."""
    far_place = dict(PLACE, id="far", location={"latitude": 28.61, "longitude": 77.20})
    answer_places_with(monkeypatch, FakeResponse({"places": [PLACE, far_place]}))

    response = search(client)

    assert [stop["place_id"] for stop in response.get_json()["stops"]] == ["abc123"]
