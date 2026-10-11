"""Internal runtime API. Only a trusted identity gateway may connect."""
import hmac
import json
import os
import re
import sqlite3
import uuid
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from utilsim.world import customer_cashflow, customer_finance, storms
from utilsim.world.map_view import WorldMap

from .library import HostedLibrary
from .setup import presentation

ROLES = {'view': {'owner', 'operator', 'billing', 'support', 'analyst'},
         'create': {'owner'}, 'advance': {'owner', 'operator'},
         'billing.view': {'owner', 'operator', 'billing', 'support', 'analyst'},
         'billing.run': {'owner', 'billing'}}


def permits(grants, action, town):
    for grant in grants:
        if not isinstance(grant, dict) or grant.get('revoked'):
            continue
        if grant.get('expiresAt'):
            try:
                expiry = datetime.fromisoformat(grant['expiresAt'].replace('Z', '+00:00'))
                if expiry <= datetime.now(UTC):
                    continue
            except (ValueError, TypeError, AttributeError):
                continue
        if (grant.get('town') in ('*', town) and isinstance(grant.get('role'), str)
                and grant['role'] in ROLES[action]):
            return True
    return False


def create_app(root, token, machine_key=None, controller_id='utilitysim-controller', controller_url=None,
               controller_token=None, controller_allow_http=False, operator_token=None):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError('Configure an internal bearer token of at least 32 characters.')
    if machine_key is not None and machine_key == token:
        raise ValueError('Machine key must be distinct from the browser gateway credential.')
    if controller_token is not None and controller_token in (token, machine_key):
        raise ValueError('Controller service token must be distinct from gateway and machine credentials.')
    if operator_token is not None and (
            not isinstance(operator_token, str) or not 32 <= len(operator_token) <= 4096
            or any(ord(char) < 33 or ord(char) > 126 for char in operator_token)
            or operator_token in (token, machine_key, controller_token)):
        raise ValueError('Configure a distinct bounded printable operator service token.')
    library = HostedLibrary(root)
    from .machine import MachinePort
    from .machine_routes import install

    machine = MachinePort(library, machine_key, controller_id)
    library.machine = machine
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.library = library

    @app.middleware('http')
    async def authenticate(request, call_next):
        supplied = request.headers.get('authorization', '')
        if request.url.path.startswith('/machine/'):
            parts = request.url.path.split('/')
            try:
                if len(parts) < 5 or parts[2] != 'worlds' or not re.fullmatch(r'[a-f0-9]{32}', parts[3]):
                    raise PermissionError()
                request.state.connection = machine.authenticate(parts[3], supplied)
            except (PermissionError, KeyError, ValueError):
                return JSONResponse({'detail': 'Fixed-world machine capability required.'}, status_code=401)
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            return response
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
            return JSONResponse({'detail': 'Internal gateway authentication required.'}, status_code=401)
        if request.url.path == '/hosted/health':
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            return response
        principal = request.headers.get('x-utilitysim-user-id', '')
        try:
            grants = json.loads(request.headers.get('x-utilitysim-grants', '[]'))
            if not isinstance(grants, list) or len(grants) > 100 or not principal or len(principal) > 200:
                raise ValueError()
        except ValueError:
            return JSONResponse({'detail': 'Verified gateway identity required.'}, status_code=401)
        request.state.principal, request.state.grants = principal, grants
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': 'Saved world or record not found.'}, status_code=404)

    @app.exception_handler(OSError)
    @app.exception_handler(sqlite3.Error)
    async def unavailable(request, exc):
        return JSONResponse({'detail': 'Persistent runtime data unavailable; no replacement world was created.'}, status_code=503)

    def owned(identity, request, action='view'):
        row = library.lookup(request.state.principal, identity)
        manifest = json.loads(row['manifest'])
        if not permits(request.state.grants, action, manifest['grantTownId']):
            raise HTTPException(403, 'World grant does not permit this action.')
        return row

    async def body(request: Request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 65536:
                raise HTTPException(413, 'Request exceeds 64 KiB.')
        try:
            value = json.loads(data)
        except ValueError as exc:
            raise HTTPException(422, 'JSON object required.') from exc
        if not isinstance(value, dict):
            raise HTTPException(422, 'JSON object required.')
        return value

    @app.get('/hosted/sources')
    def sources(request: Request):
        return {'sources': [s for s in library.templates() if permits(request.state.grants, 'view', s['grantTownId'])]}

    @app.get('/hosted/sources/{source}/configuration')
    def source_configuration(source: str, request: Request, sourceRevision: str):
        _, manifest = library.template(source, sourceRevision)
        if not permits(request.state.grants, 'view', manifest['grantTownId']):
            raise HTTPException(403, 'Source access refused.')
        return {'sourceId': source, 'sourceRevision': sourceRevision, 'townId': manifest['townId'],
                'grantTownId': manifest['grantTownId'], 'counts': manifest['counts'],
                **presentation(),
                'immutable': ['streets', 'parcels', 'premiseIds', 'serviceIds', 'meterIds'],
                'currentAdapterFixed': ['startingPopulation', 'baseDemandProfiles', 'networkTopology', 'timezone'],
                'excluded': ['billing', 'collections', 'VEE', 'staffing', 'enterpriseWorkQueues', 'studioRun']}

    @app.get('/hosted/worlds')
    def worlds(request: Request, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=50)):
        rows = [r for r in library.listing(request.state.principal)
                if permits(request.state.grants, 'view', json.loads(r['manifest'])['grantTownId'])]
        return {'worlds': [library.describe(r) for r in rows[offset:offset + limit]],
                'total': len(rows), 'offset': offset, 'limit': limit}

    @app.post('/hosted/worlds')
    def create(request: Request, value: dict = Depends(body)):
        # Existing journal metadata authorizes recovery even if the template was removed.
        try:
            command = str(uuid.UUID(value.get('commandId')))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('A creation command UUID is required.') from exc
        rows = library.listing(request.state.principal)
        prior = next((r for r in rows if r['command'] == command), None)
        if prior:
            manifest = json.loads(prior['manifest'])
        else:
            _, manifest = library.template(value.get('sourceId'), value.get('sourceRevision'))
        if not permits(request.state.grants, 'create', manifest['grantTownId']):
            raise HTTPException(403, 'An owner grant is required to create a world.')
        return library.create(request.state.principal, value)

    @app.get('/hosted/worlds/{identity}')
    def status(identity: str, request: Request):
        return library.describe(owned(identity, request))

    @app.get('/hosted/worlds/{identity}/map/snapshot')
    def snapshot(identity: str, request: Request):
        owned(identity, request)
        return WorldMap(library.library.world(identity)).snapshot()

    @app.get('/hosted/worlds/{identity}/map/bindings')
    def bindings(identity: str, request: Request):
        row = owned(identity, request)
        # Bindings retain exact parcel/premise/meter IDs, with the new environment identity.
        fields = ('parcelId', 'premiseId', 'accountId', 'simulationParcelId', 'buildingId', 'meterIds', 'servicePointIds')
        return {'worldInstanceId': identity, 'environmentId': 'instance-' + identity,
                'sourceRevision': json.loads(row['request'])['sourceRevision'],
                'premises': [{key: b[key] for key in fields if key in b} for b in json.loads(row['bindings'])]}

    @app.get('/hosted/worlds/{identity}/premises/{premise}')
    def premise_record(identity: str, premise: str, request: Request):
        owned(identity, request)
        from utilsim.world import physical_profiles

        world = library.library.world(identity)
        return {'worldInstanceId': identity, **WorldMap(world).premise(premise),
                'physicalProfiles': physical_profiles.inspect(world, premise)}

    @app.get('/hosted/worlds/{identity}/premises/{premise}/history')
    def history(identity: str, premise: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(14, ge=1, le=31)):
        owned(identity, request)
        world = library.library.world(identity)
        record = WorldMap(world).premise(premise)
        with world.read_db() as db:
            from utilsim.world import physical_profiles

            rows = [dict(r) for r in db.execute(
                'SELECT o.day,a.id assetId,a.commodity,a.unit,o.id observationId,o.status,o.quantity observedQuantity '
                'FROM assets a JOIN observations o ON o.asset=a.id '
                'WHERE a.premise=? AND o.day IN (SELECT day FROM days ORDER BY day DESC LIMIT ? OFFSET ?) '
                'ORDER BY o.day DESC,a.id', (premise, limit, offset))]
            total = db.execute('SELECT COUNT(*) FROM days').fetchone()[0]
            if rows:
                from datetime import date, timedelta

                periods = physical_profiles.intervals(db, world.metadata(db), min(r['day'] for r in rows),
                    (date.fromisoformat(max(r['day'] for r in rows)) + timedelta(days=1)).isoformat())
                for reading in rows:
                    period = periods.get(reading['observationId'])
                    if period:
                        reading.update(intervalStart=period['start'], intervalEnd=period['end'], technology=period['technology'])
        return {'worldInstanceId': identity, 'environmentId': record['environmentId'], 'townId': record['townId'],
                'premise': record['premise'], 'through': record['through'], 'totalDays': total,
                'offset': offset, 'limit': limit, 'readings': rows}

    @app.get('/hosted/worlds/{identity}/premises/{premise}/customer')
    def customer_state(identity: str, premise: str, request: Request, before: str | None = None,
                       limit: int = Query(25, ge=1, le=50)):
        owned(identity, request)
        world = library.library.world(identity)
        return {'worldInstanceId': identity, 'view': 'administrator-truth',
                'finance': customer_finance.inspect(world, premise),
                'cashflow': customer_cashflow.inspect(world, premise, before=before, limit=limit)}

    @app.get('/hosted/worlds/{identity}/observations')
    def observations(identity: str, request: Request, start: str, end: str):
        from datetime import date
        owned(identity, request)
        if not 0 < (date.fromisoformat(end) - date.fromisoformat(start)).days <= 31:
            raise ValueError('Read one to 31 days per request.')
        return library.library.world(identity).export(start, end)

    @app.get('/hosted/worlds/{identity}/events')
    def events(identity: str, request: Request, before: int | None = Query(None, ge=1, le=9223372036854775807),
               limit: int = Query(25, ge=1, le=50)):
        owned(identity, request)
        world = library.library.world(identity)
        with world.read_db() as db:
            through = world.metadata(db)['through']
            rows = [dict(r) for r in db.execute(
                'SELECT sequence,id,day,type,subject,cause,payload FROM events WHERE sequence<? '
                'ORDER BY sequence DESC LIMIT ?', (before or 9223372036854775807, limit + 1))]
        for row in rows:
            row['payload'] = json.loads(row['payload'])
        return {'worldInstanceId': identity, 'view': 'administrator-truth', 'through': through,
                'events': rows[:limit], 'nextBefore': rows[limit - 1]['sequence'] if len(rows) > limit else None}

    @app.get('/hosted/worlds/{identity}/events/storms')
    def storm_history(identity: str, request: Request, before: str | None = None,
                      eventsBefore: str | None = None, limit: int = Query(25, ge=1, le=50)):
        owned(identity, request)
        return {'worldInstanceId': identity,
                **storms.inspect(library.library.world(identity), before=before, limit=limit, events_before=eventsBefore)}

    @app.post('/hosted/worlds/{identity}/events/storms')
    def storm_action(identity: str, request: Request, value: dict = Depends(body)):
        row = owned(identity, request, 'advance')
        return library.storm_command(row, value)

    @app.post('/hosted/worlds/{identity}/advance')
    def advance(identity: str, request: Request, value: dict = Depends(body)):
        row = owned(identity, request, 'advance')
        if set(value) != {'through'}:
            raise ValueError('Provide only the desired through date.')
        return library.advance(row, value['through'])

    @app.get('/hosted/worlds/{identity}/events/sentiment')
    def sentiment_history(identity: str, request: Request, premiseId: str | None = None,
                          before: str | None = None, limit: int = Query(25, ge=1, le=50),
                          newsBefore: int | None = Query(None, ge=1, le=9223372036854775807)):
        from utilsim.world import sentiment

        owned(identity, request)
        return {'worldInstanceId': identity,
                **sentiment.inspect(library.library.world(identity), premiseId, before, limit, newsBefore)}

    @app.post('/hosted/worlds/{identity}/events/sentiment')
    def sentiment_action(identity: str, request: Request, value: dict = Depends(body)):
        return library.sentiment_command(owned(identity, request, 'advance'), value)

    install(app, machine, owned, body, controller_url, controller_token, controller_allow_http)
    from .operator import install as install_operator
    from .premises import install as install_premises
    install_operator(app, machine, owned, body, permits, controller_url, operator_token, controller_allow_http)
    install_premises(app, library, owned)
    return app


def from_environment():
    root = os.environ.get('UTILITYSIM_DATA_ROOT')
    if not root:
        raise ValueError('Mount a durable volume and set UTILITYSIM_DATA_ROOT; ephemeral disk is unsupported.')
    def secret(name):
        value, path = os.environ.get(name), os.environ.get(name + '_FILE')
        if value and path:
            raise ValueError('Configure a secret value or a secret file, not both.')
        if path:
            from pathlib import Path
            return Path(path).read_text(encoding='utf-8').strip()
        return value

    return create_app(root, secret('UTILITYSIM_RUNTIME_TOKEN'), secret('UTILITYSIM_MACHINE_KEY'),
                      os.environ.get('UTILITYSIM_CONTROLLER_ID', 'utilitysim-controller'),
                      os.environ.get('UTILITYSIM_CONTROLLER_URL'), secret('UTILITYSIM_CONTROLLER_TOKEN'),
                      os.environ.get('UTILITYSIM_CONTROLLER_ALLOW_HTTP') == '1',
                      secret('UTILITYSIM_OPERATOR_TOKEN'))
