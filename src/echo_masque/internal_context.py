"""Character-scoped explicit notes, raw history and admitted knowledge on demand."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.knowledge_fabric_context import KnowledgeContextBuilder
from echo_masque.notes import NoteAccessDenied
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.note_repository import CharacterNoteRepository
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.room_routing import RoomScope
from echo_masque.sparse_retrieval import normalize_text, sparse_score
from echo_masque.tool_runtime import ToolExecutionContext

INTERNAL_CONTEXT_TOOL_IDS = ("memory.search", "conversation.search", "knowledge.search")


class InternalSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=800)
    limit: int = Field(default=5, ge=1, le=8)


@dataclass
class InternalContextService:
    notes: CharacterNoteRepository
    rooms: RoomRepository
    deployments: DeploymentRepository
    knowledge_context: KnowledgeContextBuilder | None = None

    def _authorized_scope(self, context: ToolExecutionContext) -> RoomScope | None:
        if context.platform != "discord" or not all(
            (
                context.owner_id,
                context.character_card_id,
                context.deployment_id,
                context.connection_id,
                context.guild_id,
                context.channel_id,
            )
        ):
            return None
        deployment = self.deployments.deployment_matches_discord_destination(
            context.deployment_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
            category_id=context.category_id,
        )
        if (
            deployment is None
            or deployment.owner_id != context.owner_id
            or deployment.character_card_id != context.character_card_id
        ):
            return None
        scope = RoomScope(
            owner_id=context.owner_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
        )
        return scope if self.rooms.can_read(scope, max_age_seconds=300) else None

    @staticmethod
    def _unavailable() -> str:
        return json.dumps(
            {
                "ok": False,
                "available": False,
                "reason": "recall_scope_unavailable",
                "count": 0,
                "results": [],
                "memories": [],
            }
        )

    def memory_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        scope = self._authorized_scope(context)
        if scope is None:
            return self._unavailable()
        try:
            notes = self.notes.list(
                owner_id=context.owner_id, card_id=context.character_card_id, scope=scope, limit=256
            )
        except NoteAccessDenied:
            return self._unavailable()
        ranked = sorted(
            ((sparse_score(payload.query, item.text), item) for item in notes),
            key=lambda pair: (-pair[0], pair[1].id),
        )
        selected: list[dict[str, object]] = []
        seen: set[str] = set()
        for score, note in ranked:
            key = normalize_text(f"{note.subject_ref}: {note.text}")
            if score <= 0 or key in seen:
                continue
            seen.add(key)
            selected.append(
                {
                    "ref": note.id,
                    "origin": "authored" if note.authored else "explicit",
                    "subject_ref": note.subject_ref,
                    "kind": note.kind,
                    "value": note.text,
                    "version": note.version,
                    "source_message_ref": note.source_message_id,
                    "score": round(score, 4),
                }
            )
            if len(selected) >= payload.limit:
                break
        if self._authorized_scope(context) is None:
            return self._unavailable()
        return json.dumps(
            {
                "ok": True,
                "scope": "character_explicit_notes",
                "count": len(selected),
                "memories": selected,
                "retrieval_backend": "sparse_v1",
                "dense_index_status": "not_configured",
                "rule": "Attributed notes, not verified facts or permissions.",
            },
            ensure_ascii=False,
        )

    def conversation_search(
        self, arguments: dict[str, object], context: ToolExecutionContext
    ) -> str:
        payload = InternalSearchInput.model_validate(arguments)
        scope = self._authorized_scope(context)
        if scope is None:
            return self._unavailable()
        rows = self.rooms.search(scope, payload.query)
        ranked = sorted(
            ((sparse_score(payload.query, item.message.text), item) for item in rows),
            key=lambda pair: (-pair[0], pair[1].message.message_id),
        )
        selected: list[dict[str, object]] = []
        for score, item in ranked:
            if score <= 0:
                continue
            message = item.message
            selected.append(
                {
                    "ref": message.message_id,
                    "kind": "raw_message",
                    "revision": item.revision,
                    "author_id": message.author_id,
                    "author_is_bot": message.author_is_bot,
                    "author_deployment_id": message.author_deployment_id,
                    "content": message.text[:1200],
                    "content_truncated": len(message.text) > 1200,
                    "reply_to_message_ref": message.reply_to_message_id
                    or message.response_to_message_id,
                    "source_message_refs": [message.message_id],
                    "score": round(score, 4),
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
            )
            if len(selected) >= payload.limit:
                break
        if self._authorized_scope(context) is None:
            return self._unavailable()
        return json.dumps(
            {
                "ok": True,
                "scope": "current_discord_room_history",
                "count": len(selected),
                "results": selected,
                "retrieval_backend": "sparse_v1",
                "dense_index_status": "not_configured",
                "candidate_limit": 240,
                "candidate_limit_reached": len(rows) == 240,
            },
            ensure_ascii=False,
        )

    def knowledge_search(self, arguments: dict[str, object], context: ToolExecutionContext) -> str:
        """Return only Character-admitted, locator-free Fabric Evidence to the model."""

        payload = InternalSearchInput.model_validate(arguments)
        if self._authorized_scope(context) is None:
            return self._unavailable()
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
        prompt_hits = {item.ref: item for item in knowledge.prompt_hits()}
        results = [
            {
                "ref": f"evidence:{hit.evidence_unit_id}",
                "title": hit.document_title[:200],
                "source_version_id": hit.source_version_id,
                "authority": hit.authority_profile,
                "channels": list(hit.channels),
                "content": prompt_hits[f"evidence:{hit.evidence_unit_id}"].text,
            }
            for hit in knowledge.hits
            if f"evidence:{hit.evidence_unit_id}" in prompt_hits
        ]
        if self._authorized_scope(context) is None:
            return self._unavailable()
        return json.dumps(
            {
                "ok": True,
                "available": knowledge.result is not None,
                "scope": "current_knowledge_fabric_server",
                "count": len(results),
                "results": results,
                "dense_index_status": (
                    knowledge.result.dense_index_status if knowledge.result else "unavailable"
                ),
            },
            ensure_ascii=False,
        )

    def execute(
        self, tool_id: str, arguments: dict[str, object], context: ToolExecutionContext
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
