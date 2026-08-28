"""Persistence boundary for Phase 2 Knowledge Fabric scope and access state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from echo_masque.knowledge_fabric_character_policy import (
    CHARACTER_CORPUS_EFFECTS,
    character_corpus_is_admitted,
)
from echo_masque.knowledge_fabric_policy import (
    is_local_user_owned,
    is_user_grant_for_account,
    is_user_owned_by,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_interpretation_repository import (
    KnowledgeFabricInterpretationRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeAccessGrantRecord,
    KnowledgeCharacterCorpusPolicyRecord,
    KnowledgeCorpusRecord,
    KnowledgeExternalSourceScheduleRecord,
    KnowledgeExternalSourceSyncStateRecord,
    KnowledgeOverlayPolicyRecord,
    KnowledgeServerAdministratorRecord,
    KnowledgeServerScopeRecord,
    KnowledgeSourceRecord,
)

OWNER_SYSTEM = "system"
OWNER_USER = "user"
OWNER_ORGANIZATION = "organization"
OWNER_SERVER = "server"

VISIBILITY_PRIVATE = "private"
VISIBILITY_SHARED = "shared"
VISIBILITY_GLOBAL = "global"

GRANTEE_USER = "user"
GRANTEE_ORGANIZATION = "organization"
GRANTEE_SERVER = "server"

OVERLAY_INHERIT = "inherit"
OVERLAY_AUGMENT = "augment"
OVERLAY_OVERRIDE = "override"
OVERLAY_DENY = "deny"
OVERLAY_MODES = frozenset(
    {OVERLAY_INHERIT, OVERLAY_AUGMENT, OVERLAY_OVERRIDE, OVERLAY_DENY}
)


@dataclass(frozen=True, slots=True)
class EffectiveKnowledgeCorpus:
    """A corpus admitted by scope authorization before any future ranking step."""

    corpus: KnowledgeCorpusRecord
    overlay_mode: str


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeCorpusAccess:
    """Server-local grant/overlay state for an available system corpus."""

    corpus_id: str
    enabled: bool
    overlay_mode: str


if TYPE_CHECKING:
    from echo_masque.knowledge_object_storage import KnowledgeObjectStorage


class KnowledgeFabricRepository:
    """Keep canonical server membership and corpus access in one explicit boundary."""

    def __init__(
        self,
        database: Database,
        *,
        object_storage: KnowledgeObjectStorage | None = None,
    ) -> None:
        self.database = database
        self.object_storage = object_storage

    def ensure_server_scope(
        self,
        *,
        platform: str,
        connection_id: str,
        workspace_id: str,
    ) -> KnowledgeServerScopeRecord:
        self._require_identifier("platform", platform)
        self._require_identifier("connection_id", connection_id)
        self._require_identifier("workspace_id", workspace_id)
        with self.database.session() as session:
            existing = session.scalar(
                select(KnowledgeServerScopeRecord).where(
                    KnowledgeServerScopeRecord.platform == platform,
                    KnowledgeServerScopeRecord.connection_id == connection_id,
                    KnowledgeServerScopeRecord.workspace_id == workspace_id,
                )
            )
            if existing is not None:
                return existing
            record = KnowledgeServerScopeRecord(
                id=str(uuid4()),
                platform=platform,
                connection_id=connection_id,
                workspace_id=workspace_id,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(KnowledgeServerScopeRecord).where(
                        KnowledgeServerScopeRecord.platform == platform,
                        KnowledgeServerScopeRecord.connection_id == connection_id,
                        KnowledgeServerScopeRecord.workspace_id == workspace_id,
                    )
                )
                if existing is None:
                    raise
                return existing
            session.refresh(record)
            return record

    def get_server_scope(self, scope_id: str) -> KnowledgeServerScopeRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeServerScopeRecord, scope_id)

    def find_server_scope(
        self,
        *,
        platform: str,
        connection_id: str,
        workspace_id: str,
    ) -> KnowledgeServerScopeRecord | None:
        """Read one existing canonical server scope without creating runtime state."""

        self._require_identifier("platform", platform)
        self._require_identifier("connection_id", connection_id)
        self._require_identifier("workspace_id", workspace_id)
        with self.database.session() as session:
            return session.scalar(
                select(KnowledgeServerScopeRecord).where(
                    KnowledgeServerScopeRecord.platform == platform,
                    KnowledgeServerScopeRecord.connection_id == connection_id,
                    KnowledgeServerScopeRecord.workspace_id == workspace_id,
                )
            )

    def list_server_scopes(self) -> list[KnowledgeServerScopeRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeServerScopeRecord).order_by(
                        KnowledgeServerScopeRecord.platform,
                        KnowledgeServerScopeRecord.connection_id,
                        KnowledgeServerScopeRecord.workspace_id,
                    )
                )
            )

    def list_server_scopes_for_administrator(
        self,
        user_id: str,
    ) -> list[KnowledgeServerScopeRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeServerScopeRecord)
                    .join(
                        KnowledgeServerAdministratorRecord,
                        KnowledgeServerAdministratorRecord.server_scope_id
                        == KnowledgeServerScopeRecord.id,
                    )
                    .where(KnowledgeServerAdministratorRecord.user_id == user_id)
                    .order_by(
                        KnowledgeServerScopeRecord.platform,
                        KnowledgeServerScopeRecord.connection_id,
                        KnowledgeServerScopeRecord.workspace_id,
                    )
                )
            )

    def add_server_administrator(
        self,
        *,
        server_scope_id: str,
        user_id: str,
    ) -> KnowledgeServerAdministratorRecord:
        with self.database.session() as session:
            existing = session.scalar(
                select(KnowledgeServerAdministratorRecord).where(
                    KnowledgeServerAdministratorRecord.server_scope_id == server_scope_id,
                    KnowledgeServerAdministratorRecord.user_id == user_id,
                )
            )
            if existing is not None:
                return existing
            record = KnowledgeServerAdministratorRecord(
                id=str(uuid4()),
                server_scope_id=server_scope_id,
                user_id=user_id,
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(KnowledgeServerAdministratorRecord).where(
                        KnowledgeServerAdministratorRecord.server_scope_id == server_scope_id,
                        KnowledgeServerAdministratorRecord.user_id == user_id,
                    )
                )
                if existing is None:
                    raise
                return existing
            session.refresh(record)
            return record

    def remove_server_administrator(self, *, server_scope_id: str, user_id: str) -> bool:
        with self.database.session() as session:
            result = session.execute(
                delete(KnowledgeServerAdministratorRecord).where(
                    KnowledgeServerAdministratorRecord.server_scope_id == server_scope_id,
                    KnowledgeServerAdministratorRecord.user_id == user_id,
                )
            )
            session.commit()
            return bool(self._rowcount(result))

    def is_server_administrator(self, *, server_scope_id: str, user_id: str) -> bool:
        with self.database.session() as session:
            return (
                session.scalar(
                    select(KnowledgeServerAdministratorRecord.id).where(
                        KnowledgeServerAdministratorRecord.server_scope_id == server_scope_id,
                        KnowledgeServerAdministratorRecord.user_id == user_id,
                    )
                )
                is not None
            )

    def list_server_administrator_ids(self, server_scope_id: str) -> list[str]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeServerAdministratorRecord.user_id)
                    .where(KnowledgeServerAdministratorRecord.server_scope_id == server_scope_id)
                    .order_by(KnowledgeServerAdministratorRecord.created_at)
                )
            )

    def list_server_administrators(
        self,
        server_scope_id: str,
    ) -> list[KnowledgeServerAdministratorRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeServerAdministratorRecord)
                    .where(KnowledgeServerAdministratorRecord.server_scope_id == server_scope_id)
                    .order_by(KnowledgeServerAdministratorRecord.created_at)
                )
            )

    def create_system_global_corpus(
        self,
        *,
        name: str,
        description: str,
        default_authority_profile: str,
        status: str,
    ) -> KnowledgeCorpusRecord:
        return self._create_corpus(
            name=name,
            description=description,
            owner_type=OWNER_SYSTEM,
            owner_id="system",
            visibility=VISIBILITY_GLOBAL,
            default_authority_profile=default_authority_profile,
            status=status,
        )

    def create_server_local_corpus(
        self,
        *,
        server_scope_id: str,
        name: str,
        description: str,
        default_authority_profile: str,
        status: str,
    ) -> KnowledgeCorpusRecord:
        return self._create_corpus(
            name=name,
            description=description,
            owner_type=OWNER_SERVER,
            owner_id=server_scope_id,
            visibility=VISIBILITY_PRIVATE,
            default_authority_profile=default_authority_profile,
            status=status,
        )

    def _create_corpus(
        self,
        *,
        name: str,
        description: str,
        owner_type: str,
        owner_id: str,
        visibility: str,
        default_authority_profile: str,
        status: str,
    ) -> KnowledgeCorpusRecord:
        self._require_identifier("name", name)
        self._require_identifier("owner_id", owner_id)
        self._require_identifier("default_authority_profile", default_authority_profile)
        self._require_identifier("status", status)
        record = KnowledgeCorpusRecord(
            id=str(uuid4()),
            name=name,
            description=description,
            owner_type=owner_type,
            owner_id=owner_id,
            visibility=visibility,
            default_authority_profile=default_authority_profile,
            status=status,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_corpus(self, corpus_id: str) -> KnowledgeCorpusRecord | None:
        with self.database.session() as session:
            return session.get(KnowledgeCorpusRecord, corpus_id)

    def list_system_global_corpora(self) -> list[KnowledgeCorpusRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCorpusRecord)
                    .where(
                        KnowledgeCorpusRecord.owner_type == OWNER_SYSTEM,
                        KnowledgeCorpusRecord.visibility == VISIBILITY_GLOBAL,
                    )
                    .order_by(KnowledgeCorpusRecord.name, KnowledgeCorpusRecord.id)
                )
            )

    def list_available_system_global_corpora(self) -> list[KnowledgeCorpusRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCorpusRecord)
                    .where(
                        KnowledgeCorpusRecord.owner_type == OWNER_SYSTEM,
                        KnowledgeCorpusRecord.visibility == VISIBILITY_GLOBAL,
                        KnowledgeCorpusRecord.status == "active",
                    )
                    .order_by(KnowledgeCorpusRecord.name, KnowledgeCorpusRecord.id)
                )
            )

    def list_server_local_corpora(self, server_scope_id: str) -> list[KnowledgeCorpusRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCorpusRecord)
                    .where(
                        KnowledgeCorpusRecord.owner_type == OWNER_SERVER,
                        KnowledgeCorpusRecord.owner_id == server_scope_id,
                    )
                    .order_by(KnowledgeCorpusRecord.name, KnowledgeCorpusRecord.id)
                )
            )

    def set_server_global_grant(
        self,
        *,
        server_scope_id: str,
        corpus_id: str,
        enabled: bool,
    ) -> KnowledgeAccessGrantRecord | None:
        with self.database.session() as session:
            corpus = session.get(KnowledgeCorpusRecord, corpus_id)
            if not self._is_available_system_global(corpus):
                return None
            existing = session.scalar(
                select(KnowledgeAccessGrantRecord).where(
                    KnowledgeAccessGrantRecord.corpus_id == corpus_id,
                    KnowledgeAccessGrantRecord.grantee_type == GRANTEE_SERVER,
                    KnowledgeAccessGrantRecord.grantee_id == server_scope_id,
                )
            )
            if existing is None:
                existing = KnowledgeAccessGrantRecord(
                    id=str(uuid4()),
                    corpus_id=corpus_id,
                    grantee_type=GRANTEE_SERVER,
                    grantee_id=server_scope_id,
                    enabled=enabled,
                    access_mode="read",
                )
                session.add(existing)
            else:
                existing.enabled = enabled
            try:
                session.commit()
            except IntegrityError:
                # A second replica may create this exact grant between the read and insert.
                # Re-read only that unique record, then apply this request's reversible state.
                session.rollback()
                existing = session.scalar(
                    select(KnowledgeAccessGrantRecord).where(
                        KnowledgeAccessGrantRecord.corpus_id == corpus_id,
                        KnowledgeAccessGrantRecord.grantee_type == GRANTEE_SERVER,
                        KnowledgeAccessGrantRecord.grantee_id == server_scope_id,
                    )
                )
                if existing is None:
                    raise
                existing.enabled = enabled
                session.commit()
            session.refresh(existing)
            return existing

    def get_server_global_grant(
        self,
        *,
        server_scope_id: str,
        corpus_id: str,
    ) -> KnowledgeAccessGrantRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(KnowledgeAccessGrantRecord).where(
                    KnowledgeAccessGrantRecord.corpus_id == corpus_id,
                    KnowledgeAccessGrantRecord.grantee_type == GRANTEE_SERVER,
                    KnowledgeAccessGrantRecord.grantee_id == server_scope_id,
                )
            )

    def list_server_global_corpus_access(
        self,
        server_scope_id: str,
    ) -> list[GlobalKnowledgeCorpusAccess]:
        """Expose reversible grant/overlay state without treating denied corpora as effective."""

        with self.database.session() as session:
            corpus_ids = list(
                session.scalars(
                    select(KnowledgeCorpusRecord.id).where(
                        KnowledgeCorpusRecord.owner_type == OWNER_SYSTEM,
                        KnowledgeCorpusRecord.visibility == VISIBILITY_GLOBAL,
                        KnowledgeCorpusRecord.status == "active",
                    )
                )
            )
            grants = {
                item.corpus_id: item.enabled
                for item in session.scalars(
                    select(KnowledgeAccessGrantRecord).where(
                        KnowledgeAccessGrantRecord.grantee_type == GRANTEE_SERVER,
                        KnowledgeAccessGrantRecord.grantee_id == server_scope_id,
                    )
                )
            }
            overlays = {
                item.corpus_id: item.mode
                for item in session.scalars(
                    select(KnowledgeOverlayPolicyRecord).where(
                        KnowledgeOverlayPolicyRecord.server_scope_id == server_scope_id
                    )
                )
            }
        return [
            GlobalKnowledgeCorpusAccess(
                corpus_id=corpus_id,
                enabled=grants.get(corpus_id, False),
                overlay_mode=overlays.get(corpus_id, OVERLAY_INHERIT),
            )
            for corpus_id in corpus_ids
        ]

    def set_overlay_policy(
        self,
        *,
        server_scope_id: str,
        corpus_id: str,
        mode: str,
    ) -> KnowledgeOverlayPolicyRecord:
        if mode not in OVERLAY_MODES:
            raise ValueError("Unknown Knowledge overlay mode.")
        with self.database.session() as session:
            existing = session.scalar(
                select(KnowledgeOverlayPolicyRecord).where(
                    KnowledgeOverlayPolicyRecord.server_scope_id == server_scope_id,
                    KnowledgeOverlayPolicyRecord.corpus_id == corpus_id,
                )
            )
            if existing is None:
                existing = KnowledgeOverlayPolicyRecord(
                    id=str(uuid4()),
                    server_scope_id=server_scope_id,
                    corpus_id=corpus_id,
                    mode=mode,
                )
                session.add(existing)
            else:
                existing.mode = mode
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(KnowledgeOverlayPolicyRecord).where(
                        KnowledgeOverlayPolicyRecord.server_scope_id == server_scope_id,
                        KnowledgeOverlayPolicyRecord.corpus_id == corpus_id,
                    )
                )
                if existing is None:
                    raise
                existing.mode = mode
                session.commit()
            session.refresh(existing)
            return existing

    def get_overlay_policy(
        self,
        *,
        server_scope_id: str,
        corpus_id: str,
    ) -> KnowledgeOverlayPolicyRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(KnowledgeOverlayPolicyRecord).where(
                    KnowledgeOverlayPolicyRecord.server_scope_id == server_scope_id,
                    KnowledgeOverlayPolicyRecord.corpus_id == corpus_id,
                )
            )

    def set_character_corpus_policy(
        self,
        *,
        server_scope_id: str,
        deployment_id: str,
        corpus_id: str,
        effect: str,
    ) -> KnowledgeCharacterCorpusPolicyRecord | None:
        """Author one explicit corpus decision only for its current deployment/server identity."""

        if effect not in CHARACTER_CORPUS_EFFECTS:
            raise ValueError("Unknown Character corpus policy effect.")
        if not self.is_corpus_effectively_available(
            server_scope_id=server_scope_id,
            corpus_id=corpus_id,
        ):
            raise ValueError("Knowledge Corpus is not available to this server scope.")
        with self.database.session() as session:
            scope = session.get(KnowledgeServerScopeRecord, server_scope_id)
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if scope is None or deployment is None:
                return None
            if (
                deployment.platform != scope.platform
                or deployment.connection_id != scope.connection_id
                or deployment.workspace_id != scope.workspace_id
            ):
                return None
            character_card_id = deployment.character_card_id
            existing = session.scalar(
                select(KnowledgeCharacterCorpusPolicyRecord).where(
                    KnowledgeCharacterCorpusPolicyRecord.server_scope_id == server_scope_id,
                    KnowledgeCharacterCorpusPolicyRecord.deployment_id == deployment_id,
                    KnowledgeCharacterCorpusPolicyRecord.character_card_id
                    == character_card_id,
                    KnowledgeCharacterCorpusPolicyRecord.corpus_id == corpus_id,
                )
            )
            if existing is None:
                existing = KnowledgeCharacterCorpusPolicyRecord(
                    id=str(uuid4()),
                    server_scope_id=server_scope_id,
                    deployment_id=deployment_id,
                    character_card_id=character_card_id,
                    corpus_id=corpus_id,
                    effect=effect,
                )
                session.add(existing)
            else:
                existing.effect = effect
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(KnowledgeCharacterCorpusPolicyRecord).where(
                        KnowledgeCharacterCorpusPolicyRecord.server_scope_id == server_scope_id,
                        KnowledgeCharacterCorpusPolicyRecord.deployment_id == deployment_id,
                        KnowledgeCharacterCorpusPolicyRecord.character_card_id
                        == character_card_id,
                        KnowledgeCharacterCorpusPolicyRecord.corpus_id == corpus_id,
                    )
                )
                if existing is None:
                    raise
                existing.effect = effect
                session.commit()
            session.refresh(existing)
            return existing

    def list_character_corpus_policies(
        self,
        server_scope_id: str,
    ) -> list[KnowledgeCharacterCorpusPolicyRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeCharacterCorpusPolicyRecord)
                    .where(KnowledgeCharacterCorpusPolicyRecord.server_scope_id == server_scope_id)
                    .order_by(
                        KnowledgeCharacterCorpusPolicyRecord.deployment_id,
                        KnowledgeCharacterCorpusPolicyRecord.character_card_id,
                        KnowledgeCharacterCorpusPolicyRecord.corpus_id,
                    )
                )
            )

    def character_corpus_is_admitted(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        corpus_id: str,
    ) -> bool:
        """Read one bounded explicit decision; absent/mismatched state denies by default."""

        with self.database.session() as session:
            effects = frozenset(
                session.scalars(
                    select(KnowledgeCharacterCorpusPolicyRecord.effect)
                    .join(
                        KnowledgeServerScopeRecord,
                        KnowledgeServerScopeRecord.id
                        == KnowledgeCharacterCorpusPolicyRecord.server_scope_id,
                    )
                    .join(
                        CharacterDeploymentRecord,
                        CharacterDeploymentRecord.id
                        == KnowledgeCharacterCorpusPolicyRecord.deployment_id,
                    )
                    .where(
                        KnowledgeCharacterCorpusPolicyRecord.deployment_id == deployment_id,
                        KnowledgeCharacterCorpusPolicyRecord.character_card_id == character_card_id,
                        KnowledgeCharacterCorpusPolicyRecord.corpus_id == corpus_id,
                        CharacterDeploymentRecord.character_card_id == character_card_id,
                        CharacterDeploymentRecord.platform == KnowledgeServerScopeRecord.platform,
                        CharacterDeploymentRecord.connection_id
                        == KnowledgeServerScopeRecord.connection_id,
                        CharacterDeploymentRecord.workspace_id
                        == KnowledgeServerScopeRecord.workspace_id,
                    )
                )
            )
        return character_corpus_is_admitted(effects)

    def list_effective_corpora(self, server_scope_id: str) -> list[EffectiveKnowledgeCorpus]:
        """Return only access-authorized corpora before any future retrieval/ranking."""

        with self.database.session() as session:
            local = list(
                session.scalars(
                    select(KnowledgeCorpusRecord).where(
                        KnowledgeCorpusRecord.owner_type == OWNER_SERVER,
                        KnowledgeCorpusRecord.owner_id == server_scope_id,
                        KnowledgeCorpusRecord.status == "active",
                    )
                )
            )
            granted = list(
                session.scalars(
                    select(KnowledgeCorpusRecord)
                    .join(
                        KnowledgeAccessGrantRecord,
                        KnowledgeAccessGrantRecord.corpus_id == KnowledgeCorpusRecord.id,
                    )
                    .where(
                        KnowledgeCorpusRecord.owner_type == OWNER_SYSTEM,
                        KnowledgeCorpusRecord.visibility == VISIBILITY_GLOBAL,
                        KnowledgeCorpusRecord.status == "active",
                        KnowledgeAccessGrantRecord.grantee_type == GRANTEE_SERVER,
                        KnowledgeAccessGrantRecord.grantee_id == server_scope_id,
                        KnowledgeAccessGrantRecord.enabled.is_(True),
                    )
                )
            )
            policies = {
                item.corpus_id: item.mode
                for item in session.scalars(
                    select(KnowledgeOverlayPolicyRecord).where(
                        KnowledgeOverlayPolicyRecord.server_scope_id == server_scope_id
                    )
                )
            }
        effective = [
            EffectiveKnowledgeCorpus(
                corpus=item,
                overlay_mode=policies.get(item.id, OVERLAY_INHERIT),
            )
            for item in [*local, *granted]
            if policies.get(item.id) != OVERLAY_DENY
        ]
        return sorted(effective, key=lambda item: (item.corpus.name.casefold(), item.corpus.id))

    def is_corpus_effectively_available(
        self,
        *,
        server_scope_id: str,
        corpus_id: str,
    ) -> bool:
        return any(
            item.corpus.id == corpus_id
            for item in self.list_effective_corpora(server_scope_id)
        )

    def create_source(
        self,
        *,
        corpus_id: str,
        source_type: str,
        locator: str,
        access_profile_json: str,
        parser_profile_json: str,
        sync_policy_json: str,
        freshness_policy_json: str,
        authority_profile: str,
    ) -> KnowledgeSourceRecord:
        record = KnowledgeSourceRecord(
            id=str(uuid4()),
            corpus_id=corpus_id,
            source_type=source_type,
            locator=locator,
            access_profile_json=access_profile_json,
            parser_profile_json=parser_profile_json,
            sync_policy_json=sync_policy_json,
            freshness_policy_json=freshness_policy_json,
            authority_profile=authority_profile,
        )
        with self.database.session() as session:
            if session.get(KnowledgeCorpusRecord, corpus_id) is None:
                raise KeyError("corpus")
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_sources(self, corpus_id: str) -> list[KnowledgeSourceRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(KnowledgeSourceRecord)
                    .where(KnowledgeSourceRecord.corpus_id == corpus_id)
                    .order_by(KnowledgeSourceRecord.created_at, KnowledgeSourceRecord.id)
                )
            )

    def update_source_parser_profile(
        self,
        *,
        source_id: str,
        parser_profile_json: str,
    ) -> KnowledgeSourceRecord | None:
        """Persist one administrator-approved parser recipe without changing Source identity."""

        with self.database.session() as session:
            record = session.get(KnowledgeSourceRecord, source_id)
            if record is None:
                return None
            record.parser_profile_json = parser_profile_json
            session.commit()
            session.refresh(record)
            return record

    def delete_owner(self, user_id: str) -> dict[str, int]:
        """Delete only user-owned Fabric records and explicit user memberships/grants."""

        content_repository = KnowledgeFabricContentRepository(
            self.database,
            object_storage=self.object_storage,
        )
        interpretation_repository = KnowledgeFabricInterpretationRepository(self.database)
        with self.database.session() as session:
            corpus_ids = [
                record.id
                for record in session.scalars(
                    select(KnowledgeCorpusRecord).where(
                        KnowledgeCorpusRecord.owner_id == user_id
                    )
                )
                if is_user_owned_by(
                    owner_type=record.owner_type,
                    owner_id=record.owner_id,
                    account_id=user_id,
                )
            ]
            interpretation_counts = (
                interpretation_repository.delete_interpretations_for_corpora_in_session(
                session,
                corpus_ids,
                )
            )
            content_counts = content_repository.delete_content_for_corpora_in_session(
                session,
                corpus_ids,
            )
            source_count = 0
            policy_count = 0
            character_policy_count = 0
            corpus_grant_count = 0
            corpus_count = 0
            external_sync_state_count = 0
            external_schedule_count = 0
            if corpus_ids:
                external_schedule_count = self._rowcount(
                    session.execute(
                        delete(KnowledgeExternalSourceScheduleRecord).where(
                            KnowledgeExternalSourceScheduleRecord.source_id.in_(
                                select(KnowledgeSourceRecord.id).where(
                                    KnowledgeSourceRecord.corpus_id.in_(corpus_ids)
                                )
                            )
                        )
                    )
                )
                external_sync_state_count = self._rowcount(
                    session.execute(
                        delete(KnowledgeExternalSourceSyncStateRecord).where(
                            KnowledgeExternalSourceSyncStateRecord.source_id.in_(
                                select(KnowledgeSourceRecord.id).where(
                                    KnowledgeSourceRecord.corpus_id.in_(corpus_ids)
                                )
                            )
                        )
                    )
                )
                source_count = self._rowcount(
                    session.execute(
                        delete(KnowledgeSourceRecord).where(KnowledgeSourceRecord.corpus_id.in_(corpus_ids))
                    )
                )
                policy_count = self._rowcount(
                    session.execute(
                        delete(KnowledgeOverlayPolicyRecord).where(
                            KnowledgeOverlayPolicyRecord.corpus_id.in_(corpus_ids)
                        )
                    )
                )
                character_policy_count = self._rowcount(
                    session.execute(
                        delete(KnowledgeCharacterCorpusPolicyRecord).where(
                            KnowledgeCharacterCorpusPolicyRecord.corpus_id.in_(corpus_ids)
                        )
                    )
                )
                corpus_grant_count = self._rowcount(
                    session.execute(
                        delete(KnowledgeAccessGrantRecord).where(
                            KnowledgeAccessGrantRecord.corpus_id.in_(corpus_ids)
                        )
                    )
                )
                corpus_count = self._rowcount(
                    session.execute(
                        delete(KnowledgeCorpusRecord).where(KnowledgeCorpusRecord.id.in_(corpus_ids))
                    )
                )
            member_count = self._rowcount(
                session.execute(
                    delete(KnowledgeServerAdministratorRecord).where(
                        KnowledgeServerAdministratorRecord.user_id == user_id
                    )
                )
            )
            user_grant_ids = [
                record.id
                for record in session.scalars(
                    select(KnowledgeAccessGrantRecord).where(
                        KnowledgeAccessGrantRecord.grantee_id == user_id
                    )
                )
                if is_user_grant_for_account(
                    grantee_type=record.grantee_type,
                    grantee_id=record.grantee_id,
                    account_id=user_id,
                )
            ]
            user_grant_count = self._rowcount(
                session.execute(
                    delete(KnowledgeAccessGrantRecord).where(
                        KnowledgeAccessGrantRecord.id.in_(user_grant_ids)
                    )
                )
                if user_grant_ids
                else None
            )
            session.commit()
        content_repository.process_pending_object_deletions()
        return {
            **interpretation_counts,
            **content_counts,
            "knowledge_fabric_corpora": corpus_count,
            "knowledge_fabric_external_source_schedules": external_schedule_count,
            "knowledge_fabric_external_source_sync_states": external_sync_state_count,
            "knowledge_fabric_sources": source_count,
            "knowledge_fabric_corpus_grants": corpus_grant_count,
            "knowledge_fabric_overlay_policies": policy_count,
            "knowledge_fabric_character_corpus_policies": character_policy_count,
            "knowledge_fabric_server_administrators": member_count,
            "knowledge_fabric_user_grants": user_grant_count,
        }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        """Claim only user-owned local rows; server/system principals never transfer."""

        with self.database.session() as session:
            corpus_ids = [
                record.id
                for record in session.scalars(
                    select(KnowledgeCorpusRecord).where(
                        KnowledgeCorpusRecord.owner_id == source_owner_id
                    )
                )
                if is_local_user_owned(
                    owner_type=record.owner_type,
                    owner_id=record.owner_id,
                    local_owner_id=source_owner_id,
                )
            ]
            corpus_count = self._rowcount(
                session.execute(
                    update(KnowledgeCorpusRecord)
                    .where(KnowledgeCorpusRecord.id.in_(corpus_ids))
                    .values(owner_id=target_owner_id)
                )
                if corpus_ids
                else None
            )
            grant_ids = [
                record.id
                for record in session.scalars(
                    select(KnowledgeAccessGrantRecord).where(
                        KnowledgeAccessGrantRecord.grantee_id == source_owner_id
                    )
                )
                if is_user_grant_for_account(
                    grantee_type=record.grantee_type,
                    grantee_id=record.grantee_id,
                    account_id=source_owner_id,
                )
            ]
            grant_count = self._rowcount(
                session.execute(
                    update(KnowledgeAccessGrantRecord)
                    .where(KnowledgeAccessGrantRecord.id.in_(grant_ids))
                    .values(grantee_id=target_owner_id)
                )
                if grant_ids
                else None
            )
            session.commit()
        return {
            "knowledge_fabric_corpora": corpus_count,
            "knowledge_fabric_user_grants": grant_count,
        }

    @staticmethod
    def _is_available_system_global(corpus: KnowledgeCorpusRecord | None) -> bool:
        return bool(
            corpus is not None
            and corpus.owner_type == OWNER_SYSTEM
            and corpus.visibility == VISIBILITY_GLOBAL
            and corpus.status == "active"
        )

    @staticmethod
    def _require_identifier(field: str, value: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} is required.")

    @staticmethod
    def _rowcount(result: object) -> int:
        return int(getattr(result, "rowcount", 0) or 0)


__all__ = [
    "GRANTEE_ORGANIZATION",
    "GRANTEE_SERVER",
    "GRANTEE_USER",
    "OVERLAY_AUGMENT",
    "OVERLAY_DENY",
    "OVERLAY_INHERIT",
    "OVERLAY_MODES",
    "OVERLAY_OVERRIDE",
    "OWNER_ORGANIZATION",
    "OWNER_SERVER",
    "OWNER_SYSTEM",
    "OWNER_USER",
    "VISIBILITY_GLOBAL",
    "VISIBILITY_PRIVATE",
    "VISIBILITY_SHARED",
    "EffectiveKnowledgeCorpus",
    "GlobalKnowledgeCorpusAccess",
    "KnowledgeFabricRepository",
]
