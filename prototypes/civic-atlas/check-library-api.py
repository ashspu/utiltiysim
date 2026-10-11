"""Independent HTTP acceptance against an explicitly disposable library store.

Run the server with --store out/release-qa/worlds before using --exercise.
The read-only mode verifies identity links and meter provenance without changing
worlds. Exercise mode advances days and issues real sandbox bills.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

import httpx


def verify(client, preset, exercise):
    started = time.monotonic()

    def call(path, payload=None):
        response = client.request("GET" if payload is None else "POST", "/atlas/api/" + path,
                                  params={"town": preset}, json=payload)
        response.raise_for_status()
        return response.json()

    boot = call("bootstrap")
    snapshot, state = boot["snapshot"], boot["state"]
    assert snapshot["atlasDesign"]["presetId"] == preset
    by_kind = {}
    for p in snapshot["premises"]:
        by_kind.setdefault(p["buildingType"], p)
    service = {s["id"]: s for s in snapshot["servicePoints"]}
    picks = []
    for p in by_kind.values():
        record = call("premises/" + p["id"])
        assert record["premise"]["id"] == p["id"], "Premise API returned another property"
        history = call("premises/" + p["id"] + "/history")
        meters = {service[sid]["meterId"] for sid in p["services"].values()}
        assert history["readings"], "No generated meter reads"
        assert all(r["assetId"] in meters for r in history["readings"]), "Read leaked from another premise"
        picks.append({"premiseId": p["id"], "kind": p["buildingType"], "readings": len(history["readings"])})
    results = {"preset": preset, "homes": snapshot["homes"], "premises": len(snapshot["premises"]),
               "sampledKinds": picks, "sourceThrough": state["through"], "mutations": exercise}
    if exercise:
        town_id = snapshot["id"]
        previous = state["through"]
        call("advance", {"townId": town_id, "expectedThrough": previous})
        current = call("state")["through"]
        assert date.fromisoformat(current) == date.fromisoformat(previous) + timedelta(days=1)
        received = call("billing/ingest", {"townId": town_id})
        assert received["received"] > 0, "Billing did not receive observed meter reads"
        again = call("billing/ingest", {"townId": town_id})
        assert again["received"] == 0, "Observation ingestion duplicated reads"
        billed = call("billing/run", {"townId": town_id, "start": previous, "end": current})
        assert billed["issued"] > 0, "No invoice produced from received observations"
        repeated = call("billing/run", {"townId": town_id, "start": previous, "end": current})
        assert repeated["issued"] == 0, "Retry duplicated bills"
        bills = call("billing")
        issued = [d for d in bills["documents"] if d["status"] == "issued"]
        assert issued and all(d["sourceObservationIds"] for d in issued), "Bill lacks observed-read provenance"
        results["billing"] = {"received": received["received"], "issued": billed["issued"],
                              "blocked": billed["blocked"], "through": current,
                              "retryReceived": again["received"], "retryIssued": repeated["issued"],
                              "sampleDocument": issued[0]}
        sample = next(iter(by_kind.values()))
        before = call("premises/" + sample["id"])
        asset = before["assets"][0]
        new_device = "QA-" + asset["id"] + "-" + current
        command = {"townId": town_id, "commandId": "qa-replace-" + current,
                   "meterId": asset["id"], "newDeviceId": new_device,
                   "workOrderId": "QA-WO-" + current, "note": "Disposable release acceptance meter exchange"}
        replaced = call("billing/replace-meter", command)
        retried = call("billing/replace-meter", command)
        assert replaced == retried, "Replacement retry changed its result"
        after = call("premises/" + sample["id"])
        changed = next(a for a in after["assets"] if a["id"] == asset["id"])
        assert changed["device"] == new_device, "Billing action did not change physical device"
        call("advance", {"townId": town_id, "expectedThrough": current})
        final = call("premises/" + sample["id"])
        changed = next(a for a in final["assets"] if a["id"] == asset["id"])
        assert changed["observed_device"] == new_device, "Future read did not come from replacement device"
        results["replacement"] = {"premiseId": sample["id"], "meterId": asset["id"],
                                  "beforeDevice": asset["device"], "afterDevice": new_device,
                                  "nextReadDevice": changed["observed_device"], "retryIdentical": True}
    results["elapsedSeconds"] = round(time.monotonic() - started, 2)
    results["passed"] = True
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8054")
    parser.add_argument("--preset", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exercise", action="store_true", help="Mutate only a disposable QA runtime")
    args = parser.parse_args()
    rows = []
    with httpx.Client(base_url=args.url, timeout=900) as client:
        for preset in args.preset:
            try:
                result = verify(client, preset, args.exercise)
            except Exception as exc:
                result = {"preset": preset, "passed": False, "error": str(exc)}
            rows.append(result)
            print(json.dumps(result), flush=True)
            if not result["passed"]:
                break
    report = {"passed": len(rows) == len(args.preset) and all(r["passed"] for r in rows), "towns": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
