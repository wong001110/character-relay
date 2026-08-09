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

    first = asyncio.run(
        runner.run(request("a", initial=["a", "b"], available=["a", "b"]))
    )
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


def test_validated_invite_and_mentions_expand_before_remaining_selected_turns() -> None:
    fake = FakeCharacterRunner(
        {
            "a": character_result("a", invite="c", mentions=("c", "d", "b")),
        }
    )
    runner = SocialTurnGraphRunner(fake)  # type: ignore[arg-type]

    result = asyncio.run(
        runner.run(
            request(
                "a",
                initial=["a", "b"],
                available=["a", "b", "c", "d"],
                budget=2,
            )
        )
    )

    assert [item.deployment_id for item in result.view.cursor.pending_turns] == ["c", "d", "b"]
    assert [item.origin for item in result.view.cursor.pending_turns] == [
        "invite",
        "mention",
        "selected",
    ]
    assert result.view.next_turn is not None
    assert result.view.next_turn.deployment_id == "c"
    assert result.view.cursor.continuation_budget_remaining == 0
    assert result.state["continuation_candidate_ids"] == ("c", "d")


def test_social_turn_blocks_duplicate_and_recursive_invite_expansion() -> None:
    fake = FakeCharacterRunner(
        {
            "a": character_result("a", invite="b", mentions=("b", "c")),
            "c": character_result("c", invite="d", mentions=("d",)),
            "d": character_result("d", mentions=("a",)),
        }
    )
    traces = TraceCollector()
    runner = SocialTurnGraphRunner(fake, trace_sink=traces)  # type: ignore[arg-type]

    first = asyncio.run(
        runner.run(
            request(
                "a",
                initial=["a", "b"],
                available=["a", "b", "c", "d"],
                budget=3,
                max_depth=2,
            )
        )
    )
    # b was already pending, so it is never duplicated. c is inserted as an explicit mention.
    assert [item.deployment_id for item in first.view.cursor.pending_turns] == ["c", "b"]
    assert first.view.cursor.continuation_budget_remaining == 2

    second = asyncio.run(
        runner.run(
            request(
                "c",
                initial=["a", "b"],
                available=["a", "b", "c", "d"],
                cursor=first.view.cursor.model_dump(),
                budget=3,
                max_depth=2,
                author_is_bot=True,
            )
        )
    )
    # Fake output tries to claim an invite from a bot-authored continuation. The graph ignores
    # the invite signal but still permits the already Runtime-resolved normal Character mention.
    assert [item.deployment_id for item in second.view.cursor.pending_turns] == ["d", "b"]
    assert second.view.cursor.pending_turns[0].origin == "mention"
    assert second.view.cursor.pending_turns[0].depth == 2

    third = asyncio.run(
        runner.run(
            request(
                "d",
                initial=["a", "b"],
                available=["a", "b", "c", "d"],
                cursor=second.view.cursor.model_dump(),
                budget=3,
                max_depth=2,
                author_is_bot=True,
            )
        )
    )
    # d is already at max depth, so its mention cannot expand another Character turn.
    assert third.view.next_turn is not None
    assert third.view.next_turn.deployment_id == "b"
    assert third.view.cursor.continuation_budget_remaining == 1
    assert "private social turn text" not in repr(traces.events)
