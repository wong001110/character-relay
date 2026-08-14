"""Derived Knowledge Wiki consolidation on top of raw RAG sources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Protocol

from echo_masque.persistence.knowledge_models import (
    KnowledgeBaseRecord,
    KnowledgeDocumentRecord,
)
from echo_masque.persistence.knowledge_repository import KnowledgeRepository
from echo_masque.persistence.wiki_page_models import WikiPageRecord
from echo_masque.persistence.wiki_page_repository import WikiPageRepository
from echo_masque.utility_gateway_contracts import (
    UtilityGatewayUnavailable,
    UtilityInferenceResult,
    WikiUtilityResult,
)

_OVERVIEW_PAGE_KEY = "overview"
_DEFAULT_SOURCE_BUDGET = 12_000


class KnowledgeWikiGateway(Protocol):
    def wiki_page(
        self,
        *,
        prompt: str,
    ) -> tuple[WikiUtilityResult, UtilityInferenceResult]: ...


@dataclass(frozen=True, slots=True)
class WikiSourceSnapshot:
    knowledge_base_id: str
    source_hash: str
    source_manifest: tuple[dict[str, str], ...]
    prompt: str
    document_count: int


WikiRefreshStatus = Literal[
    "reused",
    "created",
    "updated",
    "no_sources",
    "gateway_unavailable",
]


@dataclass(frozen=True, slots=True)
class WikiRefreshResult:
    status: WikiRefreshStatus
    page: WikiPageRecord | None
    source_hash: str
    provider: str = ""
    model: str = ""
    tier: str = ""


class KnowledgeWikiService:
    """Build compact derived pages while raw Knowledge remains authoritative."""

    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        *,
        page_repository: WikiPageRepository | None = None,
        gateway: KnowledgeWikiGateway | None = None,
        source_budget_chars: int = _DEFAULT_SOURCE_BUDGET,
    ) -> None:
        self.knowledge_repository = knowledge_repository
        self.page_repository = page_repository or WikiPageRepository(
            knowledge_repository.database
        )
        self.gateway = gateway
        self.source_budget_chars = max(2_000, min(source_budget_chars, 12_000))

    @staticmethod
    def _manifest_item(document: KnowledgeDocumentRecord) -> dict[str, str]:
        return {
            "document_id": document.id,
            "title": document.title,
            "source_type": document.source_type,
            "content_sha256": document.content_sha256,
        }

    @staticmethod
    def _source_hash(
        base: KnowledgeBaseRecord,
        manifest: tuple[dict[str, str], ...],
    ) -> str:
        payload = {
            "knowledge_base_id": base.id,
            "name": base.name,
            "description": base.description,
            "documents": manifest,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _source_prompt(
        self,
        base: KnowledgeBaseRecord,
        documents: list[KnowledgeDocumentRecord],
    ) -> str:
        prefix = (
            f"Knowledge Base: {base.name}\n"
            f"Description: {base.description or '(none)'}\n"
            "Task: create one compact overview page. Preserve factual qualifiers, "
            "important names/dates, and explicit disagreements. Do not invent facts.\n\n"
            "Sources:\n"
        )
        remaining = max(0, self.source_budget_chars - len(prefix))
        if not documents or remaining <= 0:
            return prefix[: self.source_budget_chars]

        per_document = max(500, remaining // len(documents))
        sections: list[str] = []
        used = len(prefix)
        for document in documents:
            header = (
                f"\n--- SOURCE {document.id} | {document.title} "
                f"| sha256={document.content_sha256} ---\n"
            )
            available = min(
                per_document,
                max(0, self.source_budget_chars - used - len(header)),
            )
            if available <= 0:
                break
            excerpt = document.content[:available]
            sections.append(f"{header}{excerpt}")
            used += len(header) + len(excerpt)
        return (prefix + "".join(sections))[: self.source_budget_chars]

    def snapshot(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
    ) -> WikiSourceSnapshot:
        base = self.knowledge_repository.get_base(knowledge_base_id, owner_id)
        if base is None:
            raise KeyError("knowledge_base")
        documents = self.knowledge_repository.list_documents(knowledge_base_id, owner_id)
        documents.sort(key=lambda item: (item.id, item.title.casefold()))
        manifest = tuple(self._manifest_item(item) for item in documents)
        return WikiSourceSnapshot(
            knowledge_base_id=knowledge_base_id,
            source_hash=self._source_hash(base, manifest),
            source_manifest=manifest,
            prompt=self._source_prompt(base, documents),
            document_count=len(documents),
        )

    def current_overview(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
    ) -> WikiPageRecord | None:
        page = self.page_repository.get_page(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            page_key=_OVERVIEW_PAGE_KEY,
        )
        if page is None or page.stale:
            return None
        snapshot = self.snapshot(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
        )
        if snapshot.document_count == 0 or page.source_hash != snapshot.source_hash:
            self.page_repository.mark_base_stale(
                owner_id=owner_id,
                knowledge_base_id=knowledge_base_id,
            )
            return None
        return page

    def refresh_overview(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
    ) -> WikiRefreshResult:
        snapshot = self.snapshot(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
        )
        existing = self.page_repository.get_page(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            page_key=_OVERVIEW_PAGE_KEY,
        )
        if (
            existing is not None
            and not existing.stale
            and existing.source_hash == snapshot.source_hash
        ):
            return WikiRefreshResult(
                status="reused",
                page=existing,
                source_hash=snapshot.source_hash,
            )

        if existing is not None and (
            existing.source_hash != snapshot.source_hash or not snapshot.document_count
        ):
            self.page_repository.mark_base_stale(
                owner_id=owner_id,
                knowledge_base_id=knowledge_base_id,
            )

        if snapshot.document_count == 0:
            return WikiRefreshResult(
                status="no_sources",
                page=None,
                source_hash=snapshot.source_hash,
            )
        if self.gateway is None:
            return WikiRefreshResult(
                status="gateway_unavailable",
                page=None,
                source_hash=snapshot.source_hash,
            )

        try:
            draft, inference = self.gateway.wiki_page(prompt=snapshot.prompt)
        except UtilityGatewayUnavailable:
            return WikiRefreshResult(
                status="gateway_unavailable",
                page=None,
                source_hash=snapshot.source_hash,
            )

        page = self.page_repository.upsert_page(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            page_key=_OVERVIEW_PAGE_KEY,
            title=draft.title,
            body=draft.body,
            keywords=draft.keywords,
            source_manifest=snapshot.source_manifest,
            source_hash=snapshot.source_hash,
            confidence=draft.confidence,
        )
        return WikiRefreshResult(
            status="created" if existing is None else "updated",
            page=page,
            source_hash=snapshot.source_hash,
            provider=inference.route.provider,
            model=inference.route.model,
            tier=inference.route.tier,
        )


__all__ = [
    "KnowledgeWikiGateway",
    "KnowledgeWikiService",
    "WikiRefreshResult",
    "WikiRefreshStatus",
    "WikiSourceSnapshot",
]
