import sqlite3

import pytest
from fastapi.testclient import TestClient
from test_hosted_worlds import TOKEN, headers, setup  # noqa: F401

from utilsim.hosted import setup as physical_setup
from utilsim.hosted.server import create_app
from utilsim.world import World, physical_profiles


@pytest.mark.parametrize('meters,housing', [(True, False), (False, True), (True, True), (False, False)])
def test_actual_profile_summary_groups_restart_and_pinned_source(setup, meters, housing):  # noqa: F811
    root, template, value, snapshot = setup
    pinned = (template / 'source-snapshot.json').read_bytes()
    value['configuration'] = {'schemaVersion': physical_setup.VERSION, 'physical': {
        'meterChannels': {'enabled': meters, 'amiPercent': 0, 'amrPercent': 0, 'manualPercent': 100},
        'housingAge': {'enabled': housing, 'meanAgeYears': 80, 'ageSpreadYears': 0, 'retrofittedPercent': 100}}}
    client = TestClient(create_app(root, TOKEN))
    response = client.post('/hosted/worlds', json=value, headers=headers())
    assert response.status_code == 200, response.text
    created = response.json()
    summary = created['physicalProfiles']
    assert summary['enabled'] == (meters or housing)
    assert summary['meterChannelsEnabled'] == meters
    assert summary['housingAgeEnabled'] == housing
    assert summary['meterCounts'] == ({'MANUAL': 3} if meters else {})
    assert summary['housing'] == {
        'count': 1 if housing else 0, 'minAgeYears': 80 if housing else None,
        'maxAgeYears': 80 if housing else None, 'meanAgeYears': 80 if housing else None,
        'retrofittedCount': 1 if housing else 0, 'retrofittedPercent': 100 if housing else 0}
    world = client.app.state.library.library.world(created['id'])
    with world.read_db() as db:
        meta = world.metadata(db)
        assert summary['modelVersion'] == meta.get('physicalProfileModelVersion')
        assert summary['configurationDigest'] == meta.get('physicalProfileConfigurationDigest')
        before = list(db.execute('SELECT name,sql FROM sqlite_master ORDER BY name'))
        events = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    restarted = TestClient(create_app(root, TOKEN))
    base = '/hosted/worlds/' + created['id']
    assert restarted.get(base, headers=headers()).json()['physicalProfiles'] == summary
    assert restarted.get('/hosted/worlds', headers=headers()).json()['worlds'][0]['physicalProfiles'] == summary
    assert restarted.get(base + '/map/snapshot', headers=headers()).json() == snapshot
    with World(world.path).read_db() as db:
        assert list(db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')) == before
        assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == events
    assert (template / 'source-snapshot.json').read_bytes() == pinned


def test_legacy_disabled_summary_does_not_query_or_create_profile_tables(setup):  # noqa: F811
    root, _, value, _ = setup
    client = TestClient(create_app(root, TOKEN))
    result = client.post('/hosted/worlds', json=value, headers=headers()).json()
    world = client.app.state.library.library.world(result['id'])
    with world.read_db() as db:
        sql = []
        db.set_trace_callback(sql.append)
        summary = physical_profiles.summary(db, world.metadata(db))
        assert summary == result['physicalProfiles']
        assert summary['enabled'] is False and summary['modelVersion'] is None
        assert not any('physical_' in query for query in sql)
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'physical_%'").fetchone()


def test_empty_housing_aggregate_has_null_ages_and_zero_retrofit_percent(setup):  # noqa: F811
    root, _, value, _ = setup
    client = TestClient(create_app(root, TOKEN))
    result = client.post('/hosted/worlds', json=value, headers=headers()).json()
    world = client.app.state.library.library.world(result['id'])
    physical_profiles.configure(World(world.path), 'empty-housing', physical_profiles.METER_DEFAULTS,
        {**physical_profiles.HOUSING_DEFAULTS, 'enabled': True}, [])
    with world.read_db() as db:
        summary = physical_profiles.summary(db, world.metadata(db))
    assert summary['housingAgeEnabled'] and not summary['meterChannelsEnabled']
    assert summary['meterCounts'] == {}
    assert summary['housing'] == {'count': 0, 'minAgeYears': None, 'maxAgeYears': None,
                                 'meanAgeYears': None, 'retrofittedCount': 0, 'retrofittedPercent': 0}


def test_summary_uses_stored_assignments_not_requested_distribution():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE physical_meter_profiles(technology TEXT)')
    db.executemany('INSERT INTO physical_meter_profiles VALUES(?)', [('AMI',), ('AMI',), ('AMR',), ('MANUAL',)])
    db.execute('CREATE TABLE physical_housing_profiles(age_years INTEGER,retrofitted INTEGER)')
    db.executemany('INSERT INTO physical_housing_profiles VALUES(?,?)', [(0, 0), (20, 1), (70, 0)])
    db.execute('PRAGMA query_only=ON')
    meta = {'physicalProfileModelVersion': physical_profiles.VERSION, 'physicalProfileConfigurationDigest': 'pinned-digest',
            'physicalProfileConfiguration': {'meterChannels': {**physical_profiles.METER_DEFAULTS, 'enabled': True},
                                             'housingAge': {**physical_profiles.HOUSING_DEFAULTS, 'enabled': True}}}
    result = physical_profiles.summary(db, meta)
    assert result['meterCounts'] == {'AMI': 2, 'AMR': 1, 'MANUAL': 1}
    assert result['housing'] == {'count': 3, 'minAgeYears': 0, 'maxAgeYears': 70, 'meanAgeYears': 30,
                                 'retrofittedCount': 1, 'retrofittedPercent': 100 / 3}
    assert result['configurationDigest'] == 'pinned-digest'
    db.close()


def test_pending_status_does_not_initialize_or_promote_partial_profiles(setup, monkeypatch):  # noqa: F811
    root, _, value, _ = setup
    value['configuration'] = {'schemaVersion': physical_setup.VERSION, 'physical': {
        'meterChannels': {'enabled': True}, 'housingAge': {'enabled': True}}}
    client = TestClient(create_app(root, TOKEN))
    original = physical_profiles.configure
    def interrupted(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('Lost receipt after profile commit')
    monkeypatch.setattr(physical_profiles, 'configure', interrupted)
    assert client.post('/hosted/worlds', json=value, headers=headers()).status_code == 503
    def forbidden(*args, **kwargs):
        raise AssertionError('A status read must never configure profiles')
    monkeypatch.setattr(physical_profiles, 'configure', forbidden)
    pending = client.get('/hosted/worlds', headers=headers()).json()['worlds'][0]
    assert pending['physicalProfiles']['enabled']
    assert pending['state'] == 'configuring' and pending['available'] is False
    world = client.app.state.library.library.world(pending['id'])
    with world.read_db() as db:
        before = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in
                  ('physical_meter_profiles', 'physical_housing_profiles', 'commands', 'events')}
    reopened = TestClient(create_app(root, TOKEN)).get('/hosted/worlds/' + pending['id'], headers=headers()).json()
    assert reopened['physicalProfiles'] == pending['physicalProfiles']
    assert reopened['available'] is False
    with world.read_db() as db:
        after = {table: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in before}
    assert before == after
    monkeypatch.setattr(physical_profiles, 'configure', original)
    recovered = client.post('/hosted/worlds', json=value, headers=headers()).json()
    assert recovered['available'] and recovered['id'] == pending['id']
