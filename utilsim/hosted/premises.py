"""Bounded physical identifiers for selecting a premise in the hosted operator UI."""
import json

from fastapi import HTTPException, Query, Request

from utilsim.world import occupancy
from utilsim.world.map_view import WorldMap


def summary(home, binding):
    result = {'premiseId': home['id']}
    for key, value in [('address', home.get('address')), ('parcelId', binding.get('parcelId'))]:
        if isinstance(value, str) and value:
            if len(value) > 512:
                raise HTTPException(503, 'Saved premise display text exceeds its bound.')
            result[key] = value
    if not isinstance(home['id'], str) or not 1 <= len(home['id']) <= 200:
        raise HTTPException(503, 'Saved premise identifier exceeds the operator bound.')
    return result


def install(app, library, owned):
    def source(row):
        return json.loads(row['request'])['sourceRevision']

    def bindings(row):
        return {binding['premiseId']: binding for binding in json.loads(row['bindings'])}

    @app.get('/hosted/worlds/{identity}/premises')
    def premises(identity: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=50)):
        row = owned(identity, request)
        homes = sorted(WorldMap(library.library.world(identity)).snapshot()['premises'], key=lambda home: home['id'])
        mapped = bindings(row)
        return {'worldId': identity, 'sourceRevision': source(row), 'total': len(homes), 'offset': offset,
                'premises': [summary(home, mapped.get(home['id'], {})) for home in homes[offset:offset + limit]]}

    @app.get('/hosted/worlds/{identity}/premises/{premise}/summary')
    def premise_summary(identity: str, premise: str, request: Request):
        row = owned(identity, request)
        world = library.library.world(identity)
        with world.read_db() as db:
            snapshot = json.loads(db.execute("SELECT value FROM meta WHERE key='snapshot'").fetchone()[0])
            home = next((home for home in snapshot['premises'] if home['id'] == premise), None)
            if home is None:
                raise HTTPException(404, 'Physical premise is not in this world.')
            record = summary(home, bindings(row).get(premise, {}))
            kind = home.get('type') or home.get('premiseType')
            if isinstance(kind, str) and 0 < len(kind) <= 200:
                record['type'] = kind
            record['occupied'] = occupancy.current(db, premise, home)['occupied']
        return {'worldId': identity, 'sourceRevision': source(row), 'premise': record}
