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
from echo_masque.persistence.conversation_topic_decision_models import ConversationTopicDecisionRecord
from echo_masque.persistence.core_memory_models import CharacterCoreMemoryRecord
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
        # Keep derived models attached to Base.metadata before create_all().
        # Other persistence models are registered by the package import graph.
        _ = (
            WikiPageRecord,
            ConversationGraphNodeRecord,
            ConversationGraphEdgeRecord,
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
        )
        Base.metadata.create_all(self.engine)
        self._ensure_sqlite_deployment_server_invariant()

    def _ensure_sqlite_deployment_server_invariant(self) -> None:
        """Install non-destructive guards for old SQLite databases.

        Existing duplicate rows are deliberately left untouched. The triggers only reject
        future INSERT/UPDATE operations that would create another incarnation of the same
        Character Card in one Discord guild. Owners can inspect legacy conflicts through
        ``inspect_deployment_server_duplicates`` and repair them explicitly.
        """

        if self.engine.dialect.name != "sqlite":
            return
        with self.engine.begin() as connection:
            connection.exec_driver_sql(_SQLITE_DEPLOYMENT_SERVER_INSERT_TRIGGER)
            connection.exec_driver_sql(_SQLITE_DEPLOYMENT_SERVER_UPDATE_TRIGGER)

    def inspect_deployment_server_duplicates(self) -> tuple[DeploymentServerDuplicate, ...]:
        """Return legacy same-Card/same-Discord-server duplicate groups without mutating them."""

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
