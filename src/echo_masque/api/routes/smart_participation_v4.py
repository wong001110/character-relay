"""Conversation-aware Smart Participation V4 connector resolver."""

from __future__ import annotations

import hmac
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Request, status

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationResolveCandidate,
    SmartParticipationResolveCandidateView,
    SmartParticipationResolveRequest,
    SmartParticipationResolveView,
)
from echo_masque.config import Settings
from echo_masque.persistence import DeploymentRepository
from echo_masque.semantic_participation import (
    CharacterParticipationSemanticService,
    SemanticEmbeddingUnavailable,
    SemanticParticipationScore,
)

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
) -> SmartParticipationResolveCandidateView:
    return SmartParticipationResolveCandidateView(
        deployment_id=requested.deployment_id,
        character_card_id=character_card_id,
        eligible=requested.eligible,
        deterministic_score=requested.deterministic_score,
        minimum_score=requested.minimum_score,
        raw_e5_relevance=semantic.relevance if semantic is not None else 0.0,
        profile_ready=semantic.profile_ready if semantic is not None else False,
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
    """Return bounded V4 semantic evidence without yet granting speaker admission.

    This endpoint is the migration target for the narrow `/semantic-score` call. During the first
    V4 checkpoint it is intentionally evidence-only: deterministic admission remains Connector
    authority, and Graph/Learned State/Utility are still shadow-disabled here.
    """

    _authorize_connector(request, authorization)
    requested_by_id = {item.deployment_id: item for item in payload.candidates}
    records = _deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    record_by_id = {item.id: item for item in records if item.id in requested_by_id}
    analysis = _analysis_text(payload)
    service = _semantic_service(request)

    eligible = [
        record
        for deployment_id, requested in requested_by_id.items()
        if requested.eligible
        and (record := record_by_id.get(deployment_id)) is not None
        and record.participation_mode == "smart"
    ]
    score_by_id: dict[str, SemanticParticipationScore] = {}
    model = ""
    dimension = 0
    reason = "ok"

    if not analysis:
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
                    (record.id, record.owner_id, record.character_card_id)
                    for record in eligible
                ],
            )
            score_by_id = {item.deployment_id: item for item in scores}
            if not any(item.profile_ready for item in scores):
                reason = "no_semantic_profiles_ready"
        except SemanticEmbeddingUnavailable:
            reason = "embedding_unavailable"

    candidates = [
        _candidate_view(
            requested,
            character_card_id=(
                record_by_id[requested.deployment_id].character_card_id
                if requested.deployment_id in record_by_id
                else ""
            ),
            semantic=score_by_id.get(requested.deployment_id),
        )
        for requested in payload.candidates
    ]
    return SmartParticipationResolveView(
        available=bool(score_by_id),
        reason=reason,
        model=model,
        dimension=dimension,
        burst_id=payload.burst_id,
        burst_message_count=len(payload.burst_messages) or (1 if payload.message else 0),
        analysis_chars=len(analysis),
        candidates=candidates,
        # Final speaker planning is deliberately not claimed until deterministic scoring moves
        # server-side. These fields make shadow/compatibility behavior explicit to the Connector.
        speaker_plan=[],
        graph_used=False,
        learned_state_used=False,
        utility_used=False,
    )


__all__ = ["router"]
