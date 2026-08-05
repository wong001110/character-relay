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


def _metadata_semantics(
    name: str,
    description: str,
    tags: list[str],
) -> tuple[str, str, str, float]:
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
                        "Every Interaction Session participant must be an active "
                        "Discord deployment."
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

    def get_session(self, session_id: str, owner_id: str) -> DiscordInteractionSessionRecord | None:
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
            if interaction.completed_triggers >= interaction.maximum_triggers or (
                interaction.expires_at is not None and _aware(interaction.expires_at) <= now
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

    def get_sticker(self, record_id: str, owner_id: str) -> DiscordStickerSemanticRecord | None:
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
            "discord_interaction_sessions": int(getattr(session_result, "rowcount", 0) or 0),
            "discord_sticker_semantics": int(getattr(sticker_result, "rowcount", 0) or 0),
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
            "discord_interaction_sessions": int(getattr(session_result, "rowcount", 0) or 0),
            "discord_sticker_semantics": int(getattr(sticker_result, "rowcount", 0) or 0),
        }
