#!/usr/bin/env python3
"""Exercise the Portal closeout flow against a local Vite server.

The test deliberately routes every API call to local synthetic fixtures.  It never
uses a deployed API and it asserts the requests produced by visible Portal controls.
Run after starting the web server, for example:

  python scripts/verify_portal_closeout.py --base-url http://127.0.0.1:5173

CI needs the Python ``playwright`` package and an installed Chromium browser
(``python -m playwright install chromium`` when the image does not supply one).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Page, Route, sync_playwright

NOW = "2026-09-07T12:00:00Z"
CONNECTION_ID = "66e20e12-dcbb-4bb7-b0a4-6c98ee4d7248"
PROFILE_ID = "profile-1"
DEPLOYMENT_ID = "deployment-1"
GAP_ID = "gap-1"
CANDIDATE_ID = "candidate-1"
BELIEF_ID = "belief-1"
# Valid local WebP matching the synthetic card's binary portrait endpoint.
PORTRAIT_WEBP = base64.b64decode(
    "UklGRh4AAABXRUJQVlA4TBEAAAAvAAAAAAdQvOIVr/+BiOh/AAA="
)


def fixture_data() -> dict[str, Any]:
    connection = {
        "id": CONNECTION_ID,
        "platform": "discord",
        "display_name": "Character Relay Discord Bot",
        "connection_mode": "managed",
        "external_account_id": "external-bot-account",
        "status": "connected",
        "metadata": {"connector_display_name": "Character Relay Discord Bot"},
        "last_seen_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }
    profile = {
        "id": PROFILE_ID,
        "connection_id": CONNECTION_ID,
        "name": "Example Server profile",
        "guild_id": "guild-1",
        "guild_name": "Example Server",
        "channel_scope_mode": "all_except",
        "excluded_channel_ids": [],
        "excluded_category_ids": [],
        "thread_policy": "inherit_parent",
        "created_at": NOW,
        "updated_at": NOW,
    }
    deployment = {
        "id": DEPLOYMENT_ID,
        "character_card_id": "card-1",
        "character_display_name": "Example Character",
        "connection_id": CONNECTION_ID,
        "platform": "discord",
        "server_profile_id": PROFILE_ID,
        "server_profile_name": profile["name"],
        "channel_scope_mode": "all_except",
        "excluded_channel_ids": [],
        "excluded_category_ids": [],
        "workspace_id": "guild-1",
        "workspace_name": "Example Server",
        "channel_id": "",
        "channel_name": "",
        "thread_id": "",
        "thread_name": "",
        "participation_mode": "mention_only",
        "memory_scope": "channel_isolated",
        "version_label": "Current",
        "sticker_count": 0,
        "status": "paused",
        "last_message_at": None,
        "last_error": "",
        "created_at": NOW,
        "updated_at": NOW,
    }
    gap = {
        "id": GAP_ID,
        "entity_id": "entity-1",
        "missing_fields": ["birthplace"],
        "importance": 0.9,
        "resolution_state": "open",
        "discovery_requested": True,
        "possible_sources": [],
        "resolution_evidence_refs": [],
    }
    belief = {
        "id": BELIEF_ID,
        "character_card_id": "card-1",
        "subject_entity_id": "entity-1",
        "subject_ref": "Example Character",
        "predicate": "lives_in",
        "value_text": "Old place",
        "scope": "server",
        "authority_class": "user_correction",
        "authority_score": 0.9,
        "origin": "operator_review",
        "confidence": 0.8,
        "importance": 0.7,
        "status": "active",
        "authored": True,
        "evidence_refs": [],
        "dependency_edge_ids": [],
        "supersedes_belief_id": "",
        "valid_from": None,
        "valid_to": None,
        "stale_after": None,
        "updated_at": NOW,
    }
    candidate = {
        "id": CANDIDATE_ID,
        "gap_id": GAP_ID,
        "discovery_item_id": "item-1",
        "source": "discovery",
        "canonical_key": "example-character",
        "content_kind": "article",
        "title": "Verified candidate",
        "creator": "Example author",
        "url": "https://example.invalid/candidate",
        "score": 0.88,
        "rank_reason": "Matches the missing field",
        "status": "ready",
        "validation_method": "",
        "validated_evidence_ref": "",
        "reviewed_by": None,
        "reviewed_at": None,
        "expires_at": "2026-12-31T00:00:00Z",
    }
    structure = {
        "deployment_id": DEPLOYMENT_ID,
        "threads": [],
        "segments": [],
        "relations": [],
        "episodes": [],
        "entities": [],
        "knowledge_gaps": [gap],
        "beliefs": [belief],
        "social_events": [],
        "impressions": [],
    }
    return {
        "connection": connection,
        "profile": profile,
        "deployment": deployment,
        "gap": gap,
        "belief": belief,
        "candidate": candidate,
        "structure": structure,
    }


def local_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise argparse.ArgumentTypeError("--base-url must be a loopback Vite/static server URL")
    return value.rstrip("/")


def install_api_fixtures(
    page: Page,
    writes: list[tuple[str, dict[str, Any]]],
    unmatched_requests: list[str],
) -> None:
    data = fixture_data()
    candidate_review_path = (
        f"/api/deployments/{DEPLOYMENT_ID}/knowledge-gaps/{GAP_ID}/candidates/{CANDIDATE_ID}/review"
    )

    def fulfill(route: Route, payload: Any, status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def handler(route: Route) -> None:
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        method = request.method

        if method != "GET":
            try:
                payload = request.post_data_json or {}
            except Exception:
                payload = {}
            writes.append((path, payload if isinstance(payload, dict) else {}))

        if path == "/api/auth/config":
            fulfill(
                route,
                {
                    "registration_enabled": False,
                    "invitation_required": False,
                    "authentication_required": True,
                },
            )
        elif path == "/api/auth/me":
            fulfill(
                route,
                {
                    "id": "admin-1",
                    "email": "admin@local.invalid",
                    "display_name": "Local Admin",
                    "role": "admin",
                },
            )
        elif path == "/api/characters/portraits/card-1" and method == "GET":
            route.fulfill(status=200, content_type="image/webp", body=PORTRAIT_WEBP)
        elif path == "/api/characters" or path == "/api/targets":
            fulfill(route, [])
        elif path == "/api/runtime/status":
            runtime_status = {
                "enabled": False,
                "configured": False,
                "provider": "",
                "model": "",
                "credential_source": "missing",
            }
            fulfill(
                route,
                {
                    "admin_available": True,
                    "adaptive": runtime_status,
                    "judge": runtime_status,
                    "default_judge_mode": "rules",
                },
            )
        elif path == "/api/admin/runtime":
            # The always-mounted dock checks this before deciding whether to render.
            fulfill(route, {"config": {}, "status": {}})
        elif path == "/api/admin/runtime/utility-credentials":
            fulfill(route, [])
        elif path in {
            "/api/admin/runtime/utility-gateway/snapshot",
            "/api/admin/runtime/conversation-burst/snapshot",
        }:
            fulfill(route, None)
        elif path == "/api/connections":
            fulfill(route, [data["connection"]])
        elif path == "/api/discord/server-profiles":
            fulfill(route, [data["profile"]])
        elif path == "/api/discord/server-catalog":
            fulfill(
                route,
                [
                    {
                        "connection_id": CONNECTION_ID,
                        "guild_id": "guild-1",
                        "guild_name": "Example Server",
                        "channels": [
                            {
                                "id": "channel-1",
                                "name": "general",
                                "category_id": "",
                                "category_name": "",
                                "type": "text",
                            }
                        ],
                        "synced_at": NOW,
                    }
                ],
            )
        elif path == "/api/discord/logs":
            fulfill(
                route,
                {"items": [], "page": 1, "page_size": 8, "total": 0, "pages": 1},
            )
        elif path == "/api/scheduler/reminders/page":
            fulfill(
                route,
                {
                    "items": [],
                    "next_cursor": None,
                    "has_more": False,
                    "counts": {
                        "pending": 0,
                        "processing": 0,
                        "completed": 0,
                        "failed": 0,
                        "cancelled": 0,
                    },
                },
            )
        elif path == f"/api/discord/server-profiles/{PROFILE_ID}/runtime":
            fulfill(route, {"profile_id": PROFILE_ID, "timezone": "Asia/Kuala_Lumpur"})
        elif path == "/api/deployment-identities":
            fulfill(route, [])
        elif path == "/api/deployments/page":
            fulfill(
                route,
                {
                    "items": [data["deployment"]],
                    "page": 1,
                    "page_size": 20,
                    "total": 1,
                    "pages": 1,
                    "active": 0,
                    "paused": 1,
                    "attention": 0,
                },
            )
        elif path == "/api/deployments":
            fulfill(route, [data["deployment"]])
        elif path == f"/api/deployments/{DEPLOYMENT_ID}/tools":
            fulfill(route, {"deployment_id": DEPLOYMENT_ID, "enabled_tools": []})
        elif path == f"/api/deployments/{DEPLOYMENT_ID}/presence":
            fulfill(
                route,
                {
                    "deployment_id": DEPLOYMENT_ID,
                    "state": "idle",
                    "activity_type": "",
                    "source": "default",
                    "reason": "fixture",
                    "version": 1,
                    "started_at": NOW,
                    "expected_end_at": None,
                    "updated_at": NOW,
                    "persisted": True,
                    "available_for_character_runtime": True,
                    "discovery_allowed": True,
                },
            )
        elif path == f"/api/deployments/{DEPLOYMENT_ID}/presence/rhythm":
            fulfill(
                route,
                {
                    "deployment_id": DEPLOYMENT_ID,
                    "enabled": False,
                    "preferred_sleep_start_minute": 0,
                    "sleep_duration_min_minutes": 0,
                    "sleep_duration_max_minutes": 0,
                    "variation_minutes": 0,
                    "config_version": 1,
                    "schedule_local_date": "2026-09-07",
                    "schedule_timezone": "Asia/Kuala_Lumpur",
                    "scheduled_sleep_at": None,
                    "scheduled_wake_at": None,
                    "next_transition_at": None,
                    "next_state": "",
                    "last_transition_at": None,
                    "last_transition_reason": "fixture",
                },
            )
        elif path == f"/api/deployments/{DEPLOYMENT_ID}/conversation-structure":
            fulfill(route, data["structure"])
        elif path == f"/api/deployments/{DEPLOYMENT_ID}/knowledge-gaps/{GAP_ID}/candidates":
            fulfill(route, {"items": [data["candidate"]]})
        elif path == candidate_review_path and method == "POST":
            accepted = dict(
                data["candidate"],
                status="accepted",
                validated_evidence_ref="discovery_item:item-1",
                reviewed_at=NOW,
                reviewed_by="admin-1",
            )
            fulfill(route, {"gap": data["gap"], "candidate": accepted})
        elif path == f"/api/deployments/{DEPLOYMENT_ID}/beliefs/{BELIEF_ID}":
            fulfill(route, data["belief"])
        elif (
            path == f"/api/deployments/{DEPLOYMENT_ID}/beliefs/{BELIEF_ID}/correct"
            and method == "POST"
        ):
            corrected = dict(data["belief"], value_text="Corrected place", updated_at=NOW)
            fulfill(
                route,
                {
                    "action": "correct",
                    "belief": corrected,
                    "previous_belief_ids": [BELIEF_ID],
                },
            )
        else:
            unmatched_requests.append(f"{method} {path}")
            fulfill(route, {"detail": f"No local fixture for {method} {path}"}, status=404)

    page.route("**/api/**", handler)


def require_write(
    writes: list[tuple[str, dict[str, Any]]], path: str, expected: dict[str, Any]
) -> None:
    for actual_path, payload in writes:
        if actual_path == path and all(
            payload.get(key) == value for key, value in expected.items()
        ):
            return
    raise AssertionError(
        f"Portal did not send required request {path} with {expected}; writes were {writes}"
    )


def run(base_url: str) -> None:
    writes: list[tuple[str, dict[str, Any]]] = []
    unmatched_requests: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_responses: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "response",
            lambda response: (
                failed_responses.append(
                    f"{response.status} {response.request.method} {urlparse(response.url).path}"
                )
                if response.status >= 400
                else None
            ),
        )
        page.on(
            "console",
            lambda message: (
                console_errors.append(message.text) if message.type == "error" else None
            ),
        )
        install_api_fixtures(page, writes, unmatched_requests)

        page.goto(base_url, wait_until="networkidle")
        page.get_by_role("button", name="Deployments", exact=True).click()
        page.get_by_role("button", name="Edit connection", exact=True).click()
        page.get_by_text(f"Internal Connection ID: {CONNECTION_ID}", exact=True).wait_for()
        page.get_by_role("button", name="Copy Connection ID", exact=True).click()
        page.get_by_role("button", name="Copied", exact=True).wait_for()
        copied = page.evaluate("navigator.clipboard.readText()")
        if copied != CONNECTION_ID:
            raise AssertionError(
                f"Copy Connection ID produced {copied!r}, not the internal Connection UUID"
            )
        connection_drawer = page.get_by_role(
            "dialog", name="Edit fixed Discord connection", exact=True
        )
        connection_drawer.get_by_role(
            "button", name="Edit fixed Discord connection", exact=True
        ).click()
        connection_drawer.wait_for(state="hidden")

        page.get_by_role("button", name="Intelligence", exact=True).click()
        page.get_by_role("button", name="Conversation", exact=True).click()
        page.get_by_role("button", name="Entities", exact=False).click()
        page.get_by_role("button", name="Review candidates", exact=True).click()
        page.get_by_text("Verified candidate", exact=True).wait_for()
        page.get_by_role("button", name="Accept with evidence", exact=True).click()
        page.get_by_text("No candidates are awaiting review.", exact=True).wait_for()
        require_write(
            writes,
            f"/api/deployments/{DEPLOYMENT_ID}/knowledge-gaps/{GAP_ID}/candidates/"
            f"{CANDIDATE_ID}/review",
            {
                "action": "accept",
                "validated_evidence_ref": "discovery_item:item-1",
                "resolved_fields": ["birthplace"],
                "confidence": 0.7,
            },
        )

        candidate_drawer = page.get_by_role(
            "dialog", name="Review Knowledge Gap candidates", exact=True
        )
        candidate_drawer.get_by_role(
            "button", name="Review Knowledge Gap candidates", exact=True
        ).click()
        candidate_drawer.wait_for(state="hidden")
        page.get_by_role("button", name="Beliefs", exact=False).click()
        page.get_by_role("button", name="Manage belief", exact=True).click()
        belief_drawer = page.get_by_role("dialog", name="Manage belief", exact=True)
        belief_drawer.get_by_text("lives_in", exact=True).wait_for()
        correction_form = belief_drawer.get_by_role("form", name="Correct belief", exact=True)
        correction_form.get_by_role("textbox", name="New value", exact=True).fill("Corrected place")
        correction_form.get_by_role("textbox", name="Reason", exact=True).fill(
            "Confirmed in the source"
        )
        correction_form.get_by_role("button", name="Save correction", exact=True).click()
        belief_drawer.get_by_text("Corrected place", exact=True).wait_for()
        require_write(
            writes,
            f"/api/deployments/{DEPLOYMENT_ID}/beliefs/{BELIEF_ID}/correct",
            {
                "value_text": "Corrected place",
                "domain": "general",
                "reason": "Confirmed in the source",
                "confidence": 0.8,
            },
        )

        diagnostics = {
            "unmocked_api_requests": unmatched_requests,
            "failed_responses": failed_responses,
            "page_errors": page_errors,
            "console_errors": console_errors,
        }
        if any(diagnostics.values()):
            raise AssertionError(f"Portal browser diagnostics: {json.dumps(diagnostics)}")
        context.close()
        browser.close()
    print(
        "PASS: Portal first-use connection UUID, candidate provenance, and belief correction flow"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        type=local_base_url,
        required=True,
        help="loopback URL for a running Portal server",
    )
    args = parser.parse_args()
    run(args.base_url)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise
