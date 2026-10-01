"""One production room decision entry, with hard checks before and after the model."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import Field

from echo_masque.api.room_schemas import (
    DraftPreflightRequest,
    RoomChoiceView,
    RoomEventsRequest,
    RoomLocation,
    RoomRoutingRequest,
    RoomRoutingView,
)
from echo_masque.api.routes.connectors import _authorize_connector
from echo_masque.draft_runtime import DraftPreflightView, DraftRuntime
from echo_masque.model_attempt_budget import ModelAttemptBudget
from echo_masque.notes import NoteAccessDenied, NoteConflict, NoteInput, NoteView
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.room_repository import RoomRepository
from echo_masque.persistence.runtime_durability_models import RuntimeStepRecord
from echo_masque.room_director import build_director_input
from echo_masque.room_routing import (
    ContextAction,
    PublicRole,
    RoomScope,
    RoutingSnapshot,
    SpeakerChoice,
    route_rules,
)
from echo_masque.room_sources import SourceUnavailable

router = APIRouter(prefix="/api/connectors/discord/rooms", tags=["Discord rooms"])


def _scope(payload: RoomLocation, owner_id: str) -> RoomScope:
    return RoomScope(
        owner_id=owner_id,
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
    )


def _deployments(request: Request, payload: RoomLocation) -> list[CharacterDeploymentRecord]:
    repository = request.app.state.deployment_repository
    return [
        matched
        for record in repository.list_connector_deployments(
            platform="discord",
            connection_id=payload.connection_id,
        )
        if (
            matched := repository.deployment_matches_discord_destination(
                record.id,
                connection_id=payload.connection_id,
                guild_id=payload.guild_id,
                channel_id=payload.channel_id,
                thread_id=payload.thread_id,
                category_id=payload.category_id,
            )
        )
        is not None
    ]


def _observe(
    request: Request, payload: RoomEventsRequest, records: list[CharacterDeploymentRecord]
) -> tuple[RoomScope, int]:
    with request.app.state.database.session() as session:
        connection = session.get(PlatformConnectionRecord, payload.connection_id)
        if connection is None or connection.platform != "discord":
            raise HTTPException(status_code=404, detail="connection_unavailable")
        # Shared room text has one Connector custodian; private card/notes are never copied here.
        owner_id = connection.owner_id
    repository: RoomRepository = request.app.state.room_repository
    scope = _scope(payload, owner_id)
    owners = {owner_id, *(record.owner_id for record in records)}
    identities = request.app.state.discord_identity_repository
    observations = []
    for item in payload.messages:
        # Every original message destination is checked, never relabeled to this request.
        if not item.in_scope(scope):
            raise HTTPException(status_code=403, detail="source_scope_mismatch")
        route = (
            identities.resolve_message_route(
                connection_id=payload.connection_id, message_id=item.message_id
            )
            if item.author_is_bot
            else None
        )
        receipt = repository.delivery_source(scope, item.message_id) if item.author_is_bot else None
        character_id = (
            route.deployment_id
            if route is not None
            and route.channel_id == payload.channel_id
            and route.thread_id == payload.thread_id
            else receipt.deployment_id
            if receipt is not None
            else ""
        )
        if item.response_to_message_id or item.response_delivery_complete is not None:
            raise HTTPException(status_code=403, detail="source_response_link_runtime_owned")
        if item.author_deployment_id and item.author_deployment_id != character_id:
            raise HTTPException(status_code=403, detail="source_character_unverified")
        observations.append(
            item.model_copy(
                update={
                    "author_deployment_id": character_id,
                    "response_to_message_id": receipt.target_message_id
                    if receipt is not None
                    else "",
                    "response_delivery_complete": receipt.complete if receipt is not None else None,
                }
            )
        )
    revision = 0
    for owner in sorted(owners):
        owner_scope = _scope(payload, owner)
        repository.set_access(
            owner_scope, readable=payload.readable, checked_at=payload.permission_checked_at
        )
        if payload.readable:
            revision = repository.observe(owner_scope, observations)
    return scope, revision


@router.post("/events")
def observe_room_events(
    payload: RoomEventsRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _authorize_connector(request, authorization)
    records = _deployments(request, payload)
    if not records:
        raise HTTPException(status_code=403, detail="room_not_deployed")
    try:
        _, revision = _observe(request, payload, records)
    except (SourceUnavailable, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"accepted": True, "revision": revision, "readable": payload.readable}


@router.post("/resolve", response_model=RoomRoutingView)
async def resolve_room(
    payload: RoomRoutingRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> RoomRoutingView:
    _authorize_connector(request, authorization)
    all_records = _deployments(request, payload)
    records = [record for record in all_records if record.id in set(payload.deployment_ids)]
    if not records:
        return RoomRoutingView(outcome="blocked", reason="no_eligible_roles")
    repository: RoomRepository = request.app.state.room_repository
    try:
        scope, _ = _observe(request, payload, all_records)
        if not payload.readable:
            return RoomRoutingView(outcome="blocked", reason="room_access_revoked")
        history = repository.recent(scope, limit=32)
        trigger = repository.get(scope, payload.trigger_message_id)
        if trigger is None or trigger.message.deleted:
            return RoomRoutingView(outcome="blocked", reason="trigger_unavailable")
        known = {source.message.message_id: source for source in history}
        known[trigger.message.message_id] = trigger
        # Bring the verified Reply chain into routing even when a busy room displaced it.
        for source in repository.focus(scope, trigger.message.message_id).sources:
            known[source.message.message_id] = source
        if payload.action_target_message_id:
            if not payload.action_actor_id or not payload.explicit_deployment_ids:
                return RoomRoutingView(outcome="blocked", reason="invalid_context_action")
            for source in repository.focus(scope, payload.action_target_message_id).sources:
                known[source.message.message_id] = source
        elif payload.action_actor_id:
            return RoomRoutingView(outcome="blocked", reason="invalid_context_action")
        current = trigger.message.model_copy(
            update={
                "mentioned_deployment_ids": tuple(payload.explicit_deployment_ids),
            }
        )
        messages = [
            source.message.routing_message(scope, source.revision)
            for source in known.values()
            if not source.message.deleted and source.message.author_id
        ]
        messages = [
            current.routing_message(scope, trigger.revision)
            if item.id == current.message_id
            else item
            for item in messages
        ]
        reply_parent = known.get(current.reply_to_message_id)
        is_character_reply = bool(reply_parent and reply_parent.message.author_deployment_id)
        roles = []
        for record in records:
            card = request.app.state.repository.get_character_card(
                record.character_card_id, record.owner_id
            )
            if card is not None:
                # Only public display names; never persona, memory, or tool configuration.
                roles.append(
                    PublicRole(
                        deployment_id=record.id,
                        scope=scope,
                        public_name=card.display_name[:100],
                        eligible=(
                            True
                            if payload.action_actor_id
                            else record.participation_mode
                            in {"mention_only", "mention_and_reply", "smart"}
                            if payload.explicit_deployment_ids
                            else record.participation_mode
                            in {"reply_only", "mention_and_reply", "smart"}
                            if is_character_reply
                            else record.participation_mode == "smart"
                        ),
                    )
                )
        snapshot = RoutingSnapshot(
            snapshot_id=payload.request_id,
            revision=max((source.room_revision for source in known.values()), default=0),
            scope=scope,
            trigger_message_id=payload.trigger_message_id,
            messages=tuple(messages[-64:]),
            roles=tuple(roles),
            capacity_remaining=3,
            ambient_allowed=payload.ambient_requested,
            context_action=ContextAction(
                actor_id=payload.action_actor_id,
                target_message_id=payload.action_target_message_id,
                deployment_ids=tuple(payload.explicit_deployment_ids),
            )
            if payload.action_actor_id
            else None,
        )
        rules = route_rules(snapshot)
        if rules.kind in {"silence", "blocked"}:
            return RoomRoutingView(
                outcome="none" if rules.kind == "silence" else "blocked",
                reason=rules.reason,
                snapshot_revision=snapshot.revision,
            )
        # Direct decisions contain no provider request. Every optional attempt reserves its budget.
        # Bind a retry to its request/source, not an unrelated newly received room message.
        request_binding = {
            "scope": scope.model_dump(),
            "trigger": current.message_id,
            "trigger_revision": trigger.revision,
            "actor": payload.action_actor_id,
            "action_target": payload.action_target_message_id,
            "explicit": sorted(set(payload.explicit_deployment_ids)),
            "requested_roles": sorted(set(payload.deployment_ids)),
        }
        input_hash = hashlib.sha256(
            json.dumps(request_binding, sort_keys=True).encode()
        ).hexdigest()
        reservation, receipt = repository.reserve_route(
            scope,
            request_id=payload.request_id,
            input_hash=input_hash,
            requester_id=rules.requester_id or "",
            optional=rules.kind == "director",
        )
        if reservation == "replay" and receipt is not None:
            return RoomRoutingView.model_validate_json(receipt.result_json)
        if reservation != "reserved" or receipt is None:
            return RoomRoutingView(outcome="blocked", reason=reservation)
        result = RoomRoutingView(
            outcome="direct",
            reason=rules.reason,
            route_id=receipt.id,
            snapshot_revision=snapshot.revision,
        )
        try:
            choices = rules.choices
            if rules.kind == "director":
                director_input = build_director_input(snapshot)
                director = getattr(request.app.state, "room_director", None)
                if director is None:
                    result = result.model_copy(
                        update={"outcome": "unavailable", "reason": "director_not_qualified"}
                    )
                    choices = ()
                else:
                    with ModelAttemptBudget(request.app.state.database).scope(
                        scope,
                        requester_id=rules.requester_id or current.author_id,
                        operation_id=receipt.id,
                    ):
                        decision = await director.decide(director_input)
                    result = result.model_copy(
                        update={
                            "outcome": decision.outcome,
                            "reason": "director_" + (decision.failure_code or decision.outcome),
                            "attempts": list(decision.attempts),
                            "prompt_version": decision.prompt_version,
                            "input_fingerprint": decision.input_fingerprint,
                        }
                    )
                    choices = (
                        (
                            SpeakerChoice(
                                speaker=decision.decision.speaker,
                                target_message_id=decision.decision.target_message_id,
                                mode=decision.decision.mode,
                            ),
                        )
                        if decision.outcome == "decision" and decision.decision is not None
                        else ()
                    )
            current_records = {record.id: record for record in _deployments(request, payload)}
            for choice in choices:
                selected_record = current_records.get(choice.speaker)
                if selected_record is None:
                    raise SourceUnavailable("selected_role_revoked")
                selected = repository.select(
                    _scope(payload, selected_record.owner_id),
                    request_id=payload.request_id,
                    trigger_message_id=payload.trigger_message_id,
                    requester_id=rules.requester_id or "",
                    requester_is_bot=not bool(rules.requester_id),
                    choice=choice,
                    origin="context_action"
                    if payload.action_actor_id
                    else "direct"
                    if rules.kind == "direct"
                    else "ambient",
                )
                result.choices.append(
                    RoomChoiceView(
                        deployment_id=choice.speaker,
                        target_message_id=choice.target_message_id,
                        selection_id=selected.id,
                        mode=choice.mode,
                    )
                )
        except SourceUnavailable as exc:
            result = RoomRoutingView(outcome="blocked", reason=str(exc), route_id=receipt.id)
        except Exception:
            # Record a distinct fault, never forge a successful NONE or invoke another selector.
            repository.finish_route(
                receipt.id,
                status="failed",
                result_json=RoomRoutingView(
                    outcome="unavailable", reason="routing_failed", route_id=receipt.id
                ).model_dump_json(),
            )
            raise
        repository.finish_route(
            receipt.id, status=result.outcome, result_json=result.model_dump_json()
        )
        return result
    except (SourceUnavailable, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/drafts/preflight", response_model=DraftPreflightView)
async def preflight_draft(
    payload: DraftPreflightRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> DraftPreflightView:
    _authorize_connector(request, authorization)
    durable = request.app.state.durable_runtime_repository
    operation = durable.get_operation(payload.operation_id)
    if operation is None or (
        operation.connection_id,
        operation.guild_id,
        operation.channel_id,
        operation.thread_id,
    ) != (payload.connection_id, payload.guild_id, payload.channel_id, payload.thread_id):
        raise HTTPException(status_code=404, detail="draft_not_found")
    with request.app.state.database.session() as session:
        step = session.get(RuntimeStepRecord, payload.step_id)
        if step is None or step.operation_id != operation.operation_id:
            raise HTTPException(status_code=404, detail="draft_not_found")
    records = _deployments(request, payload)
    try:
        # Never accept client draft text, revisions, generation status or a replacement cursor.
        scope, _ = _observe(request, payload, records)
        runtime = DraftRuntime(
            request.app.state.discord_connector_runtime,
            request.app.state.room_repository,
            durable,
        )
        return await runtime.preflight(
            scope=scope,
            operation_id=operation.operation_id,
            step_id=step.step_id,
            deployment=next((r for r in records if r.id == step.deployment_id), None),
            writable=payload.readable and payload.writable,
        )
    except (SourceUnavailable, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class RoomNoteAction(RoomEventsRequest):
    deployment_id: str = Field(min_length=1, max_length=200)
    actor_id: str = Field(min_length=1, max_length=200)
    actor_is_bot: bool = False
    action: Literal["remember", "correct", "forget", "list"]
    kind: Literal["note", "relationship"] = "note"
    text: str = Field(default="", max_length=800)
    source_message_id: str = Field(default="", max_length=200)
    request_id: str = Field(min_length=1, max_length=200)
    note_id: str = Field(default="", max_length=64)
    expected_version: int = Field(default=0, ge=0)


@router.post("/notes", response_model=list[NoteView])
def explicit_note_action(
    payload: RoomNoteAction,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> list[NoteView]:
    """Only a genuine SDK command/context action calls this, never ordinary generated prose."""
    _authorize_connector(request, authorization)
    if payload.actor_is_bot or not payload.readable:
        raise HTTPException(status_code=403, detail="human_note_action_required")
    records = _deployments(request, payload)
    role = next((item for item in records if item.id == payload.deployment_id), None)
    if role is None:
        raise HTTPException(status_code=404, detail="note_character_unavailable")
    _observe(request, payload, records)
    scope = _scope(payload, role.owner_id)
    repo = request.app.state.character_note_repository
    try:
        if payload.action == "list":
            return [
                item
                for item in repo.list(
                    owner_id=role.owner_id,
                    card_id=role.character_card_id,
                    scope=scope,
                    subjects=(f"user:{payload.actor_id}",),
                    include_background=False,
                    limit=256,
                )
                if not item.authored and item.actor_id == payload.actor_id
            ]
        if payload.action == "remember":
            return [
                repo.create(
                    owner_id=role.owner_id,
                    card_id=role.character_card_id,
                    scope=scope,
                    actor_id=payload.actor_id,
                    source_message_id=payload.source_message_id,
                    request_id=payload.request_id,
                    payload=NoteInput(
                        subject_ref=f"user:{payload.actor_id}",
                        text=payload.text,
                        kind=payload.kind,
                    ),
                )
            ]
        if not payload.note_id or payload.expected_version < 1:
            raise NoteConflict("note_identity_and_version_required")
        result = repo.change(
            owner_id=role.owner_id,
            card_id=role.character_card_id,
            scope=scope,
            actor_id=payload.actor_id,
            note_id=payload.note_id,
            expected_version=payload.expected_version,
            source_message_id=payload.source_message_id,
            payload=NoteInput(
                subject_ref=f"user:{payload.actor_id}", text=payload.text, kind=payload.kind
            )
            if payload.action == "correct"
            else None,
        )
        return [result] if result is not None else []
    except (NoteAccessDenied, NoteConflict) as exc:
        raise HTTPException(
            status_code=409 if isinstance(exc, NoteConflict) else 403, detail=str(exc)
        ) from exc
