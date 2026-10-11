"""Willow Bend joins the existing Meadow East return and diagonal streets."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_willow(root, existing_roads):
    data=json.loads((root/'meadow-east-parcels.json').read_text(encoding='utf-8'))
    connections=[]
    for street in data['streets']:
        if street['id'] in ('meadow-return','meadow-diagonal'):
            points=np.asarray(street['controls'])/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
            connections.append(curve(points))
    return compile_district(root,'willow-bend',existing_roads,connections)
