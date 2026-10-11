import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from test_hosted_worlds import TOKEN, headers, setup  # noqa: F401
from test_world_cruise import command as cruise_command

from utilsim.hosted.server import create_app
from utilsim.world import cruise, delivery
from utilsim.world.store import World


def schedule(**overrides):
    return {'commandId': str(uuid.uuid4()), 'expectedRevision': 0, 'effectiveDate': '2026-07-15',
            'action': 'schedule', 'reason': 'Physical weather test', 'causalReference': 'hosted-acceptance',
            'startDate': '2026-07-16', 'endDate': '2026-07-18', 'temperatureOffsetC': -12,
            'multipliers': dict.fromkeys(('electric', 'gas', 'water', 'sewer'), 3), **overrides}


def cancel(storm_id, revision, effective='2026-07-15'):
    return {'commandId': str(uuid.uuid4()), 'expectedRevision': revision, 'effectiveDate': effective,
            'action': 'cancel', 'reason': 'Cancel before start', 'causalReference': 'hosted-acceptance', 'stormId': storm_id}


@pytest.fixture
def runtime(setup):  # noqa: F811 - imported pytest fixture
    root, template, value, _ = setup
    app = create_app(root, TOKEN)
    client = TestClient(app)
    first = client.post('/hosted/worlds', json=value, headers=headers()).json()
    return app, client, '/hosted/worlds/' + first['id'], first, template


def test_real_storm_schedule_advance_history_restart_and_cancellation(runtime):
    app, client, base, first, template = runtime
    before_source = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in template.iterdir()}
    endpoint = base + '/events/storms'
    assert client.get(endpoint, headers=headers()).json()['enabled'] is False
    command = schedule()
    response = client.post(endpoint, json=command, headers=headers())
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert client.post(endpoint, json=command, headers=headers()).json() == receipt
    assert client.post(endpoint, json={**schedule(), 'expectedRevision': 1}, headers=headers()).status_code == 422  # overlap
    cancelled_command = cancel(receipt['stormId'], 1)
    cancelled = client.post(endpoint, json=cancelled_command, headers=headers())
    assert cancelled.status_code == 200
    active = schedule(expectedRevision=2)
    result = client.post(endpoint, json=active, headers=headers()).json()
    assert result['revision'] == 3
    advanced = client.post(base + '/advance', json={'through': '2026-07-18'}, headers=headers())
    assert advanced.status_code == 200, advanced.text
    view = client.get(endpoint, headers=headers()).json()
    assert len(view['history']) == 2
    assert {e['stormId'] for e in view['history']} == {result['stormId']}
    assert all(e['temperatureC'] == round(e['baselineTemperatureC'] - 12, 2) for e in view['history'])
    assert client.post(endpoint, json=cancel(result['stormId'], 3, '2026-07-18'), headers=headers()).status_code == 422
    readonly = app.state.library.library.world(first['id'])
    with readonly.read_db() as db:
        assert all(db.execute('SELECT temperature FROM days WHERE day=?', (e['day'],)).fetchone()[0] == e['temperatureC'] for e in view['history'])
        assert db.execute('SELECT COUNT(*) FROM observations').fetchone()[0] > 0
        assert db.execute("SELECT COUNT(*) FROM events WHERE type='StormWeatherApplied'").fetchone()[0] == 2
    restarted = TestClient(create_app(app.state.library.root, TOKEN))
    assert restarted.get(endpoint, headers=headers()).json() == view
    assert restarted.post(endpoint, json=active, headers=headers()).json() == result
    first_page = restarted.get(base + '/events?limit=2', headers=headers()).json()
    second_page = restarted.get(base + '/events', params={'before': first_page['nextBefore'], 'limit': 50}, headers=headers()).json()
    assert {e['sequence'] for e in first_page['events']}.isdisjoint({e['sequence'] for e in second_page['events']})
    assert 'StormWeatherApplied' in {e['type'] for e in first_page['events'] + second_page['events']}
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == before_source[p.name] for p in template.iterdir())


def test_storm_authorization_validation_and_immutable_inspection(runtime):
    app, client, base, first, _ = runtime
    endpoint = base + '/events/storms'
    world = app.state.library.library.world(first['id'])
    before = world.path.read_bytes()
    for path in (endpoint, base + '/events'):
        assert client.get(path, headers=headers(user='other')).status_code == 404
        assert client.get(path, headers=headers()).status_code == 200
    for supplied_headers, code in ((headers(user='other'), 404), (headers(role='analyst'), 403), (headers(town='other'), 403)):
        assert client.post(endpoint, json=schedule(), headers=supplied_headers).status_code == code
    for override in ({'actorId': 'world-admin'}, {'environmentId': first['environmentId']}, {'worldFingerprint': first['fingerprint']},
                     {'temperatureOffsetC': True}, {'temperatureOffsetC': 41}, {'multipliers': {}},
                     {'expectedRevision': 9}, {'effectiveDate': '2026-07-16'}, {'commandId': None}, {'action': []}):
        response = client.post(endpoint, json=schedule(**override), headers=headers())
        assert response.status_code == 422, response.text
    for query in ('?before=bad', '?eventsBefore=bad', '?limit=51'):
        assert client.get(endpoint + query, headers=headers()).status_code == 422
    assert world.path.read_bytes() == before


def test_managed_and_cruise_clock_owners_block_storm_and_advance(runtime):
    app, client, base, first, _ = runtime
    world = World(app.state.library.library.world(first['id']).path)
    cruise.command(world, cruise_command(world, targetDate='2026-07-20'))
    for path, value in ((base + '/events/storms', schedule()), (base + '/advance', {'through': '2026-07-16'})):
        response = client.post(path, json=value, headers=headers())
        assert response.status_code == 422 and 'cruise owns' in response.json()['detail']
    cruise.command(world, cruise_command(world, 'cancel'))
    delivery.configure(world, first['environmentId'])
    for path, value in ((base + '/events/storms', schedule()), (base + '/advance', {'through': '2026-07-16'})):
        response = client.post(path, json=value, headers=headers())
        assert response.status_code == 422 and 'Shared delivery owns' in response.json()['detail']
