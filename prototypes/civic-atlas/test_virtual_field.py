"""Real optional VS field integration, including negative and retry controls."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from virtual_field import accept_report, repair
from virtual_systems import VirtualSystems, configured

from utilsim.config import load_preset
from utilsim.gen.pipeline import generate
from utilsim.io.snapshot import build_snapshot
from utilsim.world import water_faults
from utilsim.world.store import World


@pytest.mark.skipif(not configured(), reason="Requires separately configured private Virtual Systems")
def test_real_field_repair_receipt_retry_and_clerk_decision(tmp_path, monkeypatch):
    # Reproduce the real nested town path where a migration backup exceeds 260
    # characters while the field database itself remains an ordinary valid path.
    tmp_path = tmp_path / ("nested-" + "a" * max(1, 140 - len(str(tmp_path))))
    tmp_path.mkdir()
    snapshot = build_snapshot(
        generate(load_preset("village", houses=20, seed="FIELD-PROOF")), embed_state=False
    )
    world = World(tmp_path / "world.sqlite")
    world.initialize(snapshot, "ATLAS-FIELD-PROOF")
    world.advance("2026-01-03")
    adapter = VirtualSystems(world, snapshot)
    adapter.initialize()
    with world.read_db() as db:
        meta = world.metadata(db)
        asset = dict(
            db.execute(
                "SELECT * FROM assets WHERE commodity='water' AND installed<=? LIMIT 1", (meta["through"],)
            ).fetchone()
        )
    # Fault injection belongs only to this disposable acceptance fixture.
    water_faults.command(
        world,
        {
            "schemaVersion": water_faults.VERSION,
            "commandId": "qa-leak",
            "environmentId": meta["environment"],
            "worldFingerprint": meta["fingerprint"],
            "actorId": "world-admin",
            "expectedRevision": 0,
            "action": "start",
            "reason": "QA fixture",
            "causalReference": "qa-field",
            "assetId": asset["id"],
            "leakM3PerHour": "0.1",
        },
    )
    history = world.export_v2("2026-01-01", "2026-01-03")
    with adapter.session() as (billing, _ledger, _meta):
        receive = billing.receive_field_report

        def lose_committed_reply(envelope):
            receive(envelope)
            raise OSError("Disposable QA lost reply after recipient commit")

        with monkeypatch.context() as patch:
            patch.setattr(billing, "receive_field_report", lose_committed_reply)
            with pytest.raises(ValueError, match="delivery paused"):
                repair(
                    world,
                    billing,
                    adapter.directory,
                    asset["installation"],
                    "Investigate water concern",
                    "qa-1",
                )
        first = repair(
            world, billing, adapter.directory, asset["installation"], "Investigate water concern", "qa-1"
        )
        assert first["order"]["status"] == "reported"
        assert first["order"]["reports"][0]["status"] == "pending"
        assert first["order"]["reports"][0]["outcome"] == "completed"
        assert first["authenticatedDelivery"] and first["pendingTransport"] == 0
        assert not water_faults.inspect(world, asset["id"])["current"]["active"]
        again = repair(
            world, billing, adapter.directory, asset["installation"], "Investigate water concern", "qa-1"
        )
        assert again == first
        with pytest.raises(ValueError, match="different details"):
            repair(world, billing, adapter.directory, asset["installation"], "Changed reason", "qa-1")
        accepted = accept_report(world, billing, first["order"]["id"], "Reviewed actual crew findings")
        assert accepted["status"] == "accepted"
        assert accept_report(world, billing, first["order"]["id"], "Retry") == accepted
        assert (
            repair(
                world, billing, adapter.directory, asset["installation"], "Investigate water concern", "qa-1"
            )["order"]["status"]
            == "accepted"
        )
        no_fault = repair(
            world, billing, adapter.directory, asset["installation"], "Check service again", "qa-2"
        )
        assert no_fault["order"]["reports"][0]["outcome"] == "not_found"
        assert no_fault["order"]["status"] == "reported"
        with billing.db() as db:
            assert db.execute("SELECT COUNT(*) FROM field_reports").fetchone()[0] == 2
    with world.read_db() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM events WHERE type='PhysicalWaterLeakRepaired'").fetchone()[0]
            == 1
        )
    assert world.export_v2("2026-01-01", "2026-01-03") == history
