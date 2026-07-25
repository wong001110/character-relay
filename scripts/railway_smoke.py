"""Smoke-test a deployed Echo Masque service using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "echo-masque-railway-smoke/1.0",
    "X-Echo-User": "railway-smoke",
}


def normalized_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://")
    return base_url


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{base_url}{path}",
        data=data,
        headers=USER_HEADERS,
        method=method,
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {path} could not connect: {exc.reason}") from exc


def request_text(base_url: str, path: str) -> tuple[str, str]:
    request = Request(
        f"{base_url}{path}",
        headers={"User-Agent": USER_HEADERS["User-Agent"]},
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode(errors="replace"), response.headers.get_content_type()
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"GET {path} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"GET {path} could not connect: {exc.reason}") from exc


def contains_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def completed_language_trial(base_url: str, test_language: str) -> float:
    started = request_json(
        base_url,
        "/api/trials",
        method="POST",
        payload={
            "target_id": "demo-stable",
            "suite": ["identity_integrity"],
            "mode": "fast",
            "tester_mode": "benchmark",
            "test_language": test_language,
        },
    )
    if started.get("test_language") != test_language:
        raise RuntimeError(f"Trial did not preserve test language: {started}")
    run_id = started.get("id")
    if not isinstance(run_id, str):
        raise RuntimeError(f"Trial did not return a run ID: {started}")

    snapshot: dict[str, Any] | None = None
    for _ in range(60):
        snapshot = request_json(base_url, f"/api/trials/{run_id}/snapshot")
        status = snapshot.get("run", {}).get("status")
        if status not in {"pending", "running"}:
            break
        time.sleep(0.5)

    if snapshot is None:
        raise RuntimeError("No trial snapshot was returned.")
    run = snapshot.get("run", {})
    if run.get("status") != "completed":
        raise RuntimeError(f"Deterministic trial did not complete: {run}")
    if run.get("test_language") != test_language:
        raise RuntimeError(f"Completed run changed test language: {run}")

    result = run.get("result", {})
    score = result.get("average_score")
    if not isinstance(score, (int, float)) or score < 90:
        raise RuntimeError(f"Stable deterministic score was unexpected: {score}")

    results = result.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError(f"Trial result did not contain a scenario: {result}")
    scenario = results[0].get("scenario", {})
    if scenario.get("language") != test_language:
        raise RuntimeError(f"Scenario language was unexpected: {scenario}")

    messages = [
        event.get("payload", {}).get("message")
        for event in snapshot.get("events", [])
        if event.get("event_type") in {"tester_message", "subject_response"}
    ]
    visible_messages = [message for message in messages if isinstance(message, str)]
    if len(visible_messages) < 2:
        raise RuntimeError(f"Trial did not expose Tester and Subject messages: {snapshot}")
    if test_language == "zh-CN" and not all(contains_cjk(item) for item in visible_messages[:2]):
        raise RuntimeError(f"Chinese trial emitted non-Chinese messages: {visible_messages}")
    if test_language == "en" and any(contains_cjk(item) for item in visible_messages[:2]):
        raise RuntimeError(f"English trial emitted Chinese messages: {visible_messages}")
    return float(score)


def run_smoke(base_url: str) -> None:
    health = request_json(base_url, "/health")
    if health.get("name") != "Echo Masque":
        raise RuntimeError(f"Unexpected health response: {health}")

    _, content_type = request_text(base_url, "/")
    if content_type != "text/html":
        raise RuntimeError(f"Root did not serve the web client: {content_type}")

    targets = request_json(base_url, "/api/targets")
    target_ids = {item.get("id") for item in targets}
    if "demo-stable" not in target_ids:
        raise RuntimeError("Stable demo target is missing from the deployment.")

    english_score = completed_language_trial(base_url, "en")
    chinese_score = completed_language_trial(base_url, "zh-CN")
    print(
        "Railway multilingual smoke passed: "
        f"{base_url} (en={english_score}, zh-CN={chinese_score})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Public Railway URL, for example https://app.up.railway.app")
    args = parser.parse_args()
    run_smoke(normalized_base_url(args.base_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
