#!/usr/bin/env python3
"""Verify Room Companion with a built Portal and an isolated, real local API.

Run ``cd web && npm run build`` first, then from the repository root:

  .venv/bin/python scripts/verify_room_companion.py --chromium /usr/bin/chromium

Requires Python Playwright and Chromium. The script starts the production API/UI
entry point on an ephemeral loopback port and creates a temporary SQLite database.
Only synthetic credentials, sources and connector receipts are used. Native SSE,
React, stylesheet loading, clicks and keyboard input are exercised. No Discord
webhook, deployed API, provider or external website is contacted. Headless browser
evidence does not establish desktop always-on-top behavior or Dots/Gemini usability.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx
import uvicorn
from cryptography.fernet import Fernet
from playwright.sync_api import (
    APIResponse,
    Browser,
    BrowserContext,
    Page,
    Route,
    expect,
    sync_playwright,
)
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.config import Settings

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "companion-browser@example.invalid"
PASSWORD = "SyntheticCompanionPassphrase2026!"
CONNECTOR_SECRET = "synthetic-companion-connector-secret"
GUILD_ID = "910000000000000001"
CHANNEL_ID = "910000000000000002"
NOW = datetime.now(UTC)

# Observe native constructors/close calls; never synthesize stream events or snapshots.
OBSERVE_STREAMS = """(() => {
  const Native = window.EventSource;
  const stats = window.__roomStreams = {created: 0, active: 0, maxActive: 0, entries: []};
  window.EventSource = class extends Native {
    constructor(url, options) {
      super(url, options);
      const entry = {url: String(url), closed: false};
      stats.entries.push(entry);
      stats.created++; stats.active++;
      stats.maxActive = Math.max(stats.maxActive, stats.active);
      const close = this.close.bind(this);
      this.close = () => {
        if (!entry.closed) { entry.closed = true; stats.active--; }
        return close();
      };
    }
  };
})();"""


def isolated_settings(path: Path) -> Settings:
    # Explicitly supply every default: neither .env nor injected production bindings
    # can become settings for this disposable application.
    defaults = {
        name: field.get_default(call_default_factory=True)
        for name, field in Settings.model_fields.items()
    }
    defaults.update(
        environment="test",
        database_url=f"sqlite:///{path}",
        legacy_local_user_enabled=False,
        bootstrap_admin_email=EMAIL,
        bootstrap_admin_password=SecretStr(PASSWORD),
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
        connector_shared_secret=SecretStr(CONNECTOR_SECRET),
        browser_tools_enabled=False,
    )
    return Settings(_env_file=None, **defaults)


@contextmanager
def local_application() -> Iterator[httpx.Client]:
    with TemporaryDirectory(prefix="room-companion-") as directory:
        app = create_app(isolated_settings(Path(directory) / "browser.db"))
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        base_url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", log_level="warning", access_log=False)
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=base_url, trust_env=False, timeout=10) as client:
                deadline = time.monotonic() + 15
                while not server.started:
                    if not thread.is_alive() or time.monotonic() > deadline:
                        raise RuntimeError("Isolated local API did not start")
                    time.sleep(0.05)
                assert client.get("/health").is_success
                yield client
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
            app.state.database.engine.dispose()
            if thread.is_alive():
                raise RuntimeError("Isolated local API did not stop")


def api(client: httpx.Client, method: str, path: str, **kwargs: Any) -> Any:
    response = client.request(method, path, **kwargs)
    assert response.is_success, f"{method} {path}: {response.status_code} {response.text}"
    return response.json() if response.content else None


def source(index: int, **changes: Any) -> dict[str, Any]:
    return {
        "message_id": str(920000000000000000 + index),
        "channel_id": CHANNEL_ID,
        "author_id": "synthetic-human",
        "author_display_name": "Synthetic Alice",
        "author_is_bot": False,
        "text": f"Synthetic room message {index}",
        "created_at": (NOW + timedelta(milliseconds=index)).isoformat(),
        **changes,
    }


def observe(client: httpx.Client, connection: str, messages: list[dict[str, Any]]) -> None:
    api(
        client,
        "POST",
        "/api/connectors/discord/rooms/events",
        headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
        json={
            "connection_id": connection,
            "guild_id": GUILD_ID,
            "channel_id": CHANNEL_ID,
            "messages": messages,
            "readable": True,
            "permission_checked_at": datetime.now(UTC).isoformat(),
        },
    )


def seed(client: httpx.Client) -> tuple[str, str, str]:
    base_url = str(client.base_url).rstrip("/")
    api(client, "POST", "/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    connection = api(
        client,
        "POST",
        "/api/connections",
        json={
            "platform": "discord",
            "display_name": "Synthetic offline connector",
            "connection_mode": "managed",
            "external_account_id": "",
            "status": "disconnected",
            "metadata": {},
        },
    )["id"]
    headers = {"Authorization": f"Bearer {CONNECTOR_SECRET}"}
    api(
        client,
        "PUT",
        "/api/connectors/discord/server-catalog",
        headers=headers,
        json={
            "connection_id": connection,
            "servers": [
                {
                    "guild_id": GUILD_ID,
                    "guild_name": "Synthetic server",
                    "channels": [
                        {
                            "id": CHANNEL_ID,
                            "name": "companion",
                            "category_id": "",
                            "category_name": "",
                            "type": "text",
                        }
                    ],
                }
            ],
        },
    )
    room = api(
        client,
        "POST",
        "/api/web-chat/rooms",
        json={
            "connection_id": connection,
            "guild_id": GUILD_ID,
            "channel_id": CHANNEL_ID,
            "name": "Synthetic Companion Room",
        },
    )["id"]
    profile = api(
        client,
        "POST",
        "/api/web-chat/profiles",
        json={
            "display_name": "Synthetic Browser Participant",
        },
    )["id"]
    messages = [source(index) for index in range(1, 7)]
    messages[4] = source(
        5,
        attachments=[
            {
                "attachment_id": "synthetic-image",
                "filename": "synthetic.png",
                "content_type": "image/png",
                "description": "Synthetic fixture thumbnail",
                "url": f"{base_url}/assets/brand/character-relay-favicon.png",
            },
            {
                "attachment_id": "synthetic-file",
                "filename": "synthetic.json",
                "content_type": "application/json",
                "url": f"{base_url}/health",
            },
        ],
    )
    messages[5] = source(
        6,
        reply_to_message_id=source(2)["message_id"],
        text=(
            f"↪ https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}/{source(2)['message_id']}\n"
            "Synthetic structured reply"
        ),
    )
    observe(client, connection, messages)
    api(
        client,
        "PUT",
        f"/api/connectors/discord/web-chat/rooms/{room}/webhook",
        headers=headers,
        json={"connection_id": connection, "webhook_id": "offline-webhook"},
    )
    return connection, room, profile


def login(page: Page, base_url: str, room: str) -> None:
    page.goto(f"{base_url}/rooms?room={room}")
    page.get_by_role("button", name="EN", exact=True).click()
    page.get_by_label("Email", exact=False).fill(EMAIL)
    page.get_by_label("Password", exact=False).fill(PASSWORD)
    page.get_by_role("button", name="Enter studio", exact=True).click()
    expect(page.locator(".web-room-composer textarea")).to_be_visible()
    page.wait_for_function("window.__roomStreams.active === 1")
    expect(page.locator(".web-room-connection.is-connected")).to_be_visible()


def stream_stats(page: Page) -> dict[str, Any]:
    return page.evaluate("window.__roomStreams")


def assert_one_stream(page: Page, created: int) -> None:
    stats = stream_stats(page)
    assert stats["active"] == 1 and stats["maxActive"] == 1, stats
    assert stats["created"] == created, stats


def new_context(browser: Browser, fault: str = "") -> BrowserContext:
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    context.add_init_script(OBSERVE_STREAMS)
    if fault == "absent":
        context.add_init_script(
            "Object.defineProperty(window, 'documentPictureInPicture', {value: undefined});"
        )
    elif fault == "rejected":
        context.add_init_script("""Object.defineProperty(window, 'documentPictureInPicture', {
          value: {requestWindow: async () => {
            throw new DOMException('Synthetic native rejection', 'NotAllowedError');
          }}
        });""")
    return context


def native_journey(
    browser: Browser, client: httpx.Client, room: str, connection: str, profile: str
) -> dict[str, Any]:
    base_url = str(client.base_url).rstrip("/")
    with new_context(browser) as context:
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        login(page, base_url, room)
        created = stream_stats(page)["created"]
        assert page.evaluate("typeof documentPictureInPicture?.requestWindow") == "function", (
            "Native Document PiP unavailable"
        )
        full_input = page.locator(".web-room-composer textarea")
        full_input.fill("Shared draft from full room")
        with context.expect_page() as popup:
            page.get_by_role("button", name="Pop out · Room Companion", exact=True).click()
        pip = popup.value
        pip.on("pageerror", lambda error: errors.append(str(error)))
        root = pip.locator(".room-companion")
        expect(root).to_have_attribute("data-room-id", room)
        expect(root).to_have_attribute("data-connection-state", "connected")
        expect(root).to_have_attribute("data-latest-message-id", source(6)["message_id"])
        expect(pip.locator(".room-companion-message")).to_have_count(5)
        expect(pip.locator(f'[data-message-id="{source(1)["message_id"]}"]')).to_have_count(0)
        reply_node = pip.locator(f'[data-message-id="{source(6)["message_id"]}"]')
        expect(reply_node).to_have_attribute("data-author-id", "synthetic-human")
        expect(reply_node).to_have_attribute("data-reply-to-message-id", source(2)["message_id"])
        expect(reply_node.locator(".room-companion-reply-context")).to_have_attribute(
            "data-reply-message-id", source(2)["message_id"]
        )
        expect(reply_node.locator("p")).to_have_text("Synthetic structured reply")
        expect(
            pip.locator(".room-companion-file").filter(has_text="synthetic.json")
        ).to_be_visible()
        image = pip.get_by_alt_text("Synthetic fixture thumbnail", exact=True)
        image.scroll_into_view_if_needed()
        expect(image).to_be_visible()
        pip.wait_for_function("""() => {
            const image = document.querySelector('.room-companion-file img');
            return image?.complete && image.naturalWidth > 0;
        }""")
        expect(pip.get_by_role("textbox", name="Message", exact=False)).to_have_value(
            "Shared draft from full room"
        )
        pip.get_by_role("textbox", name="Message", exact=False).fill("Shared draft from PiP")
        expect(full_input).to_have_value("Shared draft from PiP")
        try:
            expect(root).to_have_css("display", "flex")
        except AssertionError:
            print(
                json.dumps(
                    pip.evaluate("""() => ({
                head: document.head.innerHTML,
                styles: [...document.styleSheets].map(sheet => ({href: sheet.href})),
                resources: performance.getEntriesByType('resource').map(item => item.name)
            })"""),
                    indent=2,
                )
            )
            raise
        assert pip.locator("link[rel=stylesheet]").count() > 0
        assert_one_stream(page, created)

        # Portal route changes preserve PiP and its shared session, draft and stream.
        page.get_by_role("navigation", name="Primary navigation").get_by_role(
            "button", name="Dashboard", exact=True
        ).click()
        expect(page).to_have_url(f"{base_url}/")
        assert not pip.is_closed()
        expect(pip.get_by_role("textbox", name="Message", exact=False)).to_have_value(
            "Shared draft from PiP"
        )
        assert_one_stream(page, created)

        pip.bring_to_front()
        pip.get_by_role("textbox", name="Message", exact=False).focus()
        assert pip.evaluate("document.hasFocus()")
        observe(client, connection, [source(7)])
        expect(root).to_have_attribute("data-latest-message-id", source(7)["message_id"])
        expect(root).to_have_attribute("data-unread-count", "0")

        # A real other tab is foreground; do not model Gemini or Dots capabilities.
        other = context.new_page()
        other.goto(f"{base_url}/health")
        other.bring_to_front()
        focus_status = {
            "parent": page.evaluate("document.hasFocus()"),
            "pip": pip.evaluate("document.hasFocus()"),
            "other": other.evaluate("document.hasFocus()"),
        }
        # Native PiP may retain OS focus in headless Chromium even after a tab is
        # foregrounded. Minimize is an explicit real control that stops reading.
        pip.get_by_role("button", name="Minimize Room Companion", exact=True).click()
        expect(root).to_have_attribute("data-minimized", "true")
        observe(client, connection, [source(8)])
        expect(root).to_have_attribute("data-latest-message-id", source(8)["message_id"])
        expect(root).to_have_attribute("data-unread-count", "1")
        observe(client, connection, [source(9)])
        expect(root).to_have_attribute("data-unread-count", "2")
        pip.get_by_role("button", name="Expand Room Companion", exact=True).click()
        pip.get_by_role("button", name="2 unread · View latest", exact=True).click()
        expect(root).to_have_attribute("data-unread-count", "0")

        # Real backend acceptance: no connector actually sends to Discord.
        pip.get_by_role("textbox", name="Message", exact=False).fill("Synthetic PiP quick reply")
        with page.expect_response(
            lambda response: (
                response.request.method == "POST"
                and response.url.endswith(f"/rooms/{room}/messages")
            )
        ) as accepted:
            pip.get_by_role("button", name="Send", exact=True).click()
        assert accepted.value.status == 202
        receipt = accepted.value.json()
        assert receipt["profile_id"] == profile and receipt["status"] == "pending"
        assert receipt["text"] == "Synthetic PiP quick reply"
        receipt_node = pip.locator(f'[data-outbox-id="{receipt["id"]}"]')
        expect(receipt_node).to_have_attribute("data-delivery-status", "pending")
        expect(pip.get_by_role("textbox", name="Message", exact=False)).to_have_value("")
        # Exact same ID/payload returns the existing logical send from the real API.
        same = api(
            client,
            "POST",
            f"/api/web-chat/rooms/{room}/messages",
            json={
                "client_message_id": receipt["client_message_id"],
                "profile_id": profile,
                "text": receipt["text"],
                "reply_to_message_id": "",
                "sticker_resource_key": "",
                "attachment_ids": [],
            },
        )
        assert same["id"] == receipt["id"]
        claim = api(
            client,
            "POST",
            f"/api/connectors/discord/web-chat/rooms/{room}/claim",
            headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
            json={
                "connection_id": connection,
                "claim_nonce": "synthetic-browser-claim-0001",
            },
        )
        assert claim["id"] == receipt["id"]
        expect(receipt_node).to_have_attribute("data-delivery-status", "claimed")
        api(
            client,
            "POST",
            f"/api/connectors/discord/web-chat/outbox/{receipt['id']}/ack",
            headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
            json={
                "connection_id": connection,
                "claim_nonce": claim["claim_nonce"],
                "status": "uncertain",
                "reason": "synthetic-browser-receipt",
            },
        )
        expect(receipt_node).to_have_attribute("data-delivery-status", "uncertain")
        expect(receipt_node).to_contain_text("It will not be resent automatically")

        pip.get_by_role("button", name="Open full room", exact=True).click()
        expect(page).to_have_url(f"{base_url}/rooms?room={room}")
        expect(page.locator(".web-room-pending.is-uncertain")).to_be_visible()
        expect(page.locator(".web-room-unread-button")).to_have_count(0)
        assert_one_stream(page, created)
        pip.get_by_role("button", name="Close Room Companion", exact=True).click()
        pip.wait_for_event("close") if not pip.is_closed() else None
        assert_one_stream(page, created)
        observe(client, connection, [source(10)])
        expect(page.locator(f"#web-room-message-{source(10)['message_id']}")).to_be_visible()

        # Logout closes native PiP and discards the only shared stream/state.
        with context.expect_page() as reopened:
            page.get_by_role("button", name="Pop out · Room Companion", exact=True).click()
        pip = reopened.value
        expect(pip.locator(".room-companion")).to_have_attribute("data-room-id", room)
        page.get_by_role("navigation", name="Primary navigation").get_by_role(
            "button", name="Settings", exact=True
        ).click()
        page.get_by_role("button", name="Sign out", exact=True).click()
        expect(page.get_by_role("button", name="Enter studio", exact=True)).to_be_visible()
        page.wait_for_function("window.__roomStreams.active === 0")
        assert pip.is_closed()
        assert errors == [], errors
        return {
            "native_pip": True,
            "shared_stream": stream_stats(page),
            "pending_receipt": True,
            "uncertain_receipt": True,
            "shared_draft": True,
            "unread_focus_minimize_latest": True,
            "route_and_close_keep_session": True,
            "logout_cleanup": True,
            "foreground_tab_focus_observation": focus_status,
            "reply_and_local_thumbnail_file": True,
        }


def fallback_journey(browser: Browser, client: httpx.Client, room: str, fault: str) -> None:
    base_url = str(client.base_url).rstrip("/")
    with new_context(browser, fault) as context:
        page = context.new_page()
        login(page, base_url, room)
        created = stream_stats(page)["created"]
        page.get_by_role("button", name="Pop out · Room Companion", exact=True).click()
        root = page.locator(".room-companion.is-in-app")
        expect(root).to_have_attribute("data-room-id", room)
        expect(page.locator(".room-companion-fallback-note")).to_contain_text(
            "stays inside Character Relay"
        )
        expect(root).to_contain_text("In-app companion")
        page.locator(".web-room-composer textarea").fill(f"Synthetic {fault} fallback draft")
        expect(root.get_by_role("textbox", name="Message", exact=False)).to_have_value(
            f"Synthetic {fault} fallback draft"
        )
        assert_one_stream(page, created)
        root.get_by_role("button", name="Close Room Companion", exact=True).click()
        expect(root).to_have_count(0)
        assert_one_stream(page, created)


def persisted_lifecycle_journey(browser: Browser, client: httpx.Client, room: str) -> None:
    """Exercise production persisted-page handlers; this is not a real BFcache navigation."""
    base_url = str(client.base_url).rstrip("/")
    with new_context(browser) as context:
        page = context.new_page()
        login(page, base_url, room)
        created = stream_stats(page)["created"]
        with context.expect_page() as popup:
            page.get_by_role("button", name="Pop out · Room Companion", exact=True).click()
        pip = popup.value
        expect(pip.locator(".room-companion")).to_have_attribute("data-room-id", room)
        page.locator(".web-room-composer textarea").fill("Synthetic draft to discard on pagehide")
        with pip.expect_event("close"):
            page.evaluate(
                "window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}))"
            )
        page.wait_for_function("window.__roomStreams.active === 0")
        expect(page.locator(".web-room-message")).to_have_count(0)
        expect(page.locator(".web-room-composer textarea")).to_have_value("")
        assert pip.is_closed()

        with page.expect_response(lambda response: response.url.endswith("/api/auth/me")) as auth:
            page.evaluate(
                "window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))"
            )
        assert auth.value.status == 200
        page.wait_for_function("window.__roomStreams.active === 1")
        expect(page.locator(".web-room-connection.is-connected")).to_be_visible()
        expect(page.locator(f"#web-room-message-{source(10)['message_id']}")).to_be_visible()
        assert_one_stream(page, created + 1)

        page.get_by_role("navigation", name="Primary navigation").get_by_role(
            "button", name="Settings", exact=True
        ).click()
        page.evaluate(
            "window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted: true}))"
        )
        page.wait_for_function("window.__roomStreams.active === 0")
        pending: list[tuple[Route, APIResponse]] = []

        def delay_auth(route: Route) -> None:
            response = route.fetch()
            assert response.status == 200
            pending.append((route, response))

        # Only hold this real /auth/me response. Do not intercept CSS or room SSE.
        page.route("**/api/auth/me", delay_auth)
        page.evaluate(
            "window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))"
        )
        deadline = time.monotonic() + 10
        while not pending:
            if time.monotonic() > deadline:
                raise AssertionError("Persisted pageshow did not request authentication")
            page.wait_for_timeout(20)
        page.get_by_role("button", name="Sign out", exact=True).click()
        expect(page.get_by_role("button", name="Enter studio", exact=True)).to_be_visible()
        assert stream_stats(page)["active"] == 0
        route, response = pending.pop()
        with page.expect_response(lambda response: response.url.endswith("/api/auth/me")) as stale:
            route.fulfill(response=response)
        assert stale.value.status == 200
        assert stale.value.json()["email"] == EMAIL
        page.evaluate(
            "() => new Promise(resolve => "
            "requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        expect(page.get_by_role("button", name="Enter studio", exact=True)).to_be_visible()
        stats = stream_stats(page)
        assert stats["active"] == 0 and stats["created"] == created + 1, stats
        assert context.request.get(f"{base_url}/api/auth/me").status == 401


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chromium", help="Chromium executable; defaults to Playwright's installed browser"
    )
    parser.add_argument(
        "--browser-arg",
        action="append",
        default=[],
        help="Additional Chromium argument (use --browser-arg=VALUE)",
    )
    parser.add_argument(
        "--headed", action="store_true", help="Run visibly when a desktop display is available"
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    assert (ROOT / "web/dist/index.html").is_file(), "Run cd web && npm run build first"
    with local_application() as client:
        connection, room, profile = seed(client)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=args.chromium, headless=not args.headed, args=args.browser_arg
            )
            try:
                result = native_journey(browser, client, room, connection, profile)
                for fault in ("absent", "rejected"):
                    fallback_journey(browser, client, room, fault)
                persisted_lifecycle_journey(browser, client, room)
                result.update(
                    browser=browser.version,
                    headless=not args.headed,
                    real_isolated_api=True,
                    fallback_absent_and_rejected=True,
                    dots_usability="unverified",
                    desktop_always_on_top="unverified",
                    persisted_page_handlers_and_stale_auth=True,
                    actual_bfcache_navigation="unverified",
                )
                print(json.dumps(result, indent=2))
            finally:
                browser.close()


if __name__ == "__main__":
    main()
