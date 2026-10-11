"""Authenticated, assignment-bound Virtual Systems water field work.

The caller owns the town's mutation lock and imports its configured private VS
installation. This helper does not generate faults or auto-accept field reports.
Every command has an independent saved field owner and authenticated delivery run;
it is a local supervisor workflow, not the shared physical scheduler.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path


def _write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def repair(world, billing, base_directory, installation_id, reason, command_id):
    from synth_runtime import Run
    from synth_runtime.store import digest
    from vscontracts import clock
    from vscontracts.runtime_clock import RuntimeClock
    from worldfield.recipient import TARGET, FieldRecipient, RuntimeFieldRelay

    from utilsim.world import field_execution as field

    if not all(
        isinstance(value, str) and value.strip() and len(value) <= 512
        for value in (installation_id, reason, command_id)
    ):
        raise ValueError("Provide installation, reason and a stable command ID (1–512 characters).")
    identity = hashlib.sha256(command_id.encode()).hexdigest()[:32]
    directory = Path(base_directory) / "field" / identity
    directory.mkdir(parents=True, exist_ok=True)
    intent = {"installationId": installation_id, "reason": reason, "commandId": command_id}
    intent_path = directory / "intent.json"
    if intent_path.exists():
        if json.loads(intent_path.read_text(encoding="utf-8")) != intent:
            raise ValueError("This field command ID was already used with different details.")
    else:
        _write(intent_path, intent)
    with world.read_db() as db:
        meta = world.metadata(db)
        asset = db.execute(
            "SELECT * FROM assets WHERE installation=? AND commodity='water'", (installation_id,)
        ).fetchone()
        if asset is None:
            raise ValueError("A commissioned water installation is required for this field operation.")
        asset = dict(asset)
    if billing.instance_id != meta["environment"]:
        raise ValueError("Billing and physical world environments differ.")
    with billing.db() as db:
        installation = db.execute(
            "SELECT premise_id,commodity,meter_id FROM installations WHERE id=?", (installation_id,)
        ).fetchone()
        if (
            not installation
            or installation["commodity"] != "water"
            or installation["premise_id"] != asset["premise"]
            or installation["meter_id"] != asset["id"]
        ):
            raise ValueError("The recipient installation does not match the physical water asset.")
        # A causal reference recovers the committed order even if its reply was lost.
        causal = "atlas-field-" + identity
        rows = db.execute(
            "SELECT id,causal_refs FROM investigation_orders WHERE installation_id=?", (installation_id,)
        ).fetchall()
        orders = [row["id"] for row in rows if causal in json.loads(row["causal_refs"])]
    if len(orders) > 1:
        raise ValueError("Duplicate investigation binding requires review.")
    timer = clock.install(
        RuntimeClock(datetime.fromisoformat(meta["through"] + "T12:00:00+00:00"), "America/New_York")
    )
    try:
        order = (
            billing.investigation(orders[0])
            if orders
            else billing.create_investigation(
                {
                    "kind": "supply_check",
                    "source_kind": "installations",
                    "source_id": installation_id,
                    "reason": reason,
                    "causal_refs": [causal],
                }
            )
        )
        execution = field.FieldExecution(world, directory / "field.sqlite", owner_id=causal)
        assignment = "assignment-" + identity
        crew = "plumbing-" + identity

        def command(suffix, action, **extra):
            key = causal + "-" + suffix
            with execution.db() as db:
                old = db.execute("SELECT payload FROM commands WHERE id=?", (key,)).fetchone()
                current = execution.metadata(db)
            payload = (
                json.loads(old[0])
                if old
                else {
                    "schemaVersion": field.VERSION,
                    "commandId": key,
                    "environmentId": meta["environment"],
                    "worldFingerprint": meta["fingerprint"],
                    "effectiveDate": current["through"],
                    "actorId": "world-admin",
                    "action": action,
                    "causalReference": order["id"],
                    **extra,
                }
            )
            return field.command(execution, payload)

        command(
            "crew",
            "configure-crew",
            crewId=crew,
            expectedRevision=0,
            skills=["plumbing"],
            weekdays=list(range(7)),
            dailyCapacity=1,
        )
        command(
            "assignment",
            "accept",
            assignmentId=assignment,
            crewId=crew,
            assetId=asset["id"],
            orderId=order["id"],
            orderRevision=1,
            scheduledDate=meta["through"],
            operation="repair-water-leak",
            reportDelayDays=0,
        )
        with execution.db() as db:
            accepted = db.execute(
                "SELECT checksum FROM field_assignments WHERE id=?", (assignment,)
            ).fetchone()
            ack = json.loads(
                db.execute(
                    "SELECT envelope FROM field_outbox WHERE assignment=? AND "
                    "json_extract(envelope,'$.schema')='field-ack/1'",
                    (assignment,),
                ).fetchone()[0]
            )
        config = {
            "version": "1",
            "environmentId": meta["environment"],
            "worldFingerprint": meta["fingerprint"],
            "fieldOwnerId": execution.owner_id,
            "producerActorId": "atlas-field-producer",
            "bindings": {
                assignment: {
                    "assignmentChecksum": accepted["checksum"],
                    "orderId": order["id"],
                    "orderRevision": 1,
                    "installationId": installation_id,
                    "assetId": asset["id"],
                    "crewId": crew,
                    "operation": "repair-water-leak",
                    "ackId": ack["id"],
                    "ackChecksum": digest(ack),
                    "plannedDate": ack["business_time"],
                }
            },
        }
        run = Run(directory / "runtime.sqlite")
        run.initialize(
            {
                "schemaVersion": "synth-run/1.0",
                "runId": meta["environment"],
                "seed": identity,
                "start": ack["business_time"] + "T12:00:00Z",
                "timezone": "America/New_York",
                "models": {"runtime": "1.0"},
                "configuration": {"fieldRecipientAdapter": config},
                "snapshotHash": meta["fingerprint"],
            }
        )
        credentials_path = directory / "credentials.json"
        credentials = json.loads(credentials_path.read_text()) if credentials_path.exists() else {}
        for key, actor, role, grants in [
            ("admin", "atlas-field-admin", "admin", []),
            ("producer", "atlas-field-producer", "system", [TARGET + ":acknowledge", TARGET + ":report"]),
        ]:
            if key not in credentials:
                credentials[key] = run.provision_actor(actor, role, grants)
                _write(credentials_path, credentials)
        handler = FieldRecipient(billing, run)
        relay = RuntimeFieldRelay(run, credentials["producer"], execution)
        field.run_due(execution)
        through = meta["through"] + "T12:00:00Z"
        # Receipt loss is recovered by resubmitting the same immutable messages.
        for _ in range(3):
            field.relay(execution, relay)
            with run.db() as db:
                failed = [row[0] for row in db.execute("SELECT id FROM jobs WHERE status='failed'")]
            for job in failed:
                run.retry(credentials["admin"], job)
            run.control(credentials["admin"], "resume")
            result = run.advance(credentials["admin"], through, {TARGET: handler})
            if result["status"] == "paused":
                raise ValueError(
                    "Authenticated field delivery paused; retry the same command after resolving its cause."
                )
        field.relay(execution, relay)
        with execution.db() as db:
            physical = json.loads(
                db.execute("SELECT result FROM field_assignments WHERE id=?", (assignment,)).fetchone()[0]
            )
            pending = db.execute("SELECT COUNT(*) FROM field_outbox WHERE state!='received'").fetchone()[0]
        actual = billing.investigation(order["id"])
        return {
            "order": actual,
            "physical": physical,
            "assignmentId": assignment,
            "pendingTransport": pending,
            "schedulerManaged": False,
            "authenticatedDelivery": True,
            "reportDelayDays": 0,
        }
    finally:
        clock.uninstall(timer)


def accept_report(world, billing, order_id, note):
    """Separate clerk decision; never executed as part of physical repair."""
    from vscontracts import clock
    from vscontracts.runtime_clock import RuntimeClock

    if not isinstance(note, str) or not note.strip():
        raise ValueError("Record the reason for accepting this report.")
    with world.read_db() as db:
        meta = world.metadata(db)
    timer = clock.install(
        RuntimeClock(datetime.fromisoformat(meta["through"] + "T12:00:00+00:00"), "America/New_York")
    )
    try:
        current = billing.investigation(order_id)
        if current["status"] == "accepted":
            return current
        billing.accept_field_report(order_id, {"note": note})
        return billing.investigation(order_id)
    finally:
        clock.uninstall(timer)
