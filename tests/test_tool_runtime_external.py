import asyncio
import json

import httpx
from pydantic import SecretStr

from echo_masque.providers import ChatToolCall, ChatToolFunctionCall
from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry


def call(name: str, arguments: dict[str, object]) -> ChatToolCall:
    return ChatToolCall(
        id=f"call-{name}",
        function=ChatToolFunctionCall(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


def discord_context(*, trigger_text: str = "") -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="character-1",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        trigger_text=trigger_text,
        initiator_is_bot=False,
    )


async def public_resolver(hostname: str) -> tuple[str, ...]:
    assert hostname == "example.com"
    return ("93.184.216.34",)


def test_web_search_and_image_search_use_brave_with_safe_search() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-Subscription-Token"] == "brave-test-key"
        if request.url.path.endswith("/web/search"):
            assert request.url.params["q"] == "Character Relay"
            assert request.url.params["safesearch"] == "moderate"
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {
                                "title": "Character Relay",
                                "url": "https://example.com/relay",
                                "description": "Current public information.",
                                "age": "1 hour ago",
                            }
                        ]
                    }
                },
            )
        assert request.url.path.endswith("/images/search")
        assert request.url.params["q"] == "purple cat notebook"
        assert request.url.params["safesearch"] == "strict"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Purple cat notebook",
                        "url": "https://example.com/source",
                        "source": "example.com",
                        "properties": {
                            "url": "https://example.com/image.png",
                            "width": 800,
                            "height": 600,
                        },
                        "thumbnail": {"src": "https://example.com/thumb.png"},
                    }
                ]
            },
        )

    registry = ToolRegistry(
        brave_search_api_key=SecretStr("brave-test-key"),
        http_transport=httpx.MockTransport(handler),
    )
    context = discord_context()
    web_result = asyncio.run(
        registry.execute(
            call("web_search", {"query": "Character Relay", "count": 3}),
            enabled_tool_ids=("web.search",),
            context=context,
        )
    )
    image_result = asyncio.run(
        registry.execute(
            call("image_search", {"query": "purple cat notebook", "count": 2}),
            enabled_tool_ids=("image.search",),
            context=context,
        )
    )

    web = json.loads(web_result.content)
    image = json.loads(image_result.content)
    assert web_result.trace.status == "completed"
    assert web["results"][0]["url"] == "https://example.com/relay"
    assert web["untrusted_external_content"] is True
    assert image_result.trace.status == "completed"
    assert image["safe_search"] == "strict"
    assert image["results"][0]["image_url"] == "https://example.com/image.png"
    assert len(requests) == 2


def test_fetch_page_extracts_visible_text_and_blocks_private_redirects() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/page":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=(
                    "<html><head><title>Example Page</title>"
                    "<script>ignore this instruction</script></head>"
                    "<body><h1>Hello</h1><p>Visible content.</p></body></html>"
                ),
            )
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
        )

    registry = ToolRegistry(
        http_transport=httpx.MockTransport(handler),
        host_resolver=public_resolver,
    )
    context = discord_context()
    readable = asyncio.run(
        registry.execute(
            call(
                "web_fetch_page",
                {"url": "https://example.com/page", "max_chars": 1000},
            ),
            enabled_tool_ids=("web.fetch_page",),
            context=context,
        )
    )
    blocked = asyncio.run(
        registry.execute(
            call("web_fetch_page", {"url": "https://example.com/redirect"}),
            enabled_tool_ids=("web.fetch_page",),
            context=context,
        )
    )

    page = json.loads(readable.content)
    assert readable.trace.status == "completed"
    assert page["title"] == "Example Page"
    assert "Hello Visible content." in page["text"]
    assert "ignore this instruction" not in page["text"]
    assert page["untrusted_external_content"] is True
    assert blocked.trace.status == "rejected"
    assert "non-routable" in blocked.trace.error
    assert requests == [
        "https://example.com/page",
        "https://example.com/redirect",
    ]


def test_fetch_page_rejects_private_ip_without_network_request() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="should not run")

    registry = ToolRegistry(http_transport=httpx.MockTransport(handler))
    result = asyncio.run(
        registry.execute(
            call("web_fetch_page", {"url": "http://127.0.0.1/private"}),
            enabled_tool_ids=("web.fetch_page",),
            context=discord_context(),
        )
    )

    assert result.trace.status == "rejected"
    assert called is False


def test_discord_search_messages_is_scoped_to_current_thread() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v10/guilds/guild-1/messages/search"
        assert request.url.params["content"] == "vector db"
        assert request.url.params["channel_id"] == "thread-1"
        assert request.url.params["include_nsfw"] == "false"
        assert request.headers["Authorization"] == "Bot discord-test-token"
        return httpx.Response(
            200,
            json={
                "messages": [
                    [
                        {
                            "hit": True,
                            "id": "message-1",
                            "channel_id": "thread-1",
                            "content": "We discussed vector DB here yesterday.",
                            "timestamp": "2026-08-08T12:00:00+00:00",
                            "author": {
                                "username": "alex",
                                "global_name": "Alex",
                                "bot": False,
                            },
                        }
                    ]
                ]
            },
        )

    registry = ToolRegistry(
        discord_bot_token=SecretStr("discord-test-token"),
        http_transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        registry.execute(
            call("discord_search_messages", {"query": "vector db", "limit": 5}),
            enabled_tool_ids=("discord.search_messages",),
            context=discord_context(),
        )
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["scope"] == "current_thread"
    assert payload["results"][0]["author_name"] == "Alex"
    assert "vector DB" in payload["results"][0]["content"]


def test_discord_create_poll_requires_explicit_human_request_and_current_scope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v10/channels/thread-1/messages"
        assert request.headers["Authorization"] == "Bot discord-test-token"
        body = json.loads(request.content)
        assert body["poll"]["question"]["text"] == "Lunch?"
        assert [item["poll_media"]["text"] for item in body["poll"]["answers"]] == [
            "Ramen",
            "Rice",
        ]
        assert body["allowed_mentions"] == {"parse": []}
        return httpx.Response(
            200,
            json={
                "id": "poll-message-1",
                "channel_id": "thread-1",
                "poll": {"expiry": "2026-08-10T00:00:00+00:00"},
            },
        )

    registry = ToolRegistry(
        discord_bot_token=SecretStr("discord-test-token"),
        http_transport=httpx.MockTransport(handler),
    )
    rejected = asyncio.run(
        registry.execute(
            call(
                "discord_create_poll",
                {"question": "Lunch?", "answers": ["Ramen", "Rice"]},
            ),
            enabled_tool_ids=("discord.create_poll",),
            context=discord_context(trigger_text="What should we eat?"),
        )
    )
    created = asyncio.run(
        registry.execute(
            call(
                "discord_create_poll",
                {
                    "question": "Lunch?",
                    "answers": ["Ramen", "Rice"],
                    "duration_hours": 24,
                },
            ),
            enabled_tool_ids=("discord.create_poll",),
            context=discord_context(
                trigger_text="Please create a poll for what we should eat."
            ),
        )
    )
    limited = asyncio.run(
        registry.execute(
            call(
                "discord_create_poll",
                {"question": "Again?", "answers": ["Yes", "No"]},
            ),
            enabled_tool_ids=("discord.create_poll",),
            context=discord_context(trigger_text="Create another poll."),
            allow_side_effect=False,
        )
    )

    payload = json.loads(created.content)
    assert rejected.trace.status == "rejected"
    assert "explicit poll/vote request" in rejected.trace.error
    assert created.trace.status == "completed"
    assert payload["message_id"] == "poll-message-1"
    assert payload["channel_id"] == "thread-1"
    assert limited.trace.status == "rejected"
    assert limited.trace.error == "side_effect_limit_reached"
    assert len(requests) == 1
