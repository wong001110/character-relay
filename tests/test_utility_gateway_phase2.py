from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from echo_masque.utility_gateway_runtime import (
    RagUtilityDecision,
    UtilityGatewayService,
    UtilityGatewayUnavailable,
)
from pydantic import SecretStr

from echo_masque.admin_runtime import (
    UtilityGatewayProfile,
    UtilityPaidFallback,
    UtilityProviderMember,
)
from echo_masque.api import create_app
from echo_masque.auth import SYSTEM_RUNTIME_USER_ID
from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        public_registration_enabled=False,
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def member(member_id: str, provider: str, priority: int) -> UtilityProviderMember:
    return UtilityProviderMember(
        id=member_id,
        name=member_id,
        provider=provider,  # type: ignore[arg-type]
        base_url=f"https://{member_id}.example.test",
        model="free-model",
        capabilities=("semantic_judge",),
        free_only=True,
        priority=priority,
    )


def configure_key(app: object, member_id: str) -> None:
    runtime = app.state.runtime_service  # type: ignore[attr-defined]
    runtime.credential_vault.set_scope(
        owner_id=SYSTEM_RUNTIME_USER_ID,
        scope_kind=CredentialVault.runtime_scope_kind,
        scope_id=f"utility:{member_id}",
        value=SecretStr(f"key-{member_id}"),
        actor_user_id=SYSTEM_RUNTIME_USER_ID,
        resource_type="utility_gateway",
    )


def test_free_pool_skips_exhausted_member_and_updates_health(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "gateway.db"))
    runtime = app.state.runtime_service
    first = member("groq_free", "groq", 1)
    second = member("cerebras_free", "cerebras", 2)
    runtime.save(
        runtime.config().model_copy(
            update={
                "utility_gateway": UtilityGatewayProfile(
                    enabled=True,
                    routing_strategy="fixed_priority",
                    members=(first, second),
                )
            }
        )
    )
    configure_key(app, first.id)
    configure_key(app, second.id)

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        if request.url.host == "groq_free.example.test":
            return httpx.Response(
                429,
                headers={"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset": "60"},
                json={"error": "rate limited"},
            )
        return httpx.Response(
            200,
            headers={"x-ratelimit-remaining-requests": "99"},
            json={
                "choices": [
                    {"message": {"content": '{"need_knowledge":true,"confidence":0.9,"reason_code":"relevant"}'}}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    gateway = UtilityGatewayService(runtime, http_transport=httpx.MockTransport(handler))
    decision, result = gateway.invoke(
        "semantic_judge",
        RagUtilityDecision,
        system_prompt="route",
        user_prompt="current turn",
    )

    assert decision.need_knowledge is True
    assert result.route.member_id == second.id
    assert result.attempts == 2
    assert calls == ["groq_free.example.test", "cerebras_free.example.test"]
    snapshot = {item.member_id: item for item in gateway.snapshot().members}
    assert snapshot[first.id].status in {"exhausted", "cooling_down"}
    assert snapshot[second.id].status == "healthy"


def test_paid_fallback_requires_explicit_enable_and_budget(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "paid.db"))
    runtime = app.state.runtime_service
    openrouter = member("openrouter_free", "openrouter", 1)
    runtime.save(
        runtime.config().model_copy(
            update={
                "utility_gateway": UtilityGatewayProfile(
                    enabled=True,
                    routing_strategy="fixed_priority",
                    members=(openrouter,),
                    paid_fallback=UtilityPaidFallback(enabled=False),
                )
            }
        )
    )
    configure_key(app, openrouter.id)

    def always_limited(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "limit"})

    gateway = UtilityGatewayService(runtime, http_transport=httpx.MockTransport(always_limited))
    try:
        gateway.rag_decision(prompt="needs routing")
    except UtilityGatewayUnavailable:
        pass
    else:
        raise AssertionError("disabled paid fallback must not activate")

    runtime.save(
        runtime.config().model_copy(
            update={
                "utility_gateway": UtilityGatewayProfile(
                    enabled=True,
                    routing_strategy="fixed_priority",
                    members=(openrouter,),
                    paid_fallback=UtilityPaidFallback(
                        enabled=True,
                        model="paid-model",
                        daily_budget_usd=0.001,
                        monthly_budget_usd=0.001,
                    ),
                )
            }
        )
    )
    try:
        gateway.invoke(
            "semantic_judge",
            RagUtilityDecision,
            system_prompt="route",
            user_prompt="message",
            estimated_cost_usd=0.01,
        )
    except UtilityGatewayUnavailable:
        pass
    else:
        raise AssertionError("paid fallback must remain blocked when the estimate exceeds budget")
