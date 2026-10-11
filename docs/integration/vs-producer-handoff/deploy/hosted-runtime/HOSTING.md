# Future compute deployment

No resources, costs or runtime deployment were provisioned in this work. Greg separated online initial setup (shell-owned durable setup drafts) from future online compute on 2026-10-11. Vercel remains the public UI/WorkOS gateway.

Recommended first compute deployment: one Linux Azure VM with one attached managed **data** disk, running this service as a single container or systemd process. Mount the durable ext4 volume at `/data`, owned by the service user (container UID 10001). Keep journal, immutable templates and world SQLite files together. This recommendation preserves the existing SQLite transactional engine with no storage rewrite. Azure managed disks are block volumes attached to VMs; Azure temporary disks can lose data during maintenance/redeployment/stop. [Microsoft disk documentation](https://learn.microsoft.com/en-us/azure/virtual-machines/managed-disks-overview).

Azure Container Apps supports ephemeral container/replica storage and Azure Files mounts. Choosing it would require separately proving SQLite locking, fsync and crash behavior on the selected network filesystem. It is not the default for this unchanged engine. [Microsoft Container Apps storage documentation](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts).

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

The included Dockerfile is a packaging candidate, not a verified build. Build context is repository root. It includes the existing Python engine dependencies. Do not ship local secrets or world data in the image.
