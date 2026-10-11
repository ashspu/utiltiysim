"""Fixed authenticated live Run callbacks for the existing physical field broker."""
import json
from pathlib import Path

from utilsim.world import field_execution, field_managed

from .machine import text

AUTHORITY_PATH = '/connected/field-authority'
CALENDAR_PATH = '/connected/field-calendar'
AUTHORITY_FIELDS = {'schemaVersion', 'runId', 'controllerId', 'worldFingerprint', 'fieldOwnerId',
                    'runtimePath', 'actorId', 'clock', 'runStatus', 'leaseActive', 'leaseHeld', 'crewResources',
                    'job', 'dependencies', 'reservation'}
CALENDAR_FIELDS = {'schemaVersion', 'runId', 'controllerId', 'instant'}


def field_status(port, connection):
    owner = port.field_existing(port.world(connection), connection['world'])
    with owner.db() as db:
        meta = owner.metadata(db)
        return {'schemaVersion': 'connected-field-status/1', 'fieldOwnerId': owner.owner_id,
                'environmentId': meta['environment'], 'fingerprint': meta['fingerprint'],
                'enabled': field_managed.enabled(db)}


def field_assignment(port, connection, assignment_id):
    owner = port.field_existing(port.world(connection), connection['world'])
    with owner.db() as db:
        if not field_execution.enabled(db):
            raise KeyError('Unknown accepted field assignment.')
        row = db.execute('SELECT payload,checksum FROM field_assignments WHERE id=?',
                         (text(assignment_id),)).fetchone()
    if row is None:
        raise KeyError('Unknown accepted field assignment.')
    assignment = json.loads(row['payload'])
    if field_execution.checksum(assignment) != row['checksum']:
        raise ValueError('Stored field assignment checksum mismatch.')
    return {'assignment': assignment, 'checksum': row['checksum']}


class ManagedFieldBridge:
    """The composition root supplies the proxy; callers supply identifiers only."""
    def __init__(self, port, connection, proxy):
        self.connection, self.proxy = connection, proxy
        self.owner = port.field_existing(port.world(connection), connection['world'])
        self.binding = None
        state = self.authority()
        self.binding = {key: state[key] for key in ('runtimePath', 'actorId', 'crewResources')}
        self.broker = field_managed.ManagedField(self.owner, state['runtimePath'], self.authority, self.calendar)
        with self.owner.db() as db:
            if field_managed.enabled(db):
                saved = db.execute('SELECT plan FROM field_managed ORDER BY assignment LIMIT 1').fetchone()
                if saved:
                    plan = json.loads(saved[0])
                    if (plan['runtimePath'] != self.broker.runtime_path or plan['actorId'] != state['actorId']
                            or plan['runId'] != state['runId']):
                        raise ValueError('Persisted field authority differs from the fixed runtime owner.')

    def authority(self, job=None, reservation=None):
        body = {key: text(value) for key, value in (('jobId', job), ('reservationId', reservation)) if value is not None}
        state = self.proxy.call(self.connection, AUTHORITY_PATH, body)
        if (state.get('schemaVersion') != 'connected-field-authority/1'
                or state.get('runId') != self.connection['environment']
                or state.get('controllerId') != self.connection['controller']
                or state.get('worldFingerprint') != self.connection['fingerprint']
                or state.get('fieldOwnerId') != self.owner.owner_id
                or type(state.get('leaseActive')) is not bool or type(state.get('leaseHeld')) is not bool
                or state['leaseActive'] and not state['leaseHeld']):
            raise ValueError('Live managed field authority does not match the fixed world and owner.')
        path = state.get('runtimePath')
        if not isinstance(path, str) or not path or len(path) > 4096 or not Path(path).is_absolute():
            raise ValueError('Use the actual compatible absolute runtime store path.')
        text(state.get('actorId'))
        text(state.get('runStatus'))
        field_managed._instant(state.get('clock'))
        resources = state.get('crewResources')
        if (not isinstance(resources, dict) or not resources or len(resources) > 10000
                or any(not isinstance(value, str) or not value.strip() or len(value) > 512
                       for pair in resources.items() for value in pair)
                or len(set(resources.values())) != len(resources)):
            raise ValueError('Use the pinned distinct crew-resource mappings.')
        if self.binding is not None and any(state.get(key) != value for key, value in self.binding.items()):
            raise ValueError('Live field authority changed during the operation.')
        if job is not None:
            actual = state.get('job')
            if (not isinstance(actual, dict) or actual.get('id') != job
                    or actual.get('actor') != state['actorId']
                    or not isinstance(state.get('dependencies'), list)
                    or actual.get('status') == 'delivering' and not state['leaseActive']):
                raise ValueError('Live executor job and active delivery lease are required.')
        if reservation is not None:
            booking = state.get('reservation')
            if (not isinstance(booking, dict) or booking.get('id') != reservation
                    or booking.get('actor') != state['actorId']
                    or booking.get('resource') not in resources.values()
                    or job is not None and booking.get('job') != job):
                raise ValueError('Live executor reservation must match the selected job and crew.')
        return state

    def calendar(self, day, clock, zone, fold):
        result = self.proxy.call(self.connection, CALENDAR_PATH,
                                 {'day': day, 'time': clock, 'timeZone': zone, 'fold': fold})
        if (result.get('schemaVersion') != 'connected-field-calendar/1'
                or result.get('runId') != self.connection['environment']
                or result.get('controllerId') != self.connection['controller']):
            raise ValueError('Calendar response does not match the fixed runtime.')
        field_managed._instant(result.get('instant'))
        return result['instant']

    def command(self, action, value):
        keys = {'plan': {'quote', 'schedule'}, 'bind': {'assignmentId', 'jobId', 'reservationId'},
                'execute': {'jobId', 'reservationId'}, 'cancel': {'assignmentId'}}
        if action not in keys or not isinstance(value, dict) or set(value) != keys[action]:
            raise ValueError('Use exact managed field inputs; authority comes from the fixed runtime.')
        if action in ('plan', 'bind'):
            state = self.authority()
            if state['runStatus'] != 'paused' or state['leaseHeld']:
                raise ValueError('Pause the Run and release its actual delivery lease before planning or binding.')
        if action == 'plan':
            quote, schedule = value['quote'], value['schedule']
            if not isinstance(quote, dict) or not isinstance(schedule, dict):
                raise ValueError('Provide existing field quote and schedule objects.')
            with self.owner.db() as db:
                if not field_execution.enabled(db):
                    raise KeyError('Unknown accepted field assignment.')
                assignment = db.execute('SELECT crew FROM field_assignments WHERE id=?',
                                        (text(quote.get('assignmentId')),)).fetchone()
            if (assignment is None
                    or self.binding['crewResources'].get(assignment['crew']) != schedule.get('resourceId')):
                raise ValueError('Plan using the actual assignment crew and its pinned resource.')
            return self.broker.plan(quote, schedule)
        if action == 'bind':
            return self.broker.bind(text(value['assignmentId']), text(value['jobId']), text(value['reservationId']))
        if action == 'cancel':
            return self.broker.cancel(text(value['assignmentId']))
        state = self.authority(text(value['jobId']), text(value['reservationId']))
        job = state['job']
        envelope = {key: job.get(key) for key in ('id', 'actor', 'target', 'operation', 'payload')}
        return self.broker({**envelope, 'runId': state['runId'], 'processingAt': state['clock']})
