"""is_on_route must give the same answer as a plain haversine scan."""
import random
from importlib import import_module

import pytest
from haversine import Unit, haversine

backend_app_module = import_module("backend.app")
is_on_route = backend_app_module.is_on_route


def reference_is_on_route(place, route, max_distance_meters):
    return any(
        haversine((place["lat"], place["lng"]), point, unit=Unit.METERS) <= max_distance_meters
        for point in route
    )


@pytest.mark.parametrize("base_lat", [-60.0, 0.0, 30.7, 70.0])
def test_matches_a_full_haversine_scan(base_lat):
    rng = random.Random(base_lat)
    route = [(base_lat + i * 0.0003, 10 + i * 0.0004) for i in range(200)]
    for _ in range(200):
        anchor = rng.choice(route)
        place = {
            "lat": anchor[0] + rng.uniform(-0.03, 0.03),
            "lng": anchor[1] + rng.uniform(-0.06, 0.06),
        }
        for max_distance in (500, 1500):
            assert is_on_route(place, route, max_distance) == reference_is_on_route(place, route, max_distance)


def test_point_just_inside_and_outside_the_limit():
    route = [(30.0, 76.0)]
    meters_per_degree = haversine((30.0, 76.0), (31.0, 76.0), unit=Unit.METERS)

    assert is_on_route({"lat": 30.0 + 1490 / meters_per_degree, "lng": 76.0}, route)
    assert not is_on_route({"lat": 30.0 + 1510 / meters_per_degree, "lng": 76.0}, route)


def test_far_place_is_rejected_and_empty_route_is_off_route():
    assert not is_on_route({"lat": 28.6, "lng": 77.2}, [(30.7, 76.7), (31.1, 77.1)])
    assert not is_on_route({"lat": 28.6, "lng": 77.2}, [])
