"""HTTP boundary for fixed machine ports and the approved controller registry."""
import hashlib
import http.client
import json
import ssl
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from utilsim.world.store import canonical

from .machine import MAX_RESPONSE
from .managed_field import (
    AUTHORITY_FIELDS,
    AUTHORITY_PATH,
    CALENDAR_FIELDS,
    CALENDAR_PATH,
    ManagedFieldBridge,
    field_assignment,
    field_status,
)


class ControllerCommandRejected(Exception):
    def __init__(self, code, identity):
        self.code, self.identity = code, identity


class ControllerProxy:
    """One operator-configured origin, no browser URLs, proxies or redirects."""
    def __init__(self, url, token, allow_http=False):
        self.url, self.token = None, token
        if url is None:
            if token:
                raise ValueError('Controller token requires an approved origin.')
            return
        parsed = urlsplit(url)
        if (parsed.scheme not in ('https', 'http') or parsed.scheme == 'http' and not allow_http
                or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment or not isinstance(token, str) or len(token) < 32
                or '\r' in token or '\n' in token):
            raise ValueError('Configure a fixed TLS controller origin and a separate service token.')
        self.url = parsed

    def call(self, connection, path, value=None, deadline=None):
        if self.url is None:
            raise HTTPException(503, 'Authoritative connected controller is not configured.')
        deadline = deadline if deadline is not None else time.monotonic() + 15
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(503, 'Connected controller request deadline exceeded.')
        cls = http.client.HTTPSConnection if self.url.scheme == 'https' else http.client.HTTPConnection
        kwargs = {'context': ssl.create_default_context()} if self.url.scheme == 'https' else {}
        client = cls(self.url.hostname, self.url.port, timeout=remaining, **kwargs)
        try:
            headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json',
                       'X-UtilitySim-Run-Id': connection['environment'],
                       'X-UtilitySim-Controller-Id': connection['controller']}
            client.request('POST' if value is not None else 'GET', path,
                           canonical(value).encode() if value is not None else None, headers)
            socket = client.sock
            socket.settimeout(max(.01, deadline - time.monotonic()))
            response = client.getresponse()
            if response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise ValueError('Controller must return JSON.')
            raw = bytearray()
            while not response.isclosed():
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                socket.settimeout(max(.01, deadline - time.monotonic()))
                chunk = response.read1(min(65536, 3_000_001 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > 3_000_000:
                    raise ValueError('Controller response exceeded its bound.')
            result = json.loads(raw)
            if response.status not in (200, 202):
                if (response.status in (400, 409, 422) and path == '/connected/commands' and value is not None
                        and isinstance(result, dict) and result.get('commandRejected') is True
                        and result.get('commandId') == value['commandId']
                        and result.get('runId') == connection['environment']
                        and result.get('controllerId') == connection['controller']
                        and result.get('requestSha256') == hashlib.sha256(canonical(value).encode()).hexdigest()):
                    raise ControllerCommandRejected(response.status, value['commandId'])
                raise HTTPException(response.status if response.status in (400, 409, 422) else 503,
                                    'Connected controller rejected or could not complete the request.')
            if (not isinstance(result, dict) or result.get('runId') != connection['environment']
                    or result.get('controllerId') != connection['controller']):
                raise ValueError('Controller identity mismatch.')
            allowed = {'schemaVersion', 'runId', 'controllerId', 'physicalThrough', 'clock', 'phase',
                       'revision', 'target', 'activeCommandId', 'technicalError', 'errorJobId', 'counts',
                       'supportedActions', 'lastCommand', 'commandId', 'status', 'action', 'through', 'billingAfter'}
            if path == AUTHORITY_PATH:
                allowed = AUTHORITY_FIELDS
            elif path == CALENDAR_PATH:
                allowed = CALENDAR_FIELDS
            if set(result) - allowed:
                raise ValueError('Unexpected controller response fields.')
            return result
        except HTTPException:
            raise
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise HTTPException(503, 'Authoritative controller response unavailable or invalid.') from exc
        finally:
            client.close()


def install(app, port, owned, body, controller_url=None, controller_token=None, controller_allow_http=False):
    proxy = ControllerProxy(controller_url, controller_token, controller_allow_http)

    @app.exception_handler(ControllerCommandRejected)
    async def command_rejected(request, exc):
        return JSONResponse({'detail': 'The authoritative controller confirmed this command was not accepted.',
                             'commandId': exc.identity, 'commandRejected': True}, status_code=exc.code)

    @app.get('/hosted/health')
    def health(request: Request):
        with port.library.library.db() as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ready', 'machineConfigured': port.key is not None}

    @app.post('/hosted/worlds/{identity}/connection')
    def connect(identity: str, request: Request, value: dict = Depends(body)):
        return port.connect(owned(identity, request, 'create'), value)

    @app.get('/hosted/worlds/{identity}/connection')
    def connection_status(identity: str, request: Request):
        owned(identity, request)
        return port.marker(identity)

    @app.post('/hosted/worlds/{identity}/connection/revoke')
    def revoke(identity: str, request: Request, value: dict = Depends(body)):
        owner = owned(identity, request, 'create')
        return port.revoke(owner['id'], value)

    @app.get('/hosted/worlds/{identity}/connected')
    def connected_status(identity: str, request: Request):
        owned(identity, request)
        connection = port.connection(identity)
        if not connection or not connection['active']:
            raise HTTPException(503, 'No active fixed-world controller connection.')
        return proxy.call(connection, '/connected')

    @app.post('/hosted/worlds/{identity}/connected/commands')
    def connected_command(identity: str, request: Request, value: dict = Depends(body)):
        owned(identity, request, 'advance')
        fields = {'commandId', 'expectedRevision', 'action'}
        if value.get('action') == 'advance':
            fields.add('through')
        if (set(value) != fields or value.get('action') not in ('advance', 'pause', 'resume')
                or type(value.get('expectedRevision')) is not int or value['expectedRevision'] < 0):
            raise ValueError('Use an immutable command UUID, revision and supported connected action.')
        if str(uuid.UUID(value['commandId'])) != value['commandId']:
            raise ValueError('Use a canonical command UUID.')
        if 'through' in value:
            target = value['through']
            if not isinstance(target, str):
                raise ValueError('Use a normalized UTC target instant.')
            parsed = datetime.fromisoformat(target.replace('Z', '+00:00'))
            if (parsed.tzinfo is None or parsed.microsecond
                    or parsed.astimezone(UTC).isoformat().replace('+00:00', 'Z') != target):
                raise ValueError('Use a normalized UTC target instant.')
        connection = port.connection(identity)
        if not connection or not connection['active']:
            raise HTTPException(503, 'No active fixed-world controller connection.')
        # Verify the pinned remote identity before a control mutation, and supply
        # the same binding as headers on the mutation itself.
        deadline = time.monotonic() + 15
        proxy.call(connection, '/connected', deadline=deadline)
        result = proxy.call(connection, '/connected/commands', value, deadline=deadline)
        if result.get('commandId') != value['commandId']:
            raise HTTPException(503, 'Controller did not identify the retained command.')
        return result

    @app.get('/machine/worlds/{identity}/status')
    def machine_status(identity: str, request: Request):
        return port.status(request.state.connection)

    @app.post('/machine/worlds/{identity}/field-managed/{action}')
    def managed_field(identity: str, action: str, request: Request, value: dict = Depends(body)):
        return ManagedFieldBridge(port, request.state.connection, proxy).command(action, value)

    @app.get('/machine/worlds/{identity}/field-managed/status')
    def managed_field_status(identity: str, request: Request):
        return field_status(port, request.state.connection)

    @app.get('/machine/worlds/{identity}/field-managed/assignment')
    def managed_field_assignment(identity: str, request: Request, assignmentId: str):
        return field_assignment(port, request.state.connection, assignmentId)

    @app.post('/machine/worlds/{identity}/advance')
    def machine_advance(identity: str, request: Request, value: dict = Depends(body)):
        return port.advance(request.state.connection, value)

    @app.get('/machine/worlds/{identity}/feeds/{kind}')
    def feed(identity: str, kind: str, request: Request, after: str | None = None,
             limit: int = Query(25, ge=1, le=50)):
        result = port.feed(request.state.connection, kind, after, limit)
        if len(canonical(result).encode()) > MAX_RESPONSE:
            raise HTTPException(413, 'Machine response exceeds 9 MiB.')
        return result

    @app.post('/machine/worlds/{identity}/receipts/{kind}')
    def receipt(identity: str, kind: str, request: Request, value: dict = Depends(body)):
        return port.acknowledge(request.state.connection, kind, value)

    @app.get('/machine/worlds/{identity}/payments/{intent}')
    def payment(identity: str, intent: str, request: Request):
        return port.payment(request.state.connection, intent)

    @app.get('/machine/worlds/{identity}/cohorts')
    def cohorts(identity: str, request: Request, after: str = '', limit: int = Query(25, ge=1, le=50)):
        return port.cohorts(request.state.connection, after, limit)

    @app.post('/machine/worlds/{identity}/returns/{kind}')
    def receive(identity: str, kind: str, request: Request, value: dict = Depends(body)):
        return port.receive(request.state.connection, kind, value)
