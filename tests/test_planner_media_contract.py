from echo_masque.api.smart_participation_v3_schemas import SmartParticipationResolveRequest
from echo_masque.participation_planner_v3 import MediaEpistemicContract
from echo_masque.planner_media import PlannerMediaDescriptor, PlannerMediaResult


def _request(
    descriptor: PlannerMediaDescriptor,
    *,
    dependency: str = "optional",
) -> SmartParticipationResolveRequest:
    value = descriptor.model_dump(exclude={"topic_evidence"})
    return SmartParticipationResolveRequest.model_validate(
        {
            "connection_id": "connection-1",
            "message": "https://example.test/video",
            "media_descriptors": [value],
            "media_dependency": dependency,
            "candidates": [{"deployment_id": "ann"}],
        }
    )


def test_resolved_planner_media_requires_content_grounded_character_reply() -> None:
    descriptor = PlannerMediaDescriptor(
        ref="url:1",
        kind="video",
        state="resolved",
        label="Bilibili",
        subject="剧情分析",
        summary="讨论某章节的角色身份与伏笔。",
        source_key="bilibili:demo",
        topic_evidence=True,
    )

    grounding = MediaEpistemicContract().resolve(_request(descriptor))

    assert grounding.level == "content_grounded"
    assert grounding.can_reply is True
    assert grounding.grounded_refs == ("url:1",)


def test_preview_only_media_cannot_be_promoted_to_content_grounding() -> None:
    descriptor = PlannerMediaDescriptor(
        ref="url:1",
        kind="video",
        state="preview_only",
        subject="Unverified preview title",
        topic_evidence=False,
    )

    grounding = MediaEpistemicContract().resolve(_request(descriptor))

    assert grounding.level == "preview_grounded"
    assert grounding.can_reply is True
    assert "do not claim visual/audio content perception" in grounding.guidance


def test_required_media_preview_is_not_enough_to_reply() -> None:
    descriptor = PlannerMediaDescriptor(
        ref="url:1",
        kind="video",
        state="preview_only",
        subject="Visible title only",
        topic_evidence=False,
    )

    grounding = MediaEpistemicContract().resolve(
        _request(descriptor, dependency="required")
    )

    assert grounding.level == "preview_grounded"
    assert grounding.can_reply is False
    assert grounding.reason == "required_media_preview_insufficient"


def test_planner_media_result_does_not_imply_character_perception() -> None:
    result = PlannerMediaResult(
        descriptors=(
            PlannerMediaDescriptor(
                ref="url:1",
                kind="video",
                state="resolved",
                subject="剧情视频",
                topic_evidence=True,
            ),
        ),
        dependency="optional",
        dependency_reason="media_interest_or_relevance_gray_zone",
        planning_text="[video] 剧情视频",
    )
    assert result.planning_text
    assert not hasattr(result, "character_perceived")
