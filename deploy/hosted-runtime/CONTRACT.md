# Pinned-map runtime contract

## Connected producer port (B)

This implementation keeps the world and VS as separate owners coordinated by the existing VS clock. It is not a production deployment claim. `create_app` accepts a distinct `machine_key`, approved `controller_id` (default `utilitysim-controller`), fixed `controller_url` and distinct `controller_token`. Environment equivalents are `UTILITYSIM_MACHINE_KEY`, `UTILITYSIM_CONTROLLER_ID`, `UTILITYSIM_CONTROLLER_URL`, `UTILITYSIM_CONTROLLER_TOKEN`. All three secret values (including the original `UTILITYSIM_RUNTIME_TOKEN`) support `_FILE` alternatives; specifying a value and file together is refused. Reusing the gateway credential as a machine key or controller service token is refused. Private HTTP controller transport requires explicit `UTILITYSIM_CONTROLLER_ALLOW_HTTP=1` on an inspected private/loopback network; otherwise HTTPS is required.

Owner CLI/bootstrap uses `POST /hosted/worlds/{id}/connection` with exactly `{commandId:canonical UUID,expectedRevision:nonnegative integer,controllerId:approved server controller,sewerReturnFactor:decimal,delaySeconds:integer}`. It pins the world/run/fingerprint and existing delivery settings, creates a separate field execution owner, and returns the fixed-world capability token. **Do not proxy this token to a browser.** The shell deliberately exposes no bootstrap route; copy it securely into the private controller's token file. The catalog stores only its hash; a separate machine key enables exact issuance-response replay. New commands with the current revision rotate/revoke earlier capabilities. `POST .../connection/revoke` accepts `{commandId,expectedRevision}` and disables the token. `GET .../connection` and `status.connectedClock` expose only `{configured,active,controllerId,runId,revision,manualAdvanceAllowed}`. Once a delivery stream is pinned, raw manual advancement remains denied, including paused/revoked connections; it is never silently converted back into an independent clock.

`Authorization: Bearer <fixed-world capability>` is required on every `/machine/worlds/{id}` route. The gateway bearer and browser identity/grant headers cannot supply machine authority. Cross-world tokens, rotated/revoked tokens and changed world fingerprints are refused. These routes expose committed evidence and acknowledgements, not administrative truth, snapshots, cash/policies or arbitrary paths:

| Route | Contract |
| --- | --- |
| GET `/status` | actual worldInstanceId, environmentId/runId, fingerprint, through, controllerId, revision, delivery `{configuration,pending,accepted}` |
| POST `/advance` | exact `{commandId,through:canonical date,processingAt:canonical UTC instant}`; controller authority comes from the token; exactly one next day; exact saved command retry recovers a post-day-commit crash |
| GET `/feeds/{observations,contacts,payments,financial-contacts,field}` | bounded `after` and limit1–50; `{items,nextAfter,lastCursor,worldInstanceId}`; nextAfter is null on the final page, lastCursor is the last item or original typed cursor on an empty page |
| POST `/receipts/{feed}` | raw matching existing domain receipt; exact receipt replay succeeds; changed receipt conflicts |
| GET `/payments/{intentId}` | actual available `{intent,fingerprint}` only |
| GET `/cohorts` | premise cursor and limit1–50; actual active occupied matching-cohort `{premiseId,recipientRef,runId,customerKind}`; no cash/policy fields |
| POST `/returns/invoices` | exact customer-finance-delivery/1, actually delivered and current matched world/run/cohort; existing durable inbox dedup |
| POST `/returns/provider` | exact customer-finance-provider-receipt/1 or /2; original full intention amount/fingerprint, settlement/return/failure rules unchanged |
| POST `/returns/field` | existing field-world-execution/1 command without actorId; broker supplies world-admin for configure/accept and the accepted assigned crew for execute; separate field database |

Observation feed items are `{cursor:sequence,envelope:original scheduler command,fingerprint}`. They may be enqueued before availableAt so VS can own timed delivery. The whole immutable command is retained; pagination cuts between messages, never measurements. Engine envelopes remain bounded8MiB; direct machine responses are bounded9MiB, deliberately outside the browser64KiB request/3MB response gateway. Other feeds use existing available-only world-clock filtering: contact/notice availability UTC|sequence, payment integer sequence, field date|sequence. Contact/payment/notice items include intent and fingerprint; field items include envelope and checksum. A report is withheld until its earlier dispatch acknowledgement is received.

Receipts preserve existing distinctions: observations require matching id and scheduler status pending/delivering/completed/failed; customer contacts require `{id,environmentId,fingerprint,status:accepted,receiptId}`; payments/financial contacts require runId in place of environmentId; field requires `{id,environmentId,checksum,status:received,receiptId}`. Transport acceptance does not imply successful reading validation, released bills, paid invoices or accepted work-order closure. Invoice/provider returns require actual occurrence no later than physical through midnight; intraday evidence must wait until the physical day covers that timestamp, retaining its original deliveredAt/occurredAt. No hidden consumption is used to repair missing reads or registers.

The physical-day journal commits intent before execution, runs due physical visits before the day, commits the original observations/outbox with that day, then records the stable day receipt. Previous unaccepted observation delivery blocks the next day. Exact retry after a lost reply, field effect or physical commit cannot add a second day/report. VS must queue each new command before its clock passes availableAt; neither side rewrites historic availability to bypass that guard.

Browser controls use `GET /hosted/worlds/{id}/connected` and `POST .../connected/commands` with `{commandId:UUID,expectedRevision,action:pause|resume|advance,through?}`. Through is the VS normalized whole-second UTC instant, including intraday targets; the machine advance date remains a different contract. The fixed proxy shares one15-second budget across status identity preflight plus mutation, follows no redirects/proxies, bounds JSON responses3MB, and verifies pinned run/controller and retained command identity. It forwards fixed X-UtilitySim-Run-Id/Controller-Id headers to the service; VS must validate those before command acceptance. Unconfigured/mismatched controllers return503, never fabricated status. A matching commandRejected:true proof is projected only from authenticated POST400/409/422 after VS's exact-ID dedup proves nonacceptance; preflight/auth/unknown failures cannot clear a retained browser command.

Definitive rejection additionally requires the pinned `runId`, `controllerId`, exact `commandId` and `requestSha256` matching SHA-256 of the original command serialized as sorted, compact JSON (the existing canonical serializer). The producer never supplies missing identity fields or treats an unbound error as proof. VS must persist this terminal decision so the same rejected immutable request cannot later be accepted; an accepted-ID changed-content conflict cannot reject the accepted original. The browser receives only generic detail, matching commandId and commandRejected, never private diagnostics or tokens. Outage status may retain an actual local clock/revision with `physicalThrough:null` and `technicalError`; it does not fabricate a physical date.

`GET /hosted/health` is gateway-authenticated, requires no user-world grant and actually checks the persistent catalog; `python -m utilsim.hosted.health` is the container readiness command. Machine readiness uses the actual pinned `/machine/.../status`. `python -m utilsim.hosted.backup backup|restore --source ... --destination ...` creates a private checked producer checkpoint. It serializes physical clocks, snapshots SQLite with explicit handle closure and records file checksums. Restore refuses changed paths, corrupt files and nonempty destinations; it supports an empty replacement volume at the original path. This is a producer checkpoint only: coordinated backup must pause/stop VS and preserve its separate runtime, business, delivery, control and field owners as well. Neither private backups nor secret files belong in a public repo.

### Fixed live managed-field callbacks

The opt-in managed-field bridge uses the existing ManagedField broker and two
fixed authenticated controller POST routes. `/connected/field-authority` accepts
only existing jobId/reservationId identifiers and returns `connected-field-authority/1`
with actual run/controller/world/field-owner/runtime-path/executor identity,
clock, runStatus, leaseActive, leaseHeld, crewResources and selected live job,
dependencies and reservation. Raw lease credentials are never returned. The
producer checks all pins and schema before using this flat response as the
trusted callback. `/connected/field-calendar` accepts exact
`{day,time,timeZone,fold}` and returns `connected-field-calendar/1` with pinned
run/controller and the existing DST-aware converter's canonical UTC instant.
The origin and service credential remain server configured; no worker supplies
authority, calendar conversion, an actor, clock, callback URL or runtime path.

Under the existing fixed-world machine capability:

| Route | Input / result |
| --- | --- |
| GET `/field-managed/status` | actual `{schemaVersion:connected-field-status/1,fieldOwnerId,environmentId,fingerprint,enabled}`; no controller callback on startup |
| GET `/field-managed/assignment?assignmentId=...` | actual saved `{assignment,checksum}`, verified against the original accepted payload; no controller callback |
| POST `/field-managed/plan` | exact `{quote,schedule}` using existing field-travel and managed-schedule contracts; returns original immutable plan |
| POST `/field-managed/bind` | exact `{assignmentId,jobId,reservationId}`; binds the actual matching pending job and reservation |
| POST `/field-managed/execute` | exact `{jobId,reservationId}`; producer constructs the envelope from live job/run/clock, then ManagedField rechecks authority before effects |
| POST `/field-managed/cancel` | exact `{assignmentId}`; existing actual cancellation rules apply; committed physical work cannot be undone |

Planning/binding require actual paused status and no recorded lease, including
an expired lease. Executing a delivering job requires a live unexpired lease;
already committed results retain exact replay semantics. Existing persisted
plan runtime/executor pins reject silent authority rebinding. Field status,
assignment reads, feeds and commands open the registered sidecar in SQLite
mode=rw and reject missing/empty owners rather than recreate them. Initial
connection setup alone creates and pins the separate field owner. Field feeds
and exact Billing/domain receipts remain unchanged, including acknowledgement
before report delivery.

This closes the producer code interface; actual remote Run/Billing/lease
acceptance requires the corresponding private callbacks, dispatcher and tests.
The bridge does not invent a depot in Lantern or claim the shared436 source can
quote a route without its existing required geometry. Machine cohorts describe
initial/current configured recipients; occupancy transitions require explicit
commercial/cohort reconciliation. Physical scenarios and enterprise exceptions
remain visible rather than automatically resolved.

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

V2 introduced `configurationVersion:'physical-setup/2'`, `schemas.world`, `schemas.physical`, and complete `defaults` including schemaVersion. Old `{world:...}` creation payloads remain valid and preserve their behavior. V2 configurations use `{schemaVersion:'physical-setup/2',world:{...},physical:{...}}`; missing fields normalize to defaults. Unknown groups, unsupported versions, wrong types/ranges and cashflow without finance are rejected before reserving a world. The v2 source artifact is `P:/UtilitySim/outputs/shell-workos/hosted-physical-setup-v2.json`. The endpoint currently advertises the latest version documented below.

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

`physical-setup/3` adds opt-in `meterChannels` and `housingAge` groups. V1 and v2 remain accepted and normalize to their original shapes; v2 retries do not acquire new defaults. Do not relabel an existing v2 draft as v3 without explicitly upgrading its reviewed configuration. The independent shell-ready schema is `P:/UtilitySim/outputs/shell-workos/hosted-physical-setup-v3.json`.

Meter fields: enabled, amiPercent/amrPercent/manualPercent (must total 100), amrReadIntervalDays/manualReadIntervalDays (1–366), and amiReadSuccess/amrReadSuccess/manualReadSuccess (0–1). Largest-remainder counts and stable seeded ordering assign starting meters to channels. AMI collects daily; AMR/manual collect on fixed intervals from world start or device commissioning. These schedules are scenario assumptions, not crew staffing or routing. No observations are fabricated on days without a scheduled collection. A successful read reports the accumulated device measurement over its complete interval. A missed collection reports an unknown quantity and retains private measured accumulation for a subsequent read; it never reads the truth table to repair a gap. Physical meter failure poisons that device's accumulated measurement; replacement starts a fresh interval/device. Existing observed-register reconstruction deliberately remains unknown after a reported gap. Its later recovery requires a separate physical-register contract and is not claimed here.

Export start/end select **collection dates**, while each observation retains its actual measurement interval, which may start before the requested collection window. Consumers must handle this distinction and must not prorate or fabricate daily readings. Existing JSON schema validation passes; downstream VS acceptance of these longer intervals remains a separate connector gate. Derived sewer retains the observed water interval and never uses hidden demand. Admin history adds intervalStart, intervalEnd and technology for these readings.

Housing fields: enabled, meanAgeYears and ageSpreadYears (0–200), extraThermalDemandPer50Years (0–2), retrofittedPercent (0–100). Ages are a seeded uniform distribution around the centre, clipped to 0–200; clipping can shift the realised average. Residential heating/cooling is multiplied by `1 + age/50 × extraThermalDemandPer50Years`, with the age-related addition reduced by 75% for the chosen retrofit share. These coefficients are explicitly illustrative, not a calibrated claim that old homes are inefficient. Water and nonthermal loads are unchanged. Starting nonresidential premises and later developments are not reassigned by this initial overlay.

The source snapshot, geography and all stable IDs stay unchanged. `PhysicalProfilesConfigured` and a configuration digest record applied provenance. Premise inspection adds `physicalProfiles` with applied housing attributes, meter channels and aggregate channel counts; show these applied values over the source attributes when enabled. Both effects are opt-in and run in the existing atomic day transaction. Tests prove old daily behavior, deterministic assignment, true interval accumulation, missed-read recovery without a truth query, physical failure/replacement, rollback/restart and thermal-only demand changes. Full accepted-map HTTP proof covers all 1,262 meters, three-day manual intervals, 300 residential housing profiles, source preservation and process restart.

## Physical setup v4: community and household sentiment

The source-configuration endpoint currently advertises `physical-setup/4`, adding opt-in `customerSentiment`: enabled, initialTrust (0–100), recoveryDays (1–365), experienceImpact/lateBillImpact/communityInfluence (0–1), maxContactMultiplier (1–5). V1/v2/v3 remain accepted with their existing normalized shapes. Artifact: `P:/UtilitySim/outputs/shell-workos/hosted-physical-setup-v4.json`. Existing dated occupancy, hazard, fault and development modules still require hosted adapters; adding these groups does not claim the entire inventory is exposed.

The model persists community frustration and a separate state for each starting residential household. Each day removes `priorFrustration / recoveryDays`, adds bounded influence from community mood, and applies at most one experienced-service and one late-delivered-bill impact. Actual experienced supply loss/visible overflow can affect mood; hidden fault existence and missing transmissions cannot. Financial evidence comes only from the trusted world inbox and its received invoice. A bill counts as late only when its actual delivery date is after its due date, and it is consumed once. Learning an on-time document late does not mislabel it as a late delivery. An unpaid or unreceived bill is not invented as evidence. Occupancy cohort changes reset personal memory; community mood can still influence the new household.

Community mood receives explicit scheduled public-news impulses, household feedback and recovery. Every state stays in [0,1]. The current mean influences community mood, and public mood influences households, producing bounded amplification rather than unbounded growth. Coefficients are scenario assumptions, not calibrated predictions. Good news, quiet days and restored service allow confidence to recover.

With the existing contact model enabled, personal frustration derives a multiplier from 1 to maxContactMultiplier. It raises notice probability (capped at 1), reduces repeat spacing (at least one day), and raises the episode contact cap (at most 10). Contact intentions still require a real experienced service symptom. News-only inquiries, financial-contact escalation, enterprise queue delays/staff handling and payment-propensity effects are not implemented in this slice. Existing contact envelope/schema, delivery timing and knowledge boundaries remain unchanged; sentiment and hidden causes stay in administrator history.

GET `/hosted/worlds/{id}/events/sentiment?premiseId=<optional>&before=YYYY-MM-DD&newsBefore=<sequence>&limit=25` returns `{worldInstanceId,enabled,modelVersion,view,through,revision,policy,communityTrust,householdTrust,history,nextBefore,news,nextNewsBefore}` when enabled. Date cursor pages community or household history; independent integer cursor pages news, including multiple events on one date. Disabled worlds return enabled:false and no tables are created by reading. These are administrator-truth views, not recipient evidence.

POST the same path to schedule a synthetic public-news scenario:

```json
{
  "commandId": "a UUID",
  "expectedRevision": 0,
  "effectiveDate": "2026-07-15",
  "action": "schedule",
  "reason": "Public confidence scenario",
  "causalReference": "reviewed-scenario",
  "eventDate": "2026-07-16",
  "trustChange": -30,
  "headline": "Reliability concerns in local news"
}
```

Positive trustChange improves confidence; negative values reduce it, bounded to −100…100 points. Schedule within the current day and next 3650 days. This is manually entered scenario news, not a live news feed. Cancel with action:cancel and newsId, omitting eventDate/trustChange/headline. Common fields remain required. The gateway supplies world identity and local administrator authority after principal/grant checks. Revision/date checks, exact retries, cancellation before processing and clock ownership match the storm adapter. Receipt: `{commandId,newsId,revision,eventId,status:'completed',modelVersion,effectiveDate}`. Initial sentiment must have been enabled. Applied/cancelled news cannot be cancelled again under a new command.

Sentiment, contact decisions, news application and the physical day checkpoint commit atomically. Tests cover no future/hidden knowledge, late delivery versus late learning, bounds, restored/quiet recovery, cohort resets, unchanged opt-out physics/contact contracts, rollback/restart, event idempotency, cancellation, auth, immutable inspection and independent pagination. Full accepted-map HTTP/restart proof covers 300 occupied households and one exactly-once scheduled news impulse; separate real-fault tests prove actual repeat-contact amplification.

## Scoped commercial operator transport

`POST /hosted/worlds/{id}/operator` accepts exactly `{action,premiseId,...actionFields}`. The browser cannot supply `actor`, schema/version, capabilities, upstream credentials, URLs or route paths. Actions and extra fields are:

| Action | Extra fields | Permission | Successful status |
| --- | --- | --- | --- |
| `premise` | none | billing.view | 200 |
| `job` | jobId | billing.view | 200 |
| `release-read` | commandId, exceptionId, note | billing.view + billing.run | 200 |
| `bill` | commandId, cycleId, contractId | billing.view + billing.run | 202 |
| `invoice` | commandId, cycleId, accountId | billing.view + billing.run | 202 |
| `retry-job` | commandId, jobId | billing.view + billing.run | 202 |

Identifiers and notes are nonblank strings up to 200 characters; mutation command IDs are canonical UUIDs. The producer derives the actor subject from the verified gateway principal and capabilities from its current, unrevoked, unexpired grants for the owned world's grant town. Owner/operator/billing/support/analyst can view; only owner/billing can run commercial actions. World advance permission does not authorize billing mutations. The premise must occur in this world's saved physical bindings before any outbound request.

Configure a distinct 32–4096 character printable ASCII `UTILITYSIM_OPERATOR_TOKEN` or `UTILITYSIM_OPERATOR_TOKEN_FILE` (never both). It must differ from gateway, machine and controller credentials. It uses the existing fixed controller origin and transport policy, never a new browser-selected service. Omitting it leaves the route unavailable. The literal private path is `/connected/operator`, with `connected-operator-request/1`, the derived actor, and fixed run/controller headers. No browser Origin, cookies or authorization headers are forwarded. Outbound request size is at most 4096 bytes; the entire response has a 15-second deadline and 2,000,000-byte bound. Redirects are never followed.

The private response must be `connected-operator-response/1` with the exact matching run, controller, physical premise, action and original command ID (null for reads). The premise projection permits only physicalPremiseId and accounts/premises/contracts/installations/reads/bills/invoices/exceptions/cycles/receivables; each collection is at most 200 row objects. There is no jobs array. Job actions validate the scoped job ID, instance, type/status and cycle as applicable. Release reports an actual resolved result. Typed, scoped refusal statuses 400/403/404/409/413/422/503 are preserved; malformed, unscoped, unexpected or unavailable replies become 503. Responses are not cached.

202 preserves the original queued job receipt; it is not evidence of a completed bill, invoice or ledger posting. Poll `job` with that actual job ID. The producer never retries a mutation automatically, generates a replacement UUID or labels uncertain transport failure as authoritative nonacceptance. Retry the retained exact request. Billing owns physical-to-commercial account mapping, ambiguity refusal, shared clock and held-lease checks, domain validation and atomic command/event replay; no enterprise database is read locally by the producer.

For a bounded selector, `GET /hosted/worlds/{id}/premises?offset=0&limit=50` returns `{worldId,sourceRevision,total,offset,premises:[{premiseId,address?,parcelId?}]}`. Offset is nonnegative; limit is 1–50; IDs sort lexically and an exhausted page is empty. `GET /hosted/worlds/{id}/premises/{premiseId}/summary` returns `{worldId,sourceRevision,premise:{premiseId,address?,parcelId?,type?,occupied}}` from saved geometry/bindings and current physical occupancy. Display text is bounded to 512 characters; operator premise IDs to 200. Unknown premises return 404. Both require current world view permission and ownership. The existing administrator detail and full map bindings remain compatible; this summary contains no assets, meter condition, physical quantities or fault truth.

## Current ownership

Backend chat `01a12bf4-9f78-7411-ac48-15750ae1d151` owns `utilsim/hosted/`, its tests and `deploy/hosted-runtime/`. Shell chat `01a12acd-01bf-7801-b837-d651ab299083` owns UI, WorkOS gateway and canonical Vercel release. Coordinator `01a12759-bb9e-79b1-b1b9-32f0a5864e10` coordinates online draft storage. Standing coordination authorization: Greg, 2026-10-11, chat `01a12aa3-5c1e-7142-aad0-dd177c7c9f09`.

Coordinator-approved narrow core expansion covers store.py, contacts.py, new physical_profiles.py/sentiment.py and focused tests. Existing finance/notices/enterprise/exchange/register modules were not modified. Preserve other workstream ownership when expanding this scope.
