"""Linux Docker smoke. Ephemeral credentials and data never become artifacts."""
import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.STDOUT).strip()


def fixture(data):
    snapshot = {'schemaVersion': 'utility-town/2.0', 'id': 'container-town', 'seed': '42',
        'bounds': [0, 0, 100, 100], 'roads': [], 'networks': {},
        'premises': [{'id': 'P1', 'address': '1 Fixture Street', 'floorAreaM2': 100, 'occupants': 2,
            'occupied': True, 'heatingFuel': 'gas', 'hasAC': True, 'dailyKWh': 20, 'dailyGasM3': .6, 'dailyWaterM3': .4}],
        'meters': [{'id': c, 'installedAt': '2015-01-01'} for c in ('electric', 'gas', 'water')],
        'servicePoints': [{'premiseId': 'P1', 'commodity': c, 'meterId': c, 'installationId': 'I-' + c}
                          for c in ('electric', 'gas', 'water')]}
    files = {'source-snapshot.json': canonical(snapshot), 'bindings.json': canonical({'premises': [
        {'parcelId': 'fixture-parcel', 'premiseId': 'P1', 'premiseType': 'residential', 'meterIds': ['electric', 'gas', 'water']}]})}
    manifest = {'sourceId': 'container-fixture', 'grantTownId': 'fixture', 'name': 'Container fixture',
        'townId': snapshot['id'], 'snapshotSha256': hashlib.sha256(files['source-snapshot.json'].encode()).hexdigest(),
        'counts': {'premises': 1}, 'files': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()}}
    revision = hashlib.sha256(canonical(manifest).encode()).hexdigest()
    directory = data / 'templates' / 'container-fixture' / revision
    directory.mkdir(parents=True)
    for name, value in files.items():
        (directory / name).write_text(value)
    (directory / 'manifest.json').write_text(canonical(manifest))
    return revision


def run(image, output):
    with tempfile.TemporaryDirectory(prefix='producer-container-') as directory:
        root = Path(directory).resolve()
        root.chmod(0o755)
        data, private, backup = root / 'data', root / 'private', root / 'backup'
        for path in (data, private, backup):
            path.mkdir()
            path.chmod(0o777 if path != private else 0o755)
        revision = fixture(data)
        for path in data.rglob('*'):
            path.chmod(0o755 if path.is_dir() else 0o644)
        gateway, machine = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
        for name, value in [('gateway', gateway), ('machine', machine)]:
            path = private / name
            path.write_text(value)
            path.chmod(0o444)
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        origin = f'http://127.0.0.1:{port}'
        name = 'producer-smoke-' + uuid.uuid4().hex[:12]
        mounts = ['--mount', f'type=bind,source={data},target=/data',
                  '--mount', f'type=bind,source={private},target=/run/secrets,readonly']

        def start():
            docker('run', '-d', '--name', name, '-p', f'127.0.0.1:{port}:8080', *mounts,
                '-e', 'UTILITYSIM_RUNTIME_TOKEN_FILE=/run/secrets/gateway',
                '-e', 'UTILITYSIM_MACHINE_KEY_FILE=/run/secrets/machine', image)

        opener = build_opener(ProxyHandler({}))
        headers = {'Authorization': 'Bearer ' + gateway, 'Content-Type': 'application/json',
                   'X-UtilitySim-User-Id': 'fixture-owner',
                   'X-UtilitySim-Grants': canonical([{'role': 'owner', 'town': 'fixture'}])}

        def call(path, value=None, auth=None):
            with opener.open(Request(origin + path, data=canonical(value).encode() if value is not None else None,
                                     headers=auth or headers), timeout=10) as response:
                return json.load(response)

        def wait_ready():
            for _ in range(100):
                try:
                    assert call('/hosted/health')['status'] == 'ready'
                    return
                except (URLError, ConnectionError):
                    time.sleep(.1)
            raise TimeoutError('Container did not become ready.')

        try:
            start()
            wait_ready()
            assert docker('exec', name, 'id', '-u') == '10001'
            assert json.loads(docker('exec', name, 'python', '-m', 'utilsim.hosted.health')) == {'status': 'ready'}
            created = call('/hosted/worlds', {'commandId': str(uuid.uuid4()), 'sourceId': 'container-fixture',
                'sourceRevision': revision, 'name': 'Container smoke', 'start': '2026-01-01', 'configuration': {'world': {}}})
            identity = created['id']
            connected = call(f'/hosted/worlds/{identity}/connection', {'commandId': str(uuid.uuid4()),
                'expectedRevision': 0, 'controllerId': 'utilitysim-controller', 'sewerReturnFactor': '0.9', 'delaySeconds': 21600})
            auth = {'Authorization': 'Bearer ' + connected['token'], 'Content-Type': 'application/json'}
            prefix = f'/machine/worlds/{identity}'
            command = {'commandId': 'container-day', 'through': '2026-01-02', 'processingAt': '2026-01-02T00:00:00Z'}
            advanced = call(prefix + '/advance', command, auth)
            page = call(prefix + '/feeds/observations', auth=auth)
            rows = page['items'][0]['envelope']['payload']['batch']['observations']
            assert len(rows) == 4 and {r['availableAt'] for r in rows} == {'2026-01-02T06:00:00Z'}
            receipt = {'id': advanced['observationCommandId'], 'status': 'pending'}
            call(prefix + '/receipts/observations', receipt, auth)
            try:
                call(prefix + '/status')
                raise AssertionError('Gateway credential crossed machine boundary.')
            except HTTPError as denied:
                assert denied.code == 401
            docker('restart', name)
            wait_ready()
            assert call(prefix + '/advance', command, auth) == advanced
            assert call(prefix + '/feeds/observations', auth=auth) == page
            docker('rm', '-f', name)
            docker('run', '--rm', *mounts, '--mount', f'type=bind,source={backup},target=/backup',
                   '--entrypoint', 'python', image, '-m', 'utilsim.hosted.backup', 'backup', '--source', '/data',
                   '--destination', '/backup/checkpoint')
            # Verify all destructive/move targets remain inside the disposable root.
            old = root / 'old-data'
            assert data.resolve().is_relative_to(root) and old.resolve().is_relative_to(root)
            data.rename(old)
            data.mkdir()
            data.chmod(0o777)
            docker('run', '--rm', *mounts, '--mount', f'type=bind,source={backup},target=/backup',
                   '--entrypoint', 'python', image, '-m', 'utilsim.hosted.backup', 'restore',
                   '--source', '/backup/checkpoint', '--destination', '/data')
            start()
            wait_ready()
            assert call(prefix + '/advance', command, auth) == advanced
            assert call(prefix + '/feeds/observations', auth=auth) == page
            call(prefix + '/receipts/observations', receipt, auth)
            evidence = {'containerBuiltAndBooted': True, 'uid': 10001, 'authenticatedHealth': True,
                'gatewayMachineSeparation': True, 'measuredReads': 4, 'delaySeconds': 21600,
                'restartReplay': True, 'restoredVolumeReplay': True,
                'authenticatedReadinessCommand': True,
                'imageId': docker('image', 'inspect', image, '--format', '{{.Id}}'),
                'revision': docker('image', 'inspect', image, '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}'),
                'productionConnected': False}
            output.write_text(json.dumps(evidence, indent=2) + '\n')
            print(json.dumps(evidence))
        finally:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            assert root.parent == Path(tempfile.gettempdir()).resolve() and root.name.startswith('producer-container-')
            # Release files made by UID10001 to the test runner before deleting
            # this one disposable tree; no other mount or workspace is touched.
            subprocess.run(['docker', 'run', '--rm', '--user', '0', '--mount', f'type=bind,source={root},target=/cleanup',
                            '--entrypoint', 'chown', image, '-R', f'{os.getuid()}:{os.getgid()}', '/cleanup'], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.image, args.output)


if __name__ == '__main__':
    main()
