"""Contracts for the editable reconstruction, separate from the saved world."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

ROOT=Path(__file__).parent/'web/presets/riverbend-500'


def source():
    return json.loads((ROOT/'reconstruction.json').read_text())


def test_authored_parcels_have_shared_boundaries_and_verified_access():
    data=source()
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    access=unary_union([street,*[Polygon(item['polygon'],item['holes']) for item in data['sharedAccess']]])
    shapes=[Polygon(p['polygon']) for p in data['properties']]
    neighbors=[0]*len(shapes)
    for i,lot in enumerate(shapes):
        assert lot.is_valid
        assert lot.intersection(access).area<1e-7
        assert lot.boundary.intersection(access.buffer(1e-8)).length>.1
        for j,other in enumerate(shapes[:i]):
            assert lot.intersection(other).area<1e-7
            if lot.boundary.intersection(other.boundary).length>1:
                neighbors[i]+=1
                neighbors[j]+=1
    assert min(neighbors)>=1


def test_houses_and_driveways_stay_in_lots_and_reach_their_access():
    data=source()
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    for p in data['properties']:
        lane=next((item for item in data['sharedAccess'] if item['id']==p.get('accessId')),None)
        access=Polygon(lane['polygon'],lane['holes']) if lane else street
        lot,roof,drive=(Polygon(p[k]) for k in ('polygon','footprint','driveway'))
        assert lot.buffer(1e-8).covers(roof)
        assert lot.buffer(1e-8).covers(drive)
        assert drive.distance(access)<1e-7
        assert Point(p['frontage']).distance(access.boundary)<1e-7


def test_identity_assignments_are_locked_and_reference_real_records():
    data=source()
    locks={}
    for name in ('orchard','garden','hazel','market-north','riverside-west','meadow-west','meadow-east','parkside-north','willow-bend'):
        locks.update(json.loads((ROOT/f'{name}-identity-map.json').read_text())['properties'])
    bindings={p['premiseId']:p for p in json.loads((ROOT/'bindings.json').read_text())['properties']}
    assert len({p['premiseId'] for p in data['properties']})==205
    for p in data['properties']:
        assert p['premiseId']==locks[p['id']]
        assert p['binding']==bindings[p['premiseId']]
    assert data['coverage']['unreviewedProperties']==295


def test_landscape_is_separate_vector_geometry_including_fields():
    features=source()['landscape']
    assert len({f['id'] for f in features})==len(features)
    assert sum(f['kind']=='field' for f in features)==31
    fields=unary_union([Polygon(f['polygon'],f['holes']) for f in features if f['kind']=='field'])
    assert all(Polygon(p['polygon']).intersection(fields).area<1e-7 for p in source()['properties'])
    assert 'field-013' not in {f['id'] for f in features}
    assert {'woodland','water','greenspace'}<={f['kind'] for f in features}
    for f in features:
        shape=Polygon(f['polygon'],f['holes'])
        assert shape.is_valid and shape.area>0
        assert abs(shape.area*1.35**2-f['areaM2'])<.011


def test_saved_reconstruction_svg_contains_vectors_not_a_raster_wrapper():
    svg=ET.parse(ROOT/'reconstruction.svg').getroot()
    assert not any(e.tag.endswith('image') for e in svg.iter())
    assert len([e for e in svg.iter() if e.get('data-premise-id') and e.get('role')=='button'])==205
    ids={e.get('id') for e in svg.iter()}
    assert all(p['binding']['buildingId'] in ids for p in source()['properties'])


def test_physical_details_follow_locked_records_and_fit_the_new_sites():
    original={p['id']:p for p in json.loads((ROOT/'snapshot.json').read_text())['premises']}
    properties=source()['properties']
    for p in properties:
        record=original[p['premiseId']]
        assert p['heightM']==record['height']
        assert all(value==record[key] for key,value in p['physical'].items())
        assert bool(p['solarPanels'])==record['solar']
        assert bool(p['pool'])==record['hasPool']
        for panel in p['solarPanels']:
            assert Polygon(p['footprint']).covers(Polygon(panel))
        if p['pool']:
            pool=Polygon(p['pool'])
            assert Polygon(p['polygon']).covers(pool)
            assert not pool.intersects(Polygon(p['footprint']))
            assert not pool.intersects(Polygon(p['driveway']))
            for tree in p['gardenTrees']:
                assert not Point(tree['center']).buffer(tree['radius']).intersects(pool)
    assert sum(bool(p['solarPanels']) for p in properties)==28
    assert sum(bool(p['pool']) for p in properties)==2


def test_garden_green_has_walk_access_and_does_not_take_private_lots():
    data=source()
    walks=unary_union([Polygon(p['polygon'],p['holes']) for p in data['pedestrianPaths']])
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    green=next(p for p in data['landscape'] if p['id']=='garden-green-01')
    space=Polygon(green['polygon'])
    assert all(part.is_valid and part.distance(street)<1e-7 for part in getattr(walks,'geoms',[walks]))
    assert walks.intersects(street)
    assert walks.intersects(space)
    assert all(space.intersection(Polygon(p['polygon'])).area<1e-7 for p in data['properties'])


def test_farm_buildings_are_separate_valid_shapes_without_invented_customers():
    data=source()
    farms=data['farmBuildings']
    assert len(farms)==31
    assert len({f['id'] for f in farms})==31
    shapes=[]
    for f in farms:
        shape=Polygon(f['polygon'])
        assert shape.is_valid and shape.area>10
        assert abs(shape.area*data['scaleMPerPixel']**2-f['areaM2'])<.011
        assert f['premiseId'] is None
        assert 'illustrative' in f['heightSource']
        assert all(shape.intersection(other).area<1e-7 for other in shapes)
        shapes.append(shape)
    svg=ET.parse(ROOT/'reconstruction.svg').getroot()
    assert {e.get('data-farm-id') for e in svg.iter() if e.get('data-farm-id')}=={f['id'] for f in farms}


def test_hazel_culdesac_and_woodland_walk_follow_the_authored_plan():
    data=source()
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    bulb=Point(205+249/4,270+263/4).buffer(8.3)
    assert street.is_valid and street.covers(bulb)
    homes=[p for p in data['properties'] if p['district']=='Hazel']
    assert len(homes)==18
    green=next(f for f in data['landscape'] if f['id']=='hazel-wood-01')
    assert green['renderTexture'] is True
    space=Polygon(green['polygon'])
    walks=unary_union([Polygon(p['polygon'],p['holes']) for p in data['pedestrianPaths']])
    assert walks.intersects(space)
    assert all(space.intersection(Polygon(p['polygon'])).area<1e-7 for p in data['properties'])


def test_market_street_follows_reference_asphalt_centers():
    data=source()
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    # Independently sampled asphalt centers in the approved concept image.
    # The previous trace followed the upper curb, roughly eight pixels north.
    for center in [(243,394),(279,408),(358,439)]:
        assert street.buffer(-4).covers(Point(center))
    assert len([p for p in data['properties'] if p['district']=='Market North'])==28


def test_footpaths_end_at_curbs_without_projecting_into_traffic():
    data=source()
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    for p in data['pedestrianPaths']:
        walk=Polygon(p['polygon'],p['holes'])
        assert walk.intersection(street).area<1e-7
        assert walk.distance(street)<1e-7


def test_roof_planes_cover_footprints_and_meet_without_cracks():
    import math
    from collections import Counter

    from roof_geometry import height
    data=source()
    original={p['id']:p for p in json.loads((ROOT/'snapshot.json').read_text()).get('premises')}
    assert Counter(p['roofModel']['type'] for p in data['properties'])==Counter(original[p['premiseId']]['roof'] for p in data['properties'])
    for p in data['properties']:
        model=p['roofModel']
        assert model['type']==p['physical']['roof']
        assert model['eaveHeightM']==p['heightM']
        assert abs(model['peakHeightM']-p['heightM']-model['riseM'])<1e-6
        assert bool(model['gableTriangles'])==(model['type']=='gable')
        faces=[Polygon(f['polygon']) for f in model['faces']]
        roof=unary_union(faces)
        assert roof.symmetric_difference(Polygon(p['footprint'])).area<1e-5
        assert abs(sum(f.area for f in faces)-roof.area)<1e-5
        triangles=[Polygon([v[:2] for v in tri]) for tri in model['triangles']]
        assert abs(sum(t.area for t in triangles)-roof.area)<1e-5
        for i,face in enumerate(model['faces']):
            for x,y,h in face['vertices']:
                assert math.isfinite(h) and p['heightM']-1e-6<=h<=model['peakHeightM']+1e-6
                assert abs(h-height(face['plane'],x,y))<1e-7
            for j in range(i):
                boundary=faces[i].boundary.intersection(faces[j].boundary)
                for line in getattr(boundary,'geoms',[boundary]):
                    if line.geom_type=='LineString':
                        for x,y in line.coords:
                            assert abs(height(face['plane'],x,y)-height(model['faces'][j]['plane'],x,y))<1e-6


def test_solar_modules_fit_single_roof_planes_and_preserve_recorded_capacity():
    import math

    from roof_geometry import height
    for p in source()['properties']:
        expected=math.ceil((p['physical']['solarPeakKW'] or p['physical']['solarKW'])/.42) if p['physical']['solar'] else 0
        assert len(p['solarSurfaces'])==expected
        assert len(p['solarPanels'])==expected
        for module in p['solarSurfaces']:
            face=p['roofModel']['faces'][module['faceIndex']]
            assert Polygon(face['polygon']).covers(Polygon(module['polygon']))
            for x,y,h in module['vertices']:
                assert abs(h-height(face['plane'],x,y)-.06)<1e-7


def test_rear_lots_have_connected_explicit_shared_access():
    data=source()
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    rear=[p for p in data['properties'] if p.get('accessType')=='shared-drive']
    assert {p['id'] for p in rear}=={'R02','R03'}
    assert len(data['sharedAccess'])==2
    for lane in data['sharedAccess']:
        surface=Polygon(lane['polygon'],lane['holes'])
        assert surface.is_valid and surface.area>0
        assert surface.distance(street)<1e-7
        assert surface.intersection(street).area<1e-7
        assert lane['kind']=='shared-drive' and lane['widthM']==3
        assert lane['premiseIds']==[p['premiseId'] for p in rear if p['accessId']==lane['id']]
        assert all(surface.intersection(Polygon(p['polygon'])).area<1e-7 for p in data['properties'])
    assert all(Polygon(p['polygon']).distance(street)>1 for p in rear)


def test_accessory_stays_in_parent_property_without_a_new_customer():
    data=source()
    accessories=[(p,a) for p in data['properties'] for a in p['outbuildings']]
    assert {p['id'] for p,a in accessories}=={'R01','PN-W01'}
    assert len(accessories)==2
    for p,a in accessories:
        assert a['ownerPremiseId']==p['premiseId']
        footprint=Polygon(a['footprint'])
        assert Polygon(p['polygon']).covers(footprint)
        assert not footprint.intersects(Polygon(p['footprint']))
        assert not footprint.intersects(Polygon(p['driveway']))
        assert 'premiseId' not in a and 'binding' not in a



def test_meadow_west_preserves_the_loop_and_unassigned_planted_pockets():
    data=source()
    properties=[p for p in data['properties'] if p['district']=='Meadow West']
    assert len(properties)==28
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    # Sampled asphalt centers from the approved plan: west lane, cross street,
    # southern bend, and the eastern connection into the established network.
    for point in [(235.4,517),(265.6,484.8),(307,544.4),(385.6,533.2)]:
        assert street.buffer(-3).covers(Point(point))
    pockets=[f for f in data['landscape'] if f['id'] in ('meadow-green-01','meadow-woodland-01')]
    assert len(pockets)==2
    for feature in pockets:
        area=Polygon(feature['polygon'],feature['holes'])
        assert feature['renderTexture']
        assert 'unassigned' in feature['status']
        assert area.intersection(street).area<1e-7
        assert all(area.intersection(Polygon(p['polygon'])).area<1e-7 for p in data['properties'])


def test_meadow_east_connects_its_court_and_diagonal_block():
    data=source()
    properties=[p for p in data['properties'] if p['district']=='Meadow East']
    assert len(properties)==31
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    for point in [(415,546.4),(480,531.6),(442.8,586.2),(514.2,610.2),(443.6,671.4)]:
        assert street.buffer(-3).covers(Point(point))
    pockets=[f for f in data['landscape'] if f['id'] in ('meadow-east-green-01','meadow-east-woodland-01')]
    assert len(pockets)==2
    for feature in pockets:
        area=Polygon(feature['polygon'],feature['holes'])
        assert feature['renderTexture']
        assert 'unassigned' in feature['status']
        assert area.intersection(street).area<1e-7
        assert all(area.intersection(Polygon(p['polygon'])).area<1e-7 for p in data['properties'])


def test_parkside_keeps_public_access_separate_from_back_gardens():
    data=source()
    properties=[p for p in data['properties'] if p['district']=='Parkside North']
    assert len(properties)==21
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    for point in [(559.333333,617.333333),(606.166667,567.166667),(675.333333,645.833333)]:
        assert street.buffer(-3).covers(Point(point))
    green=next(f for f in data['landscape'] if f['id']=='parkside-green-01')
    area=Polygon(green['polygon'],green['holes'])
    assert green['renderTexture'] and 'unassigned' in green['status']
    assert area.intersection(street).area<1e-7
    assert all(area.intersection(Polygon(p['polygon'])).area<1e-7 for p in data['properties'])
    walks=unary_union([Polygon(p['polygon'],p['holes']) for p in data['pedestrianPaths']])
    assert walks.covers(Point(575,642.333333))
    assert all(walks.intersection(Polygon(p['polygon'])).area<1e-7 for p in properties)


def test_willow_bend_connects_both_courts_and_preserves_the_wooded_gap():
    data=source()
    properties=[p for p in data['properties'] if p['district']=='Willow Bend']
    assert len(properties)==23
    street=Polygon(data['streetEnvelope']['polygon'],data['streetEnvelope']['holes'])
    for point in [(361.8,665.4),(398.0,725.0),(447.0,760.0),(555.0,682.0),(500.4,773.8)]:
        assert street.buffer(-3).covers(Point(point))
    # The wooded corridor separates the two housing groups in the source plan.
    for point in [(459,735),(475,721),(452,747)]:
        assert all(not Polygon(p['polygon']).covers(Point(point)) for p in properties)
        assert not street.covers(Point(point))
