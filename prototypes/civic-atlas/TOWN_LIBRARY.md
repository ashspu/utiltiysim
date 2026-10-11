# Connected town library

This is the current entry point for the seven-town shell. Older Fairhaven,
Riverbend and Two River Forest experiments remain available separately; their
launch scripts and historical findings do not describe this library release.

## Run locally

From the repository root on Windows:

```powershell
python -m uv sync --frozen --all-extras --python 3.11
npm ci --prefix packages/town-viewer
$env:ATLAS_VIRTUAL_SYSTEMS_ROOT = 'D:/path/to/compatible-private-virtual-systems'
.venv/Scripts/python.exe prototypes/civic-atlas/server.py --library --port 8044 --store out/civic-atlas-library
```

Open **http://127.0.0.1:8044/**. On macOS/Linux, use `.venv/bin/python` and the
equivalent environment-variable syntax. The private dependency is needed for
actual Virtual Systems billing; its compatible revision and configuration are
documented in [VIRTUAL_SYSTEMS.md](VIRTUAL_SYSTEMS.md). Without it, the native
UtilitySim charge preview remains a separate diagnostic calculation.

Each selected town initializes its own saved world on first use; large worlds
can take several minutes. Reopening reuses its history. Preserve the entire
store directory, including recipient databases, field requests and credentials.
Do not replace source geometry beneath a saved world: fingerprints reject a
mismatch. A changed town requires an explicit migration or a new store.

## Towns and maps

| Town | Target homes | Actual homes | Linked premises |
| --- | ---: | ---: | ---: |
| Two River Forest | 500 | 451 | 476 |
| Bramblewick | 500 | 476 | 501 |
| Lantern Bay | 500 | 469 | 498 |
| Ashtown | 5,000 | 4,537 | 4,769 |
| Copperhaven | 5,000 | 5,137 | 5,369 |
| Willowmere | 25,000 | 23,249 | 24,401 |
| Foxglove City | 50,000 | 46,360 | 48,662 |

Every home count is within 10% of its target. Nonresidential premises are
additional. Exact feature budgets, source fingerprints and internal review
records accompany each preset. Optional user visual acceptance is separate
from internal QA.

The map uses 860 spatial vector tiles, with generated building and landscape
materials fitted to authoritative geometry. Overview images cover distant
views; close views draw vector geometry and native-detail materials. Tile copies
share coordinates and identities. Properties, buildings and individual roads
are selectable; green space is scenery. The hideable menu keeps the map clear.

## Work through the connected system

1. Select a town, then inspect a property and its utility identities.
2. Simulate a physical day and deliver saved observations to actual MDM.
3. Bill a completed period and invoice eligible accounts. Missing or held
   readings block incomplete accounts; they are not silently estimated.
4. Inspect an exception, dispatch an existing water-leak investigation, and
   separately review and accept the authenticated field report.
5. Advance another day and receive the new observations. Repairs affect future
   consumption; prior readings and posted financial documents remain intact.

Operations are explicit and resumable. There is no automatic shared scheduler
in this release. Actual Virtual Systems uses the illustrative flat CAD tariffs
documented in its integration guide; native UtilitySim preview totals can differ.

## Build and deploy

The shell's **World configuration** exports a draft and the one-command build
instruction. Follow [TOWN_FACTORY.md](TOWN_FACTORY.md) for source generation,
identity checks, tile/overview packaging and review gates. The factory does not
automatically publish a new town or grant visual acceptance.

`node scripts/build_site.mjs` packages the static shell and maps into `public/`.
It excludes simulation databases and the private Virtual Systems source. The
legacy download and viewer remain under `/download/` and `/viewer/`.

A static Vercel deployment runs the map library, not the persistent billing
service. Hosted financial actions require a separately provisioned durable
backend, its private dependency, TLS, authentication and an allowed origin.
Use the local shell for the configured local runtime. Deployment preparation
does not establish that a hosted billing service has been provisioned.

## Verification boundaries

Geometry, identity/seam integrity, browser picking, financial reconciliation,
read provenance, field-report acceptance and retry behavior have separate
checks. A passing tile build does not certify billing, visual quality or
multi-year throughput. Source-specific evidence lives with the preset and in
the release QA output; retain that evidence when promoting a new version.
