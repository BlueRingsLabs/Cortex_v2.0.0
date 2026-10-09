"""Verify a Cortex webhook before believing a word of it.

A delivery carries three headers -- ``webhook-id``, ``webhook-timestamp``, ``webhook-signature``
-- and the signature is HMAC-SHA256, under the endpoint's secret, over
``"{id}.{timestamp}.{body}"``, base64, prefixed ``v1,`` (Standard Webhooks). During a secret
rotation the header carries two signatures, space-separated, and either verifying is enough.

Three things a hand-written verifier usually gets wrong, done here:

* the body is verified as the **bytes received**, never a parsed and re-serialised copy;
* the comparison is **constant-time**;
* the timestamp is checked against a **tolerance**, so a captured delivery cannot be replayed
  tomorrow. Five minutes by default; deduplicate on ``webhook-id`` within that window.

Standard library only.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import cast

from .events import Event

#: Seconds a delivery's timestamp may differ from this machine's clock.
TOLERANCE_SECONDS = 300
_PREFIX = "whsec_"


class WebhookVerificationError(Exception):
    """A delivery that must not be believed, and a machine-readable reason why.

    ``reason`` is one of ``missing_header``, ``malformed_timestamp``, ``timestamp_too_old``,
    ``timestamp_too_new``, ``malformed_secret``, ``no_matching_signature`` and
    ``malformed_body``. Answer any of them with a 4xx other than 410 -- a 410 tells Cortex to
    stop sending to the endpoint altogether.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _key(secret: str) -> bytes:
    if not secret.startswith(_PREFIX):
        raise WebhookVerificationError("malformed_secret")
    try:
        return base64.b64decode(secret[len(_PREFIX) :], validate=True)
    except (binascii.Error, ValueError) as error:
        raise WebhookVerificationError("malformed_secret") from error


def verify(
    secret: str,
    headers: Mapping[str, str],
    body: bytes,
    *,
    tolerance: int = TOLERANCE_SECONDS,
    now: float | None = None,
) -> Event:
    """The delivery's event, if it is genuine and fresh; otherwise ``WebhookVerificationError``.

    ``headers`` may be any mapping -- a framework's request headers, a plain dict; names are
    matched case-insensitively. ``body`` is the raw request body.
    """
    lowered = {name.lower(): value for name, value in headers.items()}
    try:
        message_id = lowered["webhook-id"]
        timestamp = lowered["webhook-timestamp"]
        signatures = lowered["webhook-signature"]
    except KeyError as error:
        raise WebhookVerificationError("missing_header") from error

    if not timestamp.isdigit():
        raise WebhookVerificationError("malformed_timestamp")
    sent = int(timestamp)
    current = time.time() if now is None else now
    if sent < current - tolerance:
        raise WebhookVerificationError("timestamp_too_old")
    if sent > current + tolerance:
        raise WebhookVerificationError("timestamp_too_new")

    signed = f"{message_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(_key(secret), signed, hashlib.sha256).digest())
    matched = False
    for candidate in signatures.split(" "):
        version, _, value = candidate.partition(",")
        # Every candidate is compared, so the time taken does not say which one matched.
        if version == "v1" and hmac.compare_digest(value.encode(), expected):
            matched = True
    if not matched:
        raise WebhookVerificationError("no_matching_signature")

    try:
        event = json.loads(body)
    except ValueError as error:
        raise WebhookVerificationError("malformed_body") from error
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise WebhookVerificationError("malformed_body")
    return cast(Event, event)


__all__ = ["TOLERANCE_SECONDS", "WebhookVerificationError", "verify"]
