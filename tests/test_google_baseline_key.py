from importlib import import_module

backend_app_module = import_module("backend.app")

SERVER_KEY = "SERVER-SIDE-BILLED-KEY-DO-NOT-LEAK"
BROWSER_KEY = "BROWSER-RESTRICTED-KEY"


def test_server_key_is_never_rendered_into_the_page(client, monkeypatch):
    """The server key pays for Directions/Places/Distance Matrix and is not
    referrer-restricted, so it must not reach the browser."""
    monkeypatch.setattr(backend_app_module, "API_KEY", SERVER_KEY)
    monkeypatch.delenv("GOOGLE_MAPS_JS_API_KEY", raising=False)

    response = client.get("/google-baseline")

    assert response.status_code == 200
    assert SERVER_KEY not in response.get_data(as_text=True)


def test_browser_key_is_prefilled_when_configured(client, monkeypatch):
    monkeypatch.setattr(backend_app_module, "API_KEY", SERVER_KEY)
    monkeypatch.setenv("GOOGLE_MAPS_JS_API_KEY", BROWSER_KEY)

    response = client.get("/google-baseline")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert BROWSER_KEY in body
    assert SERVER_KEY not in body
