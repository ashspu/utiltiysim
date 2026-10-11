"""Manually authored Garden district; no runtime or random lot generation."""
import json

import numpy as np
from scipy.interpolate import CubicSpline
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union


def compile_garden(root, orchard_line, orchard_road):
    data=json.loads((root/'garden-parcels.json').read_text())
    scale=data['coordinateSystem']['pixelsPerImagePixel']
    origin=np.array(data['coordinateSystem']['origin'])
    def xy(points):
        return np.asarray(points,dtype=float)/scale+origin
    controls=xy(data['streetControls'])
    t=np.r_[0,np.cumsum(np.linalg.norm(np.diff(controls,axis=0),axis=1))]
    line=LineString(CubicSpline(t,controls,bc_type='natural')(np.linspace(0,t[-1],900)))
    western_approach=LineString(xy([[0,295],[110,331],[238,360]]))
    network=unary_union([orchard_line,western_approach,line])
    roads=unary_union([orchard_road,line.buffer(5.3,cap_style=2)])
    paths=unary_union([LineString(xy(data[key])).buffer(.9,cap_style=2)
                      for key in ('pedestrianRoute','gardenPath','greenWalk')])
    locks=json.loads((root/'garden-identity-map.json').read_text())['properties']
    bindings={p['premiseId']:p for p in json.loads((root/'bindings.json').read_text())['properties']}
    result=[]
    failures=[]
    for i,row in enumerate(data['lots']):
        key,coords,center,width,depth,heading,front,front_indices,kind,garden=row
        coords=xy(coords)
        for vertex in front_indices:
            coords[vertex]=nearest_points(Point(coords[vertex]),network)[1].coords[0]
        lot=Polygon(coords).buffer(0).difference(roads).difference(paths)
        if lot.geom_type!='Polygon':
            failures.append(f'{key}: parcel split by access geometry')
            continue
        unit=Polygon([(-.5,-.5),(.5,-.5),(.5,.1),(.14,.1),(.14,.5),(-.5,.5)] if kind=='L'
                     else [(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)])
        footprint=affinity.scale(unit,width/scale,depth/scale,origin=(0,0))
        footprint=affinity.rotate(footprint,heading,origin=(0,0))
        footprint=affinity.translate(footprint,*xy(center))
        if not lot.buffer(-1/scale).covers(footprint):
            failures.append(f'{key}: footprint outside setback by {footprint.difference(lot.buffer(-1/scale)).area:.3f} px²')
        shared=lot.boundary.intersection(roads.boundary)
        if shared.length<.1:
            failures.append(f'{key}: missing road frontage')
            continue
        frontage=nearest_points(Point(xy(front)),shared)[1]
        driveway=LineString([xy(center),frontage.coords[0]]).buffer(3.4/scale,cap_style=2).intersection(lot)
        if driveway.geom_type!='Polygon':
            failures.append(f'{key}: disconnected driveway')
            continue
        result.append({'id':key,'district':'Garden','premiseId':locks[key],'binding':bindings[locks[key]],
            'polygon':list(lot.exterior.coords),'footprint':list(footprint.exterior.coords),
            'driveway':list(driveway.exterior.coords),'center':xy(center).tolist(),
            'frontage':list(frontage.coords[0]),'heading':heading,'heightM':5.8+(i%3)*1.1,
            'gardenCenter':xy(garden).tolist(),
            'status':'Authored geometry draft; linked live identity; no migration applied'})
    if failures:
        raise ValueError('\n'.join(failures))
    greens=[]
    for site in data['openSpaces']:
        polygon=Polygon(xy(site['polygon']))
        greens.append({**site,'polygon':list(polygon.exterior.coords),'holes':[],
                       'areaM2':round(polygon.area*1.35**2,2),'renderFill':'#b2c68a'})
    return result,roads,paths,greens
