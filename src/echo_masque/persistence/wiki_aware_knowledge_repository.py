"""Conservative Wiki-aware wrapper around the raw Knowledge repository."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from echo_masque.knowledge_retrieval import KnowledgeCandidate, KnowledgeResource
from echo_masque.knowledge_wiki import KnowledgeWikiService
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_repository import (
    KnowledgeRepository as BaseKnowledgeRepository,
)
from echo_masque.persistence.knowledge_repository import KnowledgeRetrievalResult
from echo_masque.semantic_participation import SemanticEncoder

if TYPE_CHECKING:
    from echo_masque.persistence.wiki_page_models import WikiPageRecord

_OVERVIEW_MARKERS = (
    "overview",
    "summary",
    "summarize",
    "high level",
    "high-level",
    "introduction",
    "introduce",
    "what is",
    "what's",
    "explain",
    "简介",
    "簡介",
    "概述",
    "总结",
    "總結",
    "介绍",
    "介紹",
    "讲解",
    "講解",
    "说明",
    "說明",
    "懒人包",
    "懶人包",
    "大概",
    "整体",
    "整體",
    "ringkasan",
    "gambaran keseluruhan",
    "terangkan",
    "penerangan",
)
_DETAIL_MARKERS = (
    "exact",
    "verbatim",
    "quote",
    "citation",
    "cite",
    "source",
    "evidence",
    "which document",
    "which file",
    "原文",
    "出处",
    "出處",
    "引用",
    "证据",
    "證據",
    "來源",
    "来源",
    "哪一份",
    "哪個文件",
    "哪个文件",
    "sumber",
    "bukti",
    "petikan",
    "tepat",
)
_MAX_WIKI_BODY_CHARS = 2_200
_MAX_PROVENANCE_ITEMS = 6


class WikiAwareKnowledgeRepository(BaseKnowledgeRepository):
    """Use a current derived overview only for explicit broad-summary queries.

    Raw Knowledge remains the authoritative fallback. Missing, stale, unavailable, or
    non-overview Wiki paths return the unmodified raw retrieval result.
    """

    def __init__(
        self,
        database: Database,
        *,
        semantic_encoder: SemanticEncoder | None = None,
        semantic_enabled: bool | None = None,
    ) -> None:
        super().__init__(
            database,
            semantic_encoder=semantic_encoder,
            semantic_enabled=semantic_enabled,
        )
        self._wiki_service_override: KnowledgeWikiService | None = None
        self._wiki_service_live: KnowledgeWikiService | None = None

    def set_wiki_service(self, service: KnowledgeWikiService | None) -> None:
        """Inject a deterministic service in tests or specialized runtimes."""

        self._wiki_service_override = service

    @staticmethod
    def _overview_intent(query: str) -> bool:
        normalized = " ".join(query.casefold().split())
        if any(marker in normalized for marker in _DETAIL_MARKERS):
            return False
        return any(marker in normalized for marker in _OVERVIEW_MARKERS)

    def _wiki_service(self) -> KnowledgeWikiService:
        if self._wiki_service_override is not None:
            return self._wiki_service_override
        if self._wiki_service_live is None:
            # Lazy imports avoid persistence-package import cycles. The live service shares
            # the same SQLite config/vault state but never becomes a new authority layer.
            from echo_masque.persistence.repository import Repository
            from echo_masque.services.runtime import RuntimeService
            from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
            from echo_masque.utility_gateway_router import UtilityGatewayRouter

            runtime = RuntimeService(Repository(self.database), self._settings)
            gateway = UtilityGatewayRouter(
                runtime,
                caller=ExistingProviderUtilityCaller(),
            )
            self._wiki_service_live = KnowledgeWikiService(self, gateway=gateway)
        return self._wiki_service_live

    @staticmethod
    def _manifest(record: WikiPageRecord) -> list[dict[str, object]]:
        try:
            value = json.loads(record.source_manifest_json)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @classmethod
    def _wiki_candidate(
        cls,
        *,
        page: WikiPageRecord,
        knowledge_base_name: str,
    ) -> KnowledgeCandidate:
        manifest = cls._manifest(page)
        provenance_lines: list[str] = []
        for item in manifest[:_MAX_PROVENANCE_ITEMS]:
            title = str(item.get("title") or "Untitled source")[:160]
            document_id = str(item.get("document_id") or "")[:80]
            content_hash = str(item.get("content_sha256") or "")[:16]
            provenance_lines.append(
                f"- {title} [document_id={document_id}; sha256={content_hash}…]"
            )
        if len(manifest) > _MAX_PROVENANCE_ITEMS:
            provenance_lines.append(
                f"- … plus {len(manifest) - _MAX_PROVENANCE_ITEMS} source(s) in this snapshot"
            )
        provenance = "\n".join(provenance_lines) or "- Source manifest unavailable"
        body = page.body.strip()[:_MAX_WIKI_BODY_CHARS]
        content = (
            "Derived Knowledge Wiki overview. Use this compact page for broad orientation only; "
            "raw Knowledge remains authoritative for exact details and evidence.\n"
            f"Source snapshot sha256: {page.source_hash}\n\n"
            f"{body}\n\n"
            "Provenance:\n"
            f"{provenance}"
        )
        return KnowledgeCandidate(
            resource=KnowledgeResource(
                chunk_id=f"wiki:{page.id}",
                knowledge_base_id=page.knowledge_base_id,
                document_id="wiki:overview",
                document_title=f"Wiki · {knowledge_base_name}"[:240],
                chunk_index=0,
                content=content,
            ),
            score=1.0,
            signals={"wiki": 1.0, "derived": 1.0},
        )

    def _overview_page(
        self,
        *,
        owner_id: str,
        knowledge_base_id: str,
    ) -> WikiPageRecord | None:
        service = self._wiki_service()
        current = service.current_overview(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
        )
        if current is not None:
            return current
        refreshed = service.refresh_overview(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
        )
        return refreshed.page

    def retrieve_for_turn(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        query: str,
        top_k: int = 4,
    ) -> KnowledgeRetrievalResult:
        raw = super().retrieve_for_turn(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
            query=query,
            top_k=top_k,
        )
        if not raw.candidates or not self._overview_intent(query):
            return raw

        base_ids = {item.resource.knowledge_base_id for item in raw.candidates}
        if len(base_ids) != 1:
            return raw
        knowledge_base_id = next(iter(base_ids))
        base = self.get_base(knowledge_base_id, owner_id)
        if base is None:
            return raw
        try:
            page = self._overview_page(
                owner_id=owner_id,
                knowledge_base_id=knowledge_base_id,
            )
        except Exception:
            # Wiki is a derived optimization only. Raw RAG must remain available under every
            # persistence/provider/protocol failure mode.
            return raw
        if page is None or page.stale:
            return raw
        return KnowledgeRetrievalResult(
            eligible_base_count=raw.eligible_base_count,
            candidate_chunk_count=raw.candidate_chunk_count,
            candidates=(
                self._wiki_candidate(page=page, knowledge_base_name=base.name),
            ),
        )


__all__ = ["WikiAwareKnowledgeRepository"]
