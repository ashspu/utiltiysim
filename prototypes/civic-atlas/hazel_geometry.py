"""Hazel joins the previously authored Garden street."""
import json

import numpy as np
from district_geometry import compile_district, curve


def compile_hazel(root, existing_roads):
    data=json.loads((root/'garden-parcels.json').read_text(encoding='utf-8'))
    controls=np.asarray(data['streetControls'])/data['coordinateSystem']['pixelsPerImagePixel']+data['coordinateSystem']['origin']
    return compile_district(root,'hazel',existing_roads,[curve(controls)])
