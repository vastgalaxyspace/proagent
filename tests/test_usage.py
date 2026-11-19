from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.infrastructure.providers.usage import (
    UsagePricing,
    collect_ai_usage,
    current_ai_usage,
    record_ai_usage,
)


class AIUsageTests(unittest.TestCase):
    def test_collects_tokens_and_estimates_cost(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=1_000,
                completion_tokens=500,
                total_tokens=1_500,
            )
        )
        with collect_ai_usage(
            pricing=UsagePricing(
                input_per_million=1.0,
                output_per_million=2.0,
            )
        ) as collector:
            record_ai_usage(
                response=response,
                provider="test-provider",
                model="test-model",
                capability="primary",
            )
            snapshot = current_ai_usage()

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["input_tokens"], 1_000)
        self.assertEqual(snapshot["output_tokens"], 500)
        self.assertEqual(snapshot["total_tokens"], 1_500)
        self.assertEqual(snapshot["request_count"], 1)
        self.assertEqual(collector.snapshot()["estimated_cost_usd"], 0.002)

    def test_inherits_usage_when_replaying_from_checkpoint(self) -> None:
        initial = {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "request_count": 1,
            "by_capability": {},
        }
        response = {
            "usage": {
                "prompt_tokens": 30,
                "completion_tokens": 10,
                "total_tokens": 40,
            }
        }
        with collect_ai_usage(
            pricing=UsagePricing(),
            initial=initial,
        ) as collector:
            record_ai_usage(
                response=response,
                provider="test-provider",
                model="test-model",
                capability="primary",
            )

        snapshot = collector.snapshot()
        self.assertEqual(snapshot["total_tokens"], 160)
        self.assertEqual(snapshot["request_count"], 2)
        self.assertIsNone(snapshot["estimated_cost_usd"])

    def test_usage_context_is_cleared_after_run(self) -> None:
        with collect_ai_usage(pricing=UsagePricing()):
            self.assertIsNotNone(current_ai_usage())
        self.assertIsNone(current_ai_usage())


if __name__ == "__main__":
    unittest.main()
