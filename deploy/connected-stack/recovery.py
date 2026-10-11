"""Coordinated stopped, encrypted backup and original-path-only restore."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from stack import (
    HERE,
    MARKER,
    ROLES,
    Refused,
    compose,
    preflight,
    read_json,
    require,
    run,
    validate_config,
    volume,
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_sqlite(root):
    for path in root.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                sqlite = stream.read(16) == b"SQLite format 3\x00"
            if not sqlite:
                continue
            try:
                with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                    require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
                            "SQLite integrity check failed; refuse backup/restore.")
            except sqlite3.Error:
                raise Refused("SQLite integrity check failed; refuse backup/restore.") from None


def files(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Symbolic links in owner stores are refused.")
        require(path.is_dir() or path.is_file(), "Special files in owner stores are refused.")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {"sha256": digest(path), "bytes": path.stat().st_size}
    return result


def stopped(cfg, config_path):
    ids = compose(cfg, config_path, "ps", "--all", "--quiet", capture=True).decode().split()
    if ids:
        states = [json.loads(line) for line in run(["docker", "inspect", "--format", "{{json .State}}", *ids], capture=True).decode().splitlines()]
        require(all(not state.get("Running") and not state.get("Restarting") for state in states),
                "All stack containers must actually be stopped.")


def checkpoint(cfg, config_path):
    pause = json.loads(compose(cfg, config_path, "exec", "--no-TTY", "controller", "python", "/ops/stack.py", "pause", "controller", capture=True))
    proof = json.loads(compose(cfg, config_path, "exec", "--no-TTY", "controller", "python", "/ops/stack.py", "checkpoint", "controller", capture=True))
    require(pause["clock"] == proof["clock"] and pause["controllerRevision"] == proof["controllerRevision"]
            and proof["runId"] == cfg["runId"] and proof["complete"] is True,
            "Clock moved between pause/idle barrier and complete checkpoint.")
    if cfg.get("fieldEnabled"):
        require("field" in proof["owners"], "Managed field owner is missing from the checkpoint.")
    return proof


def manifest(cfg, proof, root):
    return {"schemaVersion": "utilitysim-connected-backup/1", "createdAt": datetime.now(UTC).isoformat(),
            "runId": cfg["runId"], "volumeId": cfg["volumeId"], "originalDataRoot": cfg["dataRoot"],
            "containerPaths": {role: "/data" for role in ROLES}, "checkpoint": proof,
            "ownerFiles": cfg["ownerFiles"],
            "images": {role: service["image"] for role, service in cfg["services"].items()},
            "sourceCommits": {role: cfg["services"][role]["sourceCommit"] for role in ROLES},
            "files": files(root)}


def backup(cfg, config_path):
    preflight(cfg, config_path)
    require(shutil.which("age"), "Install reviewed age tooling before encrypted backup.")
    destination = Path(cfg["backupDirectory"])
    require(destination.is_dir() and destination.resolve() == destination.absolute(), "Create a protected off-volume backup directory without symbolic links first.")
    require(destination.stat().st_mode & 0o077 == 0, "Backup directory requires mode0700.")
    proof = checkpoint(cfg, config_path)
    compose(cfg, config_path, "stop", "--timeout", "120")
    stopped(cfg, config_path)
    root = Path(cfg["dataRoot"])
    verify_sqlite(root)
    record = manifest(cfg, proof, root)
    name = "connected-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".tar.age"
    final = destination / name
    # Same protected directory; plaintext is temporary and never published.
    with tempfile.TemporaryDirectory(prefix=".backup-", dir=destination) as temporary:
        temp = Path(temporary)
        os.chmod(temp, 0o700)
        (temp / "manifest.json").write_text(json.dumps(record, sort_keys=True) + "\n")
        archive = temp / "owners.tar"
        with tarfile.open(archive, "w") as tar:
            tar.add(temp / "manifest.json", arcname="manifest.json")
            tar.add(root, arcname="data")
        os.chmod(archive, 0o600)
        partial = temp / "encrypted.age"
        run(["age", "--recipient", cfg["ageRecipient"], "--output", str(partial), str(archive)], timeout=3600)
        require(partial.is_file() and partial.stat().st_size > 0, "Encrypted backup was not produced.")
        os.chmod(partial, 0o600)
        # Verify source state did not change after the shutdown barrier.
        require(files(root) == record["files"], "An external writer changed owner files while backing up.")
        partial.rename(final)
    print(json.dumps({"backup": str(final), "sha256": digest(final), "runId": cfg["runId"], "clock": proof["clock"], "servicesStopped": True}))


def unpack_verified(archive, stage, cfg, max_bytes=20 * 1024**3):
    """Never extract links, escapes, duplicate members or an unbounded archive."""
    with tarfile.open(archive, "r:") as tar:
        members = tar.getmembers()
        seen, size = set(), 0
        for member in members:
            name = PurePosixPath(member.name)
            require(member.name not in seen and not name.is_absolute() and ".." not in name.parts and
                    (member.name == "manifest.json" or name.parts and name.parts[0] == "data") and
                    (member.isdir() or member.isfile()), "Unsafe or duplicate backup archive member.")
            seen.add(member.name)
            size += member.size
            require(0 <= member.size and size <= max_bytes, "Backup exceeds the configured restore size bound.")
            target = stage.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tar.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                os.chmod(target, 0o600)
    record = read_json(stage / "manifest.json")
    require(record.get("schemaVersion") == "utilitysim-connected-backup/1" and record.get("runId") == cfg["runId"]
            and record.get("volumeId") == cfg["volumeId"] and record.get("originalDataRoot") == cfg["dataRoot"]
            and record.get("containerPaths") == {role: "/data" for role in ROLES},
            "Backup identities/original paths differ; relocated managed recovery is unsupported.")
    require(record.get("images") == {role: service["image"] for role, service in cfg["services"].items()}
            and record.get("sourceCommits") == {role: cfg["services"][role]["sourceCommit"] for role in ROLES},
            "Restore requires the recorded exact owner images and source commits.")
    require(record.get("ownerFiles") == cfg["ownerFiles"], "Original producer/VS owner bindings differ.")
    proof = record.get("checkpoint", {})
    require(proof.get("runId") == cfg["runId"] and all(proof.get(x) is True for x in ("paused", "idle", "workersStopped", "complete"))
            and {"runtime", "world", "catalog", "billing", "ledger", "evidence", "controller"} <= set(proof.get("owners", [])),
            "Backup lacks a complete paused idle checkpoint.")
    require(not cfg.get("fieldEnabled") or "field" in proof["owners"], "Backup omits managed field state.")
    require(files(stage / "data") == record.get("files"), "Backup file hashes/coverage differ from the manifest.")
    require(all((stage / "data" / item["service"] / item["path"]).is_file()
                for item in cfg["ownerFiles"].values()), "Backup omits a bound producer or VS owner file.")
    verify_sqlite(stage / "data")
    return record


def restore(cfg, config_path, archive, identity):
    require(sys.platform.startswith("linux") and shutil.which("docker") and shutil.which("age"), "Restore requires Linux, Docker and age.")
    volume(cfg)
    stopped(cfg, config_path)
    root = Path(cfg["dataRoot"])
    require(set(path.name for path in root.iterdir()) <= {MARKER, *ROLES, "lost+found"}
            and (not (root / "lost+found").exists() or not any((root / "lost+found").iterdir()))
            and all(not any((root / role).iterdir()) for role in ROLES),
            "Restore requires an empty initialized replacement volume; it never overwrites owner data.")
    key = Path(identity)
    require(key.is_file() and key.resolve() == key.absolute() and key.stat().st_mode & 0o077 == 0,
            "Supply a protected age identity file outside the archive.")
    destination = Path(cfg["backupDirectory"])
    require(destination.is_dir() and destination.resolve() == destination.absolute() and destination.stat().st_mode & 0o077 == 0,
            "Restore staging requires a protected backup directory without symbolic links.")
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=destination) as temporary:
        temp = Path(temporary)
        os.chmod(temp, 0o700)
        plain = temp / "owners.tar"
        run(["age", "--decrypt", "--identity", str(key), "--output", str(plain), str(Path(archive).resolve())], timeout=3600)
        os.chmod(plain, 0o600)
        stage = temp / "verified"
        stage.mkdir(mode=0o700)
        record = unpack_verified(plain, stage, cfg)
        for role in ROLES:
            source = stage / "data" / role
            require(source.is_dir(), "Backup omits a required owner directory.")
            shutil.copytree(source, root / role, dirs_exist_ok=True)
        for path in root.rglob("*"):
            if path.name != MARKER:
                os.chown(path, 10001, 10001)
        require(files(root) == record["files"], "Restored files differ; keep services stopped and inspect replacement volume.")
    print(json.dumps({"restored": True, "runId": cfg["runId"], "clock": record["checkpoint"]["clock"], "servicesStopped": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("--config", default=str(HERE / "deployment.json"))
    parser.add_argument("--archive")
    parser.add_argument("--identity")
    args = parser.parse_args()
    cfg = validate_config(read_json(args.config))
    if args.action == "backup":
        backup(cfg, args.config)
    else:
        require(args.archive and args.identity, "Restore requires encrypted archive and protected identity file.")
        restore(cfg, args.config, args.archive, args.identity)


if __name__ == "__main__":
    try:
        main()
    except (Refused, OSError, ValueError, tarfile.TarError) as exc:
        message = str(exc) if isinstance(exc, Refused) else "Recovery operation failed; services remain stopped if shutdown completed."
        print("Refused: " + message, file=sys.stderr)
        raise SystemExit(2) from None
