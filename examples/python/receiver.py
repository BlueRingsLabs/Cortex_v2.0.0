"""A Cortex webhook receiver in Python, standard library only.

    CORTEX_WEBHOOK_SECRET=whsec_... python examples/python/receiver.py 8081

It does the four things every receiver must: verify the raw body before parsing it, answer
quickly, ignore a delivery it has already handled (delivery is at least once, and a retry or a
replay carries the same `webhook-id`), and refuse what does not verify with a 400.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python"))

from cortex_webhooks import WebhookVerificationError, verify  # noqa: E402

SECRET = os.environ["CORTEX_WEBHOOK_SECRET"]
MAX_BODY = 1 << 20

#: Message ids already handled. In production: a table with a unique constraint, written in the
#: same transaction as the work the event causes.
handled: set[str] = set()


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - the standard library's name
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            self._answer(413, "too large")
            return
        body = self.rfile.read(length)
        try:
            event = verify(SECRET, dict(self.headers.items()), body)
        except WebhookVerificationError as refused:
            self._answer(400, refused.reason)
            return
        message_id = self.headers["webhook-id"]
        if message_id in handled:
            print(f"duplicate {message_id}", flush=True)
            self._answer(204, "")
            return
        handled.add(message_id)
        # Queue the work and answer: Cortex waits fifteen seconds for a 2xx, and retries after.
        print(f"received {event['type']} {message_id}", flush=True)
        self._answer(204, "")

    def _answer(self, status: int, reason: str) -> None:
        payload = reason.encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: object) -> None:  # quiet: the prints above say what matters
        return


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    ThreadingHTTPServer(("127.0.0.1", port), Receiver).serve_forever()
