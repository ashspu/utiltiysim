"""Author a faithful SVG reference, landscape polygons and reviewed parcel draft.

Optional authoring dependencies: scikit-image, vtracer. Never used by a server.
The visual trace is explicitly not an authoritative property/utility dataset.
Only individually authored parcels receive existing premise IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import vtracer
from garden_geometry import compile_garden
from hazel_geometry import compile_hazel
from market_geometry import compile_market
from meadow_east_geometry import compile_meadow_east
from meadow_geometry import compile_meadow
from parkside_geometry import compile_parkside
from PIL import Image
from property_details import physical_details
from riverside_geometry import compile_riverside
from scipy.interpolate import CubicSpline
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union
from skimage import measure, morphology
from south_geometry import compile_south
from willow_geometry import compile_willow

ROOT = Path(__file__).parent / 'web/presets/riverbend-500'
NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', NS[1:-1])


def path(poly):
    return ' '.join('M '+' L '.join(f'{x:.3f},{y:.3f}' for x,y in ring.coords)+' Z'
                    for ring in [poly.exterior, *poly.interiors])


def element(parent, tag, **attrs):
    return ET.SubElement(parent, NS+tag, {k.replace('_','-'):str(v) for k,v in attrs.items()})


def roof_shading(group, model):
    for face in model['faces']:
        # Consistent directional shading from the same planes used in 3D.
        a,b,_=face['plane']
        normal=np.array([-a/1.35,-b/1.35,1.0])
        normal/=np.linalg.norm(normal)
        light=np.array([-.45,-.55,1.0])
        light/=np.linalg.norm(light)
        tone=int(126+50*float(np.dot(normal,light)))
        color=f'#{tone:02x}{min(255,tone+6):02x}{max(0,tone-6):02x}'
        element(group,'path',d=path(Polygon(face['polygon'])),fill=color,pointer_events='none',data_roof_type=model['type'])
    for seam in model['seams']:
        element(group,'polyline',points=' '.join(f'{x:.3f},{y:.3f}' for x,y,_ in seam),
                fill='none',stroke='#7d8979',stroke_width='.22',pointer_events='none')


def landscape():
    rgb = np.asarray(Image.open(ROOT/'concept.png').convert('RGB')).astype(float)
    r,g,b = rgb.transpose(2,0,1)
    masks = {
        'field': (r>178)&(g>160)&(b>115)&(r>g+5)&(g>b+14)&(r-g<45)&(r-b<92),
        'woodland': (g>r+5)&(g>b+12)&(r<173)&(g<191)&(b<150),
        'greenspace': (g>r-8)&(g>160)&(r>145)&(g>b+35)&(r-b>30),
        'water': (b>r+22)&(g>r+13)&(r<153)&(b>150)&(b-g<38),
    }
    features=[]
    for kind,mask in masks.items():
        # Keep field-dividing hedges; only close subpixel painting gaps.
        mask=morphology.closing(mask,morphology.disk(1))
        mask=morphology.remove_small_holes(mask,max_size=35 if kind=='field' else 65)
        labels=measure.label(mask)
        minimum={'field':550,'woodland':130,'greenspace':180,'water':65}[kind]
        for region in measure.regionprops(labels):
            if region.area<minimum:
                continue
            y0,x0,_,_=region.bbox
            contours=measure.find_contours(np.pad(region.image,1),.5)
            rings=[Polygon(c[:,::-1]+[x0-1,y0-1]).buffer(0) for c in contours]
            rings=[p for p in rings if p.geom_type=='Polygon' and p.area>3]
            if not rings:
                continue
            exterior=max(rings,key=lambda p:p.area)
            holes=[p for p in rings if p!=exterior and exterior.covers(p.representative_point())]
            shape=exterior.difference(unary_union(holes)).simplify(.55,preserve_topology=True)
            for poly in getattr(shape,'geoms',[shape]):
                if poly.geom_type!='Polygon' or poly.area<minimum:
                    continue
                features.append({'id':f'{kind}-{sum(f["kind"]==kind for f in features)+1:03d}',
                                 'kind':kind,'polygon':list(poly.exterior.coords),
                                 'holes':[list(r.coords) for r in poly.interiors],
                                 'areaM2':round(poly.area*1.35**2,2),'source':'approved concept color boundary'})
    review=json.loads((ROOT/'landscape-review.json').read_text(encoding='utf-8'))
    if review['sourceSha256']!=hashlib.sha256((ROOT/'concept.png').read_bytes()).hexdigest():
        raise ValueError('Landscape classification review belongs to a different reference image')
    indexed={feature['id']:feature for feature in features}
    for exclusion in review['exclusions']:
        feature=indexed.get(exclusion['id'])
        if (not feature or feature['kind']!=exclusion['kind']
                or not np.allclose(Polygon(feature['polygon']).bounds,exclusion['bounds'],atol=1e-7,rtol=0)):
            raise ValueError(f'Landscape review no longer matches extracted boundary: {exclusion["id"]}')
        del indexed[exclusion['id']]
    # Filter after assigning IDs so reviewed exclusions never renumber other land.
    return list(indexed.values())


def orchard_street():
    controls=np.array([[238,360],[252,310],[275,247],[298,185],[321,153],[341,146],
        [383,147],[440,155],[500,174],[550,194],[600,225],[628,248],[644,265],
        [622,300],[595,355],[570,410],[552,469],[490,458],[420,438],
        [350,418],[280,396],[247,380],[238,360]],dtype=float)/3+[230,45]
    t=np.r_[0,np.cumsum(np.linalg.norm(np.diff(controls,axis=0),axis=1))]
    curve=LineString(CubicSpline(t,controls,bc_type='periodic')(np.linspace(0,t[-1],800)))
    branches=[LineString(np.array([[0,295],[110,331],[238,360]])/3+[230,45])]
    return curve,unary_union([curve.buffer(5.3),*[p.buffer(5.3) for p in branches]])


def parcels():
    authored=json.loads((ROOT/'orchard-parcels.json').read_text())
    snapshot=json.loads((ROOT/'snapshot.json').read_text())
    homes=[p for p in snapshot['premises'] if p['premiseType']=='residential']
    target=np.array([np.array(lot[2])/3+[230,45] for lot in authored['lots']])
    identities=json.loads((ROOT/'orchard-identity-map.json').read_text())['properties']
    home_indices={p['id']:i for i,p in enumerate(homes)}
    indices=range(len(authored['lots']))
    assigned=[home_indices[identities[lot[0]]] for lot in authored['lots']]
    bindings={p['premiseId']:p for p in json.loads((ROOT/'bindings.json').read_text())['properties']}
    result=[]
    centerline,street=orchard_street()
    frontage_indices=[[2,3],[2,3],[2,3],[2,3,4],[3,4],[2,3,4],[2,3],[3,4],[2,3],
        [2,3],[2,3,4],[4,5],[4,5,0],[3,0],[4,0],[4,5,0,1,2],[0,1],[0,1],
        [0,1],[0,1,2,3,4],[1,2],[0,1,2,3],[0,1],[0,1],[0,1],[0,1,2,3,4],[0,1],[0,1,2]]
    for i,j in zip(indices,assigned,strict=True):
        key,coords,center,width,depth,heading,front=authored['lots'][i]
        global_coords=np.array(coords,dtype=float)/3+[230,45]
        for vertex in frontage_indices[i]:
            global_coords[vertex]=nearest_points(Point(global_coords[vertex]),centerline)[1].coords[0]
        global_lot=Polygon(global_coords).buffer(0).difference(street)
        if global_lot.geom_type!='Polygon':
            raise ValueError(f'Curved frontage splits lot {key}')
        lot=affinity.scale(affinity.translate(global_lot,-230,-45),3,3,origin=(0,0))
        # Explicitly varied rectangle/L footprints, with an authored position
        # and orientation for every lot. No lot subdivision generator is used.
        if i%4==0:
            footprint=Polygon([(-.5,-.5),(.5,-.5),(.5,.1),(.14,.1),(.14,.5),(-.5,.5)])
        else:
            footprint=Polygon([(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)])
        footprint=affinity.scale(footprint,xfact=width,yfact=depth,origin=(0,0))
        footprint=affinity.rotate(footprint,heading,origin=(0,0))
        footprint=affinity.translate(footprint,*center)
        if not lot.buffer(-1).covers(footprint):
            raise ValueError(f'Footprint leaves authored lot {key}')
        shared=global_lot.boundary.intersection(street.boundary)
        if shared.length<.1:
            raise ValueError(f'No street frontage for {key}')
        global_front=nearest_points(Point(np.array(front)/3+[230,45]),shared)[1]
        front_point=Point((np.array(global_front.coords[0])-[230,45])*3)
        driveway=LineString([center,front_point.coords[0]]).buffer(3.4,cap_style=2).intersection(lot)
        def image_poly(poly):
            return [[x/3+230,y/3+45] for x,y in poly.exterior.coords]
        identity=homes[j]['id']
        result.append({'id':key,'district':'Orchard','premiseId':identity,'binding':bindings[identity],
                       'polygon':image_poly(lot),'footprint':image_poly(footprint),
                       'driveway':image_poly(driveway),'center':target[i].tolist(),
                       'frontage':(np.array(front_point.coords[0])/3+[230,45]).tolist(),
                       'heading':heading,'heightM':5.8+(i%3)*1.1,
                       'status':'Authored geometry draft; linked live identity; no migration applied'})
    for i,a in enumerate(result):
        for b in result[i+1:]:
            if Polygon(a['polygon']).intersection(Polygon(b['polygon'])).area>.001:
                raise ValueError(f'Overlapping parcels: {a["id"]}/{b["id"]}')
    return result


def trace_reference(destination):
    """Broad vector color shapes plus retained fine contour linework.

    The small-area contour cutoff applies only to this visual overlay. A full
    vector underpainting remains underneath, so it cannot create empty holes.
    Semantic landscape/parcel geometry is authored separately.
    """
    vtracer.convert_image_to_svg_py(str(ROOT/'concept.png'),str(destination),colormode='color',
        hierarchical='stacked',mode='polygon',filter_speckle=1,color_precision=6,layer_difference=4,
        corner_threshold=60,length_threshold=1,max_iterations=10,splice_threshold=45,path_precision=2)
    svg=ET.parse(destination).getroot()
    image=Image.open(ROOT/'concept.png').convert('RGB').quantize(colors=128,
        method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
    labels=np.asarray(image)
    palette=image.getpalette()
    for color_index in range(128):
        contours=measure.find_contours(np.pad(labels==color_index,1),.5,fully_connected='high')
        paths=[]
        for ring in contours:
            points=ring[:-1,::-1]-.5
            before=points-np.roll(points,1,axis=0)
            after=np.roll(points,-1,axis=0)-points
            cross=before[:,0]*after[:,1]-before[:,1]*after[:,0]
            points=points[np.abs(cross)>.01]
            if len(points)<3:
                continue
            area=abs(np.dot(points[:,0],np.roll(points[:,1],1))-np.dot(points[:,1],np.roll(points[:,0],1)))/2
            if area<.75:
                continue
            paths.append('M'+' L'.join(f'{x:g},{y:g}' for x,y in points)+' Z')
        fill='#'+''.join(f'{v:02x}' for v in palette[color_index*3:color_index*3+3])
        element(svg,'path',d=' '.join(paths),fill=fill,fill_rule='evenodd',stroke=fill,
                stroke_width='.7',stroke_linejoin='round')
    ET.ElementTree(svg).write(destination,encoding='utf-8',xml_declaration=True)


def bake(retrace=False):
    raw=ROOT/'reference-trace.svg'
    if retrace or not raw.exists():
        trace_reference(raw)
    svg=ET.parse(raw).getroot()
    svg.set('viewBox','0 0 1536 1024')
    svg.set('width','100%')
    svg.set('height','100%')
    svg.set('data-status','Visual reconstruction with separately identified semantic draft layers')
    children=list(svg)
    svg[:]=[]
    artwork=element(svg,'g',id='reference-artwork',pointer_events='none')
    for child in children:
        artwork.append(child)
    fields=landscape()
    farm_buildings=json.loads((ROOT/'farm-buildings.json').read_text(encoding='utf-8'))['buildings']
    for building in farm_buildings:
        shape=Polygon(building['polygon'])
        if not shape.is_valid or shape.area<=0:
            raise ValueError(f'Invalid farm building {building["id"]}')
        building['areaM2']=round(shape.area*1.35**2,2)
    lots=parcels()
    orchard_line,orchard_road=orchard_street()
    garden_lots,road,pedestrian_paths,garden_greens=compile_garden(ROOT,orchard_line,orchard_road)
    hazel_lots,road,hazel_paths,hazel_greens,hazel_access=compile_hazel(ROOT,road)
    market_lots,road,market_paths,market_greens,market_access=compile_market(ROOT,road)
    riverside_lots,road,riverside_paths,riverside_greens,riverside_access=compile_riverside(ROOT,road)
    meadow_lots,road,meadow_paths,meadow_greens,meadow_access=compile_meadow(ROOT,road)
    meadow_east_lots,road,meadow_east_paths,meadow_east_greens,meadow_east_access=compile_meadow_east(ROOT,road)
    parkside_lots,road,parkside_paths,parkside_greens,parkside_access=compile_parkside(ROOT,road)
    willow_lots,road,willow_paths,willow_greens,willow_access=compile_willow(ROOT,road)
    south_lots,road,south_paths,south_greens,south_access=compile_south(ROOT,road)
    shared_access=[*hazel_access,*market_access,*riverside_access,*meadow_access,*meadow_east_access,*parkside_access,*willow_access,*south_access]
    pedestrian_paths=unary_union([pedestrian_paths,hazel_paths,market_paths,riverside_paths,meadow_paths,meadow_east_paths,parkside_paths,willow_paths,south_paths]).difference(road)
    lots.extend(garden_lots)
    lots.extend(hazel_lots)
    lots.extend(market_lots)
    lots.extend(riverside_lots)
    lots.extend(meadow_lots)
    lots.extend(meadow_east_lots)
    lots.extend(parkside_lots)
    lots.extend(willow_lots)
    lots.extend(south_lots)
    fields.extend(garden_greens)
    fields.extend(hazel_greens)
    fields.extend(market_greens)
    fields.extend(riverside_greens)
    fields.extend(meadow_greens)
    fields.extend(meadow_east_greens)
    fields.extend(parkside_greens)
    fields.extend(willow_greens)
    fields.extend(south_greens)
    physical_details(ROOT,lots)
    for i,a in enumerate(lots):
        if Polygon(a['polygon']).intersection(road).area>1e-7:
            raise ValueError(f'Road crosses {a["id"]}')
        for b in lots[i+1:]:
            if Polygon(a['polygon']).intersection(Polygon(b['polygon'])).area>1e-7:
                raise ValueError(f'Overlapping districts: {a["id"]}/{b["id"]}')
    terrain=element(svg,'g',id='landscape-features',fill='transparent',stroke='none')
    for f in fields:
        poly=Polygon(f['polygon'],f['holes'])
        e=element(terrain,'path',id=f['id'],d=path(poly),fill_rule='evenodd',data_landscape_id=f['id'],
                  data_kind=f['kind'],fill='transparent' if f.get('renderTexture') else f.get('renderFill','transparent'),
                  data_base_fill='' if f.get('renderTexture') else f.get('renderFill',''),
                  tabindex='0',role='button',aria_label=f'{f["kind"]} {f["id"]}')
        element(e,'title').text=f'{f["id"]} · {f["areaM2"]/10000:.2f} hectares · traced boundary'
    farms=element(svg,'g',id='farm-buildings')
    for building in farm_buildings:
        e=element(farms,'path',id=building['id'],d=path(Polygon(building['polygon'])),
                  fill='#a6ad96',stroke='#747d69',stroke_width='.45',data_farm_id=building['id'],
                  tabindex='0',role='button',aria_label=f'Farm building {building["id"]}')
        element(e,'title').text=f'{building["id"]} · traced footprint; no linked utility record'
    district=element(svg,'g',id='authored-properties')
    # Exactly the same curb geometry trims parcels and renders the street.
    element(district,'path',id='study-street-curb',d=path(road),fill='#f3f1e7',fill_rule='evenodd')
    asphalt=road.buffer(-.9,join_style=1)
    element(district,'path',id='study-street-surface',d=path(asphalt),fill='#bcc2c4',fill_rule='evenodd')
    for lane in shared_access:
        element(district,'path',id=lane['id'],d=path(Polygon(lane['polygon'],lane['holes'])),
                fill='#dedbd0',stroke='#bbbfae',stroke_width='.2',data_access_id=lane['id'])
    for j,part in enumerate(getattr(pedestrian_paths,'geoms',[pedestrian_paths])):
        element(district,'path',id=f'garden-path-{j}',d=path(part),fill='#d7d4bd',stroke='#99a084',stroke_width='.18')
    garden_centers=[[178,310],[205,244],[227,195],[234,147],[252,96],[365,72],[415,83],
                    [499,85],[564,124],[617,151],[670,176],[721,211],[710,319],[679,368],
                    [649,422],[347,214],[394,229],[453,281],[475,301],[546,310],[517,317],
                    [509,435],[465,345],[410,338],[374,324],[303,361],[290,290],[358,264]]
    # Ground, parcel/driveway and roof are real independent vectors. Lines on
    # neighboring lots share the same authored coordinates.
    for i,p in enumerate(lots):
        group=element(district,'g',id='draft-'+p['id'],data_premise_id=p['premiseId'])
        element(group,'path',d=path(Polygon(p['polygon'])),fill=['#f3e98f','#eee78c','#f2ea95'][i%3],
                stroke='#989668',stroke_width='.43',stroke_linejoin='round',data_parcel_id=p['binding']['parcelId'])
        element(group,'path',d=path(Polygon(p['driveway'])),fill='#eeeadd',stroke='#d5d3be',stroke_width='.12')
        shape=Polygon(p['footprint'])
        if p['pool']:
            element(group,'path',d=path(Polygon(p['pool'])),fill='#89c5d2',stroke='#eee9d4',
                    stroke_width='.45',data_feature='recorded-pool')
        gx,gy=p.get('gardenCenter',np.array(garden_centers[i])/3+[230,45]) if i<28 else p['gardenCenter']
        garden=Point(gx,gy).buffer(1.35+(i%3)*.25)
        p['gardenTrees']=[]
        pool=Polygon(p['pool']) if p['pool'] else Polygon()
        if Polygon(p['polygon']).buffer(-.5).covers(garden) and not shape.buffer(.7).intersects(garden) and not pool.buffer(.4).intersects(garden):
            p['gardenTrees'].append({'center':[float(gx),float(gy)],'radius':1.35+(i%3)*.25})
            element(group,'ellipse',cx=gx+.35,cy=gy+.45,rx=1.9,ry=1.45,fill='#6c8059',opacity='.22')
            element(group,'path',d=path(garden),fill='#a8bd7e',stroke='#859e69',stroke_width='.2')
            element(group,'circle',cx=gx-.45,cy=gy-.45,r=1,fill='#bed091',opacity='.8')
        shadow=affinity.translate(shape,xoff=.75,yoff=.85)
        element(group,'path',d=path(shadow),fill='#737c65',opacity='.27',pointer_events='none')
        roof=element(group,'path',id=p['binding']['buildingId'],d=path(shape),fill=['#a3a69a','#979e94','#aab0a1','#b4b1a0'][i%4],
                     stroke='#707c70',stroke_width='.45',stroke_linejoin='round',data_premise_id=p['premiseId'],
                     tabindex='0',role='button',aria_label=f'Draft {p["id"]}, linked property {p["premiseId"]}')
        element(roof,'title').text=f'{p["id"]} · {p["binding"]["address"]} · {p["premiseId"]}'
        roof_shading(group,p['roofModel'])
        for panel in p['solarPanels']:
            element(group,'path',d=path(Polygon(panel)),fill='#42677c',stroke='#b3c9c8',
                    stroke_width='.10',data_feature='recorded-solar')
        for accessory in p['outbuildings']:
            roof=element(group,'path',id=accessory['id'],d=path(Polygon(accessory['footprint'])),
                         fill='#a3a89a',stroke='#707c70',stroke_width='.4',tabindex='0',role='button',
                         data_owner_premise_id=p['premiseId'],aria_label=f'Outbuilding belonging to {p["id"]}')
            element(roof,'title').text=f'Accessory of {p["premiseId"]}; not a separate customer'
            roof_shading(group,accessory['roofModel'])
    style=element(svg,'style')
    style.text='[data-farm-id]{cursor:pointer}[data-farm-id]:hover{fill:#d3aa77}[data-landscape-id]{cursor:crosshair}[data-landscape-id]:hover{fill:#f6fff530;stroke:#315b47;stroke-width:1}[data-premise-id][role]{cursor:pointer}[data-premise-id][role]:hover{fill:#ef956c} .selected{stroke:#c75c39!important;stroke-width:1.1!important}'
    ET.ElementTree(svg).write(ROOT/'reconstruction.svg',encoding='utf-8',xml_declaration=True)
    data={'schemaVersion':'civic-atlas-reconstruction/3','status':'Visual and semantic authoring draft; not loaded into the saved world',
          'sourceSha256':hashlib.sha256((ROOT/'concept.png').read_bytes()).hexdigest(),
          'scaleMPerPixel':1.35,'viewBox':[0,0,1536,1024], 'reviewBounds':[185,39,672,816],
          'landscape':fields,'farmBuildings':farm_buildings,'properties':lots,'sharedAccess':shared_access,
          'districts':[{'id':'orchard','name':'Orchard','count':28,'viewBox':[255,39,243,177]},
                       {'id':'garden','name':'Garden','count':len(garden_lots),'viewBox':[217,146,252,212]},
                       {'id':'hazel','name':'Hazel','count':len(hazel_lots),'viewBox':[227,269,200,160]},
                       {'id':'market-north','name':'Market North','count':len(market_lots),'viewBox':[404,298,197,206]},
                       {'id':'riverside-west','name':'Riverside West','count':len(riverside_lots),'viewBox':[564,327,78,148]},
                       {'id':'meadow-west','name':'Meadow West','count':len(meadow_lots),'viewBox':[182,390,235,242]},
                       {'id':'meadow-east','name':'Meadow East','count':len(meadow_east_lots),'viewBox':[370,457,215,225]},
                       {'id':'parkside-north','name':'Parkside North','count':len(parkside_lots),'viewBox':[467,519,248,169]},
                       {'id':'willow-bend','name':'Willow Bend','count':len(willow_lots),'viewBox':[335,603,227,207]},
                       {'id':'south-village','name':'South Village','count':len(south_lots),'viewBox':[488,681,364,170]}],
          'streetEnvelope':{'polygon':list(road.exterior.coords),'holes':[list(r.coords) for r in road.interiors]},
          'streetSurface':{'polygon':list(asphalt.exterior.coords),'holes':[list(r.coords) for r in asphalt.interiors]},
          'pedestrianPaths':[{'polygon':list(p.exterior.coords),'holes':[list(r.coords) for r in p.interiors]} for p in getattr(pedestrian_paths,'geoms',[pedestrian_paths])],
          'coverage':{'visualArtwork':'Whole approved image, including hedgerows, paths and farm buildings',
                      'farmBuildings':len(farm_buildings),'semanticProperties':len(lots),'unreviewedProperties':500-len(lots),
                      'landscape':'Color-extracted boundaries; draft classification needs review'}}
    (ROOT/'reconstruction.json').write_text(json.dumps(data,indent=2))
    geo={'type':'FeatureCollection','features':[{'type':'Feature','id':f['id'],
        'properties':{k:v for k,v in f.items() if k not in ('polygon','holes')},
        'geometry':{'type':'Polygon','coordinates':[f['polygon'],*f['holes']]}} for f in fields]}
    geo['coordinateSystem']='Local image pixels, x east / y south; 1.35 metres per pixel; not geographic coordinates'
    (ROOT/'landscape.geojson').write_text(json.dumps(geo,indent=2))
    print(json.dumps({'authoredProperties':len(lots),'landscape':{k:sum(f['kind']==k for f in fields) for k in ('field','woodland','greenspace','water')},
                      'svgBytes':(ROOT/'reconstruction.svg').stat().st_size,'rasterImages':len(svg.findall('.//'+NS+'image'))}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrace',action='store_true',help='Rebuild the full visual reference from the approved concept')
    bake(retrace=parser.parse_args().retrace)
