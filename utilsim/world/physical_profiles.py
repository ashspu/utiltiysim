"""Opt-in housing demand and measured meter collection intervals.

The pinned map remains unchanged. Uncollected device measurements are private;
only a successful scheduled read publishes their interval quantity. No truth-table
query fills missing readings. This is a scenario model, not a calibrated forecast.
"""
import json
import math
from datetime import date, timedelta
from decimal import Decimal

from .store import canonical, draw, stable

VERSION = 'world-physical-profiles/1'
METER_DEFAULTS = {'enabled': False, 'amiPercent': 80, 'amrPercent': 15, 'manualPercent': 5,
                  'amrReadIntervalDays': 7, 'manualReadIntervalDays': 30,
                  'amiReadSuccess': .99, 'amrReadSuccess': .98, 'manualReadSuccess': .95}
HOUSING_DEFAULTS = {'enabled': False, 'meanAgeYears': 40, 'ageSpreadYears': 30,
                    'extraThermalDemandPer50Years': .25, 'retrofittedPercent': 0}


def validate(meters, housing):
    for supplied, defaults in ((meters, METER_DEFAULTS), (housing, HOUSING_DEFAULTS)):
        if not isinstance(supplied, dict) or set(supplied) != set(defaults) or type(supplied['enabled']) is not bool:
            raise ValueError('Invalid physical profile settings.')
        for key, value in supplied.items():
            if key == 'enabled':
                continue
            maximum = 100 if key.endswith('Percent') else 366 if key.endswith('Days') else 200 if key.endswith('Years') else 1
            if key == 'extraThermalDemandPer50Years':
                maximum = 2
            minimum = 1 if key.endswith('Days') else 0
            if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError('Physical profile value outside supported bounds: ' + key)
            if key.endswith(('Days', 'Years')) and key != 'extraThermalDemandPer50Years' and type(value) is not int:
                raise ValueError('Age and interval values must be integers.')
    if abs(sum(meters[k] for k in ('amiPercent', 'amrPercent', 'manualPercent')) - 100) > 1e-8:
        raise ValueError('AMI, AMR and manual shares must total 100 percent.')


def allocation(identities, shares, seed, kind):
    """Largest remainder counts and stable assignment, independent of map row order."""
    ordered = sorted(identities, key=lambda identity: stable(seed, kind, identity))
    targets = {key: len(ordered) * value / 100 for key, value in shares.items()}
    counts = {key: math.floor(value) for key, value in targets.items()}
    for key in sorted(shares, key=lambda key: (-(targets[key] - counts[key]), key))[:len(ordered) - sum(counts.values())]:
        counts[key] += 1
    result, cursor = {}, 0
    for key in sorted(shares):
        for identity in ordered[cursor:cursor + counts[key]]:
            result[identity] = key
        cursor += counts[key]
    return result


def configure(world, identity, meters, housing, residential_ids):
    validate(meters, housing)
    payload = canonical({'modelVersion': VERSION, 'meterChannels': meters, 'housingAge': housing,
                         'residentialPremises': sorted(residential_ids)})
    with world.db() as db:
        meta = world.metadata(db)
        old = db.execute('SELECT * FROM commands WHERE id=?', (identity,)).fetchone()
        if old:
            if old['payload'] != payload:
                raise ValueError('Conflicting physical profile retry.')
            return json.loads(old['result'])
        if meta['through'] != meta['start'] or db.execute('SELECT 1 FROM days LIMIT 1').fetchone():
            raise ValueError('Physical profiles must be configured before the first simulated day.')
        if 'physicalProfileModelVersion' in meta:
            raise ValueError('Initial physical profiles are already pinned.')
        for sql in (
            'CREATE TABLE physical_meter_profiles(asset TEXT PRIMARY KEY,technology TEXT NOT NULL,interval_days INTEGER NOT NULL,success REAL NOT NULL)',
            'CREATE TABLE physical_device_measurements(device TEXT PRIMARY KEY,start TEXT NOT NULL,quantity TEXT)',
            'CREATE TABLE physical_read_intervals(observation TEXT PRIMARY KEY,start TEXT NOT NULL,end TEXT NOT NULL,technology TEXT NOT NULL)',
            'CREATE TABLE physical_housing_profiles(premise TEXT PRIMARY KEY,age_years INTEGER NOT NULL,year_built INTEGER NOT NULL,retrofitted INTEGER NOT NULL,thermal_multiplier REAL NOT NULL)',
        ):
            db.execute(sql)
        assets = db.execute('SELECT * FROM assets ORDER BY id').fetchall()
        assets_by_premise = {}
        for asset in assets:
            assets_by_premise.setdefault(asset['premise'], []).append(asset)
        if meters['enabled']:
            assignments = allocation([a['id'] for a in assets], {k: meters[k.lower() + 'Percent'] for k in ('AMI', 'AMR', 'MANUAL')}, meta['seed'], 'meter-technology')
            for asset in assets:
                channel = assignments[asset['id']]
                interval = 1 if channel == 'AMI' else meters[channel.lower() + 'ReadIntervalDays']
                db.execute('INSERT INTO physical_meter_profiles VALUES(?,?,?,?)',
                           (asset['id'], channel, interval, meters[channel.lower() + 'ReadSuccess']))
        if housing['enabled']:
            retrofits = allocation(residential_ids, {'yes': housing['retrofittedPercent'], 'no': 100 - housing['retrofittedPercent']}, meta['seed'], 'housing-retrofit')
            for premise in sorted(residential_ids):
                age = max(0, min(200, round(housing['meanAgeYears'] + housing['ageSpreadYears'] * (2 * draw(meta['seed'], premise, 'housing-age') - 1))))
                retrofit = retrofits[premise] == 'yes'
                multiplier = 1 + age / 50 * housing['extraThermalDemandPer50Years'] * (.25 if retrofit else 1)
                db.execute('INSERT INTO physical_housing_profiles VALUES(?,?,?,?,?)',
                           (premise, age, date.fromisoformat(meta['start']).year - age, int(retrofit), multiplier))
                for asset in assets_by_premise.get(premise, []):
                    profile = json.loads(asset['profile'])
                    profile['thermalDemandMultiplier'] = multiplier
                    db.execute('UPDATE assets SET profile=? WHERE id=?', (canonical(profile), asset['id']))
        digest = stable(json.loads(payload))
        event = world.event(db, meta['environment'], meta['start'], 'PhysicalProfilesConfigured', meta['town'],
                            {'modelVersion': VERSION, 'configurationDigest': digest, 'configuration': json.loads(payload)}, identity)
        world.put(db, 'physicalProfileModelVersion', VERSION)
        world.put(db, 'physicalProfileConfigurationDigest', digest)
        world.put(db, 'physicalProfileConfiguration', json.loads(payload))
        result = {'commandId': identity, 'eventId': event, 'modelVersion': VERSION, 'configurationDigest': digest}
        db.execute('INSERT INTO commands VALUES(?,?,?)', (identity, payload, canonical(result)))
        return result


def meter_profiles(db, meta):
    if 'physicalProfileModelVersion' not in meta:
        return {}
    if meta['physicalProfileModelVersion'] != VERSION:
        raise ValueError('Unsupported physical profile model.')
    return {row['asset']: dict(row) for row in db.execute('SELECT * FROM physical_meter_profiles')}


def measure(db, meta, asset, day, measured, observation_id, profile):
    """Return (is collection day, observed interval quantity); measurement != truth."""
    if profile is None:
        return True, measured
    state = db.execute('SELECT * FROM physical_device_measurements WHERE device=?', (asset['device'],)).fetchone()
    start = state['start'] if state else day
    prior = state['quantity'] if state else '0'
    quantity = None if prior is None or measured is None else str(Decimal(prior) + Decimal(measured))
    finish = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    origin = max(meta['start'], asset['installed'])
    due = (date.fromisoformat(finish) - date.fromisoformat(origin)).days % profile['interval_days'] == 0
    observed = quantity
    if due:
        if draw(meta['seed'], asset['device'], day, 'collection-success') >= profile['success']:
            observed = None
        db.execute('INSERT INTO physical_read_intervals VALUES(?,?,?,?)',
                   (observation_id, start, finish, profile['technology']))
        # A missed collection retains measured accumulation for the next read.
        # A meter failure remains unknown until a physical replacement starts a new device.
        if observed is not None:
            start, quantity = finish, '0'
    db.execute('INSERT INTO physical_device_measurements VALUES(?,?,?) ON CONFLICT(device) DO UPDATE SET start=excluded.start,quantity=excluded.quantity',
               (asset['device'], start, quantity))
    return due, observed


def intervals(db, meta, start, end):
    if 'physicalProfileModelVersion' not in meta:
        return {}
    return {row['observation']: dict(row) for row in db.execute(
        'SELECT r.* FROM physical_read_intervals r JOIN observations o ON o.id=r.observation WHERE o.day>=? AND o.day<?', (start, end))}


def inspect(world, premise=None):
    with world.read_db() as db:
        meta = world.metadata(db)
        if 'physicalProfileModelVersion' not in meta:
            return {'enabled': False, 'view': 'administrator-truth'}
        housing = [dict(row) for row in db.execute('SELECT * FROM physical_housing_profiles WHERE premise=?', (premise,))] if premise else []
        meters = [dict(row) for row in db.execute('SELECT p.* FROM physical_meter_profiles p JOIN assets a ON a.id=p.asset WHERE a.premise=?', (premise,))] if premise else []
        return {'enabled': True, 'modelVersion': VERSION, 'view': 'administrator-truth',
                'configurationDigest': meta['physicalProfileConfigurationDigest'],
                'configuration': meta['physicalProfileConfiguration'], 'housing': housing, 'meters': meters,
                'meterCounts': {row['technology']: row['n'] for row in db.execute('SELECT technology,COUNT(*) n FROM physical_meter_profiles GROUP BY technology')}}
