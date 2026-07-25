"""Database engine and repeatable schema initialization."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from echo_masque.persistence.models import Base


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

    def session(self) -> Session:
        return self.session_factory()
