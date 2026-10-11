"""Adapters to the existing VS CLI and producer backup, not new owner commands.

The host must stop and verify every writer before invoking snapshot actions.
Private VS imports happen only inside its authorized image.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from stack import Refused, read_json, require, validate_config


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def request(port, path, token, body=None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(f"http://127.0.0.1:{port}{path}", headers=headers,
                  data=None if body is None else json.dumps(body).encode())
    try:
        with build_opener(ProxyHandler({}), NoRedirects()).open(req, timeout=10) as response:
            raw = response.read(65537)
        require(len(raw) <= 65536, "Owner reply exceeded the bound.")
        return json.loads(raw)
    except (HTTPError, URLError, ValueError):
        raise Refused("Authenticated loopback owner operation failed.") from None


def identity(cfg, status):
    require(isinstance(status, dict) and status.get("runId") == cfg["runId"]
            and status.get("controllerId") == cfg["ownerCli"]["controllerId"]
            and type(status.get("revision")) is int and status["revision"] >= 0,
            "Controller reply differs from the configured fixed identity.")


@contextmanager
def service_token_file(cfg):
    with tempfile.TemporaryDirectory(prefix="connected-service-") as temporary:
        token_file = Path(temporary) / "service.token"
        token_file.write_text(os.environ[cfg["ownerCli"]["serviceTokenEnv"]], encoding="utf-8")
        os.chmod(token_file, 0o600)
        yield token_file


def health(cfg):
    from connected.__main__ import _status
    item = cfg["ownerCli"]
    with service_token_file(cfg) as token_file:
        result = _status(item["directory"], token_file, item["port"])
    identity(cfg, result)
    require(result.get("technicalError") is None, "VS cannot inspect the bound producer world.")
    return {"ready": True, "runId": result["runId"]}


def serve(cfg):
    from connected.__main__ import main as owner_main
    item = cfg["ownerCli"]
    with service_token_file(cfg) as token_file:
        return owner_main(["serve", "--directory", item["directory"], "--remote-config", item["remoteConfig"],
                           "--service-token-file", str(token_file), "--port", str(item["port"])])


def pause(cfg, timeout=90):
    # _status is the actual CLI implementation: it checks runtime/control binding
    # against the authenticated response, rather than trusting only HTTP fields.
    from connected.__main__ import _status
    item = cfg["ownerCli"]
    service_token, clock_token = (os.environ[name] for name in (item["serviceTokenEnv"], item["clockTokenEnv"]))
    require(service_token != clock_token, "Service and runtime capabilities must be separate.")
    with service_token_file(cfg) as token_file:
        def status():
            value = _status(item["directory"], token_file, item["port"])
            identity(cfg, value)
            return value
        before = status()
        command_id = "backup-pause-" + str(uuid.uuid4())
        receipt = request(item["port"], "/connected/commands", service_token,
                          {"commandId": command_id, "expectedRevision": before["revision"], "action": "pause"})
        identity(cfg, receipt)
        require(receipt.get("commandId") == command_id and receipt.get("status") == "accepted"
                and receipt["revision"] == before["revision"] + 1, "Pause receipt is not the submitted command.")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = status()
            require(current["revision"] == receipt["revision"], "A competing controller command changed the pause revision.")
            last = current.get("lastCommand") or {}
            require(current.get("phase") != "failed" and last.get("status") != "failed",
                    "The owner failed before the pause boundary.")
            clock = request(item["port"], "/api/clock", clock_token)
            require(clock.get("runId") == cfg["runId"], "Runtime clock belongs to another run.")
            if (current.get("phase") == "paused" and current.get("activeCommandId") is None
                    and last.get("commandId") == command_id and last.get("status") == "completed"
                    and last.get("acceptedRevision") == receipt["revision"]
                    and clock.get("status") == "paused" and clock.get("processing") is False
                    and current.get("clock") == clock.get("clock")):
                # Workers still exist. This result deliberately does NOT claim
                # workersStopped or a complete checkpoint until host shutdown.
                return {"runId": cfg["runId"], "clock": clock["clock"],
                        "controllerRevision": receipt["revision"], "pauseCommandId": command_id}
            time.sleep(0.1)
    raise Refused("Pause did not complete with a released runtime lease before shutdown.")


def readonly(path):
    require(Path(path).is_file(), "An existing owner database is required.")
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return closing(db)


def controller_ready(cfg, data_root="/data", producer_origin="http://127.0.0.1:8080"):
    from connected.runtime import _remote_config, backup_ready
    item = cfg["ownerCli"]
    remote, _token = _remote_config(item["remoteConfig"])
    require(remote["worldId"] == item["worldId"] and remote["origin"] == producer_origin
            and remote.get("allowLoopback") is True, "VS remote configuration differs from the fixed loopback world.")
    result = backup_ready(item["directory"], workers_stopped=True, remote_config=item["remoteConfig"])
    require(result.get("ready") is True and result.get("runId") == cfg["runId"], "VS did not confirm stopped backup readiness.")
    inventory = {("controller" if row["name"] == "control" else row["name"]): row["path"]
                 for row in result["owners"]}
    expected = {name: str(Path(data_root) / binding["path"]) for name, binding in cfg["ownerFiles"].items()
                if binding["service"] == "controller"}
    require(inventory == expected, "VS readiness inventory differs from configured original owner paths.")
    with readonly(inventory["controller"]) as db:
        binding = db.execute("SELECT controller_id,world_fingerprint,revision FROM binding WHERE id=1").fetchone()
    require(binding and binding["controller_id"] == item["controllerId"], "VS controller binding changed.")
    return {"runId": result["runId"], "clock": result["clock"],
            "controllerRevision": binding["revision"], "worldFingerprint": binding["world_fingerprint"]}


def copy_tree(source, destination):
    source, destination = Path(source), Path(destination)
    require(not destination.exists(), "Snapshot destination must be new.")
    destination.mkdir(parents=True, mode=0o700)
    for path in sorted(source.rglob("*")):
        require(not path.is_symlink(), "Owner snapshots refuse links.")
        require(path.is_file() or path.is_dir(), "Owner snapshots refuse special files.")
        if path.is_dir():
            continue
        if path.name.endswith(("-wal", "-shm", ".lock")):
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("rb") as stream:
            sqlite = stream.read(16) == b"SQLite format 3\x00"
        if sqlite:
            with readonly(path) as original, closing(sqlite3.connect(target)) as copy:
                original.backup(copy)
                require(copy.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "Snapshot SQLite integrity failed.")
        else:
            shutil.copyfile(path, target)
        os.chmod(target, 0o600)


def producer_snapshot(cfg, destination, root="/data"):
    from utilsim.hosted.backup import backup
    backup(root, destination)
    result = read_json(Path(destination) / "manifest.json")
    require(result.get("schemaVersion") == "producer-backup/1" and result.get("originalRoot") == str(Path(root).resolve())
            and result.get("vsCheckpointIncluded") is False
            and cfg["ownerCli"]["worldId"] in result.get("registeredWorlds", []), "Producer backup has no pinned registered world.")
    return {"producerBackup": True}


def producer_binding(cfg, root, proof, original_root="/data"):
    # Read existing identity facts only; the business stores are never rewritten.
    owners = cfg["ownerFiles"]
    with readonly(Path(root) / owners["catalog"]["path"]) as db:
        row = db.execute("SELECT environment,fingerprint,controller,active FROM hosted_connections WHERE world=?",
                         (cfg["ownerCli"]["worldId"],)).fetchone()
        world = db.execute("SELECT path,fingerprint FROM worlds WHERE id=?", (cfg["ownerCli"]["worldId"],)).fetchone()
    require(row and world and row["active"] == 1 and row["environment"] == cfg["runId"]
            and row["controller"] == cfg["ownerCli"]["controllerId"]
            and row["fingerprint"] == world["fingerprint"] == proof["worldFingerprint"]
            and world["path"] == os.path.normcase(str(Path(original_root) / owners["world"]["path"])), "Producer catalog/machine binding differs from VS.")
    with readonly(Path(root) / owners["world"]["path"]) as db:
        meta = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT key,value FROM meta WHERE key IN ('environment','fingerprint','through')")}
        pending = db.execute("SELECT COUNT(*) FROM machine_days WHERE result IS NULL").fetchone()[0]
    require(meta.get("environment") == cfg["runId"] and meta.get("fingerprint") == proof["worldFingerprint"]
            and isinstance(meta.get("through"), str) and meta["through"] <= proof["clock"][:10],
            "Producer identity/clock differs at shutdown.")
    # A committed world day with a lost reply may retain an unfinished machine
    # command. Preserve it in the full snapshot for exact original-ID retry;
    # complete means complete owner coverage, never that all jobs succeeded.
    return {"physicalThrough": meta["through"], "pendingMachineCommands": pending}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["serve", "health", "pause", "controller-snapshot", "producer-snapshot"])
    parser.add_argument("--config", default="/config/deployment.json")
    args = parser.parse_args()
    cfg = validate_config(read_json(args.config))
    require(cfg.get("recoveryMode") == "owner-cli-stopped/1", "Select the reviewed stopped owner CLI integration.")
    if args.action == "serve":
        serve(cfg)
        return
    if args.action == "health":
        result = health(cfg)
    elif args.action == "pause":
        result = pause(cfg)
    elif args.action == "controller-snapshot":
        result = controller_ready(cfg)
        copy_tree("/data", "/snapshot/data/controller")
    else:
        result = producer_snapshot(cfg, "/snapshot/producer-snapshot")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, KeyError, sqlite3.Error, ImportError):
        print("Refused: actual owner interface, credentials or snapshot validation failed.", file=sys.stderr)
        raise SystemExit(2) from None
