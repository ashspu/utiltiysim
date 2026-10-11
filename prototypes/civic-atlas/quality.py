"""Read-only, measurable source checks. Visual approval is a separate review."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree


def shape(points):
    return Polygon([(p['x'], p['z']) for p in points])


def reachable(edges, starts):
    graph = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    seen, pending = set(), list(starts)
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(graph.get(node, set()) - seen)
    return seen


def geometry_checks(town):
    checks = []

    def check(identity, title, failures, detail):
        checks.append({'id': identity, 'title': title, 'status': 'fail' if failures else 'pass',
                       'detail': detail, 'failureCount': len(failures), 'examples': failures[:10]})

    premises = town['premises']
    homes = [p for p in premises if p['premiseType'] == 'residential']
    fairhaven = town.get('atlasDesign', {}).get('version', '').startswith('civic-atlas-town500/')
    expected = 500 if fairhaven else town['homes']
    check('population', 'Homes and premises', [] if len(homes) == expected and len(premises) == town['count'] else ['count mismatch'],
          f'{len(homes)} homes; {len(premises)} premises; {sum(p["occupants"] for p in homes if p["occupied"])} occupied-household residents.')
    duplicates = []
    for key in ('premises', 'parcels', 'buildings', 'meters', 'servicePoints', 'roads'):
        ids = [record['id'] for record in town[key]]
        if len(ids) != len(set(ids)):
            duplicates.append(key)
    check('identities', 'Stable, unique source identities', duplicates, 'Premises, parcels, buildings, meters, service points and roads checked separately.')
    parcels = [shape(p['polygon']) for p in town['parcels']]
    invalid = [p['id'] for p, polygon in zip(town['parcels'], parcels, strict=True) if not polygon.is_valid or polygon.area <= 0]
    check('valid-parcels', 'Valid parcel geometry', invalid, f'{len(parcels)} parcel polygons checked.')
    if invalid:
        checks.append({'id': 'geometry-dependencies', 'title': 'Containment and overlap', 'status': 'blocked',
                       'detail': 'Repair invalid parcels before running geometry operations.', 'failureCount': 0, 'examples': []})
        return checks
    overlaps = []
    tree = STRtree(parcels)
    for i, polygon in enumerate(parcels):
        for j in tree.query(polygon, predicate='intersects'):
            if j > i and polygon.intersection(parcels[j]).area > .02:
                overlaps.append(f'{town["parcels"][i]["id"]} / {town["parcels"][j]["id"]}')
    check('parcel-overlap', 'No overlapping parcels', overlaps, 'Intersections larger than 0.02 m² are rejected.')
    by_premise = {p['premiseId']: polygon for p, polygon in zip(town['parcels'], parcels, strict=True)}
    outside = []
    for building in town['buildings']:
        footprint = shape(building['footprint']['polygon'])
        for identity in building['premiseIds']:
            if identity not in by_premise or not footprint.is_valid or not by_premise[identity].buffer(.02).covers(footprint):
                outside.append(building['id'])
    check('containment', 'Buildings fit their parcels', outside, f'{len(town["buildings"])} building footprints checked with 2 cm tolerance.')
    roads = {r['id']: r for r in town['roads']}
    lines = {key: LineString([(p['x'], p['z']) for p in r['points']]) for key, r in roads.items()}
    pavement = unary_union([lines[key].buffer(r['pavementWidthM']/2, cap_style=2) for key, r in roads.items()])
    prepared_pavement = prep(pavement)
    collisions = [p['id'] for p, polygon in zip(town['parcels'], parcels, strict=True)
                  if prepared_pavement.intersects(polygon) and polygon.intersection(pavement).area > .02]
    check('pavement', 'Parcels stay clear of road pavement', collisions, 'Uses saved road widths, not painted road edges.')
    nodes = {r[k] for r in roads.values() for k in ('a', 'b')}
    connected = reachable([(r['a'], r['b']) for r in roads.values()], [next(iter(nodes))] if nodes else [])
    check('streets', 'Connected street graph', sorted(nodes-connected) or ([] if nodes else ['no roads']), f'{len(roads)} road segments; {len(nodes)} road nodes.')
    missing = [p['id'] for p in premises if p['roadId'] not in roads or lines[p['roadId']].distance(Point(p['front']['x'], p['front']['z'])) > .02]
    check('frontage', 'Property frontage reaches its assigned road', missing, 'Checks saved frontage anchors. Painted driveways and vehicle turning still need visual review.')
    land = town.get('atlasDesign', {})
    def parcel_intersection_area(polygon):
        nearby = tree.query(polygon, predicate='intersects')
        if not len(nearby):
            return 0.0
        return polygon.intersection(unary_union([parcels[int(i)] for i in nearby])).area

    conflict = []
    areas = [*town.get('parks', []), *land.get('fields', []), *land.get('commons', []), *land.get('openAreas', [])]
    for area in areas:
        polygon = Polygon([(p['x'], p['z']) for p in area['polygon']], [[(p['x'], p['z']) for p in ring] for ring in area.get('holes', [])])
        if not polygon.is_valid or parcel_intersection_area(polygon) > .02:
            conflict.append(area['id'])
    check('open-space', 'Public and rural land stays outside parcels', conflict, f'{len(areas)} parks, fields, conservation areas and shared greens checked, including polygon holes.')
    services = {s['id']: s for s in town['servicePoints']}
    home_ids = {p['id'] for p in premises}
    bad_services = [m['id'] for m in town['meters'] if m['servicePointId'] not in services or services[m['servicePointId']]['premiseId'] not in home_ids]
    for utility, network in town['networks'].items():
        network_nodes = {n['id'] for n in network['nodes']}
        sources = network.get('sourceIds') or [network['sourceId']]
        reached = reachable([(e['from'], e['to']) for e in network['edges'] if e.get('enabled', True)], sources)
        for service in services.values():
            if service['commodity'] == utility and (service['networkNodeId'] not in network_nodes or service['networkNodeId'] not in reached):
                bad_services.append(service['id'])
    check('services', 'Recorded services connect to a utility source', bad_services, f'{len(town["meters"])} meters; water, electricity and gas topology. This does not calculate pressure or voltage.')
    if land.get('presetId'):
        buildings = {b['id']: b for b in town['buildings']}
        parcel_records = {p['id']: p for p in town['parcels']}
        accounts = {a['id'] for a in town['accounts']}
        bad_bindings = []
        for p in premises:
            if p['buildingId'] not in buildings or p['id'] not in buildings[p['buildingId']]['premiseIds'] or p['parcelId'] not in parcel_records or parcel_records[p['parcelId']]['premiseId'] != p['id'] or p['accountId'] not in accounts:
                bad_bindings.append(p['id'])
            for service_id in p['services'].values():
                if service_id not in services or services[service_id]['premiseId'] != p['id']:
                    bad_bindings.append(service_id)
        check('entity-bindings', 'Every visible property resolves to its system records', bad_bindings, f'{len(premises)} premise → building, parcel, account and service mappings. Household attributes live on each premise.')
        protected = [a for a in land.get('landUseZones', []) if a['kind'] in ('environmental', 'water')]
        collisions = []
        for area in protected:
            poly = Polygon([(p['x'], p['z']) for p in area['polygon']], [[(p['x'], p['z']) for p in ring] for ring in area.get('holes', [])])
            if parcel_intersection_area(poly) > .02:
                collisions.append(area['id'])
        check('protected-land', 'Protected corridors exclude private parcels', collisions, f'{len(protected)} original conservation and water zones checked against all parcels.')
    budget = land.get('featureBudget')
    if budget:
        actual = {'homes': len(homes), 'pools': sum(bool(p.get('hasPool')) for p in premises),
                  'solar': sum(bool(p.get('solar')) or p.get('solarKW', 0) > 0 for p in premises),
                  'school': sum(p['buildingType'] == 'school' for p in premises),
                  'church': sum(p['buildingType'] == 'church' for p in premises),
                  'commercial': sum(p['premiseType'] == 'commercial' for p in premises),
                  'industrial': sum(p['premiseType'] == 'industrial' for p in premises)}
        failures = [key for key, count in actual.items() if count != budget[key]]
        target, margin = budget.get('targetHomes', budget['homes']), budget.get('homeTolerance', 0)
        if not target * (1-margin) <= len(homes) <= target * (1+margin):
            failures.append('target home tolerance')
        check('feature-budget', 'World-builder feature budget', failures, json.dumps(actual))
        pool_failures = []
        footprints = {pid: shape(b['footprint']['polygon']) for b in town['buildings'] for pid in b['premiseIds']}
        for p in premises:
            geometry = p.get('poolPolygon')
            if bool(geometry) != bool(p.get('hasPool')):
                pool_failures.append(p['id'])
            elif geometry:
                pool = shape(geometry)
                if not pool.is_valid or pool.area <= 0 or not by_premise[p['id']].buffer(-.5).covers(pool) or pool.intersects(footprints[p['id']]) or prepared_pavement.intersects(pool):
                    pool_failures.append(p['id'])
        check('pool-geometry', 'Every recorded pool fits its own backyard', pool_failures,
              'Checks presence, validity, parcel containment, buildings and pavement. AI pixels are assessed separately.')
    return checks


def visual_review(preset):
    """Keep internal design review separate from optional user acceptance."""
    root = Path(__file__).parent / "web/presets"
    if not preset or not (root / "catalog.json").is_file():
        return {"status": "pending", "userApproval": False}
    entries = json.loads((root / "catalog.json").read_text(encoding="utf-8"))["presets"]
    entry = next((row for row in entries if row["id"] == preset), {})
    review = dict(entry.get("internalVisualReview") or {"status": "pending"})
    tile_path = root / preset / "tiles.json" if entry else None
    if review.get("status") == "passed":
        manifest = json.loads(tile_path.read_text(encoding="utf-8")) if tile_path and tile_path.is_file() else {}
        if review.get("sourceSha256") != manifest.get("sourceSha256"):
            review["status"] = "outdated"
    review["userApproval"] = bool(entry.get("userVisualApproval", False))
    return review


def quality_report(town, world):
    checks = geometry_checks(town)
    with world.read_db() as db:
        status = world._status(db)
        integrity = db.execute('PRAGMA quick_check').fetchone()[0]
        days = db.execute('SELECT MAX(day) FROM days').fetchone()[0]
        missing = [r[0] for r in db.execute('SELECT a.id FROM assets a LEFT JOIN observations o ON o.asset=a.id AND o.day=? WHERE o.id IS NULL', (days,))] if days else []
    checks.append({'id': 'database', 'title': 'Saved world database integrity', 'status': 'pass' if integrity == 'ok' else 'fail',
                   'detail': integrity, 'failureCount': int(integrity != 'ok'), 'examples': []})
    checks.append({'id': 'observations', 'title': 'Latest completed day has meter records',
                   'status': 'fail' if missing else 'pass' if days else 'blocked',
                   'detail': f'{status["assets"]} meters; latest completed day: {days or "none"}. Missing readings remain unknown, never zero.',
                   'failureCount': len(missing), 'examples': missing[:10]})
    review = visual_review(town.get('atlasDesign', {}).get('presetId'))
    from source_binding import fingerprint
    return {'schemaVersion': 'civic-atlas-quality/1', 'generatedAt': datetime.now(UTC).isoformat(),
            'townId': town['id'], 'through': status['through'],
            'snapshotSha256': fingerprint(town), 'internalVisualReview': review,
            'automatedPassed': all(c['status'] == 'pass' for c in checks), 'checks': checks,
            'reviewRequired': [
                'Internal visual QA passed for the current map source. Optional user acceptance is pending.'
                if review.get('status') == 'passed' else 'Internal visual QA is pending or belongs to an older map source.',
                'The illustrated 2.5D map retains exact parcel, building and road identities. Generated artwork is separate from vector geometry.',
                'Painted driveway continuity, sidewalk placement and loading-yard maneuverability are assessed visually; frontage anchors alone do not certify them.',
                'Artwork registration, picking, navigation and responsive layouts are checked by the separate browser suites.',
                'Simulation, actual Virtual Systems billing and authenticated water-field work have separate end-to-end checks. Road construction is not implemented.',
            ]}
