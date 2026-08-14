"""Lightweight Knowledge RAG route gate using the shared semantic embedding runtime."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Literal

from echo_masque.config import Settings, get_settings
from echo_masque.persistence.knowledge_models import KnowledgeBaseRecord
from echo_masque.persistence.knowledge_repository import KnowledgeRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)
from echo_masque.semantic_routing_judge import RagJudgeDecision, SemanticRoutingJudgeService

KnowledgeRouteStatus = Literal[
    "no_eligible_bases",
    "disabled",
    "matched",
    "not_relevant",
    "unavailable",
]
KnowledgeAssessmentRoute = Literal["on", "off", "gray"]

_ROUTE_SPARSE_STRONG = 0.18
_ROUTE_SPARSE_SUPPORT = 0.08
_ROUTE_DENSE_MINIMUM = 0.52
_ROUTE_DENSE_WITH_SPARSE_MINIMUM = 0.44
_ROUTE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "you",
    "your",
}


@dataclass(frozen=True, slots=True)
class KnowledgeRouteAssessment:
    """Deterministic/sparse/E5 Knowledge evidence with no LLM side effect."""

    status: KnowledgeRouteStatus
    route: KnowledgeAssessmentRoute
    fallback_should_retrieve: bool
    eligible_base_count: int
    best_sparse_score: float = 0.0
    best_dense_score: float = 0.0
    matched_knowledge_base_id: str = ""
    route_labels: tuple[str, ...] = ()
    current_message: str = ""
    normalized_query: str = ""
    is_contextual: bool = False

    @property
    def gray_zone(self) -> bool:
        return self.route == "gray"


@dataclass(frozen=True, slots=True)
class KnowledgeRouteDecision:
    status: KnowledgeRouteStatus
    should_retrieve: bool
    eligible_base_count: int
    best_sparse_score: float = 0.0
    best_dense_score: float = 0.0
    matched_knowledge_base_id: str = ""
    judge_used: bool = False
    judge_route: str = ""
    judge_confidence: float = 0.0
    judge_provider_id: str = ""
    judge_model: str = ""
    judge_fallback_used: bool = False
    judge_escalated: bool = False
    judge_reason_code: str = ""


class KnowledgeRouteGate:
    """Decide whether one scoped character turn should enter Knowledge retrieval."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        settings: Settings | None = None,
        encoder: SemanticEncoder | None = None,
        encoder_factory: Callable[[], SemanticEncoder] | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()
        self._encoder = encoder
        self._encoder_factory = encoder_factory
        self._encoder_lock = Lock()
        self._semantic_enabled = self.settings.knowledge_semantic_retrieval_enabled
        self._routing_judge = SemanticRoutingJudgeService(
            repository.database,
            settings=self.settings,
        )
        self._route_vector_cache: dict[tuple[str, int, str], list[float]] = {}

    @staticmethod
    def _tokenize(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[\w\u3400-\u9fff]+", value.casefold(), flags=re.UNICODE)
            if token and token not in _ROUTE_STOP_WORDS
        }

    @classmethod
    def _sparse_score(
        cls,
        base: KnowledgeBaseRecord,
        route_text: str,
        query: str,
    ) -> float:
        query_tokens = cls._tokenize(query)
        if not query_tokens:
            return 0.0
        route_tokens = cls._tokenize(route_text)
        overlap = len(query_tokens & route_tokens) / max(1, len(query_tokens))
        query_folded = query.casefold()
        phrases = [base.name, base.description]
        phrase_bonus = 0.0
        for phrase in phrases:
            compact = " ".join(phrase.split()).casefold()
            if compact and len(compact) >= 3 and compact in query_folded:
                phrase_bonus += 0.35
        return min(1.0, overlap + min(0.7, phrase_bonus))

    @staticmethod
    def _route_text(base: KnowledgeBaseRecord) -> str:
        description = " ".join(base.description.split())[:1200]
        return "\n".join(
            part
            for part in (
                f"Knowledge Base: {base.name}",
                f"Description: {description}" if description else "",
            )
            if part
        )

    def _get_encoder(self) -> SemanticEncoder:
        if self._encoder is not None:
            return self._encoder
        with self._encoder_lock:
            if self._encoder is not None:
                return self._encoder
            if self._encoder_factory is not None:
                self._encoder = self._encoder_factory()
            else:
                self._encoder = FastEmbedSemanticEncoder(
                    model_name=self.settings.semantic_embedding_model,
                    model_file=self.settings.semantic_embedding_model_file,
                    cache_dir=self.settings.semantic_embedding_cache_dir,
                    dimension=self.settings.semantic_embedding_dimension,
                )
            return self._encoder

    def _route_vector(
        self,
        *,
        base: KnowledgeBaseRecord,
        route_text: str,
        encoder: SemanticEncoder,
    ) -> list[float]:
        source_hash = hashlib.sha256(route_text.encode("utf-8")).hexdigest()
        key = (encoder.model_name, encoder.dimension, source_hash)
        cached = self._route_vector_cache.get(key)
        if cached is not None:
            return cached
        vector = encoder.embed_passage(route_text)
        self._route_vector_cache[key] = vector
        if len(self._route_vector_cache) > 512:
            first_key = next(iter(self._route_vector_cache))
            self._route_vector_cache.pop(first_key, None)
        return vector

    @staticmethod
    def _judge_values(judge: RagJudgeDecision | None) -> dict[str, object]:
        if judge is None:
            return {}
        return {
            "judge_used": True,
            "judge_route": judge.route,
            "judge_confidence": judge.confidence,
            "judge_provider_id": judge.provider_id,
            "judge_model": judge.model,
            "judge_fallback_used": judge.fallback_used,
            "judge_escalated": judge.escalated,
            "judge_reason_code": judge.reason_code,
        }

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
        bases = self.repository.list_eligible_bases(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
        )
        return [item for item in bases if item.enabled]

    def assess(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        thread_id: str,
        character_card_id: str,
        query: str,
    ) -> KnowledgeRouteAssessment:
        """Return route evidence without invoking any model Judge."""

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
            return KnowledgeRouteAssessment(
                "disabled",
                "on",
                True,
                len(eligible),
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )
        if not eligible:
            return KnowledgeRouteAssessment(
                "no_eligible_bases",
                "off",
                False,
                0,
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )
        if not normalized:
            return KnowledgeRouteAssessment(
                "not_relevant",
                "off",
                False,
                len(eligible),
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )

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
            return KnowledgeRouteAssessment(
                "matched",
                "on",
                True,
                len(eligible),
                best_sparse_score=round(best_sparse, 6),
                matched_knowledge_base_id=sparse_base.id,
                route_labels=route_labels,
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=False,
            )

        routing = self._routing_judge.runtime.semantic_routing_config()
        try:
            encoder = self._get_encoder()
            query_vector = encoder.embed_query(normalized)
            dense_scores: list[tuple[float, KnowledgeBaseRecord]] = []
            for base, route_text in routes:
                vector = self._route_vector(
                    base=base,
                    route_text=route_text,
                    encoder=encoder,
                )
                dense_scores.append((_cosine(query_vector, vector), base))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            fallback = (
                False
                if routing.enabled and routing.rag_enabled and is_contextual
                else best_sparse >= _ROUTE_SPARSE_STRONG
                if routing.enabled and routing.rag_enabled
                else True
            )
            return KnowledgeRouteAssessment(
                "unavailable",
                "on" if fallback else "off",
                fallback,
                len(eligible),
                best_sparse_score=round(best_sparse, 6),
                matched_knowledge_base_id=sparse_base.id if fallback else "",
                route_labels=route_labels,
                current_message=current_message,
                normalized_query=normalized,
                is_contextual=is_contextual,
            )

        best_dense, dense_base = max(dense_scores, key=lambda item: item[0])
        legacy_matched = best_dense >= _ROUTE_DENSE_MINIMUM or (
            best_dense >= _ROUTE_DENSE_WITH_SPARSE_MINIMUM
            and best_sparse >= _ROUTE_SPARSE_SUPPORT
        )
        common = dict(
            eligible_base_count=len(eligible),
            best_sparse_score=round(best_sparse, 6),
            best_dense_score=round(best_dense, 6),
            matched_knowledge_base_id=dense_base.id,
            route_labels=route_labels,
            current_message=current_message,
            normalized_query=normalized,
            is_contextual=is_contextual,
        )
        if not routing.enabled or not routing.rag_enabled:
            return KnowledgeRouteAssessment(
                "matched" if legacy_matched else "not_relevant",
                "on" if legacy_matched else "off",
                legacy_matched,
                **common,
            )
        if is_contextual:
            return KnowledgeRouteAssessment(
                "not_relevant",
                "gray",
                False,
                **common,
            )
        if best_dense >= routing.rag_on_threshold:
            return KnowledgeRouteAssessment(
                "matched",
                "on",
                True,
                **common,
            )
        if best_dense <= routing.rag_off_threshold and best_sparse < _ROUTE_SPARSE_SUPPORT:
            return KnowledgeRouteAssessment(
                "not_relevant",
                "off",
                False,
                **common,
            )
        return KnowledgeRouteAssessment(
            "matched" if legacy_matched else "not_relevant",
            "gray",
            legacy_matched,
            **common,
        )

    @staticmethod
    def decision_from_assessment(
        assessment: KnowledgeRouteAssessment,
        *,
        should_retrieve: bool | None = None,
        judge: RagJudgeDecision | None = None,
    ) -> KnowledgeRouteDecision:
        """Convert precomputed evidence into a trace-compatible route decision."""

        retrieve = (
            assessment.route == "on"
            if should_retrieve is None
            else bool(should_retrieve)
        )
        status: KnowledgeRouteStatus
        if assessment.status in {"disabled", "no_eligible_bases", "unavailable"}:
            status = assessment.status
        else:
            status = "matched" if retrieve else "not_relevant"
        return KnowledgeRouteDecision(
            status,
            retrieve,
            assessment.eligible_base_count,
            best_sparse_score=assessment.best_sparse_score,
            best_dense_score=assessment.best_dense_score,
            matched_knowledge_base_id=(
                assessment.matched_knowledge_base_id if retrieve else ""
            ),
            **KnowledgeRouteGate._judge_values(judge),
        )

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
        assessment = self.assess(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            thread_id=thread_id,
            character_card_id=character_card_id,
            query=query,
        )
        if not assessment.gray_zone:
            return self.decision_from_assessment(assessment)

        judge = self._routing_judge.decide(
            current_message=assessment.current_message,
            contextual_query=assessment.normalized_query,
            route_labels=assessment.route_labels,
            dense_score=assessment.best_dense_score,
            sparse_score=assessment.best_sparse_score,
        )
        matched = (
            judge.need_knowledge
            if judge is not None
            else assessment.fallback_should_retrieve
        )
        return self.decision_from_assessment(
            assessment,
            should_retrieve=matched,
            judge=judge,
        )


__all__ = [
    "KnowledgeAssessmentRoute",
    "KnowledgeRouteAssessment",
    "KnowledgeRouteDecision",
    "KnowledgeRouteGate",
    "KnowledgeRouteStatus",
]