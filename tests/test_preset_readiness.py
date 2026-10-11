"""Readiness checks exercise provenance, review scope and rollout holds."""
import hashlib
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("preset_readiness", Path(__file__).parents[1] / "scripts/preset_readiness.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def fixture(tmp_path):
    (tmp_path / "snapshot.json").write_text("{}")
    digest = hashlib.sha256(b"{}").hexdigest()
    data = {
        "schema": checker.SCHEMA, "townId": "ashtown", "revision": "r1", "owner": "builder",
        "previewLabel": "Reviewed sample", "releaseClass": "playable-template",
        "counts": {"population": 10000, "homes": 5000, "residentialPremises": 5000,
                   "otherPremises": 100, "meters": 5100},
        "target": {"metric": "homes", "value": 5000, "tolerance": 0.1},
        "assets": {"snapshot": {"path": "snapshot.json", "sha256": digest}},
        "reviewRecord": "review.json", "unresolvedAreas": [],
        "stages": {s: {"status": "complete", "evidenceAssets": ["snapshot"]} for s in checker.STAGES},
    }
    review = {"kind": "human", "reviewer": "Greg", "decision": "accepted", "townId": "ashtown",
              "revision": "r1", "evidence": "review transcript", "acceptedAt": "2026-10-11",
              "assetHashes": {"snapshot": digest}, "acceptedStages": list(checker.STAGES)}
    (tmp_path / "review.json").write_text(json.dumps(review))
    return data, review


def test_complete_evidence_does_not_open_fleet_without_learning_review(tmp_path):
    data, _ = fixture(tmp_path)
    assert checker.validate(data, tmp_path, playable=True) == []
    assert checker.fleet_gate(data, tmp_path, None)
    learning = {"decision": "accepted", "acceptedBy": "coordinator", "ashtownRevision": "r1",
                "ashtownReviewRecord": "review.json", "lessons": ["whole lots"],
                "nextPresetChecklist": ["review seams"]}
    path = tmp_path / "learning.json"
    path.write_text(json.dumps(learning))
    assert checker.fleet_gate(data, tmp_path, path) == []


def test_structural_pass_cannot_self_approve_or_expand_review_scope(tmp_path):
    data, review = fixture(tmp_path)
    review["reviewer"] = "builder"
    review["acceptedStages"] = ["roads_access"]
    (tmp_path / "review.json").write_text(json.dumps(review))
    errors = checker.validate(data, tmp_path, playable=True)
    assert any("external" in e for e in errors)
    assert any("visible_lot_parcels" in e for e in errors)


def test_changed_asset_invalidates_review(tmp_path):
    data, _ = fixture(tmp_path)
    (tmp_path / "snapshot.json").write_text('{"changed":true}')
    assert any("hash mismatch" in e for e in checker.validate(data, tmp_path, playable=True))


def test_population_is_not_home_count_and_preview_stays_preview(tmp_path):
    data, _ = fixture(tmp_path)
    data["target"] = {"metric": "population", "value": 5000, "tolerance": 0.1}
    data["releaseClass"] = "development-preview"
    assert checker.validate(data, tmp_path) == []
    errors = checker.validate(data, tmp_path, playable=True)
    assert any("outside target" in e for e in errors)
    assert any("Development preview" in e for e in errors)


def test_blocking_area_and_scale_cannot_be_waived_by_numeric_pass(tmp_path):
    data, _ = fixture(tmp_path)
    data["counts"]["population"] = 50000
    data["unresolvedAreas"] = [{"areaId": "waterfront", "severity": "blocking",
                                "reason": "identity ambiguity", "owner": "map owner"}]
    errors = checker.validate(data, tmp_path, playable=True)
    assert any("waterfront" in e for e in errors)
    assert any("scale QA" in e for e in errors)


def test_current_ashtown_shape_is_blocked_even_with_optimistic_flags(tmp_path):
    data = {"schema": "utilitysim-town-readiness/1", "townId": "ashtown",
            "playableRebuiltWorld": True, "countsVerified": True}
    assert checker.fleet_gate(data, tmp_path, None)


def test_malformed_records_fail_closed(tmp_path):
    data, _ = fixture(tmp_path)
    data["counts"] = {"population": "50000"}
    data["stages"] = {"zoning": {"status": "complete", "evidenceAssets": 5}}
    (tmp_path / "review.json").write_text("[]")
    assert checker.validate(data, tmp_path, playable=True)
    assert checker.fleet_gate([], tmp_path, None)
