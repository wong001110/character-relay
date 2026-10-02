"""Explicit, attributed note contracts; text never changes runtime permissions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from echo_masque.room_routing import RoomScope


class NoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_ref: str = Field(default="self", min_length=1, max_length=220)
    kind: Literal["note", "relationship"] = "note"
    text: str = Field(min_length=1, max_length=800)

    @field_validator("subject_ref")
    @classmethod
    def subject(cls, value: str) -> str:
        if value == "self":
            return value
        if ":" not in value:
            raise ValueError("subject must be self, user:<id> or character:<card-id>")
        prefix, identity = value.split(":", 1)
        if (
            prefix not in {"user", "character"}
            or not identity
            or any(c.isspace() for c in identity)
        ):
            raise ValueError("invalid note subject")
        return value

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty note")
        return value.strip()


class NoteView(NoteInput):
    id: str
    character_card_id: str
    scope: RoomScope | None
    authored: bool
    actor_id: str
    source_message_id: str
    version: int
    updated_at: datetime

    def prompt_text(self) -> str:
        origin = "author-defined" if self.authored else "explicit self-report"
        return f"[{self.id}; {origin}; {self.subject_ref}; {self.kind}] {self.text}"


class NoteConflict(ValueError):
    """A stale version, duplicate request mismatch or missing explicit source."""


class NoteAccessDenied(ValueError):
    """The actor/character/source does not have the requested authority."""
