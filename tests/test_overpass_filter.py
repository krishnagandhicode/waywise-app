from importlib import import_module

import pytest

backend_app_module = import_module("backend.app")

get_overpass_filter_for_query = backend_app_module.get_overpass_filter_for_query

GENERIC_FILTER = '["amenity"~"restaurant|fast_food|cafe|fuel|atm"]'


@pytest.mark.parametrize(
    "query,expected",
    [
        ("pharmacy", '["amenity"="pharmacy"]'),
        ("Pharmacy", '["amenity"="pharmacy"]'),
        ("chemist shop", '["amenity"="pharmacy"]'),
        ("drugstore", '["amenity"="pharmacy"]'),
        ("medicine store", '["amenity"="pharmacy"]'),
    ],
)
def test_pharmacy_queries_map_to_pharmacy_amenity(query, expected):
    """The UI Pharmacy button sends query=pharmacy; it must not fall through
    to the generic filter, which returns restaurants, fuel and ATMs."""
    assert get_overpass_filter_for_query(query) == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("petrol pump", '["amenity"="fuel"]'),
        ("fuel", '["amenity"="fuel"]'),
        ("atm", '["amenity"="atm"]'),
        ("bank", '["amenity"="atm"]'),
        ("hospital", '["amenity"="hospital"]'),
        ("hotel", '["tourism"="hotel"]'),
        ("restaurant", '["amenity"~"restaurant|fast_food|cafe"]'),
        ("dhaba", '["amenity"~"restaurant|fast_food|cafe"]'),
    ],
)
def test_existing_query_mappings_are_unchanged(query, expected):
    assert get_overpass_filter_for_query(query) == expected


@pytest.mark.parametrize("query", ["", None, "something unmapped"])
def test_unmapped_queries_fall_back_to_generic_filter(query):
    assert get_overpass_filter_for_query(query) == GENERIC_FILTER
