"""The image-led preset must stay bound to actual system entities."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preset_world import ROOT, build_preset_snapshot  # noqa: E402
from quality import geometry_checks, quality_report  # noqa: E402
from server import prepare_world  # noqa: E402

from utilsim.world.map_view import WorldMap  # noqa: E402


@pytest.fixture(scope='module')
def baked():
    return json.loads((ROOT / 'snapshot.json').read_text())


def test_fixed_plan_rebuilds_identically_and_passes_geometry(baked):
    assert build_preset_snapshot() == baked
    assert baked['homes'] == 500
    assert len(baked['premises']) == 525
    assert all(c['status'] == 'pass' for c in geometry_checks(baked))
    assert hashlib.sha256((ROOT / 'master.svg').read_text(encoding='utf-8').encode('utf-8')).hexdigest() == baked['atlasDesign']['masterSvgSha256']


def test_svg_and_export_bind_every_property_to_real_entities(baked):
    root = ET.parse(ROOT / 'town.svg').getroot()
    ns = {'s': 'http://www.w3.org/2000/svg'}
    parcels = root.find('s:g[@id="parcels"]', ns)
    buildings = root.find('s:g[@id="buildings"]', ns)
    assert {p.attrib['data-premise-id'] for p in parcels} == {p['id'] for p in baked['premises']}
    assert {b.attrib['data-premise-id'] for b in buildings} == {p['id'] for p in baked['premises']}
    assert {b.attrib['id'] for b in buildings} == {b['id'] for b in baked['buildings']}
    bindings = json.loads((ROOT / 'bindings.json').read_text())
    meters = {m['id']: m for m in baked['meters']}
    services = {s['id']: s for s in baked['servicePoints']}
    assert len(bindings['properties']) == 525
    for record in bindings['properties']:
        assert record['meterIds']
        for meter_id in record['meterIds']:
            assert services[meters[meter_id]['servicePointId']]['premiseId'] == record['premiseId']


def test_quality_rejects_a_building_bound_to_the_wrong_home(baked):
    damaged = copy.deepcopy(baked)
    damaged['buildings'][0]['premiseIds'] = [baked['premises'][1]['id']]
    assert next(c for c in geometry_checks(damaged) if c['id'] == 'entity-bindings')['status'] == 'fail'


def test_preset_runtime_resumes_records_without_regenerating(tmp_path, baked):
    world = prepare_world(tmp_path, 500, 'IGNORED-AT-RUNTIME', preset='riverbend-500')
    assert WorldMap(world).snapshot() == baked
    report = quality_report(baked, world)
    assert report['automatedPassed']
    assert len(report['checks']) == 14
    before = world.status()
    again = prepare_world(tmp_path, 500, 'ANOTHER-SEED', preset='riverbend-500')
    assert again.status() == before
    assert WorldMap(again).snapshot() == baked
    with pytest.raises(ValueError, match='own store'):
        prepare_world(tmp_path, 500, 'OTHER', town500=True)


def test_library_distinguishes_planned_from_available():
    catalog = json.loads((ROOT.parent / 'catalog.json').read_text())['presets']
    assert [p['targetHomes'] for p in catalog].count(500) == 3
    assert [p['targetHomes'] for p in catalog].count(5000) == 2
    assert [p['targetHomes'] for p in catalog].count(25000) == 1
    assert [p['targetHomes'] for p in catalog].count(50000) == 1
    for item in catalog:
        assert item['status'] in ('configured', 'prototype', 'internally-reviewed')
        if item['status'] in ('prototype', 'internally-reviewed'):
            assert item['actualHomes'] is not None
            assert item['targetHomes'] * .9 <= item['actualHomes'] <= item['targetHomes'] * 1.1
