from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from echo_masque.room_director import (
    AttemptReceipt,
    DirectorReply,
    DirectorUnavailable,
    build_director_input,
    call_director,
    validate_decision,
)
from echo_masque.room_routing import RoutingSnapshot, route_rules
from echo_masque.room_routing_replay import load_corpus

CORPUS = load_corpus(Path(__file__).parent / "fixtures/room_routing/corpus.jsonl.gz")


def snapshot(family: str = "human_banter") -> RoutingSnapshot:
    return next(c.snapshot for c in CORPUS.cases if c.id == f"{family}-0")


@pytest.mark.parametrize("case", CORPUS.cases, ids=lambda case: case.id)
def test_deterministic_cases_and_ambiguous_seam(case) -> None:
    result = route_rules(case.snapshot)
    if result.kind == "director":
        view = build_director_input(case.snapshot)
        assert len(view.messages) <= 24
        assert case.snapshot.trigger_message_id in {m.id for m in view.messages}
        assert all(m.scope == case.snapshot.scope for m in view.messages)
        return  # No synthetic expected label is fed into a model or used as its prediction.
    if case.expected.outcome == "blocked":
        assert result.kind == "blocked"
        assert result.reason in case.expected.reasons
    elif case.expected.outcome == "none":
        assert result.kind == "silence"
        assert result.choices == ()
    else:
        assert result.kind == "direct"
        assert result.choices in case.expected.acceptable_choices


def test_multiple_targets_are_all_kept_or_explicitly_blocked() -> None:
    result = route_rules(snapshot("direct_capacity"))
    assert result.kind == "blocked"
    assert result.requested_targets == ("ann-0", "ning-0")
    assert result.choices == ()


def test_mentions_override_only_the_implied_reply_recipient() -> None:
    result = route_rules(snapshot("mention_overrides_reply"))
    assert result.reason == "explicit_mentions"
    assert [c.speaker for c in result.choices] == ["ning-0"]


def test_context_action_is_not_replaced_by_incidental_mentions() -> None:
    result = route_rules(snapshot("context_action"))
    assert result.reason == "context_action"
    assert result.choices[0].target_message_id == snapshot("context_action").messages[0].id
    assert result.choices[0].speaker == "ann-0"


@pytest.mark.parametrize(
    "family",
    (
        "single_mention",
        "reply_character",
        "multiple_mentions",
        "direct_capacity",
        "deleted_trigger",
        "missing_content",
    ),
)
def test_direct_or_blocked_input_cannot_reach_director(family: str) -> None:
    with pytest.raises(ValueError, match="ambiguous-turn"):
        build_director_input(snapshot(family))


def test_private_source_is_filtered_before_prompt_serialization() -> None:
    view = build_director_input(snapshot("foreign_prompt_injection"))
    assert "PRIVATE_SENTINEL" not in view.user_prompt
    assert "private-0" not in view.user_prompt
    assert "owner-0" not in view.user_prompt
    assert "expected" not in view.user_prompt
    assert "label_review" not in view.user_prompt


@pytest.mark.parametrize(
    "field", ("owner_id", "connection_id", "guild_id", "channel_id", "thread_id")
)
def test_each_scope_dimension_filters_roles_and_messages(field: str) -> None:
    raw = snapshot().model_dump(mode="json")
    raw["messages"][0]["scope"][field] = "foreign"
    raw["messages"][0]["text"] = "PRIVATE_SENTINEL"
    raw["roles"][0]["scope"][field] = "foreign"
    raw["roles"][0]["public_description"] = "PRIVATE_ROLE_SENTINEL"
    view = build_director_input(RoutingSnapshot.model_validate_json(json.dumps(raw)))
    assert "PRIVATE" not in view.user_prompt
    assert {r.deployment_id for r in view.roles} == {"ning-0"}


def test_input_is_bounded_without_losing_an_older_trigger() -> None:
    original = snapshot()
    messages = tuple(
        original.messages[0].model_copy(update={"id": f"message-{i}"}) for i in range(40)
    )
    value = original.model_copy(update={"messages": messages, "trigger_message_id": "message-0"})
    view = build_director_input(value, max_messages=4)
    assert [m.id for m in view.messages] == ["message-0", "message-37", "message-38", "message-39"]
    with pytest.raises(ValueError, match="budget"):
        build_director_input(value, max_input_chars=5)


def test_prompt_fingerprint_binds_scope_revision_and_text() -> None:
    original = snapshot()
    base = build_director_input(original).fingerprint
    assert build_director_input(original.model_copy(update={"revision": 2})).fingerprint != base
    messages = (original.messages[0].model_copy(update={"text": "different"}), original.messages[1])
    assert (
        build_director_input(original.model_copy(update={"messages": messages})).fingerprint != base
    )


@pytest.mark.parametrize(
    "text",
    (
        "{}",
        '{"speaker":"ann-0","target_message_id":null,"mode":"direct_answer"}',
        '{"speaker":null,"target_message_id":null,"mode":"supplement"}',
        '{"speaker":"ann-0","target_message_id":"human_banter-0:2","mode":"none"}',
        '{"speaker":null,"target_message_id":null,"mode":"none","reason":"because"}',
        '{"speaker":null,"speaker":"ann-0","target_message_id":null,"mode":"none"}',
        'Here is JSON: {"speaker":null,"target_message_id":null,"mode":"none"}',
        '```json\n{"speaker":null,"target_message_id":null,"mode":"none"}\n```',
        '{"speaker":"foreign","target_message_id":"human_banter-0:2","mode":"reaction"}',
        '{"speaker":"ann-0","target_message_id":"secret","mode":"reaction"}',
        '{"speaker":"NONE","target_message_id":null,"mode":"none"}',
        "[]",
        "null",
        '{"speaker":true,"target_message_id":null,"mode":"none"}',
    ),
)
def test_invalid_output_is_not_a_successful_silence(text: str) -> None:
    text = text.replace("human_banter-0:2", snapshot().trigger_message_id)
    with pytest.raises(ValueError):
        validate_decision(text, build_director_input(snapshot()))


def test_none_and_useful_contribution_are_both_valid() -> None:
    view = build_director_input(snapshot())
    none = validate_decision('{"speaker":null,"target_message_id":null,"mode":"none"}', view)
    assert none.choices() == ()
    decision = validate_decision(
        json.dumps(
            {"speaker": "ann-0", "target_message_id": view.messages[0].id, "mode": "supplement"}
        ),
        view,
    )
    assert decision.choices()[0].target_message_id == view.messages[0].id


def test_unavailable_or_trimmed_messages_cannot_be_targets() -> None:
    original = snapshot()
    unavailable = original.messages[0].model_copy(update={"content_available": False})
    value = original.model_copy(update={"messages": (unavailable, original.messages[1])})
    view = build_director_input(value)
    assert json.loads(view.user_prompt)["messages"][0]["text"] == ""
    with pytest.raises(ValueError, match="target"):
        validate_decision(
            json.dumps(
                {
                    "speaker": "ann-0",
                    "target_message_id": original.messages[0].id,
                    "mode": "reaction",
                }
            ),
            view,
        )
    short = build_director_input(original, max_messages=1)
    with pytest.raises(ValueError, match="target"):
        validate_decision(
            json.dumps(
                {
                    "speaker": "ann-0",
                    "target_message_id": original.messages[0].id,
                    "mode": "reaction",
                }
            ),
            short,
        )


def test_caller_runs_once_and_preserves_all_attempts_without_repair() -> None:
    calls = []
    receipts = (
        AttemptReceipt(provider="fake", model="model-a", outcome="timeout", latency_ms=20),
        AttemptReceipt(provider="fake", model="model-b", outcome="success", latency_ms=5),
    )

    def caller(system: str, user: str, schema: dict[str, object]) -> DirectorReply:
        calls.append((system, user, schema))
        return DirectorReply(text="bad json", attempts=receipts)

    result = call_director(build_director_input(snapshot()), caller)
    assert result.outcome == "invalid" and result.decision is None
    assert result.attempts == receipts
    assert len(calls) == 1
    assert "expected" not in calls[0][1]


def test_provider_unavailability_is_distinct_from_none() -> None:
    attempt = AttemptReceipt(provider="fake", model="model", outcome="timeout", latency_ms=4)

    def caller(*_) -> DirectorReply:
        raise DirectorUnavailable((attempt,))

    result = call_director(build_director_input(snapshot()), caller)
    assert result.outcome == "unavailable" and result.decision is None
    assert result.attempts == (attempt,)


@pytest.mark.parametrize(
    "mutation",
    (
        "duplicate_message",
        "duplicate_role",
        "human_deployment",
        "unknown_field",
        "private_card",
        "negative_capacity",
    ),
)
def test_malformed_normalized_snapshot_is_rejected(mutation: str) -> None:
    raw = snapshot().model_dump(mode="json")
    if mutation == "duplicate_message":
        raw["messages"].append(raw["messages"][0])
    elif mutation == "duplicate_role":
        raw["roles"].append(raw["roles"][0])
    elif mutation == "human_deployment":
        raw["messages"][0]["author_deployment_id"] = "ann-0"
    elif mutation == "unknown_field":
        raw["tool_grant"] = "all"
    elif mutation == "private_card":
        raw["roles"][0]["private_card"] = "secret"
    else:
        raw["capacity_remaining"] = -1
    with pytest.raises(ValidationError):
        RoutingSnapshot.model_validate_json(json.dumps(raw))


def test_authenticated_context_action_keeps_requester_distinct_from_bot_source() -> None:
    original = snapshot("context_action")
    selected = original.messages[0].model_copy(
        update={"author_kind": "character", "author_deployment_id": "ning-0"}
    )
    value = original.model_copy(
        update={"messages": (selected, original.messages[1]), "trigger_message_id": selected.id}
    )
    result = route_rules(value)
    assert result.kind == "direct"
    assert result.requester_id == "operator-0"
    assert result.choices[0].speaker == "ann-0"
    assert result.choices[0].mode == "direct_answer"
    assert result.choices[0].target_message_id == selected.id


def test_bot_invitation_does_not_create_a_human_requester() -> None:
    result = route_rules(snapshot("explicit_bot_invitation"))
    assert result.kind == "direct"
    assert result.requester_id is None
    assert result.choices[0].mode == "continuation"


@pytest.mark.parametrize("family", ("single_mention", "reply_character", "multiple_mentions"))
def test_direct_route_preserves_actual_human_requester_and_all_targets(family: str) -> None:
    value = snapshot(family)
    trigger = next(m for m in value.messages if m.id == value.trigger_message_id)
    result = route_rules(value)
    assert result.requester_id == trigger.author_id
    assert result.requested_targets == tuple(c.speaker for c in result.choices)
    assert result.requested_targets


def test_unavailable_explicit_role_remains_a_tracked_target() -> None:
    result = route_rules(snapshot("disabled_target"))
    assert result.kind == "blocked"
    assert result.reason == "explicit_target_unavailable"
    assert result.requested_targets == ("ann-0",)


@pytest.mark.parametrize("capacity", (0, 1))
def test_ambient_capacity_boundary_is_not_semantic_silence(capacity: int) -> None:
    result = route_rules(snapshot().model_copy(update={"capacity_remaining": capacity}))
    if capacity == 0:
        assert result.kind == "blocked"
        assert result.reason == "capacity"
    else:
        assert result.kind == "director"
        assert result.reason == "ambiguous_room_turn"


def test_valid_json_at_exact_output_limit_and_one_over() -> None:
    view = build_director_input(snapshot())
    valid = '{"speaker":null,"target_message_id":null,"mode":"none"}'
    assert validate_decision(valid.ljust(4096), view).mode == "none"
    with pytest.raises(ValueError):
        validate_decision(valid.ljust(4097), view)


@pytest.mark.parametrize("first_value", ('"ann-0"', "null"))
def test_duplicate_keys_rejected_even_when_last_values_form_valid_none(first_value: str) -> None:
    text = '{"speaker":' + first_value + ',"speaker":null,"target_message_id":null,"mode":"none"}'
    with pytest.raises(ValueError):
        validate_decision(text, build_director_input(snapshot()))


def test_ineligible_role_is_filtered_before_director_input() -> None:
    original = snapshot()
    roles = (original.roles[0].model_copy(update={"eligible": False}), original.roles[1])
    view = build_director_input(original.model_copy(update={"roles": roles}))
    assert {role.deployment_id for role in view.roles} == {"ning-0"}


def test_deleted_context_message_is_filtered_before_director_input() -> None:
    original = snapshot()
    deleted = original.messages[0].model_copy(update={"deleted": True, "text": "DELETED_SENTINEL"})
    view = build_director_input(
        original.model_copy(update={"messages": (deleted, original.messages[1])})
    )
    assert "DELETED_SENTINEL" not in view.user_prompt
    assert {message.id for message in view.messages} == {original.trigger_message_id}
