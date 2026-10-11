"""Freeze spatial vector tiles from the authoritative world, never from painted pixels.

Tile boundaries are only transport boundaries: every feature retains its original
global coordinates and IDs. The browser draws vectors at device resolution and
uses the generated roof/tree materials at their native detail.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).parent / "web/presets"
SIZE = 512


def xy(points):
    return [(p["x"], p["z"]) for p in points]


def rings(poly):
    return [[[round(x, 3), round(y, 3)] for x, y in r.coords] for r in [poly.exterior, *poly.interiors]]


def parts(g):
    return (
        [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
    )


def pack(preset):
    if not re.fullmatch(r"[a-z0-9-]+", preset):
        raise ValueError("Use a preset ID, not a filesystem path.")
    folder = ROOT / preset

    def source(name):
        path = folder / name
        return (
            path.read_bytes()
            if path.exists()
            else gzip.decompress(path.with_suffix(path.suffix + ".gz").read_bytes())
        )

    raw = source("geometry.json")
    data = json.loads(raw)
    snap = json.loads(source("snapshot.json"))
    bounds = data["bounds"]
    scale = data.get("metresPerUnit", 1)
    bounds = [v * scale for v in bounds]
    features = []
    indices = {}

    def add(feature, geometry):
        if geometry.is_empty:
            return
        bbox = geometry.bounds
        feature["bbox"] = [round(v, 3) for v in bbox]
        # All tile copies are byte-identical objects with the same world geometry.
        for col in range(max(0, math.floor((bbox[0] - 8) / SIZE)), math.floor((bbox[2] + 8) / SIZE) + 1):
            for row in range(max(0, math.floor((bbox[1] - 8) / SIZE)), math.floor((bbox[3] + 8) / SIZE) + 1):
                indices.setdefault((col, row), []).append(len(features))
        features.append(feature)

    by_id = {p["id"]: p for p in data["properties"]}
    builds = {pid: b for b in data["buildings"] for pid in b["premiseIds"]}
    road_surfaces = [
        LineString(xy(r["points"])).buffer(r["pavementWidthM"] / 2, cap_style=2) for r in data["roads"]
    ]
    pavement_index = STRtree(road_surfaces)

    def nearby_pavement(geometry, clearance=0):
        candidates = pavement_index.query(geometry.buffer(clearance) if clearance else geometry)
        return unary_union([road_surfaces[int(i)] for i in candidates])

    # Split only huge landscape polygons for transport. Hole geometry is retained.
    for land in data["land"]:
        poly = Polygon(xy(land["polygon"]), [xy(h) for h in land.get("holes", [])])
        a, b, c, d = poly.bounds
        for col in range(max(0, math.floor(a / SIZE)), math.floor(c / SIZE) + 1):
            for row in range(max(0, math.floor(b / SIZE)), math.floor(d / SIZE) + 1):
                for j, part in enumerate(
                    parts(poly.intersection(box(col * SIZE, row * SIZE, (col + 1) * SIZE, (row + 1) * SIZE)))
                ):
                    add(
                        {
                            "type": "land",
                            "id": f"{land['id']}:{col}:{row}:{j}",
                            "kind": land["kind"],
                            "rings": rings(part),
                        },
                        part,
                    )
    for r in data["roads"]:
        add(
            {"type": "road", **r, "points": xy(r["points"])},
            LineString(xy(r["points"])).buffer(r["rowWidthM"] / 2),
        )
    if data.get("civicGreen"):
        poly = Polygon(xy(data["civicGreen"]["polygon"]))
        walkable = poly.difference(nearby_pavement(poly, 0.25).buffer(0.25))
        add(
            {
                "type": "publicGreen",
                "id": "central-public-green",
                "rings": [ring for part in parts(walkable) for ring in rings(part)],
                "designBounds": list(poly.bounds),
            },
            walkable,
        )
    lookup = {}
    for parcel in data["parcels"]:
        p = by_id[parcel["premiseId"]]
        poly = Polygon(xy(parcel["polygon"]))
        fp = builds[p["id"]]["footprint"]["polygon"]
        drive = LineString([(p["front"]["x"], p["front"]["z"]), (p["x"], p["z"])]).buffer(1.7, cap_style=2)
        # Only intersecting road surfaces can affect this drive. Querying the
        # spatial index keeps the same clipping result at city scale.
        drive = drive.difference(nearby_pavement(drive))
        rec = {
            "type": "property",
            "id": p["id"],
            "record": p,
            "rings": rings(poly),
            "roof": xy(fp),
            "drive": [rings(g) for g in parts(drive)],
        }
        add(rec, poly)
        lookup[p["id"]] = [p["x"], p["z"], math.floor(p["x"] / SIZE), math.floor(p["z"] / SIZE)]
    from two_river_streets import furniture

    street_furniture = data.get("furniture")
    if street_furniture is None:
        street_furniture = furniture(snap)
    for item in street_furniture:
        add({"type": "equipment", **item}, Point(item["x"], item["z"]).buffer(8))
    # Large-town furniture can be built separately; never invent an equipment ID.
    target = folder / "tiles"
    target.mkdir(exist_ok=True)
    byte_count = 0
    for (col, row), ids in indices.items():
        content = json.dumps(
            {
                "schema": "atlas-vector-tile/1",
                "origin": [col * SIZE, row * SIZE],
                "features": [features[i] for i in ids],
            },
            separators=(",", ":"),
        )
        (target / f"{col}-{row}.json").write_text(content, encoding="utf-8")
        byte_count += len(content.encode())
    current_tiles = {f"{col}-{row}" for col, row in indices}
    for old_tile in target.glob("*.json"):
        if old_tile.stem not in current_tiles:
            old_tile.unlink()
    manifest = {
        "schema": "atlas-tile-manifest/1",
        "presetId": preset,
        "name": snap["atlasDesign"]["name"],
        "bounds": bounds,
        "tileSize": SIZE,
        "tiles": [f"{c}-{r}" for c, r in sorted(indices)],
        "budget": data["budget"],
        "premises": len(by_id),
        "roads": len(data["roads"]),
        "sourceSha256": hashlib.sha256(raw).hexdigest(),
        "featureCount": len(features),
        "transportBytes": byte_count,
        "focus": snap["atlasDesign"].get("focus"),
        "renderMode": "native-vector-tiles-with-generated-materials",
        "roofSourcePixels": 300,
        "maxPixelsPerMetre": 10,
        "furniture": {
            "poles": sum(f["kind"] == "pole" for f in street_furniture),
            "hydrants": sum(f["kind"] == "hydrant" for f in street_furniture),
            "minimumPoleSpacingM": 35,
        },
    }
    (folder / "tiles.json").write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    (folder / "premise-index.json").write_text(json.dumps(lookup, separators=(",", ":")), encoding="utf-8")
    landmarks = {}
    for kind in ["residential", "industrial", "commercial", "church", "school"]:
        candidates = [p for p in by_id.values() if p["premiseType"] == kind or p["buildingType"] == kind]
        if candidates:
            p = candidates[len(candidates) // 2]
            landmarks[kind] = [p["x"], p["z"]]
    (folder / "landmarks.json").write_text(json.dumps(landmarks), encoding="utf-8")
    print(json.dumps(manifest | {"tiles": len(indices)}, indent=2), flush=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("preset")
    args = parser.parse_args()
    pack(args.preset)
