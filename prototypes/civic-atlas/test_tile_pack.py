"""Transport boundaries must not change geometry, ownership or road hit targets."""

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from shapely.ops import unary_union
from two_river_streets import surface

ROOT = Path(__file__).parent / "web/presets/ashtown-5000"


def source_bytes():
    path = ROOT / "geometry.json"
    return path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(".json.gz").read_bytes())


def all_features():
    manifest = json.loads((ROOT / "tiles.json").read_text())
    features = {}
    for key in manifest["tiles"]:
        tile = json.loads((ROOT / "tiles" / f"{key}.json").read_text())
        for f in tile["features"]:
            identity = (f["type"], f["id"])
            if identity in features:
                assert features[identity] == f, f"Tile seam changed {identity}"
            features[identity] = f
    return manifest, features


def test_every_tile_copy_preserves_the_same_source_and_full_identity():
    manifest, features = all_features()
    raw = source_bytes()
    source = json.loads(raw)
    assert manifest["sourceSha256"] == hashlib.sha256(raw).hexdigest()
    by_id = {p["id"]: p for p in source["properties"]}
    properties = [f for f in features.values() if f["type"] == "property"]
    assert len(properties) == len(by_id) == manifest["premises"]
    for f in properties:
        assert f["record"] == by_id[f["id"]]
    road_ids = {r["id"]: r for r in source["roads"]}
    roads = [f for f in features.values() if f["type"] == "road"]
    assert len(roads) == len(road_ids)
    for f in roads:
        assert f["points"] == [[p["x"], p["z"]] for p in road_ids[f["id"]]["points"]]
        assert f["pavementWidthM"] == road_ids[f["id"]]["pavementWidthM"]


def test_curbs_and_actual_pole_spacing_survive_tiling():
    _, features = all_features()
    source = json.loads(source_bytes())
    pavement = surface(source["roads"])
    driveways = [
        Polygon(r[0], r[1:]) for f in features.values() if f["type"] == "property" for r in f["drive"]
    ]
    # Coordinates are quantized to a millimetre in transport, allow only tiny slivers.
    assert unary_union(driveways).intersection(pavement).area < 3
    poles = [f for f in features.values() if f["type"] == "equipment" and f["kind"] == "pole"]
    assert len(poles) > 500
    xy = np.array([(p["x"], p["z"]) for p in poles])
    assert cKDTree(xy).query(xy, k=2)[0][:, 1].min() >= 35
    assert all(p["source"] == "saved network equipment" for p in poles)
