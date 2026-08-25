from types import SimpleNamespace

from echo_masque.admin_runtime import (
    AdminRuntimeConfig,
    UtilityGatewayProfile,
    UtilityPaidFallback,
    UtilityProviderMember,
)
from echo_masque.persistence import Database
from echo_masque.utility_gateway_contracts import (
    RagUtilityDecision,
    TurnDirectorProposal,
    UtilityGatewayUnavailable,
    UtilityRoute,
)
from echo_masque.utility_gateway_router import (
    UtilityCallFailed,
    UtilityCallReply,
    UtilityGatewayRouter,
)


class FakeCredential:
    pass


def provider(
    member_id: str,
    provider_id: str,
    priority: int,
    *,
    capabilities: tuple[str, ...] = ("semantic_judge",),
) -> UtilityProviderMember:
    return UtilityProviderMember(
        id=member_id,
        name=member_id,
        provider=provider_id,  # type: ignore[arg-type]
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


class Caller:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

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
        self.calls.append((route.member_id, route.tier))
        if route.member_id == "first" and route.tier == "free":
            raise UtilityCallFailed("quota", remaining_value=0)
        return UtilityCallReply(
            text=(
                '{"need_knowledge":true,"confidence":0.91,'
                '"reason_code":"needed"}'
            ),
            latency_ms=10,
        )


def credentials(_: str):
    return FakeCredential()


def test_free_pool_falls_through_after_exhaustion() -> None:
    runtime = RuntimeStub(
        UtilityGatewayProfile(
            enabled=True,
            routing_strategy="fixed_priority",
            members=(
                provider("first", "groq", 1),
                provider("second", "cerebras", 2),
            ),
        )
    )
    caller = Caller()
    gateway = UtilityGatewayRouter(
        runtime,  # type: ignore[arg-type]
        caller=caller,  # type: ignore[arg-type]
        credential_resolver=credentials,  # type: ignore[arg-type]
    )
    decision, result = gateway.invoke(
        "semantic_judge",
        RagUtilityDecision,
        system_prompt="route",
        user_prompt="message",
    )
    assert decision.need_knowledge is True
    assert result.route.member_id == "second"
    assert caller.calls == [("first", "free"), ("second", "free")]


def test_paid_fallback_requires_enable_and_respects_call_cap() -> None:
    first = provider("first", "openrouter", 1)
    runtime = RuntimeStub(
        UtilityGatewayProfile(
            enabled=True,
            members=(first,),
            paid_fallback=UtilityPaidFallback(
                enabled=True,
                model="paid-model",
                daily_budget_usd=0.02,
                monthly_budget_usd=0.20,
            ),
        )
    )
    caller = Caller()
    gateway = UtilityGatewayRouter(
        runtime,  # type: ignore[arg-type]
        caller=caller,  # type: ignore[arg-type]
        credential_resolver=credentials,  # type: ignore[arg-type]
    )
    decision, result = gateway.invoke(
        "semantic_judge",
        RagUtilityDecision,
        system_prompt="route",
        user_prompt="message",
        estimated_cost_usd=0.002,
    )
    assert decision.need_knowledge is True
    assert result.route.tier == "paid"

    try:
        gateway.invoke(
            "semantic_judge",
            RagUtilityDecision,
            system_prompt="route",
            user_prompt="message",
            estimated_cost_usd=0.10,
        )
    except UtilityGatewayUnavailable:
        pass
    else:
        raise AssertionError("oversized paid fallback was not blocked")


class DirectorCaller:
    def call(
        self,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> UtilityCallReply:
        del route, system_prompt, user_prompt, max_output_tokens, temperature
        return UtilityCallReply(
            text=(
                '{"response_mode":"answer","response_posture":"informed_response",'
                '"focus_message_ids":["message-1"],"read_requests":['
                '{"tool_id":"knowledge.search","query":"release date","limit":2}'
                '],"confidence":0.9,"reason_code":"knowledge_gap"}'
            ),
            latency_ms=8,
        )


def test_turn_director_requires_its_own_capability() -> None:
    runtime = RuntimeStub(
        UtilityGatewayProfile(
            enabled=True,
            members=(provider("judge", "groq", 1),),
        )
    )
    gateway = UtilityGatewayRouter(
        runtime,  # type: ignore[arg-type]
        caller=DirectorCaller(),
        credential_resolver=credentials,  # type: ignore[arg-type]
    )

    try:
        gateway.turn_director_decision(prompt="current turn")
    except UtilityGatewayUnavailable as exc:
        assert str(exc) == "no_eligible_provider"
    else:
        raise AssertionError("semantic judge capability was reused as turn director")


def test_turn_director_returns_a_strict_advisory_contract() -> None:
    runtime = RuntimeStub(
        UtilityGatewayProfile(
            enabled=True,
            members=(
                provider(
                    "director",
                    "groq",
                    1,
                    capabilities=("turn_director",),
                ),
            ),
        )
    )
    gateway = UtilityGatewayRouter(
        runtime,  # type: ignore[arg-type]
        caller=DirectorCaller(),
        credential_resolver=credentials,  # type: ignore[arg-type]
    )

    proposal, result = gateway.turn_director_decision(prompt="current turn")

    assert isinstance(proposal, TurnDirectorProposal)
    assert proposal.focus_message_ids == ("message-1",)
    assert proposal.read_requests[0].tool_id == "knowledge.search"
    assert result.route.member_id == "director"
