from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class QualityLimits:
    min_characters: int
    min_words: int
    min_alphanumeric_characters: int
    max_noise_ratio: float

    long_token_characters: int
    long_token_ratio: float

    repeated_boilerplate_min_pages: int
    repeated_boilerplate_min_line_characters: int

    max_ocr_characters: int


@dataclass(frozen=True)
class PageQualityResult:
    page_id: UUID
    score: float
    metrics: dict[str, Any]
    requires_ocr: bool
    warning: str | None


class QualityService:
    def __init__(self, limits: QualityLimits) -> None:
        self.limits = limits

    def assess_pages(
        self,
        pages: list[tuple[UUID, int, str]],
    ) -> list[PageQualityResult]:
        results: dict[UUID, PageQualityResult] = {}

        for page_id, _page_number, text in pages:
            metrics = self.page_text_quality(text)
            integrity = self.native_text_integrity_metrics(text)

            metrics.update(integrity)

            requires_ocr = bool(
                metrics["characters"]
                < self.limits.min_characters
                or metrics["words"] < self.limits.min_words
                or metrics["alphanumeric_characters"]
                < self.limits.min_alphanumeric_characters
                or metrics["noise_ratio"]
                > self.limits.max_noise_ratio
                or integrity["native_text_integrity_gate"]
            )

            warning = (
                "Native page text is weak or corrupted; OCR required."
                if requires_ocr
                else None
            )

            results[page_id] = PageQualityResult(
                page_id=page_id,
                score=float(metrics["score"]),
                metrics=metrics,
                requires_ocr=requires_ocr,
                warning=warning,
            )

        self._apply_repeated_boilerplate_rule(
            pages=pages,
            results=results,
        )

        return list(results.values())

    def page_text_quality(
        self,
        text: str,
    ) -> dict[str, Any]:
        characters = len(text)
        words = re.findall(r"\w+", text, flags=re.UNICODE)

        alphanumeric = sum(
            character.isalnum()
            for character in text
        )

        controls = sum(
            not (
                character.isprintable()
                or character in "\n\r\t"
            )
            for character in text
        )

        replacement_characters = text.count("\ufffd")
        alphanumeric_ratio = alphanumeric / max(1, characters)

        noise_ratio = (
            controls + replacement_characters
        ) / max(1, characters)

        score = min(
            1.0,
            0.35 * min(1.0, characters / 200)
            + 0.30 * min(1.0, len(words) / 30)
            + 0.25 * min(
                1.0,
                alphanumeric_ratio / 0.55,
            )
            + 0.10 * (
                1.0 - min(1.0, noise_ratio * 10)
            ),
        )

        return {
            "score": round(max(0.0, score), 4),
            "characters": characters,
            "words": len(words),
            "alphanumeric_characters": alphanumeric,
            "alphanumeric_ratio": round(
                alphanumeric_ratio,
                4,
            ),
            "noise_ratio": round(noise_ratio, 4),
        }

    def native_text_integrity_metrics(
        self,
        text: str,
    ) -> dict[str, Any]:
        tokens = re.findall(r"\S+", text)

        long_token_characters = sum(
            len(token)
            for token in tokens
            if len(token)
            >= self.limits.long_token_characters
        )

        long_token_ratio = (
            long_token_characters / max(1, len(text))
        )

        artifacts = (
            text.count("\ufffd")
            + len(
                re.findall(
                    r"\(cid[:;]?\d*\)",
                    text,
                    flags=re.IGNORECASE,
                )
            )
        )

        artifact_ratio = artifacts / max(1, len(text))

        integrity_gate = bool(
            artifacts > 0
            or long_token_ratio
            >= self.limits.long_token_ratio
        )

        return {
            "artifact_characters": artifacts,
            "artifact_ratio": round(artifact_ratio, 4),
            "long_unbroken_token_ratio": round(
                long_token_ratio,
                4,
            ),
            "native_text_integrity_gate": integrity_gate,
        }

    def validate_ocr_text(
        self,
        value: Any,
    ) -> tuple[str, dict[str, Any]]:
        if not isinstance(value, str):
            raise ValueError(
                "OCR returned non-text page content."
            )

        text = self._clean_text(value)

        if "\ufffd" in text:
            raise ValueError(
                "OCR returned undecodable characters."
            )

        if len(text) > self.limits.max_ocr_characters:
            raise ValueError(
                "OCR page text exceeded its maximum size."
            )

        if text.lower() in {
            "null",
            "none",
            "undefined",
            "n/a",
        }:
            raise ValueError(
                "OCR returned placeholder content."
            )

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        if len(lines) >= 8:
            repeated_count = max(
                Counter(lines).values()
            )

            if (
                repeated_count / len(lines) >= 0.60
                and len(max(lines, key=len)) >= 20
            ):
                raise ValueError(
                    "OCR returned suspiciously repeated content."
                )

        metrics = self.page_text_quality(text)
        integrity = self.native_text_integrity_metrics(text)
        metrics.update(integrity)

        if integrity["native_text_integrity_gate"]:
            raise ValueError(
                "OCR returned corrupted text."
            )

        if text and (
            metrics["alphanumeric_characters"] == 0
            or metrics["noise_ratio"] > 0.20
        ):
            raise ValueError(
                "OCR returned malformed text."
            )

        return text, metrics

    def _apply_repeated_boilerplate_rule(
        self,
        *,
        pages: list[tuple[UUID, int, str]],
        results: dict[UUID, PageQualityResult],
    ) -> None:
        if (
            len(pages)
            < self.limits.repeated_boilerplate_min_pages
        ):
            return

        lines_by_page: dict[UUID, list[str]] = {}
        occurrences: Counter[str] = Counter()

        for page_id, _page_number, text in pages:
            normalized_lines = {
                line.strip().casefold()
                for line in text.splitlines()
                if len(line.strip())
                >= (
                    self.limits
                    .repeated_boilerplate_min_line_characters
                )
            }

            lines_by_page[page_id] = list(normalized_lines)
            occurrences.update(normalized_lines)

        repeated_lines = {
            line
            for line, count in occurrences.items()
            if count
            >= self.limits.repeated_boilerplate_min_pages
        }

        if not repeated_lines:
            return

        for page_id, _page_number, text in pages:
            substantive_lines = [
                line
                for line in text.splitlines()
                if line.strip().casefold()
                not in repeated_lines
            ]

            substantive_text = self._clean_text(
                "\n".join(substantive_lines)
            )

            substantive_metrics = self.page_text_quality(
                substantive_text
            )

            weak_substantive_text = bool(
                substantive_metrics["characters"]
                < self.limits.min_characters
                or substantive_metrics["words"]
                < self.limits.min_words
                or substantive_metrics[
                    "alphanumeric_characters"
                ]
                < self.limits.min_alphanumeric_characters
            )

            if not weak_substantive_text:
                continue

            previous = results[page_id]
            metrics = dict(previous.metrics)
            metrics["repeated_boilerplate_only"] = True
            metrics[
                "substantive_characters_after_boilerplate"
            ] = len(substantive_text)

            results[page_id] = PageQualityResult(
                page_id=page_id,
                score=min(
                    previous.score,
                    float(substantive_metrics["score"]),
                ),
                metrics=metrics,
                requires_ocr=True,
                warning=(
                    "Repeated boilerplate obscures page content; "
                    "OCR required."
                ),
            )

    @staticmethod
    def _clean_text(value: str) -> str:
        value = value.replace("\x00", "")
        value = value.replace("\r\n", "\n")
        value = value.replace("\r", "\n")

        return "\n".join(
            line.strip()
            for line in value.splitlines()
        ).strip()