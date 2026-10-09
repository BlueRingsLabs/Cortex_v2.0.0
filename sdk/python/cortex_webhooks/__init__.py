"""Receive Cortex webhooks: verify the signature, then read a typed event.

    from cortex_webhooks import WebhookVerificationError, verify

    try:
        event = verify(secret, request.headers, request.body)
    except WebhookVerificationError as refused:
        return 400, refused.reason
    if event["type"] == "invoicing.invoice_issued":
        total = event["data"]["total_minor"]

The event types are generated from the platform's own catalogue; see ``events.py``.
"""

from .events import EVENT_TYPES, Event
from .verify import TOLERANCE_SECONDS, WebhookVerificationError, verify

__version__ = "2.0.0"

__all__ = [
    "EVENT_TYPES",
    "TOLERANCE_SECONDS",
    "Event",
    "WebhookVerificationError",
    "__version__",
    "verify",
]
