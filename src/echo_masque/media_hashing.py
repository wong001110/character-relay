"""Content-addressing helpers for media streams."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaDigest:
    sha256: str
    bytes_seen: int

    @property
    def media_key(self) -> str:
        return f"sha256:{self.sha256}"


class StreamingSHA256:
    """Update SHA-256 alongside an existing download/forward stream."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._bytes_seen = 0

    @property
    def bytes_seen(self) -> int:
        return self._bytes_seen

    def update(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._digest.update(chunk)
        self._bytes_seen += len(chunk)

    def result(self) -> MediaDigest:
        return MediaDigest(
            sha256=self._digest.hexdigest(),
            bytes_seen=self._bytes_seen,
        )


def sha256_chunks(chunks: Iterable[bytes]) -> MediaDigest:
    hasher = StreamingSHA256()
    for chunk in chunks:
        hasher.update(chunk)
    return hasher.result()


async def sha256_async_chunks(chunks: AsyncIterable[bytes]) -> MediaDigest:
    hasher = StreamingSHA256()
    async for chunk in chunks:
        hasher.update(chunk)
    return hasher.result()
