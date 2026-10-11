import uuid

from fastapi.testclient import TestClient
from test_hosted_worlds import TOKEN, headers, setup  # noqa: F401

from utilsim.hosted import setup as physical_setup
from utilsim.hosted.server import create_app


def create(client, value):
    value = {**value, 'configuration': {'schemaVersion': physical_setup.VERSION, 'physical': {
        'customerSentiment': {'enabled': True, 'initialTrust': 100, 'communityInfluence': 1}}}}
    response = client.post('/hosted/worlds', json=value, headers=headers())
    assert response.status_code == 200, response.text
    return response.json(), value


def event(**overrides):
    return {'commandId': str(uuid.uuid4()), 'expectedRevision': 0, 'effectiveDate': '2026-07-15',
        'action': 'schedule', 'reason': 'Public confidence scenario', 'causalReference': 'test',
        'eventDate': '2026-07-16', 'trustChange': -60, 'headline': 'Utility service in the news', **overrides}


def test_sentiment_setup_schedule_cancel_advance_and_restart(setup):  # noqa: F811
    root, _, value, _ = setup
    client = TestClient(create_app(root, TOKEN))
    created, value = create(client, value)
    assert created['initialization']['appliedCommands'] == 1
    base = '/hosted/worlds/' + created['id']
    endpoint = base + '/events/sentiment'
    command = event()
    receipt = client.post(endpoint, json=command, headers=headers()).json()
    cancelled = client.post(endpoint, json=event(expectedRevision=1, eventDate='2026-07-20'), headers=headers()).json()
    cancel = {'commandId': str(uuid.uuid4()), 'expectedRevision': 2, 'effectiveDate': '2026-07-15',
        'action': 'cancel', 'reason': 'Withdraw scenario', 'causalReference': 'test', 'newsId': cancelled['newsId']}
    assert client.post(endpoint, json=cancel, headers=headers()).status_code == 200
    assert client.post(base + '/advance', json={'through': '2026-07-17'}, headers=headers()).status_code == 200
    restarted = TestClient(create_app(root, TOKEN))
    view = restarted.get(endpoint, headers=headers()).json()
    assert view['communityTrust'] < 50 and len(view['history']) == 2
    assert sum(bool(n['applied']) for n in view['news']) == 1
    assert restarted.post(endpoint, json=command, headers=headers()).json() == receipt
    assert restarted.post('/hosted/worlds', json=value, headers=headers()).json()['id'] == created['id']
    assert restarted.post(endpoint, json={**cancel, 'commandId': str(uuid.uuid4()), 'newsId': receipt['newsId'],
        'effectiveDate': '2026-07-17', 'expectedRevision': 3}, headers=headers()).status_code == 422


def test_sentiment_readonly_auth_and_malformed_commands(setup):  # noqa: F811
    root, _, value, _ = setup
    app = create_app(root, TOKEN)
    client = TestClient(app)
    created, _ = create(client, value)
    endpoint = '/hosted/worlds/' + created['id'] + '/events/sentiment'
    world = app.state.library.library.world(created['id'])
    before = world.path.read_bytes()
    assert client.get(endpoint, headers=headers(user='other')).status_code == 404
    assert client.post(endpoint, json=event(), headers=headers(role='analyst')).status_code == 403
    for extra in ({'trustChange': True}, {'trustChange': 101}, {'actorId': 'world-admin'}, {'action': []},
                  {'eventDate': '2026-07-14'}, {'expectedRevision': 1}, {'commandId': None}):
        result = client.post(endpoint, json=event(**extra), headers=headers())
        assert result.status_code == 422, result.text
    for query in ('?limit=51', '?before=bad', '?newsBefore=0', '?premiseId=unknown'):
        assert client.get(endpoint + query, headers=headers()).status_code == 422
    assert client.get(endpoint, headers=headers()).status_code == 200
    assert world.path.read_bytes() == before
