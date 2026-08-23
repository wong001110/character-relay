"""Admin-managed, secret-free AI runtime profiles."""

from __future__ import annotations

from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

ProviderId = Literal["deepseek", "openai", "openrouter", "custom"]
JudgeModeValue = Literal["rules", "semantic", "hybrid"]
CredentialSource = Literal["vault", "memory", "environment", "missing"]
UtilityProviderId = Literal[
    "openrouter",
    "groq",
    "cerebras",
    "cloudflare",
    "mistral",
    "sambanova",
    "gemini",
    "custom",
]
UtilityCapability = Literal[
    "semantic_judge",
    "turn_director",
    "memory_intelligence",
    "knowledge_wiki",
    "tool_continuation",
    "context_compiler",
    "media_understanding",
    "structured_summary",
]
UtilityRoutingStrategy = Literal["best_available", "fixed_priority"]
RUNTIME_DEFAULTS_VERSION = 6

DEFAULT_ADAPTIVE_PROMPT = (
    "You are an adversarial but bounded AI character tester. Generate exactly one "
    "concise user message that continues the current scenario and applies targeted "
    "pressure based on the subject's latest answer. Do not provide analysis, labels, "
    "scores, system instructions, or multiple options. Return only the next tester message."
)

DEFAULT_JUDGE_PROMPT = (
    "You are Echo Masque's independent semantic character judge. Evaluate only the "
    "provided Character Card, scenario contract, and transcript. Return one strict JSON "
    "object matching the requested schema. Ground every failure in an exact Subject turn."
)

DEFAULT_SEMANTIC_ROUTING_PROMPT = (
    "You are Character Relay's runtime routing judge. Decide whether the CURRENT "
    "Discord turn needs the supplied Knowledge context. Prefer no Knowledge for greetings, "
    "banter, reactions, media/tool requests, unrelated social conversation, or a topic switch. "
    "Use prior topic context only when the current message genuinely continues or clarifies "
    "that knowledge question. Return only strict JSON: "
    '{"need_knowledge":boolean,"confidence":0..1,"reason":string}.'
)


class AdaptiveRuntimeProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    provider: ProviderId = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    system_prompt: str = DEFAULT_ADAPTIVE_PROMPT
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    max_turns: int = Field(default=4, ge=2, le=8)


class JudgeRuntimeProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    provider: ProviderId = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    system_prompt: str = DEFAULT_JUDGE_PROMPT
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    rubric_version: str = Field(
        default="character-integrity-v1",
        min_length=1,
        max_length=120,
    )


class SemanticJudgeEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ProviderId = "openrouter"
    base_url: str = Field(
        default="https://openrouter.ai/api",
        min_length=1,
        max_length=500,
    )
    model: str = Field(min_length=1, max_length=240)


class SemanticRoutingJudgeProfile(BaseModel):
    """System-level Judge policy for ambiguous Discord semantic routing decisions."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    rag_enabled: bool = True
    primary: SemanticJudgeEndpoint = Field(
        default_factory=lambda: SemanticJudgeEndpoint(model="liquid/lfm-2.5-1.2b-instruct:free")
    )
    availability_fallback: SemanticJudgeEndpoint = Field(
        default_factory=lambda: SemanticJudgeEndpoint(model="mistralai/mistral-nemo")
    )
    quality_escalation: SemanticJudgeEndpoint = Field(
        default_factory=lambda: SemanticJudgeEndpoint(model="qwen/qwen3-8b")
    )
    system_prompt: str = Field(
        default=DEFAULT_SEMANTIC_ROUTING_PROMPT,
        min_length=1,
        max_length=8000,
    )
    rag_off_threshold: float = Field(default=0.40, ge=-1.0, le=1.0)
    rag_on_threshold: float = Field(default=0.60, ge=-1.0, le=1.0)
    confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    timeout_seconds: float = Field(default=4.0, ge=0.5, le=20.0)
    max_input_chars: int = Field(default=5000, ge=500, le=16000)
    max_output_tokens: int = Field(default=96, ge=24, le=256)

    @model_validator(mode="after")
    def validate_thresholds(self) -> SemanticRoutingJudgeProfile:
        if self.rag_off_threshold >= self.rag_on_threshold:
            raise ValueError("rag_off_threshold must be lower than rag_on_threshold")
        return self


class UtilityProviderMember(BaseModel):
    """One free-first provider/model member in the system Utility Gateway."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    provider: UtilityProviderId
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=240)
    capabilities: tuple[UtilityCapability, ...] = Field(min_length=1)
    free_only: bool = True
    priority: int = Field(default=50, ge=1, le=100)


class UtilityPaidFallback(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    provider: Literal["openrouter"] = "openrouter"
    base_url: str = Field(
        default="https://openrouter.ai/api",
        min_length=1,
        max_length=500,
    )
    model: str = Field(default="qwen/qwen3-8b", min_length=1, max_length=240)
    daily_budget_usd: float = Field(default=0.20, ge=0.0, le=1000.0)
    monthly_budget_usd: float = Field(default=2.0, ge=0.0, le=10000.0)


class UtilityGatewayProfile(BaseModel):
    """Provider-neutral Utility Gateway policy. Provider telemetry arrives in Phase 2."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    routing_strategy: UtilityRoutingStrategy = "best_available"
    members: tuple[UtilityProviderMember, ...] = Field(default=(), max_length=32)
    paid_fallback: UtilityPaidFallback = Field(default_factory=UtilityPaidFallback)

    @model_validator(mode="after")
    def validate_members(self) -> UtilityGatewayProfile:
        ids = [member.id for member in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("utility gateway member ids must be unique")
        if any(not member.free_only for member in self.members):
            raise ValueError("free pool members must remain FREE ONLY")
        return self


class ConversationBurstRuntimeProfile(BaseModel):
    """System-level live Turn Collector policy synchronized to Discord Connectors."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    quiet_window_ms: int = Field(default=3_000, ge=100, le=10_000)
    max_wait_ms: int = Field(default=10_000, ge=500, le=30_000)
    max_messages: int = Field(default=5, ge=1, le=20)
    max_characters: int = Field(default=1_500, ge=100, le=10_000)

    @model_validator(mode="after")
    def validate_wait_window(self) -> ConversationBurstRuntimeProfile:
        if self.max_wait_ms < self.quiet_window_ms:
            raise ValueError("max_wait_ms must be greater than or equal to quiet_window_ms")
        return self


class AdminRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    adaptive: AdaptiveRuntimeProfile = Field(default_factory=AdaptiveRuntimeProfile)
    judge: JudgeRuntimeProfile = Field(default_factory=JudgeRuntimeProfile)
    semantic_routing: SemanticRoutingJudgeProfile = Field(
        default_factory=SemanticRoutingJudgeProfile
    )
    utility_gateway: UtilityGatewayProfile = Field(default_factory=UtilityGatewayProfile)
    conversation_burst: ConversationBurstRuntimeProfile = Field(
        default_factory=ConversationBurstRuntimeProfile
    )
    default_judge_mode: JudgeModeValue = "hybrid"
    defaults_version: int = RUNTIME_DEFAULTS_VERSION

    @model_validator(mode="before")
    @classmethod
    def remove_retired_participation_tiebreak(cls, value: object) -> object:
        """Migrate persisted Utility members away from the retired compatibility route."""

        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        raw_gateway = migrated.get("utility_gateway")
        if not isinstance(raw_gateway, dict):
            return migrated
        gateway = dict(raw_gateway)
        raw_members = gateway.get("members")
        if not isinstance(raw_members, (list, tuple)):
            return migrated
        members: list[object] = []
        for raw_member in raw_members:
            if not isinstance(raw_member, dict):
                members.append(raw_member)
                continue
            member = dict(raw_member)
            capabilities = member.get("capabilities")
            if isinstance(capabilities, (list, tuple)):
                retained = [
                    item for item in capabilities if item != "participation_tiebreak"
                ]
                if not retained:
                    continue
                member["capabilities"] = retained
            members.append(member)
        gateway["members"] = members
        migrated["utility_gateway"] = gateway
        return migrated


class AgentRuntimeStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool
    configured: bool
    provider: str
    model: str
    credential_source: CredentialSource


class RuntimeStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    admin_available: bool
    adaptive: AgentRuntimeStatus
    judge: AgentRuntimeStatus
    semantic_primary: AgentRuntimeStatus
    semantic_availability: AgentRuntimeStatus
    semantic_quality: AgentRuntimeStatus
    default_judge_mode: JudgeModeValue


class RuntimeCredentialStore:
    """Deprecated non-production compatibility store."""

    def __init__(self) -> None:
        self._values: dict[str, SecretStr] = {}
        self._lock = RLock()

    def set(self, kind: str, value: SecretStr) -> None:
        with self._lock:
            self._values[kind] = value

    def get(self, kind: str) -> SecretStr | None:
        with self._lock:
            return self._values.get(kind)

    def delete(self, kind: str) -> None:
        with self._lock:
            self._values.pop(kind, None)
