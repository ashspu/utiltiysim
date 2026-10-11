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
import sqlite3
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


def drill(utilsim, virtual_systems):
    # Reuse the producer's tiny immutable test-map fixture, never Ashtown or an
    # accepted map/run. No synthetic HTTP status/receipt implementation is used.
    sys.path[:0] = [str(virtual_systems), str(utilsim), str(utilsim / "tests")]
    import uvicorn
    from billing.store import Billing
    from connected.runtime import backup_ready, open_connected
    from connected.service import ControlService, make_server
    from customerflow.evidence import Evidence
    from fastapi.testclient import TestClient
    from receivables.store import Subledger
    from synth_runtime import Run
    from test_hosted_worlds import TOKEN, headers, setup

    from utilsim.hosted.server import create_app

    with tempfile.TemporaryDirectory(prefix="owner-api-drill-") as temporary:
        base = Path(temporary)
        producer_root, _template, creation, _snapshot = setup.__wrapped__(base)
        controller_id = "utilitysim-controller"
        app = create_app(producer_root, TOKEN, secrets.token_urlsafe(48), controller_id)
        with TestClient(app) as client:
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
            customer = {"version": "1", "environmentId": run_id, "worldFingerprint": fingerprint,
                        "producerActorId": "customer-producer", "bindings": {"isolated-account": {
                            "premiseId": _snapshot["premises"][0]["id"], "recipientRef": "isolated-recipient"}},
                        "deliveryDelayDays": 0, "settlementDelayDays": 1}
            manifest = {"schemaVersion": "synth-run/1.0", "runId": run_id, "seed": "isolated-hook-drill",
                        "start": "2026-07-15T00:00:00Z", "timezone": "UTC", "models": {"runtime": "1.0"},
                        "configuration": {"connectedController": {"version": "1", "actorId": controller_id,
                            "worldFingerprint": fingerprint}, "billingObservationAdapter": {"version": "1", "bindings": {}},
                            "customerRecipientAdapter": customer}, "snapshotHash": "isolated-test-map"}
            run = Run(directory / "runtime.sqlite")
            run.initialize(manifest)
            credentials = {"controller": run.provision_actor(controller_id, "admin", []),
                "producer": run.provision_actor("world-observations", "system", ["isu:ingest_v2"]),
                "customerProducer": run.provision_actor("customer-producer", "operator", ["customer-flow:" + name
                    for name in ("deliver-invoice", "learn-invoice", "settle-payment", "confirm-payment", "post-payment")])}
            (directory / "credentials.json").write_text(json.dumps(credentials))
            billing = Billing(directory / "billing.sqlite", run_id)
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
                        {"commandId": "isolated-resume", "expectedRevision": 0, "action": "resume"})
                    stack.require(receipt["revision"] == 1, "Resume receipt mismatch.")
                    for _ in range(100):
                        state = owners.request(server.server_port, "/connected", service_token)
                        if state.get("activeCommandId") is None:
                            break
                        time.sleep(0.02)
                    with patch.dict(os.environ, {"CONNECTED_SERVICE_TOKEN": service_token,
                                                 "CONNECTED_CLOCK_TOKEN": credentials["controller"]}):
                        stack.require(owners.health(cfg)["ready"] is True, "Actual authenticated CLI readiness failed.")
                        pause = owners.pause(cfg)
                    stack.require("workersStopped" not in pause, "Pause alone must not claim stopped workers.")
                finally:
                    server.shutdown()
                    server.server_close()
                    controller_thread.join(timeout=2)
                    service.stop()
            ready = owners.controller_ready(cfg, data_root=directory, producer_origin=f"http://127.0.0.1:{producer_port}")
            stack.require(ready["clock"] == pause["clock"] and ready["controllerRevision"] == pause["controllerRevision"] == 2,
                          "Stopped owner clock/revision mismatch.")
        finally:
            producer_server.should_exit = True
            producer_thread.join(timeout=10)
        stack.require(not producer_thread.is_alive(), "Producer writer has not stopped.")
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
            stack.require(db.execute("SELECT revision FROM binding").fetchone() == (2,), "Unpacked control revision changed.")
        return {"schemaVersion": "connected-owner-interface-drill/1", "result": "passed-local-api-only",
                "liveWorkerBackupRefused": live_refused, "executedPauseAndReleasedLease": True,
                "stoppedVsInventory": True, "actualProducerBackup": True,
                "producerVsIdentityReconciled": True, "combinedArchiveVerifiedUnpack": True,
                "controlRevision": 2, "ownerFiles": len(cfg["ownerFiles"]),
                "sourceFileSha256": {"producer/" + name: recovery.digest(utilsim / name) for name in (
                    "utilsim/hosted/backup.py", "utilsim/hosted/server.py", "utilsim/hosted/machine.py")} |
                    {"private-vs/" + name: recovery.digest(virtual_systems / name) for name in (
                        "connected/__main__.py", "connected/runtime.py", "connected/service.py")},
                "linuxDockerBoot": False, "ageEncryption": False, "originalPathApplicationRestore": False,
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
