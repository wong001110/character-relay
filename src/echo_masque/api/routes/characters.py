"""Character Card collection endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Request, status

from echo_masque.api.schemas import CharacterCardCreate, CharacterCardView
from echo_masque.persistence import Repository

router = APIRouter(prefix="/api/characters", tags=["characters"])


def repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


@router.get("", response_model=list[CharacterCardView])
def list_characters(
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> list[CharacterCardView]:
    return [
        CharacterCardView.from_record(item)
        for item in repository(request).list_character_cards(owner_id)
    ]


@router.post("", response_model=CharacterCardView, status_code=status.HTTP_201_CREATED)
def create_character(
    payload: CharacterCardCreate,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CharacterCardView:
    repo = repository(request)
    if repo.get_target(payload.target_id) is None:
        raise HTTPException(status_code=404, detail="Target binding not found.")
    record = repo.create_character_card(
        owner_id=owner_id,
        target_id=payload.target_id,
        display_name=payload.display_name,
        subtitle=payload.subtitle,
        subject_type=payload.subject_type,
        persona_summary=payload.persona_summary,
        traits=payload.traits,
        tags=payload.tags,
        expected_tone=payload.expected_tone,
        forbidden_behaviors=payload.forbidden_behaviors,
        memory_summary=payload.memory_summary,
        preferred_suites=[item.value for item in payload.preferred_suites],
        portrait_variant=payload.portrait_variant,
    )
    return CharacterCardView.from_record(record)


@router.get("/{card_id}", response_model=CharacterCardView)
def get_character(
    card_id: str,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> CharacterCardView:
    record = repository(request).get_character_card(card_id, owner_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    return CharacterCardView.from_record(record)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(
    card_id: str,
    request: Request,
    owner_id: Annotated[str, Header(alias="X-Echo-User")] = "local-user",
) -> None:
    if not repository(request).delete_character_card(card_id, owner_id):
        raise HTTPException(status_code=409, detail="Character Card cannot be deleted.")
