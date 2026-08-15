from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor: {path}\n{old[:180]}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Provider-level normalized quota observations.
replace_once(
    "src/echo_masque/providers/base.py",
    'from typing import Literal, Protocol\n',
    'from datetime import datetime\nfrom typing import Literal, Protocol\n',
)
replace_once(
    "src/echo_masque/providers/base.py",
    '''class ProviderCompletion(BaseModel):\n    model_config = ConfigDict(frozen=True)\n''',
    '''class ProviderQuotaObservation(BaseModel):\n    model_config = ConfigDict(frozen=True)\n\n    kind: str\n    remaining: float | None = None\n    limit: float | None = None\n    unit: str = \"\"\n    reset_at: datetime | None = None\n    window_seconds: int | None = None\n    source: str = \"response_header\"\n\n\nclass ProviderCompletion(BaseModel):\n    model_config = ConfigDict(frozen=True)\n''',
)
replace_once(
    "src/echo_masque/providers/base.py",
    '''    tool_calls: tuple[ChatToolCall, ...] = ()\n\n\nclass ChatProvider(Protocol):\n''',
    '''    tool_calls: tuple[ChatToolCall, ...] = ()\n    quota_observations: tuple[ProviderQuotaObservation, ...] = ()\n\n\nclass ChatProvider(Protocol):\n''',
)

replace_once(
    "src/echo_masque/providers/errors.py",
    '"""Provider error taxonomy."""\n\n',
    '"""Provider error taxonomy."""\n\nfrom echo_masque.providers.base import ProviderQuotaObservation\n\n',
)
replace_once(
    "src/echo_masque/providers/errors.py",
    '''class ProviderRateLimitError(ProviderError):\n    \"\"\"The provider rejected the request because of a temporary rate limit.\"\"\"\n\n    reason_code = \"provider_rate_limited\"\n    transient = True\n''',
    '''class ProviderRateLimitError(ProviderError):\n    \"\"\"The provider rejected the request because of a temporary rate limit.\"\"\"\n\n    reason_code = \"provider_rate_limited\"\n    transient = True\n\n    def __init__(\n        self,\n        message: str,\n        *,\n        quota_observations: tuple[ProviderQuotaObservation, ...] = (),\n    ) -> None:\n        super().__init__(message)\n        self.quota_observations = quota_observations\n''',
)

# Parse common OpenAI-compatible rate-limit headers without provider-specific estimates.
replace_once(
    "src/echo_masque/providers/openai_compatible.py",
    '''import asyncio\nimport json\nfrom time import perf_counter\nfrom urllib.parse import urlparse\n''',
    '''import asyncio\nimport json\nimport re\nfrom datetime import UTC, datetime, timedelta\nfrom email.utils import parsedate_to_datetime\nfrom time import perf_counter\nfrom urllib.parse import urlparse\n''',
)
replace_once(
    "src/echo_masque/providers/openai_compatible.py",
    '''    ProviderCompletion,\n)\n''',
    '''    ProviderCompletion,\n    ProviderQuotaObservation,\n)\n''',
)
replace_once(
    "src/echo_masque/providers/openai_compatible.py",
    '''class OpenAICompatibleProvider:\n''',
    '''_DURATION_PART = re.compile(r\"(?P<value>\\d+(?:\\.\\d+)?)(?P<unit>ms|s|m|h)\", re.I)\n\n\ndef _float_header(headers: httpx.Headers, name: str) -> float | None:\n    raw = headers.get(name)\n    if raw is None:\n        return None\n    try:\n        return float(raw.strip())\n    except ValueError:\n        return None\n\n\ndef _reset_time(raw: str | None, *, now: datetime, retry_after: bool = False) -> datetime | None:\n    value = (raw or \"\").strip()\n    if not value:\n        return None\n    if retry_after:\n        try:\n            return now + timedelta(seconds=max(0.0, float(value)))\n        except ValueError:\n            try:\n                parsed = parsedate_to_datetime(value)\n            except (TypeError, ValueError):\n                return None\n            if parsed.tzinfo is None:\n                parsed = parsed.replace(tzinfo=UTC)\n            return parsed.astimezone(UTC)\n    parts = list(_DURATION_PART.finditer(value))\n    if parts and \"\".join(item.group(0) for item in parts).casefold() == value.casefold():\n        seconds = 0.0\n        for item in parts:\n            amount = float(item.group(\"value\"))\n            unit = item.group(\"unit\").casefold()\n            seconds += amount / 1000 if unit == \"ms\" else amount * {\"s\": 1, \"m\": 60, \"h\": 3600}[unit]\n        return now + timedelta(seconds=max(0.0, seconds))\n    try:\n        numeric = float(value)\n    except ValueError:\n        return None\n    if numeric > 1_000_000_000:\n        return datetime.fromtimestamp(numeric, tz=UTC)\n    return now + timedelta(seconds=max(0.0, numeric))\n\n\ndef _quota_observations(headers: httpx.Headers) -> tuple[ProviderQuotaObservation, ...]:\n    now = datetime.now(UTC)\n    observations: list[ProviderQuotaObservation] = []\n    dimensions = (\n        (\"requests\", \"requests\", \"x-ratelimit-remaining-requests\", \"x-ratelimit-limit-requests\", \"x-ratelimit-reset-requests\"),\n        (\"tokens\", \"tokens\", \"x-ratelimit-remaining-tokens\", \"x-ratelimit-limit-tokens\", \"x-ratelimit-reset-tokens\"),\n        (\"requests\", \"requests\", \"ratelimit-remaining\", \"ratelimit-limit\", \"ratelimit-reset\"),\n    )\n    seen: set[tuple[str, str]] = set()\n    for kind, unit, remaining_header, limit_header, reset_header in dimensions:\n        remaining = _float_header(headers, remaining_header)\n        limit = _float_header(headers, limit_header)\n        reset_at = _reset_time(headers.get(reset_header), now=now)\n        if remaining is None and limit is None and reset_at is None:\n            continue\n        key = (kind, reset_header)\n        if key in seen:\n            continue\n        seen.add(key)\n        observations.append(\n            ProviderQuotaObservation(\n                kind=kind,\n                remaining=remaining,\n                limit=limit,\n                unit=unit,\n                reset_at=reset_at,\n                source=\"response_header\",\n            )\n        )\n    retry_reset = _reset_time(headers.get(\"retry-after\"), now=now, retry_after=True)\n    if retry_reset is not None:\n        observations.append(\n            ProviderQuotaObservation(\n                kind=\"retry_after\",\n                unit=\"seconds\",\n                reset_at=retry_reset,\n                source=\"retry_after_header\",\n            )\n        )\n    return tuple(observations)\n\n\nclass OpenAICompatibleProvider:\n''',
)
replace_once(
    "src/echo_masque/providers/openai_compatible.py",
    '''                    if response.status_code == 429:\n                        if attempt < self._max_retries:\n''',
    '''                    quota_observations = _quota_observations(response.headers)\n\n                    if response.status_code == 429:\n                        if attempt < self._max_retries:\n''',
)
replace_once(
    "src/echo_masque/providers/openai_compatible.py",
    '''                        raise ProviderRateLimitError(\n                            \"Model provider rate limit was exceeded.\"\n                        )\n''',
    '''                        raise ProviderRateLimitError(\n                            \"Model provider rate limit was exceeded.\",\n                            quota_observations=quota_observations,\n                        )\n''',
)
replace_once(
    "src/echo_masque/providers/openai_compatible.py",
    '''                        tool_calls=tool_calls,\n                    )\n''',
    '''                        tool_calls=tool_calls,\n                        quota_observations=quota_observations,\n                    )\n''',
)

# Persist quota dimensions in a new table (safe create_all migration for existing SQLite).
replace_once(
    "src/echo_masque/persistence/utility_gateway_models.py",
    '''class UtilityUsageRecord(Base):\n''',
    '''class UtilityProviderQuotaRecord(Base):\n    __tablename__ = \"utility_provider_quotas\"\n\n    member_id: Mapped[str] = mapped_column(String(64), primary_key=True)\n    kind: Mapped[str] = mapped_column(String(48), primary_key=True)\n    remaining: Mapped[float | None] = mapped_column(Float, nullable=True)\n    limit_value: Mapped[float | None] = mapped_column(Float, nullable=True)\n    unit: Mapped[str] = mapped_column(String(40), default=\"\", nullable=False)\n    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)\n    window_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)\n    source: Mapped[str] = mapped_column(String(48), default=\"response_header\", nullable=False)\n    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)\n\n\nclass UtilityUsageRecord(Base):\n''',
)
replace_once(
    "src/echo_masque/persistence/database.py",
    '''from echo_masque.persistence.smart_participation_state_models import (\n''',
    '''from echo_masque.persistence.utility_gateway_models import UtilityProviderQuotaRecord\nfrom echo_masque.persistence.smart_participation_state_models import (\n''',
)
replace_once(
    "src/echo_masque/persistence/database.py",
    '''            SmartParticipationDeploymentStateRecord,\n        )\n''',
    '''            SmartParticipationDeploymentStateRecord,\n            UtilityProviderQuotaRecord,\n        )\n''',
)

# API snapshot contract exposes all observed dimensions.
replace_once(
    "src/echo_masque/utility_gateway_contracts.py",
    '''class UtilityProviderSnapshot(BaseModel):\n''',
    '''class UtilityQuotaDimension(BaseModel):\n    model_config = ConfigDict(frozen=True)\n\n    kind: str\n    remaining: float | None = None\n    limit: float | None = None\n    unit: str = \"\"\n    reset_at: datetime | None = None\n    window_seconds: int | None = None\n    source: str = \"response_header\"\n    observed_at: datetime | None = None\n\n\nclass UtilityProviderSnapshot(BaseModel):\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_contracts.py",
    '''    last_observed_at: datetime | None = None\n\n\nclass UtilityGatewaySnapshot(BaseModel):\n''',
    '''    last_observed_at: datetime | None = None\n    quota_dimensions: tuple[UtilityQuotaDimension, ...] = ()\n\n\nclass UtilityGatewaySnapshot(BaseModel):\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_contracts.py",
    '''    \"UtilityProviderSnapshot\",\n''',
    '''    \"UtilityProviderSnapshot\",\n    \"UtilityQuotaDimension\",\n''',
)

# Utility router stores observations on success/failure and includes them in snapshot.
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''from echo_masque.persistence.utility_gateway_models import (\n    UtilityProviderStateRecord,\n    UtilityUsageRecord,\n)\n''',
    '''from echo_masque.persistence.utility_gateway_models import (\n    UtilityProviderQuotaRecord,\n    UtilityProviderStateRecord,\n    UtilityUsageRecord,\n)\nfrom echo_masque.providers.base import ProviderQuotaObservation\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''    UtilityProviderSnapshot,\n''',
    '''    UtilityProviderSnapshot,\n    UtilityQuotaDimension,\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''    observation_source: str = \"response\"\n''',
    '''    observation_source: str = \"response\"\n    quota_observations: tuple[ProviderQuotaObservation, ...] = ()\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''        reset_at: datetime | None = None,\n    ) -> None:\n''',
    '''        reset_at: datetime | None = None,\n        quota_observations: tuple[ProviderQuotaObservation, ...] = (),\n    ) -> None:\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''        self.reset_at = reset_at\n\n\nclass UtilityProviderCaller(Protocol):\n''',
    '''        self.reset_at = reset_at\n        self.quota_observations = quota_observations\n\n\nclass UtilityProviderCaller(Protocol):\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''    def _record_usage(\n''',
    '''    def _save_quota_observations(\n        self,\n        member_id: str,\n        observations: tuple[ProviderQuotaObservation, ...],\n    ) -> None:\n        if not observations:\n            return\n        now = datetime.now(UTC)\n        with self.database.session() as session:\n            for observation in observations:\n                record = session.get(UtilityProviderQuotaRecord, (member_id, observation.kind))\n                if record is None:\n                    record = UtilityProviderQuotaRecord(member_id=member_id, kind=observation.kind)\n                    session.add(record)\n                record.remaining = observation.remaining\n                record.limit_value = observation.limit\n                record.unit = observation.unit[:40]\n                record.reset_at = observation.reset_at\n                record.window_seconds = observation.window_seconds\n                record.source = observation.source[:48]\n                record.observed_at = now\n            session.commit()\n\n    def _quota_dimensions(self, member_id: str) -> tuple[UtilityQuotaDimension, ...]:\n        with self.database.session() as session:\n            rows = list(\n                session.scalars(\n                    select(UtilityProviderQuotaRecord)\n                    .where(UtilityProviderQuotaRecord.member_id == member_id)\n                    .order_by(UtilityProviderQuotaRecord.kind.asc())\n                )\n            )\n        return tuple(\n            UtilityQuotaDimension(\n                kind=row.kind,\n                remaining=row.remaining,\n                limit=row.limit_value,\n                unit=row.unit,\n                reset_at=self._aware(row.reset_at),\n                window_seconds=row.window_seconds,\n                source=row.source,\n                observed_at=self._aware(row.observed_at),\n            )\n            for row in rows\n        )\n\n    def _record_usage(\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''                    last_observed_at=(\n                        self._aware(state.last_observed_at) if state is not None else None\n                    ),\n                )\n''',
    '''                    last_observed_at=(\n                        self._aware(state.last_observed_at) if state is not None else None\n                    ),\n                    quota_dimensions=self._quota_dimensions(member.id),\n                )\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''                    observation_source=reply.observation_source,\n                )\n''',
    '''                    observation_source=reply.observation_source,\n                    quota_observations=reply.quota_observations,\n                )\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''                self._save_state(\n                    member,\n                    status=\"healthy\",\n''',
    '''                self._save_quota_observations(member.id, reply.quota_observations)\n                self._save_state(\n                    member,\n                    status=\"healthy\",\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_router.py",
    '''        if member is not None:\n            self._save_state(\n''',
    '''        if member is not None:\n            self._save_quota_observations(member.id, failure.quota_observations)\n            self._save_state(\n''',
)

# Live utility caller propagates observed provider metadata.
replace_once(
    "src/echo_masque/utility_gateway_live.py",
    '''        except ProviderRateLimitError as exc:\n            raise UtilityCallFailed(\"quota\", detail=str(exc)) from exc\n''',
    '''        except ProviderRateLimitError as exc:\n            resets = [\n                item.reset_at\n                for item in exc.quota_observations\n                if item.reset_at is not None\n            ]\n            reset_at = min(resets) if resets else None\n            zero = next(\n                (item for item in exc.quota_observations if item.remaining == 0),\n                None,\n            )\n            raise UtilityCallFailed(\n                \"quota\",\n                detail=str(exc),\n                remaining_value=zero.remaining if zero is not None else None,\n                remaining_unit=zero.unit if zero is not None else \"\",\n                reset_at=reset_at,\n                quota_observations=exc.quota_observations,\n            ) from exc\n''',
)
replace_once(
    "src/echo_masque/utility_gateway_live.py",
    '''            output_tokens=completion.output_tokens or 0,\n        )\n''',
    '''            output_tokens=completion.output_tokens or 0,\n            quota_observations=completion.quota_observations,\n        )\n''',
)

# Provider/header tests and persistence tests.
Path("tests/test_provider_quota_observation.py").write_text(
    '''from datetime import UTC, datetime\n\nimport httpx\nimport pytest\nfrom pydantic import SecretStr\n\nfrom echo_masque.providers.base import ChatMessage\nfrom echo_masque.providers.errors import ProviderRateLimitError\nfrom echo_masque.providers.openai_compatible import OpenAICompatibleProvider\n\n\n@pytest.mark.asyncio\nasync def test_success_exposes_request_and_token_quota_headers() -> None:\n    async def handler(request: httpx.Request) -> httpx.Response:\n        return httpx.Response(\n            200,\n            headers={\n                \"x-ratelimit-remaining-requests\": \"42\",\n                \"x-ratelimit-limit-requests\": \"100\",\n                \"x-ratelimit-reset-requests\": \"5s\",\n                \"x-ratelimit-remaining-tokens\": \"9000\",\n                \"x-ratelimit-limit-tokens\": \"10000\",\n                \"x-ratelimit-reset-tokens\": \"2s\",\n            },\n            json={\n                \"model\": \"test\",\n                \"choices\": [{\"message\": {\"content\": \"ok\"}, \"finish_reason\": \"stop\"}],\n                \"usage\": {\"prompt_tokens\": 1, \"completion_tokens\": 1},\n            },\n        )\n\n    provider = OpenAICompatibleProvider(\n        base_url=\"https://example.test/v1\",\n        api_key=SecretStr(\"key\"),\n        max_retries=0,\n        transport=httpx.MockTransport(handler),\n    )\n    result = await provider.complete(\n        messages=(ChatMessage(role=\"user\", content=\"hello\"),),\n        model=\"test\",\n        temperature=0,\n    )\n    values = {item.kind: item for item in result.quota_observations}\n    assert values[\"requests\"].remaining == 42\n    assert values[\"requests\"].limit == 100\n    assert values[\"tokens\"].remaining == 9000\n    assert values[\"tokens\"].limit == 10000\n    assert values[\"requests\"].reset_at is not None\n\n\n@pytest.mark.asyncio\nasync def test_429_preserves_retry_after_without_inventing_remaining() -> None:\n    async def handler(request: httpx.Request) -> httpx.Response:\n        return httpx.Response(429, headers={\"Retry-After\": \"30\"}, json={\"error\": \"rate\"})\n\n    provider = OpenAICompatibleProvider(\n        base_url=\"https://example.test/v1\",\n        api_key=SecretStr(\"key\"),\n        max_retries=0,\n        transport=httpx.MockTransport(handler),\n    )\n    before = datetime.now(UTC)\n    with pytest.raises(ProviderRateLimitError) as raised:\n        await provider.complete(\n            messages=(ChatMessage(role=\"user\", content=\"hello\"),),\n            model=\"test\",\n            temperature=0,\n        )\n    observation = raised.value.quota_observations[0]\n    assert observation.kind == \"retry_after\"\n    assert observation.remaining is None\n    assert observation.reset_at is not None\n    assert observation.reset_at >= before\n''',
    encoding="utf-8",
)

# System Intelligence Portal: dynamic Conversation Burst control.
Path("web/src/ConversationBurstRuntimePanel.tsx").write_text(
    '''export interface ConversationBurstRuntimeConfig {\n  enabled: boolean;\n  quiet_window_ms: number;\n  max_wait_ms: number;\n  max_messages: number;\n  max_characters: number;\n}\n\ninterface Props {\n  config: ConversationBurstRuntimeConfig;\n  zh: boolean;\n  onChange: (config: ConversationBurstRuntimeConfig) => void;\n}\n\nconst presets = [\n  { id: \"fast\", label: \"Fast\", quiet: 1500, max: 4000 },\n  { id: \"balanced\", label: \"Balanced\", quiet: 3000, max: 10000 },\n  { id: \"patient\", label: \"Patient\", quiet: 5000, max: 15000 }\n] as const;\n\nfunction seconds(value: number): number {\n  return Math.round(value / 100) / 10;\n}\n\nexport function ConversationBurstRuntimePanel({ config, zh, onChange }: Props) {\n  const patch = (values: Partial<ConversationBurstRuntimeConfig>) => onChange({ ...config, ...values });\n  const activePreset = presets.find((item) => item.quiet === config.quiet_window_ms && item.max === config.max_wait_ms)?.id;\n  return (\n    <section className=\"runtime-panel conversation-burst-runtime-panel\">\n      <div className=\"utility-section-heading\">\n        <div className=\"utility-section-heading-copy\">\n          <span className=\"utility-section-icon\">◷</span>\n          <div><span className=\"utility-section-eyebrow\">CONVERSATION BURST</span><h4>{zh ? \"Turn Collector 动态控制\" : \"Dynamic Turn Collector\"}</h4></div>\n        </div>\n        <span className={`utility-state-badge${config.enabled ? \" is-enabled\" : \"\"}`}>{config.enabled ? \"ENABLED\" : \"OFF\"}</span>\n      </div>\n      <p className=\"section-help\">{zh ? \"保存后由 Connector 在运行中同步，无需重启。已经打开的 burst 保持创建时的参数；新 burst 使用最新配置。明确角色名、Reply 与 Interaction 仍走即时 fast path。\" : \"Changes sync into the live Connector without restart. Open bursts keep their original timing snapshot; new bursts use the latest config. Explicit addressing, replies, and interactions remain immediate.\"}</p>\n      <label className=\"utility-switch-row\"><span className=\"utility-switch\"><input type=\"checkbox\" checked={config.enabled} onChange={(event) => patch({ enabled: event.currentTarget.checked })}/><span className=\"utility-switch-track\" /></span><span>{zh ? \"启用 Conversation Burst\" : \"Enable Conversation Burst\"}</span></label>\n      <div className=\"conversation-burst-presets\">{presets.map((preset) => <button type=\"button\" key={preset.id} className={`paper-button${activePreset === preset.id ? \" is-active\" : \"\"}`} onClick={() => patch({ quiet_window_ms: preset.quiet, max_wait_ms: preset.max })}>{preset.label}<small>{seconds(preset.quiet)}s / {seconds(preset.max)}s</small></button>)}</div>\n      <div className=\"utility-field-grid\">\n        <label>{zh ? \"Quiet window（秒）\" : \"Quiet window (seconds)\"}<input type=\"number\" min=\"0.1\" max=\"10\" step=\"0.1\" value={seconds(config.quiet_window_ms)} onChange={(event) => patch({ quiet_window_ms: Math.round(Number(event.currentTarget.value) * 1000) })}/></label>\n        <label>{zh ? \"Maximum wait（秒）\" : \"Maximum wait (seconds)\"}<input type=\"number\" min=\"0.5\" max=\"30\" step=\"0.5\" value={seconds(config.max_wait_ms)} onChange={(event) => patch({ max_wait_ms: Math.round(Number(event.currentTarget.value) * 1000) })}/></label>\n        <label>{zh ? \"最多消息\" : \"Max messages\"}<input type=\"number\" min=\"1\" max=\"20\" value={config.max_messages} onChange={(event) => patch({ max_messages: Number(event.currentTarget.value) })}/></label>\n        <label>{zh ? \"最多字符\" : \"Max characters\"}<input type=\"number\" min=\"100\" max=\"10000\" step=\"100\" value={config.max_characters} onChange={(event) => patch({ max_characters: Number(event.currentTarget.value) })}/></label>\n      </div>\n      <p className=\"utility-provider-note\">ⓘ {zh ? `当前目标：安静 ${seconds(config.quiet_window_ms)} 秒后判断，最迟 ${seconds(config.max_wait_ms)} 秒强制 flush。` : `Current target: decide after ${seconds(config.quiet_window_ms)}s of quiet, with a hard flush at ${seconds(config.max_wait_ms)}s.`}</p>\n    </section>\n  );\n}\n''',
    encoding="utf-8",
)

# Extend UtilityGatewayPanel runtime snapshot types/props and provider cards.
replace_once(
    "web/src/UtilityGatewayPanel.tsx",
    '''export interface UtilityCredentialStatus {\n  member_id: string;\n  configured: boolean;\n  source: string;\n}\n\ninterface Props {\n''',
    '''export interface UtilityCredentialStatus {\n  member_id: string;\n  configured: boolean;\n  source: string;\n}\n\nexport interface UtilityQuotaDimension {\n  kind: string;\n  remaining: number | null;\n  limit: number | null;\n  unit: string;\n  reset_at: string | null;\n  window_seconds: number | null;\n  source: string;\n  observed_at: string | null;\n}\n\nexport interface UtilityProviderRuntimeSnapshot {\n  member_id: string;\n  status: string;\n  cooldown_until: string | null;\n  last_error: string;\n  last_observed_at: string | null;\n  observation_source: string;\n  quota_dimensions: UtilityQuotaDimension[];\n}\n\nexport interface UtilityGatewayRuntimeSnapshot {\n  enabled: boolean;\n  members: UtilityProviderRuntimeSnapshot[];\n  paid_fallback_enabled: boolean;\n  daily_cost_usd: number;\n  monthly_cost_usd: number;\n}\n\ninterface Props {\n''',
)
replace_once(
    "web/src/UtilityGatewayPanel.tsx",
    '''  credentialStatus: UtilityCredentialStatus[];\n  zh: boolean;\n''',
    '''  credentialStatus: UtilityCredentialStatus[];\n  runtimeSnapshot: UtilityGatewayRuntimeSnapshot | null;\n  zh: boolean;\n''',
)
replace_once(
    "web/src/UtilityGatewayPanel.tsx",
    '''  credentialStatus,\n  zh,\n''',
    '''  credentialStatus,\n  runtimeSnapshot,\n  zh,\n''',
)
replace_once(
    "web/src/UtilityGatewayPanel.tsx",
    '''  const statusById = useMemo(\n    () => new Map(credentialStatus.map((item) => [item.member_id, item])),\n    [credentialStatus]\n  );\n''',
    '''  const statusById = useMemo(\n    () => new Map(credentialStatus.map((item) => [item.member_id, item])),\n    [credentialStatus]\n  );\n  const runtimeById = useMemo(\n    () => new Map((runtimeSnapshot?.members ?? []).map((item) => [item.member_id, item])),\n    [runtimeSnapshot]\n  );\n''',
)
replace_once(
    "web/src/UtilityGatewayPanel.tsx",
    '''            const credential = statusById.get(member.id);\n            const meta = providerMeta(member.provider);\n''',
    '''            const credential = statusById.get(member.id);\n            const runtime = runtimeById.get(member.id);\n            const meta = providerMeta(member.provider);\n''',
)
replace_once(
    "web/src/UtilityGatewayPanel.tsx",
    '''                    <span\n                      className={`utility-state-badge${credential?.configured ? \" is-ready\" : \" is-missing\"}`}\n                    >\n                      {credential?.configured ? \"KEY READY\" : \"NO KEY\"}\n                    </span>\n''',
    '''                    <span\n                      className={`utility-state-badge${credential?.configured ? \" is-ready\" : \" is-missing\"}`}\n                    >\n                      {credential?.configured ? \"KEY READY\" : \"NO KEY\"}\n                    </span>\n                    <span className={`utility-state-badge utility-runtime-${runtime?.status ?? \"unknown\"}`}>\n                      {(runtime?.status ?? \"unknown\").replaceAll(\"_\", \" \").toUpperCase()}\n                    </span>\n''',
)
replace_once(
    "web/src/UtilityGatewayPanel.tsx",
    '''                    <p className=\"utility-provider-note\">\n                      ⓘ {zh\n                        ? \"Quota / Health 由 Runtime 统一观测；这里不需要手动轮询 Provider。\"\n                        : \"Quota / Health is observed by Runtime; no manual provider polling is required here.\"}\n                    </p>\n''',
    '''                    <section className=\"utility-runtime-observation\">\n                      <div className=\"utility-runtime-observation-head\"><strong>{zh ? \"Runtime / Quota\" : \"Runtime / Quota\"}</strong><small>{runtime?.last_observed_at ? new Date(runtime.last_observed_at).toLocaleString() : (zh ? \"尚未观测\" : \"Not observed yet\")}</small></div>\n                      {runtime?.quota_dimensions.length ? (\n                        <div className=\"utility-quota-grid\">{runtime.quota_dimensions.map((quota) => <div className=\"utility-quota-card\" key={quota.kind}><span>{quota.kind.replaceAll(\"_\", \" \")}</span><strong>{quota.remaining === null ? \"Unknown\" : `${quota.remaining}${quota.limit === null ? \"\" : ` / ${quota.limit}`} ${quota.unit}`}</strong><small>{quota.reset_at ? `${zh ? \"重置\" : \"Reset\"}: ${new Date(quota.reset_at).toLocaleString()}` : (zh ? \"Reset unknown\" : \"Reset unknown\")}</small></div>)}</div>\n                      ) : <p className=\"utility-provider-note\">{zh ? \"Provider 尚未返回可验证的 quota header；Remaining / Reset 显示 Unknown，不做估算。\" : \"The provider has not returned authoritative quota headers yet. Remaining / Reset stay Unknown rather than estimated.\"}</p>}\n                      {runtime?.cooldown_until && <p className=\"utility-runtime-warning\">{zh ? \"暂时退出 Free Pool，预计可重新 probe：\" : \"Temporarily out of the Free Pool; probe eligible after: \"}{new Date(runtime.cooldown_until).toLocaleString()}</p>}\n                      {runtime?.last_error && <p className=\"utility-runtime-warning\">{runtime.last_error}</p>}\n                    </section>\n                    <p className=\"utility-provider-note\">\n                      ⓘ {zh\n                        ? \"ENABLED 是人工配置；429 / quota 只改变 Runtime health，不会自动关闭 member。冷却或 reset 到期后会自动重新进入 probe。\"\n                        : \"ENABLED is manual configuration. 429/quota only changes Runtime health; it never disables the member. The provider becomes probe eligible automatically after cooldown/reset.\"}\n                    </p>\n''',
)

# Replace the small System Intelligence dock with a version that loads quota snapshot and Burst controls.
Path("web/src/SemanticRoutingJudgeDock.tsx").write_text(
    '''import { useEffect, useState } from \"react\";\n\nimport { api, type AdminRuntimeConfig, type AdminRuntimeView } from \"./api\";\nimport {\n  ConversationBurstRuntimePanel,\n  type ConversationBurstRuntimeConfig\n} from \"./ConversationBurstRuntimePanel\";\nimport { useI18n } from \"./i18n\";\nimport {\n  SemanticRoutingJudgePanel,\n  type SemanticRoutingAdminView,\n  type SemanticRoutingJudgeConfig\n} from \"./SemanticRoutingJudgePanel\";\nimport { UtilityCredentialSaveProvider } from \"./UtilityCredentialSaveContext\";\nimport {\n  UtilityGatewayPanel,\n  type UtilityCredentialStatus,\n  type UtilityGatewayConfig,\n  type UtilityGatewayRuntimeSnapshot\n} from \"./UtilityGatewayPanel\";\n\ntype UtilityAdminView = SemanticRoutingAdminView & {\n  config: SemanticRoutingAdminView[\"config\"] & {\n    utility_gateway: UtilityGatewayConfig;\n    conversation_burst: ConversationBurstRuntimeConfig;\n  };\n};\n\nasync function loadUtilityCredentials(): Promise<UtilityCredentialStatus[]> {\n  const response = await fetch(\"/api/admin/runtime/utility-credentials\", { credentials: \"include\" });\n  if (!response.ok) return [];\n  return response.json() as Promise<UtilityCredentialStatus[]>;\n}\n\nasync function loadUtilitySnapshot(): Promise<UtilityGatewayRuntimeSnapshot | null> {\n  const response = await fetch(\"/api/admin/runtime/utility-gateway/snapshot\", { credentials: \"include\" });\n  if (!response.ok) return null;\n  return response.json() as Promise<UtilityGatewayRuntimeSnapshot>;\n}\n\nexport function SemanticRoutingJudgeDock() {\n  const { language } = useI18n();\n  const zh = language === \"zh-CN\";\n  const [view, setView] = useState<UtilityAdminView | null>(null);\n  const [credentialStatus, setCredentialStatus] = useState<UtilityCredentialStatus[]>([]);\n  const [runtimeSnapshot, setRuntimeSnapshot] = useState<UtilityGatewayRuntimeSnapshot | null>(null);\n  const [open, setOpen] = useState(false);\n  const [saving, setSaving] = useState(false);\n  const [message, setMessage] = useState(\"\");\n\n  async function refreshRuntimeObservation() {\n    const [credentials, snapshot] = await Promise.all([loadUtilityCredentials(), loadUtilitySnapshot()]);\n    setCredentialStatus(credentials);\n    setRuntimeSnapshot(snapshot);\n  }\n\n  useEffect(() => {\n    let active = true;\n    void Promise.all([api.getAdminRuntime(), loadUtilityCredentials(), loadUtilitySnapshot()])\n      .then(([value, credentials, snapshot]) => {\n        if (active && \"semantic_routing\" in value.config && \"utility_gateway\" in value.config && \"conversation_burst\" in value.config) {\n          setView(value as UtilityAdminView);\n          setCredentialStatus(credentials);\n          setRuntimeSnapshot(snapshot);\n        }\n      })\n      .catch(() => undefined);\n    return () => { active = false; };\n  }, []);\n\n  useEffect(() => {\n    if (!open) return;\n    const timer = window.setInterval(() => { void loadUtilitySnapshot().then(setRuntimeSnapshot); }, 15_000);\n    return () => window.clearInterval(timer);\n  }, [open]);\n\n  if (!view) return null;\n\n  function updateSemantic(config: SemanticRoutingJudgeConfig) {\n    setView((current) => current ? ({ ...current, config: { ...current.config, semantic_routing: config } } as UtilityAdminView) : current);\n    setMessage(\"\");\n  }\n\n  function updateUtility(config: UtilityGatewayConfig) {\n    setView((current) => current ? ({ ...current, config: { ...current.config, utility_gateway: config } } as UtilityAdminView) : current);\n    setMessage(\"\");\n  }\n\n  function updateConversationBurst(config: ConversationBurstRuntimeConfig) {\n    setView((current) => current ? ({ ...current, config: { ...current.config, conversation_burst: config } } as UtilityAdminView) : current);\n    setMessage(\"\");\n  }\n\n  async function persistUtilityConfigForCredential() {\n    if (!view) throw new Error(\"System Intelligence configuration is not loaded.\");\n    setMessage(\"\");\n    const next = await api.updateAdminRuntime(view.config as AdminRuntimeConfig);\n    setView(next as AdminRuntimeView as UtilityAdminView);\n  }\n\n  async function save() {\n    if (!view) return;\n    try {\n      setSaving(true);\n      setMessage(\"\");\n      const next = await api.updateAdminRuntime(view.config as AdminRuntimeConfig);\n      setView(next as AdminRuntimeView as UtilityAdminView);\n      await refreshRuntimeObservation();\n      setMessage(zh ? \"System Intelligence 已保存。Connector 会在运行中同步新 Burst 参数，无需重启。\" : \"System Intelligence saved. The Connector will sync new Burst settings live without restart.\");\n    } catch (reason) {\n      setMessage(reason instanceof Error ? reason.message : String(reason));\n    } finally {\n      setSaving(false);\n    }\n  }\n\n  return (\n    <div className={`semantic-routing-dock${open ? \" is-open\" : \"\"}`}>\n      {!open ? (\n        <button type=\"button\" className=\"semantic-routing-dock-tab\" onClick={() => setOpen(true)}><span>SUPER ADMIN</span><strong>System Intelligence</strong></button>\n      ) : (\n        <div className=\"semantic-routing-drawer paper-sheet\">\n          <header className=\"semantic-routing-drawer-head\"><div><span>SUPER ADMIN / SYSTEM RUNTIME</span><h2>System Intelligence</h2></div><button type=\"button\" className=\"close-button\" onClick={() => setOpen(false)} aria-label=\"Close\">×</button></header>\n          <ConversationBurstRuntimePanel config={view.config.conversation_burst} zh={zh} onChange={updateConversationBurst} />\n          <UtilityCredentialSaveProvider beforeSave={persistUtilityConfigForCredential}>\n            <UtilityGatewayPanel config={view.config.utility_gateway} credentialStatus={credentialStatus} runtimeSnapshot={runtimeSnapshot} zh={zh} onChange={updateUtility} onRefreshCredentials={refreshRuntimeObservation} />\n          </UtilityCredentialSaveProvider>\n          <SemanticRoutingJudgePanel view={view} zh={zh} onChange={updateSemantic} />\n          {message && <p className={message.includes(\"保存\") || message.includes(\"saved\") ? \"success-note\" : \"error-note\"}>{message}</p>}\n          <footer className=\"semantic-routing-drawer-actions\"><button type=\"button\" className=\"paper-button\" onClick={() => setOpen(false)}>{zh ? \"关闭\" : \"Close\"}</button><button type=\"button\" className=\"ink-button\" disabled={saving} onClick={() => void save()}>{saving ? (zh ? \"保存中…\" : \"Saving…\") : zh ? \"保存 System Intelligence\" : \"Save System Intelligence\"}</button></footer>\n        </div>\n      )}\n    </div>\n  );\n}\n''',
    encoding="utf-8",
)

with Path("web/src/utility-gateway.css").open("a", encoding="utf-8") as file:
    file.write('''\n\n/* Post-V4 runtime observability */\n.conversation-burst-runtime-panel { display: grid; gap: 14px; }\n.conversation-burst-presets { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }\n.conversation-burst-presets .paper-button { display: grid; gap: 2px; text-align: left; }\n.conversation-burst-presets .paper-button.is-active { box-shadow: inset 0 0 0 2px currentColor; }\n.utility-runtime-observation { margin-top: 14px; padding: 12px; border: 1px dashed rgba(43, 54, 64, 0.28); border-radius: 12px; background: rgba(255,255,255,0.38); }\n.utility-runtime-observation-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 10px; }\n.utility-quota-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }\n.utility-quota-card { display: grid; gap: 3px; padding: 9px; border-radius: 9px; background: rgba(255,255,255,0.6); }\n.utility-quota-card span { text-transform: uppercase; font-size: .72rem; letter-spacing: .06em; }\n.utility-quota-card small, .utility-runtime-observation-head small { opacity: .72; }\n.utility-runtime-warning { margin: 8px 0 0; font-size: .82rem; }\n.utility-runtime-healthy, .utility-runtime-unknown { opacity: .9; }\n.utility-runtime-cooling_down, .utility-runtime-exhausted, .utility-runtime-unavailable { font-weight: 700; }\n@media (max-width: 720px) { .conversation-burst-presets { grid-template-columns: 1fr; } }\n''')

# Focused web compile will catch integration issues.
