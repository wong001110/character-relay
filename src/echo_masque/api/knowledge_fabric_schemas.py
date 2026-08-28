"""Public Phase 2 schema surface for scoped Knowledge Fabric administration."""

from __future__ import annotations

import json
import re
from datetime import datetime
from itertools import pairwise
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, Field, field_validator

from echo_masque.knowledge_fabric_query import KnowledgeQueryHit, KnowledgeQueryResult
from echo_masque.knowledge_fabric_query_policy import query_mode_is_valid
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeImageAssetCandidate,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeAccessGrantRecord,
    KnowledgeCanonicalEntityRecord,
    KnowledgeCanonicalVisualReferenceRecord,
    KnowledgeCharacterCorpusPolicyRecord,
    KnowledgeCorpusRecord,
    KnowledgeExternalSourceScheduleRecord,
    KnowledgeExternalSourceSyncStateRecord,
    KnowledgeOverlayPolicyRecord,
    KnowledgeServerScopeRecord,
    KnowledgeSourceRecord,
)
from echo_masque.persistence.knowledge_fabric_site_collection_repository import (
    SiteCollectionSyncSummary,
)

_CREDENTIAL_PROFILE_WORDS = frozenset(
    {
        "authorization",
        "auth",
        "bearer",
        "cookie",
        "credential",
        "password",
        "secret",
        "token",
    }
)
_CREDENTIAL_PROFILE_WORD_PAIRS = frozenset(
    {
        ("access", "key"),
        ("api", "key"),
        ("client", "key"),
        ("private", "key"),
    }
)
_CREDENTIAL_PROFILE_COMPACT_NAMES = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "authorization",
        "auth",
        "bearer",
        "clientkey",
        "clientsecret",
        "cookie",
        "credential",
        "password",
        "privatekey",
        "secret",
        "token",
    }
)


def _credential_profile_key(value: str) -> bool:
    """Return whether a profile key denotes credential-bearing configuration."""

    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).casefold()
    words = tuple(word for word in re.split(r"[^a-z0-9]+", normalized) if word)
    if "".join(words) in _CREDENTIAL_PROFILE_COMPACT_NAMES:
        return True
    if _CREDENTIAL_PROFILE_WORDS.intersection(words):
        return True
    return any(pair in _CREDENTIAL_PROFILE_WORD_PAIRS for pair in pairwise(words))


def _fragment_contains_credential(fragment: str) -> bool:
    """Reject query-shaped fragments that carry credential material, not normal anchors."""

    decoded = unquote(fragment)
    for component in re.split(r"[&;]", decoded):
        key, separator, value = component.partition("=")
        if separator and value.strip() and _credential_profile_key(key):
            return True
    return False


def _profile_value_contains_credential(value: str) -> bool:
    """Catch credential values disguised behind an otherwise innocuous profile key."""

    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        return True
    if _fragment_contains_credential(value):
        return True
    return bool(re.match(r"^\s*(?:basic|bearer)\s+\S+", value, flags=re.IGNORECASE))


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
        if _fragment_contains_credential(parsed.fragment):
            raise ValueError("Source locator fragment must not contain credentials.")
        return value

    @field_validator("parser_profile", "sync_policy", "freshness_policy")
    @classmethod
    def profiles_have_no_secret_keys(cls, value: dict[str, str]) -> dict[str, str]:
        if any(
            _credential_profile_key(key) or _profile_value_contains_credential(profile_value)
            for key, profile_value in value.items()
        ):
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


class KnowledgeVisualReferenceCreate(BaseModel):
    """An administrator's provenance-backed approval of one existing image Asset."""

    canonical_entity_id: str = Field(min_length=1, max_length=64)
    evidence_unit_id: str = Field(min_length=1, max_length=64)
    asset_id: str = Field(min_length=1, max_length=64)
    descriptor: dict[str, str] = Field(default_factory=dict)
    comparison_authorized: bool = False


class KnowledgeCanonicalEntityCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=80)
    canonical_name: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, str] = Field(default_factory=dict)


class KnowledgeCanonicalEntityView(BaseModel):
    id: str
    corpus_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str]
    status: str
    metadata: dict[str, str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: KnowledgeCanonicalEntityRecord) -> KnowledgeCanonicalEntityView:
        aliases = json.loads(record.aliases_json)
        metadata = json.loads(record.metadata_json)
        return cls(
            id=record.id,
            corpus_id=record.corpus_id,
            entity_type=record.entity_type,
            canonical_name=record.canonical_name,
            aliases=[str(item) for item in aliases] if isinstance(aliases, list) else [],
            status=record.status,
            metadata=(
                {str(key): str(value) for key, value in metadata.items()}
                if isinstance(metadata, dict)
                else {}
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class KnowledgeImageAssetCandidateView(BaseModel):
    """Approval inventory metadata; private object identifiers are intentionally absent."""

    source_id: str
    source_version_id: str
    document_id: str
    document_locator: str
    asset_id: str
    evidence_unit_id: str
    asset_type: str
    caption: str

    @classmethod
    def from_candidate(
        cls, candidate: KnowledgeImageAssetCandidate
    ) -> KnowledgeImageAssetCandidateView:
        return cls(
            source_id=candidate.source_id,
            source_version_id=candidate.source_version_id,
            document_id=candidate.document_id,
            document_locator=candidate.document_locator,
            asset_id=candidate.asset_id,
            evidence_unit_id=candidate.evidence_unit_id,
            asset_type=candidate.asset_type,
            caption=candidate.caption,
        )


class KnowledgeVisualReferenceView(BaseModel):
    """Private artifact identity stays opaque; no object location is exposed."""

    id: str
    corpus_id: str
    canonical_entity_id: str
    evidence_unit_id: str
    asset_id: str
    descriptor: dict[str, str]
    comparison_authorized: bool
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls, record: KnowledgeCanonicalVisualReferenceRecord
    ) -> KnowledgeVisualReferenceView:
        decoded = json.loads(record.descriptor_json)
        descriptor = (
            {
                str(key): str(value)
                for key, value in decoded.items()
                if key != "comparison_authorized"
            }
            if isinstance(decoded, dict)
            else {}
        )
        return cls(
            id=record.id,
            corpus_id=record.corpus_id,
            canonical_entity_id=record.canonical_entity_id,
            evidence_unit_id=record.evidence_unit_id,
            asset_id=record.asset_id,
            descriptor=descriptor,
            comparison_authorized=decoded.get("comparison_authorized") is True
            if isinstance(decoded, dict)
            else False,
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


class KnowledgeExternalSourceSyncStateView(BaseModel):
    source_id: str
    last_outcome: str
    last_error_code: str | None
    updated_at: datetime

    @classmethod
    def from_record(
        cls, record: KnowledgeExternalSourceSyncStateRecord
    ) -> KnowledgeExternalSourceSyncStateView:
        return cls(
            source_id=record.source_id,
            last_outcome=record.last_outcome,
            last_error_code=record.last_error_code,
            updated_at=record.updated_at,
        )


class KnowledgeDerivedWorkSummaryView(BaseModel):
    """Redacted aggregate only; invalidation IDs, leases, errors, and metadata stay internal."""

    pending: int
    running: int
    failed: int


class KnowledgeSiteCollectionSyncSummaryView(BaseModel):
    """Aggregate Site Collection facts that are safe to expose to a global operator."""

    source_id: str
    last_completed_at: datetime | None
    available_page_count: int
    removed_page_count: int
    checked_page_count: int
    failed_page_count: int

    @classmethod
    def from_summary(
        cls, summary: SiteCollectionSyncSummary
    ) -> KnowledgeSiteCollectionSyncSummaryView:
        return cls(
            source_id=summary.source_id,
            last_completed_at=summary.last_completed_at,
            available_page_count=summary.available_page_count,
            removed_page_count=summary.removed_page_count,
            checked_page_count=summary.checked_page_count,
            failed_page_count=summary.failed_page_count,
        )


class KnowledgeSourceOperationalView(BaseModel):
    """Operator-safe Source status; profiles, locators, artifacts, and metadata stay private."""

    id: str
    corpus_id: str
    source_type: str
    authority_profile: str
    enabled: bool
    status: str
    last_checked_at: datetime | None
    last_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    external_sync: KnowledgeExternalSourceSyncStateView | None
    external_schedule: KnowledgeExternalSourceScheduleView | None
    site_collection_summary: KnowledgeSiteCollectionSyncSummaryView | None
    derived_work: KnowledgeDerivedWorkSummaryView

    @classmethod
    def from_record(
        cls,
        record: KnowledgeSourceRecord,
        *,
        external_sync: KnowledgeExternalSourceSyncStateRecord | None,
        external_schedule: KnowledgeExternalSourceScheduleRecord | None,
        site_collection_summary: SiteCollectionSyncSummary | None,
        derived_work: KnowledgeDerivedWorkSummaryView,
    ) -> KnowledgeSourceOperationalView:
        return cls(
            id=record.id,
            corpus_id=record.corpus_id,
            source_type=record.source_type,
            authority_profile=record.authority_profile,
            enabled=record.enabled,
            status=record.status,
            last_checked_at=record.last_checked_at,
            last_changed_at=record.last_changed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
            external_sync=(
                KnowledgeExternalSourceSyncStateView.from_record(external_sync)
                if external_sync is not None
                else None
            ),
            external_schedule=(
                KnowledgeExternalSourceScheduleView.from_record(external_schedule)
                if external_schedule is not None
                else None
            ),
            site_collection_summary=(
                KnowledgeSiteCollectionSyncSummaryView.from_summary(site_collection_summary)
                if site_collection_summary is not None
                else None
            ),
            derived_work=derived_work,
        )


class KnowledgeQueryInspectorRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = Field(default="overview", min_length=1, max_length=24)
    as_of: datetime | None = None

    @field_validator("query")
    @classmethod
    def query_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Knowledge query must not be blank.")
        return value

    @field_validator("mode")
    @classmethod
    def mode_is_supported(cls, value: str) -> str:
        if not query_mode_is_valid(value):
            raise ValueError("Unknown Knowledge query mode.")
        return value


class KnowledgeQueryInspectorHitView(BaseModel):
    evidence_unit_id: str
    corpus_id: str
    source_version_id: str
    evidence_locator: str
    document_title: str
    text_content: str
    authority_profile: str
    channels: list[str]

    @classmethod
    def from_hit(cls, hit: KnowledgeQueryHit) -> KnowledgeQueryInspectorHitView:
        return cls(
            evidence_unit_id=hit.evidence_unit_id,
            corpus_id=hit.corpus_id,
            source_version_id=hit.source_version_id,
            evidence_locator=hit.evidence_locator,
            document_title=hit.document_title,
            text_content=hit.text_content,
            authority_profile=hit.authority_profile,
            channels=list(hit.channels),
        )


class KnowledgeQueryInspectorResultView(BaseModel):
    mode: str
    accessible_corpus_count: int
    freshness_status: str
    hits: list[KnowledgeQueryInspectorHitView]

    @classmethod
    def from_result(cls, result: KnowledgeQueryResult) -> KnowledgeQueryInspectorResultView:
        return cls(
            mode=result.mode,
            accessible_corpus_count=result.accessible_corpus_count,
            freshness_status=result.freshness_status,
            hits=[KnowledgeQueryInspectorHitView.from_hit(hit) for hit in result.hits],
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
    "KnowledgeCanonicalEntityCreate",
    "KnowledgeCanonicalEntityView",
    "KnowledgeCharacterCorpusPolicyUpdate",
    "KnowledgeCharacterCorpusPolicyView",
    "KnowledgeCorpusCreate",
    "KnowledgeCorpusView",
    "KnowledgeDerivedWorkSummaryView",
    "KnowledgeExternalSourceScheduleUpdate",
    "KnowledgeExternalSourceScheduleView",
    "KnowledgeExternalSourceSyncStateView",
    "KnowledgeGrantUpdate",
    "KnowledgeImageAssetCandidateView",
    "KnowledgeOverlayPolicyUpdate",
    "KnowledgeOverlayPolicyView",
    "KnowledgeQueryInspectorHitView",
    "KnowledgeQueryInspectorRequest",
    "KnowledgeQueryInspectorResultView",
    "KnowledgeServerAdministratorView",
    "KnowledgeServerGlobalCorpusAccessView",
    "KnowledgeServerScopeCreate",
    "KnowledgeServerScopeView",
    "KnowledgeSourceCreate",
    "KnowledgeSourceOperationalView",
    "KnowledgeSourceView",
    "KnowledgeVisualReferenceCreate",
    "KnowledgeVisualReferenceView",
    "encode_profile",
]
