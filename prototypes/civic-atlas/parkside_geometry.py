"""Parkside North continues the existing Meadow East diagonal street."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_parkside(root, existing_roads):
    data=json.loads((root/'meadow-east-parcels.json').read_text(encoding='utf-8'))
    street=next(s for s in data['streets'] if s['id']=='meadow-diagonal')
    points=np.asarray(street['controls'])/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
    return compile_district(root,'parkside-north',existing_roads,[curve(points)])
