"""Compile a bounded collection of already-fetched public pages into one source snapshot."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from urllib.parse import urlsplit

from echo_masque.knowledge_fabric_external_policy import canonical_public_https_locator
from echo_masque.knowledge_fabric_ingestion import SourceSnapshotIngestionRequest
from echo_masque.knowledge_fabric_website_adapter import _html_structure
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
)

MAX_COLLECTION_ARTIFACT_BYTES = 5 * 1_048_576


class WebsiteCollectionResponseRejected(ValueError):
    """A fetched public page cannot join the bounded collection snapshot."""


@dataclass(frozen=True, slots=True)
class WebsiteCollectionPageInput:
    locator: str
    content: bytes
    content_type: str
    acquisition_kind: str = "pinned_https"


@dataclass(frozen=True, slots=True)
class WebsiteCollectionResponseInput:
    source_id: str
    root_locator: str
    pages: tuple[WebsiteCollectionPageInput, ...]
    fetched_at: datetime


class KnowledgeFabricWebsiteCollectionAdapter:
    """Store approved page bytes privately with one current evidence unit per page."""

    def build_snapshot(
        self, value: WebsiteCollectionResponseInput
    ) -> SourceSnapshotIngestionRequest:
        root = canonical_public_https_locator(value.root_locator)
        if not value.source_id.strip():
            raise WebsiteCollectionResponseRejected(
                "Website collection source identity is required."
            )
        if not value.pages:
            raise WebsiteCollectionResponseRejected("Website collection contains no pages.")
        pages = tuple(
            sorted(
                ((canonical_public_https_locator(item.locator), item) for item in value.pages),
                key=lambda item: item[0],
            )
        )
        if root not in {locator for locator, _item in pages}:
            raise WebsiteCollectionResponseRejected("Website collection root page is required.")
        root_host = urlsplit(root).hostname
        if root_host is None or any(
            urlsplit(locator).hostname != root_host for locator, _item in pages
        ):
            raise WebsiteCollectionResponseRejected("Website collection pages must be same-origin.")
        if len(pages) != len({locator for locator, _item in pages}):
            raise WebsiteCollectionResponseRejected(
                "Website collection page locators must be unique."
            )
        documents: list[CanonicalDocumentInput] = []
        artifact_pages: list[dict[str, str]] = []
        total_bytes = 0
        for locator, page in pages:
            content_type = page.content_type.casefold().split(";", maxsplit=1)[0].strip()
            if content_type not in {"text/html", "text/markdown", "text/plain"}:
                raise WebsiteCollectionResponseRejected(
                    "Website collection page type is unsupported."
                )
            total_bytes += len(page.content)
            if total_bytes > MAX_COLLECTION_ARTIFACT_BYTES:
                raise WebsiteCollectionResponseRejected("Website collection snapshot is too large.")
            try:
                decoded = page.content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise WebsiteCollectionResponseRejected(
                    "Website collection page is not UTF-8 text."
                ) from exc
            if content_type == "text/html":
                title, sections, blocks = _html_structure(decoded)
                text = "\n".join(
                    [section.heading for section in sections]
                    + [block.text_content for block in blocks]
                )
            else:
                title, text = locator, decoded
            text = " ".join(text.split())
            if not text:
                raise WebsiteCollectionResponseRejected(
                    "Website collection page has no usable text."
                )
            documents.append(
                CanonicalDocumentInput(
                    canonical_locator=locator,
                    title=title,
                    mime_type=content_type,
                    metadata={
                        "adapter": "website_collection_public_https",
                        "acquisition": page.acquisition_kind,
                        "locator": locator,
                    },
                    blocks=(
                        CanonicalBlockInput(
                            structural_path="page:0",
                            block_type="website_collection_page",
                            ordinal=0,
                            text_content=text,
                            coordinates={"locator": locator},
                        ),
                    ),
                )
            )
            artifact_pages.append(
                {
                    "content_base64": base64.b64encode(page.content).decode("ascii"),
                    "content_type": content_type,
                    "locator": locator,
                }
            )
        artifact = json.dumps(
            {"pages": artifact_pages, "root_locator": root},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = sha256(artifact).hexdigest()
        idempotency_digest = sha256((value.source_id + chr(0)).encode() + artifact).hexdigest()
        return SourceSnapshotIngestionRequest(
            source_id=value.source_id,
            version_key=f"website_collection:{digest}",
            idempotency_key=f"website_collection:{idempotency_digest}",
            artifact_content=artifact,
            artifact_content_type="application/json",
            documents=tuple(documents),
            published_at=value.fetched_at,
            metadata={
                "adapter": "website_collection_public_https",
                "page_count": len(documents),
                "root_locator": root,
            },
        )

    def build_page_snapshot(
        self,
        *,
        source_id: str,
        page: WebsiteCollectionPageInput,
        fetched_at: datetime,
    ) -> SourceSnapshotIngestionRequest:
        """Compile one changed page for delta current-entry publication."""

        snapshot = self.build_snapshot(
            WebsiteCollectionResponseInput(
                source_id=source_id,
                root_locator=page.locator,
                pages=(page,),
                fetched_at=fetched_at,
            )
        )
        return replace(snapshot, current_entry_mode="delta")

    def build_removal_snapshot(
        self,
        *,
        source_id: str,
        root_locator: str,
        removed_entry_locators: tuple[str, ...],
        fetched_at: datetime,
    ) -> SourceSnapshotIngestionRequest:
        """Publish explicit current-entry removals without discarding historical Evidence."""

        root = canonical_public_https_locator(root_locator)
        removed = tuple(
            sorted(canonical_public_https_locator(item) for item in removed_entry_locators)
        )
        artifact = json.dumps(
            {"removed_entry_locators": removed, "root_locator": root},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = sha256(artifact).hexdigest()
        idempotency_digest = sha256((source_id + chr(0)).encode() + artifact).hexdigest()
        return SourceSnapshotIngestionRequest(
            source_id=source_id,
            version_key=f"website_collection_removal:{digest}",
            idempotency_key=f"website_collection_removal:{idempotency_digest}",
            artifact_content=artifact,
            artifact_content_type="application/json",
            published_at=fetched_at,
            metadata={"adapter": "website_collection_public_https", "root_locator": root},
            current_entry_mode="delta",
            removed_entry_locators=removed,
        )


__all__ = [
    "MAX_COLLECTION_ARTIFACT_BYTES",
    "KnowledgeFabricWebsiteCollectionAdapter",
    "WebsiteCollectionPageInput",
    "WebsiteCollectionResponseInput",
    "WebsiteCollectionResponseRejected",
]
