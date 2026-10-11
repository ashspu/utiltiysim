"""Typed commercial transport for the authenticated selected-world gateway.

Billing owns account mapping, clock/lease checks and atomic command receipts.
This boundary supplies trusted identity and never infers business completion.
"""
import json
import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from utilsim.world.store import canonical

from .machine_routes import ControllerProxy

REQUEST_VERSION = 'connected-operator-request/1'
RESPONSE_VERSION = 'connected-operator-response/1'
PATH = '/connected/operator'
ACTIONS = {'premise': set(), 'job': {'jobId'},
           'release-read': {'commandId', 'exceptionId', 'note'},
           'bill': {'commandId', 'cycleId', 'contractId'},
           'invoice': {'commandId', 'cycleId', 'accountId'},
           'retry-job': {'commandId', 'jobId'}}
READ_ACTIONS = {'premise', 'job'}
COLLECTIONS = {'accounts', 'premises', 'contracts', 'installations', 'reads',
               'bills', 'invoices', 'exceptions', 'cycles', 'receivables'}
JOB_FIELDS = {'id', 'instance_id', 'type', 'cycle_id', 'parameters', 'parent_job_id', 'status', 'stage',
              'requested_at', 'started_at', 'completed_at', 'updated_at', 'worker_id', 'total', 'processed',
              'succeeded', 'skipped', 'exceptions', 'failed', 'error', 'elapsed_seconds', 'items', 'children'}
ENVELOPE = {'schemaVersion', 'runId', 'controllerId', 'premiseId', 'action'}
MAX_REQUEST = 4096
MAX_RESPONSE = 2_000_000


def text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 200


def validate(value):
    action = value.get('action')
    if (not isinstance(action, str) or action not in ACTIONS
            or set(value) != {'action', 'premiseId'} | ACTIONS[action]
            or any(not text(item) for item in value.values())):
        raise ValueError('Use exact supported operator action fields and nonblank strings up to 200 characters.')
    if action not in READ_ACTIONS:
        try:
            valid = str(uuid.UUID(value['commandId'])) == value['commandId']
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('Use a canonical operator command UUID.')
    return action


def projection(status, result, connection, value):
    if (not isinstance(result, dict) or result.get('schemaVersion') != RESPONSE_VERSION
            or result.get('runId') != connection['environment']
            or result.get('controllerId') != connection['controller']
            or result.get('premiseId') != value['premiseId'] or result.get('action') != value['action']):
        raise ValueError('Operator response scope mismatch.')
    if status in (400, 403, 404, 409, 413, 422, 503):
        if set(result) != ENVELOPE | {'error'} or not text(result['error']):
            raise ValueError('Invalid operator refusal.')
        return JSONResponse(result, status_code=status)
    action = value['action']
    expected = 202 if action in ('bill', 'invoice', 'retry-job') else 200
    if (status != expected or set(result) != ENVELOPE | {'commandId', 'result'}
            or result['commandId'] != value.get('commandId') or not isinstance(result['result'], dict)):
        raise ValueError('Invalid operator receipt.')
    record = result['result']
    if action == 'premise':
        if set(record) != COLLECTIONS | {'physicalPremiseId'} or record['physicalPremiseId'] != value['premiseId']:
            raise ValueError('Unexpected operator premise projection.')
        for key in COLLECTIONS:
            if (not isinstance(record[key], list) or len(record[key]) > 200
                    or any(not isinstance(row, dict) for row in record[key])):
                raise ValueError('Unbounded operator collection.')
    elif action == 'release-read':
        if (set(record) - {'status', 'replayed'} or record.get('status') != 'resolved'
                or 'replayed' in record and type(record['replayed']) is not bool):
            raise ValueError('Invalid reading release result.')
    else:
        if (set(record) - JOB_FIELDS or not text(record.get('id'))
                or record.get('instance_id') != connection['environment']
                or record.get('type') not in ('billing', 'invoicing')
                or record.get('status') not in ('queued', 'running', 'completed', 'completed_with_exceptions',
                                              'failed', 'interrupted')):
            raise ValueError('A scoped commercial job is required.')
        if action == 'job' and record['id'] != value['jobId']:
            raise ValueError('Operator returned a different job.')
        if action in ('bill', 'invoice') and (record.get('cycle_id') != value['cycleId']
                or record['type'] != {'bill': 'billing', 'invoice': 'invoicing'}[action]):
            raise ValueError('Operator returned a different cycle.')
        if status == 202 and record.get('status') != 'queued':
            raise ValueError('Expected the original queued-job receipt.')
    return JSONResponse(result, status_code=status)


def install(app, port, owned, body, permits, controller_url, token, allow_http):
    proxy = ControllerProxy(controller_url if token else None, token, allow_http)

    @app.post('/hosted/worlds/{identity}/operator')
    def operator(identity: str, request: Request, value: dict = Depends(body)):
        action = validate(value)
        row = owned(identity, request, 'billing.view' if action in READ_ACTIONS else 'billing.run')
        town = json.loads(row['manifest'])['grantTownId']
        capabilities = [capability for capability in ('billing.view', 'billing.run')
                        if permits(request.state.grants, capability, town)]
        if 'billing.view' not in capabilities:
            raise HTTPException(403, 'World grant does not permit billing view.')
        if not any(binding.get('premiseId') == value['premiseId'] for binding in json.loads(row['bindings'])):
            raise HTTPException(404, 'Physical premise is not in this world.')
        connection = port.connection(identity)
        if not connection or not connection['active']:
            raise HTTPException(503, 'No active fixed-world controller connection.')
        actor = {'subject': request.state.principal, 'capabilities': capabilities}
        if not text(actor['subject']):
            raise HTTPException(401, 'Verified gateway identity required.')
        command = {'schemaVersion': REQUEST_VERSION, 'actor': actor, **value}
        if len(canonical(command).encode()) > MAX_REQUEST:
            raise HTTPException(413, 'Operator request exceeds 4 KiB.')
        return proxy.call(connection, PATH, command, max_response=MAX_RESPONSE,
                          project=lambda status, result: projection(status, result, connection, value))
