"""Access-filtered multi-channel querying over the Knowledge Fabric evidence index."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from echo_masque.embedding_space import EmbeddingSpace
from echo_masque.knowledge_fabric_query_policy import (
    candidate_may_enter_ranking,
    freshness_status_for_mode,
    query_mode_is_valid,
    stable_reciprocal_rank_fusion,
)
from echo_masque.persistence.knowledge_fabric_index_repository import (
    KnowledgeFabricIndexRepository,
    KnowledgeIndexCandidate,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


class KnowledgeQueryEmbedder(Protocol):
    """Optional dependency for a pre-built dense index; it never sees unauthorized rows."""

    space: EmbeddingSpace

    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class KnowledgeQueryRequest:
    """One bounded internal request; server access is resolved only from its existing scope."""

    server_scope_id: str
    query: str
    mode: str
    candidate_limit: int
    result_limit: int
    as_of: datetime | None = None
    candidate_corpus_ids: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeQueryHit:
    """Source-aligned Evidence returned with channels/provenance, not a synthesized fact."""

    evidence_unit_id: str
    corpus_id: str
    source_version_id: str
    evidence_locator: str
    document_title: str
    text_content: str
    authority_profile: str
    channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeQueryResult:
    """The Phase 5 result leaves Character epistemic and prompt-budget decisions to later phases."""

    mode: str
    accessible_corpus_count: int
    freshness_status: str
    hits: tuple[KnowledgeQueryHit, ...]
    dense_index_status: str = "not_configured"


class KnowledgeQueryEngine:
    """Resolve corpus authorization before invoking sparse, dense, or entity retrieval channels."""

    def __init__(
        self,
        *,
        fabric_repository: KnowledgeFabricRepository,
        index_repository: KnowledgeFabricIndexRepository,
        embedder: KnowledgeQueryEmbedder | None = None,
    ) -> None:
        self.fabric_repository = fabric_repository
        self.index_repository = index_repository
        self.embedder = embedder

    def query(self, request: KnowledgeQueryRequest) -> KnowledgeQueryResult:
        """Return only bounded source evidence from the request scope's effective corpora."""

        self._require_request(request)
        effective = self.fabric_repository.list_effective_corpora(request.server_scope_id)
        authorized_corpus_ids = frozenset(item.corpus.id for item in effective)
        # Callers may only narrow the corpus set.  The server's effective corpus list
        # remains the authority and is resolved before retrieval/ranking.
        if request.candidate_corpus_ids is not None:
            authorized_corpus_ids &= request.candidate_corpus_ids
        freshness_status = freshness_status_for_mode(request.mode)
        if not authorized_corpus_ids:
            return KnowledgeQueryResult(
                mode=request.mode,
                accessible_corpus_count=0,
                freshness_status=freshness_status,
                hits=(),
            )

        channels, dense_status = self._retrieve_channels(
            request,
            authorized_corpus_ids=authorized_corpus_ids,
        )
        by_entry: dict[str, KnowledgeIndexCandidate] = {}
        channel_names: dict[str, list[str]] = {}
        rankings: list[tuple[str, ...]] = []
        for channel, candidates in channels:
            admitted = [
                item
                for item in candidates
                if candidate_may_enter_ranking(
                    corpus_id=item.corpus_id,
                    authorized_corpus_ids=authorized_corpus_ids,
                )
            ]
            rankings.append(tuple(item.retrieval_entry_id for item in admitted))
            for item in admitted:
                by_entry.setdefault(item.retrieval_entry_id, item)
                channel_names.setdefault(item.retrieval_entry_id, []).append(channel)

        # A grant revoked while retrieval was running cannot enter Character context.
        current_corpora = (
            frozenset(
                item.corpus.id
                for item in self.fabric_repository.list_effective_corpora(request.server_scope_id)
            )
            & authorized_corpus_ids
        )
        fused_ids = tuple(
            entry_id
            for entry_id in stable_reciprocal_rank_fusion(tuple(rankings))
            if by_entry[entry_id].corpus_id in current_corpora
        )[: request.result_limit]
        hits = tuple(
            KnowledgeQueryHit(
                evidence_unit_id=by_entry[entry_id].evidence_unit_id,
                corpus_id=by_entry[entry_id].corpus_id,
                source_version_id=by_entry[entry_id].source_version_id,
                evidence_locator=by_entry[entry_id].evidence_locator,
                document_title=by_entry[entry_id].document_title,
                text_content=by_entry[entry_id].text_content,
                authority_profile=by_entry[entry_id].authority_profile,
                channels=tuple(dict.fromkeys(channel_names[entry_id])),
            )
            for entry_id in fused_ids
        )
        return KnowledgeQueryResult(
            mode=request.mode,
            accessible_corpus_count=len(authorized_corpus_ids),
            freshness_status=freshness_status,
            hits=hits,
            dense_index_status=dense_status,
        )

    def _retrieve_channels(
        self,
        request: KnowledgeQueryRequest,
        *,
        authorized_corpus_ids: frozenset[str],
    ) -> tuple[tuple[tuple[str, Sequence[KnowledgeIndexCandidate]], ...], str]:
        sparse = self.index_repository.search_sparse(
            authorized_corpus_ids=authorized_corpus_ids,
            query=request.query,
            candidate_limit=request.candidate_limit,
        )
        if request.mode in {"exact", "code"}:
            return (("sparse", sparse),), "not_requested"

        channels: list[tuple[str, Sequence[KnowledgeIndexCandidate]]] = [("sparse", sparse)]
        dense_status = "not_configured"
        if self.embedder is not None:
            dense_status = self.index_repository.dense_index_status(
                authorized_corpus_ids=authorized_corpus_ids, space=self.embedder.space
            )
            # Sparse first. Never create passage vectors inside a query or download a model.
            if len(sparse) >= request.result_limit:
                dense_status = "not_requested_sparse_sufficient"
            elif dense_status in {"ready", "partial"}:
                try:
                    query_vector = self.embedder.embed_query(request.query)
                    channels.append(
                        (
                            "dense",
                            self.index_repository.search_dense(
                                authorized_corpus_ids=authorized_corpus_ids,
                                space=self.embedder.space,
                                query_vector=query_vector,
                                candidate_limit=request.candidate_limit,
                            ),
                        )
                    )
                except (ValueError, RuntimeError):
                    # No text/exception body in diagnostics; retain permitted sparse results.
                    dense_status = "unavailable"
        if request.mode in {"overview", "relational", "current"}:
            channels.append(
                (
                    "entity",
                    self.index_repository.search_entity_graph(
                        authorized_corpus_ids=authorized_corpus_ids,
                        query=request.query,
                        as_of=request.as_of,
                        candidate_limit=request.candidate_limit,
                    ),
                )
            )
        return tuple(channels), dense_status

    @staticmethod
    def _require_request(request: KnowledgeQueryRequest) -> None:
        if not request.server_scope_id.strip():
            raise ValueError("Knowledge server scope is required.")
        if not request.query.strip():
            raise ValueError("Knowledge query is required.")
        if not query_mode_is_valid(request.mode):
            raise ValueError("Unknown Knowledge query mode.")
        if not 1 <= request.candidate_limit <= 64 or not 1 <= request.result_limit <= 64:
            raise ValueError("Knowledge query limits must be within 1..64.")
        if len(request.query) > 800:
            raise ValueError("Knowledge query must be bounded.")


__all__ = [
    "KnowledgeQueryEmbedder",
    "KnowledgeQueryEngine",
    "KnowledgeQueryHit",
    "KnowledgeQueryRequest",
    "KnowledgeQueryResult",
]
