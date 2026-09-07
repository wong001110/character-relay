from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.context_resolver_v3 import ContextResolverV3
from echo_masque.conversation_runtime import ConversationRuntimeCoordinator
from echo_masque.conversation_runtime_maintenance import ConversationRuntimeMaintenanceService
from echo_masque.persistence import Database
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_models import ThreadWorkingStateRecord
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.entity_evidence_repository import EntityEvidenceRepository
from echo_masque.social_intelligence_v3 import SocialIntelligenceV3Service


def _runtime(database: Database) -> ConversationRuntimeRepository:
    return ConversationRuntimeRepository(database)


def _working_state(
    runtime: ConversationRuntimeRepository,
    *,
    thread_id: str,
    expires_at: datetime,
    owner_id: str = "owner-1",
) -> None:
    runtime.upsert_working_state(
        owner_id=owner_id,
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        thread_id=thread_id,
        current_object_ref="message:current",
        active_entity_ids=("entity-1",),
        open_questions=("Will the recording be uploaded?",),
        waiting_states=("Waiting for the recording.",),
        expires_at=expires_at,
        now=expires_at - timedelta(minutes=5),
    )


def _resolver(database: Database) -> ContextResolverV3:
    return ContextResolverV3(
        structure=ConversationStructureRepository(database),
        runtime=_runtime(database),
        entities=EntityEvidenceRepository(database),
        beliefs=BeliefRepository(database),
        social=SocialIntelligenceV3Service(database),
    )


def _bundle_for_thread(resolver: ContextResolverV3, *, thread_id: str) -> object:
    return resolver.resolve(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        conversation_thread_id=thread_id,
        query="recording upload",
        character_card_id="character-1",
        deployment_id="deployment-1",
        actor_id="actor-1",
    )


def test_expired_and_archived_scratch_are_excluded_from_actual_context() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = _runtime(database)
    current = datetime.now(UTC)
    _working_state(
        runtime,
        thread_id="expired-thread",
        expires_at=current - timedelta(seconds=1),
    )
    _working_state(
        runtime,
        thread_id="archived-thread",
        expires_at=current + timedelta(hours=1),
    )
    runtime.archive_working_state(
        owner_id="owner-1", thread_id="archived-thread", now=current
    )
    resolver = _resolver(database)

    expired = _bundle_for_thread(resolver, thread_id="expired-thread")
    archived = _bundle_for_thread(resolver, thread_id="archived-thread")

    assert expired.working_state is None
    assert archived.working_state is None
    with database.session() as session:
        record = session.get(ThreadWorkingStateRecord, "expired-thread")
    assert record is not None and record.status == "archived"


def test_maintenance_checkpoints_only_due_owner_state_and_is_idempotent() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = _runtime(database)
    structure = ConversationStructureRepository(database)
    coordinator = ConversationRuntimeCoordinator(structure, runtime)
    current = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    runtime.append_episode_segment(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        conversation_thread_id="due-thread",
        segment_id="due-segment",
        source_message_ids=("due-message",),
        participant_ids=("actor-1",),
        summary="A due conversation.",
        now=current - timedelta(hours=1),
    )
    _working_state(
        runtime,
        thread_id="due-thread",
        expires_at=current - timedelta(minutes=1),
    )
    runtime.append_episode_segment(
        owner_id="owner-2",
        connection_id="connection-2",
        guild_id="guild-2",
        channel_id="channel-2",
        discord_thread_id="",
        conversation_thread_id="other-thread",
        segment_id="other-segment",
        source_message_ids=("other-message",),
        participant_ids=("actor-2",),
        summary="A current conversation.",
        now=current,
    )
    _working_state(
        runtime,
        thread_id="other-thread",
        owner_id="owner-2",
        expires_at=current + timedelta(hours=1),
    )
    service = ConversationRuntimeMaintenanceService(
        coordinator, runtime, interval_seconds=60
    )

    first = service.maintain_once(now=current)
    second = service.maintain_once(now=current)

    assert first == {"episodes_checkpointed": 1, "working_states_archived": 1}
    assert second == {"episodes_checkpointed": 0, "working_states_archived": 0}
    assert runtime.working_state(owner_id="owner-1", thread_id="due-thread", now=current) is None
    assert runtime.active_episode(owner_id="owner-1", conversation_thread_id="due-thread") is None
    assert runtime.working_state(owner_id="owner-2", thread_id="other-thread", now=current)
    assert runtime.active_episode(owner_id="owner-2", conversation_thread_id="other-thread")

    async def lifecycle() -> None:
        await service.start()
        await service.start()
        await service.stop()

    asyncio.run(lifecycle())


def test_owner_checkpoint_never_archives_another_owners_scratch() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = _runtime(database)
    coordinator = ConversationRuntimeCoordinator(ConversationStructureRepository(database), runtime)
    current = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    runtime.append_episode_segment(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="channel-1",
        discord_thread_id="",
        conversation_thread_id="owner-one-thread",
        segment_id="owner-one-segment",
        source_message_ids=("owner-one-message",),
        participant_ids=("actor-1",),
        summary="Due owner one episode.",
        now=current - timedelta(hours=1),
    )
    _working_state(
        runtime,
        thread_id="owner-two-thread",
        owner_id="owner-2",
        expires_at=current - timedelta(minutes=1),
    )

    coordinator.checkpoint_inactive(owner_id="owner-1", now=current)

    with database.session() as session:
        other_owner = session.get(ThreadWorkingStateRecord, "owner-two-thread")
    assert other_owner is not None and other_owner.status == "active"


def test_maintenance_cancellation_waits_for_the_active_database_thread() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = _runtime(database)
    service = ConversationRuntimeMaintenanceService(
        ConversationRuntimeCoordinator(ConversationStructureRepository(database), runtime), runtime
    )
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    def blocking_maintenance() -> dict[str, int]:
        started.set()
        assert release.wait(timeout=3)
        completed.set()
        return {"episodes_checkpointed": 0, "working_states_archived": 0}

    service.maintain_once = blocking_maintenance  # type: ignore[method-assign]

    async def scenario() -> None:
        running = asyncio.create_task(service._run_once())
        await asyncio.to_thread(started.wait)
        running.cancel()
        await asyncio.sleep(0)
        assert not running.done()
        release.set()
        try:
            await running
        except asyncio.CancelledError:
            pass
        else:  # pragma: no cover - documents the cancellation contract.
            raise AssertionError("maintenance awaiter should preserve cancellation")

    asyncio.run(scenario())
    assert completed.is_set()


def test_api_lifespan_starts_and_stops_conversation_runtime_maintenance(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'runtime-maintenance.db'}",
            legacy_local_user_enabled=False,
            credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        )
    )

    with TestClient(app):
        assert app.state.conversation_runtime_maintenance._task is not None
    assert app.state.conversation_runtime_maintenance._task is None
