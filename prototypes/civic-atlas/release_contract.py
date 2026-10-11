"""Audit the complete geometry-to-utility identity contract before packaging a town.

This intentionally checks every premise, not a sample of rendered roofs. Visual
review, browser picking and durable billing have separate acceptance gates.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


def audit(folder: Path) -> dict:
    problems = []
    def read(name):
        source = folder / name
        return json.loads(source.read_bytes() if source.exists() else gzip.decompress((folder / (name + ".gz")).read_bytes()))
    snapshot = read("snapshot.json")
    geometry = read("geometry.json")
    budget = geometry["budget"]

    def index(rows, name):
        ids = [row["id"] for row in rows]
        duplicates = [key for key, count in Counter(ids).items() if count != 1]
        if duplicates:
            problems.append(f"{name}: duplicate IDs {duplicates[:5]}")
        return {row["id"]: row for row in rows}

    entities = {name: index(snapshot[name], name) for name in
                ("premises", "buildings", "parcels", "roads", "accounts", "servicePoints", "meters")}
    blocks = index(geometry["blocks"], "blocks")
    mapped = index(geometry["properties"], "mapped properties")
    if mapped != entities["premises"]:
        problems.append("Mapped property records differ from saved engine premises.")
    for name in ("roads", "parcels", "buildings"):
        if index(geometry[name], "mapped " + name) != entities[name]:
            problems.append(f"Mapped {name} differ from engine {name}.")
    counts = Counter(p.get("premiseType", "residential") for p in mapped.values())
    target = budget["targetHomes"]
    tolerance = budget["homeTolerance"]
    homes = counts["residential"]
    if not 0 <= tolerance <= .1 or not target * (1 - tolerance) <= homes <= target * (1 + tolerance):
        problems.append(f"Residential count {homes} is outside target {target} +/-10%.")
    if snapshot["homes"] != homes or budget["homes"] != homes:
        problems.append("Home totals disagree with counted residential premises.")
    for field, key in (("hasPool", "pools"), ("solar", "solar")):
        actual = sum(bool(p.get(field)) for p in mapped.values())
        if actual != budget[key]:
            problems.append(f"{key}: metadata count {actual} differs from budget {budget[key]}.")
    for kind in ("school", "church", "commercial", "industrial"):
        count = sum(p.get("buildingType") == kind for p in mapped.values()) if kind in ("school", "church") else counts[kind]
        if kind in budget and count != budget[kind]:
            problems.append(f"{kind}: count {count} differs from budget {budget[kind]}.")
    invalid = []
    for p in mapped.values():
        reason = []
        for field, table in (("buildingId", "buildings"), ("parcelId", "parcels"),
                             ("roadId", "roads"), ("accountId", "accounts")):
            if p.get(field) not in entities[table]:
                reason.append(field)
        if p.get("atlasBlockId") not in blocks:
            reason.append("atlasBlockId")
        if not reason:
            if entities["parcels"][p["parcelId"]]["premiseId"] != p["id"]:
                reason.append("parcel owner")
            if p["id"] not in entities["buildings"][p["buildingId"]]["premiseIds"]:
                reason.append("building owner")
            if entities["accounts"][p["accountId"]]["premiseId"] != p["id"]:
                reason.append("account owner")
        for commodity, sid in p.get("services", {}).items():
            sp = entities["servicePoints"].get(sid, {})
            meter = entities["meters"].get(sp.get("meterId"), {})
            if sp.get("premiseId") != p["id"] or sp.get("commodity") != commodity or meter.get("servicePointId") != sid:
                reason.append(f"{commodity} service/meter")
        if not p.get("services"):
            reason.append("no utility services")
        if reason:
            invalid.append({"premiseId": p["id"], "invalid": reason})
    if invalid:
        problems.append(f"{len(invalid)} premises have broken identity links.")
    expected = snapshot["atlasDesign"].get("masterSvgSha256")
    actual = hashlib.sha256((folder / "master.svg").read_text(encoding="utf-8").encode()).hexdigest()
    if actual != expected:
        problems.append("Master SVG digest differs from the baked world contract.")
    return {"preset": folder.name, "passed": not problems, "targetHomes": target,
            "actualHomes": homes, "premises": len(mapped), "roads": len(entities["roads"]),
            "blocks": len(blocks), "meters": len(entities["meters"]), "budget": budget,
            "problems": problems, "invalidLinks": invalid[:30],
            "scope": "All saved identity links and counts. Excludes visual QA, runtime and browser acceptance."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("presets", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for folder in args.presets:
        try:
            result = audit(folder)
        except (KeyError, ValueError, OSError) as exc:
            result = {"preset": folder.name, "passed": False, "problems": [str(exc)]}
        results.append(result)
        print(json.dumps({k: result[k] for k in ("preset", "passed", "problems")}), flush=True)
    report = {"passed": all(r["passed"] for r in results), "towns": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
