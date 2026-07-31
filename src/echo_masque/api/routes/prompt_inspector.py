"""Owner-scoped Character Prompt inspection and export endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query, Request, Response

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.prompt_inspector import (
    CharacterPromptInspector,
    CharacterPromptView,
    PromptExportFormat,
    PromptUnavailable,
    prompt_export_filename,
    render_prompt_export,
)

router = APIRouter(prefix="/api/characters", tags=["character-prompts"])


def inspector(request: Request) -> CharacterPromptInspector:
    return cast(
        CharacterPromptInspector,
        request.app.state.character_prompt_inspector,
    )


def inspected_prompt(
    request: Request,
    owner_id: str,
    card_id: str,
) -> CharacterPromptView:
    try:
        prompt = inspector(request).inspect(owner_id, card_id)
    except PromptUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if prompt is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    return prompt


@router.get("/{card_id}/prompt", response_model=CharacterPromptView)
def get_character_prompt(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterPromptView:
    return inspected_prompt(request, user.id, card_id)


@router.get("/{card_id}/prompt/export", response_class=Response)
def export_character_prompt(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
    export_format: Annotated[
        PromptExportFormat,
        Query(alias="format"),
    ] = "json",
) -> Response:
    prompt = inspected_prompt(request, user.id, card_id)
    body, media_type, extension = render_prompt_export(prompt, export_format)
    filename = prompt_export_filename(prompt, extension)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
