import pytest
from pydantic import ValidationError

from echo_masque.domain import TargetSummary, TargetType


def test_target_summary_has_safe_defaults() -> None:
    target = TargetSummary(name="Stable Ann", target_type=TargetType.PROMPT_MODEL)

    assert target.name == "Stable Ann"
    assert target.capabilities.supports_reset is False
    assert target.model_dump(mode="json")["target_type"] == "prompt_model"


def test_target_name_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        TargetSummary(name="", target_type=TargetType.TRANSCRIPT)
