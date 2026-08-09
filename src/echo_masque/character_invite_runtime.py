"""Prompt-local Runtime state for Tool Calling V2 character invite proposals."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CharacterInviteParticipant:
    """One prompt-local participant alias that may be proposed for invitation."""

    alias: str
    ref: str
    display_name: str
    kind: str


@dataclass(frozen=True, slots=True)
class CharacterInviteProposal:
    """A Runtime-validated proposal; the Connector still owns actual participation."""

    participant_alias: str
    candidate_deployment_id: str
    candidate_character_card_id: str
    candidate_display_name: str
    reason: str

    @property
    def participant_ref(self) -> str:
        return f"deployment:{self.candidate_deployment_id}"


@dataclass(slots=True)
class CharacterInviteTurnState:
    deployment_id: str
    connection_id: str
    guild_id: str
    channel_id: str
    thread_id: str
    category_id: str
    participants: tuple[CharacterInviteParticipant, ...]
    proposals: list[CharacterInviteProposal] = field(default_factory=list)

    def participant(self, alias: str) -> CharacterInviteParticipant | None:
        normalized = alias.strip()
        return next((item for item in self.participants if item.alias == normalized), None)

    def record(self, proposal: CharacterInviteProposal) -> None:
        # The generic Tool Runtime already allows only one completed side-effect Tool per turn.
        # Keep this list bounded as a second defensive layer.
        if not self.proposals:
            self.proposals.append(proposal)


_CURRENT_TURN: ContextVar[CharacterInviteTurnState | None] = ContextVar(
    "character_relay_character_invite_turn",
    default=None,
)


def activate_character_invite_turn(state: CharacterInviteTurnState) -> None:
    """Replace prompt-local invite state for the current async request task."""

    _CURRENT_TURN.set(state)


def current_character_invite_turn() -> CharacterInviteTurnState | None:
    return _CURRENT_TURN.get()


def current_character_invite_proposal() -> CharacterInviteProposal | None:
    state = _CURRENT_TURN.get()
    if state is None or not state.proposals:
        return None
    return state.proposals[0]


__all__ = [
    "CharacterInviteParticipant",
    "CharacterInviteProposal",
    "CharacterInviteTurnState",
    "activate_character_invite_turn",
    "current_character_invite_proposal",
    "current_character_invite_turn",
]
