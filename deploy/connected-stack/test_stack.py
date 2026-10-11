"""Portable negative gates and genuine SQLite archive recovery checks; no Docker."""
import copy
import io
import json
import sqlite3
import tarfile
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import recovery
import stack


def fixture():
    cfg = stack.read_json(stack.HERE / "deployment.example.json")
    cfg.update(readiness="deployment-ready", runId="isolated-unit-run", volumeId="bc28a5b8-92c1-4d62-a397-45ca74c528e1",
               producerHost="producer.goodquartercompany.com", ageRecipient="age1" + "q" * 58)
    for role, item in cfg["services"].items():
        item["image"] = "test/" + role + "@sha256:" + "1" * 64
        if role != "edge":
            item["healthCommand"] = ["python", "-c", "raise SystemExit(0)"]
    controller = cfg["services"]["controller"]
    controller.update(command=["python", "controller.py"], requiredSecrets=["CONNECTED_ACTOR_TOKEN"],
                      pauseCommand=["python", "hooks.py", "pause"], checkpointCommand=["python", "hooks.py", "checkpoint"])
    for key in ("producerContainerAcceptance", "controllerConnectedAcceptance", "linuxRestoreAcceptance"):
        cfg["evidence"][key] = "synthetic-unit-fixture-only"
    for name, item in cfg["ownerFiles"].items():
        item["path"] = name + ".sqlite"
    return cfg


class ConfigurationTests(unittest.TestCase):
    def test_candidate_refuses_deploy(self):
        with self.assertRaises(stack.Refused):
            stack.validate_config(stack.read_json(stack.HERE / "deployment.example.json"))

    def test_required_images_credentials_hooks_and_evidence(self):
        stack.validate_config(fixture())
        changes = [lambda x: x["services"]["producer"].update(image="image:latest"),
                   lambda x: x["services"]["controller"].update(requiredSecrets=[]),
                   lambda x: x["services"]["controller"].update(pauseCommand=[]),
                   lambda x: x["evidence"].update(linuxRestoreAcceptance=None),
                   lambda x: x.update(producerHost="runtime.example.com"),
                   lambda x: x.update(backupDirectory=x["dataRoot"] + "/backups")]
        for change in changes:
            cfg = fixture()
            change(cfg)
            with self.subTest(cfg=change), self.assertRaises(stack.Refused):
                stack.validate_config(cfg)

    def test_credentials_are_not_cli_arguments(self):
        for command in (["server", "--token=do-not-pass"], ["server", "--token", "do-not-pass"]):
            cfg = fixture()
            cfg["services"]["controller"]["command"] = command
            with self.assertRaises(stack.Refused):
                stack.validate_config(cfg)

    def test_only_tls_is_published_and_private_source_not_mounted(self):
        cfg = stack.read_json(stack.HERE / "compose.json")
        self.assertTrue(cfg["networks"]["owners"]["internal"])
        for role in stack.ROLES:
            service = cfg["services"][role]
            self.assertNotIn("ports", service)
            self.assertEqual(service["user"], "10001:10001")
            self.assertTrue(service["read_only"])
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertTrue(all(not mount["bind"]["create_host_path"] for mount in service["volumes"]))
            self.assertNotIn("docker.sock", json.dumps(service))
        self.assertEqual(cfg["services"]["edge"]["ports"], ["443:8443"])
        self.assertEqual(cfg["services"]["controller"]["network_mode"], "service:producer")


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = fixture()
        self.data = self.root / "data"
        self.data.mkdir()
        for role in stack.ROLES:
            (self.data / role).mkdir()
        for item in self.cfg["ownerFiles"].values():
            db_path = self.data / item["service"] / item["path"]
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute("CREATE TABLE progress(run TEXT, clock TEXT, cursor INTEGER)")
                db.execute("INSERT INTO progress VALUES(?,?,?)", (self.cfg["runId"], "2026-07-18T00:00:00Z", 19))
        (self.data / stack.MARKER).write_text(json.dumps({"schemaVersion": stack.SCHEMA, "volumeId": self.cfg["volumeId"], "runId": self.cfg["runId"]}))
        proof = dict(runId=self.cfg["runId"], clock="2026-07-18T00:00:00Z", controllerRevision=7,
                     paused=True, idle=True, workersStopped=True, complete=True,
                     owners=["runtime", "world", "catalog", "billing", "ledger", "evidence", "controller"])
        self.record = recovery.manifest(self.cfg, proof, self.data)

    def archive(self, record=None, extra=None):
        target = self.root / "owners.tar"
        metadata = json.dumps(record or self.record).encode()
        with tarfile.open(target, "w") as tar:
            member = tarfile.TarInfo("manifest.json")
            member.size = len(metadata)
            tar.addfile(member, io.BytesIO(metadata))
            tar.add(self.data, arcname="data")
            if extra:
                tar.addfile(extra, io.BytesIO(b""))
        return target

    def unpack(self, archive, cfg=None):
        stage = self.root / "stage"
        stage.mkdir()
        return recovery.unpack_verified(archive, stage, cfg or self.cfg)

    def test_real_sqlite_roundtrip_preserves_cursor_and_ids(self):
        self.unpack(self.archive())
        with closing(sqlite3.connect(self.root / "stage/data/controller/controller.sqlite")) as db:
            self.assertEqual(db.execute("SELECT * FROM progress").fetchone(),
                             (self.cfg["runId"], "2026-07-18T00:00:00Z", 19))

    def test_tampered_owner_refused(self):
        (self.data / "controller/controller.sqlite").write_bytes(b"changed")
        with self.assertRaises(stack.Refused):
            self.unpack(self.archive())

    def test_vs_only_archive_cannot_claim_complete_producer_checkpoint(self):
        (self.data / "producer/world.sqlite").unlink()
        record = copy.deepcopy(self.record)
        record["files"] = recovery.files(self.data)
        with self.assertRaises(stack.Refused):
            self.unpack(self.archive(record))

    def test_foreign_or_relocated_checkpoint_refused(self):
        for field, value in [("runId", "foreign"), ("dataRoot", "/srv/relocated")]:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                record["runId" if field == "runId" else "originalDataRoot"] = value
                archive = self.archive(record)
                stage = self.root / field
                stage.mkdir()
                with self.assertRaises(stack.Refused):
                    recovery.unpack_verified(archive, stage, self.cfg)

    def test_pause_ack_without_idle_and_missing_field_are_refused(self):
        for name in ("idle", "field"):
            with self.subTest(name=name):
                record = copy.deepcopy(self.record)
                cfg = copy.deepcopy(self.cfg)
                if name == "idle":
                    record["checkpoint"]["idle"] = False
                else:
                    cfg["fieldEnabled"] = True
                stage = self.root / name
                stage.mkdir()
                with self.assertRaises(stack.Refused):
                    recovery.unpack_verified(self.archive(record), stage, cfg)

    def test_archive_escape_link_duplicate_and_size_refused(self):
        for name, kind in [("data/../../escape", tarfile.REGTYPE), ("data/link", tarfile.SYMTYPE),
                           ("manifest.json", tarfile.REGTYPE)]:
            with self.subTest(name=name):
                extra = tarfile.TarInfo(name)
                extra.type = kind
                extra.linkname = "/etc/passwd"
                stage = self.root / ("case" + str(len(list(self.root.iterdir()))))
                stage.mkdir()
                with self.assertRaises(stack.Refused):
                    recovery.unpack_verified(self.archive(extra=extra), stage, self.cfg)
        stage = self.root / "tiny"
        stage.mkdir()
        with self.assertRaises(stack.Refused):
            recovery.unpack_verified(self.archive(), stage, self.cfg, max_bytes=1)


if __name__ == "__main__":
    unittest.main()
