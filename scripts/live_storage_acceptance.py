"""Capture persistent storage identity and retained Live Demo IDs from a deployed service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STABLE_CARD = "LIVE DEMO — Stable Ann"
DRIFT_CARD = "LIVE DEMO — Drift Ann (OOC Control)"
DEMO_PACK = "LIVE DEMO — Bilingual Character Integrity Pack"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "echo-masque-live-storage-acceptance/1.0",
    "X-Echo-User": "local-user",
}


def normalized_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://")
    return base_url


def request_json(base_url: str, path: str) -> Any:
    request = Request(f"{base_url}{path}", headers=HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"GET {path} returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"GET {path} could not connect: {exc.reason}") from exc


def find_named(items: object, name: str, *, field: str) -> dict[str, Any]:
    if not isinstance(items, list):
        raise RuntimeError(f"Expected a list while looking for {name}: {items}")
    for item in items:
        if isinstance(item, dict) and item.get(field) == name:
            return item
    raise RuntimeError(f"Required retained record is missing: {name}")


def capture(base_url: str) -> dict[str, object]:
    health = request_json(base_url, "/health")
    if not isinstance(health, dict):
        raise RuntimeError(f"Unexpected health response: {health}")
    storage = health.get("storage")
    if not isinstance(storage, dict):
        raise RuntimeError(f"Storage health is missing: {health}")
    instance_id = storage.get("storage_instance_id")
    if not isinstance(instance_id, str) or not instance_id:
        raise RuntimeError(f"Storage Instance ID is missing: {storage}")
    if storage.get("database_path") != "/data/echo_masque.db":
        raise RuntimeError(f"Unexpected production database path: {storage}")
    if storage.get("mount_ready") is not True:
        raise RuntimeError(f"Production Volume is not mounted: {storage}")

    cards = request_json(base_url, "/api/characters")
    packs = request_json(base_url, "/api/test-packs")
    stable = find_named(cards, STABLE_CARD, field="display_name")
    drift = find_named(cards, DRIFT_CARD, field="display_name")
    pack = find_named(packs, DEMO_PACK, field="name")

    return {
        "base_url": base_url,
        "storage": {
            "storage_instance_id": instance_id,
            "database_path": storage.get("database_path"),
            "mount_path": storage.get("mount_path"),
            "mount_ready": storage.get("mount_ready"),
        },
        "retained": {
            "stable_card_id": stable.get("id"),
            "stable_target_id": stable.get("target_id"),
            "drift_card_id": drift.get("id"),
            "drift_target_id": drift.get("target_id"),
            "test_pack_id": pack.get("id"),
            "test_pack_version": pack.get("version"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--output", type=Path, default=Path("live-storage-acceptance.json"))
    args = parser.parse_args()
    result = capture(normalized_base_url(args.base_url))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
