"""Persistence and authority helpers for Deployment-scoped Presence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.deployment_presence_models import DeploymentPresenceRecord

DeploymentPresenceState = Literal["sleeping", "idle", "browsing", "busy"]
_VALID_STATES = frozenset({"sleeping", "idle", "browsing", "busy"})


def _as_utc(value: datetime) -> datetime:
    """Treat SQLite-naive persisted datetimes as UTC and preserve aware instants."""

    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class DeploymentPresenceView:
    deployment_id: str
    owner_id: str
    state: DeploymentPresenceState
    activity_type: str
    source: str
    reason: str
    version: int
    started_at: datetime
    expected_end_at: datetime | None
    updated_at: datetime
    persisted: bool

    @property
    def available_for_character_runtime(self) -> bool:
        return self.state != "sleeping"

    @property
    def discovery_allowed(self) -> bool:
        return self.state in {"idle", "browsing"}


class DeploymentPresenceRepository:
    """Store Presence on Deployments while treating missing rows as backward-compatible IDLE."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _view(
        deployment: CharacterDeploymentRecord,
        record: DeploymentPresenceRecord | None,
    ) -> DeploymentPresenceView:
        fallback_time = _as_utc(deployment.updated_at or deployment.created_at)
        if record is None:
            return DeploymentPresenceView(
                deployment_id=deployment.id,
                owner_id=deployment.owner_id,
                state="idle",
                activity_type="",
                source="default",
                reason="presence_not_configured",
                version=0,
                started_at=fallback_time,
                expected_end_at=None,
                updated_at=fallback_time,
                persisted=False,
            )
        return DeploymentPresenceView(
            deployment_id=record.deployment_id,
            owner_id=record.owner_id,
            state=cast(DeploymentPresenceState, record.state),
            activity_type=record.activity_type,
            source=record.source,
            reason=record.reason,
            version=record.version,
            started_at=_as_utc(record.started_at),
            expected_end_at=(
                _as_utc(record.expected_end_at)
                if record.expected_end_at is not None
                else None
            ),
            updated_at=_as_utc(record.updated_at),
            persisted=True,
        )

    def get(self, *, owner_id: str, deployment_id: str) -> DeploymentPresenceView | None:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentPresenceRecord, deployment_id)
            return self._view(deployment, record)

    def get_for_runtime(self, deployment: CharacterDeploymentRecord) -> DeploymentPresenceView:
        """Read one already-authorized Deployment without introducing Character-global scope."""

        with self.database.session() as session:
            record = session.get(DeploymentPresenceRecord, deployment.id)
            return self._view(deployment, record)

    def states_for_deployments(
        self,
        deployments: list[CharacterDeploymentRecord],
    ) -> dict[str, DeploymentPresenceView]:
        if not deployments:
            return {}
        ids = [item.id for item in deployments]
        with self.database.session() as session:
            records = {
                item.deployment_id: item
                for item in session.scalars(
                    select(DeploymentPresenceRecord).where(
                        DeploymentPresenceRecord.deployment_id.in_(ids)
                    )
                )
            }
        return {
            item.id: self._view(item, records.get(item.id))
            for item in deployments
        }

    def set_state(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        state: DeploymentPresenceState,
        activity_type: str = "",
        source: str = "manual",
        reason: str = "",
        expected_end_at: datetime | None = None,
        now: datetime | None = None,
    ) -> DeploymentPresenceView | None:
        normalized_state = state.strip().casefold()
        if normalized_state not in _VALID_STATES:
            raise ValueError(f"Unsupported Deployment Presence state: {state}")
        current = _as_utc(now or datetime.now(UTC))
        normalized_activity = " ".join(activity_type.split())[:40]
        normalized_source = " ".join(source.split())[:40] or "manual"
        normalized_reason = reason.strip()[:1000]
        normalized_expected_end = (
            _as_utc(expected_end_at) if expected_end_at is not None else None
        )
        if normalized_state != "browsing":
            normalized_activity = ""

        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            record = session.get(DeploymentPresenceRecord, deployment_id)
            if record is None:
                record = DeploymentPresenceRecord(
                    deployment_id=deployment.id,
                    owner_id=deployment.owner_id,
                    state=normalized_state,
                    activity_type=normalized_activity,
                    source=normalized_source,
                    reason=normalized_reason,
                    version=1,
                    started_at=current,
                    expected_end_at=normalized_expected_end,
                    created_at=current,
                    updated_at=current,
                )
                session.add(record)
            else:
                changed_state = (
                    record.state != normalized_state
                    or record.activity_type != normalized_activity
                )
                record.state = normalized_state
                record.activity_type = normalized_activity
                record.source = normalized_source
                record.reason = normalized_reason
                record.expected_end_at = normalized_expected_end
                if changed_state:
                    record.started_at = current
                    record.version += 1
                record.updated_at = current
            session.commit()
            session.refresh(record)
            return self._view(deployment, record)

    def is_sleeping(self, deployment: CharacterDeploymentRecord) -> bool:
        return self.get_for_runtime(deployment).state == "sleeping"

    def delete_deployment(self, *, owner_id: str, deployment_id: str) -> bool:
        with self.database.session() as session:
            result = session.execute(
                delete(DeploymentPresenceRecord).where(
                    DeploymentPresenceRecord.owner_id == owner_id,
                    DeploymentPresenceRecord.deployment_id == deployment_id,
                )
            )
            session.commit()
            rowcount = cast(CursorResult[Any], result).rowcount or 0
            return bool(rowcount)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(DeploymentPresenceRecord).where(
                    DeploymentPresenceRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)


__all__ = [
    "DeploymentPresenceRepository",
    "DeploymentPresenceState",
    "DeploymentPresenceView",
]
