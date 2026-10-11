"""Principal-scoped creation journal using the existing pinned-snapshot engine."""
import json
import math
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from utilsim.config.wizard import world_configuration
from utilsim.worker import world_creation
from utilsim.worker.worlds import WorldLibrary
from utilsim.world import cruise, physical_profiles, sentiment, storms
from utilsim.world.map_view import WorldMap
from utilsim.world.store import MODEL_VERSION, World, canonical

from . import setup
from .templates import read_json, sha, verify


def configuration(value):
    if not isinstance(value, dict) or set(value) - {'world', 'physical', 'schemaVersion'}:
        raise ValueError('Unsupported setup group. Use the advertised physical setup schema; geography cannot change.')
    extended = 'physical' in value or 'schemaVersion' in value
    if extended and value.get('schemaVersion') not in setup.SUPPORTED_VERSIONS:
        raise ValueError('Physical policies require a supported schemaVersion: ' + ', '.join(setup.SUPPORTED_VERSIONS))
    supplied = value.get('world', {})
    schema, defaults = world_configuration()
    if not isinstance(supplied, dict) or set(supplied) - set(defaults):
        raise ValueError('Unknown world setting group.')
    for group, fields in supplied.items():
        if not isinstance(fields, dict) or set(fields) - set(defaults[group]):
            raise ValueError('Unknown world setting.')
        for key, number in fields.items():
            bounds = schema['properties'][group]['properties'][key]
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ValueError('World settings must be finite numbers.')
            if number < bounds.get('minimum', -math.inf) or number > bounds.get('maximum', math.inf):
                raise ValueError('World setting outside supported bounds.')
        defaults[group].update(fields)
    return {'world': defaults, **({'schemaVersion': value['schemaVersion'], 'physical': setup.normalize(value.get('physical', {}), value['schemaVersion'])} if extended else {})}


class ManagedWorld(World):
    """Open an already registered world without constructor schema writes.

    Creation owns initialization. Domain commands perform their own explicit
    migrations; invalid commands and inspection must not migrate a database.
    """
    def __init__(self, registered):
        with registered.read_db():
            self.path = str(registered.path)


class HostedLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.library = WorldLibrary(self.root)
        with self.library.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS hosted_worlds ('
                       'id TEXT PRIMARY KEY, principal TEXT NOT NULL, command TEXT NOT NULL,'
                       'request TEXT NOT NULL, manifest TEXT NOT NULL, bindings TEXT NOT NULL,'
                       'UNIQUE(principal,command))')
            db.execute('CREATE TABLE IF NOT EXISTS hosted_initialization ('
                       'id TEXT PRIMARY KEY,state TEXT NOT NULL,progress TEXT NOT NULL)')

    def templates(self):
        entries = []
        for file in sorted((self.root / 'templates').glob('*/*/manifest.json')):
            try:
                item = read_json(file)
                if sha(canonical(item).encode()) != file.parent.name:
                    continue
                entry = {**{k: item[k] for k in ('sourceId', 'name', 'townId', 'grantTownId', 'counts', 'snapshotSha256')},
                         'sourceRevision': file.parent.name, 'ready': True}
                try:
                    verify(file.parent, file.parent.name)
                except (OSError, ValueError):
                    entry.update(ready=False, error='Template package is unavailable or changed.')
                entries.append(entry)
            except (OSError, ValueError, KeyError):
                continue
        return entries

    def template(self, source, revision):
        if not isinstance(source, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', source):
            raise ValueError('Choose an approved source ID.')
        if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{64}', revision):
            raise ValueError('Choose an immutable source revision.')
        directory = self.root / 'templates' / source / revision
        manifest = verify(directory, revision)
        if manifest['sourceId'] != source:
            raise ValueError('Template source identity mismatch.')
        return directory, manifest

    def lookup(self, principal, identity):
        with self.library.db() as db:
            row = db.execute('SELECT * FROM hosted_worlds WHERE id=? AND principal=?', (identity, principal)).fetchone()
        if row is None:
            raise KeyError('Unknown saved world.')
        return row

    def create(self, principal, value):
        if not isinstance(value, dict) or set(value) != {'commandId', 'sourceId', 'sourceRevision', 'name', 'start', 'configuration'}:
            raise ValueError('Provide commandId, sourceId, sourceRevision, name, start and configuration only.')
        try:
            command = str(uuid.UUID(value['commandId']))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('A creation command UUID is required.') from exc
        name, start = value['name'], value['start']
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError('Provide a world name of 1 to 200 characters.')
        if not isinstance(start, str) or date.fromisoformat(start).isoformat() != start:
            raise ValueError('Use canonical YYYY-MM-DD dates.')
        request = {**value, 'commandId': command, 'configuration': configuration(value['configuration'])}
        encoded = canonical(request)
        with self.library.db() as db:
            existing = db.execute('SELECT * FROM hosted_worlds WHERE principal=? AND command=?', (principal, command)).fetchone()
        if existing:
            if existing['request'] != encoded:
                raise ValueError('That creation command belongs to different inputs.')
            world_creation.retry(self.library, existing['id'])
            self.apply_setup(existing)
            return self.describe(existing)
        directory, manifest = self.template(value['sourceId'], value['sourceRevision'])
        snapshot = read_json(directory / 'source-snapshot.json')
        world_creation.validate_snapshot(snapshot)
        pinned = canonical(snapshot)
        if sha(pinned.encode()) != manifest['snapshotSha256']:
            raise ValueError('Snapshot identity mismatch.')
        bindings = read_json(directory / 'bindings.json')['premises']
        identity = uuid.uuid4().hex
        settings = {k: v for fields in request['configuration']['world'].values() for k, v in fields.items()}
        engine_request = canonical({'environment': 'instance-' + identity, 'start': start,
                                    'settings': settings, 'modelVersion': MODEL_VERSION})
        with self.library.db() as db:
            # One reservation includes principal, immutable inputs, snapshot and map bindings.
            existing = db.execute('SELECT * FROM hosted_worlds WHERE principal=? AND command=?', (principal, command)).fetchone()
            if existing:
                if existing['request'] != encoded:
                    raise ValueError('That creation command belongs to different inputs.')
                identity = existing['id']
            else:
                db.execute('INSERT INTO hosted_worlds VALUES(?,?,?,?,?,?)',
                           (identity, principal, command, encoded, canonical(manifest), canonical(bindings)))
                db.execute('INSERT INTO world_creations VALUES(?,?,?,?,?,?)',
                           (identity, engine_request, pinned, sha(pinned.encode()), identity, 'pending'))
                if 'physical' in request['configuration']:
                    db.execute('INSERT INTO hosted_initialization VALUES(?,?,?)',
                               (identity, 'pending', canonical({'appliedCommands': 0})))
        world_creation.retry(self.library, identity)
        row = self.lookup(principal, identity)
        self.apply_setup(row)
        return self.describe(row)

    def initialization(self, identity):
        with self.library.db() as db:
            row = db.execute('SELECT * FROM hosted_initialization WHERE id=?', (identity,)).fetchone()
        return {'state': row['state'], **json.loads(row['progress'])} if row else {'state': 'complete', 'appliedCommands': 0}

    def apply_setup(self, row):
        if self.initialization(row['id'])['state'] == 'complete':
            return
        request = json.loads(row['request'])
        def progress(count):
            with self.library.db() as db:
                db.execute('UPDATE hosted_initialization SET progress=? WHERE id=?',
                           (canonical({'appliedCommands': count}), row['id']))
        with self.manual_world(row, initializing=True) as world:
            result = setup.apply(world, row['id'], request['configuration'], json.loads(row['bindings']),
                                 WorldMap(world).snapshot(), progress)
            state = 'complete' if result.pop('complete') else 'pending'
            with self.library.db() as db:
                db.execute('UPDATE hosted_initialization SET state=?,progress=? WHERE id=?',
                           (state, canonical(result), row['id']))

    def describe(self, row):
        request, manifest = json.loads(row['request']), json.loads(row['manifest'])
        base = '/hosted/worlds/' + row['id']
        result = {'id': row['id'], **{k: request[k] for k in ('name', 'sourceId', 'sourceRevision', 'start', 'configuration')},
                  'townId': manifest['townId'], 'grantTownId': manifest['grantTownId'], 'counts': manifest['counts'], 'snapshotSha256': manifest['snapshotSha256'],
                  'paths': {k: base + suffix for k, suffix in {'status': '', 'snapshot': '/map/snapshot',
                            'bindings': '/map/bindings', 'advance': '/advance', 'observations': '/observations',
                            'events': '/events', 'storms': '/events/storms', 'sentiment': '/events/sentiment'}.items()},
                  'capabilities': {'stormEvents': storms.VERSION, 'advanceMode': 'synchronous', 'backgroundJobs': False},
                  'configurationRevision': 1, 'configurationEditable': False}
        with self.library.db() as db:
            state = db.execute('SELECT state FROM world_creations WHERE command=?', (row['id'],)).fetchone()[0]
        result['state'] = state
        result['initialization'] = self.initialization(row['id'])
        try:
            world = self.library.world(row['id'])
            result.update(WorldMap(world).status(), available=True)
            with world.read_db() as db:
                meta = world.metadata(db)
                result['fingerprint'] = meta['fingerprint']
                result['physicalProfiles'] = physical_profiles.summary(db, meta)
        except (OSError, sqlite3.Error, KeyError, ValueError):
            result.update(available=False, error='Saved world is pending or unavailable. Retry its original creation command or restore its volume.')
        if result['initialization']['state'] != 'complete':
            result.update(state='configuring', available=False,
                          error='Initial physical policies are incomplete. Retry the original creation request before advancing.')
        return result

    def listing(self, principal):
        with self.library.db() as db:
            return db.execute('SELECT * FROM hosted_worlds WHERE principal=? ORDER BY rowid DESC', (principal,)).fetchall()

    def advance(self, row, through):
        with self.manual_world(row) as world:
            state = WorldMap(world).status()
            if not isinstance(through, str) or date.fromisoformat(through).isoformat() != through:
                raise ValueError('Use a canonical through date.')
            days = (date.fromisoformat(through) - date.fromisoformat(state['through'])).days
            if not 0 <= days <= 31:
                raise ValueError('Advance zero to 31 days per request; the clock cannot rewind.')
            world.advance(through)
        return self.describe(row)

    @contextmanager
    def manual_world(self, row, initializing=False):
        if not initializing and self.initialization(row['id'])['state'] != 'complete':
            raise ValueError('Initial physical setup is incomplete; retry its original creation request first.')
        readonly = self.library.world(row['id'])
        # Same lock order and clock ownership as the original local controls.
        with cruise.manual_control(readonly):
            with readonly.read_db() as db:
                if db.execute('SELECT 1 FROM observation_delivery_configuration LIMIT 1').fetchone():
                    raise ValueError('Shared delivery owns this clock; use its configured runtime controls.')
            yield ManagedWorld(readonly)

    def storm_command(self, row, value):
        common = {'commandId', 'expectedRevision', 'effectiveDate', 'action', 'reason', 'causalReference'}
        extra = {'schedule': {'startDate', 'endDate', 'temperatureOffsetC', 'multipliers'},
                 'cancel': {'stormId'}}.get(value.get('action')) if isinstance(value.get('action'), str) else None
        if extra is None or set(value) != common | extra:
            raise ValueError('Provide only the supported storm schedule or cancellation fields.')
        try:
            command_id = str(uuid.UUID(value['commandId']))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('A storm command UUID is required.') from exc
        with self.manual_world(row) as world:
            with world.read_db() as db:
                meta = world.metadata(db)
            # The HTTP boundary already verified principal ownership and current grants.
            # Local actor/identity fields are trusted adapter inputs, never browser authority.
            payload = {**value, 'commandId': command_id, 'schemaVersion': storms.VERSION,
                       'environmentId': meta['environment'], 'worldFingerprint': meta['fingerprint'],
                       'actorId': 'world-admin'}
            return storms.command(world, payload)

    def sentiment_command(self, row, value):
        common = {'commandId', 'expectedRevision', 'effectiveDate', 'action', 'reason', 'causalReference'}
        extra = {'schedule': {'eventDate', 'trustChange', 'headline'}, 'cancel': {'newsId'}}.get(value.get('action')) if isinstance(value.get('action'), str) else None
        if extra is None or set(value) != common | extra:
            raise ValueError('Provide only supported sentiment news schedule or cancellation fields.')
        try:
            identity = str(uuid.UUID(value['commandId']))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('A sentiment command UUID is required.') from exc
        with self.manual_world(row) as world:
            with world.read_db() as db:
                meta = world.metadata(db)
            return sentiment.command(world, {**value, 'commandId': identity, 'schemaVersion': sentiment.VERSION,
                'environmentId': meta['environment'], 'worldFingerprint': meta['fingerprint'], 'actorId': 'world-admin'})
