"""Deterministic, DTD-free Atom 1.0 snapshot compiler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import cast
from urllib.parse import urlsplit

from defusedxml import ElementTree  # type: ignore[import-untyped]

from echo_masque.knowledge_fabric_external_policy import canonical_public_https_locator
from echo_masque.knowledge_fabric_ingestion import SourceSnapshotIngestionRequest
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_MAX_ENTRY_COUNT = 200
_MAX_TEXT = 20_000


class AtomResponseRejected(ValueError):
    """An Atom payload is invalid, unsafe, or exceeds the structural contract."""


@dataclass(frozen=True, slots=True)
class AtomResponseInput:
    source_id: str
    locator: str
    content: bytes
    content_type: str
    fetched_at: datetime


class KnowledgeFabricAtomAdapter:
    """Preserve bounded Atom entry evidence without following feed links or HTML resources."""

    def build_snapshot(self, value: AtomResponseInput) -> SourceSnapshotIngestionRequest:
        locator = canonical_public_https_locator(value.locator)
        if b"<!DOCTYPE" in value.content.upper() or b"<!ENTITY" in value.content.upper():
            raise AtomResponseRejected("Atom payload may not declare DTD or entities.")
        try:
            root = ElementTree.fromstring(value.content)
        except (ElementTree.ParseError, ValueError) as exc:
            raise AtomResponseRejected("Atom payload is not valid XML.") from exc
        if root.tag != f"{_ATOM}feed":
            raise AtomResponseRejected("Atom payload must be an Atom 1.0 feed.")
        feed_title = _text(root.find(f"{_ATOM}title")) or (
            urlsplit(locator).hostname or "Atom feed"
        )
        documents: list[CanonicalDocumentInput] = []
        seen_entry_ids: set[str] = set()
        for ordinal, entry in enumerate(root.findall(f"{_ATOM}entry")):
            if ordinal >= _MAX_ENTRY_COUNT:
                raise AtomResponseRejected("Atom payload has too many entries.")
            entry_id = _text(entry.find(f"{_ATOM}id"))
            if not entry_id:
                raise AtomResponseRejected("Atom entry id is required.")
            if entry_id in seen_entry_ids:
                raise AtomResponseRejected("Atom entry id must be unique within a feed.")
            seen_entry_ids.add(entry_id)
            title = _text(entry.find(f"{_ATOM}title")) or feed_title
            content = _text(entry.find(f"{_ATOM}content")) or _text(entry.find(f"{_ATOM}summary"))
            if not content:
                continue
            link = _safe_link(entry)
            coordinates: dict[str, object] = {"feed_locator": locator, "entry_id": entry_id}
            if link is not None:
                coordinates["entry_link"] = link
            entry_hash = sha256(entry_id.encode("utf-8")).hexdigest()
            documents.append(
                CanonicalDocumentInput(
                    canonical_locator=f"atom:{locator}#{entry_hash}",
                    title=title,
                    mime_type="application/atom+xml",
                    metadata={"adapter": "atom_public_https", **coordinates},
                    blocks=(
                        CanonicalBlockInput(
                            structural_path="entry:0",
                            block_type="atom_entry",
                            ordinal=0,
                            text_content=content,
                            coordinates=coordinates,
                        ),
                    ),
                )
            )
        if not documents:
            raise AtomResponseRejected("Atom payload contains no usable entries.")
        content_type = value.content_type.casefold().split(";", maxsplit=1)[0].strip()
        digest = sha256(value.content).hexdigest()
        return SourceSnapshotIngestionRequest(
            source_id=value.source_id,
            version_key=f"atom:{digest}",
            idempotency_key=(
                f"atom:{sha256((value.source_id + chr(0)).encode() + value.content).hexdigest()}"
            ),
            artifact_content=value.content,
            artifact_content_type=content_type,
            documents=tuple(documents),
            published_at=value.fetched_at,
            metadata={"adapter": "atom_public_https", "feed_title": feed_title},
        )


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())[:_MAX_TEXT]


def _safe_link(entry: ElementTree.Element) -> str | None:
    for link in entry.findall(f"{_ATOM}link"):
        href = link.get("href", "")
        parsed = urlsplit(href)
        if (
            href
            and len(href) <= 1000
            and parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            return cast(str, href)
    return None


__all__ = ["AtomResponseInput", "AtomResponseRejected", "KnowledgeFabricAtomAdapter"]
