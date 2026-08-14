"""Conversation-aware Smart Participation V4 connector resolver."""

from __future__ import annotations

import hmac
import logging
from collections.abc import Mapping
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Request, status

from echo_masque.api.smart_participation_outcome_schemas import (
    SmartParticipationLearnedEvidenceRequest,
    SmartParticipationLearnedEvidenceView,
    SmartParticipationOutcomeObservation,
    SmartParticipationOutcomeView,
    SmartParticipationRecentSpeakerRequest,
    SmartParticipationRecentSpeakerView,
)
from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationResolveCandidate,
    SmartParticipationResolveCandidateView,
    SmartParticipationResolveRequest,
    SmartParticipationResolveView,
    SmartParticipationSpeakerPlanItem,
)
from echo_masque.character_learned_state import (
    CharacterLearnedStateService,
    LearnedStateEvidence,
)
from echo_masque.config import Settings
from echo_masque.conversation_graph_shadow import (
    ConversationGraphShadowService,
    GraphShadowObservation,
)
from echo_masque.conversation_graph_topic_shadow import (
    ConversationGraphTopicShadowService,
    TopicGraphShadowObservation,
)
from echo_masque.participation_context_rerank import (
    ParticipationContextCandidate,
    ParticipationContextPlanItem,
    ParticipationContextReranker,
    ParticipationContextResult,
)
from echo_masque.participation_final_utility import (
    ParticipationFinalUtilityResolver,
    ParticipationFinalUtilityResult,
)
from echo_masque.participation_shadow_v4 import (
    ParticipationShadowCandidate,
    ParticipationShadowPlanItem,
    ParticipationShadowScore,
    resolve_participation_shadow,
)
from echo_masque.persistence import (
    DeploymentRepository,
    Repository,
    SmartParticipationRepository,
)
from echo_masque.persistence.conversation_graph_repository import ConversationGraphRepository
from echo_masque.persistence.conversation_topic_repository import ConversationTopicRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.semantic_participation import (
    CharacterParticipationSemanticService,
    SemanticEmbeddingUnavailable,
    SemanticParticipationScore,
)
from echo_masque.services.runtime import RuntimeService
from echo_masque.smart_participation_durable_state import (
    DurableParticipationPreflight,
    SmartParticipationDurableStateService,
)
from echo_masque.smart_participation_outcome import SmartParticipationOutcomeService
from echo_masque.turn_intelligence import TurnIntelligenceService
from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
from echo_masque.utility_gateway_router import UtilityGatewayRouter

logger = logging.getLogger(__name__)
router = APIRouter()


def _authorize_connector(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = cast(Settings, request.app.state.settings)
    configured = settings.connector_shared_secret
    if configured is None or not configured.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Connector API is disabled until a shared secret is configured.",
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.casefold() != "bearer" or not hmac.compare_digest(
        token,
        configured.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid connector credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def _semantic_service(request: Request) -> CharacterParticipationSemanticService:
    return cast(
        CharacterParticipationSemanticService,
        request.app.state.semantic_participation_service,
    )


def _smart_repository(request: Request) -> SmartParticipationRepository:
    return cast(SmartParticipationRepository, request.app.state.smart_participation_repository)


def _analysis_text(payload: SmartParticipationResolveRequest) -> str:
    if not payload.burst_messages:
        return " ".join(payload.message.split())[:4_000]
    lines: list[str] = []
    for item in payload.burst_messages:
        text = " ".join(item.text.split())
        if not text:
            continue
        author = " ".join(item.author_display_name.split())[:120]
        lines.append(f"{author}: {text}" if author else text)
    return "\n".join(lines)[-4_000:]


def _candidate_view(
    requested: SmartParticipationResolveCandidate,
    *,
    character_card_id: str = "",
    semantic: SemanticParticipationScore | None = None,
    shadow: ParticipationShadowScore | None = None,
    eligible: bool | None = None,
    graph_evidence_count: int = 0,
    learned_state_evidence_count: int = 0,
    utility_adjustment: float = 0.0,
) -> SmartParticipationResolveCandidateView:
    return SmartParticipationResolveCandidateView(
        deployment_id=requested.deployment_id,
        character_card_id=character_card_id,
        eligible=requested.eligible if eligible is None else eligible,
        deterministic_score=requested.deterministic_score,
        minimum_score=requested.minimum_score,
        deterministic_signals=dict(requested.signals),
        raw_e5_relevance=semantic.relevance if semantic is not None else 0.0,
        profile_ready=semantic.profile_ready if semantic is not None else False,
        semantic_points=shadow.semantic_points if shadow is not None else 0.0,
        shadow_final_score=(
            shadow.final_score if shadow is not None else requested.deterministic_score
        ),
        shadow_selected=shadow.selected if shadow is not None else False,
        graph_evidence_count=graph_evidence_count,
        learned_state_evidence_count=learned_state_evidence_count,
        utility_adjustment=utility_adjustment,
    )


def _observe_graph_shadow(
    payload: SmartParticipationResolveRequest,
    deployments: DeploymentRepository,
) -> GraphShadowObservation:
    try:
        graph = ConversationGraphRepository(deployments.database)
        return ConversationGraphShadowService(graph).observe(payload)
    except Exception as exc:
        logger.warning(
            "Conversation Graph shadow observation skipped connection=%s guild=%s channel=%s "
            "thread=%s error=%s",
            payload.connection_id,
            payload.guild_id,
            payload.channel_id,
            payload.thread_id,
            exc,
        )
        return GraphShadowObservation(False, "", 0, 0)


def _observe_topic_graph_shadow(
    payload: SmartParticipationResolveRequest,
    deployments: DeploymentRepository,
    owner_ids: list[str],
) -> TopicGraphShadowObservation:
    try:
        graph = ConversationGraphRepository(deployments.database)
        topics = ConversationTopicRepository(deployments.database)
        return ConversationGraphTopicShadowService(graph, topics).observe(
            payload,
            owner_ids=owner_ids,
        )
    except Exception as exc:
        logger.warning(
            "Topic Graph shadow observation skipped connection=%s guild=%s channel=%s "
            "thread=%s owners=%s error=%s",
            payload.connection_id,
            payload.guild_id,
            payload.channel_id,
            payload.thread_id,
            len(owner_ids),
            exc,
        )
        return TopicGraphShadowObservation(False, 0, 0, 0, 0)


def _durable_service(request: Request) -> SmartParticipationDurableStateService:
    current = getattr(request.app.state, "smart_participation_durable_state_v4", None)
    if isinstance(current, SmartParticipationDurableStateService):
        return current
    service = SmartParticipationDurableStateService(_deployment_repository(request).database)
    request.app.state.smart_participation_durable_state_v4 = service
    return service


def _context_reranker(request: Request) -> ParticipationContextReranker:
    current = getattr(request.app.state, "participation_context_reranker_v4", None)
    if isinstance(current, ParticipationContextReranker):
        return current
    database = _deployment_repository(request).database
    service = ParticipationContextReranker(
        ConversationGraphRepository(database),
        ConversationTopicRepository(database),
        CharacterLearnedStateService(database),
    )
    request.app.state.participation_context_reranker_v4 = service
    return service


def _final_utility(request: Request) -> ParticipationFinalUtilityResolver:
    current = getattr(request.app.state, "participation_final_utility_v4", None)
    if isinstance(current, ParticipationFinalUtilityResolver):
        return current
    settings = cast(Settings, request.app.state.settings)
    database = _deployment_repository(request).database
    runtime = RuntimeService(Repository(database), settings)
    gateway = UtilityGatewayRouter(runtime, caller=ExistingProviderUtilityCaller())
    service = ParticipationFinalUtilityResolver(TurnIntelligenceService(gateway))
    request.app.state.participation_final_utility_v4 = service
    return service


def _outcome_service(request: Request) -> SmartParticipationOutcomeService:
    current = getattr(request.app.state, "smart_participation_outcome_v4", None)
    if isinstance(current, SmartParticipationOutcomeService):
        return current
    service = SmartParticipationOutcomeService(_deployment_repository(request))
    request.app.state.smart_participation_outcome_v4 = service
    return service


def _durable_preflight(
    payload: SmartParticipationResolveRequest,
    request: Request,
    records_by_id: Mapping[str, CharacterDeploymentRecord],
) -> DurableParticipationPreflight:
    smart = _smart_repository(request)
    cooldowns: dict[str, int] = {}
    for deployment_id, raw_record in records_by_id.items():
        record = raw_record
        owner_id = str(getattr(record, "owner_id", ""))
        card_id = str(getattr(record, "character_card_id", ""))
        profile = smart.get_profile(card_id, owner_id) if owner_id and card_id else None
        cooldowns[deployment_id] = int(getattr(profile, "cooldown_seconds", 120) or 0)
    return _durable_service(request).preflight(
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        candidate_cooldowns=cooldowns,
        channel_cooldown_seconds=payload.channel_cooldown_seconds,
        window_seconds=payload.window_seconds,
        max_replies_per_window=payload.max_replies_per_window,
    )


def _display_names(request: Request, records: list[object]) -> dict[str, str]:
    repository = cast(Repository, request.app.state.repository)
    values: dict[str, str] = {}
    for raw in records:
        deployment_id = str(getattr(raw, "id", ""))
        owner_id = str(getattr(raw, "owner_id", ""))
        card_id = str(getattr(raw, "character_card_id", ""))
        card = repository.get_character_card(card_id, owner_id) if card_id and owner_id else None
        values[deployment_id] = card.display_name if card is not None else deployment_id
    return values


def _plan_views(
    plan: tuple[ParticipationShadowPlanItem, ...] | tuple[ParticipationContextPlanItem, ...],
) -> list[SmartParticipationSpeakerPlanItem]:
    return [
        SmartParticipationSpeakerPlanItem(
            deployment_id=str(getattr(item, "deployment_id", "")),
            turn_role=str(getattr(item, "turn_role", "primary")),
            reason=str(getattr(item, "reason", "")),
        )
        for item in plan
        if str(getattr(item, "deployment_id", ""))
    ]


def _normalize_shadow_plan(
    plan: tuple[ParticipationShadowPlanItem, ...],
) -> tuple[ParticipationContextPlanItem, ...]:
    return tuple(
        ParticipationContextPlanItem(
            deployment_id=item.deployment_id,
            turn_role=item.turn_role,
            reason=item.reason,
        )
        for item in plan
    )


@router.post(
    "/resolve",
    response_model=SmartParticipationResolveView,
)
def resolve_smart_participation_v4(
    payload: SmartParticipationResolveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationResolveView:
    """Resolve one burst with durable preflight, E5, context rerank and final Utility."""

    _authorize_connector(request, authorization)
    settings = cast(Settings, request.app.state.settings)
    deployment_repository = _deployment_repository(request)
    graph_shadow = _observe_graph_shadow(payload, deployment_repository)
    requested_by_id = {item.deployment_id: item for item in payload.candidates}
    records = deployment_repository.list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    record_by_id = {item.id: item for item in records if item.id in requested_by_id}
    durable = _durable_preflight(payload, request, record_by_id)
    durable_global_block = durable.channel_blocked or durable.rate_limited
    effective_eligible_by_id = {
        deployment_id: bool(
            requested.eligible
            and not durable_global_block
            and deployment_id not in durable.blocked_deployment_ids
            and (record := record_by_id.get(deployment_id)) is not None
            and record.participation_mode == "smart"
        )
        for deployment_id, requested in requested_by_id.items()
    }
    analysis = _analysis_text(payload)
    service = _semantic_service(request)
    eligible = [
        record_by_id[deployment_id]
        for deployment_id, eligible_now in effective_eligible_by_id.items()
        if eligible_now
    ]
    topic_graph_shadow = _observe_topic_graph_shadow(
        payload,
        deployment_repository,
        [record.owner_id for record in eligible],
    )
    score_by_id: dict[str, SemanticParticipationScore] = {}
    model = ""
    dimension = 0
    reason = "ok"

    if durable.channel_blocked:
        reason = "durable_channel_cooldown"
    elif durable.rate_limited:
        reason = "durable_channel_rate_limit"
    elif not analysis:
        reason = "empty_analysis_text"
    elif not service.enabled:
        reason = "semantic_participation_disabled"
    elif not eligible:
        reason = "no_eligible_smart_deployments"
    else:
        try:
            model, dimension, scores = service.score(
                message=analysis,
                deployments=[
                    (record.id, record.owner_id, record.character_card_id) for record in eligible
                ],
            )
            score_by_id = {item.deployment_id: item for item in scores}
            if not any(item.profile_ready for item in scores):
                reason = "no_semantic_profiles_ready"
        except SemanticEmbeddingUnavailable:
            reason = "embedding_unavailable"

    shadow_candidates: list[ParticipationShadowCandidate] = []
    for requested in payload.candidates:
        semantic = score_by_id.get(requested.deployment_id)
        shadow_candidates.append(
            ParticipationShadowCandidate(
                deployment_id=requested.deployment_id,
                eligible=effective_eligible_by_id.get(requested.deployment_id, False),
                deterministic_score=requested.deterministic_score,
                minimum_score=requested.minimum_score,
                signals=dict(requested.signals),
                raw_e5_relevance=semantic.relevance if semantic is not None else 0.0,
                profile_ready=semantic.profile_ready if semantic is not None else False,
            )
        )
    shadow_result = resolve_participation_shadow(
        shadow_candidates,
        minimum_margin=payload.minimum_margin,
        max_participants=payload.max_participants,
    )
    shadow_by_id = {item.deployment_id: item for item in shadow_result.scores}

    context_candidates: list[ParticipationContextCandidate] = []
    for requested in payload.candidates:
        record = record_by_id.get(requested.deployment_id)
        score = shadow_by_id.get(requested.deployment_id)
        if record is None or score is None:
            continue
        signals = dict(requested.signals)
        if score.semantic_points > 0:
            signals["semantic_match"] = score.semantic_points
        context_candidates.append(
            ParticipationContextCandidate(
                deployment_id=requested.deployment_id,
                owner_id=record.owner_id,
                character_card_id=record.character_card_id,
                eligible=effective_eligible_by_id.get(requested.deployment_id, False),
                minimum_score=requested.minimum_score,
                base_final_score=score.final_score,
                deterministic_signals=signals,
            )
        )
    graph_enabled = settings.smart_participation_v4_graph_rerank_mode != "off"
    learned_enabled = settings.smart_participation_v4_learned_state_mode != "off"
    context_result: ParticipationContextResult = _context_reranker(request).rerank(
        context_candidates,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        author_id=payload.author_id,
        minimum_margin=payload.minimum_margin,
        max_participants=payload.max_participants,
        graph_enabled=graph_enabled,
        learned_enabled=learned_enabled,
    )
    context_score_by_id = {item.deployment_id: item for item in context_result.scores}
    context_active = (
        settings.smart_participation_v4_graph_rerank_mode == "active"
        or settings.smart_participation_v4_learned_state_mode == "active"
    )
    effective_plan: tuple[ParticipationContextPlanItem, ...] = (
        context_result.plan if context_active else _normalize_shadow_plan(shadow_result.plan)
    )

    utility_result = ParticipationFinalUtilityResult(
        effective_plan,
        False,
        False,
        "",
        "disabled",
    )
    if settings.smart_participation_v4_utility_mode == "active" and effective_plan:
        utility_result = _final_utility(request).resolve(
            current_burst=analysis,
            plan=effective_plan,
            scores=context_result.scores,
            display_names=_display_names(request, list(eligible)),
        )
        if utility_result.accepted:
            effective_plan = utility_result.plan

    speaker_authoritative = settings.smart_participation_v4_speaker_mode == "active"
    shadow_plan: tuple[ParticipationContextPlanItem, ...] = (
        context_result.plan
        if (graph_enabled or learned_enabled)
        else _normalize_shadow_plan(shadow_result.plan)
    )
    candidates: list[SmartParticipationResolveCandidateView] = []
    for requested in payload.candidates:
        context_score = context_score_by_id.get(requested.deployment_id)
        graph_count = 0
        learned_count = 0
        if context_score is not None:
            graph_count = sum(1 for item in context_score.evidence if item.source == "graph")
            learned_count = sum(
                1 for item in context_score.evidence if item.source == "learned_state"
            )
        candidates.append(
            _candidate_view(
                requested,
                character_card_id=(
                    record_by_id[requested.deployment_id].character_card_id
                    if requested.deployment_id in record_by_id
                    else ""
                ),
                semantic=score_by_id.get(requested.deployment_id),
                shadow=shadow_by_id.get(requested.deployment_id),
                eligible=effective_eligible_by_id.get(requested.deployment_id, False),
                graph_evidence_count=graph_count,
                learned_state_evidence_count=learned_count,
                utility_adjustment=(
                    1.0
                    if utility_result.accepted
                    and utility_result.selected_primary_id == requested.deployment_id
                    else 0.0
                ),
            )
        )

    return SmartParticipationResolveView(
        resolver_version="conversation-intelligence-v4",
        available=bool(score_by_id) or bool(effective_plan),
        reason=reason,
        model=model,
        dimension=dimension,
        burst_id=payload.burst_id or graph_shadow.burst_id,
        burst_message_count=len(payload.burst_messages) or (1 if payload.message else 0),
        analysis_chars=len(analysis),
        candidates=candidates,
        speaker_plan=_plan_views(tuple(effective_plan)) if speaker_authoritative else [],
        shadow_speaker_plan=_plan_views(tuple(shadow_plan)),
        speaker_plan_authoritative=speaker_authoritative,
        graph_shadow_observed=graph_shadow.observed,
        graph_shadow_node_count=graph_shadow.node_count,
        graph_shadow_edge_count=graph_shadow.edge_count,
        topic_graph_shadow_observed=topic_graph_shadow.observed,
        topic_graph_shadow_owner_count=topic_graph_shadow.owner_count,
        topic_graph_shadow_topic_count=topic_graph_shadow.topic_count,
        topic_graph_shadow_node_count=topic_graph_shadow.node_count,
        topic_graph_shadow_edge_count=topic_graph_shadow.edge_count,
        graph_used=context_result.graph_used,
        learned_state_used=context_result.learned_state_used,
        utility_used=utility_result.used,
    )


@router.post(
    "/observe",
    response_model=SmartParticipationOutcomeView,
)
def observe_smart_participation_v4(
    payload: SmartParticipationOutcomeObservation,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationOutcomeView:
    """Persist authoritative admission facts after Connector audience resolution."""

    _authorize_connector(request, authorization)
    try:
        result = _outcome_service(request).record(payload)
    except Exception as exc:
        # Outcome projection is derived/durable support. The Connector has already decided the
        # current turn, so a projection failure must not be converted into a duplicate retry.
        logger.warning(
            "Smart Participation outcome projection failed connection=%s message=%s error=%s",
            payload.connection_id,
            payload.message_id,
            exc,
        )
        return SmartParticipationOutcomeView(recorded=False)
    return SmartParticipationOutcomeView(
        recorded=result.recorded,
        selected_count=result.selected_count,
        graph_edge_count=result.graph_edge_count,
        learned_evidence_count=result.learned_evidence_count,
        durable_recorded=result.durable_recorded,
    )


@router.post(
    "/recent-speaker",
    response_model=SmartParticipationRecentSpeakerView,
)
def recent_smart_participation_speaker_v4(
    payload: SmartParticipationRecentSpeakerRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationRecentSpeakerView:
    """Recover only a bounded recent Smart speaker after Connector-local state loss."""

    _authorize_connector(request, authorization)
    records = _deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    allowed_requested = frozenset(payload.allowed_deployment_ids)
    allowed = frozenset(
        item.id
        for item in records
        if item.id in allowed_requested and item.participation_mode == "smart"
    )
    if not allowed:
        return SmartParticipationRecentSpeakerView()
    deployment_id = _durable_service(request).recent_speaker(
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        maximum_age_seconds=payload.maximum_age_seconds,
        allowed_deployment_ids=allowed,
    )
    return SmartParticipationRecentSpeakerView(deployment_id=deployment_id)


@router.post(
    "/learned-evidence",
    response_model=SmartParticipationLearnedEvidenceView,
)
def record_smart_participation_learned_evidence_v4(
    payload: SmartParticipationLearnedEvidenceRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationLearnedEvidenceView:
    """Record bounded Expertise/Stance evidence tied to an actual Connector deployment."""

    _authorize_connector(request, authorization)
    records = _deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    deployment = next((item for item in records if item.id == payload.deployment_id), None)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found on this connector.")
    if payload.delta == 0.0 or payload.confidence == 0.0:
        return SmartParticipationLearnedEvidenceView(recorded=False)
    service = CharacterLearnedStateService(_deployment_repository(request).database)
    view = service.record_evidence(
        LearnedStateEvidence(
            owner_id=deployment.owner_id,
            character_card_id=deployment.character_card_id,
            state_type=payload.state_type,
            subject_type=payload.subject_type,
            subject_key=payload.subject_key,
            delta=payload.delta,
            confidence=payload.confidence,
            source_type=payload.source_type,
            source_message_id=payload.source_message_id,
            source_burst_id=payload.source_burst_id,
            reason_code=payload.reason_code,
        )
    )
    return SmartParticipationLearnedEvidenceView(
        recorded=True,
        state_type=view.state_type,
        subject_key=view.subject_key,
        value=view.value,
        confidence=view.confidence,
        evidence_count=view.evidence_count,
    )


__all__ = ["router"]
