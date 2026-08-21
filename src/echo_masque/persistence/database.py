"""Database engine, schema initialization, and persistent storage identity."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from echo_masque.persistence.character_learned_state_event_models import (
    CharacterLearnedStateEventRecord,
)
from echo_masque.persistence.character_learned_state_models import CharacterLearnedStateRecord
from echo_masque.persistence.conversation_graph_models import (
    ConversationGraphEdgeRecord,
    ConversationGraphNodeRecord,
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
from echo_masque.persistence.conversation_topic_decision_models import ConversationTopicDecisionRecord
from echo_masque.persistence.core_memory_models import CharacterCoreMemoryRecord
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
from echo_masque.persistence.episodic_sql_rag_models import (
    CharacterEpisodeAccessRecord,
    ConversationEntityRecord,
    ConversationEpisodeEntityRecord,
)
from echo_masque.persistence.memory_layer_models import (
    CharacterCoreMemoryRevisionRecord,
    CharacterMemorySummaryRecord,
    SynthesizedMemoryFreshnessRecord,
)
from echo_masque.persistence.memory_vnext_models import (
    ConversationMemoryVNextRecord,
    MemoryVNextStateRecord,
)
from echo_masque.persistence.models import Base, StorageMetadataRecord
from echo_masque.persistence.smart_participation_state_models import (
    SmartParticipationDeploymentStateRecord,
    SmartParticipationScopeStateRecord,
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


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict[str, object] = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, **kwargs)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        _ = (
            WikiPageRecord,
            ConversationGraphNodeRecord,
            ConversationGraphEdgeRecord,
            ConversationThreadRecord,
            ConversationSegmentV3Record,
            ThreadMembershipRecord,
            MessageRelationRecord,
            ConversationEpisodeV3Record,
            ThreadWorkingStateRecord,
            PendingActionV3Record,
            CharacterLearnedStateRecord,
            CharacterLearnedStateEventRecord,
            SmartParticipationScopeStateRecord,
            SmartParticipationDeploymentStateRecord,
            UtilityProviderQuotaRecord,
            ConversationMemoryVNextRecord,
            MemoryVNextStateRecord,
            ConversationTopicDecisionRecord,
            ConversationEntityRecord,
            ConversationEpisodeEntityRecord,
            CharacterEpisodeAccessRecord,
            CharacterCoreMemoryRecord,
            CharacterCoreMemoryRevisionRecord,
            SynthesizedMemoryFreshnessRecord,
            CharacterMemorySummaryRecord,
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
        )
        Base.metadata.create_all(self.engine)
        self._ensure_sqlite_deployment_runtime_invariants()

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

    def inspect_deployment_server_duplicates(self) -> tuple[DeploymentServerDuplicate, ...]:
        if self.engine.dialect.name != "sqlite":
            return ()
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
