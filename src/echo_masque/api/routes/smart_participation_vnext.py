"""Conversation Intelligence v3 resolver around legacy V4 candidate evidence.

V4 is demoted to an input provider for deterministic/semantic candidate evidence. Conversation
Structure v3 owns Segment/Thread identity, ContextResolverV3 owns context selection, and
ParticipationPlannerV3 owns the final speaker plan. Topic identity is not consulted by this route.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from echo_masque.api.routes.smart_participation_v4 import resolve_smart_participation_v4
from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationResolveRequest,
    SmartParticipationSpeakerPlanItem,
)
from echo_masque.api.smart_participation_vnext_schemas import (
    ConversationSegmentRouteView,
    ReplyTargetRouteView,
    SmartParticipationResolveVNextView,
)
from echo_masque.config import Settings
from echo_masque.context_resolver_v3 import ContextResolverV3, ContextTextHit
from echo_masque.conversation_reply_planner import CharacterSegmentReplyPlanner
from echo_masque.conversation_runtime import ConversationRuntimeCoordinator
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.current_turn_belief_v3 import CurrentTurnBeliefRevisionService
from echo_masque.participation_planner_v3 import ParticipationPlannerV3
from echo_masque.persistence import DeploymentRepository, Repository
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import ConversationStructureRepository
from echo_masque.persistence.entity_evidence_repository import EntityEvidenceRepository
from echo_masque.persistence.server_knowledge_v3_repository import ServerWikiV3Repository
from echo_masque.persistence.smart_participation_state_models import SmartParticipationReplyDecisionRecord
from echo_masque.semantic_participation import CharacterParticipationSemanticService
from echo_masque.services.runtime import RuntimeService
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service
from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
from echo_masque.utility_gateway_router import UtilityGatewayRouter

router = APIRouter()


def _database(request: Request):
    return cast(DeploymentRepository, request.app.state.deployment_repository).database


def _structure_repository(request: Request) -> ConversationStructureRepository:
    current = getattr(request.app.state, "conversation_structure_repository_v3", None)
    if isinstance(current, ConversationStructureRepository):
        return current
    repository = ConversationStructureRepository(_database(request))
    request.app.state.conversation_structure_repository_v3 = repository
    return repository


def _runtime_service(request: Request) -> RuntimeService:
    runtime = getattr(request.app.state, "runtime_service", None)
    if isinstance(runtime, RuntimeService):
        return runtime
    runtime = RuntimeService(
        cast(Repository, request.app.state.repository),
        cast(Settings, request.app.state.settings),
    )
    request.app.state.runtime_service = runtime
    return runtime


def _utility_gateway(request: Request) -> UtilityGatewayRouter:
    current = getattr(request.app.state, "utility_gateway_router_v3", None)
    if isinstance(current, UtilityGatewayRouter):
        return current
    gateway = UtilityGatewayRouter(
        _runtime_service(request),
        caller=ExistingProviderUtilityCaller(),
    )
    request.app.state.utility_gateway_router_v3 = gateway
    return gateway


def _service(request: Request) -> ConversationStructureResolver:
    current = getattr(request.app.state, "conversation_structure_resolver_v3", None)
    if isinstance(current, ConversationStructureResolver):
        return current
    service = ConversationStructureResolver(
        _structure_repository(request),
        cast(Settings, request.app.state.settings),
        _utility_gateway(request),
    )
    request.app.state.conversation_structure_resolver_v3 = service
    return service


def _runtime_coordinator(request: Request) -> ConversationRuntimeCoordinator:
    current = getattr(request.app.state, "conversation_runtime_coordinator_v3", None)
    if isinstance(current, ConversationRuntimeCoordinator):
        return current
    coordinator = ConversationRuntimeCoordinator(_structure_repository(request))
    request.app.state.conversation_runtime_coordinator_v3 = coordinator
    return coordinator


def _reply_planner(request: Request) -> CharacterSegmentReplyPlanner:
    current = getattr(request.app.state, "character_segment_reply_planner_vnext", None)
    if isinstance(current, CharacterSegmentReplyPlanner):
        return current
    planner = CharacterSegmentReplyPlanner(
        cast(CharacterParticipationSemanticService, request.app.state.semantic_participation_service)
    )
    request.app.state.character_segment_reply_planner_vnext = planner
    return planner


def _participation_planner(request: Request) -> ParticipationPlannerV3:
    current = getattr(request.app.state, "participation_planner_v3", None)
    if isinstance(current, ParticipationPlannerV3):
        return current
    planner = ParticipationPlannerV3(_reply_planner(request))
    request.app.state.participation_planner_v3 = planner
    return planner


def _context_resolver(request: Request) -> ContextResolverV3:
    current = getattr(request.app.state, "context_resolver_v3", None)
    if isinstance(current, ContextResolverV3):
        return current
    database = _database(request)
    resolver = ContextResolverV3(
        structure=_structure_repository(request),
        runtime=ConversationRuntimeRepository(database),
        entities=EntityEvidenceRepository(database),
        beliefs=BeliefRepository(database),
        social=SocialIntelligenceV3Service(database),
    )
    request.app.state.context_resolver_v3 = resolver
    return resolver


def _records_for_payload(payload: SmartParticipationResolveRequest, request: Request):
    records = cast(DeploymentRepository, request.app.state.deployment_repository).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    requested = {item.deployment_id for item in payload.candidates}
    return [item for item in records if item.id in requested]


def _current_text(payload: SmartParticipationResolveRequest) -> str:
    if payload.message.strip():
        return payload.message
    if payload.burst_messages:
        return payload.burst_messages[-1].text
    return ""


def _source_message_id(payload: SmartParticipationResolveRequest) -> str:
    if payload.message_id:
        return payload.message_id
    if payload.burst_messages:
        return payload.burst_messages[-1].message_id
    return payload.burst_id or "current-turn"


def _base_result(base: object, *, source: str) -> SmartParticipationResolveVNextView:
    dumped = base.model_dump()  # type: ignore[attr-defined]
    return SmartParticipationResolveVNextView.model_validate(
        {
            **dumped,
            "resolver_version": "conversation-intelligence-v3",
            "segmentation_used": False,
            "segmentation_source": source,
            "conversation_segments": [],
            "reply_targets": [],
            "speaker_plan": [],
            "speaker_plan_authoritative": True,
            "participation_plan_reason": source,
            "media_grounding_level": "context_only",
            "media_grounding_reason": "structure_unavailable",
            "context_sufficiency": {},
        }
    )


def _persist_reply_targets(
    *,
    payload: SmartParticipationResolveRequest,
    request: Request,
    owner_id: str,
    records_by_id: Mapping[str, object],
    targets: list[ReplyTargetRouteView],
    guidance_by_id: Mapping[str, str],
    authoritative_ids: set[str],
) -> None:
    if not targets:
        return
    source_message_id = (
        payload.message_id
        or (f"burst:{payload.burst_id}" if payload.burst_id else "")
        or targets[0].segment_id
    )[:200]
    with _database(request).session() as session:
        for target in targets:
            record = records_by_id.get(target.deployment_id)
            character_card_id = str(getattr(record, "character_card_id", ""))
            existing = session.scalar(
                select(SmartParticipationReplyDecisionRecord).where(
                    SmartParticipationReplyDecisionRecord.connection_id == payload.connection_id,
                    SmartParticipationReplyDecisionRecord.guild_id == payload.guild_id,
                    SmartParticipationReplyDecisionRecord.source_message_id == source_message_id,
                    SmartParticipationReplyDecisionRecord.deployment_id == target.deployment_id,
                )
            )
            if existing is None:
                existing = SmartParticipationReplyDecisionRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    connection_id=payload.connection_id,
                    guild_id=payload.guild_id,
                    source_message_id=source_message_id,
                    deployment_id=target.deployment_id,
                    character_card_id=character_card_id,
                    segment_id=target.segment_id,
                )
                session.add(existing)
            existing.channel_id = payload.channel_id
            existing.thread_id = payload.thread_id
            existing.burst_id = payload.burst_id
            existing.character_card_id = character_card_id
            existing.segment_id = target.segment_id
            # Legacy persistence column name; value is a ConversationThread v3 id on this route.
            existing.semantic_thread_id = target.semantic_thread_id
            existing.score = target.score
            existing.reason = target.reason[:240]
            existing.guidance = guidance_by_id.get(target.deployment_id, "")[:240]
            existing.plan_kind = "speaker" if target.deployment_id in authoritative_ids else "shadow"
            existing.authoritative = target.deployment_id in authoritative_ids
            existing.resolver_version = "conversation-intelligence-v3"
        session.commit()


def _live_context(payload: SmartParticipationResolveRequest) -> tuple[str, ...]:
    if payload.burst_messages:
        return tuple(
            f"{item.author_display_name or item.author_id}: {item.text}"
            for item in payload.burst_messages
            if item.text.strip()
        )
    return (payload.message,) if payload.message.strip() else ()


def _current_segment_id(payload: SmartParticipationResolveRequest, segments: tuple[object, ...]) -> str:
    if payload.message_id:
        for segment in segments:
            if payload.message_id in getattr(segment, "message_ids", ()):
                return str(getattr(segment, "id", ""))
    return str(getattr(segments[-1], "id", "")) if segments else ""


def _wiki_hits(
    *,
    request: Request,
    owner_id: str,
    payload: SmartParticipationResolveRequest,
) -> tuple[ContextTextHit, ...]:
    query = _current_text(payload)
    if not query.strip():
        return ()
    values = ServerWikiV3Repository(_database(request)).lookup(
        owner_id=owner_id,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        query=query,
        limit=6,
    )
    return tuple(
        ContextTextHit(
            source="server_wiki_v3",
            ref=str(item.get("ref", "")),
            text=f"{item.get('title', '')}: {item.get('body', '')}",
            score=float(item.get("confidence", 0.0)),
        )
        for item in values
    )


@router.post("/resolve", response_model=SmartParticipationResolveVNextView)
def resolve_smart_participation_vnext(
    payload: SmartParticipationResolveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationResolveVNextView:
    """Resolve one turn using v3 conversation/context/participation authority."""

    # V4 is intentionally demoted to candidate evidence during cutover. Its speaker plan below is
    # never copied into v3 authority.
    base = resolve_smart_participation_v4(payload, request, authorization)
    records = _records_for_payload(payload, request)
    if not records:
        return _base_result(base, source="no_owner")
    owner_id = records[0].owner_id

    belief_repository = BeliefRepository(_database(request))
    correction_service = CurrentTurnBeliefRevisionService(
        repository=belief_repository,
        gateway=_utility_gateway(request),
    )
    extraction = correction_service.extract_self_claim(
        speaker_ref=payload.author_id,
        text=_current_text(payload),
    )
    correction_shields = {}
    for deployment in records:
        revision = correction_service.apply_to_character(
            extraction=extraction,
            owner_id=owner_id,
            character_card_id=deployment.character_card_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            speaker_ref=payload.author_id,
            source_message_id=_source_message_id(payload),
        )
        if revision is not None and revision.shield.active:
            correction_shields[deployment.id] = revision.shield

    try:
        result = _service(request).resolve(payload=payload, owner_id=owner_id)
    except Exception:
        return _base_result(base, source="conversation_structure_failed")

    try:
        _runtime_coordinator(request).observe(owner_id=owner_id, payload=payload, result=result)
    except Exception:
        # Episode/working-state projection is derived and can be repaired from raw evidence.
        pass

    segment_views = [
        ConversationSegmentRouteView(
            id=item.id,
            message_ids=list(item.message_ids),
            participant_ids=list(item.participant_ids),
            kind=item.kind,
            summary=item.summary,
            semantic_thread_id=item.semantic_thread_id,
            thread_action=item.thread_action,
            thread_evidence=item.thread_evidence,
            confidence=item.confidence,
            source=item.source,
        )
        for item in result.segments
    ]
    current_segment_id = _current_segment_id(payload, tuple(result.segments))
    wiki_hits = _wiki_hits(request=request, owner_id=owner_id, payload=payload)
    contexts = {}
    resolver = _context_resolver(request)
    for deployment in records:
        contexts[deployment.id] = resolver.resolve(
            owner_id=owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            query=_current_text(payload),
            character_card_id=deployment.character_card_id,
            deployment_id=deployment.id,
            actor_id=payload.author_id,
            segment_id=current_segment_id,
            live_context=_live_context(payload),
            wiki_hits=wiki_hits,
            correction_shield=correction_shields.get(deployment.id),
        )

    plan = _participation_planner(request).plan(
        payload=payload,
        deployments=tuple(records),
        candidate_views=tuple(base.candidates),
        segments=tuple(result.segments),
        context_by_deployment=contexts,
    )
    speaker_plan = [
        SmartParticipationSpeakerPlanItem(
            deployment_id=item.deployment_id,
            turn_role="participant",
            reason=item.reason,
            guidance=item.guidance[:240],
        )
        for item in plan.speakers
    ]
    reply_targets = [
        ReplyTargetRouteView(
            deployment_id=item.deployment_id,
            segment_id=item.segment_id,
            semantic_thread_id=item.conversation_thread_id,
            score=item.score,
            reason=item.reason,
            grounding_level=item.grounding,
            context_sufficiency=contexts[item.deployment_id].sufficiency,
        )
        for item in plan.speakers
    ]
    guidance_by_id = {item.deployment_id: item.guidance for item in plan.speakers}
    authoritative_ids = {item.deployment_id for item in plan.speakers}
    record_by_id = {item.id: item for item in records}
    _persist_reply_targets(
        payload=payload,
        request=request,
        owner_id=owner_id,
        records_by_id=record_by_id,
        targets=reply_targets,
        guidance_by_id=guidance_by_id,
        authoritative_ids=authoritative_ids,
    )

    return SmartParticipationResolveVNextView.model_validate(
        {
            **base.model_dump(),
            "resolver_version": "conversation-intelligence-v3",
            "segmentation_used": bool(segment_views),
            "segmentation_source": result.source,
            "conversation_segments": [item.model_dump() for item in segment_views],
            "reply_targets": [item.model_dump() for item in reply_targets],
            "speaker_plan": [item.model_dump() for item in speaker_plan],
            "speaker_plan_authoritative": True,
            "participation_plan_reason": plan.reason,
            "media_grounding_level": plan.grounding.level,
            "media_grounding_reason": plan.grounding.reason,
            "context_sufficiency": {
                deployment_id: context.sufficiency for deployment_id, context in contexts.items()
            },
            "utility_used": bool(base.utility_used or result.utility_used or extraction.utility_used),
        }
    )


__all__ = ["router"]
