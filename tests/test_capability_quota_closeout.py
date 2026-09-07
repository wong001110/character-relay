import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update

from echo_masque.config import Settings
from echo_masque.persistence.database import Database
from echo_masque.persistence.security_models import RateLimitBucketRecord
from echo_masque.persistence.utility_gateway_models import UtilityProviderCapabilityRecord
from echo_masque.provider_capabilities import CapabilityObservation
from echo_masque.provider_capabilities import ProviderModelCapabilityRegistry as Registry
from echo_masque.provider_capability_persistence import ProviderCapabilityPersistence
from echo_masque.quota_admission import owner_quota_admission
from echo_masque.security_controls import QuotaExceeded, QuotaService
from tests.test_database_foundation import _destructive_postgres_test_url


@pytest.mark.parametrize("seconds,current", [(899, True), (900, False), (901, False)])
def test_negative_capability_boundary(seconds: int, current: bool) -> None:
    observed = datetime(2026, 1, 1, tzinfo=UTC)
    observation = CapabilityObservation(
        provider="test",
        model="model",
        endpoint_key="key",
        capability="native_tool_calling",
        status="unsupported",
        source="runtime",
        observed_at=observed,
    )
    assert observation.current(now=observed + timedelta(seconds=seconds)) is current


def test_supported_capability_does_not_disable_itself_with_age() -> None:
    observed = datetime(2026, 1, 1, tzinfo=UTC)
    observation = CapabilityObservation(
        provider="test",
        model="model",
        endpoint_key="key",
        capability="native_tool_calling",
        status="supported",
        source="runtime",
        observed_at=observed,
    )
    assert observation.current(now=observed + timedelta(days=5))


def test_capability_identity_preserves_port_scheme_and_path_case() -> None:
    urls = [
        "https://example.com:8443/TenantA/v1",
        "https://example.com:9443/TenantA/v1",
        "https://example.com:8443/tenanta/v1",
        "http://example.com:8443/TenantA/v1",
    ]
    assert len({Registry.endpoint_key(url) for url in urls}) == len(urls)
    assert Registry.endpoint_key("https://EXAMPLE.com:443/v1/") == Registry.endpoint_key(
        "https://example.com/v1"
    )
    assert "secret" not in Registry.endpoint_key("https://user:secret@example.com/v1?token=secret")


def test_negative_capability_expires_across_restart_and_reobserves(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'capabilities.db'}")
    database.initialize()
    Registry.configure_persistence(ProviderCapabilityPersistence(database))
    args = dict(
        provider="test",
        model="model",
        base_url="https://example.com/v1",
        capability="native_tool_calling",
    )
    try:
        Registry.observe(**args, supported=False)
        assert Registry.status(**args) == "unsupported"
        with database.session() as session:
            session.execute(
                update(UtilityProviderCapabilityRecord).values(
                    updated_at=datetime.now(UTC) - timedelta(minutes=16)
                )
            )
            session.commit()
        Registry.configure_persistence(ProviderCapabilityPersistence(database))
        assert Registry.status(**args) == "unknown"
        Registry.observe(**args, supported=True)
        assert Registry.status(**args) == "supported"
    finally:
        Registry.reset_for_test()


def test_concurrent_quota_consumption_cannot_lose_admissions(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'quota.db'}")
    database.initialize()
    settings = Settings(environment="test", request_limit_per_minute=7)

    def consume(_index: int) -> bool:
        try:
            QuotaService(database, settings).consume_request("owner-1")
        except QuotaExceeded:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume, range(30))) == 7
    with database.session() as session:
        record = session.get(RateLimitBucketRecord, "request:owner-1")
        assert record is not None and record.count == 7
        record.window_started_at = datetime.now(UTC) - timedelta(minutes=2)
        session.commit()
    assert consume(31)
    with pytest.raises(QuotaExceeded):
        QuotaService(database, settings)._consume(
            key="oversize", limit=2, amount=3, window_seconds=60, message="full"
        )


def test_owner_admission_serializes_writes_and_releases_cancelled_waiter(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'admission.db'}")
    database.initialize()

    async def exercise() -> None:
        entered = asyncio.Event()

        async def contender() -> None:
            async with owner_quota_admission(database, "alice"):
                entered.set()

        async with owner_quota_admission(database, "alice"):
            waiter = asyncio.create_task(contender())
            async with owner_quota_admission(database, "bob"):
                assert not entered.is_set()
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        await asyncio.wait_for(contender(), timeout=1)
        assert entered.is_set()

    asyncio.run(exercise())


def test_naive_negative_observation_uses_utc_expiry() -> None:
    observation = CapabilityObservation(
        provider="test",
        model="model",
        endpoint_key="key",
        capability="native_tool_calling",
        status="unsupported",
        source="runtime",
        observed_at=datetime(2026, 1, 1),
    )
    assert observation.current(now=datetime(2026, 1, 1, 0, 14, 59, tzinfo=UTC))
    assert not observation.current(now=datetime(2026, 1, 1, 0, 15, 0, tzinfo=UTC))


def test_postgresql_quota_and_owner_admission_on_disposable_database() -> None:
    database = Database(_destructive_postgres_test_url())
    database.initialize()
    owner = f"closeout-{uuid4()}"
    settings = Settings(environment="test", request_limit_per_minute=7)

    def consume(_index: int) -> bool:
        try:
            QuotaService(database, settings).consume_request(owner)
        except QuotaExceeded:
            return False
        return True

    async def contend() -> None:
        active = 0
        maximum = 0
        completed = 0

        async def write() -> None:
            nonlocal active, maximum, completed
            async with owner_quota_admission(database, owner):
                active += 1
                maximum = max(maximum, active)
                # A different account remains admissible while this account is locked.
                async with owner_quota_admission(database, f"{owner}-other"):
                    await asyncio.sleep(0.01)
                active -= 1
                completed += 1

        await asyncio.wait_for(asyncio.gather(*(write() for _ in range(8))), timeout=10)
        assert maximum == 1
        assert completed == 8

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert sum(pool.map(consume, range(30))) == 7
        with database.session() as session:
            record = session.get(RateLimitBucketRecord, f"request:{owner}")
            assert record is not None and record.count == 7
        asyncio.run(contend())
    finally:
        with database.session() as session:
            record = session.get(RateLimitBucketRecord, f"request:{owner}")
            if record is not None:
                session.delete(record)
                session.commit()
        database.engine.dispose()


def test_login_failure_updates_are_atomic_and_reset_expired_block(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'login.db'}")
    database.initialize()
    quota = QuotaService(database, Settings(environment="test", login_failure_limit=5))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: quota.record_login_failure("identity"), range(20)))
    with pytest.raises(QuotaExceeded):
        quota.check_login("identity")
    with database.session() as session:
        record = session.get(RateLimitBucketRecord, "login:identity")
        assert record is not None and record.count == 20
        record.blocked_until = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    quota.check_login("identity")
    quota.record_login_failure("identity")
    with database.session() as session:
        record = session.get(RateLimitBucketRecord, "login:identity")
        assert record is not None and record.count == 1 and record.blocked_until is None
