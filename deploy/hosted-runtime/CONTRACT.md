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

## Storm events (follow-up adapter)

GET `/hosted/worlds/{id}/events?before=<sequence>&limit=25` returns `{worldInstanceId,view:'administrator-truth',through,events:[{sequence,id,day,type,subject,cause,payload}],nextBefore}`. This is the physical event journal, not the observation-only enterprise feed. Limit 1–50; nextBefore is the oldest returned sequence when older records exist.

GET `/hosted/worlds/{id}/events/storms?before=YYYY-MM-DD&eventsBefore=<sequence>&limit=25` returns the existing `storms.inspect` result plus `worldInstanceId`: `modelVersion:'world-storms/1',enabled,environmentId,worldFingerprint,through,revision,events,history,nextBefore,nextEventsBefore,view`. `events` holds schedules including cancelledEventId; `history` holds actual applied storm days with baseline/adjusted temperature, offset, risk multipliers and causal IDs. Date cursor pages applied days, integer cursor pages schedules. Inspection does not activate the storm model.

POST the same `/events/storms` path with:

```json
{
  "commandId": "a UUID",
  "expectedRevision": 0,
  "effectiveDate": "2026-07-15",
  "action": "schedule",
  "reason": "Summer weather stress scenario",
  "causalReference": "operator-scenario",
  "startDate": "2026-07-16",
  "endDate": "2026-07-18",
  "temperatureOffsetC": -10,
  "multipliers": {"electric": 2, "gas": 2, "water": 2, "sewer": 2}
}
```

For cancellation, use action `cancel` and `stormId` instead of startDate/endDate/temperatureOffsetC/multipliers. All six common fields remain required. UUIDs are canonicalized. The server injects schemaVersion, local actor, environment and fingerprint after principal/owner-or-operator grant checks; browser-supplied identity fields are rejected. POST returns the engine receipt `{commandId,stormId,status:'completed',revision,eventId,effectiveDate,modelVersion}`. Exact retry after advance/restart returns the original receipt. Changed command reuse, stale date/revision, overlap, invalid ranges and cancellation after any affected day is processed return 422.

End dates are exclusive UTC days. Duration 1–90 days, temperature offset −40…40°C, exactly four risk multipliers each 1–100. Zero baseline fault risk stays zero; scheduling does not turn on fault models. This is temperature/risk stress, not rain/wind/flood physics. Daily effects and readings commit with the existing engine day. No new scheduler, background jobs or fake progress. Status advertises `capabilities:{stormEvents:'world-storms/1',advanceMode:'synchronous',backgroundJobs:false}` and adds `paths.events` / `paths.storms`.

Manual advancement and storm mutation use the existing cruise lock and reject worlds owned by cruise or managed delivery. Invalid commands do not invoke constructor migrations. World inspection remains read-only. The accepted-map source stays unchanged.

## Physical setup v2: supported customer policies

GET source configuration now advertises `configurationVersion:'physical-setup/2'`, `schemas.world`, `schemas.physical`, and complete `defaults` including schemaVersion. Old `{world:...}` creation payloads remain valid and preserve their behavior. Extended configurations require `{schemaVersion:'physical-setup/2',world:{...},physical:{...}}`; missing fields normalize to defaults. Unknown groups, unsupported versions, wrong types/ranges and cashflow without finance are rejected before reserving a world. The new source artifact is `P:/UtilitySim/outputs/shell-workos/hosted-physical-setup-v2.json`.

Supported physical groups:

| Group | Fields | Actual engine application |
| --- | --- | --- |
| `customerContacts` | active, noticeProbabilityPerDay, deliveryDelaySeconds, repeatAfterDays, maxContacts | Existing experienced-symptom contact policy, not call-centre staffing/queues. |
| `householdFinance` | enabled, cashCents, essentialReserveCents, maxPaymentCents, paymentProbability | Initial cash/reserve/payment policy for each occupied residential premise, with a distinct instance/premise recipient reference. No enterprise bill is generated. |
| `householdCashflow` | enabled, incomeCents, incomeIntervalDays, expenseCents, expenseIntervalDays, insufficientCashPolicy | Existing recurring income/essential-expense engine, starting on the world start date. Fixed UTC-day intervals, not calendar months. Requires household finance. |

All three groups are opt-in by default. Initial assumptions are uniform across occupied residential households; distribution controls are not yet implemented. Financial values are minor currency units with no currency conversion. Existing physical modules own validation, state, cashflow events and observations. Payment intentions still require actual trusted received obligations; configuring finances does not fabricate bills or settle VS balances.

Numeric field schemas include `x-control:{kind:'slider',step,unit,allowExactInput,referenceValue,referenceLabel,labels,effect,severityBasis}`. World-weather/meter controls add `displayMinimum`/`displayMaximum` for the suggested slider track while original validation bounds remain authoritative. Reference values are illustrative defaults, not calibrated normality or judgments about customers. Browser controls must not discard exact values outside a suggested display range but inside engine validation.

The setup journal atomically reserves initial configuration with world creation. Per-domain/per-premise command IDs are deterministic; interrupted setup can replay committed commands without duplication or resetting cash. Each POST commits at most 10 new domain commands and stops between commands after an 8-second soft budget. A single command is atomic and cannot be interrupted by this budget. Until all requested initial commands finish, status is `state:'configuring',available:false,initialization:{state:'pending',eligibleHouseholds,appliedCommands,totalCommands}` and advance/event mutations are refused. Retain and retry the entire original create payload, including commandId, to continue; GET status/list do not perform setup. Completion reports `state:'complete',available:true,initialization:{state:'complete',eligibleHouseholds,appliedCommands,totalCommands}`. During crash recovery the progress object may contain only state/appliedCommands until the next successful batch. A gateway timeout is not proof of failure or success; exact POST retry resolves unfinished setup. There is no background setup worker in this slice.

GET `/hosted/worlds/{id}/premises/{premise}/customer?before=YYYY-MM-DD&limit=25` returns `{worldInstanceId,view:'administrator-truth',finance,cashflow}` using existing physical inspection. Cashflow supplies bounded dated history/nextBefore. Principal ownership and current view grant apply. This route is private administrator truth, not a VS observation feed.

**Desired scope versus present implementation:** Greg explicitly includes AMI/AMR/manual mix, housing-age distribution, customer behavior/finances and physical utility-operation assumptions in world setup. Only staffing, enterprise throughput/queues and enterprise business decisions belong elsewhere. Geography/stable IDs are pinned; other attributes are not categorically forbidden. AMI/age effects and customer sentiment remain advertised required gaps until their model/adapter tests pass. Sentiment should combine town confidence/news influence and personal received/experienced service history, with bounded contact/repeat/escalation feedback and recovery; it is not implemented by these contact-probability controls.

## Physical setup v3: meter collection and housing overlays

`physical-setup/3` adds opt-in `meterChannels` and `housingAge` groups. V1 and v2 remain accepted and normalize to their original shapes; v2 retries do not acquire new defaults. The current source-configuration endpoint advertises v3. Do not relabel an existing v2 draft as v3 without explicitly upgrading its reviewed configuration. The independent shell-ready schema is `P:/UtilitySim/outputs/shell-workos/hosted-physical-setup-v3.json`.

Meter fields: enabled, amiPercent/amrPercent/manualPercent (must total 100), amrReadIntervalDays/manualReadIntervalDays (1–366), and amiReadSuccess/amrReadSuccess/manualReadSuccess (0–1). Largest-remainder counts and stable seeded ordering assign starting meters to channels. AMI collects daily; AMR/manual collect on fixed intervals from world start or device commissioning. These schedules are scenario assumptions, not crew staffing or routing. No observations are fabricated on days without a scheduled collection. A successful read reports the accumulated device measurement over its complete interval. A missed collection reports an unknown quantity and retains private measured accumulation for a subsequent read; it never reads the truth table to repair a gap. Physical meter failure poisons that device's accumulated measurement; replacement starts a fresh interval/device. Existing observed-register reconstruction deliberately remains unknown after a reported gap. Its later recovery requires a separate physical-register contract and is not claimed here.

Export start/end select **collection dates**, while each observation retains its actual measurement interval, which may start before the requested collection window. Consumers must handle this distinction and must not prorate or fabricate daily readings. Existing JSON schema validation passes; downstream VS acceptance of these longer intervals remains a separate connector gate. Derived sewer retains the observed water interval and never uses hidden demand. Admin history adds intervalStart, intervalEnd and technology for these readings.

Housing fields: enabled, meanAgeYears and ageSpreadYears (0–200), extraThermalDemandPer50Years (0–2), retrofittedPercent (0–100). Ages are a seeded uniform distribution around the centre, clipped to 0–200; clipping can shift the realised average. Residential heating/cooling is multiplied by `1 + age/50 × extraThermalDemandPer50Years`, with the age-related addition reduced by 75% for the chosen retrofit share. These coefficients are explicitly illustrative, not a calibrated claim that old homes are inefficient. Water and nonthermal loads are unchanged. Starting nonresidential premises and later developments are not reassigned by this initial overlay.

The source snapshot, geography and all stable IDs stay unchanged. `PhysicalProfilesConfigured` and a configuration digest record applied provenance. Premise inspection adds `physicalProfiles` with applied housing attributes, meter channels and aggregate channel counts; show these applied values over the source attributes when enabled. Both effects are opt-in and run in the existing atomic day transaction. Tests prove old daily behavior, deterministic assignment, true interval accumulation, missed-read recovery without a truth query, physical failure/replacement, rollback/restart and thermal-only demand changes. Full accepted-map HTTP proof covers all 1,262 meters, three-day manual intervals, 300 residential housing profiles, source preservation and process restart.

## Implementation ownership

Backend chat `01a12bf4-9f78-7411-ac48-15750ae1d151` owns `utilsim/hosted/`, its tests and `deploy/hosted-runtime/`. Shell chat `01a12acd-01bf-7801-b837-d651ab299083` owns UI, WorkOS gateway and canonical Vercel release. Coordinator `01a12759-bb9e-79b1-b1b9-32f0a5864e10` coordinates online draft storage. Standing coordination authorization: Greg, 2026-10-11, chat `01a12aa3-5c1e-7142-aad0-dd177c7c9f09`.
