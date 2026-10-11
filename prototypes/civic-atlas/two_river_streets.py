"""Curb-trimmed accesses and spaced illustrations of actual street equipment."""

import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree


def surface(roads):
    return unary_union(
        [
            LineString([(p["x"], p["z"]) for p in r["points"]]).buffer(r["pavementWidthM"] / 2, cap_style=2)
            for r in roads
        ]
    )


def driveway_shapes(data):
    surfaces = [
        LineString([(p["x"], p["z"]) for p in r["points"]]).buffer(r["pavementWidthM"] / 2, cap_style=2)
        for r in data["roads"]
    ]
    tree = STRtree(surfaces)
    result = {}
    for p in data["properties"]:
        drive = LineString([(p["front"]["x"], p["front"]["z"]), (p["x"], p["z"])]).buffer(1.7, cap_style=2)
        nearby = unary_union([surfaces[int(i)] for i in tree.query(drive)])
        result[p["id"]] = drive.difference(nearby)
    return result


def furniture(snapshot):
    roads = snapshot["roads"]
    lines = [LineString([(p["x"], p["z"]) for p in r["points"]]) for r in roads]
    pavement = [line.buffer(r["pavementWidthM"] / 2, cap_style=2) for line, r in zip(lines, roads)]
    parcel_polys = [Polygon([(q["x"], q["z"]) for q in p["polygon"]]) for p in snapshot["parcels"]]
    driveways = driveway_shapes({"roads": roads, "properties": snapshot["premises"]}).values()
    # A point is covered by a union exactly when a member covers it. Spatial
    # lookup avoids constructing/buffering a town-wide polygon for every bake.
    obstacles = [p.buffer(0.7) for p in pavement] + [p.buffer(0.6) for p in parcel_polys]
    obstacles.extend(p.buffer(1.4) for p in driveways if not p.is_empty)
    obstacle_tree = STRtree(obstacles)

    def blocked(point):
        return any(obstacles[int(i)].covers(point) for i in obstacle_tree.query(point))

    line_tree = STRtree(lines)
    grouped = {}
    hydrants = []
    for utility in ("electric", "water"):
        for a in snapshot["networks"][utility]["equipment"]:
            if a["kind"] not in ("pole", "hydrant"):
                continue
            pt = Point(a["x"], a["z"])
            i = int(line_tree.nearest(pt))
            r = roads[i]
            if a["kind"] == "hydrant":
                # Hydraulic equipment coordinates sit on the water main. Draw
                # the above-ground hydrant in the verge, retaining the actual
                # equipment ID and explicit original network coordinates.
                s = lines[i].project(pt)
                c = lines[i].interpolate(s)
                v = np.array(lines[i].interpolate(min(lines[i].length, s + 1)).coords[0]) - np.array(
                    lines[i].interpolate(max(0, s - 1)).coords[0]
                )
                v /= max(np.linalg.norm(v), 1e-9)
                n = np.array([-v[1], v[0]])
                side = 1 if np.dot(np.array(pt.coords[0]) - np.array(c.coords[0]), n) >= 0 else -1
                for shift in (0, 4, -4, 8, -8):
                    base = np.array(lines[i].interpolate(min(lines[i].length, max(0, s + shift))).coords[0])
                    q = Point(base + n * side * (r["pavementWidthM"] / 2 + 1.5))
                    if not blocked(q):
                        hydrants.append(
                            {
                                **a,
                                "networkPosition": {"x": a["x"], "z": a["z"]},
                                "x": q.x,
                                "z": q.y,
                                "roadId": r["id"],
                                "source": "saved hydrant, illustrated curb position",
                            }
                        )
                        break
                continue
            # Do not draw equipment inside private yards, pavement, or access.
            if blocked(pt):
                continue
            if lines[i].distance(pt) > r["rowWidthM"] / 2 + 2:
                continue
            rec = {
                **a,
                "roadId": r["id"],
                "chainageM": lines[i].project(pt),
                "source": "saved network equipment",
            }
            grouped.setdefault(i, []).append(rec)
    chosen = []
    spacing_cells = {}
    # Equal chainage targets, one curb side per source road segment. All chosen
    # symbols retain real equipment IDs and coordinates. A global clearance
    # rejects close corner pairs even when they belong to different streets.
    for i in sorted(grouped, key=lambda i: (roads[i]["name"], roads[i]["id"])):
        L = lines[i].length
        candidates = grouped[i]
        intervals = max(1, round(L / 42.0))
        targets = np.linspace(21, max(21, L - 21), max(1, intervals))
        for target in targets:
            for a in sorted(candidates, key=lambda a: abs(a["chainageM"] - target)):
                if abs(a["chainageM"] - target) > 15:
                    break
                if min(a["chainageM"], L - a["chainageM"]) < 13:
                    continue
                cell = (math.floor(a["x"] / 35), math.floor(a["z"] / 35))
                neighbours = (
                    b
                    for dx in (-1, 0, 1)
                    for dz in (-1, 0, 1)
                    for b in spacing_cells.get((cell[0] + dx, cell[1] + dz), ())
                )
                if any(math.hypot(a["x"] - b["x"], a["z"] - b["z"]) < 35 for b in neighbours):
                    continue
                chosen.append(a)
                spacing_cells.setdefault(cell, []).append(a)
                break
    return chosen + hydrants
