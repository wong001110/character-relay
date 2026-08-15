from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import SecretStr

from echo_masque.admin_runtime import (
    ConversationBurstRuntimeProfile,
    UtilityGatewayProfile,
    UtilityProviderMember,
)
from echo_masque.api import create_app
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault
from echo_masque.persistence.utility_gateway_models import UtilityProviderStateRecord
from echo_masque.utility_gateway_router import UtilityGatewayRouter


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=False,
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def test_conversation_burst_runtime_defaults_and_bounds() -> None:
    profile = ConversationBurstRuntimeProfile()
    assert profile.quiet_window_ms == 3_000
    assert profile.max_wait_ms == 10_000
    assert profile.max_messages == 5
    assert profile.max_characters == 1_500


def test_expired_cooling_down_member_becomes_probe_eligible(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "utility.db"))
    runtime = app.state.runtime_service
    member = UtilityProviderMember(
        id="free_provider",
        name="Free Provider",
        provider="groq",
        base_url="https://example.test",
        model="free-model",
        capabilities=("semantic_judge",),
        free_only=True,
        priority=1,
    )
    runtime.save(
        runtime.config().model_copy(
            update={
                "utility_gateway": UtilityGatewayProfile(
                    enabled=True,
                    routing_strategy="fixed_priority",
                    members=(member,),
                )
            }
        )
    )
    runtime.credential_vault.set_scope(
        owner_id=SYSTEM_RUNTIME_USER_ID,
        scope_kind=CredentialVault.runtime_scope_kind,
        scope_id="utility:free_provider",
        value=SecretStr("test-key"),
        actor_user_id=SYSTEM_RUNTIME_USER_ID,
        resource_type="utility_gateway",
    )
    with runtime.repository.database.session() as session:
        session.add(
            UtilityProviderStateRecord(
                member_id=member.id,
                provider=member.provider,
                model=member.model,
                status="cooling_down",
                cooldown_until=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        session.commit()

    router = UtilityGatewayRouter(runtime)
    assert router.snapshot().members[0].status == "unknown"
    assert [item.id for item in router._members("semantic_judge")] == [member.id]
