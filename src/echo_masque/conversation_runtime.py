"""Conversation runtime coordinator for Segment-based Episodes and Thread working state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from echo_masque.api.smart_participation_v3_schemas import SmartParticipationResolveRequest
from echo_masque.conversation_structure_resolver import ConversationSegmentationResult
from echo_masque.persistence.conversation_runtime_models import ConversationEpisodeV3Record
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationEpisodeV3View,
    ConversationRuntimeRepository,
    ThreadWorkingStateView,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)

_DEFAULT_WORKING_TTL = timedelta(hours=6)
_DEFAULT_EPISODE_INACTIVITY = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class ConversationRuntimeObservation:
    episodes: tuple[ConversationEpisodeV3View, ...]
    working_states: tuple[ThreadWorkingStateView, ...]


class ConversationRuntimeCoordinator:
    """Project revisable structure into runtime scratch state and durable Episodes."""

    def __init__(
        self,
        structure: ConversationStructureRepository,
        runtime: ConversationRuntimeRepository | None = None,
    ) -> None:
        self.structure = structure
        self.runtime = runtime or ConversationRuntimeRepository(structure.database)

    @staticmethod
    def _question_candidates(summary: str) -> tuple[str, ...]:
        text = " ".join(summary.split())[:800]
        if not text:
            return ()
        lowered = text.lower()
        if (
            "?" in text
            or "\uff1f" in text
            or any(
                token in lowered
                for token in (
                    "嗎",
                    "吗",
                    "是不是",
                    "有沒有",
                    "有没有",
                    "why ",
                    "how ",
                    "what ",
                )
            )
        ):
            return (text,)
        return ()

    @staticmethod
    def _waiting_candidates(summary: str) -> tuple[str, ...]:
        text = " ".join(summary.split())[:800]
        lowered = text.lower()
        cues = (
            "等下",
            "稍後",
            "稍后",
            "待會",
            "待会",
            "傳給",
            "传给",
            "upload",
            "上傳",
            "上传",
            "later",
            "wait",
            "will send",
        )
        return (text,) if text and any(cue in lowered for cue in cues) else ()

    def observe(
        self,
        *,
        owner_id: str,
        payload: SmartParticipationResolveRequest,
        result: ConversationSegmentationResult,
        now: datetime | None = None,
    ) -> ConversationRuntimeObservation:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        episode_views: list[ConversationEpisodeV3View] = []
        working_views: list[ThreadWorkingStateView] = []
        for segment in result.segments:
            membership = self.structure.current_membership(
                owner_id=owner_id,
                segment_id=segment.id,
            )
            thread_id = membership.thread_id if membership is not None else ""
            if thread_id:
                thread = next(
                    (
                        item
                        for item in self.structure.recent_threads_for_server(
                            owner_id=owner_id,
                            connection_id=payload.connection_id,
                            guild_id=payload.guild_id,
                            limit=50,
                            now=current,
                        )
                        if item.id == thread_id
                    ),
                    None,
                )
                entity_ids = thread.active_entity_ids if thread is not None else ()
                working = self.runtime.upsert_working_state(
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    channel_id=payload.channel_id,
                    discord_thread_id=payload.thread_id,
                    thread_id=thread_id,
                    active_entity_ids=entity_ids,
                    open_questions=self._question_candidates(segment.summary),
                    waiting_states=self._waiting_candidates(segment.summary),
                    expires_at=current + _DEFAULT_WORKING_TTL,
                    now=current,
                )
                working_views.append(working)
            else:
                entity_ids = ()
            episode = self.runtime.append_episode_segment(
                owner_id=owner_id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                discord_thread_id=payload.thread_id,
                conversation_thread_id=thread_id,
                segment_id=segment.id,
                source_message_ids=segment.message_ids,
                participant_ids=segment.participant_ids,
                entity_ids=entity_ids,
                summary=segment.summary,
                key_events=(segment.summary,) if segment.summary else (),
                now=current,
            )
            episode_views.append(episode)
        return ConversationRuntimeObservation(
            episodes=tuple(episode_views),
            working_states=tuple(working_views),
        )

    def checkpoint_thread(
        self,
        *,
        owner_id: str,
        thread_id: str,
        reason: str = "explicit_end",
        now: datetime | None = None,
    ) -> ConversationEpisodeV3View | None:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        episode = self.runtime.close_episode(
            owner_id=owner_id,
            conversation_thread_id=thread_id,
            reason=reason,
            now=current,
        )
        self.runtime.archive_working_state(
            owner_id=owner_id,
            thread_id=thread_id,
            now=current,
        )
        return episode

    def checkpoint_inactive(
        self,
        *,
        owner_id: str,
        inactivity: timedelta = _DEFAULT_EPISODE_INACTIVITY,
        now: datetime | None = None,
    ) -> tuple[ConversationEpisodeV3View, ...]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        cutoff = current - inactivity
        changed: list[ConversationEpisodeV3View] = []
        with self.runtime.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationEpisodeV3Record).where(
                        ConversationEpisodeV3Record.owner_id == owner_id,
                        ConversationEpisodeV3Record.status == "active",
                        ConversationEpisodeV3Record.updated_at <= cutoff,
                    )
                )
            )
            thread_ids: list[str] = []
            for record in records:
                record.status = "closed"
                record.checkpoint_reason = "inactivity"
                record.ended_at = current
                record.updated_at = current
                if record.conversation_thread_id:
                    thread_ids.append(record.conversation_thread_id)
            session.commit()
            changed.extend(self.runtime.episode_view(record) for record in records)
        for thread_id in thread_ids:
            self.runtime.archive_working_state(
                owner_id=owner_id,
                thread_id=thread_id,
                now=current,
            )
        self.runtime.expire_working_states(now=current)
        return tuple(changed)


__all__ = [
    "ConversationRuntimeCoordinator",
    "ConversationRuntimeObservation",
]
