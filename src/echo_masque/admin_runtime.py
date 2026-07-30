"""Admin-managed, secret-free Adaptive Tester and Semantic Judge profiles."""

from __future__ import annotations

from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

ProviderId = Literal["deepseek", "openai", "openrouter", "custom"]
JudgeModeValue = Literal["rules", "semantic", "hybrid"]
CredentialSource = Literal["vault", "memory", "environment", "missing"]

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


class AdaptiveRuntimeProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    provider: ProviderId = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    system_prompt: str = DEFAULT_ADAPTIVE_PROMPT
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    max_turns: int = Field(default=4, ge=2, le=8)


class JudgeRuntimeProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    provider: ProviderId = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    system_prompt: str = DEFAULT_JUDGE_PROMPT
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    rubric_version: str = Field(default="character-integrity-v1", min_length=1, max_length=120)


class AdminRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    adaptive: AdaptiveRuntimeProfile = Field(default_factory=AdaptiveRuntimeProfile)
    judge: JudgeRuntimeProfile = Field(default_factory=JudgeRuntimeProfile)
    default_judge_mode: JudgeModeValue = "rules"


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
    default_judge_mode: JudgeModeValue


class RuntimeCredentialStore:
    """Deprecated non-production compatibility store."""

    def __init__(self) -> None:
        self._values: dict[str, SecretStr] = {}
        self._lock = RLock()

    def set(self, kind: Literal["adaptive", "judge"], value: SecretStr) -> None:
        with self._lock:
            self._values[kind] = value

    def get(self, kind: Literal["adaptive", "judge"]) -> SecretStr | None:
        with self._lock:
            return self._values.get(kind)

    def delete(self, kind: Literal["adaptive", "judge"]) -> None:
        with self._lock:
            self._values.pop(kind, None)
