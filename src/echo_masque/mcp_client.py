"""Bounded Streamable HTTP client boundary for controlled MCP providers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import SecretStr

from echo_masque.mcp_config import McpProviderConfig
from echo_masque.network_safety import PublicUrlGuard


class McpClientError(RuntimeError):
    """A controlled MCP client could not complete a protocol operation."""


class McpCallOutcomeUnknown(McpClientError):
    """A remote call crossed the network boundary but its outcome is unknown."""


@dataclass(frozen=True)
class McpRemoteTool:
    name: str
    title: str | None
    description: str
    input_schema: dict[str, object]


@dataclass(frozen=True)
class McpRemoteCallResult:
    is_error: bool
    content: tuple[object, ...]
    structured_content: object | None


class McpSession(Protocol):
    async def list_tools(self, *, cursor: str | None = None) -> object: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object] | None = None,
        read_timeout_seconds: float | None = None,
    ) -> object: ...


type McpSessionFactory = Callable[
    [McpProviderConfig, SecretStr | None], AbstractAsyncContextManager[McpSession]
]
type HttpTransportFactory = Callable[[], object]


class McpClient:
    """Use the official SDK while keeping Runtime's network policy outside the SDK."""

    def __init__(
        self,
        *,
        url_guard: PublicUrlGuard | None = None,
        session_factory: McpSessionFactory | None = None,
        http_transport_factory: HttpTransportFactory | None = None,
    ) -> None:
        self._url_guard = url_guard or PublicUrlGuard()
        self._session_factory = session_factory or self._official_session
        self._http_transport_factory = http_transport_factory

    async def list_tools(
        self,
        provider: McpProviderConfig,
        bearer_token: SecretStr | None,
    ) -> tuple[McpRemoteTool, ...]:
        await self._url_guard.validate(provider.endpoint)
        pages = 0
        cursor: str | None = None
        collected: list[McpRemoteTool] = []
        try:
            async with asyncio.timeout(provider.list_timeout_seconds):
                async with self._session_factory(provider, bearer_token) as session:
                    while True:
                        pages += 1
                        if pages > provider.max_catalog_pages:
                            raise McpClientError("mcp_catalog_page_limit_exceeded")
                        page = await session.list_tools(cursor=cursor)
                        tools = getattr(page, "tools", ())
                        if not isinstance(tools, (list, tuple)):
                            raise McpClientError("mcp_invalid_tools_list")
                        for raw_tool in tools:
                            collected.append(self._decode_tool(raw_tool))
                            if len(collected) > provider.max_catalog_tools:
                                raise McpClientError("mcp_catalog_tool_limit_exceeded")
                        next_cursor = getattr(page, "next_cursor", None)
                        if next_cursor is None:
                            return tuple(collected)
                        if not isinstance(next_cursor, str) or not next_cursor:
                            raise McpClientError("mcp_invalid_catalog_cursor")
                        cursor = next_cursor
        except TimeoutError as exc:
            raise McpClientError("mcp_catalog_timeout") from exc
        except McpClientError:
            raise
        except Exception as exc:
            raise McpClientError(_embedded_mcp_error_code(exc) or "mcp_catalog_failed") from exc

    async def call_tool(
        self,
        provider: McpProviderConfig,
        bearer_token: SecretStr | None,
        *,
        tool_name: str,
        arguments: dict[str, object],
    ) -> McpRemoteCallResult:
        await self._url_guard.validate(provider.endpoint)
        try:
            async with asyncio.timeout(provider.call_timeout_seconds):
                async with self._session_factory(provider, bearer_token) as session:
                    result = await session.call_tool(
                        tool_name,
                        arguments,
                        read_timeout_seconds=provider.call_timeout_seconds,
                    )
        except TimeoutError as exc:
            raise McpCallOutcomeUnknown("mcp_call_outcome_unknown") from exc
        except asyncio.CancelledError:
            raise
        except McpClientError as exc:
            raise McpCallOutcomeUnknown("mcp_call_outcome_unknown") from exc
        except Exception as exc:
            raise McpCallOutcomeUnknown("mcp_call_outcome_unknown") from exc
        content = getattr(result, "content", ())
        if not isinstance(content, (list, tuple)):
            raise McpClientError("mcp_invalid_call_result")
        return McpRemoteCallResult(
            is_error=bool(getattr(result, "is_error", False)),
            content=tuple(content),
            structured_content=getattr(result, "structured_content", None),
        )

    @staticmethod
    def _decode_tool(raw: object) -> McpRemoteTool:
        name = getattr(raw, "name", None)
        input_schema = getattr(raw, "input_schema", None)
        title = getattr(raw, "title", None)
        description = getattr(raw, "description", "")
        if not isinstance(name, str) or not isinstance(input_schema, dict):
            raise McpClientError("mcp_invalid_tool_descriptor")
        if title is not None and not isinstance(title, str):
            title = None
        return McpRemoteTool(
            name=name,
            title=title,
            description=description if isinstance(description, str) else "",
            input_schema={str(key): value for key, value in input_schema.items()},
        )

    @asynccontextmanager
    async def _official_session(
        self,
        provider: McpProviderConfig,
        bearer_token: SecretStr | None,
    ) -> AsyncIterator[McpSession]:
        # Import lazily so configuration inspection and deterministic tests do not open or
        # require an MCP client stack. ``mcp`` 2.x owns JSON/SSE Streamable HTTP framing.
        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client

        headers: dict[str, str] = {}
        if bearer_token is not None:
            headers["Authorization"] = f"Bearer {bearer_token.get_secret_value()}"
        headers["Accept-Encoding"] = "identity"

        class CappedAsyncByteStream(httpx2.AsyncByteStream):
            def __init__(self, stream: httpx2.AsyncByteStream) -> None:
                self._stream = stream
                self._received = 0

            async def __aiter__(self) -> AsyncIterator[bytes]:
                try:
                    async for chunk in self._stream:
                        self._received += len(chunk)
                        if self._received > provider.max_http_response_bytes:
                            raise McpClientError("mcp_response_too_large")
                        yield chunk
                finally:
                    await self._stream.aclose()

            async def aclose(self) -> None:
                await self._stream.aclose()

        async def reject_redirect_or_large_response(response: Any) -> None:
            if 300 <= response.status_code < 400:
                raise McpClientError("mcp_redirect_rejected")
            content_encoding = response.headers.get("content-encoding", "identity").casefold()
            if content_encoding not in {"", "identity"}:
                raise McpClientError("mcp_compressed_response_rejected")
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > provider.max_http_response_bytes:
                raise McpClientError("mcp_response_too_large")
            response.stream = CappedAsyncByteStream(response.stream)

        timeout = httpx2.Timeout(
            connect=min(10.0, provider.call_timeout_seconds),
            read=provider.call_timeout_seconds,
            write=min(10.0, provider.call_timeout_seconds),
            pool=min(10.0, provider.call_timeout_seconds),
        )
        base_transport = (
            self._http_transport_factory() if self._http_transport_factory is not None else None
        )
        async with httpx2.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
            transport=cast(httpx2.AsyncBaseTransport | None, base_transport),
            trust_env=False,
            event_hooks={"response": [reject_redirect_or_large_response]},
        ) as http_client:
            transport = streamable_http_client(provider.endpoint, http_client=http_client)
            async with Client(
                transport,
                read_timeout_seconds=provider.call_timeout_seconds,
            ) as client:
                yield client


def _embedded_mcp_error_code(error: BaseException) -> str | None:
    if isinstance(error, McpClientError):
        return str(error)
    children = getattr(error, "exceptions", ())
    if isinstance(children, tuple):
        for child in children:
            if isinstance(child, BaseException):
                nested = _embedded_mcp_error_code(child)
                if nested:
                    return nested
    cause = error.__cause__ or error.__context__
    return _embedded_mcp_error_code(cause) if cause is not None else None


__all__ = [
    "HttpTransportFactory",
    "McpCallOutcomeUnknown",
    "McpClient",
    "McpClientError",
    "McpRemoteCallResult",
    "McpRemoteTool",
    "McpSession",
    "McpSessionFactory",
]
