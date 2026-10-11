"""Bake planar gable/hip roof faces over the actual authored footprint.

The saved building height is the eave height, as in the live town viewer.
Pitch is a display choice. Intersecting rectangular wings form a continuous
roof envelope; solar modules must fit entirely on one of its planar faces.
"""
import math
from itertools import combinations

import numpy as np
from shapely import affinity, constrained_delaunay_triangles, set_precision
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union


def pieces(geometry):
    return [p for p in getattr(geometry, 'geoms', [geometry]) if p.geom_type == 'Polygon' and p.area > 1e-9]


def clip(vertices, a, b, c):
    """Clip a convex ring to a*x+b*y+c <= 0."""
    result = []
    for previous, current in zip(vertices[-1:] + vertices[:-1], vertices, strict=True):
        before, after = a * previous[0] + b * previous[1] + c, a * current[0] + b * current[1] + c
        if (before <= 1e-10) != (after <= 1e-10):
            t = before / (before - after)
            result.append([previous[0] + t * (current[0] - previous[0]), previous[1] + t * (current[1] - previous[1])])
        if after <= 1e-10:
            result.append(current)
    return result


def rectangular_wings(footprint):
    xs = sorted({round(x, 7) for x, _ in footprint.exterior.coords})
    ys = sorted({round(y, 7) for _, y in footprint.exterior.coords})
    candidates = [box(x0, y0, x1, y1) for x0, x1 in combinations(xs, 2)
                  for y0, y1 in combinations(ys, 2) if footprint.buffer(1e-7).covers(box(x0, y0, x1, y1))]
    wings = [p for p in candidates if not any(q.area > p.area + 1e-8 and q.buffer(1e-8).covers(p) for q in candidates)]
    if not wings or unary_union(wings).symmetric_difference(footprint).area > 1e-5:
        raise ValueError('Roof footprint must be an authored orthogonal rectangle or compound wing')
    return wings


def height(plane, x, y):
    return plane[0] * x + plane[1] * y + plane[2]


def build_roof(property_record, scale=1.35):
    p = property_record
    world = Polygon(p['footprint'])
    local = affinity.rotate(affinity.translate(world, -p['center'][0], -p['center'][1]), -p['heading'], origin=(0, 0))
    wings = rectangular_wings(local)
    roof_type = p['physical']['roof']
    if roof_type not in ('gable', 'hip'):
        raise ValueError(f'Unsupported recorded roof type: {roof_type}')
    specs = []
    full_width = local.bounds[2] - local.bounds[0]
    for wing in wings:
        x0, y0, x1, y1 = wing.bounds
        planes = [(1, 0, -x0), (-1, 0, x1), (0, 1, -y0), (0, -1, y1)]
        cross_width = min(x1-x0, y1-y0)
        if roof_type == 'gable':
            horizontal = abs(x1-x0-full_width)<1e-6 if len(wings)>1 else x1-x0>=y1-y0
            planes = planes[2:] if horizontal else planes[:2]
            cross_width = y1-y0 if horizontal else x1-x0
        specs.append((wing, planes, cross_width/2))
    run = max(spec[2] for spec in specs)
    rise = min(3.0, max(1.2, run * scale * .45))
    slope = rise / run
    faces = []
    for wing_index, (wing, planes, _) in enumerate(specs):
        for plane in planes:
            vertices = list(wing.exterior.coords)[:-1]
            for other in planes:
                vertices = clip(vertices, *[a - b for a, b in zip(plane, other, strict=True)])
                if len(vertices) < 3:
                    break
            if len(vertices) >= 3 and Polygon(vertices).area > 1e-8:
                # Clipped wing faces are convex. Normalize duplicate corner vertices
                # before intersections so zero-length edges cannot break noding.
                polygon = Polygon(set_precision(Polygon(vertices).convex_hull, 1e-7).exterior.coords)
                faces.append({'polygon': polygon, 'plane': plane, 'wing': wing_index})
    lines = [f['polygon'].boundary for f in faces]
    for a, b in combinations(faces, 2):
        if a['wing'] == b['wing']:
            continue
        overlap = a['polygon'].intersection(b['polygon'])
        if overlap.area < 1e-8:
            continue
        aa, bb, cc = [x - y for x, y in zip(a['plane'], b['plane'], strict=True)]
        norm = aa * aa + bb * bb
        if norm < 1e-10:
            continue
        cx, cy = -cc * aa / norm, -cc * bb / norm
        divider = LineString([(cx - bb * 1000, cy + aa * 1000), (cx + bb * 1000, cy - aa * 1000)])
        edge = overlap.intersection(divider)
        if not edge.is_empty:
            lines.append(edge)
    groups = {}
    for cell in polygonize(unary_union([set_precision(line, 1e-7) for line in lines])):
        center = cell.representative_point()
        eligible = [f for f in faces if f['polygon'].buffer(1e-8).covers(center)]
        if not eligible:
            continue
        plane = max(eligible, key=lambda f: height(f['plane'], center.x, center.y))['plane']
        groups.setdefault(plane, []).append(cell)
    angle = math.radians(p['heading'])
    cosine, sine = math.cos(angle), math.sin(angle)
    model = {'type': roof_type, 'eaveHeightM': p['heightM'], 'riseM': rise,
             'heightConvention': 'saved height is wall/eave height; pitch is illustrative',
             'faces': [], 'triangles': [], 'gableTriangles': [], 'seams': []}
    for local_plane, cells in groups.items():
        a, b, c = local_plane
        a, b, c = a * slope, b * slope, p['heightM'] + c * slope
        aa, bb = a * cosine - b * sine, a * sine + b * cosine
        plane = [aa, bb, c - aa * p['center'][0] - bb * p['center'][1]]
        for part in pieces(unary_union(cells)):
            face = affinity.translate(affinity.rotate(part.simplify(1e-8), p['heading'], origin=(0, 0)), *p['center'])
            face = Polygon(face.exterior.coords, [ring.coords for ring in face.interiors if Polygon(ring).area > 1e-8])
            if not face.is_valid:
                # Rotating a coplanar union can turn a coincident seam into a
                # zero-width spike. Remove only topology noise with no area loss.
                repaired = face.buffer(0)
                if repaired.geom_type == 'Polygon' and abs(repaired.area-face.area) < 1e-8:
                    face = repaired
            if face.interiors:
                raise ValueError(f'Unexpected roof face hole: {p["id"]}')
            if face.area < 1e-8:
                continue
            if not face.is_valid:
                raise ValueError(f'Invalid roof face {p["id"]}: {face.wkt}')
            vertices = [[x, y, height(plane, x, y)] for x, y in face.exterior.coords]
            model['faces'].append({'polygon': list(face.exterior.coords), 'plane': plane, 'vertices': vertices})
            try:
                triangles = constrained_delaunay_triangles(face).geoms
            except Exception as error:
                raise ValueError(f'Roof triangulation {p["id"]}, area {face.area}: {face.wkt}') from error
            for tri in triangles:
                points = list(tri.exterior.coords)[:-1]
                if tri.exterior.is_ccw:
                    points.reverse()  # x/elevation/y coordinates need upward normals.
                model['triangles'].append([[x, y, height(plane, x, y)] for x, y in points])
            for first, last in zip(vertices[:-1], vertices[1:], strict=True):
                edge = LineString([first[:2], last[:2]])
                if edge.difference(world.boundary.buffer(1e-6)).length > 1e-6:
                    continue
                low_first, low_last = [*first[:2], p['heightM']], [*last[:2], p['heightM']]
                for tri in ([low_first, low_last, last], [low_first, last, first]):
                    if np.linalg.norm(np.cross(np.subtract(tri[1], tri[0]), np.subtract(tri[2], tri[0]))) > 1e-8:
                        model['gableTriangles'].append(tri)
    for a, b in combinations(model['faces'], 2):
        if np.allclose(a['plane'], b['plane'], atol=1e-7, rtol=0):
            continue
        shared = Polygon(a['polygon']).boundary.intersection(Polygon(b['polygon']).boundary)
        for line in getattr(shared, 'geoms', [shared]):
            if line.geom_type == 'LineString' and line.length > 1e-6:
                model['seams'].append([[x, y, height(a['plane'], x, y)] for x, y in line.coords])
    surface = unary_union([Polygon(f['polygon']) for f in model['faces']])
    if world.symmetric_difference(surface).area > 1e-5:
        raise ValueError(f'Incomplete roof coverage: {p["id"]}: {world.symmetric_difference(surface).area}')
    model['peakHeightM'] = max(v[2] for tri in model['triangles'] for v in tri)
    point = Point(p['center'])
    pick_height = max(height(f['plane'], point.x, point.y) for f in model['faces'] if Polygon(f['polygon']).buffer(1e-7).covers(point))
    model['pickPoint'] = [point.x, point.y, pick_height]
    return model


def solar_modules(property_record, count):
    p = property_record
    candidates = []
    for index, face in sorted(enumerate(p['roofModel']['faces']), key=lambda item: Polygon(item[1]['polygon']).area, reverse=True):
        world = Polygon(face['polygon'])
        local = affinity.rotate(world, -p['heading'], origin=tuple(p['center']))
        x0, y0, x1, y1 = local.bounds
        best = []
        for shift_x, shift_y in ((0, 0), (.35, .25), (.7, .5)):
            batch = []
            for x in np.arange(x0 + .8 + shift_x, x1 - .6, 1.4):
                for y in np.arange(y0 + .6 + shift_y, y1 - .4, 1.0):
                    panel = affinity.rotate(box(x - .625, y - .4, x + .625, y + .4), p['heading'], origin=tuple(p['center']))
                    if world.buffer(-.12).covers(panel):
                        batch.append(panel)
            if len(batch) > len(best):
                best = batch
        candidates.extend((index, panel) for panel in best)
    if len(candidates) < count:
        raise ValueError(f'Recorded solar capacity needs {count} modules, only {len(candidates)} fit {p["id"]}')
    result = []
    for index, polygon in candidates[:count]:
        plane = p['roofModel']['faces'][index]['plane']
        result.append({'faceIndex': index, 'polygon': list(polygon.exterior.coords),
                       'vertices': [[x, y, height(plane, x, y) + .06] for x, y in polygon.exterior.coords]})
    return result
