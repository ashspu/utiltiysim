# Persistent producer hosting

The packaged readiness command is `python -m utilsim.hosted.health`. It probes
`http://127.0.0.1:8080/hosted/health` using the protected gateway credential from
`UTILITYSIM_RUNTIME_TOKEN_FILE` (or the existing environment variable). The route
checks the producer catalog under gateway authentication without granting a user
world access. `--origin` and `--token-file` support isolated owner acceptance;
the probe forbids redirects and proxies and prints no credential or private state.
The Docker image runs the same command as its health check. Readiness means this
producer is reachable and its catalog opens; it does not assert VS, billing or
whole-stack readiness.

Greg selected Ash's existing persistent host for the coordinated B system on2026-10-11. Root coordinates actual host access and resource/cost inspection; no new paid host is implied. Vercel remains the public UI/WorkOS gateway. Local implementation and container checks do not establish a production connection.

Run one producer process/container with persistent block-backed data owned by the service user (UID10001). Keep journal, immutable templates and world SQLite files together at stable paths. The earlier Azure VM candidate is superseded by Greg's existing-host decision; its storage requirement remains the same: preserve SQLite locking, fsync and recovery on the selected host's durable volume.

Required before deployment: subscription/project/region and budget decision; authorized compute resource; mounted durable data disk; secret distribution; restricted TLS ingress accessible only to the Vercel gateway; monitoring and bounded request concurrency; consistent backup/restore and volume replacement drill. No autoscaling or multi-host shared SQLite writers. A single worker may accept multiple requests, but SQLite serializes writes; distinct world files isolate daily histories. Longer jobs need a persisted command queue with polling before larger presets are enabled. A 31-day per-request bound is not a performance SLA.

Suggested future acceptance: same immutable hashes after import, independent worlds from each approved preset, configuration/ownership checks, process kill and VM restart, retries after partial creation, one-day advance and observation-only connector output, restore onto replacement disk, revoked-grant denial, then full WorkOS gateway and illustrated-viewer browser verification. Local tests are not deployment evidence. Do not connect the historical local demonstration databases as mutable runtime worlds.

The accepted Lantern snapshot is approximately 8 MB JSON. The full internal `/map/snapshot` route is useful for local verification. Before proxying it through Vercel, design static authenticated versioned delivery or scoped snapshot pages within platform response limits; do not assume the full snapshot can pass through a Function gateway. Original artwork also needs authenticated immutable hosting and routes mapped to the saved instance's source revision. Current service returns record/binding data, not a published illustrated viewer.

Local launch after installing repository dependencies:

```sh
python -m utilsim.hosted --import-reviewed /reviewed/lantern-harbour-final --data-root /data --source-id lantern-harbour --grant-town-id lantern-bay-500 --name 'Lantern Harbour'
# Supply UTILITYSIM_RUNTIME_TOKEN securely in the process environment.
export UTILITYSIM_DATA_ROOT=/data
uvicorn utilsim.hosted.server:from_environment --factory --host 127.0.0.1 --port 8080 --workers 1
```

The Dockerfile now pins the Python3.12-slim manifest digest, uses uv0.13.0 and `uv sync --frozen --no-dev --no-editable` with the repository lockfile, labels the source revision, creates a writable data mount point and runs as UID10001. uv's documented Docker workflow supports frozen/noneditable installs ([official uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/)). Build context is repository root; `.dockerignore` excludes private token/database/runtime artifacts. Do not ship local secrets or world data in the image.

Actual Linux image build/boot evidence is collected by the narrow `hosted-runtime-container` PR-ready/manual workflow and `scripts/check_hosted_container.py`: non-root persistent volume, authenticated health, distinct gateway/machine credentials, actual four-service observations with availability, exact retry after process restart, and checked stopped-volume restore. The workflow performs no registry push or deployment and uses only ephemeral test secrets. Until that run succeeds the Dockerfile remains a build candidate, not verified Linux or hosting evidence. Estimated incremental8–10 runner minutes/run (32–40/month at4 runs),15-minute timeout; drafts run nothing and obsolete runs cancel.

Greg selected Ash's existing persistent host for B on2026-10-11; root coordinates provider/access/budget discovery, with no new paid host implied. The shell remains on Vercel. The agreed deployment composition is owned separately in `deploy/connected-stack/`: private producer8080 and controller8027 share an inspected private/loopback network; only TLS edge443 is public. Bind the producer volume and every VS owner to stable original paths. Use secret files for gateway token, machine key and controller service token, never browser bootstrap or general gateway credentials in the worker. The connection capability goes into the fixed private controller's token file. Authenticated readiness and coordinated paused/stopped backup are deployment gates. Do not mark a static shell release, local HTTP fixture or producer-only restore as connected production acceptance.
