"""Resolve a Character's optional expression intent after generation, without a model."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select

from echo_masque.api.expression_schemas import ExpressionCandidate
from echo_masque.expression_retrieval import rank_expression_resources
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import PlatformConnectionRecord
from echo_masque.persistence.deployment_repository import DeploymentRepository
from echo_masque.persistence.expression_models import (
    DiscordExpressionSemanticRecord,
    ExpressionUsageRecord,
)
from echo_masque.persistence.expression_repository import ExpressionRepository
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.room_routing import RoomScope
from echo_masque.room_sources import scope_key
from echo_masque.smart_output import DiscordSmartOutputView, SmartEmojiPart, SmartTextPart
from echo_masque.sparse_retrieval import normalize_text
from echo_masque.tool_runtime import ToolExecutionContext


class ExpressionIntentResolver:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.catalog = ExpressionRepository(database)
        self.deployments = DeploymentRepository(database)
        self.rooms = RoomRepository(database)

    @staticmethod
    def without_resource(
        output: DiscordSmartOutputView,
        reason: Literal["no_match", "scope_unavailable"] = "no_match",
    ) -> DiscordSmartOutputView:
        if output.action == "message":
            return output.model_copy(
                update={
                    "expression_intent": None,
                    "expression_resource": None,
                    "expression_resolution": reason,
                }
            )
        if output.fallback_text.strip():
            return DiscordSmartOutputView(
                action="message",
                content=[SmartTextPart(text=output.fallback_text)],
                reply_to_message_id=output.reply_to_message_id or output.target_message_id,
                expression_resolution=reason,
            )
        return DiscordSmartOutputView(action="ignore", expression_resolution=reason)

    def resolve(
        self, output: DiscordSmartOutputView, context: ToolExecutionContext
    ) -> DiscordSmartOutputView:
        intent = output.expression_intent
        if intent is None:
            return output
        scope = RoomScope(
            owner_id=context.owner_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
        )
        role = self.deployments.deployment_matches_discord_destination(
            context.deployment_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
            category_id=context.category_id,
        )
        if (
            role is None
            or role.owner_id != context.owner_id
            or role.character_card_id != context.character_card_id
            or not self.rooms.can_read(scope, max_age_seconds=300)
        ):
            return self.without_resource(output, "scope_unavailable")
        action = (
            "inline"
            if output.action == "message"
            else "reaction"
            if output.action == "react"
            else "sticker"
        )
        with self.database.session() as session:
            connection = session.get(PlatformConnectionRecord, context.connection_id)
            if connection is None or connection.platform != "discord":
                return self.without_resource(output)
            # Catalog metadata is a guild resource, not another Character's private memory.
            records = session.scalars(
                select(DiscordExpressionSemanticRecord)
                .where(
                    DiscordExpressionSemanticRecord.owner_id == connection.owner_id,
                    DiscordExpressionSemanticRecord.connection_id == context.connection_id,
                    DiscordExpressionSemanticRecord.guild_id == context.guild_id,
                    DiscordExpressionSemanticRecord.resource_type == intent.kind,
                    DiscordExpressionSemanticRecord.enabled.is_(True),
                    DiscordExpressionSemanticRecord.available.is_(True),
                )
                .order_by(DiscordExpressionSemanticRecord.id)
                .limit(2000)
            ).all()
            recent = set(
                session.scalars(
                    select(ExpressionUsageRecord.resource_key)
                    .where(
                        ExpressionUsageRecord.owner_id == context.owner_id,
                        ExpressionUsageRecord.scope_id == scope_key(scope),
                        ExpressionUsageRecord.deployment_id == context.deployment_id,
                    )
                    .order_by(ExpressionUsageRecord.used_at.desc())
                    .limit(5)
                )
            )
            ranked = rank_expression_resources(
                [self.catalog._resource(item) for item in records],
                query=f"{intent.intent} {intent.emotion}",
                allowed_actions={action},
                recent_resource_keys=recent,
                top_k=10,
            )
        choices = []
        for candidate in ranked:
            # Matching intent is preferred over decorative name/description coincidence.
            exact_intent = normalize_text(candidate.resource.semantic_intent) == normalize_text(
                intent.intent
            )
            exact_emotion = bool(intent.emotion.strip()) and normalize_text(
                candidate.resource.semantic_emotion
            ) == normalize_text(intent.emotion)
            score = candidate.score + (0.4 if exact_intent else 0) + (0.15 if exact_emotion else 0)
            if score >= 0.2:
                choices.append((score, candidate))
        current_role = self.deployments.deployment_matches_discord_destination(
            context.deployment_id,
            connection_id=context.connection_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
            category_id=context.category_id,
        )
        if (
            current_role is None
            or current_role.owner_id != context.owner_id
            or current_role.character_card_id != context.character_card_id
            or not self.rooms.can_read(scope, max_age_seconds=300)
        ):
            return self.without_resource(output, "scope_unavailable")
        if not choices:
            return self.without_resource(output)
        choices.sort(key=lambda item: (-item[0], item[1].resource.key))
        resolved_candidate = ExpressionCandidate.model_validate(
            self.catalog.candidate_dict(choices[0][1])
        )
        updates: dict[str, object] = {
            "expression_intent": None,
            "expression_resource": resolved_candidate,
            "expression_resolution": "resolved",
        }
        if output.action == "message":
            updates["content"] = [
                *output.content,
                SmartEmojiPart(emoji=resolved_candidate.resource_key),
            ]
        elif output.action == "react":
            updates["emoji_resource_key"] = resolved_candidate.resource_key
        else:
            updates["sticker_resource_key"] = resolved_candidate.resource_key
        return output.model_copy(update=updates)
