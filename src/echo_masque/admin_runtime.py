"""Admin-managed, secret-free Adaptive Tester and Semantic Judge profiles."""

from __future__ import annotations

from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

ProviderId = Literal["deepseek", "openai", "openrouter", "custom"]
JudgeModeValue = Literal["rules", "semantic", "hybrid"]
CredentialSource = Literal["vault", "memory", "environment", "missing"]
RUNTIME_DEFAULTS_VERSION = 3

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
    "You are Character Relay's runtime routing judge. Decide whether the CURRENT Discord turn "
    "needs the supplied Knowledge context. Prefer no Knowledge for greetings, banter, reactions, "
    "media/tool requests, unrelated social conversation, or a topic switch. Use prior topic context "
    "only when the current message genuinely continues or clarifies that knowledge question. Return "
    "only strict JSON: {\"need_knowledge\":boolean,\"confidence\":0..1,\"reason\":string}."
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
    rubric_version: str = Field(default="character-integrity-v1", min_length=1, max_length=120)


class SemanticJudgeEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ProviderId = "openrouter"
    base_url: str = Field(default="https://openrouter.ai/api", min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=240)


class SemanticRoutingJudgeProfile(BaseModel):
    """System-level Judge policy for ambiguous Discord semantic routing decisions."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    rag_enabled: bool = True
    primary: SemanticJudgeEndpoint = Field(
        default_factory=lambda: SemanticJudgeEndpoint(
            model="liquid/lfm-2.5-1.2b-instruct:free"
        )
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
    def validate_thresholds(self) -> "SemanticRoutingJudgeProfile":
        if self.rag_off_threshold >= self.rag_on_threshold:
            raise ValueError("rag_off_threshold must be lower than rag_on_threshold")
        return self


class AdminRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    adaptive: AdaptiveRuntimeProfile = Field(default_factory=AdaptiveRuntimeProfile)
    judge: JudgeRuntimeProfile = Field(default_factory=JudgeRuntimeProfile)
    semantic_routing: SemanticRoutingJudgeProfile = Field(
        default_factory=SemanticRoutingJudgeProfile
    )
    default_judge_mode: JudgeModeValue = "hybrid"
    defaults_version: int = RUNTIME_DEFAULTS_VERSION


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
