import asyncio
from typing import cast

from echo_masque.api.connector_schemas import DiscordConnectorReplyView, DiscordInboundMessage
from echo_masque.api.social_turn_schemas import DiscordSocialTurnStepRequest
from echo_masque.orchestration.character_turn_graph import (
    CharacterTurnGraphResult,
    CharacterTurnGraphState,
)
from echo_masque.orchestration.social_turn_graph import SocialTurnGraphRunner
from echo_masque.orchestration.trace import RuntimeTraceEvent


def payload(deployment_id: str, *, author_is_bot: bool = False) -> DiscordInboundMessage:
    return DiscordInboundMessage.model_validate(
        {
            "connection_id": "connection-1",
            "deployment_id": deployment_id,
            "message_id": "message-1",
            "guild_id": "guild-1",
            "guild_name": "Guild",
            "channel_id": "channel-1",
            "channel_name": "general",
            "category_id": "",
            "thread_id": "",
            "thread_name": "",
            "author_id": "character:source" if author_is_bot else "user-1",
            "author_display_name": "Source" if author_is_bot else "Juen",
            "text": "private social turn text",
            "mentioned_bot": True,
            "replied_to_bot": False,
            "smart_candidate": not author_is_bot,
            "author_is_bot": author_is_bot,
            "recent_messages": [],
        }
    )


def character_result(
    deployment_id: str,
    *,
    invite: str = "",
    mentions: tuple[str, ...] = (),
) -> CharacterTurnGraphResult:
    return CharacterTurnGraphResult(
        state=cast(
            CharacterTurnGraphState,
            {
                "graph_name": "character_turn",
                "status": "completed",
                "outcome": "reply",
                "deployment_id": deployment_id,
            },
        ),
        reply=DiscordConnectorReplyView(
            action="reply",
            reason="fixture",
            deployment_id=deployment_id,
            character_display_name=deployment_id.upper(),
            text=f"reply from {deployment_id}",
        ),
        invite_candidate_deployment_id=invite,
        mentioned_character_deployment_ids=mentions,
    )


class FakeCharacterRunner:
    def __init__(self, results: dict[str, CharacterTurnGraphResult]) -> None:
        self.results = results
        self.calls: list[str] = []

    async def run(self, incoming: DiscordInboundMessage) -> CharacterTurnGraphResult:
        self.calls.append(incoming.deployment_id)
        return self.results[incoming.deployment_id]


class TraceCollector:
    def __init__(self) -> None:
        self.events: list[RuntimeTraceEvent] = []

    def emit(self, event: RuntimeTraceEvent) -> None:
        self.events.append(event)


def request(
    deployment_id: str,
    *,
    initial: list[str],
    available: list[str],
    cursor: object = None,
    budget: int = 8,
    max_depth: int = 4,
    author_is_bot: bool = False,
) -> DiscordSocialTurnStepRequest:
    return DiscordSocialTurnStepRequest.model_validate(
        {
            "payload": payload(deployment_id, author_is_bot=author_is_bot).model_dump(),
            "initial_deployment_ids": initial,
            "available_deployment_ids": available,
            "continuation_budget": budget,
            "max_depth": max_depth,
            "cursor": cursor,
        }
    )


def test_social_turn_preserves_initial_order_across_delivery_steps() -> None:
    fake = FakeCharacterRunner({"a": character_result("a"), "b": character_result("b")})
    runner = SocialTurnGraphRunner(fake)  # type: ignore[arg-type]

    first = asyncio.run(runner.run(request("a", initial=["a", "b"], available=["a", "b"])))
    assert first.view.current_deployment_id == "a"
    assert first.view.next_turn is not None
    assert first.view.next_turn.deployment_id == "b"
    assert first.view.next_turn.origin == "selected"
    assert first.view.done is False
    assert first.view.cursor.completed_deployment_ids == ["a"]

    second = asyncio.run(
        runner.run(
            request(
                "b",
                initial=["a", "b"],
                available=["a", "b"],
                cursor=first.view.cursor.model_dump(),
            )
        )
    )
    assert second.view.done is True
    assert second.view.next_turn is None
    assert second.view.cursor.completed_deployment_ids == ["a", "b"]
    assert fake.calls == ["a", "b"]


def test_direct_requests_precede_continuation_and_distinct_roles_are_bounded() -> None:
    fake = FakeCharacterRunner({"a": character_result("a", invite="c", mentions=("c", "d", "b"))})
    runner = SocialTurnGraphRunner(fake)  # type: ignore[arg-type]
    result = asyncio.run(
        runner.run(request("a", initial=["a", "b"], available=["a", "b", "c", "d"], budget=2))
    )
    assert [p.deployment_id for p in result.view.cursor.pending_turns] == ["b", "c"]
    assert [p.origin for p in result.view.cursor.pending_turns] == ["selected", "invite"]
    assert result.view.cursor.continuation_budget_remaining == 1
    assert result.state["continuation_candidate_ids"] == ("c",)


def test_bounded_reentry_a_b_a_is_allowed_without_repeating_forever() -> None:
    fake = FakeCharacterRunner(
        {"a": character_result("a", mentions=("b",)), "b": character_result("b", mentions=("a",))}
    )
    trace = TraceCollector()
    runner = SocialTurnGraphRunner(fake, trace_sink=trace)  # type: ignore[arg-type]
    cursor = None
    for role in ("a", "b", "a", "b"):
        result = asyncio.run(
            runner.run(
                request(
                    role,
                    initial=["a"],
                    available=["a", "b"],
                    cursor=cursor,
                    author_is_bot=cursor is not None,
                    max_depth=5,
                )
            )
        )
        cursor = result.view.cursor.model_dump()
    assert result.view.cursor.completed_deployment_ids == ["a", "b", "a", "b"]
    assert result.view.cursor.attempts_used == 4
    assert result.view.done
    assert fake.calls == ["a", "b", "a", "b"]
    assert "private social turn text" not in repr(trace.events)


def test_ignored_draft_never_counts_or_schedules_another_speaker() -> None:
    ignored = character_result("a", mentions=("b",))
    ignored.reply.action = "silent"
    fake = FakeCharacterRunner({"a": ignored})
    runner = SocialTurnGraphRunner(fake)  # type: ignore[arg-type]
    result = asyncio.run(runner.run(request("a", initial=["a"], available=["a", "b"])))
    assert not result.view.cursor.completed_deployment_ids
    assert result.view.cursor.attempts_used == 1
    assert result.view.done


def test_bot_invite_claim_does_not_launder_human_authority() -> None:
    fake = FakeCharacterRunner({"a": character_result("a", invite="b")})
    runner = SocialTurnGraphRunner(fake)  # type: ignore[arg-type]
    result = asyncio.run(
        runner.run(request("a", initial=["a"], available=["a", "b"], author_is_bot=True))
    )
    assert result.view.done


def test_exhausted_attempts_or_speaking_limits_stop_before_model() -> None:
    import pytest

    fake = FakeCharacterRunner({"a": character_result("a")})
    runner = SocialTurnGraphRunner(fake)  # type: ignore[arg-type]
    for cursor in (
        {"attempts_used": 12},
        {"completed_deployment_ids": ["a", "b", "a"]},
        {"completed_deployment_ids": ["b", "c", "d"]},
    ):
        cursor["pending_turns"] = [{"deployment_id": "a"}]
        with pytest.raises(ValueError, match="budget"):
            asyncio.run(
                runner.run(
                    request("a", initial=["a"], available=["a", "b", "c", "d"], cursor=cursor)
                )
            )
    assert not fake.calls
