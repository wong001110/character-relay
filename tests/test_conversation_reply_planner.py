from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from echo_masque.conversation_reply_planner import CharacterSegmentReplyPlanner
from echo_masque.persistence import Database
from echo_masque.persistence.conversation_segment_repository import ConversationSegmentRepository
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord


class FakeSemantic:
    enabled = True

    def score(self, *, message: str, deployments: list[tuple[str, str, str]]):
        deployment_id, _, card_id = deployments[0]
        relevance = 0.92 if "SQL RAG" in message or "架构" in message else 0.21
        return (
            "fake",
            3,
            [
                SimpleNamespace(
                    deployment_id=deployment_id,
                    character_card_id=card_id,
                    relevance=relevance,
                    profile_ready=True,
                )
            ],
        )


def test_reply_planner_selects_one_relevant_segment_from_multi_thread_burst() -> None:
    database = Database("sqlite://")
    database.initialize()
    repo = ConversationSegmentRepository(database)
    now = datetime.now(UTC)
    first_thread = repo.create_thread(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        label="game video",
        summary="讨论游戏视频",
        keywords=("game",),
        now=now,
    )
    second_thread = repo.create_thread(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        label="Character Relay architecture",
        summary="讨论 SQL RAG 和 conversation architecture",
        keywords=("SQL", "RAG"),
        now=now,
    )
    segments = repo.record_segments(
        owner_id="owner-1",
        burst_id="burst-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        now=now,
        segments=(
            {
                "segment_key": "1",
                "message_ids": ("m1", "m2"),
                "participant_ids": ("u1",),
                "kind": "discussion",
                "summary": "这个游戏视频很好笑",
                "semantic_thread_id": first_thread.id,
                "thread_action": "attach",
                "thread_evidence": True,
                "confidence": 0.8,
                "source": "utility",
            },
            {
                "segment_key": "2",
                "message_ids": ("m3", "m4"),
                "participant_ids": ("u2",),
                "kind": "discussion",
                "summary": "Character Relay 的 SQL RAG 架构需要调整",
                "semantic_thread_id": second_thread.id,
                "thread_action": "attach",
                "thread_evidence": True,
                "confidence": 0.9,
                "source": "utility",
            },
        ),
    )
    deployment = CharacterDeploymentRecord(
        id="deployment-1",
        owner_id="owner-1",
        character_card_id="card-1",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-1",
        channel_id="general",
        participation_mode="smart",
    )
    target = CharacterSegmentReplyPlanner(FakeSemantic()).select(  # type: ignore[arg-type]
        deployment=deployment,
        segments=segments,
        latest_message_id="m4",
        deterministic_signals={},
    )
    assert target is not None
    assert target.segment_id == segments[1].id
    assert target.semantic_thread_id == second_thread.id
    assert "unrelated simultaneous discussions" in target.guidance


def test_reply_planner_direct_pressure_prefers_current_direct_segment() -> None:
    database = Database("sqlite://")
    database.initialize()
    repo = ConversationSegmentRepository(database)
    now = datetime.now(UTC)
    segments = repo.record_segments(
        owner_id="owner-1",
        burst_id="burst-2",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        now=now,
        segments=(
            {
                "segment_key": "1",
                "message_ids": ("m1",),
                "participant_ids": ("u1",),
                "kind": "discussion",
                "summary": "SQL RAG architecture",
                "semantic_thread_id": "t1",
                "thread_action": "attach",
                "thread_evidence": True,
                "confidence": 0.8,
                "source": "utility",
            },
            {
                "segment_key": "2",
                "message_ids": ("m2",),
                "participant_ids": ("u2",),
                "kind": "discussion",
                "summary": "请问你刚才说的那个视频呢",
                "semantic_thread_id": "t2",
                "thread_action": "attach",
                "thread_evidence": True,
                "confidence": 0.8,
                "source": "utility",
            },
        ),
    )
    deployment = CharacterDeploymentRecord(
        id="deployment-1",
        owner_id="owner-1",
        character_card_id="card-1",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-1",
        channel_id="general",
        participation_mode="smart",
    )
    target = CharacterSegmentReplyPlanner(FakeSemantic()).select(  # type: ignore[arg-type]
        deployment=deployment,
        segments=segments,
        latest_message_id="m2",
        deterministic_signals={"name_match": 10.0},
    )
    assert target is not None
    assert target.segment_id == segments[1].id
    assert target.reason.startswith("direct")
