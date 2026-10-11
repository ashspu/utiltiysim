"""Read-only, exhaustive financial disposition audit for an Atlas recipient."""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


def audit(folder, start, end):
    db = sqlite3.connect(
        (folder / "virtual-systems/billing.sqlite").resolve().as_uri() + "?mode=ro", uri=True
    )
    db.row_factory = sqlite3.Row
    cycle = "ATLAS-" + start + "-" + end
    accounts = {r["id"] for r in db.execute("SELECT id FROM accounts")}
    installations = {r["id"] for r in db.execute("SELECT id FROM installations")}
    contracts = [dict(r) for r in db.execute("SELECT * FROM contracts")]
    active = [c for c in contracts if c["start"] < end and c["end"] > start]
    inactive = [c for c in contracts if not (c["start"] < end and c["end"] > start)]
    bills = [dict(r) for r in db.execute("SELECT * FROM bills WHERE cycle_id=?", (cycle,))]
    billed = {b["contract_id"]: b for b in bills}
    assert len(billed) == len(bills), "Duplicate contract document in fixture period"
    invoiced = {r[0] for r in db.execute("SELECT bill_id FROM invoice_bills")}
    exceptions = defaultdict(list)
    for r in db.execute("SELECT * FROM exceptions WHERE cycle_id=? AND status='open'", (cycle,)):
        exceptions[r["subject"]].append(dict(r))
    legitimate = {"MISSING_CONSUMPTION", "HELD_READ", "BILLING_BLOCK", "BILLING_BLOCKED", "MISSING_TARIFF"}
    rows = []
    for c in active:
        bill = billed.get(c["id"])
        if bill:
            assert bill["service_start"] == max(start, c["start"])
            assert bill["service_end"] == min(end, c["end"])
            assert bill["account_id"] == c["account_id"]
            state = "invoiced" if bill["id"] in invoiced else "billed-awaiting-invoice"
            reason = []
        else:
            holds = exceptions[c["id"]]
            assert holds, "Unexplained unbilled contract: " + c["id"]
            reason = sorted({h["code"] for h in holds})
            assert set(reason) <= legitimate, "Unexpected hold requires explicit review: " + str(reason)
            state = "held"
        rows.append(
            {
                "contractId": c["id"],
                "accountId": c["account_id"],
                "installationId": c["installation_id"],
                "state": state,
                "reasons": reason,
            }
        )
    assert set(billed) <= {c["id"] for c in active}
    byaccount = defaultdict(list)
    for row in rows:
        byaccount[row["accountId"]].append(row)
    accountrows = []
    for account in sorted(accounts):
        items = byaccount[account]
        state = (
            "outside-period-or-no-active-contract"
            if not items
            else "held"
            if any(i["state"] == "held" for i in items)
            else "fully-invoiced"
            if all(i["state"] == "invoiced" for i in items)
            else "billed-awaiting-invoice"
        )
        accountrows.append({"accountId": account, "state": state, "activeContracts": len(items)})
    for invoice in db.execute("SELECT * FROM invoices WHERE cycle_id=?", (cycle,)):
        amount = db.execute(
            "SELECT SUM(b.total_minor) FROM invoice_bills ib JOIN bills b ON b.id=ib.bill_id WHERE ib.invoice_id=?",
            (invoice["id"],),
        ).fetchone()[0]
        assert amount == invoice["total_minor"], "Invoice differs from its billing documents"
    missing_source = db.execute(
        "SELECT COUNT(*) FROM bills b WHERE b.cycle_id=? AND NOT EXISTS (SELECT 1 FROM bill_reads br WHERE br.bill_id=b.id)",
        (cycle,),
    ).fetchone()[0]
    assert missing_source == 0, "Bill has no actual reading provenance"
    assert {c["installation_id"] for c in contracts} == installations
    summary = {
        "passed": True,
        "cycle": cycle,
        "accounts": len(accounts),
        "accountDispositions": dict(Counter(r["state"] for r in accountrows)),
        "installations": len(installations),
        "activeContracts": len(active),
        "outsidePeriodContracts": len(inactive),
        "contractDispositions": dict(Counter(r["state"] for r in rows)),
        "bills": len(bills),
        "everyBillHasObservedReadProvenance": True,
        "everyInvoiceMatchesSourceBills": True,
        "unexplainedContracts": 0,
        "unexplainedAccounts": 0,
    }
    db.close()
    return {
        "summary": summary,
        "contracts": rows,
        "accounts": accountrows,
        "outsidePeriodContracts": [
            {"contractId": c["id"], "start": c["start"], "end": c["end"]} for c in inactive
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.folder, args.start, args.end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
