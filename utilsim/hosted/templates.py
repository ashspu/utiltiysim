"""Admin-only import of reviewed map packages; never generate geography."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from utilsim.worker.world_creation import MAX_SNAPSHOT_BYTES, validate_snapshot
from utilsim.world.store import canonical


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def safe_file(root, relative):
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Template file leaves its package.')
    return path


def verify(directory, revision=None):
    manifest = read_json(directory / 'manifest.json')
    if revision and sha(canonical(manifest).encode()) != revision:
        raise ValueError('Template manifest changed.')
    for name, digest in manifest['files'].items():
        if sha(safe_file(directory, name).read_bytes()) != digest:
            raise ValueError('Template file checksum failed: ' + name)
    return manifest


def import_reviewed(package, root, source_id, name, grant_town_id):
    """Explicit administrator operation. Copies immutable templates, not source history."""
    import re
    if not all(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', item) for item in (source_id, grant_town_id)):
        raise ValueError('Invalid source ID.')
    package, root = Path(package).resolve(), Path(root).resolve()
    runtime = read_json(package / 'runtime-manifest.json')
    delivery = read_json(package / 'delivery.json')
    raw = (package / 'source-snapshot.json').read_bytes()
    if len(raw) > MAX_SNAPSHOT_BYTES or sha(raw) != runtime['sourceSnapshotSha256']:
        raise ValueError('Reviewed source snapshot checksum/size failed.')
    snapshot = json.loads(raw)
    validate_snapshot(snapshot)
    bindings = read_json(package / 'bindings.json')['premises']
    homes = {p['id'] for p in snapshot['premises']}
    if len(bindings) != len(homes) or {b['premiseId'] for b in bindings} != homes:
        raise ValueError('Reviewed premise bindings do not cover the snapshot.')
    if len({b['parcelId'] for b in bindings}) != len(bindings):
        raise ValueError('Reviewed parcel identities are not unique.')
    services = {}
    for service in snapshot['servicePoints']:
        services.setdefault(service['premiseId'], set()).add(service['meterId'])
    for binding in bindings:
        if set(binding['meterIds']) != services.get(binding['premiseId'], set()):
            raise ValueError('Reviewed meter bindings differ from the snapshot.')
    files = {'source-snapshot.json': sha(raw)}
    for filename in ('bindings.json', 'scene.json', 'properties.geojson', 'simulation-routing.geojson', 'unmapped.geojson'):
        files[filename] = sha(safe_file(package, filename).read_bytes())
    for entry in delivery['artwork']:
        filename = entry['path']
        actual = sha(safe_file(package, filename).read_bytes())
        if actual != entry['sha256']:
            raise ValueError('Reviewed artwork checksum failed.')
        files[filename] = actual
    for key, filename in [('parcelsPath', 'properties.geojson'), ('routingPath', 'simulation-routing.geojson'), ('unmappedPath', 'unmapped.geojson')]:
        if files[filename] != runtime['sourceHashes'][key]:
            raise ValueError('Reviewed geometry checksum failed.')
    manifest = {'schemaVersion': 'hosted-template/1', 'sourceId': source_id, 'name': name,
                'townId': snapshot['id'], 'grantTownId': grant_town_id, 'snapshotSha256': sha(canonical(snapshot).encode()),
                'counts': {'premises': len(homes), 'residential': delivery['residential'],
                           'nonResidential': delivery['nonResidential'], 'meters': len(snapshot['meters'])},
                'files': files}
    if manifest['counts']['residential'] + manifest['counts']['nonResidential'] != len(homes):
        raise ValueError('Reviewed premise counts differ from the snapshot.')
    revision = sha(canonical(manifest).encode())
    parent = root / 'templates' / source_id
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / revision
    if target.exists():
        verify(target, revision)
        return revision
    with tempfile.TemporaryDirectory(dir=parent, prefix='.import-') as temporary:
        staged = Path(temporary) / 'package'
        staged.mkdir()
        for filename in files:
            destination = staged / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_file(package, filename), destination)
        (staged / 'manifest.json').write_text(canonical(manifest), encoding='utf-8')
        verify(staged, revision)
        staged.rename(target)
    return revision
