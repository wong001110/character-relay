from __future__ import annotations

from dataclasses import replace

import pytest
from test_participation_planner_v3 import (
    _candidate_view,
    _deployment,
    _payload,
    _planner,
    _segment,
)

from scripts.replay_legacy_planner import replay_planner


def replay(**kwargs):
    return replay_planner(
        case_id="example",
        planner=_planner(0.9),
        payload=_payload(),
        deployments=(_deployment(),),
        candidate_views=(_candidate_view(),),
        segments=(replace(_segment(), message_ids=("message-1", "message-2")),),
        **kwargs,
    )


def test_real_planner_class_runs_with_explicit_fake_semantics_and_unknown_target() -> None:
    result = replay()
    assert result.prediction.outcome == "speak"
    assert result.prediction.choices[0].speaker == "deployment-1"
    assert result.prediction.choices[0].target_message_id is None
    assert len(result.planner_source_sha256) == 64
    assert result.prediction.usage.cost_usd is None
    assert result.comparison_scope == "planner_only"


def test_actual_source_link_can_be_preserved() -> None:
    result = replay(actual_source_links={"deployment-1": "message-1"})
    assert result.prediction.choices[0].target_message_id == "message-1"


def test_out_of_segment_source_link_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside"):
        replay(actual_source_links={"deployment-1": "other-message"})


def test_upstream_failure_is_not_planner_silence() -> None:
    result = replay(upstream_error="semantic_encoder_unavailable")
    assert result.prediction.outcome == "error"
    assert result.prediction.choices == ()
