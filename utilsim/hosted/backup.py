"""Private consistent producer backup; coordinated stacks must pause/stop VS too.

Restore requires the original data-root path because registered SQLite owner
paths are pinned. Never publish these archives: they contain private world state.
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
from contextlib import ExitStack, closing
from pathlib import Path

from utilsim.world import cruise

from .library import HostedLibrary


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def backup(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination == root or destination.is_relative_to(root) or destination.exists():
        raise ValueError('Choose a new private backup directory outside the data root.')
    if not (root / 'world-library.sqlite').is_file():
        raise ValueError('An existing initialized producer volume is required.')
    library = HostedLibrary(root)
    with library.library.db() as db:
        worlds = [r['id'] for r in db.execute('SELECT id FROM worlds ORDER BY id')]
    with ExitStack() as locks:
        for identity in worlds:
            world = library.library.world(identity)
            if not Path(world.path).resolve().is_relative_to(root):
                raise ValueError('Refuse a source world registered outside the owned volume.')
            locks.enter_context(cruise._exclusive(world))
        # Same lock order as machine changes: physical clock(s), then catalog.
        locks.enter_context(library.library.db())
        destination.mkdir(parents=True)
        for source in sorted(p for p in root.rglob('*') if p.is_file()):
            if source.is_symlink() or not source.resolve().is_relative_to(root):
                raise ValueError('Backup refuses links outside the owned volume.')
            if source.name.endswith(('-wal', '-shm', '.cruise.lock')):
                continue
            target = destination / 'data' / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == '.sqlite':
                with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
                    with closing(sqlite3.connect(target)) as copy:
                        original.backup(copy)
                        if copy.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                            raise ValueError('A database backup failed its integrity check.')
            else:
                shutil.copyfile(source, target)
        files = {p.relative_to(destination / 'data').as_posix(): digest(p)
                 for p in sorted((destination / 'data').rglob('*')) if p.is_file()}
        manifest = {'schemaVersion': 'producer-backup/1', 'originalRoot': str(root), 'files': files,
                    'registeredWorlds': worlds, 'vsCheckpointIncluded': False}
        (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        return {'schemaVersion': manifest['schemaVersion'], 'files': len(files), 'worlds': len(worlds)}


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['schemaVersion'] != 'producer-backup/1' or str(destination) != manifest['originalRoot']:
        raise ValueError('Restore only to the original pinned data-root path.')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Restore refuses to overwrite a nonempty volume.')
    for name, expected in manifest['files'].items():
        path = (source / 'data' / name).resolve()
        if not path.is_relative_to(source / 'data') or digest(path) != expected:
            raise ValueError('Backup path or checksum is invalid.')
    destination.mkdir(parents=True, exist_ok=True)
    for name in manifest['files']:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / 'data' / name, target)
    return {'schemaVersion': manifest['schemaVersion'], 'files': len(manifest['files'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    print(json.dumps((backup if args.action == 'backup' else restore)(args.source, args.destination)))


if __name__ == '__main__':
    main()
