from datetime import UTC, datetime, timedelta
from pathlib import Path

from echo_masque.knowledge_fabric_website_sync import WebsiteSyncResult
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_external_sync_run_repository import (
    KnowledgeFabricExternalSyncRunRepository,
)
from echo_masque.persistence.knowledge_fabric_models import KnowledgeExternalSourceSyncRunRecord
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord
from echo_masque.persistence.schema_migrations import KNOWLEDGE_FABRIC_EXTERNAL_SYNC_RUN_REVISION


def test_sync_run_reports_are_redacted_source_scoped_and_expire(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'sync-runs.db'}")
    database.initialize()
    fabric = KnowledgeFabricRepository(database)
    corpus = fabric.create_system_global_corpus(
        name="Reports", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="website_collection_public_https",
        locator="https://example.test/wiki",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="official",
    )
    reports = KnowledgeFabricExternalSyncRunRepository(database, retention_days=1)
    started = datetime(2026, 8, 28, tzinfo=UTC)
    stored = reports.record_completed(
        source_id=source.id,
        started_at=started,
        completed_at=started + timedelta(seconds=12),
        result=WebsiteSyncResult(
            outcome="changed",
            discovered_page_count=4,
            changed_page_count=2,
            unchanged_page_count=1,
            failed_page_count=0,
            removed_page_count=1,
            admitted_image_count=3,
        ),
    )

    assert stored.source_id == source.id
    assert stored.discovered_page_count == 4
    assert reports.list_for_source_ids((source.id,))[source.id] == [stored]
    with database.session() as session:
        record = session.get(KnowledgeExternalSourceSyncRunRecord, stored.id)
        assert record is not None
        assert record.expires_at == datetime(2026, 8, 29, 0, 0, 12)
        assert session.get(
            DatabaseSchemaMigrationRecord, KNOWLEDGE_FABRIC_EXTERNAL_SYNC_RUN_REVISION
        ) is not None

    assert reports.purge_expired(now=started + timedelta(days=1, seconds=13)) == 1
    assert reports.list_for_source_ids((source.id,))[source.id] == []
