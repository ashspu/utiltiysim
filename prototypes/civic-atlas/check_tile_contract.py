"""Verify complete tile coverage and identical seam copies of selectable features."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def audit(folder):
    manifest = json.loads((folder / "tiles.json").read_text())
    index = json.loads((folder / "premise-index.json").read_text())
    raw = (folder / "geometry.json").read_bytes() if (folder / "geometry.json").exists() else gzip.decompress((folder / "geometry.json.gz").read_bytes())
    source = json.loads(raw)
    problems = []
    if hashlib.sha256(raw).hexdigest() != manifest["sourceSha256"]:
        problems.append("Tiles were baked from a different geometry revision")
    found, digests, duplicates, selected_tiles = {}, {}, 0, {}
    for key in manifest["tiles"]:
        chunk = json.loads((folder / "tiles" / (key + ".json")).read_text())
        for feature in chunk["features"]:
            if feature["type"] not in ("property", "road"):
                continue
            fid = feature["type"] + ":" + feature["id"]
            digest = hashlib.sha256(json.dumps(feature, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if fid in digests:
                duplicates += 1
                if digests[fid] != digest:
                    problems.append(f"Adjacent tiles disagree about {fid}")
            digests[fid] = digest
            found[fid] = feature
            selected_tiles.setdefault(fid, set()).add(key)
    properties = {f["id"]: f for f in found.values() if f["type"] == "property"}
    roads = {f["id"]: f for f in found.values() if f["type"] == "road"}
    expected = {p["id"] for p in source["properties"]}
    if set(properties) != expected or set(index) != expected:
        problems.append("Map coverage/index differs from the complete saved premise set")
    if set(roads) != {r["id"] for r in source["roads"]}:
        problems.append("Map omits or invents saved road segments")
    for road in source["roads"]:
        actual = roads.get(road["id"], {})
        expected_points = [[point["x"], point["z"]] for point in road["points"]]
        if actual.get("points") != expected_points:
            problems.append(f"Rendered road centreline differs from metadata for {road['id']}")
        if any(actual.get(key) != value for key, value in road.items() if key != "points"):
            problems.append(f"Road attributes differ from metadata for {road['id']}")
    for identity, entry in index.items():
        owner = f"{entry[2]}-{entry[3]}"
        if owner not in selected_tiles.get("property:" + identity, set()):
            problems.append(f"Premise lookup targets a tile without {identity}")
    for p in source["properties"]:
        if properties.get(p["id"], {}).get("record") != p:
            problems.append(f"Tile record differs from metadata for {p['id']}")
    return {"preset": folder.name, "passed": not problems, "tiles": len(manifest["tiles"]),
            "properties": len(properties), "roads": len(roads), "identicalSeamCopies": duplicates,
            "problems": problems[:30], "problemCount": len(problems),
            "scope": "All selectable feature IDs, metadata, tile lookup and seam copies. Visual screenshots remain a separate gate."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folders", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [audit(folder) for folder in args.folders]
    report = {"passed": all(r["passed"] for r in results), "towns": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
