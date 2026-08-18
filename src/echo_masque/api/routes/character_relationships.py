"""Character Relationship Prior and Deployment Social Intelligence v2 endpoints."""

from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.api.relationship_schemas import (
    CharacterRelationshipPriorList,
    CharacterRelationshipPriorUpdate,
    CharacterRelationshipPriorView,
    DeploymentRelationshipCandidateList,
    DeploymentRelationshipCandidateView,
    DeploymentRelationshipStateList,
    DeploymentRelationshipStateView,
    PersonImpressionUpdate,
    PersonImpressionView,
    RelationshipEvidenceRequest,
    RelationshipGenerationRequest,
    RelationshipGenerationView,
)
from echo_masque.authoring_runtime import AuthoringRuntimeService
from echo_masque.character_relationships import CharacterRelationshipService
from echo_masque.persistence import DeploymentRepository, Repository
from echo_masque.providers import ChatMessage, ProviderError

character_router = APIRouter()
deployment_router = APIRouter()


class _GeneratedPrior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    familiarity: float = Field(ge=-1.0, le=1.0)
    affinity: float = Field(ge=-1.0, le=1.0)
    trust: float = Field(ge=-1.0, le=1.0)
    comfort: float = Field(ge=-1.0, le=1.0)
    rationale: str = Field(default="", max_length=1000)


def _service(request: Request) -> CharacterRelationshipService:
    return CharacterRelationshipService(cast(DeploymentRepository, request.app.state.deployment_repository).database)


def _prior_view(value) -> CharacterRelationshipPriorView:
    return CharacterRelationshipPriorView(
        id=value.id,
        source_character_card_id=value.source_character_card_id,
        target_character_card_id=value.target_character_card_id,
        relationship_type=value.relationship_type,
        description=value.description,
        familiarity=value.familiarity,
        affinity=value.affinity,
        trust=value.trust,
        comfort=value.comfort,
    )


def _state_view(value) -> DeploymentRelationshipStateView:
    return DeploymentRelationshipStateView(
        id=value.id,
        source_deployment_id=value.source_deployment_id,
        target_type=value.target_type,
        target_key=value.target_key,
        familiarity=value.familiarity,
        affinity=value.affinity,
        trust=value.trust,
        comfort=value.comfort,
        familiarity_baseline=value.familiarity_baseline,
        affinity_baseline=value.affinity_baseline,
        trust_baseline=value.trust_baseline,
        comfort_baseline=value.comfort_baseline,
        last_evidence_at=value.last_evidence_at.isoformat(),
    )


def _impression_view(value) -> PersonImpressionView:
    return PersonImpressionView(
        target_type=value.target_type,
        target_key=value.target_key,
        summary=value.summary,
        observations=list(value.observations),
        evidence_refs=list(value.evidence_refs),
        confidence=value.confidence,
    )


@character_router.get(
    "/{character_id}/relationships",
    response_model=CharacterRelationshipPriorList,
)
def list_character_relationships(
    character_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterRelationshipPriorList:
    card = cast(Repository, request.app.state.repository).get_character_card(character_id, user.id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    return CharacterRelationshipPriorList(
        items=[
            _prior_view(item)
            for item in _service(request).list_priors(
                owner_id=user.id,
                source_character_card_id=character_id,
            )
        ]
    )


@character_router.put(
    "/{character_id}/relationships/{target_character_id}",
    response_model=CharacterRelationshipPriorView,
)
def save_character_relationship(
    character_id: str,
    target_character_id: str,
    payload: CharacterRelationshipPriorUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterRelationshipPriorView:
    try:
        value = _service(request).upsert_prior(
            owner_id=user.id,
            source_character_card_id=character_id,
            target_character_card_id=target_character_id,
            relationship_type=payload.relationship_type,
            description=payload.description,
            familiarity=payload.familiarity,
            affinity=payload.affinity,
            trust=payload.trust,
            comfort=payload.comfort,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Character Card not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _prior_view(value)


@character_router.post(
    "/{character_id}/relationships/{target_character_id}/generate",
    response_model=RelationshipGenerationView,
)
async def generate_character_relationship_prior(
    character_id: str,
    target_character_id: str,
    payload: RelationshipGenerationRequest,
    request: Request,
    user: CurrentUserDependency,
) -> RelationshipGenerationView:
    repository = cast(Repository, request.app.state.repository)
    source = repository.get_character_card(character_id, user.id)
    target = repository.get_character_card(target_character_id, user.id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    runtime = cast(AuthoringRuntimeService, request.app.state.authoring_runtime_service)
    provider = runtime.provider()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authoring Runtime is unavailable for Relationship Prior generation.",
        )
    config = runtime.config()
    prompt = {
        "source_character": {
            "name": source.display_name,
            "persona": source.persona_summary,
            "traits": json.loads(source.traits_json or "[]"),
            "tone": source.expected_tone or "",
        },
        "target_character": {
            "name": target.display_name,
            "persona": target.persona_summary,
            "traits": json.loads(target.traits_json or "[]"),
            "tone": target.expected_tone or "",
        },
        "canonical_relationship_type": payload.relationship_type,
        "canonical_relationship_description": payload.description,
        "required_schema": _GeneratedPrior.model_json_schema(),
    }
    try:
        completion = await provider.complete(
            messages=(
                ChatMessage(
                    role="system",
                    content=(
                        "Generate reviewable Starting Dynamics for one directional canonical "
                        "Character relationship. These are authoring priors, not runtime facts. "
                        "Infer only from the supplied Character Cards and explicit relationship. "
                        "Return exactly one strict JSON object. familiarity/affinity/trust/comfort "
                        "must each be numbers from -1 to 1. Do not invent secret history."
                    ),
                ),
                ChatMessage(role="user", content=json.dumps(prompt, ensure_ascii=False)),
            ),
            model=config.model,
            temperature=min(config.temperature, 0.25),
            max_output_tokens=300,
            response_format={"type": "json_object"},
        )
        text = completion.text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("missing JSON object")
        generated = _GeneratedPrior.model_validate_json(text[start : end + 1])
    except (ProviderError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Relationship Prior generation returned an invalid structured result.",
        ) from exc
    return RelationshipGenerationView(
        relationship_type=payload.relationship_type,
        description=payload.description,
        familiarity=generated.familiarity,
        affinity=generated.affinity,
        trust=generated.trust,
        comfort=generated.comfort,
        rationale=generated.rationale,
        provider_model=completion.model,
    )


@deployment_router.get(
    "/deployments/{deployment_id}/relationships",
    response_model=DeploymentRelationshipStateList,
)
def list_deployment_relationships(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentRelationshipStateList:
    values = _service(request).list_states(
        owner_id=user.id,
        source_deployment_id=deployment_id,
    )
    return DeploymentRelationshipStateList(items=[_state_view(item) for item in values])


@deployment_router.get(
    "/deployments/{deployment_id}/relationships/candidates",
    response_model=DeploymentRelationshipCandidateList,
)
def list_deployment_relationship_candidates(
    deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentRelationshipCandidateList:
    deployments = cast(DeploymentRepository, request.app.state.deployment_repository)
    repository = cast(Repository, request.app.state.repository)
    records = deployments.list_connector_deployments(platform="discord", connection_id="")
    # list_connector_deployments historically filters by connection when supplied; use owner list
    # through the normal repository when the connection is not known yet.
    source = next(
        (
            item
            for connection in deployments.list_connections(user.id)
            for item in deployments.list_connector_deployments(
                platform="discord",
                connection_id=connection.id,
            )
            if item.id == deployment_id and item.owner_id == user.id
        ),
        None,
    )
    del records
    if source is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    source_card = repository.get_character_card(source.character_card_id, user.id)
    if source_card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    peers = [
        item
        for item in deployments.list_connector_deployments(
            platform="discord",
            connection_id=source.connection_id,
        )
        if item.owner_id == user.id
        and item.id != source.id
        and item.workspace_id == source.workspace_id
    ]
    service = _service(request)
    values: list[DeploymentRelationshipCandidateView] = []
    for peer in peers:
        card = repository.get_character_card(peer.character_card_id, user.id)
        prior = service.get_prior(
            owner_id=user.id,
            source_character_card_id=source.character_card_id,
            target_character_card_id=peer.character_card_id,
        )
        state = service.get_state(
            owner_id=user.id,
            source_deployment_id=source.id,
            target_type="deployment",
            target_key=peer.id,
        )
        impression = service.get_impression(
            owner_id=user.id,
            source_deployment_id=source.id,
            target_type="deployment",
            target_key=peer.id,
        )
        values.append(
            DeploymentRelationshipCandidateView(
                target_deployment_id=peer.id,
                target_character_card_id=peer.character_card_id,
                target_display_name=card.display_name if card is not None else peer.character_card_id,
                canonical_prior=_prior_view(prior) if prior is not None else None,
                dynamic_state=_state_view(state) if state is not None else None,
                impression=_impression_view(impression) if impression is not None else None,
            )
        )
    return DeploymentRelationshipCandidateList(
        source_deployment_id=source.id,
        source_character_card_id=source.character_card_id,
        source_display_name=source_card.display_name,
        items=values,
    )


@deployment_router.post(
    "/deployments/{deployment_id}/relationships/initialize/{target_deployment_id}",
    response_model=DeploymentRelationshipStateView,
)
def initialize_deployment_relationship(
    deployment_id: str,
    target_deployment_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentRelationshipStateView:
    try:
        value = _service(request).initialize_character_pair(
            owner_id=user.id,
            source_deployment_id=deployment_id,
            target_deployment_id=target_deployment_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _state_view(value)


@deployment_router.post(
    "/deployments/{deployment_id}/relationships/evidence",
    response_model=DeploymentRelationshipStateView,
)
def record_deployment_relationship_evidence(
    deployment_id: str,
    payload: RelationshipEvidenceRequest,
    request: Request,
    user: CurrentUserDependency,
) -> DeploymentRelationshipStateView:
    try:
        value = _service(request).record_evidence(
            owner_id=user.id,
            source_deployment_id=deployment_id,
            target_type=payload.target_type,
            target_key=payload.target_key,
            dimension=payload.dimension,
            delta=payload.delta,
            confidence=payload.confidence,
            reason_code=payload.reason_code,
            source_message_id=payload.source_message_id,
            source_burst_id=payload.source_burst_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Relationship target not found.") from exc
    return _state_view(value)


@deployment_router.put(
    "/deployments/{deployment_id}/relationships/impression",
    response_model=PersonImpressionView,
)
def save_person_impression(
    deployment_id: str,
    payload: PersonImpressionUpdate,
    request: Request,
    user: CurrentUserDependency,
) -> PersonImpressionView:
    try:
        value = _service(request).upsert_impression(
            owner_id=user.id,
            source_deployment_id=deployment_id,
            target_type=payload.target_type,
            target_key=payload.target_key,
            summary=payload.summary,
            observations=tuple(payload.observations),
            evidence_refs=tuple(payload.evidence_refs),
            confidence=payload.confidence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Deployment not found.") from exc
    return _impression_view(value)


__all__ = ["character_router", "deployment_router"]
