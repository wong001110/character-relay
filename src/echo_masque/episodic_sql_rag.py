"""SAG-inspired deterministic Episode v3 indexing for query-time SQL expansion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from echo_masque.persistence.conversation_runtime_models import ConversationEpisodeV3Record
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.episodic_sql_rag_repository import EpisodicSqlRagRepository


def _decode(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _day_key(value: datetime) -> str:
    current = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return current.astimezone(UTC).date().isoformat()


@dataclass(slots=True)
class EpisodicSqlRagIndexer:
    """Maintain a read-optimized index derived from Episode v3; never own conversation truth."""

    repository: EpisodicSqlRagRepository

    def _link(
        self,
        episode: ConversationEpisodeV3Record,
        *,
        entity_type: str,
        canonical_key: str,
        label: str = "",
        confidence: float = 1.0,
        source_type: str = "deterministic",
    ) -> None:
        entity = self.repository.upsert_entity(
            owner_id=episode.owner_id,
            connection_id=episode.connection_id,
            guild_id=episode.guild_id,
            entity_type=entity_type,
            canonical_key=canonical_key,
            label=label or canonical_key,
            source_type=source_type,
        )
        self.repository.link_episode_entity(
            owner_id=episode.owner_id,
            episode_id=episode.id,
            entity_id=entity.id,
            confidence=confidence,
            source_type=source_type,
        )

    def index_episode(
        self,
        episode: ConversationEpisodeV3Record,
        *,
        deployment_id: str = "",
    ) -> None:
        """Index only deterministic provenance; semantic interpretation remains Evidence Graph work."""

        for actor_id in _decode(episode.participant_ids_json)[:30]:
            self._link(
                episode,
                entity_type="actor",
                canonical_key=f"discord_actor:{actor_id}",
                label=actor_id,
            )
        for media_ref in _decode(episode.media_refs_json)[:20]:
            self._link(
                episode,
                entity_type="media",
                canonical_key=media_ref,
                label=media_ref,
            )
        for entity_id in _decode(episode.entity_ids_json)[:30]:
            self._link(
                episode,
                entity_type="entity_ref",
                canonical_key=f"entity:{entity_id}",
                label=entity_id,
            )
        self._link(
            episode,
            entity_type="channel",
            canonical_key=f"discord_channel:{episode.channel_id}",
            label=episode.channel_id,
        )
        if episode.discord_thread_id:
            self._link(
                episode,
                entity_type="discord_thread",
                canonical_key=f"discord_thread:{episode.discord_thread_id}",
                label=episode.discord_thread_id,
            )
        self._link(
            episode,
            entity_type="time_day",
            canonical_key=f"utc_day:{_day_key(episode.ended_at)}",
            label=_day_key(episode.ended_at),
        )

        if not deployment_id:
            return
        with self.repository.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if (
                deployment is None
                or deployment.owner_id != episode.owner_id
                or deployment.connection_id != episode.connection_id
                or deployment.platform != episode.platform
            ):
                return
            character_card_id = deployment.character_card_id
        self.repository.grant_character_access(
            owner_id=episode.owner_id,
            character_card_id=character_card_id,
            deployment_id=deployment_id,
            episode_id=episode.id,
            access_reason="runtime_context",
            confidence=1.0,
            now=episode.updated_at,
        )


__all__ = ["EpisodicSqlRagIndexer"]
