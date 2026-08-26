from __future__ import annotations

import asyncio
import ssl
from collections.abc import Mapping

import pytest

from echo_masque.knowledge_fabric_pinned_fetcher import (
    PINNED_HTTPS_MAX_RESPONSE_BYTES,
    AsyncioPinnedHttpsDialTransport,
    PinnedHttpsDialRequest,
    PinnedHttpsFetchError,
    PinnedPublicHttpsFetcher,
)
from echo_masque.knowledge_fabric_website_sync import WebsiteFetchResponse


class FakeDialTransport:
    def __init__(self, response: WebsiteFetchResponse) -> None:
        self.response = response
        self.requests: list[PinnedHttpsDialRequest] = []

    async def fetch(self, request: PinnedHttpsDialRequest) -> WebsiteFetchResponse:
        self.requests.append(request)
        return self.response


def test_pinned_fetcher_dials_one_selected_literal_ip_but_keeps_hostname_for_tls_and_host() -> None:
    resolver_calls: list[str] = []

    async def resolver(hostname: str) -> tuple[str, ...]:
        resolver_calls.append(hostname)
        return ("93.184.216.34", "2606:4700:4700::1111")

    transport = FakeDialTransport(
        WebsiteFetchResponse(200, b"public body", {"content-type": "text/plain"})
    )
    fetcher = PinnedPublicHttpsFetcher(resolver=resolver, dial_transport=transport)

    response = asyncio.run(
        fetcher.fetch(
            url="https://example.test/guide",
            headers={"Accept": "text/plain", "If-None-Match": '"v1"'},
        )
    )

    assert response.content == b"public body"
    assert resolver_calls == ["example.test"]
    assert transport.requests == [
        PinnedHttpsDialRequest(
            dial_address="93.184.216.34",
            server_hostname="example.test",
            request_target="/guide",
            headers={"accept": "text/plain", "if-none-match": '"v1"'},
            max_response_bytes=PINNED_HTTPS_MAX_RESPONSE_BYTES,
        )
    ]


@pytest.mark.parametrize(
    ("url", "headers"),
    [
        ("http://example.test/guide", {}),
        ("https://EXAMPLE.test/guide", {}),
        ("https://example.test/guide?secret=value", {}),
        ("https://user:password@example.test/guide", {}),
        ("https://example.test:443/guide", {}),
        ("https://example.test/guide", {"Authorization": "secret"}),
        ("https://example.test/guide", {"Accept": "text/plain\r\nCookie: secret"}),
    ],
)
def test_pinned_fetcher_rejects_noncanonical_or_credential_bearing_requests_before_dns(
    url: str,
    headers: Mapping[str, str],
) -> None:
    async def resolver(_hostname: str) -> tuple[str, ...]:
        raise AssertionError("DNS must not run for rejected input")

    transport = FakeDialTransport(WebsiteFetchResponse(200, b"body", {}))
    fetcher = PinnedPublicHttpsFetcher(resolver=resolver, dial_transport=transport)

    with pytest.raises(PinnedHttpsFetchError, match=r"^source_rejected$"):
        asyncio.run(fetcher.fetch(url=url, headers=headers))
    assert transport.requests == []


@pytest.mark.parametrize(
    "candidates",
    [
        (),
        ("93.184.216.34", "127.0.0.1"),
        ("10.0.0.7",),
        ("not-an-address",),
    ],
)
def test_pinned_fetcher_requires_every_resolved_candidate_to_be_global(
    candidates: tuple[str, ...],
) -> None:
    async def resolver(_hostname: str) -> tuple[str, ...]:
        return candidates

    transport = FakeDialTransport(WebsiteFetchResponse(200, b"body", {}))
    fetcher = PinnedPublicHttpsFetcher(resolver=resolver, dial_transport=transport)

    with pytest.raises(PinnedHttpsFetchError, match=r"^dns_rejected$"):
        asyncio.run(fetcher.fetch(url="https://example.test/", headers={}))
    assert transport.requests == []


def test_pinned_fetcher_maps_resolver_and_response_cap_failures_without_provider_detail() -> None:
    async def failing_resolver(_hostname: str) -> tuple[str, ...]:
        raise RuntimeError("private resolver detail")

    transport = FakeDialTransport(WebsiteFetchResponse(200, b"body", {}))
    fetcher = PinnedPublicHttpsFetcher(resolver=failing_resolver, dial_transport=transport)
    with pytest.raises(PinnedHttpsFetchError, match=r"^dns_failed$") as resolver_error:
        asyncio.run(fetcher.fetch(url="https://example.test/", headers={}))
    assert "private resolver detail" not in str(resolver_error.value)

    async def resolver(_hostname: str) -> tuple[str, ...]:
        return ("93.184.216.34",)

    too_large = FakeDialTransport(
        WebsiteFetchResponse(200, b"x" * (PINNED_HTTPS_MAX_RESPONSE_BYTES + 1), {})
    )
    fetcher = PinnedPublicHttpsFetcher(resolver=resolver, dial_transport=too_large)
    with pytest.raises(PinnedHttpsFetchError, match=r"^response_too_large$"):
        asyncio.run(fetcher.fetch(url="https://example.test/", headers={}))

    redirect = FakeDialTransport(
        WebsiteFetchResponse(302, b"", {"location": "https://different.test/"})
    )
    fetcher = PinnedPublicHttpsFetcher(resolver=resolver, dial_transport=redirect)
    assert asyncio.run(fetcher.fetch(url="https://example.test/", headers={})).status_code == 302
    assert len(redirect.requests) == 1


class FakeReader:
    def __init__(self, response: bytes) -> None:
        self._response = bytearray(response)

    async def readline(self) -> bytes:
        newline = self._response.find(b"\n")
        if newline < 0:
            result = bytes(self._response)
            self._response.clear()
            return result
        result = bytes(self._response[: newline + 1])
        del self._response[: newline + 1]
        return result

    async def readexactly(self, count: int) -> bytes:
        if len(self._response) < count:
            partial = bytes(self._response)
            self._response.clear()
            raise asyncio.IncompleteReadError(partial=partial, expected=count)
        result = bytes(self._response[:count])
        del self._response[:count]
        return result

    async def read(self, count: int) -> bytes:
        result = bytes(self._response[:count])
        del self._response[:count]
        return result


class FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, content: bytes) -> None:
        self.writes.append(content)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def test_asyncio_transport_dials_literal_ip_and_uses_original_hostname_for_sni_and_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    writer = FakeWriter()

    async def open_connection(**kwargs: object) -> tuple[FakeReader, FakeWriter]:
        calls.append(kwargs)
        return (
            FakeReader(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok"
            ),
            writer,
        )

    monkeypatch.setattr(
        "echo_masque.knowledge_fabric_pinned_fetcher.asyncio.open_connection", open_connection
    )
    transport = AsyncioPinnedHttpsDialTransport(timeout_seconds=1)

    response = asyncio.run(
        transport.fetch(
            PinnedHttpsDialRequest(
                dial_address="93.184.216.34",
                server_hostname="example.test",
                request_target="/guide",
                headers={"accept": "text/plain"},
                max_response_bytes=PINNED_HTTPS_MAX_RESPONSE_BYTES,
            )
        )
    )

    assert response == WebsiteFetchResponse(
        200,
        b"ok",
        {"content-type": "text/plain", "content-length": "2"},
    )
    assert calls == [
        {
            "host": "93.184.216.34",
            "port": 443,
            "ssl": transport._ssl_context,
            "server_hostname": "example.test",
        }
    ]
    assert writer.writes == [
        (
            b"GET /guide HTTP/1.1\r\nHost: example.test\r\nConnection: close\r\n"
            b"accept: text/plain\r\n\r\n"
        )
    ]
    assert writer.closed


def test_asyncio_transport_rejects_insecure_tls_context_and_oversize_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insecure = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    insecure.check_hostname = False
    insecure.verify_mode = ssl.CERT_NONE
    with pytest.raises(ValueError, match="TLS verification cannot be disabled"):
        AsyncioPinnedHttpsDialTransport(timeout_seconds=1, ssl_context=insecure)

    reader = FakeReader(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + b"100001\r\n")
    writer = FakeWriter()

    async def open_connection(**_kwargs: object) -> tuple[FakeReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(
        "echo_masque.knowledge_fabric_pinned_fetcher.asyncio.open_connection", open_connection
    )
    transport = AsyncioPinnedHttpsDialTransport(timeout_seconds=1)
    with pytest.raises(PinnedHttpsFetchError, match=r"^response_too_large$"):
        asyncio.run(
            transport.fetch(
                PinnedHttpsDialRequest(
                    dial_address="93.184.216.34",
                    server_hostname="example.test",
                    request_target="/",
                    headers={},
                    max_response_bytes=PINNED_HTTPS_MAX_RESPONSE_BYTES,
                )
            )
        )
