import json
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest
from test_world_v2 import world

from utilsim.world import World
from utilsim.world import physical_profiles as profiles


def configure(w, **meter_fields):
    return profiles.configure(w, 'profiles', {**profiles.METER_DEFAULTS, 'enabled': True,
        'amiPercent': 0, 'amrPercent': 0, 'manualPercent': 100, 'manualReadIntervalDays': 3,
        'manualReadSuccess': 1, **meter_fields}, profiles.HOUSING_DEFAULTS, ['P1'])


def test_collection_intervals_measure_accumulation_and_preserve_source(tmp_path):
    w = world(tmp_path, annual_meter_failure=0, annual_meter_drift=0)
    with w.read_db() as db:
        before = db.execute("SELECT value FROM meta WHERE key='snapshot'").fetchone()[0]
    receipt = configure(w)
    assert configure(w) == receipt
    w.advance('2026-01-03')
    assert w.export('2026-01-01', '2026-01-03')['observations'] == []
    w = World(w.path)
    w.advance('2026-01-04')
    batch = w.export_v2('2026-01-03', '2026-01-04')
    jsonschema.validate(batch, json.loads((Path(__file__).parents[1] / 'schemas/utility-observations-2.0.schema.json').read_text()))
    assert len(batch['observations']) == 4  # 3 real meters plus derived sewer
    with w.read_db() as db:
        assert db.execute("SELECT value FROM meta WHERE key='snapshot'").fetchone()[0] == before
        for reading in batch['observations']:
            assert reading['start'] == '2026-01-01' and reading['end'] == '2026-01-04'
            if reading['commodity'] != 'sewer':
                measured = sum(Decimal(row[0]) for row in db.execute('SELECT quantity FROM truth WHERE asset=?', (reading['meterId'],)))
                assert Decimal(reading['quantity']) == measured
                assert reading['registerValue'] == reading['quantity']
    assert 'physical_device_measurements' not in json.dumps(batch)


def test_missed_collection_recovers_measured_interval_without_truth_query(tmp_path, monkeypatch):
    w = world(tmp_path, annual_meter_failure=0, annual_meter_drift=0)
    configure(w, manualReadIntervalDays=2, manualReadSuccess=.5)
    with w.db() as db:
        db.execute("UPDATE assets SET condition='drifting',drift=2")
    monkeypatch.setattr(profiles, 'draw', lambda *args: 1 if '2026-01-02' in args else 0)
    w.advance('2026-01-03')
    assert all(r['quantity'] is None for r in w.export('2026-01-01', '2026-01-03')['observations'])
    # Corrupt private truth after the measurement: recovery must use device evidence.
    with w.db() as db:
        expected = {r['device']: Decimal(r['quantity']) for r in db.execute('SELECT * FROM physical_device_measurements')}
        db.execute("UPDATE truth SET quantity='999999'")
    w.advance('2026-01-05')
    batch = w.export_v2('2026-01-04', '2026-01-05')
    for reading in batch['observations']:
        if reading['commodity'] == 'sewer':
            continue
        assert reading['start'] == '2026-01-01'
        assert expected[reading['deviceId']] < Decimal(reading['quantity']) < 1000
        assert reading['registerValue'] is None  # conservative existing reconstruction after a reported gap


def test_meter_failure_stays_missing_and_replacement_starts_new_interval(tmp_path):
    w = world(tmp_path, annual_meter_failure=0, annual_meter_drift=0)
    configure(w, manualReadIntervalDays=2)
    with w.db() as db:
        db.execute("UPDATE assets SET condition='failed'")
    w.advance('2026-01-03')
    assert all(r['quantity'] is None for r in w.export('2026-01-01', '2026-01-03')['observations'])
    w.replace_meter('replace', 'TEST', 'water', 'new-water', 'WO', 'Physical replacement')
    w.advance('2026-01-05')
    readings = w.export_v2('2026-01-04', '2026-01-05')['observations']
    water = next(r for r in readings if r['commodity'] == 'water')
    assert water['deviceId'] == 'new-water' and water['start'] == '2026-01-03'
    assert Decimal(water['quantity']) > 0 and water['registerValue'] is not None
    assert all(r['quantity'] is None for r in readings if r['commodity'] in ('electric', 'gas'))


def test_housing_age_changes_only_thermal_load_and_retrofit_reduces_effect(tmp_path):
    states = []
    for name, age, retrofit in [('new', 0, 0), ('old', 100, 0), ('retrofitted', 100, 100)]:
        w = world(tmp_path, name, annual_meter_failure=0, annual_meter_drift=0,
                  winter_mean_c=0, summer_mean_c=0, daily_weather_spread_c=0)
        profiles.configure(w, 'profiles', profiles.METER_DEFAULTS,
            {**profiles.HOUSING_DEFAULTS, 'enabled': True, 'meanAgeYears': age, 'ageSpreadYears': 0,
             'extraThermalDemandPer50Years': .5, 'retrofittedPercent': retrofit}, ['P1'])
        w.advance('2026-01-02')
        states.append({r['commodity']: Decimal(r['quantity']) for r in w.export('2026-01-01', '2026-01-02')['observations']})
    assert states[0]['gas'] < states[2]['gas'] < states[1]['gas']
    assert len({s['water'] for s in states}) == len({s['electric'] for s in states}) == 1


def test_profile_allocation_validation_and_old_world_behavior(tmp_path):
    identities = ['a', 'b', 'c', 'd', 'e']
    allocations = profiles.allocation(identities, {'AMI': 60, 'AMR': 20, 'MANUAL': 20}, '42', 'tech')
    assert sorted(allocations.values()) == ['AMI', 'AMI', 'AMI', 'AMR', 'MANUAL']
    assert allocations == profiles.allocation(list(reversed(identities)), {'AMI': 60, 'AMR': 20, 'MANUAL': 20}, '42', 'tech')
    baseline = world(tmp_path, 'baseline', annual_meter_failure=0, annual_meter_drift=0)
    modern = world(tmp_path, 'modern', annual_meter_failure=0, annual_meter_drift=0)
    configure(modern, amiPercent=100, amrPercent=0, manualPercent=0, amiReadSuccess=1)
    for w in (baseline, modern):
        w.advance('2026-01-04')
    assert baseline.export('2026-01-01', '2026-01-04')['observations'] == modern.export('2026-01-01', '2026-01-04')['observations']
    with pytest.raises(ValueError, match='total 100'):
        configure(baseline, amiPercent=50)
    with pytest.raises(ValueError, match='before the first'):
        configure(baseline)


def test_day_rollback_includes_device_accumulation_and_restart_is_identical(tmp_path, monkeypatch):
    expected = world(tmp_path, 'expected', annual_meter_failure=0, annual_meter_drift=0)
    interrupted = world(tmp_path, 'interrupted', annual_meter_failure=0, annual_meter_drift=0)
    for w in (expected, interrupted):
        configure(w)
    original = profiles.measure
    def fail(*args):
        original(*args)
        raise RuntimeError('Interrupted after measurement')
    with monkeypatch.context() as patch:
        patch.setattr(profiles, 'measure', fail)
        with pytest.raises(RuntimeError, match='Interrupted'):
            interrupted.advance('2026-01-04')
    with interrupted.read_db() as db:
        assert db.execute('SELECT COUNT(*) FROM physical_device_measurements').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM truth').fetchone()[0] == 0
    expected.advance('2026-01-07')
    interrupted = World(interrupted.path)
    interrupted.advance('2026-01-03')
    interrupted.advance('2026-01-07')
    assert expected.export_v2('2026-01-01', '2026-01-07') == interrupted.export_v2('2026-01-01', '2026-01-07')
