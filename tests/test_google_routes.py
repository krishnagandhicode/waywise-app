"""Google route lookup via the Routes API (computeRoutes)."""
from importlib import import_module

import polyline
import pytest
import requests

backend_app_module = import_module("backend.app")

ROUTE = [(30.7333, 76.7794), (30.75, 76.8), (31.1048, 77.1734)]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


def routes_payload(legs):
    return {
        "routes": [
            {
                "polyline": {"encodedPolyline": polyline.encode(ROUTE)},
                "legs": legs,
            }
        ]
    }


def step(text):
    return {"navigationInstruction": {"maneuver": "TURN_LEFT", "instructions": text}}


@pytest.fixture
def capture_post(monkeypatch):
    """Records each requests.post call and answers with the queued payload."""
    monkeypatch.setattr(backend_app_module, "API_KEY", "test-key")
    calls = []
    state = {"response": FakeResponse({})}

    def fake_post(url, *args, **kwargs):
        calls.append({"url": url, **kwargs})
        return state["response"]

    monkeypatch.setattr(backend_app_module.requests, "post", fake_post)

    def respond_with(payload, status_code=200):
        state["response"] = FakeResponse(payload, status_code)

    return calls, respond_with


def test_route_and_steps_are_parsed(capture_post):
    calls, respond_with = capture_post
    respond_with(routes_payload([{"steps": [step("Head north on NH5"), step("Turn left")]}]))

    coordinates, steps = backend_app_module.get_route_with_google("Chandigarh", "Shimla")

    assert coordinates == ROUTE
    assert steps == ["Head north on NH5", "Turn left"]


def test_steps_are_flattened_across_legs(capture_post):
    _calls, respond_with = capture_post
    respond_with(routes_payload([{"steps": [step("First leg")]}, {"steps": [step("Second leg")]}]))

    _coordinates, steps = backend_app_module.get_route_with_google("A", "B")

    assert steps == ["First leg", "Second leg"]


def test_request_sends_key_in_header_with_a_field_mask(capture_post):
    calls, respond_with = capture_post
    respond_with(routes_payload([{"steps": [step("Go")]}]))

    backend_app_module.get_route_with_google("Chandigarh", "Shimla")

    call = calls[0]
    assert call["url"] == backend_app_module.ROUTES_API_URL
    assert call["headers"]["X-Goog-Api-Key"] == "test-key"
    assert call["headers"]["X-Goog-FieldMask"] == backend_app_module.ROUTES_FIELD_MASK
    assert "test-key" not in call["url"]
    assert call["json"]["origin"] == {"address": "Chandigarh"}
    assert call["json"]["destination"] == {"address": "Shimla"}


def test_route_without_steps_gets_generic_instructions(capture_post):
    """get_decoded_route treats empty steps as a failed lookup, so a route that
    came back without instructions must still yield some."""
    _calls, respond_with = capture_post
    respond_with(routes_payload([{"steps": [{}]}]))

    coordinates, steps = backend_app_module.get_route_with_google("A", "B")

    assert coordinates == ROUTE
    assert steps


def test_no_route_raises_value_error(capture_post):
    """Routes API answers an unroutable pair with an empty object."""
    _calls, respond_with = capture_post
    respond_with({})

    with pytest.raises(ValueError):
        backend_app_module.get_route_with_google("Nowhere", "Elsewhere")


def test_http_error_raises_request_exception(capture_post):
    _calls, respond_with = capture_post
    respond_with({"error": {"status": "PERMISSION_DENIED"}}, status_code=403)

    with pytest.raises(requests.exceptions.RequestException):
        backend_app_module.get_route_with_google("A", "B")


def test_missing_key_raises_value_error(monkeypatch):
    monkeypatch.setattr(backend_app_module, "API_KEY", None)

    with pytest.raises(ValueError):
        backend_app_module.get_route_with_google("A", "B")


def test_routes_api_failure_falls_back_to_the_free_route(capture_post, monkeypatch):
    _calls, respond_with = capture_post
    respond_with({"error": {"status": "PERMISSION_DENIED"}}, status_code=403)
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", "google")
    monkeypatch.setattr(backend_app_module, "GOOGLE_FALLBACK_ENABLED", True)
    monkeypatch.setattr(backend_app_module, "route_cache", {})
    monkeypatch.setattr(
        backend_app_module, "get_route_with_osrm", lambda o, d: (ROUTE, ["Free step"])
    )

    coordinates, steps, provider = backend_app_module.get_decoded_route("A", "B")

    assert provider == "free"
    assert steps == ["Free step"]
