"""Fixed-world machine capability and durable connected-clock producer port.

This port exposes committed evidence, never administrator views or arbitrary
world paths. Browser identity and machine authority have different credentials.
"""
import hashlib
import hmac
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from utilsim.world import contacts, cruise, customer_finance, customer_notices, delivery, field_execution
from utilsim.world.store import canonical, stable

from .library import ManagedWorld

MAX_RESPONSE = 9 * 1024 * 1024
FEEDS = {'observations', 'contacts', 'payments', 'financial-contacts', 'field'}


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError('Use nonempty text of at most 512 characters.')
    return value


class ExistingFieldExecution(field_execution.FieldExecution):
    """Open the registered sidecar without creating a missing/empty owner."""
    def __init__(self, world, path, owner_id):
        self.world, self.path, self.owner_id = world, str(path), owner_id
        with world.read_db() as db:
            meta = field_execution._world_identity(db)
        binding = {**{key: meta[key] for key in ('environment', 'fingerprint')}, 'owner': owner_id}
        with self.db() as db:
            if not field_execution._owned_store(db, binding):
                raise ValueError('Registered field owner is empty; restore the original sidecar.')

    @contextmanager
    def db(self):
        db = sqlite3.connect(Path(self.path).resolve().as_uri() + '?mode=rw', uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


class MachinePort:
    def __init__(self, library, key=None, controller_id='utilitysim-controller'):
        if key is not None and (not isinstance(key, str) or len(key) < 32):
            raise ValueError('Configure a separate machine key of at least 32 characters.')
        self.library, self.key, self.controller_id = library, key, text(controller_id)
        with library.library.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS hosted_connections('
                       'world TEXT PRIMARY KEY,capability TEXT UNIQUE NOT NULL,controller TEXT NOT NULL,'
                       'environment TEXT NOT NULL,fingerprint TEXT NOT NULL,revision INTEGER NOT NULL,'
                       'active INTEGER NOT NULL,command TEXT NOT NULL,request TEXT NOT NULL,token_hash TEXT NOT NULL)')

    def connection(self, identity):
        with self.library.library.db() as db:
            return db.execute('SELECT * FROM hosted_connections WHERE world=?', (identity,)).fetchone()

    def marker(self, identity):
        row = self.connection(identity)
        return {'configured': row is not None, 'active': bool(row and row['active']),
                'controllerId': row['controller'] if row else None, 'runId': row['environment'] if row else None,
                'revision': row['revision'] if row else 0, 'manualAdvanceAllowed': row is None}

    def token(self, capability):
        secret = hmac.new(self.key.encode(), ('utilitysim-machine/1:' + capability).encode(), hashlib.sha256).hexdigest()
        return 'msc_' + capability + '.' + secret

    def connect(self, owner, value):
        if self.key is None:
            raise ValueError('Machine connectivity is not configured on this runtime.')
        fields = {'commandId', 'expectedRevision', 'controllerId', 'sewerReturnFactor', 'delaySeconds'}
        if set(value) != fields or value['controllerId'] != self.controller_id:
            raise ValueError('Use the approved fixed controller and exact connection fields.')
        command = str(uuid.UUID(text(value['commandId'])))
        if command != value['commandId'] or type(value['expectedRevision']) is not int or value['expectedRevision'] < 0:
            raise ValueError('Use a canonical command UUID and nonnegative revision.')
        factor, delay = delivery.delivery_settings(value['sewerReturnFactor'], value['delaySeconds'])
        if self.library.initialization(owner['id'])['state'] != 'complete':
            raise ValueError('Complete physical initialization before connecting.')
        world = ManagedWorld(self.library.library.world(owner['id']))
        encoded = canonical(value)
        with cruise.synchronized_action(world):
            with world.read_db() as db:
                meta = world.metadata(db)
            pinned = delivery.status(world, limit=1)['configuration']
            if pinned and (pinned['sewerReturnFactor'], pinned['delaySeconds']) != (factor, delay):
                raise ValueError('Observation delivery settings are pinned; use a separate world.')
            with self.library.library.db() as db:
                old = db.execute('SELECT * FROM hosted_connections WHERE world=?', (owner['id'],)).fetchone()
                if old and old['command'] == command:
                    if old['request'] != encoded:
                        raise ValueError('Conflicting connection command retry.')
                    capability = old['capability']
                    if hashlib.sha256(self.token(capability).encode()).hexdigest() != old['token_hash']:
                        raise ValueError('Machine key changed; rotate the connection with a new command.')
                else:
                    revision = old['revision'] if old else 0
                    if revision != value['expectedRevision']:
                        raise ValueError('Connection revision changed.')
                    if old and (old['controller'], old['environment'], old['fingerprint']) != (
                            self.controller_id, meta['environment'], meta['fingerprint']):
                        raise ValueError('Connection identity is pinned; use a separate world.')
                    capability = uuid.uuid4().hex
                    digest = hashlib.sha256(self.token(capability).encode()).hexdigest()
                    db.execute('INSERT OR REPLACE INTO hosted_connections VALUES(?,?,?,?,?,?,0,?,?,?)',
                               (owner['id'], capability, self.controller_id, meta['environment'], meta['fingerprint'],
                                revision + 1, command, encoded, digest))
            # The catalog intent first prevents a manual-clock takeover after a crash.
            delivery.configure(world, meta['environment'], factor, delay)
            with world.db() as db:
                db.execute('CREATE TABLE IF NOT EXISTS machine_days('
                           'id TEXT PRIMARY KEY,through TEXT UNIQUE NOT NULL,request TEXT NOT NULL,result TEXT)')
            fresh_intent = (old is None or not old['active'] and old['revision'] == 1
                            and json.loads(old['request']).get('expectedRevision') == 0)
            if 'machineFieldOwnerId' not in meta and fresh_intent:
                field = self.field(world, owner['id'])
            else:
                field = self.field_existing(world, owner['id'])
            with world.db() as db:
                world.put(db, 'machineFieldOwnerId', field.owner_id)
            with self.library.library.db() as db:
                db.execute('UPDATE hosted_connections SET active=1 WHERE world=?', (owner['id'],))
        return {**self.marker(owner['id']), 'worldInstanceId': owner['id'], 'environmentId': meta['environment'],
                'fingerprint': meta['fingerprint'], 'token': self.token(capability)}

    def revoke(self, identity, value):
        if set(value) != {'commandId', 'expectedRevision'}:
            raise ValueError('Provide a command UUID and expected connection revision.')
        command = str(uuid.UUID(text(value['commandId'])))
        if command != value['commandId'] or type(value['expectedRevision']) is not int or value['expectedRevision'] < 0:
            raise ValueError('Use a canonical UUID and nonnegative revision.')
        world = ManagedWorld(self.library.library.world(identity))
        with cruise.synchronized_action(world), self.library.library.db() as db:
            old = db.execute('SELECT * FROM hosted_connections WHERE world=?', (identity,)).fetchone()
            if not old:
                raise KeyError('No connection configured.')
            encoded = canonical(value)
            if old['command'] == command:
                if old['request'] != encoded:
                    raise ValueError('Conflicting revocation retry.')
            else:
                if old['revision'] != value['expectedRevision']:
                    raise ValueError('Connection revision changed.')
                db.execute('UPDATE hosted_connections SET active=0,revision=revision+1,command=?,request=? WHERE world=?',
                           (command, encoded, identity))
        return self.marker(identity)

    def authenticate(self, identity, supplied):
        if self.key is None or not isinstance(supplied, str) or len(supplied) > 200:
            raise PermissionError('Fixed-world machine capability required.')
        match = re.fullmatch(r'Bearer msc_([a-f0-9]{32})\.([a-f0-9]{64})', supplied)
        row = self.connection(identity)
        if (not match or not row or not row['active'] or row['capability'] != match[1]
                or not hmac.compare_digest(hashlib.sha256(supplied[7:].encode()).hexdigest(), row['token_hash'])
                or not hmac.compare_digest(supplied[7:], self.token(row['capability']))):
            raise PermissionError('Fixed-world machine capability required.')
        world = ManagedWorld(self.library.library.world(identity))
        with world.read_db() as db:
            meta = world.metadata(db)
        if meta['environment'] != row['environment'] or meta['fingerprint'] != row['fingerprint']:
            raise PermissionError('Machine world identity changed.')
        return row

    def world(self, connection):
        return ManagedWorld(self.library.library.world(connection['world']))

    def field(self, world, identity):
        return field_execution.FieldExecution(world, self.library.root / 'worlds' / identity / 'machine-field.sqlite',
                                              owner_id='connected-' + identity)

    def field_existing(self, world, identity):
        return ExistingFieldExecution(world, self.library.root / 'worlds' / identity / 'machine-field.sqlite',
                                      owner_id='connected-' + identity)

    def status(self, connection):
        world = self.world(connection)
        with world.read_db() as db:
            meta = world.metadata(db)
        state = delivery.status(world, limit=1)
        return {'worldInstanceId': connection['world'], 'environmentId': meta['environment'],
                'runId': meta['environment'], 'fingerprint': meta['fingerprint'], 'through': meta['through'],
                'controllerId': connection['controller'], 'revision': connection['revision'],
                'delivery': {k: state[k] for k in ('configuration', 'pending', 'accepted')}}

    def advance(self, connection, value):
        if set(value) != {'commandId', 'through', 'processingAt'}:
            raise ValueError('Provide only commandId, through and processingAt.')
        text(value['commandId'])
        text(value['through'])
        text(value['processingAt'])
        finish = date.fromisoformat(value['through'])
        if finish.isoformat() != value['through']:
            raise ValueError('Use a canonical through date.')
        processed = datetime.fromisoformat(value['processingAt'].replace('Z', '+00:00'))
        if (processed.tzinfo is None or processed.astimezone(UTC).isoformat().replace('+00:00', 'Z') != value['processingAt']
                or processed < datetime.combine(finish, datetime.min.time(), UTC)):
            raise ValueError('Controller processing time must reach the physical boundary in canonical UTC.')
        day = (finish - timedelta(days=1)).isoformat()
        identity = canonical({'commandId': value['commandId'], 'through': value['through'],
                              'controllerId': connection['controller'], 'runId': connection['environment']})
        world = self.world(connection)
        with cruise.synchronized_action(world):
            with world.db() as db:
                prior = db.execute('SELECT * FROM machine_days WHERE id=?', (value['commandId'],)).fetchone()
                if prior:
                    if prior['request'] != identity:
                        raise ValueError('Conflicting physical-day retry.')
                    if prior['result'] is not None:
                        return json.loads(prior['result'])
                else:
                    meta = world.metadata(db)
                    if meta['through'] != day:
                        raise ValueError('Advance exactly the next physical day, in order.')
                    if db.execute("SELECT 1 FROM observation_outbox WHERE state='pending' LIMIT 1").fetchone():
                        raise ValueError('Previous physical observations still await durable acceptance.')
                    if db.execute('SELECT 1 FROM machine_days WHERE result IS NULL').fetchone():
                        raise ValueError('Retry the incomplete physical-day command first.')
                    db.execute('INSERT INTO machine_days VALUES(?,?,?,NULL)', (value['commandId'], value['through'], identity))
            with world.read_db() as db:
                through = world.metadata(db)['through']
            if through == day:
                field_execution.run_due(self.field_existing(world, connection['world']))
                world.advance(value['through'])
            with world.db() as db:
                message = db.execute('SELECT id FROM observation_outbox WHERE day=?', (day,)).fetchone()
                if not message or world.metadata(db)['through'] != value['through']:
                    raise ValueError('Physical-day journal requires recovery; no replacement was created.')
                result = {'commandId': value['commandId'], 'through': value['through'],
                          'environmentId': connection['environment'], 'observationCommandId': message['id']}
                db.execute('UPDATE machine_days SET result=? WHERE id=?', (canonical(result), value['commandId']))
                return result

    def feed(self, connection, kind, after=None, limit=25):
        if kind not in FEEDS or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('Use a known feed and limit between 1 and 50.')
        world = self.world(connection)
        resume_cursor = int(after or 0) if kind in ('observations', 'payments') else after
        if kind == 'observations':
            cursor = int(after or 0)
            customer_finance._page(cursor, limit)
            with world.read_db() as db:
                rows = db.execute('SELECT * FROM observation_outbox WHERE sequence>? ORDER BY sequence LIMIT ?',
                                  (cursor, limit + 1)).fetchall()
            items = []
            for row in rows[:limit]:
                envelope = json.loads(row['envelope'])
                if stable(envelope) != row['fingerprint']:
                    raise ValueError('Stored observation checksum mismatch.')
                items.append({'cursor': row['sequence'], 'envelope': envelope, 'fingerprint': row['fingerprint']})
            page = {'items': items, 'nextAfter': items[-1]['cursor'] if len(rows) > limit else None}
        elif kind == 'field':
            field = self.field_existing(world, connection['world'])
            page = field_execution.ready(field, after, limit)
            allowed = []
            with field.db() as db:
                for item in page['items']:
                    row = db.execute('SELECT * FROM field_outbox WHERE id=?', (item['envelope']['id'],)).fetchone()
                    if db.execute("SELECT 1 FROM field_outbox WHERE assignment=? AND sequence<? AND state!='received'",
                                  (row['assignment'], row['sequence'])).fetchone():
                        page['nextAfter'] = allowed[-1]['cursor'] if allowed else after
                        break
                    allowed.append(item)
            page['items'] = allowed
        else:
            module = {'contacts': contacts, 'payments': customer_finance, 'financial-contacts': customer_notices}[kind]
            page = module.ready(world, int(after or 0) if kind == 'payments' else after, limit)
            for item in page['items']:
                item['fingerprint'] = stable(item['intent'])
        # Preserve whole immutable messages; truncate between messages only.
        size, bounded = 1024, []
        for item in page['items']:
            addition = len(canonical(item).encode()) + 2
            if size + addition > MAX_RESPONSE:
                page['nextAfter'] = bounded[-1]['cursor'] if bounded else resume_cursor
                break
            size += addition
            bounded.append(item)
        if page['items'] and not bounded:
            raise ValueError('One immutable feed item exceeds the machine response bound.')
        return {**page, 'items': bounded, 'lastCursor': bounded[-1]['cursor'] if bounded else resume_cursor,
                'worldInstanceId': connection['world']}

    def acknowledge(self, connection, kind, receipt):
        if kind not in FEEDS:
            raise ValueError('Unknown evidence feed.')
        world = self.world(connection)
        store = self.field_existing(world, connection['world']) if kind == 'field' else world
        table, state, digest = {
            'observations': ('observation_outbox', 'state', 'fingerprint'),
            'contacts': ('contact_outbox', 'state', 'fingerprint'),
            'payments': ('customer_finance_intents', 'delivery_state', 'fingerprint'),
            'financial-contacts': ('customer_notice_outbox', 'state', 'fingerprint'),
            'field': ('field_outbox', 'state', 'checksum')}[kind]
        text(receipt.get('id'))
        with cruise.synchronized_action(world), store.db() as db:
            if not db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (table,)).fetchone():
                raise KeyError('Unknown evidence.')
            row = db.execute(f'SELECT * FROM {table} WHERE id=?', (receipt['id'],)).fetchone()
            if not row:
                raise KeyError('Unknown evidence.')
            message = json.loads(row['envelope'])
            if (field_execution.checksum(message) if kind == 'field' else stable(message)) != row[digest]:
                raise ValueError('Stored evidence checksum mismatch.')
            if kind == 'observations':
                if receipt.get('status') not in ('pending', 'delivering', 'completed', 'failed'):
                    raise ValueError('Matching durable scheduler receipt required.')
            else:
                scope = 'environmentId' if kind in ('contacts', 'field') else 'runId'
                expected = {'id', scope, digest, 'status', 'receiptId'}
                if (set(receipt) != expected or receipt[scope] != connection['environment']
                        or receipt[digest] != row[digest]
                        or receipt['status'] != ('received' if kind == 'field' else 'accepted')):
                    raise ValueError('Matching exact recipient receipt required.')
                text(receipt['receiptId'])
                available = row['available_day'] if kind == 'field' else row['available_at']
                meta = store.metadata(db)
                if available > meta['through'] + ('' if kind == 'field' else 'T00:00:00Z'):
                    raise ValueError('Evidence is not available at the physical clock.')
                if kind == 'field' and db.execute(
                        "SELECT 1 FROM field_outbox WHERE assignment=? AND sequence<? AND state!='received'",
                        (row['assignment'], row['sequence'])).fetchone():
                    raise ValueError('A field report requires its dispatch acknowledgement first.')
            encoded = canonical(receipt)
            if row['receipt'] is not None and row['receipt'] != encoded:
                raise ValueError('Conflicting receipt retry.')
            db.execute(f'UPDATE {table} SET {state}=?,receipt=?,last_error=NULL WHERE id=?',
                       ('received' if kind == 'field' else 'accepted', encoded, receipt['id']))
        return {'id': receipt['id'], 'status': 'recorded'}

    def payment(self, connection, identity):
        world = self.world(connection)
        with world.read_db() as db:
            if not customer_finance.enabled(db):
                raise KeyError('Unknown payment intent.')
            row = db.execute('SELECT envelope,fingerprint,available_at FROM customer_finance_intents WHERE id=?',
                             (identity,)).fetchone()
            if not row or row['available_at'] > world.metadata(db)['through'] + 'T00:00:00Z':
                raise KeyError('Unknown payment intent.')
            intent = json.loads(row['envelope'])
            if stable(intent) != row['fingerprint']:
                raise ValueError('Stored payment checksum mismatch.')
            return {'intent': intent, 'fingerprint': row['fingerprint']}

    def cohorts(self, connection, after='', limit=25):
        if not isinstance(after, str) or len(after) > 512 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('Use a bounded premise cursor and cohort page.')
        world = self.world(connection)
        with world.read_db() as db:
            rows = [] if not customer_finance.enabled(db) else db.execute(
                'SELECT premise,recipient,stamp,policy FROM customer_finance_profiles WHERE premise>? '
                'ORDER BY premise LIMIT ?', (after, limit + 1)).fetchall()
            items = []
            for row in rows[:limit]:
                stamp, occupied = customer_finance._stamp(db, row['premise'])
                policy = json.loads(row['policy'])
                if occupied and stamp == row['stamp'] and policy['active']:
                    items.append({'premiseId': row['premise'], 'recipientRef': row['recipient'],
                                  'runId': connection['environment'], 'customerKind': policy['customerKind']})
            cursor = rows[min(len(rows), limit) - 1]['premise'] if rows else after
            return {'items': items, 'lastCursor': cursor, 'nextAfter': cursor if len(rows) > limit else None,
                    'worldInstanceId': connection['world']}

    def receive(self, connection, kind, value):
        world = self.world(connection)
        if kind == 'field':
            if 'actorId' in value:
                raise ValueError('Field actor authority is supplied by the fixed-world broker.')
            field = self.field_existing(world, connection['world'])
            actor = 'world-admin'
            if value.get('action') == 'execute':
                with field.db() as db:
                    actor = field_execution._assignment(db, value.get('assignmentId'))['crew']
            return field_execution.command(field, {**value, 'actorId': actor})
        if kind not in ('invoices', 'provider'):
            raise ValueError('Unknown return route.')
        with cruise.synchronized_action(world):
            return (customer_finance.receive_delivery if kind == 'invoices' else customer_finance.provider_receipt)(world, value)
