"""Meadow West extends the existing Market Street and Old Farm Road geometry."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_meadow(root, existing_roads):
    data=json.loads((root/'hazel-parcels.json').read_text(encoding='utf-8'))
    connections=[]
    for street in data['streets']:
        if street['id'] in ('market-west','old-farm-extension'):
            points=np.asarray(street['controls'])/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
            connections.append(curve(points))
    return compile_district(root,'meadow-west',existing_roads,connections)
