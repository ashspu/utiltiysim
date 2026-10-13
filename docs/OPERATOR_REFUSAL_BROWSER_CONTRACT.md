# Permanent commercial refusal and invoice eligibility

The producer successor validates the private owner's response against the pinned Run/controller/premise/action, exact mutation UUID, HTTP status and full trusted request hash before translating its proof. Private hashing includes actor/capabilities and uses Python sorted compact JSON with ensure_ascii=True. This document does not reproduce the private implementation.

The public browser proof is an optional `rejection` object on a non-success response:

```json
{"commandId":"original UUID","requestHash":"64 lowercase hex characters","status":403,"disposition":"permanently-rejected"}
```

Browser `requestHash` is SHA256 of UTF-8 well-formed `JSON.stringify` over the original browser action body with sorted keys. Current request bodies are flat, ASCII-keyed and string-valued. Unicode remains literal in this browser hash; lone UTF-16 surrogates use JavaScript's escaped JSON form. This hash is deliberately different from the private full trusted request digest. En dash/café/CJK/emoji test body hash: `ca01be6f6314916dc1fd0ca7925d531b5e2b22e91c7f889ca0ba444ec25a92e8`.

Only `release-read` HTTP404 and `invoice`/`retry-job` HTTP403 can carry terminal proof. The shell gateway verifies returned pins and the translated hash against the exact browser body. The browser again verifies all four proof fields, matching HTTP status, UUID and retained payload hash before discarding its pending command. It rechecks the stored identity/body before removal, preserving a newer command from another page. No terminal claim is inferred from an HTTP code, error text or transport failure. Generic/auth/preflight refusals, busy409, clock503, conflicting UUID content and malformed proofs retain the original request.

A proved permanent refusal reports nonacceptance and requires refreshing records before another mutation. It never becomes an accepted job or business-success receipt. Existing successful receipt storage/replay is unchanged. Browser storage removal/hash failures retain recovery state.

Premise responses optionally include `invoiceEligibleAccountIds`, at most 200 distinct IDs drawn only from that response's scoped accounts. The shell preserves the actual owner projection without adding cohorts. Missing eligibility means unknown and disables invoicing; an empty list means known none. Other commercial records remain visible. Eligibility does not imply operator permission or cycle readiness; fresh permission and private owner checks still apply.

The browser uses native Web Crypto SHA256. Root-owned Node/test-DOM acceptance adapters must provide `crypto.subtle` as well as `crypto.randomUUID`; this is a test environment capability, not a production authentication substitution. No browser bearer credentials, private URLs, actor capabilities or private trusted request are persisted or exposed.

## Review and validation evidence

Shell successor is based on accepted public operator head `8b0ded085f241e609fd73f3c226ed950c53b4b6d`. Contract reviewed against frozen private refusal head `672f54d07902611f235bba2b54229fddeacfaa51` and its owner-supplied refusal documentation, plus the producer successor implementation in `b-connected-operator-proof` based on public `05426c5ec640de650d664eddfaa38f7f1cdfdd52`. Producer successor publication remains its owner's responsibility; this review does not claim an uncommitted producer source pin is a release.

Local Node checks: all 144 shell auth tests pass, including 35 focused operator API/state/page tests. Tests cover exact owner pins and proof field set, body hashes with Unicode/key reordering/lone surrogate behavior, mismatched or private-ASCII digest rejection, lost permanent refusal reply and reload retry, retained auth/busy/clock uncertainty, storage removal faults, successful receipt replay, eligible-account scope/duplicates/bounds, absent eligibility, actual page proof handling, and required refresh after permanent refusal. Whitespace checks pass. No full engine rerun, private source copying, fixture mutation, deploy, push or PR was performed by this workstream.

Actual producer → private service → shell HTTP acceptance remains coordinator-owned and separate from these Node checks. Prior accepted browser receipts and immutable world data are unchanged.
