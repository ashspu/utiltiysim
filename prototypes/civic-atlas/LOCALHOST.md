# Civic Atlas on Windows

**Current library:** use [TOWN_LIBRARY.md](TOWN_LIBRARY.md) to run all seven
towns and the connected shell on port 8044. The sections below are historical
notes for the preserved experiments on ports 8041–8043. Their old counts,
planned-town statements and integration limits apply only to those versions.

## Two River Forest experiment — 10 October 2026

Run `prototypes/civic-atlas/start-local.ps1 -Preset two-river-forest-500`. The separate saved store is `out/civic-atlas-two-river-forest-500-v2`; port 8043 serves the shell and the new illustrated map at `/presets/two-river-forest-500/review.html?stage=hybrid`. The map's tools switch through the image/SVG/system-binding stages; Pilot area reveals the higher-resolution neighbourhood. Every one of 476 property regions and 103 road segments is selectable. The snapshot has 451 homes (user-approved 450–550 tolerance), 100 pools, no solar, one school, one church, 16 shops, six industrial premises and one water-works premise. It retains seven simulation days and 1,384 meters.

`two_river_forest.py` authors the fixed source, `two_river_render.py` builds the SVG stages, and `two_river_streets.py` clips accesses at pavement and selects saved pole records with a global 35 m spacing minimum. The displayed 164 poles are a subset of network equipment; 54 hydrant symbols use curb display positions with their original network positions retained. `test_two_river_forest.py` checks counts, geometry, blocks, feature corruption and street details. The bulk live-property check found writer-lock contention in inspection; `World.read_db()` now provides an enforced read-only transaction for WorldMap inspection, with concurrent-reader regression tests.

The generated illustration is an experimental underlay. Its exact painted pool count, zero-solar appearance and building footprint alignment are not certified; the data and controlled SVG are. The school and some roofs were reshaped by the image model. Full-town raster output is 1536×1024; only one 240×160 map-unit pilot has a separate detail texture. Manual concept interpretation, remaining block tiling/seams, and explicit identity migration for future geometry changes remain open. Do not replace an existing saved store by rerunning the authoring script. The stage gallery and prompts are served at `/presets/two-river-forest-500/process-report.html`. No visual-release approval has been claimed.

This continuation uses `codex/civic-atlas-handoff` at `cf31197` as its base. The local branch is `codex/civic-atlas-localhost`. It preserves the original town, artwork and UtilitySim engine; newer `main` changes have not been merged.

The confirmed milestone remains **500 homes**, not 500 residents: Fairhaven has 475 occupied homes, 1,185 residents, 25 nonresidential premises and 1,500 physical meters.

## Start or reopen

From the repository root:

```powershell
python -m uv sync --frozen --all-extras --python 3.11
npm ci --prefix packages/town-viewer
./prototypes/civic-atlas/start-local.ps1 -OpenBrowser
```

Dependencies only need installation once. Subsequent launches reuse the SQLite store and keep the server running in the background. The launcher detects an existing Fairhaven server and refuses an occupied port belonging to another application. After backend edits, use `-Restart`; it will stop only a process whose command line matches this checkout's server and store.

- Welcome: http://127.0.0.1:8041/#welcome
- Town: http://127.0.0.1:8041/#map
- Quality report: http://127.0.0.1:8041/#quality
- Store: `out/civic-atlas-town500-v2/world.sqlite`
- Logs: `out/civic-atlas/server-8041.stdout.log` and `.stderr.log`

Keep the store to preserve simulation history. Restarting never recreates an existing world. The server remains loopback-only. Authentication and external applications are not configured.

## Added in this continuation

**Property reading history:** select a roof, then choose **View reading history**. The Activity page reads saved observations and physical quantities for that exact property, pages through 14 completed days at a time, and exports the displayed records as JSON. Missing readings remain unknown. Return to property preserves the selected map entity and framing.

**Quality checks:** the sidebar opens twelve read-only checks covering counts, unique identities, parcel validity/nonoverlap, footprint containment, road-pavement exclusion, connected streets, frontage, open-space conflicts, service connectivity, database integrity and latest-day observation coverage. The downloadable report contains a source SHA-256 and the saved day. This does not certify painted driveways, vehicle access, aesthetic fidelity or larger-city performance. Artwork registration and interaction require the separate browser suites.

**Portable verification:** the four primary browser suites and the new records suite discover installed Edge/Chrome/Chromium on Windows, macOS or Linux. `CHROMIUM_PATH` and `PLAYWRIGHT_MODULE` remain overrides; the renderer's legacy `ATLAS_CHROMIUM` and `ATLAS_PLAYWRIGHT_MODULE` overrides also work. `ATLAS_URL` selects a different server.

## Verify

```powershell
./prototypes/civic-atlas/check-local.ps1
```

This runs the 17 Python tests, prototype Ruff checks and five sequential browser suites. Browser tooling is installed into ignored `out/` if absent. The default verification does not advance the world. Add `-Advance` to explicitly commit one physical day and verify persistence through reload; each such run adds one day.

The initial Windows verification passed on an Intel i5-6600K, 16 GB RAM, Edge 155, Python 3.11 and Node 24. This records the test environment; it is not a measured FPS guarantee. Outputs are in `out/civic-atlas/review-town500/`, `workspace-review/`, `welcome-review/` and `review/`.

The original handoff's 198 manifest entries were verified against their original Git blobs. Windows checkout CRLF conversion changes raw text-file hashes; current source edits also intentionally differ from that historical manifest. Do not regenerate the historical manifest to hide those differences.

## Remaining product work

The legacy Fairhaven town still uses a regular grid and twelve illustrations repeated across 58 placements. Configure is inspection-only; construction is a browser sketch/export. Auth, external integrations, pressure/voltage analysis and the broader specialist workflow inventory are future work.

## Map workspace and image-led presets

The map fills the viewport. Navigation starts hidden; its menu can expand, collapse to icons, or hide completely. Map options hold layers, optional address search/destinations, zoom, input settings and sketch controls. Property records open on demand in a dialog; there is no permanent right inspector. The source records/history pages remain available.

The accepted direction is now a **fixed library of four ~500-home towns, four ~5,000-home towns and two ~50,000-home cities**. `web/presets/catalog.json` distinguishes available prototypes from planned entries. **Only Riverbend is implemented; the other nine are planned.** The discarded procedural organic experiment is not part of the application.

Start Riverbend separately:

```powershell
./prototypes/civic-atlas/start-local.ps1 -Preset riverbend-500 -OpenBrowser
```

- Live 3D: http://127.0.0.1:8042/#map
- Image / vector comparison: http://127.0.0.1:8042/presets/riverbend-500/review.html
- Live source checks: http://127.0.0.1:8042/#quality
- Store: `out/civic-atlas-riverbend-500-v2/world.sqlite`

Riverbend contains 500 homes, 525 premises, 1,191 occupied-household residents and 1,530 actual meters. These are a new preset's records; the legacy Fairhaven store remains intact. A preliminary `riverbend-500-v1` development store, if present, is retained but no longer used by the launcher.

### Authoring and identity contract

1. **Concept:** `concept.png` was generated using the built-in image tool with the user's Whitby reference. The user approved this visual direction, not final vector or 3D fidelity.
2. **Semantic tracing:** `roads.json` and `zones.json` hold hand-refined paths and land reservations from the image. `trace_plan.py` produces `master.svg`, which contains real editable vectors, no embedded raster. The nine supplied zoning categories are retained; water is an additional physical surface.
3. **Bake:** `preset_world.py` reads that SVG, fits parcels/buildings within its street and reservation constraints, builds the real UtilitySim utility/customer entities, and refuses failed geometry. It writes `snapshot.json`, `town.svg` and `bindings.json`. The small frontage/appearance variation happens once at authoring time with a fixed seed. Loading a preset never generates new streets or lots.
4. **Binding:** every SVG parcel and building carries `data-premise-id`. A property binding records the preset/revision plus premise, building, parcel, account, service-point and meter IDs. Household attributes live on the premise; there is no fabricated separate household table. Meters resolve through `meter.servicePointId → servicePoint.premiseId`. IDs are scoped by the preset/world. Clicking an SVG building links to its same 3D house and saved records.
5. **Freeze:** source SVG and concept SHA-256 values are retained. A changed master SVG cannot initialize a new runtime until rebaked. Existing stores resume their own saved snapshot. Future geometry revisions require an explicit migration map; rebaking is not a migration and must not overwrite a user's history.

```powershell
.venv/Scripts/python.exe prototypes/civic-atlas/trace_plan.py
.venv/Scripts/python.exe prototypes/civic-atlas/preset_world.py
.venv/Scripts/python.exe -m pytest prototypes/civic-atlas/test_preset_world.py -q
node prototypes/civic-atlas/check-preset.mjs
```

Riverbend has fourteen live checks: the twelve baseline checks plus property/entity bindings and protected-land exclusion. All open-space polygons retain their holes. Shared curved parcel vertices retain full precision to prevent rounding from creating overlap slivers. The test suite also rebuilds the fixed source identically and verifies every SVG/property/meter binding, runtime persistence, and a deliberately corrupted mapping.

The browser acceptance clicks twelve actual rendered roofs across the town, checks their premise/parcel/building/meter references and saved readings, follows SVG → 3D selection, checks zoning, and verifies reload does not change source or simulation state. `check-map-workspace.mjs` checks hidden/collapsible navigation, optional tools and record dialog, 1600/1024 layouts, source selection and pan.

### Visual acceptance and larger presets

This is a working geometry and metadata prototype, not final artwork. The vector plan preserves the concept's composition; its fitted 500 houses are not a pixel-for-pixel trace of painted roofs. Curved curb joins, driveway presentation, park furnishing, civic campus coverage, agricultural texture and the 3D visual treatment still need close visual review. Do not label the 3D version approved based on source checks.

The nine remaining presets need individual generated concepts and reviewed master plans. At 5,000/50,000 homes, use district-level vector authoring, spatial tiles, instanced buildings, simplified distant geometry and lazy record lookup. A single generated image cannot provide accurate individual parcel geometry at those scales. No large-town performance claim has been made or measured in this milestone.

### Detailed reconstruction studio (latest revision)

The user rejected the coarse vector/property treatment above. `/presets/riverbend-500/review.html` now opens the reconstruction studio; `review-v1.html` preserves the previous whole-town prototype and its record links. **The revised geometry has not migrated into the saved 500-home world.** Passing the old world's fourteen checks does not approve this new design or validate all of the reference's painted houses.

The studio provides full-image SVG artwork, including outer farm fields, farm buildings/access tracks, hedgerows, woodland, riverbanks, gardens and original parcel linework. The exported SVG contains no raster image. The optional Reference/Overlay mode loads the original image separately for visual comparison. `landscape.geojson` contains 31 field areas plus woodland, greenspace and water boundaries in local image coordinates (1.35 metres/pixel), with holes preserved. Classification is a draft: a green patch is not necessarily a public park. `landscape-review.json` records reviewed exclusions and pins them to the source image hash and feature bounds. The Garden residential patch formerly labelled `field-013` is excluded from farmland; remaining landscape IDs are stable. All authored residential parcels are checked against the mapped farm fields. `farm-buildings.json` adds 31 separately traced roof footprints across ten outlying farmstead groups. These retain independent IDs and deliberately have no assigned premise/customer IDs. Their 4.5 m display heights are illustrative, not measured metadata. The Landscape 3D view makes the extracted land polygons (including holes) independently selectable, retains the approved artwork texture in its original coordinates, and extrudes the farm footprints. Farm building and field picks never fabricate a link to a utility account.

The detailed conversion now covers **205 homes**: 28 in `orchard-parcels.json`, 21 in `garden-parcels.json`, 18 in `hazel-parcels.json`, 28 in `market-north-parcels.json`, 7 in `riverside-west-parcels.json`, 28 in `meadow-west-parcels.json`, 31 in `meadow-east-parcels.json`, 21 in `parkside-north-parcels.json`, and 23 in `willow-bend-parcels.json`. Their shared vertices, curved street frontage, footprints, driveway polygons and gardens feed `reconstruction.json` and `reconstruction.svg`. All nine district identity-map files lock authored lots to existing premise IDs; geometry changes must not rematch IDs by nearest neighbor. Garden also has a connected rear pedestrian route and an authored green pocket with unassigned ownership. Hazel preserves the reference cul-de-sac and rear footpath, adds a connected woodland pocket, and extends the eastern road to Market Street. Market North adds the curved court and its interior footpaths. Market Street’s western centerline was corrected against sampled asphalt in the reference before extending its junction eastward. `district_geometry.py` compiles these explicit manual coordinates; it does not create new lots. Footpaths terminate at the exact curb boundary rather than projecting into the carriageway. The Property 3D study extrudes the same 205 footprints, displays the same parcel/curb/path geometry, and links to actual live records and saved readings. Its surrounding ground artwork remains a visual reference, not a converted full-town 3D model.

Recorded physical settings follow those identities. The 205 homes include twenty-eight solar homes and two pools, rendered only where their records enable them. PV modules must fit the authored roof; the pool has a curated position in `site-details.json` and must avoid the building and driveway. Saved building height is the wall/eave height, matching the live viewer. `roof_geometry.py` constructs continuous gable and hip surfaces over the actual rectangular or L-shaped footprint; it adds an illustrative roof rise above the recorded wall height. The current 205 homes have 117 gabled and 88 hipped roofs. SVG shading and the 3D mesh consume the same planar roof faces. Solar modules are fitted wholly within those faces, raised 6 cm above the roof, and their count follows recorded capacity. Decorative windows follow the recorded story count and actual wall edges; doors face the driveway. Pitch and opening positions are display choices, not measured engine attributes. These remain architecture studies awaiting full-town visual review.

Riverside West preserves seven individually traced homes beside the river. Two rear lots reach the public street through explicit 3 m shared driveways; these access layouts are draft interpretations, not public roads or newly assigned customers. The northern property’s traced outbuilding remains nested under its parent premise, and clicking its SVG or 3D roof selects that parent record. Shared access and accessory geometry are validated for containment, public-street connection and parcel separation.

Meadow West adds 28 reference-traced homes around an irregular loop, a rear-garden path network, an internal planted pocket and a woodland wedge. The open spaces preserve the source texture and are clipped against actual street, footpath and parcel geometry; ownership is unassigned. The four additional solar homes follow their locked records. The previous 102 property shapes, driveways, bindings and physical settings are unchanged.

Meadow East adds 31 homes around a planted cul-de-sac and a longer diagonal loop. Its street connections use the existing Market and Meadow West geometry. Two additional planted pockets preserve the reference texture, with ownership unassigned. The new homes include five recorded solar installations. All previous 130 parcels, footprints, driveways, IDs, physical settings and roof models are unchanged. A numerical zero-width spike on one rotated roof face is repaired only when polygon area is preserved.

Parkside North adds 21 homes, a connected court, a curved collector and a walking route along the park edge. The planted pocket is clipped against roads, walks and private parcels and retains the source texture. A second traced outbuilding is nested under PN-W01 / P-00253 and selects the parent customer record. Previous 161 home geometries and bindings remain unchanged.

Willow Bend adds 23 homes around two cul-de-sacs and the southwestern bend. The new streets connect to the existing Meadow East return and diagonal street. The woodland corridor and outer farm fields remain outside private lots. Existing 182 property shapes, IDs, roof models and physical settings are unchanged.

Remaining: reconstruct the other 295 homes and nonresidential sites, review landscape classifications, correct the full street graph against the reference, build a reviewed geometry migration preserving all record identities/history, then review the complete 3D appearance. `master.svg`, `town.svg`, and the saved world's coarse v1 geometry are intentionally distinct from the new authoring draft.

Authoring-only dependencies (not server requirements):

```powershell
python -m uv pip install --python .venv/Scripts/python.exe scikit-image==0.26.0 vtracer==0.6.15
.venv/Scripts/python.exe prototypes/civic-atlas/reconstruct_plan.py
.venv/Scripts/python.exe -m pytest prototypes/civic-atlas/test_reconstruction.py -q
node prototypes/civic-atlas/check-reconstruction.mjs
```

`reference-trace.svg` is a baked visual authoring asset; the authoring script reuses it when present. The runtime never invokes a raster tracer. The reconstruction checks exercise parcel nonoverlap/shared boundaries, footprint containment, actual street frontage and driveway contact, stable IDs and metadata, landscape polygon validity, SVG/3D pointer selection, saved history, SVG and 3D field/farm picking, pan/zoom, narrow viewports and unchanged saved-world state. These do not replace visual approval.
