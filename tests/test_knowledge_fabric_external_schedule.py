from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from echo_masque.knowledge_fabric_external_policy import WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_external_schedule_repository import (
    KnowledgeFabricExternalScheduleRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord
from echo_masque.persistence.schema_migrations import KNOWLEDGE_FABRIC_EXTERNAL_SCHEDULE_REVISION


def _repository(tmp_path: Path) -> tuple[KnowledgeFabricRepository, KnowledgeFabricExternalScheduleRepository]:
    database = Database(f"sqlite:///{tmp_path / 'external-schedule.db'}")
    database.initialize()
    fabric = KnowledgeFabricRepository(database)
    corpus = fabric.create_system_global_corpus(
        name="External sources",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    for locator in ("https://example.test/one", "https://example.test/two"):
        fabric.create_source(
            corpus_id=corpus.id,
            source_type=WEBSITE_PUBLIC_HTTPS_SOURCE_TYPE,
            locator=locator,
            access_profile_json="{}",
            parser_profile_json="{}",
            sync_policy_json="{}",
            freshness_policy_json="{}",
            authority_profile="standard",
        )
    return fabric, KnowledgeFabricExternalScheduleRepository(database)


def test_external_schedule_is_default_disabled_and_requires_a_canonical_supported_source(
    tmp_path: Path,
) -> None:
    fabric, schedules = _repository(tmp_path)
    source = fabric.list_sources(fabric.list_system_global_corpora()[0].id)[0]
    now = datetime(2026, 8, 26, tzinfo=UTC)

    configured = schedules.configure(
        source_id=source.id,
        enabled=False,
        interval_seconds=900,
        now=now,
    )

    assert configured.enabled is False
    assert configured.next_run_at is None
    assert schedules.claim_due(now=now) == []
    with pytest.raises(ValueError, match="approved range"):
        schedules.configure(source_id=source.id, enabled=True, interval_seconds=899, now=now)


def test_external_schedule_leases_once_per_host_and_retries_without_raw_errors(
    tmp_path: Path,
) -> None:
    fabric, schedules = _repository(tmp_path)
    sources = fabric.list_sources(fabric.list_system_global_corpora()[0].id)
    now = datetime(2026, 8, 26, tzinfo=UTC)
    for source in sources:
        schedules.configure(source_id=source.id, enabled=True, interval_seconds=900, now=now)

    first_claims = schedules.claim_due(now=now)

    assert len(first_claims) == 1
    first = first_claims[0]
    assert first.hostname == "example.test"
    assert schedules.mark_result(
        claim=first,
        succeeded=False,
        error_code="fetch_failed",
        now=now,
    )
    failed = schedules.get(first.source_id)
    assert failed is not None
    assert failed.last_error_code == "fetch_failed"
    assert failed.next_run_at == now.replace(tzinfo=None) + timedelta(minutes=15)
    assert not schedules.mark_result(
        claim=first,
        succeeded=True,
        now=now + timedelta(minutes=1),
    )

    second_claims = schedules.claim_due(now=now + timedelta(minutes=1))

    assert len(second_claims) == 1
    assert second_claims[0].source_id != first.source_id
    assert schedules.mark_result(
        claim=second_claims[0],
        succeeded=True,
        now=now + timedelta(minutes=1),
    )
    succeeded = schedules.get(second_claims[0].source_id)
    assert succeeded is not None
    assert succeeded.attempt_count == 0
    assert succeeded.next_run_at == now.replace(tzinfo=None) + timedelta(minutes=16)
    with pytest.raises(ValueError, match="error code"):
        schedules.mark_result(
            claim=second_claims[0],
            succeeded=False,
            error_code="provider detail: secret",
            now=now,
        )


def test_external_schedule_recovers_expired_lease_and_records_schema_revision(tmp_path: Path) -> None:
    fabric, schedules = _repository(tmp_path)
    source = fabric.list_sources(fabric.list_system_global_corpora()[0].id)[0]
    now = datetime(2026, 8, 26, tzinfo=UTC)
    schedules.configure(source_id=source.id, enabled=True, interval_seconds=900, now=now)
    claim = schedules.claim_due(now=now, lease_seconds=30)[0]

    assert schedules.recover_expired(now=now + timedelta(seconds=31)) == 1
    recovered = schedules.get(source.id)
    assert recovered is not None and recovered.lease_token == ""
    assert schedules.claim_due(now=now + timedelta(seconds=31)) == []
    with schedules.database.session() as session:
        assert session.get(
            DatabaseSchemaMigrationRecord,
            KNOWLEDGE_FABRIC_EXTERNAL_SCHEDULE_REVISION,
        )
    assert claim.source_id == source.id
