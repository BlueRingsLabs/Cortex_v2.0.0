"""Every journey of the evaluation runbook, run against the live demonstration, claim by claim.

    python examples/evaluate/journey.py                      # cortex.gonzaloromeroai.com
    python examples/evaluate/journey.py --base-url https://your.installation
    python examples/evaluate/journey.py --self-test          # the signing, offline

The runbook (docs/evaluation-runbook.md) says what each screen shows. This says it again over
the API the screens use, and checks it: a sign-in bound to a key, a step-up, the subjects, the
customer overview, the knowledge corpus, the assistant's grounding, the ACL watched from the
care agent's side -- granted and revoked -- the key generations, the audit trail and the webhook
catalogue. Every line is PASS or FAIL, and the exit status is the number of failures.

Nothing to install. Sessions are bound to a key with DPoP (RFC 9449), which needs an ES256
signature; it is done here in pure Python (P-256 from SEC 2, deterministic only in that it is
correct -- the nonce is random, as ECDSA requires), because an evaluation that starts with
"first install a cryptography library" has already lost a reader. Do not reuse it for anything
that matters: it is written to be read, not to resist timing analysis.

It changes one thing, and puts it back: it grants the care agent one collection, watches the
agent's answers change, and revokes the grant. The demonstration is restored every night anyway.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from credentials import published  # noqa: E402
from totp import STEP, code  # noqa: E402

DEFAULT_BASE = "https://cortex.gonzaloromeroai.com"
TENANT = "carrier-large"

# ------------------------------------------------------------------ P-256, by the book --

_P = 2**256 - 2**224 + 2**192 + 2**96 - 1
_A = _P - 3
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
)
Point = tuple[int, int] | None


def _add(p: Point, q: Point) -> Point:
    if p is None:
        return q
    if q is None:
        return p
    if p[0] == q[0] and (p[1] + q[1]) % _P == 0:
        return None
    if p == q:
        slope = (3 * p[0] * p[0] + _A) * pow(2 * p[1], -1, _P) % _P
    else:
        slope = (q[1] - p[1]) * pow(q[0] - p[0], -1, _P) % _P
    x = (slope * slope - p[0] - q[0]) % _P
    return x, (slope * (p[0] - x) - p[1]) % _P


def _multiply(k: int, point: Point) -> Point:
    result: Point = None
    while k:
        if k & 1:
            result = _add(result, point)
        point = _add(point, point)
        k >>= 1
    return result


class SigningKey:
    """An ephemeral ES256 key: the one a session is bound to, and gone when this exits."""

    def __init__(self) -> None:
        self._d = secrets.randbelow(_N - 1) + 1
        public = _multiply(self._d, _G)
        assert public is not None
        self.public = public

    def jwk(self) -> dict[str, str]:
        x, y = self.public
        return {"kty": "EC", "crv": "P-256", "x": _b64(x.to_bytes(32, "big")), "y": _b64(y.to_bytes(32, "big"))}

    def sign(self, message: bytes) -> bytes:
        z = int.from_bytes(hashlib.sha256(message).digest(), "big")
        while True:
            k = secrets.randbelow(_N - 1) + 1
            point = _multiply(k, _G)
            assert point is not None
            r = point[0] % _N
            s = pow(k, -1, _N) * (z + r * self._d) % _N
            if r and s:
                return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify(public: tuple[int, int], message: bytes, signature: bytes) -> bool:
    r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    if not (0 < r < _N and 0 < s < _N):
        return False
    z = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, _N)
    point = _add(_multiply(z * w % _N, _G), _multiply(r * w % _N, public))
    return point is not None and point[0] % _N == r


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ------------------------------------------------------------- a session, bound to a key --


class Session:
    def __init__(self, base: str, tenant: str) -> None:
        self.base, self.tenant = base.rstrip("/"), tenant
        self.key = SigningKey()
        self.token: str | None = None

    def _proof(self, method: str, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        claims: dict[str, Any] = {
            "htm": method,
            "htu": f"{parts.scheme}://{parts.netloc}{parts.path}",
            "iat": int(time.time()),
            "jti": secrets.token_urlsafe(16),
        }
        if self.token is not None:
            claims["ath"] = _b64(hashlib.sha256(self.token.encode()).digest())
        header = {"typ": "dpop+jwt", "alg": "ES256", "jwk": self.key.jwk()}
        signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
        return f"{signing_input}.{_b64(self.key.sign(signing_input.encode()))}"

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        url = f"{self.base}/api/v1{path}"
        headers = {"X-Cortex-Tenant": self.tenant, "DPoP": self._proof(method, url)}
        if self.token is not None:
            headers["Authorization"] = f"DPoP {self.token}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as refused:
            raw = refused.read()
            try:
                return refused.code, json.loads(raw)
            except ValueError:
                return refused.code, raw.decode(errors="replace")

    def sign_in(self, username: str, password: str) -> dict[str, Any]:
        status, body = self.call("POST", "/auth/login", {"username": username, "password": password})
        if status != 200:
            raise SystemExit(f"sign-in as {username} refused: {status} {body}")
        self.token = body["tokens"]["access_token"]
        return body

    def step_up(self, secret: str) -> None:
        """Raise this session to assurance 2. The answer is a fresh token pair for it."""
        if STEP - int(time.time()) % STEP < 3:
            time.sleep(4)  # never spend a code in its last second
        status, body = self.call("POST", "/auth/step-up", {"factor": "totp", "code": code(secret)})
        if status != 200:
            raise SystemExit(f"step-up refused: {status} {body}")
        self.token = body["access_token"]


# ----------------------------------------------------------------------- the journeys --

failures = 0


def check(claim: str, held: bool, detail: str = "") -> None:
    global failures
    failures += 0 if held else 1
    print(f"  {'PASS' if held else 'FAIL'}  {claim}{f'  ({detail})' if detail else ''}")


def ask(session: Session, question: str) -> list[dict[str, Any]]:
    status, body = session.call(
        "POST", "/assistant", {"reference": f"Q-{secrets.token_hex(6)}", "question": question}
    )
    return list(body.get("grounding", [])) if status in (200, 201) else []


def journeys(base: str) -> int:
    sign_ins = published()
    evaluator = Session(base, TENANT)

    print("\n1. Sign-in and session elevation")
    signed = evaluator.sign_in("evaluator", sign_ins["evaluator"]["password"])
    check("the evaluator signs in, bound to this script's key", signed["assurance_level"] == 1)
    check("no password change is demanded of a published account", signed["must_change_credentials"] is False)
    before, _ = evaluator.call("GET", "/audit?limit=1")
    evaluator.step_up(sign_ins["evaluator"]["totp"])
    after, _ = evaluator.call("GET", "/audit?limit=1")
    check(
        "the audit trail asks for a second factor, and a TOTP step-up provides it",
        before == 401 and after == 200,
        f"{before} before, {after} after",
    )

    print("\n2. Subjects and the customer overview")
    status, subjects = evaluator.call("GET", "/subjects?limit=5")
    check("the subjects screen's rows are readable", status == 200 and len(subjects) == 5, f"{status}")
    if status == 200 and subjects:
        first = subjects[0]
        print(f"        e.g. {first['display_name']} · {first['reference']} · {first['org_unit_path']} · {first['classification']}")
    status, customers = evaluator.call("GET", "/crm/customers?term=Subject%20000")
    rows = customers.get("customers", []) if status == 200 else []
    check("a name prefix finds customers in the overview", len(rows) > 0, f"{len(rows)} rows for 'Subject 000'")

    print("\n3. Knowledge and the grounded assistant")
    status, listing = evaluator.call("GET", "/collections")
    found = {c["reference"]: c["classification"] for c in listing.get("collections", [])} if status == 200 else {}
    check(
        "four collections at four sensitivities",
        {"care-handbook", "network-operations", "regulatory", "security"} <= set(found),
        ", ".join(f"{k}={v}" for k, v in sorted(found.items())),
    )
    for question, expected in (
        ("How do I port a number to another carrier?", "CARE-PORTABILITY"),
        ("¿Cuánto tarda la portabilidad numérica?", "CARE-PORTABILIDAD-ES"),
        ("Qual é o prazo da portabilidade numérica?", "CARE-PORTABILIDADE-PT"),
        ("Who declares a P1 major incident?", "NOC-MAJOR-INCIDENT"),
        ("How often is the key-encryption key rotated?", "SEC-KEY-MANAGEMENT"),
    ):
        passages = ask(evaluator, question)
        top = passages[0]["document_reference"] if passages else "nothing"
        check(f"“{question}” grounds on {expected} first", top == expected, top)

    print("\n4. The ACL, from the side it protects")
    agent = Session(base, TENANT)
    agent.sign_in("agent", sign_ins["agent"]["password"])
    noc = "Who declares a P1 major incident?"
    before = {p["collection_reference"] for p in ask(agent, noc)}
    check("the care agent reads the handbook and nothing else", before <= {"care-handbook"}, ", ".join(sorted(before)) or "nothing")
    status, people = evaluator.call("GET", "/iam/principals?limit=200")
    agent_id = next((p["id"] for p in people if p["username"] == "agent"), None) if status == 200 else None
    reference = f"G-JOURNEY-{secrets.token_hex(3).upper()}"
    status, _ = evaluator.call(
        "POST",
        "/collections/grants",
        {
            "reference": reference,
            "collection_reference": "network-operations",
            "principal_id": agent_id,
            "capability_id": "collection:read",
            "reason": "The evaluation journey: covering the outage desk",
        },
    )
    check("the evaluator grants the agent the network runbooks", status == 201, str(status))
    during = ask(agent, noc)
    top = during[0]["document_reference"] if during else "nothing"
    check("the agent's next question grounds on them", top == "NOC-MAJOR-INCIDENT", top)
    status, _ = evaluator.call("POST", "/collections/grants/revocations", {"reference": reference, "reason": "The journey is over"})
    after = {p["collection_reference"] for p in ask(agent, noc)}
    check("revoked, and the agent reads the handbook alone again", status in (200, 201) and after <= {"care-handbook"}, ", ".join(sorted(after)) or "nothing")

    print("\n5. Encryption keys and the audit trail")
    status, keys = evaluator.call("GET", "/platform/keys")
    if status == 200:
        check(
            "values are sealed under the newest generation, none under an older one",
            keys["superseded"] == 0,
            f"generation {keys['current_generation']} of {keys['generations']}",
        )
    else:
        check("the key status is readable", False, str(status))
    status, trail = evaluator.call("GET", "/audit?event_type=knowledge.collection_access_changed&limit=5")
    targets = [r.get("target_id") for r in trail.get("records", [])] if status == 200 else []
    check("the grant and its revocation are on the audit trail", "network-operations" in targets, f"{len(targets)} records")
    status, rotated = evaluator.call("GET", "/audit?event_type=platform.keys_resealed&limit=5")
    check("the last re-seal is on the audit trail", status == 200 and len(rotated.get("records", [])) > 0, str(status))

    print("\n6. Integrations")
    status, catalogue = evaluator.call("GET", "/integrations/webhooks/catalogue")
    facts = {f.get("name") for f in catalogue.get("facts", [])} if status == 200 else set()
    check(
        "the webhook catalogue offers the key re-seal among its facts",
        {"tenancy.reseal_requested", "tenancy.keys_resealed"} <= facts,
        f"{len(facts)} facts",
    )

    print(f"\n{'all claims held' if failures == 0 else f'{failures} claim(s) did not hold'}")
    return failures


def self_test() -> int:
    key = SigningKey()
    signature = key.sign(b"cortex")
    assert verify(key.public, b"cortex", signature)
    assert not verify(key.public, b"cortez", signature)
    print("ES256 sign and verify: ok")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(self_test() if arguments.self_test else journeys(arguments.base_url))
