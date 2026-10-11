"""Negative controls for release gates, including a compressed-only checkout."""
import gzip
import json
import shutil
from pathlib import Path

import pytest
from release_contract import audit

SOURCE = Path(__file__).parent / "web/presets/two-river-forest-500"


@pytest.fixture
def packaged(tmp_path):
    for name in ("snapshot.json.gz", "geometry.json.gz", "master.svg"):
        shutil.copyfile(SOURCE / name, tmp_path / name)
    return tmp_path


def test_compressed_only_checkout_has_complete_identity_links(packaged):
    result = audit(packaged)
    assert result["passed"]
    assert result["actualHomes"] == 451
    assert result["premises"] == 476


def test_missing_account_is_rejected_even_if_map_and_snapshot_agree(packaged):
    for name, table in (("geometry", "properties"), ("snapshot", "premises")):
        path = packaged / (name + ".json.gz")
        data = json.loads(gzip.decompress(path.read_bytes()))
        data[table][0]["accountId"] = "NONEXISTENT-ACCOUNT"
        path.write_bytes(gzip.compress(json.dumps(data).encode()))
    result = audit(packaged)
    assert not result["passed"]
    assert result["invalidLinks"][0]["invalid"] == ["accountId"]


def test_falsely_declared_sample_size_is_rejected(packaged):
    path = packaged / "geometry.json.gz"
    data = json.loads(gzip.decompress(path.read_bytes()))
    data["budget"]["targetHomes"] = 5000
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    result = audit(packaged)
    assert not result["passed"]
    assert any("outside target" in p for p in result["problems"])


def test_changed_master_svg_is_rejected(packaged):
    path = packaged / "master.svg"
    path.write_text(path.read_text(encoding="utf-8") + "\n<!-- changed -->", encoding="utf-8")
    assert not audit(packaged)["passed"]
