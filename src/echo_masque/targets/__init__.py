"""Target adapters."""

from echo_masque.targets.base import TargetAdapter
from echo_masque.targets.deterministic import fragile_target, stable_target

__all__ = ["TargetAdapter", "fragile_target", "stable_target"]
