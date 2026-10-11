"""Connect Meadow East to the locked Market and Meadow West streets."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_meadow_east(root, existing_roads):
    connections=[]
    for name,street_id in [('market-north','market-east'),('meadow-west','meadow-east-lane')]:
        data=json.loads((root/f'{name}-parcels.json').read_text(encoding='utf-8'))
        street=next(s for s in data['streets'] if s['id']==street_id)
        points=np.asarray(street['controls'])/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
        connections.append(curve(points))
    return compile_district(root,'meadow-east',existing_roads,connections)
