"""Actual HTTP callback transport with explicit public trusted-runtime fixtures.

Private Run/service integration is verified separately by the VS owner.
"""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from test_world_field_managed import configured, utc
from test_world_field_travel import request
from test_world_water_faults import command as leak_command

from utilsim.hosted.machine_routes import ControllerProxy
from utilsim.hosted.managed_field import ManagedFieldBridge, field_assignment, field_status
from utilsim.world import field_execution, water_faults

TOKEN = 'public-test-distinct-controller-service-token-32'


@contextmanager
def connected(tmp_path):
    world, owner, authority, _, schedule = configured(tmp_path)
    with owner.db() as db:
        meta = owner.metadata(db)
    connection = {'world': 'fixture-world', 'environment': 'TEST', 'controller': 'controller',
                  'fingerprint': meta['fingerprint']}
    port = SimpleNamespace(world=lambda _: world, field_existing=lambda *_: owner)
    state = {'lease': False, 'change': {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.headers['Authorization'] == 'Bearer ' + TOKEN
            assert self.headers['X-UtilitySim-Run-Id'] == 'TEST'
            assert self.headers['X-UtilitySim-Controller-Id'] == 'controller'
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            value = {'runId': 'TEST', 'controllerId': 'controller'}
            if self.path == '/connected/field-calendar':
                value.update(schemaVersion='connected-field-calendar/1',
                             instant=utc(body['day'], body['time'], body['timeZone'], body['fold']))
            else:
                assert self.path == '/connected/field-authority'
                state['authorityCalls'] = state.get('authorityCalls', 0) + 1
                actual = authority(None, None)
                value.update(schemaVersion='connected-field-authority/1', worldFingerprint=meta['fingerprint'],
                    fieldOwnerId=owner.owner_id, runtimePath=str((tmp_path / 'runtime.sqlite').resolve()),
                    actorId=actual['actorId'], clock=actual['clock'], runStatus='paused',
                    leaseActive=state['lease'], leaseHeld=state.get('held', state['lease']),
                    crewResources={'crew-plumbing': schedule['resourceId']})
                if body.get('jobId'):
                    value.update(job=actual['job'], dependencies=actual['dependencies'])
                if body.get('reservationId'):
                    value['reservation'] = actual['reservation']
                value.update(state['change'])
                if state.get('flipAt') and state['authorityCalls'] >= state['flipAt']:
                    value.update(state['transition'])
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    proxy = ControllerProxy(f'http://127.0.0.1:{server.server_port}', TOKEN, allow_http=True)
    try:
        yield world, owner, authority, schedule, port, connection, proxy, state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_http_callbacks_actual_physical_visit_and_completed_receipt_replay(tmp_path):
    with connected(tmp_path) as (world, owner, auth, schedule, port, connection, proxy, state):
        water_faults.command(world, leak_command(world))
        bridge = ManagedFieldBridge(port, connection, proxy)
        plan = bridge.command('plan', {'quote': request(owner), 'schedule': schedule})
        assert plan['end'] == '2026-01-01T09:38:22Z'
        auth.accept(bridge.broker, plan)
        binding = {'assignmentId': 'A1', 'jobId': 'visit-1', 'reservationId': 'booking-1'}
        assert bridge.command('bind', binding)['planId'] == plan['planId']
        assert field_execution.run_due(owner) == []
        auth.dispatch(world, plan)
        execute = {'jobId': 'visit-1', 'reservationId': 'booking-1'}
        with pytest.raises(ValueError, match='lease'):
            ManagedFieldBridge(port, connection, proxy).command('execute', execute)
        assert water_faults.inspect(world, 'water')['current']['active']
        state['lease'] = True
        result = ManagedFieldBridge(port, connection, proxy).command('execute', execute)
        assert result['outcome'] == 'completed' and result['visitDate'] == '2026-01-01'
        assert water_faults.inspect(world, 'water')['current']['active'] is None
        auth.state['job']['status'] = 'completed'
        state['lease'] = False
        assert ManagedFieldBridge(port, connection, proxy).command('execute', execute) == result
        with world.db() as db:
            assert db.execute("SELECT COUNT(*) FROM events WHERE type='PhysicalWaterLeakRepaired'").fetchone()[0] == 1
        with pytest.raises(ValueError, match='Completed physical'):
            ManagedFieldBridge(port, connection, proxy).command('cancel', {'assignmentId': 'A1'})


@pytest.mark.parametrize('change', [
    {'worldFingerprint': 'FOREIGN'}, {'fieldOwnerId': 'FOREIGN'}, {'schemaVersion': 'wrong'},
    {'leaseActive': 'yes'}, {'leaseHeld': 'yes'}, {'leaseActive': True, 'leaseHeld': False},
    {'runtimePath': 'relative.sqlite'}, {'crewResources': {'crew-plumbing': ''}},
])
def test_foreign_or_unproved_live_authority_has_no_physical_effect(tmp_path, change):
    with connected(tmp_path) as (world, owner, _, _, port, connection, proxy, state):
        water_faults.command(world, leak_command(world))
        state['change'] = change
        with pytest.raises(ValueError):
            ManagedFieldBridge(port, connection, proxy)
        assert water_faults.inspect(world, 'water')['current']['active']
        assert field_status(port, connection)['enabled'] is False
        assert field_assignment(port, connection, 'A1')['checksum']


def test_no_caller_authority_or_resource_rebinding_and_actual_assignment_proof(tmp_path):
    with connected(tmp_path) as (_, owner, _, schedule, port, connection, proxy, state):
        status = field_status(port, connection)
        assert status['fieldOwnerId'] == owner.owner_id and status['enabled'] is False
        accepted = field_assignment(port, connection, 'A1')
        assert field_execution.checksum(accepted['assignment']) == accepted['checksum']
        bridge = ManagedFieldBridge(port, connection, proxy)
        with pytest.raises(ValueError, match='authority'):
            bridge.command('execute', {'jobId': 'visit-1', 'reservationId': 'booking-1', 'actorId': 'admin'})
        with pytest.raises(ValueError, match='pinned resource'):
            bridge.command('plan', {'quote': request(owner), 'schedule': {**schedule, 'resourceId': 'forged'}})
        state['held'] = True
        with pytest.raises(ValueError, match='release its actual delivery lease'):
            bridge.command('plan', {'quote': request(owner), 'schedule': schedule})
        assert field_status(port, connection)['enabled'] is False
        del state['held']
        bridge.command('plan', {'quote': request(owner), 'schedule': schedule})
        state['change'] = {'runtimePath': str((tmp_path / 'different-runtime.sqlite').resolve())}
        with pytest.raises(ValueError, match='Persisted field authority'):
            ManagedFieldBridge(port, connection, proxy)


@pytest.mark.parametrize('action', ['plan', 'bind'])
@pytest.mark.parametrize('transition', [
    {'runStatus': 'running', 'leaseActive': True, 'leaseHeld': True},
    {'runStatus': 'running', 'leaseActive': False, 'leaseHeld': False},
    {'runStatus': 'paused', 'leaseActive': False, 'leaseHeld': True},
])
def test_later_authority_transition_does_not_persist_plan_or_binding(tmp_path, action, transition):
    with connected(tmp_path) as (_, owner, auth, schedule, port, connection, proxy, state):
        bridge = ManagedFieldBridge(port, connection, proxy)
        value = {'quote': request(owner), 'schedule': schedule}
        if action == 'bind':
            plan = bridge.command('plan', value)
            auth.accept(bridge.broker, plan)
            value = {'assignmentId': 'A1', 'jobId': 'visit-1', 'reservationId': 'booking-1'}
        state.update(authorityCalls=0, flipAt=3, transition=transition)
        bridge = ManagedFieldBridge(port, connection, proxy)
        with pytest.raises(ValueError, match='Pause the Run'):
            bridge.command(action, value)
        assert state['authorityCalls'] == 3
        assert bridge.require_idle is False
        if action == 'plan':
            assert field_status(port, connection)['enabled'] is False
        else:
            with owner.db() as db:
                row = db.execute('SELECT binding FROM field_managed WHERE assignment=?', ('A1',)).fetchone()
                assert row['binding'] is None
