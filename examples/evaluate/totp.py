"""The six-digit code for a step-up, from a TOTP secret, with nothing but the standard library.

    python examples/evaluate/totp.py                  # the evaluator's published secret
    python examples/evaluate/totp.py <BASE32 SECRET>  # any other
    python examples/evaluate/totp.py --self-test      # RFC 6238's own test vectors

Cortex's authenticators are RFC 6238 as every authenticator app implements it: HMAC-SHA1,
six digits, a thirty-second step. A phone app works just as well; this exists so that an
evaluation needs nothing installed. When the screen asks for a code and this one has under
five seconds left, wait for the next: a code is accepted for its own step and the one either
side of it, but no further.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import sys
import time
from pathlib import Path

STEP = 30
DIGITS = 6


def code(secret: str, at: float | None = None, *, digits: int = DIGITS, digest: str = "sha1") -> str:
    """The code for ``secret`` at ``at`` (now, by default)."""
    key = base64.b32decode(secret.upper().replace(" ", "") + "=" * (-len(secret) % 8))
    counter = int((time.time() if at is None else at) // STEP)
    mac = hmac.new(key, struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def published_secret() -> str:
    """The evaluator's authenticator secret, as the repository's README publishes it."""
    from credentials import published  # noqa: PLC0415 -- beside this file

    return published()["evaluator"]["totp"]


def self_test() -> None:
    # RFC 6238, appendix B: the SHA-1 seed is the ASCII "12345678901234567890".
    seed = base64.b32encode(b"12345678901234567890").decode()
    for at, expected in ((59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924")):
        got = code(seed, at, digits=8)
        assert got == expected, f"at {at}: {got} != {expected}"
    print("RFC 6238 vectors: ok")


def main(argv: list[str]) -> int:
    if argv[1:] == ["--self-test"]:
        self_test()
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    secret = argv[1] if len(argv) > 1 else published_secret()
    remaining = STEP - int(time.time()) % STEP
    print(f"{code(secret)}   (valid for another {remaining} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
