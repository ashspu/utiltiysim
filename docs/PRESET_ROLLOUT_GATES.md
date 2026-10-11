# Preset rollout gates

Proposal, 11 October 2026. Fleet creation and release are **BLOCKED**. This work prepares evidence checks only; do not generate or build the remaining maps until Ashtown is complete, reviewed, and its lessons accepted for reuse. Coordinator owns final sample selection. Ashtown source alignment remains owned by chat `01a12b9e-2a9f-7440-b1da-89f9ac8e468e`.

Controlling plan: [ONLINE_WORLD_ROADMAP](ONLINE_WORLD_ROADMAP.md). Original design references: [CIVIC_ATLAS_MAP_DESIGN](CIVIC_ATLAS_MAP_DESIGN.md), [ISOMETRIC_MAP](ISOMETRIC_MAP.md), [WORLD_MAP](WORLD_MAP.md). Earlier procedural catalog status is historical evidence, not approval of rebuilt imagery or geometry.

## Current evidence and holds

- `P:/UtilitySim/map-workstreams/ashtown/integration/ashtown-readiness.json`: development-only; final illustration, authoritative parcel registry and playable rebuilt world false. Source `status.json` and `handoff.json` record the rejected frontage-seeded Voronoi draft and an accepted 18-yard manual proof, not citywide verified homes. Actual valid count remains unknown; 5,000 homes ±10% remains the Ashtown target.
- `runtime/reviewed-routing/independent-acceptance.json` in that workstream accepts numeric connectivity and targeted interchange fidelity. It explicitly excludes complete visual alignment, lane rules, buildings/frontage binding and end-to-end simulation. Passing this gate does not accept the entire map.
- Accepted Harbour source: `P:/Codex/2026-10-10/prototypes-civic-atlas-start-elsewhere-md/outputs/lantern-harbour-final`. Nine panels, 436 premises (300 residential, 136 other), 1,262 meters. The accepted visual reference falls short of the original 500-home target. Preserve known cosmetic seam bands and residual 170 unassigned areas as evidence; do not silently count them as homes or waive Ashtown's target. Harbour identity is separate from catalog Lantern Bay.

## Reusable ordered checklist

1. **Zoning:** pin source concept, terrain/water, feature budget, fixed occupancy assumptions, target metric and tolerance. Population, homes, residential premises, buildings, households and meters are separate measures.
2. **Regional art and seams:** accept ownership mosaic, global anchors and crossings before tracing. Preserve complete regional partitions and inspect shared edges at useful zoom.
3. **Roads/access:** trace observed major/local paving and actual access. Review crossings, bridge separation, ramps, direction restrictions and property frontage. Estimated roads or connected graphs alone are insufficient.
4. **Visible whole-lot parcels:** trace/generalize coherent shared boundaries aligned to source yards. Reject generic Voronoi cuts, roof-mask notches, rear-garden fragments and count-padding. Review curved, simple and waterfront blocks before citywide counting.
5. **Stable identities:** pin one authoritative parcel/premise/service/meter registry; retain waterfront identities and single ownership across tiles. Declare ambiguous land nonbillable until resolved. Check contained pools and exact feature budgets.
6. **Constrained block illustration:** generate whole street-bounded blocks from accepted guides; preserve roads, yards and IDs. Avoid per-property pasted sprites and cropped fragments that introduce seams. Record prompts, model/source provenance and resulting hashes.
7. **Zoom/click/snapshot QA:** inspect overview/detail/seams, actual pointer picking, residential/civic/business records, deep links and selection; verify snapshot identity, isolated creation, advancement, restart/resume and unchanged source. Report measured performance and separate scale acceptance for 25k/50k.

Each stage needs hashed evidence and explicit review scope. Review acceptance comes from a human or independent reviewer other than the builder. Structural tests cannot issue it. Final coordinator review must accept the completed Ashtown revision and a lessons/checklist handoff before fleet construction begins; fleet release additionally requires each selected template's playable evidence.

## Proposed machine-readable contract

`scripts/preset_readiness.schema.json` defines the proposed JSON Schema shape (unknown preview counts may be null). `scripts/preset_readiness.py` checks release evidence using standard-library Python; play requires actual counts and complete accepted stages. A manifest has:

| Field | Contract |
| --- | --- |
| `schema`, `townId`, `revision`, `owner`, `previewLabel` | Exact schema and nonempty identities; immutable revision identifies the reviewed bundle. |
| `releaseClass` | `development-preview` or `playable-template`; preview validity never authorizes play. |
| `target` | `{metric: "homes" or "population", value: positive integer, tolerance: fraction 0..0.1}`. Coordinator decides targets; no conversion using assumed household size. |
| `counts` | Actual nonnegative integers: `population`, `homes`, `residentialPremises`, `otherPremises`, `meters`; attach hashed count/occupancy QA evidence. Unknown counts block play. |
| `assets` | Named `{path, sha256}` entries for concept, registrations, geometry/registry, prompts/art, QA, snapshot and count report. Paths relative to manifest, or explicit local paths. Checker reads and hashes every entry. |
| `stages` | Keys `zoning`, `regional_art_seams`, `roads_access`, `visible_lot_parcels`, `premise_service_ids`, `block_illustration`, `zoom_click_snapshot_qa`; each `{status: "complete", evidenceAssets: [asset names]}` for play. |
| `reviewRecord` | Path to externally authored acceptance record; never infer acceptance from flags or tests. |
| `unresolvedAreas` | Explicit list, even when empty; each `{areaId, severity: "blocking" or "cosmetic", reason, owner}`. Any blocking item holds release; cosmetic items must remain visible in the accepted evidence. |

The review record contains `kind` (`human` or `independent-review`), `reviewer`, `decision: "accepted"`, `acceptedAt`, `evidence` (link/path to acceptance), `townId`, `revision`, `assetHashes` matching the complete manifest and `acceptedStages`. Scale acceptance adds `scale_qa` and must link measured full-world workload and recovery evidence. Hashing binds evidence bytes; it does not prove visual truth, authenticate authorship or replace coordinator examination of the acceptance source. This validator is a preparation CLI, not wired into deployment authorization.

The fleet learning record contains `decision: "accepted"`, `acceptedBy` (coordinator, distinct from builder), `ashtownRevision`, `ashtownReviewRecord`, nonempty `lessons`, and `nextPresetChecklist`. Carry rejected Voronoi/estimated-road lessons, source-aligned whole yards, waterfront identities and whole-block/cropless seam handling into that checklist. Commit the reviewed handoff with the manifest so records remain inspectable.

```powershell
python scripts/preset_readiness.py PATH_TO_MANIFEST --mode preview
python scripts/preset_readiness.py PATH_TO_MANIFEST --mode playable
python scripts/preset_readiness.py P:/UtilitySim/map-workstreams/ashtown/integration/ashtown-readiness.json --mode fleet
python scripts/preset_readiness.py PATH_TO_COMPLETED_ASHTOWN_MANIFEST --mode fleet --learning-record PATH_TO_ACCEPTED_LEARNING_RECORD
python -m pytest --noconftest tests/test_preset_readiness.py
```

Output is `BLOCKED` (exit 1) or `EVIDENCE_COMPLETE` (exit 0), deliberately never `APPROVED`. The current Ashtown command returns BLOCKED: its legacy development evidence cannot satisfy release schema and no accepted learning handoff exists. A valid preview only checks its identities and asset provenance; it makes no playable claim.

## Provisional sample mix, no construction authorization

Existing `prototypes/civic-atlas/web/presets/catalog.json` provides names/character only: Two River Forest, Bramblewick and Lantern Bay as three small candidates; Ashtown and Copperhaven as two 5k candidates; Willowmere (25k) **or** Foxglove City (50k) as a scale candidate. This is a six-slot proposal, with a five-slot alternative dropping one small candidate. It is not a final selection or decision about population. Catalog suffixes currently describe `targetHomes`; original design discusses population. Resolve that distinction explicitly with the coordinator after Ashtown review. Reusing legacy claimed actual counts would bypass the required source-aligned pipeline. Retain accepted Harbour separately as a honestly labelled reference unless the coordinator chooses its role in the release set.

## Handoff

Prepared in branch `codex/preset-rollout-gates` from `0067f61`, worktree `P:/UtilitySim/worktrees/preset-rollout-gates`. Scope: this document, validator and focused tests only; no maps, images, geometry, UI, PR or deployment. Next owner: coordinator obtains completed Ashtown evidence and independently accepted lessons, then selects sample mix/targets. Root coordinates Slack in #vbs-agents thread `1791739340.071919`. Standing chat/Slack coordination authorization: Greg, 11 October 2026, chat `01a12aa3-5c1e-7142-aad0-dd177c7c9f09`; [chat-organisation skill](C:/Users/Greg/.codex/skills/chat-organisation/SKILL.md). No recurring monitor created.
