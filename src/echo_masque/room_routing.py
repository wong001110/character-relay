"""Bounded routing contracts for the Room Director spike (not production-wired).

Inputs are runtime-normalized, permission-checked data, not a public request schema.
Nothing here grants tool access, fetches a message, or sends a response. In particular,
context actions and continuation eligibility must come from authenticated runtime code.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"^\S+$")]
ReasonCode = Annotated[
    str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
]
SpeakingMode = Literal["direct_answer", "supplement", "reaction", "continuation"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RoomScope(FrozenModel):
    owner_id: Identifier
    connection_id: Identifier
    guild_id: Identifier
    channel_id: Identifier
    thread_id: str = Field(default="", max_length=200)


class RoomMessage(FrozenModel):
    id: Identifier
    scope: RoomScope
    author_id: Identifier
    author_kind: Literal["human", "character", "other_bot"] = "human"
    author_deployment_id: Identifier | None = None
    text: str = Field(default="", max_length=4000)
    version: int = Field(default=1, ge=1)
    reply_to_message_id: Identifier | None = None
    response_to_message_id: Identifier | None = None
    response_delivery_complete: bool | None = None
    # Actual normalized platform mention IDs; never inferred from names or quoted prose.
    mentioned_deployment_ids: tuple[Identifier, ...] = Field(default=(), max_length=24)
    deleted: bool = False
    content_available: bool = True
    has_unseen_media: bool = False

    @model_validator(mode="after")
    def character_identity(self) -> RoomMessage:
        if (self.author_kind == "character") != (self.author_deployment_id is not None):
            raise ValueError("Only a known Character message has a deployment identity.")
        return self


class PublicRole(FrozenModel):
    deployment_id: Identifier
    scope: RoomScope
    public_name: str = Field(min_length=1, max_length=100)
    public_description: str = Field(default="", max_length=600)
    eligible: bool = True


class ContextAction(FrozenModel):
    """A pre-authorized message-selection action, not model or message-text metadata."""

    actor_id: Identifier
    target_message_id: Identifier
    deployment_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=24)


class RoutingSnapshot(FrozenModel):
    snapshot_id: Identifier
    revision: int = Field(ge=0)
    scope: RoomScope
    trigger_message_id: Identifier
    messages: tuple[RoomMessage, ...] = Field(max_length=64)
    roles: tuple[PublicRole, ...] = Field(max_length=24)
    context_action: ContextAction | None = None
    capacity_remaining: int = Field(default=1, ge=0, le=24)
    ambient_allowed: bool = False
    continuation_allowed: bool = False

    @model_validator(mode="after")
    def unique_identities(self) -> RoutingSnapshot:
        if len({m.id for m in self.messages}) != len(self.messages):
            raise ValueError("Duplicate message IDs must be reconciled before routing.")
        if len({r.deployment_id for r in self.roles}) != len(self.roles):
            raise ValueError("Duplicate deployment IDs must be reconciled before routing.")
        return self

    def visible_messages(self) -> tuple[RoomMessage, ...]:
        # R1 is deliberately exact-room. A future permitted ancestor adapter must keep
        # original provenance and explicit authorization; it cannot rewrite scopes to fit.
        return tuple(m for m in self.messages if m.scope == self.scope and not m.deleted)

    def eligible_roles(self) -> tuple[PublicRole, ...]:
        return tuple(r for r in self.roles if r.scope == self.scope and r.eligible)


class SpeakerChoice(FrozenModel):
    speaker: Identifier
    target_message_id: Identifier
    mode: SpeakingMode


class RuleResult(FrozenModel):
    kind: Literal["direct", "director", "silence", "blocked"]
    reason: ReasonCode
    requester_id: Identifier | None = None
    choices: tuple[SpeakerChoice, ...] = ()
    requested_targets: tuple[Identifier, ...] = ()


def route_rules(snapshot: RoutingSnapshot) -> RuleResult:
    """Route explicit sources without a model; never turn a failure into semantic NONE.

    A verified context action wins over incidental mentions in the selected text. Explicit
    platform mentions win over Reply's default addressee (e.g. reply to Ann but ask Ning).
    All explicit mentioned roles are retained, or the whole request is capacity-blocked;
    this helper never silently admits only a prefix. Names in plain text are ambiguous.
    """
    messages = {m.id: m for m in snapshot.visible_messages()}
    trigger = messages.get(snapshot.trigger_message_id)
    if trigger is None:
        return RuleResult(kind="blocked", reason="trigger_unavailable")
    if not trigger.content_available and snapshot.context_action is None:
        return RuleResult(kind="blocked", reason="message_content_unavailable")
    if trigger.author_kind == "other_bot" and snapshot.context_action is None:
        return RuleResult(kind="silence", reason="untrusted_bot_trigger")
    if (
        trigger.author_kind == "character"
        and not snapshot.continuation_allowed
        and snapshot.context_action is None
    ):
        return RuleResult(kind="silence", reason="continuation_not_admitted")

    roles = {r.deployment_id for r in snapshot.eligible_roles()}
    targets: tuple[str, ...] = ()
    target_message_id = trigger.id
    reason = ""
    requester_id = trigger.author_id if trigger.author_kind == "human" else None
    if snapshot.context_action is not None:
        # The authenticated action actor is not the selected message's author.
        requester_id = snapshot.context_action.actor_id
        target = messages.get(snapshot.context_action.target_message_id)
        if target is None or not target.content_available:
            return RuleResult(kind="blocked", reason="selected_source_unavailable")
        targets = tuple(dict.fromkeys(snapshot.context_action.deployment_ids))
        target_message_id = target.id
        reason = "context_action"
    elif trigger.mentioned_deployment_ids:
        targets = tuple(dict.fromkeys(trigger.mentioned_deployment_ids))
        reason = "explicit_mentions"  # Overrides Reply's implied addressee, not another request.
    elif trigger.reply_to_message_id is not None:
        parent = messages.get(trigger.reply_to_message_id)
        if parent is None:
            return RuleResult(kind="blocked", reason="reply_source_unavailable")
        if parent.author_kind == "character" and parent.author_deployment_id is not None:
            targets = (parent.author_deployment_id,)
            reason = "reply_to_character"

    if targets:
        if not set(targets) <= roles:
            return RuleResult(
                kind="blocked", reason="explicit_target_unavailable", requested_targets=targets
            )
        if len(targets) > snapshot.capacity_remaining:
            return RuleResult(kind="blocked", reason="capacity", requested_targets=targets)
        mode: SpeakingMode = (
            "continuation"
            if trigger.author_kind == "character" and snapshot.context_action is None
            else "direct_answer"
        )
        return RuleResult(
            kind="direct",
            reason=reason,
            requester_id=requester_id,
            requested_targets=targets,
            choices=tuple(
                SpeakerChoice(speaker=t, target_message_id=target_message_id, mode=mode)
                for t in targets
            ),
        )
    if not snapshot.ambient_allowed:
        return RuleResult(kind="silence", reason="ambient_disabled")
    if not roles:
        return RuleResult(kind="silence", reason="no_eligible_roles")
    if snapshot.capacity_remaining == 0:
        return RuleResult(kind="blocked", reason="capacity")
    return RuleResult(kind="director", reason="ambiguous_room_turn")
