"""Stage SVGs from the same saved geometry used by the simulator and picker."""

import hashlib
import random

from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree
from two_river_streets import driveway_shapes

S = 1.7
COLORS = {"water": "#80b8c2", "environmental": "#386a50", "parks": "#abc88c", "agricultural": "#d7c391"}


def coords(points):
    return [(p["x"] / S, p["z"] / S) for p in points]


def path(points):
    return "M" + "L".join(f"{x:.4f},{y:.4f}" for x, y in coords(points)) + "Z"


def area(a):
    return path(a["polygon"]) + "".join(path(h) for h in a.get("holes", []))


def line(points):
    return "M" + "L".join(f"{x:.4f},{y:.4f}" for x, y in coords(points))


def tag(d, fill, extra=""):
    return f'<path d="{d}" fill="{fill}" {extra}/>'


def raw_polygon(p):
    rings = [p.exterior, *p.interiors]
    return "".join("M" + "L".join(f"{x / S:.4f},{y / S:.4f}" for x, y in r.coords) + "Z" for r in rings)


def equipment_svg(data):
    out = []
    for a in data.get("furniture", []):
        x, y = a["x"] / S, a["z"] / S
        if a["kind"] == "pole":
            out.append(
                f'<g data-equipment="{a["id"]}"><path d="M{x},{y}l4.3,5.6" stroke="#293e3540" stroke-width=".8"/><path d="M{x},{y}v-3.2" stroke="#72563b" stroke-width=".8"/><path d="M{x - 1.1},{y - 2.8}h2.2" stroke="#664d37" stroke-width=".5"/><circle cx="{x}" cy="{y}" r=".5" fill="#554633"/></g>'
            )
        else:
            out.append(
                f'<g data-equipment="{a["id"]}"><ellipse cx="{x + 0.55}" cy="{y + 0.5}" rx=".7" ry=".45" fill="#233e3540"/><path d="M{x},{y}v-1.3M{x - 0.65},{y - 0.65}h1.3" stroke="#bc3f2c" stroke-width=".65"/><circle cx="{x}" cy="{y - 1.35}" r=".4" fill="#dfb75c"/></g>'
            )
    return "".join(out)


def render(data, stage, view="0 0 1536 1024"):
    detailed = stage >= 4
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="3072" height="2048" data-metres-per-pixel="1.7">',
        '<defs><pattern id="field" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(15)"><rect width="5" height="5" fill="#d5c497"/><path d="M0 0V5" stroke="#bdab79" stroke-width=".5"/></pattern>',
        '<filter id="shadow" x="-30%" y="-30%" width="170%" height="170%"><feDropShadow dx="1.3" dy="1.8" stdDeviation=".65" flood-color="#1c3024" flood-opacity=".3"/></filter></defs>',
        '<rect width="1536" height="1024" fill="#adc48d"/>',
    ]
    for a in data["land"]:
        color = (
            "url(#field)" if detailed and a["kind"] == "agricultural" else COLORS.get(a["kind"], "#a8c589")
        )
        out.append(tag(area(a), color, 'fill-rule="evenodd"'))
    # Stable landscape texture, only inside the saved conservation polygons.
    if detailed:
        forests = [
            Polygon(coords(a["polygon"]), [coords(h) for h in a.get("holes", [])])
            for a in data["land"]
            if a["kind"] == "environmental"
        ]
        tree = STRtree(forests)
        rng = random.Random(8726)
        for _ in range(15500):
            x, y = rng.uniform(0, 1536), rng.uniform(0, 1024)
            if len(tree.query(Point(x, y), predicate="within")):
                r = rng.uniform(2.2, 5.6)
                color = rng.choice(["#44704f", "#5a8056", "#345f48", "#73905c", "#466948"])
                out.append(
                    f'<circle cx="{x + 1:.2f}" cy="{y + 1.5:.2f}" r="{r:.2f}" fill="#274938" opacity=".5"/><circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{color}"/><circle cx="{x - 0.6:.2f}" cy="{y - 1:.2f}" r="{r * 0.5:.2f}" fill="#b0bb79" opacity=".18"/>'
                )
    by_id = {p["id"]: p for p in data["properties"]}
    block_colors = ["#e4dfac", "#e0dfae", "#d3dbb1", "#cfd9a9", "#dfd8a7", "#cedaaf", "#d4deba"]
    for parcel in data["parcels"]:
        p = by_id[parcel["premiseId"]]
        kind = p["premiseType"]
        key = int(hashlib.sha256(p["uid"].encode()).hexdigest()[:8], 16)
        fill = (
            ("#eee5a5" if stage == 2 else block_colors[key % len(block_colors)])
            if kind == "residential"
            else "#df9f86"
            if kind == "commercial"
            else "#c49eaf"
            if kind == "institutional"
            else "#9caec2"
        )
        out.append(
            tag(
                path(parcel["polygon"]),
                fill,
                f'data-premise="{p["id"]}" stroke="#727e59" stroke-width="{0.35 if stage >= 3 else 0.12}"',
            )
        )
    # Pavement and future hit areas share these exact centreline paths and widths.
    for road in data["roads"]:
        out.append(
            tag(
                line(road["points"]),
                "none",
                f'stroke="#e2dec7" stroke-width="{road["rowWidthM"] / S:.3f}" stroke-linecap="round" stroke-linejoin="round"',
            )
        )
    for road in data["roads"]:
        out.append(
            tag(
                line(road["points"]),
                "none",
                f'data-road="{road["id"]}" stroke="#8b9390" stroke-width="{road["pavementWidthM"] / S:.3f}" stroke-linecap="round" stroke-linejoin="round"',
            )
        )
        if detailed and road["roadClass"] != "local":
            out.append(
                tag(line(road["points"]), "none", 'stroke="#e6deaf" stroke-width=".4" stroke-dasharray="3 5"')
            )
    if stage >= 3:
        drives = driveway_shapes(data) if detailed else {}
        building_by_id = {b["id"]: b for b in data["buildings"]}
        for p in data["properties"]:
            b = building_by_id[p["buildingId"]]
            foot = b["footprint"]["polygon"]
            q = coords(foot)
            key = int(hashlib.sha256(p["uid"].encode()).hexdigest()[:8], 16)
            tone = ["#766553", "#897866", "#68695d", "#9c7960", "#677373", "#82705b"][key % 6]
            if detailed:
                # Driveway follows the same frontage anchor as the utility model.
                drive = drives[p["id"]]
                for part in getattr(drive, "geoms", [drive]):
                    if part.geom_type == "Polygon":
                        out.append(
                            tag(
                                raw_polygon(part),
                                "#c5c2ad",
                                'fill-rule="evenodd" data-driveway="' + p["id"] + '"',
                            )
                        )
                out.append(
                    tag(
                        path(foot),
                        "#ebe0c8",
                        'transform="translate(0,1.1)" stroke="#6e6b57" stroke-width=".25"',
                    )
                )
            out.append(
                tag(
                    path(foot),
                    tone,
                    f'data-building="{p["id"]}" stroke="#4d5549" stroke-width=".35"'
                    + (' filter="url(#shadow)"' if detailed else ""),
                )
            )
            if detailed and len(q) == 4:
                a = [(q[0][i] + q[1][i]) / 2 for i in (0, 1)]
                c = [(q[2][i] + q[3][i]) / 2 for i in (0, 1)]
                roof = "M" + "L".join(f"{x},{y}" for x, y in [q[0], a, c, q[3]]) + "Z"
                out.append(tag(roof, "#eee2be", 'opacity=".18"'))
                out.append(f'<path d="M{a[0]},{a[1]}L{c[0]},{c[1]}" stroke="#453f36" stroke-width=".3"/>')
            if p.get("poolPolygon"):
                out.append(
                    tag(
                        path(p["poolPolygon"]),
                        "#53b6cb",
                        f'data-pool="{p["id"]}" stroke="#f4ecd3" stroke-width="1.3"',
                    )
                )
                out.append(tag(path(p["poolPolygon"]), "none", 'stroke="#348b9f" stroke-width=".25"'))
    if detailed:
        out.append(equipment_svg(data))
    if stage == 4:
        for p in data["properties"]:
            out.append(
                f'<text x="{p["x"] / S}" y="{p["z"] / S}" font-family="Arial" font-size="2.8" fill="white" text-anchor="middle">{p["id"].removeprefix("P-")}</text>'
            )
    out.append("</svg>")
    return "".join(out)


def render_stages(data, root, out):
    for stage, name in [
        (2, "02-measured-zoning"),
        (3, "03-parcels-buildings"),
        (4, "04-system-bindings"),
        (5, "05-controlled-map"),
    ]:
        svg = render(data, stage)
        (root / (name + ".svg")).write_text(svg, encoding="utf-8")
        (out / (name + ".svg")).write_text(svg, encoding="utf-8")
    (root / "master.svg").write_text(render(data, 3), encoding="utf-8")
    (root / "pilot-source.svg").write_text(render(data, 5, "420 90 240 160"), encoding="utf-8")
    (root / "street-furniture.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1536 1024">' + equipment_svg(data) + "</svg>",
        encoding="utf-8",
    )
