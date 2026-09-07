"""Cross-process owner admission held across API quota checks and resource writes."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from echo_masque.persistence.database import Database
from echo_masque.security_controls import QuotaExceeded


def _try_file_lock(handle: BinaryIO) -> bool:
    try:
        if os.name == "nt":
            import importlib

            windows_lock = importlib.import_module("msvcrt")
            handle.seek(0)
            windows_lock.locking(handle.fileno(), windows_lock.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _acquire(database: Database, owner_id: str, cancelled: threading.Event) -> Callable[[], None]:
    # A separate PostgreSQL connection holds a transaction advisory lock while repositories
    # use their own transactions. SQLite uses an OS lock, never a competing write transaction.
    owner_key = hashlib.sha256(f"quota-admission-v1:{owner_id}".encode()).digest()
    until = time.monotonic() + 5
    if database.engine.dialect.name == "postgresql":
        lock_engine = create_engine(
            database.engine.url, poolclass=NullPool, connect_args={"connect_timeout": 5}
        )
        connection = lock_engine.connect()
        key = int.from_bytes(owner_key[:8], "big", signed=True)
        try:
            while not cancelled.is_set() and time.monotonic() < until:
                if connection.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}):

                    def release() -> None:
                        try:
                            connection.rollback()
                        finally:
                            connection.close()
                            lock_engine.dispose()

                    return release
                cancelled.wait(0.025)
        except BaseException:
            connection.close()
            lock_engine.dispose()
            raise
        connection.close()
        lock_engine.dispose()
    elif database.engine.dialect.name == "sqlite":
        database_name = database.engine.url.database or ":memory:"
        if database_name != ":memory:":
            database_name = str(Path(database_name).resolve())
        identity = hashlib.sha256(database_name.encode() + owner_key).hexdigest()
        directory = Path(tempfile.gettempdir()) / "character-relay-admission"
        directory.mkdir(mode=0o700, exist_ok=True)
        handle = (directory / identity).open("a+b")
        try:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            while not cancelled.is_set() and time.monotonic() < until:
                if _try_file_lock(handle):
                    return handle.close
                cancelled.wait(0.025)
        except BaseException:
            handle.close()
            raise
        handle.close()
    else:
        raise RuntimeError("Unsupported database for owner quota admission")
    raise QuotaExceeded(
        "Another account operation is still running. Try again shortly.", retry_after=1
    )


@asynccontextmanager
async def owner_quota_admission(database: Database, owner_id: str) -> AsyncIterator[None]:
    cancelled = threading.Event()
    acquiring = asyncio.create_task(asyncio.to_thread(_acquire, database, owner_id, cancelled))
    try:
        release = await asyncio.shield(acquiring)
    except asyncio.CancelledError:
        cancelled.set()
        try:
            release = await acquiring
        except QuotaExceeded:
            pass
        else:
            await asyncio.to_thread(release)
        raise
    try:
        yield
    finally:
        await asyncio.shield(asyncio.to_thread(release))


__all__ = ["owner_quota_admission"]
