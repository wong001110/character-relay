"""Owner-scoped Knowledge Base and deterministic RAG V1 APIs."""

from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.knowledge_schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseView,
    KnowledgeDocumentCreate,
    KnowledgeDocumentView,
    KnowledgeRetrieveHit,
    KnowledgeRetrieveRequest,
    KnowledgeRetrieveView,
)
from echo_masque.persistence import KnowledgeRepository, Repository

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def knowledge_repository(request: Request) -> KnowledgeRepository:
    return cast(KnowledgeRepository, request.app.state.knowledge_repository)


def character_repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _validate_character(request: Request, owner_id: str, character_card_id: str) -> None:
    if not character_card_id:
        return
    if character_repository(request).get_character_card(character_card_id, owner_id) is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")


@router.get("/bases", response_model=list[KnowledgeBaseView])
def list_bases(request: Request, user: CurrentUserDependency) -> list[KnowledgeBaseView]:
    return [
        KnowledgeBaseView.from_record(item)
        for item in knowledge_repository(request).list_bases(user.id)
    ]


@router.post(
    "/bases",
    response_model=KnowledgeBaseView,
    status_code=status.HTTP_201_CREATED,
)
def create_base(
    payload: KnowledgeBaseCreate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeBaseView:
    _validate_character(request, user.id, payload.character_card_id)
    try:
        record = knowledge_repository(request).create_base(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Character Card not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return KnowledgeBaseView.from_record(record)


@router.get("/bases/{base_id}", response_model=KnowledgeBaseView)
def get_base(
    base_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeBaseView:
    record = knowledge_repository(request).get_base(base_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")
    return KnowledgeBaseView.from_record(record)


@router.put("/bases/{base_id}", response_model=KnowledgeBaseView)
def update_base(
    base_id: str,
    payload: KnowledgeBaseUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeBaseView:
    _validate_character(request, user.id, payload.character_card_id)
    try:
        record = knowledge_repository(request).update_base(
            base_id,
            user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        detail = "Knowledge Base not found."
        if str(exc).strip("'") == "character":
            detail = "Character Card not found."
        raise HTTPException(status_code=404, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return KnowledgeBaseView.from_record(record)


@router.delete("/bases/{base_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_base(
    base_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not knowledge_repository(request).delete_base(base_id, user.id):
        raise HTTPException(status_code=404, detail="Knowledge Base not found.")


@router.get(
    "/bases/{base_id}/documents",
    response_model=list[KnowledgeDocumentView],
)
def list_documents(
    base_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> list[KnowledgeDocumentView]:
    try:
        records = knowledge_repository(request).list_documents(base_id, user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.") from exc
    return [KnowledgeDocumentView.from_record(item) for item in records]


@router.post(
    "/bases/{base_id}/documents",
    response_model=KnowledgeDocumentView,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    base_id: str,
    payload: KnowledgeDocumentCreate,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeDocumentView:
    try:
        record = knowledge_repository(request).create_document(
            owner_id=user.id,
            knowledge_base_id=base_id,
            title=payload.title,
            content=payload.content,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Knowledge Base not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return KnowledgeDocumentView.from_record(record)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if not knowledge_repository(request).delete_document(document_id, user.id):
        raise HTTPException(status_code=404, detail="Knowledge Document not found.")


@router.post("/retrieve", response_model=KnowledgeRetrieveView)
def retrieve(
    payload: KnowledgeRetrieveRequest,
    request: Request,
    user: CurrentUserDependency,
) -> KnowledgeRetrieveView:
    _validate_character(request, user.id, payload.character_card_id)
    result = knowledge_repository(request).retrieve_for_turn(
        owner_id=user.id,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        character_card_id=payload.character_card_id,
        query=payload.query,
        top_k=payload.top_k,
    )
    return KnowledgeRetrieveView(
        eligible_base_count=result.eligible_base_count,
        candidate_chunk_count=result.candidate_chunk_count,
        hits=[
            KnowledgeRetrieveHit(
                knowledge_base_id=item.resource.knowledge_base_id,
                document_id=item.resource.document_id,
                document_title=item.resource.document_title,
                chunk_index=item.resource.chunk_index,
                content=item.resource.content,
                score=item.score,
                signals=item.signals,
            )
            for item in result.candidates
        ],
    )
