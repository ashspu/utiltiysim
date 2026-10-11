"""Local observation-led billing workbench using UtilitySim's tariff calculator.

This ledger is deliberately separate from physical truth and from external IS-U.
It never fills a missing read from truth. Periods are half-open [start, end).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from utilsim.m2c.billing import charges, lines
from utilsim.world.store import canonical, stable

SCHEMA = """
CREATE TABLE IF NOT EXISTS reads(id TEXT PRIMARY KEY, meter TEXT, premise TEXT,
 installation TEXT, commodity TEXT, unit TEXT, day TEXT, device TEXT, quantity TEXT,
 status TEXT, received_at TEXT, UNIQUE(meter,day));
CREATE INDEX IF NOT EXISTS reads_meter_day ON reads(meter,day);
CREATE INDEX IF NOT EXISTS reads_premise ON reads(premise,day);
CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, account TEXT, premise TEXT,
 installation TEXT, meter TEXT, start TEXT, end TEXT, status TEXT, amount_cents INTEGER,
 currency TEXT, payload TEXT, UNIQUE(meter,start,end));
CREATE INDEX IF NOT EXISTS documents_premise ON documents(premise,start);
CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,meter TEXT,premise TEXT,day TEXT,
 reason TEXT,status TEXT,work_order TEXT);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
"""


class BillingBridge:
    def __init__(self, world, snapshot):
        self.world = world
        self.snapshot = snapshot
        self.path = Path(world.path).with_name("billing.sqlite")
        self.premises = {p["id"]: p for p in snapshot["premises"]}
        self.accounts = {a["id"]: a for a in snapshot.get("accounts", [])}
        self.partners = {p["id"]: p for p in snapshot.get("businessPartners", [])}
        self.contracts = {c["installationId"]: c for c in snapshot.get("contracts", [])}
        self.assignments = {a["contractId"]: a for a in snapshot.get("tariffAssignments", [])}
        self.tariffs = {t["id"]: t for t in snapshot.get("tariffs", [])}

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=60)
        db.row_factory = sqlite3.Row
        try:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            identity = self.snapshot["id"]
            prior = db.execute("SELECT value FROM metadata WHERE key='town'").fetchone()
            if prior and prior[0] != identity:
                raise ValueError("The billing ledger belongs to another town.")
            db.execute("INSERT OR IGNORE INTO metadata VALUES('town',?)", (identity,))
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def inspect(self, premise=None, offset=0, limit=50):
        if premise and premise not in self.premises:
            raise ValueError("Unknown premise.")
        accounts = [a for a in self.accounts.values() if a.get("premiseId") == premise] if premise else []
        with self.world.read_db() as world_db:
            world_meta = self.world.metadata(world_db)
        result = {"schemaVersion": "civic-atlas-billing/1", "townId": self.snapshot["id"],
                  "mode": "local-observation-ledger", "externalVirtualSystems": "not-configured",
                  "calculator": "utilsim.m2c.billing", "receivedReads": 0, "missingReads": 0,
                  "issuedDocuments": 0, "blockedDocuments": 0, "issuedAmountCents": 0,
                  "accounts": accounts, "customers": [self.partners[a["businessPartnerId"]] for a in accounts
                                                       if a.get("businessPartnerId") in self.partners],
                  "documents": [], "cases": [], "reads": [], "offset": offset, "limit": limit,
                  "nextPeriodStart": world_meta["start"], "through": world_meta["through"]}
        if not self.path.exists():
            return result
        with sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            clause, args = (" WHERE premise=?", (premise,)) if premise else ("", ())
            last_end = db.execute("SELECT MAX(end) FROM documents WHERE status='issued'" +
                                  (" AND premise=?" if premise else ""), args).fetchone()[0]
            result["nextPeriodStart"] = last_end or world_meta["start"]
            result["receivedReads"] = db.execute("SELECT COUNT(*) FROM reads" + clause, args).fetchone()[0]
            result["missingReads"] = db.execute("SELECT COUNT(*) FROM reads WHERE quantity IS NULL" +
                                               (" AND premise=?" if premise else ""), args).fetchone()[0]
            totals = db.execute("SELECT status,COUNT(*) n,SUM(amount_cents) amount FROM documents" + clause +
                                " GROUP BY status", args).fetchall()
            for row in totals:
                result["issuedDocuments" if row["status"] == "issued" else "blockedDocuments"] = row["n"]
                if row["status"] == "issued":
                    result["issuedAmountCents"] = row["amount"] or 0
            result["documents"] = [json.loads(r[0]) for r in db.execute(
                "SELECT payload FROM documents" + clause + " ORDER BY end DESC,id LIMIT ? OFFSET ?",
                (*args, limit, offset))]
            result["cases"] = [dict(r) for r in db.execute("SELECT * FROM cases" + clause +
                " ORDER BY day DESC,id LIMIT ? OFFSET ?", (*args, limit, offset))]
            result["reads"] = [dict(r) for r in db.execute("SELECT * FROM reads" + clause +
                " ORDER BY day DESC,id LIMIT ? OFFSET ?", (*args, limit, offset))]
        return result

    def ingest(self):
        """Receive committed observations exactly once; no physical-truth query."""
        inserted = 0
        with self.db() as db, self.world.read_db() as source:
            meta = self.world.metadata(source)
            cursor = db.execute("SELECT value FROM metadata WHERE key='receivedThrough'").fetchone()
            start = cursor[0] if cursor else meta["start"]
            for row in source.execute(
                "SELECT o.*,a.premise,a.installation,a.commodity,a.unit FROM observations o "
                "JOIN assets a ON a.id=o.asset WHERE o.day>=? AND o.day<? ORDER BY o.day,o.id",
                (start, meta["through"])):
                count = db.execute("INSERT OR IGNORE INTO reads VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (row["id"], row["asset"], row["premise"], row["installation"], row["commodity"],
                     row["unit"], row["day"], row["device"], row["quantity"], row["status"], meta["through"])).rowcount
                inserted += count
                if row["quantity"] is None:
                    db.execute("INSERT OR IGNORE INTO cases VALUES(?,?,?,?,?,'open',NULL)",
                        ("CASE-" + stable(row["id"]), row["asset"], row["premise"], row["day"], "missing-read"))
            db.execute("INSERT OR REPLACE INTO metadata VALUES('receivedThrough',?)", (meta["through"],))
        return {"received": inserted, "receivedThrough": meta["through"], "summary": self.inspect()}

    def run(self, start, end):
        begin, finish = date.fromisoformat(start), date.fromisoformat(end)
        if begin.isoformat() != start or finish.isoformat() != end or not 0 < (finish - begin).days <= 366:
            raise ValueError("Use a billing period of 1–366 completed days.")
        with self.world.read_db() as source:
            meta = self.world.metadata(source)
            if start < meta["start"] or end > meta["through"]:
                raise ValueError("Bill only completed physical days.")
            meters = [dict(r) for r in source.execute("SELECT id,premise,installation,commodity,unit FROM assets")]
        issued = blocked = reused = 0
        with self.db() as db:
            for meter in meters:
                prior = db.execute("SELECT status FROM documents WHERE meter=? AND start=? AND end=?",
                                   (meter["id"], start, end)).fetchone()
                if prior and prior[0] == "issued":
                    reused += 1
                    continue
                overlap = db.execute("SELECT 1 FROM documents WHERE meter=? AND status='issued' AND start<? AND end>?",
                                     (meter["id"], end, start)).fetchone()
                if overlap:
                    raise ValueError("This period overlaps an issued bill; use a new unbilled period.")
                contract = self.contracts.get(meter["installation"], {})
                assignment = self.assignments.get(contract.get("id"), {})
                tariff = self.tariffs.get(assignment.get("tariffId"))
                account = self.accounts.get(contract.get("accountId"), {})
                readings = [dict(r) for r in db.execute("SELECT * FROM reads WHERE meter=? AND day>=? AND day<? ORDER BY day",
                                                      (meter["id"], start, end))]
                reason = None
                if not tariff or not account:
                    reason = "Missing configured contract, account or tariff."
                elif contract.get("validFrom", "")[:10] > start or (contract.get("validTo") and contract["validTo"][:10] < end):
                    reason = "Contract does not cover this billing period."
                elif len(readings) != (finish - begin).days or any(r["quantity"] is None or r["status"] != "observed" for r in readings):
                    reason = "Incomplete received observations. Missing use is never filled from physical truth."
                amount = 0
                bill_lines = []
                if not reason:
                    quantity = sum(float(r["quantity"]) for r in readings)
                    components, subtotal, tax = charges(tariff, meter["commodity"], np.array([quantity]), np.array([0.0]),
                        np.array([0.0]), np.array([float((finish - begin).days)]), 1e20, 0, np.array([False]))
                    bill_lines = lines(components, 0)
                    bill_lines.append({"type": "tax", "description": "Tax", "amount": float(tax[0])})
                    amount = int(round(float(subtotal[0] + tax[0]) * 100))
                identity = "BILL-" + stable(self.snapshot["id"], meter["id"], start, end)
                status = "blocked" if reason else "issued"
                doc = {"id": identity, "premiseId": meter["premise"], "accountId": account.get("id"),
                       "installationId": meter["installation"], "meterId": meter["id"], "commodity": meter["commodity"],
                       "start": start, "end": end, "status": status, "reason": reason, "amountCents": amount,
                       "currency": account.get("currency", "CAD"), "tariffId": assignment.get("tariffId"),
                       "sourceObservationIds": [r["id"] for r in readings], "lines": bill_lines,
                       "quantity": round(sum(float(r["quantity"] or 0) for r in readings), 4),
                       "unit": meter["unit"], "due": (finish + timedelta(days=21)).isoformat()}
                db.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (identity, account.get("id"), meter["premise"], meter["installation"], meter["id"], start,
                            end, status, amount, doc["currency"], canonical(doc)))
                issued += status == "issued"
                blocked += status == "blocked"
        return {"issued": issued, "blocked": blocked, "unchanged": reused, "summary": self.inspect()}

    def replace(self, command_id, meter, device, work_order, note):
        with self.world.read_db() as source:
            environment = self.world.metadata(source)["environment"]
        result = self.world.replace_meter(command_id, environment, meter, device, work_order, note)
        with self.db() as db:
            db.execute("UPDATE cases SET status='replacement-completed',work_order=? WHERE meter=? AND status='open'",
                       (work_order, meter))
        return {**result, "note": "Replacement affects future days. Historical missing reads and blocked bills remain unresolved."}
