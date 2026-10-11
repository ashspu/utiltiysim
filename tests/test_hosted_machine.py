import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_hosted_worlds import TOKEN, headers
from test_hosted_worlds import setup as setup
from test_world_customer_finance import command as finance_command
from test_world_customer_finance import delivery as invoice_delivery
from test_world_customer_finance import receipt as provider_receipt
from test_world_field_execution import command as field_command
from test_world_field_execution import receipt as field_receipt
from test_world_water_faults import command as leak_command

from utilsim.hosted.server import create_app
from utilsim.world import customer_finance, field_execution, water_faults
from utilsim.world.store import canonical, stable

MACHINE_KEY = 'test-machine-key-distinct-from-browser-credential'


def instance(setup):
    root, _, value, _ = setup
    app = create_app(root, TOKEN, MACHINE_KEY)
    client = TestClient(app)
    created = client.post('/hosted/worlds', json=value, headers=headers()).json()
    return app, client, created


def connect(client, identity, revision=0, **changes):
    value = {'commandId': str(uuid.uuid4()), 'expectedRevision': revision,
             'controllerId': 'utilitysim-controller', 'sewerReturnFactor': '0.9', 'delaySeconds': 21600, **changes}
    result = client.post(f'/hosted/worlds/{identity}/connection', json=value, headers=headers())
    assert result.status_code == 200, result.text
    return value, result.json(), {'Authorization': 'Bearer ' + result.json()['token']}


def advance(client, identity, auth, through='2026-07-16', **extra):
    value = {'commandId': 'world-day-' + through, 'through': through, 'processingAt': through + 'T00:00:00Z', **extra}
    return client.post(f'/machine/worlds/{identity}/advance', json=value, headers=auth)


def acknowledge_day(client, identity, auth, after=0):
    page = client.get(f'/machine/worlds/{identity}/feeds/observations', params={'after': after, 'limit': 1}, headers=auth).json()
    item = page['items'][0]
    receipt = {'id': item['envelope']['id'], 'status': 'pending'}
    response = client.post(f'/machine/worlds/{identity}/receipts/observations', json=receipt, headers=auth)
    assert response.status_code == 200, response.text
    return item, receipt


def test_capability_isolation_rotation_revocation_and_manual_clock_guard(setup):
    app, client, world = instance(setup)
    identity = world['id']
    base = f'/machine/worlds/{identity}'
    assert client.get(base + '/status', headers=headers()).status_code == 401
    command, connection, auth = connect(client, identity)
    health = client.get('/hosted/health', headers={'Authorization': 'Bearer ' + TOKEN})
    assert health.status_code == 200 and health.json()['status'] == 'ready'
    assert client.get('/hosted/health').status_code == 401
    assert client.get('/hosted/health', headers=auth).status_code == 401
    assert client.post(f'/hosted/worlds/{identity}/connection', json=command, headers=headers()).json() == connection
    assert client.get(base + '/status', headers=auth).status_code == 200
    assert client.get('/hosted/worlds', headers=auth).status_code == 401
    other = client.post('/hosted/worlds', json={**setup[2], 'commandId': str(uuid.uuid4())}, headers=headers()).json()
    assert client.get(f"/machine/worlds/{other['id']}/status", headers=auth).status_code == 401
    assert client.post(f'/hosted/worlds/{identity}/advance', json={'through': '2026-07-16'}, headers=headers()).status_code == 422
    changed = {**command, 'controllerId': 'arbitrary-browser-controller', 'commandId': str(uuid.uuid4())}
    assert client.post(f'/hosted/worlds/{identity}/connection', json=changed, headers=headers()).status_code == 422
    _, rotated, new_auth = connect(client, identity, revision=1)
    assert client.get(base + '/status', headers=auth).status_code == 401
    assert client.get(base + '/status', headers=new_auth).status_code == 200
    revoke = {'commandId': str(uuid.uuid4()), 'expectedRevision': rotated['revision']}
    marker = client.post(f'/hosted/worlds/{identity}/connection/revoke', json=revoke, headers=headers()).json()
    assert marker['configured'] and not marker['active'] and not marker['manualAdvanceAllowed']
    assert client.get(base + '/status', headers=new_auth).status_code == 401
    assert app.state.library.describe(app.state.library.lookup('user-a', identity))['connectedClock'] == marker
    assert client.post(f'/hosted/worlds/{identity}/advance', json={'through': '2026-07-16'}, headers=headers()).status_code == 422


def test_immutable_outbox_lost_ack_restart_exact_retry_and_ordering(setup):
    app, client, world = instance(setup)
    identity = world['id']
    _, _, auth = connect(client, identity)
    assert advance(client, identity, auth, processingAt='2026-07-15T23:59:59Z').status_code == 422
    first = advance(client, identity, auth)
    assert first.status_code == 200, first.text
    assert advance(client, identity, auth, '2026-07-17').status_code == 422
    item, receipt = acknowledge_day(client, identity, auth)
    rows = item['envelope']['payload']['batch']['observations']
    assert {r['availableAt'] for r in rows} == {'2026-07-16T06:00:00Z'}
    assert {r['commodity'] for r in rows} == {'electric', 'gas', 'water', 'sewer'}
    assert item['fingerprint'] == stable(item['envelope'])
    assert not any(k in json.dumps(item) for k in ('actualQuantity', 'cashCents', 'token'))
    # Simulate losing the acknowledgement response and reopening the actual store.
    reopened = TestClient(create_app(setup[0], TOKEN, MACHINE_KEY))
    repeated = reopened.post(f'/machine/worlds/{identity}/receipts/observations', json=receipt, headers=auth)
    assert repeated.status_code == 200
    assert advance(reopened, identity, auth).json() == first.json()
    assert reopened.get(f'/machine/worlds/{identity}/feeds/observations', headers=auth).json()['items'][0] == item
    assert reopened.post(f'/machine/worlds/{identity}/receipts/observations', json={**receipt, 'status': 'completed'}, headers=auth).status_code == 422
    assert advance(reopened, identity, auth, '2026-07-17').status_code == 200
    with app.state.library.library.world(identity).read_db() as db:
        assert db.execute('SELECT COUNT(*) FROM days').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM observation_outbox').fetchone()[0] == 2


def test_concurrent_one_day_and_recovery_after_day_commit(setup, monkeypatch):
    app, client, world = instance(setup)
    identity = world['id']
    _, _, auth = connect(client, identity)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: advance(client, identity, auth), range(2)))
    assert all(r.status_code == 200 for r in results)
    assert results[0].json() == results[1].json()
    acknowledge_day(client, identity, auth)
    from utilsim.hosted.library import ManagedWorld
    original = ManagedWorld.advance

    def interrupted(self, through):
        original(self, through)
        raise OSError('Simulated post-commit process loss')

    monkeypatch.setattr(ManagedWorld, 'advance', interrupted)
    assert advance(client, identity, auth, '2026-07-17').status_code == 503
    monkeypatch.setattr(ManagedWorld, 'advance', original)
    assert advance(client, identity, auth, '2026-07-17').status_code == 200
    with app.state.library.library.world(identity).read_db() as db:
        assert db.execute('SELECT COUNT(*) FROM days').fetchone()[0] == 2


def test_actual_invoice_payment_provider_feedback_and_scope_denial(setup):
    app, client, world = instance(setup)
    identity = world['id']
    physical = app.state.library.machine.world({'world': identity})
    customer_finance.command(physical, finance_command(physical))
    _, _, auth = connect(client, identity)
    prefix = f'/machine/worlds/{identity}'
    invoice = invoice_delivery(physical)
    assert client.post(prefix + '/returns/invoices', json={**invoice, 'environmentId': 'OTHER'}, headers=auth).status_code == 422
    response = client.post(prefix + '/returns/invoices', json=invoice, headers=auth)
    assert response.status_code == 200, response.text
    assert client.post(prefix + '/returns/invoices', json=invoice, headers=auth).json() == response.json()
    assert advance(client, identity, auth).status_code == 200
    intents = client.get(prefix + '/feeds/payments', headers=auth).json()
    intent = intents['items'][0]['intent']
    assert intent['amountCents'] == 4000
    assert client.get(prefix + '/payments/' + intent['id'], headers=auth).json()['intent'] == intent
    accepted = {'id': intent['id'], 'runId': intent['runId'], 'fingerprint': stable(intent), 'status': 'accepted', 'receiptId': 'payment-received'}
    assert client.post(prefix + '/receipts/payments', json=accepted, headers=auth).status_code == 200
    assert customer_finance.inspect(physical, 'P1')['cashCents'] == 10000
    receipt = provider_receipt(physical, intent)
    settled = client.post(prefix + '/returns/provider', json=receipt, headers=auth)
    assert settled.status_code == 200, settled.text
    assert client.post(prefix + '/returns/provider', json=receipt, headers=auth).json() == settled.json()
    assert customer_finance.inspect(physical, 'P1')['cashCents'] == 6000
    assert client.post(prefix + '/returns/provider', json={**receipt, 'amountCents': 1}, headers=auth).status_code == 422
    assert client.post(prefix + '/returns/invoices', json={**invoice, 'deliveryId': 'future', 'deliveredAt': '2026-07-17T00:00:00Z'}, headers=auth).status_code == 422


def test_field_actual_repair_dispatch_receipt_before_report_and_separate_db(setup):
    app, client, world = instance(setup)
    identity = world['id']
    physical = app.state.library.machine.world({'world': identity})
    with physical.read_db() as db:
        meta = physical.metadata(db)
    water_faults.command(physical, leak_command(physical, environmentId=meta['environment']))
    _, _, auth = connect(client, identity)
    field = app.state.library.machine.field(physical, identity)
    prefix = f'/machine/worlds/{identity}'
    for command in [field_command(field, 'crew', 'configure-crew'), field_command(field)]:
        command.pop('actorId')
        response = client.post(prefix + '/returns/field', json=command, headers=auth)
        assert response.status_code == 200, response.text
    status = client.get(prefix + '/field-managed/status', headers=auth)
    assert status.status_code == 200 and status.json()['fieldOwnerId'] == field.owner_id
    assert status.json()['enabled'] is False
    proof = client.get(prefix + '/field-managed/assignment', params={'assignmentId': 'A1'}, headers=auth)
    assert proof.status_code == 200
    assert field_execution.checksum(proof.json()['assignment']) == proof.json()['checksum']
    assert advance(client, identity, auth).status_code == 200
    page = client.get(prefix + '/feeds/field', headers=auth).json()
    assert len(page['items']) == 1 and page['items'][0]['envelope']['schema'] == 'field-ack/1'
    ack = field_receipt(page['items'][0]['envelope'])
    assert client.post(prefix + '/receipts/field', json=ack, headers=auth).status_code == 200
    report = client.get(prefix + '/feeds/field', params={'after': page['lastCursor']}, headers=auth).json()['items'][0]['envelope']
    assert report['schema'] == 'field-report/1'
    assert client.post(prefix + '/receipts/field', json=field_receipt(report), headers=auth).status_code == 200
    with physical.read_db() as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE type='PhysicalWaterLeakRepaired'").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'field_%'").fetchall()


def test_initial_connection_recovers_empty_uncommitted_field_after_process_loss(setup, monkeypatch):
    app, client, world = instance(setup)
    port = app.state.library.machine
    command = {'commandId': str(uuid.uuid4()), 'expectedRevision': 0,
               'controllerId': 'utilitysim-controller', 'sewerReturnFactor': '0.9', 'delaySeconds': 21600}
    def interrupted_field(_world, identity):
        path = setup[0] / 'worlds' / identity / 'machine-field.sqlite'
        assert path.resolve().is_relative_to(setup[0].resolve())
        path.write_bytes(b'')
        raise OSError('Lost process before first field transaction committed.')
    monkeypatch.setattr(port, 'field', interrupted_field)
    endpoint = f"/hosted/worlds/{world['id']}/connection"
    assert client.post(endpoint, json=command, headers=headers()).status_code == 503
    restarted = TestClient(create_app(setup[0], TOKEN, MACHINE_KEY))
    assert restarted.post(endpoint, json={**command, 'commandId': str(uuid.uuid4())}, headers=headers()).status_code == 422
    recovered = restarted.post(endpoint, json=command, headers=headers())
    assert recovered.status_code == 200 and recovered.json()['active'] is True
    assert restarted.post(endpoint, json=command, headers=headers()).json() == recovered.json()


def test_registered_field_reads_refuse_missing_or_empty_owner_without_replacement(setup):
    app, client, world = instance(setup)
    _, _, auth = connect(client, world['id'])
    field = app.state.library.machine.field_existing(app.state.library.machine.world({'world': world['id']}), world['id'])
    path = Path(field.path)
    saved = path.with_name('saved-field.sqlite')
    assert path.resolve().is_relative_to(setup[0].resolve()) and saved.resolve().is_relative_to(setup[0].resolve())
    endpoint = f"/machine/worlds/{world['id']}/field-managed/status"
    assignment_endpoint = f"/machine/worlds/{world['id']}/field-managed/assignment"
    assert client.get(assignment_endpoint, params={'assignmentId': 'absent'}, headers=auth).status_code == 404
    path.rename(saved)
    try:
        assert client.get(assignment_endpoint, params={'assignmentId': 'absent'}, headers=auth).status_code == 503
        assert client.get(endpoint, headers=auth).status_code == 503
        assert not path.exists()
        path.write_bytes(b'')
        assert client.get(endpoint, headers=auth).status_code == 422
        path.unlink()
    finally:
        saved.rename(path)
    assert client.get(endpoint, headers=auth).status_code == 200


def test_unconfigured_controller_is_truthful_and_no_machine_metadata_in_browser_status(setup):
    _, client, world = instance(setup)
    _, _, auth = connect(client, world['id'])
    status = client.get(f"/hosted/worlds/{world['id']}", headers=headers()).json()
    assert status['connectedClock']['configured'] and 'token' not in status
    assert client.get(f"/hosted/worlds/{world['id']}/connected", headers=headers()).status_code == 503
    assert client.get(f"/machine/worlds/{world['id']}/status", headers=auth).json()['delivery']['configuration']['from'] == '2026-07-15'


def test_backup_restore_original_path_preserves_capability_days_and_receipts(setup, tmp_path):
    from utilsim.hosted.backup import backup, restore

    _, client, world = instance(setup)
    identity = world['id']
    _, _, auth = connect(client, identity)
    assert advance(client, identity, auth).status_code == 200
    item, receipt = acknowledge_day(client, identity, auth)
    archive = tmp_path / 'private-backup'
    result = backup(setup[0], archive)
    assert result['worlds'] == 1
    lost = setup[0].with_name('old-volume')
    assert lost.resolve().is_relative_to(tmp_path.resolve()) and setup[0].resolve().is_relative_to(tmp_path.resolve())
    setup[0].rename(lost)
    restore(archive, setup[0])
    reopened = TestClient(create_app(setup[0], TOKEN, MACHINE_KEY))
    assert advance(reopened, identity, auth).status_code == 200
    assert reopened.get(f'/machine/worlds/{identity}/feeds/observations', headers=auth).json()['items'][0] == item
    assert reopened.post(f'/machine/worlds/{identity}/receipts/observations', json=receipt, headers=auth).status_code == 200


def test_three_day_collection_keeps_original_interval_in_daily_immutable_feed(setup):
    root, _, value, _ = setup
    value['configuration'].update(schemaVersion='physical-setup/4', physical={'meterChannels': {
        'enabled': True, 'amiPercent': 0, 'amrPercent': 0, 'manualPercent': 100,
        'manualReadIntervalDays': 3, 'manualReadSuccess': 1}})
    client = TestClient(create_app(root, TOKEN, MACHINE_KEY))
    created = client.post('/hosted/worlds', json=value, headers=headers()).json()
    identity = created['id']
    _, _, auth = connect(client, identity)
    for day in (16, 17, 18):
        result = advance(client, identity, auth, '2026-07-' + str(day))
        assert result.status_code == 200, result.text
        item, _ = acknowledge_day(client, identity, auth, after=day - 16)
        rows = item['envelope']['payload']['batch']['observations']
        if day != 18:
            assert rows == []
        else:
            assert {r['start'] for r in rows} == {'2026-07-15'}
            assert {r['end'] for r in rows} == {'2026-07-18'}
            assert item['envelope']['payload']['batch']['start'] == '2026-07-17'
            assert {r['availableAt'] for r in rows} == {'2026-07-18T06:00:00Z'}


def test_real_http_controller_proxy_binding_retained_command_and_wrong_run_denial(setup):
    app, client, world = instance(setup)
    _, connected, _ = connect(client, world['id'])
    service_token = 'test-distinct-controller-service-credential-32chars'
    expected_run = connected['environmentId']
    state = {'runId': expected_run, 'posts': [], 'headers': [], 'getError': False, 'postError': None, 'outage': False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, code=200):
            raw = json.dumps(value).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            assert self.headers['Authorization'] == 'Bearer ' + service_token
            if state['getError']:
                self.reply({'commandRejected': True, 'commandId': state['posts'][-1]['commandId']}, 409)
                return
            state['headers'].append((self.headers['X-UtilitySim-Run-Id'], self.headers['X-UtilitySim-Controller-Id']))
            self.reply({'schemaVersion': 'connected-status/1', 'runId': state['runId'],
                        'controllerId': 'utilitysim-controller', 'physicalThrough': None if state['outage'] else '2026-07-15',
                        'technicalError': 'ProducerUnavailable' if state['outage'] else None,
                        'clock': '2026-07-15T00:00:00Z', 'phase': 'idle', 'revision': 0,
                        'target': None, 'activeCommandId': None, 'lastCommand': None,
                        'counts': {'pending': 0, 'failed': 0, 'missing': 0, 'unmapped': 0, 'held': 0},
                        'supportedActions': ['pause', 'advance']})

        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['posts'].append(value)
            if state['postError'] is not None:
                self.reply({'commandId': value['commandId'], **state['postError']}, 409)
                return
            self.reply({'runId': state['runId'], 'controllerId': 'utilitysim-controller',
                        'commandId': value['commandId'], 'status': 'accepted', 'revision': 1})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        client = TestClient(create_app(setup[0], TOKEN, MACHINE_KEY,
            controller_url=f'http://127.0.0.1:{server.server_port}', controller_token=service_token, controller_allow_http=True))
        prefix = f"/hosted/worlds/{world['id']}/connected"
        status = client.get(prefix, headers=headers())
        assert status.status_code == 200, status.text
        assert status.json()['runId'] == expected_run
        state['outage'] = True
        outage = client.get(prefix, headers=headers())
        assert outage.status_code == 200 and outage.json()['physicalThrough'] is None
        assert outage.json()['technicalError'] == 'ProducerUnavailable'
        state['outage'] = False
        command = {'commandId': str(uuid.uuid4()), 'expectedRevision': 0, 'action': 'advance', 'through': '2026-07-18T06:00:00Z'}
        reply = client.post(prefix + '/commands', json=command, headers=headers())
        assert reply.status_code == 200, reply.text
        assert reply.json()['commandId'] == command['commandId'] and state['posts'] == [command]
        assert all(value == (expected_run, 'utilitysim-controller') for value in state['headers'])
        for target in ('2026-07-18', '2026-07-18T06:00:00.100000Z', '2026-07-18T07:00:00+01:00'):
            invalid = client.post(prefix + '/commands', json={**command, 'through': target}, headers=headers())
            assert invalid.status_code == 422 and state['posts'] == [command]
        state['runId'] = 'OTHER'
        assert client.post(prefix + '/commands', json=command, headers=headers()).status_code == 503
        assert state['posts'] == [command]
        assert client.post(prefix + '/commands', json=command, headers=headers(user='OTHER')).status_code == 404
        state['runId'] = expected_run
        state['postError'] = {'runId': expected_run, 'controllerId': 'utilitysim-controller',
                              'requestSha256': hashlib.sha256(canonical(command).encode()).hexdigest(),
                              'commandRejected': True, 'detail': 'private-provider-detail'}
        rejected = client.post(prefix + '/commands', json=command, headers=headers())
        assert rejected.status_code == 409 and rejected.json()['commandRejected'] is True
        assert rejected.json()['commandId'] == command['commandId'] and 'private-provider' not in rejected.text
        state['postError']['requestSha256'] = 'wrong-immutable-request'
        wrong_request = client.post(prefix + '/commands', json=command, headers=headers())
        assert wrong_request.status_code == 409 and 'commandRejected' not in wrong_request.json()
        state['postError'] = {'commandRejected': True}
        unbound = client.post(prefix + '/commands', json=command, headers=headers())
        assert unbound.status_code == 409 and 'commandRejected' not in unbound.json()
        state['postError'] = {'detail': 'Ambiguous changed-content conflict; not nonacceptance proof'}
        ambiguous = client.post(prefix + '/commands', json=command, headers=headers())
        assert ambiguous.status_code == 409 and 'commandRejected' not in ambiguous.json()
        state['getError'] = True
        preflight = client.post(prefix + '/commands', json=command, headers=headers())
        assert preflight.status_code == 409 and 'commandRejected' not in preflight.json()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_secret_file_bootstrap_and_credential_reuse_refused(setup, monkeypatch, tmp_path):
    from utilsim.hosted.server import from_environment

    with pytest.raises(ValueError, match='distinct'):
        create_app(setup[0], TOKEN, TOKEN)
    with pytest.raises(ValueError, match='distinct'):
        create_app(setup[0], TOKEN, MACHINE_KEY, controller_token=TOKEN)
    monkeypatch.setenv('UTILITYSIM_DATA_ROOT', str(setup[0]))
    for name, value in [('UTILITYSIM_RUNTIME_TOKEN', TOKEN), ('UTILITYSIM_MACHINE_KEY', MACHINE_KEY)]:
        secret = tmp_path / name
        secret.write_text(value + '\n')
        monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv(name + '_FILE', str(secret))
    for name in ('UTILITYSIM_CONTROLLER_URL', 'UTILITYSIM_CONTROLLER_TOKEN', 'UTILITYSIM_CONTROLLER_TOKEN_FILE'):
        monkeypatch.delenv(name, raising=False)
    assert TestClient(from_environment()).get('/hosted/health', headers=headers()).json()['machineConfigured']
    monkeypatch.setenv('UTILITYSIM_RUNTIME_TOKEN', TOKEN)
    with pytest.raises(ValueError, match='not both'):
        from_environment()
