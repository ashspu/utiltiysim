"""Optional adapter to the separately installed, private Virtual Systems engine.

No private source is bundled. All financial mutations use recipient domain methods;
physical truth is never passed to Billing. Dedicated stores live beside the town.
"""
import json
import os
import sys
from contextlib import contextmanager, nullcontext
from datetime import date, timedelta
from pathlib import Path

from source_binding import fingerprint

_indexed_paths = set()


def ensure_query_indexes(billing):
    """Index-only tuning on this adapter's dedicated recipient, never business writes."""
    identity = str(Path(billing.path).resolve())
    if identity in _indexed_paths:
        return
    with billing.db() as db:
        db.execute("CREATE INDEX IF NOT EXISTS atlas_bills_cycle_account ON bills(cycle_id,account_id,currency)")
        db.execute("CREATE INDEX IF NOT EXISTS atlas_contracts_account ON contracts(account_id,start,end)")
        db.execute("CREATE INDEX IF NOT EXISTS atlas_jobs_parent ON jobs(parent_job_id)")
        db.execute("CREATE INDEX IF NOT EXISTS atlas_jobs_queue ON jobs(status,requested_at)")
        db.execute("CREATE INDEX IF NOT EXISTS atlas_job_items_status ON job_items(job_id,status)")
        db.execute("CREATE INDEX IF NOT EXISTS atlas_outbox_due ON outbox(status,next_attempt_at,created_at)")
    _indexed_paths.add(identity)


def configured():
    root = Path(os.environ.get("ATLAS_VIRTUAL_SYSTEMS_ROOT", ""))
    return bool(os.environ.get("ATLAS_VIRTUAL_SYSTEMS_ROOT")) and all((root / path).is_file() for path in (
        "worldfeed/adapter.py", "billing/store.py", "receivables/store.py", "synth_runtime/__init__.py", "worldfield/recipient.py"))


class VirtualSystems:
    def __init__(self, world, snapshot):
        self.world, self.snapshot = world, snapshot
        with world.read_db() as db:
            bound = db.execute("SELECT value FROM meta WHERE key='atlasSourceSha256'").fetchone()
        self.source_hash = json.loads(bound[0]) if bound else fingerprint(snapshot)
        self.directory = Path(world.path).parent / "virtual-systems"
        self.manifest_path = self.directory / "atlas-integration.json"

    def readiness(self):
        return {"configured": configured(), "initialized": self.manifest_path.is_file(),
                "mode": "actual-virtual-systems" if configured() else "not-configured",
                "schedulerManaged": False, "fieldAdapter": "authenticated-manual-water-repair",
                "tariffPolicy": "Illustrative flat CAD rates: electric 0.20/kWh, gas 0.45/m3, water 1.80/m3, sewer 1.20/m3; no fixed fees or tax. These differ from the native town tariff model."}

    @contextmanager
    def session(self, channel_name="batch"):
        if not configured():
            raise ValueError("Set ATLAS_VIRTUAL_SYSTEMS_ROOT to the separately installed Virtual Systems checkout.")
        root = str(Path(os.environ["ATLAS_VIRTUAL_SYSTEMS_ROOT"]).resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
        from billing.store import ACTOR, Billing
        from receivables.store import Subledger
        from vscontracts import CHANNEL, clock
        from vscontracts.runtime_clock import RuntimeClock
        from worldfeed.adapter import instant
        with self.world.read_db() as db:
            meta = self.world.metadata(db)
        self.directory.mkdir(parents=True, exist_ok=True)
        token = clock.install(RuntimeClock(instant(meta["through"] + "T12:00:00Z"), "America/New_York"))
        actor, channel = ACTOR.set("atlas-operator"), CHANNEL.set(channel_name)
        billing = ledger = None
        try:
            billing = Billing(self.directory / "billing.sqlite", meta["environment"])
            ensure_query_indexes(billing)
            ledger = Subledger(self.directory / "ledger.sqlite", meta["environment"])
            yield billing, ledger, meta
        finally:
            if billing:
                billing.store.release_thread()
            if ledger:
                ledger.store.release_thread()
            CHANNEL.reset(channel)
            ACTOR.reset(actor)
            clock.uninstall(token)

    def manifest(self):
        if not self.manifest_path.is_file():
            raise ValueError("Initialize the dedicated Virtual Systems recipients first.")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if manifest["sourceSha256"] != self.source_hash:
            raise ValueError("Virtual Systems recipients belong to another source revision. Existing history was preserved.")
        return manifest

    def save(self, manifest):
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.manifest_path)

    def initialize(self):
        if self.manifest_path.is_file():
            self.manifest()
            return self.inspect()
        self.directory.mkdir(parents=True, exist_ok=True)
        source_pin = self.directory / "source-sha256.txt"
        if source_pin.is_file():
            if source_pin.read_text(encoding="utf-8") != self.source_hash:
                raise ValueError("An incomplete recipient setup belongs to another source; saved data was preserved.")
        elif (self.directory / "billing.sqlite").exists():
            raise ValueError("Unbound recipient database exists. Select a new dedicated store.")
        else:
            source_pin.write_text(self.source_hash, encoding="utf-8")
        with self.session() as (billing, ledger, meta):
            first_end = (date.fromisoformat(meta["start"]) + timedelta(days=1)).isoformat()
            batch = self.world.export_v2(meta["start"], first_end)
            assets = batch["assets"]
            partners = {p["id"]: p for p in self.snapshot.get("businessPartners", [])}
            accounts = {a["premiseId"]: a for a in self.snapshot.get("accounts", [])}
            contracts = {c["installationId"]: c for c in self.snapshot.get("contracts", []) if c.get("status", "active") == "active"}
            bindings = {a["servicePointId"]: a["installationId"] for a in assets}
            rates = {"electric": "0.20", "gas": "0.45", "water": "1.80", "sewer": "1.20"}
            # One recipient-owned transaction, including its validation and events.
            with billing.db() as db:
                def create(kind, payload):
                    if not db.execute("SELECT 1 FROM " + kind + " WHERE id=?", (payload["id"],)).fetchone():
                        billing._create(db, kind, payload)
                for commodity, rate in rates.items():
                    create("tariffs", {"id": "ATLAS-FLAT-" + commodity, "code": "ATLAS-ILLUSTRATIVE-" + commodity,
                        "commodity": commodity, "rate": rate, "version": 1, "fixed_minor": 0, "currency": "CAD"})
                for account in self.snapshot.get("accounts", []):
                    partner = partners.get(account.get("businessPartnerId"), {})
                    create("accounts", {"id": account["id"], "name": partner.get("name") or account["id"]})
                for premise in self.snapshot["premises"]:
                    account = accounts.get(premise["id"])
                    if not account:
                        raise ValueError("Every mapped premise must have an existing account before VS provisioning.")
                    partner = partners.get(account.get("businessPartnerId"), {})
                    create("accounts", {"id": account["id"], "name": partner.get("name") or account["id"]})
                    kind = premise.get("premiseType", "residential")
                    create("premises", {"id": premise["id"], "address_line1": premise.get("address") or premise["id"],
                        "premise_type": kind if kind in ("residential", "commercial", "industrial", "agricultural", "municipal") else "municipal"})
                for asset in sorted(assets, key=lambda a: a["commodity"] == "sewer"):
                    row = {"id": asset["installationId"], "meter_id": asset["meterId"],
                           "premise_id": asset["premiseId"], "commodity": asset["commodity"]}
                    if asset["commodity"] == "sewer":
                        row.update(source_installation_id=bindings[asset["sourceServicePointId"]],
                                   derivation_factor=asset["derivation"]["factor"])
                    create("installations", row)
                    contract = contracts.get(asset["installationId"], {})
                    create("contracts", {"id": contract.get("id") or "ATLAS-" + asset["installationId"],
                        "account_id": contract.get("accountId") or accounts[asset["premiseId"]]["id"], "installation_id": row["id"],
                        "tariff_id": "ATLAS-FLAT-" + asset["commodity"], "start": max(meta["start"], asset["serviceFrom"])})
            self.save({"version": 1, "sourceSha256": self.source_hash, "bindings": bindings,
                       "receivedThrough": meta["start"], "missingObservations": 0, "environment": meta["environment"]})
        return self.inspect()

    def ingest(self):
        manifest = self.manifest()
        totals = {"imported": 0, "replayed": 0, "missing": 0, "held": 0}
        with self.session("mdm") as (billing, ledger, meta):
            from worldfeed.adapter import deliver
            cursor = date.fromisoformat(manifest["receivedThrough"])
            while cursor.isoformat() < meta["through"]:
                end = (cursor + timedelta(days=1)).isoformat()
                batch = self.world.export_v2(cursor.isoformat(), end)
                result = deliver(batch, instance_id=meta["environment"], bindings=manifest["bindings"],
                                 as_of=meta["through"] + "T12:00:00Z", receive=billing.receive_meter_read)
                if result["blockedSource"]:
                    raise ValueError("Virtual Systems rejected a source reading; retry is safe: " + result["error"])
                counts = result["plan"]["counts"]
                if counts["unmapped"] or counts["unsupported_service"] or counts["not_available"]:
                    raise ValueError("An observation is unmapped, unsupported or unavailable; ingestion cursor was retained.")
                totals["missing"] += counts["missing"]
                for receipt in result["receipts"]:
                    totals["replayed" if receipt["replayed"] else "imported"] += 1
                    totals["held"] += receipt["status"] == "held"
                manifest["receivedThrough"] = end
                manifest["missingObservations"] += counts["missing"]
                self.save(manifest)
                cursor += timedelta(days=1)
        return {**totals, "receivedThrough": manifest["receivedThrough"]}

    @staticmethod
    def recover_jobs(billing):
        # The Atlas world lock excludes another financial worker on this store.
        # Keep committed documents and resume any job queued before a crash.
        billing.recover_interrupted_jobs()
        while job := billing.claim_next_job("atlas-recovery"):
            billing.run_job(job)

    @staticmethod
    def partition(billing, cycle):
        readiness = billing.cycle_readiness(cycle)
        unbilled = set(readiness["unbilled"])
        with billing.db() as db:
            period = db.execute("SELECT * FROM cycles WHERE id=?", (cycle,)).fetchone()
            contracts = billing._active_contracts(db, period)
            pending = {r[0] for r in db.execute("SELECT DISTINCT b.account_id FROM bills b WHERE b.cycle_id=? "
                "AND NOT EXISTS (SELECT 1 FROM invoice_bills ib WHERE ib.bill_id=b.id)", (cycle,))}
            invoiced_contracts = {r[0] for r in db.execute("SELECT DISTINCT b.contract_id FROM bills b "
                "JOIN invoice_bills ib ON ib.bill_id=b.id WHERE b.cycle_id=?", (cycle,))}
        accounts = {r["account_id"] for r in contracts}
        held = {r["account_id"] for r in contracts if r["id"] in unbilled}
        eligible = sorted(pending - held)
        return {"cycle": cycle, "start": period["start"], "end": period["end"],
                "contracts": len(contracts), "billedContracts": readiness["billed"],
                "heldContracts": len(unbilled), "invoicedContracts": len(invoiced_contracts),
                "accounts": len(accounts), "heldAccounts": len(held),
                "eligibleAccounts": len(eligible), "invoicedAccounts": len(accounts - pending - held),
                "heldAccountSample": sorted(held)[:50]}, eligible

    def record_partition(self, billing, cycle):
        result, eligible = self.partition(billing, cycle)
        manifest = self.manifest()
        manifest["lastBillingBatch"] = result
        self.save(manifest)
        return result, eligible

    @staticmethod
    def post_invoices(billing, ledger):
        delivered = 0
        while receipts := billing.dispatch_due(ledger.post_invoice):
            if any(r["outcome"] != "delivered" for r in receipts):
                raise ValueError("Invoice delivery is pending; retry the same period to resume.")
            delivered += len(receipts)
        return delivered

    def invoice_eligible(self, start, end):
        self.manifest()
        cycle = "ATLAS-" + start + "-" + end
        with self.session() as (billing, ledger, meta):
            if not meta["start"] <= start < end <= meta["through"]:
                raise ValueError("Choose a completed simulation period.")
            self.recover_jobs(billing)
            _, eligible = self.record_partition(billing, cycle)
            batch = billing.invoice_batch(cycle) if hasattr(billing, "invoice_batch") else nullcontext()
            with batch:
                for account in eligible:
                    # The recipient rechecks complete-account eligibility. Its
                    # committed invoices are the durable checkpoint on retry.
                    billing.invoice(cycle, account_id=account)
            delivered = self.post_invoices(billing, ledger)
            disposition, _ = self.record_partition(billing, cycle)
        return {"cycle": cycle, "ledgerDeliveries": delivered, "accountsProcessed": len(eligible),
                "disposition": disposition, **self.inspect()}

    def run(self, start, end):
        self.manifest()
        with self.session() as (billing, ledger, meta):
            if not meta["start"] <= start < end <= meta["through"]:
                raise ValueError("Choose a completed simulation period.")
            cycle = "ATLAS-" + start + "-" + end
            with billing.db() as db:
                exists = db.execute("SELECT 1 FROM cycles WHERE id=?", (cycle,)).fetchone()
            if not exists:
                billing.create("cycles", {"id": cycle, "label": start + " to " + end, "start": start, "end": end})
            self.recover_jobs(billing)
            billing.bill(cycle)
            try:
                billing.invoice(cycle)
            except ValueError as exc:
                disposition, _ = self.record_partition(billing, cycle)
                return {"cycle": cycle, "invoiceBlocked": str(exc), "disposition": disposition, **self.inspect()}
            delivered = self.post_invoices(billing, ledger)
            disposition, _ = self.record_partition(billing, cycle)
        return {"cycle": cycle, "ledgerDeliveries": delivered, "disposition": disposition, **self.inspect()}

    def resolve(self, identity, note):
        self.manifest()
        with self.session() as (billing, ledger, meta):
            return billing.resolve(identity, note)

    def inspect(self, premise=None, offset=0, exception_code=None, invoice_offset=0):
        ready = self.readiness()
        if not ready["initialized"]:
            return ready
        manifest = self.manifest()
        with self.session() as (billing, ledger, meta):
            with billing.db() as db:
                counts = {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                          for table in ("accounts", "installations", "reads", "bills", "invoices", "exceptions")}
                invoices = [dict(r) for r in db.execute("SELECT v.* FROM invoices v WHERE ? IS NULL OR v.account_id IN "
                    "(SELECT c.account_id FROM contracts c JOIN installations i ON i.id=c.installation_id WHERE i.premise_id=?) "
                    "ORDER BY rowid DESC LIMIT 50 OFFSET ?", (premise, premise, invoice_offset))]
                exceptions = [dict(r) for r in db.execute("SELECT e.*,COALESCE(i.premise_id,ri.premise_id,si.premise_id) premiseId "
                    "FROM exceptions e LEFT JOIN contracts c ON c.id=e.subject LEFT JOIN installations i ON i.id=c.installation_id "
                    "LEFT JOIN reads r ON r.id=e.read_id LEFT JOIN installations ri ON ri.id=r.installation_id "
                    "LEFT JOIN installations si ON si.id=e.subject WHERE e.status='open' AND "
                    "(? IS NULL OR COALESCE(i.premise_id,ri.premise_id,si.premise_id)=?) AND (? IS NULL OR e.code=?) "
                    "ORDER BY (e.code='HIGH_CONSUMPTION') DESC,e.rowid DESC LIMIT 50 OFFSET ?", (premise,premise,exception_code,exception_code,offset))]
                exception_count = db.execute("SELECT COUNT(*) FROM exceptions WHERE status='open' AND (? IS NULL OR code=?)", (exception_code,exception_code)).fetchone()[0]
                readings = [dict(r) for r in db.execute("SELECT r.* FROM reads r JOIN installations i ON i.id=r.installation_id "
                    "WHERE i.premise_id=? ORDER BY r.rowid DESC LIMIT 20", (premise,))] if premise else []
                field_orders = [dict(r) for r in db.execute("SELECT o.id,o.causal_refs FROM investigation_orders o "
                    "JOIN installations i ON i.id=o.installation_id WHERE i.premise_id=? ORDER BY o.rowid DESC LIMIT 20", (premise,))] if premise else []
                next_start = (db.execute("SELECT MIN(start) FROM cycles WHERE status!='invoiced'").fetchone()[0]
                    or db.execute("SELECT MAX(end) FROM cycles WHERE status='invoiced'").fetchone()[0] or meta["start"])
            field_requests = []
            for order in field_orders:
                for causal in json.loads(order["causal_refs"]):
                    identity = causal.removeprefix("atlas-field-")
                    if causal.startswith("atlas-field-") and len(identity) == 32 and all(c in "0123456789abcdef" for c in identity):
                        intent_path = self.directory / "field" / identity / "intent.json"
                        if intent_path.is_file():
                            field_requests.append({**json.loads(intent_path.read_text(encoding="utf-8")), "order": billing.investigation(order["id"])})
            trial = ledger.trial_balance()
        return {**ready, "counts": counts, "invoices": invoices, "exceptions": exceptions,
                "fieldRequests": field_requests, "invoiceOffset": invoice_offset, "exceptionOffset": offset, "exceptionTotal": exception_count, "receivedReadings": readings, "trialBalance": trial, "receivedThrough": manifest["receivedThrough"],
                "missingObservations": manifest["missingObservations"], "nextPeriodStart": next_start,
                "lastBillingBatch": manifest.get("lastBillingBatch"),
                "through": meta["through"]}
