"""Database engine, schema initialization, and persistent storage identity."""

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
        )
        Base.metadata.create_all(self.engine)

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
