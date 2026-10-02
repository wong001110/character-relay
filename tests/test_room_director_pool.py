"""Transport/qualification contract tests. Fake reports below are NOT live qualification."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError
from test_room_routing import snapshot

from echo_masque.providers.base import ProviderCompletion
from echo_masque.providers.errors import ProviderUnavailableError
from echo_masque.room_director import PROMPT_VERSION, build_director_input
from echo_masque.room_director_policy import DirectorQualification, RoomDirectorPolicy
from echo_masque.room_director_pool import RoomDirectorPool
from echo_masque.utility_gateway_contracts import UtilityRoute


def report(member: str = "one", **changes: object) -> DirectorQualification:
    now = datetime.now(UTC)
    return DirectorQualification.model_validate(
        {
            "member_id": member,
            "provider": "fixture",
            "base_url": "https://fixture.example/v1",
            "model": "fixture-model",
            "observed_model": "fixture-model",
            "prompt_version": PROMPT_VERSION,
            "corpus_sha256": "a" * 64,
            "report_sha256": "b" * 64,
            "case_count": 240,
            "expected_none_count": 80,
            "expected_contribution_count": 100,
            "labels_human_reviewed": True,
            "labels_reviewed_by": "TEST-ONLY-FAKE-REVIEWER",
            "none_precision": 0.95,
            "none_recall": 0.90,
            "joint_speaker_target_accuracy": 0.90,
            "missed_direct_responses": 0,
            "scope_violations": 0,
            "approved_at": now - timedelta(minutes=1),
            "expires_at": now + timedelta(days=1),
            **changes,
        }
    )


def route(member: str = "one", **changes: object) -> UtilityRoute:
    return UtilityRoute(
        **{
            "member_id": member,
            "provider": "fixture",
            "model": "fixture-model",
            "base_url": "https://fixture.example/v1",
            "tier": "free",
            "api_key": SecretStr("fixture"),
            "reason": "test",
            **changes,
        }
    )


def gateway(policy: RoomDirectorPolicy, routes: tuple = (route(),)) -> object:
    def free_routes(capability: str) -> tuple:
        assert capability == "room_director"
        assert all(item.tier == "free" for item in routes)
        return routes

    return SimpleNamespace(
        runtime=SimpleNamespace(config=lambda: SimpleNamespace(room_director=policy)),
        free_routes=free_routes,
        observe_director_transport=lambda *a, **kw: None,
    )


def completion(**changes: object) -> ProviderCompletion:
    return ProviderCompletion.model_validate(
        {
            "text": '{"speaker":null,"target_message_id":null,"mode":"none"}',
            "model": "fixture-model",
            "latency_ms": 2,
            **changes,
        }
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": False},
        {"qualifications": ()},
        {"qualifications": (report(labels_human_reviewed=False),)},
        {"qualifications": (report(scope_violations=1),)},
        {"qualifications": (report(prompt_version="old-prompt"),)},
        {
            "qualifications": (
                report(
                    approved_at=datetime.now(UTC) - timedelta(days=2),
                    expires_at=datetime.now(UTC) - timedelta(days=1),
                ),
            )
        },
    ],
)
def test_unqualified_never_calls_provider(changes: dict) -> None:
    policy = RoomDirectorPolicy.model_validate(
        {"enabled": True, "qualifications": (report(),), **changes}
    )

    def forbidden(*args: object) -> None:
        raise AssertionError("Unqualified model must not receive room content")

    result = asyncio.run(
        RoomDirectorPool(gateway(policy), provider_factory=forbidden).decide(
            build_director_input(snapshot())
        )
    )
    assert result.outcome == "unavailable"
    assert result.attempts == ()


def test_none_is_success_and_unknown_usage_is_not_zero_cost() -> None:
    calls = []

    class Provider:
        async def complete(self, **kwargs: object) -> ProviderCompletion:
            calls.append(kwargs)
            assert kwargs["response_format"] is None
            assert kwargs["max_output_tokens"] == 256
            assert "TEST-ONLY" not in repr(kwargs)
            return completion()

    pool = RoomDirectorPool(
        gateway(RoomDirectorPolicy(enabled=True, qualifications=(report(),))),
        provider_factory=lambda _: Provider(),
    )
    result = asyncio.run(pool.decide(build_director_input(snapshot())))
    assert result.outcome == "none"
    assert len(calls) == len(result.attempts) == 1
    assert result.attempts[0].input_tokens is None
    assert result.attempts[0].cost_usd is None


def test_transport_fallback_is_bounded_and_records_both_physical_attempts() -> None:
    calls = []

    class Provider:
        def __init__(self, member: str) -> None:
            self.member = member

        async def complete(self, **kwargs: object) -> ProviderCompletion:
            calls.append(self.member)
            if self.member == "one":
                raise ProviderUnavailableError("fixture failure")
            return completion(input_tokens=123, output_tokens=10)

    pool = RoomDirectorPool(
        gateway(
            RoomDirectorPolicy(enabled=True, qualifications=(report("one"), report("two"))),
            (route("one"), route("two")),
        ),
        provider_factory=lambda item: Provider(item.member_id),
    )
    result = asyncio.run(pool.decide(build_director_input(snapshot())))
    assert calls == ["one", "two"]
    assert result.outcome == "none"
    assert [item.outcome for item in result.attempts] == ["unavailable", "success"]
    assert result.attempts[1].input_tokens == 123


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "changed-model"},
        {"finish_reason": "length"},
        {"text": '{"speaker":null,"target_message_id":null,"mode":"none","extra":true}'},
        {"text": '{"speaker":"other-room","target_message_id":"m","mode":"supplement"}'},
    ],
)
def test_bad_response_never_retries_until_someone_speaks(changes: dict) -> None:
    calls = []

    class Provider:
        async def complete(self, **kwargs: object) -> ProviderCompletion:
            calls.append(1)
            return completion(**changes)

    pool = RoomDirectorPool(
        gateway(
            RoomDirectorPolicy(enabled=True, qualifications=(report("one"), report("two"))),
            (route("one"), route("two")),
        ),
        provider_factory=lambda _: Provider(),
    )
    result = asyncio.run(pool.decide(build_director_input(snapshot())))
    assert result.outcome == "invalid"
    assert len(calls) == 1


def test_total_deadline_does_not_reset_on_failover() -> None:
    calls = []

    class Provider:
        async def complete(self, **kwargs: object) -> ProviderCompletion:
            calls.append(1)
            await asyncio.sleep(1)
            return completion()

    policy = RoomDirectorPolicy(
        enabled=True, deadline_seconds=0.5, qualifications=(report("one"), report("two"))
    )
    pool = RoomDirectorPool(
        gateway(policy, (route("one"), route("two"))), provider_factory=lambda _: Provider()
    )
    result = asyncio.run(pool.decide(build_director_input(snapshot())))
    assert result.outcome == "unavailable"
    assert [item.outcome for item in result.attempts] == ["timeout"]
    assert len(calls) == 1


def test_configuration_and_prompt_changes_invalidate_evidence_binding() -> None:
    policy = RoomDirectorPolicy(enabled=True, qualifications=(report(),))

    def forbidden(*args: object) -> None:
        raise AssertionError("changed endpoint/model cannot reuse qualification")

    for item in (route(model="new-model"), route(base_url="https://other.example/v1")):
        result = asyncio.run(
            RoomDirectorPool(gateway(policy, (item,)), provider_factory=forbidden).decide(
                build_director_input(snapshot())
            )
        )
        assert result.outcome == "unavailable"
        assert not result.attempts
    with pytest.raises(ValidationError):
        RoomDirectorPolicy(max_attempts=3)
    with pytest.raises(ValidationError):
        RoomDirectorPolicy(qualifications=(report(), report()))


def test_diagnostic_failure_does_not_replay_an_obtained_decision() -> None:
    service = gateway(RoomDirectorPolicy(enabled=True, qualifications=(report(),)))

    def lost(*args: object, **kwargs: object) -> None:
        raise RuntimeError("diagnostic-only failure")

    service.observe_director_transport = lost

    class Provider:
        async def complete(self, **kwargs: object) -> ProviderCompletion:
            return completion()

    result = asyncio.run(
        RoomDirectorPool(service, provider_factory=lambda _: Provider()).decide(
            build_director_input(snapshot())
        )
    )
    assert result.outcome == "none"
    assert len(result.attempts) == 1
