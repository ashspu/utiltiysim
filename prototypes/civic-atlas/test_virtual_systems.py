"""Optional real-recipient integration; no private VS code is bundled."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from virtual_systems import VirtualSystems, configured

from utilsim.config import load_preset
from utilsim.gen.pipeline import generate
from utilsim.io.snapshot import build_snapshot
from utilsim.world.store import World


@pytest.mark.skipif(not configured(), reason="Set ATLAS_VIRTUAL_SYSTEMS_ROOT to run real private-recipient proof")
def test_actual_recipient_invoice_and_independent_ledger(tmp_path):
    snapshot = build_snapshot(generate(load_preset("village", houses=20, seed="VS-PROOF")), embed_state=False)
    world = World(tmp_path / "world.sqlite")
    world.initialize(snapshot, "ATLAS-VS-PROOF", settings={"annual_meter_failure": 0, "annual_meter_drift": 0})
    world.advance("2026-01-03")
    adapter = VirtualSystems(world, snapshot)
    initialized = adapter.initialize()
    assert initialized["counts"]["accounts"] == len(snapshot["accounts"])
    received = adapter.ingest()
    assert received["imported"] > 0 and received["missing"] == 0
    assert adapter.ingest()["imported"] == 0
    financial = adapter.run("2026-01-01", "2026-01-03")
    for _ in range(10):
        if "invoiceBlocked" not in financial:
            break
        with adapter.session() as (billing, ledger, meta):
            with billing.db() as db:
                exceptions = [dict(r) for r in db.execute("SELECT * FROM exceptions WHERE status='open' AND code='HIGH_CONSUMPTION'")]
            for item in exceptions:
                try:
                    billing.resolve(item["id"], "Independent QA inspected the synthetic source interval and confirmed this high consumption.")
                except ValueError:
                    pass
        financial = adapter.run("2026-01-01", "2026-01-03")
    assert financial["counts"]["invoices"] > 0, financial.get("invoiceBlocked")
    assert financial["trialBalance"]["totals"]["CAD"]["balanced"]
    newer = {row["id"] for row in adapter.inspect()["invoices"]}
    older = {row["id"] for row in adapter.inspect(invoice_offset=50)["invoices"]}
    assert newer.isdisjoint(older)
    with adapter.session() as (billing, ledger, meta):
        with billing.db() as db:
            total = db.execute("SELECT SUM(total_minor) FROM invoices").fetchone()[0]
            assert db.execute("SELECT COUNT(*) FROM bill_reads").fetchone()[0] > 0
        assert sum(row["original_minor"] for row in ledger.receivables()) == total
    retry = adapter.run("2026-01-01", "2026-01-03")
    assert retry["counts"]["invoices"] == financial["counts"]["invoices"]
    assert retry["ledgerDeliveries"] == 0
    assert VirtualSystems(World(world.path), snapshot).inspect()["counts"] == retry["counts"]


@pytest.mark.skipif(not configured(), reason="Requires the real private VS recipients")
def test_http_billing_field_world_next_read_roundtrip(tmp_path):
    import server
    from fastapi.testclient import TestClient

    from utilsim.world import water_faults

    snapshot = build_snapshot(generate(load_preset("village", houses=20, seed="VS-HTTP")), embed_state=False)
    world = World(tmp_path / "world.sqlite")
    world.initialize(snapshot, "ATLAS-HTTP-PROOF", settings={"annual_meter_failure": 0, "annual_meter_drift": 0})
    world.advance("2026-01-03")
    with world.read_db() as db:
        meta = world.metadata(db)
        asset = dict(db.execute("SELECT * FROM assets WHERE commodity='water' AND installed<'2026-01-01' LIMIT 1").fetchone())
    water_faults.command(world, {"schemaVersion": water_faults.VERSION, "commandId": "qa-leak",
        "environmentId": meta["environment"], "worldFingerprint": meta["fingerprint"], "actorId": "world-admin",
        "expectedRevision": 0, "action": "start", "reason": "Disposable QA fixture", "causalReference": "qa",
        "assetId": asset["id"], "leakM3PerHour": "2"})
    world.advance("2026-01-04")
    body = {"townId": snapshot["id"]}
    with TestClient(server.create_app(world), base_url="http://127.0.0.1") as client:
        assert client.post("/atlas/api/virtual-systems/initialize", json=body).status_code == 200
        assert client.post("/atlas/api/virtual-systems/ingest", json=body).status_code == 200
        property_record = client.get("/atlas/api/premises/" + asset["premise"]).json()
        property_water = next(a for a in property_record["assets"] if a["id"] == asset["id"])
        assert property_water["installation"] == asset["installation"]
        request = {**body, "installationId": property_water["installation"], "reason": "Water consumption increased", "commandId": "api-repair"}
        response = client.post("/atlas/api/virtual-systems/repair", json=request)
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["authenticatedDelivery"] and report["order"]["status"] == "reported"
        assert report["order"]["reports"][0]["outcome"] == "completed"
        saved_request = client.get("/atlas/api/virtual-systems?premise=" + asset["premise"]).json()["fieldRequests"][0]
        assert saved_request["commandId"] == "api-repair"
        assert saved_request["order"]["id"] == report["order"]["id"]
        assert client.post("/atlas/api/virtual-systems/repair", json=request).json() == report
        accepted = client.post("/atlas/api/virtual-systems/accept-report", json={**body, "orderId": report["order"]["id"], "note": "Reviewed crew repair evidence"})
        assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
        assert client.post("/atlas/api/advance", json={**body, "expectedThrough": "2026-01-04"}).status_code == 200
        assert client.post("/atlas/api/virtual-systems/ingest", json=body).status_code == 200
        assert client.get("/atlas/api/virtual-systems?premise=" + asset["premise"]).status_code == 200
    with VirtualSystems(world, snapshot).session() as (billing, ledger, meta):
        with billing.db() as db:
            received = {row["start"]: float(row["quantity"]) for row in db.execute(
                "SELECT start,quantity FROM reads WHERE installation_id=?", (asset["installation"],))}
            assert received["2026-01-03"] > received["2026-01-04"] + 40
            assert db.execute("SELECT COUNT(*) FROM field_reports").fetchone()[0] == 1
    assert not water_faults.inspect(world, asset["id"])["current"]["active"]


@pytest.mark.skipif(not configured(), reason="Requires the real private VS recipients")
def test_eligible_batch_holds_incomplete_accounts_and_resumes(tmp_path, monkeypatch):
    snapshot = build_snapshot(generate(load_preset("village", houses=20, seed="VS-PARTITION")), embed_state=False)
    world = World(tmp_path / "world.sqlite")
    world.initialize(snapshot, "ATLAS-PARTITION", settings={"annual_meter_failure": 0, "annual_meter_drift": 0})
    world.advance("2026-01-03")
    adapter = VirtualSystems(world, snapshot)
    adapter.initialize()
    # Deliberately missing producer input in this disposable fixture. Billing
    # must hold the entire account and cannot borrow hidden physical truth.
    original = world.export_v2
    first = original("2026-01-01", "2026-01-02")
    installation = next(o["installationId"] for o in first["observations"] if o["commodity"] == "electric")
    def missing_input(*args, **kwargs):
        batch = original(*args, **kwargs)
        for observation in batch["observations"]:
            if observation["installationId"] == installation:
                observation.update(status="missing", quantity=None, registerValue=None)
        from worldfeed.adapter import stable
        batch["batchId"] = stable({k: v for k, v in batch.items() if k != "batchId"})
        return batch
    monkeypatch.setattr(world, "export_v2", missing_input)
    assert adapter.ingest()["missing"] == 2
    financial = adapter.run("2026-01-01", "2026-01-03")
    assert financial["invoiceBlocked"]
    before = financial["disposition"]
    assert before["heldContracts"] > 0 and before["eligibleAccounts"] > 0
    with adapter.session() as (billing, ledger, meta):
        with billing.db() as db:
            held_account = db.execute("SELECT account_id FROM contracts WHERE installation_id=?", (installation,)).fetchone()[0]
    from billing.store import Billing
    original_invoice = Billing.invoice
    attempts = 0
    def lost_worker(self, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("Disposable worker stopped after the first committed account")
        return original_invoice(self, *args, **kwargs)
    with monkeypatch.context() as stopped:
        stopped.setattr(Billing, "invoice", lost_worker)
        with pytest.raises(RuntimeError, match="worker stopped"):
            adapter.invoice_eligible("2026-01-01", "2026-01-03")
    assert adapter.inspect()["counts"]["invoices"] == 1
    result = adapter.invoice_eligible("2026-01-01", "2026-01-03")
    assert result["accountsProcessed"] == before["eligibleAccounts"] - 1
    assert result["disposition"]["eligibleAccounts"] == 0
    assert result["disposition"]["heldAccounts"] == before["heldAccounts"]
    assert result["nextPeriodStart"] == "2026-01-01"  # Partial invoices cannot silently skip held service.
    assert result["trialBalance"]["totals"]["CAD"]["balanced"]
    with adapter.session() as (billing, ledger, meta):
        with billing.db() as db:
            assert not db.execute("SELECT 1 FROM invoices WHERE account_id=?", (held_account,)).fetchone()
            assert db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == before["eligibleAccounts"]
    retry = adapter.invoice_eligible("2026-01-01", "2026-01-03")
    assert retry["accountsProcessed"] == retry["ledgerDeliveries"] == 0
    assert retry["counts"]["invoices"] == result["counts"]["invoices"]
