from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


Capability = Literal[
    "primary",
    "embedding",
    "reranker",
    "verifier",
]


class AIProviderSettings(BaseSettings):
    provider: Literal[
        "gemini",
        "openai_compatible",
    ] = "gemini"

    api_key: SecretStr | None = None
    api_key_file: Path | None = None

    primary_api_key: SecretStr | None = None
    primary_api_key_file: Path | None = None
    embedding_api_key: SecretStr | None = None
    embedding_api_key_file: Path | None = None
    reranker_api_key: SecretStr | None = None
    reranker_api_key_file: Path | None = None
    verifier_api_key: SecretStr | None = None
    verifier_api_key_file: Path | None = None

    base_url: str = ""
    primary_base_url: str = ""
    embedding_base_url: str = ""
    reranker_base_url: str = ""
    verifier_base_url: str = ""

    model_fast: str = "gemini-3.8-flash"
    model_deep: str = "gemini-3.8-flash"
    model_embedding: str = "gemini-embedding-001"
    model_reranker: str = "gemini-3.8-flash"
    model_verifier: str = "gemini-3.8-flash"

    embedding_dimensions: int = 3072
    embedding_batch_size: int = 64
    reranker_api_style: Literal["chat", "rerank"] = "chat"
    reranker_candidate_characters: int = 1800

    primary_request_timeout_seconds: int = 240
    embedding_request_timeout_seconds: int = 120
    reranker_request_timeout_seconds: int = 240
    verifier_request_timeout_seconds: int = 240
    max_retries: int = 2
    input_cost_per_million_tokens: float = 0.0
    output_cost_per_million_tokens: float = 0.0
    embedding_cost_per_million_tokens: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> object:
        normalized = str(value).strip().lower()

        if normalized in {
            "openai",
            "openai-compatible",
            "openai_compatible",
            "yotta",
            "yota",
        }:
            return "openai_compatible"

        return normalized

    def api_key_for(self, capability: Capability) -> str:
        direct_keys = {
            "primary": self.primary_api_key,
            "embedding": self.embedding_api_key,
            "reranker": self.reranker_api_key,
            "verifier": self.verifier_api_key,
        }
        key_files = {
            "primary": self.primary_api_key_file,
            "embedding": self.embedding_api_key_file,
            "reranker": self.reranker_api_key_file,
            "verifier": self.verifier_api_key_file,
        }

        direct_key = direct_keys[capability]
        if direct_key is not None:
            return direct_key.get_secret_value()

        key_file = key_files[capability]
        if key_file is not None:
            return self._read_key_file(key_file)

        if self.api_key is not None:
            return self.api_key.get_secret_value()

        if self.api_key_file is not None:
            return self._read_key_file(self.api_key_file)

        raise ValueError(
            f"API key is not configured for {capability}."
        )

    def base_url_for(self, capability: Capability) -> str:
        capability_urls = {
            "primary": self.primary_base_url,
            "embedding": self.embedding_base_url,
            "reranker": self.reranker_base_url,
            "verifier": self.verifier_base_url,
        }
        selected = capability_urls[capability].strip()

        if not selected:
            selected = self.base_url.strip()

        if not selected and self.provider == "gemini":
            selected = (
                "https://generativelanguage.googleapis.com/"
                "v1beta/openai/"
            )

        if not selected:
            raise ValueError(
                f"Base URL is not configured for {capability}."
            )

        return selected.rstrip("/") + "/"

    def model_for(
        self,
        capability: Capability,
        *,
        deep: bool = False,
    ) -> str:
        models = {
            "primary": self.model_deep if deep else self.model_fast,
            "embedding": self.model_embedding,
            "reranker": self.model_reranker,
            "verifier": self.model_verifier,
        }
        model = models[capability].strip()

        if not model:
            raise ValueError(
                f"Model is not configured for {capability}."
            )

        return model

    def timeout_for(self, capability: Capability) -> int:
        timeouts = {
            "primary": self.primary_request_timeout_seconds,
            "embedding": self.embedding_request_timeout_seconds,
            "reranker": self.reranker_request_timeout_seconds,
            "verifier": self.verifier_request_timeout_seconds,
        }
        return max(1, timeouts[capability])

    def validate_capability(self, capability: Capability) -> None:
        self.api_key_for(capability)
        self.base_url_for(capability)
        self.model_for(capability)

        if capability == "embedding":
            if self.embedding_dimensions <= 0:
                raise ValueError(
                    "AI_EMBEDDING_DIMENSIONS must be positive."
                )
            if self.embedding_batch_size <= 0:
                raise ValueError(
                    "AI_EMBEDDING_BATCH_SIZE must be positive."
                )

    @staticmethod
    def _read_key_file(path: Path) -> str:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(
                f"Unable to read API key file: {path}"
            ) from exc

        if not value:
            raise ValueError(f"API key file is empty: {path}")

        return value


class OpenParserSettings(BaseSettings):
    api_key: SecretStr | None = None
    api_key_file: Path | None = None
    base_url: str = "https://api.openparser.dev"
    ocr_model: str = "paddleocr-vl-1.6"
    request_timeout_seconds: int = 240
    max_response_mb: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPENPARSER_",
        case_sensitive=False,
        extra="ignore",
    )

    def resolved_api_key(self) -> str:
        if self.api_key is not None:
            return self.api_key.get_secret_value()

        if self.api_key_file is not None:
            return AIProviderSettings._read_key_file(
                self.api_key_file
            )

        raise ValueError("OPENPARSER_API_KEY is required.")

    def validate_configuration(self) -> None:
        self.resolved_api_key()

        normalized_url = self.base_url.strip().rstrip("/")
        if not normalized_url:
            raise ValueError("OPENPARSER_BASE_URL is required.")
        if not normalized_url.startswith("https://") and not (
            normalized_url.startswith("http://localhost")
            or normalized_url.startswith("http://127.0.0.1")
        ):
            raise ValueError(
                "OPENPARSER_BASE_URL must use HTTPS."
            )
        if not self.ocr_model.strip():
            raise ValueError("OPENPARSER_OCR_MODEL is required.")
        if self.request_timeout_seconds <= 0:
            raise ValueError(
                "OPENPARSER_REQUEST_TIMEOUT_SECONDS must be positive."
            )
        if self.max_response_mb <= 0:
            raise ValueError(
                "OPENPARSER_MAX_RESPONSE_MB must be positive."
            )


@lru_cache
def get_ai_provider_settings() -> AIProviderSettings:
    return AIProviderSettings()


@lru_cache
def get_openparser_settings() -> OpenParserSettings:
    return OpenParserSettings()
