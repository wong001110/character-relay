import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.api.connector_schemas import DiscordConnectorReplyView
from echo_masque.config import Settings
from echo_masque.persistence.database import Database
from echo_masque.persistence.runtime_durability_models import (
    RuntimeOperationRecord,
    RuntimeStepRecord,
)
from echo_masque.persistence.turn_job_models import TurnJobRecord
from echo_masque.persistence.turn_job_repository import TurnJobRepository
from echo_masque.turn_jobs import TurnJobManager
from echo_masque.turn_progress import publish_turn_progress, require_active_turn

SECRET = "turn-job-test-secret"


def test_recovery_filters_delivered_history_before_limit(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'recovery.db'}")
    database.initialize()
    repository = TurnJobRepository(database)
    pending_id = _submit(repository, message_id="pending-final")
    repository.mark_running(pending_id)
    repository.complete(pending_id, field="reply", value='{"step_id":"pending-step"}')
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(
            RuntimeOperationRecord(
                operation_id="operation-1",
                owner_id="owner-1",
                connection_id="connection-1",
                status="awaiting_delivery",
            )
        )
        session.add(
            RuntimeStepRecord(
                step_id="pending-step",
                operation_id="operation-1",
                deployment_id="deployment-1",
                step_index=0,
                status="generated",
            )
        )
        session.add(
            RuntimeStepRecord(
                step_id="delivered-step",
                operation_id="operation-1",
                deployment_id="deployment-1",
                step_index=1,
                status="delivered",
            )
        )
        # More settled jobs than the previous scan cap must not hide an unresolved final.
        for index in range(510):
            session.add(
                TurnJobRecord(
                    job_id=f"settled-{index}",
                    kind="message",
                    owner_id="owner-1",
                    connection_id="connection-1",
                    deployment_id="deployment-1",
                    status="succeeded",
                    runtime_step_id="delivered-step",
                    deadline_at=now + timedelta(seconds=30),
                    expires_at=now + timedelta(hours=1),
                    created_at=now - timedelta(minutes=1),
                )
            )
        session.commit()
    assert [
        job.job_id for job in repository.list_recoverable(connection_id="connection-1", limit=1)
    ] == [pending_id]
    assert repository.list_recoverable(connection_id="other") == []
    with database.session() as session:
        step = session.get(RuntimeStepRecord, "pending-step")
        assert step is not None
        step.status = "delivered"
        session.commit()
    assert repository.list_recoverable(connection_id="connection-1") == []


def test_terminal_notice_is_consumed_before_send_and_retention_erases_progress(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'terminal-retention.db'}")
    database.initialize()
    repository = TurnJobRepository(database)
    job_id = _submit(repository)
    assert not repository.acknowledge_final_notice(job_id, connection_id="connection-1")
    assert repository.publish_progress(job_id, "Preparing the image.")
    repository.fail(job_id, status="timed_out", error_code="deadline_exceeded")
    assert [job.job_id for job in repository.list_recoverable(connection_id="connection-1")] == [
        job_id
    ]
    assert not repository.acknowledge_final_notice(job_id, connection_id="other")
    assert repository.acknowledge_final_notice(job_id, connection_id="connection-1")
    assert not repository.acknowledge_final_notice(job_id, connection_id="connection-1")
    assert repository.list_recoverable(connection_id="connection-1") == []
    with database.session() as session:
        job = session.get(TurnJobRecord, job_id)
        assert job is not None and job.request_json == "{}"
        job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert repository.get(job_id, connection_id="connection-1") is None
    assert repository.list_progress(job_id) == []


def test_completed_job_can_drain_existing_progress_but_cancelled_job_cannot_claim_it(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'progress-terminal-state.db'}")
    database.initialize()
    repository = TurnJobRepository(database)
    succeeded_id = _submit(repository, message_id="progress-success")
    assert repository.publish_progress(succeeded_id, "Almost done.")
    assert repository.mark_running(succeeded_id) is not None
    repository.complete(succeeded_id, field="reply", value='{"action":"silent"}')
    claimed = repository.claim_progress(succeeded_id, nonce="succeeded-progress")
    assert claimed is not None and claimed.text == "Almost done."

    cancelled_id = _submit(repository, message_id="progress-cancelled")
    assert repository.publish_progress(cancelled_id, "Will not send.")
    assert repository.cancel(
        cancelled_id,
        owner_id="owner-1",
        connection_id="connection-1",
        reason="user_cancelled",
    )
    assert repository.claim_progress(cancelled_id, nonce="cancelled-progress") is None


def test_recovery_paginates_past_revoked_jobs_and_excludes_social(tmp_path: Path) -> None:
    app = _app_with_scope(tmp_path / "recovery-scope.db")
    repository = app.state.turn_job_repository
    now = datetime.now(UTC)
    active = SimpleNamespace(id="deployment-1", owner_id="owner-1")
    app.state.deployment_repository.deployment_matches_discord_destination = (
        lambda deployment_id, **_kwargs: active if deployment_id == "deployment-1" else None
    )
    with TestClient(app) as client:
        with repository.database.session() as session:
            for index in range(50):
                session.add(
                    TurnJobRecord(
                        job_id=f"a-revoked-{index:02}",
                        kind="message",
                        owner_id="owner-1",
                        connection_id="connection-1",
                        deployment_id="revoked",
                        status="failed",
                        deadline_at=now + timedelta(seconds=30),
                        expires_at=now + timedelta(hours=1),
                    )
                )
                session.add(
                    TurnJobRecord(
                        job_id=f"a-social-{index:02}",
                        kind="social",
                        owner_id="owner-1",
                        connection_id="connection-1",
                        deployment_id="deployment-1",
                        status="failed",
                        deadline_at=now + timedelta(seconds=30),
                        expires_at=now + timedelta(hours=1),
                    )
                )
            session.add(
                TurnJobRecord(
                    job_id="z-valid",
                    kind="message",
                    owner_id="owner-1",
                    connection_id="connection-1",
                    deployment_id="deployment-1",
                    status="failed",
                    deadline_at=now + timedelta(seconds=30),
                    expires_at=now + timedelta(hours=1),
                )
            )
            session.commit()
        first = client.get(
            "/api/connectors/discord/turn-jobs",
            headers=_connector_headers(),
            params={"connection_id": "connection-1"},
        )
        assert first.status_code == 200
        assert first.json()["items"] == []
        assert first.json()["next_cursor"] == "a-revoked-49"
        second = client.get(
            "/api/connectors/discord/turn-jobs",
            headers=_connector_headers(),
            params={"connection_id": "connection-1", "after_job_id": first.json()["next_cursor"]},
        )
        assert [item["job_id"] for item in second.json()["items"]] == ["z-valid"]
        assert second.json()["next_cursor"] is None


def _settings(path: Path, *, queue: int = 2) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        browser_tools_enabled=False,
        semantic_participation_enabled=False,
        legacy_local_user_enabled=False,
        connector_shared_secret=SecretStr(SECRET),
        turn_job_max_queue=queue,
        turn_job_max_concurrency=1,
    )


def _inbound(message_id: str) -> dict[str, object]:
    return {
        "connection_id": "connection-1",
        "deployment_id": "deployment-1",
        "message_id": message_id,
        "guild_id": "guild-1",
        "channel_id": "channel-1",
        "author_id": "user-1",
        "author_display_name": "User",
        "text": "hello",
        "recent_messages": [],
    }


def _connector_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {SECRET}"}


def _app_with_scope(path: Path, *, queue: int = 2):
    app = create_app(_settings(path, queue=queue))
    active = SimpleNamespace(id="deployment-1", owner_id="owner-1")
    app.state.deployment_repository.get_active_discord_deployment_for_guild = (
        lambda *_args, **_kwargs: active
    )
    app.state.deployment_repository.deployment_matches_discord_destination = (
        lambda *_args, **_kwargs: active
    )
    return app


def test_turn_job_routes_submit_poll_claim_and_ack_scoped_progress(tmp_path: Path) -> None:
    app = _app_with_scope(tmp_path / "routes.db")

    async def delayed_runner(_kind: str, _payload: str) -> str:
        assert await publish_turn_progress("Looking up the image now.")
        await asyncio.sleep(0.08)
        return DiscordConnectorReplyView(
            action="reply", reason="ready", text="done"
        ).model_dump_json()

    app.state.turn_job_manager.runner = delayed_runner
    with TestClient(app) as client:
        submitted = client.post(
            "/api/connectors/discord/messages/jobs",
            headers=_connector_headers(),
            json=_inbound("route-message"),
        )
        assert submitted.status_code == 202, submitted.text
        body = submitted.json()
        assert body["progress"] == []
        job_id = body["job_id"]

        duplicate = client.post(
            "/api/connectors/discord/messages/jobs",
            headers=_connector_headers(),
            json=_inbound("route-message"),
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["job_id"] == job_id
        assert (
            client.get(
                f"/api/connectors/discord/turn-jobs/{job_id}?connection_id=wrong",
                headers=_connector_headers(),
            ).status_code
            == 404
        )

        view = None
        for _ in range(30):
            view = client.get(
                f"/api/connectors/discord/turn-jobs/{job_id}?connection_id=connection-1",
                headers=_connector_headers(),
            )
            if view.json()["progress"]:
                break
            time.sleep(0.01)
        assert (
            view is not None and view.json()["progress"][0]["text"] == "Looking up the image now."
        )
        claim = client.post(
            f"/api/connectors/discord/turn-jobs/{job_id}/progress/claim?connection_id=connection-1",
            headers=_connector_headers(),
            json={"nonce": "nonce-1"},
        )
        assert claim.status_code == 200
        progress_id = claim.json()["event"]["id"]
        assert (
            client.post(
                f"/api/connectors/discord/turn-jobs/{job_id}/progress/claim?connection_id=connection-1",
                headers=_connector_headers(),
                json={"nonce": "nonce-2"},
            ).json()["event"]
            is None
        )
        assert (
            client.post(
                f"/api/connectors/discord/turn-jobs/{job_id}/progress/{progress_id}/ack?connection_id=connection-1",
                headers=_connector_headers(),
                json={"nonce": "wrong"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/connectors/discord/turn-jobs/{job_id}/progress/{progress_id}/ack?connection_id=connection-1",
                headers=_connector_headers(),
                json={"nonce": "nonce-1"},
            ).status_code
            == 204
        )
        for _ in range(30):
            view = client.get(
                f"/api/connectors/discord/turn-jobs/{job_id}?connection_id=connection-1",
                headers=_connector_headers(),
            )
            if view.json()["status"] == "succeeded":
                break
            time.sleep(0.01)
        assert view is not None and view.json()["reply"]["reason"] == "ready"


def test_turn_job_queue_full_still_reattaches_duplicate_submission(tmp_path: Path) -> None:
    app = _app_with_scope(tmp_path / "queue.db", queue=1)

    async def slow_runner(_kind: str, _payload: str) -> str:
        await asyncio.sleep(5)
        return DiscordConnectorReplyView(action="silent", reason="late").model_dump_json()

    app.state.turn_job_manager.runner = slow_runner
    with TestClient(app) as client:
        first = client.post(
            "/api/connectors/discord/messages/jobs",
            headers=_connector_headers(),
            json=_inbound("first"),
        )
        assert first.status_code == 202
        first_id = first.json()["job_id"]
        for _ in range(20):
            active = client.get(
                f"/api/connectors/discord/turn-jobs/{first_id}?connection_id=connection-1",
                headers=_connector_headers(),
            )
            if active.json()["status"] == "running":
                break
            time.sleep(0.01)
        assert active.json()["status"] == "running"
        second = client.post(
            "/api/connectors/discord/messages/jobs",
            headers=_connector_headers(),
            json=_inbound("second"),
        )
        assert second.status_code == 202
        duplicate = client.post(
            "/api/connectors/discord/messages/jobs",
            headers=_connector_headers(),
            json=_inbound("second"),
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["job_id"] == second.json()["job_id"]


def test_exact_author_scoped_cancel_terminalizes_running_job_and_blocks_late_result(
    tmp_path: Path,
) -> None:
    app = _app_with_scope(tmp_path / "cancel.db")
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_runner(_kind: str, _payload: str) -> str:
        started.set()
        await release.wait()
        require_active_turn()
        return DiscordConnectorReplyView(
            action="reply", reason="late", text="old reply"
        ).model_dump_json()

    app.state.turn_job_manager.runner = delayed_runner
    with TestClient(app) as client:
        submitted = client.post(
            "/api/connectors/discord/messages/jobs",
            headers=_connector_headers(),
            json=_inbound("cancel-target"),
        )
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]
        for _ in range(30):
            if started.is_set():
                break
            time.sleep(0.01)
        assert started.is_set()
        cancelled = client.post(
            "/api/connectors/discord/turn-jobs/cancel?connection_id=connection-1",
            headers=_connector_headers(),
            json={
                "deployment_id": "deployment-1",
                "guild_id": "guild-1",
                "channel_id": "channel-1",
                "thread_id": "",
                "category_id": "",
                "source_message_id": "cancel-target",
                "source_author_id": "user-1",
                "reason": "user_cancelled",
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json() == [job_id]
        # A different author cannot cancel this request, even with the same destination/event.
        denied = client.post(
            "/api/connectors/discord/turn-jobs/cancel?connection_id=connection-1",
            headers=_connector_headers(),
            json={
                "deployment_id": "deployment-1",
                "guild_id": "guild-1",
                "channel_id": "channel-1",
                "thread_id": "",
                "category_id": "",
                "source_message_id": "cancel-target",
                "source_author_id": "other-user",
                "reason": "user_cancelled",
            },
        )
        assert denied.status_code == 200 and denied.json() == []
        release.set()
        for _ in range(30):
            view = client.get(
                f"/api/connectors/discord/turn-jobs/{job_id}?connection_id=connection-1",
                headers=_connector_headers(),
            )
            if view.json()["status"] == "cancelled":
                break
            time.sleep(0.01)
        assert view.json()["status"] == "cancelled"
        assert view.json()["reply"] is None


def test_cancel_generated_final_before_delivery_claim_is_atomic_and_does_not_replay(
    tmp_path: Path,
) -> None:
    app = _app_with_scope(tmp_path / "cancel-generated.db")
    repository = app.state.turn_job_repository
    operation_id = "a" * 64
    step_id = "b" * 64
    record, _ = repository.submit(
        kind="message",
        owner_id="owner-1",
        connection_id="connection-1",
        deployment_id="deployment-1",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id="generated-target",
        source_author_id="user-1",
        request_json="{}",
        deadline_seconds=30,
    )
    assert repository.mark_running(record.job_id) is not None
    repository.complete(
        record.job_id,
        field="reply",
        value=DiscordConnectorReplyView(
            action="reply",
            reason="ready",
            text="must not send",
            operation_id=operation_id,
            step_id=step_id,
            durable_status="generated",
            delivery_required=True,
        ).model_dump_json(),
    )
    with repository.database.session() as session:
        session.add(
            RuntimeOperationRecord(
                operation_id=operation_id,
                operation_kind="character_turn",
                owner_id="owner-1",
                connection_id="connection-1",
                guild_id="guild-1",
                channel_id="channel-1",
                source_message_id="generated-target",
                status="awaiting_delivery",
                initial_deployment_ids_json='["deployment-1"]',
            )
        )
        session.add(
            RuntimeStepRecord(
                step_id=step_id,
                operation_id=operation_id,
                deployment_id="deployment-1",
                status="generated",
                response_json='{"text":"must not send"}',
            )
        )
        session.commit()
    with TestClient(app) as client:
        assert repository.publish_progress(record.job_id, "already stored") is False
        cancelled = client.post(
            "/api/connectors/discord/turn-jobs/cancel?connection_id=connection-1",
            headers=_connector_headers(),
            json={
                "deployment_id": "deployment-1",
                "guild_id": "guild-1",
                "channel_id": "channel-1",
                "thread_id": "",
                "category_id": "",
                "source_message_id": "generated-target",
                "source_author_id": "user-1",
                "reason": "user_cancelled",
            },
        )
        assert cancelled.status_code == 200 and cancelled.json() == [record.job_id]
        assert client.post(
            f"/api/connectors/discord/turn-jobs/{record.job_id}/progress/claim?connection_id=connection-1",
            headers=_connector_headers(),
            json={"nonce": "post-cancel-progress"},
        ).status_code == 409
        delivery_claim = client.post(
            "/api/connectors/discord/messages/delivery/claim",
            headers=_connector_headers(),
            json={
                "connection_id": "connection-1",
                "operation_id": operation_id,
                "step_id": step_id,
                "claim_nonce": "post-cancel-delivery"
            },
        )
        assert delivery_claim.status_code == 409
    with repository.database.session() as session:
        step = session.get(RuntimeStepRecord, step_id)
        operation = session.get(RuntimeOperationRecord, operation_id)
        job = session.get(TurnJobRecord, record.job_id)
        assert step is not None and step.status == "failed" and step.response_json == "{}"
        assert operation is not None and operation.status == "failed"
        assert job is not None and job.status == "cancelled" and not job.reply_json


def test_cancel_reports_not_cancelled_when_delivery_claim_won(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'cancel-lost-race.db'}")
    database.initialize()
    repository = TurnJobRepository(database)
    operation_id = "c" * 64
    step_id = "d" * 64
    job, _ = repository.submit(
        kind="message", owner_id="owner-1", connection_id="connection-1",
        deployment_id="deployment-1", guild_id="guild-1", channel_id="channel-1",
        message_id="claim-won", source_author_id="user-1", request_json="{}", deadline_seconds=30,
    )
    assert repository.mark_running(job.job_id) is not None
    repository.complete(job.job_id, field="reply", value=f'{{"step_id":"{step_id}"}}')
    with database.session() as session:
        session.add(RuntimeOperationRecord(
            operation_id=operation_id, operation_kind="character_turn", owner_id="owner-1",
            connection_id="connection-1", guild_id="guild-1", channel_id="channel-1",
            source_message_id="claim-won", status="awaiting_delivery",
            initial_deployment_ids_json='["deployment-1"]',
        ))
        session.add(
            RuntimeStepRecord(
                step_id=step_id,
                operation_id=operation_id,
                deployment_id="deployment-1",
                status="generated",
            )
        )
        session.commit()
    assert repository.database is database
    from echo_masque.persistence.runtime_durability_repository import DurableRuntimeRepository

    claim, _ = DurableRuntimeRepository(database).claim_delivery(
        operation_id=operation_id, step_id=step_id, claim_nonce="delivery-claim-wins"
    )
    assert claim == "granted"
    assert repository.cancel_matching_request(
        owner_id="owner-1", connection_id="connection-1", deployment_id="deployment-1",
        guild_id="guild-1", channel_id="channel-1", thread_id="", category_id="",
        source_message_id="claim-won", source_author_id="user-1", reason="user_cancelled",
    ) == []
    assert repository.get(job.job_id, connection_id="connection-1").status == "succeeded"


def _submit(repository: TurnJobRepository, *, message_id: str = "message-1") -> str:
    record, _ = repository.submit(
        kind="message",
        owner_id="owner-1",
        connection_id="connection-1",
        deployment_id="deployment-1",
        guild_id="guild-1",
        channel_id="channel-1",
        message_id=message_id,
        request_json='{"message_id":"message-1"}',
        deadline_seconds=30,
    )
    return record.job_id


def test_turn_job_persists_early_progress_dedupes_and_scopes(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'turn-jobs.db'}")
    database.initialize()
    repository = TurnJobRepository(database)
    started, release = asyncio.Event(), asyncio.Event()

    async def runner(_kind: str, _payload: str) -> str:
        assert await publish_turn_progress("I'm gathering the image details now.")
        started.set()
        await release.wait()
        return '{"action":"reply","reason":"done"}'

    async def exercise() -> None:
        manager = TurnJobManager(repository, runner, max_queue=2, deadline_seconds=30)
        await manager.start()
        job_id = _submit(repository)
        duplicate, created = repository.submit(
            kind="message",
            owner_id="owner-1",
            connection_id="connection-1",
            deployment_id="deployment-1",
            guild_id="guild-1",
            channel_id="channel-1",
            message_id="message-1",
            request_json="{}",
            deadline_seconds=30,
        )
        assert not created and duplicate.job_id == job_id
        assert manager.submit(job_id)
        await asyncio.wait_for(started.wait(), timeout=1)
        assert [item.text for item in repository.list_progress(job_id)] == [
            "I'm gathering the image details now."
        ]
        assert repository.get(job_id, connection_id="other-connection") is None
        release.set()
        for _ in range(20):
            if repository.get(job_id, connection_id="connection-1").status == "succeeded":
                break
            await asyncio.sleep(0.01)
        await manager.stop()

    asyncio.run(exercise())


def test_turn_job_timeout_shutdown_and_reconstruction_preserve_terminal_reply(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'reconstruct.db'}")
    database.initialize()
    repository = TurnJobRepository(database)
    calls: list[str] = []

    async def fast_runner(_kind: str, _payload: str) -> str:
        calls.append("run")
        return '{"action":"silent","reason":"complete"}'

    async def exercise() -> None:
        manager = TurnJobManager(repository, fast_runner, max_queue=2, deadline_seconds=30)
        await manager.start()
        final_id = _submit(repository, message_id="final")
        assert manager.submit(final_id)
        for _ in range(20):
            if repository.get(final_id, connection_id="connection-1").status == "succeeded":
                break
            await asyncio.sleep(0.01)
        await manager.stop()
        # A fresh manager never replays a completed job and its result remains available.
        reconstructed = TurnJobManager(repository, fast_runner)
        final = repository.get(final_id, connection_id="connection-1")
        assert final is not None and final.status == "succeeded" and final.reply_json
        assert reconstructed.repository.get(final_id, connection_id="connection-1") is not None

        timed_out_id = _submit(repository, message_id="expired")
        with database.session() as session:
            row = session.get(type(final), timed_out_id)
            assert row is not None
            row.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        await reconstructed.start()
        assert reconstructed.submit(timed_out_id)
        for _ in range(20):
            if repository.get(timed_out_id, connection_id="connection-1").status == "timed_out":
                break
            await asyncio.sleep(0.01)
        assert repository.get(timed_out_id, connection_id="connection-1").status == "timed_out"
        assert calls == ["run"]
        await reconstructed.stop()

        started, release = asyncio.Event(), asyncio.Event()

        async def blocked_runner(_kind: str, _payload: str) -> str:
            started.set()
            await release.wait()
            return '{"action":"silent","reason":"late"}'

        stopping = TurnJobManager(repository, blocked_runner, deadline_seconds=30)
        stopped_id = _submit(repository, message_id="stopping")
        await stopping.start()
        assert stopping.submit(stopped_id)
        await asyncio.wait_for(started.wait(), timeout=1)
        await stopping.stop()
        assert repository.get(stopped_id, connection_id="connection-1").status == "stopped"

    asyncio.run(exercise())


def test_stopping_one_manager_leaves_other_managers_job_running(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'manager-ownership.db'}")
    database.initialize()
    repository = TurnJobRepository(database)

    async def exercise() -> None:
        first_started, second_started = asyncio.Event(), asyncio.Event()
        release = asyncio.Event()

        async def first_runner(_kind: str, _payload: str) -> str:
            first_started.set()
            await release.wait()
            return '{"action":"silent","reason":"first"}'

        async def second_runner(_kind: str, _payload: str) -> str:
            second_started.set()
            await release.wait()
            return '{"action":"silent","reason":"second"}'

        first = TurnJobManager(repository, first_runner)
        second = TurnJobManager(repository, second_runner)
        first_id = _submit(repository, message_id="manager-first")
        second_id = _submit(repository, message_id="manager-second")
        await first.start()
        await second.start()
        assert first.submit(first_id)
        assert second.submit(second_id)
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.wait_for(second_started.wait(), timeout=1)
        await first.stop()
        assert repository.get(second_id, connection_id="connection-1").status == "running"
        await second.stop()

    asyncio.run(exercise())
