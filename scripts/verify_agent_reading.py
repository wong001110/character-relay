"""Synthetic, real API/SSE/Chromium acceptance for Web Room session reminders.

Run after `npm run build --prefix web` with `.venv/bin/python
scripts/verify_agent_reading.py --chromium /usr/bin/chromium`.
No deployed endpoint, actual Discord connection or account credentials are used.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx
import uvicorn
from playwright.sync_api import Page, expect, sync_playwright
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from verify_room_companion import (
    CONNECTOR_SECRET,
    ROOT,
    api,
    isolated_settings,
    login,
    new_context,
    observe,
    seed,
    source,
)

from echo_masque.api import create_app


class StreamCutMiddleware(BaseHTTPMiddleware):
    """A test-only real HTTP interruption; never injects browser events or API data."""

    def __init__(self, app, cut: threading.Event) -> None:
        super().__init__(app)
        self.cut = cut

    async def dispatch(self, request, call_next):
        stream = request.url.path.startswith("/api/web-chat/rooms/") and request.url.path.endswith(
            "/events"
        )
        if stream and self.cut.is_set():
            return Response(status_code=503)
        response = await call_next(request)
        if stream:
            original = response.body_iterator

            async def interrupted():
                async for chunk in original:
                    if self.cut.is_set():
                        break
                    yield chunk

            response.body_iterator = interrupted()
        return response


@contextmanager
def local_agent_application() -> Iterator[tuple[httpx.Client, threading.Event]]:
    with TemporaryDirectory(prefix="agent-reading-browser-") as directory:
        app = create_app(isolated_settings(Path(directory) / "browser.db"))
        cut = threading.Event()
        app.add_middleware(StreamCutMiddleware, cut=cut)
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
                        raise RuntimeError("Isolated Agent API failed to start")
                    time.sleep(0.05)
                assert client.get("/health").is_success
                yield client, cut
        finally:
            cut.clear()
            server.should_exit = True
            thread.join(timeout=10)
            listener.close()
            app.state.database.engine.dispose()
            if thread.is_alive():
                raise RuntimeError("Isolated Agent API failed to stop")


def panel(page: Page):
    return page.locator("[data-agent-reading]").first


def enable(page: Page) -> None:
    page.get_by_role("button", name="Enable Agent reading", exact=True).first.click()
    expect(panel(page)).to_have_attribute("data-status", "idle", timeout=15_000)
    expect(panel(page)).to_have_attribute("data-pending-count", "0")


def clear(page: Page) -> None:
    page.get_by_role("button", name="Done · clear reminders", exact=True).first.click()
    expect(panel(page)).to_have_attribute("data-pending-count", "0")


def journey(browser, client, stream_cut: threading.Event) -> dict[str, Any]:
    connection, room, profile = seed(client)
    base_url = str(client.base_url).rstrip("/")
    result: dict[str, Any] = {}
    # More than a snapshot of history must never become processing work.
    observe(client, connection, [source(index) for index in range(7, 71)])
    observe(client, connection, [source(index) for index in range(71, 91)])
    with new_context(browser) as context:
        page = context.new_page()
        requests: list[str] = []
        context.on(
            "request",
            lambda request: (
                requests.append(request.url) if "/agent-reading/" in request.url else None
            ),
        )
        page.add_init_script("""(() => {
          const Native = window.EventSource;
          window.__agentRollovers = 0;
          window.EventSource = class extends Native {
            constructor(url, options) {
              super(url, options);
              this.addEventListener('rollover', () => window.__agentRollovers++);
            }
          };
        })();""")
        login(page, base_url, room)
        enable(page)
        expect(page.locator(f"#web-room-message-{source(90)['message_id']}")).to_be_in_viewport()
        result["history_is_context_zero_on_join"] = True

        observe(client, connection, [source(91)])
        expect(panel(page)).to_have_attribute("data-pending-count", "1", timeout=15_000)
        observe(client, connection, [source(91, text="Synthetic edit")])
        observe(client, connection, [source(90, deleted=True, text="", content_available=False)])
        expect(panel(page)).to_have_attribute("data-pending-count", "1")
        clear(page)
        observe(client, connection, [source(92)])
        expect(panel(page)).to_have_attribute("data-pending-count", "1", timeout=15_000)
        result["live_increment_edits_delete_clear_then_later_arrival"] = True

        # A real synthetic delivery receipt establishes canonical own identity.
        accepted = api(
            client,
            "POST",
            f"/api/web-chat/rooms/{room}/messages",
            json={
                "client_message_id": "synthetic-counter-own-echo",
                "profile_id": profile,
                "text": "Synthetic own message",
                "reply_to_message_id": "",
            },
        )
        claimed = api(
            client,
            "POST",
            f"/api/connectors/discord/web-chat/rooms/{room}/claim",
            headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
            json={
                "connection_id": connection,
                "claim_nonce": "synthetic-counter-claim-0001",
            },
        )
        assert claimed["id"] == accepted["id"]
        api(
            client,
            "POST",
            f"/api/connectors/discord/web-chat/outbox/{accepted['id']}/ack",
            headers={"Authorization": f"Bearer {CONNECTOR_SECRET}"},
            json={
                "connection_id": connection,
                "claim_nonce": claimed["claim_nonce"],
                "status": "delivered",
                "message_id": source(93)["message_id"],
                "created_at": source(93)["created_at"],
                "webhook_id": "offline-webhook",
            },
        )
        observe(
            client,
            connection,
            [
                source(
                    93,
                    author_id="offline-webhook",
                    author_is_bot=True,
                    webhook_id="offline-webhook",
                    text="Synthetic own message",
                )
            ],
        )
        expect(page.locator(f"#web-room-message-{source(93)['message_id']}")).to_be_visible(
            timeout=15_000
        )
        expect(panel(page)).to_have_attribute("data-pending-count", "1")
        result["verified_own_receipt_echo_ignored"] = True

        page.locator(".web-room-composer textarea").fill("Synthetic shared draft")
        with context.expect_page() as popup:
            page.get_by_role("button", name="Pop out · Room Companion", exact=True).click()
        pip = popup.value
        expect(panel(pip)).to_have_attribute("data-pending-count", "1")
        clear(pip)
        expect(panel(page)).to_have_attribute("data-pending-count", "0")
        page.get_by_role("navigation", name="Primary navigation").get_by_role(
            "button", name="Characters", exact=True
        ).click()
        observe(client, connection, [source(94)])
        expect(panel(pip)).to_have_attribute("data-pending-count", "1", timeout=15_000)
        pip.get_by_role("button", name="Open full room", exact=True).click()
        expect(panel(page)).to_have_attribute("data-pending-count", "1")
        expect(page.locator(".web-room-composer textarea")).to_have_value("Synthetic shared draft")
        pip.get_by_role("button", name="Close Room Companion", exact=True).click()
        result["native_companion_counter_clear_route_and_draft_shared"] = True

        # Real transport interruption; recovery baselines current messages.
        stream_cut.set()
        expect(panel(page)).to_have_attribute("data-status", "disconnected", timeout=15_000)
        observe(client, connection, [source(95)])
        stream_cut.clear()
        expect(panel(page)).to_have_attribute("data-connection", "connected", timeout=20_000)
        expect(page.locator(f"#web-room-message-{source(95)['message_id']}")).to_be_visible()
        expect(panel(page)).to_have_attribute("data-pending-count", "1")
        observe(client, connection, [source(96)])
        expect(panel(page)).to_have_attribute("data-pending-count", "2", timeout=15_000)
        result["actual_disconnect_preserves_count_recovery_baselines"] = True

        context.set_offline(True)
        expect(panel(page)).to_have_attribute("data-status", "disconnected", timeout=15_000)
        clear(page)
        context.set_offline(False)
        expect(panel(page)).to_have_attribute("data-connection", "connected", timeout=20_000)
        expect(panel(page)).to_have_attribute("data-pending-count", "0")
        result["offline_status_and_local_clear"] = True

        second = api(
            client,
            "POST",
            "/api/web-chat/profiles",
            json={"display_name": "Second synthetic participant"},
        )["id"]
        page.reload()
        expect(page.locator(".web-room-connection.is-connected")).to_be_visible(timeout=15_000)
        page.locator(".web-room-sidebar").get_by_role("combobox").nth(1).select_option(profile)
        enable(page)
        observe(client, connection, [source(97)])
        expect(panel(page)).to_have_attribute("data-pending-count", "1", timeout=15_000)
        page.locator(".web-room-sidebar").get_by_role("combobox").nth(1).select_option(second)
        expect(panel(page)).to_have_attribute("data-profile-id", second)
        expect(panel(page)).to_have_attribute("data-pending-count", "0")
        result["reload_and_participant_switch_start_zero"] = True

        # Heartbeats and normal finite rollover must neither count history nor duplicate SSE.
        rollovers = page.evaluate("window.__agentRollovers")
        page.wait_for_function(
            "before => window.__agentRollovers > before", arg=rollovers, timeout=70_000
        )
        expect(panel(page)).to_have_attribute("data-connection", "connected", timeout=15_000)
        expect(panel(page)).to_have_attribute("data-pending-count", "0")
        assert page.evaluate("window.__roomStreams.maxActive") == 1
        assert requests == []
        result["natural_rollover_one_stream_zero_progress_api_requests"] = True
        page.locator(".web-room-composer textarea").fill("")
    assert client.get(f"/api/web-chat/rooms/{room}/agent-reading/{profile}").status_code == 404
    return result


def fallback_journey(browser, client) -> bool:
    connection, room, _ = seed(client)
    with new_context(browser, "absent") as context:
        page = context.new_page()
        login(page, str(client.base_url).rstrip("/"), room)
        enable(page)
        page.get_by_role("button", name="Pop out · Room Companion", exact=True).click()
        roots = page.locator("[data-agent-reading]")
        expect(roots).to_have_count(2)
        observe(client, connection, [source(7)])
        for index in range(2):
            expect(roots.nth(index)).to_have_attribute("data-pending-count", "1", timeout=15_000)
        page.locator(".room-companion").get_by_role(
            "button", name="Done · clear reminders", exact=True
        ).click()
        for index in range(2):
            expect(roots.nth(index)).to_have_attribute("data-pending-count", "0")
        assert page.evaluate("window.__roomStreams.maxActive") == 1
        page.get_by_role("button", name="Close Room Companion", exact=True).click()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    assert (ROOT / "web/dist/index.html").is_file(), "Build the Portal first."
    with local_agent_application() as (client, stream_cut), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium)
        try:
            result = journey(browser, client, stream_cut)
            result["fallback_companion_shared_count_and_clear"] = fallback_journey(browser, client)
            print(
                json.dumps(
                    {"browser": browser.version, "isolated": True, "checks": result}, indent=2
                )
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
