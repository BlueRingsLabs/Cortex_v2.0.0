# Cortex webhook SDKs

Verify a Cortex webhook and read it as a typed event, in Python, TypeScript or Go. Each SDK
is a few dozen lines over its language's standard library — no dependencies — and each is
tested against [`vectors.json`](vectors.json): deliveries signed by the platform's own
signing code, and the verdict each must get. The event types are generated from the
platform's catalogue, so they are the shapes Cortex actually sends.

The scheme is [Standard Webhooks](https://www.standardwebhooks.com) v1, so any of its
libraries works too. The full reference — headers, delivery semantics, the retry schedule
and every event field by field — is [`api/webhooks.md`](../api/webhooks.md).

## Python (3.10+)

```bash
pip install "cortex-webhooks @ git+https://github.com/BlueRingsLabs/Cortex_v2.0.0#subdirectory=sdk/python"
```

```python
from cortex_webhooks import WebhookVerificationError, verify

def receive(request):
    try:
        event = verify(SECRET, request.headers, request.body)  # the raw body, as bytes
    except WebhookVerificationError as refused:
        return 400, refused.reason
    if event["type"] == "invoicing.invoice_issued":
        queue_invoice(event["data"]["invoice_reference"], event["data"]["total_minor"])
    return 204, ""
```

## TypeScript (Node 22.18+)

```bash
npm install "github:BlueRingsLabs/Cortex_v2.0.0#path:sdk/typescript"
```

```ts
import { verify, WebhookVerificationError } from "@blueringslabs/cortex-webhooks";

app.post("/cortex", express.raw({ type: "application/json" }), (req, res) => {
  try {
    const event = verify(SECRET, req.headers, req.body); // req.body is the raw Buffer
    if (event.type === "payments.payment_failed" && event.data.retryable) {
      scheduleRetry(event.data.attempt_key);
    }
    res.sendStatus(204);
  } catch (error) {
    res.status(400).send(error instanceof WebhookVerificationError ? error.reason : "invalid");
  }
});
```

## Go (1.22+)

```bash
go get github.com/BlueRingsLabs/Cortex_v2.0.0/sdk/go
```

```go
func receive(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	event, err := cortexwebhooks.Verify(secret, r.Header, body, time.Now())
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if event.Type == cortexwebhooks.EventActivationPortExecuted {
		var port cortexwebhooks.ActivationPortExecutedData
		_ = json.Unmarshal(event.Data, &port)
	}
	w.WriteHeader(http.StatusNoContent)
}
```

## What every receiver should do

* **Verify the raw body.** Parse it after verifying, never before.
* **Answer 2xx within fifteen seconds**, after queueing the work rather than doing it.
* **Deduplicate on `webhook-id`.** Delivery is at least once; a retry or a replay carries the
  same id.
* **Do not rely on order.** Each event carries the time it was published; the API is the
  source of truth for current state.
* **Answer 410 only to stop for good.** It pauses the endpoint until somebody resumes it.
  Any other failure is retried for about a day.

## Testing the SDKs

```bash
python -m unittest discover -s sdk/python/tests -t sdk/python   # Python 3.10+
node --test sdk/typescript/test/*.test.ts                      # Node 22.18+
(cd sdk/go && go test ./...)                                   # Go 1.22+
```

Each runs the same [`vectors.json`](vectors.json): deliveries signed by the platform's own
signing code at release, and the verdict each must get. CI runs all three on every push, and
the [examples](../examples/) against the same deliveries over HTTP.

## Licence

Apache License 2.0 — see [`LICENSE`](LICENSE). Copyright 2026 Gonzalo Luis Romero. The SDKs
are licensed so that integrators can embed them; the Cortex platform itself is not.
