# Pinned-map runtime contract

Status: local implementation only. No online compute provisioned or deployed. Per Greg's 2026-10-11 clarification, online initial setup and durable setup drafts are distinct from a playable simulation; future compute hosting is separate work. These endpoints create real physical worlds and must not serve as draft-storage endpoints.

The trusted WorkOS gateway supplies `Authorization: Bearer <internal token>`, `X-UtilitySim-User-Id`, and `X-UtilitySim-Grants` (JSON array of verified current `{role,town,expiresAt?,revoked?}` grants). Never forward browser-provided identity headers. Internal token must have at least 32 characters and stays server-side. Enforce TLS and network ingress restriction when hosting. All world data is principal-owned; sharing is not implemented. Ownership plus a current scoped grant is required. Owner creates, owner/operator advance, existing viewer roles inspect. No role bootstrap.

## Identifier boundaries

- `sourceId`: approved template slug, e.g. `lantern-harbour`.
- `grantTownId`: existing permission/catalog namespace, e.g. `lantern-bay-500`. This legacy grant name does not describe actual home count.
- `townId`: exact snapshot map ID, `town-47ecb8e861787476` for accepted Lantern Harbour.
- `sourceRevision`: SHA-256 of canonical imported manifest including snapshot, geometry, bindings and artwork file hashes.
- `id`: random independent saved-world instance ID; each owns separate history and environment `instance-<id>`.

## Endpoints

| Method/path | Shape |
| --- | --- |
| GET `/hosted/sources` | `{sources:[{sourceId,sourceRevision,grantTownId,townId,name,counts,snapshotSha256,ready}]}` |
| GET `/hosted/sources/{sourceId}/configuration?sourceRevision=...` | `{sourceId,sourceRevision,grantTownId,townId,counts,schemas:{world},defaults:{world},immutable,excluded}` |
| GET `/hosted/worlds?offset=0&limit=25` | `{worlds:[status],total,offset,limit}`; filters both ownership and current grants. Maximum page 50. |
| POST `/hosted/worlds` | `{commandId,sourceId,sourceRevision,name,start,configuration}`; returns status. UUID idempotency scoped to principal. Same normalized inputs replay same instance; changed inputs reject. |
| GET `/hosted/worlds/{id}` | Saved status, full normalized configuration, fingerprint, through, state, available, counts, paths. |
| GET `/hosted/worlds/{id}/map/snapshot` | Exact pinned `utility-town/2.0` snapshot; no regeneration. |
| GET `/hosted/worlds/{id}/map/bindings` | `{worldInstanceId,environmentId,sourceRevision,premises:[{parcelId,premiseId,accountId,simulationParcelId,buildingId,meterIds,servicePointIds}]}`; old localhost links omitted. |
| GET `/hosted/worlds/{id}/premises/{premiseId}` | Existing engine administrator map record plus `worldInstanceId`. |
| GET `/hosted/worlds/{id}/premises/{premiseId}/history?offset=0&limit=14` | Scoped recorded observations, through, premise, environment, totalDays. Maximum 31 days. |
| GET `/hosted/worlds/{id}/observations?start=...&end=...` | Existing observation-only engine export, start inclusive/end exclusive, maximum 31 days. |
| POST `/hosted/worlds/{id}/advance` | `{through:"YYYY-MM-DD"}`; idempotent monotonic cursor, at most 31 new days per request; returns status. |

Status includes `id,name,sourceId,sourceRevision,grantTownId,townId,start,through,configuration,configurationRevision:1,configurationEditable:false,counts,snapshotSha256,fingerprint,environmentId,modelVersion,days,assets,observations,state,available,paths`. Pending/unavailable records remain visible with an error and may lack physical status fields. No path to a server filesystem is accepted or returned. No delete/import-source-world/billing endpoint exists. Request bodies are limited to 64 KiB. Errors use `{detail}` with 401 internal identity absent, 403 grant denied, 404 foreign/missing instance, 422 invalid data, 503 unavailable durable storage. Reads use no-store.

## Physical setup scope

`configuration` contains only `{world:{weather:{winter_mean_c,summer_mean_c,daily_weather_spread_c},meters:{annual_meter_failure,annual_meter_drift}}}`. Missing fields normalize to defaults from `utilsim.config.wizard.world_configuration()`. Reject unknown groups, booleans, nonfinite numbers and unsupported ranges. Name and canonical start date are separate. These five settings are persisted and consumed by the existing daily physical engine.

Snapshot-owned population, demand profiles, premises, account IDs, service topology, meter identities and geometry stay pinned. Calendar advances in UTC daily boundaries; the engine does not implement regional/DST day boundaries. Snapshot timezone is not an editable runtime setting. Initial setup cannot change these map assumptions. Later occupancy and physical-action capabilities need separate explicitly scoped adapters; this API does not silently pretend they are active setup controls.

Exclude Studio year runs, billing, tariff processing, collections, VEE, staffing, enterprise work queues, and Virtual Systems settings. Unsupported fields are rejected, never retained with implied effect. Configuration is immutable after creation; changes currently require a new instance. A future dated settings command needs independent engine support and revision/audit semantics.

## Durability and restart

`UTILITYSIM_DATA_ROOT` must be a persistent local/block volume. It contains a SQLite creation/ownership journal, immutable imported template packages, and separate `worlds/<id>/world.sqlite` files. Reservation atomically pins principal, command, normalized settings, snapshot and bindings before engine initialization. Existing `world_creation.resume` handles a crash between world commit and library commit. Retrying the original creation payload recovers without rereading mutable sources. Existing instances can inspect their pinned snapshot and bindings even if a template is unavailable; rendering original artwork requires retaining its immutable package.

One runtime replica and one worker are the initial deployment contract. Never use Vercel Function temporary disk, network filesystem SQLite locking without verification, browser storage, or the shared demonstration world as persistence. Back up journal, templates and world databases consistently. Production gateway timeout/job scheduling and large-world load limits remain acceptance work before deployment.

## Ownership

Backend chat `01a12bf4-9f78-7411-ac48-15750ae1d151` owns `utilsim/hosted/`, its tests and `deploy/hosted-runtime/`. Shell chat `01a12acd-01bf-7801-b837-d651ab299083` owns UI, WorkOS gateway and canonical Vercel release. Coordinator `01a12759-bb9e-79b1-b1b9-32f0a5864e10` coordinates online draft storage. Standing coordination authorization: Greg, 2026-10-11, chat `01a12aa3-5c1e-7142-aad0-dd177c7c9f09`.
