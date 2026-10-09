# Integrating with Cortex

For an engineer connecting another system to a Cortex installation: what the
[OpenAPI document](../api/openapi.json) does not tell you, and the four places a naive
integration goes wrong.

---

## 1. The surface

Everything is under `/api/v1`; there is no unversioned surface. [`api/openapi.json`](../api/openapi.json)
is the integration subset — the routes an external system calls, with their request and response
shapes — generated from the platform's code at release. A running installation serves its whole
specification at `/openapi.json`.

## 2. Sessions are bound to a key

A Cortex access token is **not a bearer token**. It is bound to a key pair your client holds, and
every authenticated request also carries a **DPoP proof** ([RFC 9449](https://www.rfc-editor.org/rfc/rfc9449)):
a short-lived JWT signed by your private key, naming the method, the URL and a hash of the token.
A token stolen from a log or a proxy is inert, because whoever stole it cannot sign the proof.

```
POST /api/v1/auth/login          tokens, bound to the key in the proof's jwk header
POST /api/v1/auth/refresh        rotate
POST /api/v1/auth/step-up        raise the session's assurance for privileged operations
GET  /api/v1/auth/context        who this session is
POST /api/v1/auth/logout
```

Generate an Ed25519 or ES256 key pair once per client and keep the private half. The proof must
carry:

| Claim | Rule |
| --- | --- |
| `typ` | `dpop+jwt` |
| `alg` | from the allow-list; `none`, HMAC and RS256 are refused |
| `jwk` | the public key only |
| `htm`, `htu` | the method, and the URL as scheme, host and path — no query, no fragment |
| `ath` | base64url(SHA-256(access token)), on every request after login |
| `jti`, `iat` | unique per proof, issued within ±30 seconds |

Every `jti` is burned in a replay cache shared by every API process, so a proof cannot be reused
because the retry landed somewhere else. Send the tenant in `x-cortex-tenant`: it scopes the
request and does not authorise it — the wrong tenant returns nothing, not someone else's data.

## 3. Errors have one shape

```json
{
  "error": { "code": "precondition_failed", "category": "precondition", "message": "…" },
  "correlation_id": "01M1BPFGBJVDTDVWPZZNRZW4AT"
}
```

Branch on `category`, which tells you how to react, and on `code`, which is stable; never on
`message`.

| Category | React by |
| --- | --- |
| `validation` | fixing the request |
| `authentication` | re-authenticating — or stepping up: a `401` with code `mfa_required` means "authenticate more strongly", not "no" |
| `authorization` | nothing; the session is not permitted |
| `not_found` | nothing |
| `conflict` | re-reading and deciding; somebody else changed it |
| `rate_limit` | backing off exponentially |
| `precondition` | satisfying the stated precondition first |
| `dependency` | retrying with backoff; something downstream is unavailable |
| `internal` | reporting it, with the correlation id |
| `security` | stopping, and looking at your own logs |

**The `correlation_id` is on every response, success and failure**, and in the
`X-Cortex-Correlation-Id` header. Log it: it is the one thread between your request and the
operator's logs.

## 4. Anything that moves money is idempotent on your key

Payments, point-of-sale charges, invoice emission, payroll, settlements and online charging
sessions take a key you supply; the same key with the same payload returns the same result, not a
second effect. **Generate the key before the first attempt** — a key generated per retry is a
request id, and it will charge somebody twice.

For a switch, `POST /api/v1/bss/balances/sessions` quotes and holds credit for **units**, not
money: Cortex prices the increment under the tariff the subscription was sold under. A refusal for
want of credit is a `200` with `granted: false` — the ordinary outcome for a prepaid line, not an
error. The session reference is the idempotency key: retry freely after a timeout.

## 5. Listings are keyset-paginated

Pass back the opaque `cursor` a page gives you (bare-array listings return it in `X-Next-Cursor`);
its absence ends the walk. Page four hundred costs what page one costs, and rows inserted while
you walk cannot make you skip or repeat one. Do not construct a cursor.

## 6. Hearing about what happened: webhooks

Register a receiver with the facts it wants; its secret is shown once. Every delivery is a `POST`
signed to the [Standard Webhooks](https://www.standardwebhooks.com) v1 scheme:

| Header | Meaning |
| --- | --- |
| `webhook-id` | the message id — the same on every retry and replay |
| `webhook-timestamp` | seconds since the epoch, when this attempt was signed |
| `webhook-signature` | `v1,` and base64(HMAC-SHA256(secret, `{id}.{timestamp}.{body}`)); several during a secret rotation |

What a receiver must do:

* **Verify the raw body before parsing it**, with one of the [SDKs](../sdk/) — or any Standard
  Webhooks library.
* **Answer 2xx within fifteen seconds**, after queueing the work rather than doing it.
* **Deduplicate on `webhook-id`**: delivery is at least once.
* **Not rely on order**: each event says when it was published; the API is the source of truth
  for current state.
* **Answer 410 only to stop for good** — it pauses the endpoint until an administrator resumes
  it. Any other failure is retried with backoff for about a day, then dead-lettered where an
  administrator can see why and replay it.

Every fact, field by field, is in [`api/webhooks.md`](../api/webhooks.md); a JSON Schema for each
body is in [`api/schemas/`](../api/schemas/).

---

*Gonzalo Romero — sole author.*
