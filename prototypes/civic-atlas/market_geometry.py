"""Market North shares the exact existing Old Farm Road connection."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_market(root, existing_roads):
    data=json.loads((root/'hazel-parcels.json').read_text(encoding='utf-8'))
    controls=next(s['controls'] for s in data['streets'] if s['id']=='old-farm-extension')
    points=np.asarray(controls)/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
    return compile_district(root,'market-north',existing_roads,[curve(points)])
