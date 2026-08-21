"""Runtime-scoped Internal Context Tools for Roleplay model recall."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field

from echo_masque.config import Settings, get_settings
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.persistence.belief_repository import BeliefRepository, BeliefV3View
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationEpisodeV3View,
    ConversationRuntimeRepository,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
    ConversationThreadView,
)
from echo_masque.persistence.core_memory_models import CharacterCoreMemoryRecord
from echo_masque.persistence.core_memory_repository import CoreMemoryRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
)
from echo_masque.tool_runtime import ToolExecutionContext

_INTERNAL_BELIEF_NAMESPACE = "internal-belief-v3"
_INTERNAL_CORE_MEMORY_NAMESPACE = "internal-core-memory"
_INTERNAL_THREAD_NAMESPACE = "internal-thread-v3"
_INTERNAL_EPISODE_NAMESPACE = "internal-episode-v3"
INTERNAL_CONTEXT_TOOL_IDS = (
    "memory.search",
    "thread.search",
    "episode.search",
    "wiki.lookup",
)


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
    ) -> tuple[dict[str, object], ...] | list[dict[str, object]]: ...


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
    belief_repository: BeliefRepository
    structure_repository: ConversationStructureRepository
    runtime_repository: ConversationRuntimeRepository
    settings: Settings | None = None
    encoder: SemanticEncoder | None = None
    wiki_lookup_backend: WikiLookupBackend | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        database = self.belief_repository.database
        self.vectors = SemanticVectorRepository(database)
        self.core_memory = CoreMemoryRepository(database)

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

    def _rank(
        self,
        *,
        owner_id: str,
        namespace: str,
        query: str,
        values: list[tuple[str, str]],
        semantic_floor: float,
        sparse_floor: float,
    ) -> list[tuple[float, str]]:
        scores: list[tuple[float, str]] = []
        try:
            encoder = self._encoder()
            query_vector = encoder.embed_query(query)
            for resource_id, text in values:
                semantic = _cosine(
                    query_vector,
                    self._semantic_vector(
                        owner_id=owner_id,
                        namespace=namespace,
                        resource_id=resource_id,
                        semantic_text=text,
                        encoder=encoder,
                    ),
                )
                sparse = _sparse(query, text)
                if semantic >= semantic_floor or sparse >= sparse_floor:
                    scores.append((semantic * 0.84 + sparse * 0.16, resource_id))
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            for resource_id, text in values:
                sparse = _sparse(query, text)
                if sparse >= sparse_floor:
                    scores.append((sparse, resource_id))
        scores.sort(key=lambda item: item[0], reverse=True)
        return scores

    def memory_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        beliefs = self.belief_repository.recall(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            limit=120,
        )
        core = self.core_memory.list_for_character(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            subject_user_id="",
            status="active",
            limit=100,
        )
        belief_by_id = {item.id: item for item in beliefs}
        core_by_id = {item.id: item for item in core}
        candidates = [
            (
                item.id,
                f"{item.subject_ref} {item.predicate} {item.value_text} {item.status}",
            )
            for item in beliefs
        ] + [(item.id, item.content) for item in core]
        ranked = self._rank(
            owner_id=context.owner_id,
            namespace=_INTERNAL_BELIEF_NAMESPACE,
            query=payload.query,
            values=candidates,
            semantic_floor=0.28,
            sparse_floor=0.08,
        )
        selected: list[dict[str, object]] = []
        seen_content: set[str] = set()
        used_core_ids: list[str] = []
        for score, resource_id in ranked:
            core_record = core_by_id.get(resource_id)
            belief = belief_by_id.get(resource_id)
            if core_record is not None:
                content = core_record.content
                key = _normalized_content(content)
                if not key or key in seen_content:
                    continue
                seen_content.add(key)
                used_core_ids.append(core_record.id)
                selected.append(
                    {
                        "ref": core_record.id,
                        "origin": "canonical",
                        "status": "active",
                        "memory_type": core_record.memory_type,
                        "content": content,
                        "priority": round(core_record.priority, 3),
                        "score": round(score, 4),
                    }
                )
            elif belief is not None:
                content = f"{belief.subject_ref or belief.subject_entity_id} {belief.predicate}: {belief.value_text}"
                key = _normalized_content(content)
                if not key or key in seen_content:
                    continue
                seen_content.add(key)
                selected.append(
                    {
                        "ref": belief.id,
                        "origin": "learned_claim",
                        "status": belief.status,
                        "subject_ref": belief.subject_ref,
                        "subject_entity_id": belief.subject_entity_id,
                        "predicate": belief.predicate,
                        "value": belief.value_text,
                        "authority": belief.authority_class,
                        "authority_score": round(belief.authority_score, 3),
                        "confidence": round(belief.confidence, 3),
                        "score": round(score, 4),
                    }
                )
            if len(selected) >= payload.limit:
                break
        self.core_memory.mark_used(tuple(used_core_ids))
        return json.dumps(
            {
                "ok": True,
                "scope": "character_belief_layers",
                "count": len(selected),
                "memories": selected,
                "rule": "active=known; provisional=tentative; disputed=conflicting evidence",
            },
            ensure_ascii=False,
        )

    def thread_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        records = self.structure_repository.recent_threads_for_server(
            owner_id=context.owner_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            limit=120,
        )
        by_id: dict[str, ConversationThreadView] = {item.id: item for item in records}
        ranked = self._rank(
            owner_id=context.owner_id,
            namespace=_INTERNAL_THREAD_NAMESPACE,
            query=payload.query,
            values=[
                (
                    item.id,
                    f"{item.canonical_label} {item.anchor_summary} {item.working_summary}",
                )
                for item in records
            ],
            semantic_floor=0.28,
            sparse_floor=0.08,
        )
        selected = [(score, by_id[item_id]) for score, item_id in ranked[: payload.limit]]
        return json.dumps(
            {
                "ok": True,
                "scope": "current_discord_server_conversation_threads",
                "count": len(selected),
                "threads": [
                    {
                        "ref": item.id,
                        "label": item.canonical_label,
                        "anchor_summary": item.anchor_summary[:900],
                        "working_summary": item.working_summary[:900],
                        "status": item.status,
                        "participant_refs": list(item.participant_ids[:12]),
                        "entity_refs": list(item.active_entity_ids[:12]),
                        "score": round(score, 4),
                        "last_active_at": item.last_active_at.isoformat(),
                    }
                    for score, item in selected
                ],
            },
            ensure_ascii=False,
        )

    def episode_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        records = self.runtime_repository.recent_episodes(
            owner_id=context.owner_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            limit=200,
        )
        by_id: dict[str, ConversationEpisodeV3View] = {item.id: item for item in records}
        ranked = self._rank(
            owner_id=context.owner_id,
            namespace=_INTERNAL_EPISODE_NAMESPACE,
            query=payload.query,
            values=[
                (
                    item.id,
                    " ".join((item.summary, *item.key_events)),
                )
                for item in records
            ],
            semantic_floor=0.24,
            sparse_floor=0.08,
        )
        selected = [(score, by_id[item_id]) for score, item_id in ranked[: payload.limit]]
        return json.dumps(
            {
                "ok": True,
                "scope": "current_discord_server_episodes",
                "count": len(selected),
                "episodes": [
                    {
                        "ref": item.id,
                        "conversation_thread_ref": item.conversation_thread_id,
                        "channel_ref": item.channel_id,
                        "discord_thread_ref": item.discord_thread_id,
                        "summary": item.summary,
                        "key_events": list(item.key_events[:8]),
                        "source_message_refs": list(item.source_message_ids[:12]),
                        "entity_refs": list(item.entity_ids[:12]),
                        "score": round(score, 4),
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
        pages = list(
            self.wiki_lookup_backend(
                owner_id=context.owner_id,
                connection_id=context.connection_id,
                guild_id=context.guild_id,
                query=payload.query,
                limit=payload.limit,
            )
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
        if tool_id == "thread.search":
            return self.thread_search(arguments, context)
        if tool_id == "episode.search":
            return self.episode_search(arguments, context)
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
