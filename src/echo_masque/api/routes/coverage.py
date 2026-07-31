"""Owner-scoped Rubric comparison and Calibration coverage endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query, Request

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.coverage_analytics import (
    CoverageAnalyticsService,
    DatasetCoverageReport,
    RubricComparisonReport,
    RubricComparisonRequest,
)

router = APIRouter(prefix="/api/analytics", tags=["coverage-analytics"])


def service(request: Request) -> CoverageAnalyticsService:
    return cast(
        CoverageAnalyticsService,
        request.app.state.coverage_analytics_service,
    )


@router.get(
    "/datasets/{dataset_id}/coverage",
    response_model=DatasetCoverageReport,
)
def dataset_coverage(
    dataset_id: str,
    request: Request,
    user: CurrentUserDependency,
    evaluation_id: Annotated[str | None, Query()] = None,
) -> DatasetCoverageReport:
    try:
        return service(request).coverage(
            user.id,
            dataset_id,
            evaluation_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/rubrics/compare",
    response_model=RubricComparisonReport,
)
def compare_rubrics(
    payload: RubricComparisonRequest,
    request: Request,
    user: CurrentUserDependency,
) -> RubricComparisonReport:
    try:
        return service(request).compare_rubrics(user.id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
