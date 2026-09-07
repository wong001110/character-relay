"""Dependency-free binary codec for persisted float embedding vectors."""

from __future__ import annotations

import struct
from collections.abc import Sequence


def serialize_vector(vector: Sequence[float]) -> bytes:
    if not vector:
        raise ValueError("Embedding vector cannot be empty.")
    return struct.pack(f"<{len(vector)}f", *vector)


def deserialize_vector(value: bytes, dimension: int) -> list[float]:
    expected = dimension * 4
    if len(value) != expected:
        raise ValueError(
            "Stored embedding has "
            f"{len(value)} bytes; expected {expected} for {dimension} dimensions."
        )
    return list(struct.unpack(f"<{dimension}f", value))


__all__ = ["deserialize_vector", "serialize_vector"]
