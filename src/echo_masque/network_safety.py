"""Network-safety helpers shared by browser and HTTP-backed Tools."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from time import monotonic
from urllib.parse import urlparse


type HostResolver = Callable[[str], Awaitable[tuple[str, ...]]]


class PublicUrlRejected(ValueError):
    """Raised when a proposed URL is not safe for external Tool access."""


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

        try:
            ipaddress.ip_address(hostname)
            addresses = (hostname,)
        except ValueError:
            addresses = await self._resolve_cached(hostname)
        if not addresses:
            raise PublicUrlRejected("Hostname did not resolve to a public address.")
        for raw_address in addresses:
            try:
                address = ipaddress.ip_address(raw_address.split("%", maxsplit=1)[0])
            except ValueError as exc:
                raise PublicUrlRejected("Hostname resolved to an invalid address.") from exc
            if not address.is_global:
                raise PublicUrlRejected(
                    "Private, local, reserved, or non-routable URLs are not allowed."
                )
        return url

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
