"""Pure safety and branch decisions for deterministic document adapters."""

from __future__ import annotations

from collections.abc import Sequence

_DOCX_CONTENT_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
_MARKDOWN_SUFFIXES = (".md", ".markdown")
_TEXT_SUFFIXES = (".txt", ".text", ".log")


def document_format(*, content_type: str, filename: str) -> str | None:
    """Classify only the deterministic formats implemented by Phase 8a."""

    normalized_type = content_type.partition(";")[0].strip().casefold()
    normalized_name = filename.strip().casefold()
    if normalized_type in _DOCX_CONTENT_TYPES or normalized_name.endswith(".docx"):
        return "docx"
    if normalized_type == "application/pdf" or normalized_name.endswith(".pdf"):
        return "pdf"
    if normalized_type in {"text/markdown", "text/x-markdown"} or normalized_name.endswith(
        _MARKDOWN_SUFFIXES
    ):
        return "markdown"
    if normalized_type.startswith("text/") or normalized_name.endswith(_TEXT_SUFFIXES):
        return "text"
    return None


def document_filename_is_safe(filename: str) -> bool:
    """Keep a caller's document label from becoming a filesystem path or object key."""

    normalized = filename.strip()
    return bool(normalized) and "/" not in normalized and "\\" not in normalized


def document_requires_ocr(page_texts: Sequence[str]) -> bool:
    """Require a later OCR worker only when a PDF has no usable text layer at all."""

    return not any(value.strip() for value in page_texts)


__all__ = [
    "document_filename_is_safe",
    "document_format",
    "document_requires_ocr",
]
