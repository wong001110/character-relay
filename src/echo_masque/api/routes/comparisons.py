"""Run comparison and regression-gate endpoints."""

from fastapi import APIRouter, HTTPException, Request

from echo_masque.api.access import require_run_access
from echo_masque.api.dependencies import OptionalAuthContextDependency
from echo_masque.api.schemas import ComparisonRequest
from echo_masque.comparison import ComparisonResult, RegressionPolicy, compare_results
from echo_masque.persistence import Repository

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


@router.post("", response_model=ComparisonResult)
def compare(
    payload: ComparisonRequest,
    request: Request,
    context: OptionalAuthContextDependency,
) -> ComparisonResult:
    require_run_access(request, payload.baseline_run_id, context)
    require_run_access(request, payload.candidate_run_id, context)
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
