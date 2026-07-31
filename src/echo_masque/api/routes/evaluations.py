"""Run and retrieve immutable Judge evaluations against approved Calibration Datasets."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.evaluation_analytics import (
    JudgeEvaluationCreate,
    JudgeEvaluationView,
)
from echo_masque.judge_evaluation import EvaluationConflict, JudgeEvaluationService
from echo_masque.persistence import AuthRepository, EvaluationRepository

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def evaluation_service(request: Request) -> JudgeEvaluationService:
    return cast(JudgeEvaluationService, request.app.state.judge_evaluation_service)


def evaluation_repository(request: Request) -> EvaluationRepository:
    return cast(EvaluationRepository, request.app.state.evaluation_repository)


def auth_repository(request: Request) -> AuthRepository:
    return cast(AuthRepository, request.app.state.auth_repository)


@router.get("", response_model=list[JudgeEvaluationView])
def list_evaluations(
    request: Request,
    user: CurrentUserDependency,
) -> list[JudgeEvaluationView]:
    return evaluation_repository(request).list(user.id)


@router.get("/{evaluation_id}", response_model=JudgeEvaluationView)
def get_evaluation(
    evaluation_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> JudgeEvaluationView:
    item = evaluation_repository(request).get(evaluation_id, user.id)
    if item is None:
        raise HTTPException(status_code=404, detail="Judge Evaluation not found.")
    return item


@router.post(
    "",
    response_model=JudgeEvaluationView,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluation(
    payload: JudgeEvaluationCreate,
    request: Request,
    user: CurrentUserDependency,
) -> JudgeEvaluationView:
    try:
        item = await evaluation_service(request).evaluate(user.id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvaluationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    auth_repository(request).audit(
        actor_user_id=user.id,
        action="evaluation.completed",
        resource_type="judge_evaluation",
        resource_id=item.id,
        metadata={
            "dataset_id": item.dataset_id,
            "dataset_version": item.dataset_version,
            "modes": item.modes,
            "status": item.status,
            "prediction_count": len(item.predictions),
        },
    )
    return item
