from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Procurement Tender Agent"
    app_environment: Literal[
        "development",
        "test",
        "production",
    ] = "development"
    debug: bool = False
    api_prefix: str = "/v1"
    api_host: str = "127.0.0.1"
    api_port: int = 8001
    api_reload: bool = False

    database_url: str = (
        "postgresql+psycopg://"
        "proagent:proagent@localhost:5432/proagent"
    )

    checkpoint_pool_min_size: int = 1
    checkpoint_pool_max_size: int = 10
    coverage_policy_path: Path = Path(
        "app/tender_agent/prompts/"
        "coverage_audit.yaml"
    )

    ai_enabled: bool = False
    tender_fields_config_path: Path = Path(
    "config/tender_fields.yaml"
)

    field_understanding_prompt_path: Path = Path(
    "app/tender_agent/prompts/"
    "field_understanding.yaml"
)

    field_retrieval_limit: int = 8
    field_minimum_confidence: float = 0.65
    field_max_chunk_characters: int = 3500

    storage_root: Path = Path("runtime/storage")
    normalization_default_currency: str = "INR"

    normalization_default_timezone: str = (
        "Asia/Kolkata"
    )

    reconciliation_minimum_confidence: float = 0.65

    max_upload_files: int = 100
    max_upload_file_bytes: int = 50 * 1024 * 1024
    max_upload_total_bytes: int = 500 * 1024 * 1024
    upload_chunk_bytes: int = 1024 * 1024
    classification_probe_characters: int = 4000
    classification_minimum_confidence: float = 0.60

    max_pdf_pages: int = 500
    max_document_characters: int = 50_000
    min_native_page_characters: int = 40

    max_archive_files: int = 80
    max_archive_total_bytes: int = 250 * 1024 * 1024
    max_archive_entry_bytes: int = 80 * 1024 * 1024
    max_archive_compression_ratio: int = 200

    max_spreadsheet_cells: int = 500_000

    office_converter_bin: str = "libreoffice"
    office_converter_timeout_seconds: int = 120
    retrieval_chunk_characters: int = 1200
    retrieval_chunk_overlap_characters: int = 200
    retrieval_search_candidate_pool: int = 24

    ocr_enabled: bool = False
    ocr_provider: Literal[
        "disabled",
        "tesseract",
        "openparser",
    ] = "disabled"
    tesseract_command: str | None = None
    ocr_language: str = "eng"
    ocr_render_scale: float = 2.0
    ocr_timeout_seconds: int = 120

    ocr_min_page_characters: int = 40
    ocr_min_words: int = 8
    ocr_min_alphanumeric_characters: int = 25
    ocr_max_noise_ratio: float = 0.15
    ocr_min_accepted_score: float = 0.40
    ocr_max_attempts: int = 2

    requirement_dictionary_path: Path = Path(
        "config/requirement_dictionary.yaml"
    )
    requirement_prompt_path: Path = Path(
        "app/tender_agent/prompts/"
        "requirement_extraction.yaml"
    )
    requirement_retrieval_limit: int = 12
    requirement_minimum_confidence: float = 0.65
    requirement_max_chunk_characters: int = 3500

    native_text_long_token_characters: int = 80
    native_text_long_token_ratio: float = 0.25
    repeated_boilerplate_min_pages: int = 3
    repeated_boilerplate_min_line_characters: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PROAGENT_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

