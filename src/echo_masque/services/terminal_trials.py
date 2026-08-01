"""Terminal-state guard for background Trial execution."""

from __future__ import annotations

import json
import logging

from echo_masque.domain import TrialStatus
from echo_masque.services.trials import TrialService as CoreTrialService

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = {TrialStatus.PENDING.value, TrialStatus.RUNNING.value}
_FALLBACK_ERROR = "Trial execution ended before a terminal status was persisted."
_UNEXPECTED_ERROR = "Trial execution failed unexpectedly."


class TrialService(CoreTrialService):
    """Run the normal Trial service and guarantee a persisted terminal state.

    Provider failures are normally handled by ``CoreTrialService``. This outer guard covers
    failures while persisting the terminal state, unexpected exceptions, task cancellation,
    and any future execution path that returns while the Run is still pending or running.
    """

    async def execute(self, run_id: str) -> None:
        try:
            await super().execute(run_id)
        except Exception:
            logger.exception("Unexpected Trial execution failure for run %s.", run_id)
            self._persist_terminal_failure(run_id, _UNEXPECTED_ERROR)
        finally:
            run = self.repository.get_run(run_id)
            if run is not None and run.status in _ACTIVE_STATUSES:
                self._persist_terminal_failure(
                    run_id,
                    self._last_failure_message(run_id) or _FALLBACK_ERROR,
                )

    def _persist_terminal_failure(self, run_id: str, message: str) -> None:
        """Persist failure before attempting the optional observable event."""

        try:
            self.repository.set_run_status(
                run_id,
                TrialStatus.FAILED,
                error=message,
            )
        except (KeyError, RuntimeError):
            logger.exception("Could not persist failed status for run %s.", run_id)
            return

        if self._has_failure_event(run_id):
            return
        try:
            self.repository.append_trial_event(
                run_id,
                "session_failed",
                {"message": message},
            )
        except (KeyError, RuntimeError):
            logger.exception("Could not append terminal failure event for run %s.", run_id)

    def _has_failure_event(self, run_id: str) -> bool:
        return any(
            item.event_type == "session_failed"
            for item in self.repository.list_trial_events(run_id)
        )

    def _last_failure_message(self, run_id: str) -> str | None:
        for item in reversed(self.repository.list_trial_events(run_id)):
            if item.event_type != "session_failed":
                continue
            try:
                payload = json.loads(item.payload_json)
            except (TypeError, json.JSONDecodeError):
                continue
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return None


__all__ = ["TrialService"]
