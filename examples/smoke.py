"""Run a receiver and send it what Cortex sends: a genuine delivery, a retry, and three forgeries.

    python examples/smoke.py python     # or: node, go

The deliveries are signed here, with this file's own implementation of the Standard Webhooks
scheme (`hmac` and `base64` from the standard library), using the secret and the body of the
first vector the platform signed. So a receiver that passes accepts what Cortex sends, handles
a retry once, and refuses a changed body, a stale timestamp and a missing signature -- through
HTTP, the way a real delivery reaches it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTOR = next(
    vector
    for vector in json.loads((ROOT / "sdk" / "vectors.json").read_text(encoding="utf-8"))["vectors"]
    if vector["expect"]["ok"] and vector["expect"]["type"] != "webhook.ping"
)
SECRET: str = VECTOR["secret"]
BODY: bytes = VECTOR["body"].encode("utf-8")
EVENT_TYPE: str = VECTOR["expect"]["type"]

RECEIVERS = {
    "python": ([sys.executable, "examples/python/receiver.py", "8081"], ROOT, 8081),
    "node": (["node", "examples/node/receiver.ts", "8082"], ROOT, 8082),
    "go": (["go", "run", ".", "8083"], ROOT / "examples" / "go", 8083),
}


def sign(message_id: str, timestamp: int, body: bytes) -> str:
    key = base64.b64decode(SECRET.removeprefix("whsec_"))
    signed = f"{message_id}.{timestamp}.".encode() + body
    return "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


def deliver(port: int, headers: dict[str, str], body: bytes) -> tuple[int, str]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as refused:
        return refused.code, refused.read().decode()


def wait_for(port: int, deadline: float) -> None:
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise SystemExit(f"nothing listening on {port}")


def main(language: str) -> int:
    command, cwd, port = RECEIVERS[language]
    receiver = subprocess.Popen(
        command,
        cwd=cwd,
        env={**os.environ, "CORTEX_WEBHOOK_SECRET": SECRET},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    failures: list[str] = []
    try:
        wait_for(port, time.monotonic() + 120)
        now = int(time.time())
        message_id = f"msg_smoke_{now}"

        def headers(timestamp: int, body: bytes = BODY, **extra: str) -> dict[str, str]:
            return {
                "content-type": "application/json",
                "webhook-id": message_id,
                "webhook-timestamp": str(timestamp),
                "webhook-signature": sign(message_id, timestamp, body),
                **extra,
            }

        cases = [
            ("a genuine delivery", headers(now), BODY, 204),
            ("the same delivery again", headers(now), BODY, 204),
            ("a changed body", headers(now), BODY.replace(b"1", b"2", 1), 400),
            ("a stale timestamp", headers(now - 3600), BODY, 400),
        ]
        missing = headers(now)
        del missing["webhook-signature"]
        cases.append(("no signature", missing, BODY, 400))

        for name, sent, body, expected in cases:
            status, reason = deliver(port, sent, body)
            verdict = "ok" if status == expected else "FAILED"
            print(f"{language}: {name}: {status} {reason!r} -- {verdict}")
            if status != expected:
                failures.append(name)
    finally:
        receiver.terminate()
        output, _ = receiver.communicate(timeout=30)

    lines = [line for line in output.splitlines() if line.strip()]
    if lines.count(f"received {EVENT_TYPE} {message_id}") != 1:
        failures.append("the genuine delivery was not handled exactly once")
    if f"duplicate {message_id}" not in lines:
        failures.append("the retry was not recognised as a duplicate")
    if failures:
        print(f"{language}: FAILED: {failures}\n{output}")
        return 1
    print(f"{language}: every delivery answered as Cortex expects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
