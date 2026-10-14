"""The demonstration's published sign-ins, read from the repository's README -- one source.

The README is where they are published, and where a rotation is published again; reading them
from there means a script can never hold a password the README no longer shows. Environment
variables override them, for an installation of your own:

    CORTEX_EVALUATOR_PASSWORD, CORTEX_EVALUATOR_TOTP, CORTEX_AGENT_PASSWORD
"""

from __future__ import annotations

import os
import re
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"
_ROW = re.compile(r"^\| [^|]+ \| `(?P<user>evaluator|agent)` \| `(?P<password>[^`]+)` \| (?:`(?P<totp>[A-Z2-7]+)`|—) \|$", re.M)


def published() -> dict[str, dict[str, str]]:
    found = {
        match["user"]: {"password": match["password"], "totp": match["totp"] or ""}
        for match in _ROW.finditer(README.read_text(encoding="utf-8"))
    }
    if os.environ.get("CORTEX_EVALUATOR_PASSWORD"):
        found.setdefault("evaluator", {})["password"] = os.environ["CORTEX_EVALUATOR_PASSWORD"]
    if os.environ.get("CORTEX_EVALUATOR_TOTP"):
        found.setdefault("evaluator", {})["totp"] = os.environ["CORTEX_EVALUATOR_TOTP"]
    if os.environ.get("CORTEX_AGENT_PASSWORD"):
        found.setdefault("agent", {})["password"] = os.environ["CORTEX_AGENT_PASSWORD"]
    missing = {"evaluator", "agent"} - set(found)
    if missing:
        raise SystemExit(f"no published sign-in for {', '.join(sorted(missing))} in {README}")
    return found
