"""Character-level Smart Participation configuration, semantics, and Playground APIs."""

import hmac
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from echo_masque.api.dependencies import (
    CurrentUserDependency,
    quota_http_exception,
    quota_service,
)
from echo_masque.api.smart_participation_schemas import (
    SmartParticipationFeedbackCreate,
    SmartParticipationFeedbackView,
    SmartParticipationGeneratedProfile,
    SmartParticipationPlaygroundRequest,
    SmartParticipationPlaygroundView,
    SmartParticipationProfileUpdate,
    SmartParticipationProfileView,
    SmartParticipationSemanticCandidateView,
    SmartParticipationSemanticProfileView,
    SmartParticipationSemanticScoreRequest,
    SmartParticipationSemanticScoreView,
)
from echo_masque.authoring_generation import AuthoringRuntimeUnavailable
from echo_masque.config import Settings
from echo_masque.participation_tiebreak import (
    ParticipationTieBreakService,
    ParticipationTieCandidate,
)
from echo_masque.persistence import (
    DeploymentRepository,
    Repository,
    SmartParticipationRepository,
)
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.providers import ProviderError
from echo_masque.security_controls import QuotaExceeded
from echo_masque.semantic_participation import (
    CharacterParticipationSemanticService,
    CharacterSemanticProfileInspection,
    SemanticEmbeddingUnavailable,
    participation_semantic_text,
)
from echo_masque.smart_participation import ParticipationProfile, evaluate_participation
from echo_masque.smart_participation_generation import SmartParticipationGenerationService

router = APIRouter(prefix="/api/smart-participation", tags=["smart-participation"])


def smart_repository(request: Request) -> SmartParticipationRepository:
    return cast(
        SmartParticipationRepository,
        request.app.state.smart_participation_repository,
    )


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def generation_service(request: Request) -> SmartParticipationGenerationService:
    return cast(
        SmartParticipationGenerationService,
        request.app.state.smart_participation_generation_service,
    )


def semantic_service(request: Request) -> CharacterParticipationSemanticService:
    return cast(
        CharacterParticipationSemanticService,
        request.app.state.semantic_participation_service,
    )


def tie_break_service(request: Request) -> ParticipationTieBreakService:
    current = getattr(request.app.state, "participation_tiebreak_service", None)
    if isinstance(current, ParticipationTieBreakService):
        return current
    service = ParticipationTieBreakService(
        character_repository(request),
        cast(Settings, request.app.state.settings),
    )
    request.app.state.participation_tiebreak_service = service
    return service


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


def _require_character(
    request: Request,
    character_card_id: str,
    owner_id: str,
) -> CharacterCardRecord:
    card = character_repository(request).get_character_card(character_card_id, owner_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    return card


def _profile_value(
    view: SmartParticipationProfileView | SmartParticipationProfileUpdate,
) -> ParticipationProfile:
    return ParticipationProfile(
        enabled=view.enabled,
        style=view.style,
        group_role=view.group_role,
        topics=view.topics,
        keywords=view.keywords,
        trigger_phrases=view.trigger_phrases,
        avoid_phrases=view.avoid_phrases,
        cooldown_seconds=view.cooldown_seconds,
        preferred_follow_up_character_card_id=view.preferred_follow_up_character_card_id,
        follow_up_window_seconds=view.follow_up_window_seconds,
    )


def _semantic_profile_view(
    inspection: CharacterSemanticProfileInspection,
    *,
    rebuilt: bool = False,
) -> SmartParticipationSemanticProfileView:
    return SmartParticipationSemanticProfileView(
        character_card_id=inspection.character_card_id,
        status=inspection.status,
        enabled=inspection.enabled,
        created=inspection.embedding_bytes > 0,
        model_name=inspection.model_name,
        dimension=inspection.dimension,
        embedding_bytes=inspection.embedding_bytes,
        source_hash=inspection.source_hash,
        semantic_text=inspection.semantic_text,
        created_at=inspection.created_at,
        updated_at=inspection.updated_at,
        rebuilt=rebuilt,
    )


@router.get(
    "/profiles/{character_card_id}",
    response_model=SmartParticipationProfileView,
)
def get_profile(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> SmartParticipationProfileView:
    _require_character(request, character_card_id, user.id)
    record = smart_repository(request).get_profile(character_card_id, user.id)
    if record is None:
        return SmartParticipationProfileView.default(character_card_id)
    return SmartParticipationProfileView.from_record(record)


@router.put(
    "/profiles/{character_card_id}",
    response_model=SmartParticipationProfileView,
)
def update_profile(
    character_card_id: str,
    payload: SmartParticipationProfileUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> SmartParticipationProfileView:
    _require_character(request, character_card_id, user.id)
    try:
        record = smart_repository(request).upsert_profile(
            character_card_id=character_card_id,
            owner_id=user.id,
            enabled=payload.enabled,
            style=payload.style,
            group_role=payload.group_role,
            topics=payload.topics,
            keywords=payload.keywords,
            trigger_phrases=payload.trigger_phrases,
            avoid_phrases=payload.avoid_phrases,
            cooldown_seconds=payload.cooldown_seconds,
            preferred_follow_up_character_card_id=(
                payload.preferred_follow_up_character_card_id
            ),
            follow_up_window_seconds=payload.follow_up_window_seconds,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Character Card not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SmartParticipationProfileView.from_record(record)


@router.post(
    "/profiles/{character_card_id}/generate",
    response_model=SmartParticipationGeneratedProfile,
)
async def generate_profile(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> SmartParticipationGeneratedProfile:
    """Generate a reviewable draft; never persist it automatically."""

    _require_character(request, character_card_id, user.id)
    try:
        quota_service(request).consume_authoring_generation(user.id)
        result = await generation_service(request).generate(user.id, character_card_id)
        return SmartParticipationGeneratedProfile.model_validate(result.model_dump())
    except QuotaExceeded as exc:
        raise quota_http_exception(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthoringRuntimeUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/semantic-profile/{character_card_id}",
    response_model=SmartParticipationSemanticProfileView,
)
def get_semantic_profile(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> SmartParticipationSemanticProfileView:
    """Inspect one Character Card semantic profile without running the embedding model."""

    _require_character(request, character_card_id, user.id)
    inspection = semantic_service(request).inspect_profile(
        owner_id=user.id,
        character_card_id=character_card_id,
    )
    return _semantic_profile_view(inspection)


@router.post(
    "/semantic-profile/{character_card_id}",
    response_model=SmartParticipationSemanticProfileView,
)
def create_semantic_profile(
    character_card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> SmartParticipationSemanticProfileView:
    """Explicitly create or refresh one Character Card semantic embedding."""

    _require_character(request, character_card_id, user.id)
    service = semantic_service(request)
    if not service.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic participation is disabled on this deployment.",
        )
    try:
        _, rebuilt = service.ensure_profile(
            owner_id=user.id,
            character_card_id=character_card_id,
        )
    except SemanticEmbeddingUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Character Card not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    inspection = service.inspect_profile(
        owner_id=user.id,
        character_card_id=character_card_id,
    )
    return _semantic_profile_view(inspection, rebuilt=rebuilt)


@router.get(
    "/connector-profiles",
    response_model=dict[str, SmartParticipationProfileView],
)
def list_connector_profiles(
    request: Request,
    connection_id: str = Query(min_length=1, max_length=64),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, SmartParticipationProfileView]:
    """Return only persisted profile overrides for active deployments on one Connector."""

    _authorize_connector(request, authorization)
    records = deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=connection_id,
    )
    repo = smart_repository(request)
    result: dict[str, SmartParticipationProfileView] = {}
    for deployment in records:
        profile = repo.get_profile(deployment.character_card_id, deployment.owner_id)
        if profile is not None:
            result[deployment.id] = SmartParticipationProfileView.from_record(profile)
    return result


@router.post(
    "/semantic-score",
    response_model=SmartParticipationSemanticScoreView,
)
def score_semantic_participation(
    payload: SmartParticipationSemanticScoreRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationSemanticScoreView:
    """Return semantic relevance only; raw Character Card vectors never leave the API."""

    _authorize_connector(request, authorization)
    service = semantic_service(request)
    if not service.enabled:
        return SmartParticipationSemanticScoreView(
            available=False,
            reason="semantic_participation_disabled",
        )

    requested = set(payload.deployment_ids)
    records = deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    eligible = [
        deployment
        for deployment in records
        if deployment.id in requested and deployment.participation_mode == "smart"
    ]
    if not eligible:
        return SmartParticipationSemanticScoreView(
            available=False,
            reason="no_eligible_smart_deployments",
        )

    try:
        model, dimension, scores = service.score(
            message=payload.message,
            deployments=[
                (deployment.id, deployment.owner_id, deployment.character_card_id)
                for deployment in eligible
            ],
        )
    except SemanticEmbeddingUnavailable:
        return SmartParticipationSemanticScoreView(
            available=False,
            reason="embedding_unavailable",
        )

    ready = [item for item in scores if item.profile_ready]
    tie_candidates: list[ParticipationTieCandidate] = []
    deployment_by_id = {item.id: item for item in eligible}
    repo = character_repository(request)
    for item in ready:
        deployment = deployment_by_id.get(item.deployment_id)
        if deployment is None:
            continue
        card = repo.get_character_card(deployment.character_card_id, deployment.owner_id)
        if card is None:
            continue
        tie_candidates.append(
            ParticipationTieCandidate(
                deployment_id=item.deployment_id,
                character_card_id=item.character_card_id,
                display_name=card.display_name,
                semantic_summary=participation_semantic_text(card),
                relevance=item.relevance,
            )
        )
    outcome = tie_break_service(request).apply(
        message=payload.message,
        candidates=tie_candidates,
    )
    reason = "utility_tiebreak" if outcome.used else "ok"

    return SmartParticipationSemanticScoreView(
        available=bool(ready),
        reason=reason if ready else "no_semantic_profiles_ready",
        model=model,
        dimension=dimension,
        candidates=[
            SmartParticipationSemanticCandidateView(
                deployment_id=item.deployment_id,
                character_card_id=item.character_card_id,
                semantic_relevance=outcome.adjusted_relevance.get(
                    item.deployment_id,
                    item.relevance,
                ),
                profile_ready=item.profile_ready,
            )
            for item in scores
        ],
    )


@router.post(
    "/playground/{character_card_id}/evaluate",
    response_model=SmartParticipationPlaygroundView,
)
def evaluate_playground(
    character_card_id: str,
    payload: SmartParticipationPlaygroundRequest,
    request: Request,
    user: CurrentUserDependency,
) -> SmartParticipationPlaygroundView:
    card = _require_character(request, character_card_id, user.id)
    repo = smart_repository(request)
    if payload.profile_override is not None:
        profile_value = payload.profile_override
    else:
        record = repo.get_profile(character_card_id, user.id)
        profile_value = (
            SmartParticipationProfileView.from_record(record)
            if record is not None
            else SmartParticipationProfileView.default(character_card_id)
        )

    previous_is_primary = False
    previous_id = payload.previous_character_card_id.strip()
    if previous_id:
        _require_character(request, previous_id, user.id)
        previous_record = repo.get_profile(previous_id, user.id)
        previous_is_primary = bool(
            previous_record is not None
            and previous_record.enabled
            and previous_record.group_role == "primary"
        )

    preview = evaluate_participation(
        profile=_profile_value(profile_value),
        message=payload.message,
        character_display_name=card.display_name,
        previous_character_card_id=previous_id,
        previous_character_is_primary=previous_is_primary,
    )
    return SmartParticipationPlaygroundView(
        character_card_id=character_card_id,
        decision=preview.decision,
        reason=preview.reason,
        score=preview.score,
        minimum_score=preview.minimum_score,
        signals=preview.signals,
        matched_topics=preview.matched_topics,
        matched_keywords=preview.matched_keywords,
        matched_trigger_phrases=preview.matched_trigger_phrases,
        matched_avoid_phrases=preview.matched_avoid_phrases,
        follow_up_eligible=preview.follow_up_eligible,
        follow_up_reason=preview.follow_up_reason,
    )


@router.post(
    "/feedback/{character_card_id}",
    response_model=SmartParticipationFeedbackView,
    status_code=status.HTTP_201_CREATED,
)
def record_feedback(
    character_card_id: str,
    payload: SmartParticipationFeedbackCreate,
    request: Request,
    user: CurrentUserDependency,
) -> SmartParticipationFeedbackView:
    _require_character(request, character_card_id, user.id)
    try:
        record = smart_repository(request).record_feedback(
            owner_id=user.id,
            character_card_id=character_card_id,
            message=payload.message,
            previous_character_card_id=payload.previous_character_card_id,
            predicted_decision=payload.predicted_decision,
            predicted_reason=payload.predicted_reason,
            score=payload.score,
            minimum_score=payload.minimum_score,
            signals=payload.signals,
            feedback_label=payload.feedback_label,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Character Card not found.") from exc
    return SmartParticipationFeedbackView.from_record(record)
