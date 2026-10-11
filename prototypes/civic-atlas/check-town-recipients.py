"""Full-source bounded town proof against the separately installed recipients.

Run only against a dedicated QA directory; all normal simulation and recipient
methods remain in use. No missing reading is fabricated or approved.
"""

import argparse
import importlib.util
import json
import time
from pathlib import Path

from source_binding import read_snapshot, require_binding, source_fingerprint
from virtual_systems import VirtualSystems

from utilsim.world.store import World


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preset", required=True)
    p.add_argument("--store", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--days", type=int, default=2)
    args = p.parse_args()
    from datetime import date, timedelta

    started = time.monotonic()
    base = Path(__file__).parent / "web/presets" / args.preset
    snap = read_snapshot(base)
    world = World(args.store / "world.sqlite")
    end = (date(2026, 1, 1) + timedelta(days=args.days)).isoformat()
    if not world.status().get("environmentId"):
        world.initialize(snap, snap["atlasDesign"]["name"], start="2026-01-01")
        require_binding(world, source_fingerprint(base, snap))
        world.advance(end)
    else:
        require_binding(world, source_fingerprint(base, snap))
        with world.read_db() as db:
            saved_through = world.metadata(db)["through"]
        if saved_through < end:
            world.advance(end)
    print(
        json.dumps({"step": "world", "preset": args.preset, "seconds": round(time.monotonic() - started, 2)}),
        flush=True,
    )
    adapter = VirtualSystems(world, snap)
    init = adapter.initialize()
    print(
        json.dumps(
            {"step": "provisioned", "preset": args.preset, "seconds": round(time.monotonic() - started, 2)}
        ),
        flush=True,
    )
    assert init["counts"]["accounts"] == len(snap["accounts"])
    initial = adapter.ingest()
    assert adapter.ingest()["imported"] == 0
    print(
        json.dumps(
            {
                "step": "received",
                "preset": args.preset,
                "seconds": round(time.monotonic() - started, 2),
                "imported": initial["imported"],
            }
        ),
        flush=True,
    )
    start = "2026-01-01"
    adapter.run(start, end)
    print(
        json.dumps(
            {"step": "billed", "preset": args.preset, "seconds": round(time.monotonic() - started, 2)}
        ),
        flush=True,
    )
    # Held observed consumption requires a clerk. This fixture leaves all such
    # holds open and verifies the guarded eligible-account invoice action.
    result = adapter.invoice_eligible(start, end)
    print(
        json.dumps(
            {"step": "invoiced", "preset": args.preset, "seconds": round(time.monotonic() - started, 2)}
        ),
        flush=True,
    )
    assert result["counts"]["invoices"] > 0
    assert result["trialBalance"]["totals"]["CAD"]["balanced"]
    repeat = adapter.invoice_eligible(start, end)
    assert repeat["accountsProcessed"] == 0 and repeat["ledgerDeliveries"] == 0
    assert repeat["counts"]["invoices"] == result["counts"]["invoices"]
    spec = importlib.util.spec_from_file_location(
        "partition", Path(__file__).with_name("check-virtual-partition.py")
    )
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    partition = audit.audit(args.store, start, end)
    assert partition["summary"]["unexplainedContracts"] == 0
    active = sum(partition["summary"]["accountDispositions"].values())
    assert active == len(snap["accounts"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_name(args.output.stem + "-partition.json").write_text(
        json.dumps(partition, indent=2), encoding="utf-8"
    )
    nextday = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    world.advance(nextday)
    new = adapter.ingest()
    assert new["imported"] > 0 and new["receivedThrough"] == nextday
    assert adapter.ingest()["imported"] == 0
    saved = adapter.inspect()
    assert saved["counts"]["invoices"] == result["counts"]["invoices"]
    report = {
        "passed": True,
        "preset": args.preset,
        "homes": snap["atlasDesign"]["featureBudget"]["homes"],
        "premises": len(snap["premises"]),
        "accounts": len(snap["accounts"]),
        "period": {"start": start, "end": end},
        "initialObservations": initial,
        "counts": result["counts"],
        "partition": partition["summary"],
        "trialBalance": result["trialBalance"],
        "nextDayReadings": new,
        "retryCreatesNoInvoicesOrLedgerEntries": True,
        "sourceFingerprint": adapter.source_hash,
        "automaticHoldApprovals": 0,
        "schedulerManaged": False,
        "elapsedSeconds": round(time.monotonic() - started, 2),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
