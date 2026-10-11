"""Bake a fixed, image-led SVG plan into real UtilitySim entities and networks."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from town500_world import _exits, _facility  # noqa: E402

from utilsim.config import load_preset  # noqa: E402
from utilsim.customers.generate import build_customers  # noqa: E402
from utilsim.gen.addresses import assign_addresses  # noqa: E402
from utilsim.gen.buildings import _rect, assign_households, build_premises  # noqa: E402
from utilsim.gen.landuse import LandUse  # noqa: E402
from utilsim.gen.parcels import candidate_lots  # noqa: E402
from utilsim.gen.roads.build import Geography  # noqa: E402
from utilsim.gen.roads.model import ARTERIAL, COLLECTOR, LOCAL, ROW_WIDTH, RoadLine  # noqa: E402
from utilsim.gen.roads.planarize import planarize  # noqa: E402
from utilsim.gen.terrain import Terrain  # noqa: E402
from utilsim.gen.zoning import build_era_field  # noqa: E402
from utilsim.io.snapshot import build_snapshot  # noqa: E402
from utilsim.model.town import Town  # noqa: E402
from utilsim.net.context import NetContext  # noqa: E402
from utilsim.net.electric import build_electric  # noqa: E402
from utilsim.net.gas import build_gas  # noqa: E402
from utilsim.net.water import build_water  # noqa: E402

ROOT = Path(__file__).parent / 'web/presets/riverbend-500'
VERSION = 'civic-atlas-preset/1'
SEED = 'CIVIC-ATLAS-RIVERBEND-500-V1'


def components(geom):
    return [p for p in getattr(geom, 'geoms', [geom]) if p.geom_type == 'Polygon' and p.area > 50]


def read_master():
    root = ET.parse(ROOT / 'master.svg').getroot()
    scale = float(root.attrib['data-metres-per-pixel'])
    def xy(x, y):
        return ((float(x)-768)*scale, (512-float(y))*scale)
    roads, zones = [], []
    for el in root.iter():
        if el.tag.endswith('polyline'):
            coords = [xy(*p.split(',')) for p in el.attrib['points'].split()]
            roads.append(RoadLine(np.array(coords), {'arterial': ARTERIAL, 'collector': COLLECTOR, 'local': LOCAL}[el.attrib['data-kind']], el.attrib['data-name']))
        elif el.tag.endswith('path'):
            rings = [[xy(*pair) for pair in re.findall(r'(-?[\d.]+),(-?[\d.]+)', ring)] for ring in el.attrib['d'].split('M') if ring.strip()]
            polygon = Polygon(rings[0], rings[1:]).buffer(0)
            for part in components(polygon):
                zones.append({'id': el.attrib['id'], 'kind': el.attrib['data-kind'], 'color': el.attrib['fill'], 'shape': part})
    extent = (-768*scale, -512*scale, 768*scale, 512*scale)
    return roads, zones, extent, xy


def build_preset_snapshot():
    lines, zones, extent, xy = read_master()
    cfg = load_preset('village', seed=SEED, houses=500, overrides={'town': {
        'terrain_relief_m': 0, 'era_core_year': 1935, 'era_span_years': 70, 'industrial_lots': 1},
        'housing': {'lot_frontage_m': {'pre_1945': 13.5, 'postwar': 16.5, 'modern': 15.0}}})
    roads = planarize([], lines, min_dangle=2)
    if roads.dropped_edges:
        raise ValueError(f'Trace has disconnected roads: {roads.dropped_edges} dropped edges')
    terrain = Terrain(cfg.seeds.for_('town'), relief_m=0, base_m=90)
    center = xy(720, 505)
    era = build_era_field(cfg.seeds.for_('town'), center, 1000, extent, 500, 1935, 70, 9, cfg.gas.all_electric_district_share)
    geo = Geography(roads, era, terrain, center, extent, cfg.town.anchor_lat, cfg.town.anchor_lon,
                    {'type': 'synthetic', 'label': 'Riverbend — approved image-led master plan', 'expansion': 'none', 'streetModel': VERSION})
    lots, _ = candidate_lots(geo, cfg, extent)
    # Compare exported coordinates at full precision: GEOS's inherited 1 cm
    # grid otherwise hides narrow overlaps that reappear when read from JSON.
    lots.poly = [set_precision(p, 0) for p in lots.poly]
    road_land = unary_union([LineString(g).buffer(ROW_WIDTH[roads.graph.edge_class[i]]/2, cap_style=2) for i, g in enumerate(roads.graph.geometry)])
    areas = {kind: unary_union([z['shape'] for z in zones if z['kind'] == kind]) for kind in {z['kind'] for z in zones}}
    # Purposeful campus / employment sites traced from their colored districts.
    def site(x0, y0, x1, y1):
        a, b = xy(x0, y0), xy(x1, y1)
        return box(a[0], b[1], b[0], a[1])
    facility_specs = [
        ('SCHOOL-01', 'school', 'Riverbend School', (443, 203, 554, 305), 'School Lane'),
        ('CHURCH-01', 'school', 'Riverbend Community Hall', (670, 667, 722, 711), 'River Walk'),
        ('DEPOT-01', 'depot', 'East Service Depot', (1158, 694, 1279, 737), 'Market Street'),
        ('INDUSTRY-01', 'industrial', 'Riverbend Workshops', (1050, 760, 1174, 813), 'Workshop Road'),
        ('PUMP-01', 'pump_station', 'River Pump Site', (946, 707, 984, 744), 'Workshop Road'),
        ('SUB-01', 'substation', 'East Substation', (1260, 812, 1310, 845), 'Depot Lane'),
        ('GATE-01', 'city_gate', 'East Gas Gate', (1199, 806, 1230, 835), 'Depot Lane'),
        ('TANK-01', 'elevated_tank', 'North Water Tower', (1018, 422, 1041, 445), 'Mill Bridge'),
    ]
    facilities = []
    for identity, kind, name, bounds, street in facility_specs:
        available = components(site(*bounds).difference(road_land.buffer(1)))
        if not available:
            raise ValueError(f'No clear site for {identity}')
        facilities.append(_facility(roads, identity, kind, name, max(available, key=lambda p: p.area), street))
    pads = unary_union([f.poly.buffer(4) for f in facilities])
    protected = areas['environmental'].union(areas['water'])
    reserved = unary_union([pads, protected, areas['parks'], areas['institutional'], areas['industrial'], areas['development']])
    housing_area = areas['residential']
    commercial_area = areas['commercial'].union(areas['mixed_use'])
    eligible, shop_candidates = [], []
    for i, p in enumerate(lots.poly):
        # Land reservations are hard boundaries. Keep the original street edge
        # when trimming a rear boundary; never shift the road to fit a building.
        clear = p.difference(reserved)
        valid_parts = [part for part in components(clear) if part.distance(Point(lots.row_xy[i])) < .5]
        if not valid_parts:
            continue
        p = max(valid_parts, key=lambda part: part.area)
        lots.poly[i] = p
        if p.intersection(pads).area > .02 or p.intersection(protected).area > .02:
            continue
        fitted = _rect(np.asarray(p.centroid.coords[0]), lots.tangent[i], lots.normal[i], 7, 8)
        if not p.buffer(-.7).covers(fitted):
            continue
        if p.intersection(commercial_area).area > p.area*.18:
            shop_candidates.append(i)
        elif p.intersection(housing_area).area > p.area*.45 and p.intersection(reserved).area < p.area*.16:
            eligible.append(i)
    tree = STRtree(lots.poly)
    accepted = set()
    def accept(indices, count):
        chosen = []
        for i in indices:
            if i in accepted:
                continue
            neighbors = [j for j in tree.query(lots.poly[i], predicate='intersects') if j in accepted]
            if neighbors:
                original = lots.poly[i]
                pieces = components(original.difference(unary_union([lots.poly[j] for j in neighbors])))
                if not pieces:
                    continue
                fitted = max(pieces, key=lambda p: p.area)
                if fitted.area < original.area*.90 or fitted.distance(Point(lots.row_xy[i])) > .5:
                    continue
                if not fitted.buffer(-.7).covers(_rect(np.asarray(fitted.centroid.coords[0]), lots.tangent[i], lots.normal[i], 7, 8)):
                    continue
                lots.poly[i] = fitted
            accepted.add(i)
            chosen.append(i)
            if len(chosen) == count:
                break
        return chosen
    shops = accept(sorted(shop_candidates, key=lambda i: lots.poly[i].centroid.distance(Point(center))), 20)
    # Round-robin street allocation keeps houses in every traced neighborhood.
    streets = {}
    for i in eligible:
        streets.setdefault(roads.names[lots.edge[i]], []).append(i)
    ordered = []
    while any(streets.values()):
        for name in sorted(streets):
            if streets[name]:
                ordered.append(streets[name].pop(0))
    chosen = accept(ordered, 500)
    if len(chosen) != 500 or len(shops) != 20:
        raise ValueError(f'The fixed plan fits {len(chosen)} homes / {len(shops)} shops. Refine the plan; do not invent remote lots. Eligible {len(eligible)} / {len(shop_candidates)}.')
    lu = LandUse(roads, lots.subset(chosen), lots.subset(shops), facilities, [], extent, 1000., _exits(roads, extent, center))
    prem = build_premises(lu, cfg, terrain, era)
    for i in range(len(prem.ids)):
        if prem.facility_id[i] == 'CHURCH-01':
            prem.building_type[i] = 'church'
        if not prem.lot[i].buffer(.02).covers(prem.footprint[i]):
            center_i = np.asarray(prem.lot[i].centroid.coords[0])
            tangent = np.array([math.cos(prem.heading[i]), math.sin(prem.heading[i])])
            footprint = _rect(center_i, tangent, prem.normal[i], 7, 8)
            if not prem.lot[i].buffer(-.5).covers(footprint):
                raise ValueError(f'Building cannot fit its parcel: {prem.ids[i]}')
            prem.xy[i] = center_i
            prem.width[i], prem.depth[i], prem.footprint[i] = 7, 8, footprint
    assign_households(prem, cfg, era)
    assign_addresses(prem, roads, geo.center)
    ctx = NetContext(cfg, lu, prem, terrain, era, cfg.seeds.for_('town'))
    networks = {'electric': build_electric(ctx), 'water': build_water(ctx), 'gas': build_gas(ctx)}
    town = Town(cfg, geo, lu, prem, networks)
    town.customers = build_customers(town)
    snapshot = build_snapshot(town, embed_state=False)
    # Preserve shared curved boundary vertices without another rounding pass.
    source_lots = {identity: prem.lot[i] for i, identity in enumerate(prem.ids)}
    for parcel in snapshot['parcels']:
        parcel['polygon'] = [{'x': float(x), 'z': float(-y)} for x, y in source_lots[parcel['premiseId']].exterior.coords[:-1]]
    occupied = unary_union([*lu.houses.poly, *lu.commercial.poly, *[f.poly for f in facilities], road_land])
    open_areas = []
    def vector(poly):
        return [{'x': float(x), 'z': float(-y)} for x, y in poly.exterior.coords[:-1]]
    for kind in ('environmental', 'parks', 'agricultural', 'water', 'development'):
        for i, polygon in enumerate(components(areas[kind].difference(occupied))):
            open_areas.append({'id': f'{kind}-{i:03d}', 'kind': kind, 'polygon': vector(polygon),
                              'holes': [vector(Polygon(ring)) for ring in polygon.interiors]})
    display_zones = []
    for z in zones:
        for i, polygon in enumerate(components(z['shape'].difference(road_land))):
            display_zones.append({'id': f'{z["id"]}-{i}', 'kind': z['kind'], 'color': z['color'], 'polygon': vector(polygon),
                                  'holes': [vector(Polygon(ring)) for ring in polygon.interiors]})
    snapshot['atlasDesign'] = {
        'version': VERSION, 'presetId': 'riverbend-500', 'revision': 1, 'name': 'Riverbend',
        'curated': True, 'defaultArt': 'native', 'description': 'Fixed image-led master plan, traced into SVG and baked into UtilitySim.',
        'focus': {'x': center[0], 'z': -center[1], 'viewHeightM': 1180},
        'masterSvgSha256': hashlib.sha256((ROOT / 'master.svg').read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
        'conceptSha256': hashlib.sha256((ROOT / 'concept.png').read_bytes()).hexdigest(),
        'landUseZones': display_zones,
        'openAreas': open_areas, 'parks': [], 'fields': [],
        'sourceReview': 'Concept direction approved; vector tracing and 3D property layout require visual review.',
        'binding': {'premiseId': 'premises.id', 'parcelId': 'parcels.id', 'buildingId': 'buildings.id',
                    'meters': 'meters.servicePointId → servicePoints.premiseId',
                    'households': 'premises.occupants / occupied / tenure', 'regenerateAtRuntime': False},
    }
    return snapshot


def export_bound_svg(snapshot):
    root = ET.parse(ROOT / 'master.svg').getroot()
    ns = '{http://www.w3.org/2000/svg}'
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    scale = float(root.attrib['data-metres-per-pixel'])
    def coords(polygon):
        return ' '.join(f'{p["x"]/scale+768:.5f},{p["z"]/scale+512:.5f}' for p in polygon)
    parcels = ET.SubElement(root, ns+'g', {'id': 'parcels', 'fill': 'none', 'stroke': '#666949', 'stroke-width': '.4'})
    buildings = ET.SubElement(root, ns+'g', {'id': 'buildings', 'fill': '#738270', 'stroke': '#485c4e', 'stroke-width': '.4'})
    for p in snapshot['parcels']:
        ET.SubElement(parcels, ns+'polygon', {'id': p['id'], 'data-premise-id': p['premiseId'], 'points': coords(p['polygon'])})
    for b in snapshot['buildings']:
        el = ET.SubElement(buildings, ns+'polygon', {'id': b['id'], 'data-premise-id': b['premiseIds'][0], 'points': coords(b['footprint']['polygon']), 'tabindex': '0', 'role': 'link'})
        ET.SubElement(el, ns+'title').text = b['premiseIds'][0]
    ET.indent(root)
    ET.ElementTree(root).write(ROOT / 'town.svg', encoding='utf-8', xml_declaration=True)
    bindings = []
    for p in snapshot['premises']:
        services = list(p['services'].values())
        bindings.append({'key': f'riverbend-500/v1/{p["id"]}', 'premiseId': p['id'], 'parcelId': p['parcelId'],
                         'buildingId': p['buildingId'], 'address': p['address'], 'accountId': p['accountId'],
                         'servicePointIds': services, 'meterIds': [m['id'] for m in snapshot['meters'] if m['servicePointId'] in services]})
    (ROOT / 'bindings.json').write_text(json.dumps({'schemaVersion': 'civic-atlas-bindings/1', 'presetId': 'riverbend-500', 'revision': 1,
                                                  'worldId': snapshot['id'], 'properties': bindings}, indent=2))


if __name__ == '__main__':
    from quality import geometry_checks
    result = build_preset_snapshot()
    report = geometry_checks(result)
    print(json.dumps(report, indent=2))
    if any(c['status'] != 'pass' for c in report):
        raise SystemExit('Refusing to bake a preset with failed source geometry checks.')
    (ROOT / 'snapshot.json').write_text(json.dumps(result, separators=(',', ':')))
    export_bound_svg(result)
    print(json.dumps({'homes': result['homes'], 'premises': result['count'], 'path': str(ROOT / 'snapshot.json')}))
