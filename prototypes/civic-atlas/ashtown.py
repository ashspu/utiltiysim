"""Fixed Ashtown authoring: hierarchy, protected civic core, parcels, live world."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline
from shapely import set_precision
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union
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
from utilsim.gen.landuse import LandUse, _exits
from utilsim.gen.parcels import candidate_lots, land_blocks
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

PRESET = "ashtown-5000"
ROOT = Path(__file__).parent / "web/presets" / PRESET
OUT = Path(__file__).resolve().parents[4] / "outputs/ashtown"
SEED = "ASHTOWN-5000-V1"
FRAME = (0.0, -2800.0, 4200.0, 0.0)
CENTER = (2050.0, -1340.0)


def site(x0, z0, x1, z1):
    return box(x0, -z1, x1, -z0)


def curve(pts):
    a = np.array([(x, -z) for x, z in pts], dtype=float)
    t = np.r_[0, np.cumsum(np.linalg.norm(np.diff(a, axis=0), axis=1))]
    return CubicSpline(t, a, bc_type="natural")(
        np.unique(np.r_[t, np.linspace(0, t[-1], max(10, int(t[-1] / 12)))])
    )


def make_plan(cfg, terrain, era):
    def road(name, kind, pts):
        return RoadLine(curve(pts), kind, name, source_id=uid("ashtown-road", name))

    lines = [
        road(
            "North County Road",
            ARTERIAL,
            [(0, 260), (800, 240), (1600, 330), (2400, 280), (3200, 270), (4200, 250)],
        ),
        road(
            "South Bypass",
            ARTERIAL,
            [(0, 2540), (900, 2500), (1800, 2530), (2600, 2620), (3400, 2600), (4200, 2500)],
        ),
        road("West County Road", ARTERIAL, [(300, 0), (330, 700), (240, 1450), (380, 2100), (400, 2800)]),
        road("East Bypass", ARTERIAL, [(3960, 0), (3890, 900), (4030, 1900), (3910, 2800)]),
        road(
            "Old Market Road",
            COLLECTOR,
            [(240, 1500), (900, 1250), (1450, 1020), (1850, 1000), (2340, 1000), (2920, 850), (3900, 700)],
        ),
        road(
            "Green Avenue",
            COLLECTOR,
            [(280, 1850), (1000, 1800), (1700, 1550), (2300, 1580), (2940, 1660), (4050, 2000)],
        ),
        road(
            "Westgate Avenue", COLLECTOR, [(1080, 240), (1020, 700), (1100, 1200), (1010, 1800), (1150, 2510)]
        ),
        road(
            "Eastgate Avenue", COLLECTOR, [(2740, 270), (2670, 790), (2570, 1240), (2740, 1740), (2680, 2620)]
        ),
        road(
            "Market Street",
            COLLECTOR,
            [(1770, 325), (1800, 800), (1600, 1090), (1570, 1400), (1700, 1550), (1820, 2060), (1800, 2530)],
        ),
        road(
            "Church Street",
            COLLECTOR,
            [(2350, 285), (2310, 750), (2460, 1020), (2480, 1300), (2410, 1580), (2350, 2000), (2440, 2600)],
        ),
        road("Mill Lane", COLLECTOR, [(3310, 268), (3370, 930), (3210, 1440), (3190, 2030), (3320, 2600)]),
    ]
    green = Point(2070, -1280).buffer(1, quad_segs=48)
    from shapely.affinity import scale

    green = scale(green, 235, 205, origin=(2070, -1280))
    church = site(2280, 1060, 2420, 1260)
    market = site(1660, 1130, 1840, 1410)
    specs = [
        ("CHURCH-01", "school", "Ashtown Minster", church, "Church Street"),
        ("MARKET-01", "depot", "Ashtown Market Hall", market, "Market Street"),
    ]
    school_centers = [
        (760, 630),
        (1400, 550),
        (2120, 560),
        (2970, 620),
        (3510, 1120),
        (2910, 1870),
        (2080, 2200),
        (1460, 2160),
        (730, 1860),
        (1270, 1330),
    ]
    for i, (x, z) in enumerate(school_centers):
        specs.append(
            (
                f"SCHOOL-{i + 1:02}",
                "school",
                f"Ashtown School {i + 1}",
                site(x - 60, z - 55, x + 60, z + 55),
                None,
            )
        )
    industry = site(3370, 1840, 3870, 2420)
    for row in range(10):
        z = 1870 + row * 54
        lines.append(road(f"Works Row {row + 1}", LOCAL, [(3280, z), (3900, z)]))
        for col in range(6):
            x = 3400 + col * 76
            specs.append(
                (
                    f"INDUSTRY-{row * 6 + col + 1:02}",
                    "industrial",
                    f"Ashtown Works {row * 6 + col + 1}",
                    site(x, z + 11, x + 58, z + 44),
                    f"Works Row {row + 1}",
                )
            )
    lines.append(road("Foundry Road", COLLECTOR, [(3280, 1800), (3280, 2460)]))
    lines.append(road("Works East Road", COLLECTOR, [(3900, 1800), (3900, 2470)]))
    lines.append(road("Service Avenue", COLLECTOR, [(3190, 1800), (3900, 1800), (4010, 1860)]))
    lines.append(road("Depot Avenue", COLLECTOR, [(3200, 2460), (3900, 2470), (3920, 2540)]))
    specs.extend(
        [
            ("PUMP-01", "pump_station", "Ashtown Water Works", site(3510, 2440, 3580, 2485), "Depot Avenue"),
            ("SUB-01", "substation", "Ashtown Substation", site(3600, 2440, 3670, 2485), "Depot Avenue"),
            ("GATE-01", "city_gate", "Ashtown Gas Gate", site(3690, 2450, 3740, 2490), "Depot Avenue"),
            ("TANK-01", "elevated_tank", "North Water Tower", site(3550, 400, 3590, 440), None),
        ]
    )
    reserved = unary_union([green, *[s[3].buffer(5) for s in specs], industry])
    develop = site(410, 380, 3810, 2410)
    # Two landscape fingers join the civic green, without cutting the public core.
    creek = LineString(
        curve([(450, 0), (560, 350), (465, 810), (580, 1330), (460, 1750), (550, 2240), (620, 2800)])
    )
    water = creek.buffer(9)
    forest = creek.buffer(32)
    reserved = reserved.union(forest)
    rng = np.random.default_rng(29071)
    names = [
        "Ash",
        "Willow",
        "Birch",
        "Cedar",
        "Oak",
        "Hazel",
        "Juniper",
        "Maple",
        "Elm",
        "Linden",
        "Chestnut",
        "Rowan",
        "Orchard",
        "Hawthorn",
        "Beech",
        "Sycamore",
    ]
    # Partition the real street-bounded land with gently curved streets. This
    # bakes a fixed plan once; no geometry changes at runtime.
    for generation in range(6):
        net = planarize([], lines, min_dangle=25, min_edge=1)
        geo = Geography(net, era, terrain, CENTER, FRAME, cfg.town.anchor_lat, cfg.town.anchor_lon, {})
        blocks, _ = land_blocks(geo, FRAME)
        additions = []
        for block in blocks:
            available = block.intersection(develop).difference(reserved)
            if available.area < 24000:
                continue
            rect = block.minimum_rotated_rectangle
            q = np.array(rect.exterior.coords[:4])
            edges = np.diff(np.vstack([q, q[0]]), axis=0)
            long = edges[np.argmax(np.linalg.norm(edges, axis=1))]
            long /= np.linalg.norm(long)
            cross = np.array([-long[1], long[0]])
            center = np.array(available.representative_point().coords[0])
            # Position/angle variety respects the surrounding irregular block.
            angle = rng.uniform(-0.18, 0.18)
            direction = cross * math.cos(angle) + long * math.sin(angle)
            normal = np.array([-direction[1], direction[0]])
            lengths = np.linspace(-5000, 5000, 9)
            wiggle = rng.uniform(-16, 16) * np.sin(lengths / 190)
            raw = LineString(
                [center + direction * d + normal * w for d, w in zip(lengths, wiggle, strict=True)]
            )
            clipped = raw.intersection(block.buffer(18)).difference(reserved.buffer(9))
            for part in getattr(clipped, "geoms", [clipped]):
                if part.geom_type != "LineString" or part.length < 85:
                    continue
                if part.intersection(available).length < 65:
                    continue
                idx = len(lines) + len(additions)
                name = f"{names[idx % len(names)]} {'Crescent' if idx % 3 == 0 else 'Lane' if idx % 3 == 1 else 'Street'} {idx // len(names) + 1}"
                additions.append(
                    RoadLine(np.array(part.coords), LOCAL, name, source_id=uid("ash-local", idx))
                )
        lines.extend(additions)
        print("subdivision", generation, "added", len(additions), flush=True)
    # Attach any dangling authored campus access to the nearest connected road
    # via short public access lanes, then run the same graph quality gate.
    net = planarize([], lines, min_dangle=25, min_edge=1)
    print("roads", net.summary(), flush=True)
    road_land = unary_union(
        [
            LineString(g).buffer(ROW_WIDTH[net.graph.edge_class[i]] / 2, cap_style=2)
            for i, g in enumerate(net.graph.geometry)
        ]
    )
    facilities = []
    for identity, kind, label, p, street in specs:
        clear = parts(p.difference(road_land.buffer(1)).difference(forest))
        if not clear:
            raise ValueError(f"Lost reserved site {identity}")
        facilities.append(_facility(net, identity, kind, label, max(clear, key=lambda p: p.area), street))
    return net, develop, green, water, forest, industry, facilities, road_land


def build():
    ROOT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_preset(
        "village",
        seed=SEED,
        houses=5000,
        overrides={
            "town": {"terrain_relief_m": 0, "industrial_lots": 10},
            "housing": {
                "lot_frontage_m": {"pre_1945": 14.0, "postwar": 15.0, "modern": 16.0},
                "lot_depth_m": {"pre_1945": 36.0, "postwar": 40.0, "modern": 43.0},
            },
        },
    )
    terrain = Terrain(cfg.seeds.for_("town"), relief_m=0, base_m=90)
    era = build_era_field(
        cfg.seeds.for_("town"), CENTER, 2500, FRAME, 5000, 1925, 90, 24, cfg.gas.all_electric_district_share
    )
    net, develop, green, water, forest, industry, facilities, road_land = make_plan(cfg, terrain, era)
    geo = Geography(
        net,
        era,
        terrain,
        CENTER,
        FRAME,
        cfg.town.anchor_lat,
        cfg.town.anchor_lon,
        {"type": "synthetic", "label": "Ashtown", "expansion": "none", "streetModel": "ashtown/1"},
    )
    lots, blocks = candidate_lots(geo, cfg, FRAME)
    lots.poly = [set_precision(p, 0) for p in lots.poly]
    lots.uid = [uid("ash-lot", p.wkb_hex) for p in lots.poly]
    forbidden = unary_union([forest, green, industry, road_land, *[f.poly.buffer(2) for f in facilities]])
    tree = STRtree(lots.poly)
    accepted = {}
    homes = []
    shop_candidates = []
    for i, p in enumerate(lots.poly):
        valid = [
            q
            for q in parts(p.difference(forbidden).intersection(develop), 350)
            if q.distance(Point(lots.row_xy[i])) < 0.55
        ]
        if not valid:
            continue
        p = max(valid, key=lambda q: q.area)
        t, n, row = lots.tangent[i], lots.normal[i], lots.row_xy[i]
        fitted = _rect(row + n * 13, t, n, 9.0, 10.0)
        if not p.buffer(-0.6).covers(fitted):
            continue
        nearby = [accepted[int(j)] for j in tree.query(p, predicate="intersects") if int(j) in accepted]
        if nearby:
            p = p.difference(unary_union(nearby))
        if p.geom_type != "Polygon" or not p.buffer(-0.6).covers(fitted):
            continue
        lots.poly[i] = p
        accepted[i] = p
        c = p.centroid
        if c.distance(Point(CENTER)) < 700 and net.graph.edge_class[lots.edge[i]] != LOCAL:
            shop_candidates.append(i)
        else:
            homes.append(i)
    print("capacity", len(homes), "shops", len(shop_candidates), flush=True)
    if len(homes) < 4500:
        raise ValueError("Residential capacity below approved range")
    # Select contiguous interior capacity; outer unused land remains greenspace.
    homes.sort(key=lambda i: lots.poly[i].centroid.distance(Point(CENTER)))
    homes = homes[:5000]
    shop_candidates.sort(key=lambda i: lots.poly[i].centroid.distance(Point(CENTER)))
    shops = shop_candidates[:159]
    if len(shops) < 159:
        raise ValueError("Market district needs more commercial frontage")
    lu = LandUse(
        net, lots.subset(homes), lots.subset(shops), facilities, [], FRAME, 3000.0, _exits(net, FRAME, CENTER)
    )
    prem = build_premises(lu, cfg, terrain, era)
    by_uid = {uid("premise", lots.uid[i]): i for i in homes + shops}
    candidates = {}
    for j, key in enumerate(prem.uid):
        if key in by_uid:
            i = by_uid[key]
            t, n, row = lots.tangent[i], lots.normal[i], lots.row_xy[i]
            variant = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
            w, d = 9 + (variant % 4) * 0.5, 10 + ((variant // 4) % 3) * 0.6
            c = row + n * (7 + d / 2)
            footprint = _rect(c, t, n, w, d)
            if not prem.lot[j].buffer(-0.4).covers(footprint):
                w, d, c = 9.0, 10.0, row + n * 13
                footprint = _rect(c, t, n, w, d)
            prem.xy[j] = c
            prem.width[j] = w
            prem.depth[j] = d
            prem.footprint[j] = footprint
            pool = _rect(row + n * 29 + t * 1.5, t, n, 5.0, 8.0)
            if prem.residential[j] and prem.lot[j].buffer(-1).covers(pool) and pool.distance(footprint) > 3:
                candidates[key] = pool
        else:
            f = next(f for f in facilities if f.id == prem.facility_id[j])
            if f.id == "CHURCH-01":
                prem.building_type[j] = "church"
                prem.width[j] = 55.0
                prem.depth[j] = 85.0
                prem.height[j] = 24.0
                prem.roof[j] = "gable"
                f.kind = "church"
            elif f.id == "MARKET-01":
                prem.ptype[j] = 1
                prem.building_type[j] = "market_hall"
                prem.width[j] = 100.0
                prem.depth[j] = 85.0
                prem.height[j] = 12.0
            elif f.kind == "industrial":
                prem.width[j] = 38.0
                prem.depth[j] = 21.0
            t = np.array([math.cos(prem.heading[j]), math.sin(prem.heading[j])])
            n = prem.normal[j]
            for _ in range(25):
                footprint = _rect(prem.xy[j], t, n, prem.width[j], prem.depth[j])
                if prem.lot[j].buffer(-1).covers(footprint):
                    break
                prem.width[j] *= 0.92
                prem.depth[j] *= 0.92
            prem.footprint[j] = footprint
        if not prem.lot[j].buffer(0.001).covers(prem.footprint[j]):
            raise ValueError(f"Footprint fit {prem.ids[j]}")
    print("pool capacity", len(candidates), flush=True)
    if len(candidates) < 1000:
        raise ValueError("Pool capacity")
    pools = set(sorted(candidates, key=lambda k: hashlib.sha256((SEED + k).encode()).hexdigest())[:1000])
    assign_households(prem, cfg, era)
    prem.attrs["solar"][:] = False
    prem.attrs["pv_kw"][:] = 0
    prem.attrs["pool"][:] = False
    pool_shapes = {}
    for j, key in enumerate(prem.uid):
        if key in pools:
            prem.attrs["pool"][j] = True
            pool_shapes[prem.ids[j]] = candidates[key]
    assign_addresses(prem, net, CENTER)
    print("building utility networks", flush=True)
    ctx = NetContext(cfg, lu, prem, terrain, era, cfg.seeds.for_("town"))
    networks = {"electric": build_electric(ctx), "water": build_water(ctx), "gas": build_gas(ctx)}
    town = Town(cfg, geo, lu, prem, networks)
    town.customers = build_customers(town)
    snapshot = build_snapshot(town, embed_state=False)
    original = {pid: prem.lot[i] for i, pid in enumerate(prem.ids)}
    for p in snapshot["parcels"]:
        p["polygon"] = vect(original[p["premiseId"]])
    occupied = unary_union([*prem.lot, *[f.poly for f in facilities], road_land])
    land = []
    for kind, g in [
        ("water", water),
        ("environmental", forest.difference(water)),
        ("parks", develop.difference(forest)),
        ("agricultural", box(*FRAME).difference(develop.union(forest))),
    ]:
        for i, p in enumerate(parts(g.difference(occupied), 25)):
            land.append(area_record(f"{kind}-{i}", kind, p))
    block_records = []
    btree = STRtree(blocks)
    members = {}
    for home in snapshot["premises"]:
        hits = btree.query(Point(home["x"], -home["z"]), predicate="within")
        if not len(hits):
            raise ValueError("Unowned property")
        idx = int(hits[0])
        home["atlasBlockId"] = f"ASH-B{idx:04}"
        members.setdefault(idx, []).append(home["id"])
        if home["id"] in pool_shapes:
            home["poolPolygon"] = vect(pool_shapes[home["id"]])
    for i, ids in members.items():
        block_records.append(area_record(f"ASH-B{i:04}", "block", blocks[i], premiseIds=ids))
    budget = {
        "targetHomes": 5000,
        "homeTolerance": 0.1,
        "homes": len(homes),
        "pools": 1000,
        "solar": 0,
        "school": 10,
        "church": 1,
        "commercial": 160,
        "industrial": 60,
    }
    snapshot["atlasDesign"] = {
        "version": "ashtown/1",
        "presetId": PRESET,
        "revision": 1,
        "name": "Ashtown",
        "curated": True,
        "defaultArt": "native",
        "focus": {"x": 2050, "z": 1340, "viewHeightM": 2700},
        "openAreas": land,
        "landUseZones": [area_record("civic-green", "parks", green)],
        "blocks": block_records,
        "parks": [],
        "fields": [],
        "featureBudget": budget,
        "sourceReview": "Generated-asset tiled map experiment; visual approval pending.",
    }
    data = {
        "bounds": [0, 0, 4200, 2800],
        "metresPerUnit": 1,
        "budget": budget,
        "roads": snapshot["roads"],
        "properties": snapshot["premises"],
        "parcels": snapshot["parcels"],
        "buildings": snapshot["buildings"],
        "blocks": block_records,
        "land": land,
        "facilities": snapshot["facilities"],
        "civicGreen": area_record("civic-green", "parks", green),
    }
    (ROOT / "geometry.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    # Geometry contract hash, independent from textures and rendered tile caches.
    master = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4200 2800">'
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
    (ROOT / "master.svg").write_text(master, encoding="utf-8")
    snapshot["atlasDesign"]["masterSvgSha256"] = hashlib.sha256(master.encode()).hexdigest()
    (ROOT / "snapshot.json").write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")
    checks = geometry_checks(snapshot)
    for folder in (ROOT, OUT):
        (folder / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2), flush=True)
    if any(c["status"] != "pass" for c in checks):
        raise ValueError("Quality gates failed")
    print("ASHTOWN BAKED", len(homes), snapshot["count"], flush=True)


if __name__ == "__main__":
    build()
