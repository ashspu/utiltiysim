import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from test_world_creation import source

from utilsim.hosted.server import create_app
from utilsim.hosted.templates import sha
from utilsim.world.store import World, canonical

TOKEN = 'test-internal-gateway-token-32-characters'


def headers(user='user-a', role='owner', town='map-one'):
    return {'Authorization': 'Bearer ' + TOKEN, 'X-UtilitySim-User-Id': user,
            'X-UtilitySim-Grants': json.dumps([{'role': role, 'town': town}])}


@pytest.fixture
def setup(tmp_path):
    _, snapshot = source(tmp_path)
    root = tmp_path / 'store'
    files = {'source-snapshot.json': canonical(snapshot),
             'bindings.json': canonical({'premises': [
                 {'parcelId': 'parcel-' + p['id'], 'premiseId': p['id'], 'premiseType': 'residential',
                  'meterIds': [s['meterId'] for s in snapshot['servicePoints'] if s['premiseId'] == p['id']]}
                 for p in snapshot['premises']]})}
    manifest = {'sourceId': 'test-map', 'grantTownId': 'map-one', 'name': 'Test map', 'townId': snapshot['id'],
                'snapshotSha256': sha(canonical(snapshot).encode()), 'counts': {'premises': len(snapshot['premises'])},
                'files': {k: sha(v.encode()) for k, v in files.items()}}
    revision = sha(canonical(manifest).encode())
    template = root / 'templates' / 'test-map' / revision
    template.mkdir(parents=True)
    for key, value in files.items():
        (template / key).write_text(value, encoding='utf-8')
    (template / 'manifest.json').write_text(canonical(manifest), encoding='utf-8')
    value = {'commandId': str(uuid.uuid4()), 'sourceId': 'test-map', 'sourceRevision': revision,
             'name': 'Independent world', 'start': '2026-07-15',
             'configuration': {'world': {'weather': {'summer_mean_c': 30}, 'meters': {'annual_meter_failure': 0}}}}
    return root, template, value, snapshot


def test_restart_creation_isolation_mapping_and_real_readings(setup, monkeypatch):
    root, template, value, snapshot = setup
    def forbidden(*args, **kwargs):
        raise AssertionError('Procedural generation is forbidden')
    monkeypatch.setattr('utilsim.gen.pipeline.generate', forbidden)
    client = TestClient(create_app(root, TOKEN))
    result = client.post('/hosted/worlds', json=value, headers=headers())
    assert result.status_code == 200, result.text
    first = result.json()
    assert first['available'] and first['days'] == first['observations'] == 0
    assert first['configuration']['world']['weather']['summer_mean_c'] == 30
    second = client.post('/hosted/worlds', json={**value, 'commandId': str(uuid.uuid4())}, headers=headers()).json()
    assert first['id'] != second['id'] and first['environmentId'] != second['environmentId']
    base = '/hosted/worlds/' + first['id']
    assert client.get(base + '/map/snapshot', headers=headers()).json() == snapshot
    bindings = client.get(base + '/map/bindings', headers=headers()).json()
    assert {b['premiseId'] for b in bindings['premises']} == {p['id'] for p in snapshot['premises']}
    advanced = client.post(base + '/advance', json={'through': '2026-07-17'}, headers=headers())
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()['days'] == 2 and advanced.json()['observations'] > 0
    assert client.get('/hosted/worlds/' + second['id'], headers=headers()).json()['days'] == 0
    restarted = TestClient(create_app(root, TOKEN))
    reopened = restarted.get(base, headers=headers()).json()
    assert reopened['days'] == 2 and reopened['configuration'] == first['configuration']
    assert restarted.get(base + '/observations?start=2026-07-15&end=2026-07-17', headers=headers()).status_code == 200
    history = restarted.get(base + '/premises/' + snapshot['premises'][0]['id'] + '/history', headers=headers()).json()
    assert history['readings'] and history['environmentId'] == first['environmentId']
    # Existing worlds and retries work after removal of the external template package.
    shutil.rmtree(template)
    replay = restarted.post('/hosted/worlds', json={**value, 'commandId': value['commandId'].upper()}, headers=headers())
    assert replay.status_code == 200 and replay.json()['id'] == first['id']
    assert restarted.get(base + '/map/snapshot', headers=headers()).json() == snapshot


def test_auth_principal_town_and_input_boundaries(setup):
    root, template, value, _ = setup
    client = TestClient(create_app(root, TOKEN))
    assert client.get('/hosted/worlds').status_code == 401
    assert client.get('/hosted/worlds', headers={'Authorization': 'Bearer ' + TOKEN}).status_code == 401
    assert client.post('/hosted/worlds', json=value, headers=headers(role='analyst')).status_code == 403
    assert client.post('/hosted/worlds', json=value, headers=headers(town='different-map')).status_code == 403
    first = client.post('/hosted/worlds', json=value, headers=headers()).json()
    base = '/hosted/worlds/' + first['id']
    assert client.get('/hosted/worlds', headers=headers(user='other')).json()['total'] == 0
    assert client.get(base, headers=headers(user='other')).status_code == 404
    assert client.post(base + '/advance', json={'through': '2026-07-16'}, headers=headers(user='other')).status_code == 404
    assert client.get(base, headers=headers(town='different-map')).status_code == 403
    assert client.post(base + '/advance', json={'through': '2026-07-16'}, headers=headers(role='analyst')).status_code == 403
    for update in ({'owner': 'other'}, {'path': 'C:/some/world.sqlite'}, {'name': 'different'},
                   {'configuration': {'town': {'houses': 500}}}, {'configuration': {'world': {'meters': {'annual_meter_failure': True}}}}):
        assert client.post('/hosted/worlds', json={**value, **update}, headers=headers()).status_code == 422
    for through in ('2026-07-14', '2026-09-01'):
        assert client.post(base + '/advance', json={'through': through}, headers=headers()).status_code == 422
    (template / 'source-snapshot.json').write_text('{}')
    assert client.post('/hosted/worlds', json={**value, 'commandId': str(uuid.uuid4())}, headers=headers()).status_code == 422
    assert client.get('/hosted/worlds', headers=headers()).json()['total'] == 1


def test_grants_revocation_and_principal_command_scoping(setup):
    root, _, value, _ = setup
    client = TestClient(create_app(root, TOKEN))
    first = client.post('/hosted/worlds', json=value, headers=headers()).json()
    other = client.post('/hosted/worlds', json=value, headers=headers(user='other')).json()
    assert first['id'] != other['id']
    base = '/hosted/worlds/' + first['id']
    for additional in ({'revoked': True}, {'expiresAt': '2020-01-01T00:00:00Z'}, {'expiresAt': 'invalid'}):
        denied = {**headers(), 'X-UtilitySim-Grants': json.dumps([{'role': 'owner', 'town': 'map-one', **additional}])}
        assert client.get('/hosted/worlds', headers=denied).json()['total'] == 0
        assert client.get(base, headers=denied).status_code == 403
    for command in (None, 123, 'not-a-uuid'):
        assert client.post('/hosted/worlds', json={**value, 'commandId': command}, headers=headers()).status_code == 422
    assert client.get('/hosted/sources', headers=headers()).json()['sources'][0]['ready']
    schema = client.get('/hosted/sources/test-map/configuration', params={'sourceRevision': value['sourceRevision']}, headers=headers()).json()
    assert set(schema['schemas']['world']['properties']) == {'weather', 'meters'}
    assert 'billing' in schema['excluded']


def test_recovery_and_concurrent_retry(setup, monkeypatch):
    root, _, value, _ = setup
    app = create_app(root, TOKEN)
    client = TestClient(app)
    initialize = World.initialize
    def interrupted(self, *args):
        initialize(self, *args)
        raise OSError('Crash after world commit')
    monkeypatch.setattr(World, 'initialize', interrupted)
    assert client.post('/hosted/worlds', json=value, headers=headers()).status_code == 503
    pending = client.get('/hosted/worlds', headers=headers()).json()['worlds']
    assert len(pending) == 1 and pending[0]['state'] == 'pending' and not pending[0]['available']
    monkeypatch.setattr(World, 'initialize', initialize)
    restarted = TestClient(create_app(root, TOKEN))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: restarted.post('/hosted/worlds', json=value, headers=headers()), range(4)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.json()['id'] for r in results}) == 1
    assert restarted.get('/hosted/worlds', headers=headers()).json()['total'] == 1
    world = app.state.library.library.world(results[0].json()['id'])
    with world.read_db() as db:
        assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1
