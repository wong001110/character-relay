"""Current speaker context from raw sources, with no semantic-thread prerequisite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.character_turn_context_types import CharacterContextTraceView, CharacterTurnContext
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.note_repository import CharacterNoteRepository
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.persistence.server_runtime_repository import ServerRuntimeRepository
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import FocusedContext, SourceMessage, SourceUnavailable, scope_key
from echo_masque.server_time import activate_server_timezone, server_local_now
from echo_masque.smart_output import SmartOutputContext

if TYPE_CHECKING:
    from echo_masque.connector_runtime import ResolvedCharacterTurn


def payload_scope(payload: DiscordInboundMessage, owner_id: str) -> RoomScope:
    return RoomScope(
        owner_id=owner_id,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
    )


def bind_requester(
    payload: DiscordInboundMessage,
    deployment: CharacterDeploymentRecord,
    repository: RoomRepository,
) -> DiscordInboundMessage:
    """Replace all caller-supplied authority hints with the authenticated source binding."""
    scope = payload_scope(payload, deployment.owner_id)
    if payload.source_selection_id:
        selection = repository.selection(scope, payload.source_selection_id, deployment.id)
        if payload.message_id != selection.trigger_message_id:
            raise SourceUnavailable("selection_trigger_mismatch")
        updates: dict[str, object] = {
            "runtime_request_id": selection.request_id,
            "runtime_requester_id": selection.requester_id,
            "runtime_requester_is_bot": selection.requester_is_bot,
            "runtime_target_message_id": selection.target_message_id,
            "runtime_selection_origin": selection.origin,
        }
    else:
        updates = {
            "runtime_request_id": payload.message_id,
            "runtime_requester_id": payload.author_id,
            "runtime_requester_is_bot": payload.author_is_bot,
            "runtime_target_message_id": payload.message_id,
            "runtime_selection_origin": "continuation"
            if payload.author_is_bot
            else ("direct" if payload.mentioned_bot or payload.replied_to_bot else "ambient"),
        }
    return payload.model_copy(update=updates)


@dataclass(frozen=True, slots=True)
class RoomContextBundle:
    query: str
    focus: FocusedContext | None
    temporal_context: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def focused_message_ids(self) -> tuple[str, ...]:
        return self.focus.message_ids if self.focus is not None else ()

    @property
    def native_context_id(self) -> str:
        return (
            scope_key(self.focus.scope)
            if self.focus is not None and self.focus.scope.thread_id
            else ""
        )

    def prompt_sections(self) -> tuple[str, ...]:
        if self.focus is None:
            return ()
        missing = (
            "An earlier Reply ancestor is unavailable. "
            "Do not invent its content; clarify when needed."
            if self.focus.missing_ancestor_ids
            else ""
        )
        return tuple(
            value
            for value in (
                "SOURCE FOCUS\nThe primary reply target is explicitly marked in the transcript. "
                "Other recent messages are context, not replacement requests. "
                "Reply relationships organize evidence, not private access or shared preferences. "
                + missing,
                "TIME\n" + "\n".join(self.temporal_context),
                "EXPLICIT NOTES\n" + "\n".join(self.notes) if self.notes else "",
                "RECALL\nUse memory.search, conversation.search or knowledge.search only when past "
                "information is needed. A missing result is valid; "
                "do not fill it with invented memory.",
            )
            if value
        )


@dataclass(frozen=True, slots=True)
class RoomContextResult:
    bundle: RoomContextBundle
    turn_context: CharacterTurnContext
    payload: DiscordInboundMessage
    error_reason: str = ""


class RoomContextService:
    def __init__(
        self, repository: RoomRepository, *, notes: CharacterNoteRepository | None = None
    ) -> None:
        self.repository = repository
        self.notes = notes
        self.server_runtime = ServerRuntimeRepository(repository.database)

    def build(self, resolved: ResolvedCharacterTurn) -> RoomContextResult:
        payload = bind_requester(resolved.payload, resolved.deployment, self.repository)
        scope = payload_scope(payload, resolved.deployment.owner_id)
        try:
            if not payload.source_selection_id:
                # Legacy/test callers without origin metadata contribute only their current
                # authenticated event. An unscoped history item is never relabeled to fit.
                observations = [
                    SourceMessage(
                        message_id=item.message_id,
                        channel_id=item.channel_id,
                        thread_id=item.thread_id,
                        author_id=item.author_id,
                        author_display_name=item.author_display_name,
                        author_is_bot=item.is_bot,
                        author_deployment_id=item.author_deployment_id,
                        text=item.text,
                        reply_to_message_id=item.reply_to_message_id,
                        created_at=item.created_at,
                        edited_at=item.edited_at,
                        content_available=item.content_available,
                        has_unseen_media=bool(item.emojis or item.stickers),
                    )
                    for item in payload.recent_messages
                    if item.channel_id == payload.channel_id and item.thread_id == payload.thread_id
                ]
                if not any(item.message_id == payload.message_id for item in observations):
                    observations.append(
                        SourceMessage(
                            message_id=payload.message_id,
                            channel_id=payload.channel_id,
                            thread_id=payload.thread_id,
                            author_id=payload.author_id,
                            author_display_name=payload.author_display_name,
                            author_is_bot=payload.author_is_bot,
                            text=payload.text,
                            reply_to_message_id=payload.reply_to_message_id,
                            created_at=payload.source_created_at,
                            edited_at=payload.source_edited_at,
                            has_unseen_media=bool(payload.attachments or payload.embeds),
                        )
                    )
                self.repository.observe(scope, observations)
            focus = self.repository.focus(scope, payload.runtime_target_message_id)
            target = next(
                source
                for source in focus.sources
                if source.message.message_id == focus.target_message_id
            )
            messages = [
                DiscordContextMessage(
                    message_id=source.message.message_id,
                    channel_id=scope.channel_id,
                    thread_id=scope.thread_id,
                    author_id=source.message.author_id,
                    author_display_name=source.message.author_display_name,
                    author_deployment_id=source.message.author_deployment_id,
                    is_bot=source.message.author_is_bot,
                    text=source.message.text,
                    reply_to_message_id=(
                        source.message.reply_to_message_id or source.message.response_to_message_id
                    ),
                    created_at=source.message.created_at,
                    edited_at=source.message.edited_at,
                )
                for source in focus.sources
            ]
            updates: dict[str, object] = {"recent_messages": messages}
            if payload.runtime_selection_origin == "direct":
                # Quoted or caller-supplied prose never replaces the actual requesting source.
                updates["text"] = target.message.text
            payload = payload.model_copy(update=updates)
            timezone = self.server_runtime.resolve_timezone(
                owner_id=scope.owner_id, connection_id=scope.connection_id, guild_id=scope.guild_id
            )
            activate_server_timezone(timezone)
            note_lines: tuple[str, ...] = ()
            if self.notes is not None:
                subjects = {f"user:{payload.runtime_requester_id}"}
                with self.repository.database.session() as session:
                    for source in focus.sources:
                        if source.message.message_id not in focus.anchor_ids:
                            continue
                        if not source.message.author_is_bot:
                            subjects.add(f"user:{source.message.author_id}")
                        elif source.message.author_deployment_id:
                            role = session.get(
                                CharacterDeploymentRecord, source.message.author_deployment_id
                            )
                            if role is not None:
                                subjects.add(f"character:{role.character_card_id}")
                note_lines = tuple(
                    note.prompt_text()
                    for note in self.notes.list(
                        owner_id=scope.owner_id,
                        card_id=resolved.card.id,
                        scope=scope,
                        subjects=tuple(sorted(subjects))[:24],
                        limit=8,
                    )
                )
            bundle = RoomContextBundle(
                query=target.message.text,
                focus=focus,
                notes=note_lines,
                temporal_context=(
                    f"Default timezone: {timezone} (IANA).",
                    "Current local datetime: "
                    f"{server_local_now(timezone).isoformat(timespec='seconds')}.",
                ),
            )
            trace = CharacterContextTraceView(
                rag_status="skipped",
                rag_reason="recall_on_demand",
                query_chars=len(bundle.query),
                conversation_message_count=len(messages),
                conversation_chars=sum(len(item.text) for item in messages),
                conversation_thread_id=payload.thread_id,
                source_target_message_id=focus.target_message_id,
                source_snapshot_revision=focus.room_revision,
                source_fingerprint=focus.fingerprint,
                source_anchor_ids=list(focus.anchor_ids),
                source_requester_id=payload.runtime_requester_id,
                source_origin=payload.runtime_selection_origin,
                source_category_id=payload.category_id,
                source_content_hashes={
                    s.message.message_id: s.message.draft_fingerprint() for s in focus.sources
                },
                source_revisions={
                    source.message.message_id: source.revision for source in focus.sources
                },
            )
            error = ""
        except SourceUnavailable as exc:
            bundle = RoomContextBundle(query="", focus=None)
            trace = CharacterContextTraceView(rag_status="failed", rag_reason=str(exc))
            error = str(exc)
        return RoomContextResult(
            bundle,
            CharacterTurnContext(
                smart_output=SmartOutputContext.from_payload(
                    payload, character_name=resolved.card.display_name
                ),
                knowledge=(),
                trace=trace,
            ),
            payload,
            error,
        )
