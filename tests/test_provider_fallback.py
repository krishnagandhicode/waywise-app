import pytest
from importlib import import_module

backend_app_module = import_module("backend.app")


def test_get_decoded_route_falls_back_to_free_when_google_fails(monkeypatch):
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", "google")
    monkeypatch.setattr(backend_app_module, "GOOGLE_FALLBACK_ENABLED", True)
    monkeypatch.setattr(backend_app_module, "route_cache", {})

    def failing_google_route(origin, destination):
        raise ValueError("Google provider is unavailable")

    def free_route(origin, destination):
        return [(30.0, 76.0), (30.1, 76.1)], ["Proceed on the route"]

    monkeypatch.setattr(backend_app_module, "get_route_with_google", failing_google_route)
    monkeypatch.setattr(backend_app_module, "get_route_with_osrm", free_route)

    coords, steps, provider = backend_app_module.get_decoded_route("Chandigarh", "Mohali")

    assert provider == "free"
    assert coords
    assert steps


def test_get_decoded_route_raises_when_google_fails_and_fallback_disabled(monkeypatch):
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", "google")
    monkeypatch.setattr(backend_app_module, "GOOGLE_FALLBACK_ENABLED", False)
    monkeypatch.setattr(backend_app_module, "route_cache", {})

    def failing_google_route(origin, destination):
        raise ValueError("Google provider is unavailable")

    monkeypatch.setattr(backend_app_module, "get_route_with_google", failing_google_route)

    with pytest.raises(ValueError):
        backend_app_module.get_decoded_route("Chandigarh", "Mohali")
