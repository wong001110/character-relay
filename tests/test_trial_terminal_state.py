import asyncio

from echo_masque.domain import TrialStatus
from echo_masque.persistence import Database, Repository
from echo_masque.services.terminal_trials import TrialService
from echo_masque.services.trials import TrialService as CoreTrialService


def repository(tmp_path) -> Repository:
    database = Database(f"sqlite:///{tmp_path / 'trial-terminal.db'}")
    database.initialize()
    return Repository(database)


def pending_run(repo: Repository) -> str:
    target = repo.create_target(
        name="Terminal guard fixture",
        target_kind="stable",
        config={},
    )
    return repo.create_run(
        target_id=target.id,
        suite=["identity_integrity"],
    ).id


def test_terminal_guard_recovers_session_failed_run(monkeypatch, tmp_path) -> None:
    repo = repository(tmp_path)
    run_id = pending_run(repo)

    async def incomplete_failure(self: CoreTrialService, current_run_id: str) -> None:
        self.repository.set_run_status(current_run_id, TrialStatus.RUNNING)
        self.repository.append_trial_event(
            current_run_id,
            "session_failed",
            {"message": "Model provider timed out."},
        )

    monkeypatch.setattr(CoreTrialService, "execute", incomplete_failure)

    asyncio.run(TrialService(repo).execute(run_id))

    run = repo.get_run(run_id)
    assert run is not None
    assert run.status == TrialStatus.FAILED.value
    assert run.error == "Model provider timed out."
    failures = [
        item for item in repo.list_trial_events(run_id) if item.event_type == "session_failed"
    ]
    assert len(failures) == 1


def test_terminal_guard_sanitizes_unexpected_execution_error(monkeypatch, tmp_path) -> None:
    repo = repository(tmp_path)
    run_id = pending_run(repo)

    async def unexpected_failure(self: CoreTrialService, current_run_id: str) -> None:
        self.repository.set_run_status(current_run_id, TrialStatus.RUNNING)
        raise RuntimeError("internal detail must not be returned")

    monkeypatch.setattr(CoreTrialService, "execute", unexpected_failure)

    asyncio.run(TrialService(repo).execute(run_id))

    run = repo.get_run(run_id)
    assert run is not None
    assert run.status == TrialStatus.FAILED.value
    assert run.error == "Trial execution failed unexpectedly."
    failure = next(
        item for item in repo.list_trial_events(run_id) if item.event_type == "session_failed"
    )
    assert "internal detail" not in failure.payload_json
