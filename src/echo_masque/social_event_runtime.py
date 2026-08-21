"""Runtime projection of explicit Discord reply evidence into Social Intelligence v3."""

from __future__ import annotations

from dataclasses import dataclass, field

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.conversation_relations import ConversationRelationService
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.social_intelligence_v3 import (
    SocialEventApplication,
    SocialIntelligenceV3Service,
)


@dataclass(slots=True)
class ExplicitReplySocialEventProjector:
    """Record only a user reply to a Runtime-known Character message as social evidence."""

    database: Database
    identities: DiscordIdentityRepository = field(init=False)
    relations: ConversationRelationService = field(init=False)
    social: SocialIntelligenceV3Service = field(init=False)

    def __post_init__(self) -> None:
        self.identities = DiscordIdentityRepository(self.database)
        self.relations = ConversationRelationService(
            ConversationStructureRepository(self.database)
        )
        self.social = SocialIntelligenceV3Service(self.database)

    def observe(self, payload: DiscordInboundMessage) -> SocialEventApplication | None:
        """Keep interaction addressee evidence separate from any semantic target inference."""

        if (
            payload.author_is_bot
            or not payload.author_id
            or not payload.message_id
            or not payload.reply_to_message_id
        ):
            return None
        route = self.identities.resolve_message_route(
            connection_id=payload.connection_id,
            message_id=payload.reply_to_message_id,
        )
        if (
            route is None
            or route.deployment_id != payload.deployment_id
            or route.workspace_id != payload.guild_id
            or route.channel_id != payload.channel_id
            or route.thread_id != payload.thread_id
        ):
            return None
        relation = self.relations.record(
            owner_id=route.owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            source_message_id=payload.message_id,
            relation_type="REPLY_TO",
            target_ref_type="message",
            target_ref=payload.reply_to_message_id,
            confidence=1.0,
            source="discord_explicit",
            evidence_refs=(payload.message_id, payload.reply_to_message_id),
            status="resolved",
        )
        return self.social.record_event(
            owner_id=route.owner_id,
            source_deployment_id=route.deployment_id,
            target_type="actor",
            target_key=payload.author_id,
            event_type="direct_interaction",
            confidence=1.0,
            source_relation_id=relation.id,
            relation_resolved=True,
            source_message_ids=(payload.message_id,),
            reason="explicit_user_reply_to_character_message",
        )


__all__ = ["ExplicitReplySocialEventProjector"]
