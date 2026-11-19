from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterator


def _value(source: Any, *names: str) -> Any:
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        value = getattr(source, name, None)
        if value is not None:
            return value
    return None


@dataclass(frozen=True)
class UsagePricing:
    input_per_million: float = 0.0
    output_per_million: float = 0.0
    embedding_per_million: float = 0.0


class AIUsageCollector:
    def __init__(
        self,
        *,
        pricing: UsagePricing,
        initial: dict[str, Any] | None = None,
    ) -> None:
        self.pricing = pricing
        self.input_tokens = int((initial or {}).get("input_tokens", 0))
        self.output_tokens = int((initial or {}).get("output_tokens", 0))
        self.total_tokens = int((initial or {}).get("total_tokens", 0))
        self.request_count = int((initial or {}).get("request_count", 0))
        self.by_capability: dict[str, dict[str, Any]] = deepcopy(
            (initial or {}).get("by_capability", {})
        )

    def record(
        self,
        *,
        response: Any,
        provider: str,
        model: str,
        capability: str,
    ) -> None:
        usage = _value(response, "usage", "usage_metadata")
        if usage is None:
            return

        input_tokens = int(
            _value(usage, "prompt_tokens", "input_tokens") or 0
        )
        output_tokens = int(
            _value(usage, "completion_tokens", "output_tokens") or 0
        )
        total_tokens = int(
            _value(usage, "total_tokens")
            or input_tokens + output_tokens
        )

        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens
        self.request_count += 1

        capability_usage = self.by_capability.setdefault(
            capability,
            {
                "provider": provider,
                "model": model,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "request_count": 0,
            },
        )
        capability_usage["input_tokens"] += input_tokens
        capability_usage["output_tokens"] += output_tokens
        capability_usage["total_tokens"] += total_tokens
        capability_usage["request_count"] += 1

    def snapshot(self) -> dict[str, Any]:
        embedding_tokens = int(
            self.by_capability.get("embedding", {}).get(
                "input_tokens",
                0,
            )
        )
        chat_input_tokens = self.input_tokens - embedding_tokens
        pricing_configured = any(
            rate > 0
            for rate in (
                self.pricing.input_per_million,
                self.pricing.output_per_million,
                self.pricing.embedding_per_million,
            )
        )
        estimated_cost = (
            (
                chat_input_tokens * self.pricing.input_per_million
                + self.output_tokens * self.pricing.output_per_million
                + embedding_tokens * self.pricing.embedding_per_million
            )
            / 1_000_000
            if pricing_configured
            else None
        )
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "request_count": self.request_count,
            "estimated_cost_usd": (
                round(estimated_cost, 8)
                if estimated_cost is not None
                else None
            ),
            "pricing_configured": pricing_configured,
            "by_capability": deepcopy(self.by_capability),
        }


_current_collector: ContextVar[AIUsageCollector | None] = ContextVar(
    "ai_usage_collector",
    default=None,
)


@contextmanager
def collect_ai_usage(
    *,
    pricing: UsagePricing,
    initial: dict[str, Any] | None = None,
) -> Iterator[AIUsageCollector]:
    collector = AIUsageCollector(pricing=pricing, initial=initial)
    token = _current_collector.set(collector)
    try:
        yield collector
    finally:
        _current_collector.reset(token)


def record_ai_usage(
    *,
    response: Any,
    provider: str,
    model: str,
    capability: str,
) -> None:
    collector = _current_collector.get()
    if collector is not None:
        collector.record(
            response=response,
            provider=provider,
            model=model,
            capability=capability,
        )


def current_ai_usage() -> dict[str, Any] | None:
    collector = _current_collector.get()
    return collector.snapshot() if collector is not None else None
