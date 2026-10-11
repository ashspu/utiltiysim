"""Bake the approved raster composition into editable, semantic SVG geometry.

Road centerlines and semantic zoning boundaries are hand-traced and refined from
the approved concept. Color thresholding cannot reliably distinguish roof colors
from land use, so it is not used for authoritative geometry. This is an authoring
step, never a runtime generator. Review the SVG before changing the baked world.
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from scipy.interpolate import PchipInterpolator
from shapely.geometry import LineString, Polygon
from shapely.ops import nearest_points, unary_union

ROOT = Path(__file__).parent / 'web/presets/riverbend-500'
COLORS = {
    'residential': '#eee985', 'commercial': '#ed8183', 'industrial': '#7fb0eb',
    'institutional': '#e6a4d5', 'agricultural': '#e7dcc6', 'parks': '#bee777',
    'environmental': '#8da777', 'mixed_use': '#ac80c6', 'development': '#b8bcbd',
    'water': '#72b9d8',
}


def parts(shape):
    return [p for p in getattr(shape, 'geoms', [shape]) if p.geom_type == 'Polygon']


def path_data(poly):
    rings = [poly.exterior, *poly.interiors]
    return ' '.join('M ' + ' L '.join(f'{x:.2f},{y:.2f}' for x, y in r.coords) + ' Z' for r in rings)


def bake():
    trace = json.loads((ROOT / 'roads.json').read_text())
    raw_zones = json.loads((ROOT / 'zones.json').read_text())['zones']
    zones = []
    polygons = [Polygon(coords).buffer(0) for _, _, coords in raw_zones]
    for index, (name, kind, _) in enumerate(raw_zones):
        polygon = polygons[index].difference(unary_union(polygons[index+1:]))
        for i, part in enumerate(parts(polygon)):
            zones.append({'id': f'{kind}-{index:02d}-{i}', 'kind': kind, 'name': name, 'polygon': part})
    roads = []
    for i, (name, kind, coords) in enumerate(trace['roads']):
        values = np.asarray(coords, dtype=float)
        # Small tracing discrepancies snap to existing road centerlines.
        if roads:
            network = unary_union([r['line'] for r in roads])
            from shapely.geometry import Point
            for end in (0, -1):
                q = nearest_points(Point(values[end]), network)[1]
                if q.distance(Point(values[end])) < 12:
                    values[end] = q.coords[0]
        t = np.r_[0., np.cumsum(np.linalg.norm(np.diff(values, axis=0), axis=1))]
        # Shape-preserving interpolation avoids spline overshoot near T joins.
        samples = np.unique(np.r_[t, np.arange(0, t[-1], 3)])
        line = LineString(PchipInterpolator(t, values, axis=0)(samples))
        roads.append({'id': f'road-{i+1:03d}', 'name': name, 'kind': kind, 'line': line})
    svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg', 'viewBox': '0 0 1536 1024',
                            'data-preset': 'riverbend-500', 'data-metres-per-pixel': str(trace['metresPerPixel'])})
    ET.SubElement(svg, 'title').text = 'Riverbend — fixed master plan, traced from approved concept'
    ET.SubElement(svg, 'desc').text = 'Editable zoning boundaries and connected road centerlines. Parcel and building records are baked separately from this geometry.'
    ET.SubElement(svg, 'rect', {'width': '1536', 'height': '1024', 'fill': COLORS['agricultural']})
    group = ET.SubElement(svg, 'g', {'id': 'zones', 'stroke': '#58684b', 'stroke-width': '.35', 'fill-rule': 'evenodd'})
    for zone in zones:
        ET.SubElement(group, 'path', {'id': zone['id'], 'data-kind': zone['kind'], 'd': path_data(zone['polygon']), 'fill': COLORS[zone['kind']]})
    group = ET.SubElement(svg, 'g', {'id': 'roads', 'fill': 'none', 'stroke': '#acb4b1', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'})
    for road in roads:
        ET.SubElement(group, 'polyline', {'id': road['id'], 'data-name': road['name'], 'data-kind': road['kind'],
                      'points': ' '.join(f'{x:.2f},{y:.2f}' for x, y in road['line'].coords),
                      'stroke-width': str({'arterial': 12, 'collector': 9, 'local': 5}[road['kind']])})
    ET.indent(svg)
    ET.ElementTree(svg).write(ROOT / 'master.svg', encoding='utf-8', xml_declaration=True)
    print(json.dumps({'roads': len(roads), 'zones': len(zones), 'output': str(ROOT / 'master.svg')}))


if __name__ == '__main__':
    bake()
