# Connect the existing Virtual Systems engine

The map shell can use the separately installed private Virtual Systems repository. Its source is not included in this public repository. Configure the backend process, not the browser:

```powershell
$env:ATLAS_VIRTUAL_SYSTEMS_ROOT = 'D:/path/to/virtual-systems'
.venv/Scripts/python.exe prototypes/civic-atlas/server.py --library --port 8044 --store out/civic-atlas-library
```

The compatible checkout must provide `billing.store`, `receivables.store`, `worldfeed.adapter`, `synth_runtime`, and `worldfield.recipient`. The integration was verified against private VS base commit `32c91ff2`, with the isolated large-batch performance revision `13271e12111d62be3a47e6a9199e83b0efd6a764`. Point the variable at that compatible optimized checkout for large towns. The original installation stays read-only. Existing VS runs are never opened or reset.

Each selected town receives dedicated stores inside `<store>/<preset>/virtual-systems/`: Billing owns `billing.sqlite`; Receivables owns `ledger.sqlite`. Source fingerprints bind the recipients to the same saved town. A source change requires an explicit migration or a new store. Stop the runtime before a filesystem backup (or use SQLite-consistent live backups). Preserve the whole town directory, including its physical world, recipient stores, field runs and server-side credentials.

## Main workflow

When the installation is configured, **Billing & meter reads** is the actual Virtual Systems workspace. Initialize the selected town, deliver its saved observations to MDM, and run a completed billing period. Periods include the start date and exclude the end date. The real recipient validates readings, bills contracts, creates invoices and delivers them to its separate receivables ledger. Source observation IDs and the recipient inbox make retries idempotent.

Missing observations remain missing. Held consumption requires a reasoned operator review. Use the exception filter and pagination to inspect every hold; the property action opens the same map premise and its actual account, source readings and invoices. The default recipient operation blocks invoicing when the selected cycle is incomplete. **Invoice eligible accounts** separately processes every fully billed account through the same public account-scoped guard. Accounts with missing or held consumption remain blocked. The saved invoices are resume checkpoints, so retrying a batch does not issue duplicates. The last-batch summary accounts for issued, eligible and held accounts; a partially invoiced period remains the default until all service is handled. The product never invoices an incomplete account.

The illustrative VS tariff configuration is explicitly separate from native UtilitySim tariffs: CAD 0.20/kWh electricity, 0.45/m³ gas, 1.80/m³ water, and 1.20/m³ derived sewer, with no fixed fee or tax. VS currently has a flat-rate tariff model. Its totals therefore need not match UtilitySim's tiered/delivery/tax calculations. The separate **Local charge preview** retains those native calculations for diagnostics and does not post to VS receivables.

## Billing issue to physical work

Open a property from an exception or the map, enter the reason for a water-service investigation, and dispatch the plumbing inspection. This creates a real VS investigation, a saved UtilitySim field assignment, and an authenticated assignment-bound delivery run. Existing physical leaks are repaired; a visit without a leak reports `not_found`. The product never injects a fault to make a repair appear successful.

The field report is initially pending. Review and accept it separately in the property dialog. Advance the next physical day, then deliver the new observations to MDM. Billing can now see the changed consumption while prior readings and posted documents remain intact. Stable command IDs prevent a lost reply or retry from repairing or reporting twice. Physical meter replacement remains a separately labeled local action; the actual VS field adapter supports water-leak repair only.

## Runtime ownership and scale

This integration is an explicit local supervisor: the user advances physical days, delivers observations, runs financial batches and requests field work. VS financial operations and observation receipt use noon UTC on the saved world's current simulation date, matching the field supervisor's instant and Eastern business date. Field visits use that same local business date and zero report-delay for this interactive workflow, with authenticated scheduler delivery and a separate clerk decision. Automatic shared world scheduling is not enabled.

Large financial batches require the separately maintained VS performance patch: transaction-local job progress, account-scoped readiness and the `Billing.invoice_batch(cycle)` context. This defers only the derived whole-cycle summary until batch completion; each account still validates and commits independently, and the final summary reconciles on error. The original VS checkout remains unchanged. Without the optimization the same guarded API works but repeated cycle scans make large runs impractical.

Observation delivery processes one committed day at a time through the real MDM adapter. It does not enable the unsharded shared world's 8 MiB daily gateway envelope; large towns exceed that gateway limit. This is not a claim that automatic scheduling or arbitrary large-run throughput has been verified. The seven town source packs, visual release and large-recipient performance have separate QA evidence.

The browser never receives private VS credentials or filesystem access. Hosted use additionally requires the durable backend, TLS, an allowed origin, and `ATLAS_API_TOKEN`; a static Vercel deployment alone cannot host these SQLite stores or the private VS engine.

## Verification

```powershell
$env:ATLAS_VIRTUAL_SYSTEMS_ROOT = 'D:/path/to/virtual-systems'
.venv/Scripts/python.exe -m pytest prototypes/civic-atlas/test_virtual_systems.py prototypes/civic-atlas/test_virtual_field.py -q
```

The optional tests use fresh disposable stores. They verify actual recipient read provenance, billing and invoice retries, a balanced independent ledger, durable reopen, authenticated field receipt/retry, explicit report acceptance, preservation of history, and the complete HTTP path from a physical leak through repair to reduced next-day consumption received by MDM. Without the private installation these tests skip, rather than report a fabricated integration success.
