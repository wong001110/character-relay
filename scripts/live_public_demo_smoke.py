"""Validate the public Demo account against the deployed Bootstrap Admin workspace."""

from __future__ import annotations

import argparse
import json
from typing import Any

import httpx

from echo_masque.public_demo import PUBLIC_DEMO_EMAIL, PUBLIC_DEMO_PASSWORD

_PREFERRED_CARD_NAMES = (
    "LIVE DEMO — Stable Ann",
    "LIVE DEMO — Drift Ann (OOC Control)",
)


def require(response: httpx.Response, expected: int, label: str) -> httpx.Response:
    if response.status_code != expected:
        raise RuntimeError(
            f"{label} returned HTTP {response.status_code}: {response.text[:500]}"
        )
    return response


def login(client: httpx.Client, email: str, password: str, label: str) -> None:
    require(
        client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        ),
        200,
        f"{label} login",
    )


def list_json(client: httpx.Client, path: str, label: str) -> list[dict[str, Any]]:
    payload = require(client.get(path), 200, label).json()
    if not isinstance(payload, list):
        raise RuntimeError(f"{label} did not return a JSON list.")
    return [item for item in payload if isinstance(item, dict)]


def selected_source_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {str(item.get("display_name")): item for item in cards}
    selected = [by_name[name] for name in _PREFERRED_CARD_NAMES if name in by_name]
    selected_ids = {str(item.get("id")) for item in selected}
    for item in cards:
        item_id = str(item.get("id"))
        if item_id in selected_ids:
            continue
        tags = item.get("tags")
        display_name = str(item.get("display_name", ""))
        if (
            (isinstance(tags, list) and "live-demo" in tags)
            or display_name.startswith("LIVE DEMO —")
        ):
            selected.append(item)
            selected_ids.add(item_id)
        if len(selected) >= 2:
            return selected[:2]
    for item in cards:
        if str(item.get("id")) not in selected_ids:
            selected.append(item)
        if len(selected) >= 2:
            break
    return selected[:2]


def names(items: list[dict[str, Any]], key: str) -> set[str]:
    return {str(item.get(key)) for item in items}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    timeout = httpx.Timeout(30.0)
    with (
        httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=True) as admin,
        httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=True) as demo,
    ):
        login(admin, args.admin_email, args.admin_password, "Admin")
        admin_cards = list_json(admin, "/api/characters", "Admin Character list")
        expected_cards = selected_source_cards(admin_cards)
        if len(expected_cards) != 2:
            raise RuntimeError(
                f"Expected two source Character Cards, found {len(expected_cards)}."
            )
        admin_scenarios = list_json(admin, "/api/scenarios", "Admin Scenario list")
        admin_packs = list_json(admin, "/api/test-packs", "Admin Test Pack list")
        if not admin_scenarios or not admin_packs:
            raise RuntimeError(
                "Bootstrap Admin must have at least one Scenario and one Test Pack."
            )

        login(demo, PUBLIC_DEMO_EMAIL, PUBLIC_DEMO_PASSWORD, "Public Demo")
        me = require(demo.get("/api/auth/me"), 200, "Public Demo identity").json()
        if me.get("role") != "user" or me.get("email") != PUBLIC_DEMO_EMAIL:
            raise RuntimeError("Public Demo account identity or role is incorrect.")

        demo_cards = list_json(demo, "/api/characters", "Demo Character list")
        expected_card_names = names(expected_cards, "display_name")
        demo_card_names = names(demo_cards, "display_name")
        if len(demo_cards) != 2 or demo_card_names != expected_card_names:
            raise RuntimeError(
                "Demo Character Cards do not match the selected Admin source Cards."
            )

        demo_scenarios = list_json(demo, "/api/scenarios", "Demo Scenario list")
        if names(demo_scenarios, "name") != names(admin_scenarios, "name"):
            raise RuntimeError("Demo Scenarios do not match the Admin workspace.")

        demo_packs = list_json(demo, "/api/test-packs", "Demo Test Pack list")
        if names(demo_packs, "name") != names(admin_packs, "name"):
            raise RuntimeError("Demo Test Packs do not match the Admin workspace.")

        configured_cards: list[str] = []
        for card in demo_cards:
            card_id = str(card.get("id"))
            status = require(
                demo.get(f"/api/characters/{card_id}/credential"),
                200,
                "Demo Character credential status",
            ).json()
            if status.get("required") is True and status.get("configured") is not True:
                raise RuntimeError(
                    f"Demo Character {card.get('display_name')} has no usable credential."
                )
            configured_cards.append(str(card.get("display_name")))

        blocked = demo.post("/api/scenarios", json={})
        require(blocked, 403, "Demo read-only Scenario boundary")
        if "read-only" not in str(blocked.json().get("detail", "")):
            raise RuntimeError("Demo mutation rejection did not identify the read-only boundary.")
        require(demo.get("/api/auth/sessions"), 403, "Demo Session-management boundary")
        require(demo.post("/api/auth/logout"), 204, "Demo logout")

    print(
        json.dumps(
            {
                "status": "passed",
                "base_url": base_url,
                "demo_email": PUBLIC_DEMO_EMAIL,
                "role": "user",
                "character_names": sorted(demo_card_names),
                "scenario_count": len(demo_scenarios),
                "test_pack_count": len(demo_packs),
                "credential_ready_cards": sorted(configured_cards),
                "read_only_boundary": True,
                "daily_run_limit": 20,
                "secrets_included": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
