from __future__ import annotations

from pathlib import Path

import yaml

from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
)


class FieldCatalogService:
    def __init__(
        self,
        *,
        config_path: Path,
    ) -> None:
        self.config_path = config_path

    def load(self) -> TenderFieldCatalog:
        if not self.config_path.is_file():
            raise RuntimeError(
                "Tender field configuration was not found: "
                f"{self.config_path}"
            )

        parsed = yaml.safe_load(
            self.config_path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(parsed, dict):
            raise RuntimeError(
                "Tender field configuration must contain "
                "an object."
            )

        catalog = TenderFieldCatalog.model_validate(
            parsed
        )

        field_keys = [
            field.key
            for _section, field
            in catalog.all_fields()
        ]

        duplicate_keys = sorted(
            {
                field_key
                for field_key in field_keys
                if field_keys.count(field_key) > 1
            }
        )

        if duplicate_keys:
            raise RuntimeError(
                "Duplicate tender field keys: "
                + ", ".join(duplicate_keys)
            )

        return catalog