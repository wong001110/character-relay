from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from echo_masque.context_resolver_v3 import ContextResolverV3
from echo_masque.internal_context import InternalContextService
from echo_masque.persistence import Database
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.entity_evidence_repository import EntityEvidenceRepository
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service
from echo_masque.tool_runtime import ToolExecutionContext


class _Routes:
    def __init__(self, visible_message_ids: set[str]) -> None:
        self.visible_message_ids = visible_message_ids

    def resolve_message_route(self, *, connection_id: str, message_id: str) -> object | None:
        if connection_id == "connection-1" and message_id in self.visible_message_ids:
            return SimpleNamespace(deployment_id="deployment-1")
        return None


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="character-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        initiator_user_id="actor-1",
    )


def _belief(
    repository: BeliefRepository,
    *,
    value: str,
    importance: float,
    owner: str = "owner-1",
    guild: str = "guild-1",
    character: str = "character-1",
) -> None:
    repository.create(
        owner_id=owner,
        character_card_id=character,
        connection_id="connection-1",
        guild_id=guild,
        subject_entity_id="",
        subject_ref="actor-1",
        predicate="personal.note",
        value_text=value,
        scope="character_server",
        authority_class="conversation",
        authority_score=0.8,
        origin="conversation",
        confidence=0.8,
        importance=importance,
        status="active",
        evidence_refs=("message:test",),
    )


def _episode(
    runtime: ConversationRuntimeRepository,
    *,
    key: str,
    summary: str,
    message_id: str,
    now: datetime,
    owner: str = "owner-1",
    guild: str = "guild-1",
) -> object:
    created = runtime.append_episode_segment(
        owner_id=owner,
        connection_id="connection-1",
        guild_id=guild,
        channel_id="general",
        discord_thread_id="",
        conversation_thread_id=f"thread-{key}",
        segment_id=f"segment-{key}",
        source_message_ids=(message_id,),
        participant_ids=("actor-1",),
        summary=summary,
        key_events=(summary,),
        now=now,
    )
    return runtime.close_episode(
        owner_id=owner,
        conversation_thread_id=f"thread-{key}",
        reason="test",
        now=now,
    ) or created


def test_memory_search_finds_low_importance_belief_beyond_old_candidate_window() -> None:
    database = Database("sqlite://")
    database.initialize()
    beliefs = BeliefRepository(database)
    for index in range(160):
        _belief(beliefs, value=f"routine note {index}", importance=0.99)
    _belief(
        beliefs,
        value="The moonlit orchid is the actor's private recall phrase.",
        importance=0.01,
    )
    _belief(
        beliefs,
        value="moonlit orchid from another owner",
        importance=1.0,
        owner="owner-2",
    )
    _belief(
        beliefs,
        value="moonlit orchid from another server",
        importance=1.0,
        guild="guild-2",
    )
    _belief(
        beliefs,
        value="moonlit orchid for another character",
        importance=1.0,
        character="character-2",
    )
    service = InternalContextService(
        beliefs,
        ConversationStructureRepository(database),
        ConversationRuntimeRepository(database),
    )

    result = json.loads(service.memory_search({"query": "moonlit orchid", "limit": 5}, _context()))

    assert result["count"] == 1
    assert result["memories"][0]["value"] == (
        "The moonlit orchid is the actor's private recall phrase."
    )


def test_episode_recall_reaches_old_history_and_never_returns_unperceived_or_cross_scope_records(
) -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = ConversationRuntimeRepository(database)
    structure = ConversationStructureRepository(database)
    now = datetime(2026, 9, 1, tzinfo=UTC)
    # The former thread window stopped at 100.  Aggregate Thread prose is deliberately not
    # returned at any depth because its full message provenance cannot be proven perceived.
    for index in range(101):
        structure.create_thread(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="general",
            discord_thread_id="",
            canonical_label=(
                "moonlit orchid private thread" if index == 100 else f"routine thread {index}"
            ),
            anchor_summary="unperceived aggregate",
            working_summary="unperceived aggregate",
            now=now + timedelta(minutes=index),
        )
    old_visible = _episode(
        runtime,
        key="old-visible",
        summary="moonlit orchid was chosen for the release plan",
        message_id="visible-old",
        now=now,
    )
    for index in range(200):
        _episode(
            runtime,
            key=f"recent-{index}",
            summary=f"routine status update {index}",
            message_id=f"visible-recent-{index}",
            now=now + timedelta(minutes=index + 1),
        )
    _episode(
        runtime,
        key="hidden",
        summary="moonlit orchid hidden from this character",
        message_id="hidden-message",
        now=now + timedelta(days=1),
    )
    _episode(
        runtime,
        key="other-owner",
        summary="moonlit orchid other owner",
        message_id="other-owner-message",
        now=now,
        owner="owner-2",
    )
    _episode(
        runtime,
        key="other-server",
        summary="moonlit orchid other server",
        message_id="other-server-message",
        now=now,
        guild="guild-2",
    )
    routes = _Routes({"visible-old"})
    service = InternalContextService(
        BeliefRepository(database),
        structure,
        runtime,
        identities=routes,  # type: ignore[arg-type]
    )

    result = json.loads(
        service.conversation_search({"query": "moonlit orchid", "limit": 5}, _context())
    )

    assert [item["ref"] for item in result["results"]] == [old_visible.id]
    assert all(item["kind"] == "episode" for item in result["results"])

    resolver = ContextResolverV3(
        structure=structure,
        runtime=runtime,
        entities=EntityEvidenceRepository(database),
        beliefs=BeliefRepository(database),
        social=SocialIntelligenceV3Service(database),
        identities=routes,  # type: ignore[arg-type]
    )
    bundle = resolver.resolve(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        query="moonlit orchid",
        character_card_id="character-1",
        deployment_id="deployment-1",
        actor_id="actor-1",
    )
    assert [item.id for item in bundle.episodes] == [old_visible.id]


def test_episode_checkpoint_keeps_early_summary_within_the_existing_bound() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = ConversationRuntimeRepository(database)
    now = datetime(2026, 9, 1, tzinfo=UTC)
    runtime.append_episode_segment(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        conversation_thread_id="thread-summary",
        segment_id="segment-first",
        source_message_ids=("first",),
        participant_ids=("actor-1",),
        summary="Early decision: choose the moonlit orchid.",
        now=now,
    )
    updated = runtime.append_episode_segment(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        conversation_thread_id="thread-summary",
        segment_id="segment-later",
        source_message_ids=("later",),
        participant_ids=("actor-1",),
        summary="Later update: publication is scheduled.",
        now=now + timedelta(minutes=1),
    )

    assert "Early decision" in updated.summary
    assert "Later update" in updated.summary
    assert len(updated.summary) <= 4000
