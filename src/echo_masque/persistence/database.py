"""Database engine, schema initialization, and persistent storage identity."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlite3 import Connection as SQLiteConnection

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from echo_masque.persistence.belief_models import (
    BeliefEvidenceDependencyRecord,
    BeliefRevisionEventRecord,
    BeliefV3Record,
)
from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.character_learned_state_models import CharacterLearnedStateRecord
from echo_masque.persistence.character_relationship_models import (
    CharacterPersonImpressionRecord,
    CharacterRelationshipPriorRecord,
    DeploymentRelationshipEventRecord,
    DeploymentRelationshipStateRecord,
)
from echo_masque.persistence.conversation_runtime_models import (
    ConversationEpisodeV3Record,
    PendingActionV3Record,
    ThreadWorkingStateRecord,
)
from echo_masque.persistence.conversation_structure_models import (
    ConversationSegmentV3Record,
    ConversationThreadRecord,
    MessageRelationRecord,
    ThreadMembershipRecord,
)
from echo_masque.persistence.deployment_activity_models import (
    DeploymentActivitySessionItemRecord,
    DeploymentActivitySessionRecord,
)
from echo_masque.persistence.deployment_presence_models import DeploymentPresenceRecord
from echo_masque.persistence.deployment_presence_notice_models import DeploymentPresenceNoticeRecord
from echo_masque.persistence.deployment_presence_rhythm_models import DeploymentPresenceRhythmRecord
from echo_masque.persistence.discovery_models import (
    DeploymentDiscoveryDecisionRecord,
    DeploymentDiscoveryExposureRecord,
    DeploymentDiscoveryProfileRecord,
    DiscoveryItemRecord,
    DiscoverySourceQueryCacheRecord,
)
from echo_masque.persistence.discovery_share_models import (
    DeploymentDiscoverySharePolicyRecord,
    DeploymentDiscoveryShareRecord,
)
from echo_masque.persistence.discord_identity_models import DiscordGuildActorIdentityRecord
from echo_masque.persistence.entity_evidence_models import (
    EntityV3Record,
    EvidenceEdgeV3Record,
    KnowledgeGapRecord,
)
from echo_masque.persistence.episodic_sql_rag_models import (
    CharacterEpisodeAccessRecord,
    ConversationEntityRecord,
    ConversationEpisodeEntityRecord,
)
from echo_masque.persistence.models import Base, StorageMetadataRecord
from echo_masque.persistence.intelligence_v3_migration_models import (
    IntelligenceV3HardCutoverMigrationRecord,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeAccessGrantRecord,
    KnowledgeCharacterCorpusPolicyRecord,
    KnowledgeAssetReferenceRecord,
    KnowledgeCanonicalBlockRecord,
    KnowledgeCanonicalDocumentRecord,
    KnowledgeCanonicalEntityRecord,
    KnowledgeCanonicalSectionRecord,
    KnowledgeCorpusRecord,
    KnowledgeDependencyInvalidationRecord,
    KnowledgeEvidenceEmbeddingRecord,
    KnowledgeEvidenceGraphRelationRecord,
    KnowledgeEvidenceRetrievalEntryRecord,
    KnowledgeEvidenceUnitRecord,
    KnowledgeExternalHostRateRecord,
    KnowledgeExternalSourceScheduleRecord,
    KnowledgeExternalSourceSyncStateRecord,
    KnowledgeExtractedAssertionRecord,
    KnowledgeIngestionCheckpointRecord,
    KnowledgeIngestionJobRecord,
    KnowledgeInterpretationEvidenceRecord,
    KnowledgeObjectArtifactRecord,
    KnowledgeOverlayPolicyRecord,
    KnowledgeProjectionDependencyRecord,
    KnowledgeProjectionRecord,
    KnowledgeRuntimeEntityResolutionRecord,
    KnowledgeServerAdministratorRecord,
    KnowledgeServerScopeRecord,
    KnowledgeSourceRecord,
    KnowledgeSourceCurrentEntryRecord,
    KnowledgeSourceVersionRecord,
    KnowledgeWorldEventParticipantRecord,
    KnowledgeWorldEventRecord,
)
from echo_masque.persistence.operational_migration_models import (
    OperationalDataMigrationRecord,
)
from echo_masque.persistence.schema_migration_models import (
    DatabaseDataMigrationRecord,
    DatabaseSchemaMigrationRecord,
)
from echo_masque.persistence.server_knowledge_v3_models import (
    KnowledgeConsolidationCheckpointV3Record,
    ServerWikiPageV3Record,
)
from echo_masque.persistence.smart_participation_state_models import (
    SmartParticipationDeploymentStateRecord,
    SmartParticipationScopeStateRecord,
)
from echo_masque.persistence.social_intelligence_models import (
    ImpressionV3Record,
    SocialEventV3Record,
)
from echo_masque.persistence.utility_gateway_models import UtilityProviderQuotaRecord
from echo_masque.persistence.wiki_page_models import WikiPageRecord


@dataclass(frozen=True, slots=True)
class DeploymentServerDuplicate:
    """One legacy duplicate Deployment identity that requires explicit owner repair."""

    owner_id: str
    connection_id: str
    workspace_id: str
    character_card_id: str
    deployment_count: int


_SQLITE_DEPLOYMENT_SERVER_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS cr_one_character_per_discord_server_insert
BEFORE INSERT ON character_deployments
WHEN NEW.platform = 'discord'
 AND NEW.workspace_id <> ''
 AND EXISTS (
    SELECT 1
    FROM character_deployments AS existing
    WHERE existing.owner_id = NEW.owner_id
      AND existing.platform = 'discord'
      AND existing.connection_id = NEW.connection_id
      AND existing.workspace_id = NEW.workspace_id
      AND existing.character_card_id = NEW.character_card_id
 )
BEGIN
    SELECT RAISE(ABORT, 'character_card_already_deployed_to_discord_server');
END;
"""

_SQLITE_DEPLOYMENT_SERVER_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS cr_one_character_per_discord_server_update
BEFORE UPDATE OF owner_id, platform, connection_id, workspace_id, character_card_id
ON character_deployments
WHEN NEW.platform = 'discord'
 AND NEW.workspace_id <> ''
 AND EXISTS (
    SELECT 1
    FROM character_deployments AS existing
    WHERE existing.id <> NEW.id
      AND existing.owner_id = NEW.owner_id
      AND existing.platform = 'discord'
      AND existing.connection_id = NEW.connection_id
      AND existing.workspace_id = NEW.workspace_id
      AND existing.character_card_id = NEW.character_card_id
 )
BEGIN
    SELECT RAISE(ABORT, 'character_card_already_deployed_to_discord_server');
END;
"""

_SQLITE_DEPLOYMENT_PRESENCE_DELETE_TRIGGER = """
CREATE TRIGGER cr_delete_deployment_presence
AFTER DELETE ON character_deployments
BEGIN
    DELETE FROM deployment_presence WHERE deployment_id = OLD.id;
    DELETE FROM deployment_presence_notices WHERE deployment_id = OLD.id;
    DELETE FROM deployment_presence_rhythms WHERE deployment_id = OLD.id;
    DELETE FROM deployment_activity_session_items WHERE deployment_id = OLD.id;
    DELETE FROM deployment_activity_sessions WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_profiles WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_exposures WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_decisions WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_share_policies WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_shares WHERE deployment_id = OLD.id;
END;
"""

_POSTGRES_DEPLOYMENT_SERVER_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_character_deployment_discord_server
ON character_deployments (owner_id, connection_id, workspace_id, character_card_id)
WHERE platform = 'discord' AND workspace_id <> ''
"""

_POSTGRES_DEPLOYMENT_PRESENCE_DELETE_FUNCTION = """
CREATE OR REPLACE FUNCTION cr_delete_deployment_runtime() RETURNS trigger AS $$
BEGIN
    DELETE FROM deployment_presence WHERE deployment_id = OLD.id;
    DELETE FROM deployment_presence_notices WHERE deployment_id = OLD.id;
    DELETE FROM deployment_presence_rhythms WHERE deployment_id = OLD.id;
    DELETE FROM deployment_activity_session_items WHERE deployment_id = OLD.id;
    DELETE FROM deployment_activity_sessions WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_profiles WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_exposures WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_decisions WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_share_policies WHERE deployment_id = OLD.id;
    DELETE FROM deployment_discovery_shares WHERE deployment_id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql
"""

_POSTGRES_DEPLOYMENT_PRESENCE_DELETE_TRIGGER_DROP = """
DROP TRIGGER IF EXISTS cr_delete_deployment_runtime ON character_deployments
"""

_POSTGRES_DEPLOYMENT_PRESENCE_DELETE_TRIGGER_CREATE = """
CREATE TRIGGER cr_delete_deployment_runtime
AFTER DELETE ON character_deployments
FOR EACH ROW EXECUTE FUNCTION cr_delete_deployment_runtime()
"""


def _enable_sqlite_foreign_keys(
    dbapi_connection: SQLiteConnection, _: ConnectionPoolEntry
) -> None:
    """Enable SQLite foreign-key checks for every newly opened DB-API connection."""

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict[str, object] = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, **kwargs)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(
        self,
        *,
        run_legacy_migrations: bool = True,
        allow_incomplete_data_migration: bool = False,
    ) -> None:
        # Explicitly touch authority/runtime model classes so schema creation is deterministic.
        _ = (
            WikiPageRecord,
            ConversationThreadRecord,
            ConversationSegmentV3Record,
            ThreadMembershipRecord,
            MessageRelationRecord,
            ConversationEpisodeV3Record,
            ThreadWorkingStateRecord,
            PendingActionV3Record,
            EntityV3Record,
            EvidenceEdgeV3Record,
            KnowledgeGapRecord,
            BeliefV3Record,
            BeliefEvidenceDependencyRecord,
            BeliefRevisionEventRecord,
            SocialEventV3Record,
            ImpressionV3Record,
            ServerWikiPageV3Record,
            KnowledgeConsolidationCheckpointV3Record,
            CharacterRelationshipPriorRecord,
            DeploymentRelationshipStateRecord,
            DeploymentRelationshipEventRecord,
            CharacterPersonImpressionRecord,
            CharacterLearnedStateRecord,
            CharacterLearnedStateEventRecord,
            SmartParticipationScopeStateRecord,
            SmartParticipationDeploymentStateRecord,
            UtilityProviderQuotaRecord,
            ConversationEntityRecord,
            ConversationEpisodeEntityRecord,
            CharacterEpisodeAccessRecord,
            DiscordGuildActorIdentityRecord,
            DeploymentPresenceRecord,
            DeploymentPresenceNoticeRecord,
            DeploymentPresenceRhythmRecord,
            DeploymentActivitySessionRecord,
            DeploymentActivitySessionItemRecord,
            DiscoveryItemRecord,
            DiscoverySourceQueryCacheRecord,
            DeploymentDiscoveryProfileRecord,
            DeploymentDiscoveryExposureRecord,
            DeploymentDiscoveryDecisionRecord,
            DeploymentDiscoverySharePolicyRecord,
            DeploymentDiscoveryShareRecord,
            IntelligenceV3HardCutoverMigrationRecord,
            OperationalDataMigrationRecord,
            DatabaseSchemaMigrationRecord,
            DatabaseDataMigrationRecord,
            KnowledgeServerScopeRecord,
            KnowledgeServerAdministratorRecord,
            KnowledgeCorpusRecord,
            KnowledgeSourceRecord,
            KnowledgeSourceCurrentEntryRecord,
            KnowledgeExternalSourceSyncStateRecord,
            KnowledgeExternalSourceScheduleRecord,
            KnowledgeExternalHostRateRecord,
            KnowledgeObjectArtifactRecord,
            KnowledgeSourceVersionRecord,
            KnowledgeCanonicalDocumentRecord,
            KnowledgeCanonicalSectionRecord,
            KnowledgeCanonicalBlockRecord,
            KnowledgeAssetReferenceRecord,
            KnowledgeEvidenceUnitRecord,
            KnowledgeIngestionJobRecord,
            KnowledgeIngestionCheckpointRecord,
            KnowledgeDependencyInvalidationRecord,
            KnowledgeProjectionRecord,
            KnowledgeProjectionDependencyRecord,
            KnowledgeEvidenceRetrievalEntryRecord,
            KnowledgeEvidenceEmbeddingRecord,
            KnowledgeCanonicalEntityRecord,
            KnowledgeRuntimeEntityResolutionRecord,
            KnowledgeExtractedAssertionRecord,
            KnowledgeWorldEventRecord,
            KnowledgeWorldEventParticipantRecord,
            KnowledgeEvidenceGraphRelationRecord,
            KnowledgeInterpretationEvidenceRecord,
            KnowledgeAccessGrantRecord,
            KnowledgeCharacterCorpusPolicyRecord,
            KnowledgeOverlayPolicyRecord,
        )
        Base.metadata.create_all(self.engine)

        # The foundation runner owns PostgreSQL extension/bootstrap revisions.  It
        # deliberately precedes product migrations so later revisions can depend on
        # pgvector without creating Knowledge Fabric semantics during this phase.
        from echo_masque.persistence.schema_migrations import (
            DatabaseFoundationMigration,
            KnowledgeFabricContentMigration,
            KnowledgeFabricCharacterPolicyMigration,
            KnowledgeFabricCurrentEntryMigration,
            KnowledgeFabricExternalScheduleMigration,
            KnowledgeFabricIndexMigration,
            KnowledgeFabricInterpretationMigration,
            KnowledgeFabricProjectionMigration,
            KnowledgeFabricExternalSyncMigration,
            KnowledgeFabricScopeMigration,
        )

        DatabaseFoundationMigration(self).run()
        KnowledgeFabricScopeMigration(self).run()
        KnowledgeFabricContentMigration(self).run()
        KnowledgeFabricCharacterPolicyMigration(self).run()
        KnowledgeFabricCurrentEntryMigration(self).run()
        KnowledgeFabricInterpretationMigration(self).run()
        KnowledgeFabricIndexMigration(self).run()
        KnowledgeFabricProjectionMigration(self).run()
        KnowledgeFabricExternalSyncMigration(self).run()
        KnowledgeFabricExternalScheduleMigration(self).run()

        if not allow_incomplete_data_migration:
            self._assert_no_incomplete_data_migration()

        if not run_legacy_migrations:
            self._ensure_sqlite_deployment_runtime_invariants()
            self._ensure_postgresql_deployment_runtime_invariants()
            self._ensure_sqlite_message_relation_author_snapshots()
            return

        # Existing installations may still contain old Topic/Memory/Episode tables.  The raw
        # hard-cutover migration preserves useful durable evidence into v3 stores, deliberately
        # discards Topic/SemanticThread identity, then removes the old tables.  Because it uses
        # reflection, legacy ORM models do not need to stay registered.
        from echo_masque.persistence.intelligence_v3_migration import (
            IntelligenceV3HardCutoverMigration,
        )

        IntelligenceV3HardCutoverMigration(self).run()

        from echo_masque.persistence.discord_event_privacy_migration import (
            DiscordEventPrivacyMigration,
        )

        DiscordEventPrivacyMigration(self).run()
        self._ensure_sqlite_deployment_runtime_invariants()
        self._ensure_postgresql_deployment_runtime_invariants()
        self._ensure_sqlite_message_relation_author_snapshots()

    def _assert_no_incomplete_data_migration(self) -> None:
        """Fail closed rather than serving a target while its one-time copy is incomplete."""

        with self.session() as session:
            record = session.get(DatabaseDataMigrationRecord, "sqlite-to-postgresql-v1")
        if record is not None and record.status != "completed":
            raise RuntimeError(
                "Database startup is blocked because the SQLite-to-PostgreSQL migration is "
                f"{record.status!r}; finish it or use a fresh target database."
            )

    def _ensure_sqlite_deployment_runtime_invariants(self) -> None:
        if self.engine.dialect.name != "sqlite":
            return
        with self.engine.begin() as connection:
            columns = {
                str(row[1])
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(deployment_activity_sessions)"
                ).all()
            }
            if columns and "planned_duration_minutes" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE deployment_activity_sessions "
                    "ADD COLUMN planned_duration_minutes INTEGER NOT NULL DEFAULT 20"
                )
            connection.exec_driver_sql(_SQLITE_DEPLOYMENT_SERVER_INSERT_TRIGGER)
            connection.exec_driver_sql(_SQLITE_DEPLOYMENT_SERVER_UPDATE_TRIGGER)
            connection.exec_driver_sql("DROP TRIGGER IF EXISTS cr_delete_deployment_presence")
            connection.exec_driver_sql(_SQLITE_DEPLOYMENT_PRESENCE_DELETE_TRIGGER)

    def _ensure_postgresql_deployment_runtime_invariants(self) -> None:
        """Port the deployed SQLite identity and cleanup guarantees to PostgreSQL."""

        if self.engine.dialect.name != "postgresql":
            return
        duplicates = self.inspect_deployment_server_duplicates()
        if duplicates:
            raise RuntimeError(
                "PostgreSQL deployment migration found duplicate Discord server deployments; "
                "repair them explicitly before enabling the server-wide unique constraint."
            )
        with self.engine.begin() as connection:
            connection.exec_driver_sql(_POSTGRES_DEPLOYMENT_SERVER_UNIQUE_INDEX)
            connection.exec_driver_sql(_POSTGRES_DEPLOYMENT_PRESENCE_DELETE_FUNCTION)
            connection.exec_driver_sql(_POSTGRES_DEPLOYMENT_PRESENCE_DELETE_TRIGGER_DROP)
            connection.exec_driver_sql(_POSTGRES_DEPLOYMENT_PRESENCE_DELETE_TRIGGER_CREATE)

    def _ensure_sqlite_message_relation_author_snapshots(self) -> None:
        """Add non-content author snapshots to pre-existing Conversation v3 relation tables."""

        if self.engine.dialect.name != "sqlite":
            return
        required = {
            "source_author_id": "VARCHAR(200) NOT NULL DEFAULT ''",
            "source_author_display_name": "VARCHAR(200) NOT NULL DEFAULT ''",
            "target_author_id": "VARCHAR(200) NOT NULL DEFAULT ''",
            "target_author_display_name": "VARCHAR(200) NOT NULL DEFAULT ''",
        }
        with self.engine.begin() as connection:
            columns = {
                str(row[1])
                for row in connection.exec_driver_sql("PRAGMA table_info(message_relations_v3)").all()
            }
            for name, definition in required.items():
                if columns and name not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE message_relations_v3 ADD COLUMN {name} {definition}"
                    )

    def inspect_deployment_server_duplicates(self) -> tuple[DeploymentServerDuplicate, ...]:
        query = """
        SELECT owner_id, connection_id, workspace_id, character_card_id, COUNT(*)
        FROM character_deployments
        WHERE platform = 'discord' AND workspace_id <> ''
        GROUP BY owner_id, connection_id, workspace_id, character_card_id
        HAVING COUNT(*) > 1
        ORDER BY owner_id, connection_id, workspace_id, character_card_id
        """
        with self.engine.connect() as connection:
            rows = connection.exec_driver_sql(query).all()
        return tuple(
            DeploymentServerDuplicate(
                owner_id=str(row[0]),
                connection_id=str(row[1]),
                workspace_id=str(row[2]),
                character_card_id=str(row[3]),
                deployment_count=int(row[4]),
            )
            for row in rows
        )

    def ensure_storage_instance_id(self) -> str:
        """Return one identity that remains stable for the lifetime of the database."""

        with self.session() as session:
            record = session.get(StorageMetadataRecord, "default")
            now = datetime.now(UTC)
            if record is None:
                record = StorageMetadataRecord(
                    id="default",
                    instance_id=str(uuid4()),
                    created_at=now,
                    last_started_at=now,
                )
                session.add(record)
            else:
                record.last_started_at = now
            session.commit()
            session.refresh(record)
            return record.instance_id

    def session(self) -> Session:
        return self.session_factory()
