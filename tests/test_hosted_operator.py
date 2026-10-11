"""Real HTTP proxy boundary; commercial execution is verified by its private owner."""
import json
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from test_hosted_machine import MACHINE_KEY, connect
from test_hosted_worlds import TOKEN, headers
from test_hosted_worlds import setup as setup

from utilsim.hosted.operator import COLLECTIONS, REQUEST_VERSION, RESPONSE_VERSION
from utilsim.hosted.server import create_app

CONTROL_TOKEN = 'public-test-controller-service-distinct-32'
OPERATOR_TOKEN = 'public-test-operator-service-distinct-32'


@contextmanager
def service():
    state = {'calls': [], 'response': None, 'drop': False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.path == '/connected/operator'
            assert self.headers['Authorization'] == 'Bearer ' + OPERATOR_TOKEN
            assert not self.headers.get('Origin')
            assert not self.headers.get('Transfer-Encoding')
            length = int(self.headers['Content-Length'])
            assert 0 < length <= 4096
            value = json.loads(self.rfile.read(length))
            assert value['schemaVersion'] == REQUEST_VERSION
            state['calls'].append(value)
            run, controller = self.headers['X-UtilitySim-Run-Id'], self.headers['X-UtilitySim-Controller-Id']
            if state['drop']:
                state['drop'] = False
                self.close_connection = True
                return
            action = value['action']
            result = {'schemaVersion': RESPONSE_VERSION, 'runId': run, 'controllerId': controller,
                      'premiseId': value['premiseId'], 'action': action,
                      'commandId': value.get('commandId')}
            code = 200
            if action == 'premise':
                result['result'] = {'physicalPremiseId': value['premiseId'], **{key: [] for key in COLLECTIONS}}
            elif action == 'release-read':
                result['result'] = {'status': 'resolved'}
            else:
                code = 200 if action == 'job' else 202
                result['result'] = {'id': value.get('jobId', 'job-original'), 'instance_id': run,
                    'type': 'invoicing' if action == 'invoice' else 'billing', 'status': 'queued',
                    'cycle_id': value.get('cycleId', 'cycle')}
            if state['response']:
                code, result = state['response'](value, result)
            raw = json.dumps(result).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def hosted(setup):
    with service() as (origin, state):
        app = create_app(setup[0], TOKEN, MACHINE_KEY, controller_url=origin,
                         controller_token=CONTROL_TOKEN, controller_allow_http=True, operator_token=OPERATOR_TOKEN)
        client = TestClient(app)
        world = client.post('/hosted/worlds', json=setup[2], headers=headers()).json()
        _, _, machine_auth = connect(client, world['id'])
        state.update(client=client, world=world, machine_auth=machine_auth, origin=origin, root=setup[0])
        yield state


def post(state, action='premise', auth=None, **extra):
    return state['client'].post(f"/hosted/worlds/{state['world']['id']}/operator",
        json={'action': action, 'premiseId': 'P1', **extra}, headers=auth or headers())


def bill(state, auth=None, **extra):
    return post(state, 'bill', auth, commandId=str(uuid.uuid4()), cycleId='cycle', contractId='contract', **extra)


def test_actual_http_pins_trusted_actor_roles_and_queued_receipt(hosted):
    for role in ('owner', 'operator', 'billing', 'support', 'analyst'):
        assert post(hosted, auth=headers(role=role)).status_code == 200
        sent = hosted['calls'][-1]
        assert sent['actor']['subject'] == 'user-a'
        assert sent['actor']['capabilities'] == (['billing.view', 'billing.run'] if role in ('owner', 'billing') else ['billing.view'])
        response = bill(hosted, headers(role=role))
        assert response.status_code == (202 if role in ('owner', 'billing') else 403)
        assert response.headers['cache-control'] == 'no-store'
        if response.status_code == 202:
            assert response.json()['result']['status'] == 'queued'
    assert post(hosted, auth=hosted['machine_auth']).status_code == 401
    assert post(hosted, auth=headers('other-user')).status_code == 404
    assert post(hosted, auth=headers(town='other-town')).status_code == 403


def test_all_actions_exact_original_uuid_and_lost_reply_reopen(hosted):
    actions = [('job', {'jobId': 'job-original'}),
               ('release-read', {'exceptionId': 'held-read', 'note': 'Reviewed actual usage'}),
               ('bill', {'cycleId': 'cycle', 'contractId': 'contract'}),
               ('invoice', {'cycleId': 'cycle', 'accountId': 'account'}),
               ('retry-job', {'jobId': 'failed-job'})]
    for action, fields in actions:
        if action != 'job':
            fields['commandId'] = str(uuid.uuid4())
        response = post(hosted, action, **fields)
        assert response.status_code == (200 if action in ('job', 'release-read') else 202)
        assert response.json()['commandId'] == fields.get('commandId')
    retained = {'commandId': str(uuid.uuid4()), 'cycleId': 'cycle', 'contractId': 'contract'}
    hosted['drop'] = True
    assert post(hosted, 'bill', **retained).status_code == 503
    assert len(hosted['calls']) == 6  # Transport never retries an uncertain mutation itself.
    hosted['client'] = TestClient(create_app(hosted['root'], TOKEN, MACHINE_KEY, controller_url=hosted['origin'],
        controller_token=CONTROL_TOKEN, controller_allow_http=True, operator_token=OPERATOR_TOKEN))
    assert post(hosted, 'bill', **retained).status_code == 202
    assert hosted['calls'][-1] == hosted['calls'][-2]


@pytest.mark.parametrize('grant', [
    {'role': 'owner', 'town': 'map-one', 'revoked': True},
    {'role': 'owner', 'town': 'map-one', 'expiresAt': '2000-01-01T00:00:00Z'},
    {'role': 'owner', 'town': 'map-one', 'expiresAt': 'invalid'},
    {'role': ['owner'], 'town': 'map-one'},
])
def test_current_grants_refuse_before_forwarding(hosted, grant):
    auth = {**headers(), 'X-UtilitySim-Grants': json.dumps([grant])}
    assert bill(hosted, auth).status_code == 403
    assert hosted['calls'] == []


@pytest.mark.parametrize('extra', [{'actor': {'subject': 'forged'}}, {'schemaVersion': REQUEST_VERSION},
    {'url': 'http://attacker'}, {'capabilities': ['billing.run']}, {'premiseId': 'foreign'},
    {'action': 'whole-cycle'}, {'premiseId': ''}, {'premiseId': 1}])
def test_no_browser_authority_arbitrary_routes_or_foreign_premise(hosted, extra):
    response = post(hosted, **extra)
    assert response.status_code in (404, 422)
    assert hosted['calls'] == []


def test_canonical_uuid_size_bounds_disabled_and_revoked_connection(hosted):
    assert post(hosted, 'bill', commandId=str(uuid.uuid4()).upper(), cycleId='cycle', contractId='contract').status_code == 422
    assert post(hosted, 'bill', commandId='not-uuid', cycleId='cycle', contractId='contract').status_code == 422
    assert post(hosted, 'bill', commandId=str(uuid.uuid4()), cycleId='😀' * 200, contractId='😀' * 200).status_code == 413
    disabled = TestClient(create_app(hosted['root'], TOKEN, MACHINE_KEY))
    assert disabled.post(f"/hosted/worlds/{hosted['world']['id']}/operator",
        json={'action': 'premise', 'premiseId': 'P1'}, headers=headers()).status_code == 503
    marker = hosted['client'].get(f"/hosted/worlds/{hosted['world']['id']}/connection", headers=headers()).json()
    assert hosted['client'].post(f"/hosted/worlds/{hosted['world']['id']}/connection/revoke",
        json={'commandId': str(uuid.uuid4()), 'expectedRevision': marker['revision']}, headers=headers()).status_code == 200
    assert post(hosted).status_code == 503
    assert hosted['calls'] == []


@pytest.mark.parametrize('change', [
    {'runId': 'other'}, {'controllerId': 'other'}, {'premiseId': 'other'}, {'action': 'invoice'},
    {'commandId': str(uuid.uuid4())}, {'schemaVersion': 'other'}, {'secret': 'unexpected'},
    {'result': {'physicalPremiseId': 'P1', **{key: [] for key in COLLECTIONS}, 'jobs': []}},
    {'result': {'physicalPremiseId': 'P1', **{key: [] for key in COLLECTIONS}, 'accounts': [{}] * 201}},
])
def test_invalid_upstream_scope_projection_or_bounds_fail_closed(hosted, change):
    hosted['response'] = lambda value, result: (200, {**result, **change})
    assert post(hosted).status_code == 503


def test_response_size_redirect_and_untyped_errors_are_not_forwarded(hosted):
    hosted['response'] = lambda value, result: (200, {**result, 'result': {
        'physicalPremiseId': 'P1', **{key: [] for key in COLLECTIONS}, 'accounts': [{'name': 'x' * 2_000_000}]}})
    assert post(hosted).status_code == 503
    hosted['response'] = lambda value, result: (302, {'url': 'http://attacker'})
    assert post(hosted).status_code == 503
    hosted['response'] = lambda value, result: (403, {'error': 'admission failed'})
    assert post(hosted).status_code == 503


@pytest.mark.parametrize('status', [400, 403, 404, 409, 413, 422, 503])
def test_scoped_refusals_preserve_status_and_do_not_report_completion(hosted, status):
    def refusal(value, result):
        return status, {key: result[key] for key in ('schemaVersion', 'runId', 'controllerId', 'premiseId', 'action')} | {'error': 'Actual operator refusal'}
    hosted['response'] = refusal
    response = bill(hosted)
    assert response.status_code == status
    assert 'result' not in response.json() and 'commandRejected' not in response.json()


def test_premise_pages_summary_scope_and_no_hidden_truth(hosted, setup):
    base = f"/hosted/worlds/{hosted['world']['id']}/premises"
    first = hosted['client'].get(base, params={'limit': 1}, headers=headers()).json()
    second = hosted['client'].get(base, params={'limit': 1, 'offset': 1}, headers=headers()).json()
    expected = sorted(p['id'] for p in setup[3]['premises'])
    assert first['total'] == len(expected) and first['sourceRevision'] == setup[2]['sourceRevision']
    assert first['premises'][0]['premiseId'] == expected[0]
    assert [record['premiseId'] for record in second['premises']] == expected[1:2]
    assert hosted['client'].get(base, params={'limit': 51}, headers=headers()).status_code == 422
    assert hosted['client'].get(base, params={'offset': -1}, headers=headers()).status_code == 422
    assert hosted['client'].get(base, params={'offset': 100000}, headers=headers()).json()['premises'] == []
    detail = hosted['client'].get(base + '/' + expected[0] + '/summary', headers=headers()).json()
    assert detail['premise']['premiseId'] == expected[0] and isinstance(detail['premise']['occupied'], bool)
    assert set(detail) == {'worldId', 'sourceRevision', 'premise'}
    assert set(detail['premise']) <= {'premiseId', 'address', 'parcelId', 'type', 'occupied'}
    assert hosted['client'].get(base + '/foreign/summary', headers=headers()).status_code == 404
    assert hosted['client'].get(base, headers=headers('other-user')).status_code == 404
    assert hosted['client'].get(base, headers=headers(town='other-town')).status_code == 403
    assert hosted['client'].get(base, headers=hosted['machine_auth']).status_code == 401


def test_operator_secret_config_and_file_bootstrap(setup, monkeypatch, tmp_path):
    from utilsim.hosted.server import from_environment

    for secret in (TOKEN, MACHINE_KEY, CONTROL_TOKEN, 'short', 'x' * 31 + '\n', 'x' * 4097):
        with pytest.raises(ValueError, match='operator'):
            create_app(setup[0], TOKEN, MACHINE_KEY, controller_token=CONTROL_TOKEN, operator_token=secret)
    with service() as (origin, _):
        for name in ('UTILITYSIM_RUNTIME_TOKEN', 'UTILITYSIM_MACHINE_KEY', 'UTILITYSIM_CONTROLLER_TOKEN', 'UTILITYSIM_OPERATOR_TOKEN'):
            monkeypatch.delenv(name, raising=False)
            monkeypatch.delenv(name + '_FILE', raising=False)
        monkeypatch.setenv('UTILITYSIM_DATA_ROOT', str(setup[0]))
        monkeypatch.setenv('UTILITYSIM_RUNTIME_TOKEN', TOKEN)
        monkeypatch.setenv('UTILITYSIM_CONTROLLER_TOKEN', CONTROL_TOKEN)
        monkeypatch.setenv('UTILITYSIM_CONTROLLER_URL', origin)
        monkeypatch.setenv('UTILITYSIM_CONTROLLER_ALLOW_HTTP', '1')
        file = tmp_path / 'operator-token'
        file.write_text(OPERATOR_TOKEN + '\n')
        monkeypatch.setenv('UTILITYSIM_OPERATOR_TOKEN_FILE', str(file))
        assert TestClient(from_environment()).get('/hosted/health', headers=headers()).status_code == 200
        monkeypatch.setenv('UTILITYSIM_OPERATOR_TOKEN', OPERATOR_TOKEN)
        with pytest.raises(ValueError, match='not both'):
            from_environment()
