import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.character_turn_context_v3 import (
    CharacterTurnContextV3Service,
)
from echo_masque.connector_runtime import DiscordConnectorRuntime, ResolvedCharacterTurn
from echo_masque.context_resolver_v3 import ContextResolverV3
from echo_masque.conversation_runtime import ConversationRuntimeCoordinator
from echo_masque.conversation_structure_resolver import ConversationStructureResolver
from echo_masque.credentials import CredentialStore
from echo_masque.current_turn_belief_v3 import (
    CurrentTurnBeliefRevisionService,
    CurrentTurnClaimExtraction,
)
from echo_masque.deployment_discovery_service import (
    DeploymentDiscoveryPreviewService,
    DeploymentDiscoveryUnavailable,
)
from echo_masque.domain import TargetResponse
from echo_masque.entity_grounding_v3 import EntityGroundingService
from echo_masque.knowledge_gap_discovery_v3 import KnowledgeGapDiscoveryService
from echo_masque.orchestration import CharacterTurnGraphRunner
from echo_masque.persistence import Database, DeploymentRepository, KnowledgeRepository, Repository
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationSegmentView,
    ConversationStructureRepository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    KnowledgeGapView,
)
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.persistence.server_knowledge_v3_repository import ServerWikiV3Repository
from echo_masque.persistence.smart_participation_state_models import (
    SmartParticipationReplyDecisionRecord,
)
from echo_masque.smart_output import SmartOutputContext
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service
from echo_masque.targets import stable_target


class _NoResolve:
    def resolve(self, **_: object) -> object:
        raise AssertionError("persisted Segment must be reused")


class _NoObserve:
    def observe(self, **_: object) -> object:
        raise AssertionError("persisted Smart Participation turn must not be observed twice")


class _ResolveOnce:
    def __init__(self, segment: ConversationSegmentView) -> None:
        self.segment = segment
        self.calls = 0

    def resolve(self, **_: object) -> object:
        self.calls += 1
        return SimpleNamespace(segments=(self.segment,))


class _ObserveOnce:
    def __init__(self) -> None:
        self.calls = 0

    def observe(self, **_: object) -> object:
        self.calls += 1
        return None


class _CountingCorrections:
    def __init__(self) -> None:
        self.extract_calls = 0
        self.apply_calls = 0

    def extract_self_claim(self, **_: object) -> CurrentTurnClaimExtraction:
        self.extract_calls += 1
        return CurrentTurnClaimExtraction(
            decision=None,
            utility_used=False,
            reason="no claim",
        )

    def apply_to_character(self, **_: object) -> None:
        self.apply_calls += 1
        return None


class _PromptCaptureTarget:
    def __init__(self) -> None:
        self.prompt = ""

    async def send(self, prompt: str) -> TargetResponse:
        self.prompt = prompt
        return TargetResponse(text="captured", latency_ms=0, trace={})


def _service(
    database: Database,
    *,
    structure_resolver: object | None = None,
    runtime_coordinator: object | None = None,
    corrections: object | None = None,
    entity_grounding: EntityGroundingService | None = None,
    knowledge_gap_discovery: KnowledgeGapDiscoveryService | None = None,
) -> CharacterTurnContextV3Service:
    structure = ConversationStructureRepository(database)
    runtime = ConversationRuntimeRepository(database)
    return CharacterTurnContextV3Service(
        structure=structure,
        structure_resolver=cast(ConversationStructureResolver, structure_resolver or _NoResolve()),
        runtime_coordinator=cast(
            ConversationRuntimeCoordinator,
            runtime_coordinator or _NoObserve(),
        ),
        context_resolver=ContextResolverV3(
            structure=structure,
            runtime=runtime,
            entities=EntityEvidenceRepository(database),
            beliefs=BeliefRepository(database),
            social=SocialIntelligenceV3Service(database),
        ),
        knowledge=KnowledgeRepository(database, semantic_enabled=False),
        wiki=ServerWikiV3Repository(database),
        corrections=cast(
            CurrentTurnBeliefRevisionService,
            corrections or CurrentTurnBeliefRevisionService(repository=BeliefRepository(database)),
        ),
        entity_grounding=entity_grounding,
        knowledge_gap_discovery=knowledge_gap_discovery,
    )


def _resolved() -> ResolvedCharacterTurn:
    payload = DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-1",
        guild_id="guild-1",
        channel_id="channel-1",
        author_id="user-1",
        author_display_name="Juen",
        text="What did we decide?",
        mentioned_bot=True,
    )
    deployment = CharacterDeploymentRecord(
        id="deployment-1",
        owner_id="owner-1",
        character_card_id="card-1",
        connection_id="connection-1",
        platform="discord",
        workspace_id="guild-1",
        workspace_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        thread_id="",
        thread_name="",
        participation_mode="mention_and_reply",
        memory_scope="channel_isolated",
        version_label="Current",
        sticker_count=0,
        status="active",
    )
    card = CharacterCardRecord(
        id="card-1",
        owner_id="owner-1",
        target_id="target-1",
        display_name="Ann",
        subtitle="",
        persona_summary="",
    )
    target = TargetRecord(
        id="target-1",
        name="Stable",
        target_kind="stable",
        config_json="{}",
    )
    return ResolvedCharacterTurn(payload, deployment, card, target, stable_target())


def test_persisted_v3_segment_is_reused_without_observing_again(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'context.db'}")
    database.initialize()
    structure = ConversationStructureRepository(database)
    now = datetime.now(UTC)
    segment = structure.record_segments(
        owner_id="owner-1",
        burst_id="burst-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        segments=(
            {
                "segment_key": "message-1",
                "message_ids": ("message-1",),
                "participant_ids": ("user-1",),
                "summary": "Release decision",
                "confidence": 1.0,
            },
        ),
        now=now,
    )[0]
    structure.assign_membership(
        owner_id="owner-1",
        segment_id=segment.id,
        thread_id="",
        relation="unresolved",
        confidence=1.0,
        source="test",
        reason="fixture",
        now=now,
    )
    with database.session() as session:
        session.add(
            SmartParticipationReplyDecisionRecord(
                id="decision-1",
                owner_id="owner-1",
                connection_id="connection-1",
                guild_id="guild-1",
                channel_id="channel-1",
                thread_id="",
                source_message_id="message-1",
                deployment_id="deployment-1",
                character_card_id="card-1",
                segment_id=segment.id,
                semantic_thread_id="stale-thread-must-not-be-trusted",
                authoritative=True,
                resolver_version="conversation-intelligence-v3",
            )
        )
        session.commit()

    runtime = ConversationRuntimeRepository(database)
    service = CharacterTurnContextV3Service(
        structure=structure,
        structure_resolver=cast(ConversationStructureResolver, _NoResolve()),
        runtime_coordinator=cast(ConversationRuntimeCoordinator, _NoObserve()),
        context_resolver=ContextResolverV3(
            structure=structure,
            runtime=runtime,
            entities=EntityEvidenceRepository(database),
            beliefs=BeliefRepository(database),
            social=SocialIntelligenceV3Service(database),
        ),
        knowledge=KnowledgeRepository(database, semantic_enabled=False),
        wiki=ServerWikiV3Repository(database),
        corrections=CurrentTurnBeliefRevisionService(repository=BeliefRepository(database)),
    )

    result = service.build(_resolved())

    assert result.error_reason == ""
    assert result.bundle.segment is not None
    assert result.bundle.segment.id == segment.id
    assert result.bundle.thread is None
    assert any("LIVE CONTEXT" in item for item in result.bundle.prompt_sections())
    assert any("SERVER TIME" in item for item in result.bundle.prompt_sections())


def test_explicit_turn_without_resolve_decision_resolves_and_observes_once(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'explicit.db'}")
    database.initialize()
    segment = ConversationSegmentView(
        id="segment-1",
        burst_id="burst-1",
        message_ids=("message-1",),
        participant_ids=("user-1",),
        kind="discussion",
        summary="What did we decide?",
        thread_id="",
        membership_relation="unresolved",
        membership_confidence=1.0,
        confidence=1.0,
        source="test",
        created_at=datetime.now(UTC),
    )
    structure_resolver = _ResolveOnce(segment)
    runtime_coordinator = _ObserveOnce()
    service = _service(
        database,
        structure_resolver=structure_resolver,
        runtime_coordinator=runtime_coordinator,
    )

    resolved_segment, thread_id = service._resolve_segment(_resolved())

    assert resolved_segment.id == "segment-1"
    assert thread_id == ""
    assert structure_resolver.calls == 1
    assert runtime_coordinator.calls == 1


def test_resolve_correction_cache_prevents_normal_turn_reapplication(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'correction-cache.db'}")
    database.initialize()
    corrections = _CountingCorrections()
    service = _service(database, corrections=corrections)
    resolved = _resolved()
    resolve_payload = service._structure_payload(resolved)

    service.corrections_for_participation(
        payload=resolve_payload,
        owner_id="owner-1",
        deployment_characters=(("deployment-1", "card-1"),),
    )
    service.correction_for_turn(resolved)

    assert corrections.extract_calls == 1
    assert corrections.apply_calls == 1


def test_v3_bundle_sections_reach_the_provider_prompt(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'provider-prompt.db'}")
    database.initialize()
    target = _PromptCaptureTarget()
    resolved = _resolved()
    resolved.payload = resolved.payload.model_copy(
        update={
            "recent_messages": [
                DiscordContextMessage(
                    message_id="segment-message",
                    author_id="user-2",
                    author_display_name="Segment member",
                    text="Selected discussion.",
                ),
                DiscordContextMessage(
                    message_id="other-message",
                    author_id="user-3",
                    author_display_name="Other member",
                    text="Unrelated simultaneous discussion.",
                ),
                DiscordContextMessage(
                    message_id="message-1",
                    author_id="user-1",
                    author_display_name="Juen",
                    text="What did we decide?",
                ),
            ]
        }
    )
    resolved.target = target  # type: ignore[assignment]
    turn_context = SimpleNamespace(
        smart_output=SmartOutputContext.from_payload(
            resolved.payload,
            character_name=resolved.card.display_name,
        ),
        trace=None,
    )
    bundle = SimpleNamespace(
        prompt_sections=lambda: ("V3 BUNDLE SENTINEL",),
        segment=SimpleNamespace(message_ids=("segment-message", "message-1")),
    )
    context_service = SimpleNamespace(
        build=lambda _: SimpleNamespace(
            bundle=bundle,
            turn_context=turn_context,
            error_reason="",
        )
    )
    runtime = DiscordConnectorRuntime(
        Repository(database),
        DeploymentRepository(database),
        CredentialStore(),
        context_service_v3=cast(CharacterTurnContextV3Service, context_service),
    )

    prepared = runtime.prepare_character_turn(resolved)
    asyncio.run(runtime.invoke_character_model(prepared))

    assert "V3 BUNDLE SENTINEL" in prepared.prompt
    assert "V3 BUNDLE SENTINEL" in target.prompt
    assert "Selected discussion." in prepared.prompt
    assert "What did we decide?" in prepared.prompt
    assert "Unrelated simultaneous discussion." not in prepared.prompt
    assert prepared.prompt_manifest["focused_segment_applied"] is True


def test_context_failure_routes_graph_silently_without_provider_call(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'graph-context-failure.db'}")
    database.initialize()
    resolved = _resolved()
    provider_called = False

    class _Runtime:
        def resolve_character_turn(self, _: DiscordInboundMessage) -> tuple[object, None]:
            return resolved, None

        def prepare_character_turn(self, _: object) -> object:
            return SimpleNamespace(
                resolved=resolved,
                context_error="context_unavailable",
                context_bundle=None,
                turn_context=None,
            )

        async def invoke_character_model(self, _: object) -> TargetResponse:
            nonlocal provider_called
            provider_called = True
            raise AssertionError("provider must not be called after context failure")

    result = asyncio.run(
        CharacterTurnGraphRunner(cast(DiscordConnectorRuntime, _Runtime())).run(resolved.payload)
    )

    assert result.reply.action == "silent"
    assert result.reply.reason == "context_unavailable"
    assert result.state["outcome"] == "silent"
    assert result.state["context_status"] == "failed"
    assert provider_called is False


def _entity_segment() -> ConversationSegmentView:
    return ConversationSegmentView(
        id="segment-entity",
        burst_id="burst-entity",
        message_ids=("message-1",),
        participant_ids=("user-1",),
        kind="discussion",
        summary="Entity question",
        thread_id="",
        membership_relation="unresolved",
        membership_confidence=1.0,
        confidence=1.0,
        source="test",
        created_at=datetime.now(UTC),
    )


def test_entity_runtime_does_not_promote_arbitrary_message_tokens(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'no-arbitrary-entity.db'}")
    database.initialize()
    entities = EntityEvidenceRepository(database)
    service = _service(database, entity_grounding=EntityGroundingService(entities))
    resolved = _resolved()
    resolved.payload = resolved.payload.model_copy(update={"text": "Who is CompletelyUnknownName?"})

    service._ground_existing_entity_references(
        resolved=resolved,
        segment=_entity_segment(),
    )

    assert (
        entities.recent_entities(
            owner_id="owner-1", connection_id="connection-1", guild_id="guild-1"
        )
        == ()
    )


def test_entity_runtime_reuses_only_same_scope_provisional_entity_and_gap_is_idempotent(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'entity-runtime-scope.db'}")
    database.initialize()
    entities = EntityEvidenceRepository(database)
    local = entities.ensure_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        name="Pilot",
        entity_type="person",
        source_refs=("message:earlier",),
    )
    entities.ensure_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-2",
        name="Pilot",
        entity_type="person",
        source_refs=("message:other-server",),
    )
    service = _service(database, entity_grounding=EntityGroundingService(entities))
    resolved = _resolved()
    resolved.payload = resolved.payload.model_copy(update={"text": "Who is Pilot?"})

    service._ground_existing_entity_references(resolved=resolved, segment=_entity_segment())
    service._ground_existing_entity_references(resolved=resolved, segment=_entity_segment())

    local_gaps = entities.unresolved_gaps(
        owner_id="owner-1", connection_id="connection-1", guild_id="guild-1"
    )
    assert len(local_gaps) == 1
    assert local_gaps[0].entity_id == local.id
    assert local_gaps[0].missing_fields == ("identity",)
    assert local_gaps[0].importance == 0.75
    assert (
        entities.unresolved_gaps(
            owner_id="owner-1", connection_id="connection-1", guild_id="guild-2"
        )
        == ()
    )


class _CandidatesReadyDiscovery:
    async def run_knowledge_gap(self, **_: object) -> object:
        return SimpleNamespace(ranked=())


class _UnavailableDiscovery:
    async def run_knowledge_gap(self, **_: object) -> object:
        raise DeploymentDiscoveryUnavailable("no configured source")


def _gap_service(
    database: Database,
    discovery: object,
) -> tuple[EntityEvidenceRepository, KnowledgeGapDiscoveryService, KnowledgeGapView]:
    entities = EntityEvidenceRepository(database)
    entity = entities.ensure_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        name="Pilot",
        entity_type="person",
        source_refs=("message:seed",),
    )
    gap = entities.create_gap(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_id=entity.id,
        missing_fields=("identity",),
        triggered_by_ref="message:seed",
        importance=0.75,
    )
    return (
        entities,
        KnowledgeGapDiscoveryService(
            entities=entities,
            discovery=cast(DeploymentDiscoveryPreviewService, discovery),
        ),
        gap,
    )


def test_knowledge_gap_candidates_remain_unresolved_until_evidence_acceptance(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'gap-candidates.db'}")
    database.initialize()
    entities, service, gap = _gap_service(database, _CandidatesReadyDiscovery())

    result = asyncio.run(
        service.search(
            owner_id="owner-1",
            deployment_id="deployment-1",
            connection_id="connection-1",
            guild_id="guild-1",
            gap=gap,
        )
    )

    assert result.status == "candidates_ready"
    assert result.gap.resolution_state == "searching"
    assert (
        entities.gap_for_scope(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            gap_id=gap.id,
        ).resolution_state
        == "searching"
    )


def test_unavailable_knowledge_gap_discovery_reopens_unresolved(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'gap-unavailable.db'}")
    database.initialize()
    _entities, service, gap = _gap_service(database, _UnavailableDiscovery())

    result = asyncio.run(
        service.search(
            owner_id="owner-1",
            deployment_id="deployment-1",
            connection_id="connection-1",
            guild_id="guild-1",
            gap=gap,
        )
    )

    assert result.status == "unavailable"
    assert result.gap.resolution_state == "unresolved"
    assert result.gap.discovery_requested is True
