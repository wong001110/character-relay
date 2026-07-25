"""Adapter for complete external chatbots exposed over HTTP."""

import os
from collections.abc import Callable, Mapping
from time import perf_counter
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

SecretLookup = Callable[[str], str | None]


class HttpTargetConfig(BaseModel):
    """Secret-free HTTP adapter contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_url: str = Field(min_length=1)
    reset_url: str | None = None
    message_field: str = "message"
    session_field: str = "session_id"
    response_text_path: str = "response"
    trace_path: str | None = "trace"
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    auth_env: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class HttpTarget:
    """Send trial turns to an external chatbot without inspecting its internals."""

    def __init__(
        self,
        *,
        name: str,
        config: HttpTargetConfig,
        secret_lookup: SecretLookup | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._secret_lookup = secret_lookup or os.environ.get
        self._transport = transport
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

    def _headers(self) -> dict[str, str]:
        if self.config.auth_env is None:
            return {"Content-Type": "application/json"}
        secret = self._secret_lookup(self.config.auth_env)
        if not secret:
            raise ProviderAuthenticationError(
                "The external target credential environment variable is not set."
            )
        value = f"{self.config.auth_scheme} {secret}".strip()
        return {"Content-Type": "application/json", self.config.auth_header: value}

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
        safe_trace.update(
            {
                "adapter": "custom-http",
                "session_id": self._session_id,
                "message_url": self.config.message_url,
            }
        )
        return TargetResponse(
            text=text,
            latency_ms=round((perf_counter() - started) * 1000),
            trace=safe_trace,
        )

    async def _post(
        self,
        url: str,
        payload: dict[str, str],
        *,
        expect_payload: bool,
    ) -> Mapping[str, object] | None:
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(url, json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("External target timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderProtocolError("External target could not be reached.") from exc

        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError("External target rejected the credential.")
        if response.is_error:
            raise ProviderProtocolError(
                f"External target returned HTTP {response.status_code}."
            )
        if not expect_payload:
            return None
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderProtocolError("External target returned invalid JSON.") from exc
        if not isinstance(body, Mapping):
            raise ProviderProtocolError("External target response must be a JSON object.")
        return body


def _read_path(payload: Mapping[str, object], path: str) -> object:
    current: object = payload
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise ProviderProtocolError(f"External target response is missing path: {path}.")
        current = current[segment]
    return current
