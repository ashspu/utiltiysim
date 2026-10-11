# Generative town blocks: design proposal

Status: **design proposal, not implemented.** Written 10 October 2026 for hand-back to the Civic Atlas implementer.
It turns the manual two-block experiment into a repeatable, validated pipeline. Nothing here claims that the
pipeline, the manifest format or the QA gates exist yet.

Visual companion: the "Generative Town Blocks" design canvas (seven artboards: concept, block anatomy, manifest,
block families, pipeline, layer composition, viewer mock). This document is the authoritative text; the canvas
illustrates it.

Read first:

- [Civic Atlas map design](CIVIC_ATLAS_MAP_DESIGN.md), section 6, "Parallel experiment: whole-block artwork".
- [Whole-block study](../prototypes/civic-atlas/BLOCK_ART_STUDY.md): how the two existing plates were made and
  registered.
- [Handoff next steps](../prototypes/civic-atlas/handoff/NEXT_STEPS.md), Priority 2: "prototype constrained
  generation and validation rather than manually painting the entire town."

The acceptance target remains the owner's **B / Civic Atlas** concept image
(`prototypes/civic-atlas/handoff/references/B-civic-atlas-target.png`).

## 1. The idea in one paragraph

**The block is the drawn unit. The premise is the data unit.** Each road-bounded block gets one generated
illustration, painted by an image model from a guide rendered out of the real town snapshot. Underneath every
image sits a manifest derived from the snapshot, never from the picture: lot hit regions keyed by premise ID,
meter and service-drop anchors, frontages, and provenance. The viewer hit-tests, highlights and dims using the
manifest. Roads, utility networks, state, crews and labels stay vector or sprite layers bound to engine fields.
The picture is replaceable decoration; the IDs never move.

## 2. Why blocks rather than per-building sprites

- **Richness comes from the whole scene.** The concept's quality is lawns, mature canopy, fences, driveways and
  shared shadows painted together. Assembling those from individual props produced the repeated, sparse look the
  handoff describes as "visibly far from the reference".
- **Rotation sets never converged.** The isometric batch-v2 sheets drifted between angles. Civic Atlas has
  committed to one fixed orthographic camera, so a per-block image only needs that one view.
- **The two-block study already showed it works.** Fourteen houses across two plates kept exact picking, utility
  overlays and pan/zoom in the tested views. Agent review accepted that limited experiment; the owner has not
  accepted the full-town appearance or this proposed pipeline.
- **Whole-town plates have a larger replacement cost.** A source manifest can support picking under a town-wide
  image too, but a parcel edit invalidates a much larger plate. Resolution, memory and regeneration cost favour
  smaller independently replaceable regions.

## 3. Non-negotiables

Carried from the art handoff, the map design and the owner's direction:

1. Visual placement never creates, deletes or renumbers premises, service points, meters or registers.
2. The simulation is authoritative. Artwork carries no state. Outages, pressure, incidents and crews are overlays.
3. Utility equipment keeps explicit attachment anchors defined independently of image crops.
4. Every painted building must match its source identity, footprint, frontage and recorded physical features.
   Validate projected geometry with height and allowed eaves; a roof may project beyond a ground-level lot boundary
   without the building crossing it. Wrong building counts or unexplained geometric drift fail acceptance.
5. Generation runs offline into a pack. The desktop app never calls an image model at runtime and works offline.
6. A block whose pixel-affecting source or rendering dependencies changed is refused and falls back to native
   rendering until new art is accepted. Invalidation follows dependencies, including affected neighbouring blocks.

## 4. Two layers per block

### Image layer

- One image per block, rendered for the fixed Civic Atlas camera. The current study uses 1536 × 1024
  (about 10 source pixels per metre); production needs a second, higher-resolution level for close inspection
  (section 9).
- The image is **clipped at the curb line**: the study insets 6.8 m from the road-centreline polygon with a narrow
  inward feather. Everything outside the curb is discarded, not painted over.
- Painted content: buildings, roofs, yards, lawns, driveways, fences, trees, ground shadows.
- Never painted: roads, sidewalks, utility equipment whose state can change, vehicles, labels, selection or
  incident marks.

### Metadata layer

- One manifest per block (section 5), generated from the snapshot before any image exists.
- Lot hit regions retain source parcel and building geometry and explicit premise IDs. A parcel can contain
  multiple buildings and a building can serve multiple premises. Native source geometry remains authoritative for
  picking; the art pipeline cannot move a hit region to follow a painting error.
- Anchors: recorded meter, service and driveway positions where the snapshot supplies them. A network connection
  does not necessarily specify a wall attachment. Any derived visual attachment must be labelled as derived,
  identify its source asset and derivation version, and never be presented as a recorded measurement. Missing
  anchors remain unavailable rather than invented.
- Registration: record the complete orthographic projection, coordinate convention and image frame. Four corner
  fiducials detect crop or frame drift; they do not detect internal movement of roofs or anchors. Validate each
  building and required attachment against the guide separately, including expected occlusion.

## 5. Block manifest

Proposed schema `utility-block/0.1`. It extends the study's `civic-atlas-block-art/1` metadata (signature, block
polygon, camera, anchors, frame) with lots, anchors, family and provenance. All coordinates are town metres; image
space is reached only through the recorded camera. In the example, ground polygons use `[x, z]`; 3D positions
use `[x, y, z]`, with x east, y up and z south. The example contains one of the block's lots, not the full manifest.

```json
{
  "schema": "utility-block/0.1",
  "blockId": "blk-0417",
  "family": "postwar_grid_res",
  "seed": 42,
  "styleCard": "civic-atlas/v3",
  "camera": {
    "type": "orthographic",
    "position": [491, 120, 1004], "target": [475, 0, 922], "up": [0, 1, 0],
    "frustum": {"left": -90, "right": 90, "top": 60, "bottom": -60, "near": 0.5, "far": 2000},
    "zoom": 1, "frame": [1536, 1024], "pixelRatio": 1
  },
  "sourceSignature": "sha256:…",

  "footprint": {
    "polygon": [[412.0, 880.5], [538.0, 880.5], [538.0, 962.0], [412.0, 962.0]],
    "curbInsetM": 6.8,
    "frontages": [
      {"roadId": "rd-091", "side": "N", "lots": 4},
      {"roadId": "rd-092", "side": "S", "lots": 4}
    ]
  },

  "lots": [
    {
      "parcelId": "p-2210",
      "premiseIds": ["prm-01877"],
      "frontage": "rd-092",
      "parcelPolygon": [[452.0, 930.0], [470.0, 930.0], [470.0, 950.0], [452.0, 950.0]],
      "buildings": [{
        "buildingId": "bld-01877", "premiseIds": ["prm-01877"],
        "footprint": [[456, 935], [468, 935], [468, 946], [456, 946]],
        "type": "house", "era": "postwar", "roof": "gable", "stories": 1,
        "heightM": 5.2, "frontDirection": [0, 1], "solar": false
      }],
      "anchors": [{
        "assetId": "meter-01877", "premiseId": "prm-01877", "kind": "meter",
        "position": [468, 1.5, 941], "wall": "E", "authority": "recorded",
        "expectedVisibility": "occluded"
      }]
    }
  ],

  "streetscape": {"trees": 14, "boulevard": "grass", "fences": "partial"},

  "image": {
    "base": "blocks/blk-0417/base.webp",
    "detail": "blocks/blk-0417/detail.webp",
    "mask": "blocks/blk-0417/mask.png",
    "presentationMasks": {"buildings": "blocks/blk-0417/building-ids.png"}
  },

  "provenance": {
    "generator": "[IMAGE MODEL AND VERSION]",
    "promptHash": "sha256:…",
    "guide": "blocks/blk-0417/guide.png",
    "references": ["blocks/blk-0416/base.webp"],
    "candidates": 3,
    "chosen": 2,
    "approval": "pending | auto | reviewed",
    "reviewedBy": null,
    "qa": {"status": "pending", "report": "blocks/blk-0417/qa.json"}
  }
}
```

Field ownership:

| Field | Written by | Rule |
| --- | --- | --- |
| `footprint`, `lots`, `sourceSignature` | Manifest derivation from the snapshot | Read-only to the art pipeline. |
| `anchors` | Recorded source positions or explicitly versioned derivation | Retain asset identity and authority; never move an anchor to fit the image. |
| `family`, `streetscape` | Derivation from land use and era | Selects the style card and prompt details. |
| `image` | Pipeline | Replaceable at any time without touching an ID. |
| `provenance` | Pipeline and reviewer | Audit trail; keeps guide, output, settings and approval together. |

Rules:

- Source parcel and building hit regions are immutable. Incorrect painted placement is rejected or regenerated,
  never repaired by moving the source geometry. Presentation masks resolve to existing building and premise IDs.
- An apartment court may have multiple buildings and many premises. Picking a building resolves its premise list;
  the picture neither creates units nor forces a one-lot/one-premise relationship.
- The source/render signature covers every pixel-affecting dependency: relevant parcel/building/anchor geometry,
  terrain elevation, adjacent road and curb geometry, physical features, camera/frustum/frame, lighting, style,
  seed, and guide, mask and compositor versions. Record the dependency IDs and versions so an edit invalidates
  every affected plate, including neighbouring shadow or canopy dependencies. Exclude unrelated world records and
  transient state. Do not assume an edit always affects only one block.
- Keep an artifact key for the source/render signature plus model version, prompt, reference-image hashes and
  generated content hash. Record which accepted artifact is bound to the current source signature.
- Occupancy, incidents and outages are runtime data, not static artwork facts. Per-premise state needs identity
  masks or native overlays; dimming an entire block cannot represent one affected premise. Seasonal geometry and
  close-view detail remain separate proposals, not capabilities supplied by a colour lookup alone.

## 6. Block families

A family is a style card plus a footprint class. Derivation tags each block from land use and era. All families share
one camera, sun angle and palette so they sit together. Family descriptions are styling hints, not a source of
infrastructure: service types, voltages, equipment and premise membership must come from the saved model.

| Family | Typical content | Notes |
| --- | --- | --- |
| `postwar_grid_res` | 6–12 detached homes, two frontages | Most of a town. Era and roof type are the main levers. |
| `main_street_1945` | Attached storefronts, rear parking | Signage band, flat roofs, rooftop units; source-backed rear service access. |
| `modern_culdesac` | Irregular lots on a turning circle | Varied homes; service type and transformer positions only when recorded. |
| `apartment_court` | One parcel, many premises | Hit region is the building, not per unit. |
| `civic` | School, church, hall, playing field | Facility kind and name go into the prompt. |
| `industrial` | Plant or depot, yard, fencing | Large meter set and transformer pad are anchors. |
| `park` | Paths, ball diamond, canopy | Premise membership and equipment anchors follow the source park records. |
| `utility_site` | Substation, tower, pump, city gate | Ground and fence are painted. The equipment stays a sprite so operating state can change it. |

The two study plates are garden-rich postwar blocks. The handoff notes they are "not an adequate style library";
modest yards, older and denser housing, commercial and industrial families are required before judging the whole
town.

## 7. Pipeline

Runs offline, once per block, keyed by the manifest hash. Output goes into the town pack beside the snapshot.

1. **Derive.** Bounded faces of a planar road representation provide candidate regions, respecting grade-separated
   crossings. They are not the entire partition: explicit rules also cover dead ends, cul-de-sacs, open town edges,
   river edges and facility campuses. Assign each source parcel/building exactly once, retaining multi-premise
   membership and a native fallback for unresolved regions. Record boundary ownership and dependency IDs.
   Anchors retain recorded or explicitly derived authority. Output: one manifest per supported region.
2. **Compose.** Render the guide through the exact map camera: plain massing, footprints, lot lines, driveway stubs,
   numbered house anchors and corner fiducials. `prototypes/civic-atlas/render-block-guide.mjs` already does most of
   this for one block; generalise it to any block ID. Assemble the prompt from the family style card plus manifest
   facts: building count and identity per frontage, eras, roofs, storeys, solar, tree density and actual front directions.
3. **Generate.** Send guide, prompt and style references to an image-edit model. Request three candidates. Include
   already-accepted neighbouring blocks as references so canopy species, lawn tint and roof palette agree.
4. **Register.** Confirm the full frame was preserved by locating the fiducials. Clip at the curb mask, feather the
   ground edge, clean the alpha. Reject any candidate whose fiducials moved beyond tolerance. Frame alignment alone
   does not approve internal geometry; retain the uncut image for containment and clipping-loss checks.
5. **Score.** Run the gates in section 8. Pick the best passing candidate, or send the block back to step 2 with a
   corrected prompt. Borderline candidates go to a review gallery like `assets/town/isometric/batch-v2/index.html`.
6. **Publish.** Write the accepted base, available detail level, identity/occlusion masks and completed manifest into
   `packs/<town>/blocks/<blockId>/`. Reuse unchanged dependency signatures. Regenerate the dependency closure of an
   edit; independent blocks stay cached.

### Choice of image model

The owner prefers ChatGPT's image model for house quality, and it is a reasonable first choice: the step needs an
image-edit model that keeps composition from a guide image and follows reference images for style. Keep the model
behind a small adapter (guide, prompt, references in; candidate images out) so it can be swapped. Record the model
and version in provenance. Do not assume any model reliably counts houses: the gates, not the prompt, enforce
count and placement.

Image-to-image is required. Text-only prompts will not put eight houses where eight parcels are.

## 8. QA gates

| Gate | Check | Threshold |
| --- | --- | --- |
| `frameIntact` | All four fiducials found within tolerance of the guide positions | Hard reject |
| `buildingIdentity` | Every source building has one matched painted building; wings/dormers are not extra premises. Counts and frontage orientation agree | Hard reject on missing, added or ambiguous identity |
| `projectedGeometry` | Each match fits the source footprint, height-aware projected silhouette and allowed eaves; no unexplained lot crossing or internal frame warp | Per-building tolerance to calibrate; no centroid-only pass |
| `anchorRegistration` | Every required anchor keeps asset identity and source projection. Visible attachments fit their projected surface; occluded ones retain correct hidden position and reveal behaviour | Reject any required mismatch; do not average away failures |
| `edgeIntegrity` | No opaque pixels outside the final mask; inspect the uncut image for important clipped buildings/canopy and inspect adjacent road seams | 0 final leakage, plus visual acceptance of clipping and joins |
| `lightDir` | Shadow direction from roof segments versus the style card's sun angle | ± 10° (proposed) |
| `paletteDelta` | Mean lawn and paving colour versus accepted neighbours | Review if exceeded |
| `hazeAndText` | No atmospheric haze, baked labels or watermarks | Hard reject |
| `solarAndFeatures` | Recorded solar, pools or other modelled roof features are present | Hard reject when modelled |

Thresholds marked proposed must be calibrated on the first proof. Guide-based segmentation can assist review,
but matching a roof centroid or frame corners cannot prove source fidelity. Retain per-building and per-anchor
results, expected occlusion and uncertainty. Ambiguous matches require review; unimplemented checks remain pending,
never implicitly passing. Verify frontage access, storeys and recorded features alongside geometric registration.

Automatic acceptance is a later step. Until the gates are trusted, every block needs human approval recorded in
provenance. The handoff is explicit that agent reviews do not substitute for owner sign-off on the visual milestone.

## 9. Composition in the viewer

Draw order, bottom to top:

1. Terrain and water, generated once for the town at low resolution.
2. **Block images**, each a camera-aligned quad in world coordinates, masked at the curb.
3. Road layer: pavement, markings, sidewalks and curbs from `roads[]`. It owns every pixel between blocks.
4. Network overlays for the active lens: mains, valves, hydrants, poles, wires, meters, snapped to block anchors.
5. State and selection: selected source lot/building outline, incident halo and per-premise lens/state overlays.
   Any recolour uses validated identity masks; no block-wide outage claim for a single affected premise.
6. Crews and vehicles on the road graph, from the operations timeline.
7. Labels: street names along roads, place names, legend.

Why seams should not show:

- Street-separated blocks never touch. The road layer between them is drawn by the viewer.
- Every block shares camera, sun angle and palette from one style card, and the palette gate compares neighbours.
- Cross-road shadows need source-derived native shadow proxies or a separate registered shadow layer. Clipping a
  painted shadow does not recreate it on the road; continuity and avoidance of duplicate shadows remain proof gates.

Still unproven, and required before calling this production-ready:

- Directly touching blocks with grass-to-grass joins, and which block owns canopy that overhangs a shared edge.
- Depth or occlusion masks for vehicles, new buildings and selected assets passing behind painted roofs and trees.
- Close-view resolution. At the closest supported zoom the study's texture spans about 2.1 CSS pixels per source
  pixel and fine detail softens. Add a detail level per block, generated as tiles or upscaled and re-checked.

Zoom levels:

| Zoom | Draws |
| --- | --- |
| Town | Terrain, block images at reduced resolution, roads, landmark sprites, district tints, place labels |
| Neighbourhood | Full block images, lens overlay, incidents, crews, street names, lot hover. This is the concept-image view. |
| Street | Detail level, meter and service-drop sprites at anchors, asset IDs, property lines on request |

## 10. Edits and invalidation

- A road, parcel, footprint, elevation, frontage or rendering-contract change recomputes the affected dependency
  signatures, including neighbouring plates where a shared edge, shadow or canopy is influenced.
- Changed blocks fall back to native rendering immediately and are queued for regeneration.
- The study's "Test stale-art fallback" control is the model for this behaviour; keep it.
- Construction previews in Build mode use native rendering. Generated art appears only after acceptance.

## 11. Cost shape

- Cost scales with blocks, not homes. A few thousand homes are a few hundred blocks. A 50,000-resident town is a few
  thousand blocks.
- Three candidates per block and occasional regeneration are the main generation spend. Budget review time,
  storage, GPU texture memory and detail levels as well. Runtime state overlays require no image-model calls;
  seasonal art may require separate generation and validation.
- Accepted blocks can be reused across seeds that share a family and footprint class only when the manifest hash
  matches exactly. Never reuse art across different lots.
- Generation is not part of CI. Packs are produced by an explicit offline command and committed or distributed as
  assets, so the CI budget in `CLAUDE.md` is unaffected.

## 12. First proof

Goal: one screenshot that reads like the concept image at neighbourhood zoom, and a click on any painted roof that
returns the correct premise.

1. Generalise `render-block-guide.mjs` to render a guide and manifest for any block ID in the reference world, adding
   corner fiducials and lot lines.
2. Derive manifests for every block in a representative area: residential variety, a commercial street, a park and a
   utility site, per handoff Priority 1.
3. Generate three candidates per block through the adapter, using accepted neighbours as references.
4. Implement `frameIntact`, source building/anchor correspondence and `edgeIntegrity` first. Review projected
   geometry, expected occlusion, frontage and physical features explicitly until automated gates are validated.
5. Load accepted blocks through the existing `?art=blocks` path and compare against native assets at the same
   camera, at town, neighbourhood and street zoom.
6. Change one parcel and then a shared road/terrain dependency. Confirm all affected plates fall back and
   regenerate, while independent cached plates remain. Test a multi-premise building and an open-edge region.
7. Put the comparable views in front of the owner. Their judgement is the acceptance gate.

## 13. Decisions still open

- Which image model and adapter interface; whether candidate generation runs locally or through a hosted API.
- Exact curb inset and feather width for families other than detached residential.
- Detail-level strategy: tiled sub-generation versus upscale plus re-check.
- Canopy ownership rule for directly touching blocks.
- How much automatic acceptance to allow once the gates are calibrated.
- Whether packs ship generated art in the repository, as release assets, or generated on the user's machine with
  their own model access.
