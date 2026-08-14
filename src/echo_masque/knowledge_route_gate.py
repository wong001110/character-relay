"""Cheap semantic relevance gate before full Knowledge chunk retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from echo_masque.config import Settings, get_settings
from echo_masque.knowledge_retrieval import KnowledgeResource, score_sparse_knowledge_resources
from echo_masque.persistence import Repository
from echo_masque.persistence.knowledge_models import KnowledgeBaseRecord, KnowledgeChunkRecord
from echo_masque.persistence.knowledge_repository import KnowledgeRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)
from echo_masque.semantic_routing_judge import RagJudgeDecision, SemanticRoutingJudgeService

_ROUTE_VECTOR_NAMESPACE = "knowledge-base-route"
_ROUTE_SPARSE_STRONG = 0.08
_ROUTE_SPARSE_SUPPORT = 0.025
_ROUTE_DENSE_MINIMUM = 0.50
_ROUTE_DENSE_WITH_SPARSE_MINIMUM = 0.44
_ROUTE_SAMPLE_SCAN_LIMIT = 40
_ROUTE_SAMPLE_DOCUMENTS = 8
_ROUTE_TEXT_LIMIT = 10_000

KnowledgeRouteStatus = Literal[
    "no_eligible_bases",
    "disabled",
    "matched",
    "not_relevant",
    "unavailable",
]


@dataclass(frozen=True, slots=True)
class KnowledgeRouteDecision:
    status: KnowledgeRouteStatus
    should_retrieve: bool
    eligible_base_count: int
    best_sparse_score: float = 0.0
    best_dense_score: float = 0.0
    matched_knowledge_base_id: str = ""
    judge_model: str = ""
    judge_tier: str = ""
    judge_confidence: float = 0.0
    judge_reason: str = ""
    judge_attempts: int = 0
    judge_latency_ms: int = 0

    @property
    def best_score(self) -> float:
        return max(self.best_sparse_score, self.best_dense_score)


class KnowledgeRouteGate:
    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        *,
        settings: Settings | None = None,
        encoder: SemanticEncoder | None = None,
        semantic_enabled: bool | None = None,
    ) -> None:
        self.knowledge_repository = knowledge_repository
        self.database = knowledge_repository.database
        self.settings = settings or get_settings()
        self._encoder = encoder
        self._semantic_enabled = (
            semantic_enabled
            if semantic_enabled is not None
            else (
                self.settings.semantic_embedding_runtime_enabled
                and self.settings.knowledge_semantic_retrieval_enabled
            )
        )
        self._vectors = SemanticVectorRepository(self.database)
        self._routing_judge = SemanticRoutingJudgeService(
            Repository(self.database), self.settings
        )

    def _get_encoder(self) -> SemanticEncoder:
        if self._encoder is None:
            self._encoder = FastEmbedSemanticEncoder(
                model_name=self.settings.semantic_embedding_model,
                model_file=self.settings.semantic_embedding_model_file,
                cache_dir=self.settings.semantic_embedding_cache_dir,
                dimension=self.settings.semantic_embedding_dimension,
            )
        return self._encoder

    def _eligible_bases(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
    ) -> list[KnowledgeBaseRecord]:
        return [
            item
            for item in self.knowledge_repository.list_bases(owner_id)
            if self.knowledge_repository._base_matches_turn(
                item,
                connection_id=connection_id,
                guild_id=guild_id,
                channel_id=channel_id,
                thread_id=thread_id,
                character_card_id=character_card_id,
            )
        ]

    def _route_text(self, base: KnowledgeBaseRecord) -> str:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(KnowledgeChunkRecord)
                    .where(
                        KnowledgeChunkRecord.owner_id == base.owner_id,
                        KnowledgeChunkRecord.knowledge_base_id == base.id,
                    )
                    .order_by(
                        KnowledgeChunkRecord.document_id,
                        KnowledgeChunkRecord.chunk_index,
                    )
                    .limit(_ROUTE_SAMPLE_SCAN_LIMIT)
                )
            )
        samples: list[KnowledgeChunkRecord] = []
        seen_documents: set[str] = set()
        for record in records:
            if record.document_id in seen_documents:
                continue
            samples.append(record)
            seen_documents.add(record.document_id)
            if len(samples) >= _ROUTE_SAMPLE_DOCUMENTS:
                break
        lines = [f"Knowledge Base: {base.name}"]
        if base.description.strip():
            lines.append(f"Description: {base.description.strip()}")
        for record in samples:
            lines.append(f"Document: {record.document_title}")
            lines.append(record.content)
        return "\n".join(lines)[:_ROUTE_TEXT_LIMIT]

    @staticmethod
    def _sparse_score(base: KnowledgeBaseRecord, route_text: str, query: str) -> float:
        resource = KnowledgeResource(
            chunk_id=f"route:{base.id}",
            knowledge_base_id=base.id,
            document_id="route",
            document_title=base.name,
            chunk_index=0,
            content=route_text,
        )
        scored = score_sparse_knowledge_resources([resource], query=query)
        return scored[0].score if scored else 0.0

    def _route_vector(
        self,
        *,
        base: KnowledgeBaseRecord,
        route_text: str,
        encoder: SemanticEncoder,
    ) -> list[float]:
        source_hash = self._vectors.source_hash(
            route_text, encoder.model_name, encoder.dimension
        )
        cached = self._vectors.get(
            owner_id=base.owner_id,
            namespace=_ROUTE_VECTOR_NAMESPACE,
            resource_id=base.id,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        vector = encoder.embed_passage(route_text)
        self._vectors.upsert(
            owner_id=base.owner_id,
            namespace=_ROUTE_VECTOR_NAMESPACE,
            resource_id=base.id,
            semantic_text=route_text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            vector=vector,
        )
        return vector

    @staticmethod
    def _judge_values(decision: RagJudgeDecision | None) -> dict[str, object]:
        if decision is None:
            return {}
        return {
            "judge_model": decision.model,
            "judge_tier": decision.tier,
            "judge_confidence": round(decision.confidence, 6),
            "judge_reason": decision.reason[:240],
            "judge_attempts": decision.attempts,
            "judge_latency_ms": decision.latency_ms,
        }

    def decide(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        query: str,
    ) -> KnowledgeRouteDecision:
        raw_lines = [item.strip() for item in query.splitlines() if item.strip()]
        current_message = raw_lines[-1] if raw_lines else " ".join(query.split())
        is_contextual = len(raw_lines) > 1
        normalized = " ".join(query.split())[:4000]
        eligible = self._eligible_bases(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
        )
        if not self._semantic_enabled:
            return KnowledgeRouteDecision("disabled", True, len(eligible))
        if not eligible:
            return KnowledgeRouteDecision("no_eligible_bases", False, 0)
        if not normalized:
            return KnowledgeRouteDecision("not_relevant", False, len(eligible))

        routes = [(base, self._route_text(base)) for base in eligible]
        route_labels = tuple(
            (
                f"{base.name}: {base.description.strip()}"
                if base.description.strip()
                else base.name
            )[:500]
            for base, _ in routes
        )
        sparse_scores = [
            (self._sparse_score(base, route_text, normalized), base)
            for base, route_text in routes
        ]
        best_sparse, sparse_base = max(sparse_scores, key=lambda item: item[0])
        if best_sparse >= _ROUTE_SPARSE_STRONG and not is_contextual:
            return KnowledgeRouteDecision(
                "matched",
                True,
                len(eligible),
                best_sparse_score=round(best_sparse, 6),
                matched_knowledge_base_id=sparse_base.id,
            )

        try:
            encoder = self._get_encoder()
            query_vector = encoder.embed_query(normalized)
            dense_scores: list[tuple[float, KnowledgeBaseRecord]] = []
            for base, route_text in routes:
                vector = self._route_vector(
                    base=base, route_text=route_text, encoder=encoder
                )
                dense_scores.append((_cosine(query_vector, vector), base))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            routing = self._routing_judge.runtime.semantic_routing_config()
            if routing.enabled and routing.rag_enabled:
                retrieve = (
                    False if is_contextual else best_sparse >= _ROUTE_SPARSE_STRONG
                )
            else:
                retrieve = True
            return KnowledgeRouteDecision(
                "unavailable",
                retrieve,
                len(eligible),
                best_sparse_score=round(best_sparse, 6),
            )

        best_dense, dense_base = max(dense_scores, key=lambda item: item[0])
        legacy_matched = best_dense >= _ROUTE_DENSE_MINIMUM or (
            best_dense >= _ROUTE_DENSE_WITH_SPARSE_MINIMUM
            and best_sparse >= _ROUTE_SPARSE_SUPPORT
        )
        routing = self._routing_judge.runtime.semantic_routing_config()
        judge: RagJudgeDecision | None = None
        if routing.enabled and routing.rag_enabled:
            if is_contextual:
                judge = self._routing_judge.decide(
                    current_message=current_message,
                    contextual_query=normalized,
                    route_labels=route_labels,
                    dense_score=best_dense,
                    sparse_score=best_sparse,
                )
                matched = judge.need_knowledge if judge is not None else False
            elif best_dense >= routing.rag_on_threshold:
                matched = True
            elif (
                best_dense <= routing.rag_off_threshold
                and best_sparse < _ROUTE_SPARSE_SUPPORT
            ):
                matched = False
            else:
                judge = self._routing_judge.decide(
                    current_message=current_message,
                    contextual_query=normalized,
                    route_labels=route_labels,
                    dense_score=best_dense,
                    sparse_score=best_sparse,
                )
                matched = (
                    judge.need_knowledge if judge is not None else legacy_matched
                )
        else:
            matched = legacy_matched

        return KnowledgeRouteDecision(
            "matched" if matched else "not_relevant",
            matched,
            len(eligible),
            best_sparse_score=round(best_sparse, 6),
            best_dense_score=round(best_dense, 6),
            matched_knowledge_base_id=dense_base.id if matched else "",
            **self._judge_values(judge),
        )


__all__ = ["KnowledgeRouteDecision", "KnowledgeRouteGate", "KnowledgeRouteStatus"]
