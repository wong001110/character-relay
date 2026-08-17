"""Runtime-scoped Internal Context Tools for Roleplay model recall."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from echo_masque.config import Settings, get_settings
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.conversation_episode_repository import ConversationEpisodeRepository
from echo_masque.persistence.conversation_topic_models import ConversationTopicRecord
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.core_memory_models import CharacterCoreMemoryRecord
from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository
from echo_masque.persistence.memory_vnext_models import ConversationMemoryVNextRecord
from echo_masque.persistence.memory_vnext_repository import MemoryVNextRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
)
from echo_masque.tool_runtime import ToolExecutionContext

_INTERNAL_MEMORY_NAMESPACE = "internal-memory-vnext"
_INTERNAL_CORE_MEMORY_NAMESPACE = "internal-core-memory"
_INTERNAL_TOPIC_NAMESPACE = "internal-topic-recall"
_INTERNAL_EPISODE_NAMESPACE = "internal-episode-recall"
INTERNAL_CONTEXT_TOOL_IDS = (
    "memory.search",
    "topic.search",
    "conversation.search",
    "wiki.lookup",
)

MemorySearchOrigin = Literal["core", "synthesized"]
MemorySearchRecord = CharacterCoreMemoryRecord | ConversationMemoryVNextRecord


class InternalSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=800)
    limit: int = Field(default=5, ge=1, le=8)


class WikiLookupBackend(Protocol):
    def __call__(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, object]]: ...


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _sparse(query: str, content: str) -> float:
    left = set(semantic_tokens(query))
    right = set(semantic_tokens(content))
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _normalized_content(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass
class InternalContextService:
    memory_repository: MemoryVNextRepository
    topic_repository: ConversationTopicRepository
    episode_repository: ConversationEpisodeRepository
    settings: Settings | None = None
    encoder: SemanticEncoder | None = None
    wiki_lookup_backend: WikiLookupBackend | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.vectors = SemanticVectorRepository(self.memory_repository.database)
        self.core_memory = CoreMemoryRepository(self.memory_repository.database)
        self.episodic_sql_rag = EpisodicSqlRagRepository(self.memory_repository.database)

    def _encoder(self) -> SemanticEncoder:
        if self.encoder is None:
            assert self.settings is not None
            self.encoder = FastEmbedSemanticEncoder(
                model_name=self.settings.semantic_embedding_model,
                model_file=self.settings.semantic_embedding_model_file,
                cache_dir=self.settings.semantic_embedding_cache_dir,
                dimension=self.settings.semantic_embedding_dimension,
            )
        return self.encoder

    def _semantic_vector(
        self,
        *,
        owner_id: str,
        namespace: str,
        resource_id: str,
        semantic_text: str,
        encoder: SemanticEncoder,
    ) -> list[float]:
        source_hash = self.vectors.source_hash(
            semantic_text,
            encoder.model_name,
            encoder.dimension,
        )
        cached = self.vectors.get(
            owner_id=owner_id,
            namespace=namespace,
            resource_id=resource_id,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        vector = encoder.embed_passage(semantic_text)
        self.vectors.upsert(
            owner_id=owner_id,
            namespace=namespace,
            resource_id=resource_id,
            semantic_text=semantic_text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            vector=vector,
        )
        return vector

    def _memory_vector(
        self,
        record: ConversationMemoryVNextRecord,
        encoder: SemanticEncoder,
    ) -> list[float]:
        return self._semantic_vector(
            owner_id=record.owner_id,
            namespace=_INTERNAL_MEMORY_NAMESPACE,
            resource_id=record.id,
            semantic_text=record.content,
            encoder=encoder,
        )

    def _core_memory_vector(
        self,
        record: CharacterCoreMemoryRecord,
        encoder: SemanticEncoder,
    ) -> list[float]:
        return self._semantic_vector(
            owner_id=record.owner_id,
            namespace=_INTERNAL_CORE_MEMORY_NAMESPACE,
            resource_id=record.id,
            semantic_text=record.content,
            encoder=encoder,
        )

    def memory_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        synthesized = self.memory_repository.active_candidates(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            subject_user_id=context.initiator_user_id,
            topic_id=context.topic_id,
        )
        core = self.core_memory.list_for_character(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            subject_user_id=context.initiator_user_id,
            status="active",
            limit=100,
        )
        ranked: list[tuple[float, MemorySearchOrigin, MemorySearchRecord]] = []
        try:
            encoder = self._encoder()
            query_vector = encoder.embed_query(payload.query)
            for record in core:
                semantic = _cosine(query_vector, self._core_memory_vector(record, encoder))
                score = record.priority * 0.58 + max(0.0, semantic) * 0.42
                if record.priority >= 0.85 or semantic >= 0.28:
                    ranked.append((score, "core", record))
            for record in synthesized:
                semantic = _cosine(query_vector, self._memory_vector(record, encoder))
                score = semantic * 0.72 + record.importance * 0.18 + record.confidence * 0.10
                if semantic >= 0.34:
                    ranked.append((score, "synthesized", record))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            for record in core:
                sparse = _sparse(payload.query, record.content)
                score = record.priority * 0.70 + sparse * 0.30
                if record.priority >= 0.85 or sparse >= 0.08:
                    ranked.append((score, "core", record))
            for record in synthesized:
                semantic = _sparse(payload.query, record.content)
                if semantic >= 0.10:
                    score = (
                        semantic * 0.72
                        + record.importance * 0.18
                        + record.confidence * 0.10
                    )
                    ranked.append((score, "synthesized", record))
        ranked.sort(key=lambda item: item[0], reverse=True)

        selected: list[tuple[float, MemorySearchOrigin, MemorySearchRecord]] = []
        seen_content: set[str] = set()
        # Core Memory wins exact-content dedup even if a synthesized copy has a slightly higher
        # semantic score. It is explicit user-controlled truth and must remain the durable layer.
        for origin in ("core", "synthesized"):
            for item in ranked:
                score, item_origin, record = item
                if item_origin != origin:
                    continue
                key = _normalized_content(record.content)
                if not key or key in seen_content:
                    continue
                seen_content.add(key)
                selected.append((score, item_origin, record))
        selected.sort(key=lambda item: item[0], reverse=True)
        selected = selected[: payload.limit]

        core_ids = tuple(
            cast(CharacterCoreMemoryRecord, record).id
            for _score, origin, record in selected
            if origin == "core"
        )
        synthesized_ids = tuple(
            cast(ConversationMemoryVNextRecord, record).id
            for _score, origin, record in selected
            if origin == "synthesized"
        )
        self.core_memory.mark_used(core_ids)
        self.memory_repository.mark_used(synthesized_ids)

        memories: list[dict[str, object]] = []
        for score, origin, record in selected:
            if origin == "core":
                core_record = cast(CharacterCoreMemoryRecord, record)
                memories.append(
                    {
                        "ref": core_record.id,
                        "origin": "core",
                        "scope_type": core_record.scope_type,
                        "memory_type": core_record.memory_type,
                        "content": core_record.content,
                        "priority": round(core_record.priority, 3),
                        "score": round(score, 4),
                    }
                )
            else:
                synthesized_record = cast(ConversationMemoryVNextRecord, record)
                memories.append(
                    {
                        "ref": synthesized_record.id,
                        "origin": "synthesized",
                        "scope_type": synthesized_record.scope_type,
                        "memory_type": synthesized_record.memory_type,
                        "content": synthesized_record.content,
                        "confidence": round(synthesized_record.confidence, 3),
                        "importance": round(synthesized_record.importance, 3),
                        "score": round(score, 4),
                    }
                )
        return json.dumps(
            {
                "ok": True,
                "scope": "character_memory_layers",
                "count": len(memories),
                "memories": memories,
            },
            ensure_ascii=False,
        )

    def topic_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        records = self.topic_repository.recent_for_scope(
            owner_id=context.owner_id,
            platform=context.platform,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
            limit=20,
        )
        scored: list[tuple[float, ConversationTopicRecord]] = []
        try:
            encoder = self._encoder()
            query_vector = encoder.embed_query(payload.query)
            for item in records:
                semantic_text = f"{item.topic_label} {item.summary}".strip()
                semantic = _cosine(
                    query_vector,
                    self._semantic_vector(
                        owner_id=item.owner_id,
                        namespace=_INTERNAL_TOPIC_NAMESPACE,
                        resource_id=item.id,
                        semantic_text=semantic_text,
                        encoder=encoder,
                    ),
                )
                sparse = _sparse(payload.query, semantic_text)
                if semantic >= 0.30 or sparse >= 0.12:
                    scored.append((semantic * 0.82 + sparse * 0.18, item))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            scored = [
                (_sparse(payload.query, f"{item.topic_label} {item.summary}"), item)
                for item in records
            ]
        scored.sort(key=lambda item: (item[0], item[1].last_active_at), reverse=True)
        selected = [(score, item) for score, item in scored if score > 0][: payload.limit]
        return json.dumps(
            {
                "ok": True,
                "scope": "current_discord_location",
                "count": len(selected),
                "topics": [
                    {
                        "ref": item.id,
                        "label": item.topic_label,
                        "summary": item.summary[:800],
                        "status": item.status,
                        "score": round(score, 4),
                        "last_active_at": item.last_active_at.isoformat(),
                    }
                    for score, item in selected
                ],
            },
            ensure_ascii=False,
        )

    def _episode_scores(
        self,
        *,
        query: str,
        records: tuple[ConversationEpisodeRecord, ...],
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        try:
            encoder = self._encoder()
            query_vector = encoder.embed_query(query)
            for item in records:
                semantic_text = f"{item.summary} {item.key_points_json}".strip()
                semantic = _cosine(
                    query_vector,
                    self._semantic_vector(
                        owner_id=item.owner_id,
                        namespace=_INTERNAL_EPISODE_NAMESPACE,
                        resource_id=item.id,
                        semantic_text=semantic_text,
                        encoder=encoder,
                    ),
                )
                sparse = _sparse(query, semantic_text)
                if semantic >= 0.24 or sparse >= 0.10:
                    scores[item.id] = semantic * 0.84 + sparse * 0.16
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            for item in records:
                sparse = _sparse(query, f"{item.summary} {item.key_points_json}")
                if sparse >= 0.08:
                    scores[item.id] = sparse
        return scores

    def conversation_search(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        # Server-wide episodic recall is permitted only through explicit CharacterEpisodeAccess
        # evidence. Old/unproven server history deliberately fails closed rather than making a
        # Character omniscient.
        perceived = self.episodic_sql_rag.accessible_episodes(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            limit=240,
        )
        base_scores = self._episode_scores(query=payload.query, records=perceived)
        seed_limit = max(6, payload.limit * 2)
        seed_ids = tuple(
            episode_id
            for episode_id, _score in sorted(
                base_scores.items(), key=lambda item: item[1], reverse=True
            )[:seed_limit]
        )
        expanded_ids = self.episodic_sql_rag.expand_episode_ids(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            seed_episode_ids=seed_ids,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            max_entity_degree=48,
            limit=96,
        )
        expanded_records = self.episodic_sql_rag.episodes_by_ids(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            episode_ids=expanded_ids,
        )
        expanded_scores = self._episode_scores(query=payload.query, records=expanded_records)
        seed_set = set(seed_ids)
        expanded_set = set(expanded_ids) - seed_set
        ranked: list[tuple[float, ConversationEpisodeRecord]] = []
        for item in expanded_records:
            semantic_score = expanded_scores.get(item.id, base_scores.get(item.id, 0.0))
            structural_boost = 0.12 if item.id in expanded_set else 0.0
            current_location_boost = (
                0.04
                if item.channel_id == context.channel_id and item.thread_id == context.thread_id
                else 0.0
            )
            score = semantic_score + structural_boost + current_location_boost
            if score > 0.0:
                ranked.append((score, item))
        ranked.sort(key=lambda item: (item[0], item[1].ended_at), reverse=True)
        selected = ranked[: payload.limit]
        return json.dumps(
            {
                "ok": True,
                "scope": "current_discord_server_perceived",
                "retrieval_mode": "e5_seed_sql_event_entity_expand",
                "seed_count": len(seed_ids),
                "expanded_count": len(expanded_set),
                "count": len(selected),
                "episodes": [
                    {
                        "ref": item.id,
                        "topic_ref": item.topic_id,
                        "channel_ref": item.channel_id,
                        "thread_ref": item.thread_id,
                        "summary": item.summary,
                        "key_points": json.loads(item.key_points_json or "[]")[:8],
                        "source_message_refs": json.loads(
                            item.source_message_ids_json or "[]"
                        )[:12],
                        "score": round(score, 4),
                        "expanded_via_entity": item.id in expanded_set,
                        "ended_at": item.ended_at.isoformat(),
                    }
                    for score, item in selected
                ],
            },
            ensure_ascii=False,
        )

    def wiki_lookup(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        if self.wiki_lookup_backend is None:
            return json.dumps(
                {
                    "ok": True,
                    "available": False,
                    "scope": "current_discord_server",
                    "pages": [],
                },
                ensure_ascii=False,
            )
        pages = self.wiki_lookup_backend(
            owner_id=context.owner_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            query=payload.query,
            limit=payload.limit,
        )
        return json.dumps(
            {
                "ok": True,
                "available": True,
                "scope": "current_discord_server",
                "count": len(pages),
                "pages": pages,
            },
            ensure_ascii=False,
        )

    def execute(
        self,
        tool_id: str,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        if tool_id == "memory.search":
            return self.memory_search(arguments, context)
        if tool_id == "topic.search":
            return self.topic_search(arguments, context)
        if tool_id == "conversation.search":
            return self.conversation_search(arguments, context)
        if tool_id == "wiki.lookup":
            return self.wiki_lookup(arguments, context)
        raise ValueError("Unknown Internal Context Tool.")


def internal_context_tool_schemas() -> tuple[dict[str, object], ...]:
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 800},
            "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    return tuple(
        {
            "tool_id": tool_id,
            "provider_name": tool_id.replace(".", "_"),
            "parameters": schema,
        }
        for tool_id in INTERNAL_CONTEXT_TOOL_IDS
    )


__all__ = [
    "INTERNAL_CONTEXT_TOOL_IDS",
    "InternalContextService",
    "InternalSearchInput",
    "WikiLookupBackend",
    "internal_context_tool_schemas",
]
