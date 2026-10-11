"""Bake a configuration into a reviewable town package; never imply visual/live approval."""

from __future__ import annotations

import argparse
import functools
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PRESETS = HERE / "web/presets"


def browser_preflight(node):
    """Check optional browser dependencies before generating expensive source geometry."""
    setup = (
        "Run npm install --prefix out/civic-atlas/browser --no-save playwright-core@1.64.0 "
        "from the repository root and install Edge/Chrome/Chromium (or set CHROMIUM_PATH). "
        "Use --skip-overview to leave browser rendering explicitly pending."
    )
    try:
        completed = subprocess.run(
            [node, "--input-type=module", "-e",
             f"await import({json.dumps((HERE / 'browser-runtime.mjs').as_uri())});"],
            cwd=REPO, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"Browser overview preflight failed: {error}. {setup}") from error
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"Browser overview preflight failed. {setup}\n{detail}")


def checked_resume(preset):
    if not re.fullmatch(r"[a-z][a-z0-9-]{3,63}", preset):
        raise ValueError("Resume requires a preset slug, not a file path")
    folder = PRESETS / preset
    manifest = json.loads((folder / "build-manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("geometryPassed") or manifest.get("config", {}).get("id") != preset:
        raise ValueError("Resume requires a successful matching factory build manifest")
    return preset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", type=Path, help="New town configuration; existing IDs are protected")
    source.add_argument("--resume", help="Package an existing validated factory bake without regenerating it")
    parser.add_argument("--node", default="node", help="Node.js executable for the browser overview baker")
    parser.add_argument(
        "--skip-overview", action="store_true", help="Leave overview images explicitly pending"
    )
    args = parser.parse_args()
    if not args.skip_overview and not shutil.which(args.node):
        parser.error("Node.js is required for overview baking; supply --node or explicitly --skip-overview")
    if not args.skip_overview:
        try:
            browser_preflight(args.node)
        except ValueError as error:
            parser.error(str(error))
    if args.config:
        from town_factory import validate_custom_config

        config_path = args.config.resolve()
        config = validate_custom_config(json.loads(config_path.read_text(encoding="utf-8")))
        preset = config["id"]
    else:
        preset = checked_resume(args.resume)
    folder = PRESETS / preset
    report_path = REPO / "out/factory-runs" / f"{preset}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": "town-authoring-pipeline/1",
        "presetId": preset,
        "startedAt": datetime.now(UTC).isoformat(),
        "stages": [],
        "visualAcceptance": "pending",
        "virtualSystemAcceptance": "pending",
        "releaseApproved": False,
    }

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def run(stage, script, *arguments, runtime=sys.executable, environment=None):
        entry = {"stage": stage, "status": "running"}
        report["stages"].append(entry)
        save()
        print(f"\n[{stage}]", flush=True)
        completed = subprocess.run(
            [runtime, str(HERE / script), *map(str, arguments)], cwd=REPO, env=environment
        )
        entry["status"] = "passed" if completed.returncode == 0 else "failed"
        entry["exitCode"] = completed.returncode
        save()
        if completed.returncode:
            raise SystemExit(completed.returncode)

    if args.config:
        run("source-geometry", "town_factory.py", "--config", config_path)
    else:
        report["stages"].append({"stage": "source-geometry", "status": "resumed-validated-bake"})
    run("identity-contract", "release_contract.py", folder, "--output", folder / "identity-checks.json")
    run("spatial-tiles", "tile_pack.py", preset)
    if not args.skip_overview:

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, _format, *arguments):
                pass

        handler = functools.partial(QuietHandler, directory=str(HERE / "web"))
        with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                environment = os.environ.copy()
                environment["ATLAS_URL"] = f"http://127.0.0.1:{server.server_port}"
                run(
                    "overview-images", "bake-overview.mjs", preset, runtime=args.node, environment=environment
                )
            finally:
                server.shutdown()
                worker.join()
        report["overviewImages"] = "baked; visual acceptance pending"
    else:
        report["overviewImages"] = "pending; explicitly skipped"
    # Fresh checkouts contain compressed authoritative sources. Materialize
    # their exact bytes locally when resuming packaging, without regeneration.
    for filename in ("snapshot.json", "geometry.json"):
        raw = folder / filename
        if not raw.exists():
            with gzip.open(folder / (filename + ".gz"), "rb") as source, raw.open("wb") as target:
                shutil.copyfileobj(source, target)
    run("compressed-sources", "package-presets.py", folder)
    report["completedAt"] = datetime.now(UTC).isoformat()
    report["reviewInstructions"] = [
        "Overview rendering does not grant visual acceptance; inspect both rendered images.",
        "Inspect whole-town density, neighbourhood variety, tile boundaries and close property detail.",
        "Run browser picking and the virtual-system read, bill, exception and repair workflow.",
        "Promote the new town into the curated catalogue only after recording those review results.",
    ]
    save()
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
