"""Versioned town authoring from explicit world-builder budgets.

Geometry is baked before artwork. Each visible roof, pool and property is owned
by an engine premise; display tiles may never create additional customers.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polylabel, substring, unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quality import geometry_checks
from town500_world import _facility
from two_river_forest import area_record, parts, vect

from utilsim.config import load_preset
from utilsim.core.ids import uid
from utilsim.customers.generate import build_customers
from utilsim.gen.addresses import assign_addresses
from utilsim.gen.buildings import _rect, assign_households, build_premises
from utilsim.gen.landuse import Facility, LandUse, _exits
from utilsim.gen.parcels import candidate_lots
from utilsim.gen.roads.build import Geography
from utilsim.gen.roads.model import ARTERIAL, COLLECTOR, LOCAL, ROW_WIDTH, RoadLine
from utilsim.gen.roads.planarize import planarize
from utilsim.gen.terrain import Terrain
from utilsim.gen.zoning import build_era_field
from utilsim.io.snapshot import build_snapshot
from utilsim.model.town import Town
from utilsim.net.context import NetContext
from utilsim.net.electric import build_electric
from utilsim.net.gas import build_gas
from utilsim.net.water import build_water

ROOT = Path(__file__).parent / "web/presets"
CHECKPOINTS = Path(__file__).resolve().parents[2] / "out/factory-checkpoints"
CONFIGS = [
    dict(
        id="two-river-forest-500",
        name="Two River Forest",
        homes=500,
        pools=100,
        schools=1,
        church=1,
        shops=16,
        industry=6,
        seed=301,
        character="Two wooded rivers and countryside",
        palette="forest",
        existing=True,
    ),
    dict(
        id="bramblewick-500",
        name="Bramblewick",
        homes=500,
        pools=80,
        schools=1,
        church=1,
        shops=16,
        industry=6,
        seed=427,
        character="Orchard village, winding lanes and a broad common",
        palette="orchard",
    ),
    dict(
        id="lantern-bay-500",
        name="Lantern Bay",
        homes=500,
        pools=60,
        schools=1,
        church=1,
        shops=20,
        industry=6,
        seed=791,
        character="Lakeside crescents and a waterfront market",
        palette="coastal",
    ),
    dict(
        id="ashtown-5000",
        name="Ashtown",
        homes=5000,
        pools=1000,
        schools=10,
        church=1,
        shops=160,
        industry=60,
        seed=29071,
        character="A large market and minster flank the central green",
        palette="ash",
        existing=True,
    ),
    dict(
        id="copperhaven-5000",
        name="Copperhaven",
        homes=5000,
        pools=700,
        schools=10,
        church=1,
        shops=160,
        industry=60,
        seed=12031,
        character="Wooded neighbourhoods and copper-roofed civic squares",
        palette="copper",
    ),
    dict(
        id="willowmere-25000",
        name="Willowmere",
        homes=25000,
        pools=4000,
        schools=50,
        church=1,
        shops=800,
        industry=300,
        seed=58423,
        character="Garden districts around protected wetlands and market greens",
        palette="wetland",
    ),
    dict(
        id="foxglove-city-50000",
        name="Foxglove City",
        homes=50000,
        pools=7500,
        schools=100,
        church=1,
        shops=1600,
        industry=600,
        seed=87011,
        character="Linked urban villages with forest fingers and a civic heart",
        palette="foxglove",
    ),
]


def config(preset):
    return next(c for c in CONFIGS if c["id"] == preset)


def validate_custom_config(raw):
    """Validate configuration before authoring; existing curated worlds are immutable here."""
    c = dict(raw)
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,63}", str(c.get("id", ""))):
        raise ValueError("id must be a lowercase slug of 4 to 64 characters")
    if c["id"] in {p["id"] for p in CONFIGS} or (ROOT / c["id"]).exists():
        raise ValueError("Choose a new id; --config never overwrites an existing town or saved world")
    if (
        not isinstance(c.get("name"), str)
        or not 1 <= len(c["name"].strip()) <= 80
        or any(x in c["name"] for x in "<>")
    ):
        raise ValueError("name must contain 1 to 80 plain-text characters")
    limits = {
        "homes": (450, 50000),
        "pools": (0, 45000),
        "schools": (1, 103),
        "church": (1, 1),
        "shops": (1, 2000),
        "industry": (1, 600),
        "seed": (0, 2147483647),
    }
    for key, (low, high) in limits.items():
        value = c.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}")
    district_capacity = 1 if c["homes"] <= 500 else math.ceil(c["homes"] / 500)
    if c["schools"] > district_capacity:
        raise ValueError("School budget exceeds the number of reserved neighbourhood campuses")
    if c["pools"] > c["homes"] * 0.9:
        raise ValueError("Pool budget cannot exceed the minimum allowed home count")
    if c.get("solar", 0) != 0 or c.get("homeTolerance", 0.1) != 0.1:
        raise ValueError("This factory version supports zero solar and a 10% home-count tolerance")
    if c.get("palette") not in {"forest", "orchard", "coastal", "ash", "copper", "wetland", "foxglove"}:
        raise ValueError("Unknown visual palette")
    c["character"] = str(c.get("character") or "Custom configuration, visual review pending")[:240]
    c.pop("existing", None)
    return c


def internal_visual_review(folder):
    source = folder / "internal-visual-review.json"
    if not source.exists():
        return None
    review = json.loads(source.read_text(encoding="utf-8"))
    geometry = folder / "geometry.json"
    packed = folder / "geometry.json.gz"
    if geometry.exists():
        stream = geometry.open("rb")
    elif packed.exists():
        stream = gzip.open(packed, "rb")
    else:
        return {**review, "status": "source-missing"}
    with stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != review.get("sourceSha256"):
        return {**review, "status": "outdated", "currentSourceSha256": digest}
    return review


def write_catalog():
    """Inventory availability from complete, checked bakes; never infer artwork approval."""
    entries = []
    for c in CONFIGS:
        folder = ROOT / c["id"]
        budget = None
        manifest_path = folder / "build-manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("geometryPassed"):
                budget = manifest["featureBudget"]
        elif c.get("existing"):
            source = folder / "snapshot.json"
            packed = folder / "snapshot.json.gz"
            if source.exists():
                budget = json.loads(source.read_text(encoding="utf-8"))["atlasDesign"]["featureBudget"]
            elif packed.exists():
                with gzip.open(packed, "rt", encoding="utf-8") as stream:
                    budget = json.load(stream)["atlasDesign"]["featureBudget"]
        review = internal_visual_review(folder)
        entries.append(
            {
                "id": c["id"],
                "name": c["name"],
                "targetHomes": c["homes"],
                "actualHomes": budget["homes"] if budget else None,
                "homeTolerance": 0.1,
                "status": "internally-reviewed"
                if budget and review and review.get("status") == "passed"
                else "prototype"
                if budget
                else "configured",
                "conceptDirectionApproved": False,
                "visualReleaseApproved": False,
                "userVisualApproval": False,
                "internalVisualReview": review,
                "revision": 1,
                "path": "shared/tiled-map.html?preset=" + c["id"],
                "character": c["character"],
                "palette": c["palette"],
                "featureBudget": budget
                or {
                    "targetHomes": c["homes"],
                    "homeTolerance": 0.1,
                    "pools": c["pools"],
                    "solar": 0,
                    "school": c["schools"],
                    "church": c["church"],
                    "commercial": c["shops"],
                    "industrial": c["industry"],
                },
            }
        )
    target = ROOT / "catalog.json"
    target.write_text(
        json.dumps(
            {
                "schemaVersion": "civic-atlas-preset-library/1",
                "policy": "Seven fixed versioned towns. Configured towns are not available maps. Source geometry, artwork and live-system QA are separate gates. No runtime regeneration.",
                "presets": entries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def road(name, kind, coords, seed):
    return RoadLine(np.asarray(coords, dtype=float), kind, name, source_id=uid("factory-road", seed, name))


def indexed_facility(roads, identity, kind, label, polygon, lines, tree):
    """Equivalent nearest frontage without rebuilding every road for each campus."""
    center = np.asarray(polygon.centroid.coords[0])
    target = Point(center)
    edge = min(int(i) for i in tree.query_nearest(target, all_matches=True))
    line = lines[edge]
    distance = line.project(target)
    front = np.asarray(line.interpolate(distance).coords[0])
    tangent = np.asarray(line.coords[-1]) - np.asarray(line.coords[0])
    tangent /= np.linalg.norm(tangent)
    normal = np.array([-tangent[1], tangent[0]])
    return Facility(
        identity,
        kind,
        label,
        center,
        polygon,
        math.atan2(tangent[1], tangent[0]),
        edge,
        distance,
        1 if np.dot(center - front, normal) >= 0 else -1,
    )


def local_street_has_clearance(piece, street_tree, street_lines):
    """Allow junction approaches but reject sustained close parallel streets."""
    if piece.length <= 90:
        return True
    core = substring(piece, 30, piece.length - 30)
    near_streets = street_tree.query(core.buffer(24), predicate="intersects")
    occupied = unary_union([street_lines[int(i)].buffer(24) for i in near_streets])
    return core.intersection(occupied).length <= core.length * 0.22


def checkpoint_sources(preset, snapshot, data, master, c, seed, budget, generation_seconds):
    """Save unpublished source state before expensive QA; descriptor is committed last."""
    folder = CHECKPOINTS / preset
    folder.mkdir(parents=True, exist_ok=True)
    digests = {}
    for filename, value in [("snapshot.json", snapshot), ("geometry.json", data), ("master.svg", master)]:
        target = folder / filename
        pending = folder / (filename + ".pending")
        with pending.open("w", encoding="utf-8", newline="") as stream:
            if filename.endswith(".json"):
                json.dump(value, stream, separators=(",", ":"))
            else:
                stream.write(value)
        pending.replace(target)
        with target.open("rb") as stream:
            digests[filename] = hashlib.file_digest(stream, "sha256").hexdigest()
    context = {
        "schemaVersion": "town-source-checkpoint/1",
        "presetId": preset,
        "config": c,
        "seed": seed,
        "featureBudget": budget,
        "generationSeconds": generation_seconds,
        "files": digests,
        "published": False,
    }
    pending = folder / "checkpoint.json.pending"
    pending.write_text(json.dumps(context, indent=2), encoding="utf-8")
    pending.replace(folder / "checkpoint.json")
    return folder


def load_checkpoint(preset):
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,63}", preset):
        raise ValueError("Checkpoint requires a preset slug")
    folder = CHECKPOINTS / preset
    context = json.loads((folder / "checkpoint.json").read_text(encoding="utf-8"))
    expected = {"snapshot.json", "geometry.json", "master.svg"}
    if (
        context.get("schemaVersion") != "town-source-checkpoint/1"
        or context.get("presetId") != preset
        or context.get("config", {}).get("id") != preset
        or set(context.get("files", {})) != expected
    ):
        raise ValueError("Checkpoint descriptor is incomplete or belongs to a different town")
    for filename in sorted(expected):
        with (folder / filename).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != context["files"][filename]:
            raise ValueError(f"Checkpoint file digest mismatch: {filename}")
    snapshot = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    data = json.loads((folder / "geometry.json").read_text(encoding="utf-8"))
    master = (folder / "master.svg").read_text(encoding="utf-8")
    if (
        snapshot.get("atlasDesign", {}).get("presetId") != preset
        or data.get("budget") != context["featureBudget"]
        or snapshot["atlasDesign"].get("masterSvgSha256") != hashlib.sha256(master.encode()).hexdigest()
    ):
        raise ValueError("Checkpoint sources do not match their configuration or master SVG")
    return snapshot, data, master, context


def resume_checkpoint(preset):
    snapshot, data, master, context = load_checkpoint(preset)
    started = time.perf_counter() - context["generationSeconds"]
    return finish_bake(
        snapshot, data, master, context["config"], context["seed"], context["featureBudget"], started
    )


def plan(c, *, generations=10):
    """Curved arterials and recursively subdivided street-bounded land, without district templates."""
    from scipy.interpolate import CubicSpline
    from shapely.affinity import scale

    from utilsim.gen.parcels import land_blocks

    rng = np.random.default_rng(c["seed"])
    factor = math.sqrt(c["homes"] / 5000)
    width, height = 4200 * factor, 2800 * factor
    frame = (0.0, -height, width, 0.0)
    center = (width * (0.41 if c["palette"] == "coastal" else 0.50), -height * 0.49)
    lines = []

    def curved(name, kind, coords):
        pts = np.array([(x * width, -y * height) for x, y in coords])
        tt = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        sampled = CubicSpline(tt, pts, bc_type="natural")(
            np.unique(np.r_[tt, np.linspace(0, tt[-1], max(10, int(tt[-1] / 15)))])
        )
        lines.append(road(name, kind, sampled, c["seed"]))

    coastal = c["palette"] == "coastal"
    west = 0.20 if coastal else 0.075
    curved("North County Road", ARTERIAL, [(0, 0.085), (0.25, 0.065), (0.55, 0.115), (0.8, 0.075), (1, 0.10)])
    curved("South County Road", ARTERIAL, [(0, 0.93), (0.3, 0.92), (0.65, 0.95), (1, 0.91)])
    curved(
        "West County Road", ARTERIAL, [(west, 0), (west + 0.025, 0.3), (west - 0.015, 0.65), (west + 0.04, 1)]
    )
    curved("East County Road", ARTERIAL, [(0.94, 0), (0.92, 0.35), (0.965, 0.7), (0.94, 1)])
    curved(
        f"{c['name']} Main Street",
        COLLECTOR,
        (
            [(west, 0.65), (0.3, 0.54), (0.5, 0.43), (0.73, 0.34), (0.95, 0.28)]
            if c["palette"] == "orchard"
            else [(west, 0.58), (0.35, 0.43), (0.52, 0.40), (0.76, 0.49), (0.95, 0.56)]
            if coastal
            else [(west, 0.61), (0.3, 0.52), (0.5, 0.41), (0.73, 0.30), (0.95, 0.22)]
            if c["palette"] == "copper"
            else [(west, 0.48), (0.3, 0.43), (0.5, 0.425), (0.73, 0.47), (0.95, 0.54)]
        ),
    )
    curved("Green Avenue", COLLECTOR, [(west, 0.75), (0.3, 0.68), (0.53, 0.62), (0.77, 0.69), (0.95, 0.72)])
    curved("Market Road", COLLECTOR, [(0.37, 0.07), (0.36, 0.28), (0.405, 0.44), (0.39, 0.63), (0.44, 0.94)])
    curved("Church Road", COLLECTOR, [(0.65, 0.08), (0.64, 0.3), (0.61, 0.43), (0.64, 0.65), (0.62, 0.94)])
    if c["homes"] > 500:
        curved("Westgate Drive", COLLECTOR, [(0.23, 0.07), (0.26, 0.33), (0.21, 0.62), (0.25, 0.93)])
        curved("Eastgate Drive", COLLECTOR, [(0.80, 0.08), (0.78, 0.30), (0.83, 0.54), (0.78, 0.93)])
    green = scale(
        Point(center).buffer(1, quad_segs=36), max(48, 130 * factor), max(42, 110 * factor), origin=center
    )
    size = min(95.0, max(48.0, 70 * factor))
    cx, cy = center
    church = box(cx + max(60, 155 * factor), cy - size / 2, cx + max(60, 155 * factor) + size, cy + size / 2)
    market = box(cx - max(60, 155 * factor) - size, cy - size / 2, cx - max(60, 155 * factor), cy + size / 2)
    specs = [
        ("CHURCH-01", "school", f"{c['name']} Church", church),
        ("MARKET-01", "depot", f"{c['name']} Market Hall", market),
    ]
    if coastal:
        water = [
            scale(
                Point(-width * 0.11, -height * 0.5).buffer(1, quad_segs=56),
                width * 0.28,
                height * 0.67,
                origin=(-width * 0.11, -height * 0.5),
            ).intersection(box(*frame))
        ]
    else:
        corridors = {
            "orchard": [[(0.17, 0), (0.27, 0.24), (0.16, 0.43), (0.24, 0.68), (0.35, 1)]],
            "copper": [[(0, 0.18), (0.22, 0.23), (0.45, 0.135), (0.72, 0.16), (1, 0.06)]],
            "wetland": [
                [(0, 0.18), (0.25, 0.22), (0.5, 0.15), (0.75, 0.20), (1, 0.13)],
                [(0, 0.88), (0.27, 0.78), (0.52, 0.82), (0.73, 0.76), (1, 0.73)],
            ],
            "foxglove": [
                [(0.16, 0), (0.23, 0.25), (0.13, 0.49), (0.18, 0.77), (0.1, 1)],
                [(0.67, 0), (0.73, 0.17), (0.82, 0.26), (0.88, 0.4), (1, 0.44)],
            ],
        }.get(c["palette"], [[(0.115, 0), (0.145, 0.3), (0.105, 0.65), (0.16, 1)]])
        water = [
            LineString([(x * width, -y * height) for x, y in coords]).buffer(max(7, 11 * factor))
            for coords in corridors
        ]
    ncols = max(3, math.ceil(math.sqrt(c["industry"] * 1.3)))
    nrows = math.ceil(c["industry"] / ncols)
    cw, ch = 68.0, 65.0
    ix = width * 0.91 - ncols * cw
    iy = -height * 0.30 if c["palette"] == "wetland" else -height * 0.87 + nrows * ch
    for row in range(nrows):
        y = iy - row * ch
        lines.append(road(f"Foundry Row {row + 1}", LOCAL, [(ix - 20, y), (width * 0.94, y)], c["seed"]))
        for col in range(ncols):
            number = row * ncols + col + 1
            if number > c["industry"]:
                break
            x = ix + col * cw
            specs.append(
                (
                    f"INDUSTRY-{number:04}",
                    "industrial",
                    f"{c['name']} Works {number}",
                    box(x, y - 49, x + 53, y - 12),
                )
            )
    lines.append(road("Works Way", COLLECTOR, [(ix - 20, 0), (ix - 20, -height)], c["seed"]))
    industry = box(
        ix - 12, iy - nrows * ch - 15 if c["palette"] == "wetland" else -height * 0.89, width * 0.93, iy + 20
    )
    cols = math.ceil(math.sqrt(c["schools"] * 1.35))
    rows = math.ceil(c["schools"] / cols)
    for k in range(c["schools"]):
        row, col = divmod(k, cols)
        x = width * (west + 0.10 + (col + 0.5) / cols * (0.78 - west))
        y = -height * (0.16 + (row + 0.5) / rows * 0.63)
        if (
            industry.distance(Point(x, y)) < 100
            or green.distance(Point(x, y)) < 120
            or (c["homes"] > 5000 and any(w.distance(Point(x, y)) < 100 for w in water))
        ):
            y = -height * (0.16 + (row + 0.2) / rows * 0.55)
        size = min(95, max(50, 60 * factor))
        specs.append(
            (
                f"SCHOOL-{k + 1:03}",
                "school",
                f"{c['name']} School {k + 1}",
                box(x - size / 2, y - size / 2, x + size / 2, y + size / 2),
            )
        )
    sy = -height * 0.89
    for k, (identity, kind, label, size) in enumerate(
        [
            ("SUB-01", "substation", "Substation", 45),
            ("PUMP-01", "pump_station", "Water Works", 40),
            ("GATE-01", "city_gate", "Gas Gate", 30),
            ("TANK-01", "elevated_tank", "Water Tower", 30),
        ]
    ):
        x = width * 0.55 + k * 60
        specs.append((identity, kind, f"{c['name']} {label}", box(x, sy + 12, x + size, sy + 12 + size)))
    develop = box(width * (west + 0.015), -height * 0.88, width * 0.905, -height * 0.13).difference(industry)
    reserves = [green, *[p.buffer(3) for _, _, _, p in specs], industry, *[p.buffer(20) for p in water]]
    reserve_tree = STRtree(reserves)
    planning_barriers = unary_union(reserves)
    words = [
        "Willow",
        "Rowan",
        "Hazel",
        "Bramble",
        "Foxglove",
        "Alder",
        "Orchard",
        "Juniper",
        "Elm",
        "Linden",
        "Hawthorn",
        "Cedar",
        "Mill",
        "Chestnut",
        "Maple",
        "Birch",
    ]
    for generation in range(generations + (4 if c["homes"] > 5000 and generations else 0)):
        net = planarize([], lines, min_dangle=25, min_edge=1)
        geo = Geography(net, None, None, center, frame, 43.0, -79.0, {})
        blocks, _ = land_blocks(geo, frame)
        if c["homes"] > 5000:
            # Reserved land is a real block boundary. Otherwise clipped street ends
            # leave the same giant block intact and each pass adds a parallel
            # dead end instead of subdividing the land along either bank.
            blocks = [part for block in blocks for part in parts(block.difference(planning_barriers), 500)]
        street_lines = [LineString(points) for points in net.graph.geometry]
        street_tree = STRtree(street_lines)
        additions = []
        for block in blocks:
            nearby = reserve_tree.query(block, predicate="intersects")
            available = block.intersection(develop)
            if len(nearby):
                available = available.difference(unary_union([reserves[int(j)] for j in nearby]))
            if available.area < (14500 if c["homes"] > 5000 else 21000):
                continue
            rect = block.minimum_rotated_rectangle
            q = np.array(rect.exterior.coords[:4])
            edges = np.diff(np.vstack([q, q[0]]), axis=0)
            long = edges[np.argmax(np.linalg.norm(edges, axis=1))]
            long /= np.linalg.norm(long)
            cross = np.array([-long[1], long[0]])
            origin = np.array(available.representative_point().coords[0])
            origin_point = Point(origin)
            if origin_point.distance(street_lines[int(street_tree.nearest(origin_point))]) < 42:
                continue
            angle = rng.uniform(-0.30, 0.30)
            direction = cross * math.cos(angle) + long * math.sin(angle)
            normal = np.array([-direction[1], direction[0]])
            length = max(width, height) * 2
            distances = np.linspace(-length, length, 65)
            waviness = rng.uniform(-20, 20) * np.sin(distances / 150 + rng.uniform(-1, 1))
            raw = LineString(
                [origin + direction * d + normal * w for d, w in zip(distances, waviness, strict=True)]
            )
            clipped = raw.intersection(block.buffer(18))
            if len(nearby):
                clipped = clipped.difference(unary_union([reserves[int(j)].buffer(8) for j in nearby]))
            for piece in getattr(clipped, "geoms", [clipped]):
                if (
                    piece.geom_type != "LineString"
                    or piece.length < 80
                    or piece.intersection(available).length < 65
                ):
                    continue
                if c["homes"] > 5000 and not local_street_has_clearance(piece, street_tree, street_lines):
                    continue
                idx = len(lines) + len(additions)
                name = f"{words[idx % len(words)]} {'Lane' if idx % 3 == 0 else 'Crescent' if idx % 3 == 1 else 'Street'} {idx // len(words) + 1}"
                additions.append(road(name, LOCAL, np.array(piece.coords), c["seed"]))
        lines.extend(additions)
        print("subdivision", generation, "added", len(additions), flush=True)
        if not additions:
            break
    return lines, [np.array(center)], [green], specs, water, frame, center, develop


def build(preset, custom=None):
    c = custom or config(preset)
    if c.get("existing"):
        raise ValueError("This preset has a dedicated authored generator; preserve its existing bake.")
    started = time.perf_counter()
    seed = f"FACTORY-{c['seed']}-V{4}"
    cfg = load_preset(
        "village",
        seed=seed,
        houses=c["homes"],
        overrides={
            "town": {"terrain_relief_m": 0, "industrial_lots": min(10, c["industry"])},
            "housing": {
                "lot_frontage_m": {
                    "pre_1945": 15.0 if c["palette"] == "coastal" else 17.0,
                    "postwar": 16.0 if c["palette"] == "coastal" else 18.0,
                    "modern": 17.0 if c["palette"] == "coastal" else 19.0,
                },
                "lot_depth_m": {"pre_1945": 41.0, "postwar": 43.0, "modern": 45.0},
            },
        },
    )
    lines, centers, greens, specs, water, frame, center, develop = plan(c)
    print(preset, "connected urban plan", flush=True)
    terrain = Terrain(cfg.seeds.for_("town"), relief_m=0, base_m=90)
    era = build_era_field(
        cfg.seeds.for_("town"),
        center,
        max(frame[2], -frame[1]),
        frame,
        c["homes"],
        1925,
        90,
        24,
        cfg.gas.all_electric_district_share,
    )
    net = planarize([], lines, min_dangle=20, min_edge=1)
    print("roads", net.summary(), flush=True)
    geo = Geography(
        net,
        era,
        terrain,
        center,
        frame,
        cfg.town.anchor_lat,
        cfg.town.anchor_lon,
        {
            "type": "synthetic",
            "label": c["name"],
            "expansion": "none",
            "streetModel": "curated-neighbourhoods/1",
        },
    )
    road_land = unary_union(
        [
            LineString(g).buffer(ROW_WIDTH[net.graph.edge_class[i]] / 2, cap_style=2)
            for i, g in enumerate(net.graph.geometry)
        ]
    )
    facilities = []
    facility_lines = [LineString(points) for points in net.graph.geometry]
    facility_tree = STRtree(facility_lines)
    site_exclusion = road_land.buffer(0.5).union(unary_union(water).buffer(5))
    prepared_sites = prep(site_exclusion)
    spec_tree = STRtree([record[3] for record in specs])
    for site_index, (identity, kind, label, poly) in enumerate(specs):
        nearby_sites = [
            facilities[int(j)].poly.buffer(1)
            for j in spec_tree.query(poly.buffer(1), predicate="intersects")
            if int(j) < site_index
        ]
        occupied_sites = unary_union(nearby_sites)
        clear = parts(
            (poly.difference(site_exclusion) if prepared_sites.intersects(poly) else poly).difference(
                occupied_sites
            ),
            400 if kind == "school" else 100,
        )
        if not clear:
            raise ValueError(f"Facility lost: {identity}")
        polygon = max(clear, key=lambda p: p.area)
        facilities.append(
            indexed_facility(net, identity, kind, label, polygon, facility_lines, facility_tree)
            if c["homes"] > 5000
            else _facility(net, identity, kind, label, polygon, None)
        )
    reserves = [*greens, *[p.buffer(20) for p in water], *[f.poly.buffer(1) for f in facilities]]
    reserve_tree = STRtree(reserves)
    lots, blocks = candidate_lots(geo, cfg, frame)
    lots.poly = [set_precision(p, 0) for p in lots.poly]
    lots.uid = [uid("factory-lot", seed, p.wkb_hex) for p in lots.poly]
    home_ids, shop_ids = [], []
    tree = STRtree(lots.poly)
    accepted = {}
    prepared_develop = prep(develop)
    for i, p in enumerate(lots.poly):
        if not prepared_develop.intersects(p):
            continue
        nearby_reserves = reserve_tree.query(p, predicate="intersects")
        clear = (
            p.difference(unary_union([reserves[int(j)] for j in nearby_reserves]))
            if len(nearby_reserves)
            else p
        )
        choices = [q for q in parts(clear, 300) if q.distance(Point(lots.row_xy[i])) < 0.1]
        if not choices:
            continue
        q = max(choices, key=lambda p: p.area)
        if not q.buffer(-0.5).covers(
            _rect(lots.row_xy[i] + lots.normal[i] * 13, lots.tangent[i], lots.normal[i], 9, 10)
        ):
            continue
        nearby = [accepted[int(j)] for j in tree.query(q, predicate="intersects") if int(j) in accepted]
        if nearby:
            q = q.difference(unary_union(nearby))
        if q.geom_type != "Polygon" or not q.buffer(-0.4).covers(
            _rect(lots.row_xy[i] + lots.normal[i] * 13, lots.tangent[i], lots.normal[i], 9, 10)
        ):
            continue
        lots.poly[i] = q
        accepted[i] = q
        if net.graph.edge_class[lots.edge[i]] != LOCAL:
            shop_ids.append(i)
        else:
            home_ids.append(i)
    shop_ids.sort(key=lambda i: lots.poly[i].centroid.distance(Point(center)))
    if c["homes"] > 5000 and len(shop_ids) < c["shops"] - 1:
        # A city centre also has shops on side streets. Keep the remaining
        # commercial budget together around the market instead of requiring
        # every business to occupy an arterial or collector frontage.
        deficit = c["shops"] - 1 - len(shop_ids)
        market_streets = sorted(home_ids, key=lambda i: lots.poly[i].centroid.distance(Point(center)))[
            :deficit
        ]
        market_ids = set(market_streets)
        home_ids = [i for i in home_ids if i not in market_ids]
        shop_ids.extend(market_streets)
    home_ids.extend(shop_ids[c["shops"] - 1 :])
    shop_ids = shop_ids[: c["shops"] - 1]
    home_ids.sort(key=lambda i: (lots.poly[i].centroid.distance(Point(center)), lots.uid[i]))
    print("capacity", len(home_ids), "homes", len(shop_ids), "shops", flush=True)
    if len(home_ids) < c["homes"] * 0.9 or len(shop_ids) != c["shops"] - 1:
        raise ValueError(f"Insufficient capacity {len(home_ids)} for {c['homes']}")
    if len(home_ids) > c["homes"] * 1.1:
        raise ValueError(
            "Plan exceeds approved density; reduce neighbourhood count rather than leaving empty streets"
        )
    lu = LandUse(
        net,
        lots.subset(home_ids),
        lots.subset(shop_ids),
        facilities,
        [],
        frame,
        max(frame[2], -frame[1]),
        _exits(net, frame, center),
    )
    prem = build_premises(lu, cfg, terrain, era)
    by_uid = {uid("premise", lots.uid[i]): i for i in home_ids + shop_ids}
    pool_shapes = {}
    pool_candidates = []
    for j, key in enumerate(prem.uid):
        if key in by_uid:
            i = by_uid[key]
            t, n, row = lots.tangent[i], lots.normal[i], lots.row_xy[i]
            v = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
            w, d = 9 + (v % 4) * 0.5, 10 + ((v // 4) % 3) * 0.6
            pos = row + n * (7 + d / 2)
            fp = _rect(pos, t, n, w, d)
            if not prem.lot[j].buffer(-0.4).covers(fp):
                w, d, pos = 9.0, 10.0, row + n * 13
                fp = _rect(pos, t, n, w, d)
            prem.xy[j] = pos
            prem.width[j] = w
            prem.depth[j] = d
            prem.footprint[j] = fp
            pool = _rect(row + n * 29 + t * 1.5, t, n, 5.0, 8.0)
            if prem.residential[j] and prem.lot[j].buffer(-1).covers(pool) and pool.distance(fp) > 3:
                pool_candidates.append((key, j, pool))
        else:
            f = next(f for f in facilities if f.id == prem.facility_id[j])
            # A clipped campus can be concave. Its centroid may lie in the road
            # or water cutout, so choose a point with real building clearance.
            if not prem.lot[j].buffer(-2).covers(Point(prem.xy[j])):
                prem.xy[j] = np.asarray(polylabel(prem.lot[j], tolerance=0.5).coords[0])
            if f.id == "CHURCH-01":
                prem.building_type[j] = "church"
                prem.width[j] = 40
                prem.depth[j] = 55
                prem.height[j] = 21
                prem.roof[j] = "gable"
                f.kind = "church"
            elif f.id == "MARKET-01":
                prem.ptype[j] = 1
                prem.building_type[j] = "market_hall"
                prem.width[j] = 55
                prem.depth[j] = 50
                prem.height[j] = 12
            elif f.kind == "industrial":
                prem.width[j] = 44
                prem.depth[j] = 30
            t = np.array([math.cos(prem.heading[j]), math.sin(prem.heading[j])])
            n = prem.normal[j]
            for _ in range(30):
                fp = _rect(prem.xy[j], t, n, prem.width[j], prem.depth[j])
                if prem.lot[j].buffer(-1).covers(fp):
                    break
                prem.width[j] *= 0.9
                prem.depth[j] *= 0.9
            prem.footprint[j] = fp
        if not prem.lot[j].buffer(0.001).covers(prem.footprint[j]):
            raise ValueError(f"Footprint outside own parcel: {prem.ids[j]}")
    if len(pool_candidates) < c["pools"]:
        raise ValueError("Insufficient legal backyard pool positions")
    assign_households(prem, cfg, era)
    prem.attrs["solar"][:] = False
    prem.attrs["pv_kw"][:] = 0
    prem.attrs["pool"][:] = False
    for _, j, pool in sorted(
        pool_candidates, key=lambda item: hashlib.sha256((seed + item[0]).encode()).hexdigest()
    )[: c["pools"]]:
        prem.attrs["pool"][j] = True
        pool_shapes[prem.ids[j]] = pool
    assign_addresses(prem, net, center)
    print("networks", len(prem.ids), "premises", flush=True)
    ctx = NetContext(cfg, lu, prem, terrain, era, cfg.seeds.for_("town"))
    networks = {}
    for name, builder in [("electric", build_electric), ("water", build_water), ("gas", build_gas)]:
        networks[name] = builder(ctx)
        print(name, "built", round(time.perf_counter() - started, 1), "seconds", flush=True)
    town = Town(cfg, geo, lu, prem, networks)
    town.customers = build_customers(town)
    snapshot = build_snapshot(town, embed_state=False)
    original = {pid: prem.lot[i] for i, pid in enumerate(prem.ids)}
    for p in snapshot["parcels"]:
        p["polygon"] = vect(original[p["premiseId"]])
    # Geometry union is performed once, not per district or per property.
    occupied = unary_union([*prem.lot, *[f.poly for f in facilities], road_land])
    waters = unary_union(water).intersection(box(*frame))
    environments = waters.buffer(28).difference(waters)
    land = []
    for kind, g in [
        ("water", waters),
        ("environmental", environments),
        ("parks", develop),
        ("agricultural", box(*frame).difference(develop)),
    ]:
        for i, p in enumerate(
            parts(
                g.difference(occupied)
                .difference(waters if kind not in ("water",) else Polygon())
                .difference(environments if kind not in ("water", "environmental") else Polygon()),
                25,
            )
        ):
            land.append(area_record(f"{kind}-{i}", kind, p))
    btree = STRtree(blocks)
    members = {}
    for p in snapshot["premises"]:
        hits = btree.query(Point(p["x"], -p["z"]), predicate="within")
        if not len(hits):
            raise ValueError(f"Property has no block {p['id']}")
        b = int(hits[0])
        p["atlasBlockId"] = f"BLOCK-{b:05}"
        members.setdefault(b, []).append(p["id"])
        if p["id"] in pool_shapes:
            p["poolPolygon"] = vect(pool_shapes[p["id"]])
    block_records = [
        area_record(f"BLOCK-{i:05}", "block", blocks[i], premiseIds=ids) for i, ids in members.items()
    ]
    budget = {
        "targetHomes": c["homes"],
        "homeTolerance": 0.1,
        "homes": len(home_ids),
        "pools": c["pools"],
        "solar": 0,
        "school": c["schools"],
        "church": c["church"],
        "commercial": c["shops"],
        "industrial": c["industry"],
    }
    snapshot["atlasDesign"] = {
        "version": "curated-town-factory/1",
        "presetId": preset,
        "revision": 1,
        "name": c["name"],
        "curated": True,
        "defaultArt": "native",
        "focus": {"x": center[0], "z": -center[1], "viewHeightM": -frame[1]},
        "openAreas": land,
        "landUseZones": [],
        "blocks": block_records,
        "parks": [],
        "fields": [],
        "featureBudget": budget,
        "palette": c["palette"],
        "sourceReview": "Geometry generated from fixed world-builder configuration; visual review required.",
    }
    data = {
        "bounds": [0, 0, frame[2], -frame[1]],
        "metresPerUnit": 1,
        "budget": budget,
        "roads": snapshot["roads"],
        "properties": snapshot["premises"],
        "parcels": snapshot["parcels"],
        "buildings": snapshot["buildings"],
        "blocks": block_records,
        "land": land,
        "facilities": snapshot["facilities"],
        "civicGreen": area_record(
            "civic-green",
            "parks",
            greens[min(range(len(centers)), key=lambda i: np.linalg.norm(centers[i] - center))],
        ),
        "palette": c["palette"],
    }
    dest = ROOT / preset
    dest.mkdir(parents=True, exist_ok=True)
    master = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
        + str(frame[2])
        + " "
        + str(-frame[1])
        + '">'
        + "".join(
            '<path data-premise="'
            + p["premiseId"]
            + '" d="M'
            + "L".join(f"{q['x']},{q['z']}" for q in p["polygon"])
            + 'Z"/>'
            for p in data["parcels"]
        )
        + "</svg>"
    )
    snapshot["atlasDesign"]["masterSvgSha256"] = hashlib.sha256(master.encode()).hexdigest()
    checkpoint_sources(preset, snapshot, data, master, c, seed, budget, time.perf_counter() - started)
    return finish_bake(snapshot, data, master, c, seed, budget, started)


def finish_bake(snapshot, data, master, c, seed, budget, started):
    dest = ROOT / c["id"]
    dest.mkdir(parents=True, exist_ok=True)
    print("checking geometry", flush=True)
    checks = geometry_checks(snapshot)
    manifest = {
        "schemaVersion": "curated-town-build/1",
        "config": c,
        "featureBudget": budget,
        "buildSeconds": round(time.perf_counter() - started, 2),
        "artStatus": "pending",
        "geometryPassed": all(q["status"] == "pass" for q in checks),
        "seed": seed,
        "bounds": data["bounds"],
    }
    print(json.dumps(manifest, indent=2), flush=True)
    failed = [q for q in checks if q["status"] != "pass"]
    if failed:
        (dest / "build-failure.json").write_text(json.dumps(failed, indent=2), encoding="utf-8")
        raise ValueError(json.dumps(failed, indent=2))
    # Only validated geometry replaces a prior bake. The manifest is written last.
    (dest / "master.svg").write_text(master, encoding="utf-8")
    for name, obj in [
        ("snapshot", snapshot),
        ("geometry", data),
        ("checks", checks),
        ("build-manifest", manifest),
    ]:
        pending = dest / f"{name}.json.pending"
        pending.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
        pending.replace(dest / f"{name}.json")
    (dest / "build-failure.json").unlink(missing_ok=True)
    write_catalog()
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("preset", nargs="?", choices=[c["id"] for c in CONFIGS if not c.get("existing")])
    parser.add_argument(
        "--config",
        type=Path,
        help="Build a new, unlisted town from an explicit JSON budget; never overwrite an existing id",
    )
    parser.add_argument(
        "--resume-checkpoint", help="Re-run final QA and publish a matching unpublished source checkpoint"
    )
    args = parser.parse_args()
    if sum(map(bool, [args.preset, args.config, args.resume_checkpoint])) != 1:
        parser.error("provide a preset, --config JSON, OR --resume-checkpoint ID")
    if args.resume_checkpoint:
        resume_checkpoint(args.resume_checkpoint)
    elif args.config:
        custom = validate_custom_config(json.loads(args.config.read_text(encoding="utf-8")))
        build(custom["id"], custom)
    else:
        build(args.preset)
