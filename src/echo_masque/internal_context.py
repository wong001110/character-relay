"""Runtime-scoped Internal Context Tools for Roleplay model recall."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from pydantic import BaseModel, Field

from echo_masque.config import Settings, get_settings
from echo_masque.expression_retrieval import semantic_tokens
from echo_masque.knowledge_fabric_context import KnowledgeContextBuilder
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationEpisodeV3View,
    ConversationRuntimeRepository,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
)
from echo_masque.tool_runtime import ToolExecutionContext

_INTERNAL_BELIEF_NAMESPACE = "internal-belief-v3"
_INTERNAL_EPISODE_NAMESPACE = "internal-episode-v3"
INTERNAL_CONTEXT_TOOL_IDS = (
    "memory.search",
    "conversation.search",
    "knowledge.search",
)


class InternalSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=800)
    limit: int = Field(default=5, ge=1, le=8)


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
    knowledge_context: KnowledgeContextBuilder | None = None
    identities: DiscordIdentityRepository | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.vectors = SemanticVectorRepository(self.belief_repository.database)
        self.identities = self.identities or DiscordIdentityRepository(
            self.runtime_repository.database
        )

    @staticmethod
    def _query_terms(query: str) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(token for token in semantic_tokens(query) if len(token) > 1)
        )[:16]

    def _episode_was_perceived(
        self,
        *,
        context: ToolExecutionContext,
        episode: ConversationEpisodeV3View,
    ) -> bool:
        """Use the same route-based deployment perception gate as automatic context."""

        if not context.deployment_id or self.identities is None:
            return False
        return any(
            (
                route := self.identities.resolve_message_route(
                    connection_id=context.connection_id,
                    message_id=message_id,
                )
            )
            is not None
            and route.deployment_id == context.deployment_id
            for message_id in episode.source_message_ids
        )

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
        beliefs = self.belief_repository.search_relevant(
            owner_id=context.owner_id,
            character_card_id=context.character_card_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            query_terms=self._query_terms(payload.query),
            limit=240,
        )
        belief_by_id = {item.id: item for item in beliefs}
        candidates = [
            (
                item.id,
                f"{item.subject_ref} {item.predicate} {item.value_text} {item.status}",
            )
            for item in beliefs
        ]
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
        for score, resource_id in ranked:
            belief = belief_by_id.get(resource_id)
            if belief is None:
                continue
            subject = belief.subject_ref or belief.subject_entity_id
            content = f"{subject} {belief.predicate}: {belief.value_text}".strip()
            key = _normalized_content(content)
            if not key or key in seen_content:
                continue
            seen_content.add(key)
            selected.append(
                {
                    "ref": belief.id,
                    "origin": "authored" if belief.authored else "learned",
                    "status": belief.status,
                    "subject_ref": belief.subject_ref,
                    "subject_entity_id": belief.subject_entity_id,
                    "predicate": belief.predicate,
                    "value": belief.value_text,
                    "authority": belief.authority_class,
                    "authority_score": round(belief.authority_score, 3),
                    "confidence": round(belief.confidence, 3),
                    "importance": round(belief.importance, 3),
                    "score": round(score, 4),
                }
            )
            if len(selected) >= payload.limit:
                break
        return json.dumps(
            {
                "ok": True,
                "scope": "character_beliefs",
                "count": len(selected),
                "memories": selected,
                "rule": "active=known; provisional=tentative; disputed=conflicting evidence",
            },
            ensure_ascii=False,
        )

    def _episode_hits(
        self,
        *,
        query: str,
        context: ToolExecutionContext,
        limit: int,
    ) -> list[dict[str, object]]:
        records = self.runtime_repository.search_episodes(
            owner_id=context.owner_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            query_terms=self._query_terms(query),
            limit=240,
        )
        records = tuple(
            item for item in records if self._episode_was_perceived(context=context, episode=item)
        )
        by_id: dict[str, ConversationEpisodeV3View] = {item.id: item for item in records}
        ranked = self._rank(
            owner_id=context.owner_id,
            namespace=_INTERNAL_EPISODE_NAMESPACE,
            query=query,
            values=[(item.id, " ".join((item.summary, *item.key_events))) for item in records],
            semantic_floor=0.24,
            sparse_floor=0.08,
        )
        return [
            {
                "ref": item.id,
                "kind": "episode",
                "conversation_thread_ref": item.conversation_thread_id,
                "summary": item.summary,
                "key_events": list(item.key_events[:8]),
                "source_message_refs": list(item.source_message_ids[:12]),
                "entity_refs": list(item.entity_ids[:12]),
                "score": round(score, 4),
                "ended_at": item.ended_at.isoformat(),
            }
            for score, item_id in ranked[:limit]
            for item in (by_id[item_id],)
        ]

    def conversation_search(
        self,
        arguments: dict[str, object],
        context: ToolExecutionContext,
    ) -> str:
        """Search only durable Episodes that the requesting deployment perceived."""

        payload = InternalSearchInput.model_validate(arguments)
        episodes = self._episode_hits(query=payload.query, context=context, limit=payload.limit)
        return json.dumps(
            {
                "ok": True,
                "scope": "current_discord_server_conversation",
                "count": len(episodes),
                "results": episodes,
            },
            ensure_ascii=False,
        )

    def knowledge_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        """Return only Character-admitted, locator-free Fabric Evidence to the model."""

        payload = InternalSearchInput.model_validate(arguments)
        if self.knowledge_context is None:
            return json.dumps(
                {
                    "ok": True,
                    "available": False,
                    "scope": "current_knowledge_fabric_server",
                    "results": [],
                },
                ensure_ascii=False,
            )
        knowledge = self.knowledge_context.build(
            platform=context.platform,
            connection_id=context.connection_id,
            workspace_id=context.guild_id,
            deployment_id=context.deployment_id,
            character_card_id=context.character_card_id,
            query=payload.query,
            result_limit=payload.limit,
        )
        prompt_hits = knowledge.prompt_hits()
        results = [
            {
                "ref": prompt_hit.ref,
                "title": hit.document_title,
                "source_version_id": hit.source_version_id,
                "authority": hit.authority_profile,
                "channels": list(hit.channels),
                "content": prompt_hit.text,
            }
            for hit, prompt_hit in zip(knowledge.hits, prompt_hits, strict=True)
        ]
        return json.dumps(
            {
                "ok": True,
                "available": knowledge.result is not None,
                "scope": "current_knowledge_fabric_server",
                "count": len(results),
                "results": results,
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
        if tool_id == "conversation.search":
            return self.conversation_search(arguments, context)
        if tool_id == "knowledge.search":
            return self.knowledge_search(arguments, context)
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
    "internal_context_tool_schemas",
]
