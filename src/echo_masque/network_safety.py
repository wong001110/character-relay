"""Network-safety helpers shared by browser and HTTP-backed Tools."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import ParseResult, urlparse

import httpx
import httpcore


type HostResolver = Callable[[str], Awaitable[tuple[str, ...]]]


class PublicUrlRejected(ValueError):
    """Raised when a proposed URL is not safe for external Tool access."""


@dataclass(frozen=True, slots=True)
class PublicConnectionTarget:
    """A public URL and the literal addresses admitted for one immediate dial.

    This value deliberately has a very short lifetime: callers use one of ``addresses`` for the
    next socket connection while retaining ``hostname`` for the Host header and TLS SNI.  It is
    therefore stronger than the cache-backed ``validate`` convenience method, which remains for
    non-dial decisions such as result filtering.
    """

    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


async def default_host_resolver(hostname: str) -> tuple[str, ...]:
    def resolve() -> tuple[str, ...]:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        addresses = [str(record[4][0]) for record in records if record[4]]
        return tuple(dict.fromkeys(addresses))

    try:
        return await asyncio.to_thread(resolve)
    except socket.gaierror as exc:
        raise PublicUrlRejected("Hostname could not be resolved.") from exc


class PublicUrlGuard:
    """Reject localhost/private/reserved destinations before Browser or HTTP access."""

    def __init__(
        self,
        resolver: HostResolver | None = None,
        *,
        cache_seconds: int = 300,
    ) -> None:
        self._resolver = resolver or default_host_resolver
        self._cache_seconds = max(1, cache_seconds)
        self._host_cache: dict[str, tuple[float, tuple[str, ...]]] = {}
        self._lock = asyncio.Lock()

    async def validate(self, url: str) -> str:
        _parsed, hostname, _port = self._parse_url(url)
        addresses: tuple[str, ...]
        try:
            ipaddress.ip_address(hostname)
            addresses = (hostname,)
        except ValueError:
            addresses = await self._resolve_cached(hostname)
        self._require_public_addresses(addresses)
        return url

    async def resolve_for_connection(self, url: str) -> PublicConnectionTarget:
        """Resolve and validate an address set for the socket opened by this request.

        Unlike :meth:`validate`, this bypasses the DNS cache and callers must dial one returned
        literal address.  Resolving and then letting another HTTP implementation resolve the
        hostname again would reintroduce the DNS rebinding gap this method is intended to close.
        """

        parsed, hostname, port = self._parse_url(url)
        addresses: tuple[str, ...]
        try:
            ipaddress.ip_address(hostname)
            addresses = (hostname,)
        except ValueError:
            addresses = await self._resolver(hostname)
        normalized = self._require_public_addresses(addresses)
        return PublicConnectionTarget(
            url=url,
            scheme=parsed.scheme,
            hostname=hostname,
            port=port,
            addresses=normalized,
        )

    @staticmethod
    def _parse_url(url: str) -> tuple[ParseResult, str, int]:
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError as exc:
            raise PublicUrlRejected("URL is invalid.") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise PublicUrlRejected("Only public http/https URLs are supported.")
        if parsed.username or parsed.password:
            raise PublicUrlRejected("URLs containing credentials are not allowed.")
        if port is not None and port not in {80, 443}:
            raise PublicUrlRejected("Only standard web ports 80 and 443 are allowed.")

        hostname = parsed.hostname.rstrip(".").casefold()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise PublicUrlRejected("Localhost URLs are not allowed.")
        return parsed, hostname, port or (443 if parsed.scheme == "https" else 80)

    @staticmethod
    def _require_public_addresses(addresses: tuple[str, ...]) -> tuple[str, ...]:
        if not addresses:
            raise PublicUrlRejected("Hostname did not resolve to a public address.")
        normalized: list[str] = []
        for raw_address in addresses:
            try:
                address = ipaddress.ip_address(raw_address.split("%", maxsplit=1)[0])
            except ValueError as exc:
                raise PublicUrlRejected("Hostname resolved to an invalid address.") from exc
            if not address.is_global:
                raise PublicUrlRejected(
                    "Private, local, reserved, or non-routable URLs are not allowed."
                )
            normalized.append(str(address))
        return tuple(dict.fromkeys(normalized))

    async def _resolve_cached(self, hostname: str) -> tuple[str, ...]:
        now = monotonic()
        cached = self._host_cache.get(hostname)
        if cached is not None and cached[0] > now:
            return cached[1]
        async with self._lock:
            now = monotonic()
            cached = self._host_cache.get(hostname)
            if cached is not None and cached[0] > now:
                return cached[1]
            addresses = await self._resolver(hostname)
            self._host_cache[hostname] = (
                now + self._cache_seconds,
                addresses,
            )
            return addresses


class PinnedHttpTransportError(httpx.NetworkError):
    """A direct public-address HTTP transport could not open a safe connection."""


class PinnedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve once and make httpcore dial that public literal address.

    httpcore keeps the request origin unchanged, so it sends the configured Host header and calls
    ``start_tls`` with the original hostname for SNI/certificate verification.  Only the TCP dial
    receives the selected literal IP.  The delegated backend is the installed httpcore AnyIO
    backend (or the compatible ``httpcore2`` backend used by MCP).
    """

    def __init__(self, backend: Any, *, url_guard: PublicUrlGuard) -> None:
        self._backend = backend
        self._url_guard = url_guard

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        target = await self._url_guard.resolve_for_connection(_connection_url(host, port))
        return await self._backend.connect_tcp(
            host=target.addresses[0],
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, *_: Any, **__: Any) -> Any:
        raise PinnedHttpTransportError("Pinned HTTP does not permit Unix-socket connections.")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


def _connection_url(host: str, port: int) -> str:
    """Build a guard input from httpcore's origin without allowing URL syntax injection."""

    if not host or port not in {80, 443}:
        raise PublicUrlRejected("Only standard web ports 80 and 443 are allowed.")
    normalized = host.rstrip(".").casefold()
    if not normalized or any(character in normalized for character in "/?#@"):
        raise PublicUrlRejected("Hostname is invalid.")
    authority = f"[{normalized}]" if ":" in normalized else normalized
    scheme = "https" if port == 443 else "http"
    return f"{scheme}://{authority}:{port}/"


class _HTTPXCoreResponseStream(httpx.AsyncByteStream):
    """Preserve httpcore's streaming body rather than buffering protocol responses."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    async def __aiter__(self):  # type: ignore[no-untyped-def]
        try:
            async for part in self._stream:
                yield part
        except Exception as exc:
            raise _map_httpcore_exception(exc) from exc

    async def aclose(self) -> None:
        if hasattr(self._stream, "aclose"):
            await self._stream.aclose()


class PinnedAsyncHTTPTransport(httpx.AsyncBaseTransport):
    """HTTPX transport using httpcore's parser with literal-IP public TCP dials.

    This intentionally delegates HTTP/1.1, HTTP/2, chunking, compression and response streaming to
    installed HTTPX/httpcore.  Redirect handling remains with each caller; every redirected request
    gets a new connection admission whenever httpcore opens a connection.
    """

    def __init__(
        self,
        *,
        url_guard: PublicUrlGuard | None = None,
        max_connections: int = 10,
        network_backend: Any | None = None,
    ) -> None:
        import httpcore

        self._url_guard = url_guard or PublicUrlGuard()
        self._httpcore = httpcore
        self._pool = httpcore.AsyncConnectionPool(
            max_connections=max(1, max_connections),
            http1=True,
            http2=False,
            network_backend=PinnedAsyncNetworkBackend(
                network_backend or httpcore.AnyIOBackend(),
                url_guard=self._url_guard,
            ),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        core_request = self._httpcore.Request(
            method=request.method,
            url=self._httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            response = await self._pool.handle_async_request(core_request)
        except PublicUrlRejected:
            raise
        except Exception as exc:
            raise _map_httpcore_exception(exc) from exc
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_HTTPXCoreResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


def _map_httpcore_exception(exc: Exception) -> httpx.HTTPError:
    """Translate public httpcore failure classes at the HTTPX boundary."""

    import httpcore

    mapping: tuple[tuple[type[Exception], type[httpx.HTTPError]], ...] = (
        (httpcore.ConnectTimeout, httpx.ConnectTimeout),
        (httpcore.ReadTimeout, httpx.ReadTimeout),
        (httpcore.WriteTimeout, httpx.WriteTimeout),
        (httpcore.PoolTimeout, httpx.PoolTimeout),
        (httpcore.ConnectError, httpx.ConnectError),
        (httpcore.ReadError, httpx.ReadError),
        (httpcore.WriteError, httpx.WriteError),
        (httpcore.ProxyError, httpx.ProxyError),
        (httpcore.UnsupportedProtocol, httpx.UnsupportedProtocol),
        (httpcore.ProtocolError, httpx.ProtocolError),
        (httpcore.TimeoutException, httpx.TimeoutException),
        (httpcore.NetworkError, httpx.NetworkError),
    )
    for source, target in mapping:
        if isinstance(exc, source):
            return target(str(exc))
    return PinnedHttpTransportError("Pinned HTTP transport failed.")
