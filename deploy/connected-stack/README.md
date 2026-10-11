# Connected B single-host deployment candidate

This package prepares provider-neutral infrastructure for UtilitySim B. It does not provision a host, publish an image, change Vercel or start a demo. Its example deliberately fails preflight. Use the existing authenticated Vercel shell and dedicated setup store; deploy the producer and private VS controller only after their owners provide tested artifacts and the host/budget decision is settled.

## Current readiness

- Public base is main `60283b932b039b5a47032c97850fd422d74a8826`. Producer candidate was `44e5af22df6e552773a4554c912bd05e0b764c9b`; private recipient candidate `32c91ff2e8b926e4be47a7800df5935f9cf724ec` plus interval correction `17c9e4ffd685fa0d8fc7d8a0593f5fbf55863eff`. These are provenance references, not deploy-ready image revisions. Replace them with reviewed integrated successors when published.
- Producer owner supplies Docker packaging and `/hosted`/fixed-world `/machine` runtime. Private VS owner supplies connected startup, scoped credentials, authenticated readiness and actual idle/checkpoint hooks. Current VS control service binds `127.0.0.1:8027`, `GET /connected`, `POST /connected/commands`; command acceptance is asynchronous and is not an idle barrier.
- `compose.json` is JSON-form YAML; portable tests parse its structure and the fetched official Compose draft2020-12 JSON schema validates it. Local tests exercise configuration rejection and genuine SQLite archive/hash/cursor recovery. No Docker daemon, Caddy binary, age binary or Linux volume was available here; no container boot, TLS handshake, encrypted-backup execution or cloud restore is claimed.
- No new CI, schedule, resource or charge. Existing Ash host versus new budget remains an external decision. Ashtown stays stopped.

## Network and storage boundary

```text
browser -> Vercel WorkOS gateway -> https://actual-producer-host:443
                                      edge TLS -> producer:8080 /hosted/*
producer machine/control bridge -> 127.0.0.1:8027 private VS controller
private VS RemoteWorld port      -> 127.0.0.1:8080 /machine/worlds/pinned-id
```

Controller is a separate private image with `network_mode:service:producer`. This shares the network namespace so its strict loopback listener works; it does not share PID namespace, credentials or filesystem. Only443 is published. Edge never proxies `/machine`, `/connected`, metrics or arbitrary paths. Raw9MiB machine feeds remain on loopback, avoiding the Vercel Function4.5MB body limit. Producer has only the internal owners network; controller inherits it, so neither can call external APIs. Any real payment-provider network access requires a separately reviewed constrained design; this candidate assumes the current synthetic provider evidence.

Both Python images must support Python3.11+, UID/GID10001, read-only root filesystem, `/tmp` tmpfs and the supplied entrypoint wrapper. All capabilities are dropped; no privileged mode, Docker socket or public private-source mount. Edge requires a Caddy binary and binds unprivileged8443 mapped to443. TLS certificate renewal is an operator action; this template does not enable ACME or a paid DNS service. Edge health validates config; the acceptance drill must additionally test actual public TLS/readiness. Connection credentials remain server-side in Vercel; workers never receive controller/admin credentials.

Mount an already formatted durable local block filesystem at the configured host `dataRoot`, default `/srv/utilitysim-b/data`. Each owner gets its own stable container `/data`:

| Host directory | Container | Contents |
| --- | --- | --- |
| `dataRoot/producer` | producer `/data` | catalog, templates, world DBs, creation/setup journals, machine binding/outboxes and public field owner if configured |
| `dataRoot/controller` | controller `/data` | VS runtime, Billing, ledger, evidence, controller cursors, `control.sqlite`, optional VS field owner |

Do not change these original container paths after plans/run manifests are pinned. Managed v1 paths are absolute and relocation is unsupported. The complete owner checkpoint must explain the remote physical-world owner and every field owner; no two writers may operate one owner file. A missing mounted filesystem or volume identity marker refuses launch. Compose bind mounts set `create_host_path:false` to avoid silent empty directories. Scripts never format, delete, migrate, generate a replacement world or pull/build images automatically.

`ownerFiles` binds each real owner to its service and original relative database path. Preflight refuses missing/linked files and owner aliasing. Every backup manifest retains these bindings, clock/revision, image/source pins and file coverage for **both** full data trees. When field is enabled, bind both `producerField` and private `field`. The VS-only `backup-ready --workers-stopped` inventory is not a complete producer/catalog/field backup and cannot be treated as the combined checkpoint hook. The hooks must reconcile the producer readiness/binding proof with the private owner inventory under the actual barrier.

## Required owner interface

Configure exact argument arrays in `deployment.json`; no shell evaluation or credential arguments. Protected secret JSON maps contain only the declared environment names and values. Wrapper loads those into the service process, avoiding Docker environment metadata containing token values. If an owner launcher supports `--token-file`, point it at an image-specific protected file path prepared by that owner; do not invent flags or duplicate runtime binding logic here.

`healthCommand` must verify authenticated fixed-run readiness and all required owner identities, not merely a listening socket. Producer checks must include source/world/machine binding and mounted world; controller checks must validate its actual fixed run, handler set and clock binding. Each command returns exit0 only when ready, within12s, with no raw credentials in stdout/stderr. The deployment wrapper discards health output.

Controller `pauseCommand` and `checkpointCommand` are **required integration hooks, not implemented VS endpoints**. They run inside the private controller image with protected environment values and must return bounded JSON:

```json
{"runId":"actual-fixed-run","clock":"2026-07-18T00:00:00Z","controllerRevision":7,"paused":true,"idle":true,"workersStopped":true}
```

Checkpoint additionally returns `complete:true` and `owners:["runtime","world","catalog","billing","ledger","evidence","controller"]`, plus `field` when enabled. Include actual `control.sqlite` and controller state, not just historical five-owner snapshots. The hooks must acquire the owner's exclusive phase/checkpoint barrier, reject active business/controller leases, wait until accepted pause is executed, stop independent writers and prevent any new command from reentering until stack shutdown. The pause and checkpoint clock/revision must match. A `202 accepted`, `phase:paused` or runtime-only lease check is insufficient. Do not implement hooks by forging these booleans or by inferring them from HTTP command acceptance.

No resume occurs in recovery scripts. The owner startup must reopen the paused run without automatically resuming; operator resume is a separate authenticated command after verification. Launching the service's command worker is distinct from executing business advancement. Confirm restart behavior with the VS owner before marking deployment-ready.

## Host preparation and launch

1. Obtain authorized host/disk/region/budget, DNS443 reachability, Docker+Compose, Python3.11+ and reviewed age binary. A one-host block disk avoids changing SQLite semantics; still test locking/fsync on the actual filesystem. Restrict SSH/management ingress. Do not expose8080/8027. Do not rely on an assumed stable Vercel egress address.
2. Mount the already formatted durable filesystem, record its device/UUID and configure boot mounting. Scripts do not create or format a disk. Install reviewed deployment files to `/opt/utilitysim-b/deploy/connected-stack` with root-owned read-only code. Keep host backup/TLS directories disjoint from data. Backup destination must be protected mode0700, with encrypted copies exported to an approved off-host store; a directory on this host is only staging.
3. Copy `deployment.example.json` to an ignored/operator-controlled `/etc/utilitysim-b/deployment.json`. Replace every null/empty command with real owner-provided values; retain `candidate` until reviewed producer-container, connected-controller and Linux restore evidence exists. No fake DNS hostname/image can substitute for evidence. Pin image digests and integrated source SHAs, actual run/fingerprint mapping, logical volume UUID, TLS hostname and backup recipient. Declare whether field is included.
4. Prepare `/etc/utilitysim-b/producer.json` and `controller.json` outside Git from the owner's private credential process. They must belong to UID10001, mode0600/0400; minimum32 characters for token/password/secret names. Use separate gateway, fixed-world machine, controller service and runtime actor credentials; the wrapper does not create permissions or validate application scope. Check the owner's startup contract and required file layout. Real TLS `fullchain.pem`/`privatekey.pem` must be readable by10001; private key mode0600/0400 and `/tls` directory traversable by that UID.
5. Fetch verified producer/controller/Caddy images by digest using the approved registry/account outside these scripts. Controller private code stays in an authorized private artifact. Obtain actual acceptance evidence in a disposable run before enabling production configuration. The initial restore drill uses owner-run acceptance tooling; `linuxRestoreAcceptance` cannot be populated with unit-test results.
6. Set `readiness:deployment-ready` only after the preceding gates. For a new empty mounted filesystem, initialize the logical volume marker and owner directories; the command refuses existing data and never formats/deletes:

```sh
sudo python3 /opt/utilitysim-b/deploy/connected-stack/stack.py initialize-volume --config /etc/utilitysim-b/deployment.json
sudo python3 /opt/utilitysim-b/deploy/connected-stack/stack.py preflight --config /etc/utilitysim-b/deployment.json
sudo python3 /opt/utilitysim-b/deploy/connected-stack/stack.py up --config /etc/utilitysim-b/deployment.json
```

Preflight requires Linux, real mounted volume/marker, correct UID ownership, required secrets, matching current TLS certificate/key, local digest-pinned images, a Docker daemon and Compose configuration validation. It suppresses secret-bearing command output. Failed launch/health may leave stopped/unhealthy containers; inspect locally and use `stack.py stop` without deleting data. Expired TLS does not prevent the stop action.

7. Only after the disposable boot/kill/reboot/restore drill, install the provided systemd unit, adapting paths if needed and preserving `/data` inside each container. Systemd starts Compose; Docker restart policies supervise containers. Do not enable boot startup before the real mount gate and owner paused-on-restart behavior are proved. No unit was installed by this work.
8. Shell owner configures the existing owner connector with `https://actual-producer-host` and its dedicated gateway credential. Perform real WorkOS callback and fixed-world authorized status/command polling through the shell. Verify wrong-principal/world denial, signed-out denial, direct `/machine`/`/connected` public404, command revision conflicts and bounded polling. Never put the machine token in the browser.

## Coordinated encrypted backup

`recovery.py backup` calls actual owner pause and checkpoint hooks, requires matching clock/revision and complete ownership, stops **all** stack containers, confirms they are stopped, checks every SQLite DB, records file hashes/size and exact images/source SHAs, archives both complete data trees and encrypts with age. It rechecks source hashes after encryption to detect uncoordinated external writers. It leaves services stopped. Plaintext archive exists only in a temporary mode0700 staging directory and is removed after use. The data may contain runtime credentials, so only the encrypted `.tar.age` is a deliverable. The external age identity is never archived.

```sh
sudo python3 /opt/utilitysim-b/deploy/connected-stack/recovery.py backup --config /etc/utilitysim-b/deployment.json
```

Record the returned encrypted archive SHA256, run/clock and stop status in the operations record, then transfer the encrypted archive to approved off-host storage. Define retention/RPO/RTO and verify decryption with the protected identity in an isolated restore drill; this package creates no schedule or remote backup service. A managed-disk crash snapshot alone does not establish this application checkpoint. No online multi-store backup consistency is claimed.

## Original-path replacement restore

1. Keep the original disk unchanged. On an isolated replacement host/volume, install the same reviewed code/images/config and logical volume/run IDs; mount at the same host dataRoot and same container `/data` paths. No stack container or external writer may run.
2. Initialize the **empty** replacement mount with `initialize-volume`. Restore refuses nonempty owner stores and requires an authenticated/decryptable encrypted archive, same original paths, exact image/commit pins, complete paused owner checkpoint and matching file coverage/hashes. It rejects tar links, path escapes, duplicate entries, special files and payloads above20GiB by default. Larger accepted runs require a reviewed bound change; do not bypass checks. Identity file must be protected and stay outside the archive and Git.

```sh
sudo python3 /opt/utilitysim-b/deploy/connected-stack/recovery.py restore \
  --config /etc/utilitysim-b/deployment.json \
  --archive /protected-staging/connected-timestamp.tar.age \
  --identity /protected-key-location/restore-identity.txt
```

3. Restore leaves services stopped. If interrupted, keep the partially populated replacement volume isolated; the script refuses an automatic overwrite/retry. Inspect it and use a fresh empty replacement for another attempt. It never removes existing files for recovery.
4. Reopen with preflight/up; validate paused controller, identical run/world fingerprints, clock, pending jobs, cursor/control revision, received observations, invoice/payment/allocation counts, balanced ledger and field plans. Replay original IDs after lease expiry as the owner specifies. Assert no duplicate invoice/payment/repair/report and denied revoked grants. Only then resume through the authenticated control API and perform cutover. Managed relocation remains unsupported.

## Portable verification

From repository root:

```sh
python -m unittest discover -s deploy/connected-stack -p test_stack.py -v
python -m compileall -q deploy/connected-stack
python deploy/connected-stack/stack.py validate --config deploy/connected-stack/deployment.example.json
```

Last command must exit2: candidate deployment is intentionally refused. Unit fixtures are synthetic validation inputs, never DNS/account/resource evidence. Standard-library tests do not substitute for `docker compose config`, Linux boot, age encryption/decryption, owner hooks or real connected browser/VS acceptance.

Ownership: root infrastructure work owns only `deploy/connected-stack/**`; producer retains `deploy/hosted-runtime/**` and all runtime packaging; shell retains canonical Vercel/UI; private VS coordinator retains controller/runtime transactions. Coordination authorization: Greg, 2026-10-11, chat `01a12aa3-5c1e-7142-aad0-dd177c7c9f09`, #vbs-agents for UtilitySim/Virtual-Systems. Host audit: `P:/UtilitySim/outputs/b-connected/hosting-audit.md`.

Platform references checked 2026-10-11: [Compose services](https://docs.docker.com/reference/compose-file/services/) (shared service network namespace, noncreating bind mounts and health gates), [Caddy manual TLS](https://caddyserver.com/docs/caddyfile/directives/tls), [age tooling](https://github.com/FiloSottile/age), [SQLite backup semantics](https://www.sqlite.org/backup.html), [Vercel Function payload limit](https://vercel.com/docs/functions/limitations).
