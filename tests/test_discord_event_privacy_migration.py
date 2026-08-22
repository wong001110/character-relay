from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from echo_masque.api.deployment_schemas import DiscordConnectorLogView
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    DiscordConnectorEventRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.discord_event_privacy_migration import (
    DISCORD_EVENT_PRIVACY_MIGRATION_ID,
    DiscordEventPrivacyMigration,
)
from echo_masque.persistence.operational_migration_models import (
    OperationalDataMigrationRecord,
)


def _reset_privacy_ledger(database: Database) -> None:
    with database.session() as session:
        record = session.get(
            OperationalDataMigrationRecord,
            DISCORD_EVENT_PRIVACY_MIGRATION_ID,
        )
        assert record is not None
        session.delete(record)
        session.commit()


def _legacy_event(event_id: str, details_json: str) -> DiscordConnectorEventRecord:
    return DiscordConnectorEventRecord(
        id=event_id,
        owner_id="owner-1",
        connection_id="connection-1",
        level="info",
        event_type="smart_participation_decision",
        message="PRIVATE TOP-LEVEL DISCORD MESSAGE",
        guild_id="guild-1",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        thread_id="",
        thread_name="",
        source_message_id="message-1",
        deployment_id="",
        character_name="",
        details_json=details_json,
        occurred_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def test_privacy_migration_sanitizes_legacy_rows_once(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'discord-privacy.db'}"
    database = Database(url)
    database.initialize()
    _reset_privacy_ledger(database)

    with database.session() as session:
        session.add(
            PlatformConnectionRecord(
                id="connection-1",
                owner_id="owner-1",
                platform="discord",
                display_name="Discord",
                connection_mode="managed",
                external_account_id="bot-1",
                status="error",
                metadata_json=(
                    '{"last_error":"PRIVATE HEARTBEAT ERROR",'
                    '"event_log_last_error":"PRIVATE EVENT ERROR","gateway_ready":true}'
                ),
            )
        )
        session.add(
            _legacy_event(
                "legacy-private",
                '{"trigger_preview":"PRIVATE TRIGGER PREVIEW",'
                '"nested":{"responseBody":"PRIVATE BODY",'
                '"sourceMessageId":"safe-source-id"},'
                '"candidate_count":2,"decision_reason":"mention_gate"}',
            )
        )
        session.add(_legacy_event("legacy-malformed", "{not-json"))
        session.commit()

    restarted = Database(url)
    restarted.initialize()
    with restarted.session() as session:
        private = session.get(DiscordConnectorEventRecord, "legacy-private")
        malformed = session.get(DiscordConnectorEventRecord, "legacy-malformed")
        connection = session.get(PlatformConnectionRecord, "connection-1")
        ledger = session.get(
            OperationalDataMigrationRecord,
            DISCORD_EVENT_PRIVACY_MIGRATION_ID,
        )
        assert private is not None
        assert malformed is not None
        assert connection is not None
        assert ledger is not None
        assert private.message == "Discord connector operational event."
        assert "PRIVATE" not in private.details_json
        assert "safe-source-id" in private.details_json
        assert "candidate_count" in private.details_json
        assert malformed.details_json == "{}"
        assert "PRIVATE" not in connection.metadata_json
        assert ledger.status == "completed"
        assert ledger.attempt_count == 1

    Database(url).initialize()
    with restarted.session() as session:
        ledger = session.get(
            OperationalDataMigrationRecord,
            DISCORD_EVENT_PRIVACY_MIGRATION_ID,
        )
        assert ledger is not None
        assert ledger.attempt_count == 1


def test_log_view_sanitizes_rows_written_after_completed_migration(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'discord-read-guard.db'}")
    database.initialize()
    record = _legacy_event(
        "post-migration-tamper",
        '{"rawContent":"PRIVATE RAW","reason_code":"safe_reason"}',
    )

    view = DiscordConnectorLogView.from_record(record)

    assert view.message == "Discord connector operational event."
    assert view.details == {"reason_code": "safe_reason"}
    assert "PRIVATE" not in view.model_dump_json()


def test_privacy_migration_retries_after_interruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"sqlite:///{tmp_path / 'discord-retry.db'}"
    database = Database(url)
    database.initialize()
    _reset_privacy_ledger(database)
    migration = DiscordEventPrivacyMigration(database)

    def interrupt(_: object) -> int:
        raise RuntimeError("injected interruption")

    monkeypatch.setattr(migration, "_sanitize_records", interrupt)
    with pytest.raises(RuntimeError, match="injected interruption"):
        migration.run()

    with database.session() as session:
        failed = session.scalar(
            select(OperationalDataMigrationRecord).where(
                OperationalDataMigrationRecord.id == DISCORD_EVENT_PRIVACY_MIGRATION_ID
            )
        )
        assert failed is not None
        assert failed.status == "failed"
        assert failed.attempt_count == 1
        assert failed.last_error == "RuntimeError"

    Database(url).initialize()
    with database.session() as session:
        completed = session.get(
            OperationalDataMigrationRecord,
            DISCORD_EVENT_PRIVACY_MIGRATION_ID,
        )
        assert completed is not None
        assert completed.status == "completed"
        assert completed.attempt_count == 2


def test_independent_initializers_claim_privacy_migration_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"sqlite:///{tmp_path / 'discord-concurrent.db'}"
    database = Database(url)
    database.initialize()
    _reset_privacy_ledger(database)
    calls = 0
    calls_lock = Lock()
    original = DiscordEventPrivacyMigration._sanitize_records

    def count_runner(migration: DiscordEventPrivacyMigration, session: Session) -> int:
        nonlocal calls
        with calls_lock:
            calls += 1
        return original(migration, session)

    monkeypatch.setattr(DiscordEventPrivacyMigration, "_sanitize_records", count_runner)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(Database(url).initialize) for _ in range(2)]
        for future in futures:
            future.result()

    with database.session() as session:
        ledger = session.get(
            OperationalDataMigrationRecord,
            DISCORD_EVENT_PRIVACY_MIGRATION_ID,
        )
        assert ledger is not None
        assert ledger.status == "completed"
        assert ledger.attempt_count == 1
    assert calls == 1
