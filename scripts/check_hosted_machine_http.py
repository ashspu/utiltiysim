"""Prepare one fresh accepted Lantern world for actual HTTP VS acceptance.

Credentials stay in the private QA root. This never seeds invoices, advances the
world or fabricates outbox acknowledgements. VS drives the coordinated phases.
"""
import argparse
import json
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from utilsim.hosted.templates import import_reviewed
from utilsim.world.store import canonical


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def initialize(root, source):
    root.mkdir(parents=True, exist_ok=True)
    secret_root = root / 'private'
    secret_root.mkdir(exist_ok=True)
    for name in ('gateway', 'machine-key', 'controller'):
        file = secret_root / (name + '.token')
        if not file.exists():
            file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    revision = import_reviewed(source, root / 'data', 'lantern-harbour', 'Lantern Harbour', 'lantern-bay-500')
    write(root / 'runtime-env.json', {
        'UTILITYSIM_DATA_ROOT': str(root / 'data'),
        'UTILITYSIM_RUNTIME_TOKEN_FILE': str(secret_root / 'gateway.token'),
        'UTILITYSIM_MACHINE_KEY_FILE': str(secret_root / 'machine-key.token'),
        'UTILITYSIM_CONTROLLER_TOKEN_FILE': str(secret_root / 'controller.token'),
        'UTILITYSIM_CONTROLLER_URL': 'http://127.0.0.1:8027',
        'UTILITYSIM_CONTROLLER_ALLOW_HTTP': '1',
        'UTILITYSIM_CONTROLLER_ID': 'utilitysim-controller'})
    request_path = root / 'create-command.json'
    if not request_path.exists():
        write(request_path, {'commandId': str(uuid.uuid4()), 'sourceId': 'lantern-harbour', 'sourceRevision': revision,
                            'name': 'Lantern coordinated HTTP acceptance', 'start': '2026-07-15',
                            'configuration': {'schemaVersion': 'physical-setup/4',
                                'world': {'meters': {'annual_meter_failure': 0, 'annual_meter_drift': 0}},
                                'physical': {'meterChannels': {'enabled': True, 'amiPercent': 0,
                                    'amrPercent': 0, 'manualPercent': 100, 'manualReadIntervalDays': 3,
                                    'manualReadSuccess': 1},
                                    'householdFinance': {'enabled': True, 'cashCents': 10000,
                                        'essentialReserveCents': 0, 'maxPaymentCents': 10000, 'paymentProbability': 1},
                                    'customerContacts': {'active': True, 'noticeProbabilityPerDay': 1,
                                        'deliveryDelaySeconds': 0, 'repeatAfterDays': 1, 'maxContacts': 10}}}})
    assert json.loads(request_path.read_text())['sourceRevision'] == revision
    return revision


def prepare(root, origin):
    url = urlsplit(origin)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or not url.port or url.path:
        raise ValueError('Use an explicit loopback QA origin.')
    opener = build_opener(ProxyHandler({}))
    gateway = (root / 'private/gateway.token').read_text()
    headers = {'Authorization': 'Bearer ' + gateway, 'Content-Type': 'application/json',
               'X-UtilitySim-User-Id': 'connected-http-qa',
               'X-UtilitySim-Grants': json.dumps([{'town': 'lantern-bay-500', 'role': 'owner'}])}

    def call(path, value=None, auth=None):
        with opener.open(Request(origin + path, data=canonical(value).encode() if value is not None else None,
                                 headers=auth or headers), timeout=20) as response:
            return json.load(response)

    creation = json.loads((root / 'create-command.json').read_text())
    started, calls, slowest = time.monotonic(), 0, 0
    while True:
        before = time.monotonic()
        world = call('/hosted/worlds', creation)
        slowest = max(slowest, time.monotonic() - before)
        calls += 1
        if world['available']:
            break
        print(json.dumps({'phase': 'initialize', 'applied': world['initialization'].get('appliedCommands'), 'calls': calls}), flush=True)
        if time.monotonic() - started > 600:
            raise TimeoutError('Initialization incomplete; retry retained creation command.')
    identity = world['id']
    connection_file = root / 'connection-command.json'
    if not connection_file.exists():
        write(connection_file, {'commandId': str(uuid.uuid4()), 'expectedRevision': 0,
                                'controllerId': 'utilitysim-controller', 'sewerReturnFactor': '0.9', 'delaySeconds': 21600})
    connection = call(f'/hosted/worlds/{identity}/connection', json.loads(connection_file.read_text()))
    token_file = root / 'private/world-capability.token'
    token_file.write_text(connection['token'], encoding='utf-8')
    auth = {'Authorization': 'Bearer ' + connection['token']}
    status = call(f'/machine/worlds/{identity}/status', auth=auth)
    cohorts, after = [], ''
    while True:
        from urllib.parse import urlencode
        page = call(f'/machine/worlds/{identity}/cohorts?' + urlencode({'after': after, 'limit': 50}), auth=auth)
        cohorts.extend(page['items'])
        if page['nextAfter'] is None:
            break
        after = page['nextAfter']
    assert len(cohorts) == 300 and status['through'] == '2026-07-15'
    config = {'origin': origin, 'worldId': identity, 'tokenFile': str(token_file), 'allowLoopback': True}
    write(root / 'remote-world.json', config)
    write(root / 'cohorts.json', cohorts)
    proof = {'prepared': True, 'worldId': identity, 'runId': status['runId'], 'fingerprint': status['fingerprint'],
             'through': status['through'], 'sourceRevision': creation['sourceRevision'], 'premises': 436,
             'meterAssets': 1262, 'configuredHouseholds': len(cohorts), 'creationCalls': calls,
             'slowestCreateSeconds': round(slowest, 3), 'elapsedSeconds': round(time.monotonic() - started, 3),
             'runtimeConnectedToVS': False, 'invoiceSeeded': False, 'outboxAcknowledgementsSeeded': False,
             'remoteWorldConfig': str(root / 'remote-world.json')}
    write(root / 'prepared.json', proof)
    print(json.dumps(proof), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['initialize', 'prepare'])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--origin')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == 'initialize':
        if args.source is None:
            parser.error('--source is required')
        print(json.dumps({'sourceRevision': initialize(root, args.source.resolve()), 'envFile': str(root / 'runtime-env.json')}))
    else:
        prepare(root, args.origin)


if __name__ == '__main__':
    main()
