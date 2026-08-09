"""Strict hard-deletion helpers for disposable Character Relay test accounts."""

from __future__ import annotations

import re

from sqlalchemy import delete, or_, select, update

from echo_masque.account_lifecycle import AccountLifecycleService, LifecycleConflict
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import (
    AuditEventRecord,
    AuthSessionRecord,
    EncryptedCredentialRecord,
    InvitationRecord,
    TargetOwnershipRecord,
    UserRecord,
)
from echo_masque.persistence.provider_trace_models import (
    ProviderTraceIndexRecord,
    ProviderTraceRecord,
)
from echo_masque.persistence.security_models import RateLimitBucketRecord

_PHASE15_TEST_EMAIL = re.compile(r"^phase15-[ab]-\d+@example\.invalid$", re.IGNORECASE)
_EXACT_SYNTHETIC_IDS = frozenset({"railway-smoke"})


class SyntheticTestAccountError(RuntimeError):
    """Raised when a hard-delete target is not a recognized disposable test account."""


class SyntheticTestAccountService:
    """Hard-delete only tightly recognized smoke/acceptance fixtures.

    Normal user deletion remains intentionally anonymized/soft-deleted so retained audit
    records still have a stable history. This service is only for synthetic accounts created
    by Character Relay's own automated acceptance tests.
    """

    def __init__(
        self,
        database: Database,
        lifecycle: AccountLifecycleService,
    ) -> None:
        self.database = database
        self.lifecycle = lifecycle

    def purge_legacy(self) -> list[str]:
        """Remove historical synthetic fixtures without touching ordinary deleted users."""

        with self.database.session() as session:
            users = list(
                session.scalars(
                    select(UserRecord).where(UserRecord.id != SYSTEM_RUNTIME_USER_ID)
                )
            )
            accepted_emails = self._accepted_invitation_emails(session)
            candidate_ids = [
                user.id
                for user in users
                if user.id in _EXACT_SYNTHETIC_IDS
                or (
                    not user.is_active
                    and self._is_phase15_test_identity(
                        user,
                        accepted_emails.get(user.id, ()),
                    )
                )
            ]

        deleted: list[str] = []
        for user_id in candidate_ids:
            try:
                if self.hard_delete(user_id):
                    deleted.append(user_id)
            except (LifecycleConflict, SyntheticTestAccountError):
                # A strict verifier already limits candidates. Keep startup/admin cleanup
                # best-effort rather than making an unrelated account screen unavailable.
                continue
        return deleted

    def hard_delete(self, user_id: str) -> bool:
        normalized = user_id.strip()
        if not normalized or normalized == SYSTEM_RUNTIME_USER_ID:
            raise SyntheticTestAccountError("Synthetic test account not found.")

        with self.database.session() as session:
            user = session.get(UserRecord, normalized)
            if user is None:
                return False
            accepted = self._accepted_invitation_emails(session).get(user.id, ())
            if not self._is_synthetic(user, accepted):
                raise SyntheticTestAccountError(
                    "Hard deletion is restricted to Character Relay synthetic test accounts."
                )
            active = user.is_active
            email = user.email

        if active:
            # Dispatch through the application's full lifecycle implementation first. The
            # Evaluation-aware subclass clears deployments/RAG/reminders/etc. before the row
            # itself is finally hard-deleted below.
            self.lifecycle.delete_account(normalized, email=email)

        self._hard_delete_row(normalized)
        return True

    def _hard_delete_row(self, user_id: str) -> None:
        with self.database.session() as session:
            trace_ids = list(
                session.scalars(
                    select(ProviderTraceIndexRecord.trace_id).where(
                        ProviderTraceIndexRecord.owner_id == user_id
                    )
                )
            )
            if trace_ids:
                session.execute(
                    delete(ProviderTraceIndexRecord).where(
                        ProviderTraceIndexRecord.trace_id.in_(trace_ids)
                    )
                )
                session.execute(
                    delete(ProviderTraceRecord).where(
                        ProviderTraceRecord.trace_id.in_(trace_ids)
                    )
                )

            session.execute(
                update(AuditEventRecord)
                .where(AuditEventRecord.actor_user_id == user_id)
                .values(actor_user_id=None)
            )
            session.execute(
                delete(InvitationRecord).where(
                    or_(
                        InvitationRecord.accepted_by == user_id,
                        InvitationRecord.created_by == user_id,
                    )
                )
            )
            session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.user_id == user_id))
            session.execute(
                delete(EncryptedCredentialRecord).where(
                    EncryptedCredentialRecord.owner_id == user_id
                )
            )
            session.execute(
                delete(TargetOwnershipRecord).where(TargetOwnershipRecord.owner_id == user_id)
            )
            session.execute(
                delete(RateLimitBucketRecord).where(
                    RateLimitBucketRecord.key == f"request:{user_id}"
                )
            )
            user = session.get(UserRecord, user_id)
            if user is not None:
                session.delete(user)
            session.commit()

    @staticmethod
    def _accepted_invitation_emails(session: object) -> dict[str, tuple[str, ...]]:
        execute = getattr(session, "execute")
        rows = list(
            execute(
                select(InvitationRecord.accepted_by, InvitationRecord.email).where(
                    InvitationRecord.accepted_by.is_not(None)
                )
            )
        )
        grouped: dict[str, list[str]] = {}
        for user_id, email in rows:
            if isinstance(user_id, str) and isinstance(email, str):
                grouped.setdefault(user_id, []).append(email.casefold().strip())
        return {key: tuple(values) for key, values in grouped.items()}

    @classmethod
    def _is_synthetic(cls, user: UserRecord, accepted_emails: tuple[str, ...]) -> bool:
        return user.id in _EXACT_SYNTHETIC_IDS or cls._is_phase15_test_identity(
            user,
            accepted_emails,
        )

    @staticmethod
    def _is_phase15_test_identity(
        user: UserRecord,
        accepted_emails: tuple[str, ...],
    ) -> bool:
        if _PHASE15_TEST_EMAIL.fullmatch(user.email.casefold().strip()):
            return True
        return any(_PHASE15_TEST_EMAIL.fullmatch(email) for email in accepted_emails)
