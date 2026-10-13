# Workspace controls

Saved setup cards now offer **Delete** (move to Trash) and **Restore**. These actions
change only the account's saved starting conditions; they retain the exact map pins
and physical configuration and do not delete a simulation or its recorded history.
Fresh verified town ownership and the current setup revision are required. Redis
stores the transition and immutable command receipt atomically in the owner hash.
Repeated commands return their original receipt without rewriting a later restore.

The browser stores the exact lifecycle request before sending it. Unknown outcomes
keep that request across reload; new edits, starts and lifecycle actions wait for
recovery. Definitive stale/invalid requests can be dismissed explicitly before
reloading the current records. A pending simulation creation must be recovered
before its starting setup can be deleted. Storage failures prevent transport.

The workspace Settings cog groups the existing owner compute connection page and
the actual simulation/property billing handoff. It does not fabricate an import
download or register a runtime. Actual billing access continues through the owned
world, premise summary and separate Virtual Billing System operator page.

The wizard uses coloured collapsible groups, compact precise inputs and a single
AMI/AMR/manual distribution with two keyboard-accessible boundaries. Optional
groups keep their existing Off defaults and retain their values while collapsed.
Typing a share adjusts a neighbouring segment to keep the total at 100%; saved
values and configuration versions are never silently normalized or upgraded.

`/settings-concepts.html` contains three working layouts using the supported v4
catalog: Atlas cards, Seasonal canvas and Control desk. Changes are independent
preview drafts, remain in that page and never save or start a simulation. Atlas
cards is the direction applied to the production wizard.

Verification includes account/town isolation, atomic Lua replay and restore,
actual browser delete→Trash→restore using disposable local records, lost-response
recovery and storage/duplicate-send guards, exact saved-version round trips and
fractional/edge-case meter mixes. Desktop layout and keyboard checks cover the
normal viewport and a 900px desktop window. Preview authentication/records are
explicit test adapters; no real owner's setups were changed.
