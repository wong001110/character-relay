"""Run a small multilingual production smoke test against a deployed service."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import cast


EXPECTED_PRODUCT_NAMES = {"Character Relay", "Echo Masque"}


def normalized_base_url(value: str) -> str:
    return value.rstrip("/")


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> dict[str, object] | list[dict[str, object]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return cast(
                dict[str, object] | list[dict[str, object]],
                json.loads(response.read().decode("utf-8")),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with {exc.code}: {body}") from exc


def request_text(base_url: str, path: str) -> tuple[str, str]:
    request = urllib.request.Request(f"{base_url}{path}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8"), response.headers.get_content_type()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {path} failed with {exc.code}: {body}") from exc


def contains_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def validate_storage_health(health: dict[str, object], *, required: bool) -> str:
    storage = health.get("storage")
    if not isinstance(storage, dict):
        if required:
            raise RuntimeError(f"Health response omitted storage details: {health}")
        return "not-reported"
    instance_id = storage.get("storage_instance_id")
    if not isinstance(instance_id, str) or not instance_id:
        raise RuntimeError(f"Storage identity is missing: {storage}")
    if required:
        if storage.get("database_kind") != "sqlite":
            raise RuntimeError(f"Production smoke requires SQLite storage: {storage}")
        if storage.get("mount_path") != "/data" or storage.get("mount_ready") is not True:
            raise RuntimeError(f"Persistent /data mount is not ready: {storage}")
    return instance_id


def completed_language_trial(base_url: str, test_language: str) -> float:
    run = request_json(
        base_url,
        "/api/trials",
        method="POST",
        payload={
            "target_id": "demo-stable",
            "suite": ["identity_integrity"],
            "mode": "fast",
            "tester_mode": "benchmark",
            "judge_mode": "rules",
            "test_language": test_language,
        },
    )
    if not isinstance(run, dict):
        raise RuntimeError(f"Trial start response was not an object: {run}")
    run_id = run.get("id")
    if not isinstance(run_id, str):
        raise RuntimeError(f"Trial start response had no id: {run}")

    deadline = time.monotonic() + 90
    snapshot: dict[str, object] | None = None
    while time.monotonic() < deadline:
        candidate = request_json(base_url, f"/api/trials/{run_id}/snapshot")
        if not isinstance(candidate, dict):
            raise RuntimeError(f"Trial snapshot response was not an object: {candidate}")
        snapshot = candidate
        run_view = candidate.get("run")
        if not isinstance(run_view, dict):
            raise RuntimeError(f"Trial snapshot omitted run metadata: {candidate}")
        status = run_view.get("status")
        if status == "completed":
            break
        if status in {"failed", "cancelled"}:
            raise RuntimeError(f"Trial ended as {status}: {candidate}")
        time.sleep(0.5)
    else:
        raise RuntimeError(f"Trial {run_id} did not complete before timeout: {snapshot}")

    if snapshot is None:
        raise RuntimeError(f"Trial {run_id} produced no snapshot")
    run_view = snapshot.get("run")
    if not isinstance(run_view, dict):
        raise RuntimeError(f"Trial snapshot omitted final run metadata: {snapshot}")
    result = run_view.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Trial result was missing: {snapshot}")
    score = result.get("average_score")
    if not isinstance(score, int | float):
        raise RuntimeError(f"Trial score was missing: {result}")
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


def run_smoke(base_url: str, *, require_storage: bool = False) -> None:
    health = request_json(base_url, "/health")
    if not isinstance(health, dict) or health.get("name") not in EXPECTED_PRODUCT_NAMES:
        raise RuntimeError(f"Unexpected health response: {health}")
    storage_instance_id = validate_storage_health(health, required=require_storage)

    _, content_type = request_text(base_url, "/")
    if content_type != "text/html":
        raise RuntimeError(f"Root did not serve the web client: {content_type}")

    targets = request_json(base_url, "/api/targets")
    if not isinstance(targets, list):
        raise RuntimeError(f"Target listing was not an array: {targets}")
    target_ids = {item.get("id") for item in targets}
    if "demo-stable" not in target_ids:
        raise RuntimeError("Stable demo target is missing from the deployment.")

    english_score = completed_language_trial(base_url, "en")
    chinese_score = completed_language_trial(base_url, "zh-CN")
    print(
        "Railway multilingual smoke passed: "
        f"{base_url} (storage={storage_instance_id}, en={english_score}, zh-CN={chinese_score})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Public Railway URL, for example https://app.up.railway.app")
    parser.add_argument(
        "--require-storage",
        action="store_true",
        help="Fail unless SQLite uses a ready /data persistent mount.",
    )
    args = parser.parse_args()
    run_smoke(normalized_base_url(args.base_url), require_storage=args.require_storage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
