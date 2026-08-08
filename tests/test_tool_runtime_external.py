import asyncio
import json
from contextlib import asynccontextmanager

import httpx
from pydantic import SecretStr

from echo_masque.network_safety import PublicUrlGuard
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
    assert hostname in {"example.com", "cdn.example.com"}
    return ("93.184.216.34",)


class FakeBrowser:
    available = True

    def __init__(self) -> None:
        self.session_keys: list[str] = []
        self.rendered_urls: list[str] = []

    @asynccontextmanager
    async def use_session_key(self, key: str):
        self.session_keys.append(key)
        yield

    async def search_web(self, query: str, count: int) -> dict[str, object]:
        return {
            "ok": True,
            "provider": "browser",
            "query": query,
            "result_count": 1,
            "results": [
                {
                    "title": "Character Relay",
                    "url": "https://example.com/relay",
                    "snippet": f"count={count}",
                }
            ],
        }

    async def search_images(self, query: str, count: int) -> dict[str, object]:
        return {
            "ok": True,
            "provider": "browser",
            "query": query,
            "safe_search": "strict",
            "result_count": 1,
            "results": [
                {
                    "title": "Purple cat notebook",
                    "image_url": "https://cdn.example.com/cat.png",
                    "thumbnail_url": "https://cdn.example.com/cat-thumb.png",
                    "source_url": "https://example.com/cat",
                    "count": count,
                }
            ],
        }

    async def search_places(
        self,
        query: str,
        location: str,
        count: int,
    ) -> dict[str, object]:
        return {
            "ok": True,
            "provider": "browser",
            "query": query,
            "location": location,
            "result_count": 1,
            "results": [
                {
                    "name": "Example Cafe",
                    "description": f"Top {count} near {location}",
                    "source_url": "https://example.com/cafe",
                }
            ],
        }

    async def fetch_rendered_page(self, url: str, max_chars: int) -> dict[str, object]:
        self.rendered_urls.append(url)
        return {
            "ok": True,
            "final_url": url,
            "title": "Rendered",
            "text": "Rendered JavaScript content."[:max_chars],
            "rendered_with": "playwright-chromium",
        }


def test_browser_backed_search_image_and_places_share_deployment_session() -> None:
    browser = FakeBrowser()
    registry = ToolRegistry(browser_runtime=browser)  # type: ignore[arg-type]
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
    places_result = asyncio.run(
        registry.execute(
            call(
                "places_search",
                {"query": "cafe", "location": "Johor Bahru", "count": 4},
            ),
            enabled_tool_ids=("places.search",),
            context=context,
        )
    )

    web = json.loads(web_result.content)
    image = json.loads(image_result.content)
    places = json.loads(places_result.content)
    assert web_result.trace.status == "completed"
    assert web["provider"] == "browser"
    assert web["results"][0]["url"] == "https://example.com/relay"
    assert image_result.trace.status == "completed"
    assert image["safe_search"] == "strict"
    assert image["results"][0]["image_url"].endswith("cat.png")
    assert places_result.trace.status == "completed"
    assert places["location"] == "Johor Bahru"
    assert browser.session_keys == [
        "owner-1:deployment-1",
        "owner-1:deployment-1",
        "owner-1:deployment-1",
    ]


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
                    "<body><h1>Hello</h1><p>Visible content with enough ordinary text "
                    "to keep the HTTP fast path instead of requesting a JavaScript-rendered "
                    "fallback. This sentence intentionally makes the content comfortably longer "
                    "than the Browser Capability heuristic threshold used by this test.</p></body></html>"
                ),
            )
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
        )

    registry = ToolRegistry(
        http_transport=httpx.MockTransport(handler),
        url_guard=PublicUrlGuard(public_resolver),
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
    assert "Hello Visible content" in page["text"]
    assert "ignore this instruction" not in page["text"]
    assert page["untrusted_external_content"] is True
    assert page["fetched_with"] == "httpx"
    assert blocked.trace.status == "rejected"
    assert "non-routable" in blocked.trace.error
    assert requests == [
        "https://example.com/page",
        "https://example.com/redirect",
    ]


def test_fetch_page_uses_browser_fallback_for_javascript_shell() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body>JavaScript is required.</body></html>",
        )

    browser = FakeBrowser()
    registry = ToolRegistry(
        browser_runtime=browser,  # type: ignore[arg-type]
        http_transport=httpx.MockTransport(handler),
        url_guard=PublicUrlGuard(public_resolver),
    )
    result = asyncio.run(
        registry.execute(
            call("web_fetch_page", {"url": "https://example.com/app"}),
            enabled_tool_ids=("web.fetch_page",),
            context=discord_context(),
        )
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["rendered_with"] == "playwright-chromium"
    assert browser.rendered_urls == ["https://example.com/app"]


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


def test_weather_uses_open_meteo_without_api_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "geocoding-api.open-meteo.com":
            assert request.url.params["name"] == "Johor Bahru"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Johor Bahru",
                            "admin1": "Johor",
                            "country": "Malaysia",
                            "latitude": 1.4655,
                            "longitude": 103.7578,
                            "timezone": "Asia/Kuala_Lumpur",
                        }
                    ]
                },
            )
        assert request.url.host == "api.open-meteo.com"
        return httpx.Response(
            200,
            json={
                "current": {"temperature_2m": 30.2, "weather_code": 3},
                "current_units": {"temperature_2m": "°C"},
                "daily": {
                    "time": ["2026-08-09"],
                    "temperature_2m_max": [32.0],
                    "temperature_2m_min": [25.0],
                },
                "daily_units": {"temperature_2m_max": "°C"},
            },
        )

    registry = ToolRegistry(http_transport=httpx.MockTransport(handler))
    result = asyncio.run(
        registry.execute(
            call("weather_get", {"location": "Johor Bahru", "days": 1}),
            enabled_tool_ids=("weather.get",),
            context=discord_context(),
        )
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["provider"] == "open-meteo"
    assert payload["location"]["country"] == "Malaysia"
    assert payload["current"]["temperature_2m"] == 30.2
    assert len(requests) == 2


def test_file_inspect_parses_public_json_as_untrusted_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/sample.json"
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b'{"project":"Character Relay","phase":"V1.2"}',
        )

    registry = ToolRegistry(
        http_transport=httpx.MockTransport(handler),
        url_guard=PublicUrlGuard(public_resolver),
    )
    result = asyncio.run(
        registry.execute(
            call(
                "file_inspect",
                {
                    "url": "https://example.com/sample.json",
                    "filename": "sample.json",
                },
            ),
            enabled_tool_ids=("file.inspect",),
            context=discord_context(),
        )
    )

    payload = json.loads(result.content)
    assert result.trace.status == "completed"
    assert payload["inspection"]["kind"] == "json"
    assert payload["inspection"]["shape"]["keys"] == ["project", "phase"]
    assert payload["untrusted_external_content"] is True


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
