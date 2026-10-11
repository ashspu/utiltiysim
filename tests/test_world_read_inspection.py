"""Inspection must not compete for SQLite's reserved writer lock."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from utilsim.world.store import World


def test_readers_can_inspect_committed_state_while_writer_is_reserved(tmp_path):
    world = World(tmp_path / "world.sqlite")
    with world.db() as db:
        world.put(db, "test", {"value": "committed"})
    with world.db() as writer:
        world.put(writer, "test", {"value": "pending"})

        def inspect():
            with world.read_db() as reader:
                return world.metadata(reader)["test"]["value"]

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(inspect) for _ in range(6)]
            assert [f.result(timeout=5) for f in futures] == ["committed"] * 6
    assert inspect() == "pending"


def test_read_connection_rejects_writes(tmp_path):
    world = World(tmp_path / "world.sqlite")
    with world.read_db() as reader:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            world.put(reader, "forbidden", 1)


def test_missing_source_is_never_recreated_by_inspection(tmp_path):
    path = tmp_path / "world.sqlite"
    world = World(path)
    path.rename(tmp_path / "moved.sqlite")
    with pytest.raises(sqlite3.OperationalError):
        with world.read_db():
            pass
    assert not path.exists()
