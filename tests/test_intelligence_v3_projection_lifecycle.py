from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationMediaDescriptor,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.conversation_runtime import ConversationRuntimeCoordinator
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.entity_grounding_v3 import EntityGroundingService
from echo_masque.evidence_graph_v3 import EvidenceGraphService
from echo_masque.intelligence_v3_projection import ProjectionConversationRuntimeCoordinator
from echo_masque.persistence import Database
from echo_masque.persistence.belief_models import BeliefV3Record
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_models import ConversationEpisodeV3Record
from echo_masque.persistence.conversation_runtime_repository import (
    ConversationEpisodeV3View,
    ConversationRuntimeRepository,
)
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.entity_evidence_models import EvidenceEdgeV3Record
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    EvidenceEdgeV3View,
)


def _database() -> Database:
    database = Database("sqlite://")
    database.initialize()
    return database


def _api_settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email="phase4-admin@example.com",
        bootstrap_admin_password=SecretStr("Phase4Admin2026!"),
        bootstrap_admin_display_name="Phase 4 Admin",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def _projection_payload() -> SmartParticipationResolveRequest:
    messages = [
        SmartParticipationBurstMessage(
            message_id="projection-message-1",
            author_id="actor-1",
            text="Can we upload the recording?",
        ),
        SmartParticipationBurstMessage(
            message_id="projection-message-2",
            author_id="actor-2",
            text="Yes, reply to the first message.",
            reply_to_message_id="projection-message-1",
        ),
    ]
    return SmartParticipationResolveRequest(
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        burst_id="projection-burst-1",
        message_id=messages[-1].message_id,
        author_id=messages[-1].author_id,
        reply_to_message_id=messages[-1].reply_to_message_id,
        message=messages[-1].text,
        burst_messages=messages,
        candidates=[SmartParticipationResolveCandidate(deployment_id="deployment-1")],
    )


def _edge(
    repository: EntityEvidenceRepository,
    *,
    guild_id: str = "guild-1",
) -> EvidenceEdgeV3View:
    return repository.add_edge(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id=guild_id,
        source_ref_type="message",
        source_ref="message-1",
        relation_type="REFERS_TO",
        target_ref_type="entity",
        target_ref="entity-1",
        confidence=0.8,
        authority_class="conversation_interpretation",
        source_kind="utility",
        evidence_refs=("message:message-1", "segment:segment-1"),
        producer="projection-test",
    )


def test_evidence_projection_is_idempotent_and_scope_safe() -> None:
    database = _database()
    repository = EntityEvidenceRepository(database)

    first = _edge(repository)
    replay = repository.add_edge(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        source_ref_type="message",
        source_ref="message-1",
        relation_type="REFERS_TO",
        target_ref_type="entity",
        target_ref="entity-1",
        confidence=0.95,
        authority_class="conversation_interpretation",
        source_kind="utility",
        evidence_refs=("segment:segment-1", "message:message-1"),
        producer="projection-test",
    )
    other_guild = _edge(repository, guild_id="guild-2")

    assert replay.id == first.id
    assert other_guild.id != first.id
    with database.session() as session:
        records = list(session.scalars(select(EvidenceEdgeV3Record)))
    assert len(records) == 2
    with database.session() as session:
        stored = session.get(EvidenceEdgeV3Record, first.id)
        assert stored is not None
        session.delete(stored)
        session.commit()
    recreated = _edge(repository)
    assert recreated.id == first.id


def test_closed_episode_replay_returns_existing_episode() -> None:
    database = _database()
    runtime = ConversationRuntimeRepository(database)
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    def append() -> ConversationEpisodeV3View:
        return runtime.append_episode_segment(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            channel_id="channel-1",
            discord_thread_id="",
            conversation_thread_id="thread-1",
            segment_id="segment-1",
            source_message_ids=("message-1",),
            participant_ids=("user-1",),
            max_segments=1,
            now=now,
        )

    closed = append()
    replay = append()

    assert closed.status == "closed"
    assert replay.id == closed.id
    assert replay.status == "closed"
    with database.session() as session:
        records = list(session.scalars(select(ConversationEpisodeV3Record)))
    assert len(records) == 1


def test_episode_and_working_state_keep_each_media_reference_by_source_message() -> None:
    database = _database()
    structure = ConversationStructureRepository(database)
    resolver = ConversationStructureResolver(
        structure,
        Settings(semantic_embedding_enabled=False),
        None,
    )
    payload = _projection_payload().model_copy(
        update={
            "media_descriptors": [
                SmartParticipationMediaDescriptor(
                    ref="message:projection-message-1:attachment:1",
                    kind="image",
                    state="preview_only",
                    source_key="discord-attachment:first",
                ),
                SmartParticipationMediaDescriptor(
                    ref="message:projection-message-1:attachment:2",
                    kind="image",
                    state="preview_only",
                    source_key="discord-attachment:second",
                ),
                SmartParticipationMediaDescriptor(
                    ref="message:projection-message-2:attachment:1",
                    kind="video",
                    state="preview_only",
                    source_key="discord-attachment:third",
                ),
            ]
        }
    )
    result = resolver.resolve(payload=payload, owner_id="owner-1")
    coordinator = ConversationRuntimeCoordinator(
        structure,
        ConversationRuntimeRepository(database),
    )

    observation = coordinator.observe(owner_id="owner-1", payload=payload, result=result)

    expected = {
        "message:projection-message-1:media:discord-attachment:first",
        "message:projection-message-1:media:discord-attachment:second",
        "message:projection-message-2:media:discord-attachment:third",
    }
    assert set(observation.episodes[0].media_refs) == expected
    assert set(observation.working_states[0].referenced_media) == expected


def test_rejecting_evidence_invalidates_dependent_belief() -> None:
    database = _database()
    evidence = EntityEvidenceRepository(database)
    beliefs = BeliefRepository(database)
    edge = _edge(evidence)
    belief = beliefs.create(
        owner_id="owner-1",
        character_card_id="card-1",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_entity_id="entity-1",
        subject_ref="entity:entity-1",
        predicate="identity",
        value_text="The person in the image is Ann.",
        scope="server",
        authority_class="conversation",
        authority_score=0.6,
        origin="visual_grounding",
        confidence=0.8,
        importance=0.7,
        status="active",
        evidence_refs=(edge.id,),
        dependency_edge_ids=(edge.id,),
    )

    rejected = evidence.reject_edge(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        edge_id=edge.id,
    )

    assert rejected.status == "rejected"
    with database.session() as session:
        stored = session.get(BeliefV3Record, belief.id)
    assert stored is not None
    assert stored.status == "rejected"


def test_evidence_rejection_cannot_cross_guild_scope() -> None:
    database = _database()
    evidence = EntityEvidenceRepository(database)
    edge = _edge(evidence)

    with pytest.raises(KeyError, match="Evidence edge not found"):
        evidence.reject_edge(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-2",
            edge_id=edge.id,
        )

    with database.session() as session:
        stored = session.get(EvidenceEdgeV3Record, edge.id)
    assert stored is not None
    assert stored.status == "active"


def test_entity_without_explicit_evidence_remains_unresolved() -> None:
    database = _database()
    repository = EntityEvidenceRepository(database)
    service = EntityGroundingService(repository)

    result = service.resolve_or_provision(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        name="Ann",
        entity_type="person",
        evidence_refs=(),
        missing_fields=("identity",),
    )

    assert result.state == "unresolved"
    assert result.entity is None
    assert result.knowledge_gap is None
    assert repository.recent_entities(
        owner_id="owner-1", connection_id="connection-1", guild_id="guild-1"
    ) == ()


def test_projection_coordinator_replay_preserves_edge_ids_and_isolates_one_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database()
    structure = ConversationStructureRepository(database)
    resolver = ConversationStructureResolver(
        structure,
        Settings(semantic_embedding_enabled=False),
        None,
    )
    payload = _projection_payload()
    result = resolver.resolve(payload=payload, owner_id="owner-1")
    graph = EvidenceGraphService(EntityEvidenceRepository(database))
    coordinator = ProjectionConversationRuntimeCoordinator(
        structure,
        ConversationRuntimeRepository(database),
        graph=graph,
    )

    def fail_relation(**_: object) -> None:
        raise RuntimeError("one derived edge failed")

    monkeypatch.setattr(graph, "project_message_relation", fail_relation)
    coordinator.observe(owner_id="owner-1", payload=payload, result=result)
    with database.session() as session:
        after_failure = list(session.scalars(select(EvidenceEdgeV3Record)))
    assert after_failure
    assert all(item.relation_type != "REPLY_TO" for item in after_failure)

    monkeypatch.undo()
    coordinator.observe(owner_id="owner-1", payload=payload, result=result)
    with database.session() as session:
        first_ids = tuple(sorted(item.id for item in session.scalars(select(EvidenceEdgeV3Record))))
    coordinator.observe(owner_id="owner-1", payload=payload, result=result)
    with database.session() as session:
        replay_ids = tuple(
            sorted(item.id for item in session.scalars(select(EvidenceEdgeV3Record)))
        )
    assert replay_ids == first_ids
