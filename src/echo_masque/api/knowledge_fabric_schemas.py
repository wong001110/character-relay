"""Public Phase 2 schema surface for scoped Knowledge Fabric administration."""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeAccessGrantRecord,
    KnowledgeCharacterCorpusPolicyRecord,
    KnowledgeCorpusRecord,
    KnowledgeExternalSourceScheduleRecord,
    KnowledgeOverlayPolicyRecord,
    KnowledgeServerScopeRecord,
    KnowledgeSourceRecord,
)


class KnowledgeServerScopeCreate(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    connection_id: str = Field(min_length=1, max_length=64)
    workspace_id: str = Field(min_length=1, max_length=200)

    @field_validator("platform", "connection_id", "workspace_id")
    @classmethod
    def no_blank_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class KnowledgeServerScopeView(BaseModel):
    id: str
    platform: str
    connection_id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: KnowledgeServerScopeRecord) -> KnowledgeServerScopeView:
        return cls(
            id=record.id,
            platform=record.platform,
            connection_id=record.connection_id,
            workspace_id=record.workspace_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class KnowledgeServerAdministratorView(BaseModel):
    user_id: str
    created_at: datetime


class KnowledgeCorpusCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    default_authority_profile: str = Field(default="standard", min_length=1, max_length=80)

    @field_validator("name", "default_authority_profile")
    @classmethod
    def no_blank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class KnowledgeCorpusView(BaseModel):
    id: str
    name: str
    description: str
    owner_type: str
    owner_id: str
    visibility: str
    default_authority_profile: str
    status: str
    overlay_mode: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: KnowledgeCorpusRecord,
        *,
        overlay_mode: str | None = None,
    ) -> KnowledgeCorpusView:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            owner_type=record.owner_type,
            owner_id=record.owner_id,
            visibility=record.visibility,
            default_authority_profile=record.default_authority_profile,
            status=record.status,
            overlay_mode=overlay_mode,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class KnowledgeGrantUpdate(BaseModel):
    enabled: bool


class KnowledgeAccessGrantView(BaseModel):
    corpus_id: str
    grantee_type: str
    grantee_id: str
    enabled: bool
    access_mode: str
    updated_at: datetime

    @classmethod
    def from_record(cls, record: KnowledgeAccessGrantRecord) -> KnowledgeAccessGrantView:
        return cls(
            corpus_id=record.corpus_id,
            grantee_type=record.grantee_type,
            grantee_id=record.grantee_id,
            enabled=record.enabled,
            access_mode=record.access_mode,
            updated_at=record.updated_at,
        )


class KnowledgeServerGlobalCorpusAccessView(BaseModel):
    corpus_id: str
    enabled: bool
    overlay_mode: str


class KnowledgeOverlayPolicyUpdate(BaseModel):
    mode: str = Field(min_length=1, max_length=24)


class KnowledgeOverlayPolicyView(BaseModel):
    corpus_id: str
    mode: str
    updated_at: datetime

    @classmethod
    def from_record(cls, record: KnowledgeOverlayPolicyRecord) -> KnowledgeOverlayPolicyView:
        return cls(
            corpus_id=record.corpus_id,
            mode=record.mode,
            updated_at=record.updated_at,
        )


class KnowledgeCharacterCorpusPolicyUpdate(BaseModel):
    effect: str = Field(min_length=1, max_length=16)


class KnowledgeCharacterCorpusPolicyView(BaseModel):
    deployment_id: str
    character_card_id: str
    corpus_id: str
    effect: str
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: KnowledgeCharacterCorpusPolicyRecord,
    ) -> KnowledgeCharacterCorpusPolicyView:
        return cls(
            deployment_id=record.deployment_id,
            character_card_id=record.character_card_id,
            corpus_id=record.corpus_id,
            effect=record.effect,
            updated_at=record.updated_at,
        )


class KnowledgeSourceCreate(BaseModel):
    source_type: str = Field(min_length=1, max_length=40)
    locator: str = Field(min_length=1, max_length=1000)
    parser_profile: dict[str, str] = Field(default_factory=dict)
    sync_policy: dict[str, str] = Field(default_factory=dict)
    freshness_policy: dict[str, str] = Field(default_factory=dict)
    authority_profile: str = Field(default="standard", min_length=1, max_length=80)

    @field_validator("locator")
    @classmethod
    def locator_has_no_embedded_credential(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Source locator must be an absolute HTTP(S) URL.")
        if parsed.username or parsed.password or parsed.query:
            raise ValueError("Source locator must not contain credentials or query parameters.")
        return value

    @field_validator("parser_profile", "sync_policy", "freshness_policy")
    @classmethod
    def profiles_have_no_secret_keys(cls, value: dict[str, str]) -> dict[str, str]:
        forbidden = {"api_key", "credential", "password", "secret", "token"}
        if any(key.casefold() in forbidden for key in value):
            raise ValueError("Source profiles must not contain credentials or secrets.")
        return value


class KnowledgeSourceView(BaseModel):
    id: str
    corpus_id: str
    source_type: str
    locator: str
    parser_profile: dict[str, str]
    sync_policy: dict[str, str]
    freshness_policy: dict[str, str]
    authority_profile: str
    enabled: bool
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: KnowledgeSourceRecord) -> KnowledgeSourceView:
        return cls(
            id=record.id,
            corpus_id=record.corpus_id,
            source_type=record.source_type,
            locator=record.locator,
            parser_profile=_decode_profile(record.parser_profile_json),
            sync_policy=_decode_profile(record.sync_policy_json),
            freshness_policy=_decode_profile(record.freshness_policy_json),
            authority_profile=record.authority_profile,
            enabled=record.enabled,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class KnowledgeExternalSourceScheduleUpdate(BaseModel):
    enabled: bool
    interval_seconds: int = Field(default=900, ge=900, le=604800)


class KnowledgeExternalSourceScheduleView(BaseModel):
    source_id: str
    enabled: bool
    interval_seconds: int
    next_run_at: datetime | None
    last_error_code: str | None
    updated_at: datetime

    @classmethod
    def from_record(
        cls, record: KnowledgeExternalSourceScheduleRecord
    ) -> KnowledgeExternalSourceScheduleView:
        return cls(
            source_id=record.source_id,
            enabled=record.enabled,
            interval_seconds=record.interval_seconds,
            next_run_at=record.next_run_at,
            last_error_code=record.last_error_code,
            updated_at=record.updated_at,
        )


def encode_profile(value: dict[str, str]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _decode_profile(value: str) -> dict[str, str]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        return {}
    return {str(key): str(item) for key, item in decoded.items()}


__all__ = [
    "KnowledgeAccessGrantView",
    "KnowledgeCharacterCorpusPolicyUpdate",
    "KnowledgeCharacterCorpusPolicyView",
    "KnowledgeCorpusCreate",
    "KnowledgeCorpusView",
    "KnowledgeExternalSourceScheduleUpdate",
    "KnowledgeExternalSourceScheduleView",
    "KnowledgeGrantUpdate",
    "KnowledgeOverlayPolicyUpdate",
    "KnowledgeOverlayPolicyView",
    "KnowledgeServerAdministratorView",
    "KnowledgeServerGlobalCorpusAccessView",
    "KnowledgeServerScopeCreate",
    "KnowledgeServerScopeView",
    "KnowledgeSourceCreate",
    "KnowledgeSourceView",
    "encode_profile",
]
