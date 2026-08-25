"""Deterministic compilers for already-authorized manual and uploaded documents.

The adapter has no API, network, filesystem, credential, or object-storage authority.  A trusted
caller supplies immutable bytes and the existing ingestion service owns private R2/S3 publication.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree

from pypdf import PdfReader

from echo_masque.knowledge_fabric_document_policy import (
    document_filename_is_safe,
    document_format,
    document_requires_ocr,
)
from echo_masque.knowledge_fabric_ingestion import SourceSnapshotIngestionRequest
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    CanonicalSectionInput,
)

_MARKDOWN_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*#*\s*$")
_MARKDOWN_LIST = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
_DOCX_NAMESPACE = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
_DOCX_HEADING = re.compile(r"^heading\s*([1-9])$", re.IGNORECASE)


class SourceDocumentAdapterError(ValueError):
    """The supplied source bytes cannot be deterministically compiled in Phase 8a."""


class UnsupportedSourceDocument(SourceDocumentAdapterError):
    """The file type has no approved deterministic parser yet."""


class DocumentRequiresOcr(SourceDocumentAdapterError):
    """The PDF has no usable text layer and must wait for a later OCR boundary."""


@dataclass(frozen=True, slots=True)
class SourceDocumentInput:
    """One already-authorized immutable document selected for an existing Fabric Source."""

    source_id: str
    version_key: str
    idempotency_key: str
    canonical_locator: str
    filename: str
    content: bytes
    content_type: str
    title: str = ""
    published_at: datetime | None = None


class KnowledgeFabricDocumentAdapter:
    """Compile source-native document structure into the existing ingestion request contract."""

    def build_snapshot(self, value: SourceDocumentInput) -> SourceSnapshotIngestionRequest:
        """Return a private-artifact snapshot without performing publication itself."""

        if (
            not value.source_id.strip()
            or not value.version_key.strip()
            or not value.idempotency_key.strip()
        ):
            raise SourceDocumentAdapterError("Document snapshot identity is required.")
        if not value.canonical_locator.strip():
            raise SourceDocumentAdapterError("Document canonical locator is required.")
        if not document_filename_is_safe(value.filename):
            raise SourceDocumentAdapterError("Document filename is invalid.")
        source_format = document_format(content_type=value.content_type, filename=value.filename)
        if source_format is None:
            raise UnsupportedSourceDocument("Document type is not supported.")
        document = self._compile_document(value, source_format=source_format)
        return SourceSnapshotIngestionRequest(
            source_id=value.source_id,
            version_key=value.version_key,
            idempotency_key=value.idempotency_key,
            artifact_content=value.content,
            artifact_content_type=value.content_type,
            documents=(document,),
            published_at=value.published_at,
            metadata={"adapter": "document", "filename": value.filename, "format": source_format},
        )

    @staticmethod
    def manual_text(
        *,
        source_id: str,
        version_key: str,
        idempotency_key: str,
        canonical_locator: str,
        title: str,
        text: str,
        markdown: bool = False,
        published_at: datetime | None = None,
    ) -> SourceSnapshotIngestionRequest:
        """Compile explicit manual text for a Fabric Source; legacy scope is never inferred."""

        suffix = "manual.md" if markdown else "manual.txt"
        content_type = "text/markdown" if markdown else "text/plain"
        return KnowledgeFabricDocumentAdapter().build_snapshot(
            SourceDocumentInput(
                source_id=source_id,
                version_key=version_key,
                idempotency_key=idempotency_key,
                canonical_locator=canonical_locator,
                filename=suffix,
                content=text.encode("utf-8"),
                content_type=content_type,
                title=title,
                published_at=published_at,
            )
        )

    def _compile_document(
        self,
        value: SourceDocumentInput,
        *,
        source_format: str,
    ) -> CanonicalDocumentInput:
        if source_format == "markdown":
            sections, blocks = _markdown_structure(_decode_utf8(value.content))
        elif source_format == "text":
            sections, blocks = _text_structure(_decode_utf8(value.content))
        elif source_format == "docx":
            sections, blocks = _docx_structure(value.content)
        else:
            sections, blocks = _pdf_structure(value.content)
        return CanonicalDocumentInput(
            canonical_locator=value.canonical_locator,
            title=value.title or value.filename,
            mime_type=value.content_type.partition(";")[0].strip() or _mime_type(source_format),
            metadata={"filename": value.filename, "format": source_format},
            sections=sections,
            blocks=blocks,
        )


def _decode_utf8(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceDocumentAdapterError("Text document is not valid UTF-8.") from exc


def _text_structure(
    value: str,
) -> tuple[tuple[CanonicalSectionInput, ...], tuple[CanonicalBlockInput, ...]]:
    blocks: list[CanonicalBlockInput] = []
    for ordinal, (line_start, lines) in enumerate(_paragraph_groups(value.splitlines())):
        blocks.append(
            CanonicalBlockInput(
                structural_path=f"paragraph:{ordinal}",
                block_type="paragraph",
                ordinal=ordinal,
                text_content="\n".join(lines),
                coordinates={"line_start": line_start, "line_end": line_start + len(lines) - 1},
            )
        )
    return (), tuple(blocks)


def _markdown_structure(
    value: str,
) -> tuple[tuple[CanonicalSectionInput, ...], tuple[CanonicalBlockInput, ...]]:
    sections: list[CanonicalSectionInput] = []
    blocks: list[CanonicalBlockInput] = []
    heading_stack: list[tuple[int, str]] = []
    pending: list[str] = []
    pending_start = 0

    def flush_pending() -> None:
        nonlocal pending, pending_start
        if not pending:
            return
        nonempty = [line for line in pending if line.strip()]
        if not nonempty:
            pending = []
            return
        if all(_MARKDOWN_LIST.match(line) for line in nonempty):
            block_type = "list"
        elif all("|" in line for line in nonempty):
            block_type = "table"
        else:
            block_type = "paragraph"
        text = "\n".join(pending).strip()
        blocks.append(
            CanonicalBlockInput(
                structural_path=f"{block_type}:{len(blocks)}",
                block_type=block_type,
                ordinal=len(blocks),
                text_content=text,
                section_path=heading_stack[-1][1] if heading_stack else None,
                coordinates={
                    "line_start": pending_start,
                    "line_end": pending_start + len(pending) - 1,
                    "links": _markdown_links(text),
                },
            )
        )
        pending = []

    for line_number, line in enumerate(value.splitlines(), start=1):
        match = _MARKDOWN_HEADING.match(line)
        if match is not None:
            flush_pending()
            level = len(match.group(1))
            heading = match.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            path = f"heading:{len(sections)}"
            sections.append(
                CanonicalSectionInput(
                    structural_path=path,
                    heading=heading,
                    ordinal=len(sections),
                    parent_path=heading_stack[-1][1] if heading_stack else None,
                    coordinates={"line": line_number, "level": level},
                )
            )
            blocks.append(
                CanonicalBlockInput(
                    structural_path=f"heading_block:{len(blocks)}",
                    block_type="heading",
                    ordinal=len(blocks),
                    text_content=heading,
                    section_path=path,
                    coordinates={"line": line_number, "level": level},
                )
            )
            heading_stack.append((level, path))
            continue
        if not pending:
            pending_start = line_number
        pending.append(line)
        if not line.strip():
            flush_pending()
    flush_pending()
    return tuple(sections), tuple(blocks)


def _paragraph_groups(lines: Sequence[str]) -> tuple[tuple[int, tuple[str, ...]], ...]:
    groups: list[tuple[int, tuple[str, ...]]] = []
    current: list[str] = []
    start = 0
    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            if not current:
                start = line_number
            current.append(line)
        elif current:
            groups.append((start, tuple(current)))
            current = []
    if current:
        groups.append((start, tuple(current)))
    return tuple(groups)


def _markdown_links(value: str) -> list[str]:
    return [match.group(1) for match in _MARKDOWN_LINK.finditer(value)]


def _docx_structure(
    value: bytes,
) -> tuple[tuple[CanonicalSectionInput, ...], tuple[CanonicalBlockInput, ...]]:
    try:
        with zipfile.ZipFile(io.BytesIO(value)) as archive:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
            relationships = _docx_relationships(archive)
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise SourceDocumentAdapterError("DOCX document could not be parsed.") from exc

    sections: list[CanonicalSectionInput] = []
    blocks: list[CanonicalBlockInput] = []
    heading_stack: list[tuple[int, str]] = []
    table_number = 0
    body = document.find("w:body", _DOCX_NAMESPACE)
    if body is None:
        raise SourceDocumentAdapterError("DOCX document body is missing.")
    for child in body:
        if child.tag == _docx_tag("p"):
            text = _docx_text(child)
            level = _docx_heading_level(child)
            links, images = _docx_references(child, relationships)
            section_path: str | None
            if level is not None:
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                section_path = f"heading:{len(sections)}"
                sections.append(
                    CanonicalSectionInput(
                        structural_path=section_path,
                        heading=text,
                        ordinal=len(sections),
                        parent_path=heading_stack[-1][1] if heading_stack else None,
                        coordinates={"paragraph": len(blocks), "level": level},
                    )
                )
                heading_stack.append((level, section_path))
                block_type = "heading"
            elif _docx_is_list(child):
                section_path = heading_stack[-1][1] if heading_stack else None
                block_type = "list_item"
            elif images and not text:
                section_path = heading_stack[-1][1] if heading_stack else None
                block_type = "image_reference"
            else:
                section_path = heading_stack[-1][1] if heading_stack else None
                block_type = "paragraph"
            if text or images:
                blocks.append(
                    CanonicalBlockInput(
                        structural_path=f"{block_type}:{len(blocks)}",
                        block_type=block_type,
                        ordinal=len(blocks),
                        text_content=text,
                        section_path=section_path,
                        coordinates={
                            "paragraph": len(blocks),
                            "links": links,
                            "image_relationships": images,
                        },
                    )
                )
        elif child.tag == _docx_tag("tbl"):
            rows = _docx_table_rows(child)
            blocks.append(
                CanonicalBlockInput(
                    structural_path=f"table:{table_number}",
                    block_type="table",
                    ordinal=len(blocks),
                    text_content="\n".join("\t".join(row) for row in rows),
                    section_path=heading_stack[-1][1] if heading_stack else None,
                    coordinates={"table": table_number, "row_count": len(rows)},
                )
            )
            table_number += 1
    return tuple(sections), tuple(blocks)


def _docx_relationships(archive: zipfile.ZipFile) -> Mapping[str, str]:
    try:
        root = ElementTree.fromstring(archive.read("word/_rels/document.xml.rels"))
    except KeyError:
        return {}
    return {
        item.attrib["Id"]: item.attrib["Target"]
        for item in root.findall("rel:Relationship", _DOCX_NAMESPACE)
        if "Id" in item.attrib and "Target" in item.attrib
    }


def _docx_text(value: ElementTree.Element[str]) -> str:
    return "".join(node.text or "" for node in value.findall(".//w:t", _DOCX_NAMESPACE)).strip()


def _docx_heading_level(value: ElementTree.Element[str]) -> int | None:
    style = value.find("w:pPr/w:pStyle", _DOCX_NAMESPACE)
    if style is None:
        return None
    match = _DOCX_HEADING.match(style.attrib.get(_docx_tag("val"), ""))
    return int(match.group(1)) if match is not None else None


def _docx_is_list(value: ElementTree.Element[str]) -> bool:
    return value.find("w:pPr/w:numPr", _DOCX_NAMESPACE) is not None


def _docx_references(
    value: ElementTree.Element[str], relationships: Mapping[str, str]
) -> tuple[list[str], list[str]]:
    relationship_ids = [
        node.attrib[_relationship_tag("id")]
        for node in value.findall(".//*[@r:id]", _DOCX_NAMESPACE)
        if _relationship_tag("id") in node.attrib
    ]
    embed_ids = [
        node.attrib[_relationship_tag("embed")]
        for node in value.findall(".//a:blip", _DOCX_NAMESPACE)
        if _relationship_tag("embed") in node.attrib
    ]
    return (
        [relationships[item] for item in relationship_ids if item in relationships],
        [relationships[item] for item in embed_ids if item in relationships],
    )


def _docx_table_rows(value: ElementTree.Element[str]) -> list[list[str]]:
    return [
        [_docx_text(cell) for cell in row.findall("w:tc", _DOCX_NAMESPACE)]
        for row in value.findall("w:tr", _DOCX_NAMESPACE)
    ]


def _docx_tag(name: str) -> str:
    return f"{{{_DOCX_NAMESPACE['w']}}}{name}"


def _relationship_tag(name: str) -> str:
    return f"{{{_DOCX_NAMESPACE['r']}}}{name}"


def _pdf_structure(
    value: bytes,
) -> tuple[tuple[CanonicalSectionInput, ...], tuple[CanonicalBlockInput, ...]]:
    try:
        reader = PdfReader(io.BytesIO(value))
        page_texts = [
            page.extract_text(extraction_mode="layout") or "" if "/Contents" in page else ""
            for page in reader.pages
        ]
    except Exception as exc:
        raise SourceDocumentAdapterError("PDF document could not be parsed.") from exc
    if document_requires_ocr(page_texts):
        raise DocumentRequiresOcr("PDF has no usable text layer.")
    sections: list[CanonicalSectionInput] = []
    blocks: list[CanonicalBlockInput] = []
    for ordinal, text in enumerate(page_texts, start=1):
        if not text.strip():
            continue
        section_path = f"page:{ordinal}"
        sections.append(
            CanonicalSectionInput(
                structural_path=section_path,
                heading=f"Page {ordinal}",
                ordinal=ordinal - 1,
                coordinates={"page": ordinal},
            )
        )
        blocks.append(
            CanonicalBlockInput(
                structural_path=f"page:{ordinal}:text",
                block_type="pdf_page",
                ordinal=len(blocks),
                text_content=text.strip(),
                section_path=section_path,
                coordinates={"page": ordinal, "text_layer": True},
            )
        )
    return tuple(sections), tuple(blocks)


def _mime_type(source_format: str) -> str:
    return {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "markdown": "text/markdown",
        "pdf": "application/pdf",
        "text": "text/plain",
    }[source_format]


__all__ = [
    "DocumentRequiresOcr",
    "KnowledgeFabricDocumentAdapter",
    "SourceDocumentAdapterError",
    "SourceDocumentInput",
    "UnsupportedSourceDocument",
]
