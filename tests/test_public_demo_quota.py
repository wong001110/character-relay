from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.public_demo import PUBLIC_DEMO_USER_ID
from echo_masque.security_controls import QuotaExceeded


def test_public_demo_daily_run_budget_is_persistent(tmp_path: Path) -> None:
    database_path = tmp_path / "public-demo-quota.db"
    key = Fernet.generate_key().decode("ascii")
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{database_path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email="admin@example.com",
        bootstrap_admin_password=SecretStr("AdminPassword2026!"),
        credential_encryption_keys=SecretStr(key),
        public_demo_enabled=True,
        public_demo_max_runs_per_day=1,
    )

    first = create_app(settings)
    first.state.quota_service.enforce_run_start(PUBLIC_DEMO_USER_ID)

    restarted = create_app(settings)
    with pytest.raises(QuotaExceeded, match="daily Run quota"):
        restarted.state.quota_service.enforce_run_start(PUBLIC_DEMO_USER_ID)
