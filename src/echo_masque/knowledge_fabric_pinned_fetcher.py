"""Pinned-DNS HTTPS transport for the bounded Knowledge Fabric worker boundary.

This module intentionally has no scheduler, proxy, credential, redirect, or Tool Runtime
integration.  A resolver returns every address candidate once; the fetcher rejects the whole
request unless every candidate is public, then hands exactly one literal address to its dial
transport.  The original hostname is retained separately for HTTP Host and TLS SNI/certificate
verification.
"""

from __future__ import annotations

import asyncio
import ipaddress
import ssl
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlsplit

from echo_masque.knowledge_fabric_external_policy import canonical_public_https_locator
from echo_masque.knowledge_fabric_website_sync import WebsiteFetchResponse

PINNED_HTTPS_MAX_RESPONSE_BYTES = 1_048_576
_MAX_RESPONSE_HEADER_BYTES = 32_768
_MAX_RESPONSE_HEADER_COUNT = 100
_ALLOWED_REQUEST_HEADERS = frozenset({"accept", "if-none-match", "if-modified-since"})

type PinnedHostResolver = Callable[[str], Awaitable[tuple[str, ...]]]


class PinnedHttpsFetchError(ValueError):
    """A bounded failure category; raw network/provider detail is deliberately not exposed."""

    _CODES = frozenset(
        {
            "source_rejected",
            "dns_failed",
            "dns_rejected",
            "connect_failed",
            "tls_failed",
            "protocol_rejected",
            "response_too_large",
        }
    )

    def __init__(self, code: str) -> None:
        if code not in self._CODES:
            raise ValueError("Pinned HTTPS fetch error code is invalid.")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PinnedHttpsDialRequest:
    """The resolver-selected literal destination and separate hostname verification identity."""

    dial_address: str
    server_hostname: str
    request_target: str
    headers: Mapping[str, str]
    max_response_bytes: int


class PinnedHttpsDialTransport(Protocol):
    """One literal-IP HTTPS exchange, supplied explicitly to preserve testability."""

    async def fetch(self, request: PinnedHttpsDialRequest) -> WebsiteFetchResponse: ...


class PinnedPublicHttpsFetcher:
    """Resolve once, validate every candidate, and fetch exactly one canonical HTTPS page."""

    def __init__(
        self,
        *,
        resolver: PinnedHostResolver,
        dial_transport: PinnedHttpsDialTransport,
    ) -> None:
        self._resolver = resolver
        self._dial_transport = dial_transport

    async def fetch(self, *, url: str, headers: Mapping[str, str]) -> WebsiteFetchResponse:
        """Fetch one page without proxy discovery, redirects, credentials, or repeat DNS lookup."""

        canonical_url = self._canonical_url(url)
        request_headers = self._safe_request_headers(headers)
        parsed = urlsplit(canonical_url)
        hostname = parsed.hostname
        if hostname is None:  # canonical_public_https_locator already rejects this; retain defence.
            raise PinnedHttpsFetchError("source_rejected")

        addresses = await self._resolve_public_addresses(hostname)
        try:
            response = await self._dial_transport.fetch(
                PinnedHttpsDialRequest(
                    dial_address=addresses[0],
                    server_hostname=hostname,
                    request_target=_request_target(parsed.path),
                    headers=request_headers,
                    max_response_bytes=PINNED_HTTPS_MAX_RESPONSE_BYTES,
                )
            )
        except PinnedHttpsFetchError:
            raise
        except Exception:
            raise PinnedHttpsFetchError("connect_failed") from None
        if len(response.content) > PINNED_HTTPS_MAX_RESPONSE_BYTES:
            raise PinnedHttpsFetchError("response_too_large")
        return response

    @staticmethod
    def _canonical_url(url: str) -> str:
        try:
            canonical_url = canonical_public_https_locator(url)
        except ValueError:
            raise PinnedHttpsFetchError("source_rejected") from None
        if canonical_url != url:
            raise PinnedHttpsFetchError("source_rejected")
        return canonical_url

    @staticmethod
    def _safe_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
        safe_headers: dict[str, str] = {}
        for name, value in headers.items():
            normalized_name = name.casefold()
            if (
                normalized_name not in _ALLOWED_REQUEST_HEADERS
                or not value
                or normalized_name in safe_headers
            ):
                raise PinnedHttpsFetchError("source_rejected")
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise PinnedHttpsFetchError("source_rejected")
            safe_headers[normalized_name] = value
        return safe_headers

    async def _resolve_public_addresses(self, hostname: str) -> tuple[str, ...]:
        try:
            literal_address = ipaddress.ip_address(hostname)
        except ValueError:
            try:
                candidates = await self._resolver(hostname)
            except Exception:
                raise PinnedHttpsFetchError("dns_failed") from None
        else:
            candidates = (str(literal_address),)
        if not candidates:
            raise PinnedHttpsFetchError("dns_rejected")

        addresses: list[str] = []
        for candidate in candidates:
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                raise PinnedHttpsFetchError("dns_rejected") from None
            if not address.is_global:
                raise PinnedHttpsFetchError("dns_rejected")
            addresses.append(str(address))
        return tuple(dict.fromkeys(addresses))


class AsyncioPinnedHttpsDialTransport:
    """Direct HTTP/1.1-over-TLS transport with no proxy/environment configuration path.

    The caller supplies the timeout because sync policy owns operational timing; this transport
    does not invent a Fabric scheduling/configuration field.  Its TLS context must retain hostname
    verification and certificate validation, or construction fails closed.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Pinned HTTPS timeout must be positive.")
        context = ssl_context or ssl.create_default_context()
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("Pinned HTTPS TLS verification cannot be disabled.")
        self._timeout_seconds = timeout_seconds
        self._ssl_context = context

    async def fetch(self, request: PinnedHttpsDialRequest) -> WebsiteFetchResponse:
        """Dial the literal address while verifying TLS for the registered hostname."""

        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(
                    host=request.dial_address,
                    port=443,
                    ssl=self._ssl_context,
                    server_hostname=request.server_hostname,
                )
                try:
                    writer.write(_http_request_bytes(request))
                    await writer.drain()
                    return await _read_http_response(reader, request.max_response_bytes)
                finally:
                    writer.close()
                    with suppress(ConnectionError, OSError):
                        await writer.wait_closed()
        except PinnedHttpsFetchError:
            raise
        except ssl.SSLError:
            raise PinnedHttpsFetchError("tls_failed") from None
        except (TimeoutError, ConnectionError, OSError):
            raise PinnedHttpsFetchError("connect_failed") from None
        except Exception:
            raise PinnedHttpsFetchError("connect_failed") from None


def _request_target(path: str) -> str:
    """Produce one origin-form target without allowing locator text into HTTP framing."""

    return quote(path or "/", safe="/%:@!$&'()*+,;=-._~")


def _http_request_bytes(request: PinnedHttpsDialRequest) -> bytes:
    lines = [
        f"GET {request.request_target} HTTP/1.1",
        f"Host: {request.server_hostname}",
        "Connection: close",
    ]
    lines.extend(f"{name}: {value}" for name, value in request.headers.items())
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


async def _read_http_response(
    reader: asyncio.StreamReader,
    max_response_bytes: int,
) -> WebsiteFetchResponse:
    status_line = await _read_response_line(reader)
    try:
        _protocol, raw_status, _reason = status_line.split(" ", maxsplit=2)
        status_code = int(raw_status)
    except (TypeError, ValueError):
        raise PinnedHttpsFetchError("protocol_rejected") from None
    if not 100 <= status_code <= 599:
        raise PinnedHttpsFetchError("protocol_rejected")

    headers: dict[str, str] = {}
    total_header_bytes = len(status_line) + 2
    for _ in range(_MAX_RESPONSE_HEADER_COUNT):
        line = await _read_response_line(reader)
        total_header_bytes += len(line) + 2
        if total_header_bytes > _MAX_RESPONSE_HEADER_BYTES:
            raise PinnedHttpsFetchError("protocol_rejected")
        if not line:
            break
        if ":" not in line:
            raise PinnedHttpsFetchError("protocol_rejected")
        raw_name, raw_value = line.split(":", maxsplit=1)
        name = raw_name.strip().casefold()
        value = raw_value.strip()
        if not name or name in headers:
            raise PinnedHttpsFetchError("protocol_rejected")
        headers[name] = value
    else:
        raise PinnedHttpsFetchError("protocol_rejected")

    transfer_encoding = headers.get("transfer-encoding", "").casefold()
    content_length = headers.get("content-length")
    if transfer_encoding and content_length is not None:
        raise PinnedHttpsFetchError("protocol_rejected")
    if transfer_encoding:
        if transfer_encoding != "chunked":
            raise PinnedHttpsFetchError("protocol_rejected")
        content = await _read_chunked_body(reader, max_response_bytes)
    elif content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            raise PinnedHttpsFetchError("protocol_rejected") from None
        if declared_length < 0:
            raise PinnedHttpsFetchError("protocol_rejected")
        if declared_length > max_response_bytes:
            raise PinnedHttpsFetchError("response_too_large")
        try:
            content = await reader.readexactly(declared_length)
        except asyncio.IncompleteReadError:
            raise PinnedHttpsFetchError("protocol_rejected") from None
    else:
        content = await _read_until_eof(reader, max_response_bytes)
    return WebsiteFetchResponse(status_code=status_code, content=content, headers=headers)


async def _read_response_line(reader: asyncio.StreamReader) -> str:
    try:
        raw_line = await reader.readline()
    except ValueError:
        raise PinnedHttpsFetchError("protocol_rejected") from None
    if not raw_line.endswith(b"\r\n"):
        raise PinnedHttpsFetchError("protocol_rejected")
    try:
        return raw_line[:-2].decode("iso-8859-1")
    except UnicodeDecodeError:
        raise PinnedHttpsFetchError("protocol_rejected") from None


async def _read_chunked_body(reader: asyncio.StreamReader, max_response_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        raw_size = await _read_response_line(reader)
        try:
            chunk_size = int(raw_size.split(";", maxsplit=1)[0], 16)
        except ValueError:
            raise PinnedHttpsFetchError("protocol_rejected") from None
        if chunk_size < 0 or total + chunk_size > max_response_bytes:
            raise PinnedHttpsFetchError("response_too_large")
        if chunk_size == 0:
            while True:
                trailer = await _read_response_line(reader)
                if not trailer:
                    return b"".join(chunks)
                if ":" not in trailer:
                    raise PinnedHttpsFetchError("protocol_rejected")
        try:
            chunk = await reader.readexactly(chunk_size)
            terminator = await reader.readexactly(2)
        except asyncio.IncompleteReadError:
            raise PinnedHttpsFetchError("protocol_rejected") from None
        if terminator != b"\r\n":
            raise PinnedHttpsFetchError("protocol_rejected")
        chunks.append(chunk)
        total += chunk_size


async def _read_until_eof(reader: asyncio.StreamReader, max_response_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await reader.read(min(65_536, max_response_bytes - total + 1))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_response_bytes:
            raise PinnedHttpsFetchError("response_too_large")
        chunks.append(chunk)


__all__ = [
    "PINNED_HTTPS_MAX_RESPONSE_BYTES",
    "AsyncioPinnedHttpsDialTransport",
    "PinnedHostResolver",
    "PinnedHttpsDialRequest",
    "PinnedHttpsDialTransport",
    "PinnedHttpsFetchError",
    "PinnedPublicHttpsFetcher",
]
