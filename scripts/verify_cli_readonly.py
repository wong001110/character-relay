#!/usr/bin/env python3
"""Synthetic real API/Portal/CLI journey; never contacts the deployed service.

Build the Portal first, then run:
  .venv/bin/python scripts/verify_cli_readonly.py --chromium /usr/bin/chromium

The CLI's fixed official HTTPS URLs are mapped by a test-only transport to a
disposable loopback server. No mock responses, production settings, real account,
credential files or message sends are used. Secrets stay in process memory.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from playwright.sync_api import expect, sync_playwright
from verify_room_companion import EMAIL, PASSWORD, isolated_settings, observe, seed, source

from echo_masque.api import create_app
from echo_masque.cli_client import OFFICIAL_ORIGIN, run_session


@contextmanager
def local_application() -> Iterator[httpx.Client]:
    with TemporaryDirectory(prefix="cli-browser-") as directory:
        settings = isolated_settings(Path(directory) / "browser.db")
        settings.cli_auth_enabled = True
        app = create_app(settings)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            with httpx.Client(base_url=origin, trust_env=False, timeout=15) as client:
                deadline = time.monotonic() + 15
                while not server.started:
                    if not worker.is_alive() or time.monotonic() > deadline:
                        raise RuntimeError("Isolated API failed to start")
                    time.sleep(0.05)
                yield client
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            listener.close()
            app.state.database.engine.dispose()
            if worker.is_alive():
                raise RuntimeError("Isolated API failed to stop")


class Output(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.code_ready = threading.Event()
        self.user_code = ""

    def write(self, value: str) -> int:
        result = super().write(value)
        match = re.search(r"Approval code: ([A-Z0-9]{5}-[A-Z0-9]{5})", self.getvalue())
        if match:
            self.user_code = match.group(1)
            self.code_ready.set()
        return result


class LocalRealAPITransport(httpx.BaseTransport):
    """Harness seam only: execute official-origin requests against the real local API."""

    def __init__(self, origin: str) -> None:
        self.client = httpx.Client(base_url=origin, trust_env=False, timeout=15)
        self.secrets: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url).split("/api/")[0] != OFFICIAL_ORIGIN:
            raise RuntimeError("CLI attempted another origin")
        response = self.client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=request.headers,
            content=request.read(),
        )
        # Copy no remote Cookie/session to the test CLI. These fields are assertions only.
        if response.status_code == 200:
            payload = response.json()
            for key in ("device_code", "access_token"):
                if isinstance(payload.get(key), str):
                    self.secrets.append(payload[key])
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    def close(self) -> None:
        self.client.close()


def watch_stream(
    origin: str,
    room: str,
    token: str,
    ready: threading.Event,
    events: list[str],
    failures: list[str],
) -> None:
    try:
        with (
            httpx.Client(base_url=origin, trust_env=False, timeout=8) as client,
            client.stream(
                "GET", f"/api/cli/rooms/{room}/events", headers={"Authorization": "Bearer " + token}
            ) as response,
        ):
            if response.status_code != 200:
                raise RuntimeError("Stream admission failed")
            for line in response.iter_lines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                    events.append(event)
                    if event == "snapshot":
                        ready.set()
                    if event in {"revoked", "unavailable"}:
                        return
    except Exception as exc:
        failures.append(type(exc).__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    with local_application() as api:
        origin = str(api.base_url).rstrip("/")
        connection, room, _ = seed(api)
        observe(api, connection, [source(1)])
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=args.chromium,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context()
            context.add_init_script("localStorage.setItem('echo-masque-language', 'en')")
            page = context.new_page()
            mutations: list[str] = []
            page.on(
                "request",
                lambda req: (
                    mutations.append(req.url)
                    if req.method in {"POST", "DELETE"} and "/cli-auth/" in req.url
                    else None
                ),
            )
            page.goto(origin + "/cli/authorize")
            page.locator('input[name="email"]').fill(EMAIL)
            page.locator('input[name="password"]').fill(PASSWORD)
            page.locator('button[type="submit"]').click()
            expect(page.get_by_role("heading", name="Approve CLI access")).to_be_visible()
            assert page.url.endswith("/cli/authorize"), "Login lost approval route"

            for revoke_in_cli in (False, True):
                output = Output()
                failures: list[str] = []
                transport = LocalRealAPITransport(origin)

                def run(
                    transport: LocalRealAPITransport = transport,
                    revoke_in_cli: bool = revoke_in_cli,
                    output: Output = output,
                    failures: list[str] = failures,
                ) -> None:
                    try:
                        with httpx.Client(transport=transport) as cli:
                            run_session(cli, [room], revoke=revoke_in_cli, output=output)
                    except Exception as exc:
                        failures.append(type(exc).__name__)

                worker = threading.Thread(target=run, daemon=True)
                worker.start()
                assert output.code_ready.wait(10), "CLI did not display approval instructions"
                page.goto(origin + "/cli/authorize?user_code=" + output.user_code)
                expect(page.locator('input[name="user_code"]')).to_have_value(output.user_code)
                assert not any("/decision" in path for path in mutations), "Implicit approval"
                page.get_by_role("button", name="Review request", exact=True).click()
                expect(page.get_by_text(room, exact=True)).to_be_visible()
                expect(page.get_by_text("Character Relay CLI", exact=False)).to_be_visible()
                expect(page.get_by_text("messages:read", exact=True)).to_be_visible()
                page.get_by_role("button", name="Approve read-only access", exact=True).click()
                expect(page.get_by_role("status")).to_have_text(
                    "Approved. Return to your CLI to continue."
                )
                worker.join(timeout=20)
                assert not worker.is_alive() and not failures, "CLI real API session failed"
                text = output.getvalue()
                snapshots = [
                    json.loads(line) for line in text.splitlines() if line.startswith('{"room_id"')
                ]
                assert (
                    snapshots
                    and snapshots[0]["room_id"] == room
                    and 1 <= snapshots[0]["message_count"] <= 64
                ), "CLI did not read the real bounded snapshot"
                assert all(secret not in text for secret in transport.secrets), (
                    "Secret console output"
                )
                assert "Synthetic room message" not in text, "Unexpected transcript output"
                token = next(secret for secret in transport.secrets if secret.startswith("crcli_"))
                if not revoke_in_cli:
                    ready = threading.Event()
                    events: list[str] = []
                    stream_failures: list[str] = []
                    watcher = threading.Thread(
                        target=watch_stream,
                        args=(origin, room, token, ready, events, stream_failures),
                        daemon=True,
                    )
                    watcher.start()
                    assert ready.wait(8), "Real SSE did not deliver its initial snapshot"
                    page.goto(origin + "/settings?tab=account")
                    page.get_by_role("button", name="Revoke", exact=True).click()
                    expect(page.get_by_text(re.compile(r"^Revoked:"))).to_be_visible()
                    watcher.join(timeout=7)
                    assert not watcher.is_alive() and not stream_failures, (
                        "SSE did not stop after revoke"
                    )
                    assert events == ["snapshot", "revoked"], "SSE emitted after invalidation"
                assert (
                    api.get(
                        "/api/cli-auth/me", headers={"Authorization": "Bearer " + token}
                    ).status_code
                    == 401
                )
                mutations.clear()
            context.close()
            browser.close()
    print(
        "PASS: real login preserves approval route; explicit review/approve; memory CLI reads; "
        "browser and CLI revoke; real SSE stops after revoke; no secret/transcript output. "
        "Synthetic local API only."
    )


if __name__ == "__main__":
    main()
