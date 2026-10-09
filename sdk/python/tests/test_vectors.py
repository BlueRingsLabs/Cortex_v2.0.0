"""The Python verifier against the deliveries the platform signed (`../../vectors.json`).

The vectors are produced by Cortex's own signing code at release, so passing them means this
verifier accepts what Cortex actually sends and refuses what it must -- not merely that it
agrees with a description of the scheme. Standard library only, like the SDK.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from cortex_webhooks import EVENT_TYPES, WebhookVerificationError, verify

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "vectors.json").read_text(encoding="utf-8")
)


class TheVerifierAgreesWithThePlatform(unittest.TestCase):
    def test_every_vector(self) -> None:
        for vector in VECTORS["vectors"]:
            with self.subTest(vector["name"]):
                expect = vector["expect"]
                body = vector["body"].encode("utf-8")
                if expect["ok"]:
                    event = verify(vector["secret"], vector["headers"], body, now=vector["now"])
                    self.assertEqual(event["type"], expect["type"])
                else:
                    with self.assertRaises(WebhookVerificationError) as refused:
                        verify(vector["secret"], vector["headers"], body, now=vector["now"])
                    self.assertEqual(refused.exception.reason, expect["reason"])

    def test_it_knows_every_event_type_the_platform_publishes(self) -> None:
        self.assertEqual(sorted(EVENT_TYPES), sorted(VECTORS["event_types"]))


if __name__ == "__main__":
    unittest.main()
