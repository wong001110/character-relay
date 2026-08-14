from echo_masque.participation_shadow_v4 import (
    ParticipationShadowCandidate,
    resolve_participation_shadow,
    semantic_participation_points,
)


def candidate(
    deployment_id: str,
    *,
    deterministic_score: float,
    minimum_score: float = 5.0,
    relevance: float = 0.0,
    profile_ready: bool = True,
    eligible: bool = True,
    signals: dict[str, float] | None = None,
) -> ParticipationShadowCandidate:
    return ParticipationShadowCandidate(
        deployment_id=deployment_id,
        eligible=eligible,
        deterministic_score=deterministic_score,
        minimum_score=minimum_score,
        signals=signals or {},
        raw_e5_relevance=relevance,
        profile_ready=profile_ready,
    )


def test_semantic_points_match_connector_bounds() -> None:
    assert semantic_participation_points(0.74) == 0.0
    assert semantic_participation_points(0.75) == 0.0
    assert semantic_participation_points(0.825) == 3.0
    assert semantic_participation_points(0.90) == 6.0
    assert semantic_participation_points(0.99) == 6.0
    assert semantic_participation_points(0.90, profile_ready=False) == 0.0


def test_shadow_plan_adds_raw_e5_to_connector_deterministic_score() -> None:
    result = resolve_participation_shadow(
        [
            candidate("ann", deterministic_score=3.0, relevance=0.90),
            candidate("ning", deterministic_score=4.0, relevance=0.825),
        ],
        minimum_margin=2.0,
        max_participants=2,
    )

    assert [item.deployment_id for item in result.plan] == ["ann", "ning"]
    by_id = {item.deployment_id: item for item in result.scores}
    assert by_id["ann"].semantic_points == 6.0
    assert by_id["ann"].final_score == 9.0
    assert by_id["ann"].selected is True
    assert by_id["ning"].semantic_points == 3.0
    assert by_id["ning"].final_score == 7.0
    assert by_id["ning"].selected is True


def test_second_candidate_needs_character_specific_reason() -> None:
    result = resolve_participation_shadow(
        [
            candidate("ann", deterministic_score=6.0, relevance=0.75),
            candidate(
                "ning",
                deterministic_score=6.0,
                relevance=0.75,
                signals={"question": 2.0, "help_request": 2.0},
            ),
        ],
        minimum_margin=2.0,
        max_participants=2,
    )

    assert [item.deployment_id for item in result.plan] == ["ann"]


def test_blocked_candidate_cannot_be_selected_even_with_high_e5() -> None:
    result = resolve_participation_shadow(
        [
            candidate("ann", deterministic_score=4.0, relevance=0.90),
            candidate(
                "blocked",
                deterministic_score=100.0,
                relevance=0.99,
                eligible=False,
            ),
        ],
        minimum_margin=2.0,
        max_participants=2,
    )

    assert [item.deployment_id for item in result.plan] == ["ann"]
    by_id = {item.deployment_id: item for item in result.scores}
    assert by_id["blocked"].selected is False
