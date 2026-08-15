"""Structured Discord Smart Output protocol and resolution helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.api.expression_schemas import ExpressionCandidate, ExpressionDecision
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


def _expression_aliases(
    candidates: list[ExpressionCandidate],
) -> dict[str, ExpressionCandidate]:
    """Build stable prompt-local aliases without exposing Discord resource IDs."""

    aliases: dict[str, ExpressionCandidate] = {}
    emoji_index = 0
    sticker_index = 0
    for candidate in candidates[:6]:
        if candidate.resource_type == "emoji":
            emoji_index += 1
            alias = f"e{emoji_index}"
        elif candidate.resource_type == "sticker":
            sticker_index += 1
            alias = f"s{sticker_index}"
        else:
            continue
        aliases[alias] = candidate
    return aliases


def _payload_requires_visible_action(payload: DiscordInboundMessage) -> bool:
    """Return whether Runtime has already admitted this Character for the turn."""

    return bool(
        getattr(payload, "interaction_session_id", "")
        or getattr(payload, "mentioned_bot", False)
        or getattr(payload, "replied_to_bot", False)
        or getattr(payload, "smart_candidate", False)
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

    emoji: str = Field(min_length=1, max_length=32)


class SmartMentionPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention: str = Field(min_length=1, max_length=240)


SmartMessagePart = Annotated[
    SmartTextPart | SmartEmojiPart | SmartMentionPart,
    Field(union_mode="left_to_right"),
]


class SmartOutputProposal(BaseModel):
    """Compact model-authored proposal. References are prompt-local aliases."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["ignore", "message", "short_message", "react", "sticker"]
    content: list[SmartMessagePart] = Field(default_factory=list, max_length=24)
    reply_to: str | None = Field(default=None, max_length=32)
    target: str | None = Field(default=None, max_length=32)
    emoji: str | None = Field(default=None, max_length=32)
    sticker: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def validate_action_shape(self) -> SmartOutputProposal:
        if self.action == "ignore":
            if self.content or any((self.reply_to, self.target, self.emoji, self.sticker)):
                raise ValueError("ignore must not include action payload")
            return self
        if self.action in {"message", "short_message"}:
            if not self.content:
                raise ValueError(f"{self.action} requires content")
            if any((self.target, self.emoji, self.sticker)):
                raise ValueError(f"{self.action} contains unsupported action fields")
            return self
        if self.action == "react":
            if self.content or self.reply_to or self.sticker or not self.target or not self.emoji:
                raise ValueError("react requires target and emoji only")
            return self
        if self.content or self.target or self.emoji or not self.sticker:
            raise ValueError("sticker requires sticker and optional reply_to only")
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


@dataclass(frozen=True, slots=True)
class SmartOutputContext:
    message_alias_to_id: dict[str, str]
    message_id_to_alias: dict[str, str]
    participant_alias_to_ref: dict[str, str]
    participant_ref_to_name: dict[str, str]
    participant_alias_descriptions: tuple[str, ...]
    invite_turn_token: str | None = None
    participation_required: bool = False

    @classmethod
    def from_payload(
        cls,
        payload: DiscordInboundMessage,
        *,
        character_name: str,
    ) -> SmartOutputContext:
        messages = list(payload.recent_messages)
        if not any(item.message_id == payload.message_id for item in messages):
            # The caller adds the latest message to the visible transcript separately.
            messages = [*messages]
        unique: dict[str, object] = {}
        for item in messages[-10:]:
            if item.message_id:
                unique[item.message_id] = item
        message_alias_to_id: dict[str, str] = {"trigger": payload.message_id}
        older_ids = [item_id for item_id in unique if item_id != payload.message_id]
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
        )

    def message_alias(self, message_id: str) -> str:
        return self.message_id_to_alias.get(message_id, "context")

    def _available_actions(self, candidates: list[ExpressionCandidate]) -> tuple[str, ...]:
        actions = ["message", "short_message"]
        aliases = _expression_aliases(candidates)
        if any(
            item.resource_type == "emoji" and "reaction" in item.allowed_actions
            for item in aliases.values()
        ):
            actions.append("react")
        if any(
            item.resource_type == "sticker" and "sticker" in item.allowed_actions
            for item in aliases.values()
        ):
            actions.append("sticker")
        if not self.participation_required:
            actions.insert(0, "ignore")
        return tuple(actions)

    def prompt_guidance(self, candidates: list[ExpressionCandidate]) -> tuple[str, ...]:
        actions = self._available_actions(candidates)
        lines: list[str] = [
            "Choose exactly one natural Discord social action for this character.",
            (
                "The action is a proposal only; Character Relay validates every "
                "reference before execution."
            ),
            "Available actions: " + ", ".join(actions) + ".",
        ]
        if self.participation_required:
            lines.extend(
                (
                    "Runtime has already admitted this character for this turn.",
                    "Produce one visible social action. Silence/ignore is not an available action.",
                )
            )
        else:
            lines.append("Use ignore when this character would naturally stay silent.")
        lines.extend(
            (
                "Use message for a normal chat message.",
                (
                    "Use short_message for a brief visible chat reaction; its text content is "
                    f"limited to {_SHORT_MESSAGE_MAX_TEXT} characters."
                ),
                "Unicode Emoji may appear directly inside a text value.",
                (
                    "A message content array is ordered. Each item must contain exactly "
                    "one of: text, emoji, mention."
                ),
                (
                    "A custom Server Emoji in message content must use an Emoji alias "
                    "listed below and may appear anywhere in the content array."
                ),
                (
                    "Use react for a lightweight Emoji reaction attached to one supplied "
                    "message reference."
                ),
                "Use sticker when a listed Server Sticker is the whole social action for this turn.",
                (
                    "For message, short_message, and sticker, omit reply_to to send directly to "
                    "the channel; set reply_to to a supplied message reference only when an "
                    "explicit Discord reply is socially useful."
                ),
                (
                    "Never invent message references, participant aliases, Emoji aliases, "
                    "or Sticker aliases."
                ),
                "Never mention yourself. Your own participant alias is intentionally not supplied.",
                (
                    "Do not emit reasoning, confidence, explanations, prose outside the "
                    "control line, or legacy CR_EXPRESSION controls."
                ),
                "Return exactly one line in the form [[CR_OUTPUT {...}]].",
                "Examples (copy the shape, not unavailable sample aliases):",
                (
                    '[[CR_OUTPUT {"action":"message","content":'
                    '[{"text":"你 😂 真的认真的?"}]}]]'
                ),
                '[[CR_OUTPUT {"action":"short_message","content":[{"text":"哈?"}]}]]',
                (
                    '[[CR_OUTPUT {"action":"message","reply_to":"trigger","content":'
                    '[{"text":"这句我不同意。 "},{"emoji":"e1"},'
                    '{"text":" "},{"mention":"p1"}]}]]'
                ),
                '[[CR_OUTPUT {"action":"react","target":"trigger","emoji":"e1"}]]',
                '[[CR_OUTPUT {"action":"sticker","sticker":"s1"}]]',
            )
        )
        if not self.participation_required:
            lines.append('[[CR_OUTPUT {"action":"ignore"}]]')
        lines.append(
            "Message references available this turn: " + ", ".join(self.message_alias_to_id.keys())
        )
        if self.participant_alias_descriptions:
            lines.extend(("Mentionable participants:", *self.participant_alias_descriptions))
        else:
            lines.append("Mentionable participants: none.")

        expression_aliases = _expression_aliases(candidates)
        if expression_aliases:
            lines.append("Retrieved Server expression aliases:")
            for alias, item in expression_aliases.items():
                meaning = item.semantic_description or item.semantic_intent or item.name
                lines.append(
                    f"- {alias}; type={item.resource_type}; name={item.name}; "
                    f"actions={','.join(item.allowed_actions)}; meaning={meaning}"
                )
        else:
            lines.append("Retrieved Server expression aliases: none.")
        return tuple(lines)

    def parse_and_resolve(
        self,
        raw: str,
        candidates: list[ExpressionCandidate],
    ) -> tuple[DiscordSmartOutputView | None, str]:
        marker = _OUTPUT_PATTERN.fullmatch(raw)
        value: object
        if marker is not None:
            try:
                value = json.loads(marker.group(1))
            except json.JSONDecodeError:
                return None, "invalid_smart_output_control"
        else:
            # Providers occasionally prepend harmless prose or omit one final closing
            # bracket after an otherwise valid CR_OUTPUT. Recover only the final control,
            # require a complete JSON value, and reject any trailing prose. Runtime
            # schema/reference validation still runs below.
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
        return self.resolve(proposal, candidates)

    def resolve(
        self,
        proposal: SmartOutputProposal,
        candidates: list[ExpressionCandidate],
    ) -> tuple[DiscordSmartOutputView | None, str]:
        by_alias = _expression_aliases(candidates)

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

        if proposal.action == "react":
            candidate = by_alias.get(proposal.emoji or "")
            if (
                candidate is None
                or candidate.resource_type != "emoji"
                or not candidate.available
                or not candidate.enabled
                or "reaction" not in candidate.allowed_actions
            ):
                return None, "reaction_resource_not_allowed"
            return (
                DiscordSmartOutputView(
                    action="react",
                    target_message_id=message_id(proposal.target),
                    emoji_resource_key=candidate.resource_key,
                ),
                "ok",
            )

        if proposal.action == "sticker":
            candidate = by_alias.get(proposal.sticker or "")
            if (
                candidate is None
                or candidate.resource_type != "sticker"
                or not candidate.available
                or not candidate.enabled
                or "sticker" not in candidate.allowed_actions
            ):
                return None, "sticker_resource_not_allowed"
            return (
                DiscordSmartOutputView(
                    action="sticker",
                    reply_to_message_id=message_id(proposal.reply_to),
                    sticker_resource_key=candidate.resource_key,
                ),
                "ok",
            )

        resolved_parts: list[SmartMessagePart] = []
        custom_emoji_count = 0
        text_length = 0
        for part in proposal.content:
            if isinstance(part, SmartTextPart):
                text_length += len(part.text)
                resolved_parts.append(part)
                continue
            if isinstance(part, SmartEmojiPart):
                candidate = by_alias.get(part.emoji)
                if (
                    candidate is None
                    or candidate.resource_type != "emoji"
                    or not candidate.available
                    or not candidate.enabled
                    or "inline" not in candidate.allowed_actions
                ):
                    return None, "inline_emoji_resource_not_allowed"
                custom_emoji_count += 1
                if custom_emoji_count > 1:
                    return None, "too_many_custom_emojis"
                resolved_parts.append(SmartEmojiPart(emoji=candidate.resource_key))
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
            # Do not let one Tool proposal silently expand into multiple Character turns.
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
