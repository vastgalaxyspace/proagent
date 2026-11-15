from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from openpyxl import load_workbook
from pypdf import PdfReader


ExtractionResultStatus = Literal[
    "extracted",
    "needs_ocr",
    "empty",
]


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    source_page_number: int
    source_name: str
    text: str
    extraction_method: str
    ocr_required: bool
    warnings: list[str]
    layout: dict[str, Any]


@dataclass(frozen=True)
class NativeExtractionResult:
    status: ExtractionResultStatus
    text: str
    pages: list[ExtractedPage]
    warnings: list[str]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class NativeParserLimits:
    max_pdf_pages: int
    max_document_characters: int
    min_native_page_characters: int

    max_archive_files: int
    max_archive_total_bytes: int
    max_archive_entry_bytes: int
    max_archive_compression_ratio: int

    max_spreadsheet_cells: int

    office_converter_bin: str
    office_converter_timeout_seconds: int


class NativeDocumentParser:
    _DOCUMENT_SUFFIXES = frozenset(
        {
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".htm",
        }
    )

    _TEXT_SUFFIXES = frozenset(
        {
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".htm",
        }
    )

    def __init__(self, limits: NativeParserLimits) -> None:
        self.limits = limits

    def extract(
        self,
        *,
        path: Path,
        document_id: str,
    ) -> NativeExtractionResult:
        suffix = path.suffix.lower()

        if suffix == ".zip":
            result = self._extract_archive(
                path=path,
                document_id=document_id,
            )
        else:
            result = self._extract_path(
                path=path,
                document_id=document_id,
                source_name=path.name,
            )

        combined_text = result.text

        if len(combined_text) > self.limits.max_document_characters:
            warnings = [
                *result.warnings,
                (
                    "Combined document text was truncated to "
                    f"{self.limits.max_document_characters} characters."
                ),
            ]

            result = replace(
                result,
                text=combined_text[
                    : self.limits.max_document_characters
                ],
                warnings=warnings,
            )

        return result

    def _extract_path(
        self,
        *,
        path: Path,
        document_id: str,
        source_name: str,
    ) -> NativeExtractionResult:
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_pdf(
                path=path,
                source_name=source_name,
            )

        if suffix == ".docx":
            return self._extract_docx(
                path=path,
                source_name=source_name,
            )

        if suffix == ".xlsx":
            return self._extract_xlsx(
                path=path,
                source_name=source_name,
            )

        if suffix in {".doc", ".xls"}:
            return self._extract_legacy_office(
                path=path,
                document_id=document_id,
                source_name=source_name,
            )

        if suffix in self._TEXT_SUFFIXES:
            return self._extract_text_file(
                path=path,
                source_name=source_name,
            )

        raise ValueError(
            f"Unsupported native extraction type: {suffix or 'none'}"
        )

    def _extract_pdf(
        self,
        *,
        path: Path,
        source_name: str,
    ) -> NativeExtractionResult:
        reader = PdfReader(str(path))

        if reader.is_encrypted:
            raise ValueError(
                "Encrypted PDF documents are not supported."
            )

        if len(reader.pages) > self.limits.max_pdf_pages:
            raise ValueError(
                f"PDF contains more than "
                f"{self.limits.max_pdf_pages} pages."
            )

        pages: list[ExtractedPage] = []
        document_parts: list[str] = []
        warnings: list[str] = []

        for page_number, pdf_page in enumerate(
            reader.pages,
            start=1,
        ):
            page_warnings: list[str] = []

            try:
                raw_text = pdf_page.extract_text(
                    extraction_mode="layout"
                ) or ""
            except TypeError:
                raw_text = pdf_page.extract_text() or ""

            text = self._clean_text(raw_text)

            ocr_required = (
                len(text)
                < self.limits.min_native_page_characters
            )

            if ocr_required:
                warning = (
                    f"Page {page_number} has weak or no native text; "
                    "OCR is required."
                )
                page_warnings.append(warning)
                warnings.append(warning)

            if text:
                document_parts.append(
                    f"[page {page_number}]\n{text}"
                )

            pages.append(
                ExtractedPage(
                    page_number=page_number,
                    source_page_number=page_number,
                    source_name=source_name,
                    text=text,
                    extraction_method="pypdf",
                    ocr_required=ocr_required,
                    warnings=page_warnings,
                    layout={
                        "kind": "pdf_page",
                        "page_number": page_number,
                    },
                )
            )

        combined_text = self._clean_text(
            "\n\n".join(document_parts)
        )

        if any(page.ocr_required for page in pages):
            status: ExtractionResultStatus = "needs_ocr"
        elif combined_text:
            status = "extracted"
        else:
            status = "empty"

        return NativeExtractionResult(
            status=status,
            text=combined_text,
            pages=pages,
            warnings=warnings,
            metadata={
                "parser": "pypdf",
                "pdf_page_count": len(pages),
            },
        )

    def _extract_docx(
        self,
        *,
        path: Path,
        source_name: str,
    ) -> NativeExtractionResult:
        from docx import Document as WordDocument

        document = WordDocument(str(path))

        text_parts: list[str] = []
        blocks: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []

        for item in document.iter_inner_content():
            if hasattr(item, "rows"):
                rows: list[list[str]] = []

                for row in item.rows:
                    values = [
                        self._clean_text(cell.text)
                        for cell in row.cells
                    ]
                    rows.append(values)

                table_text = self._table_text(rows)

                if table_text:
                    text_parts.append(table_text)

                tables.append(
                    {
                        "rows": rows,
                        "reading_order": (
                            len(blocks) + len(tables)
                        ),
                    }
                )

                continue

            text = self._clean_text(
                str(getattr(item, "text", ""))
            )

            if not text:
                continue

            style = getattr(item, "style", None)
            style_name = str(
                getattr(style, "name", "") or ""
            )

            text_parts.append(text)
            blocks.append(
                {
                    "text": text,
                    "style": style_name,
                    "reading_order": (
                        len(blocks) + len(tables)
                    ),
                }
            )

        text = self._clean_text("\n\n".join(text_parts))
        warnings = [] if text else [
            "DOCX contains no extractable text."
        ]

        page = ExtractedPage(
            page_number=1,
            source_page_number=1,
            source_name=source_name,
            text=text,
            extraction_method="python_docx",
            ocr_required=False,
            warnings=warnings,
            layout={
                "kind": "docx_document",
                "blocks": blocks,
                "tables": tables,
            },
        )

        return NativeExtractionResult(
            status="extracted" if text else "empty",
            text=text,
            pages=[page],
            warnings=warnings,
            metadata={
                "parser": "python_docx",
                "paragraph_count": len(blocks),
                "table_count": len(tables),
            },
        )

    def _extract_xlsx(
        self,
        *,
        path: Path,
        source_name: str,
    ) -> NativeExtractionResult:
        workbook = load_workbook(
            filename=path,
            read_only=True,
            data_only=True,
        )

        pages: list[ExtractedPage] = []
        document_parts: list[str] = []
        total_cells = 0

        try:
            for sheet_number, sheet in enumerate(
                workbook.worksheets,
                start=1,
            ):
                rows: list[list[str]] = []

                for row in sheet.iter_rows(values_only=True):
                    values = [
                        "" if value is None else str(value)
                        for value in row
                    ]

                    while values and not values[-1]:
                        values.pop()

                    if not any(values):
                        continue

                    total_cells += len(values)

                    if (
                        total_cells
                        > self.limits.max_spreadsheet_cells
                    ):
                        raise ValueError(
                            "Spreadsheet exceeds the configured "
                            "cell limit."
                        )

                    rows.append(values)

                table_text = self._table_text(rows)
                sheet_text = self._clean_text(
                    f"[sheet {sheet.title}]\n{table_text}"
                )

                if sheet_text:
                    document_parts.append(sheet_text)

                pages.append(
                    ExtractedPage(
                        page_number=sheet_number,
                        source_page_number=sheet_number,
                        source_name=source_name,
                        text=sheet_text,
                        extraction_method="openpyxl",
                        ocr_required=False,
                        warnings=[],
                        layout={
                            "kind": "spreadsheet",
                            "sheet_name": sheet.title,
                            "rows": rows,
                        },
                    )
                )
        finally:
            workbook.close()

        combined_text = self._clean_text(
            "\n\n".join(document_parts)
        )

        warnings = [] if combined_text else [
            "XLSX contains no populated cells."
        ]

        return NativeExtractionResult(
            status="extracted" if combined_text else "empty",
            text=combined_text,
            pages=pages,
            warnings=warnings,
            metadata={
                "parser": "openpyxl",
                "sheet_count": len(pages),
                "processed_cells": total_cells,
            },
        )

    def _extract_text_file(
        self,
        *,
        path: Path,
        source_name: str,
    ) -> NativeExtractionResult:
        raw_text = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        text = self._clean_text(raw_text)
        warnings = [] if text else [
            "Text document contains no extractable text."
        ]

        return NativeExtractionResult(
            status="extracted" if text else "empty",
            text=text,
            pages=[
                ExtractedPage(
                    page_number=1,
                    source_page_number=1,
                    source_name=source_name,
                    text=text,
                    extraction_method="utf8_text",
                    ocr_required=False,
                    warnings=warnings,
                    layout={
                        "kind": "text_document",
                    },
                )
            ],
            warnings=warnings,
            metadata={
                "parser": "utf8_text",
            },
        )

    def _extract_legacy_office(
        self,
        *,
        path: Path,
        document_id: str,
        source_name: str,
    ) -> NativeExtractionResult:
        output_directory = path.parent / "converted"
        output_directory.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="libreoffice-",
            dir=output_directory,
            ignore_cleanup_errors=True,
        ) as profile_directory:
            try:
                subprocess.run(
                    [
                        self.limits.office_converter_bin,
                        (
                            "-env:UserInstallation="
                            f"{Path(profile_directory).resolve().as_uri()}"
                        ),
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(output_directory),
                        str(path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=(
                        self.limits
                        .office_converter_timeout_seconds
                    ),
                )
            except FileNotFoundError as exc:
                raise ValueError(
                    "DOC/XLS extraction requires LibreOffice."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise ValueError(
                    "DOC/XLS conversion timed out."
                ) from exc
            except subprocess.CalledProcessError as exc:
                detail = self._clean_text(exc.stderr)[:240]

                raise ValueError(
                    f"DOC/XLS conversion failed: {detail}"
                ) from exc

        converted_path = output_directory / f"{path.stem}.pdf"

        if not converted_path.is_file():
            raise ValueError(
                "DOC/XLS conversion produced no PDF."
            )

        result = self._extract_pdf(
            path=converted_path,
            source_name=source_name,
        )

        return replace(
            result,
            pages=[
                replace(
                    page,
                    extraction_method="libreoffice+pypdf",
                )
                for page in result.pages
            ],
            metadata={
                **result.metadata,
                "converter": "libreoffice",
                "original_document_id": document_id,
            },
        )

    def _extract_archive(
        self,
        *,
        path: Path,
        document_id: str,
    ) -> NativeExtractionResult:
        pages: list[ExtractedPage] = []
        document_parts: list[str] = []
        warnings: list[str] = []
        total_uncompressed_bytes = 0
        processed_member_count = 0
        failed_member_count = 0
        skipped_member_count = 0

        with zipfile.ZipFile(path) as archive:
            members = [
                member
                for member in archive.infolist()
                if not member.is_dir()
            ]

            if not members:
                raise ValueError(
                    "ZIP archive contains no documents."
                )

            if len(members) > self.limits.max_archive_files:
                raise ValueError(
                    "ZIP archive contains too many files."
                )

            with tempfile.TemporaryDirectory(
                prefix="tender-archive-"
            ) as extraction_directory:
                extraction_root = Path(
                    extraction_directory
                ).resolve()

                for member in members:
                    member_path = PurePosixPath(
                        member.filename.replace("\\", "/")
                    )

                    unix_mode = member.external_attr >> 16

                    if (
                        member_path.is_absolute()
                        or ".." in member_path.parts
                        or unix_mode & 0o170000 == 0o120000
                    ):
                        raise ValueError(
                            "ZIP contains an unsafe path or link."
                        )

                    if member.flag_bits & 0x1:
                        raise ValueError(
                            "Encrypted ZIP members are unsupported."
                        )

                    if self._is_ignorable_archive_member(
                        member_path
                    ):
                        skipped_member_count += 1
                        warnings.append(
                            f"{member_path.as_posix()}: skipped "
                            "temporary Office or archive metadata file."
                        )
                        continue

                    suffix = Path(member.filename).suffix.lower()

                    if suffix not in self._DOCUMENT_SUFFIXES:
                        raise ValueError(
                            "ZIP contains an unsupported document type: "
                            f"{suffix or 'none'}."
                        )

                    if (
                        member.file_size
                        > self.limits.max_archive_entry_bytes
                    ):
                        raise ValueError(
                            "A ZIP member exceeds its size limit."
                        )

                    compression_ratio = (
                        member.file_size
                        / max(1, member.compress_size)
                    )

                    if (
                        compression_ratio
                        > self.limits
                        .max_archive_compression_ratio
                    ):
                        raise ValueError(
                            "ZIP compression ratio is unsafe."
                        )

                    total_uncompressed_bytes += member.file_size

                    if (
                        total_uncompressed_bytes
                        > self.limits.max_archive_total_bytes
                    ):
                        raise ValueError(
                            "ZIP expands beyond its total size limit."
                        )

                    target_path = extraction_root.joinpath(
                        *member_path.parts
                    ).resolve()

                    if not target_path.is_relative_to(
                        extraction_root
                    ):
                        raise ValueError(
                            "ZIP member escaped extraction directory."
                        )

                    target_path.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    with archive.open(member) as source:
                        with target_path.open("wb") as destination:
                            shutil.copyfileobj(source, destination)

                    try:
                        member_result = self._extract_path(
                            path=target_path,
                            document_id=document_id,
                            source_name=member_path.as_posix(),
                        )
                    except Exception as exc:
                        failed_member_count += 1
                        warnings.append(
                            f"{member_path.as_posix()}: native "
                            f"extraction failed: {exc}"
                        )
                        continue

                    processed_member_count += 1

                    document_parts.append(
                        f"[file {member_path.as_posix()}]\n"
                        f"{member_result.text}"
                    )

                    warnings.extend(
                        (
                            f"{member_path.as_posix()}: "
                            f"{warning}"
                        )
                        for warning in member_result.warnings
                    )

                    for page in member_result.pages:
                        pages.append(
                            replace(
                                page,
                                page_number=len(pages) + 1,
                                source_name=(
                                    member_path.as_posix()
                                ),
                            )
                        )

        combined_text = self._clean_text(
            "\n\n".join(document_parts)
        )

        if any(page.ocr_required for page in pages):
            status: ExtractionResultStatus = "needs_ocr"
        elif combined_text:
            status = "extracted"
        else:
            status = "empty"

        return NativeExtractionResult(
            status=status,
            text=combined_text,
            pages=pages,
            warnings=warnings,
            metadata={
                "parser": "zip_archive",
                "member_count": len(members),
                "processed_member_count": processed_member_count,
                "failed_member_count": failed_member_count,
                "skipped_member_count": skipped_member_count,
                "uncompressed_bytes": total_uncompressed_bytes,
            },
        )

    @staticmethod
    def _is_ignorable_archive_member(
        member_path: PurePosixPath,
    ) -> bool:
        parts = member_path.parts
        name = member_path.name

        return bool(
            name.startswith("~$")
            or name in {".DS_Store", "Thumbs.db", "desktop.ini"}
            or "__MACOSX" in parts
        )

    @staticmethod
    def _table_text(rows: list[list[str]]) -> str:
        return "\n".join(
            " | ".join(value.strip() for value in row)
            for row in rows
        )

    @staticmethod
    def _clean_text(value: str) -> str:
        value = value.replace("\x00", "")
        value = value.replace("\r\n", "\n").replace("\r", "\n")

        cleaned_lines = [
            re.sub(r"[ \t]+", " ", line).strip()
            for line in value.splitlines()
        ]

        output: list[str] = []
        previous_blank = False

        for line in cleaned_lines:
            is_blank = not line

            if is_blank and previous_blank:
                continue

            output.append(line)
            previous_blank = is_blank

        return "\n".join(output).strip()
