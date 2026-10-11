"""Disposable real owner API/snapshot drill; does not prove Linux/Docker restore.

Requires authorized private VS checkout plus producer dependencies on PYTHONPATH.
No existing run or deployment is opened. Private source and credentials are never
copied into this public repository or report.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import owners
import recovery
import stack


def restore_disposable(base, sources, originals):
    """Retain originals, then restore only this drill's previously verified trees."""
    base = Path(base).resolve(strict=True)
    pairs = list(zip(sources, originals, strict=True))
    retained = base / "retained-originals"
    stack.require(not retained.exists(), "Disposable retention destination must be new.")
    resolved = []
    for source, original in pairs:
        paths = [Path(source), Path(original)]
        for path in paths:
            actual = path.resolve(strict=True)
            stack.require(actual.is_relative_to(base) and actual != base and path.absolute() == actual
                          and path.is_dir() and not path.is_symlink(), "Restore paths must stay inside the created temporary workspace.")
            stack.require(all(not p.is_symlink() and p.resolve().is_relative_to(base) for p in path.rglob("*")),
                          "Disposable restore refuses links.")
        resolved.extend(paths)
    stack.require(all(a != b and not a.is_relative_to(b) and not b.is_relative_to(a)
                      for i, a in enumerate(resolved) for b in resolved[i + 1:]), "Restore trees must be disjoint.")
    # All targets are checked before the first move. No deletion is needed.
    retained.mkdir()
    for index, (source, original) in enumerate(pairs):
        Path(original).rename(retained / str(index))
        shutil.copytree(source, original)
        stack.require(recovery.files(source) == recovery.files(original), "Restored tree differs from verified archive.")


def wait_command(port, token, command_id):
    for _ in range(500):
        state = owners.request(port, "/connected", token)
        last = state.get("lastCommand") or {}
        stack.require(last.get("status") != "failed", "Actual control command failed.")
        if state.get("activeCommandId") is None and last.get("commandId") == command_id and last.get("status") == "completed":
            return state
        time.sleep(0.02)
    raise RuntimeError("Actual control command did not complete.")


def durable_state(directory):
    with owners.readonly(directory / "runtime.sqlite") as db:
        jobs = [tuple(row) for row in db.execute("SELECT id,fingerprint,status FROM jobs WHERE target IN ('world','isu') ORDER BY id")]
        cursors = [tuple(row) for row in db.execute("SELECT type,subject,payload FROM journal WHERE type IN ('ConnectedProducerCheckpoint','ConnectedBillingCheckpoint') ORDER BY sequence")]
    return jobs, cursors


def drill(utilsim, virtual_systems):
    # Reuse the producer's tiny immutable test-map fixture, never Ashtown or an
    # accepted map/run. No synthetic HTTP status/receipt implementation is used.
    sys.path[:0] = [str(virtual_systems), str(utilsim), str(utilsim / "tests")]
    commits = {label: subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
               for label, root in (("producer", utilsim), ("privateVs", virtual_systems))}
    import uvicorn
    from billing.store import Billing
    from connected.remote import RemoteWorld
    from connected.runtime import backup_ready, open_connected
    from connected.service import ControlService, make_server
    from customerflow.evidence import Evidence
    from fastapi.testclient import TestClient
    from receivables.store import Subledger
    from synth_runtime import Run
    from test_hosted_worlds import TOKEN, headers, setup

    from utilsim.hosted.health import probe
    from utilsim.hosted.server import create_app

    with tempfile.TemporaryDirectory(prefix="owner-api-drill-") as temporary:
        base = Path(temporary)
        producer_root, _template, creation, _snapshot = setup.__wrapped__(base)
        controller_id = "utilitysim-controller"
        machine_key = secrets.token_urlsafe(48)
        app = create_app(producer_root, TOKEN, machine_key, controller_id)
        with TestClient(app) as client:
            stack.require(client.get("/hosted/health").status_code == 401,
                          "Actual producer health must reject unauthenticated access.")
            created = client.post("/hosted/worlds", json=creation, headers=headers())
            stack.require(created.status_code == 200, "Disposable producer world creation failed.")
            world = created.json()
            connection = client.post(f"/hosted/worlds/{world['id']}/connection", headers=headers(),
                json={"commandId": str(uuid.uuid4()), "expectedRevision": 0,
                      "controllerId": controller_id, "sewerReturnFactor": "0.9", "delaySeconds": 21600})
            stack.require(connection.status_code == 200, "Disposable fixed-world connection failed.")
            binding = connection.json()
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            producer_port = sock.getsockname()[1]
        producer_server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=producer_port,
                                                       log_level="critical", access_log=False))
        producer_thread = threading.Thread(target=producer_server.run, daemon=True)
        producer_thread.start()
        for _ in range(100):
            if producer_server.started:
                break
            time.sleep(0.02)
        stack.require(producer_server.started, "Actual producer HTTP server did not start.")
        try:
            directory = base / "controller"
            directory.mkdir()
            run_id, fingerprint = binding["environmentId"], binding["fingerprint"]
            port = RemoteWorld(f"http://127.0.0.1:{producer_port}", world["id"], binding["token"], run_id,
                               fingerprint, controller_id, allow_loopback=True)
            days = list(port.commands("2026-07-17"))
            first_day = {**days[0], "processingAt": "2026-07-16T00:00:00Z"}
            port.advance(first_day)
            batch = port.feed("observations")["items"][0]["envelope"]["payload"]["batch"]
            bindings = {asset["servicePointId"]: "ISOLATED-" + asset["installationId"] for asset in batch["assets"]}
            customer = {"version": "1", "environmentId": run_id, "worldFingerprint": fingerprint,
                        "producerActorId": "customer-producer", "bindings": {"isolated-account": {
                            "premiseId": _snapshot["premises"][0]["id"], "recipientRef": "isolated-recipient"}},
                        "deliveryDelayDays": 0, "settlementDelayDays": 1}
            manifest = {"schemaVersion": "synth-run/1.0", "runId": run_id, "seed": "isolated-hook-drill",
                        "start": "2026-07-15T00:00:00Z", "timezone": "UTC", "models": {"runtime": "1.0"},
                        "configuration": {"connectedController": {"version": "1", "actorId": controller_id,
                            "worldFingerprint": fingerprint}, "billingObservationAdapter": {"version": "1", "bindings": bindings},
                            "customerRecipientAdapter": customer}, "snapshotHash": "isolated-test-map"}
            run = Run(directory / "runtime.sqlite")
            run.initialize(manifest)
            credentials = {"controller": run.provision_actor(controller_id, "admin", []),
                "producer": run.provision_actor("world-observations", "system", ["isu:ingest_v2"]),
                "customerProducer": run.provision_actor("customer-producer", "operator", ["customer-flow:" + name
                    for name in ("deliver-invoice", "learn-invoice", "settle-payment", "confirm-payment", "post-payment")])}
            (directory / "credentials.json").write_text(json.dumps(credentials))
            billing = Billing(directory / "billing.sqlite", run_id)
            for premise in _snapshot["premises"]:
                billing.create("premises", {"id": premise["id"], "address_line1": premise["address"]})
            for asset in sorted(batch["assets"], key=lambda a: a["commodity"] == "sewer"):
                installation = {"id": bindings[asset["servicePointId"]], "commodity": asset["commodity"], "premise_id": asset["premiseId"]}
                if asset["commodity"] == "sewer":
                    installation.update(source_installation_id=bindings[asset["sourceServicePointId"]], derivation_factor=asset["derivation"]["factor"])
                else:
                    installation["meter_id"] = asset["meterId"]
                billing.create("installations", installation)
            billing.store.close()
            ledger = Subledger(directory / "ledger.sqlite", run_id)
            ledger.store.close()
            Evidence(directory / "evidence.sqlite", {"runId": run_id, "configuration": customer})
            (directory / "world.token").write_text(binding["token"])
            remote = directory / "remote-world.json"
            remote.write_text(json.dumps({"origin": f"http://127.0.0.1:{producer_port}", "worldId": world["id"],
                                         "tokenFile": "world.token", "allowLoopback": True}))
            cfg = copy.deepcopy(stack.read_json(stack.HERE / "deployment.example.json"))
            cfg.update(runId=run_id, dataRoot=str(base), volumeId="bc28a5b8-92c1-4d62-a397-45ca74c528e1")
            cfg["ownerCli"].update(directory=str(directory), remoteConfig=str(remote), controllerId=controller_id, worldId=world["id"])
            for name in ("runtime", "billing", "ledger", "evidence", "controller"):
                cfg["ownerFiles"][name]["path"] = "control.sqlite" if name == "controller" else name + ".sqlite"
            cfg["ownerFiles"]["world"]["path"] = str(Path(app.state.library.library.world(world["id"]).path).relative_to(producer_root)).replace("\\", "/")
            cfg["ownerFiles"]["producerField"]["path"] = str(Path(cfg["ownerFiles"]["world"]["path"]).parent / "machine-field.sqlite").replace("\\", "/")
            with patch.dict(os.environ, {"UTILITYSIM_RUNTIME_TOKEN": TOKEN}):
                stack.require(probe(f"http://127.0.0.1:{producer_port}", TOKEN)["status"] == "ready",
                              "Actual producer owner's packaged health probe failed.")
                stack.require(owners.producer_health(cfg, root=producer_root, port=producer_port)["ready"] is True,
                              "Actual producer authenticated health/binding failed.")
            service_token = secrets.token_urlsafe(48)
            with open_connected(directory, remote_config=remote) as composition:
                service = ControlService(composition.controller, directory / "control.sqlite", service_token)
                server = make_server(service, port=0)
                cfg["ownerCli"]["port"] = server.server_port
                service.start()
                controller_thread = threading.Thread(target=server.serve_forever, daemon=True)
                controller_thread.start()
                try:
                    try:
                        backup_ready(directory, workers_stopped=True, remote_config=remote)
                    except RuntimeError:
                        live_refused = True
                    else:
                        raise RuntimeError("Live controller was incorrectly accepted for backup.")
                    receipt = owners.request(server.server_port, "/connected/commands", service_token,
                        {"commandId": "isolated-resume", "expectedRevision": 0, "action": "resume"}, pins=(run_id, controller_id))
                    stack.require(receipt["revision"] == 1, "Resume receipt mismatch.")
                    wait_command(server.server_port, service_token, "isolated-resume")
                    composition.controller.poll()
                    for day in days:
                        run.enqueue(credentials["controller"], day)
                    owners.request(server.server_port, "/connected/commands", service_token,
                                   {"commandId": "initial-advance", "expectedRevision": 1, "action": "advance",
                                    "through": "2026-07-16T00:00:00Z"}, pins=(run_id, controller_id))
                    wait_command(server.server_port, service_token, "initial-advance")
                    with patch.dict(os.environ, {"CONNECTED_SERVICE_TOKEN": service_token,
                                                 "CONNECTED_CLOCK_TOKEN": credentials["controller"]}):
                        stack.require(owners.health(cfg)["ready"] is True, "Actual authenticated CLI readiness failed.")
                        pause = owners.pause(cfg)
                    jobs_before, cursors_before = durable_state(directory)
                    pending_before = [row for row in jobs_before if row[2] == "pending"]
                    stack.require(len(pending_before) == 2
                                  and cursors_before, "Drill needs genuine pending day/read IDs and cursors.")
                    stack.require("workersStopped" not in pause, "Pause alone must not claim stopped workers.")
                finally:
                    server.shutdown()
                    server.server_close()
                    controller_thread.join(timeout=2)
                    service.stop()
                    composition.controller.close_thread()
            ready = owners.controller_ready(cfg, data_root=directory, producer_origin=f"http://127.0.0.1:{producer_port}")
            stack.require(ready["clock"] == pause["clock"] and ready["controllerRevision"] == pause["controllerRevision"] == 3,
                          "Stopped owner clock/revision mismatch.")
        finally:
            producer_server.should_exit = True
            producer_thread.join(timeout=10)
        stack.require(not producer_thread.is_alive(), "Producer writer has not stopped.")
        stack.require(not controller_thread.is_alive(), "Controller HTTP writer has not stopped.")
        stage = base / "snapshot"
        stage.mkdir()
        owners.copy_tree(directory, stage / "data/controller")
        owners.producer_snapshot(cfg, stage / "producer-snapshot", root=producer_root)
        (stage / "producer-snapshot/data").rename(stage / "data/producer")
        physical = owners.producer_binding(cfg, stage / "data/producer", ready, original_root=producer_root)
        proof = {**ready, **physical, "paused": True, "idle": True,
                 "workersStopped": True, "complete": True, "owners": sorted(cfg["ownerFiles"])}
        marker = {"schemaVersion": stack.SCHEMA, "runId": run_id, "volumeId": cfg["volumeId"]}
        (stage / "data" / stack.MARKER).write_text(json.dumps(marker))
        record = recovery.manifest(cfg, proof, stage / "data")
        (stage / "manifest.json").write_text(json.dumps(record))
        with tarfile.open(stage / "owners.tar", "w") as archive:
            archive.add(stage / "manifest.json", arcname="manifest.json")
            archive.add(stage / "data", arcname="data")
        restored = base / "verified-unpack"
        restored.mkdir()
        recovery.unpack_verified(stage / "owners.tar", restored, cfg)
        with closing(sqlite3.connect(restored / "data/controller/control.sqlite")) as db:
            stack.require(db.execute("SELECT revision FROM binding").fetchone() == (3,), "Unpacked control revision changed.")
        restore_disposable(base, [restored / "data/producer", restored / "data/controller"], [producer_root, directory])
        stack.require(durable_state(directory) == (jobs_before, cursors_before), "Original pending IDs/fingerprints/cursors changed on restore.")
        reopened_app = create_app(producer_root, TOKEN, machine_key, controller_id)
        producer_server = uvicorn.Server(uvicorn.Config(reopened_app, host="127.0.0.1", port=producer_port,
                                                       log_level="critical", access_log=False))
        producer_thread = threading.Thread(target=producer_server.run, daemon=True)
        producer_thread.start()
        for _ in range(100):
            if producer_server.started:
                break
            time.sleep(0.02)
        stack.require(producer_server.started, "Restored producer did not reopen.")
        try:
            with patch.dict(os.environ, {"UTILITYSIM_RUNTIME_TOKEN": TOKEN}):
                owners.producer_health(cfg, root=producer_root, port=producer_port)
            with open_connected(directory, remote_config=remote) as composition:
                service = ControlService(composition.controller, directory / "control.sqlite", service_token)
                server = make_server(service, port=cfg["ownerCli"]["port"])
                service.start()
                controller_thread = threading.Thread(target=server.serve_forever, daemon=True)
                controller_thread.start()
                try:
                    initial = owners.request(server.server_port, "/connected", service_token)
                    stack.require(initial["phase"] == "paused" and initial["revision"] == 3
                                  and initial["clock"] == ready["clock"] and initial["runId"] == run_id
                                  and durable_state(directory) == (jobs_before, cursors_before), "Actual reopened service changed the saved boundary.")
                    composition.controller.check_identity()
                    owners.request(server.server_port, "/connected/commands", service_token,
                                   {"commandId": "restored-resume", "expectedRevision": 3, "action": "resume"}, pins=(run_id, controller_id))
                    wait_command(server.server_port, service_token, "restored-resume")
                    advance = {"commandId": "restored-advance", "expectedRevision": 4, "action": "advance", "through": "2026-07-17T06:00:00Z"}
                    receipt = owners.request(server.server_port, "/connected/commands", service_token, advance, pins=(run_id, controller_id))
                    final = wait_command(server.server_port, service_token, advance["commandId"])
                    stack.require(final["clock"] == advance["through"] and final["counts"]["failed"] == 0, "Restored advance did not reach the shared clock.")
                    with owners.readonly(directory / "billing.sqlite") as db:
                        reads = [tuple(row) for row in db.execute("SELECT id,source_id FROM reads ORDER BY id")]
                    stack.require(len(reads) == 8 and len({row[1] for row in reads}) == 8, "Expected eight unique actual commodity readings.")
                    completed, final_cursors = durable_state(directory)
                    stack.require(any(row[0] == "ConnectedProducerCheckpoint" and row[1] == "observations"
                                      and json.loads(row[2])["after"] == 2 for row in final_cursors),
                                  "Restored producer cursor did not advance through both days.")
                    stack.require(all((row[0], row[1], "completed") in completed for row in pending_before), "Original pending jobs were not completed with the same fingerprints.")
                    stack.require(owners.request(server.server_port, "/connected/commands", service_token, advance, pins=(run_id, controller_id)) == receipt,
                                  "Exact control retry changed its receipt.")
                    replay_state = owners.request(server.server_port, "/connected", service_token)
                    stack.require(replay_state["revision"] == final["revision"] and replay_state["clock"] == final["clock"]
                                  and durable_state(directory) == (completed, final_cursors), "Exact control retry changed durable progress.")
                    port.advance(first_day)
                    with owners.readonly(directory / "billing.sqlite") as db:
                        stack.require(reads == [tuple(row) for row in db.execute("SELECT id,source_id FROM reads ORDER BY id")], "Retry duplicated readings.")
                    with owners.readonly(producer_root / cfg["ownerFiles"]["world"]["path"]) as db:
                        machine_days = [row[0] for row in db.execute("SELECT id FROM machine_days ORDER BY id")]
                        actual_days = db.execute("SELECT COUNT(*) FROM days").fetchone()[0]
                    stack.require(actual_days == 2 and set(machine_days) == {day["id"] for day in days}, "Retry duplicated physical days or changed original IDs.")
                    with patch.dict(os.environ, {"CONNECTED_SERVICE_TOKEN": service_token, "CONNECTED_CLOCK_TOKEN": credentials["controller"]}):
                        owners.pause(cfg)
                finally:
                    server.shutdown()
                    server.server_close()
                    controller_thread.join(timeout=2)
                    service.stop()
                    composition.controller.close_thread()
        finally:
            producer_server.should_exit = True
            producer_thread.join(timeout=10)
        stack.require(not producer_thread.is_alive() and not controller_thread.is_alive(), "Restored writers must stop.")
        return {"schemaVersion": "connected-owner-interface-drill/1", "result": "passed-local-original-path-restore",
                "liveWorkerBackupRefused": live_refused, "executedPauseAndReleasedLease": True,
                "stoppedVsInventory": True, "actualProducerBackup": True,
                "producerVsIdentityReconciled": True, "combinedArchiveVerifiedUnpack": True,
                "producerAuthenticatedHealthAndOriginalBinding": True,
                "controlRevision": 3, "ownerFiles": len(cfg["ownerFiles"]), "pendingOriginalJobs": len(pending_before),
                "authenticatedResumeAndExactReplay": True, "physicalDays": actual_days, "uniqueBillingReads": len(reads),
                "testedSourceCommits": commits,
                "sourceFileSha256": {"producer/" + name: recovery.digest(utilsim / name) for name in (
                    "utilsim/hosted/backup.py", "utilsim/hosted/server.py", "utilsim/hosted/machine.py",
                    "utilsim/hosted/machine_routes.py", "utilsim/hosted/health.py")} |
                    {"private-vs/" + name: recovery.digest(virtual_systems / name) for name in (
                        "connected/__main__.py", "connected/runtime.py", "connected/service.py", "connected/controller.py", "connected/remote.py")},
                "linuxDockerBoot": False, "ageEncryption": False, "originalPathApplicationRestore": True,
                "linuxOriginalPathApplicationRestore": False,
                "managedRemoteField": False, "productionDeployed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--utilsim", type=Path, required=True)
    parser.add_argument("--virtual-systems", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = drill(args.utilsim.resolve(), args.virtual_systems.resolve())
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, ImportError):
        print("Refused: isolated owner interface drill failed; no existing deployment was changed.", file=sys.stderr)
        raise SystemExit(2) from None
