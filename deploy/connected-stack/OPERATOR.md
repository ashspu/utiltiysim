# Optional connected billing operator

Keep `operatorEnabled: false` until the approved private controller build supports
the typed operator bridge and the public producer supports its fixed-world proxy.
This does not activate a Vercel account connection or relax the private release hold.

For an approved deployment, set `operatorEnabled: true` with the existing
`owner-cli-stopped/1` configuration. Add `UTILITYSIM_OPERATOR_TOKEN` to the producer's
`requiredSecrets` and `CONNECTED_OPERATOR_TOKEN` to the controller's. Protected
service files must supply the **same distinct** 32–4096 character printable ASCII
capability. It must differ from gateway, machine, control and runtime clock secrets.
Never place its value in deployment JSON, CLI arguments, browser storage or Slack.
The reviewed startup adapter creates a temporary mode0600 token file and passes
`--operator-token-file` to the existing `connected serve` process; it removes the
file when that process exits. The producer uses its existing fixed controller URL.

Provision a dedicated `worker` Run actor with no grants and a non-admin role. The
private bridge processes native Billing work synchronously in the controller's
existing worker lifetime, between shared Run advances. Do not launch native Billing
background workers or add another public listener. Queued jobs wait while paused.

Bootstrap `connectedOperatorView` version1 with the approved world's fingerprint
and explicit physical-premise → commercial-premise bindings. Keep observation
installation mappings and financial recipient cohorts separate. A property view
does not enroll an account for bill delivery or payment settlement. Existing
approved configurations without the view manifest retain the legacy scope.

The current three-service topology, loopback controller route, independent owner
databases and complete stopped-owner recovery inventory remain unchanged. Operator
receipts are durable Billing events and are included with that owner. Before live
activation, verify actual gateway → producer → controller property access, current
grants, attributed read review, exact job recovery, shared-clock serialization and
original-path restore using the approved source commits. Local portable checks
cannot establish real host storage, TLS, deployed identity or restore readiness.
