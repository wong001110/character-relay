"""Target adapters."""

from echo_masque.targets.base import TargetAdapter
from echo_masque.targets.deterministic import fragile_target, stable_target
from echo_masque.targets.prompt_model import PromptModelConfig, PromptModelTarget

__all__ = [
    "PromptModelConfig",
    "PromptModelTarget",
    "TargetAdapter",
    "fragile_target",
    "stable_target",
]
