"""Coverage for /find_stops, the core endpoint.

Weighted towards the invariants that keep billed call volume down, since
those are the ones that cost money when they regress.
"""
from importlib import import_module

import pytest

backend_app_module = import_module("backend.app")

ROUTE = [(30.7333, 76.7794), (30.75, 76.80), (30.77, 76.82), (31.10, 77.17)]
STEPS = ["Head north", "Continue on the highway"]


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def search(client, **overrides):
    params = {"origin": "Chandigarh", "destination": "Shimla", "query": "pharmacy"}
    params.update(overrides)
    return client.get("/find_stops", query_string=params)


# --- parameter validation ---------------------------------------------------

@pytest.mark.parametrize(
    "params",
    [
        pytest.param({}, id="nothing"),
        pytest.param({"origin": "Chandigarh"}, id="origin-only"),
        pytest.param({"destination": "Shimla"}, id="destination-only"),
    ],
)
def test_missing_origin_or_destination_is_rejected(client, params):
    response = client.get("/find_stops", query_string=params)
    assert response.status_code == 400
    assert "origin, destination" in response.get_json()["error"]


def test_missing_query_is_rejected(client):
    response = client.get(
        "/find_stops", query_string={"origin": "Chandigarh", "destination": "Shimla"}
    )
    assert response.status_code == 400
    assert "query" in response.get_json()["error"]


@pytest.mark.parametrize(
    "live_lat,live_lng",
    [
        pytest.param("30.7", None, id="lat-without-lng"),
        pytest.param(None, "76.7", id="lng-without-lat"),
        pytest.param("not-a-number", "76.7", id="non-numeric"),
        pytest.param("91", "76.7", id="lat-out-of-range"),
        pytest.param("30.7", "181", id="lng-out-of-range"),
    ],
)
def test_invalid_live_coordinates_are_rejected(client, live_lat, live_lng):
    params = {}
    if live_lat is not None:
        params["live_lat"] = live_lat
    if live_lng is not None:
        params["live_lng"] = live_lng
    response = search(client, **params)
    assert response.status_code == 400


def test_null_island_coordinates_are_treated_as_a_real_fix(client, monkeypatch):
    """lat/lng of exactly 0.0 is a valid GPS fix, not a missing one. Truthiness
    checks used to drop it."""
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", True)

    response = search(client, live_lat="0.0", live_lng="0.0", query="petrol")

    assert response.status_code == 200
    stops = response.get_json()["stops"]
    assert stops
    # Scoring only runs when the fix was accepted.
    assert all("score_seconds" in stop for stop in stops)


# --- route_only bootstrap ---------------------------------------------------

@pytest.mark.parametrize("query", ["route_only", "none", "__route_only__"])
def test_route_only_returns_the_route_without_stops(client, monkeypatch, query):
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", False)
    monkeypatch.setattr(
        backend_app_module, "get_decoded_route", lambda o, d: (ROUTE, STEPS, "free")
    )

    response = search(client, query=query)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["stops"] == []
    assert payload["route_coordinates"]
    assert payload["directions"] == STEPS


def test_route_only_makes_no_poi_or_ranking_calls(client, monkeypatch):
    """The navigation bootstrap fires on every trip start. If it ever reaches
    Places/Overpass or a ranking matrix it silently doubles the cost of a trip."""
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", False)
    monkeypatch.setattr(
        backend_app_module, "get_decoded_route", lambda o, d: (ROUTE, STEPS, "free")
    )

    def explode(*args, **kwargs):
        raise AssertionError("route_only must not make outbound HTTP calls")

    monkeypatch.setattr(backend_app_module.requests, "get", explode)

    assert search(client, query="route_only").status_code == 200


# --- mock mode --------------------------------------------------------------

def test_mock_mode_ranks_stops_ahead_of_the_user_first(client, monkeypatch):
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", True)

    response = search(client, query="petrol", live_lat="30.7333", live_lng="76.7794")
    stops = response.get_json()["stops"]

    assert response.status_code == 200
    assert len(stops) >= 2
    scores = [stop["score_seconds"] for stop in stops]
    assert scores == sorted(scores), "stops must come back in ascending score order"


def test_backtrack_penalty_is_applied_to_stops_behind_the_user(client, monkeypatch):
    """A stop the driver has already passed must be penalised, not offered as
    the nearest option."""
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", True)

    # Sit near the end of the Chandigarh -> Shimla route so the mock stops,
    # which cluster earlier along it, fall behind the current position.
    response = search(client, query="petrol", live_lat="31.1048", live_lng="77.1734")
    stops = response.get_json()["stops"]

    penalised = [s for s in stops if s.get("backtrack_penalty_seconds")]
    assert penalised, "expected at least one stop behind the user to be penalised"
    for stop in penalised:
        assert stop["ahead_of_user"] is False
        assert stop["score_seconds"] > stop["duration_seconds"]


def test_route_failure_returns_404_for_a_stop_search(client, monkeypatch):
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", False)
    monkeypatch.setattr(
        backend_app_module, "get_decoded_route", lambda o, d: (None, None, None)
    )

    response = search(client)

    assert response.status_code == 404
    assert "route" in response.get_json()["error"].lower()


# --- caching ----------------------------------------------------------------

def test_repeat_search_is_served_from_the_ranked_cache(client, monkeypatch):
    """The ranked cache is what stops a repeat search from re-running the billed
    Distance Matrix call. If it regresses, every repeat search costs again."""
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", "google")
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", False)
    monkeypatch.setattr(backend_app_module, "API_KEY", "test-key")
    monkeypatch.setattr(backend_app_module, "stop_candidate_cache", {})
    monkeypatch.setattr(backend_app_module, "ranked_stops_cache", {})
    monkeypatch.setattr(
        backend_app_module, "get_decoded_route", lambda o, d: (ROUTE, STEPS, "google")
    )

    calls = {"places": 0, "matrix": 0}
    places_payload = {
        "status": "OK",
        "results": [
            {
                "place_id": "p1",
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
            calls["matrix"] += 1
            return FakeResponse(matrix_payload)
        calls["places"] += 1
        return FakeResponse(places_payload)

    monkeypatch.setattr(backend_app_module.requests, "get", fake_get)

    first = search(client)
    after_first = dict(calls)
    second = search(client)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.get_json()["stops"] == first.get_json()["stops"]
    assert calls == after_first, "repeat search must not re-call Places or Distance Matrix"


def test_google_places_sample_points_stay_capped_on_a_long_route(client, monkeypatch):
    """Places calls must scale with the cap, not with route length."""
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", "google")
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", False)
    monkeypatch.setattr(backend_app_module, "API_KEY", "test-key")
    monkeypatch.setattr(backend_app_module, "stop_candidate_cache", {})
    monkeypatch.setattr(backend_app_module, "ranked_stops_cache", {})

    long_route = [(30.0 + i * 0.001, 76.0 + i * 0.001) for i in range(1000)]
    monkeypatch.setattr(
        backend_app_module, "get_decoded_route", lambda o, d: (long_route, STEPS, "google")
    )

    calls = {"places": 0}

    def fake_get(url, *args, **kwargs):
        calls["places"] += 1
        return FakeResponse({"status": "ZERO_RESULTS", "results": []})

    monkeypatch.setattr(backend_app_module.requests, "get", fake_get)

    response = search(client)

    assert response.status_code == 200
    assert calls["places"] <= backend_app_module.GOOGLE_MAX_SEARCH_POINTS
