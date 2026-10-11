"""Recorded physical settings follow each locked property into its draft site."""
import json
import math

from roof_geometry import build_roof, solar_modules
from shapely import affinity
from shapely.geometry import Polygon, box


def physical_details(root, properties):
    source={p['id']:p for p in json.loads((root/'snapshot.json').read_text())['premises']}
    sites=json.loads((root/'site-details.json').read_text())
    fields=('solar','solarKW','solarPeakKW','hasPool','stories','roof','yearBuilt',
            'occupied','occupants','heatingFuel','hasEV','irrigation','roofTone')
    for p in properties:
        recorded=source[p['premiseId']]
        p['physical']={k:recorded[k] for k in fields}
        p['heightM']=recorded['height']
        p['roofModel']=build_roof(p)
        p['outbuildings']=[]
        for specification in sites.get(p['premiseId'],{}).get('outbuildings',[]):
            accessory={**specification,'ownerPremiseId':p['premiseId']}
            footprint=Polygon(accessory['footprint'])
            if (not Polygon(p['polygon']).buffer(-.15).covers(footprint)
                    or Polygon(p['footprint']).buffer(.3).intersects(footprint)):
                raise ValueError(f'Accessory does not fit its parent parcel: {accessory["id"]}')
            accessory['roofModel']=build_roof({**accessory,'physical':{'roof':accessory['roof']}})
            p['outbuildings'].append(accessory)

        p['solarPanels']=[]
        p['solarSurfaces']=[]
        roof=Polygon(p['footprint'])
        if recorded['solar']:
            capacity=recorded['solarPeakKW'] or recorded['solarKW']
            count=max(1,math.ceil(capacity/.42))
            p['solarSurfaces']=solar_modules(p,count)
            p['solarPanels']=[module['polygon'] for module in p['solarSurfaces']]
        p['pool']=None
        if recorded['hasPool']:
            spec=sites.get(p['premiseId'],{}).get('pool')
            if not spec:
                raise ValueError(f'Author the recorded pool site for {p["premiseId"]}')
            width,depth=spec['widthM']/1.35,spec['depthM']/1.35
            pool=affinity.rotate(box(-width/2,-depth/2,width/2,depth/2),p['heading'],origin=(0,0))
            pool=affinity.translate(pool,*spec['center'])
            if (not Polygon(p['polygon']).buffer(-.35).covers(pool) or roof.buffer(.6).intersects(pool)
                    or Polygon(p['driveway']).buffer(.2).intersects(pool)):
                raise ValueError(f'Pool leaves its available rear garden: {p["premiseId"]}')
            p['pool']=list(pool.exterior.coords)
