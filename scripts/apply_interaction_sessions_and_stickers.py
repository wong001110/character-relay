from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.strip() + "\n", encoding="utf-8")


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if old not in content:
        raise RuntimeError(f"Expected snippet not found in {path}: {old[:120]!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8")


write(
    "src/echo_masque/persistence/interaction_models.py",
    r'''
"""Persistence models for Discord interaction sessions and Sticker semantics."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from echo_masque.persistence.models import Base, utcnow


class DiscordInteractionSessionRecord(Base):
    """One bounded multi-character interaction configured from the Portal."""

    __tablename__ = "discord_interaction_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    guild_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    category_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    target_user_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    target_display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    participant_deployment_ids_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    session_type: Mapped[str] = mapped_column(String(32), default="roast", nullable=False)
    rounds_per_trigger: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    maximum_triggers: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completed_triggers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    intensity: Mapped[str] = mapped_column(String(24), default="playful", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="paused", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscordInteractionRunRecord(Base):
    """Idempotent execution record for one triggering Discord message."""

    __tablename__ = "discord_interaction_runs"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "source_message_id",
            name="uq_discord_interaction_run_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stop_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscordStickerSemanticRecord(Base):
    """Observed Discord Sticker metadata with optional owner-confirmed semantics."""

    __tablename__ = "discord_sticker_semantics"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "connection_id",
            "guild_id",
            "sticker_id",
            name="uq_discord_sticker_semantic",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    connection_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    guild_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    sticker_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), default="Sticker", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    format_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    asset_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    semantic_intent: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    semantic_emotion: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    semantic_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    semantic_source: Mapped[str] = mapped_column(
        String(32), default="discord_metadata", nullable=False
    )
    semantic_confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
''',
)

write(
    "src/echo_masque/persistence/interaction_repository.py",
    r'''
"""Persistence operations for Discord Interaction Sessions and Sticker semantics."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordDeploymentScopeRecord,
    DiscordServerProfileRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.interaction_models import (
    DiscordInteractionRunRecord,
    DiscordInteractionSessionRecord,
    DiscordStickerSemanticRecord,
)
from echo_masque.persistence.models import utcnow


class InteractionConflict(RuntimeError):
    """Raised when an Interaction Session configuration is invalid."""


def _encode(values: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(item.strip() for item in values if item.strip())))


def _decode(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [item.strip() for item in decoded if isinstance(item, str) and item.strip()]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _metadata_semantics(name: str, description: str, tags: list[str]) -> tuple[str, str, str, float]:
    details: list[str] = []
    if description.strip():
        details.append(description.strip())
    if tags:
        details.append(f"Discord tags: {', '.join(tags)}")
    if details:
        return (
            "sticker_reaction",
            "",
            f"Sticker named {name}. {'; '.join(details)}.",
            0.65,
        )
    return (
        "sticker_reaction",
        "",
        f"Sticker named {name}; no confirmed meaning has been configured yet.",
        0.35,
    )


class InteractionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def participant_ids(record: DiscordInteractionSessionRecord) -> list[str]:
        return _decode(record.participant_deployment_ids_json)

    @staticmethod
    def sticker_tags(record: DiscordStickerSemanticRecord) -> list[str]:
        return _decode(record.tags_json)

    def _validate_destination(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        category_id: str,
        participant_deployment_ids: list[str],
    ) -> None:
        if len(participant_deployment_ids) != 2 or len(set(participant_deployment_ids)) != 2:
            raise InteractionConflict("Roast Sessions require exactly two different deployments.")
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if (
                connection is None
                or connection.owner_id != owner_id
                or connection.platform != "discord"
            ):
                raise KeyError("connection")
            for deployment_id in participant_deployment_ids:
                deployment = session.get(CharacterDeploymentRecord, deployment_id)
                if (
                    deployment is None
                    or deployment.owner_id != owner_id
                    or deployment.connection_id != connection_id
                    or deployment.platform != "discord"
                    or deployment.status != "active"
                ):
                    raise InteractionConflict(
                        "Every Interaction Session participant must be an active Discord deployment."
                    )
                scope = session.get(DiscordDeploymentScopeRecord, deployment.id)
                if scope is None:
                    if (
                        deployment.workspace_id != guild_id
                        or deployment.channel_id != channel_id
                        or deployment.thread_id
                    ):
                        raise InteractionConflict(
                            "Every participant must be active in the selected Discord channel."
                        )
                    continue
                profile = session.get(DiscordServerProfileRecord, scope.server_profile_id)
                if profile is None or profile.guild_id != guild_id:
                    raise InteractionConflict(
                        "Every participant must use the selected Discord server."
                    )
                excluded_channels = set(_decode(profile.excluded_channel_ids_json)) | set(
                    _decode(scope.excluded_channel_ids_json)
                )
                excluded_categories = set(_decode(profile.excluded_category_ids_json)) | set(
                    _decode(scope.excluded_category_ids_json)
                )
                if channel_id in excluded_channels or (
                    category_id and category_id in excluded_categories
                ):
                    raise InteractionConflict(
                        "A selected participant is excluded from this Discord channel."
                    )

    def create_session(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        guild_name: str,
        channel_id: str,
        channel_name: str,
        category_id: str,
        target_user_id: str,
        target_display_name: str,
        participant_deployment_ids: list[str],
        rounds_per_trigger: int,
        maximum_triggers: int,
        cooldown_seconds: int,
        duration_seconds: int,
        intensity: str,
        status: str,
    ) -> DiscordInteractionSessionRecord:
        self._validate_destination(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            channel_id=channel_id,
            category_id=category_id,
            participant_deployment_ids=participant_deployment_ids,
        )
        now = utcnow()
        record = DiscordInteractionSessionRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            guild_name=guild_name,
            channel_id=channel_id,
            channel_name=channel_name,
            category_id=category_id,
            target_user_id=target_user_id,
            target_display_name=target_display_name,
            participant_deployment_ids_json=_encode(participant_deployment_ids),
            session_type="roast",
            rounds_per_trigger=rounds_per_trigger,
            maximum_triggers=maximum_triggers,
            completed_triggers=0,
            cooldown_seconds=cooldown_seconds,
            duration_seconds=duration_seconds,
            intensity=intensity,
            status=status,
            started_at=now if status == "active" else None,
            expires_at=(now + timedelta(seconds=duration_seconds)) if status == "active" else None,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_sessions(self, owner_id: str) -> list[DiscordInteractionSessionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(DiscordInteractionSessionRecord)
                    .where(DiscordInteractionSessionRecord.owner_id == owner_id)
                    .order_by(
                        DiscordInteractionSessionRecord.updated_at.desc(),
                        DiscordInteractionSessionRecord.id.desc(),
                    )
                )
            )

    def get_session(
        self, session_id: str, owner_id: str
    ) -> DiscordInteractionSessionRecord | None:
        with self.database.session() as session:
            record = session.get(DiscordInteractionSessionRecord, session_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def set_session_status(
        self,
        session_id: str,
        owner_id: str,
        status: str,
    ) -> DiscordInteractionSessionRecord | None:
        now = utcnow()
        with self.database.session() as session:
            record = session.get(DiscordInteractionSessionRecord, session_id)
            if record is None or record.owner_id != owner_id:
                return None
            if status == "active":
                if record.status in {"completed", "stopped"}:
                    record.completed_triggers = 0
                record.started_at = now
                record.expires_at = now + timedelta(seconds=record.duration_seconds)
                record.last_triggered_at = None
            record.status = status
            session.commit()
            session.refresh(record)
            return record

    def delete_session(self, session_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(DiscordInteractionSessionRecord, session_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.execute(
                delete(DiscordInteractionRunRecord).where(
                    DiscordInteractionRunRecord.session_id == session_id
                )
            )
            session.delete(record)
            session.commit()
            return True

    def claim_session(
        self,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        target_user_id: str,
        source_message_id: str,
    ) -> tuple[
        DiscordInteractionSessionRecord | None,
        DiscordInteractionRunRecord | None,
        bool,
    ]:
        now = utcnow()
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(DiscordInteractionSessionRecord)
                    .where(
                        DiscordInteractionSessionRecord.connection_id == connection_id,
                        DiscordInteractionSessionRecord.guild_id == guild_id,
                        DiscordInteractionSessionRecord.channel_id == channel_id,
                        DiscordInteractionSessionRecord.target_user_id == target_user_id,
                        DiscordInteractionSessionRecord.status == "active",
                    )
                    .order_by(DiscordInteractionSessionRecord.created_at)
                )
            )
            for record in records:
                if record.expires_at is not None and _aware(record.expires_at) <= now:
                    record.status = "completed"
                    continue
                if record.completed_triggers >= record.maximum_triggers:
                    record.status = "completed"
                    continue
                existing = session.scalar(
                    select(DiscordInteractionRunRecord).where(
                        DiscordInteractionRunRecord.session_id == record.id,
                        DiscordInteractionRunRecord.source_message_id == source_message_id,
                    )
                )
                if existing is not None:
                    session.commit()
                    return record, existing, False
                if record.last_triggered_at is not None:
                    next_allowed = _aware(record.last_triggered_at) + timedelta(
                        seconds=record.cooldown_seconds
                    )
                    if next_allowed > now:
                        continue
                run = DiscordInteractionRunRecord(
                    id=str(uuid4()),
                    owner_id=record.owner_id,
                    session_id=record.id,
                    source_message_id=source_message_id,
                )
                record.completed_triggers += 1
                record.last_triggered_at = now
                session.add(run)
                session.commit()
                session.refresh(record)
                session.refresh(run)
                return record, run, True
            session.commit()
            return None, None, False

    def complete_run(
        self,
        *,
        connection_id: str,
        run_id: str,
        status: str,
        reply_count: int,
        stop_reason: str,
    ) -> bool:
        now = utcnow()
        with self.database.session() as session:
            run = session.get(DiscordInteractionRunRecord, run_id)
            if run is None:
                return False
            interaction = session.get(DiscordInteractionSessionRecord, run.session_id)
            if interaction is None or interaction.connection_id != connection_id:
                return False
            run.status = status
            run.reply_count = reply_count
            run.stop_reason = stop_reason[:2000]
            run.completed_at = now
            if (
                interaction.completed_triggers >= interaction.maximum_triggers
                or (
                    interaction.expires_at is not None
                    and _aware(interaction.expires_at) <= now
                )
            ):
                interaction.status = "completed"
            session.commit()
            return True

    def list_stickers(
        self,
        owner_id: str,
        *,
        connection_id: str | None = None,
        guild_id: str | None = None,
    ) -> list[DiscordStickerSemanticRecord]:
        with self.database.session() as session:
            conditions = [DiscordStickerSemanticRecord.owner_id == owner_id]
            if connection_id:
                conditions.append(DiscordStickerSemanticRecord.connection_id == connection_id)
            if guild_id:
                conditions.append(DiscordStickerSemanticRecord.guild_id == guild_id)
            return list(
                session.scalars(
                    select(DiscordStickerSemanticRecord)
                    .where(*conditions)
                    .order_by(
                        DiscordStickerSemanticRecord.last_seen_at.desc(),
                        DiscordStickerSemanticRecord.name,
                    )
                )
            )

    def get_sticker(
        self, record_id: str, owner_id: str
    ) -> DiscordStickerSemanticRecord | None:
        with self.database.session() as session:
            record = session.get(DiscordStickerSemanticRecord, record_id)
            if record is None or record.owner_id != owner_id:
                return None
            return record

    def upsert_manual_sticker(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        sticker_id: str,
        name: str,
        description: str,
        tags: list[str],
        format_type: str,
        asset_url: str,
        semantic_intent: str,
        semantic_emotion: str,
        semantic_description: str,
    ) -> DiscordStickerSemanticRecord:
        now = utcnow()
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if (
                connection is None
                or connection.owner_id != owner_id
                or connection.platform != "discord"
            ):
                raise KeyError("connection")
            record = session.scalar(
                select(DiscordStickerSemanticRecord).where(
                    DiscordStickerSemanticRecord.owner_id == owner_id,
                    DiscordStickerSemanticRecord.connection_id == connection_id,
                    DiscordStickerSemanticRecord.guild_id == guild_id,
                    DiscordStickerSemanticRecord.sticker_id == sticker_id,
                )
            )
            if record is None:
                record = DiscordStickerSemanticRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    sticker_id=sticker_id,
                )
                session.add(record)
            record.name = name
            record.description = description
            record.tags_json = _encode(tags)
            record.format_type = format_type
            record.asset_url = asset_url
            record.semantic_intent = semantic_intent
            record.semantic_emotion = semantic_emotion
            record.semantic_description = semantic_description
            record.semantic_source = "manual"
            record.semantic_confidence = 1.0
            record.last_seen_at = now
            session.commit()
            session.refresh(record)
            return record

    def resolve_sticker(
        self,
        *,
        connection_id: str,
        guild_id: str,
        sticker_id: str,
        name: str,
        description: str,
        tags: list[str],
        format_type: str,
        asset_url: str,
    ) -> DiscordStickerSemanticRecord:
        now = utcnow()
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, connection_id)
            if connection is None or connection.platform != "discord":
                raise KeyError("connection")
            record = session.scalar(
                select(DiscordStickerSemanticRecord).where(
                    DiscordStickerSemanticRecord.owner_id == connection.owner_id,
                    DiscordStickerSemanticRecord.connection_id == connection_id,
                    DiscordStickerSemanticRecord.guild_id == guild_id,
                    DiscordStickerSemanticRecord.sticker_id == sticker_id,
                )
            )
            if record is None:
                record = DiscordStickerSemanticRecord(
                    id=str(uuid4()),
                    owner_id=connection.owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    sticker_id=sticker_id,
                )
                session.add(record)
            record.name = name or record.name
            record.description = description
            record.tags_json = _encode(tags)
            record.format_type = format_type
            record.asset_url = asset_url
            record.last_seen_at = now
            if record.semantic_source != "manual":
                intent, emotion, meaning, confidence = _metadata_semantics(
                    record.name,
                    description,
                    tags,
                )
                record.semantic_intent = intent
                record.semantic_emotion = emotion
                record.semantic_description = meaning
                record.semantic_source = "discord_metadata"
                record.semantic_confidence = confidence
            session.commit()
            session.refresh(record)
            return record

    def delete_sticker(self, record_id: str, owner_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(DiscordStickerSemanticRecord, record_id)
            if record is None or record.owner_id != owner_id:
                return False
            session.delete(record)
            session.commit()
            return True

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            run_result = session.execute(
                delete(DiscordInteractionRunRecord).where(
                    DiscordInteractionRunRecord.owner_id == owner_id
                )
            )
            session_result = session.execute(
                delete(DiscordInteractionSessionRecord).where(
                    DiscordInteractionSessionRecord.owner_id == owner_id
                )
            )
            sticker_result = session.execute(
                delete(DiscordStickerSemanticRecord).where(
                    DiscordStickerSemanticRecord.owner_id == owner_id
                )
            )
            session.commit()
        return {
            "discord_interaction_runs": int(getattr(run_result, "rowcount", 0) or 0),
            "discord_interaction_sessions": int(
                getattr(session_result, "rowcount", 0) or 0
            ),
            "discord_sticker_semantics": int(
                getattr(sticker_result, "rowcount", 0) or 0
            ),
        }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            run_result = session.execute(
                update(DiscordInteractionRunRecord)
                .where(DiscordInteractionRunRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session_result = session.execute(
                update(DiscordInteractionSessionRecord)
                .where(DiscordInteractionSessionRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            sticker_result = session.execute(
                update(DiscordStickerSemanticRecord)
                .where(DiscordStickerSemanticRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
        return {
            "discord_interaction_runs": int(getattr(run_result, "rowcount", 0) or 0),
            "discord_interaction_sessions": int(
                getattr(session_result, "rowcount", 0) or 0
            ),
            "discord_sticker_semantics": int(
                getattr(sticker_result, "rowcount", 0) or 0
            ),
        }
''',
)

write(
    "src/echo_masque/api/interaction_schemas.py",
    r'''
"""HTTP schemas for Interaction Sessions and the Discord Sticker Dictionary."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

InteractionStatus = Literal["active", "paused", "stopped", "completed"]
InteractionIntensity = Literal["light", "playful", "sharp"]


class InteractionSessionCreate(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    guild_name: str = Field(default="", max_length=160)
    channel_id: str = Field(min_length=1, max_length=200)
    channel_name: str = Field(default="", max_length=160)
    category_id: str = Field(default="", max_length=200)
    target_user_id: str = Field(min_length=2, max_length=200)
    target_display_name: str = Field(default="", max_length=160)
    participant_deployment_ids: list[str] = Field(min_length=2, max_length=2)
    rounds_per_trigger: int = Field(default=1, ge=1, le=3)
    maximum_triggers: int = Field(default=1, ge=1, le=5)
    cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    duration_seconds: int = Field(default=600, ge=60, le=86400)
    intensity: InteractionIntensity = "playful"
    status: Literal["active", "paused"] = "paused"


class InteractionSessionStatusUpdate(BaseModel):
    status: InteractionStatus


class InteractionSessionView(BaseModel):
    id: str
    connection_id: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    category_id: str
    target_user_id: str
    target_display_name: str
    participant_deployment_ids: list[str]
    participant_names: list[str]
    session_type: Literal["roast"] = "roast"
    rounds_per_trigger: int
    maximum_triggers: int
    completed_triggers: int
    maximum_replies_per_trigger: int
    cooldown_seconds: int
    duration_seconds: int
    intensity: InteractionIntensity
    status: InteractionStatus
    started_at: datetime | None
    expires_at: datetime | None
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StickerSemanticCreate(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)
    semantic_intent: str = Field(default="sticker_reaction", max_length=80)
    semantic_emotion: str = Field(default="", max_length=80)
    semantic_description: str = Field(min_length=1, max_length=2000)


class StickerSemanticView(BaseModel):
    id: str
    connection_id: str
    guild_id: str
    sticker_id: str
    name: str
    description: str
    tags: list[str]
    format_type: str
    asset_url: str
    semantic_intent: str
    semantic_emotion: str
    semantic_description: str
    semantic_source: Literal["manual", "discord_metadata", "unknown"]
    semantic_confidence: float
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime
''',
)

write(
    "src/echo_masque/api/routes/interactions.py",
    r'''
"""Owner-scoped Interaction Session and Discord Sticker Dictionary endpoints."""

from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.interaction_schemas import (
    InteractionSessionCreate,
    InteractionSessionStatusUpdate,
    InteractionSessionView,
    StickerSemanticCreate,
    StickerSemanticView,
)
from echo_masque.persistence import (
    DeploymentRepository,
    InteractionConflict,
    InteractionRepository,
    Repository,
)
from echo_masque.persistence.interaction_models import (
    DiscordInteractionSessionRecord,
    DiscordStickerSemanticRecord,
)

router = APIRouter(prefix="/api", tags=["interactions"])


def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def session_view(
    request: Request,
    record: DiscordInteractionSessionRecord,
) -> InteractionSessionView:
    ids = interaction_repository(request).participant_ids(record)
    names: list[str] = []
    deployments = deployment_repository(request)
    characters = character_repository(request)
    for deployment_id in ids:
        deployment = deployments.get_deployment(deployment_id, record.owner_id)
        if deployment is None:
            names.append("Unavailable deployment")
            continue
        card = characters.get_character_card(deployment.character_card_id, record.owner_id)
        names.append(card.display_name if card is not None else "Archived character")
    return InteractionSessionView(
        id=record.id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        guild_name=record.guild_name,
        channel_id=record.channel_id,
        channel_name=record.channel_name,
        category_id=record.category_id,
        target_user_id=record.target_user_id,
        target_display_name=record.target_display_name,
        participant_deployment_ids=ids,
        participant_names=names,
        rounds_per_trigger=record.rounds_per_trigger,
        maximum_triggers=record.maximum_triggers,
        completed_triggers=record.completed_triggers,
        maximum_replies_per_trigger=record.rounds_per_trigger * len(ids),
        cooldown_seconds=record.cooldown_seconds,
        duration_seconds=record.duration_seconds,
        intensity=record.intensity,  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        started_at=record.started_at,
        expires_at=record.expires_at,
        last_triggered_at=record.last_triggered_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def sticker_view(
    request: Request,
    record: DiscordStickerSemanticRecord,
) -> StickerSemanticView:
    return StickerSemanticView(
        id=record.id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        sticker_id=record.sticker_id,
        name=record.name,
        description=record.description,
        tags=interaction_repository(request).sticker_tags(record),
        format_type=record.format_type,
        asset_url=record.asset_url,
        semantic_intent=record.semantic_intent,
        semantic_emotion=record.semantic_emotion,
        semantic_description=record.semantic_description,
        semantic_source=record.semantic_source,  # type: ignore[arg-type]
        semantic_confidence=record.semantic_confidence,
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/interaction-sessions", response_model=list[InteractionSessionView])
def list_interaction_sessions(
    request: Request,
    user: CurrentUserDependency,
) -> list[InteractionSessionView]:
    return [
        session_view(request, item)
        for item in interaction_repository(request).list_sessions(user.id)
    ]


@router.post(
    "/interaction-sessions",
    response_model=InteractionSessionView,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction_session(
    payload: InteractionSessionCreate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionSessionView:
    try:
        record = interaction_repository(request).create_session(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    except InteractionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session_view(request, record)


@router.patch(
    "/interaction-sessions/{session_id}/status",
    response_model=InteractionSessionView,
)
def update_interaction_session_status(
    session_id: str,
    payload: InteractionSessionStatusUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> InteractionSessionView:
    record = interaction_repository(request).set_session_status(
        session_id,
        user.id,
        payload.status,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Interaction Session not found.")
    return session_view(request, record)


@router.delete(
    "/interaction-sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_interaction_session(
    session_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not interaction_repository(request).delete_session(session_id, user.id):
        raise HTTPException(status_code=404, detail="Interaction Session not found.")


@router.get(
    "/discord/sticker-dictionary",
    response_model=list[StickerSemanticView],
)
def list_sticker_dictionary(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
) -> list[StickerSemanticView]:
    return [
        sticker_view(request, item)
        for item in interaction_repository(request).list_stickers(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
        )
    ]


@router.put(
    "/discord/sticker-dictionary",
    response_model=StickerSemanticView,
)
def save_sticker_dictionary_entry(
    payload: StickerSemanticCreate,
    request: Request,
    user: CurrentUserDependency,
) -> StickerSemanticView:
    try:
        record = interaction_repository(request).upsert_manual_sticker(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return sticker_view(request, record)


@router.delete(
    "/discord/sticker-dictionary/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_sticker_dictionary_entry(
    record_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not interaction_repository(request).delete_sticker(record_id, user.id):
        raise HTTPException(status_code=404, detail="Sticker Dictionary entry not found.")
''',
)

# Connector schemas.
connector_schemas_path = "src/echo_masque/api/connector_schemas.py"
replace(
    connector_schemas_path,
    "class DiscordContextMessage(BaseModel):\n",
    r'''class DiscordStickerContent(BaseModel):
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)
    semantic_intent: str = Field(default="sticker_reaction", max_length=80)
    semantic_emotion: str = Field(default="", max_length=80)
    semantic_description: str = Field(default="", max_length=2000)
    semantic_source: Literal["manual", "discord_metadata", "unknown"] = "unknown"
    semantic_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DiscordStickerObservation(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    sticker_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    format_type: str = Field(default="unknown", max_length=40)
    asset_url: str = Field(default="", max_length=2000)


class DiscordInteractionSessionConnectorView(BaseModel):
    id: str
    participant_deployment_ids: list[str] = Field(min_length=2, max_length=2)
    rounds_per_trigger: int = Field(ge=1, le=3)
    intensity: Literal["light", "playful", "sharp"]
    target_user_id: str
    target_display_name: str


class DiscordInteractionClaimRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    guild_id: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    target_user_id: str = Field(min_length=1, max_length=200)
    source_message_id: str = Field(min_length=1, max_length=200)


class DiscordInteractionClaimView(BaseModel):
    claimed: bool = False
    run_id: str | None = None
    session: DiscordInteractionSessionConnectorView | None = None


class DiscordInteractionRunComplete(BaseModel):
    connection_id: str = Field(min_length=1, max_length=64)
    status: Literal["completed", "failed"]
    reply_count: int = Field(default=0, ge=0, le=30)
    stop_reason: str = Field(default="", max_length=2000)


class DiscordContextMessage(BaseModel):
''',
)
replace(
    connector_schemas_path,
    "    text: str = Field(default=\"\", max_length=10000)\n    created_at: datetime | None = None\n    is_bot: bool = False\n\n\nclass DiscordInboundMessage",
    "    text: str = Field(default=\"\", max_length=10000)\n"
    "    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)\n"
    "    created_at: datetime | None = None\n"
    "    is_bot: bool = False\n\n\nclass DiscordInboundMessage",
)
replace(
    connector_schemas_path,
    "    author_is_bot: bool = False\n    available_characters: list[str] = Field(default_factory=list, max_length=30)\n    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)\n",
    "    author_is_bot: bool = False\n"
    "    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)\n"
    "    available_characters: list[str] = Field(default_factory=list, max_length=30)\n"
    "    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)\n"
    "    interaction_session_id: str = Field(default=\"\", max_length=64)\n"
    "    interaction_type: str = Field(default=\"\", max_length=32)\n"
    "    interaction_intensity: str = Field(default=\"\", max_length=24)\n"
    "    interaction_round: int = Field(default=0, ge=0, le=10)\n"
    "    interaction_total_rounds: int = Field(default=0, ge=0, le=10)\n"
    "    interaction_position: int = Field(default=0, ge=0, le=10)\n"
    "    interaction_participant_count: int = Field(default=0, ge=0, le=10)\n"
    "    interaction_target_user_id: str = Field(default=\"\", max_length=200)\n"
    "    interaction_target_display_name: str = Field(default=\"\", max_length=160)\n",
)

# Persistence exports.
persistence_init = "src/echo_masque/persistence/__init__.py"
replace(
    persistence_init,
    "from echo_masque.persistence.matrix_repository import MatrixRepository\n",
    "from echo_masque.persistence.interaction_models import (\n"
    "    DiscordInteractionRunRecord,\n"
    "    DiscordInteractionSessionRecord,\n"
    "    DiscordStickerSemanticRecord,\n"
    ")\n"
    "from echo_masque.persistence.interaction_repository import (\n"
    "    InteractionConflict,\n"
    "    InteractionRepository,\n"
    ")\n"
    "from echo_masque.persistence.matrix_repository import MatrixRepository\n",
)
replace(
    persistence_init,
    '    "EvaluationRepository",\n',
    '    "EvaluationRepository",\n'
    '    "DiscordInteractionRunRecord",\n'
    '    "DiscordInteractionSessionRecord",\n'
    '    "DiscordStickerSemanticRecord",\n'
    '    "InteractionConflict",\n'
    '    "InteractionRepository",\n',
)

# Route exports.
routes_init = "src/echo_masque/api/routes/__init__.py"
replace(
    routes_init,
    "from echo_masque.api.routes.health import router as health_router\n",
    "from echo_masque.api.routes.health import router as health_router\n"
    "from echo_masque.api.routes.interactions import router as interactions_router\n",
)
replace(
    routes_init,
    '    "health_router",\n',
    '    "health_router",\n    "interactions_router",\n',
)

# Application wiring.
app_path = "src/echo_masque/api/__init__.py"
replace(
    app_path,
    "    health_router,\n",
    "    health_router,\n    interactions_router,\n",
)
replace(
    app_path,
    "    MatrixRepository,\n",
    "    InteractionRepository,\n    MatrixRepository,\n",
)
replace(
    app_path,
    "    discord_identity_repository = DiscordIdentityRepository(database)\n",
    "    discord_identity_repository = DiscordIdentityRepository(database)\n"
    "    interaction_repository = InteractionRepository(database)\n",
)
replace(
    app_path,
    "        discord_identity_repository,\n    )\n",
    "        discord_identity_repository,\n        interaction_repository,\n    )\n",
)
replace(
    app_path,
    "    app.state.discord_identity_repository = discord_identity_repository\n",
    "    app.state.discord_identity_repository = discord_identity_repository\n"
    "    app.state.interaction_repository = interaction_repository\n",
)
replace(
    app_path,
    "    app.include_router(discord_identities_router)\n",
    "    app.include_router(discord_identities_router)\n"
    "    app.include_router(interactions_router)\n",
)

# Account lifecycle.
lifecycle_path = "src/echo_masque/evaluation_lifecycle.py"
replace(
    lifecycle_path,
    "    EvaluationRepository,\n",
    "    EvaluationRepository,\n    InteractionRepository,\n",
)
replace(
    lifecycle_path,
    "        discord_identity_repository: DiscordIdentityRepository | None = None,\n",
    "        discord_identity_repository: DiscordIdentityRepository | None = None,\n"
    "        interaction_repository: InteractionRepository | None = None,\n",
)
replace(
    lifecycle_path,
    "        self.discord_identity_repository = (\n            discord_identity_repository or DiscordIdentityRepository(database)\n        )\n",
    "        self.discord_identity_repository = (\n            discord_identity_repository or DiscordIdentityRepository(database)\n        )\n"
    "        self.interaction_repository = interaction_repository or InteractionRepository(database)\n",
)
replace(
    lifecycle_path,
    "        evaluation_counts = self.evaluation_repository.delete_owner(user_id)\n",
    "        evaluation_counts = self.evaluation_repository.delete_owner(user_id)\n"
    "        interaction_counts = self.interaction_repository.delete_owner(user_id)\n",
)
replace(
    lifecycle_path,
    "            **evaluation_counts,\n            **identity_counts,\n",
    "            **evaluation_counts,\n            **interaction_counts,\n            **identity_counts,\n",
)
replace(
    lifecycle_path,
    "        identity_counts = self.discord_identity_repository.claim_owner(\n            \"local-user\",\n            actor_user_id,\n        )\n",
    "        identity_counts = self.discord_identity_repository.claim_owner(\n            \"local-user\",\n            actor_user_id,\n        )\n"
    "        interaction_counts = self.interaction_repository.claim_owner(\n"
    "            \"local-user\",\n"
    "            actor_user_id,\n"
    "        )\n",
)
replace(
    lifecycle_path,
    "            **deployment_counts,\n            **identity_counts,\n",
    "            **deployment_counts,\n            **identity_counts,\n            **interaction_counts,\n",
)

# Internal connector routes.
connectors_route = "src/echo_masque/api/routes/connectors.py"
replace(
    connectors_route,
    "    DiscordIdentityMode,\n",
    "    DiscordIdentityMode,\n"
    "    DiscordInteractionClaimRequest,\n"
    "    DiscordInteractionClaimView,\n"
    "    DiscordInteractionRunComplete,\n"
    "    DiscordInteractionSessionConnectorView,\n",
)
replace(
    connectors_route,
    "    DiscordServerCatalogSync,\n",
    "    DiscordServerCatalogSync,\n"
    "    DiscordStickerContent,\n"
    "    DiscordStickerObservation,\n",
)
replace(
    connectors_route,
    "    DiscordIdentityRepository,\n    Repository,\n",
    "    DiscordIdentityRepository,\n    InteractionRepository,\n    Repository,\n",
)
replace(
    connectors_route,
    "def character_repository(request: Request) -> Repository:\n",
    "def interaction_repository(request: Request) -> InteractionRepository:\n"
    "    return cast(InteractionRepository, request.app.state.interaction_repository)\n\n\n"
    "def character_repository(request: Request) -> Repository:\n",
)
insert_connector_routes = r'''

@router.post("/stickers/resolve", response_model=DiscordStickerContent)
def resolve_discord_sticker(
    payload: DiscordStickerObservation,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordStickerContent:
    _authorize_connector(request, authorization)
    try:
        record = interaction_repository(request).resolve_sticker(**payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return DiscordStickerContent(
        sticker_id=record.sticker_id,
        name=record.name,
        description=record.description,
        tags=interaction_repository(request).sticker_tags(record),
        format_type=record.format_type,
        asset_url=record.asset_url,
        semantic_intent=record.semantic_intent,
        semantic_emotion=record.semantic_emotion,
        semantic_description=record.semantic_description,
        semantic_source=record.semantic_source,
        semantic_confidence=record.semantic_confidence,
    )


@router.post("/interaction-sessions/claim", response_model=DiscordInteractionClaimView)
def claim_interaction_session(
    payload: DiscordInteractionClaimRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DiscordInteractionClaimView:
    _authorize_connector(request, authorization)
    interaction, run, claimed = interaction_repository(request).claim_session(
        **payload.model_dump()
    )
    if interaction is None or run is None:
        return DiscordInteractionClaimView()
    return DiscordInteractionClaimView(
        claimed=claimed,
        run_id=run.id,
        session=DiscordInteractionSessionConnectorView(
            id=interaction.id,
            participant_deployment_ids=interaction_repository(request).participant_ids(
                interaction
            ),
            rounds_per_trigger=interaction.rounds_per_trigger,
            intensity=interaction.intensity,
            target_user_id=interaction.target_user_id,
            target_display_name=interaction.target_display_name,
        ),
    )


@router.post(
    "/interaction-sessions/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def complete_interaction_run(
    run_id: str,
    payload: DiscordInteractionRunComplete,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    if not interaction_repository(request).complete_run(
        run_id=run_id,
        **payload.model_dump(),
    ):
        raise HTTPException(status_code=404, detail="Interaction run not found.")
'''
replace(
    connectors_route,
    "\n\n@router.post(\"/messages\", response_model=DiscordConnectorReplyView)\n",
    insert_connector_routes
    + "\n\n@router.post(\"/messages\", response_model=DiscordConnectorReplyView)\n",
)

# Runtime Sticker context and controlled interaction guidance.
runtime_path = "src/echo_masque/connector_runtime.py"
replace(
    runtime_path,
    "        mode = deployment.participation_mode\n",
    "        if payload.interaction_session_id:\n            return True\n"
    "        mode = deployment.participation_mode\n",
)
replace(
    runtime_path,
    "    @staticmethod\n    def _social_prompt(\n",
    r'''    @staticmethod
    def _context_message_content(message: DiscordContextMessage) -> str:
        parts: list[str] = []
        if message.text.strip():
            parts.append(message.text.strip())
        for sticker in message.stickers:
            meaning = (
                sticker.semantic_description.strip()
                or sticker.description.strip()
                or f"Sticker named {sticker.name} with no confirmed meaning."
            )
            parts.append(
                f"[Discord Sticker: {sticker.name}; interpreted meaning: {meaning}; "
                f"source: {sticker.semantic_source}; confidence: "
                f"{sticker.semantic_confidence:.2f}]"
            )
        return "\n".join(parts) or "(No readable text or interpreted Sticker content.)"

    @staticmethod
    def _social_prompt(
''',
)
replace(
    runtime_path,
    "                    text=payload.text,\n                    is_bot=payload.author_is_bot,\n",
    "                    text=payload.text,\n                    stickers=payload.stickers,\n                    is_bot=payload.author_is_bot,\n",
)
replace(
    runtime_path,
    "                f\"{item.author_display_name} | {item.author_id}]: {item.text}\"\n",
    "                f\"{item.author_display_name} | {item.author_id}]: \"\n"
    "                f\"{DiscordConnectorRuntime._context_message_content(item)}\"\n",
)
replace(
    runtime_path,
    "        tag_guidance: tuple[str, ...] = ()\n",
    r'''        interaction_guidance: tuple[str, ...] = ()
        if payload.interaction_session_id:
            intensity_rules = {
                "light": "Use mild teasing and keep the response easy to brush off.",
                "playful": "Use clear playful roasting with wit, not hostility.",
                "sharp": "Be more direct and cutting, while remaining non-abusive.",
            }
            interaction_guidance = (
                "This reply is part of a Portal-configured Roast Interaction Session.",
                f"The target member is {payload.interaction_target_display_name or payload.author_display_name} "
                f"with stable Discord user ID {payload.interaction_target_user_id or payload.author_id}.",
                f"You are speaker {payload.interaction_position} of "
                f"{payload.interaction_participant_count} in round "
                f"{payload.interaction_round} of {payload.interaction_total_rounds}.",
                intensity_rules.get(
                    payload.interaction_intensity,
                    "Use playful teasing without hostility.",
                ),
                "Build on earlier character replies in this Interaction Session without "
                "repeating the same joke. Do not Tag another character; speaking order is "
                "controlled by the Session.",
                "Roast only the target member's current words, choices, harmless habits, "
                "gameplay, coding mistakes, lateness, or self-directed jokes. Never target "
                "identity traits, nationality, race, religion, gender, sexuality, disability, "
                "health, body, appearance, trauma, family, private data, or threats. Do not "
                "invent personal facts or encourage harassment outside this bounded exchange.",
            )
        tag_guidance: tuple[str, ...] = ()
''',
)
replace(
    runtime_path,
    "                *tag_guidance,\n",
    "                *interaction_guidance,\n                *tag_guidance,\n",
)
replace(
    runtime_path,
    "                    f\"{payload.author_display_name} | {payload.author_id}]: {payload.text}\"\n",
    "                    f\"{payload.author_display_name} | {payload.author_id}]: \"\n"
    "                    f\"{DiscordConnectorRuntime._context_message_content(DiscordContextMessage(\"\n"
    "                    f\"message_id=payload.message_id, author_id=payload.author_id, \"\n"
    "                    f\"author_display_name=payload.author_display_name, text=payload.text, \"\n"
    "                    f\"stickers=payload.stickers, is_bot=payload.author_is_bot))}\"\n",
)

# TypeScript connector types.
types_path = "connectors/discord/src/types.ts"
replace(
    types_path,
    "export interface DiscordContextMessage {\n",
    r'''export interface DiscordStickerContent {
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
}

export interface DiscordStickerObservation {
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
}

export interface DiscordInteractionSession {
  id: string;
  participant_deployment_ids: string[];
  rounds_per_trigger: number;
  intensity: "light" | "playful" | "sharp";
  target_user_id: string;
  target_display_name: string;
}

export interface DiscordInteractionClaim {
  claimed: boolean;
  run_id: string | null;
  session: DiscordInteractionSession | null;
}

export interface DiscordInteractionClaimRequest {
  guild_id: string;
  channel_id: string;
  target_user_id: string;
  source_message_id: string;
}

export interface DiscordInteractionRunComplete {
  status: "completed" | "failed";
  reply_count: number;
  stop_reason: string;
}

export interface DiscordContextMessage {
''',
)
replace(
    types_path,
    "  text: string;\n  created_at?: string;\n  is_bot: boolean;\n}\n\nexport interface DiscordInboundMessage",
    "  text: string;\n  stickers: DiscordStickerContent[];\n  created_at?: string;\n"
    "  is_bot: boolean;\n}\n\nexport interface DiscordInboundMessage",
)
replace(
    types_path,
    "  author_is_bot: boolean;\n  available_characters: string[];\n  recent_messages: DiscordContextMessage[];\n",
    "  author_is_bot: boolean;\n"
    "  stickers: DiscordStickerContent[];\n"
    "  available_characters: string[];\n"
    "  recent_messages: DiscordContextMessage[];\n"
    "  interaction_session_id: string;\n"
    "  interaction_type: string;\n"
    "  interaction_intensity: string;\n"
    "  interaction_round: number;\n"
    "  interaction_total_rounds: number;\n"
    "  interaction_position: number;\n"
    "  interaction_participant_count: number;\n"
    "  interaction_target_user_id: string;\n"
    "  interaction_target_display_name: string;\n",
)

# Relay client methods.
relay_client = "connectors/discord/src/relayClient.ts"
replace(
    relay_client,
    "  ConnectorHeartbeat,\n",
    "  ConnectorHeartbeat,\n"
    "  DiscordInteractionClaim,\n"
    "  DiscordInteractionClaimRequest,\n"
    "  DiscordInteractionRunComplete,\n",
)
replace(
    relay_client,
    "  DiscordServerCatalogSync,\n",
    "  DiscordServerCatalogSync,\n"
    "  DiscordStickerContent,\n"
    "  DiscordStickerObservation,\n",
)
replace(
    relay_client,
    "  async processMessage(\n",
    r'''  async resolveSticker(
    payload: DiscordStickerObservation
  ): Promise<DiscordStickerContent> {
    return this.request<DiscordStickerContent>("/api/connectors/discord/stickers/resolve", {
      method: "POST",
      body: JSON.stringify({ connection_id: this.connectionId, ...payload })
    });
  }

  async claimInteraction(
    payload: DiscordInteractionClaimRequest
  ): Promise<DiscordInteractionClaim> {
    return this.request<DiscordInteractionClaim>(
      "/api/connectors/discord/interaction-sessions/claim",
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async completeInteractionRun(
    runId: string,
    payload: DiscordInteractionRunComplete
  ): Promise<void> {
    await this.request<void>(
      `/api/connectors/discord/interaction-sessions/runs/${runId}`,
      {
        method: "POST",
        body: JSON.stringify({ connection_id: this.connectionId, ...payload })
      }
    );
  }

  async processMessage(
''',
)

# Discord Connector orchestration.
index_path = "connectors/discord/src/index.ts"
replace(
    index_path,
    "  DiscordCatalogServer,\n  DiscordContextMessage,\n  DiscordDeployment\n",
    "  DiscordCatalogServer,\n"
    "  DiscordContextMessage,\n"
    "  DiscordDeployment,\n"
    "  DiscordInteractionClaim,\n"
    "  DiscordStickerContent\n",
)
replace(
    index_path,
    "function deploymentDisplayName(deployment: DiscordDeployment): string {\n",
    r'''async function resolveMessageStickers(
  message: Message<true>
): Promise<DiscordStickerContent[]> {
  const resolved: DiscordStickerContent[] = [];
  for (const sticker of message.stickers.values()) {
    const observation = {
      guild_id: message.guildId,
      sticker_id: sticker.id,
      name: sticker.name || "Sticker",
      description: sticker.description ?? "",
      tags: (sticker.tags ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      format_type: String(sticker.format),
      asset_url: sticker.url
    };
    try {
      resolved.push(await relay.resolveSticker(observation));
    } catch (error) {
      log("Unable to resolve Discord Sticker semantics.", {
        stickerId: sticker.id,
        error: error instanceof Error ? error.message : String(error)
      });
      resolved.push({
        ...observation,
        semantic_intent: "sticker_reaction",
        semantic_emotion: "",
        semantic_description: `Sticker named ${observation.name}; meaning is not configured.`,
        semantic_source: "unknown",
        semantic_confidence: 0
      });
    }
  }
  return resolved;
}

function deploymentDisplayName(deployment: DiscordDeployment): string {
''',
)
replace(
    index_path,
    "      author_is_bot: true,\n      available_characters:",
    "      author_is_bot: true,\n      stickers: [],\n      interaction_session_id: \"\",\n"
    "      interaction_type: \"\",\n      interaction_intensity: \"\",\n"
    "      interaction_round: 0,\n      interaction_total_rounds: 0,\n"
    "      interaction_position: 0,\n      interaction_participant_count: 0,\n"
    "      interaction_target_user_id: \"\",\n"
    "      interaction_target_display_name: \"\",\n      available_characters:",
)
replace(
    index_path,
    "      text: outgoingText,\n      created_at: new Date().toISOString(),\n      is_bot: true\n",
    "      text: outgoingText,\n      stickers: [],\n"
    "      created_at: new Date().toISOString(),\n      is_bot: true\n",
)
interaction_function = r'''

async function processInteractionSession(
  sourceMessage: Message<true>,
  claim: DiscordInteractionClaim,
  candidates: DiscordDeployment[],
  location: ReturnType<typeof channelLocation>,
  key: string,
  botUserId: string,
  authorDisplayName: string,
  originalText: string,
  stickers: DiscordStickerContent[]
): Promise<boolean> {
  const session = claim.session;
  const runId = claim.run_id;
  if (!claim.claimed || !session || !runId) return false;

  const ordered = session.participant_deployment_ids.map((deploymentId) =>
    candidates.find((item) => item.deployment_id === deploymentId)
  );
  if (ordered.some((item) => !item)) {
    await relay.completeInteractionRun(runId, {
      status: "failed",
      reply_count: 0,
      stop_reason: "One or more Session participants are not active in this channel."
    });
    log("Interaction Session could not resolve all participants.", {
      sessionId: session.id,
      runId,
      participantDeploymentIds: session.participant_deployment_ids
    });
    return true;
  }

  let replyCount = 0;
  try {
    for (let round = 1; round <= session.rounds_per_trigger; round += 1) {
      for (const [participantIndex, baseDeployment] of ordered.entries()) {
        if (!baseDeployment) continue;
        const deployment = resolveDeploymentLocation(baseDeployment, location);
        await sourceMessage.channel.sendTyping();
        const reply = await relay.processMessage({
          deployment_id: deployment.deployment_id,
          message_id: sourceMessage.id,
          guild_id: sourceMessage.guildId,
          guild_name: sourceMessage.guild.name,
          channel_id: location.channelId,
          channel_name: location.channelName,
          category_id: location.categoryId,
          thread_id: location.threadId,
          thread_name: location.threadName,
          author_id: sourceMessage.author.id,
          author_display_name: authorDisplayName,
          text:
            originalText ||
            "The target member sent interpreted Discord Sticker content without text.",
          mentioned_bot: false,
          replied_to_bot: false,
          smart_candidate: false,
          author_is_bot: false,
          stickers,
          available_characters: [],
          recent_messages: context.get(key),
          interaction_session_id: session.id,
          interaction_type: "roast",
          interaction_intensity: session.intensity,
          interaction_round: round,
          interaction_total_rounds: session.rounds_per_trigger,
          interaction_position: participantIndex + 1,
          interaction_participant_count: ordered.length,
          interaction_target_user_id: session.target_user_id,
          interaction_target_display_name:
            session.target_display_name || authorDisplayName
        });
        if (reply.action !== "reply" || !reply.text) continue;
        const normalizedReply = normalizeBotTagReply(
          candidates,
          reply.text,
          deployment.deployment_id,
          config.groupAddressAliases
        );
        const outgoingText = normalizedReply.displayText.trim();
        if (!outgoingText) continue;
        const sentMessageIds = await sendCharacterReply(
          sourceMessage,
          deployment,
          outgoingText,
          botUserId
        );
        await rememberSentMessages(deployment, sentMessageIds, sourceMessage.guildId);
        context.push(key, {
          message_id: sentMessageIds[0] ?? `relay-interaction-${Date.now()}`,
          author_id: `character:${deployment.character_card_id}`,
          author_display_name: deploymentDisplayName(deployment),
          text: outgoingText,
          stickers: [],
          created_at: new Date().toISOString(),
          is_bot: true
        });
        replyCount += 1;
        log("Interaction Session character reply sent to Discord.", {
          sessionId: session.id,
          runId,
          deploymentId: deployment.deployment_id,
          round,
          participantPosition: participantIndex + 1,
          replyCount,
          sourceMessageId: sourceMessage.id,
          sentMessageIds,
          latencyMs: reply.latency_ms ?? null
        });
      }
    }
    await relay.completeInteractionRun(runId, {
      status: "completed",
      reply_count: replyCount,
      stop_reason: replyCount ? "rounds_completed" : "no_character_replies"
    });
  } catch (error) {
    await relay
      .completeInteractionRun(runId, {
        status: "failed",
        reply_count: replyCount,
        stop_reason: error instanceof Error ? error.message : String(error)
      })
      .catch(() => undefined);
    throw error;
  }
  return true;
}
'''
replace(
    index_path,
    "\nasync function processMessage(message: Message): Promise<void> {\n",
    interaction_function + "\nasync function processMessage(message: Message): Promise<void> {\n",
)
replace(
    index_path,
    "  const contextMessage: DiscordContextMessage = {\n    message_id: guildMessage.id,\n    author_id: guildMessage.author.id,\n    author_display_name: authorDisplayName,\n    text: originalText,\n    created_at: guildMessage.createdAt.toISOString(),\n    is_bot: false\n  };\n\n  enqueue(key, async () => {\n    context.push(key, contextMessage);\n",
    r'''  enqueue(key, async () => {
    const stickers = await resolveMessageStickers(guildMessage);
    const contextMessage: DiscordContextMessage = {
      message_id: guildMessage.id,
      author_id: guildMessage.author.id,
      author_display_name: authorDisplayName,
      text: originalText,
      stickers,
      created_at: guildMessage.createdAt.toISOString(),
      is_bot: false
    };
    context.push(key, contextMessage);

    const interactionClaim = await relay.claimInteraction({
      guild_id: guildMessage.guildId,
      channel_id: location.channelId,
      target_user_id: guildMessage.author.id,
      source_message_id: guildMessage.id
    });
    if (
      await processInteractionSession(
        guildMessage,
        interactionClaim,
        candidates,
        location,
        key,
        botUser.id,
        authorDisplayName,
        originalText,
        stickers
      )
    ) {
      return;
    }
''',
)
replace(
    index_path,
    "          hasReadableText: Boolean(audience.text || originalText)\n",
    "          hasReadableText: Boolean(audience.text || originalText || stickers.length)\n",
)
replace(
    index_path,
    "        author_is_bot: false,\n        available_characters:",
    "        author_is_bot: false,\n        stickers,\n"
    "        interaction_session_id: \"\",\n        interaction_type: \"\",\n"
    "        interaction_intensity: \"\",\n        interaction_round: 0,\n"
    "        interaction_total_rounds: 0,\n        interaction_position: 0,\n"
    "        interaction_participant_count: 0,\n"
    "        interaction_target_user_id: \"\",\n"
    "        interaction_target_display_name: \"\",\n        available_characters:",
)
replace(
    index_path,
    "          \"The user addressed the character without additional readable text.\",\n",
    "          (stickers.length\n"
    "            ? \"The user addressed the character with interpreted Sticker content and no text.\"\n"
    "            : \"The user addressed the character without additional readable text.\"),\n",
)
# The second bot context push occurrence after normal reply.
replace(
    index_path,
    "        text: outgoingText,\n        created_at: new Date().toISOString(),\n        is_bot: true\n",
    "        text: outgoingText,\n        stickers: [],\n"
    "        created_at: new Date().toISOString(),\n        is_bot: true\n",
)
replace(
    index_path,
    "      custom_group_address_aliases: config.groupAddressAliases.length,\n",
    "      custom_group_address_aliases: config.groupAddressAliases.length,\n"
    "      interaction_sessions_enabled: true,\n"
    "      sticker_understanding_enabled: true,\n",
)

# Portal API and module.
write(
    "web/src/interactionApi.ts",
    r'''
export type InteractionStatus = "active" | "paused" | "stopped" | "completed";
export type InteractionIntensity = "light" | "playful" | "sharp";

export interface InteractionSession {
  id: string;
  connection_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  category_id: string;
  target_user_id: string;
  target_display_name: string;
  participant_deployment_ids: string[];
  participant_names: string[];
  session_type: "roast";
  rounds_per_trigger: number;
  maximum_triggers: number;
  completed_triggers: number;
  maximum_replies_per_trigger: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  status: InteractionStatus;
  started_at: string | null;
  expires_at: string | null;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InteractionSessionCreate {
  connection_id: string;
  guild_id: string;
  guild_name: string;
  channel_id: string;
  channel_name: string;
  category_id: string;
  target_user_id: string;
  target_display_name: string;
  participant_deployment_ids: string[];
  rounds_per_trigger: number;
  maximum_triggers: number;
  cooldown_seconds: number;
  duration_seconds: number;
  intensity: InteractionIntensity;
  status: "active" | "paused";
}

export interface StickerSemantic {
  id: string;
  connection_id: string;
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
  semantic_source: "manual" | "discord_metadata" | "unknown";
  semantic_confidence: number;
  last_seen_at: string;
  created_at: string;
  updated_at: string;
}

export interface StickerSemanticCreate {
  connection_id: string;
  guild_id: string;
  sticker_id: string;
  name: string;
  description: string;
  tags: string[];
  format_type: string;
  asset_url: string;
  semantic_intent: string;
  semantic_emotion: string;
  semantic_description: string;
}

async function errorMessage(response: Response): Promise<string> {
  const raw = await response.text();
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
  } catch {
    // Preserve raw response.
  }
  return raw || `Request failed with ${response.status}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const interactionApi = {
  listSessions: () => request<InteractionSession[]>("/api/interaction-sessions"),
  createSession: (payload: InteractionSessionCreate) =>
    request<InteractionSession>("/api/interaction-sessions", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateSessionStatus: (sessionId: string, status: InteractionStatus) =>
    request<InteractionSession>(`/api/interaction-sessions/${sessionId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status })
    }),
  deleteSession: (sessionId: string) =>
    request<void>(`/api/interaction-sessions/${sessionId}`, { method: "DELETE" }),
  listStickers: () =>
    request<StickerSemantic[]>("/api/discord/sticker-dictionary"),
  saveSticker: (payload: StickerSemanticCreate) =>
    request<StickerSemantic>("/api/discord/sticker-dictionary", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteSticker: (recordId: string) =>
    request<void>(`/api/discord/sticker-dictionary/${recordId}`, {
      method: "DELETE"
    })
};
''',
)

write(
    "web/src/InteractionSessionsPanel.tsx",
    r'''
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  deploymentApi,
  type CharacterDeployment,
  type DiscordServerCatalog,
  type PlatformConnection
} from "./deploymentApi";
import {
  interactionApi,
  type InteractionIntensity,
  type InteractionSession,
  type InteractionStatus,
  type StickerSemantic
} from "./interactionApi";

interface Props {
  demoMode: boolean;
  zh: boolean;
}

function discordUserId(value: string): string {
  return value.trim().replaceAll(/[<@!>]/gu, "");
}

function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}

export function InteractionSessionsPanel({ demoMode, zh }: Props) {
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [catalog, setCatalog] = useState<DiscordServerCatalog[]>([]);
  const [deployments, setDeployments] = useState<CharacterDeployment[]>([]);
  const [sessions, setSessions] = useState<InteractionSession[]>([]);
  const [stickers, setStickers] = useState<StickerSemantic[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionFormOpen, setSessionFormOpen] = useState(false);
  const [stickerFormOpen, setStickerFormOpen] = useState(false);
  const [editingSticker, setEditingSticker] = useState<StickerSemantic | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [guildId, setGuildId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [firstDeploymentId, setFirstDeploymentId] = useState("");
  const [secondDeploymentId, setSecondDeploymentId] = useState("");
  const [intensity, setIntensity] = useState<InteractionIntensity>("playful");

  async function load() {
    try {
      setLoading(true);
      const [nextConnections, nextCatalog, nextDeployments, nextSessions, nextStickers] =
        await Promise.all([
          deploymentApi.listConnections(),
          deploymentApi.listDiscordServerCatalog(),
          deploymentApi.listDeployments(),
          interactionApi.listSessions(),
          interactionApi.listStickers()
        ]);
      const discordConnections = nextConnections.filter((item) => item.platform === "discord");
      setConnections(discordConnections);
      setCatalog(nextCatalog);
      setDeployments(nextDeployments);
      setSessions(nextSessions);
      setStickers(nextStickers);
      setConnectionId((current) => current || discordConnections[0]?.id || "");
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const servers = catalog.filter((item) => item.connection_id === connectionId);
  const selectedServer = servers.find((item) => item.guild_id === guildId) ?? servers[0];
  const channels = selectedServer?.channels ?? [];
  const selectedChannel = channels.find((item) => item.id === channelId) ?? channels[0];
  const eligibleDeployments = useMemo(
    () =>
      deployments.filter(
        (item) =>
          item.platform === "discord" &&
          item.status === "active" &&
          item.connection_id === connectionId &&
          (!selectedServer || item.workspace_id === selectedServer.guild_id)
      ),
    [connectionId, deployments, selectedServer]
  );

  useEffect(() => {
    if (selectedServer && selectedServer.guild_id !== guildId) {
      setGuildId(selectedServer.guild_id);
    }
    if (selectedChannel && selectedChannel.id !== channelId) {
      setChannelId(selectedChannel.id);
    }
    if (!eligibleDeployments.some((item) => item.id === firstDeploymentId)) {
      setFirstDeploymentId(eligibleDeployments[0]?.id ?? "");
    }
    if (
      !eligibleDeployments.some(
        (item) => item.id === secondDeploymentId && item.id !== firstDeploymentId
      )
    ) {
      setSecondDeploymentId(
        eligibleDeployments.find((item) => item.id !== firstDeploymentId)?.id ?? ""
      );
    }
  }, [
    channelId,
    eligibleDeployments,
    firstDeploymentId,
    guildId,
    secondDeploymentId,
    selectedChannel,
    selectedServer
  ]);

  async function createSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const targetUserId = discordUserId(String(data.get("target_user_id") ?? ""));
    if (!selectedServer || !selectedChannel || !targetUserId) return;
    try {
      setWorking(true);
      await interactionApi.createSession({
        connection_id: connectionId,
        guild_id: selectedServer.guild_id,
        guild_name: selectedServer.guild_name,
        channel_id: selectedChannel.id,
        channel_name: selectedChannel.name,
        category_id: selectedChannel.category_id,
        target_user_id: targetUserId,
        target_display_name: String(data.get("target_display_name") ?? "").trim(),
        participant_deployment_ids: [firstDeploymentId, secondDeploymentId],
        rounds_per_trigger: Number(data.get("rounds_per_trigger") ?? 1),
        maximum_triggers: Number(data.get("maximum_triggers") ?? 1),
        cooldown_seconds: Number(data.get("cooldown_seconds") ?? 60),
        duration_seconds: Number(data.get("duration_minutes") ?? 10) * 60,
        intensity,
        status: String(data.get("status")) === "active" ? "active" : "paused"
      });
      setSessionFormOpen(false);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function setStatus(item: InteractionSession, status: InteractionStatus) {
    try {
      setWorking(true);
      await interactionApi.updateSessionStatus(item.id, status);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeSession(item: InteractionSession) {
    if (!window.confirm(zh ? "删除这个 Interaction Session？" : "Delete this Interaction Session?")) {
      return;
    }
    try {
      setWorking(true);
      await interactionApi.deleteSession(item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  function openStickerForm(item: StickerSemantic | null = null) {
    setEditingSticker(item);
    if (item) {
      setConnectionId(item.connection_id);
      setGuildId(item.guild_id);
    }
    setStickerFormOpen(true);
  }

  async function saveSticker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const stickerGuildId = String(data.get("guild_id") ?? guildId).trim();
    try {
      setWorking(true);
      await interactionApi.saveSticker({
        connection_id: String(data.get("connection_id") ?? connectionId),
        guild_id: stickerGuildId,
        sticker_id: String(data.get("sticker_id") ?? "").trim(),
        name: String(data.get("name") ?? "Sticker").trim(),
        description: String(data.get("description") ?? "").trim(),
        tags: String(data.get("tags") ?? "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        format_type: String(data.get("format_type") ?? "unknown").trim(),
        asset_url: String(data.get("asset_url") ?? "").trim(),
        semantic_intent:
          String(data.get("semantic_intent") ?? "sticker_reaction").trim() ||
          "sticker_reaction",
        semantic_emotion: String(data.get("semantic_emotion") ?? "").trim(),
        semantic_description: String(data.get("semantic_description") ?? "").trim()
      });
      setStickerFormOpen(false);
      setEditingSticker(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  async function removeSticker(item: StickerSemantic) {
    if (!window.confirm(zh ? "删除这个 Sticker 语义？" : "Delete this Sticker meaning?")) return;
    try {
      setWorking(true);
      await interactionApi.deleteSticker(item.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="interaction-module">
      {error && <p className="error-note interaction-error">{error}</p>}
      <section className="paper-sheet interaction-panel">
        <div className="panel-heading-row">
          <div>
            <p className="tape-label">INTERACTION SESSIONS</p>
            <h2>{zh ? "可控的多角色互动" : "Controlled multi-character interactions"}</h2>
            <p>
              {zh
                ? "Roast Session 只在指定 Channel、指定用户与固定轮次内运行。每一轮代表两个角色各回复一次。"
                : "Roast Sessions run only for one target member in one channel. Each round gives both characters one turn."}
            </p>
          </div>
          {!demoMode && (
            <button className="ink-button" onClick={() => setSessionFormOpen((value) => !value)}>
              {sessionFormOpen ? (zh ? "关闭" : "Close") : zh ? "+ 新 Session" : "+ New session"}
            </button>
          )}
        </div>

        {sessionFormOpen && !demoMode && (
          <form className="interaction-form" onSubmit={createSession}>
            <label>
              {zh ? "Discord Connector" : "Discord connector"}
              <select value={connectionId} onChange={(event) => setConnectionId(event.currentTarget.value)}>
                {connections.map((item) => (
                  <option value={item.id} key={item.id}>{item.display_name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "Server" : "Server"}
              <select value={selectedServer?.guild_id ?? ""} onChange={(event) => setGuildId(event.currentTarget.value)}>
                {servers.map((item) => (
                  <option value={item.guild_id} key={item.guild_id}>{item.guild_name}</option>
                ))}
              </select>
            </label>
            <label>
              Channel
              <select value={selectedChannel?.id ?? ""} onChange={(event) => setChannelId(event.currentTarget.value)}>
                {channels.map((item) => (
                  <option value={item.id} key={item.id}>#{item.name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "目标用户 ID 或 Mention" : "Target user ID or mention"}
              <input name="target_user_id" required placeholder="<@606232885489303603>" />
            </label>
            <label>
              {zh ? "目标显示名称" : "Target display name"}
              <input name="target_display_name" placeholder="501 Not Implemented" />
            </label>
            <label>
              {zh ? "第一位角色" : "First character"}
              <select value={firstDeploymentId} onChange={(event) => setFirstDeploymentId(event.currentTarget.value)}>
                {eligibleDeployments.map((item) => (
                  <option value={item.id} key={item.id}>{item.character_display_name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "第二位角色" : "Second character"}
              <select value={secondDeploymentId} onChange={(event) => setSecondDeploymentId(event.currentTarget.value)}>
                {eligibleDeployments.filter((item) => item.id !== firstDeploymentId).map((item) => (
                  <option value={item.id} key={item.id}>{item.character_display_name}</option>
                ))}
              </select>
            </label>
            <label>
              {zh ? "每次触发轮数" : "Rounds per trigger"}
              <input name="rounds_per_trigger" type="number" min="1" max="3" defaultValue="1" />
            </label>
            <label>
              {zh ? "最多触发次数" : "Maximum triggers"}
              <input name="maximum_triggers" type="number" min="1" max="5" defaultValue="1" />
            </label>
            <label>
              {zh ? "冷却秒数" : "Cooldown seconds"}
              <input name="cooldown_seconds" type="number" min="0" max="3600" defaultValue="60" />
            </label>
            <label>
              {zh ? "持续分钟" : "Duration minutes"}
              <input name="duration_minutes" type="number" min="1" max="1440" defaultValue="10" />
            </label>
            <label>
              {zh ? "强度" : "Intensity"}
              <select value={intensity} onChange={(event) => setIntensity(event.currentTarget.value as InteractionIntensity)}>
                <option value="light">Light</option>
                <option value="playful">Playful</option>
                <option value="sharp">Sharp</option>
              </select>
            </label>
            <label>
              {zh ? "建立后状态" : "Initial status"}
              <select name="status" defaultValue="paused">
                <option value="paused">Paused</option>
                <option value="active">Active</option>
              </select>
            </label>
            <div className="interaction-form-summary">
              <strong>{zh ? "固定顺序" : "Fixed order"}</strong>
              <span>
                {eligibleDeployments.find((item) => item.id === firstDeploymentId)?.character_display_name || "—"}
                {" → "}
                {eligibleDeployments.find((item) => item.id === secondDeploymentId)?.character_display_name || "—"}
              </span>
              <small>{zh ? "1 轮 = 两个角色各回复一次。" : "One round means one reply from each character."}</small>
            </div>
            <button className="ink-button" disabled={working || !firstDeploymentId || !secondDeploymentId}>
              {working ? (zh ? "保存中…" : "Saving…") : zh ? "建立 Roast Session" : "Create Roast Session"}
            </button>
          </form>
        )}

        {loading ? (
          <p>{zh ? "读取 Session…" : "Loading sessions…"}</p>
        ) : (
          <div className="interaction-card-grid">
            {sessions.map((item) => (
              <article className="interaction-card" key={item.id}>
                <div className="interaction-card-heading">
                  <strong>Roast Session</strong>
                  <span className={`deployment-status status-${item.status}`}>{item.status}</span>
                </div>
                <p><b>{zh ? "目标" : "Target"}:</b> {item.target_display_name || item.target_user_id}</p>
                <p><b>{zh ? "角色" : "Characters"}:</b> {item.participant_names.join(" → ")}</p>
                <p><b>{zh ? "位置" : "Location"}:</b> {item.guild_name} / #{item.channel_name}</p>
                <p><b>{zh ? "轮次" : "Rounds"}:</b> {item.rounds_per_trigger} · {item.maximum_replies_per_trigger} {zh ? "条回复/触发" : "replies/trigger"}</p>
                <p><b>{zh ? "触发" : "Triggers"}:</b> {item.completed_triggers} / {item.maximum_triggers}</p>
                <p><b>{zh ? "冷却" : "Cooldown"}:</b> {item.cooldown_seconds}s · {minutes(item.duration_seconds)}m</p>
                {!demoMode && (
                  <div className="interaction-actions">
                    {item.status !== "active" && (
                      <button className="paper-button" disabled={working} onClick={() => void setStatus(item, "active")}>{zh ? "启用" : "Activate"}</button>
                    )}
                    {item.status === "active" && (
                      <button className="paper-button" disabled={working} onClick={() => void setStatus(item, "paused")}>{zh ? "暂停" : "Pause"}</button>
                    )}
                    {!['stopped', 'completed'].includes(item.status) && (
                      <button className="paper-button" disabled={working} onClick={() => void setStatus(item, "stopped")}>{zh ? "停止" : "Stop"}</button>
                    )}
                    <button className="text-button danger-text" disabled={working} onClick={() => void removeSession(item)}>{zh ? "删除" : "Delete"}</button>
                  </div>
                )}
              </article>
            ))}
            {!sessions.length && <p>{zh ? "还没有 Interaction Session。" : "No Interaction Sessions yet."}</p>}
          </div>
        )}
      </section>

      <section className="paper-sheet interaction-panel">
        <div className="panel-heading-row">
          <div>
            <p className="tape-label">STICKER DICTIONARY</p>
            <h2>{zh ? "让角色理解用户发送的 Sticker" : "Teach characters what Discord Stickers mean"}</h2>
            <p>
              {zh
                ? "Connector 会自动记录见过的 Sticker。人工定义优先于名称、description 与 tags 推断。"
                : "The connector records observed Stickers automatically. Manual meanings override Discord metadata."}
            </p>
          </div>
          {!demoMode && (
            <button className="ink-button" onClick={() => stickerFormOpen ? setStickerFormOpen(false) : openStickerForm()}>
              {stickerFormOpen ? (zh ? "关闭" : "Close") : zh ? "+ 添加含义" : "+ Add meaning"}
            </button>
          )}
        </div>

        {stickerFormOpen && !demoMode && (
          <form className="interaction-form sticker-form" onSubmit={saveSticker} key={editingSticker?.id ?? "new-sticker"}>
            <label>
              Connector
              <select name="connection_id" defaultValue={editingSticker?.connection_id ?? connectionId}>
                {connections.map((item) => <option value={item.id} key={item.id}>{item.display_name}</option>)}
              </select>
            </label>
            <label>
              Server ID
              <input name="guild_id" required defaultValue={editingSticker?.guild_id ?? selectedServer?.guild_id ?? ""} />
            </label>
            <label>
              Sticker ID
              <input name="sticker_id" required readOnly={Boolean(editingSticker)} defaultValue={editingSticker?.sticker_id ?? ""} />
            </label>
            <label>
              Name
              <input name="name" required defaultValue={editingSticker?.name ?? ""} />
            </label>
            <label>
              Discord description
              <input name="description" defaultValue={editingSticker?.description ?? ""} />
            </label>
            <label>
              Discord tags
              <input name="tags" defaultValue={editingSticker?.tags.join(", ") ?? ""} />
            </label>
            <label>
              Intent
              <input name="semantic_intent" defaultValue={editingSticker?.semantic_intent ?? "sticker_reaction"} />
            </label>
            <label>
              Emotion
              <input name="semantic_emotion" defaultValue={editingSticker?.semantic_emotion ?? ""} placeholder="amused / shy / annoyed" />
            </label>
            <label className="interaction-form-wide">
              {zh ? "角色应理解的含义" : "Meaning supplied to characters"}
              <textarea name="semantic_description" required rows={3} defaultValue={editingSticker?.semantic_description ?? ""} />
            </label>
            <input type="hidden" name="format_type" value={editingSticker?.format_type ?? "unknown"} />
            <input type="hidden" name="asset_url" value={editingSticker?.asset_url ?? ""} />
            <button className="ink-button" disabled={working}>{working ? (zh ? "保存中…" : "Saving…") : zh ? "保存 Sticker 含义" : "Save Sticker meaning"}</button>
          </form>
        )}

        <div className="sticker-table">
          {stickers.map((item) => (
            <article className="sticker-row" key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <span>ID: {item.sticker_id}</span>
              </div>
              <div>
                <strong>{item.semantic_intent || "sticker_reaction"}</strong>
                <span>{item.semantic_emotion || "—"}</span>
              </div>
              <p>{item.semantic_description}</p>
              <div>
                <span className={`sticker-source source-${item.semantic_source}`}>{item.semantic_source}</span>
                <small>{Math.round(item.semantic_confidence * 100)}%</small>
              </div>
              {!demoMode && (
                <div className="interaction-actions">
                  <button className="paper-button" onClick={() => openStickerForm(item)}>{zh ? "编辑" : "Edit"}</button>
                  <button className="text-button danger-text" onClick={() => void removeSticker(item)}>{zh ? "删除" : "Delete"}</button>
                </div>
              )}
            </article>
          ))}
          {!loading && !stickers.length && <p>{zh ? "尚未观察到 Sticker。发送后会自动出现在这里。" : "No Stickers observed yet. They appear here after use."}</p>}
        </div>
      </section>
    </section>
  );
}
''',
)

write(
    "web/src/interactionSessions.css",
    r'''
.interaction-module {
  display: grid;
  gap: 24px;
  margin-top: 24px;
}

.interaction-panel {
  padding: 24px;
}

.interaction-panel h2 {
  margin: 4px 0 8px;
}

.interaction-panel .panel-heading-row {
  align-items: flex-start;
}

.interaction-error {
  margin: 0;
}

.interaction-form {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 20px 0;
  padding: 18px;
  border: 1px dashed var(--ink-soft, #9b9489);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.38);
}

.interaction-form label {
  display: grid;
  gap: 6px;
  font-size: 0.84rem;
  font-weight: 700;
}

.interaction-form input,
.interaction-form select,
.interaction-form textarea {
  width: 100%;
}

.interaction-form-wide,
.interaction-form-summary,
.interaction-form > .ink-button {
  grid-column: 1 / -1;
}

.interaction-form-summary {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(155, 124, 245, 0.08);
}

.interaction-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.interaction-card {
  padding: 16px;
  border: 1px solid rgba(86, 79, 69, 0.2);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.42);
}

.interaction-card p {
  margin: 8px 0;
}

.interaction-card-heading,
.interaction-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.interaction-actions {
  justify-content: flex-start;
  margin-top: 12px;
}

.sticker-table {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.sticker-row {
  display: grid;
  grid-template-columns: minmax(140px, 0.7fr) minmax(130px, 0.6fr) minmax(220px, 1.5fr) auto auto;
  gap: 14px;
  align-items: center;
  padding: 14px;
  border-bottom: 1px solid rgba(86, 79, 69, 0.16);
}

.sticker-row > div {
  display: grid;
  gap: 3px;
}

.sticker-row p {
  margin: 0;
}

.sticker-source {
  display: inline-flex;
  width: fit-content;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(90, 127, 104, 0.12);
  font-size: 0.76rem;
}

.source-manual {
  background: rgba(155, 124, 245, 0.14);
}

@media (max-width: 900px) {
  .interaction-form {
    grid-template-columns: 1fr 1fr;
  }
  .sticker-row {
    grid-template-columns: 1fr 1fr;
  }
  .sticker-row p,
  .sticker-row .interaction-actions {
    grid-column: 1 / -1;
  }
}

@media (max-width: 620px) {
  .interaction-form,
  .sticker-row {
    grid-template-columns: 1fr;
  }
}
''',
)

# Portal integration.
deployment_center = "web/src/DeploymentCenter.tsx"
replace(
    deployment_center,
    "import { useI18n } from \"./i18n\";\n",
    "import { useI18n } from \"./i18n\";\n"
    "import { InteractionSessionsPanel } from \"./InteractionSessionsPanel\";\n",
)
replace(
    deployment_center,
    "      </section>\n    </main>\n  );\n}\n",
    "      </section>\n"
    "      <InteractionSessionsPanel demoMode={demoMode} zh={zh} />\n"
    "    </main>\n  );\n}\n",
)
replace(
    "web/src/main.tsx",
    'import "./discordServerProfiles.css";\n',
    'import "./discordServerProfiles.css";\nimport "./interactionSessions.css";\n',
)

# Tests.
write(
    "tests/test_interaction_sessions_and_stickers.py",
    r'''
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.config import Settings
from echo_masque.connector_runtime import DiscordConnectorRuntime

ADMIN_EMAIL = "interaction-admin@example.com"
ADMIN_PASSWORD = "InteractionAdmin2026!"
CONNECTOR_SECRET = "interaction-connector-secret"


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=SecretStr(ADMIN_PASSWORD),
        bootstrap_admin_display_name="Interaction Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
    )


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CONNECTOR_SECRET}"}


def create_character(client: TestClient, name: str) -> dict[str, object]:
    response = client.post(
        "/api/characters",
        json={
            "target_id": "demo-stable",
            "display_name": name,
            "subtitle": "Interaction fixture",
            "subject_type": "companion",
            "persona_summary": f"{name} uses concise dry humor.",
            "traits": ["witty"],
            "tags": ["discord"],
            "expected_tone": "Playful and concise.",
            "forbidden_behaviors": ["invent private memories"],
            "memory_summary": "Use only supplied Discord context.",
            "preferred_suites": ["identity_integrity"],
            "portrait_variant": "lavender",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def seed(client: TestClient) -> tuple[dict[str, object], list[dict[str, object]]]:
    login(client)
    connection_response = client.post(
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Managed Discord",
            "connection_mode": "managed",
            "external_account_id": "bot-1",
            "status": "connected",
            "metadata": {},
        },
    )
    assert connection_response.status_code == 201
    connection = connection_response.json()
    deployments: list[dict[str, object]] = []
    for name in ("Ann", "Ning"):
        character = create_character(client, name)
        response = client.post(
            "/api/deployments",
            json={
                "character_card_id": character["id"],
                "connection_id": connection["id"],
                "workspace_id": "guild-1",
                "workspace_name": "Guild",
                "channel_id": "channel-1",
                "channel_name": "general",
                "thread_id": "",
                "thread_name": "",
                "participation_mode": "mention_and_reply",
                "memory_scope": "channel_isolated",
                "version_label": "Current",
                "sticker_count": 0,
                "status": "active",
            },
        )
        assert response.status_code == 201, response.text
        deployments.append(response.json())
    return connection, deployments


def test_roast_session_claim_is_bounded_and_idempotent(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "interaction.db")))
    connection, deployments = seed(client)
    created = client.post(
        "/api/interaction-sessions",
        json={
            "connection_id": connection["id"],
            "guild_id": "guild-1",
            "guild_name": "Guild",
            "channel_id": "channel-1",
            "channel_name": "general",
            "category_id": "",
            "target_user_id": "user-1",
            "target_display_name": "Target",
            "participant_deployment_ids": [deployments[0]["id"], deployments[1]["id"]],
            "rounds_per_trigger": 2,
            "maximum_triggers": 1,
            "cooldown_seconds": 0,
            "duration_seconds": 600,
            "intensity": "playful",
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["maximum_replies_per_trigger"] == 4

    claim_payload = {
        "connection_id": connection["id"],
        "guild_id": "guild-1",
        "channel_id": "channel-1",
        "target_user_id": "user-1",
        "source_message_id": "message-1",
    }
    first = client.post(
        "/api/connectors/discord/interaction-sessions/claim",
        json=claim_payload,
        headers=headers(),
    )
    assert first.status_code == 200, first.text
    assert first.json()["claimed"] is True
    assert first.json()["session"]["participant_deployment_ids"] == [
        deployments[0]["id"],
        deployments[1]["id"],
    ]

    duplicate = client.post(
        "/api/connectors/discord/interaction-sessions/claim",
        json=claim_payload,
        headers=headers(),
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["claimed"] is False

    completed = client.post(
        f"/api/connectors/discord/interaction-sessions/runs/{first.json()['run_id']}",
        json={
            "connection_id": connection["id"],
            "status": "completed",
            "reply_count": 4,
            "stop_reason": "rounds_completed",
        },
        headers=headers(),
    )
    assert completed.status_code == 204
    listed = client.get("/api/interaction-sessions")
    assert listed.json()[0]["status"] == "completed"


def test_sticker_metadata_is_observed_and_manual_semantics_win(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "stickers.db")))
    connection, _ = seed(client)
    observation = {
        "connection_id": connection["id"],
        "guild_id": "guild-1",
        "sticker_id": "sticker-1",
        "name": "side_eye_cat",
        "description": "A cat looking doubtful",
        "tags": ["doubt", "teasing"],
        "format_type": "png",
        "asset_url": "https://cdn.discordapp.com/stickers/sticker-1.png",
    }
    observed = client.post(
        "/api/connectors/discord/stickers/resolve",
        json=observation,
        headers=headers(),
    )
    assert observed.status_code == 200, observed.text
    assert observed.json()["semantic_source"] == "discord_metadata"
    assert "doubt" in observed.json()["semantic_description"]

    manual = client.put(
        "/api/discord/sticker-dictionary",
        json={
            **observation,
            "semantic_intent": "playful_disbelief",
            "semantic_emotion": "amused",
            "semantic_description": "The user is playfully saying they do not believe the claim.",
        },
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["semantic_source"] == "manual"

    resolved_again = client.post(
        "/api/connectors/discord/stickers/resolve",
        json={**observation, "description": "Changed metadata"},
        headers=headers(),
    )
    assert resolved_again.status_code == 200
    assert resolved_again.json()["semantic_intent"] == "playful_disbelief"
    assert resolved_again.json()["semantic_source"] == "manual"


def test_social_prompt_explains_stickers_and_bounded_roast() -> None:
    sticker = {
        "sticker_id": "sticker-1",
        "name": "side_eye_cat",
        "description": "",
        "tags": ["doubt"],
        "format_type": "png",
        "asset_url": "",
        "semantic_intent": "playful_disbelief",
        "semantic_emotion": "amused",
        "semantic_description": "The member is playfully expressing disbelief.",
        "semantic_source": "manual",
        "semantic_confidence": 1.0,
    }
    payload = DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="message-1",
        guild_id="guild-1",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        author_id="user-1",
        author_display_name="Target",
        stickers=[sticker],
        recent_messages=[
            DiscordContextMessage(
                message_id="message-1",
                author_id="user-1",
                author_display_name="Target",
                stickers=[sticker],
            )
        ],
        interaction_session_id="session-1",
        interaction_type="roast",
        interaction_intensity="playful",
        interaction_round=1,
        interaction_total_rounds=2,
        interaction_position=1,
        interaction_participant_count=2,
        interaction_target_user_id="user-1",
        interaction_target_display_name="Target",
    )
    prompt = DiscordConnectorRuntime._social_prompt(character_name="Ann", payload=payload)
    assert "playfully expressing disbelief" in prompt
    assert "Portal-configured Roast Interaction Session" in prompt
    assert "Never target identity traits" in prompt
    assert "speaker 1 of 2" in prompt
''',
)

# Documentation.
replace(
    "connectors/discord/README.md",
    "## Runtime behavior\n",
    r'''## Interaction Sessions and Sticker understanding

The Portal includes a bounded `Interaction Sessions` module. The initial Session type is
`roast`, with exactly two active Discord character deployments, a fixed speaking order,
1-3 rounds per trigger, a target Discord user ID, trigger limit, cooldown, duration, and
light/playful/sharp intensity. One round means each configured character receives one turn.
The Connector claims each target message idempotently and reports the completed run.

Incoming Discord Stickers are resolved through `/api/connectors/discord/stickers/resolve`.
Observed metadata is cached in the Portal's Sticker Dictionary. Owner-confirmed meanings are
marked `manual` and always override subsequent Discord name/description/tag metadata. Sticker
semantics are stored in shared channel context, so Sticker-only messages can be understood by
characters and by Interaction Sessions.

## Runtime behavior
''',
)

# Remove the generator after it has run.
Path(__file__).unlink()
