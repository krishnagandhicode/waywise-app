"""Google stop ranking via the Routes API (computeRouteMatrix)."""
from importlib import import_module

import pytest
import requests

backend_app_module = import_module("backend.app")

rank = backend_app_module.rank_stops_with_google_matrix


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


def make_stops():
    return [
        {"name": "Far", "location": {"lat": 30.9, "lng": 76.9}},
        {"name": "Near", "location": {"lat": 30.75, "lng": 76.8}},
        {"name": "Middle", "location": {"lat": 30.8, "lng": 76.85}},
    ]


@pytest.fixture
def matrix_post(monkeypatch):
    monkeypatch.setattr(backend_app_module, "API_KEY", "test-key")
    calls = []
    state = {"response": FakeResponse([])}

    def fake_post(url, *args, **kwargs):
        calls.append({"url": url, **kwargs})
        return state["response"]

    monkeypatch.setattr(backend_app_module.requests, "post", fake_post)

    def respond_with(payload, status_code=200):
        state["response"] = FakeResponse(payload, status_code)

    return calls, respond_with


def element(destination_index, seconds, meters, **extra):
    item = {"status": {}, "condition": "ROUTE_EXISTS", "duration": f"{seconds}s", "distanceMeters": meters}
    # Mirrors the API: zero-valued fields are omitted, so index 0 has no key.
    if destination_index:
        item["destinationIndex"] = destination_index
    item.update(extra)
    return item


def test_unordered_elements_are_matched_by_destination_index(matrix_post):
    """The API returns elements in any order; ranking must not assume position."""
    _calls, respond_with = matrix_post
    respond_with([element(2, 600, 8000), element(0, 1500, 20000), element(1, 300, 2500)])

    ranked = rank(make_stops(), (30.73, 76.77))

    assert [stop["name"] for stop in ranked] == ["Near", "Middle", "Far"]
    near = ranked[0]
    assert near["duration_seconds"] == 300
    assert near["duration"] == "5 mins"
    assert near["distance"] == "2.5 km"
    assert near["score_seconds"] == 300


def test_backtrack_penalty_is_added_to_the_score(matrix_post):
    _calls, respond_with = matrix_post
    respond_with([element(0, 1500, 20000), element(1, 300, 2500), element(2, 600, 8000)])
    stops = make_stops()
    stops[1]["backtrack_penalty_seconds"] = 900

    ranked = rank(stops, (30.73, 76.77))

    assert [stop["name"] for stop in ranked] == ["Middle", "Near", "Far"]


def test_failed_elements_leave_the_stop_unranked(matrix_post):
    _calls, respond_with = matrix_post
    respond_with([
        element(0, 100, 1000, condition="ROUTE_NOT_FOUND"),
        element(1, 300, 2500),
        element(2, 200, 1500, status={"code": 3, "message": "bad waypoint"}),
    ])

    ranked = rank(make_stops(), (30.73, 76.77))

    assert ranked[0]["name"] == "Near"
    assert "duration_seconds" not in ranked[1]
    assert "duration_seconds" not in ranked[2]


def test_fractional_durations_are_parsed():
    assert backend_app_module.parse_google_duration_seconds("3.5s") == 3
    assert backend_app_module.parse_google_duration_seconds("1234s") == 1234
    assert backend_app_module.parse_google_duration_seconds(None) is None


def test_live_position_is_sent_as_lat_lng(matrix_post):
    calls, respond_with = matrix_post
    respond_with([])

    rank(make_stops(), (30.73, 76.77))

    body = calls[0]["json"]
    assert body["origins"][0]["waypoint"] == {
        "location": {"latLng": {"latitude": 30.73, "longitude": 76.77}}
    }
    assert len(body["destinations"]) == 3
    assert calls[0]["headers"]["X-Goog-FieldMask"] == backend_app_module.ROUTE_MATRIX_FIELD_MASK
    assert "status" in backend_app_module.ROUTE_MATRIX_FIELD_MASK.split(",")


def test_origin_text_is_sent_as_an_address(matrix_post):
    calls, respond_with = matrix_post
    respond_with([])

    rank(make_stops(), "Chandigarh")

    assert calls[0]["json"]["origins"][0]["waypoint"] == {"address": "Chandigarh"}


def test_non_list_response_raises(matrix_post):
    _calls, respond_with = matrix_post
    respond_with({"error": {"status": "INVALID_ARGUMENT"}})

    with pytest.raises(ValueError):
        rank(make_stops(), "Chandigarh")


# --- through /find_stops ------------------------------------------------------

ROUTE = [(30.7333, 76.7794), (30.75, 76.80), (30.77, 76.82)]


@pytest.fixture
def google_search(monkeypatch):
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", "google")
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", False)
    monkeypatch.setattr(backend_app_module, "API_KEY", "test-key")
    monkeypatch.setattr(backend_app_module, "stop_candidate_cache", {})
    monkeypatch.setattr(backend_app_module, "ranked_stops_cache", {})
    monkeypatch.setattr(
        backend_app_module, "get_decoded_route", lambda o, d: (ROUTE, ["Head north"], "google")
    )
    places_payload = {
        "status": "OK",
        "results": [
            {"place_id": "p1", "name": "Test Pharmacy", "geometry": {"location": {"lat": 30.75, "lng": 76.80}}}
        ],
    }
    monkeypatch.setattr(
        backend_app_module.requests, "get", lambda *a, **kw: FakeResponse(places_payload)
    )


def test_matrix_failure_falls_back_to_straight_line_ranking(client, google_search, monkeypatch):
    """A ranking outage must not cost the user their stops."""
    monkeypatch.setattr(
        backend_app_module.requests,
        "post",
        lambda *a, **kw: FakeResponse({"error": {}}, status_code=503),
    )

    response = client.get(
        "/find_stops",
        query_string={
            "origin": "Chandigarh", "destination": "Shimla", "query": "pharmacy",
            "live_lat": "30.7333", "live_lng": "76.7794",
        },
    )

    assert response.status_code == 200
    stops = response.get_json()["stops"]
    assert [stop["name"] for stop in stops] == ["Test Pharmacy"]
    assert stops[0]["distance"].endswith("km")
