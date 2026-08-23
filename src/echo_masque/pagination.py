"""Stable opaque cursors for time-ordered administrative lists."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime


def encode_time_cursor(created_at: datetime, identifier: str) -> str:
    value = created_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    payload = json.dumps(
        {"created_at": value.astimezone(UTC).isoformat(), "id": identifier},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_time_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        identifier = str(payload["id"]).strip()
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Invalid pagination cursor.") from exc
    if not identifier:
        raise ValueError("Invalid pagination cursor.")
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at.astimezone(UTC), identifier


def encode_ranked_time_cursor(rank: float, updated_at: datetime, identifier: str) -> str:
    """Encode a cursor for lists ordered by rank, then descending time and ID."""

    value = updated_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    payload = json.dumps(
        {
            "rank": float(rank),
            "updated_at": value.astimezone(UTC).isoformat(),
            "id": identifier,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_ranked_time_cursor(cursor: str) -> tuple[float, datetime, str]:
    """Decode a cursor created by :func:`encode_ranked_time_cursor`."""

    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        rank = float(payload["rank"])
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        identifier = str(payload["id"]).strip()
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Invalid pagination cursor.") from exc
    if not identifier:
        raise ValueError("Invalid pagination cursor.")
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return rank, updated_at.astimezone(UTC), identifier
