"""Deterministic compiler for an already-fetched public Website response."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from echo_masque.knowledge_fabric_external_policy import (
    canonical_public_https_locator,
    website_response_idempotency_key,
    website_response_version_key,
)
from echo_masque.knowledge_fabric_ingestion import SourceSnapshotIngestionRequest
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    CanonicalSectionInput,
)


class WebsiteResponseRejected(ValueError):
    """An otherwise successful HTTP response cannot become source text safely."""


@dataclass(frozen=True, slots=True)
class WebsiteResponseInput:
    source_id: str
    locator: str
    content: bytes
    content_type: str
    fetched_at: datetime


class KnowledgeFabricWebsiteAdapter:
    """Convert bounded UTF-8 website text into the existing private snapshot contract."""

    def build_snapshot(self, value: WebsiteResponseInput) -> SourceSnapshotIngestionRequest:
        locator = canonical_public_https_locator(value.locator)
        content_type = value.content_type.casefold().split(";", maxsplit=1)[0].strip()
        try:
            decoded = value.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WebsiteResponseRejected("Website response is not UTF-8 text.") from exc
        if content_type == "text/html":
            title, sections, blocks = _html_structure(decoded)
        else:
            title = urlsplit(locator).hostname or "Website source"
            sections = ()
            blocks = (
                CanonicalBlockInput(
                    structural_path="response:0",
                    block_type="website_text",
                    ordinal=0,
                    text_content=decoded,
                    coordinates={"locator": locator},
                ),
            )
        return SourceSnapshotIngestionRequest(
            source_id=value.source_id,
            version_key=website_response_version_key(value.content),
            idempotency_key=website_response_idempotency_key(
                source_id=value.source_id,
                content=value.content,
            ),
            artifact_content=value.content,
            artifact_content_type=content_type,
            documents=(
                CanonicalDocumentInput(
                    canonical_locator=locator,
                    title=title,
                    mime_type=content_type,
                    metadata={"adapter": "website_public_https", "locator": locator},
                    sections=sections,
                    blocks=blocks,
                ),
            ),
            published_at=value.fetched_at,
            metadata={"adapter": "website_public_https"},
        )


class _MainTextParser(HTMLParser):
    _ignored_tags = frozenset({"footer", "head", "nav", "script", "style"})
    _block_tags = frozenset({"p", "li", "pre", "blockquote"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._main_depth = 0
        self._body_depth = 0
        self._tag: str | None = None
        self._parts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.casefold()
        if lower in self._ignored_tags:
            self._ignored_depth += 1
        if lower == "main":
            self._main_depth += 1
        if lower == "body":
            self._body_depth += 1
        if lower == "title":
            self._in_title = True
        if lower in self._block_tags or lower in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self._tag = lower

    def handle_endtag(self, tag: str) -> None:
        lower = tag.casefold()
        if lower == "title":
            self._in_title = False
        if self._tag == lower:
            self._flush()
        if lower == "main" and self._main_depth:
            self._main_depth -= 1
        if lower == "body" and self._body_depth:
            self._body_depth -= 1
        if lower in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._ignored_depth == 0 and (self._main_depth > 0 or self._body_depth > 0):
            self._parts.append(data)

    def finish(self) -> list[tuple[str, str]]:
        self._flush()
        return self.items

    def _flush(self) -> None:
        text = " ".join("".join(self._parts).split())
        self._parts.clear()
        if text:
            self.items.append((self._tag or "p", text))
        self._tag = None


def _html_structure(
    content: str,
) -> tuple[str, tuple[CanonicalSectionInput, ...], tuple[CanonicalBlockInput, ...]]:
    parser = _MainTextParser()
    parser.feed(content)
    items = parser.finish()
    title = " ".join("".join(parser.title_parts).split()) or "Website source"
    sections: list[CanonicalSectionInput] = []
    blocks: list[CanonicalBlockInput] = []
    active_section: str | None = None
    for _ordinal, (tag, text) in enumerate(items):
        if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
            active_section = f"heading:{len(sections)}"
            sections.append(
                CanonicalSectionInput(
                    structural_path=active_section,
                    heading=text,
                    ordinal=len(sections),
                    coordinates={"level": int(tag[1])},
                )
            )
            continue
        blocks.append(
            CanonicalBlockInput(
                structural_path=f"block:{len(blocks)}",
                block_type={"li": "list_item", "pre": "preformatted"}.get(tag, "paragraph"),
                ordinal=len(blocks),
                text_content=text,
                section_path=active_section,
                coordinates={"html_tag": tag},
            )
        )
    if not blocks and content.strip():
        blocks.append(
            CanonicalBlockInput(
                structural_path="block:0",
                block_type="paragraph",
                ordinal=0,
                text_content=" ".join(content.split()),
            )
        )
    return title, tuple(sections), tuple(blocks)


__all__ = ["KnowledgeFabricWebsiteAdapter", "WebsiteResponseInput", "WebsiteResponseRejected"]
