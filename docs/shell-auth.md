# Hosted shell authentication

The production root is the UtilitySim landing page. It lists the versioned town
library and never chooses a remembered or default map. Explicit `/?town=...`
links retain their town, premise and page after sign-in. `/library.html?town=...`
opens the selected workspace. The desktop launcher remains independently usable.

## Identity and permissions

WorkOS AuthKit provides the identity and encrypted session. Login uses PKCE and
a ten-minute encrypted, HttpOnly browser cookie to bind callback state. Sessions
use HttpOnly, Secure, SameSite=Lax cookies in hosting; localhost uses HTTP for QA.
Logout is POST with an exact origin check, clears the local cookie and ends the
WorkOS session. Session responses and gateway responses are never cached.

GolfyGolf reference reviewed: `golf-sim/apps/api/src/auth/{routes,actor,bundles}.ts`
and its domain capability catalogue at main commit `6f54fbf`. GolfyGolf uses
WorkOS identity with application-owned scoped grants. A new identity has no
capabilities. Its domain-specific course/player roles are not UtilitySim roles.

UtilitySim applies that model with the following explicit application bundles:

| Role | Capabilities |
| --- | --- |
| owner | All UtilitySim capabilities |
| operator | View/advance worlds, view billing, dispatch field work |
| billing | View worlds and billing, run billing actions |
| support | View worlds and billing, dispatch field work |
| analyst | View worlds and billing |

`UTILITYSIM_ROLE_GRANTS` is an operator-managed JSON object keyed by WorkOS user
ID, for example `{"user_example":[{"role":"analyst","town":"ashtown-5000"}]}`.
Each grant names a catalog town slug or `*`, and can include `expiresAt` or
`revoked:true`. Unknown roles, expired grants, unverified email addresses and
unlisted users are denied. No first-user, domain or email owner bootstrap exists.
Update the environment variable and redeploy to change a hosted grant. There is
not yet an in-app permission editor or GolfyGolf's database-backed grant audit UI.

The `/atlas/api/*` gateway checks the verified WorkOS identity, capability and
town before calling the runtime. Unknown routes are denied. It forwards only to
the configured HTTPS runtime, with the server-only `UTILITYSIM_RUNTIME_TOKEN`.
The runtime must enforce its bearer token and independently validate its internal
town ID. Public static town artwork is a preview, not protected billing data.
Do not place secrets or customer data in static map assets.

## Environment setup

Use a distinct UtilitySim WorkOS project with separate production and staging
applications. Production callback is
`https://utiltiysim.vercel.app/api/auth/callback`; sign-out and homepage are
`https://utiltiysim.vercel.app/`.

Development uses staging, with callback `http://localhost:3000/api/auth/callback`
and sign-out `http://localhost:3000/`. Preview credentials use staging and an
explicit branch alias callback and logout URL. Scope preview environment values
to that branch; register additional exact aliases before enabling other preview
branches. Do not use wildcard callbacks or production secrets in previews.

Required server variables are listed in `.env.example`. Generate a separate
random cookie password of at least 32 characters for each Vercel environment.
Secrets are supplied to Vercel via stdin and never enter the static build or Git.
No cross-origin browser token access is required, so AuthKit CORS stays empty.

## Verification

Run `npm run test:auth`, `npm test --prefix packages/town-viewer`, then
`node scripts/build_site.mjs`. Exercise a real staging AuthKit callback and logout,
an authenticated account without grants, town-scoped access, a signed-out gateway
request and the deployed root separately. The hosted shell does not establish a
hosted billing runtime or migrate the saved local worlds. A missing runtime
returns an explicit 503 rather than inventing bills or simulation state.
