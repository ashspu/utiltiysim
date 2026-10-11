"""Baked experiment gates: counts, joins, geometry, and negative controls."""

import copy
import gzip
import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import Point, Polygon

sys.path.insert(0, str(Path(__file__).parent))
from quality import geometry_checks
from two_river_streets import driveway_shapes, surface

ROOT = Path(__file__).parent / "web/presets/two-river-forest-500"


def read_source(name):
    path = ROOT / name
    return json.loads(path.read_bytes() if path.exists() else gzip.decompress((ROOT / (name + ".gz")).read_bytes()))


@pytest.fixture(scope="module")
def source():
    return read_source("snapshot.json")


def test_actual_map_meets_tolerance_and_exact_features(source):
    assert source["homes"] == 451 and source["count"] == 476
    assert all(c["status"] == "pass" for c in geometry_checks(source))
    assert (
        hashlib.sha256((ROOT / "master.svg").read_text(encoding="utf-8").encode()).hexdigest()
        == source["atlasDesign"]["masterSvgSha256"]
    )


def test_blocks_own_all_properties_and_match_geometry(source):
    seen = []
    by_id = {p["id"]: p for p in source["premises"]}
    for block in source["atlasDesign"]["blocks"]:
        poly = Polygon(
            [(p["x"], p["z"]) for p in block["polygon"]],
            [[(p["x"], p["z"]) for p in hole] for hole in block.get("holes", [])],
        )
        for identity in block["premiseIds"]:
            home = by_id[identity]
            assert home["atlasBlockId"] == block["id"]
            assert poly.buffer(0.02).covers(Point(home["x"], home["z"]))
            seen.append(identity)
    assert len(seen) == len(set(seen)) == 476


def test_svg_has_one_building_per_premise_and_exact_pools(source):
    svg = ET.parse(ROOT / "05-controlled-map.svg").getroot()
    buildings = [e.get("data-building") for e in svg.iter() if e.get("data-building")]
    pools = [e.get("data-pool") for e in svg.iter() if e.get("data-pool")]
    roads = [e.get("data-road") for e in svg.iter() if e.get("data-road")]
    assert len(buildings) == len(set(buildings)) == 476
    assert set(pools) == {p["id"] for p in source["premises"] if p["hasPool"]}
    assert len(pools) == 100
    assert set(roads) == {r["id"] for r in source["roads"]}


def test_driveways_end_at_pavement_and_poles_never_cluster(source):
    data = read_source("geometry.json")
    pavement = surface(data["roads"])
    for drive in driveway_shapes(data).values():
        assert drive.intersection(pavement).area < 0.000001
    poles = [a for a in data["furniture"] if a["kind"] == "pole"]
    assert len(poles) > 100
    native = {a["id"]: a for a in source["networks"]["electric"]["equipment"] if a["kind"] == "pole"}
    for i, a in enumerate(poles):
        point = Point(a["x"], a["z"])
        assert not pavement.covers(point)
        assert (a["x"], a["z"]) == (native[a["id"]]["x"], native[a["id"]]["z"])
        assert all(point.distance(Point(b["x"], b["z"])) >= 35 for b in poles[i + 1 :])
    hydrants = [a for a in data["furniture"] if a["kind"] == "hydrant"]
    assert len(hydrants) == 54
    assert all(not pavement.covers(Point(a["x"], a["z"])) for a in hydrants)


@pytest.mark.parametrize("damage", ["extra_pool", "solar", "pool_on_house", "missing_pool", "wrong_budget"])
def test_feature_gates_reject_corruption(source, damage):
    data = copy.deepcopy(source)
    pool_home = next(p for p in data["premises"] if p["hasPool"])
    if damage == "extra_pool":
        next(p for p in data["premises"] if not p["hasPool"])["hasPool"] = True
    elif damage == "solar":
        pool_home["solarKW"] = 3
    elif damage == "pool_on_house":
        pool_home["poolPolygon"] = next(b for b in data["buildings"] if pool_home["id"] in b["premiseIds"])[
            "footprint"
        ]["polygon"]
    elif damage == "missing_pool":
        del pool_home["poolPolygon"]
    else:
        data["atlasDesign"]["featureBudget"]["targetHomes"] = 600
    assert any(
        c["status"] == "fail" for c in geometry_checks(data) if c["id"] in ("feature-budget", "pool-geometry")
    )
