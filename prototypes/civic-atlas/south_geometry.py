"""South Village extends Willow Bend and the existing riverside approach."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_south(root, existing_roads):
    connections=[]
    for name,ids in [('willow-bend',('willow-outer-lane','laurel-lane')),
                     ('parkside-north',('parkside-east',))]:
        data=json.loads((root/f'{name}-parcels.json').read_text(encoding='utf-8'))
        for street in data['streets']:
            if street['id'] in ids:
                points=np.asarray(street['controls'])/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
                connections.append(curve(points))
    return compile_district(root,'south-village',existing_roads,connections)
