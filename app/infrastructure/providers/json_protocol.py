from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(value: str) -> dict[str, Any]:
    normalized = value.strip()
    fence_match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        normalized,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if fence_match:
        normalized = fence_match.group(1).strip()

    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "AI provider returned invalid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            "AI provider did not return a JSON object."
        )

    return parsed
