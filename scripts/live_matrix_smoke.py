"""Create or verify one retained Phase 14 Matrix on the public Echo Masque deployment."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "echo-masque-live-matrix/1.0",
    "X-Echo-User": "local-user",
}
MATRIX_NAME = "LIVE DEMO — Phase 14 Stable Temperature Matrix"
CARD_NAME = "LIVE DEMO — Stable Ann"
PACK_NAME = "LIVE DEMO — Bilingual Character Integrity Pack"


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
    timeout: int = 30,
) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    request = Request(
        f"{base_url}{path}",
        data=data,
        headers=USER_HEADERS,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {path} could not connect: {exc.reason}") from exc


def wait_for_phase14(base_url: str) -> None:
    last_error = ""
    for attempt in range(1, 31):
        try:
            response = request_json(base_url, "/api/matrices?page=1", timeout=20)
            if isinstance(response, dict) and "items" in response:
                print(f"Phase 14 API ready on attempt {attempt}.")
                return
            last_error = f"Unexpected Matrix response: {response}"
        except RuntimeError as exc:
            last_error = str(exc)
        print(f"Waiting for Phase 14 deployment ({attempt}/30): {last_error}")
        time.sleep(20)
    raise RuntimeError(f"Phase 14 API did not become ready: {last_error}")


def named_item(items: object, name: str) -> dict[str, Any]:
    if not isinstance(items, list):
        raise RuntimeError(f"Expected a list while looking for {name}: {items}")
    matches = [item for item in items if isinstance(item, dict) and item.get("display_name", item.get("name")) == name]
    if not matches:
        raise RuntimeError(f"Required retained Live Demo item is missing: {name}")
    return matches[0]


def matrix_definition(card_id: str, pack_id: str) -> dict[str, object]:
    return {
        "subjects": [{"character_card_id": card_id, "prompt_version_ids": []}],
        "model_overrides": [],
        "temperatures": [0.3, 0.7],
        "test_pack_ids": [pack_id],
        "test_languages": ["zh-CN"],
        "tester_modes": ["benchmark"],
        "judge_modes": ["rules"],
        "repeat_count": 1,
        "concurrency": 1,
        "max_attempts": 2,
    }


def find_matrix(base_url: str) -> dict[str, Any] | None:
    page = request_json(base_url, "/api/matrices?page=1&page_size=100")
    items = page.get("items") if isinstance(page, dict) else None
    if not isinstance(items, list):
        raise RuntimeError(f"Matrix list was malformed: {page}")
    for item in items:
        if isinstance(item, dict) and item.get("name") == MATRIX_NAME:
            return item
    return None


def create_or_reuse_matrix(base_url: str, card_id: str, pack_id: str) -> dict[str, Any]:
    existing = find_matrix(base_url)
    if existing is not None:
        return existing
    definition = matrix_definition(card_id, pack_id)
    preview = request_json(
        base_url,
        "/api/matrices/preview",
        method="POST",
        payload=definition,
    )
    if preview.get("task_count") != 2 or preview.get("within_limit") is not True:
        raise RuntimeError(f"Unexpected Matrix preview: {preview}")
    created = request_json(
        base_url,
        "/api/matrices",
        method="POST",
        payload={
            "name": MATRIX_NAME,
            "description": (
                "Retained production acceptance comparing Stable Ann at Temperature 0.3 and 0.7 "
                "with the Chinese Benchmark + Rules path."
            ),
            "definition": definition,
        },
    )
    if not isinstance(created, dict) or not isinstance(created.get("id"), str):
        raise RuntimeError(f"Matrix creation did not return an ID: {created}")
    return created


def ensure_launched(base_url: str, matrix: dict[str, Any]) -> dict[str, Any]:
    matrix_id = matrix.get("id")
    if not isinstance(matrix_id, str):
        raise RuntimeError(f"Matrix ID is missing: {matrix}")
    status = matrix.get("status")
    if status == "draft":
        return request_json(
            base_url,
            f"/api/matrices/{matrix_id}/launch",
            method="POST",
            payload={"confirmed_task_count": 2},
            timeout=60,
        )
    if status in {"paused", "failed"}:
        return request_json(
            base_url,
            f"/api/matrices/{matrix_id}/resume",
            method="POST",
            timeout=60,
        )
    return matrix


def wait_for_matrix(base_url: str, matrix_id: str) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for _ in range(120):
        result = request_json(base_url, f"/api/matrices/{matrix_id}")
        if not isinstance(result, dict):
            raise RuntimeError(f"Matrix detail was malformed: {result}")
        latest = result
        if result.get("status") not in {"draft", "queued", "running"}:
            break
        time.sleep(2)
    if latest.get("status") != "completed":
        raise RuntimeError(f"Live Matrix did not complete: {latest}")
    return latest


def run_acceptance(base_url: str) -> dict[str, object]:
    wait_for_phase14(base_url)
    cards = request_json(base_url, "/api/characters")
    packs = request_json(base_url, "/api/test-packs")
    card = named_item(cards, CARD_NAME)
    pack = named_item(packs, PACK_NAME)
    matrix = create_or_reuse_matrix(base_url, str(card["id"]), str(pack["id"]))
    matrix = ensure_launched(base_url, matrix)
    matrix_id = matrix.get("id")
    if not isinstance(matrix_id, str):
        raise RuntimeError(f"Matrix ID was missing: {matrix}")
    completed = wait_for_matrix(base_url, matrix_id)
    tasks = request_json(base_url, f"/api/matrices/{matrix_id}/tasks")
    analytics = request_json(base_url, f"/api/matrices/{matrix_id}/analytics")
    if not isinstance(tasks, list) or len(tasks) != 2:
        raise RuntimeError(f"Expected two Matrix tasks: {tasks}")
    if {item.get("status") for item in tasks if isinstance(item, dict)} != {"completed"}:
        raise RuntimeError(f"Matrix tasks did not all complete: {tasks}")
    temperatures = {
        item.get("combination", {}).get("temperature")
        for item in tasks
        if isinstance(item, dict) and isinstance(item.get("combination"), dict)
    }
    if temperatures != {0.3, 0.7}:
        raise RuntimeError(f"Temperature variants were unexpected: {temperatures}")
    if analytics.get("completed_runs") != 2:
        raise RuntimeError(f"Matrix analytics did not include two runs: {analytics}")
    result = {
        "base_url": base_url,
        "matrix": completed,
        "card": {"id": card["id"], "name": card["display_name"]},
        "test_pack": {"id": pack["id"], "name": pack["name"], "version": pack["version"]},
        "tasks": tasks,
        "analytics": analytics,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--output", default="live-matrix-result.json")
    args = parser.parse_args()
    result = run_acceptance(normalized_base_url(args.base_url))
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
