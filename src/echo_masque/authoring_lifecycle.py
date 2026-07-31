"""Account lifecycle integration for Phase 16 authoring resources."""

from echo_masque.account_lifecycle import (
    AccountLifecycleService,
    LifecycleConflict,
)
from echo_masque.authoring_archive import AuthoringArchiveService
from echo_masque.persistence import AuthRepository, Database


class AuthoringAwareAccountLifecycleService(AccountLifecycleService):
    def __init__(
        self,
        database: Database,
        auth_repository: AuthRepository,
        authoring_archive_service: AuthoringArchiveService,
    ) -> None:
        super().__init__(database, auth_repository)
        self.authoring_archive_service = authoring_archive_service

    def delete_account(self, user_id: str, *, email: str) -> dict[str, int]:
        deleted = super().delete_account(user_id, email=email)
        deleted.update(self.authoring_archive_service.delete_owner(user_id))
        return deleted

    def claim_local_workspace(self, *, actor_user_id: str) -> dict[str, int]:
        base_counts: dict[str, int] = {}
        base_error: LifecycleConflict | None = None
        try:
            base_counts = super().claim_local_workspace(actor_user_id=actor_user_id)
        except LifecycleConflict as exc:
            base_error = exc

        authoring_counts = self.authoring_archive_service.claim_owner(
            "local-user",
            actor_user_id,
        )
        combined = {**base_counts, **authoring_counts}
        if sum(combined.values()) == 0:
            if base_error is not None:
                raise base_error
            raise LifecycleConflict("No unclaimed local workspace data was found.")

        if sum(authoring_counts.values()) > 0:
            self.auth_repository.audit(
                actor_user_id=actor_user_id,
                action="workspace.authoring_local_claimed",
                resource_type="workspace",
                resource_id=actor_user_id,
                metadata=authoring_counts,
            )
        return combined
