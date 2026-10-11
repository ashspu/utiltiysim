"""Fail-closed readiness evidence checker; never grants human approval."""
import argparse
import hashlib
import json
from pathlib import Path

STAGES = (
    "zoning", "regional_art_seams", "roads_access", "visible_lot_parcels",
    "premise_service_ids", "block_illustration", "zoom_click_snapshot_qa",
)
SCHEMA = "utilitysim-preset-release/1"


def validate(manifest, base, *, playable=False):
    """Return blockers. Evidence paths resolve relative to the manifest directory."""
    errors = []
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        return ["Unsupported schema; legacy catalog/readiness is development evidence only"]
    for key in ("townId", "revision", "owner", "previewLabel"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            errors.append(f"Missing {key}")
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or not assets:
        return errors + ["Missing hashed assets"]
    verified = {}
    for name, asset in assets.items():
        try:
            path = Path(base) / asset["path"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != asset["sha256"]:
                raise ValueError("hash mismatch")
            verified[name] = digest
        except (KeyError, TypeError, OSError, ValueError) as exc:
            errors.append(f"Asset {name}: {exc}")
    if not playable:
        return errors
    if manifest.get("releaseClass") != "playable-template":
        errors.append("Development preview is not a playable template")
    counts = manifest.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    required = ("population", "homes", "residentialPremises", "otherPremises", "meters")
    for key in required:
        value = counts.get(key)
        if type(value) is not int or value < 0:
            errors.append(f"Unverified actual count: {key}")
    target = manifest.get("target", {})
    if not isinstance(target, dict):
        target = {}
    metric = target.get("metric")
    value, tolerance = target.get("value"), target.get("tolerance")
    if (metric not in ("population", "homes") or type(value) is not int or value <= 0
            or type(tolerance) not in (int, float) or not 0 <= tolerance <= 0.1):
        errors.append("Invalid explicit population/home target and tolerance")
    elif type(counts.get(metric)) is int and abs(counts[metric] - value) > value * tolerance:
        errors.append("Actual count outside target tolerance")
    review_path = manifest.get("reviewRecord")
    try:
        review = json.loads((Path(base) / review_path).read_text(encoding="utf-8"))
        if not isinstance(review, dict) or not isinstance(review.get("acceptedStages"), list):
            raise ValueError("Invalid review record")
        if (review.get("kind") not in ("human", "independent-review")
                or review.get("reviewer") in (None, "", manifest.get("owner"))
                or review.get("decision") != "accepted"
                or review.get("townId") != manifest.get("townId")
                or review.get("revision") != manifest.get("revision")
                or not review.get("evidence") or not review.get("acceptedAt")
                or review.get("assetHashes") != verified):
            errors.append("Acceptance must be external, scoped to revision and exact asset hashes")
    except (TypeError, OSError, ValueError):
        review = {}
        errors.append("Missing readable external acceptance record")
    stages = manifest.get("stages", {})
    if not isinstance(stages, dict):
        stages = {}
    for stage in STAGES:
        entry = stages.get(stage, {})
        if not isinstance(entry, dict):
            entry = {}
        evidence_assets = entry.get("evidenceAssets")
        if (entry.get("status") != "complete" or not entry.get("evidenceAssets")
                or not isinstance(evidence_assets, list)
                or any(not isinstance(name, str) or name not in verified for name in evidence_assets)
                or stage not in review.get("acceptedStages", [])):
            errors.append(f"Stage incomplete or outside accepted review scope: {stage}")
    unresolved = manifest.get("unresolvedAreas")
    if not isinstance(unresolved, list):
        errors.append("Declare unresolvedAreas, including an explicit empty list")
    else:
        for item in unresolved:
            if not isinstance(item, dict) or not all(item.get(k) for k in ("areaId", "reason", "severity", "owner")):
                errors.append("Unresolved area lacks identity, severity, reason or owner")
            elif item["severity"] not in ("cosmetic", "blocking"):
                errors.append("Unknown unresolved severity")
            elif item["severity"] == "blocking":
                errors.append(f"Blocking unresolved area: {item['areaId']}")
    scale = max((v for k, v in counts.items() if k in ("population", "homes") and type(v) is int), default=0)
    if scale >= 25000 and "scale_qa" not in review.get("acceptedStages", []):
        errors.append("25k/50k requires separately accepted scale QA")
    return errors


def fleet_gate(ashtown, base, learning_record):
    errors = validate(ashtown, base, playable=True)
    if not isinstance(ashtown, dict) or ashtown.get("townId") != "ashtown":
        errors.append("Repeatability gate must be Ashtown")
    if not isinstance(ashtown, dict):
        return errors
    try:
        learning = json.loads(Path(learning_record).read_text(encoding="utf-8"))
        if not isinstance(learning, dict):
            raise ValueError("Invalid learning record")
        if (learning.get("decision") != "accepted" or not learning.get("acceptedBy")
                or learning.get("acceptedBy") == ashtown.get("owner")
                or learning.get("ashtownRevision") != ashtown.get("revision")
                or learning.get("ashtownReviewRecord") != ashtown.get("reviewRecord")
                or not learning.get("lessons") or not learning.get("nextPresetChecklist")):
            errors.append("Ashtown lessons require coordinator acceptance tied to reviewed revision")
    except (TypeError, OSError, ValueError):
        errors.append("Missing accepted Ashtown learning handoff")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--mode", choices=("preview", "playable", "fleet"), default="playable")
    parser.add_argument("--learning-record", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        errors = (fleet_gate(data, args.manifest.parent, args.learning_record) if args.mode == "fleet"
                  else validate(data, args.manifest.parent, playable=args.mode == "playable"))
    except (OSError, ValueError, TypeError) as exc:
        errors = [str(exc)]
    print(json.dumps({"status": "BLOCKED" if errors else "EVIDENCE_COMPLETE",
                      "mode": args.mode, "blockers": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
