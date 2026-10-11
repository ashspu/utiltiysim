# Configuration-first town authoring

The curated catalogue has three 500-home towns, two 5,000-home towns, one
25,000-home town and one 50,000-home town. Home counts may differ from the target
by at most 10%. Pools, schools, churches, commercial premises and industrial
premises have exact budgets. The seven presets currently specify no solar.

`town_factory.py` bakes an explicit configuration into real UtilitySim premises,
customers, meters and electric, water and gas networks. It does not call an image
model or infer ownership from a raster image. Generated concept art guides the
authoring; the resulting geometry is authoritative for both rendering and data.

## Build a new town

Export a draft from the shell, or save a UTF-8 JSON file such as:

```json
{
  "id": "juniper-crossing-500",
  "name": "Juniper Crossing",
  "homes": 500,
  "pools": 75,
  "schools": 1,
  "church": 1,
  "shops": 16,
  "industry": 6,
  "seed": 7231,
  "palette": "orchard",
  "character": "A wooded market village with an oblique high street",
  "solar": 0,
  "homeTolerance": 0.1
}
```

From the repository root:

```powershell
npm install --prefix out/civic-atlas/browser --no-save playwright-core@1.64.0
.venv/Scripts/python.exe prototypes/civic-atlas/build-town.py --config world.json
```

Install Edge, Chrome or Chromium locally; the browser runtime discovers standard
installation paths. For another installation, set `CHROMIUM_PATH` to the browser
executable. The npm command installs the pinned automation dependency, not a
browser. The orchestrator imports the browser runtime before generating source
geometry, so missing dependencies fail early with setup instructions. This
preflight checks dependency and executable discovery; the overview step still
verifies that the browser actually launches and renders.

This runs source generation and geometry checks, the complete identity audit,
spatial tile packing, browser overview rendering and compressed-source
packaging. It starts a temporary static server on a free loopback port for the
overview step and shuts it down afterward. Node.js and the repository browser
runtime are required. Supply `--node PATH` if Node is not on `PATH`.

The progress and remaining review gates are written to
`out/factory-runs/<id>.json`. Every failed command stops the pipeline. To retry
packaging after an interrupted downstream step, without regenerating a
successfully baked town:

```powershell
.venv/Scripts/python.exe prototypes/civic-atlas/build-town.py --resume juniper-crossing-500
```

`--skip-overview` is available for source-only environments and records the
missing overview explicitly. For geometry authoring alone, use
`town_factory.py --config world.json` instead of the orchestrator.

New builds also save an unpublished source checkpoint under
`out/factory-checkpoints/<id>/` immediately before final geometry QA. If that
last phase is interrupted, preserve the already generated utility networks and
resume with:

```powershell
.venv/Scripts/python.exe prototypes/civic-atlas/town_factory.py --resume-checkpoint juniper-crossing-500
.venv/Scripts/python.exe prototypes/civic-atlas/build-town.py --resume juniper-crossing-500
```

Resume verifies every checkpoint digest and reruns the geometry gates. A
checkpoint is never a released map, and failed checks cannot publish it. The
checkpoint descriptor is written last so a partial write is rejected.

Custom IDs cannot overwrite a curated preset or an existing destination folder.
The command validates the budget before creating geometry. Supported palettes
are `forest`, `orchard`, `coastal`, `ash`, `copper`, `wetland` and `foxglove`.
`character` records design intent; it is not a natural-language generation API.
The palette and seed select supported layout rules. New design constraints need
explicit authoring and visual review.

To reproduce source geometry for a factory-owned curated preset, run
`town_factory.py <preset-id>`, then package it with `build-town.py --resume <preset-id>`.
Two River Forest and Ashtown retain their dedicated generators; the factory
refuses to overwrite those sources. Run large builds sequentially because the
complete simulation snapshot is held in memory while it is validated.

## Geometry and identity contract

1. Reserve water, civic green, school campuses, market, church and industry.
2. Build a connected arterial and collector network, then subdivide usable
   street-bounded land into irregular blocks. Streets follow the same graph
   used by utility networks and map hit targets. Large-town subdivision treats
   reserved land as block boundaries and rejects sustained close parallel
   roads, preventing repeated clipped streets beside rivers and campuses.
3. Form legal road-fronting parcels. Place each building and pool inside its
   own parcel. Reject an over-dense or under-capacity plan; never add invisible
   customers to meet the advertised count.
4. Create customer accounts, installations, meters and utility networks from
   those premises. Every rendered building resolves to its premise and parcel.
5. Validate footprints, overlap, roads, budget and metadata ownership. Publish
   `snapshot.json`, `geometry.json`, `master.svg`, `checks.json` and
   `build-manifest.json` only after the geometry gates pass.

Coordinates in new factory geometry are metres, with `metresPerUnit: 1` and
explicit `bounds`. Parcels, buildings, roads, blocks and accounts retain stable
IDs for a given generator revision, configuration and seed. A new layout is a
new world: existing saved billing worlds must not silently reuse changed map
sources under the same identity.

`geometryPassed` is not visual or end-to-end approval. `artStatus: pending` is
intentional until the rendered map has been inspected. Check density, street
character, edge continuity and property detail at both whole-town and close
zoom. Revise the plan and rebuild when it fails that review.

## Release sequence

The orchestrator packages spatial tiles and renders overview levels with the
same browser renderer used at property zoom. Rendering may add vegetation and texture, but must not add
unmapped roofs or pools. Geometry and snapshot sources are stored as gzip files
for Git/deployment; raw JSON remains useful for local authoring. Loaders support
the compressed sources.

Before promoting a town into the curated catalogue, run the release contract
audit, inspect tiled artwork, and exercise the real shell workflow: select a
mapped property, inspect its meters, simulate days, collect reads, issue bills,
resolve an exception and verify the resulting ledger and world state. A custom
bake does not automatically add itself to the curated release catalogue.

Focused generator regression tests:

```powershell
.venv/Scripts/python.exe -m pytest prototypes/civic-atlas/test_town_factory.py prototypes/civic-atlas/test_preset_world.py prototypes/civic-atlas/test_two_river_forest.py -q
```
