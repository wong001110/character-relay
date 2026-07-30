"""Invitation, role, workspace-claim, audit, and account lifecycle operations."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from echo_masque.auth import Role, SYSTEM_RUNTIME_USER_ID
from echo_masque.persistence import AuthRepository, Database
from echo_masque.persistence.models import (
    AuditEventRecord,
    AuthSessionRecord,
    CharacterCardRecord,
    CharacterTrialRecord,
    CustomScenarioRecord,
    EncryptedCredentialRecord,
    EvidenceRecord,
    ExperimentMatrixRecord,
    ExperimentMatrixTaskRecord,
    InvitationRecord,
    PersistenceProbeRecord,
    PromptVersionRecord,
    RunSnapshotRecord,
    TargetOwnershipRecord,
    TargetRecord,
    TestPackItemRecord,
    TestPackRecord,
    TrialEventRecord,
    TrialRunRecord,
    TurnRecord,
    UserRecord,
)
from echo_masque.persistence.security_models import RateLimitBucketRecord

InvitationRole = Literal["user", "admin"]
LOCAL_WORKSPACE_OWNER = "local-user"


class LifecycleConflict(RuntimeError):
    """Raised when a lifecycle mutation would violate a security invariant."""


class AccountLifecycleService:
    def __init__(self, database: Database, auth_repository: AuthRepository) -> None:
        self.database = database
        self.auth_repository = auth_repository

    def create_invitation(
        self,
        *,
        actor_user_id: str,
        email: str | None,
        role: InvitationRole,
        expires_in_days: int,
    ) -> tuple[InvitationRecord, str]:
        code = secrets.token_urlsafe(32)
        normalized_email = email.casefold().strip() if email else None
        record = InvitationRecord(
            id=str(uuid4()),
            code_hash=self._digest(code),
            email=normalized_email,
            role=role,
            created_by=actor_user_id,
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        self.auth_repository.audit(
            actor_user_id=actor_user_id,
            action="invitation.created",
            resource_type="invitation",
            resource_id=record.id,
            metadata={"email": normalized_email, "role": role},
        )
        return record, code

    def list_invitations(self, *, limit: int = 100) -> list[InvitationRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(InvitationRecord)
                    .order_by(InvitationRecord.created_at.desc())
                    .limit(limit)
                )
            )

    def revoke_invitation(self, invitation_id: str, *, actor_user_id: str) -> bool:
        with self.database.session() as session:
            record = session.get(InvitationRecord, invitation_id)
            if record is None or record.accepted_at is not None:
                return False
            if record.revoked_at is None:
                record.revoked_at = datetime.now(UTC)
                session.commit()
        self.auth_repository.audit(
            actor_user_id=actor_user_id,
            action="invitation.revoked",
            resource_type="invitation",
            resource_id=invitation_id,
        )
        return True

    def list_users(self) -> list[UserRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(UserRecord)
                    .where(UserRecord.id != SYSTEM_RUNTIME_USER_ID)
                    .order_by(UserRecord.created_at)
                )
            )

    def set_role(
        self,
        user_id: str,
        role: InvitationRole,
        *,
        actor_user_id: str,
    ) -> UserRecord | None:
        if user_id == SYSTEM_RUNTIME_USER_ID:
            raise LifecycleConflict("The system Runtime account cannot be modified.")
        if user_id == actor_user_id and role != "admin":
            raise LifecycleConflict("An Admin cannot demote the current account.")
        with self.database.session() as session:
            record = session.get(UserRecord, user_id)
            if record is None or not record.is_active:
                return None
            if record.role == "admin" and role != "admin":
                active_admins = session.scalar(
                    select(func.count())
                    .select_from(UserRecord)
                    .where(
                        UserRecord.role == "admin",
                        UserRecord.is_active.is_(True),
                        UserRecord.id != SYSTEM_RUNTIME_USER_ID,
                    )
                )
                if int(active_admins or 0) <= 1:
                    raise LifecycleConflict("At least one active Admin must remain.")
            previous = record.role
            record.role = role
            session.commit()
            session.refresh(record)
        self.auth_repository.audit(
            actor_user_id=actor_user_id,
            action="account.role_changed",
            resource_type="user",
            resource_id=user_id,
            metadata={"previous_role": previous, "new_role": role},
        )
        return record

    def list_audit_events(self, *, limit: int = 200) -> list[AuditEventRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(AuditEventRecord)
                    .order_by(AuditEventRecord.created_at.desc())
                    .limit(limit)
                )
            )

    def claim_local_workspace(self, *, actor_user_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        owner_models = {
            "characters": CharacterCardRecord,
            "scenarios": CustomScenarioRecord,
            "test_packs": TestPackRecord,
            "run_snapshots": RunSnapshotRecord,
            "prompt_versions": PromptVersionRecord,
            "matrices": ExperimentMatrixRecord,
            "probes": PersistenceProbeRecord,
            "credentials": EncryptedCredentialRecord,
        }
        with self.database.session() as session:
            for label, model in owner_models.items():
                result = session.execute(
                    update(model)
                    .where(model.owner_id == LOCAL_WORKSPACE_OWNER)
                    .values(owner_id=actor_user_id)
                )
                counts[label] = int(result.rowcount or 0)

            ownerships = list(
                session.scalars(
                    select(TargetOwnershipRecord).where(
                        TargetOwnershipRecord.owner_id == LOCAL_WORKSPACE_OWNER
                    )
                )
            )
            claimed_ownerships = 0
            for ownership in ownerships:
                existing = session.scalar(
                    select(TargetOwnershipRecord).where(
                        TargetOwnershipRecord.target_id == ownership.target_id,
                        TargetOwnershipRecord.owner_id == actor_user_id,
                    )
                )
                if existing is None:
                    ownership.owner_id = actor_user_id
                    claimed_ownerships += 1
                else:
                    session.delete(ownership)
            counts["target_ownership"] = claimed_ownerships

            target_ids = set(
                session.scalars(
                    select(CharacterCardRecord.target_id).where(
                        CharacterCardRecord.owner_id == actor_user_id
                    )
                )
            )
            for target_id in target_ids:
                if target_id.startswith("demo-"):
                    continue
                existing = session.scalar(
                    select(TargetOwnershipRecord).where(
                        TargetOwnershipRecord.target_id == target_id,
                        TargetOwnershipRecord.owner_id == actor_user_id,
                    )
                )
                if existing is None:
                    session.add(
                        TargetOwnershipRecord(
                            id=str(uuid4()),
                            target_id=target_id,
                            owner_id=actor_user_id,
                        )
                    )
                    counts["target_ownership"] += 1
            session.commit()

        total = sum(counts.values())
        if total == 0:
            raise LifecycleConflict("No unclaimed local workspace data was found.")
        self.auth_repository.audit(
            actor_user_id=actor_user_id,
            action="workspace.local_claimed",
            resource_type="workspace",
            resource_id=actor_user_id,
            metadata=counts,
        )
        return counts

    def delete_account(self, user_id: str, *, email: str) -> dict[str, int]:
        if user_id == SYSTEM_RUNTIME_USER_ID:
            raise LifecycleConflict("The system Runtime account cannot be deleted.")
        with self.database.session() as session:
            user = session.get(UserRecord, user_id)
            if user is None or not user.is_active:
                raise LifecycleConflict("Account is already unavailable.")
            if user.role == "admin":
                active_admins = session.scalar(
                    select(func.count())
                    .select_from(UserRecord)
                    .where(
                        UserRecord.role == "admin",
                        UserRecord.is_active.is_(True),
                        UserRecord.id != SYSTEM_RUNTIME_USER_ID,
                    )
                )
                if int(active_admins or 0) <= 1:
                    raise LifecycleConflict(
                        "Create another Admin before deleting the final Admin account."
                    )

        self.auth_repository.audit(
            actor_user_id=user_id,
            action="account.deletion_started",
            resource_type="user",
            resource_id=user_id,
        )
        deleted = self._delete_workspace(user_id)
        with self.database.session() as session:
            session.execute(
                delete(AuthSessionRecord).where(AuthSessionRecord.user_id == user_id)
            )
            session.execute(
                delete(EncryptedCredentialRecord).where(
                    EncryptedCredentialRecord.owner_id == user_id
                )
            )
            session.execute(
                delete(RateLimitBucketRecord).where(
                    RateLimitBucketRecord.key.in_(
                        (f"request:{user_id}", f"login:{self._digest(email.casefold().strip())}")
                    )
                )
            )
            user = session.get(UserRecord, user_id)
            if user is None:
                raise LifecycleConflict("Account disappeared during deletion.")
            user.email = f"deleted-{user.id}@echo-masque.invalid"
            user.display_name = "Deleted User"
            user.role = "user"
            user.is_active = False
            session.commit()
        self.auth_repository.audit(
            actor_user_id=user_id,
            action="account.deleted",
            resource_type="user",
            resource_id=user_id,
            metadata=deleted,
        )
        return deleted

    def _delete_workspace(self, owner_id: str) -> dict[str, int]:
        deleted: dict[str, int] = {}
        with self.database.session() as session:
            matrix_ids = list(
                session.scalars(
                    select(ExperimentMatrixRecord.id).where(
                        ExperimentMatrixRecord.owner_id == owner_id
                    )
                )
            )
            if matrix_ids:
                result = session.execute(
                    delete(ExperimentMatrixTaskRecord).where(
                        ExperimentMatrixTaskRecord.matrix_id.in_(matrix_ids)
                    )
                )
                deleted["matrix_tasks"] = int(result.rowcount or 0)
                result = session.execute(
                    delete(ExperimentMatrixRecord).where(
                        ExperimentMatrixRecord.id.in_(matrix_ids)
                    )
                )
                deleted["matrices"] = int(result.rowcount or 0)

            run_ids = list(
                session.scalars(
                    select(RunSnapshotRecord.run_id).where(
                        RunSnapshotRecord.owner_id == owner_id
                    )
                )
            )
            if run_ids:
                for label, model in (
                    ("evidence", EvidenceRecord),
                    ("events", TrialEventRecord),
                    ("turns", TurnRecord),
                    ("character_trials", CharacterTrialRecord),
                ):
                    result = session.execute(
                        delete(model).where(model.run_id.in_(run_ids))
                    )
                    deleted[label] = int(result.rowcount or 0)
                result = session.execute(
                    delete(RunSnapshotRecord).where(
                        RunSnapshotRecord.run_id.in_(run_ids)
                    )
                )
                deleted["run_snapshots"] = int(result.rowcount or 0)
                result = session.execute(
                    delete(TrialRunRecord).where(TrialRunRecord.id.in_(run_ids))
                )
                deleted["trial_runs"] = int(result.rowcount or 0)

            pack_ids = list(
                session.scalars(
                    select(TestPackRecord.id).where(TestPackRecord.owner_id == owner_id)
                )
            )
            if pack_ids:
                result = session.execute(
                    delete(TestPackItemRecord).where(
                        TestPackItemRecord.pack_id.in_(pack_ids)
                    )
                )
                deleted["pack_items"] = int(result.rowcount or 0)
                result = session.execute(
                    delete(TestPackRecord).where(TestPackRecord.id.in_(pack_ids))
                )
                deleted["test_packs"] = int(result.rowcount or 0)

            result = session.execute(
                delete(CustomScenarioRecord).where(
                    CustomScenarioRecord.owner_id == owner_id
                )
            )
            deleted["scenarios"] = int(result.rowcount or 0)

            card_records = list(
                session.scalars(
                    select(CharacterCardRecord).where(
                        CharacterCardRecord.owner_id == owner_id
                    )
                )
            )
            card_ids = [item.id for item in card_records]
            target_ids = {item.target_id for item in card_records}
            if card_ids:
                result = session.execute(
                    delete(PromptVersionRecord).where(
                        PromptVersionRecord.character_card_id.in_(card_ids)
                    )
                )
                deleted["prompt_versions"] = int(result.rowcount or 0)
                result = session.execute(
                    delete(CharacterCardRecord).where(
                        CharacterCardRecord.id.in_(card_ids)
                    )
                )
                deleted["characters"] = int(result.rowcount or 0)

            result = session.execute(
                delete(TargetOwnershipRecord).where(
                    TargetOwnershipRecord.owner_id == owner_id
                )
            )
            deleted["target_ownership"] = int(result.rowcount or 0)
            for target_id in target_ids:
                if target_id.startswith("demo-"):
                    continue
                remaining_cards = session.scalar(
                    select(func.count())
                    .select_from(CharacterCardRecord)
                    .where(CharacterCardRecord.target_id == target_id)
                )
                remaining_owners = session.scalar(
                    select(func.count())
                    .select_from(TargetOwnershipRecord)
                    .where(TargetOwnershipRecord.target_id == target_id)
                )
                if not remaining_cards and not remaining_owners:
                    result = session.execute(
                        delete(TargetRecord).where(TargetRecord.id == target_id)
                    )
                    deleted["targets"] = deleted.get("targets", 0) + int(
                        result.rowcount or 0
                    )

            result = session.execute(
                delete(PersistenceProbeRecord).where(
                    PersistenceProbeRecord.owner_id == owner_id
                )
            )
            deleted["probes"] = int(result.rowcount or 0)
            session.commit()
        return deleted

    @staticmethod
    def audit_metadata(record: AuditEventRecord) -> dict[str, object]:
        try:
            value = json.loads(record.metadata_json)
        except json.JSONDecodeError:
            return {}
        return cast(dict[str, object], value) if isinstance(value, dict) else {}

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
