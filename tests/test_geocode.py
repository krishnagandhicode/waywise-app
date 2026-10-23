"""Geocoding falls back from Nominatim to Photon."""
from importlib import import_module

import pytest
import requests

backend_app_module = import_module("backend.app")
geocode_location = backend_app_module.geocode_location

NOMINATIM_HIT = [{"lat": "30.7333", "lon": "76.7794"}]
PHOTON_HIT = {"features": [{"geometry": {"type": "Point", "coordinates": [77.1734, 31.1048]}}]}


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
def geocoders(monkeypatch):
    """Routes requests.get to canned Nominatim/Photon answers and counts calls."""
    monkeypatch.setattr(backend_app_module, "geocode_cache", {})
    monkeypatch.setattr(backend_app_module, "nominatim_blocked_until", 0.0)
    calls = {"nominatim": 0, "photon": 0}
    answers = {"nominatim": FakeResponse(NOMINATIM_HIT), "photon": FakeResponse(PHOTON_HIT)}

    def fake_get(url, *args, **kwargs):
        name = "nominatim" if url == backend_app_module.NOMINATIM_SEARCH_URL else "photon"
        calls[name] += 1
        answer = answers[name]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(backend_app_module.requests, "get", fake_get)
    return calls, answers


def test_nominatim_answer_is_used_without_photon(geocoders):
    calls, _answers = geocoders

    assert geocode_location("Chandigarh") == {"lat": 30.7333, "lng": 76.7794}
    assert calls == {"nominatim": 1, "photon": 0}


def test_rate_limited_nominatim_falls_back_to_photon(geocoders):
    """Shared hosting IPs get 429 from Nominatim even at low volume."""
    calls, answers = geocoders
    answers["nominatim"] = FakeResponse([], status_code=429)

    assert geocode_location("Shimla") == {"lat": 31.1048, "lng": 77.1734}
    assert calls == {"nominatim": 1, "photon": 1}


def test_nominatim_is_skipped_for_a_while_after_a_429(geocoders):
    calls, answers = geocoders
    answers["nominatim"] = FakeResponse([], status_code=429)

    geocode_location("Shimla")
    geocode_location("Delhi")

    assert calls == {"nominatim": 1, "photon": 2}


def test_nominatim_is_retried_once_the_back_off_expires(geocoders, monkeypatch):
    calls, answers = geocoders
    answers["nominatim"] = FakeResponse([], status_code=429)
    geocode_location("Shimla")

    monkeypatch.setattr(backend_app_module, "nominatim_blocked_until", 0.0)
    answers["nominatim"] = FakeResponse(NOMINATIM_HIT)
    geocode_location("Delhi")

    assert calls == {"nominatim": 2, "photon": 1}


def test_other_nominatim_errors_fall_back_without_a_back_off(geocoders):
    calls, answers = geocoders
    answers["nominatim"] = requests.exceptions.Timeout("slow")

    assert geocode_location("Shimla") == {"lat": 31.1048, "lng": 77.1734}
    assert backend_app_module.nominatim_blocked_until == 0.0


def test_nominatim_finding_nothing_asks_photon(geocoders):
    calls, answers = geocoders
    answers["nominatim"] = FakeResponse([])

    assert geocode_location("Some small village") == {"lat": 31.1048, "lng": 77.1734}
    assert calls == {"nominatim": 1, "photon": 1}


def test_both_failing_raises_so_the_route_reports_an_error(geocoders):
    _calls, answers = geocoders
    answers["nominatim"] = FakeResponse([], status_code=429)
    answers["photon"] = FakeResponse({}, status_code=503)

    with pytest.raises(requests.exceptions.RequestException):
        geocode_location("Shimla")
    assert backend_app_module.geocode_cache == {}


def test_no_match_anywhere_returns_none_and_is_not_cached(geocoders):
    _calls, answers = geocoders
    answers["nominatim"] = FakeResponse([])
    answers["photon"] = FakeResponse({"features": []})

    assert geocode_location("qwxyz nowhere") is None
    assert backend_app_module.geocode_cache == {}


def test_results_are_cached_across_both_geocoders(geocoders):
    calls, answers = geocoders
    answers["nominatim"] = FakeResponse([], status_code=429)

    geocode_location("Shimla")
    geocode_location("  shimla ")

    assert calls == {"nominatim": 1, "photon": 1}


def test_free_route_survives_a_rate_limited_nominatim(geocoders, monkeypatch):
    """The live failure: every route 502'd while Nominatim answered 429."""
    import polyline

    calls, answers = geocoders
    answers["nominatim"] = FakeResponse([], status_code=429)
    osrm_route = {
        "code": "Ok",
        "routes": [{
            "geometry": polyline.encode([(30.73, 76.78), (31.10, 77.17)]),
            "legs": [{"steps": [{"maneuver": {"type": "depart"}, "name": "NH5"}]}],
        }],
    }
    real_get = backend_app_module.requests.get

    def get_with_osrm(url, *args, **kwargs):
        if "/route/v1/" in url:
            return FakeResponse(osrm_route)
        return real_get(url, *args, **kwargs)

    monkeypatch.setattr(backend_app_module.requests, "get", get_with_osrm)

    coordinates, steps = backend_app_module.get_route_with_osrm("Chandigarh", "Shimla")

    assert len(coordinates) == 2
    assert steps == ["Depart on NH5"]
    assert calls["photon"] == 2
