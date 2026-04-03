def test_health_endpoint_returns_ok(client):
    response = client.get('/health')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'ok'
    assert 'provider' in payload
    assert 'mock_mode' in payload
