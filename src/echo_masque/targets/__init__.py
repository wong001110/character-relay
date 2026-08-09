"""Target adapters."""

from echo_masque.targets.base import TargetAdapter
from echo_masque.targets.deterministic import fragile_target, stable_target
from echo_masque.targets.http_target import HttpTarget, HttpTargetConfig
from echo_masque.targets.prompt_model import (
    PromptModelConfig,
    PromptModelTarget,
    PromptModelToolTurn,
)

__all__ = [
    "HttpTarget",
    "HttpTargetConfig",
    "PromptModelConfig",
    "PromptModelTarget",
    "PromptModelToolTurn",
    "TargetAdapter",
    "fragile_target",
    "stable_target",
]
