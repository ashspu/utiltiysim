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
from pathlib import Path

import httpx

from utilsim.hosted.templates import import_reviewed, read_json, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--report', required=True)
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

    process = launch()
    try:
        value = {'commandId': str(uuid.uuid4()), 'sourceId': 'lantern-harbour', 'sourceRevision': revision,
                 'name': 'Isolated accepted-map restart QA', 'start': '2026-07-15',
                 'configuration': {'world': {'weather': {'summer_mean_c': 29}, 'meters': {'annual_meter_failure': 0}}}}
        first = call('POST', '/hosted/worlds', json=value)
        second = call('POST', '/hosted/worlds', json={**value, 'commandId': str(uuid.uuid4())})
        base = '/hosted/worlds/' + first['id']
        assert first['environmentId'] != second['environmentId']
        assert first['days'] == first['observations'] == 0
        snapshot = call('GET', base + '/map/snapshot')
        assert snapshot == read_json(package / 'source-snapshot.json')
        bindings = call('GET', base + '/map/bindings')['premises']
        original = read_json(package / 'bindings.json')['premises']
        assert {(b['parcelId'], b['premiseId'], tuple(b['meterIds'])) for b in bindings} == {
            (b['parcelId'], b['premiseId'], tuple(b['meterIds'])) for b in original}
        advanced = call('POST', base + '/advance', json={'through': '2026-07-17'})
        assert advanced['days'] == 2 and advanced['observations'] > 0
        assert call('GET', '/hosted/worlds/' + second['id'])['days'] == 0
        process.terminate()
        process.wait(timeout=15)
        process = launch()
        resumed = call('GET', base)
        assert resumed['configuration'] == first['configuration']
        assert resumed['fingerprint'] == first['fingerprint'] and resumed['through'] == advanced['through']
        assert call('POST', '/hosted/worlds', json=value)['id'] == first['id']
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
        assert all(p.exists() and sha(p.read_bytes()) == before[str(p)] for p in source_paths)
        report = {'status': 'passed-local-only', 'sourceRevision': revision, 'sourceFilesUnchanged': len(source_paths),
                  'sourceWorldChecked': source_world.exists(), 'counts': first['counts'], 'independentWorldIds': [first['id'], second['id']],
                  'restartResumedThrough': resumed['through'], 'observations': resumed['observations'], 'premiseChecks': picks,
                  'configurationRoundtrip': True, 'actualProcessRestart': True, 'idempotentCreate': True,
                  'principalIsolation': True, 'mapAndMeterBindingsExact': True, 'hostedDeployed': False}
        Path(args.report).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=15)
        client.close()


if __name__ == '__main__':
    main()
