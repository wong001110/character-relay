"""Identity of a prepared retrieval space; equal dimensions do not imply compatibility."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingSpace:
    provider: str
    model: str
    dimension: int
    version: str

    def __post_init__(self) -> None:
        if (
            any(
                not item.strip() or len(item) > 160
                for item in (self.provider, self.model, self.version)
            )
            or not 1 <= self.dimension <= 8192
        ):
            raise ValueError("A bounded provider/model/dimension/version identity is required.")

    @property
    def namespace(self) -> str:
        # Existing embedding_model storage becomes an opaque full-profile namespace. Old
        # bare model-name rows never match and can be discarded at the explicit reset.
        identity = json.dumps(
            [self.provider, self.model, self.dimension, self.version], separators=(",", ":")
        )
        return "space:" + hashlib.sha256(identity.encode()).hexdigest()

    def validate(self, vector: Sequence[float]) -> None:
        if (
            len(vector) != self.dimension
            or any(
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                for value in vector
            )
            or not any(value != 0 for value in vector)
        ):
            raise ValueError(
                "Embedding must have the declared dimension and finite nonzero values."
            )
