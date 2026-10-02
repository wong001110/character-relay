"""Small admitted evidence DTO; no conversation classification or selection authority."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextTextHit:
    source: str
    ref: str
    text: str
    score: float = 1.0
