"""Exercise actual Virtual Systems recipients on an explicitly disposable server."""

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exercise", action="store_true", required=True)
    args = parser.parse_args()
    started = time.monotonic()
    with httpx.Client(base_url=args.url, timeout=1800) as client:

        def call(path, body=None, **query):
            response = client.request(
                "GET" if body is None else "POST",
                "/atlas/api/" + path,
                params={"town": args.preset, **query},
                json=body,
            )
            response.raise_for_status()
            return response.json()

        town = call("summary")
        payload = {"townId": town["town"]["id"]}
        print(
            json.dumps({"step": "opened", "preset": args.preset, "homes": town["town"]["homes"]}), flush=True
        )
        initialized = call("virtual-systems/initialize", payload)
        assert initialized["mode"] == "actual-virtual-systems"
        assert initialized["counts"]["accounts"] == town["town"]["accounts"]
        print(json.dumps({"step": "recipient-provisioned", "counts": initialized["counts"]}), flush=True)
        ingest = call("virtual-systems/ingest", payload)
        assert ingest["imported"] > 0
        assert call("virtual-systems/ingest", payload)["imported"] == 0
        print(json.dumps({"step": "observations-received", **ingest}), flush=True)
        end = town["state"]["through"]
        period = {**payload, "start": (date.fromisoformat(end) - timedelta(days=1)).isoformat(), "end": end}
        billed = call("virtual-systems/run", period)
        reviewed = 0
        for _ in range(500):
            if not billed.get("invoiceBlocked"):
                break
            holds = call("virtual-systems", exceptionCode="HIGH_CONSUMPTION")["exceptions"]
            progress = 0
            for hold in holds:
                if hold["code"] != "HIGH_CONSUMPTION":
                    continue
                response = client.post(
                    "/atlas/api/virtual-systems/resolve",
                    params={"town": args.preset},
                    json={
                        **payload,
                        "exceptionId": hold["id"],
                        "note": "Disposable synthetic QA: reviewed observed high consumption and accepted this fixture reading.",
                    },
                )
                if response.is_success:
                    progress += 1
            if not progress:
                break
            reviewed += progress
            billed = call("virtual-systems/run", period)
            print(
                json.dumps(
                    {
                        "step": "reviewed-observed-holds",
                        "reviewed": reviewed,
                        "invoices": billed["counts"]["invoices"],
                    }
                ),
                flush=True,
            )
        assert billed["counts"]["invoices"] > 0, billed.get("invoiceBlocked")
        assert billed["trialBalance"]["totals"]["CAD"]["balanced"]
        repeated = call("virtual-systems/run", period)
        assert repeated["counts"]["invoices"] == billed["counts"]["invoices"]
        assert repeated.get("ledgerDeliveries", 0) == 0
        saved = call("virtual-systems")
        assert saved["counts"] == repeated["counts"]
        report = {
            "passed": True,
            "preset": args.preset,
            "homes": town["town"]["homes"],
            "accounts": town["town"]["accounts"],
            "observations": ingest,
            "counts": saved["counts"],
            "period": period,
            "trialBalance": saved["trialBalance"],
            "reviewedHighConsumptionHolds": reviewed,
            "retryInvoiceCountStable": True,
            "retryLedgerDeliveries": repeated.get("ledgerDeliveries", 0),
            "remainingExceptions": saved.get("exceptionTotal"),
            "schedulerManaged": saved["schedulerManaged"],
            "tariffPolicy": saved["tariffPolicy"],
            "elapsedSeconds": round(time.monotonic() - started, 2),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
