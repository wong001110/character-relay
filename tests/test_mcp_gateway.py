"""Focused controlled-MCP gateway contracts without a networked MCP server."""

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from echo_masque.mcp_client import (
    McpCallOutcomeUnknown,
    McpClient,
    McpClientError,
    McpRemoteCallResult,
)
from echo_masque.mcp_config import McpDeploymentGrant, McpProviderConfig
from echo_masque.mcp_gateway import McpGateway
from echo_masque.network_safety import PublicUrlGuard
from echo_masque.tool_external import ExternalToolFailed, ExternalToolRejected
from echo_masque.tool_runtime import ToolExecutionContext


def _provider(*, grants: tuple[McpDeploymentGrant, ...] | None = None) -> McpProviderConfig:
    return McpProviderConfig(
        id="catalog",
        endpoint="https://mcp.example.test/tools",
        deployment_grants=grants
        or (
            McpDeploymentGrant(
                owner_id="owner-a",
                deployment_id="deployment-a",
                tool_names=("find_records", "create_image"),
            ),
        ),
    )


def _context(
    *,
    owner_id: str = "owner-a",
    deployment_id: str = "deployment-a",
) -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id=owner_id,
        deployment_id=deployment_id,
        character_card_id="card-a",
        platform="discord",
    )


class FakeMcpClient:
    def __init__(self, *, tools: list[object], result: McpRemoteCallResult | None = None) -> None:
        self.tools = tools
        self.result = result or McpRemoteCallResult(
            is_error=False,
            content=(SimpleNamespace(type="text", text="Found one record."),),
            structured_content={"count": 1},
        )
        self.list_calls = 0
        self.call_calls: list[tuple[str, dict[str, object]]] = []
        self.raise_on_call: Exception | None = None

    async def list_tools(self, *_: object) -> tuple[object, ...]:
        self.list_calls += 1
        return tuple(self.tools)

    async def call_tool(
        self,
        *_: object,
        tool_name: str,
        arguments: dict[str, object],
    ) -> McpRemoteCallResult:
        self.call_calls.append((tool_name, arguments))
        if self.raise_on_call is not None:
            raise self.raise_on_call
        return self.result


def _tool(name: str, schema: dict[str, object] | None = None) -> object:
    return SimpleNamespace(
        name=name,
        title=name.replace("_", " ").title(),
        description=f"Use {name} to search public records.",
        input_schema=schema
        or {
            "type": "object",
            "properties": {"query": {"type": "string", "maxLength": 200}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )


def _gateway(fake: FakeMcpClient, **kwargs: object) -> McpGateway:
    return McpGateway(
        providers=(_provider(),),
        client_factory=lambda _: fake,  # type: ignore[arg-type]
        **kwargs,
    )


def test_config_rejects_wildcard_grants_and_non_exact_endpoint() -> None:
    with pytest.raises(ValueError, match="wildcards"):
        McpDeploymentGrant(owner_id="owner", deployment_id="deployment", tool_names=("*",))
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        McpProviderConfig(id="catalog", endpoint="https://user:token@example.test/mcp")
    with pytest.raises(ValueError, match="maximum image"):
        McpProviderConfig(
            id="catalog",
            endpoint="https://mcp.example.test/mcp",
            max_image_bytes=16_384,
            max_http_response_bytes=16_384,
        )


def test_discover_returns_at_most_three_granted_descriptors() -> None:
    fake = FakeMcpClient(tools=[_tool("find_records"), _tool("not_granted")])
    payload = json.loads(asyncio.run(_gateway(fake).discover({"query": "records"}, _context())))

    assert payload["ok"] is True
    assert payload["external_data_untrusted"] is True
    assert [item["tool_name"] for item in payload["tools"]] == ["find_records"]
    assert len(payload["tools"]) <= 3
    assert len(payload["tools"][0]["schema_fingerprint"]) == 64


def test_discover_skips_a_schema_that_would_exceed_response_budget() -> None:
    oversized_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "title": "x" * 15_500},
        },
    }
    fake = FakeMcpClient(tools=[_tool("find_records", oversized_schema), _tool("create_image")])
    payload = json.loads(asyncio.run(_gateway(fake).discover({"query": "records"}, _context())))

    assert payload["omitted_schema_count"] == 1
    assert payload["omitted_reason"] == "schema_response_budget"
    assert [item["tool_name"] for item in payload["tools"]] == ["create_image"]
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= 16_384


@pytest.mark.parametrize(
    "owner_id,deployment_id",
    [
        ("owner-b", "deployment-a"),
        ("owner-a", "deployment-b"),
        ("owner-b", "deployment-b"),
    ],
)
def test_discover_cannot_cross_owner_deployment_grant(owner_id, deployment_id) -> None:
    fake = FakeMcpClient(tools=[_tool("find_records")])
    payload = json.loads(
        asyncio.run(
            _gateway(fake).discover(
                {"query": "records"},
                _context(owner_id=owner_id, deployment_id=deployment_id),
            )
        )
    )

    assert payload["tools"] == []
    assert fake.list_calls == 0


def test_current_static_gateway_scope_is_checked_before_progress_or_network() -> None:
    fake = FakeMcpClient(tools=[_tool("find_records")])
    checked: list[str] = []
    gateway = _gateway(
        fake,
        scope_validator=lambda _context, tool_id: checked.append(tool_id),
    )

    asyncio.run(gateway.discover({"query": "records"}, _context()))

    assert checked == ["mcp.discover"]


def test_discover_rejects_duplicate_remote_tool_names() -> None:
    fake = FakeMcpClient(tools=[_tool("find_records"), _tool("find_records")])

    with pytest.raises(ExternalToolFailed, match="duplicate_remote_tool_name"):
        asyncio.run(_gateway(fake).discover({"query": "records"}, _context()))


def test_invoke_revalidates_current_schema_and_grant_before_calling_remote() -> None:
    fake = FakeMcpClient(tools=[_tool("find_records")])
    gateway = _gateway(fake)
    discovered = json.loads(asyncio.run(gateway.discover({"query": "records"}, _context())))
    descriptor = discovered["tools"][0]

    result = json.loads(
        asyncio.run(
            gateway.invoke(
                {
                    "server_id": "catalog",
                    "tool_name": "find_records",
                    "schema_fingerprint": descriptor["schema_fingerprint"],
                    "arguments": {"query": "today"},
                },
                _context(),
            )
        )
    )

    assert result["ok"] is True
    assert result["structured_content"] == {"count": 1}
    assert fake.call_calls == [("find_records", {"query": "today"})]

    with pytest.raises(ExternalToolRejected, match="schema_changed"):
        asyncio.run(
            gateway.invoke(
                {
                    "server_id": "catalog",
                    "tool_name": "find_records",
                    "schema_fingerprint": "0" * 64,
                    "arguments": {"query": "today"},
                },
                _context(),
            )
        )
    assert len(fake.call_calls) == 1


def test_invoke_rejects_arguments_that_do_not_match_remote_schema() -> None:
    fake = FakeMcpClient(tools=[_tool("find_records")])
    gateway = _gateway(fake)
    discovered = json.loads(asyncio.run(gateway.discover({"query": "records"}, _context())))
    descriptor = discovered["tools"][0]

    with pytest.raises(ExternalToolRejected, match="arguments_do_not_match"):
        asyncio.run(
            gateway.invoke(
                {
                    "server_id": "catalog",
                    "tool_name": "find_records",
                    "schema_fingerprint": descriptor["schema_fingerprint"],
                    "arguments": {"other": "not allowed"},
                },
                _context(),
            )
        )
    assert fake.call_calls == []


def test_schema_with_regex_or_combinator_is_not_discoverable() -> None:
    unsafe_schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "pattern": "(a+)+$"}},
    }
    fake = FakeMcpClient(tools=[_tool("find_records", unsafe_schema)])

    payload = json.loads(asyncio.run(_gateway(fake).discover({"query": "records"}, _context())))

    assert payload["tools"] == []


def test_unknown_call_outcome_is_explicit_external_failure() -> None:
    fake = FakeMcpClient(tools=[_tool("find_records")])
    fake.raise_on_call = McpCallOutcomeUnknown("mcp_call_outcome_unknown")
    gateway = _gateway(fake)
    discovered = json.loads(asyncio.run(gateway.discover({"query": "records"}, _context())))
    descriptor = discovered["tools"][0]

    with pytest.raises(ExternalToolFailed, match="mcp_call_outcome_unknown"):
        asyncio.run(
            gateway.invoke(
                {
                    "server_id": "catalog",
                    "tool_name": "find_records",
                    "schema_fingerprint": descriptor["schema_fingerprint"],
                    "arguments": {"query": "today"},
                },
                _context(),
            )
        )


def test_image_is_delivered_once_without_returning_base64_to_model() -> None:
    image = base64.b64encode(b"image-binary").decode("ascii")
    fake = FakeMcpClient(
        tools=[_tool("create_image")],
        result=McpRemoteCallResult(
            is_error=False,
            content=(
                SimpleNamespace(type="image", mime_type="image/png", data=image),
                SimpleNamespace(type="image", mime_type="image/png", data=image),
            ),
            structured_content=None,
        ),
    )
    delivered: list[tuple[str, str]] = []

    async def image_delivery(
        _: ToolExecutionContext, mime_type: str, data_base64: str
    ) -> dict[str, object]:
        delivered.append((mime_type, data_base64))
        return {"artifact_id": "artifact-1"}

    gateway = _gateway(fake, image_delivery=image_delivery)
    discovered = json.loads(asyncio.run(gateway.discover({"query": "image"}, _context())))
    descriptor = discovered["tools"][0]
    result = json.loads(
        asyncio.run(
            gateway.invoke(
                {
                    "server_id": "catalog",
                    "tool_name": "create_image",
                    "schema_fingerprint": descriptor["schema_fingerprint"],
                    "arguments": {"query": "a flower"},
                },
                _context(),
            )
        )
    )

    assert delivered == [("image/png", image)]
    assert result["artifacts"] == [{"artifact_id": "artifact-1"}]
    assert image not in json.dumps(result)


class _PagingSession:
    def __init__(self) -> None:
        self.cursors: list[str | None] = []

    async def list_tools(self, *, cursor: str | None = None) -> object:
        self.cursors.append(cursor)
        if cursor is None:
            return SimpleNamespace(tools=[_tool("one")], next_cursor="second")
        return SimpleNamespace(tools=[_tool("two")], next_cursor=None)

    async def call_tool(self, *_: object, **__: object) -> object:
        raise AssertionError("not used")


def test_client_pages_until_next_cursor_is_none() -> None:
    session = _PagingSession()

    @asynccontextmanager
    async def session_factory(*_: object):
        yield session

    async def resolver(_: str) -> tuple[str, ...]:
        return ("8.8.8.8",)

    client = McpClient(
        url_guard=PublicUrlGuard(resolver),
        session_factory=session_factory,  # type: ignore[arg-type]
    )
    tools = asyncio.run(client.list_tools(_provider(), None))

    assert [item.name for item in tools] == ["one", "two"]
    assert session.cursors == [None, "second"]


def _sdk_provider(*, max_http_response_bytes: int = 100_000) -> McpProviderConfig:
    return McpProviderConfig(
        id="catalog",
        endpoint="https://mcp.example.test/mcp",
        max_image_bytes=16_384,
        max_http_response_bytes=max_http_response_bytes,
        deployment_grants=(
            McpDeploymentGrant(
                owner_id="owner-a",
                deployment_id="deployment-a",
                tool_names=("find_records",),
            ),
        ),
    )


def test_official_sdk_streamable_http_transport_lists_tools() -> None:
    import httpx2
    from mcp.server import MCPServer

    server = MCPServer("fixture")

    @server.tool()
    def find_records(query: str) -> str:
        return query

    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host="mcp.example.test",
    )

    async def resolver(_: str) -> tuple[str, ...]:
        return ("8.8.8.8",)

    client = McpClient(
        url_guard=PublicUrlGuard(resolver),
        http_transport_factory=lambda: httpx2.ASGITransport(
            app=app,
            client=("8.8.8.8", 1234),
        ),
    )

    async def list_from_lifespan() -> tuple[object, ...]:
        async with app.router.lifespan_context(app):
            return await client.list_tools(_sdk_provider(), None)

    tools = asyncio.run(list_from_lifespan())
    assert [item.name for item in tools] == ["find_records"]


def test_official_sdk_rejects_chunked_response_that_exceeds_received_byte_limit() -> None:
    import httpx2

    async def oversized_app(scope: object, receive: object, send: object) -> None:
        del scope
        await receive()  # type: ignore[operator]
        await send(  # type: ignore[operator]
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(  # type: ignore[operator]
            {"type": "http.response.body", "body": b"x" * 100_001, "more_body": False}
        )

    async def resolver(_: str) -> tuple[str, ...]:
        return ("8.8.8.8",)

    client = McpClient(
        url_guard=PublicUrlGuard(resolver),
        http_transport_factory=lambda: httpx2.ASGITransport(app=oversized_app),
    )

    with pytest.raises(McpClientError, match="mcp_response_too_large"):
        asyncio.run(client.list_tools(_sdk_provider(), None))


def test_official_sdk_rejects_malformed_sse_response() -> None:
    import httpx2

    async def malformed_sse_app(scope: object, receive: object, send: object) -> None:
        del scope
        await receive()  # type: ignore[operator]
        await send(  # type: ignore[operator]
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/event-stream")],
            }
        )
        await send(  # type: ignore[operator]
            {"type": "http.response.body", "body": b"data: {not-json}\n\n", "more_body": False}
        )

    async def resolver(_: str) -> tuple[str, ...]:
        return ("8.8.8.8",)

    client = McpClient(
        url_guard=PublicUrlGuard(resolver),
        http_transport_factory=lambda: httpx2.ASGITransport(app=malformed_sse_app),
    )

    with pytest.raises(McpClientError):
        asyncio.run(client.list_tools(_sdk_provider(), None))
