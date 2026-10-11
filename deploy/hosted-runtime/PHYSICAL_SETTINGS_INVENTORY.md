# Physical settings inventory and hosted adapter gaps

Inspected 2026-10-11 against backend commit `7cbb4aa` (engine inherited from `bf82292`). This is a code inventory, not a claim that every local capability is exposed, tested or deployed through the hosted connector. The companion JSON enumerates every original `SimConfig` group and its field names/schema, plus literal policy defaults from the physical engine. It is a review artifact, not an accepted creation payload.

## What the current create contract accepts

**Direct Greg corrections, 2026-10-11:** World setup must include AMI/AMR, house ages, customer behavior and household financial circumstances. Five fields are incomplete. Even pseudo utility-operation settings belong in the world builder when they model world conditions; staffing, enterprise throughput, queues and business decisions remain external. Classify individual fields by effect, not old section names. Statements below about frozen attributes describe current adapter limitations, not final product scope. Only accepted geography and stable identities are inherently pinned; other attributes need supported overlays/dedicated commands.

Greg requested sliders for most settings with understandable severity/effect. Provide linked AMI/AMR/manual percentages totaling 100%, housing-age distributions, customer behavior/budget/reserve controls, preset reference markers and exact numeric entry. Severity means stress relative to the chosen preset where meaningful, not moral judgments about customers or a universal good/bad score. Show concrete effect and units. UI controls must report capability support; do not imply an ignored parameter changes the engine.

The original `utilsim/config/wizard.py:world_configuration()` defines exactly five fields consumed by `World.initialize()`:

| Field | Default | Validation |
| --- | --- | --- |
| `world.weather.winter_mean_c` | 2 | finite number |
| `world.weather.summer_mean_c` | 26 | finite number |
| `world.weather.daily_weather_spread_c` | 6 | finite, nonnegative |
| `world.meters.annual_meter_failure` | 0.015 | finite, 0–1 |
| `world.meters.annual_meter_drift` | 0.01 | finite, 0–1 |

World display name and start date are separate fields. Source revision fixes the snapshot, premise/meter IDs, demand profiles and geography. UTC daily boundaries apply. These are the supported initialization controls, **not the complete physical-world configuration surface**. None of the settings below can be sent to the current `/hosted/worlds` creation configuration until a validated adapter exists.

## Existing physical command surface beyond initialization

These modules already validate local commands and write durable dated state. Expose them through explicit instance-scoped adapters, preserving their validators and histories; do not copy their fields into an ignored setup object. `utilsim/world/server.py` is the local route reference. Current hosted routes expose inspection, snapshot/bindings, observations and bounded direct advance only.

| Area and source module | Existing controls / variables | Hosted work needed |
| --- | --- | --- |
| Occupancy — `occupancy.py` | Schedule/cancel premise occupancy; `effectiveDate`, `occupied`, `occupants`; cancel via `targetCommandId`. | Per-premise dated command adapter. Preset starting population stays fixed; later simulated occupancy is a separate explicit event, not silent preset regeneration. |
| Storms — `storms.py` | Schedule/cancel; start/end dates, temperature offset, electric/gas/water/sewer risk multipliers. Duration 1–90 days; offset −40…40°C; multipliers 1–100; overlapping active scenarios rejected. | Dated event creation/list/cancel and actual effect/history display. |
| Infrastructure aging — `hazards.py` | Active flag; four family profiles with `ageYears`, `annualAgeIncrease`, `coldBelowC`, `coldMultiplier`. Bounds 0–10000, 0–1, −80…60, 1–100 respectively. | Current-date, revision-checked policy adapter. This is distinct from the legacy incidents-generation group. |
| Downstream water leaks — `water_faults.py` | Configure annual probability/leak rate; start fault on asset; repair identified fault with work-order reference. | Policy + authorized physical command adapters; preserve hidden truth versus meter observations. |
| Water mains — `water_mains.py` | Configure `breaksPer100kmYear`, `lossM3PerHour`; start/isolate/repair/restore phases against saved topology. | Per-edge fault/state/revision adapters, section and service impact inspection. |
| Electric/gas networks — `network_faults.py` | Configure annual probability; start/restore fault using commodity, edge, fault and work-order IDs. | Topology-bound adapters and current-state views. Must not regenerate network design. |
| Sewer laterals — `sewer.py` | Annual probability, return factor, storage volume, blocked daily capacity; start/clear blockage on an existing water-linked service. | Policy/event adapters; do not invent sewer meters or treat physical return factor as tariff setup. |
| Meter replacement — `store.py:replace_meter` | Command, environment, meter, replacement device, work-order reference, note. | Explicit authorized physical command and audit. Reference presence alone does not establish an externally authorized VS work order. |
| Development — `development.py` | Plan/pause/fail/resume an existing premise project; construction duration, start/utility-ready/occupancy dates, occupants, notification delay. | Existing-premise lifecycle adapter; not an unrestricted town/parcel editor. |
| Customer experience/contact intent — `contacts.py` | Active, notice probability, delivery delay, repeat interval, max contacts; reacts to experienced physical symptoms. | Physical-behavior policy + observation/intent delivery. Does not own VS contact-centre staffing or case resolution. |
| Customer finances — `customer_finance.py` | Active, customer kind, recipient reference, cash/reserve/payment cap, payment probability; explicit credit. | Customer-side behavior controls and authenticated receipts. This module does not calculate/post enterprise bills. |
| Household cashflow — `customer_cashflow.py` | Active; income and essential-expense streams; insufficient-cash and income-overflow policies. | Per-premise dated behavior policy; keep enterprise receivable/collection decisions external. |
| Reactions to received financial notices — `customer_notices.py` | Active, notice probability, delivery delay, repeat interval, max contacts. | Trusted received-evidence adapter and customer intent output; not a billing decision engine. |
| Time controller — `cruise.py` | Start/pause/resume/cancel a durable run; target date, policy for field progression, current phase/revision. | Instance-scoped control/status plus a background worker. Reuse `cruise.tick`/checkpoint semantics; do not emulate progress in browser timers. |
| Observation delivery — `delivery.py`, `exchange.py` | Environment binding, sewer return factor, delay; durable day outbox and relay; v2 observation export. | Separate connector settings, authenticated destination, retries/acks and recipient proof. These are not town-generation fields. |
| Field execution/reporting/travel — `field_execution.py`, `field_reporting.py`, `field_travel.py`, `field_water_mains.py`, `field_cancellation.py`, `field_managed.py` | Physical execution/report modes, travel against saved roads, authorized assignment outcomes and phased main work/cancellation. Requires separate field store for several controls. | Explicit shared ownership with VS workforce/assignment owner. Do not import old Studio crew/queue defaults as UtilitySim staffing policy. |

Command envelopes commonly bind schema version, command ID, environment, fingerprint, actor, expected revision, effective date, reason and causal reference. Exact keys differ by module: call its validator rather than imposing one generic envelope. Existing local modules often require `actorId='world-admin'`; an online adapter must authorize the authenticated principal first and record its audit identity. A browser-supplied local actor string is not authorization.

The hosted follow-up uses the original `cruise.manual_control` lock and rejects shared-delivery ownership in manual advance/storm paths. It adds real GET/POST `/hosted/worlds/{id}/events/storms` and GET `/events`. No cruise/managed-delivery configuration endpoint or background worker is exposed. Other domains listed here remain adapter gaps.

## Original wizard groups: do not equate “generation” with “physical setup”

| Original groups | Treatment for a selected illustrated preset |
| --- | --- |
| `seeds`, `town`, `housing`, `electric`, `gas`, `water`, `ami` | Snapshot-generation inputs. Freeze population, geometry, household/equipment distributions, network design and meter identities. A future editable demand or equipment overlay must be explicitly modeled, dated and tested; current initialization does not consume arbitrary changes to these objects. |
| `weather` | Legacy seasonal generation model, containing four seasonal distributions, persistence, storm frequency and heating/cooling bases. Not equivalent to the daily world's five-field init schema. Only the explicit world weather controls are currently accepted. |
| `incidents` | Legacy generation incident rates and manual-only flag. Map to the actual physical fault/hazard modules individually; never silently retain them as active daily settings. |
| `operations` | Legacy crews, shifts, response targets and movement speeds. Mixed execution/workforce concepts; no automatic port. VS owns enterprise staffing/queues, while explicit physical travel/execution belongs at the authorized integration boundary. |
| `customers_billing` | Mixed group: `services` fixes physical service topology; other fields include read-unit/cycle, currency/tax/tariffs and payer assumptions. Freeze service selection from the template; exclude enterprise tariff/billing configuration. Customer behavior uses the dedicated physical modules above, not blind import of this group. |
| `process`, `reading`, `vee`, `billing`, `contact`, `field`, `kpi` | Studio-year enterprise process, staffing, validation, billing, service centre, work queues and metrics. Do not expose as physical initial setup. Some field/customer concepts have separate world modules; those are distinct contracts. |
| `anomalies`, `scenario`, `outages` | Legacy Studio-run simulation inputs. Some concepts overlap physical meter/fault/storm capabilities, but these objects are not accepted world commands. Translate deliberately to validated physical controls before exposing. |

This catches two traps: `SimConfig.RUN_GROUPS` does not identify every enterprise field (`operations` and `customers_billing` are generation groups), and excluding every customer/field concept would also remove genuine physical/customer behavior.

## Suggested integration order

1. Keep cloud drafts limited to the schema they actually validate, with an explicit schema version and capability list.
2. Add adapter discovery that reports supported domains and command versions for the configured compute service. A reachable URL alone does not make every domain supported.
3. Add clock ownership/status and occupancy/storm event adapters first; prove schedule → advance → physical effect → restart → no duplicate event.
4. Add hazard/fault and customer behavior settings with existing revision/date/idempotency guards, then connector delivery and field integration with their owners.
5. If initial setup should preconfigure opt-in policies, create a recoverable initialization sequence: base world first, deterministic per-domain commands next, playable status only after all required commands commit. No partial failure should claim the whole draft was applied.

No new UI, runtime settings, source worlds, infrastructure or paid services were changed for this inventory. Ash's configurable connector belongs to shell/VS integration owners. Publishing and provisioning remain separate from this local code inventory.
