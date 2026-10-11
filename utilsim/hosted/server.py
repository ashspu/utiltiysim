"""Internal runtime API. Only a trusted identity gateway may connect."""
import hmac
import json
import os
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
         'create': {'owner'}, 'advance': {'owner', 'operator'}}


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
        if grant.get('town') in ('*', town) and grant.get('role') in ROLES[action]:
            return True
    return False


def create_app(root, token):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError('Configure an internal bearer token of at least 32 characters.')
    library = HostedLibrary(root)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.library = library

    @app.middleware('http')
    async def authenticate(request, call_next):
        supplied = request.headers.get('authorization', '')
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
            return JSONResponse({'detail': 'Internal gateway authentication required.'}, status_code=401)
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
                'currentAdapterFixed': ['startingPopulation', 'demandProfiles', 'networkTopology', 'housingAge', 'meterChannels', 'timezone'],
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
        return {'worldInstanceId': identity, **WorldMap(library.library.world(identity)).premise(premise)}

    @app.get('/hosted/worlds/{identity}/premises/{premise}/history')
    def history(identity: str, premise: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(14, ge=1, le=31)):
        owned(identity, request)
        world = library.library.world(identity)
        record = WorldMap(world).premise(premise)
        with world.read_db() as db:
            rows = [dict(r) for r in db.execute(
                'SELECT o.day,a.id assetId,a.commodity,a.unit,o.id observationId,o.status,o.quantity observedQuantity '
                'FROM assets a JOIN observations o ON o.asset=a.id '
                'WHERE a.premise=? AND o.day IN (SELECT day FROM days ORDER BY day DESC LIMIT ? OFFSET ?) '
                'ORDER BY o.day DESC,a.id', (premise, limit, offset))]
            total = db.execute('SELECT COUNT(*) FROM days').fetchone()[0]
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

    return app


def from_environment():
    root = os.environ.get('UTILITYSIM_DATA_ROOT')
    if not root:
        raise ValueError('Mount a durable volume and set UTILITYSIM_DATA_ROOT; ephemeral disk is unsupported.')
    return create_app(root, os.environ.get('UTILITYSIM_RUNTIME_TOKEN'))
