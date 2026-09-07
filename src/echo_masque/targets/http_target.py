"""Adapter for complete external chatbots exposed over HTTP."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.domain import TargetCapabilities, TargetResponse, TargetSummary, TargetType
from echo_masque.providers import (
    ProviderAuthenticationError,
    ProviderProtocolError,
    ProviderTimeoutError,
)
from echo_masque.security import redact
from echo_masque.target_endpoint_policy import EndpointPolicyRejected, TargetEndpointPolicy

if TYPE_CHECKING:
    from echo_masque.config import Settings

SecretLookup = Callable[[str], str | None]


class HttpTargetConfig(BaseModel):
    """Secret-free HTTP adapter contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_url: str
    reset_url: str | None = None
    message_field: str = "message"
    session_field: str = "session_id"
    response_text_path: str = "response"
    trace_path: str | None = "trace"
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    auth_env: str | None = None
    timeout_seconds: float = Field(default=30, gt=0, le=120)


class HttpTarget:
    """Test a private chatbot without requiring its prompt or model details."""

    def __init__(
        self,
        *,
        name: str,
        config: HttpTargetConfig,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        secret_lookup: SecretLookup | None = None,
        settings: Settings | None = None,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("Provide either client or transport, not both.")
        self.config = config
        self._client = client or httpx.AsyncClient(transport=transport, trust_env=False)
        self._owns_client = client is None
        # An untrusted persisted target may name a credential, but cannot read process env.
        # Trusted standalone callers must explicitly inject their credential resolver.
        self._secret_lookup = secret_lookup or (lambda _name: None)
        if settings is None:
            from echo_masque.config import get_settings

            settings = get_settings()
        self._endpoint_policy = TargetEndpointPolicy.from_settings(settings)
        self._session_id = str(uuid4())
        self._summary = TargetSummary(
            name=name,
            target_type=TargetType.HTTP_API,
            capabilities=TargetCapabilities(
                supports_reset=config.reset_url is not None,
                supports_trace=config.trace_path is not None,
            ),
        )

    @property
    def summary(self) -> TargetSummary:
        return self._summary

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def reset(self) -> None:
        self._session_id = str(uuid4())
        if self.config.reset_url is None:
            return
        await self._post(
            self.config.reset_url,
            {self.config.session_field: self._session_id},
            expect_payload=False,
        )

    async def send(self, message: str) -> TargetResponse:
        started = perf_counter()
        body = await self._post(
            self.config.message_url,
            {
                self.config.session_field: self._session_id,
                self.config.message_field: message,
            },
            expect_payload=True,
        )
        assert body is not None
        text = _read_path(body, self.config.response_text_path)
        if not isinstance(text, str):
            raise ProviderProtocolError("External target response text must be a string.")
        raw_trace: object = {}
        if self.config.trace_path:
            try:
                raw_trace = _read_path(body, self.config.trace_path)
            except ProviderProtocolError:
                raw_trace = {}
        safe_trace = redact(raw_trace)
        if not isinstance(safe_trace, dict):
            safe_trace = {"value": safe_trace}
        trace = cast(dict[str, object], safe_trace)
        trace.update(
            {
                "adapter": "custom-http",
                "session_id": self._session_id,
                "message_url": self.config.message_url,
            }
        )
        return TargetResponse(
            text=text,
            latency_ms=round((perf_counter() - started) * 1000),
            trace=trace,
        )

    async def _post(
        self,
        url: str,
        payload: dict[str, str],
        *,
        expect_payload: bool,
    ) -> Mapping[str, object] | None:
        try:
            self._endpoint_policy.require_http_target_url(url)
        except EndpointPolicyRejected as exc:
            raise ProviderProtocolError("External target endpoint is not approved.") from exc
        headers: dict[str, str] = {}
        if self.config.auth_env:
            token = self._secret_lookup(self.config.auth_env)
            if not token:
                raise ProviderAuthenticationError(
                    "External target credential is unavailable."
                )
            headers[self.config.auth_header] = f"{self.config.auth_scheme} {token}".strip()
        try:
            response = await self._client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.config.timeout_seconds,
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("External target request timed out.") from exc
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError("External target rejected authentication.")
        if 300 <= response.status_code < 400:
            raise ProviderProtocolError("External target redirect was refused.")
        if response.is_error:
            raise ProviderProtocolError(
                f"External target returned HTTP {response.status_code}."
            )
        if not expect_payload:
            return None
        try:
            value: object = response.json()
        except ValueError as exc:
            raise ProviderProtocolError("External target returned invalid JSON.") from exc
        if not isinstance(value, Mapping):
            raise ProviderProtocolError("External target response must be a JSON object.")
        return value


def _read_path(payload: Mapping[str, object], path: str) -> object:
    current: object = payload
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise ProviderProtocolError(f"External target response missing path: {path}")
        current = current[segment]
    return current
