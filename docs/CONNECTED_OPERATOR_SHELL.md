# Saved-world commercial operator entry

UtilitySim keeps physical setup, events, observations and world navigation. The separate Virtual Systems operator page inspects the actual commercial owners associated with a selected physical premise. It does not introduce a Billing database, commercial worker, financial policy or clock in the public shell.

## Entry and identity

Open a saved simulation in `/world-control.html?id=<world instance>`. The illustrated town is a preview, not an interactive parcel hit-test map. **Explore a premise** pages through actual instance premises and inspects a safe physical summary. It never invents commercial IDs or property locations. A configured connected world offers **Open Virtual Systems records** for that exact world and physical premise.

The producer resolves its immutable commercial mapping. Physical premise and commercial premise/account IDs may differ. Unmapped, ambiguous, foreign or oversized scopes fail explicitly; the shell never substitutes a default account or silently truncates the view. This mapping does not change invoice/payment recipient selection.

## Fixed public routes

| Shell route | Producer route | Permission |
| --- | --- | --- |
| `GET /api/compute?action=premises&id=...&offset=0&limit=50` | `GET /hosted/worlds/{id}/premises` | `world.view` |
| `GET /api/compute?action=premise&id=...&premiseId=...` | `GET /hosted/worlds/{id}/premises/{premiseId}/summary` | `world.view` |
| `POST /api/operator?id=...`, action `premise` or `job` | `POST /hosted/worlds/{id}/operator` | `billing.view` |
| Same POST, action `release-read`, `bill`, `invoice`, `retry-job` | Same fixed operator route | `billing.view` and `billing.run` |

Every POST, including operator reads, requires same Origin. WorkOS identity must be current and email verified; current grants are scoped to the approved world's town. Only owner/billing roles have commercial mutation permission. The saved connector is account owned and its credential is sealed server side. The browser cannot supply an actor, grants, upstream URL, controller ID, Run ID or service credential. Page authentication does not replace API authorization.

The producer supplies the trusted human subject and the narrow commercial capabilities to its separately authenticated private operator service. It pins the selected world's registered Run/controller. Success uses `connected-operator-response/1` and must match pins, selected premise, action and command identity. The public gateway projects bounded display fields, excluding raw job parameters, attempts, payloads, technical errors, credentials and hidden physical truth.

## Commands, execution and recovery

Commercial commands use a canonical UUID persisted before POST. A lost or unreadable reply, authentication failure or generic 4xx retains the exact original request. Reload and retry use the same UUID and payload; refresh does not erase uncertainty. Retention is isolated by account and world, and another premise cannot replay or replace the pending operation. Browser storage failure disables unsafe mutations.

HTTP 202 confirms durable queue admission only. Use the scoped `job` action for actual execution progress, then refresh the commercial records for bills, invoices and receivables. Job completion is not proof of delivery or settlement. Business exceptions remain distinct from transport failures. There is no issued-document reversal or whole-cycle operation in this interface.

Virtual Systems uses its existing Billing/receivables owners and the connected controller's shared clock and lock. Paused Runs may accept scoped operator requests; background commercial work waits for resume. The operator page reports the actual shared clock and has no advancement action. The configured private composition executes the existing commercial queue; do not add a second native Billing worker.

## Release boundaries

These routes require the compatible producer operator proxy, bounded premise endpoints and opt-in private connected operator service with a separate server-only operator credential. Ash configures the actual persistent host, fixed origins, credential files, Run/controller/world pins and production access. Publishing the shell does not enable a host or create those bindings.

Accept the complete same-instance path with real HTTP owner stores, identity/grant substitutions, actual mapped records, queue admission vs committed output, and exact replay after reply loss. Local QA identity/transport adapters must be identified separately from production WorkOS and TLS verification. Existing Ashtown review and illustrated-preset expansion gates remain in force.
