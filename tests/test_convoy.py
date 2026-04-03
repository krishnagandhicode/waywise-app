def test_convoy_create_and_state_flow(client):
    create_resp = client.post('/convoy/create', json={'name': 'Tester', 'destination': 'Delhi'})
    assert create_resp.status_code == 200

    create_payload = create_resp.get_json()
    room_id = create_payload['room_id']
    member_id = create_payload['member_id']
    assert create_payload['destination'] == 'Delhi'

    destination_resp = client.post('/convoy/destination', json={
        'room_id': room_id,
        'member_id': member_id,
        'destination': 'Jaipur',
    })
    assert destination_resp.status_code == 200
    assert destination_resp.get_json()['destination'] == 'Jaipur'

    state_resp = client.get('/convoy/state', query_string={'room_id': room_id})
    assert state_resp.status_code == 200
    state_payload = state_resp.get_json()
    assert state_payload['room_id'] == room_id
    assert state_payload['destination'] == 'Jaipur'
    assert len(state_payload['members']) >= 1

    leave_resp = client.post('/convoy/leave', json={'room_id': room_id, 'member_id': member_id})
    assert leave_resp.status_code == 200
