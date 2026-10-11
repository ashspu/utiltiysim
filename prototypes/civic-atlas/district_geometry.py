"""Compile explicit traced district geometry; never generate or subdivide lots at runtime."""
import json

import numpy as np
from scipy.interpolate import CubicSpline
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union


def curve(points):
    t=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    return LineString(CubicSpline(t,points,bc_type='natural')(np.linspace(0,t[-1],700)))


def compile_district(root, name, existing_roads, connections):
    data=json.loads((root/f'{name}-parcels.json').read_text())
    scale=data['coordinateSystem']['pixelsPerImagePixel']
    origin=np.array(data['coordinateSystem']['origin'])
    def xy(points):
        return np.asarray(points,dtype=float)/scale+origin
    lines=[curve(xy(street['controls'])) for street in data['streets']]
    network=unary_union([*connections,*lines])
    roads=unary_union([existing_roads,*[line.buffer(street['width'],cap_style=2)
        for line,street in zip(lines,data['streets'],strict=True)],
        *[Point(xy(bulb['center'])).buffer(bulb['radius'],quad_segs=32) for bulb in data['bulbs']]])
    paths=unary_union([LineString(xy(points)).buffer(.9,cap_style=2) for points in data['paths']])
    access_lines={lane['id']:LineString(xy(lane['controls'])) for lane in data.get('accessLanes',[])}
    access_land={lane['id']:access_lines[lane['id']].buffer(lane['widthM']/1.35/2,cap_style=2).difference(roads) for lane in data.get('accessLanes',[])}
    all_access=unary_union(list(access_land.values()))
    locks=json.loads((root/f'{name}-identity-map.json').read_text())['properties']
    bindings={p['premiseId']:p for p in json.loads((root/'bindings.json').read_text())['properties']}
    result=[]
    failures=[]
    for i,row in enumerate(data['lots']):
        key,coords,center,width,depth,heading,front,front_indices,kind,garden=row
        access_id=data.get('frontageLinks',{}).get(key)
        frontage_network=access_lines[access_id] if access_id else network
        frontage_surface=access_land[access_id] if access_id else roads
        coords=xy(coords)
        for vertex in front_indices:
            coords[vertex]=nearest_points(Point(coords[vertex]),frontage_network)[1].coords[0]
        lot=Polygon(coords).buffer(0).difference(roads).difference(paths).difference(all_access)
        if lot.geom_type!='Polygon':
            failures.append(f'{key}: parcel split by access geometry')
            continue
        unit=Polygon([(-.5,-.5),(.5,-.5),(.5,.1),(.14,.1),(.14,.5),(-.5,.5)] if kind=='L'
                     else [(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)])
        footprint=affinity.scale(unit,width/scale,depth/scale,origin=(0,0))
        footprint=affinity.rotate(footprint,heading,origin=(0,0))
        footprint=affinity.translate(footprint,*xy(center))
        if not lot.buffer(-1/scale).covers(footprint):
            failures.append(f'{key}: footprint outside setback at {((np.array(footprint.difference(lot.buffer(-1/scale)).bounds).reshape(2,2)-origin)*scale).tolist()}')
        # A micron tolerance retains straight shared-drive edges after GEOS noding.
        shared=lot.boundary.intersection(frontage_surface.buffer(1e-8) if access_id else frontage_surface.boundary)
        if shared.length<.1:
            failures.append(f'{key}: missing road frontage')
            continue
        frontage=nearest_points(Point(xy(front)),shared)[1]
        driveway=LineString([xy(center),frontage.coords[0]]).buffer(3.4/scale,cap_style=2).intersection(lot)
        if driveway.geom_type!='Polygon':
            failures.append(f'{key}: disconnected driveway')
            continue
        result.append({'id':key,'district':data['district'],'premiseId':locks[key],'binding':bindings[locks[key]],
            'polygon':list(lot.exterior.coords),'footprint':list(footprint.exterior.coords),
            'driveway':list(driveway.exterior.coords),'center':xy(center).tolist(),
            'frontage':list(frontage.coords[0]),'heading':heading,'heightM':5.8+(i%3)*1.1,
            'gardenCenter':xy(garden).tolist(),
            'accessType':'shared-drive' if access_id else 'public-street','accessId':access_id,
            'status':'Authored geometry draft; linked live identity; no migration applied'})
    if failures:
        raise ValueError('\n'.join(failures))
    greens=[]
    for site in data['openSpaces']:
        polygon=Polygon(xy(site['polygon']))
        if site.get('clipToBlock'):
            polygon=polygon.difference(unary_union([roads,paths,*[Polygon(p['polygon']) for p in result]]))
            if polygon.geom_type!='Polygon':
                raise ValueError(f'Open space split by block boundaries: {site["id"]}')
        greens.append({**site,'polygon':list(polygon.exterior.coords),'holes':[list(ring.coords) for ring in polygon.interiors],
                       'areaM2':round(polygon.area*1.35**2,2),'renderFill':site.get('renderFill','#b2c68a')})
    access=[]
    for lane in data.get('accessLanes',[]):
        shape=access_land[lane['id']]
        if shape.geom_type!='Polygon' or shape.distance(roads)>1e-7:
            raise ValueError(f'Shared access is disconnected: {lane["id"]}')
        access.append({**lane,'polygon':list(shape.exterior.coords),'holes':[list(r.coords) for r in shape.interiors],
                       'centerline':list(access_lines[lane['id']].coords),
                       'premiseIds':[p['premiseId'] for p in result if p['accessId']==lane['id']]})
    return result,roads,paths,greens,access
