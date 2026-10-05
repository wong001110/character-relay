"""Synthetic, real API/SSE/Chromium acceptance for Web Room Agent batch reading.

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
from datetime import UTC, datetime, timedelta
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
    expect(panel(page)).to_have_attribute("data-status", "needs_reread", timeout=15_000)


def read(page: Page) -> dict[str, Any]:
    page.get_by_role("button", name="Read batch", exact=True).first.click()
    root = panel(page)
    expect(root.locator("[data-agent-batch-id]")).to_be_visible(timeout=15_000)
    return {
        "id": root.locator("[data-agent-batch-id]").get_attribute("data-agent-batch-id"),
        "end": root.locator("[data-agent-batch-id]").get_attribute("data-to-revision"),
    }


def complete(page: Page) -> None:
    page.get_by_role("button", name="Complete this batch", exact=True).first.click()
    expect(panel(page).locator("[data-agent-batch-id]")).to_have_count(0, timeout=15_000)


def journey(browser, client, stream_cut: threading.Event) -> dict[str, Any]:
    connection, room, profile = seed(client)
    base_url = str(client.base_url).rstrip("/")
    endpoint = f"/api/web-chat/rooms/{room}/agent-reading/{profile}"
    result: dict[str, Any] = {}
    with new_context(browser) as context:
        page = context.new_page()
        # Instrument native events without creating/injecting snapshots or transport state.
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
        captured = read(page)
        page.screenshot(path="/tmp/character-relay-agent-reading.png", full_page=True)
        initial = api(client, "GET", endpoint)
        assert initial["batch"]["id"] == captured["id"]
        assert initial["cursor_revision"] == 0
        observe(client, connection, [source(7)])
        expect(panel(page)).to_have_attribute("data-pending-count", "7", timeout=15_000)
        assert (
            panel(page).locator("[data-agent-batch-id]").get_attribute("data-agent-batch-id")
            == captured["id"]
        )
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "pending", timeout=15_000)
        after = api(client, "GET", endpoint)
        assert after["cursor_revision"] == int(captured["end"]) and after["pending_count"] == 1
        result["fixed_cutoff_preserves_late_arrival"] = True
        read(page)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "idle")

        # Same latest message ID, but old source edit and delete remain observable.
        observe(
            client,
            connection,
            [
                source(
                    1,
                    text="Synthetic edited body",
                    edited_at=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
                )
            ],
        )
        expect(panel(page)).to_have_attribute("data-status", "pending", timeout=15_000)
        read(page)
        expect(panel(page)).to_contain_text("Synthetic edited body")
        observe(client, connection, [source(1, text="", deleted=True)])
        expect(panel(page)).not_to_contain_text("Synthetic edited body", timeout=15_000)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "pending")
        read(page)
        expect(panel(page)).to_contain_text("deleted", ignore_case=True)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "idle")
        result["same_id_edit_delete_and_redaction"] = True

        # UI send accepted by real outbox, synthetic delivery receipt, verified ingest echo.
        # No actual Discord webhook/network send is executed.
        page.locator(".web-room-composer textarea").fill("Synthetic Agent echo")
        with page.expect_response(
            lambda response: (
                response.request.method == "POST"
                and response.url.endswith(f"/rooms/{room}/messages")
            )
        ) as accepted:
            page.locator(".web-room-composer").get_by_role(
                "button", name="Send", exact=True
            ).click()
        assert accepted.value.status == 202
        receipt = accepted.value.json()
        headers = {"Authorization": f"Bearer {CONNECTOR_SECRET}"}
        claim = api(
            client,
            "POST",
            f"/api/connectors/discord/web-chat/rooms/{room}/claim",
            headers=headers,
            json={"connection_id": connection, "claim_nonce": "agent-browser-claim-0001"},
        )
        api(
            client,
            "POST",
            f"/api/connectors/discord/web-chat/outbox/{receipt['id']}/ack",
            headers=headers,
            json={
                "connection_id": connection,
                "claim_nonce": claim["claim_nonce"],
                "status": "delivered",
                "message_id": source(8)["message_id"],
                "created_at": source(8)["created_at"],
                "webhook_id": "offline-webhook",
            },
        )
        observe(
            client,
            connection,
            [
                source(
                    8,
                    author_id="offline-webhook",
                    author_is_bot=True,
                    webhook_id="offline-webhook",
                    text="Synthetic Agent echo",
                )
            ],
        )
        expect(
            page.locator(f".web-room-messages [data-message-id='{source(8)['message_id']}']")
        ).to_be_visible(timeout=15_000)
        expect(panel(page)).to_have_attribute("data-status", "idle")
        assert api(client, "GET", endpoint)["pending_count"] == 0
        result["verified_own_echo_does_not_trigger"] = True

        # Durable position survives reload; reload explicitly requires a reread.
        persisted = api(client, "GET", endpoint)["cursor_revision"]
        page.reload()
        expect(page.locator(".web-room-connection.is-connected")).to_be_visible(timeout=15_000)
        enable(page)
        assert api(client, "GET", endpoint)["cursor_revision"] == persisted
        read(page)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "idle")
        result["reload_preserves_position_and_requires_reread"] = True

        # Unexpected actual network failure blocks confirmation; a newer gap survives
        # completion of a batch captured before disconnection.
        observe(client, connection, [source(9)])
        expect(panel(page)).to_have_attribute("data-status", "pending", timeout=15_000)
        captured = read(page)
        stream_cut.set()
        expect(panel(page)).to_have_attribute("data-status", "unknown", timeout=20_000)
        expect(
            page.get_by_role("button", name="Complete this batch", exact=True).first
        ).to_be_disabled()
        observe(client, connection, [source(10)])
        stream_cut.clear()
        expect(page.locator(".web-room-connection.is-connected")).to_be_visible(timeout=20_000)
        expect(panel(page)).to_have_attribute("data-status", "needs_reread", timeout=20_000)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "needs_reread")
        assert api(client, "GET", endpoint)["pending_count"] == 1
        read(page)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "idle")
        result["actual_disconnect_newer_gap_and_late_message"] = True

        # An independent participant cannot inherit the first participant's progress.
        second = api(
            client,
            "POST",
            "/api/web-chat/profiles",
            json={"display_name": "Other synthetic participant"},
        )["id"]
        page.reload()
        expect(page.locator(".web-room-connection.is-connected")).to_be_visible(timeout=15_000)
        page.locator(".web-room-sidebar").get_by_role("combobox").nth(1).select_option(second)
        enable(page)
        second_endpoint = f"/api/web-chat/rooms/{room}/agent-reading/{second}"
        assert api(client, "GET", second_endpoint)["cursor_revision"] == 0
        read(page)
        assert panel(page).locator(f"[data-message-id='{source(8)['message_id']}']").count() == 1
        complete(page)
        page.locator(".web-room-sidebar").get_by_role("combobox").nth(1).select_option(profile)
        expect(panel(page)).to_have_attribute("data-profile-id", profile, timeout=15_000)
        assert api(client, "GET", endpoint)["cursor_revision"] > persisted
        result["participant_progress_isolated"] = True

        # Natural server finite-stream rollover should not manufacture recovery work.
        # The API refresh supplies real current permission evidence before waiting.
        read(page)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "idle")
        observe(client, connection, [])
        rollovers = page.evaluate("window.__agentRollovers")
        page.wait_for_function(
            "before => window.__agentRollovers > before", arg=rollovers, timeout=70_000
        )
        expect(page.locator(".web-room-connection.is-connected")).to_be_visible(timeout=15_000)
        expect(panel(page)).to_have_attribute("data-status", "idle", timeout=15_000)
        assert page.evaluate("window.__roomStreams.maxActive") == 1
        result["natural_rollover_no_gap_and_one_stream"] = True

        # The real native Companion shares the same processing batch and draft.
        observe(client, connection, [source(11)])
        expect(panel(page)).to_have_attribute("data-status", "pending", timeout=15_000)
        page.locator(".web-room-composer textarea").fill("Synthetic draft kept during batch")
        with context.expect_page() as popup:
            page.get_by_role("button", name="Pop out · Room Companion", exact=True).click()
        pip = popup.value
        expect(panel(pip)).to_have_attribute("data-status", "pending", timeout=15_000)
        captured = read(pip)
        expect(panel(page).locator("[data-agent-batch-id]")).to_have_attribute(
            "data-agent-batch-id", captured["id"]
        )
        complete(pip)
        expect(panel(page)).to_have_attribute("data-status", "idle", timeout=15_000)
        expect(page.locator(".web-room-composer textarea")).to_have_value(
            "Synthetic draft kept during batch"
        )
        assert page.evaluate("window.__roomStreams.maxActive") == 1
        pip.get_by_role("button", name="Close Room Companion", exact=True).click()
        page.locator(".web-room-composer textarea").fill("")
        result["native_companion_shared_batch_and_draft"] = True

        # Browser offline/online signals also establish uncertainty even when an
        # emulated offline transition does not tear down an existing native TCP stream.
        context.set_offline(True)
        expect(panel(page)).to_have_attribute("data-status", "unknown", timeout=15_000)
        expect(page.get_by_role("button", name="Read batch", exact=True).first).to_be_disabled()
        context.set_offline(False)
        expect(page.locator(".web-room-connection.is-connected")).to_be_visible(timeout=20_000)
        expect(panel(page)).to_have_attribute("data-status", "needs_reread", timeout=20_000)
        read(page)
        complete(page)
        expect(panel(page)).to_have_attribute("data-status", "idle")
        result["native_offline_online_signals"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    assert (ROOT / "web/dist/index.html").is_file(), "Build the Portal first."
    with local_agent_application() as (client, stream_cut), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium)
        try:
            result = journey(browser, client, stream_cut)
            print(
                json.dumps(
                    {"browser": browser.version, "isolated": True, "checks": result}, indent=2
                )
            )
        finally:
            browser.close()


if __name__ == "__main__":
    main()
