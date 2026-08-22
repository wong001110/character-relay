from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from echo_masque.api import create_app
from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveRequest,
)
from echo_masque.config import Settings
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.entity_grounding_v3 import EntityGroundingService
from echo_masque.evidence_graph_v3 import EvidenceGraphService
from echo_masque.intelligence_v3_projection import ProjectionConversationRuntimeCoordinator
from echo_masque.knowledge_consolidation_v3 import KnowledgeConsolidationV3Service
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
from echo_masque.persistence.deployment_models import DiscordServerProfileRecord
from echo_masque.persistence.entity_evidence_models import EvidenceEdgeV3Record
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    EvidenceEdgeV3View,
)
from echo_masque.persistence.server_knowledge_v3_repository import (
    KnowledgeConsolidationCheckpointV3Repository,
    ServerWikiV3Repository,
)
from echo_masque.utility_gateway_contracts import UtilityGatewayUnavailable


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


class _UnavailableConsolidationGateway:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        self.calls += 1
        raise UtilityGatewayUnavailable("unavailable")


def test_consolidation_checkpoint_reuses_completed_source_and_enforces_scope() -> None:
    database = _database()
    entities = EntityEvidenceRepository(database)
    entity = entities.ensure_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        name="Ann",
        entity_type="person",
        source_refs=("message:message-1",),
    )
    BeliefRepository(database).create(
        owner_id="owner-1",
        character_card_id="card-1",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_entity_id=entity.id,
        subject_ref=f"entity:{entity.id}",
        predicate="role",
        value_text="Moderator",
        scope="server",
        authority_class="conversation",
        authority_score=0.7,
        origin="explicit_user_statement",
        confidence=0.9,
        importance=0.6,
        status="active",
        evidence_refs=("message:message-1",),
    )
    gateway = _UnavailableConsolidationGateway()
    service = KnowledgeConsolidationV3Service(
        wiki=ServerWikiV3Repository(database),
        checkpoints=KnowledgeConsolidationCheckpointV3Repository(database),
        gateway=gateway,  # type: ignore[arg-type]
    )

    first = service.consolidate_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_id=entity.id,
    )
    replay = service.consolidate_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_id=entity.id,
    )

    assert first.utility_status == "utility_unavailable"
    assert replay.wiki_page_id == first.wiki_page_id
    assert gateway.calls == 1
    with pytest.raises(KeyError, match="Entity not found"):
        service.consolidate_entity(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-2",
            entity_id=entity.id,
        )

    entities.ensure_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        name="Ann",
        entity_type="person",
        metadata={"role": "moderator"},
    )
    changed = service.consolidate_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_id=entity.id,
    )
    assert changed.wiki_page_id == first.wiki_page_id
    assert gateway.calls == 2


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


def test_owner_server_profile_consolidation_endpoint_enforces_owner_and_server_scope(
    tmp_path: Path,
) -> None:
    app = create_app(_api_settings(tmp_path / "phase4-consolidation-api.db"))
    client = TestClient(app)
    login = client.post(
        "/api/auth/login",
        json={
            "email": "phase4-admin@example.com",
            "password": "Phase4Admin2026!",
        },
    )
    assert login.status_code == 200, login.text
    owner_id = str(client.get("/api/auth/me").json()["id"])
    database = app.state.database
    profile_id = str(uuid4())
    other_owner_profile_id = str(uuid4())
    with database.session() as session:
        session.add(
            DiscordServerProfileRecord(
                id=profile_id,
                owner_id=owner_id,
                connection_id="connection-1",
                name="Phase 4 Server",
                guild_id="guild-1",
                guild_name="Phase 4 Guild",
            )
        )
        session.add(
            DiscordServerProfileRecord(
                id=other_owner_profile_id,
                owner_id="other-owner",
                connection_id="connection-1",
                name="Other Server",
                guild_id="guild-1",
                guild_name="Other Guild",
            )
        )
        session.commit()
    entity = EntityEvidenceRepository(database).ensure_entity(
        owner_id=owner_id,
        connection_id="connection-1",
        guild_id="guild-1",
        name="Explicit Entity",
        entity_type="concept",
        source_refs=("message:phase4",),
    )

    response = client.post(
        f"/api/server-profiles/{profile_id}/knowledge-consolidation/entities/{entity.id}"
    )
    assert response.status_code == 200, response.text
    assert response.json()["source_ref"] == entity.id

    wrong_owner = client.post(
        f"/api/server-profiles/{other_owner_profile_id}/knowledge-consolidation/entities/{entity.id}"
    )
    assert wrong_owner.status_code == 404

    other_guild_entity = EntityEvidenceRepository(database).ensure_entity(
        owner_id=owner_id,
        connection_id="connection-1",
        guild_id="guild-2",
        name="Other Guild Entity",
        entity_type="concept",
        source_refs=("message:other-guild",),
    )
    wrong_server = client.post(
        f"/api/server-profiles/{profile_id}/knowledge-consolidation/entities/{other_guild_entity.id}"
    )
    assert wrong_server.status_code == 404
