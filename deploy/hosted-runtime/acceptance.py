"""Local accepted-map acceptance through real HTTP and process restart.

Run from repository root with PYTHONPATH set there. Creates only isolated QA worlds.
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

import httpx

from utilsim.hosted.templates import import_reviewed, read_json, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--customer-setup', action='store_true')
    parser.add_argument('--physical-profiles', action='store_true')
    parser.add_argument('--sentiment', action='store_true')
    args = parser.parse_args()
    package = Path(args.package)
    source_paths = [p for p in package.rglob('*') if p.is_file()]
    source_world = Path(read_json(package / 'runtime-manifest.json')['databasePath'])
    if source_world.exists():
        source_paths += [source_world, *source_world.parent.glob('world.sqlite-*')]
    before = {str(p): sha(p.read_bytes()) for p in source_paths}
    revision = import_reviewed(package, args.root, 'lantern-harbour', 'Lantern Harbour', 'lantern-bay-500')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    token = secrets.token_urlsafe(48)
    env = {**os.environ, 'UTILITYSIM_DATA_ROOT': args.root, 'UTILITYSIM_RUNTIME_TOKEN': token}
    client = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=120,
                          headers={'Authorization': 'Bearer ' + token, 'X-UtilitySim-User-Id': 'isolated-runtime-qa',
                                   'X-UtilitySim-Grants': '[{"role":"owner","town":"lantern-bay-500"}]'})
    def launch():
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'utilsim.hosted.server:from_environment',
                                    '--factory', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Runtime process failed at startup.')
            try:
                if client.get('/hosted/worlds').status_code == 200:
                    return process
            except httpx.ConnectError:
                pass
            time.sleep(.1)
        process.terminate()
        process.wait()
        raise RuntimeError('Runtime did not become ready.')

    def call(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    setup_request_seconds = []
    def create_world(value):
        for attempt in range(100):
            request_started = time.monotonic()
            result = call('POST', '/hosted/worlds', json=value)
            setup_request_seconds.append(round(time.monotonic() - request_started, 3))
            if result['available']:
                return result
            if attempt % 4 == 0:
                print(json.dumps({'setupProgress': result['initialization']}), flush=True)
        raise RuntimeError('Setup did not finish within bounded acceptance retries.')

    process = launch()
    try:
        value = {'commandId': str(uuid.uuid4()), 'sourceId': 'lantern-harbour', 'sourceRevision': revision,
                 'name': 'Isolated accepted-map restart QA', 'start': '2026-07-15',
                 'configuration': {'world': {'weather': {'summer_mean_c': 29}, 'meters': {'annual_meter_failure': 0}}}}
        if args.customer_setup:
            value['configuration'].update(schemaVersion='physical-setup/2', physical={
                'customerContacts': {'active': True, 'noticeProbabilityPerDay': .8},
                'householdFinance': {'enabled': True, 'cashCents': 10000, 'essentialReserveCents': 2000,
                                     'maxPaymentCents': 3000, 'paymentProbability': .6},
                'householdCashflow': {'enabled': True, 'incomeCents': 1000, 'incomeIntervalDays': 1,
                                      'expenseCents': 400, 'expenseIntervalDays': 1}})
        if args.physical_profiles:
            value['configuration']['schemaVersion'] = 'physical-setup/3'
            value['configuration'].setdefault('physical', {}).update(
                meterChannels={'enabled': True, 'amiPercent': 0, 'amrPercent': 0, 'manualPercent': 100,
                               'manualReadIntervalDays': 3, 'manualReadSuccess': 1},
                housingAge={'enabled': True, 'meanAgeYears': 100, 'ageSpreadYears': 0})
        if args.sentiment:
            value['configuration']['schemaVersion'] = 'physical-setup/4'
            value['configuration'].setdefault('physical', {}).update(
                customerSentiment={'enabled': True, 'initialTrust': 100, 'communityInfluence': 1})
        simulated_days = 3 if args.physical_profiles else 2
        target = '2026-07-18' if args.physical_profiles else '2026-07-17'
        started = time.monotonic()
        first = create_world(value)
        creation_seconds = round(time.monotonic() - started, 2)
        second = create_world({**value, 'commandId': str(uuid.uuid4()), 'configuration': {'world': value['configuration']['world']}})
        base = '/hosted/worlds/' + first['id']
        assert first['environmentId'] != second['environmentId']
        assert first['days'] == first['observations'] == 0
        snapshot = call('GET', base + '/map/snapshot')
        assert snapshot == read_json(package / 'source-snapshot.json')
        bindings = call('GET', base + '/map/bindings')['premises']
        original = read_json(package / 'bindings.json')['premises']
        assert {(b['parcelId'], b['premiseId'], tuple(b['meterIds'])) for b in bindings} == {
            (b['parcelId'], b['premiseId'], tuple(b['meterIds'])) for b in original}
        storm_path = base + '/events/storms'
        assert call('GET', storm_path)['enabled'] is False
        storm = {'commandId': str(uuid.uuid4()), 'expectedRevision': 0, 'effectiveDate': first['through'],
                 'action': 'schedule', 'reason': 'Accepted-map physical weather QA', 'causalReference': 'isolated-http-qa',
                 'startDate': '2026-07-16', 'endDate': '2026-07-17', 'temperatureOffsetC': -10,
                 'multipliers': dict.fromkeys(('electric', 'gas', 'water', 'sewer'), 2)}
        storm_receipt = call('POST', storm_path, json=storm)
        cancelled_storm = {**storm, 'commandId': str(uuid.uuid4()), 'expectedRevision': 1,
                           'startDate': '2026-07-17', 'endDate': '2026-07-18'}
        cancelled_receipt = call('POST', storm_path, json=cancelled_storm)
        cancellation = {k: cancelled_storm[k] for k in ('effectiveDate', 'reason', 'causalReference')}
        cancellation.update(commandId=str(uuid.uuid4()), expectedRevision=2, action='cancel', stormId=cancelled_receipt['stormId'])
        call('POST', storm_path, json=cancellation)
        if args.sentiment:
            sentiment_path = base + '/events/sentiment'
            news = {'commandId': str(uuid.uuid4()), 'expectedRevision': 0, 'effectiveDate': first['through'],
                    'action': 'schedule', 'reason': 'Accepted-map public confidence scenario', 'causalReference': 'isolated-http-qa',
                    'eventDate': '2026-07-16', 'trustChange': -60, 'headline': 'Utility reliability questioned in local news'}
            news_receipt = call('POST', sentiment_path, json=news)
        advanced = call('POST', base + '/advance', json={'through': target})
        assert advanced['days'] == simulated_days and advanced['observations'] > 0
        assert call('GET', '/hosted/worlds/' + second['id'])['days'] == 0
        process.terminate()
        process.wait(timeout=15)
        process = launch()
        resumed = call('GET', base)
        assert resumed['configuration'] == first['configuration']
        assert resumed['fingerprint'] == first['fingerprint'] and resumed['through'] == advanced['through']
        assert call('POST', '/hosted/worlds', json=value)['id'] == first['id']
        storm_history = call('GET', storm_path)
        assert len(storm_history['history']) == 1
        applied = storm_history['history'][0]
        assert applied['stormId'] == storm_receipt['stormId']
        assert applied['temperatureC'] == round(applied['baselineTemperatureC'] - 10, 2)
        assert call('POST', storm_path, json=storm) == storm_receipt
        assert call('POST', storm_path, json=cancelled_storm) == cancelled_receipt
        assert next(e for e in storm_history['events'] if e['stormId'] == cancelled_receipt['stormId'])['cancelledEventId']
        assert client.post(storm_path, json={**cancellation, 'commandId': str(uuid.uuid4()), 'expectedRevision': 3,
                                           'effectiveDate': resumed['through'], 'stormId': storm_receipt['stormId']}).status_code == 422
        journal = call('GET', base + '/events?limit=50')
        while 'StormWeatherApplied' not in {e['type'] for e in journal['events']} and journal['nextBefore'] is not None:
            journal = call('GET', base + '/events?limit=50&before=' + str(journal['nextBefore']))
        assert 'StormWeatherApplied' in {e['type'] for e in journal['events']}
        assert call('GET', '/hosted/worlds/' + second['id'] + '/events/storms')['history'] == []
        picks = []
        for kind in sorted({p.get('premiseType', 'unknown') for p in original}):
            binding = next(p for p in original if p.get('premiseType', 'unknown') == kind)
            detail = call('GET', base + '/premises/' + binding['premiseId'])
            history = call('GET', base + '/premises/' + binding['premiseId'] + '/history')
            assert detail['environmentId'] == first['environmentId']
            assert {a['id'] for a in detail['assets']} == set(binding['meterIds'])
            assert history['readings']
            assert {r['assetId'] for r in history['readings']} <= set(binding['meterIds'])
            picks.append({'type': kind, 'premiseId': binding['premiseId'], 'readings': len(history['readings'])})
        assert client.get(base, headers={'X-UtilitySim-User-Id': 'other-principal'}).status_code == 404
        customer_proof = None
        if args.customer_setup:
            residential = next(p for p in original if p['premiseType'] == 'residential')
            customer_path = base + '/premises/' + residential['premiseId'] + '/customer'
            customer = call('GET', customer_path)
            assert customer['finance']['cashCents'] == 10000 + 600 * simulated_days
            assert len(customer['cashflow']['history']) == simulated_days
            assert first['initialization']['eligibleHouseholds'] == 300
            assert first['initialization']['appliedCommands'] == 601 + int(args.physical_profiles) + int(args.sentiment)
            customer_proof = {'initialization': first['initialization'], 'creationSeconds': creation_seconds,
                              'maxCreateRequestSeconds': max(setup_request_seconds), 'createRequestCount': len(setup_request_seconds),
                              'samplePremiseId': residential['premiseId'], 'startingCashCents': 10000,
                              'resumedCashCents': customer['finance']['cashCents'], 'cashflowDays': simulated_days}
        profile_proof = None
        if args.physical_profiles:
            residential = next(p for p in original if p['premiseType'] == 'residential')
            applied_profiles = call('GET', base + '/premises/' + residential['premiseId'])['physicalProfiles']
            assert applied_profiles['meterCounts'] == {'MANUAL': 1262}
            assert applied_profiles['housing'][0]['age_years'] == 100
            reads = call('GET', base + '/observations?start=2026-07-17&end=2026-07-18')['observations']
            assert len(reads) == 1262 and all(r['start'] == '2026-07-15' and r['end'] == target for r in reads)
            assert call('GET', base + '/observations?start=2026-07-15&end=2026-07-17')['observations'] == []
            second_base = '/hosted/worlds/' + second['id']
            call('POST', second_base + '/advance', json={'through': target})
            daily = call('GET', second_base + '/observations?start=2026-07-15&end=2026-07-18')['observations']
            sample_water = next(r for r in reads if r['commodity'] == 'water' and r['quantity'] is not None)
            reference = sum(Decimal(r['quantity']) for r in daily if r['meterId'] == sample_water['meterId'])
            assert Decimal(sample_water['quantity']) == reference
            profile_proof = {'modelVersion': applied_profiles['modelVersion'], 'meterCounts': applied_profiles['meterCounts'],
                'housingAgeYears': 100, 'intervalStart': '2026-07-15', 'intervalEnd': target,
                'intervalReadings': len(reads), 'noUnscheduledDailyReadings': True,
                'sampleWaterMatchesThreeDailyMeasurements': True, 'maxCreateRequestSeconds': max(setup_request_seconds)}
        sentiment_proof = None
        if args.sentiment:
            mood = call('GET', sentiment_path)
            assert 0 <= mood['communityTrust'] < 50
            assert len(mood['history']) == simulated_days
            assert call('POST', sentiment_path, json=news) == news_receipt
            assert sum(bool(n['applied']) for n in mood['news']) == 1
            assert all(r['payload']['occupiedHouseholds'] == 300 for r in mood['history'])
            sentiment_proof = {'modelVersion': mood['modelVersion'], 'initialTrust': 100,
                'resumedCommunityTrust': mood['communityTrust'], 'occupiedHouseholds': 300,
                'appliedNewsEvents': 1, 'exactRetryAfterRestart': True, 'historyDays': len(mood['history'])}
        assert all(p.exists() and sha(p.read_bytes()) == before[str(p)] for p in source_paths)
        report = {'status': 'passed-local-only', 'sourceRevision': revision, 'sourceFilesUnchanged': len(source_paths),
                  'sourceWorldChecked': source_world.exists(), 'counts': first['counts'], 'independentWorldIds': [first['id'], second['id']],
                  'restartResumedThrough': resumed['through'], 'observations': resumed['observations'], 'premiseChecks': picks,
                  'configurationRoundtrip': True, 'actualProcessRestart': True, 'idempotentCreate': True,
                  'customerSetup': customer_proof,
                  'physicalProfiles': profile_proof,
                  'sentiment': sentiment_proof,
                  'principalIsolation': True, 'mapAndMeterBindingsExact': True, 'hostedDeployed': False,
                  'stormLoop': {'scheduled': True, 'cancelledBeforeStart': True, 'startedCancellationRejected': True,
                                'exactRetryAfterRestart': True, 'appliedDays': len(storm_history['history']),
                                'baselineTemperatureC': applied['baselineTemperatureC'], 'temperatureC': applied['temperatureC'],
                                'temperatureOffsetC': applied['temperatureOffsetC'], 'riskMultipliers': applied['multipliers']}}
        Path(args.report).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=15)
        client.close()


if __name__ == '__main__':
    main()
