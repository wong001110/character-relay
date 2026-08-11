"""Internal generated-media download endpoint for managed Discord connectors."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from echo_masque.api.routes.connectors import _authorize_connector
from echo_masque.persistence import GeneratedMediaArtifactRepository

router = APIRouter(tags=["connectors"])


def _repository(request: Request) -> GeneratedMediaArtifactRepository:
    return cast(
        GeneratedMediaArtifactRepository,
        request.app.state.generated_media_repository,
    )


@router.get("/generated-media/{artifact_id}")
def fetch_generated_media(
    artifact_id: str,
    request: Request,
    deployment_id: str = Query(min_length=1, max_length=64),
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Return one short-lived generated artifact only to its deployment's connector."""

    _authorize_connector(request, authorization)
    record = _repository(request).get(artifact_id)
    if record is None or record.deployment_id != deployment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated media artifact not found.",
        )
    filename = record.filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=record.content,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Character-Relay-Media-Key": record.media_key,
        },
    )


__all__ = ["router"]
