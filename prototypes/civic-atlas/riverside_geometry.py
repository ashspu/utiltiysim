"""Riverside lots use the exact Market North road and explicit shared drives."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_riverside(root, existing_roads):
    data=json.loads((root/'market-north-parcels.json').read_text(encoding='utf-8'))
    controls=next(s['controls'] for s in data['streets'] if s['id']=='school-road-east')
    points=np.asarray(controls)/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
    return compile_district(root,'riverside-west',existing_roads,[curve(points)])
