import pytest


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({}, id="no-body"),
        pytest.param({"data": "hello", "content_type": "text/plain"}, id="wrong-content-type"),
        pytest.param({"data": "{not json", "content_type": "application/json"}, id="malformed-json"),
        pytest.param({"data": "null", "content_type": "application/json"}, id="json-null"),
        pytest.param({"data": "[1, 2]", "content_type": "application/json"}, id="json-array"),
    ],
)
def test_chat_rejects_non_object_bodies_with_json_400(client, kwargs):
    """These previously returned an HTML 415/400 or crashed with a 500."""
    response = client.post("/chat", **kwargs)
    assert response.status_code == 400
    assert response.is_json
    assert "error" in response.get_json()


def test_chat_tolerates_non_string_message(client):
    """message=123 used to raise AttributeError on .lower() and return a 500."""
    response = client.post("/chat", json={"message": 123})
    assert response.status_code == 200
    assert response.get_json()["reply"]


def test_chat_missing_message_returns_generic_reply(client):
    response = client.post("/chat", json={})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["action"] is None
    assert payload["reply"]


@pytest.mark.parametrize(
    "message,expected_action",
    [
        ("navigate to Shimla", "navigate"),
        ("find petrol", "find_stops"),
        ("play music", "music"),
        ("hello there", None),
    ],
)
def test_chat_intents_still_route(client, message, expected_action):
    response = client.post("/chat", json={"message": message})
    assert response.status_code == 200
    assert response.get_json()["action"] == expected_action


@pytest.mark.parametrize(
    "message,expected_query",
    [
        ("find a pharmacy", "pharmacy"),
        ("find a chemist nearby", "pharmacy"),
        ("find medicine", "pharmacy"),
        ("find petrol", "petrol pump"),
        ("find fuel", "petrol pump"),
        ("find an atm", "atm"),
        ("find a bank", "atm"),
        ("find a dhaba", "dhaba"),
        ("find something to eat", "restaurant"),
    ],
)
def test_chat_covers_every_quick_search_stop_type(client, message, expected_query):
    """index.html offers Fuel / Food / Pharmacy / ATM. Pharmacy and ATM used to
    fall through to the restaurant default, so chat could not reach them."""
    response = client.post("/chat", json={"message": message})
    assert response.status_code == 200
    assert response.get_json()["data"]["query"] == expected_query
