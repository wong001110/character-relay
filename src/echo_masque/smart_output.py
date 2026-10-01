"""Structured Discord Smart Output protocol and resolution helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.api.expression_schemas import (
    ExpressionCandidate,
    ExpressionDecision,
    ExpressionIntent,
)
from echo_masque.character_invite_runtime import (
    CharacterInviteParticipant,
    CharacterInviteTurnState,
    activate_character_invite_turn,
    current_character_invite_proposal,
)

if TYPE_CHECKING:
    from echo_masque.api.connector_schemas import DiscordInboundMessage

_OUTPUT_PATTERN = re.compile(r"^\s*\[\[CR_OUTPUT\s+(\{.*\})\s*\]\]\s*$", re.DOTALL)
_SHORT_MESSAGE_MAX_TEXT = 280


def _payload_requires_visible_action(payload: DiscordInboundMessage) -> bool:
    """Return whether the conversation directly expects this Character to answer.

    Smart Participation is only a nomination signal. A proactive candidate must retain the option
    to stay silent after seeing the final conversation context; explicit mentions, replies, and an
    active interaction session still require a visible response.
    """

    if payload.runtime_selection_origin:
        return payload.runtime_selection_origin in {"direct", "context_action"}
    return bool(
        getattr(payload, "interaction_session_id", "")
        or getattr(payload, "mentioned_bot", False)
        or getattr(payload, "replied_to_bot", False)
    )


class DiscordActionParticipant(BaseModel):
    """A runtime-approved participant that a character may mention."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=240)
    display_name: str = Field(min_length=1, max_length=100)
    kind: Literal["human", "character"]


class SmartTextPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)


class SmartEmojiPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emoji: str = Field(min_length=1, max_length=240)


class SmartMentionPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention: str = Field(min_length=1, max_length=240)


SmartMessagePart = Annotated[
    SmartTextPart | SmartEmojiPart | SmartMentionPart,
    Field(union_mode="left_to_right"),
]


class SmartOutputProposal(BaseModel):
    """Model proposes content and optional expression meaning, never resource IDs."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["ignore", "message", "short_message", "react", "sticker"]
    content: list[SmartTextPart | SmartMentionPart] = Field(default_factory=list, max_length=24)
    reply_to: str | None = Field(default=None, max_length=32)
    target: str | None = Field(default=None, max_length=32)
    expression: ExpressionIntent | None = None
    fallback_text: str = Field(default="", max_length=280)

    @model_validator(mode="after")
    def validate_action_shape(self) -> SmartOutputProposal:
        if self.action == "ignore":
            if self.content or any(
                (self.reply_to, self.target, self.expression, self.fallback_text)
            ):
                raise ValueError("ignore must not include action payload")
        elif self.action in {"message", "short_message"}:
            if not self.content or self.target or self.fallback_text:
                raise ValueError("message requires content and optional reply/expression")
            if self.expression is not None and self.expression.kind != "emoji":
                raise ValueError("message supports an optional inline emoji intent")
        elif self.action == "react":
            if (
                self.content
                or self.reply_to
                or not self.target
                or self.expression is None
                or self.expression.kind != "emoji"
            ):
                raise ValueError("react requires target and emoji intent")
        elif (
            self.content
            or self.target
            or self.expression is None
            or self.expression.kind != "sticker"
        ):
            raise ValueError("sticker requires sticker intent and optional reply")
        return self


class DiscordSmartOutputView(BaseModel):
    """Resolved output returned to the Discord Connector.

    Prompt-local aliases have already been converted back to runtime references.
    The LLM never receives raw participant, message, Emoji, or Sticker IDs.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["ignore", "message", "react", "sticker"]
    message_style: Literal["normal", "short"] = "normal"
    content: list[SmartMessagePart] = Field(default_factory=list)
    reply_to_message_id: str | None = None
    target_message_id: str | None = None
    emoji_resource_key: str | None = None
    sticker_resource_key: str | None = None
    # Proposals are resolved after generation; resources are runtime-authored only.
    expression_intent: ExpressionIntent | None = None
    expression_resource: ExpressionCandidate | None = None
    expression_resolution: Literal["not_requested", "resolved", "no_match", "scope_unavailable"] = (
        "not_requested"
    )
    fallback_text: str = Field(default="", max_length=280)


@dataclass(frozen=True, slots=True)
class SmartOutputContext:
    message_alias_to_id: dict[str, str]
    message_id_to_alias: dict[str, str]
    participant_alias_to_ref: dict[str, str]
    participant_ref_to_name: dict[str, str]
    participant_alias_descriptions: tuple[str, ...]
    invite_turn_token: str | None = None
    participation_required: bool = False
    proactive_candidate: bool = False

    @classmethod
    def from_payload(
        cls,
        payload: DiscordInboundMessage,
        *,
        character_name: str,
    ) -> SmartOutputContext:
        messages = list(payload.recent_messages)
        if not any(item.message_id == payload.message_id for item in messages):
            messages = [*messages]
        unique: dict[str, object] = {}
        for item in messages[-10:]:
            if item.message_id:
                unique[item.message_id] = item
        primary_id = payload.runtime_target_message_id or payload.message_id
        message_alias_to_id: dict[str, str] = {"trigger": primary_id}
        older_ids = [item_id for item_id in unique if item_id != primary_id]
        for index, message_id in enumerate(older_ids[-8:], start=1):
            message_alias_to_id[f"m{index}"] = message_id
        message_id_to_alias = {value: key for key, value in message_alias_to_id.items()}

        participant_alias_to_ref: dict[str, str] = {}
        participant_ref_to_name: dict[str, str] = {}
        descriptions: list[str] = []
        participants = []
        seen_refs: set[str] = set()
        for participant in payload.mentionable_participants:
            if participant.ref in seen_refs:
                continue
            if participant.ref == f"deployment:{payload.deployment_id}":
                continue
            if payload.interaction_session_id and participant.kind == "character":
                continue
            seen_refs.add(participant.ref)
            participants.append(participant)
        for index, participant in enumerate(participants[:12], start=1):
            alias = f"p{index}"
            participant_alias_to_ref[alias] = participant.ref
            participant_ref_to_name[participant.ref] = participant.display_name
            descriptions.append(f"- {alias}: {participant.display_name} ({participant.kind})")

        invite_turn_token = str(uuid4())
        activate_character_invite_turn(
            CharacterInviteTurnState(
                turn_token=invite_turn_token,
                deployment_id=payload.deployment_id,
                connection_id=getattr(payload, "connection_id", ""),
                guild_id=getattr(payload, "guild_id", ""),
                channel_id=getattr(payload, "channel_id", ""),
                thread_id=getattr(payload, "thread_id", ""),
                category_id=getattr(payload, "category_id", ""),
                participants=tuple(
                    CharacterInviteParticipant(
                        alias=alias,
                        ref=ref,
                        display_name=participant_ref_to_name.get(ref, ""),
                        kind="character" if ref.startswith("deployment:") else "human",
                    )
                    for alias, ref in participant_alias_to_ref.items()
                ),
            )
        )

        return cls(
            message_alias_to_id=message_alias_to_id,
            message_id_to_alias=message_id_to_alias,
            participant_alias_to_ref=participant_alias_to_ref,
            participant_ref_to_name=participant_ref_to_name,
            participant_alias_descriptions=tuple(descriptions),
            invite_turn_token=invite_turn_token,
            participation_required=_payload_requires_visible_action(payload),
            proactive_candidate=bool(getattr(payload, "smart_candidate", False)),
        )

    def message_alias(self, message_id: str) -> str:
        return self.message_id_to_alias.get(message_id, "context")

    def prompt_guidance(self) -> tuple[str, ...]:
        # No catalogue is fetched or included before the Character asks for an expression.
        lines = [
            "Choose one natural Discord social action; runtime validates every reference.",
            "Return exactly one [[CR_OUTPUT {...}]] line, without explanations or reasoning.",
            "Use message for a reply and short_message for <=280 characters. Content parts are "
            "text or a supplied participant mention alias. Never invent aliases or resource IDs.",
            "An expression is optional. Omit it when words alone suffice. Otherwise describe "
            "a short intent and emotion; runtime may find no appropriate resource and omit it.",
            "For message an optional expression.kind=emoji adds one inline emoji. Use react "
            "with a target message alias and emoji intent, or sticker with a sticker intent.",
            "For react/sticker provide fallback_text when a direct human request needs an answer "
            "even if no suitable resource exists. Do not fetch a catalogue yourself.",
            "Never mention yourself. Mentions invite discussion, not permission to use tools.",
            '[[CR_OUTPUT {"action":"message","content":[{"text":"我懂你的意思。"}]}]]',
            '[[CR_OUTPUT {"action":"short_message","content":[{"text":"同意。"}]}]]',
            '[[CR_OUTPUT {"action":"message","reply_to":"trigger",'
            '"content":[{"text":"有點離譜。"}],'
            '"expression":{"kind":"emoji","intent":"tease","emotion":"amused"}}]]',
            '[[CR_OUTPUT {"action":"react","target":"trigger","expression":{"kind":"emoji",'
            '"intent":"agree","emotion":"pleased"},"fallback_text":"同意。"}]]',
            '[[CR_OUTPUT {"action":"sticker","expression":{"kind":"sticker","intent":"thanks",'
            '"emotion":"grateful"},"fallback_text":"謝謝。"}]]',
            "Message references available this turn: " + ", ".join(self.message_alias_to_id),
        ]
        if self.participation_required:
            lines.append("This is a direct request. Answer or clarify; do not ignore it.")
        else:
            lines.append(
                'No useful contribution is a valid success: [[CR_OUTPUT {"action":"ignore"}]]. '
                "A proactive nomination is not an obligation to speak."
            )
        lines.extend(("Mentionable participants:", *self.participant_alias_descriptions))
        return tuple(lines)

    def parse_and_resolve(
        self,
        raw: str,
    ) -> tuple[DiscordSmartOutputView | None, str]:
        marker = _OUTPUT_PATTERN.fullmatch(raw)
        value: object
        if marker is not None:
            try:
                value = json.loads(marker.group(1))
            except json.JSONDecodeError:
                return None, "invalid_smart_output_control"
        else:
            token = "[[CR_OUTPUT"
            start = raw.rfind(token)
            if start < 0:
                return None, "missing_smart_output_control"
            candidate = raw[start + len(token) :].lstrip()
            if not candidate.startswith("{"):
                return None, "invalid_smart_output_control"
            try:
                value, end = json.JSONDecoder().raw_decode(candidate)
            except json.JSONDecodeError:
                return None, "invalid_smart_output_control"
            if candidate[end:].strip() not in {"]", "]]"}:
                return None, "missing_smart_output_control"
        try:
            proposal = SmartOutputProposal.model_validate(value)
        except ValueError:
            return None, "invalid_smart_output_control"
        return self.resolve(proposal)

    def resolve(
        self,
        proposal: SmartOutputProposal,
    ) -> tuple[DiscordSmartOutputView | None, str]:

        def message_id(alias: str | None) -> str | None:
            if alias is None:
                return None
            return self.message_alias_to_id.get(alias)

        if proposal.reply_to is not None and message_id(proposal.reply_to) is None:
            return None, "unknown_reply_message_reference"
        if proposal.target is not None and message_id(proposal.target) is None:
            return None, "unknown_target_message_reference"

        if proposal.action == "ignore":
            if self.participation_required:
                return None, "admitted_turn_requires_visible_action"
            return DiscordSmartOutputView(action="ignore"), "ok"

        if proposal.action in {"react", "sticker"}:
            if self.participation_required and not proposal.fallback_text.strip():
                return None, "direct_expression_requires_text_fallback"
            return DiscordSmartOutputView(
                action="react" if proposal.action == "react" else "sticker",
                expression_intent=proposal.expression,
                fallback_text=proposal.fallback_text,
                target_message_id=message_id(proposal.target),
                reply_to_message_id=message_id(proposal.reply_to),
            ), "ok"

        resolved_parts: list[SmartMessagePart] = []
        text_length = 0
        for part in proposal.content:
            if isinstance(part, SmartTextPart):
                text_length += len(part.text)
                resolved_parts.append(part)
                continue
            participant_ref = self.participant_alias_to_ref.get(part.mention)
            if participant_ref is None:
                return None, "unknown_mention_participant"
            resolved_parts.append(SmartMentionPart(mention=participant_ref))

        if text_length > 4000:
            return None, "message_text_too_long"
        if proposal.action == "short_message" and text_length > _SHORT_MESSAGE_MAX_TEXT:
            return None, "short_message_too_long"
        if not resolved_parts:
            return None, "empty_message_content"
        output = DiscordSmartOutputView(
            action="message",
            message_style="short" if proposal.action == "short_message" else "normal",
            content=resolved_parts,
            expression_intent=proposal.expression,
            reply_to_message_id=message_id(proposal.reply_to),
        )
        return self._materialize_character_invite(output), "ok"

    def _materialize_character_invite(
        self,
        output: DiscordSmartOutputView,
    ) -> DiscordSmartOutputView:
        proposal = current_character_invite_proposal(self.invite_turn_token)
        if proposal is None or output.action != "message":
            return output
        candidate_ref = proposal.participant_ref
        if candidate_ref not in self.participant_ref_to_name:
            return output

        character_mentions = [
            part.mention
            for part in output.content
            if isinstance(part, SmartMentionPart) and part.mention.startswith("deployment:")
        ]
        if any(item != candidate_ref for item in character_mentions):
            return output
        if candidate_ref in character_mentions:
            return output

        content = list(output.content)
        if content:
            content.append(SmartTextPart(text=" "))
        content.append(SmartMentionPart(mention=candidate_ref))
        return output.model_copy(update={"content": content})

    def legacy_visible_text(self, output: DiscordSmartOutputView) -> str:
        if output.action != "message":
            return ""
        values: list[str] = []
        for part in output.content:
            if isinstance(part, SmartTextPart):
                values.append(part.text)
            elif isinstance(part, SmartMentionPart):
                name = self.participant_ref_to_name.get(part.mention)
                if name:
                    values.append(f"@{name}")
        return "".join(values).strip()


def expression_decision_for(output: DiscordSmartOutputView) -> ExpressionDecision:
    if output.action == "react" and output.emoji_resource_key:
        return ExpressionDecision(action="reaction", resource_key=output.emoji_resource_key)
    if output.action == "sticker" and output.sticker_resource_key:
        return ExpressionDecision(action="sticker", resource_key=output.sticker_resource_key)
    if output.action == "message":
        for part in output.content:
            if isinstance(part, SmartEmojiPart):
                return ExpressionDecision(action="inline", resource_key=part.emoji)
    return ExpressionDecision(action="none")


def legacy_message_output(text: str, message_id: str) -> DiscordSmartOutputView:
    cleaned = text.strip()
    if not cleaned:
        return DiscordSmartOutputView(action="ignore")
    return DiscordSmartOutputView(
        action="message",
        content=[SmartTextPart(text=cleaned)],
        reply_to_message_id=message_id,
    )


__all__ = [
    "DiscordActionParticipant",
    "DiscordSmartOutputView",
    "SmartEmojiPart",
    "SmartMentionPart",
    "SmartOutputContext",
    "SmartOutputProposal",
    "SmartTextPart",
    "expression_decision_for",
    "legacy_message_output",
]
