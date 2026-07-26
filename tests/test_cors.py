from importlib import import_module

import pytest

backend_app_module = import_module("backend.app")

parse_allowed_origins = backend_app_module.parse_allowed_origins


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, []),
        ("", []),
        ("   ", []),
        (",,", []),
        ("https://a.example", ["https://a.example"]),
        (
            "https://a.example, https://b.example",
            ["https://a.example", "https://b.example"],
        ),
        ("  https://a.example  ,, https://b.example ", ["https://a.example", "https://b.example"]),
    ],
)
def test_parse_allowed_origins(raw, expected):
    assert parse_allowed_origins(raw) == expected


def test_no_cors_header_for_foreign_origin_by_default(client):
    """With no WAYWISE_ALLOWED_ORIGINS configured, a third-party page must not
    be able to read API responses from a deployment."""
    response = client.get("/health", headers={"Origin": "https://not-waywise.example"})

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_same_origin_requests_are_unaffected(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
