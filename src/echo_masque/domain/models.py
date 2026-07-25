"""Provider-independent domain models."""

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


class TargetType(StrEnum):
    DETERMINISTIC = "deterministic"
    PROMPT_MODEL = "prompt_model"
    HTTP_API = "http_api"
    TRANSCRIPT = "transcript"


class TrialStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TestKind(StrEnum):
    IDENTITY_INTEGRITY = "identity_integrity"
    FALSE_MEMORY = "false_memory"
    PROMPT_INJECTION = "prompt_injection"
    LONG_CONVERSATION_DRIFT = "long_conversation_drift"


class MessageRole(StrEnum):
    TESTER = "tester"
    TARGET = "target"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TargetCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)
    supports_reset: bool = False
    supports_trace: bool = False
    supports_tools: bool = False


class TargetSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    target_type: TargetType
    capabilities: TargetCapabilities = Field(default_factory=TargetCapabilities)


class CharacterProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = Field(min_length=1, max_length=120)
    persona: str = Field(min_length=1)
    rules: tuple[str, ...] = ()
    known_memories: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()


class TargetResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    trace: dict[str, object] = Field(default_factory=dict)


class TrialScenario(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    kind: TestKind
    messages: tuple[str, ...]
    expected_behavior: str
    forbidden_phrases: tuple[str, ...] = ()
    required_phrases: tuple[str, ...] = ()


class TrialTurn(BaseModel):
    model_config = ConfigDict(frozen=True)
    index: int = Field(ge=1)
    tester_message: str
    target_response: str
    latency_ms: int | None = None
    trace: dict[str, object] = Field(default_factory=dict)


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    message: str
    turn_index: int
    excerpt: str
    severity: Severity


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)
    passed: bool
    score: int = Field(ge=0, le=100)
    failure_type: str | None = None
    severity: Severity = Severity.INFO
    summary: str
    evidence: tuple[Evidence, ...] = ()


class TrialResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    target: TargetSummary
    scenario: TrialScenario
    status: TrialStatus
    turns: tuple[TrialTurn, ...]
    verdict: Verdict
    breakpoint: int | None = None


class TrialSuiteResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    target: TargetSummary
    results: tuple[TrialResult, ...]

    @computed_field
    @property
    def passed(self) -> bool:
        return all(item.verdict.passed for item in self.results)

    @computed_field
    @property
    def average_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(item.verdict.score for item in self.results) / len(self.results)


class HealthResponse(BaseModel):
    name: str
    version: str
    status: str = "ok"
    environment: str
