"""Persistence for SAG-inspired episodic SQL retrieval structures."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, delete, func, select, update

from echo_masque.persistence.conversation_episode_models import ConversationEpisodeRecord
from echo_masque.persistence.database import Database
from echo_masque.persistence.episodic_sql_rag_models import (
    CharacterEpisodeAccessRecord,
    ConversationEntityRecord,
    ConversationEpisodeEntityRecord,
)

_EXPANSION_ENTITY_TYPES = (
    "topic",
    "actor",
    "character",
    "media",
    "concept",
    "project",
    "goal",
    "preference",
    "product",
    "organization",
    "location",
    "named_entity",
)


class EpisodicSqlRagRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_entity(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        entity_type: str,
        canonical_key: str,
        label: str = "",
        source_type: str = "deterministic",
    ) -> ConversationEntityRecord:
        now = datetime.now(UTC)
        key = canonical_key.strip()[:320]
        kind = entity_type.strip()[:40]
        if not key or not kind:
            raise ValueError("Entity type/key are required.")
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationEntityRecord).where(
                    ConversationEntityRecord.owner_id == owner_id,
                    ConversationEntityRecord.connection_id == connection_id,
                    ConversationEntityRecord.guild_id == guild_id,
                    ConversationEntityRecord.entity_type == kind,
                    ConversationEntityRecord.canonical_key == key,
                )
            )
            if record is None:
                record = ConversationEntityRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    entity_type=kind,
                    canonical_key=key,
                    label=label.strip()[:320],
                    source_type=source_type.strip()[:40] or "deterministic",
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                if label.strip():
                    record.label = label.strip()[:320]
                record.updated_at = now
            session.commit()
            session.refresh(record)
            return record

    def link_episode_entity(
        self,
        *,
        owner_id: str,
        episode_id: str,
        entity_id: str,
        confidence: float = 1.0,
        source_type: str = "deterministic",
    ) -> ConversationEpisodeEntityRecord:
        with self.database.session() as session:
            record = session.scalar(
                select(ConversationEpisodeEntityRecord).where(
                    ConversationEpisodeEntityRecord.episode_id == episode_id,
                    ConversationEpisodeEntityRecord.entity_id == entity_id,
                )
            )
            if record is None:
                record = ConversationEpisodeEntityRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    episode_id=episode_id,
                    entity_id=entity_id,
                    confidence=max(0.0, min(1.0, confidence)),
                    source_type=source_type.strip()[:40] or "deterministic",
                )
                session.add(record)
            else:
                record.confidence = max(record.confidence, max(0.0, min(1.0, confidence)))
            session.commit()
            session.refresh(record)
            return record

    def grant_character_access(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        deployment_id: str,
        episode_id: str,
        access_reason: str = "runtime_context",
        confidence: float = 1.0,
        now: datetime | None = None,
    ) -> CharacterEpisodeAccessRecord:
        current = now or datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterEpisodeAccessRecord).where(
                    CharacterEpisodeAccessRecord.owner_id == owner_id,
                    CharacterEpisodeAccessRecord.character_card_id == character_card_id,
                    CharacterEpisodeAccessRecord.episode_id == episode_id,
                )
            )
            if record is None:
                record = CharacterEpisodeAccessRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                    deployment_id=deployment_id[:64],
                    episode_id=episode_id,
                    access_reason=access_reason[:60],
                    confidence=max(0.0, min(1.0, confidence)),
                    first_observed_at=current,
                    last_observed_at=current,
                )
                session.add(record)
            else:
                record.deployment_id = deployment_id[:64]
                record.access_reason = access_reason[:60]
                record.confidence = max(record.confidence, max(0.0, min(1.0, confidence)))
                record.last_observed_at = current
            session.commit()
            session.refresh(record)
            return record

    def accessible_episode_ids(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        episode_ids: tuple[str, ...] = (),
        limit: int = 500,
    ) -> tuple[str, ...]:
        with self.database.session() as session:
            query = select(CharacterEpisodeAccessRecord.episode_id).where(
                CharacterEpisodeAccessRecord.owner_id == owner_id,
                CharacterEpisodeAccessRecord.character_card_id == character_card_id,
            )
            if episode_ids:
                query = query.where(CharacterEpisodeAccessRecord.episode_id.in_(episode_ids))
            values = list(
                session.scalars(
                    query.order_by(CharacterEpisodeAccessRecord.last_observed_at.desc()).limit(
                        max(1, min(limit, 2000))
                    )
                )
            )
        return tuple(dict.fromkeys(values))

    def accessible_episodes(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        limit: int = 240,
    ) -> tuple[ConversationEpisodeRecord, ...]:
        """Return only server Episodes this Character is proven to have perceived."""

        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationEpisodeRecord)
                    .join(
                        CharacterEpisodeAccessRecord,
                        and_(
                            CharacterEpisodeAccessRecord.episode_id
                            == ConversationEpisodeRecord.id,
                            CharacterEpisodeAccessRecord.owner_id == owner_id,
                            CharacterEpisodeAccessRecord.character_card_id == character_card_id,
                        ),
                    )
                    .where(
                        ConversationEpisodeRecord.owner_id == owner_id,
                        ConversationEpisodeRecord.connection_id == connection_id,
                        ConversationEpisodeRecord.guild_id == guild_id,
                    )
                    .order_by(ConversationEpisodeRecord.ended_at.desc())
                    .limit(max(1, min(limit, 1000)))
                )
            )
        return tuple(records)

    def episodes_by_ids(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        episode_ids: tuple[str, ...],
    ) -> tuple[ConversationEpisodeRecord, ...]:
        if not episode_ids:
            return ()
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationEpisodeRecord)
                    .join(
                        CharacterEpisodeAccessRecord,
                        and_(
                            CharacterEpisodeAccessRecord.episode_id
                            == ConversationEpisodeRecord.id,
                            CharacterEpisodeAccessRecord.owner_id == owner_id,
                            CharacterEpisodeAccessRecord.character_card_id == character_card_id,
                        ),
                    )
                    .where(
                        ConversationEpisodeRecord.owner_id == owner_id,
                        ConversationEpisodeRecord.connection_id == connection_id,
                        ConversationEpisodeRecord.guild_id == guild_id,
                        ConversationEpisodeRecord.id.in_(episode_ids),
                    )
                    .order_by(ConversationEpisodeRecord.ended_at.desc())
                )
            )
        return tuple(records)

    def entity_ids_for_episodes(
        self,
        *,
        owner_id: str,
        episode_ids: tuple[str, ...],
        max_entity_degree: int = 80,
        entity_types: tuple[str, ...] = _EXPANSION_ENTITY_TYPES,
    ) -> tuple[str, ...]:
        if not episode_ids:
            return ()
        with self.database.session() as session:
            degree = (
                select(
                    ConversationEpisodeEntityRecord.entity_id.label("entity_id"),
                    func.count(ConversationEpisodeEntityRecord.episode_id).label("degree"),
                )
                .where(ConversationEpisodeEntityRecord.owner_id == owner_id)
                .group_by(ConversationEpisodeEntityRecord.entity_id)
                .subquery()
            )
            values = list(
                session.scalars(
                    select(ConversationEpisodeEntityRecord.entity_id)
                    .join(degree, degree.c.entity_id == ConversationEpisodeEntityRecord.entity_id)
                    .join(
                        ConversationEntityRecord,
                        ConversationEntityRecord.id == ConversationEpisodeEntityRecord.entity_id,
                    )
                    .where(
                        ConversationEpisodeEntityRecord.owner_id == owner_id,
                        ConversationEpisodeEntityRecord.episode_id.in_(episode_ids),
                        ConversationEntityRecord.entity_type.in_(entity_types),
                        degree.c.degree <= max(2, max_entity_degree),
                    )
                )
            )
        return tuple(dict.fromkeys(values))

    def expand_episode_ids(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        seed_episode_ids: tuple[str, ...],
        connection_id: str,
        guild_id: str,
        channel_id: str = "",
        thread_id: str = "",
        max_entity_degree: int = 80,
        limit: int = 80,
    ) -> tuple[str, ...]:
        """One bounded event→entity→event expansion constrained by Character perception."""

        entity_ids = self.entity_ids_for_episodes(
            owner_id=owner_id,
            episode_ids=seed_episode_ids,
            max_entity_degree=max_entity_degree,
        )
        if not entity_ids:
            return seed_episode_ids
        with self.database.session() as session:
            query = (
                select(ConversationEpisodeRecord.id)
                .join(
                    ConversationEpisodeEntityRecord,
                    ConversationEpisodeEntityRecord.episode_id == ConversationEpisodeRecord.id,
                )
                .join(
                    CharacterEpisodeAccessRecord,
                    and_(
                        CharacterEpisodeAccessRecord.episode_id == ConversationEpisodeRecord.id,
                        CharacterEpisodeAccessRecord.owner_id == owner_id,
                        CharacterEpisodeAccessRecord.character_card_id == character_card_id,
                    ),
                )
                .where(
                    ConversationEpisodeRecord.owner_id == owner_id,
                    ConversationEpisodeRecord.connection_id == connection_id,
                    ConversationEpisodeRecord.guild_id == guild_id,
                    ConversationEpisodeEntityRecord.entity_id.in_(entity_ids),
                )
            )
            if channel_id:
                query = query.where(ConversationEpisodeRecord.channel_id == channel_id)
            if thread_id:
                query = query.where(ConversationEpisodeRecord.thread_id == thread_id)
            values = list(
                session.scalars(
                    query.order_by(ConversationEpisodeRecord.ended_at.desc()).limit(
                        max(1, min(limit, 300))
                    )
                )
            )
        return tuple(dict.fromkeys((*seed_episode_ids, *values)))

    def entities_for_episode(
        self,
        *,
        owner_id: str,
        episode_id: str,
    ) -> tuple[ConversationEntityRecord, ...]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ConversationEntityRecord)
                    .join(
                        ConversationEpisodeEntityRecord,
                        ConversationEpisodeEntityRecord.entity_id == ConversationEntityRecord.id,
                    )
                    .where(
                        ConversationEpisodeEntityRecord.owner_id == owner_id,
                        ConversationEpisodeEntityRecord.episode_id == episode_id,
                    )
                    .order_by(ConversationEntityRecord.entity_type, ConversationEntityRecord.label)
                )
            )
        return tuple(records)

    def delete_episode(self, *, owner_id: str, episode_id: str) -> None:
        with self.database.session() as session:
            session.execute(
                delete(CharacterEpisodeAccessRecord).where(
                    CharacterEpisodeAccessRecord.owner_id == owner_id,
                    CharacterEpisodeAccessRecord.episode_id == episode_id,
                )
            )
            session.execute(
                delete(ConversationEpisodeEntityRecord).where(
                    ConversationEpisodeEntityRecord.owner_id == owner_id,
                    ConversationEpisodeEntityRecord.episode_id == episode_id,
                )
            )
            session.commit()

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            access_result = session.execute(
                delete(CharacterEpisodeAccessRecord).where(
                    CharacterEpisodeAccessRecord.owner_id == owner_id
                )
            )
            incidence_result = session.execute(
                delete(ConversationEpisodeEntityRecord).where(
                    ConversationEpisodeEntityRecord.owner_id == owner_id
                )
            )
            entity_result = session.execute(
                delete(ConversationEntityRecord).where(
                    ConversationEntityRecord.owner_id == owner_id
                )
            )
            session.commit()
            return {
                "character_episode_access": int(getattr(access_result, "rowcount", 0) or 0),
                "conversation_episode_entities": int(
                    getattr(incidence_result, "rowcount", 0) or 0
                ),
                "conversation_entities": int(getattr(entity_result, "rowcount", 0) or 0),
            }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            access_result = session.execute(
                update(CharacterEpisodeAccessRecord)
                .where(CharacterEpisodeAccessRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            incidence_result = session.execute(
                update(ConversationEpisodeEntityRecord)
                .where(ConversationEpisodeEntityRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            entity_result = session.execute(
                update(ConversationEntityRecord)
                .where(ConversationEntityRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return {
                "character_episode_access": int(getattr(access_result, "rowcount", 0) or 0),
                "conversation_episode_entities": int(
                    getattr(incidence_result, "rowcount", 0) or 0
                ),
                "conversation_entities": int(getattr(entity_result, "rowcount", 0) or 0),
            }


__all__ = ["EpisodicSqlRagRepository"]
