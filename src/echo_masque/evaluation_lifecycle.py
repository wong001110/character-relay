"""Account deletion and legacy ownership integration for Judge evaluations."""

from typing import cast

from echo_masque.account_lifecycle import LifecycleConflict
from echo_masque.authoring_archive import AuthoringArchiveService
from echo_masque.calibration_lifecycle import CalibrationAwareAccountLifecycleService
from echo_masque.persistence import (
    AuthRepository,
    CalibrationRepository,
    Database,
    EvaluationRepository,
)


class EvaluationAwareAccountLifecycleService(
    CalibrationAwareAccountLifecycleService
):
    def __init__(
        self,
        database: Database,
        auth_repository: AuthRepository,
        authoring_archive_service: AuthoringArchiveService,
        calibration_repository: CalibrationRepository,
        evaluation_repository: EvaluationRepository,
    ) -> None:
        super().__init__(
            database,
            auth_repository,
            authoring_archive_service,
            calibration_repository,
        )
        self.evaluation_repository = evaluation_repository

    def delete_account(self, user_id: str, *, email: str) -> dict[str, int]:
        deleted = super().delete_account(user_id, email=email)
        deleted.update(self.evaluation_repository.delete_owner(user_id))
        return deleted

    def claim_local_workspace(self, *, actor_user_id: str) -> dict[str, int]:
        base_counts: dict[str, int] = {}
        base_error: LifecycleConflict | None = None
        try:
            base_counts = super().claim_local_workspace(actor_user_id=actor_user_id)
        except LifecycleConflict as exc:
            base_error = exc

        evaluation_counts = self.evaluation_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        combined = {**base_counts, **evaluation_counts}
        if sum(combined.values()) == 0:
            if base_error is not None:
                raise base_error
            raise LifecycleConflict("No unclaimed local workspace data was found.")

        if sum(evaluation_counts.values()) > 0:
            self.auth_repository.audit(
                actor_user_id=actor_user_id,
                action="workspace.evaluation_local_claimed",
                resource_type="workspace",
                resource_id=actor_user_id,
                metadata=cast(dict[str, object], evaluation_counts),
            )
        return combined
