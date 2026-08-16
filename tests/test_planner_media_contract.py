from echo_masque.api.smart_participation_v4_schemas import SmartParticipationResolveRequest
from echo_masque.api.routes.smart_participation_v4 import _analysis_text
from echo_masque.planner_media import PlannerMediaDescriptor, PlannerMediaResult


def test_resolved_planner_media_is_structured_topic_and_admission_evidence() -> None:
    descriptor = PlannerMediaDescriptor(
        ref="url:1",
        kind="video",
        state="resolved",
        label="Bilibili",
        subject="绝区零剧情分析",
        summary="讨论某章节的反派身份与伏笔。",
        source_key="bilibili:demo",
        topic_evidence=True,
    )
    request = SmartParticipationResolveRequest.model_validate(
        {
            "connection_id": "connection-1",
            "message": "https://b23.tv/demo",
            "media_descriptors": [descriptor.model_dump()],
            "candidates": [{"deployment_id": "ann"}],
        }
    )
    analysis = _analysis_text(request)
    assert "绝区零剧情分析" in analysis
    assert "反派身份" in analysis


def test_preview_only_media_is_not_promoted_to_topic_evidence() -> None:
    descriptor = PlannerMediaDescriptor(
        ref="url:1",
        kind="video",
        state="preview_only",
        subject="Unverified preview title",
        topic_evidence=False,
    )
    request = SmartParticipationResolveRequest.model_validate(
        {
            "connection_id": "connection-1",
            "message": "https://example.test/video",
            "media_descriptors": [descriptor.model_dump()],
            "candidates": [{"deployment_id": "ann"}],
        }
    )
    assert "Unverified preview title" not in _analysis_text(request)


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
