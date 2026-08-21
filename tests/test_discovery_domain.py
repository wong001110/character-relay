from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from echo_masque.discovery_contracts import (
    DiscoveryAttentionLevel,
    DiscoveryCandidate,
    DiscoveryDecision,
    DiscoveryMode,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discovery_repository import DiscoveryRepository


def seed_deployment(
    database: Database,
    *,
    deployment_id: str,
    guild_id: str,
) -> None:
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id=deployment_id,
                owner_id="owner-1",
                character_card_id="character-shared",
                connection_id="connection-1",
                platform="discord",
                workspace_id=guild_id,
                workspace_name=guild_id,
                channel_id=f"@server:{guild_id}",
                channel_name="All channels",
                thread_id="",
                thread_name="",
                participation_mode="smart",
                memory_scope="server_shared",
                version_label="Current",
                sticker_count=0,
                status="active",
            )
        )
        session.commit()


def candidate(key: str = "youtube:abc") -> DiscoveryCandidate:
    return DiscoveryCandidate(
        source="youtube",
        canonical_key=key,
        content_kind="video",
        title="I built a desktop AI robot",
        description="A public project demo.",
        creator="Example Creator",
        url="https://www.youtube.com/watch?v=abc",
        metadata={"duration_seconds": 240},
    )


def test_objective_item_is_shared_but_exposure_is_deployment_scoped(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'discovery-scope.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-a", guild_id="guild-a")
    seed_deployment(database, deployment_id="deployment-b", guild_id="guild-b")
    repository = DiscoveryRepository(database)
    now = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)

    first = repository.upsert_item(candidate(), now=now)
    second = repository.upsert_item(candidate(), now=now + timedelta(minutes=1))
    assert first.id == second.id
    assert repository.list_exposures(owner_id="owner-1", deployment_id="deployment-a") == ()
    assert repository.list_exposures(owner_id="owner-1", deployment_id="deployment-b") == ()

    exposure = repository.record_exposure(
        owner_id="owner-1",
        deployment_id="deployment-a",
        discovery_item_id=first.id,
        attention_level=DiscoveryAttentionLevel.WATCH,
        interest_score=0.9,
        subjective_reason="Matches this server's learned AI/robotics interests.",
        now=now + timedelta(minutes=2),
    )
    assert exposure is not None
    assert exposure.attention_level == "watch"
    assert len(repository.list_exposures(owner_id="owner-1", deployment_id="deployment-a")) == 1
    assert repository.list_exposures(owner_id="owner-1", deployment_id="deployment-b") == ()


def test_shadow_mode_can_record_would_share_but_never_executed_share(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'discovery-shadow.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-a", guild_id="guild-a")
    repository = DiscoveryRepository(database)
    item = repository.upsert_item(candidate())
    assert (
        repository.record_exposure(
            owner_id="owner-1",
            deployment_id="deployment-a",
            discovery_item_id=item.id,
            attention_level=DiscoveryAttentionLevel.ENGAGE,
            interest_score=0.95,
        )
        is not None
    )

    shadow = repository.record_decision(
        owner_id="owner-1",
        deployment_id="deployment-a",
        discovery_item_id=item.id,
        mode=DiscoveryMode.SHADOW,
        decision=DiscoveryDecision.WOULD_SHARE,
        motivation="RELATED_TO_PAST_CONVERSATION",
        confidence=0.88,
        scores={"interest": 0.95},
        evidence={"conversation_thread_id": "thread-1"},
    )
    assert shadow is not None
    assert shadow.decision == "would_share"

    with pytest.raises(ValueError, match="Shadow Discovery cannot"):
        repository.record_decision(
            owner_id="owner-1",
            deployment_id="deployment-a",
            discovery_item_id=item.id,
            mode=DiscoveryMode.SHADOW,
            decision=DiscoveryDecision.SHARE,
        )
    with pytest.raises(ValueError, match="Shadow Discovery cannot"):
        repository.record_decision(
            owner_id="owner-1",
            deployment_id="deployment-a",
            discovery_item_id=item.id,
            mode=DiscoveryMode.SHADOW,
            decision=DiscoveryDecision.PROPOSE_SHARE,
        )


def test_decision_requires_lived_exposure_and_cleanup_preserves_exposed_items(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'discovery-cleanup.db'}")
    database.initialize()
    seed_deployment(database, deployment_id="deployment-a", guild_id="guild-a")
    repository = DiscoveryRepository(database)
    past = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)

    unexposed = repository.upsert_item(
        candidate("youtube:unexposed"),
        ttl=timedelta(hours=1),
        now=past,
    )
    exposed = repository.upsert_item(
        candidate("youtube:exposed"),
        ttl=timedelta(hours=1),
        now=past,
    )
    assert (
        repository.record_decision(
            owner_id="owner-1",
            deployment_id="deployment-a",
            discovery_item_id=unexposed.id,
            mode=DiscoveryMode.SHADOW,
            decision=DiscoveryDecision.REMEMBER,
        )
        is None
    )

    assert (
        repository.record_exposure(
            owner_id="owner-1",
            deployment_id="deployment-a",
            discovery_item_id=exposed.id,
            attention_level=DiscoveryAttentionLevel.NOTICE,
            now=past,
        )
        is not None
    )
    assert repository.cleanup_expired_unexposed(now=past + timedelta(days=1)) == 1

    # The unexposed shared candidate is gone; the lived/exposed item's objective shell is retained.
    assert (
        repository.record_exposure(
            owner_id="owner-1",
            deployment_id="deployment-a",
            discovery_item_id=unexposed.id,
            attention_level=DiscoveryAttentionLevel.NOTICE,
        )
        is None
    )
    assert len(repository.list_exposures(owner_id="owner-1", deployment_id="deployment-a")) == 1
