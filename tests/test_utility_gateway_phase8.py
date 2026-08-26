from __future__ import annotations

from types import SimpleNamespace

from echo_masque.admin_runtime import (
    AdminRuntimeConfig,
    UtilityGatewayProfile,
    UtilityProviderMember,
)
from echo_masque.persistence import Database
from echo_masque.utility_gateway_contracts import RagUtilityDecision, UtilityRoute
from echo_masque.utility_gateway_router import UtilityCallReply, UtilityGatewayRouter


class FakeCredential:
    pass


def member(
    member_id: str,
    *,
    capabilities: tuple[str, ...],
    priority: int = 1,
) -> UtilityProviderMember:
    return UtilityProviderMember(
        id=member_id,
        name=member_id,
        provider="openrouter",
        base_url="https://offline.invalid",
        model="offline-model",
        capabilities=capabilities,  # type: ignore[arg-type]
        priority=priority,
    )


class RuntimeStub:
    def __init__(self, gateway: UtilityGatewayProfile) -> None:
        database = Database("sqlite://")
        database.initialize()
        self.repository = SimpleNamespace(database=database)
        self._config = AdminRuntimeConfig(utility_gateway=gateway)

    def config(self) -> AdminRuntimeConfig:
        return self._config


class MalformedThenValidCaller:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def call(
        self,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> UtilityCallReply:
        del system_prompt, user_prompt, max_output_tokens, temperature
        self.calls.append(route.member_id)
        if route.member_id == "first":
            return UtilityCallReply(text="not-json", latency_ms=4)
        return UtilityCallReply(
            text=(
                '{"need_knowledge":true,"confidence":0.87,'
                '"reason_code":"fallback_valid"}'
            ),
            latency_ms=5,
        )


def credentials(_: str) -> FakeCredential:
    return FakeCredential()


def test_malformed_structured_output_falls_through_to_next_free_provider() -> None:
    runtime = RuntimeStub(
        UtilityGatewayProfile(
            enabled=True,
            routing_strategy="fixed_priority",
            members=(
                member("first", capabilities=("semantic_judge",), priority=1),
                member("second", capabilities=("semantic_judge",), priority=2),
            ),
        )
    )
    caller = MalformedThenValidCaller()
    gateway = UtilityGatewayRouter(
        runtime,  # type: ignore[arg-type]
        caller=caller,
        credential_resolver=credentials,  # type: ignore[arg-type]
    )

    decision, result = gateway.invoke(
        "semantic_judge",
        RagUtilityDecision,
        system_prompt="route",
        user_prompt="current turn",
    )

    assert decision.need_knowledge is True
    assert result.route.member_id == "second"
    assert result.attempts == 2
    assert caller.calls == ["first", "second"]
