from importlib import import_module

backend_app_module = import_module("backend.app")

MAX_LOCATION = backend_app_module.MAX_LOCATION_INPUT_LENGTH
MAX_QUERY = backend_app_module.MAX_QUERY_INPUT_LENGTH


def search(client, **overrides):
    params = {"origin": "Chandigarh", "destination": "Shimla", "query": "pharmacy"}
    params.update(overrides)
    return client.get("/find_stops", query_string=params)


def test_over_long_origin_is_rejected(client):
    response = search(client, origin="x" * (MAX_LOCATION + 1))
    assert response.status_code == 400
    assert "characters or fewer" in response.get_json()["error"]


def test_over_long_destination_is_rejected(client):
    response = search(client, destination="x" * (MAX_LOCATION + 1))
    assert response.status_code == 400
    assert "characters or fewer" in response.get_json()["error"]


def test_over_long_query_is_rejected(client):
    response = search(client, query="x" * (MAX_QUERY + 1))
    assert response.status_code == 400
    assert "characters or fewer" in response.get_json()["error"]


def test_rejected_input_never_reaches_the_cache(client, monkeypatch):
    """The point of the cap: unbounded distinct keys grow the caches forever."""
    monkeypatch.setattr(backend_app_module, "stop_candidate_cache", {})
    monkeypatch.setattr(backend_app_module, "route_cache", {})
    monkeypatch.setattr(backend_app_module, "geocode_cache", {})

    search(client, origin="x" * (MAX_LOCATION + 1))

    assert backend_app_module.stop_candidate_cache == {}
    assert backend_app_module.route_cache == {}
    assert backend_app_module.geocode_cache == {}


def test_a_realistic_reverse_geocoded_address_still_works(client, monkeypatch):
    """The GPS button fills these fields from a Nominatim display_name, which is
    long but nowhere near the cap. This must not start 400ing."""
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", True)
    address = (
        "Shop 12, Sector 17 Plaza, Sector 17C, Chandigarh, "
        "Chandigarh District, Chandigarh, 160017, India"
    )
    assert len(address) < MAX_LOCATION

    response = search(client, origin=address, destination="Shimla")

    assert response.status_code == 200


def test_input_exactly_at_the_limit_is_accepted(client, monkeypatch):
    monkeypatch.setattr(backend_app_module, "MOCK_MODE", True)
    response = search(client, origin="x" * MAX_LOCATION)
    assert response.status_code == 200
