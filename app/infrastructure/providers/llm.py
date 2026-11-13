from __future__ import annotations

from typing import Any, Literal, Protocol

from app.infrastructure.providers.client import build_ai_client
from app.infrastructure.providers.json_protocol import (
    parse_json_object,
)
from app.infrastructure.providers.settings import AIProviderSettings


LLMCapability = Literal["primary", "verifier"]


class LLMProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        deep: bool = False,
    ) -> str:
        ...

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        deep: bool = False,
    ) -> dict[str, Any]:
        ...


class APILLMProvider:
    def __init__(
        self,
        *,
        settings: AIProviderSettings,
        capability: LLMCapability,
    ) -> None:
        self.settings = settings
        self.capability = capability
        self.client = build_ai_client(
            settings=settings,
            capability=capability,
        )

    @property
    def name(self) -> str:
        return self.settings.provider

    @property
    def model(self) -> str:
        return self.settings.model_for(self.capability)

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        deep: bool = False,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.model_for(
                self.capability,
                deep=deep,
            ),
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "LLM provider returned empty content."
            )

        return content.strip()

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        deep: bool = False,
    ) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.settings.model_for(
                self.capability,
                deep=deep,
            ),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\nReturn valid JSON only."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "LLM provider returned empty content."
            )

        return parse_json_object(content)
