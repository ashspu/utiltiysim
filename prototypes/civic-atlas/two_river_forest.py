"""Two River Forest: counted geometry first; illustration is a replaceable layer.

Coordinates below are authored against the generated zoning proposal. This is
an explicit, editable interpretation, not a claim of automatic raster tracing.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline
from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quality import geometry_checks
from town500_world import _facility

from utilsim.config import load_preset
from utilsim.core.ids import uid
from utilsim.customers.generate import build_customers
from utilsim.gen.addresses import assign_addresses
from utilsim.gen.buildings import _rect, assign_households, build_premises
from utilsim.gen.landuse import LandUse, _exits
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

PRESET = "two-river-forest-500"
ROOT = Path(__file__).parent / "web/presets" / PRESET
OUT = Path(__file__).resolve().parents[4] / "outputs/two-river-forest"
SCALE = 1.7
SEED = "TWO-RIVER-FOREST-500-V1"
FRAME = (0.0, -1024 * SCALE, 1536 * SCALE, 0.0)


def xy(p):
    return np.array([p[0] * SCALE, -p[1] * SCALE])


def poly(points):
    return Polygon([xy(p) for p in points])


def smooth(points, closed=False):
    a = np.asarray(points, dtype=float)
    if closed and not np.array_equal(a[0], a[-1]):
        a = np.vstack([a, a[0]])
    t = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(a, axis=0), axis=1))]
    cs = CubicSpline(t, a, bc_type="periodic" if closed else "natural")
    return cs(np.unique(np.r_[t, np.linspace(0, t[-1], max(12, int(t[-1] / 5)))]))


def parts(g, minimum=1):
    return [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and p.area > minimum]


def vect(p):
    return [{"x": float(x), "z": float(-y)} for x, y in p.exterior.coords[:-1]]


def area_record(identity, kind, p, **kw):
    return dict(id=identity, kind=kind, polygon=vect(p), holes=[vect(Polygon(r)) for r in p.interiors], **kw)


def source_plan():
    specs = []

    def road(name, kind, pts, closed=False):
        specs.append((name, kind, smooth(pts, closed)))

    road(
        "Main Street",
        COLLECTOR,
        [
            (696, 0),
            (719, 82),
            (734, 156),
            (734, 274),
            (734, 490),
            (733, 669),
            (731, 718),
            (748, 800),
            (732, 886),
            (738, 1024),
        ],
    )
    road(
        "North County Road",
        ARTERIAL,
        [
            (0, 65),
            (180, 60),
            (360, 54),
            (545, 67),
            (719, 82),
            (914, 70),
            (1100, 62),
            (1180, 67),
            (1452, 70),
            (1536, 65),
        ],
    )
    road(
        "Forest Bypass",
        ARTERIAL,
        [
            (1452, 0),
            (1452, 250),
            (1452, 449),
            (1435, 576),
            (1380, 675),
            (1309, 749),
            (1200, 861),
            (1070, 925),
            (921, 952),
            (740, 985),
            (530, 1024),
        ],
    )
    road(
        "River Road",
        COLLECTOR,
        [
            (480, 292),
            (571, 274),
            (650, 268),
            (734, 274),
            (862, 284),
            (950, 299),
            (1017, 342),
            (1090, 365),
            (1185, 412),
            (1203, 480),
            (1198, 611),
            (1232, 660),
            (1269, 714),
            (1309, 749),
        ],
    )
    road(
        "Bridge Avenue",
        COLLECTOR,
        [
            (425, 550),
            (483, 518),
            (554, 502),
            (630, 489),
            (734, 490),
            (842, 498),
            (922, 520),
            (1006, 548),
            (1082, 569),
            (1160, 610),
            (1198, 611),
        ],
    )
    road(
        "Mill Road",
        COLLECTOR,
        [
            (1006, 548),
            (1003, 597),
            (985, 632),
            (948, 668),
            (913, 714),
            (1005, 741),
            (1107, 770),
            (1190, 773),
            (1268, 767),
            (1309, 749),
        ],
    )
    road("Works Lane", LOCAL, [(985, 632), (1069, 657), (1157, 684), (1140, 772)])
    road("Foundry Lane", LOCAL, [(1082, 569), (1069, 657), (1039, 751)])
    road(
        "Cedar Crescent",
        LOCAL,
        [
            (734, 156),
            (674, 147),
            (582, 141),
            (549, 112),
            (487, 105),
            (455, 128),
            (454, 174),
            (467, 211),
            (507, 210),
            (541, 200),
            (565, 168),
            (582, 141),
        ],
    )
    road("Cedar Lane", LOCAL, [(441, 239), (478, 222), (507, 210)])
    road(
        "Alder Drive",
        LOCAL,
        [
            (480, 292),
            (455, 253),
            (422, 216),
            (400, 176),
            (397, 163),
            (370, 146),
            (363, 118),
            (380, 94),
            (411, 90),
            (441, 108),
            (455, 128),
        ],
    )
    road(
        "Birch Walk",
        LOCAL,
        [(441, 239), (505, 240), (565, 235), (609, 214), (634, 183), (648, 159), (674, 147)],
    )
    road(
        "Maple Close",
        LOCAL,
        [
            (734, 182),
            (777, 180),
            (816, 165),
            (838, 160),
            (849, 187),
            (843, 211),
            (817, 224),
            (777, 223),
            (734, 223),
        ],
    )
    road("Maple Mews", LOCAL, [(816, 165), (827, 134)])
    road(
        "Pine Crescent",
        LOCAL,
        [
            (950, 299),
            (929, 265),
            (942, 214),
            (932, 175),
            (932, 145),
            (984, 134),
            (1038, 123),
            (1058, 150),
            (1093, 183),
            (1100, 201),
            (1068, 215),
            (1043, 241),
            (1081, 275),
            (1130, 282),
            (1136, 258),
            (1119, 222),
            (1100, 201),
        ],
    )
    road("Fern Lane", LOCAL, [(942, 214), (963, 197), (1001, 188), (1035, 208), (1043, 241)])
    road("Pine Green", LOCAL, [(929, 265), (958, 266), (983, 276), (971, 300)])
    road("Juniper Rise", LOCAL, [(1081, 275), (1067, 351), (1090, 365)])
    road("Juniper Court", LOCAL, [(1071, 327), (1129, 336)])
    road("School Lane", LOCAL, [(480, 292), (483, 339), (488, 375), (509, 412), (536, 450), (554, 502)])
    road("School Close", LOCAL, [(488, 375), (510, 361), (554, 350)])
    road("School Green", LOCAL, [(570, 310), (554, 350), (560, 389), (589, 426), (642, 430)])
    road(
        "Willow Crescent",
        LOCAL,
        [
            (483, 518),
            (425, 550),
            (398, 531),
            (392, 475),
            (408, 424),
            (440, 394),
            (469, 431),
            (503, 447),
            (526, 478),
            (483, 487),
            (450, 483),
            (421, 452),
            (408, 424),
        ],
    )
    road("Willow Link", LOCAL, [(526, 478), (536, 450)])
    road("Church Lane", LOCAL, [(777, 336), (814, 340), (829, 314), (813, 286)])
    road("Chapel Crescent", LOCAL, [(777, 336), (780, 380), (828, 389), (866, 413), (878, 447), (870, 491)])
    road("Chapel Walk", LOCAL, [(803, 491), (806, 449), (843, 449), (878, 447)])
    road(
        "Oak Terrace",
        LOCAL,
        [(950, 299), (928, 322), (907, 356), (928, 378), (986, 392), (1040, 410), (1067, 351)],
    )
    road("Oak Court", LOCAL, [(1040, 410), (1012, 446), (1006, 478), (923, 465), (907, 453)])
    road(
        "Elm Crescent",
        LOCAL,
        [
            (1006, 548),
            (1048, 548),
            (1072, 512),
            (1086, 475),
            (1125, 445),
            (1156, 466),
            (1166, 492),
            (1152, 524),
            (1134, 536),
            (1094, 529),
            (1072, 512),
        ],
    )
    road("Elm Court", LOCAL, [(1125, 445), (1120, 425)])
    road(
        "Meadow Lane",
        LOCAL,
        [(483, 518), (497, 547), (499, 586), (524, 620), (565, 649), (610, 668), (660, 670), (733, 669)],
    )
    road("Meadow Court", LOCAL, [(524, 620), (548, 595), (548, 550)])
    road(
        "Hawthorn Crescent",
        LOCAL,
        [
            (660, 670),
            (660, 608),
            (639, 588),
            (616, 576),
            (610, 540),
            (651, 535),
            (689, 536),
            (678, 509),
            (655, 491),
        ],
    )
    road("Hawthorn Link", LOCAL, [(616, 576), (595, 609), (565, 649)])
    road("Sycamore Close", LOCAL, [(733, 584), (789, 584), (789, 555), (840, 558), (873, 557), (896, 548)])
    road(
        "Sycamore Crescent",
        LOCAL,
        [
            (789, 584),
            (789, 620),
            (827, 622),
            (850, 618),
            (870, 645),
            (885, 651),
            (916, 630),
            (935, 578),
            (920, 545),
            (892, 520),
        ],
    )
    road("South Walk", LOCAL, [(733, 669), (790, 670), (846, 671), (885, 651)])
    # All junction endpoints are snapped to the closest other authored line,
    # before planarisation. No extra pick-only or approximate road overlay.
    for index in range(len(specs)):
        pts = specs[index][2]
        for j in (0, -1):
            p = Point(pts[j])
            best = None
            for k, (_, _, other) in enumerate(specs):
                if k == index:
                    continue
                line = LineString(other)
                d = line.distance(p)
                if d < 12 and (best is None or d < best[0]):
                    best = (d, line.interpolate(line.project(p)), k)
            if best:
                pts[j] = best[1].coords[0]
                target = specs[best[2]][2]
                seg = min(
                    range(len(target) - 1), key=lambda i: LineString(target[i : i + 2]).distance(best[1])
                )
                target = np.insert(target, seg + 1, pts[j], axis=0)
                specs[best[2]] = (specs[best[2]][0], specs[best[2]][1], target)
    lines = [
        RoadLine(np.array([xy(p) for p in pts]), kind, name, source_id=uid("trf-road", name))
        for name, kind, pts in specs
    ]
    west = LineString(
        [
            xy(p)
            for p in smooth(
                [
                    (215, -30),
                    (228, 50),
                    (201, 128),
                    (220, 174),
                    (288, 212),
                    (332, 271),
                    (302, 328),
                    (253, 365),
                    (216, 445),
                    (237, 521),
                    (276, 577),
                    (336, 626),
                    (401, 670),
                    (422, 738),
                    (481, 802),
                    (557, 821),
                    (650, 811),
                    (748, 799),
                    (824, 824),
                    (904, 842),
                    (954, 899),
                    (919, 958),
                    (969, 1060),
                ]
            )
        ]
    )
    east = LineString(
        [
            xy(p)
            for p in smooth(
                [
                    (1240, -30),
                    (1197, 28),
                    (1188, 67),
                    (1209, 123),
                    (1261, 185),
                    (1283, 233),
                    (1341, 295),
                    (1379, 352),
                    (1373, 419),
                    (1328, 481),
                    (1301, 545),
                    (1303, 607),
                    (1280, 665),
                    (1244, 728),
                    (1190, 785),
                    (1097, 837),
                    (1007, 859),
                    (904, 842),
                ]
            )
        ]
    )
    water = unary_union([west.buffer(11 * SCALE), east.buffer(10 * SCALE)]).intersection(box(*FRAME))
    woods = unary_union([west.buffer(68 * SCALE), east.buffer(65 * SCALE)]).intersection(box(*FRAME))
    develop = poly(
        [
            (355, 80),
            (455, 69),
            (583, 85),
            (700, 110),
            (847, 110),
            (900, 91),
            (1044, 90),
            (1106, 143),
            (1165, 236),
            (1190, 360),
            (1220, 462),
            (1216, 616),
            (1180, 745),
            (1110, 756),
            (924, 699),
            (846, 709),
            (741, 730),
            (611, 726),
            (522, 693),
            (445, 599),
            (356, 570),
            (354, 458),
            (402, 370),
            (437, 300),
            (399, 231),
            (350, 176),
        ]
    )
    return lines, water, woods, develop


def build():
    ROOT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_preset(
        "village",
        seed=SEED,
        houses=500,
        overrides={
            "town": {"terrain_relief_m": 0, "industrial_lots": 6},
            "housing": {
                "lot_frontage_m": {"pre_1945": 21.0, "postwar": 23.0, "modern": 25.0},
                "lot_depth_m": {"pre_1945": 37.0, "postwar": 40.0, "modern": 43.0},
            },
        },
    )
    lines, water, woods, develop = source_plan()
    roads = planarize([], lines, min_dangle=2)
    print("roads", roads.summary(), flush=True)
    if roads.dropped_edges or roads.graph.components()[0] != 1:
        raise ValueError("Disconnected authored roads")
    terrain = Terrain(cfg.seeds.for_("town"), relief_m=0, base_m=90)
    center = tuple(xy((734, 490)))
    era = build_era_field(
        cfg.seeds.for_("town"), center, 1050, FRAME, 500, 1940, 75, 10, cfg.gas.all_electric_district_share
    )
    geo = Geography(
        roads,
        era,
        terrain,
        center,
        FRAME,
        cfg.town.anchor_lat,
        cfg.town.anchor_lon,
        {
            "type": "synthetic",
            "label": "Two River Forest",
            "expansion": "none",
            "streetModel": "two-river-forest/1",
        },
    )
    road_land = unary_union(
        [
            LineString(g).buffer(ROW_WIDTH[roads.graph.edge_class[i]] / 2, cap_style=2)
            for i, g in enumerate(roads.graph.geometry)
        ]
    )

    def site(bounds):
        x0, y0, x1, y1 = bounds
        return poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    specs = [
        ("SCHOOL-01", "school", "Two River Forest School", (612, 314, 687, 421), "School Green"),
        ("CHURCH-01", "school", "Forest Parish Church", (807, 398, 861, 439), "Chapel Crescent"),
    ]
    # Six serviceable industrial sites, each with one building and one premise.
    for n, b in enumerate(
        [
            (1021, 571, 1061, 616),
            (1008, 621, 1048, 646),
            (1088, 608, 1121, 656),
            (968, 654, 1011, 706),
            (1047, 674, 1092, 730),
            (1101, 694, 1140, 752),
        ]
    ):
        specs.append(
            (
                f"INDUSTRY-{n + 1:02d}",
                "industrial",
                f"Forest Works {n + 1}",
                b,
                "Foundry Lane" if n in (0, 1, 3, 4) else "Works Lane",
            )
        )
    specs += [
        ("PUMP-01", "pump_station", "Forest water works", (1150, 691, 1178, 713), "Works Lane"),
        ("SUB-01", "substation", "Forest substation", (1150, 721, 1176, 747), "Mill Road"),
        ("TANK-01", "elevated_tank", "Forest water tower", (902, 671, 918, 691), "Mill Road"),
        ("GATE-01", "city_gate", "Forest gas gate", (1190, 670, 1204, 682), "River Road"),
    ]
    facilities = []
    for identity, kind, name, b, street in specs:
        p = max(parts(site(b).difference(road_land.buffer(1)).difference(woods)), key=lambda p: p.area)
        facilities.append(_facility(roads, identity, kind, name, p, street))
    pads = unary_union([f.poly.buffer(2) for f in facilities])
    industry = poly([(1020, 560), (1185, 633), (1180, 755), (1100, 767), (920, 721), (965, 642)])
    protected = woods
    lots, blocks = candidate_lots(geo, cfg, FRAME)
    # Curving roads can share a start node and street source ID; bind authored
    # lots to their geometry digest so those junction lots cannot alias.
    lots.uid = [uid("trf-lot", p.wkb_hex) for p in lots.poly]
    lots.poly = [set_precision(p, 0) for p in lots.poly]
    occupied = []
    chosen = []
    shops = []
    for i, p in enumerate(lots.poly):
        clear = p.difference(unary_union([protected, pads, industry, road_land])).intersection(develop)
        valid = [a for a in parts(clear, 200) if a.distance(Point(lots.row_xy[i])) < 0.55]
        if not valid:
            continue
        p = max(valid, key=lambda p: p.area)
        if p.area < 430:
            continue
        # The same fitting contract is used later for house and backyard pool.
        t, n = lots.tangent[i], lots.normal[i]
        row = lots.row_xy[i]
        house = _rect(row + n * 13, t, n, 10, 11)
        if not p.buffer(-0.6).covers(house):
            continue
        if occupied:
            p = p.difference(unary_union([q for q in occupied if p.intersects(q)]))
            if p.geom_type != "Polygon" or not p.buffer(-0.6).covers(house):
                continue
        lots.poly[i] = p
        occupied.append(p)
        rp = lots.front_xy[i] / np.array([SCALE, -SCALE])
        if roads.names[lots.edge[i]] == "Main Street" and 160 < rp[1] < 485:
            shops.append(i)
        else:
            chosen.append(i)
    print("capacity", len(chosen), "shops", len(shops), flush=True)
    if not 450 <= len(chosen) <= 550 or len(shops) < 16:
        raise ValueError("Capacity outside the approved 10% tolerance")
    # Spatial ordering makes removed capacity cohesive greens instead of random
    # vacant slots sprinkled between houses. Every retained house is in the map.
    chosen.sort(
        key=lambda i: (
            lots.poly[i].centroid.distance(Point(center))
            + (150 if roads.names[lots.edge[i]] in ("North County Road", "Forest Bypass") else 0)
        )
    )
    shops.sort(key=lambda i: lots.poly[i].centroid.distance(Point(center)))
    shops = shops[:16]
    lu = LandUse(
        roads,
        lots.subset(chosen),
        lots.subset(shops),
        facilities,
        [],
        FRAME,
        1250.0,
        _exits(roads, FRAME, center),
    )
    prem = build_premises(lu, cfg, terrain, era)
    by_uid = {uid("premise", lots.uid[i]): i for i in chosen + shops}
    pool_candidates = {}
    pool_shapes = {}
    for j, key in enumerate(prem.uid):
        if key in by_uid:
            i = by_uid[key]
            t, n = lots.tangent[i], lots.normal[i]
            row = lots.row_xy[i]
            # Stable variations constrained by each individual lot.
            variant = int(hashlib.sha256(key.encode()).hexdigest()[:6], 16)
            w, d = (
                (9.0 + (variant % 4) * 0.7, 10.0 + ((variant // 4) % 3) * 0.7)
                if prem.residential[j]
                else (12.0, 14.0)
            )
            c = row + n * (6.5 + d / 2)
            footprint = _rect(c, t, n, w, d)
            if not prem.lot[j].buffer(-0.4).covers(footprint):
                w, d = 9.0, 10.0
                c = row + n * 13
                footprint = _rect(c, t, n, w, d)
            if not prem.lot[j].buffer(-0.4).covers(footprint):
                raise ValueError(
                    f"House fit {prem.ids[j]} uid={key} lot={i} difference={prem.lot[j].symmetric_difference(lots.poly[i]).area}"
                )
            prem.xy[j] = c
            prem.width[j] = w
            prem.depth[j] = d
            prem.footprint[j] = footprint
            p = _rect(row + n * 29 + t * 2, t, n, 5.0, 8.0)
            if prem.residential[j] and prem.lot[j].buffer(-1.0).covers(p) and p.distance(footprint) > 3:
                pool_candidates[key] = p
        else:
            if prem.facility_id[j] == "CHURCH-01":
                prem.building_type[j] = "church"
                prem.width[j] = 24
                prem.depth[j] = 17
                prem.height[j] = 10
                prem.roof[j] = "gable"
                next(f for f in facilities if f.id == "CHURCH-01").kind = "church"
            # Fit industrial buildings to their smaller, road-bounded sites.
            if prem.building_type[j] == "industrial":
                prem.width[j] = 32.0
                prem.depth[j] = 26.0
            t = np.array([math.cos(prem.heading[j]), math.sin(prem.heading[j])])
            n = prem.normal[j]
            footprint = _rect(prem.xy[j], t, n, prem.width[j], prem.depth[j])
            for _ in range(16):
                if prem.lot[j].buffer(-1).covers(footprint):
                    break
                prem.width[j] *= 0.93
                prem.depth[j] *= 0.93
                footprint = _rect(prem.xy[j], t, n, prem.width[j], prem.depth[j])
            prem.footprint[j] = footprint
        if not prem.lot[j].buffer(0.001).covers(prem.footprint[j]):
            raise ValueError(f"Building outside parcel {prem.ids[j]}")
    print("pool capacity", len(pool_candidates), flush=True)
    if len(pool_candidates) < 100:
        raise ValueError("Not enough suitable private backyards")
    pool_keys = set(
        sorted(pool_candidates, key=lambda k: hashlib.sha256((SEED + k).encode()).hexdigest())[:100]
    )
    assign_households(prem, cfg, era)
    prem.attrs["solar"][:] = False
    prem.attrs["pv_kw"][:] = 0.0
    prem.attrs["pool"][:] = False
    for j, key in enumerate(prem.uid):
        if key in pool_keys:
            prem.attrs["pool"][j] = True
            pool_shapes[prem.ids[j]] = pool_candidates[key]
    assign_addresses(prem, roads, center)
    ctx = NetContext(cfg, lu, prem, terrain, era, cfg.seeds.for_("town"))
    networks = {"electric": build_electric(ctx), "water": build_water(ctx), "gas": build_gas(ctx)}
    town = Town(cfg, geo, lu, prem, networks)
    town.customers = build_customers(town)
    snapshot = build_snapshot(town, embed_state=False)
    for p in snapshot["parcels"]:
        idx = prem.ids.index(p["premiseId"])
        p["polygon"] = vect(prem.lot[idx])
    occupied = unary_union([*prem.lot, *[f.poly for f in facilities], road_land])
    open_areas = []
    for kind, g in [
        ("water", water),
        ("environmental", woods.difference(water)),
        ("parks", develop.difference(woods).difference(occupied)),
        ("agricultural", box(*FRAME).difference(develop.union(woods)).difference(road_land)),
    ]:
        for i, p in enumerate(parts(g.difference(occupied), 20)):
            open_areas.append(area_record(f"{kind}-{i:03}", kind, p))
    zones = [area_record(f"protected-{i}", "environmental", p) for i, p in enumerate(parts(woods))]
    block_records = []
    for i, p in enumerate(blocks):
        members = [
            home["id"] for home in snapshot["premises"] if p.buffer(0.01).covers(Point(home["x"], -home["z"]))
        ]
        if members:
            block_records.append(
                area_record(f"TRF-B{i:03}", "block", p, name=f"Block {i + 1}", premiseIds=members)
            )
    block_of = {pid: b["id"] for b in block_records for pid in b["premiseIds"]}
    for home in snapshot["premises"]:
        home["atlasBlockId"] = block_of[home["id"]]
        if home["id"] in pool_shapes:
            home["poolPolygon"] = vect(pool_shapes[home["id"]])
    snapshot["atlasDesign"] = {
        "version": "two-river-forest/1",
        "presetId": PRESET,
        "revision": 1,
        "name": "Two River Forest",
        "curated": True,
        "defaultArt": "native",
        "description": "Count-certified geometry interpreted from a generative zoning concept; separate experimental illustration.",
        "focus": {"x": center[0], "z": -center[1], "viewHeightM": 1700},
        "openAreas": open_areas,
        "landUseZones": zones,
        "blocks": block_records,
        "parks": [],
        "fields": [],
        "featureBudget": {
            "targetHomes": 500,
            "homeTolerance": 0.10,
            "homes": len(chosen),
            "pools": 100,
            "solar": 0,
            "school": 1,
            "church": 1,
            "commercial": 16,
            "industrial": 6,
        },
        "sourceReview": "First experiment. Human interpretation of concept; visual fidelity unapproved.",
    }
    # Export one authoritative geometry source for stage rendering and picking.
    from two_river_streets import furniture

    data = {
        "bounds": [0, 0, 1536, 1024],
        "metresPerUnit": SCALE,
        "budget": snapshot["atlasDesign"]["featureBudget"],
        "roads": snapshot["roads"],
        "furniture": furniture(snapshot),
        "properties": snapshot["premises"],
        "parcels": snapshot["parcels"],
        "buildings": snapshot["buildings"],
        "blocks": block_records,
        "land": open_areas,
        "facilities": snapshot["facilities"],
    }
    (ROOT / "geometry.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    from two_river_render import render_stages

    render_stages(data, ROOT, OUT)
    snapshot["atlasDesign"]["masterSvgSha256"] = hashlib.sha256(
        (ROOT / "master.svg").read_bytes()
    ).hexdigest()
    checks = geometry_checks(snapshot)
    checks += [
        {
            "id": "exact-features",
            "title": f"{len(chosen)} homes (450–550 permitted) / 100 fitted pools / no solar / 1 school / 1 church / 6 industry / 16 shops",
            "status": "pass"
            if 450 <= sum(p["premiseType"] == "residential" for p in snapshot["premises"]) <= 550
            and sum(p["hasPool"] for p in snapshot["premises"]) == 100
            and not any(p["solar"] or p["solarKW"] for p in snapshot["premises"])
            and len(pool_shapes) == 100
            and sum(p["buildingType"] == "school" for p in snapshot["premises"]) == 1
            and sum(p["buildingType"] == "church" for p in snapshot["premises"]) == 1
            and sum(p["premiseType"] == "commercial" for p in snapshot["premises"]) == 16
            and sum(p["premiseType"] == "industrial" for p in snapshot["premises"]) == 6
            else "fail",
        }
    ]
    (ROOT / "snapshot.json").write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")
    (ROOT / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    (OUT / "geometry-checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2), flush=True)
    if any(c["status"] != "pass" for c in checks):
        raise ValueError("Quality gate failed")
    print("BAKED", len(snapshot["premises"]), "premises", len(block_records), "blocks", flush=True)


if __name__ == "__main__":
    build()
