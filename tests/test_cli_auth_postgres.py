"""Device-grant concurrency on the explicitly disposable PostgreSQL CI database."""

from concurrent.futures import ThreadPoolExecutor

import pytest
import test_web_rooms
from sqlalchemy import inspect, select
from test_cli_auth import CLIENT, csrf_headers, device, poll, reset_poll
from test_database_foundation import _destructive_postgres_test_url

from echo_masque.cli_auth import CliAuthError, CliAuthService
from echo_masque.persistence import Database
from echo_masque.persistence.cli_auth_models import CliDeviceRecord, CliGrantRecord
from echo_masque.persistence.models import Base
from echo_masque.persistence.schema_migration_models import DatabaseSchemaMigrationRecord
from echo_masque.persistence.web_room_repository import WebRoomRepository


def test_postgresql_cli_grants_durable_polling_and_atomic_redemption(tmp_path, monkeypatch):
    url = _destructive_postgres_test_url()
    reset = Database(url)
    try:
        Base.metadata.drop_all(reset.engine)
    finally:
        reset.engine.dispose()
    original_settings = test_web_rooms.settings
    monkeypatch.setattr(
        test_web_rooms,
        "settings",
        lambda path: original_settings(path).model_copy(
            update={"database_url": url, "cli_auth_enabled": True}
        ),
    )
    cli = test_web_rooms.web.__wrapped__(tmp_path)
    second_database = Database(url)
    try:
        # Idempotent bootstrap must retain in-flight authorization state.
        challenge = device(cli)
        assert poll(cli, challenge).json() == {"error": "authorization_pending"}
        assert poll(cli, challenge).json() == {"error": "slow_down"}
        second_database.initialize()
        second_database.initialize()
        restarted = CliAuthService(
            second_database, cli[0].state.settings, WebRoomRepository(second_database)
        )
        with pytest.raises(CliAuthError, match=r"^slow_down$"):
            restarted.exchange(CLIENT, challenge["device_code"])
        with second_database.session() as session:
            record = session.scalar(select(CliDeviceRecord))
            assert record.status == "pending"
            assert record.interval == 15
            assert record.poll_version == 3
            revisions = session.scalars(
                select(DatabaseSchemaMigrationRecord).where(
                    DatabaseSchemaMigrationRecord.revision == "cli-readonly-grants-v1"
                )
            ).all()
            assert len(revisions) == 1
        headers = csrf_headers(cli[1])
        assert (
            cli[1]
            .post(
                "/api/cli-auth/authorizations/review",
                headers=headers,
                json={"user_code": challenge["user_code"]},
            )
            .status_code
            == 200
        )
        approved = cli[1].post(
            "/api/cli-auth/authorizations/decision",
            headers=headers,
            json={"user_code": challenge["user_code"], "decision": "approve"},
        )
        assert approved.status_code == 200
        reset_poll(cli, challenge)

        def exchange(service):
            try:
                result = service.exchange(CLIENT, challenge["device_code"])
                return True, result["access_token"]
            except CliAuthError:
                return False, None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(exchange, [cli[0].state.cli_auth_service, restarted]))
        assert sum(success for success, _ in results) == 1
        credential = next(token for success, token in results if success)
        principal = restarted.resolve(credential)
        assert principal.room_ids == (cli[4],)
        with second_database.session() as session:
            assert session.scalar(select(CliDeviceRecord)).status == "redeemed"
            assert len(session.scalars(select(CliGrantRecord)).all()) == 1
        with pytest.raises(CliAuthError, match=r"^invalid_grant$"):
            restarted.exchange(CLIENT, challenge["device_code"])
        restarted.revoke(principal.grant_id, principal.user_id)
        with pytest.raises(CliAuthError, match=r"^invalid_token$"):
            cli[0].state.cli_auth_service.resolve(credential)
        assert {"cli_device_authorizations", "cli_readonly_grants"} <= set(
            inspect(second_database.engine).get_table_names()
        )
    finally:
        second_database.engine.dispose()
        cli[0].state.database.engine.dispose()
