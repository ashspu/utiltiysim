# Town library release

The static shell and saved map tiles can run on Vercel. Physical simulation and
billing require a persistent process and durable storage. A successful static
deployment alone does not prove that the billing runtime is connected.

## Local runtime

From the repository root, install the project and start the library:

```powershell
python -m pip install -e .
python prototypes/civic-atlas/server.py --library --port 8044 --store out/library-worlds
```

Open `http://127.0.0.1:8044/`. Each town gets its own saved world. Opening a large
town initializes its physical history and can take several minutes. Existing
stores are checked against their saved map and snapshot; a source mismatch is
rejected instead of silently attaching customers to a different map.

The source snapshots and geometry are committed as deterministic `.json.gz`
files. The runtime and tile generator can read those directly. Large uncompressed
working copies are intentionally not required in a fresh checkout.

To connect the separately installed Virtual Systems application, set
`ATLAS_VIRTUAL_SYSTEMS_ROOT` to its checkout before starting the server. The shell
then provisions dedicated recipient stores alongside each town. It uses actual
Virtual Systems received-reading, invoice and Subledger transactions. The current
adapter explicitly uses illustrative flat CAD tariffs and reports that shared
automatic scheduling is not configured; it does not silently translate the native
UtilitySim tariff model.

A water-service investigation can authorize a real on-site visit, repair an
existing leak, and deliver the saved field report through an authenticated
per-assignment runtime. A visit with no active leak returns `not_found`. Receiving
a report leaves clerk review pending; accepting it is a separate operation.
This local supervisor path uses zero report delay and does not claim a shared
workforce resource scheduler. Credentials stay in the town's durable private
store. Back up that store together with its recipient and field databases.

## Persistent container

The compose definition binds only to localhost and keeps world databases in a
named volume. Set a private `ATLAS_API_TOKEN` in the process environment before
starting it. Do not put the token in source control or URLs.

```powershell
docker compose -f deploy/civic-atlas/compose.yaml up --build -d
```

For actual Virtual Systems in the container, set
`ATLAS_VIRTUAL_SYSTEMS_ROOT_HOST` to the separately installed private checkout,
then add `-f deploy/civic-atlas/compose.virtual-systems.yaml` to the compose
command. This mounts the dependency read-only; it does not publish private code.
The tested performance dependency is commit
`13271e12111d62be3a47e6a9199e83b0efd6a764`, based on
`32c91ff2e8b926e4be47a7800df5935f9cf724ec`. Its local patch/provenance accompany
the release report and must be applied only to an authorized private checkout.
The optional container integration remains unverified without a Docker runtime.

For a hosted runtime, terminate HTTPS in front of the service, set
`ATLAS_ALLOWED_HOSTS` to its explicit hostname, and set
`ATLAS_ALLOWED_ORIGINS` to the shell's exact HTTPS origin. Enter the runtime URL
and access token in the shell's Connections view. The shell stores them in the
current browser tab session. Back up the durable volume while the runtime is
stopped or use SQLite's online backup API; copying live database files alone is
not a valid backup procedure.

The container definition is a packaging option. Its availability is separate
from verification on a machine with Docker installed. Virtual Systems is a
separately configured application; its private source and credentials are never
included in this public image or static site.

## Static release

```powershell
node scripts/build_site.mjs
```

The build requires all seven catalog towns, their tile manifests, premise
indices, landmarks, overviews and tile chunks. It rejects tiles whose source
hash differs from the packaged geometry. It copies only browser artifacts to
`public/`; source snapshots, credentials and databases are excluded. The old
desktop download page remains available at `/download/`.

Vercel's existing `vercel.json` builds this static output. A disconnected shell
must show its unavailable runtime state and disable mutations. Do not present a
static preview as a fully connected billing system.

## Release acceptance

Use fresh disposable stores for mutation checks. Never point `--exercise` at a
user's saved world. The acceptance layers are intentionally separate:

1. `release_contract.py`: complete premise, parcel, building, block, street,
   account and service identity coverage; residential tolerance and feature budgets.
2. `check_tile_contract.py`: complete selectable feature coverage, exact road
   geometry, premise lookup and identical feature copies across tile boundaries.
3. `check-library-map.mjs`: real pointer selection, device-resolution rendering,
   tile-junction screenshots and browser errors. Review screenshots separately.
4. `check-library-api.py --exercise`: durable UtilitySim observation ingestion,
   local billing provenance, retry safety and a physical meter replacement whose
   next observation comes from the replacement device.
5. `check-library-shell.mjs`: roof selection to account details, simulated day,
   receiving observations, local billing and reload persistence through the UI.
6. The configured Virtual Systems integration must additionally demonstrate its
   own received readings, invoices, balanced ledger and authorized work flowing
   back to the physical world. Local billing checks do not substitute for this.

`check-virtual-system-api.py --exercise` tests a full town's actual recipient
provisioning, observation import, invoice/ledger posting, explicitly reviewed
synthetic high-consumption holds and replay safety on a disposable API server.
`test_virtual_field.py` additionally injects a lost response after the recipient
commits a report and verifies recovery without a second repair or report. Its
synthetic leak exists only in the test fixture; the product never creates a fault
to make a repair appear successful.

Publish only after the final source revision passes these gates and visual
review. Historical QA output for an earlier town layout is not acceptance of a
later layout. Keep screenshots and reports associated with the tested revision.

The final scalable recipient gate is `check-town-recipients.py --preset ID
--store DEDICATED_QA_DIRECTORY --output REPORT.json`. It uses the entire saved
source, simulates two days, sends actual observations, bills all eligible
contracts, invoices complete accounts, audits every account/installation and
contract, checks the independent balanced ledger, then advances another day and
checks replay. It never automatically approves a hold. `check-virtual-partition.py`
produces the complete per-contract/account disposition evidence.
