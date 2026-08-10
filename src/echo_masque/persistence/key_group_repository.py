"""Persistence operations for reusable account-level provider Key Groups."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import delete, select

from echo_masque.persistence.database import Database
from echo_masque.persistence.key_group_models import (
    CharacterKeyGroupAssignmentRecord,
    ProviderKeyGroupRecord,
)

KeyGroupCapability = Literal["character", "media", "image_generation"]
DefaultModelMap = dict[str, str] | dict[KeyGroupCapability, str]
_VALID_CAPABILITIES = frozenset({"character", "media", "image_generation"})


@dataclass(frozen=True)
class ResolvedKeyGroup:
    group: ProviderKeyGroupRecord
    assignment: CharacterKeyGroupAssignmentRecord
    model: str


def _capability(value: str) -> KeyGroupCapability:
    normalized = value.strip().casefold()
    if normalized not in _VALID_CAPABILITIES:
        raise ValueError(f"Unsupported Key Group capability: {value}")
    return cast(KeyGroupCapability, normalized)


def _models_json(values: DefaultModelMap | None) -> str:
    normalized: dict[str, str] = {}
    for raw_capability, raw_model in (values or {}).items():
        capability = _capability(raw_capability)
        model = raw_model.strip()
        if model:
            normalized[capability] = model[:200]
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def default_models(record: ProviderKeyGroupRecord) -> dict[str, str]:
    try:
        raw = json.loads(record.default_models_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in raw.items()
        if str(key) in _VALID_CAPABILITIES and str(value).strip()
    }


class KeyGroupRepository:
    """Owner-scoped CRUD and Character capability assignments for Key Groups."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_group(
        self,
        *,
        owner_id: str,
        name: str,
        provider: str,
        base_url: str = "",
        default_models: DefaultModelMap | None = None,
    ) -> ProviderKeyGroupRecord:
        record = ProviderKeyGroupRecord(
            id=str(uuid4()),
            owner_id=owner_id,
            name=name.strip(),
            provider=provider.strip(),
            base_url=base_url.strip(),
            default_models_json=_models_json(default_models),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_groups(self, owner_id: str) -> list[ProviderKeyGroupRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ProviderKeyGroupRecord)
                    .where(ProviderKeyGroupRecord.owner_id == owner_id)
                    .order_by(ProviderKeyGroupRecord.name.asc())
                )
            )

    def get_group(self, owner_id: str, group_id: str) -> ProviderKeyGroupRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(ProviderKeyGroupRecord).where(
                    ProviderKeyGroupRecord.id == group_id,
                    ProviderKeyGroupRecord.owner_id == owner_id,
                )
            )

    def update_group(
        self,
        *,
        owner_id: str,
        group_id: str,
        name: str,
        provider: str,
        base_url: str,
        default_models: DefaultModelMap | None,
    ) -> ProviderKeyGroupRecord | None:
        with self.database.session() as session:
            record = session.scalar(
                select(ProviderKeyGroupRecord).where(
                    ProviderKeyGroupRecord.id == group_id,
                    ProviderKeyGroupRecord.owner_id == owner_id,
                )
            )
            if record is None:
                return None
            record.name = name.strip()
            record.provider = provider.strip()
            record.base_url = base_url.strip()
            record.default_models_json = _models_json(default_models)
            session.commit()
            session.refresh(record)
            return record

    def delete_group(self, *, owner_id: str, group_id: str) -> bool:
        with self.database.session() as session:
            record = session.scalar(
                select(ProviderKeyGroupRecord).where(
                    ProviderKeyGroupRecord.id == group_id,
                    ProviderKeyGroupRecord.owner_id == owner_id,
                )
            )
            if record is None:
                return False
            session.execute(
                delete(CharacterKeyGroupAssignmentRecord).where(
                    CharacterKeyGroupAssignmentRecord.owner_id == owner_id,
                    CharacterKeyGroupAssignmentRecord.key_group_id == group_id,
                )
            )
            session.delete(record)
            session.commit()
            return True

    def set_assignment(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        capability: str,
        key_group_id: str,
        model_override: str | None = None,
    ) -> CharacterKeyGroupAssignmentRecord:
        normalized_capability = _capability(capability)
        with self.database.session() as session:
            group = session.scalar(
                select(ProviderKeyGroupRecord).where(
                    ProviderKeyGroupRecord.id == key_group_id,
                    ProviderKeyGroupRecord.owner_id == owner_id,
                )
            )
            if group is None:
                raise ValueError("Key Group not found.")
            record = session.scalar(
                select(CharacterKeyGroupAssignmentRecord).where(
                    CharacterKeyGroupAssignmentRecord.owner_id == owner_id,
                    CharacterKeyGroupAssignmentRecord.character_card_id == character_card_id,
                    CharacterKeyGroupAssignmentRecord.capability == normalized_capability,
                )
            )
            normalized_model = (model_override or "").strip() or None
            if record is None:
                record = CharacterKeyGroupAssignmentRecord(
                    id=str(uuid4()),
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                    capability=normalized_capability,
                    key_group_id=key_group_id,
                    model_override=normalized_model,
                )
                session.add(record)
            else:
                record.key_group_id = key_group_id
                record.model_override = normalized_model
            session.commit()
            session.refresh(record)
            return record

    def get_assignment(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        capability: str,
    ) -> CharacterKeyGroupAssignmentRecord | None:
        normalized_capability = _capability(capability)
        with self.database.session() as session:
            return session.scalar(
                select(CharacterKeyGroupAssignmentRecord).where(
                    CharacterKeyGroupAssignmentRecord.owner_id == owner_id,
                    CharacterKeyGroupAssignmentRecord.character_card_id == character_card_id,
                    CharacterKeyGroupAssignmentRecord.capability == normalized_capability,
                )
            )

    def list_assignments(
        self,
        *,
        owner_id: str,
        character_card_id: str,
    ) -> list[CharacterKeyGroupAssignmentRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(CharacterKeyGroupAssignmentRecord)
                    .where(
                        CharacterKeyGroupAssignmentRecord.owner_id == owner_id,
                        CharacterKeyGroupAssignmentRecord.character_card_id == character_card_id,
                    )
                    .order_by(CharacterKeyGroupAssignmentRecord.capability.asc())
                )
            )

    def delete_assignment(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        capability: str,
    ) -> bool:
        normalized_capability = _capability(capability)
        with self.database.session() as session:
            record = session.scalar(
                select(CharacterKeyGroupAssignmentRecord).where(
                    CharacterKeyGroupAssignmentRecord.owner_id == owner_id,
                    CharacterKeyGroupAssignmentRecord.character_card_id == character_card_id,
                    CharacterKeyGroupAssignmentRecord.capability == normalized_capability,
                )
            )
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def resolve(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        capability: str,
    ) -> ResolvedKeyGroup | None:
        assignment = self.get_assignment(
            owner_id=owner_id,
            character_card_id=character_card_id,
            capability=capability,
        )
        if assignment is None:
            return None
        group = self.get_group(owner_id, assignment.key_group_id)
        if group is None:
            return None
        normalized_capability = _capability(capability)
        model = assignment.model_override or default_models(group).get(normalized_capability, "")
        return ResolvedKeyGroup(group=group, assignment=assignment, model=model)
