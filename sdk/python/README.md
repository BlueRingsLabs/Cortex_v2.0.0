# cortex-webhooks

Verify a Cortex webhook and read it as a typed event. Python 3.10+, standard library only.

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

The scheme is Standard Webhooks v1. Deduplicate on the `webhook-id` header: delivery is at least
once. The SDKs for TypeScript and Go, and what every receiver should do, are described in the
[README one directory up](../README.md).

Apache License 2.0. Copyright 2026 Gonzalo Luis Romero.
