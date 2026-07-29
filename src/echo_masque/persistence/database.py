"""Database engine, schema initialization, and persistent storage identity."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from echo_masque.persistence.models import Base, StorageMetadataRecord


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
