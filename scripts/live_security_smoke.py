"""Run the Phase 15 multi-account and encrypted-vault acceptance against a live service."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import httpx


def expect(response: httpx.Response, status_code: int) -> Any:
    if response.status_code != status_code:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code}: {response.text[:500]}"
        )
    if status_code == 204:
        return None
    return response.json()


def login(client: httpx.Client, email: str, password: str) -> dict[str, Any]:
    return expect(
        client.post("/api/auth/login", json={"email": email, "password": password}),
        200,
    )


def invite_and_register(
    admin: httpx.Client,
    client: httpx.Client,
    *,
    email: str,
    password: str,
) -> dict[str, Any]:
    invitation = expect(
        admin.post(
            "/api/admin/invitations",
            json={"email": email, "role": "user", "expires_in_days": 1},
        ),
        201,
    )
    code = invitation["code"]
    return expect(
        client.post(
            "/api/auth/register",
            json={
                "email": email,
                "display_name": email.split("@", maxsplit=1)[0],
                "password": password,
                "invitation_code": code,
            },
        ),
        201,
    )


def purge_legacy_test_accounts(admin: httpx.Client) -> None:
    response = admin.delete("/api/admin/synthetic-test-users")
    if response.status_code != 200:
        raise RuntimeError(
            "Could not purge legacy synthetic test accounts: "
            f"{response.status_code} {response.text[:500]}"
        )


def hard_delete_test_account(admin: httpx.Client, user_id: str) -> None:
    response = admin.delete(f"/api/admin/synthetic-test-users/{user_id}")
    if response.status_code not in {200, 404}:
        raise RuntimeError(
            f"Could not hard-delete synthetic user {user_id}: "
            f"{response.status_code} {response.text[:500]}"
        )


def run_acceptance(
    base_url: str,
    *,
    admin_email: str,
    admin_password: str,
) -> dict[str, object]:
    base = base_url.rstrip("/")
    nonce = str(int(time.time()))
    user_password = f"Phase15-live-{nonce}-secure"
    user_a_email = f"phase15-a-{nonce}@example.invalid"
    user_b_email = f"phase15-b-{nonce}@example.invalid"
    dummy_provider_key = f"phase15-dummy-{nonce}-never-log"

    with (
        httpx.Client(base_url=base, timeout=30, follow_redirects=True) as admin,
        httpx.Client(base_url=base, timeout=30, follow_redirects=True) as user_a,
        httpx.Client(base_url=base, timeout=30, follow_redirects=True) as user_b,
    ):
        login(admin, admin_email, admin_password)
        # Remove historical soft-deleted smoke fixtures before creating this run. The purge
        # endpoint ignores ordinary deleted accounts and active Phase 15 users from another run.
        purge_legacy_test_accounts(admin)
        user_a_id = ""
        user_b_id = ""
        try:
            auth_a = invite_and_register(
                admin,
                user_a,
                email=user_a_email,
                password=user_password,
            )
            user_a_id = str(auth_a["user"]["id"])
            auth_b = invite_and_register(
                admin,
                user_b,
                email=user_b_email,
                password=user_password,
            )
            user_b_id = str(auth_b["user"]["id"])

            card = expect(
                user_a.post(
                    "/api/characters/prompt-model",
                    json={
                        "display_name": "Phase 15 Live Ann",
                        "subtitle": "Ephemeral security acceptance",
                        "subject_type": "companion",
                        "persona_summary": "A temporary acceptance subject.",
                        "traits": ["temporary", "secure"],
                        "tags": ["phase15-live"],
                        "expected_tone": "Calm",
                        "forbidden_behaviors": ["credential disclosure"],
                        "memory_summary": "No retained user facts.",
                        "preferred_suites": ["identity_integrity"],
                        "portrait_variant": "lavender",
                        "provider": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "model": "deepseek-v4-flash",
                        "system_prompt": "You are a temporary Phase 15 acceptance subject.",
                        "temperature": 0.2,
                        "api_key": dummy_provider_key,
                    },
                ),
                201,
            )
            card_id = card["id"]

            expect(user_b.get(f"/api/characters/{card_id}"), 404)
            b_cards = expect(user_b.get("/api/characters"), 200)
            if any(item.get("id") == card_id for item in b_cards):
                raise RuntimeError("User B could list User A's Character Card.")

            credential = expect(
                user_a.get(f"/api/characters/{card_id}/credential"),
                200,
            )
            if not credential.get("configured") or credential.get("source") != "vault":
                raise RuntimeError(
                    "Character credential was not in the encrypted vault: "
                    f"{credential}"
                )

            rotated = expect(admin.post("/api/admin/credentials/rotate"), 200)
            if int(rotated.get("rotated_count", 0)) < 1:
                raise RuntimeError(f"Vault rotation did not rotate a credential: {rotated}")
            after_rotation = expect(
                user_a.get(f"/api/characters/{card_id}/credential"),
                200,
            )
            if not after_rotation.get("configured"):
                raise RuntimeError("Credential became unavailable after key rotation.")

            archive = expect(user_a.get("/api/account/export"), 200)
            serialized = json.dumps(archive)
            if dummy_provider_key in serialized or "encrypted_value" in serialized:
                raise RuntimeError("Workspace export exposed credential material.")

            return {
                "status": "passed",
                "user_a": user_a_id,
                "user_b": user_b_id,
                "character_id": card_id,
                "rotation_count": rotated["rotated_count"],
                "key_version": rotated["key_version"],
            }
        finally:
            # Super Admin cleanup dispatches through the full owner lifecycle first, then
            # removes the synthetic User row, invitations, trace rows, and audit FK actor.
            if user_a_id:
                hard_delete_test_account(admin, user_a_id)
            if user_b_id:
                hard_delete_test_account(admin, user_b_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()
    result = run_acceptance(
        args.base_url,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
