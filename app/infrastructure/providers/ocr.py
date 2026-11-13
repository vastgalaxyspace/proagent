from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader, PdfWriter

from app.infrastructure.providers.settings import OpenParserSettings


@dataclass(frozen=True)
class OCRResult:
    text: str
    provider: str
    confidence: float
    layout: dict[str, Any]


class OCRProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    def is_available(self) -> bool:
        ...

    def extract_pdf_page(
        self,
        *,
        path: Path,
        page_number: int,
    ) -> OCRResult:
        ...


class DisabledOCRProvider:
    @property
    def name(self) -> str:
        return "disabled"

    def is_available(self) -> bool:
        return False

    def extract_pdf_page(
        self,
        *,
        path: Path,
        page_number: int,
    ) -> OCRResult:
        raise RuntimeError(
            "OCR is disabled. Configure an OCR provider."
        )


class TesseractOCRProvider:
    def __init__(
        self,
        *,
        command: str | None,
        language: str,
        render_scale: float,
        timeout_seconds: int,
    ) -> None:
        self.command = command
        self.language = language
        self.render_scale = render_scale
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract

            if self.command:
                pytesseract.pytesseract.tesseract_cmd = (
                    self.command
                )

            pytesseract.get_tesseract_version()
            return True

        except Exception:
            return False

    def extract_pdf_page(
        self,
        *,
        path: Path,
        page_number: int,
    ) -> OCRResult:
        import pypdfium2 as pdfium
        import pytesseract
        from pytesseract import Output

        if self.command:
            pytesseract.pytesseract.tesseract_cmd = (
                self.command
            )

        pdf = pdfium.PdfDocument(str(path))

        try:
            if page_number < 1 or page_number > len(pdf):
                raise ValueError(
                    "OCR page number is outside the PDF."
                )

            page = pdf[page_number - 1]

            try:
                bitmap = page.render(
                    scale=self.render_scale,
                )

                try:
                    image = bitmap.to_pil().copy()
                finally:
                    bitmap.close()

            finally:
                page.close()

        finally:
            pdf.close()

        data = pytesseract.image_to_data(
            image,
            lang=self.language,
            output_type=Output.DICT,
            timeout=self.timeout_seconds,
        )

        line_groups: dict[
            tuple[int, int, int],
            list[str],
        ] = {}

        confidences: list[float] = []
        words: list[dict[str, Any]] = []

        item_count = len(data.get("text", []))

        for index in range(item_count):
            text = str(data["text"][index] or "").strip()

            try:
                confidence = float(
                    data["conf"][index]
                )
            except (TypeError, ValueError):
                confidence = -1

            if not text:
                continue

            key = (
                int(data["block_num"][index]),
                int(data["par_num"][index]),
                int(data["line_num"][index]),
            )

            line_groups.setdefault(key, []).append(text)

            if confidence >= 0:
                confidences.append(confidence)

            width = max(1, image.width)
            height = max(1, image.height)

            left = int(data["left"][index])
            top = int(data["top"][index])
            word_width = int(data["width"][index])
            word_height = int(data["height"][index])

            words.append(
                {
                    "text": text,
                    "confidence": confidence,
                    "bbox": [
                        left / width,
                        top / height,
                        (left + word_width) / width,
                        (top + word_height) / height,
                    ],
                }
            )

        text = "\n".join(
            " ".join(tokens)
            for tokens in line_groups.values()
        ).strip()

        confidence = (
            sum(confidences) / len(confidences) / 100
            if confidences
            else 0.0
        )

        return OCRResult(
            text=text,
            provider=self.name,
            confidence=round(confidence, 4),
            layout={
                "kind": "ocr_page",
                "page_number": page_number,
                "image_width": image.width,
                "image_height": image.height,
                "words": words,
            },
        )


class OpenParserOCRProvider:
    def __init__(
        self,
        *,
        settings: OpenParserSettings,
    ) -> None:
        settings.validate_configuration()
        self.settings = settings

    @property
    def name(self) -> str:
        return "openparser"

    @property
    def model(self) -> str:
        return self.settings.ocr_model

    def is_available(self) -> bool:
        try:
            self.settings.validate_configuration()
            return True
        except ValueError:
            return False

    def extract_pdf_page(
        self,
        *,
        path: Path,
        page_number: int,
    ) -> OCRResult:
        selected_pdf = self._selected_page_pdf(
            path=path,
            page_number=page_number,
        )
        payload = self._parse_pdf(
            pdf_bytes=selected_pdf,
            source_path=path,
            page_number=page_number,
        )

        return self._result_from_payload(
            payload=payload,
            page_number=page_number,
        )

    @staticmethod
    def _selected_page_pdf(
        *,
        path: Path,
        page_number: int,
    ) -> bytes:
        reader = PdfReader(str(path))

        if page_number < 1 or page_number > len(reader.pages):
            raise ValueError(
                "OCR page number is outside the PDF."
            )

        writer = PdfWriter()
        writer.add_page(reader.pages[page_number - 1])
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def _parse_pdf(
        self,
        *,
        pdf_bytes: bytes,
        source_path: Path,
        page_number: int,
    ) -> dict[str, Any]:
        request_json = json.dumps(
            {
                "ocr_model": self.settings.ocr_model,
                "output_format": "openparser@1",
            },
            separators=(",", ":"),
        ).encode("utf-8")

        boundary = f"----proagent-{uuid.uuid4().hex}"
        body = b"".join(
            [
                (
                    f"--{boundary}\r\n"
                    "Content-Disposition: form-data; "
                    'name="request"\r\n'
                    "Content-Type: application/json\r\n\r\n"
                ).encode("utf-8"),
                request_json,
                b"\r\n",
                (
                    f"--{boundary}\r\n"
                    "Content-Disposition: form-data; "
                    'name="file"; filename="selected-page.pdf"\r\n'
                    "Content-Type: application/pdf\r\n\r\n"
                ).encode("utf-8"),
                pdf_bytes,
                f"\r\n--{boundary}--\r\n".encode("utf-8"),
            ]
        )

        source_digest = hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest()
        idempotency_key = hashlib.sha256(
            (
                f"{source_digest}:{page_number}:"
                f"{self.settings.ocr_model}"
            ).encode("utf-8")
        ).hexdigest()

        request = urllib.request.Request(
            (
                f"{self.settings.base_url.rstrip('/')}"
                "/parse"
            ),
            data=body,
            headers={
                "Authorization": (
                    "Bearer "
                    f"{self.settings.resolved_api_key()}"
                ),
                "Content-Type": (
                    "multipart/form-data; "
                    f"boundary={boundary}"
                ),
                "Idempotency-Key": idempotency_key,
                "Accept": "application/json",
                "User-Agent": "proagent/0.1",
            },
            method="POST",
        )

        maximum_bytes = (
            self.settings.max_response_mb
            * 1024
            * 1024
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=(
                    self.settings.request_timeout_seconds
                ),
            ) as response:
                response_body = response.read(
                    maximum_bytes + 1
                )
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                "OpenParser OCR request failed with "
                f"HTTP {exc.code}."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "OpenParser OCR endpoint could not be reached."
            ) from exc

        if len(response_body) > maximum_bytes:
            raise RuntimeError(
                "OpenParser OCR response exceeded the "
                "configured size limit."
            )

        try:
            payload = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "OpenParser OCR returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                "OpenParser OCR returned a non-object response."
            )

        return payload

    def _result_from_payload(
        self,
        *,
        payload: dict[str, Any],
        page_number: int,
    ) -> OCRResult:
        pages = payload.get("pages") or []

        if pages and not isinstance(pages, list):
            raise RuntimeError(
                "OpenParser OCR returned invalid pages."
            )

        raw_blocks = (
            payload.get("blocks")
            or payload.get("elements")
            or []
        )

        if not isinstance(raw_blocks, list):
            raise RuntimeError(
                "OpenParser OCR returned invalid blocks."
            )

        blocks: list[dict[str, Any]] = []
        text_parts: list[str] = []
        confidences: list[float] = []
        tables: list[dict[str, Any]] = []

        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                continue

            block_text = str(
                raw_block.get("text")
                or raw_block.get("content")
                or raw_block.get("markdown")
                or ""
            ).strip()
            role = str(
                raw_block.get("role")
                or raw_block.get("kind")
                or "text"
            ).strip().lower()
            confidence = self._confidence_value(
                raw_block.get("confidence")
            )
            locations = raw_block.get("locations") or []
            location = (
                locations[0]
                if isinstance(locations, list)
                and locations
                and isinstance(locations[0], dict)
                else {}
            )
            bbox = (
                location.get("bbox")
                if isinstance(location, dict)
                else None
            )

            normalized_block = {
                "kind": role,
                "text": block_text,
                "confidence": confidence,
                "bbox": bbox,
                "table_html": (
                    raw_block.get("table_html")
                    or raw_block.get("html")
                    or ""
                ),
            }
            blocks.append(normalized_block)

            if block_text:
                text_parts.append(block_text)
            if confidence is not None:
                confidences.append(confidence)
            if "table" in role or normalized_block["table_html"]:
                tables.append(normalized_block)

        text = "\n\n".join(text_parts).strip()

        if not text:
            text = str(
                payload.get("markdown")
                or payload.get("text")
                or ""
            ).strip()

        if not text and pages:
            first_page = pages[0]
            if isinstance(first_page, dict):
                text = str(
                    first_page.get("markdown")
                    or first_page.get("text")
                    or first_page.get("content")
                    or ""
                ).strip()

        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else (0.75 if text else 0.0)
        )

        return OCRResult(
            text=text,
            provider=self.name,
            confidence=round(confidence, 4),
            layout={
                "kind": "ocr_page",
                "page_number": page_number,
                "model": self.model,
                "blocks": blocks,
                "tables": tables,
                "page_metadata": pages[0] if pages else {},
            },
        )

    @staticmethod
    def _confidence_value(value: Any) -> float | None:
        if isinstance(value, dict):
            value = value.get("score")

        if value is None:
            return None

        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None

        if confidence > 1:
            confidence /= 100

        return min(1.0, max(0.0, confidence))


def build_ocr_provider(
    *,
    enabled: bool,
    provider_name: str,
    tesseract_command: str | None,
    language: str,
    render_scale: float,
    timeout_seconds: int,
    openparser_settings: OpenParserSettings | None = None,
) -> OCRProvider:
    if not enabled or provider_name == "disabled":
        return DisabledOCRProvider()

    if provider_name == "tesseract":
        return TesseractOCRProvider(
            command=tesseract_command,
            language=language,
            render_scale=render_scale,
            timeout_seconds=timeout_seconds,
        )

    if provider_name == "openparser":
        if openparser_settings is None:
            raise ValueError(
                "OpenParser settings are required."
            )

        return OpenParserOCRProvider(
            settings=openparser_settings
        )

    raise ValueError(
        f"Unsupported OCR provider: {provider_name}"
    )
