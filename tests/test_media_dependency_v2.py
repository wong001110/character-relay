from echo_masque.media_dependency import (
    apply_utility_media_dependency,
    resolve_media_dependency,
)


def test_explicit_media_question_is_runtime_required() -> None:
    decision = resolve_media_dependency(text="这个视频里面讲了什么？", has_media=True)
    assert decision.dependency == "required"
    assert decision.locked is True
    assert decision.utility_refinement_allowed is False


def test_media_only_turn_is_optional_after_planner_descriptor() -> None:
    decision = resolve_media_dependency(text="", has_media=True)
    assert decision.dependency == "optional"
    assert decision.locked is False
    assert decision.utility_refinement_allowed is True


def test_runtime_locked_required_cannot_be_downgraded_by_utility() -> None:
    decision = resolve_media_dependency(text="帮我总结这个链接", has_media=True)
    refined = apply_utility_media_dependency(decision, "none")
    assert refined == decision


def test_gray_zone_can_be_refined_without_changing_runtime_authority_model() -> None:
    decision = resolve_media_dependency(text="笑死这个", has_media=True)
    refined = apply_utility_media_dependency(decision, "none")
    assert refined.dependency == "none"
    assert refined.reason == "utility_gray_zone_refinement"
