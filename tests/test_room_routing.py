from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from echo_masque.room_routing import (
    DirectorPolicy,
    ModelIdentity,
    ProviderReply,
    RoomDecision,
    RoomInput,
    RoomMessage,
    RoomRole,
    RoomScope,
    RoutingResult,
    parse_decision,
    route_direct,
    route_rules_only,
    route_with_director,
)

SCOPE = RoomScope(owner_id="owner", connection_id="conn", guild_id="guild", channel_id="room")
FOREIGN = SCOPE.model_copy(update={"native_thread_id": "private"})
FREE = ModelIdentity(provider="test", model="small", tier="free")
OTHER = ModelIdentity(provider="test", model="backup", tier="free")
PAID = ModelIdentity(provider="test", model="paid", tier="paid")
NONE = '{"speaker":null,"target_message_id":null,"mode":"none"}'
SPEAK = '{"speaker":"ann","target_message_id":"m1","mode":"supplement"}'
POLICY = DirectorPolicy(qualified_models=(FREE, OTHER))


def room(**updates: object) -> RoomInput:
    values: dict[str, object] = {
        "scope": SCOPE, "revision": 4, "trigger_message_id": "m1",
        "roles": tuple(
            RoomRole(deployment_id=role, scope=SCOPE, public_name=role)
            for role in ("ann", "ning")
        ),
        "messages": (RoomMessage(
            message_id="m1", scope=SCOPE, author_id="human", text="Anyone have a useful addition?",
            visible_to=("ann", "ning"),
        ),),
    }
    values.update(updates)
    return RoomInput.model_validate(values)


def altered_message(snapshot: RoomInput, **updates: object) -> RoomInput:
    data = snapshot.messages[0].model_dump()
    data.update(updates)
    message = RoomMessage.model_validate(data)
    return snapshot.model_copy(update={"messages": (message,)})


@dataclass
class FakeProvider:
    identity: ModelIdentity = FREE
    content: str = NONE
    delay: float = 0
    failure: Exception | None = None
    calls: list[tuple[str, str, int]] = field(default_factory=list)

    async def complete(self, *, system: str, user: str, max_output_tokens: int) -> ProviderReply:
        self.calls.append((system, user, max_output_tokens))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure:
            raise self.failure
        return ProviderReply(content=self.content, input_tokens=25, output_tokens=8, cost_usd=0.0)


def run(
    snapshot: RoomInput, *providers: FakeProvider, policy: DirectorPolicy = POLICY,
) -> RoutingResult:
    return asyncio.run(route_with_director(snapshot, providers, policy))


@pytest.mark.parametrize("content", [
    '{}', 'null', '[]', '```json\n' + NONE + '\n```',
    '{"speaker":"NONE","target_message_id":null,"mode":"none"}',
    '{"speaker":"ann","target_message_id":null,"mode":"supplement"}',
    '{"speaker":null,"target_message_id":null,"mode":"none","tools":["delete"]}',
    '{"speaker":null,"speaker":"ann","target_message_id":null,"mode":"none"}',
    '{"speaker":12,"target_message_id":"m1","mode":"supplement"}',
    '{"speaker":NaN,"target_message_id":null,"mode":"none"}',
    '{"speaker":"stranger","target_message_id":"m1","mode":"supplement"}',
    '{"speaker":"ann","target_message_id":"private","mode":"supplement"}',
    'x' * 4097,
])
def test_strict_model_contract_rejects_ambiguous_or_unauthorized_output(content: str) -> None:
    with pytest.raises(ValueError):
        parse_decision(content, {"ann"}, {"m1"})


def test_valid_none_and_speaking_contract() -> None:
    assert parse_decision(NONE, {"ann"}, {"m1"}).mode == "none"
    assert parse_decision(SPEAK, {"ann"}, {"m1"}).speaker == "ann"


def test_explicit_mention_bypasses_even_a_broken_provider() -> None:
    snapshot = altered_message(room(), mentioned_deployment_ids=("ann",))
    provider = FakeProvider(failure=RuntimeError("must not run"))
    result = run(snapshot, provider)
    assert result.origin == "direct"
    assert result.decisions[0].speaker == "ann"
    assert not result.attempts and not provider.calls


def test_multiple_explicit_mentions_preserve_deferred_requests() -> None:
    snapshot = altered_message(room(), mentioned_deployment_ids=("ann", "ning", "ann"))
    result = run(snapshot)
    assert result.status == "partial"
    assert [item.speaker for item in result.decisions] == ["ann"]
    assert [(item.deployment_id, item.reason) for item in result.deferred] == [("ning", "capacity")]
    result = run(snapshot.model_copy(update={"remaining_turns": 2}))
    assert result.status == "selected"
    assert {item.speaker for item in result.decisions} == {"ann", "ning"}


def test_unavailable_direct_role_never_retargets_another_role() -> None:
    provider = FakeProvider(content=SPEAK)
    result = run(altered_message(room(), mentioned_deployment_ids=("missing",)), provider)
    assert result.status == "blocked" and not result.decisions
    assert result.deferred[0].deployment_id == "missing"
    assert not provider.calls


def test_reply_routes_to_actual_role_but_explicit_mention_wins_conflict() -> None:
    snapshot = altered_message(room(), reply_to_id="parent")
    parent = RoomMessage(
        message_id="parent", scope=SCOPE, author_id="webhook", author_deployment_id="ning",
        visible_to=("ann", "ning"), text="Previous reply",
    )
    snapshot = snapshot.model_copy(update={"messages": (parent, *snapshot.messages)})
    result = route_direct(snapshot)
    assert result and result.decisions[0].speaker == "ning"
    trigger = snapshot.messages[-1].model_copy(update={"mentioned_deployment_ids": ("ann",)})
    result = route_direct(snapshot.model_copy(update={"messages": (parent, trigger)}))
    assert result and result.decisions[0].speaker == "ann"
    assert result.decisions[0].target_message_id == "m1"


def test_manual_role_selection_has_priority() -> None:
    snapshot = altered_message(room(), mentioned_deployment_ids=("ning",))
    result = route_direct(snapshot.model_copy(update={"action_deployment_ids": ("ann",)}))
    assert result and result.decisions[0].speaker == "ann"


@pytest.mark.parametrize("text", ['Ann said "@Ning answer"', 'everyone is away', 'Annette is here'])
def test_names_and_quoted_text_are_not_platform_mentions(text: str) -> None:
    snapshot = altered_message(room(), text=text)
    assert route_direct(snapshot) is None
    assert route_rules_only(snapshot).status == "none"


@pytest.mark.parametrize("updates", [
    {"deleted": True}, {"scope": FOREIGN}, {"content_available": False}, {"visible_to": ("ning",)},
    {"targetable": False},
])
def test_unreadable_direct_source_cannot_be_admitted(updates: dict[str, object]) -> None:
    snapshot = altered_message(room(), mentioned_deployment_ids=("ann",), **updates)
    result = run(snapshot, FakeProvider(content=SPEAK))
    assert result.status == "blocked" and not result.decisions


def test_missing_reply_source_is_not_ambient_fallback() -> None:
    provider = FakeProvider()
    result = run(altered_message(room(), reply_to_id="unfetched"), provider)
    assert result.reason == "reply_source_unavailable"
    assert not provider.calls


def test_private_reply_parent_is_not_a_public_direct_route() -> None:
    snapshot = altered_message(room(), reply_to_id="parent")
    parent = RoomMessage(
        message_id="parent", scope=SCOPE, author_id="webhook", author_deployment_id="ning",
        visible_to=("ann",), text="Do not disclose",
    )
    result = run(
        snapshot.model_copy(update={"messages": (parent, *snapshot.messages)}), FakeProvider(),
    )
    assert result.status == "blocked" and result.deferred[0].deployment_id == "ning"


def test_direct_capacity_exhaustion_is_not_successful_none() -> None:
    snapshot = altered_message(room(remaining_turns=0), mentioned_deployment_ids=("ann",))
    result = run(snapshot)
    assert result.status == "blocked" and result.deferred[0].reason == "capacity"
    assert run(room(remaining_turns=0)).reason == "capacity"


def test_director_can_choose_none_without_trying_every_provider() -> None:
    primary, backup = FakeProvider(), FakeProvider(identity=OTHER, content=SPEAK)
    result = run(room(), primary, backup)
    assert result.status == "none" and len(result.attempts) == 1
    assert not backup.calls
    assert result.attempts[0].input_tokens == 25
    assert result.prompt_sha256 and len(result.prompt_sha256) == 64


def test_director_selects_a_visible_older_target_not_necessarily_latest() -> None:
    older = RoomMessage(
        message_id="old", scope=SCOPE, author_id="human2", visible_to=("ann", "ning"),
    )
    snapshot = room(messages=(older, *room().messages))
    result = run(snapshot, FakeProvider(content=SPEAK.replace('"m1"', '"old"')))
    assert result.status == "selected" and result.decisions[0].target_message_id == "old"


def test_prompt_filters_cross_scope_and_per_character_private_context() -> None:
    forbidden = RoomMessage(
        message_id="secret", scope=FOREIGN, author_id="human2", text="SECRET_X",
        visible_to=("ann", "ning"),
    )
    private = forbidden.model_copy(update={
        "message_id": "private", "scope": SCOPE, "visible_to": ("ann",), "text": "SECRET_Y",
    })
    snapshot = room(messages=(forbidden, private, *room().messages))
    provider = FakeProvider()
    run(snapshot, provider)
    prompt = provider.calls[0][1]
    assert "SECRET_X" not in prompt and "SECRET_Y" not in prompt
    assert "owner_id" not in prompt and "visible_to" not in prompt
    assert [message["id"] for message in json.loads(prompt)["messages"]] == ["m1"]


def test_foreign_candidate_is_not_in_prompt_or_valid_output() -> None:
    snapshot = room()
    other = snapshot.roles[-1].model_copy(update={
        "scope": FOREIGN, "public_description": "PRIVATE",
    })
    provider = FakeProvider(content=SPEAK.replace('"ann"', '"ning"'))
    result = run(snapshot.model_copy(update={"roles": (snapshot.roles[0], other)}), provider)
    assert result.status == "invalid" and "PRIVATE" not in provider.calls[0][1]


def test_prompt_budget_and_trimming_preserve_trigger() -> None:
    snapshot = room()
    more = tuple(snapshot.messages[0].model_copy(update={
        "message_id": f"new{i}", "text": "context " * 150,
    }) for i in range(10))
    provider = FakeProvider()
    policy = POLICY.model_copy(update={"max_prompt_chars": 2000, "max_messages": 3})
    run(
        snapshot.model_copy(update={"messages": (*snapshot.messages, *more)}),
        provider, policy=policy,
    )
    system, user, _ = provider.calls[0]
    assert len(system) + len(user) <= 2000
    assert "m1" in {message["id"] for message in json.loads(user)["messages"]}
    too_large = altered_message(room(), text="x" * 4000)
    rejected = FakeProvider()
    assert run(too_large, rejected, policy=policy).status == "blocked"
    assert not rejected.calls


def test_excluded_or_non_targetable_ids_are_rejected() -> None:
    source = RoomMessage(
        message_id="background", scope=SCOPE, author_id="human", targetable=False,
        visible_to=("ann", "ning"),
    )
    snapshot = room(messages=(source, *room().messages))
    provider = FakeProvider(content=SPEAK.replace('"m1"', '"background"'))
    assert run(snapshot, provider).status == "invalid"


def test_only_qualified_free_providers_run_with_bounded_attempts() -> None:
    paid = FakeProvider(identity=PAID)
    unknown = FakeProvider(identity=FREE.model_copy(update={"model": "unqualified"}))
    broken = FakeProvider(content='{}')
    backup = FakeProvider(identity=OTHER, content=SPEAK)
    result = run(room(), paid, unknown, broken, backup)
    assert result.status == "selected" and len(result.attempts) == 2
    assert not paid.calls and not unknown.calls
    assert result.attempts[0].status == "invalid"
    assert result.attempts[1].status == "ok"
    assert run(room(), paid, unknown).status == "unavailable"
    assert run(room(), FakeProvider(content='{}'), FakeProvider(identity=OTHER),
               policy=POLICY.model_copy(update={"max_attempts": 1})).status == "invalid"


def test_qualified_list_cannot_enable_paid_fallback() -> None:
    provider = FakeProvider(identity=PAID)
    result = run(room(), provider, policy=DirectorPolicy(qualified_models=(PAID,)))
    assert result.status == "unavailable" and not provider.calls


def test_timeout_stops_total_deadline_and_does_not_call_backup() -> None:
    provider, backup = FakeProvider(delay=0.1), FakeProvider(identity=OTHER)
    result = run(
        room(), provider, backup, policy=POLICY.model_copy(update={"deadline_seconds": 0.01}),
    )
    assert result.status == "error" and result.attempts[0].status == "timeout"
    assert result.attempts[0].input_tokens is None
    assert not backup.calls


def test_provider_error_body_is_not_saved_as_metadata() -> None:
    result = run(room(), FakeProvider(failure=RuntimeError("api-key-SECRET-transcript")))
    assert result.status == "error" and "SECRET" not in result.model_dump_json()
    assert result.attempts[0].cost_usd is None


def test_cancellation_propagates() -> None:
    async def exercise() -> None:
        task = asyncio.create_task(route_with_director(room(), (FakeProvider(delay=1),), POLICY))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(exercise())


def test_duplicate_source_ids_and_unbounded_input_rejected() -> None:
    snapshot = room()
    with pytest.raises(ValidationError):
        room(messages=(*snapshot.messages, *snapshot.messages))
    with pytest.raises(ValidationError):
        RoomDecision(speaker=None, target_message_id=None, mode="supplement")
    with pytest.raises(ValidationError):
        altered_message(snapshot, text="x" * 4001)
    with pytest.raises(ValidationError):
        RoutingResult(origin="director", status="none", reason="fake", source_revision=4)


def test_real_provider_model_identifiers_are_supported() -> None:
    model = ModelIdentity(provider="cloudflare", model="@cf/vendor/model:free", tier="free")
    assert model.model == "@cf/vendor/model:free"


def test_frozen_snapshot_contract_roundtrips_without_private_role_fields() -> None:
    snapshot = room()
    assert RoomInput.model_validate_json(snapshot.model_dump_json()) == snapshot
    data = snapshot.roles[0].model_dump()
    data["private_notes"] = "must not be supplied to director"
    with pytest.raises(ValidationError):
        RoomRole.model_validate(data)
