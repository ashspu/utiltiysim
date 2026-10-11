"""Rollback copies must survive a nested Windows town/runtime directory."""
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from utilsim.world.migrations import rollback_backup


def test_backup_target_longer_than_windows_max_path(tmp_path):
    directory = tmp_path / ("a" * max(20, 212 - len(str(tmp_path))))
    directory.mkdir()
    source = directory / "field.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE evidence(value TEXT)")
        db.execute("INSERT INTO evidence VALUES('retained')")
    world = SimpleNamespace(path=str(source))
    first = rollback_backup(world, "field-execution")
    second = rollback_backup(world, "field-execution")
    assert first != second
    assert len(first) > 260
    if os.name == "nt":
        assert first.startswith("\\\\?\\")
    assert Path(first).exists()
    with sqlite3.connect(first) as db:
        assert db.execute("SELECT value FROM evidence").fetchone()[0] == "retained"
    with sqlite3.connect(source) as db:
        assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1
