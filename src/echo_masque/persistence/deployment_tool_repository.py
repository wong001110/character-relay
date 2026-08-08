"""Persistence for manual Tool assignments on Character Deployments."""

import json

from sqlalchemy import delete, select, update

from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DeploymentToolProfileRecord,
)


def _normalize(values: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def _decode(value: str) -> list[str]:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return _normalize(tuple(item for item in raw if isinstance(item, str)))


class DeploymentToolRepository:
    """Store only the deployment-level allowlist; Tool definitions live in ToolRegistry."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get_enabled_tools(self, deployment_id: str, owner_id: str) -> list[str] | None:
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                return None
            profile = session.get(DeploymentToolProfileRecord, deployment_id)
            if profile is None or profile.owner_id != owner_id:
                return []
            return _decode(profile.enabled_tools_json)

    def get_enabled_tools_for_runtime(self, deployment_id: str) -> tuple[str, ...]:
        """Runtime lookup for an already-authorized active deployment."""

        with self.database.session() as session:
            profile = session.get(DeploymentToolProfileRecord, deployment_id)
            if profile is None:
                return ()
            return tuple(_decode(profile.enabled_tools_json))

    def set_enabled_tools(
        self,
        *,
        deployment_id: str,
        owner_id: str,
        enabled_tools: list[str] | tuple[str, ...],
    ) -> list[str]:
        normalized = _normalize(enabled_tools)
        with self.database.session() as session:
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if deployment is None or deployment.owner_id != owner_id:
                raise KeyError("deployment")
            profile = session.get(DeploymentToolProfileRecord, deployment_id)
            if profile is None:
                profile = DeploymentToolProfileRecord(
                    deployment_id=deployment_id,
                    owner_id=owner_id,
                    enabled_tools_json=json.dumps(normalized),
                )
                session.add(profile)
            else:
                if profile.owner_id != owner_id:
                    raise KeyError("deployment")
                profile.enabled_tools_json = json.dumps(normalized)
            session.commit()
            return normalized

    def delete_deployment(self, deployment_id: str, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(DeploymentToolProfileRecord).where(
                    DeploymentToolProfileRecord.deployment_id == deployment_id,
                    DeploymentToolProfileRecord.owner_id == owner_id,
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_connection(self, connection_id: str, owner_id: str) -> int:
        with self.database.session() as session:
            deployment_ids = select(CharacterDeploymentRecord.id).where(
                CharacterDeploymentRecord.owner_id == owner_id,
                CharacterDeploymentRecord.connection_id == connection_id,
            )
            result = session.execute(
                delete(DeploymentToolProfileRecord).where(
                    DeploymentToolProfileRecord.owner_id == owner_id,
                    DeploymentToolProfileRecord.deployment_id.in_(deployment_ids),
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def delete_owner(self, owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                delete(DeploymentToolProfileRecord).where(
                    DeploymentToolProfileRecord.owner_id == owner_id
                )
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(DeploymentToolProfileRecord)
                .where(DeploymentToolProfileRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
            return int(getattr(result, "rowcount", 0) or 0)
