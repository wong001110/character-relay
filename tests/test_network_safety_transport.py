"""Synthetic socket-bound egress checks; no network destinations are contacted."""

from __future__ import annotations

import asyncio

import httpx
import httpx2
import pytest

from echo_masque.mcp_client import _PinnedMcpHTTPTransport
from echo_masque.network_safety import PinnedAsyncHTTPTransport, PublicUrlGuard, PublicUrlRejected


class _Stream:
    def __init__(self, content: bytes) -> None:
        self._content = bytearray(content)
        self.writes: list[bytes] = []
        self.tls_hostname = ""
        self.closed = False

    async def read(self, count: int, timeout: float | None = None) -> bytes:
        del timeout
        result = bytes(self._content[:count])
        del self._content[:count]
        return result

    async def write(self, content: bytes, timeout: float | None = None) -> None:
        del timeout
        self.writes.append(content)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: object,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> _Stream:
        del ssl_context, timeout
        self.tls_hostname = server_hostname or ""
        return self

    def get_extra_info(self, _info: str) -> None:
        return None


class _Backend:
    def __init__(self, stream: _Stream) -> None:
        self.stream = stream
        self.calls: list[dict[str, object]] = []

    async def connect_tcp(self, **kwargs: object) -> _Stream:
        self.calls.append(kwargs)
        return self.stream

    async def connect_unix_socket(self, **_kwargs: object) -> _Stream:
        raise AssertionError("Unix sockets must be rejected")

    async def sleep(self, _seconds: float) -> None:
        return None


def test_pinned_transport_dials_validated_literal_address_and_keeps_hostname_for_tls(
) -> None:
    stream = _Stream(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
        b"Content-Length: 2\r\n\r\nok"
    )
    backend = _Backend(stream)

    async def resolver(hostname: str) -> tuple[str, ...]:
        assert hostname == "provider.example.test"
        return ("93.184.216.34",)

    async def scenario() -> None:
        transport = PinnedAsyncHTTPTransport(
            url_guard=PublicUrlGuard(resolver),
            network_backend=backend,
        )
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            response = await client.get("https://provider.example.test/v1/models")
        assert response.text == "ok"

    asyncio.run(scenario())

    assert backend.calls[0]["host"] == "93.184.216.34"
    assert stream.tls_hostname == "provider.example.test"
    assert b"Host: provider.example.test\r\n" in stream.writes[0]
    assert b"GET /v1/models HTTP/1.1\r\n" in stream.writes[0]
    assert stream.closed


def test_pinned_transport_rejects_private_resolution_before_opening_socket(
) -> None:
    backend = _Backend(_Stream(b""))

    async def resolver(_hostname: str) -> tuple[str, ...]:
        return ("127.0.0.1",)

    async def scenario() -> None:
        transport = PinnedAsyncHTTPTransport(
            url_guard=PublicUrlGuard(resolver),
            network_backend=backend,
        )
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            with pytest.raises(PublicUrlRejected):
                await client.get("https://unsafe.example.test/private")

    asyncio.run(scenario())
    assert backend.calls == []


def test_mcp_httpx2_adapter_preserves_the_httpcore_stream_and_pinned_dial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _Stream(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    backend = _Backend(stream)
    monkeypatch.setattr("httpcore2.AnyIOBackend", lambda: backend)

    async def resolver(hostname: str) -> tuple[str, ...]:
        assert hostname == "mcp.example.test"
        return ("93.184.216.34",)

    async def scenario() -> None:
        transport = _PinnedMcpHTTPTransport(
            httpx2,
            url_guard=PublicUrlGuard(resolver),
            max_response_bytes=1024,
        )
        response = await transport.handle_async_request(
            httpx2.Request("GET", "https://mcp.example.test/tools")
        )
        assert await response.aread() == b"ok"
        await transport.aclose()

    asyncio.run(scenario())
    assert backend.calls[0]["host"] == "93.184.216.34"
    assert stream.tls_hostname == "mcp.example.test"
