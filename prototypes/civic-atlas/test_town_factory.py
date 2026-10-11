"""Factory constraints that must hold before any generated artwork is published."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import town_factory
from pydantic import ValidationError
from town_factory import (
    CONFIGS,
    config,
    indexed_facility,
    local_street_has_clearance,
    plan,
    road,
    validate_custom_config,
)

from utilsim.config import load_preset


def test_requested_library_sizes_and_explicit_features():
    assert sorted(c["homes"] for c in CONFIGS) == [500, 500, 500, 5000, 5000, 25000, 50000]
    assert len({c["id"] for c in CONFIGS}) == len(CONFIGS)
    ash = config("ashtown-5000")
    assert (ash["pools"], ash["schools"], ash["church"]) == (1000, 10, 1)
    for c in CONFIGS:
        assert 0 <= c["pools"] <= c["homes"] * 0.9
        assert c["shops"] >= 1


@pytest.mark.parametrize("target", [500, 5000, 25000, 50000])
def test_engine_accepts_required_world_sizes(target):
    assert load_preset("village", houses=target).town.houses == target


def test_engine_rejects_unvalidated_size_above_release_limit():
    with pytest.raises(ValidationError):
        load_preset("village", houses=50001)


def test_custom_configuration_is_validated_before_creating_geometry():
    raw = {**config("bramblewick-500"), "id": "factory-test-new-town"}
    assert validate_custom_config(raw)["homes"] == 500
    with pytest.raises(ValueError, match="new id"):
        validate_custom_config(config("bramblewick-500"))
    with pytest.raises(ValueError, match="Pool budget"):
        validate_custom_config({**raw, "pools": 451})
    with pytest.raises(ValueError, match="zero solar"):
        validate_custom_config({**raw, "solar": 5})


def test_indexed_campus_access_matches_original_nearest_road_including_ties():
    from shapely.geometry import LineString, box
    from shapely.strtree import STRtree
    from town500_world import _facility

    from utilsim.gen.roads.planarize import planarize

    roads = planarize(
        [],
        [road("East Road", 0, [(-100, 0), (100, 0)], 42), road("North Road", 1, [(0, -100), (0, 100)], 42)],
    )
    lines = [LineString(p) for p in roads.graph.geometry]
    tree = STRtree(lines)
    for x, y in [(15, 15), (-15, 15), (35, -10), (-18, -27)]:
        p = box(x - 4, y - 4, x + 4, y + 4)
        expected = _facility(roads, "SCHOOL", "school", "Test school", p)
        actual = indexed_facility(roads, "SCHOOL", "school", "Test school", p, lines, tree)
        assert actual.edge == expected.edge
        assert actual.s == pytest.approx(expected.s)
        assert actual.heading == pytest.approx(expected.heading)
        assert actual.side == expected.side


def test_local_street_clearance_rejects_parallel_rakes_but_allows_connected_branches():
    from shapely.geometry import LineString
    from shapely.strtree import STRtree

    existing = [LineString([(0, 0), (1000, 0)])]
    tree = STRtree(existing)
    assert not local_street_has_clearance(LineString([(50, 12), (900, 18)]), tree, existing)
    assert local_street_has_clearance(LineString([(50, 65), (900, 90)]), tree, existing)
    assert local_street_has_clearance(LineString([(500, 0), (500, 180)]), tree, existing)


def test_checkpoint_is_unpublished_and_rejects_modified_or_partial_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(town_factory, "CHECKPOINTS", tmp_path / "checkpoints")
    monkeypatch.setattr(town_factory, "ROOT", tmp_path / "public")
    preset, master, budget = "checkpoint-test", "<svg/>", {"homes": 476}
    snapshot = {
        "atlasDesign": {"presetId": preset, "masterSvgSha256": hashlib.sha256(master.encode()).hexdigest()}
    }
    data = {"budget": budget}
    folder = town_factory.checkpoint_sources(
        preset, snapshot, data, master, {"id": preset}, "seed", budget, 12
    )
    assert not town_factory.ROOT.exists()
    loaded_snapshot, loaded_data, loaded_master, context = town_factory.load_checkpoint(preset)
    assert (loaded_snapshot, loaded_data, loaded_master) == (snapshot, data, master)
    assert context["published"] is False
    (folder / "geometry.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        town_factory.load_checkpoint(preset)
    with pytest.raises(ValueError, match="preset slug"):
        town_factory.load_checkpoint("../checkpoint-test")


def fingerprint(lines):
    return hashlib.sha256(b"".join(np.asarray(line.points).tobytes() for line in lines)).hexdigest()


def test_coastal_and_orchard_streets_differ_and_are_reproducible():
    orchard = plan(config("bramblewick-500"), generations=0)[0]
    coast = plan(config("lantern-bay-500"), generations=0)[0]
    assert fingerprint(orchard) != fingerprint(coast)
    assert fingerprint(orchard) == fingerprint(plan(config("bramblewick-500"), generations=0)[0])


@pytest.mark.parametrize(
    "preset",
    ["bramblewick-500", "lantern-bay-500", "copperhaven-5000", "willowmere-25000", "foxglove-city-50000"],
)
def test_facility_sites_match_budget_and_roads_have_distinct_source_ids(preset):
    c = config(preset)
    lines, _, _, specs, _, _, _, _ = plan(c, generations=0)
    assert len({line.source_id for line in lines}) == len(lines)
    assert sum(s[0].startswith("SCHOOL-") for s in specs) == c["schools"]
    assert sum(s[0].startswith("INDUSTRY-") for s in specs) == c["industry"]
    assert sum(s[0] == "CHURCH-01" for s in specs) == c["church"]
    assert sum(s[0] == "MARKET-01" for s in specs) == 1


def test_catalogue_does_not_claim_visual_approval_from_source_geometry():
    root = Path(__file__).parent / "web/presets"
    catalog = json.loads((root / "catalog.json").read_text())["presets"]
    assert {p["id"] for p in catalog} == {c["id"] for c in CONFIGS}
    for item in catalog:
        assert item["visualReleaseApproved"] is False
        if item["status"] in ("prototype", "internally-reviewed"):
            assert item["targetHomes"] * 0.9 <= item["actualHomes"] <= item["targetHomes"] * 1.1


def test_internal_visual_review_expires_when_source_geometry_changes(tmp_path):
    geometry = tmp_path / "geometry.json"
    geometry.write_bytes(b'{"version":1}')
    review = {"status": "passed", "sourceSha256": hashlib.sha256(geometry.read_bytes()).hexdigest()}
    (tmp_path / "internal-visual-review.json").write_text(json.dumps(review), encoding="utf-8")
    assert town_factory.internal_visual_review(tmp_path)["status"] == "passed"
    geometry.write_bytes(b'{"version":2}')
    assert town_factory.internal_visual_review(tmp_path)["status"] == "outdated"
