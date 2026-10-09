# Webhook receivers

One receiver per language, each a single file over its standard library and the SDK beside it,
each doing the four things every receiver must:

1. **Verify the raw body** before parsing it — and refuse what does not verify with a `400`.
2. **Answer quickly**: queue the work and return `204`. Cortex waits fifteen seconds for a `2xx`,
   then retries.
3. **Handle each delivery once.** Delivery is at least once, and a retry or a replay from the
   Integrations screen carries the same `webhook-id`. These keep handled ids in memory; yours
   should keep them where the work they cause is written, under a unique constraint.
4. **Bound what it reads**: a megabyte here, far above anything Cortex sends.

| Language | Run |
| --- | --- |
| Python 3.10+ | `CORTEX_WEBHOOK_SECRET=whsec_… python examples/python/receiver.py 8081` |
| TypeScript, Node 22.18+ | `CORTEX_WEBHOOK_SECRET=whsec_… node examples/node/receiver.ts 8082` |
| Go 1.22+ | `cd examples/go && CORTEX_WEBHOOK_SECRET=whsec_… go run . 8083` |

## Proving one works

```bash
python examples/smoke.py python    # or node, or go
```

starts the receiver and sends it, over HTTP, a genuine delivery, the same delivery again, a
changed body, a stale timestamp and a missing signature — signed by `smoke.py`'s own
implementation of the scheme, with the secret and body of a delivery the platform signed. It
passes when the first is handled, the second recognised as a duplicate, and the three forgeries
refused. CI runs it for all three languages on every push.

Licensed under Apache-2.0, like everything in this repository.
