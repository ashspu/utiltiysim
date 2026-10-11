# Physical event/time UI handoff

2026-10-11. Owner: shell event/time subagent, branch `codex/event-time-ui`, worktree `P:/UtilitySim/worktrees/event-time-ui`, base `0067f61`. Scope authorised by Greg's request for GPT-6.1 Sol agents implementing the online physical-world plan. Standing coordination authority: Greg, 2026-10-11, chat `01a12aa3-5c1e-7142-aad0-dd177c7c9f09`. Shell coordinator owns build, protected pagegate, integration, browser QA and release; backend chat `01a12bf4-9f78-7411-ac48-15750ae1d151` owns hosted adapters. Root handles Slack in #vbs-agents thread `1791739340.071919`.

## Integration

Publish the new web files `world-control.html`, `world-control.js`, `world-control.css`, `world-control-core.mjs`, `world-control-events.mjs`. Protect the HTML through the existing WorkOS pagegate and link real runtime records with `/world-control.html?id=<instance UUID>`. Do not link setup drafts or source slugs as instances. No map renderer or catalog preview is added: source revision and independent instance ID are displayed directly from saved runtime status.

The same-origin compute gateway supplies actions `worlds`, `status`, `advance`, `observations`, `storms`, `events`, as agreed with the compute connector owner. No runtime URL, credential, identity header, localhost fallback, local world library or Virtual Systems dependency appears in this UI.

UTC cursor is the next unprocessed day. Advance-to-date is exclusive, with 1–31 new days per request. Absolute target capture suppresses duplicate click advancement. Any uncertain advance blocks commands until status refresh recovers persisted state. There is no automatic retry that recalculates a new target. The engine owns the monotonic/idempotent cursor and atomic daily commits.

Storm requests send only the hosted command fields; the server supplies actor/environment/fingerprint/schema. Schedule/cancel command IDs and exact bodies are retained in instance-scoped session storage solely for command retry, not world persistence. A pending command blocks advancing and switching instances. Definite 4xx rejection releases it; uncertain transport/5xx outcomes require exact retry. Successful commands reload schedules and actual outcome history. Cursor and revision checks remain server authoritative. Event history is paged with stable journal/schedule sequences and storm-day dates. All runtime text is inserted using textContent.

## Verification and remaining gates

`node --test prototypes/civic-atlas/test_world_control.mjs`: 3 passing tests for leap/year/DST boundaries, invalid dates and 31-day bounds; concurrent clicks sending one absolute target; and connection loss requiring recovery before subsequent advancement. `node --check` passes for both UI modules. These UI state tests do not constitute real engine restart or scheduling acceptance.

Integrated approved CUA browser QA remains with root after gateway/backend commits: open real instance, schedule a future storm, advance across its interval, inspect actual baseline/adjusted temperatures and journal lineage, reload/reopen the same committed state, verify cancelled future scenarios produce no effective days, and exercise ambiguous exact retries and mobile/keyboard behavior. Backend owner owns transaction/concurrency/restart tests. No deployment or merge performed here.

Runtime has no durable jobs, live progress, pause or cancellation of advances; UI explicitly reports that limit. Storm cancellation exists only before a scenario begins. Broader physical event domains need separately scoped adapters; no disconnected domain controls are presented.
