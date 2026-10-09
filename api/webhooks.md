# Cortex webhooks — the reference

<!-- Generated from the Cortex platform's own code at release 2.0.0. Do not edit. -->

Cortex sends a tenant's facts to the systems it runs — an ERP, a data warehouse, a network
provisioning system, a contact-centre platform — as they happen: an invoice issued, a payment
declined, a line barred, a number ported. Each is one signed HTTPS `POST` to an endpoint the
tenant registered, for the facts it chose.

A fact carries identifiers and codes, never a customer's name, number or document. A receiver
that needs those reads them from the API with its own credentials, under its own permissions.

## What arrives

```http
POST /your/endpoint HTTP/1.1
Content-Type: application/json
User-Agent: Cortex-Webhooks/2
webhook-id: 01K8Z3R2V9Q6M4T1W7Y5B3N8C0
webhook-timestamp: 1790000000
webhook-signature: v1,r5kYEmvONNyB5j4KfCiteYVkQUEJk4H/2jalBwGnuP0=

{"data":{"currency_code":"ARS","cycle_reference":"2026-09","due_on":"2026-10-20","invoice_reference":"A-0001-00000042","kind":"invoice","subject_id":"01K8Z3QX7M2N5P8R1T4V6W9Y3B","total_minor":1234500},"schema_version":1,"timestamp":"2026-09-21T14:13:17Z","type":"invoicing.invoice_issued"}
```

That delivery is genuine: it verifies under `whsec_AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=` at the timestamp it carries
(the secret is the kit's test key — 32 bytes counting up — and is never issued to an endpoint).

| Header | Meaning |
|---|---|
| `webhook-id` | The fact's own identity. The same on every retry and every replay: **deduplicate on it.** |
| `webhook-timestamp` | When this attempt was signed, in seconds since the epoch. |
| `webhook-signature` | `v1,` and base64 of HMAC-SHA256 over `{webhook-id}.{webhook-timestamp}.{body}`, under the endpoint's secret. During a rotation, two signatures, space-separated. |

The body is the envelope `type`, `timestamp` (when the fact was published, UTC — not when this
attempt was made), `schema_version` and `data`, compact, keys sorted, UTF-8.

## Verifying

This is the [Standard Webhooks](https://www.standardwebhooks.com) scheme, so any of its
libraries verifies a Cortex delivery. The kit ships one verifier per language, each tested
against [`sdk/vectors.json`](../sdk/vectors.json) — deliveries signed by the platform's own
signing code, and the verdict each must get:

```python
from cortex_webhooks import WebhookVerificationError, verify

event = verify(secret, request.headers, raw_body)  # raises WebhookVerificationError
```

```ts
import { verify } from "@blueringslabs/cortex-webhooks";

const event = verify(secret, request.headers, rawBody); // throws WebhookVerificationError
```

```go
event, err := cortexwebhooks.Verify(secret, r.Header, body, time.Now())
```

Whatever verifies it must:

1. use the **raw body**, as received. A parsed and re-serialised body is a different byte
   string and will not verify;
2. compare in **constant time**;
3. refuse a `webhook-timestamp` more than **five minutes** from its own clock, and deduplicate
   `webhook-id` within that window, so a captured delivery cannot be replayed;
4. accept the delivery if **any** `v1` signature in the header verifies.

The secret is `whsec_` followed by base64 of 32 random bytes. It is shown once, when the endpoint
is registered or its secret rotated. After that the console shows its fingerprint: the
SHA-256 of the 32 key bytes, which a receiver can compute to confirm it holds the same one.

## Delivery

* **At least once.** A receiver may see a fact twice — after a timeout it answered too late,
  after a replay. The `webhook-id` is the same; deduplicate on it.
* **Not in order.** Two facts can arrive in either order. Each carries its own `timestamp`, and
  the API is the source of truth for current state.
* **Acknowledge with 2xx within 15 seconds**, after queueing the work rather than
  doing it. Anything else is a failure, and the body of the answer is not read beyond
  64 KiB or kept.
* **Redirects are not followed.** A `3xx` is a failure: it is a second destination nobody
  registered.
* **`410 Gone` stops delivery**: the delivery is dead-lettered and the endpoint paused until an
  operator resumes it.
* **`429` and `503` may carry `Retry-After`**, in seconds or as an HTTP date. It lengthens the
  wait, never shortens it, and never beyond 10 hours.

### Retries

8 attempts over about a day:

| Attempt | Waits | Since the first |
|---|---|---|
| 1 | immediately | 0 h 00 min |
| 2 | 5 s | 0 h 00 min |
| 3 | 5 min | 0 h 05 min |
| 4 | 30 min | 0 h 35 min |
| 5 | 2 h | 2 h 35 min |
| 6 | 5 h | 7 h 35 min |
| 7 | 10 h | 17 h 35 min |
| 8 | 10 h | 27 h 35 min |

After the last, the delivery is **dead**: listed in the console with every attempt and its
answer, and replayable with the same `webhook-id` and the same bytes. If the endpoint has not
accepted anything for a day when a delivery dies, it is paused too, so its backlog waits for an
operator instead of dying one fact at a time. A paused endpoint keeps queueing; resuming sends
the backlog.

Delivered rows are kept 30 days and dead ones 90.

## Registering an endpoint

In the console under **Administration → Integrations**, or over the API:

| Route | Does | Needs |
|---|---|---|
| `GET /api/v1/integrations/webhooks/catalogue` | The facts below, field by field, with their JSON Schemas | `platform:read_integrations` |
| `GET /api/v1/integrations/webhooks` | Endpoints, their health and backlogs, and the hosts facts may leave for | `platform:read_integrations` |
| `POST /api/v1/integrations/webhooks` | Register: reference, URL, the facts, a reason. Answers with the secret, once | `platform:manage_integrations`, second factor |
| `PATCH /api/v1/integrations/webhooks/{reference}` | Move it, change its facts or description, with a reason | `platform:manage_integrations`, second factor |
| `POST …/{reference}/pause`, `…/resume`, `…/retirement` | Hold, resume, or end it — each with a reason | `platform:manage_integrations`, second factor |
| `POST …/{reference}/secret` | Rotate: a new secret, the old one signing beside it for 0 to 168 hours | `platform:manage_integrations`, second factor |
| `POST …/{reference}/tests` | Queue a signed `webhook.ping`, tried once | `platform:manage_integrations`, second factor |
| `GET …/{reference}/deliveries?state=` | The delivery log, newest first, by `X-Next-Cursor` | `platform:read_integrations` |
| `GET …/deliveries/{id}` | One delivery: its exact body and every attempt | `platform:read_integrations` |
| `POST …/deliveries/{id}/replay` | Send a dead delivery again, with a reason | `platform:manage_integrations`, second factor |

An endpoint is `https` on port 443, at a name rather than an address, with no credentials in
the URL. Every send resolves the name again and refuses an address in a private range or the
cloud metadata service. Registering is the decision that facts may leave for that host: it needs
a second factor and a reason, and it is on the audit chain. A tenant registers at most
20 endpoints.

### Rotating a secret without missing a delivery

Rotate with an overlap: from then until the overlap ends, every delivery carries a signature
under the new secret and one under the old. Install the new secret on the receiver at any point
in the window; it verifies before and after.

## The facts

Every endpoint receives only the facts it was registered for. There is no "everything": a fact
added in a later release reaches a receiver when somebody chooses to send it there.

`webhook.ping` is sent only by the console's **Send a test ping**, with `data.endpoint_reference`.
Schema: [`schemas/webhook.ping.v1.json`](schemas/webhook.ping.v1.json).

### `activation.port_executed` (v1)

A number moved between carriers on its execution day. `direction` says which way; a port out is the moment retention has lost the line.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `counterparty_code` | string | The other carrier's code. |  |
| `direction` | string | in: the number arrived; out: it left for another carrier. | `in`, `out` |
| `executed_on` | string (date) | The day the number moved. |  |
| `port_reference` | string | The portability request's reference. |  |
| `subject_id` | string or null (ulid) | The customer holding the line the port activated; null for a port with no order behind it, which names nobody. |  |

Schema: [`schemas/activation.port_executed.v1.json`](schemas/activation.port_executed.v1.json)

### `cases.case_opened` (v1)

A customer case was raised and routed. Rules escalate by priority, category or queue.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `case_reference` | string | The case's reference, as the case screens and API show it. |  |
| `category` | string | The tenant's own category code for the case. |  |
| `channel` | string | How the case came in: phone, email, store, chat... |  |
| `priority` | string | The case's priority. | `high`, `low`, `normal`, `urgent` |
| `queue_code` | string | The code of the queue the case was routed to. |  |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |

Schema: [`schemas/cases.case_opened.v1.json`](schemas/cases.case_opened.v1.json)

### `cases.case_sla_breached` (v1)

A case ran past a service level it was promised -- first response or resolution. Published once per clock, when the sweep first finds it late.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `case_reference` | string | The case's reference, as the case screens and API show it. |  |
| `priority` | string | The case's priority. | `high`, `low`, `normal`, `urgent` |
| `queue_code` | string | The code of the queue the case was routed to. |  |
| `sla_kind` | string | Which promise was missed. | `first_response`, `resolution` |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |

Schema: [`schemas/cases.case_sla_breached.v1.json`](schemas/cases.case_sla_breached.v1.json)

### `dunning.step_taken` (v1)

A collections case took a step of its schedule -- a reminder, a warning, a suspension. Once per step: the step's own row is what makes it exactly-once.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `action` | string | What the step did. | `refer`, `remind`, `suspend`, `warn`, `write_off` |
| `case_reference` | string | The collections case's reference. |  |
| `days_overdue` | integer | How late the debt was when the step ran. |  |
| `step_no` | integer | Which step of the schedule, from 1. |  |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |

Schema: [`schemas/dunning.step_taken.v1.json`](schemas/dunning.step_taken.v1.json)

### `identity.principal_created` (v1)

A principal now exists. Consumers may provision module-local records for them.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `base_kind` | string | Which kind of account: staff, leadership, administrator, a customer's own or a machine identity. | `administrator`, `client`, `employee`, `manager`, `service` |
| `principal_id` | string (ulid) | The new account. |  |

Schema: [`schemas/identity.principal_created.v1.json`](schemas/identity.principal_created.v1.json)

### `identity.principal_suspended` (v1)

A principal's access was withdrawn. Consumers reassign their work and close sessions.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `principal_id` | string (ulid) | The account whose access was withdrawn. |  |
| `reason` | string | A machine code, status_changed_to_<status>. Never free text. |  |

Schema: [`schemas/identity.principal_suspended.v1.json`](schemas/identity.principal_suspended.v1.json)

### `invoicing.invoice_issued` (v1)

A customer's document for a cycle was numbered and sealed -- an invoice, or a statement when an offer took the whole bill. Rules watch large bills and warn before a charge.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `currency_code` | string (currency) | ISO 4217 code of the amount. |  |
| `cycle_reference` | string | The billing cycle the document closes. |  |
| `due_on` | string (date) | When payment is due. |  |
| `invoice_reference` | string | The document's number: fiscal for an invoice or a credit note, from the statements' own series for a statement. |  |
| `kind` | string | An invoice, a credit note, or a statement that demands nothing. | `credit_note`, `invoice`, `statement` |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |
| `total_minor` | integer | An amount in minor units of currency_code -- cents, centavos. |  |

Schema: [`schemas/invoicing.invoice_issued.v1.json`](schemas/invoicing.invoice_issued.v1.json)

### `payments.payment_failed` (v1)

A gateway declined a charge. Not published for an unknown outcome: a charge nobody answered for may have landed. Rules raise a follow-up for collections.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `amount_minor` | integer | An amount in minor units of currency_code -- cents, centavos. |  |
| `attempt_key` | string | The attempt's idempotency key, unique per charge attempt. |  |
| `currency_code` | string (currency) | ISO 4217 code of the amount. |  |
| `failure_code` | string | Why the gateway declined, as a closed code. | `declined`, `expired`, `insufficient_funds`, `invalid_request`, `suspected_fraud`, `unavailable` |
| `invoice_reference` | string or null | The invoice the charge was for; null for a charge against no invoice. |  |
| `retryable` | boolean | Whether retrying the same method later is sensible. |  |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |

Schema: [`schemas/payments.payment_failed.v1.json`](schemas/payments.payment_failed.v1.json)

### `subjects.subject_created` (v1)

A subject record was opened. Consumers may begin holding data against it.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `kind` | string | A person or an organisation. | `organisation`, `person` |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |

Schema: [`schemas/subjects.subject_created.v1.json`](schemas/subjects.subject_created.v1.json)

### `subjects.subject_erased` (v1)

A subject exercised erasure. Every consumer holding derived identifying data must destroy it — this is the event that makes a right to be forgotten reach modules that never owned the record.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |

*Never sent:* `erasure_basis` -- Text an operator typed to record the legal ground. Usually a statute, sometimes a sentence naming who asked -- it stays in the audit trail and does not leave the deployment.

Schema: [`schemas/subjects.subject_erased.v1.json`](schemas/subjects.subject_erased.v1.json)

### `subjects.subject_reclassified` (v1)

A subject's data classification changed. Consumers re-evaluate their handling rules.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `classification` | string | The sensitivity the customer's record is now handled at. | `confidential`, `internal`, `public`, `restricted` |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |

Schema: [`schemas/subjects.subject_reclassified.v1.json`](schemas/subjects.subject_reclassified.v1.json)

### `subscriptions.subscription_suspended` (v1)

A hold was placed on a line -- for credit, fraud, a customer's request or a lost handset. Rules raise a follow-up for retention or collections.

| Field | Type | Meaning | Values |
|---|---|---|---|
| `barring` | string | outgoing bars calls and data the customer makes; full bars everything. | `full`, `outgoing` |
| `kind` | string | Why: non-payment, the customer's request, fraud, theft or a regulator. | `customer_request`, `fraud`, `non_payment`, `regulatory`, `theft` |
| `subject_id` | string (ulid) | The customer the fact concerns. Read them with GET /subjects/{id}. |  |
| `subscription_reference` | string | The line or service that was barred. |  |

Schema: [`schemas/subscriptions.subscription_suspended.v1.json`](schemas/subscriptions.subscription_suspended.v1.json)
