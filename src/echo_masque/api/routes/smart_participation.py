"""Character-level Smart Participation configuration and deterministic Playground APIs."""

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.smart_participation_schemas import (
    SmartParticipationFeedbackCreate,
    SmartParticipationFeedbackView,
    SmartParticipationPlaygroundRequest,
    SmartParticipationPlaygroundView,
    SmartParticipationProfileUpdate,
    SmartParticipationProfileView,
)
from echo_masque.persistence import Repository, SmartParticipationRepository
from echo_masque.smart_participation import ParticipationProfile, evaluate_participation

router = APIRouter(prefix="/api/smart-participation", tags=["smart-participation"])


def smart_repository(request: Request) -> SmartParticipationRepository:
    return cast(
        SmartParticipationRepository,
        request.app.state.smart_participation_repository,
    )


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _require_character(request: Request, character_card_id: str, owner_id: str):
    card = character_repository(request).get_character_card(character_card_id, owner_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    return card


def _profile_value(view: SmartParticipationProfileView) -> ParticipationProfile:
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
    record = repo.get_profile(character_card_id, user.id)
    profile_view = (
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
        profile=_profile_value(profile_view),
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
