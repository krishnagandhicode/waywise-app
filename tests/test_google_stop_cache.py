"""Google provider path: a transient Places failure must not poison the cache."""
from importlib import import_module

import pytest

backend_app_module = import_module("backend.app")

ROUTE = [(30.7333, 76.7794), (30.75, 76.80), (30.77, 76.82)]
STEPS = ["Head north"]


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


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


def search(client):
    return client.get(
        "/find_stops",
        query_string={"origin": "Chandigarh", "destination": "Shimla", "query": "pharmacy"},
    )


def test_transient_places_failure_is_not_cached(client, google_provider, monkeypatch):
    """UNKNOWN_ERROR is Google's documented retryable status. Caching the empty
    result would hide stops for STOP_CACHE_TTL_SECONDS after Google recovers."""
    monkeypatch.setattr(
        backend_app_module.requests,
        "get",
        lambda *a, **kw: FakeResponse({"status": "UNKNOWN_ERROR"}),
    )

    response = search(client)

    assert response.status_code == 200
    assert response.get_json()["stops"] == []
    assert backend_app_module.stop_candidate_cache == {}
    assert "provider_notice" in response.get_json()


def test_zero_results_is_cached_as_a_real_answer(client, google_provider, monkeypatch):
    """A genuinely empty area must cache, or every request re-bills Places."""
    monkeypatch.setattr(
        backend_app_module.requests,
        "get",
        lambda *a, **kw: FakeResponse({"status": "ZERO_RESULTS", "results": []}),
    )

    response = search(client)

    assert response.status_code == 200
    assert response.get_json()["stops"] == []
    assert len(backend_app_module.stop_candidate_cache) == 1


def test_successful_search_is_cached(client, google_provider, monkeypatch):
    places_payload = {
        "status": "OK",
        "results": [
            {
                "place_id": "abc123",
                "name": "Test Pharmacy",
                "rating": 4.5,
                "geometry": {"location": {"lat": 30.75, "lng": 76.80}},
            }
        ],
    }
    matrix_payload = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "status": "OK",
                        "distance": {"text": "2.0 km", "value": 2000},
                        "duration": {"text": "5 mins", "value": 300},
                    }
                ]
            }
        ],
    }

    def fake_get(url, *args, **kwargs):
        if url == backend_app_module.DISTANCE_MATRIX_API_URL:
            return FakeResponse(matrix_payload)
        return FakeResponse(places_payload)

    monkeypatch.setattr(backend_app_module.requests, "get", fake_get)

    response = search(client)
    stops = response.get_json()["stops"]

    assert response.status_code == 200
    assert [stop["name"] for stop in stops] == ["Test Pharmacy"]
    assert len(backend_app_module.stop_candidate_cache) == 1
