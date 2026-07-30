"""Downloadable trial report endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response

from echo_masque.api.access import require_run_access
from echo_masque.api.dependencies import OptionalAuthContextDependency
from echo_masque.persistence import Repository, decode_trial_metadata
from echo_masque.reports import export_json_report, export_markdown_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/trials/{run_id}")
def trial_report(
    run_id: str,
    request: Request,
    context: OptionalAuthContextDependency,
    format: Literal["markdown", "json"] = "markdown",
) -> Response:
    require_run_access(request, run_id, context)
    repository: Repository = request.app.state.repository
    record = repository.get_run(run_id)
    result = repository.result_for(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Trial not found.")
    if result is None:
        raise HTTPException(status_code=409, detail="Trial is not completed.")
    metadata = decode_trial_metadata(record.suite_json)
    report_metadata: dict[str, object] = {
        "run_id": record.id,
        "target_id": record.target_id,
        "suite": metadata.suite,
        "test_language": metadata.test_language.value,
        "tester_mode": metadata.tester_mode,
        "judge_mode": metadata.judge_mode.value,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    if format == "json":
        return Response(
            export_json_report(result, metadata=report_metadata),
            media_type="application/json",
        )
    return Response(
        export_markdown_report(result, metadata=report_metadata),
        media_type="text/markdown",
    )
