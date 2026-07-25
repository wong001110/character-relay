from echo_masque.domain import TargetSummary, TargetType


def test_target_summary_is_secret_free() -> None:
    target = TargetSummary(name="Ann", target_type=TargetType.DETERMINISTIC)
    assert target.name == "Ann"
    assert "api_key" not in target.model_dump()
