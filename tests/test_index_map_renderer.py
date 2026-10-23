"""The index page picks its map renderer from the provider."""
from importlib import import_module

backend_app_module = import_module("backend.app")

SERVER_KEY = "SERVER-SIDE-BILLED-KEY-DO-NOT-LEAK"
BROWSER_KEY = "BROWSER-RESTRICTED-KEY"
LEAFLET_SCRIPT = "unpkg.com/leaflet/dist/leaflet.js"


def get_index(client, monkeypatch, provider, browser_key=None):
    monkeypatch.setattr(backend_app_module, "MAP_PROVIDER", provider)
    monkeypatch.setattr(backend_app_module, "API_KEY", SERVER_KEY)
    if browser_key:
        monkeypatch.setenv("GOOGLE_MAPS_JS_API_KEY", browser_key)
    else:
        monkeypatch.delenv("GOOGLE_MAPS_JS_API_KEY", raising=False)
    response = client.get("/")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_free_provider_renders_with_leaflet(client, monkeypatch):
    body = get_index(client, monkeypatch, "free")

    assert 'data-renderer="leaflet"' in body
    assert LEAFLET_SCRIPT in body


def test_google_provider_renders_with_google_maps(client, monkeypatch):
    """Google route and place results must not be drawn on OpenStreetMap tiles."""
    body = get_index(client, monkeypatch, "google", browser_key=BROWSER_KEY)

    assert 'data-renderer="google"' in body
    assert f'data-google-key="{BROWSER_KEY}"' in body
    assert LEAFLET_SCRIPT not in body


def test_server_key_is_never_rendered_into_the_page(client, monkeypatch):
    """With no browser key configured the page must not fall back to the
    billed, unrestricted server key."""
    body = get_index(client, monkeypatch, "google")

    assert SERVER_KEY not in body
    assert 'data-google-key=""' in body


def test_map_id_defaults_and_can_be_overridden(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_MAP_ID", raising=False)
    assert 'data-google-map-id="DEMO_MAP_ID"' in get_index(client, monkeypatch, "google")

    monkeypatch.setenv("GOOGLE_MAPS_MAP_ID", "abc123")
    assert 'data-google-map-id="abc123"' in get_index(client, monkeypatch, "google")
