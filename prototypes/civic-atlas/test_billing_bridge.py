"""Observation ingestion, tariff billing and physical remediation round-trip."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from utilsim.config import load_preset
from utilsim.gen.pipeline import generate
from utilsim.io.snapshot import build_snapshot
from utilsim.world.store import World

SPEC = importlib.util.spec_from_file_location("atlas_billing_server", Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server
SPEC.loader.exec_module(server)


@pytest.fixture(scope="module")
def snapshot():
    return build_snapshot(generate(load_preset("village", houses=20, seed="BILLING-FLOW")), embed_state=False)


@pytest.fixture
def world(tmp_path, snapshot):
    value = World(tmp_path / "world.sqlite")
    value.initialize(snapshot, "BILLING-FLOW", settings={"annual_meter_failure": 0, "annual_meter_drift": 0})
    value.advance("2026-01-03")
    return value


def client(world):
    return TestClient(server.create_app(world), base_url="http://127.0.0.1")


def test_bills_require_received_reads_and_retries_never_duplicate(world, snapshot):
    town = {"townId": snapshot["id"]}
    period = {**town, "start": "2026-01-01", "end": "2026-01-03"}
    with client(world) as c:
        blocked = c.post("/atlas/api/billing/run", json=period).json()
        assert blocked["issued"] == 0 and blocked["blocked"] > 0
        first = c.post("/atlas/api/billing/ingest", json=town).json()
        assert first["received"] == world.status()["observations"]
        assert c.post("/atlas/api/billing/ingest", json=town).json()["received"] == 0
        issued = c.post("/atlas/api/billing/run", json=period).json()
        assert issued["issued"] > 0
        retry = c.post("/atlas/api/billing/run", json=period).json()
        assert retry["issued"] == 0 and retry["unchanged"] == issued["issued"]
        assert retry["summary"]["nextPeriodStart"] == period["end"]
        doc = next(d for d in issued["summary"]["documents"] if d["status"] == "issued")
        assert doc["accountId"] in {a["id"] for a in snapshot["accounts"]}
        assert doc["tariffId"] in {t["id"] for t in snapshot["tariffs"]}
        assert len(doc["sourceObservationIds"]) == 2
        assert doc["amountCents"] == round(sum(line["amount"] for line in doc["lines"]) * 100)
        assert c.post("/atlas/api/billing/run", json={**period, "end": "2026-01-02"}).status_code == 409
    with client(World(world.path)) as c:
        saved = c.get("/atlas/api/billing").json()
        assert saved["issuedDocuments"] == issued["summary"]["issuedDocuments"]
        assert saved["receivedReads"] == first["received"]


def test_missing_observation_never_uses_truth_and_replacement_affects_future(world, snapshot):
    with world.read_db() as db:
        asset = db.execute("SELECT a.id,a.premise FROM assets a JOIN observations o ON a.id=o.asset LIMIT 1").fetchone()
        meter, premise = asset["id"], asset["premise"]
    with world.db() as db:
        db.execute("UPDATE assets SET condition='failed' WHERE id=?", (meter,))
    world.advance("2026-01-04")
    with world.db() as db:
        db.execute("UPDATE truth SET quantity='9999999' WHERE asset=?", (meter,))
    town = {"townId": snapshot["id"]}
    with client(world) as c:
        c.post("/atlas/api/billing/ingest", json=town).raise_for_status()
        c.post("/atlas/api/billing/run", json={**town, "start": "2026-01-03", "end": "2026-01-04"}).raise_for_status()
        account = c.get("/atlas/api/billing", params={"premise": premise}).json()
        failed = next(d for d in account["documents"] if d["meterId"] == meter)
        assert failed["status"] == "blocked" and failed["amountCents"] == 0 and failed["quantity"] == 0
        assert account["cases"] and account["customers"] and account["accounts"]
        payload = {**town, "commandId": "replace-1", "meterId": meter, "newDeviceId": "new-device-1",
                   "workOrderId": "WO-1", "note": "Completed missing-read meter replacement."}
        first = c.post("/atlas/api/billing/replace-meter", json=payload)
        assert first.status_code == 200
        assert c.post("/atlas/api/billing/replace-meter", json=payload).json() == first.json()
        state = world.status()
        c.post("/atlas/api/advance", json={**town, "expectedThrough": state["through"]}).raise_for_status()
        c.post("/atlas/api/billing/ingest", json=town).raise_for_status()
        c.post("/atlas/api/billing/run", json={**town, "start": "2026-01-04", "end": "2026-01-05"}).raise_for_status()
        final = c.get("/atlas/api/billing", params={"premise": premise}).json()
        assert any(d["status"] == "issued" and d["meterId"] == meter and d["start"] == "2026-01-04" for d in final["documents"])
        assert any(d["status"] == "blocked" and d["meterId"] == meter and d["start"] == "2026-01-03" for d in final["documents"])
        assert any(r["device"] == "new-device-1" and r["quantity"] is not None for r in final["reads"])
        assert "9999999" not in json.dumps(final)


def test_identity_auth_and_invalid_periods_cannot_bill(world, snapshot, monkeypatch):
    monkeypatch.setenv("ATLAS_API_TOKEN", "test-secret")
    with client(world) as c:
        assert c.get("/atlas/api/billing").status_code == 401
        headers = {"Authorization": "Bearer test-secret"}
        assert c.post("/atlas/api/billing/ingest", json={"townId": "wrong"}, headers=headers).status_code == 409
        for start, end in [("2026-01-01", "2027-01-03"), ("2026-01-03", "2026-01-02"), ("2026-01-01", "2026-01-09")]:
            assert c.post("/atlas/api/billing/run", json={"townId": snapshot["id"], "start": start, "end": end}, headers=headers).status_code == 409
    assert not Path(world.path).with_name("billing.sqlite").exists()


def test_library_unknown_selection_cannot_create_world(tmp_path):
    with TestClient(server.create_library_app(tmp_path), base_url="http://127.0.0.1") as c:
        assert c.get("/atlas/api/catalog").status_code == 200
        assert c.get("/atlas/api/state?town=../../elsewhere").status_code == 400
        assert c.get("/").status_code == 200
    assert not list(tmp_path.rglob("*.sqlite"))


def test_full_source_binding_rejects_metadata_only_change(world, snapshot):
    from source_binding import fingerprint, require_binding
    before = world.status()
    require_binding(world, fingerprint(snapshot))
    changed = json.loads(json.dumps(snapshot))
    changed["premises"][0]["hasPool"] = not changed["premises"][0].get("hasPool", False)
    # Geometry is identical, so a geometry/SVG-only checksum cannot catch this.
    assert changed["parcels"] == snapshot["parcels"]
    with pytest.raises(ValueError, match="authoritative town source changed"):
        require_binding(world, fingerprint(changed))
    assert world.status() == before
    require_binding(World(world.path), fingerprint(snapshot))


def test_library_rejects_untrusted_origin_before_world_initialization(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(server, "prepare_world", lambda *a, **k: calls.append(k))
    with TestClient(server.create_library_app(tmp_path), base_url="http://127.0.0.1") as c:
        assert c.get("/atlas/api/summary?town=ashtown-5000", headers={"Origin": "https://untrusted.example", "Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert c.post("/atlas/api/billing/ingest?town=ashtown-5000", content="{}").status_code == 415
    assert calls == []


def test_library_explicit_hosted_origin_preflight_and_token(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_ALLOWED_ORIGINS", "https://utilitysim.example")
    monkeypatch.setenv("ATLAS_API_TOKEN", "test-secret")
    with TestClient(server.create_library_app(tmp_path), base_url="http://127.0.0.1") as c:
        preflight = c.options("/atlas/api/catalog", headers={"Origin": "https://utilitysim.example",
                             "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "https://utilitysim.example"
        assert c.get("/atlas/api/catalog", headers={"Origin": "https://utilitysim.example"}).status_code == 401
        response = c.get("/atlas/api/catalog", headers={"Origin": "https://utilitysim.example", "Authorization": "Bearer test-secret"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://utilitysim.example"
