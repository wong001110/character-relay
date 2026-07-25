"""Run comparison and regression-gate endpoints."""

from fastapi import APIRouter, HTTPException, Request

from echo_masque.api.schemas import ComparisonRequest
from echo_masque.comparison import ComparisonResult, RegressionPolicy, compare_results
from echo_masque.persistence import Repository

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


@router.post("", response_model=ComparisonResult)
def compare(payload: ComparisonRequest, request: Request) -> ComparisonResult:
    repository: Repository = request.app.state.repository
    baseline = repository.result_for(payload.baseline_run_id)
    candidate = repository.result_for(payload.candidate_run_id)
    if baseline is None or candidate is None:
        raise HTTPException(status_code=409, detail="Both trials must be completed.")
    try:
        return compare_results(
            baseline,
            candidate,
            RegressionPolicy(
                max_score_drop=payload.max_score_drop,
                max_latency_increase_percent=payload.max_latency_increase_percent,
                allow_new_failures=payload.allow_new_failures,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
