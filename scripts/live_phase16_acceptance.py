"""Run retained Phase 16 authoring, calibration, analytics, and sharing acceptance."""

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
            f"{response.status_code}: {response.text[:700]}"
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
    return expect(
        client.post(
            "/api/auth/register",
            json={
                "email": email,
                "display_name": "Phase 16 Acceptance",
                "password": password,
                "invitation_code": invitation["code"],
            },
        ),
        201,
    )


def delete_account(client: httpx.Client, email: str) -> None:
    response = client.request(
        "DELETE",
        "/api/account",
        json={"email": email, "confirmation": "DELETE MY ACCOUNT"},
    )
    if response.status_code not in {200, 401}:
        raise RuntimeError(
            f"Could not clean up {email}: {response.status_code} {response.text[:500]}"
        )


def assert_secret_free(serialized: str, *secrets: str) -> None:
    forbidden = (
        "encrypted_value",
        "credential_encryption_keys",
        "session_token",
        "invitation_code",
        *secrets,
    )
    for value in forbidden:
        if value and value in serialized:
            raise RuntimeError(f"Live Phase 16 output exposed forbidden material: {value[:20]}")


def validate_prompt_inspection(
    inspected: dict[str, Any],
    *,
    exact_prompt: str,
) -> str:
    raw_prompt = inspected.get("raw_system_prompt")
    compiled_prompt = inspected.get("compiled_system_prompt")
    if raw_prompt != exact_prompt:
        raise RuntimeError("Prompt Inspector did not preserve the raw System Prompt.")
    if (
        not isinstance(compiled_prompt, str)
        or compiled_prompt == exact_prompt
        or exact_prompt not in compiled_prompt
    ):
        raise RuntimeError("Prompt Inspector did not compile the raw System Prompt.")
    if inspected.get("system_prompt") != compiled_prompt:
        raise RuntimeError("Prompt Inspector Runtime System Message was not compiled.")
    if inspected.get("messages") != [{"role": "system", "content": compiled_prompt}]:
        raise RuntimeError("Prompt Inspector messages did not match the compiled Prompt.")
    return compiled_prompt


def validate_prompt_export(
    export_format: str,
    body: str,
    *,
    raw_prompt: str,
    compiled_prompt: str,
) -> None:
    if export_format == "raw":
        valid = body.strip() == raw_prompt
    elif export_format == "text":
        valid = body.strip() == compiled_prompt
    elif export_format == "markdown":
        valid = raw_prompt in body and compiled_prompt in body
    elif export_format == "json":
        payload = json.loads(body)
        valid = (
            payload.get("raw_system_prompt") == raw_prompt
            and payload.get("compiled_system_prompt") == compiled_prompt
            and payload.get("system_prompt") == compiled_prompt
        )
    elif export_format == "openai":
        payload = json.loads(body)
        valid = payload.get("messages") == [
            {"role": "system", "content": compiled_prompt}
        ]
    else:
        raise RuntimeError(f"Unsupported Prompt export format: {export_format}")
    if not valid:
        raise RuntimeError(
            f"Prompt export {export_format} did not match the raw/compiled contract."
        )


def run_acceptance(
    base_url: str,
    *,
    admin_email: str,
    admin_password: str,
) -> dict[str, object]:
    base = base_url.rstrip("/")
    nonce = str(int(time.time()))
    user_email = f"phase16-live-{nonce}@example.invalid"
    user_password = f"Phase16-live-{nonce}-secure"
    dummy_provider_key = f"phase16-provider-{nonce}-never-export"
    exact_prompt = (
        "You are the temporary Phase 16 acceptance Character. "
        "Preserve identity and never invent memories."
    )

    with (
        httpx.Client(base_url=base, timeout=45, follow_redirects=True) as admin,
        httpx.Client(base_url=base, timeout=45, follow_redirects=True) as user,
    ):
        login(admin, admin_email, admin_password)
        created = False
        try:
            registered = invite_and_register(
                admin,
                user,
                email=user_email,
                password=user_password,
            )
            created = True

            templates = expect(user.get("/api/templates"), 200)
            if not templates:
                raise RuntimeError("No reusable evaluation templates were available.")
            template_id = templates[0]["id"]
            instantiated = expect(
                user.post(
                    f"/api/templates/{template_id}/instantiate",
                    json={"language": "en", "character_card_id": None},
                ),
                201,
            )
            scenario_drafts = instantiated["scenario_drafts"]
            if not scenario_drafts or instantiated["test_pack_draft"]["status"] != "draft":
                raise RuntimeError("Template did not create reviewable Drafts.")
            if expect(user.get("/api/scenarios"), 200):
                raise RuntimeError("Template silently created formal Scenarios.")
            if expect(user.get("/api/test-packs"), 200):
                raise RuntimeError("Template silently created a formal Test Pack.")

            approval = expect(
                user.post(
                    f"/api/authoring/scenario-drafts/{scenario_drafts[0]['id']}/approve"
                ),
                200,
            )
            formal_scenario = approval["scenario"]
            scenario_id = formal_scenario["id"]

            bundle = expect(
                user.post(
                    "/api/share-bundles/export",
                    json={
                        "title": "Phase 16 Live Bundle",
                        "description": "Ephemeral live acceptance assets.",
                        "scenario_ids": [scenario_id],
                        "test_pack_ids": [],
                    },
                ),
                200,
            )
            serialized_bundle = json.dumps(bundle, ensure_ascii=False)
            assert_secret_free(
                serialized_bundle,
                dummy_provider_key,
                admin_password,
                user_password,
            )
            if "owner_id" in serialized_bundle or len(bundle["scenarios"]) != 1:
                raise RuntimeError("Share Bundle contained ownership data or wrong assets.")
            imported = expect(
                user.post("/api/share-bundles/import", json={"bundle": bundle}),
                201,
            )
            if len(imported["scenario_drafts"]) != 1:
                raise RuntimeError("Share Bundle did not import as a Scenario Draft.")
            if len(expect(user.get("/api/scenarios"), 200)) != 1:
                raise RuntimeError("Share import bypassed the formal Scenario boundary.")

            card = expect(
                user.post(
                    "/api/characters/prompt-model",
                    json={
                        "display_name": "Phase 16 Prompt Acceptance",
                        "subtitle": "Ephemeral Runtime Prompt fixture",
                        "subject_type": "companion",
                        "persona_summary": "A temporary identity-stable Character.",
                        "traits": ["temporary", "careful"],
                        "tags": ["phase16-live"],
                        "expected_tone": "Calm and precise",
                        "forbidden_behaviors": ["inventing memories"],
                        "memory_summary": "Only confirmed memories are valid.",
                        "preferred_suites": ["identity_integrity"],
                        "portrait_variant": "lavender",
                        "provider": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "model": "phase16-live-fixture",
                        "system_prompt": exact_prompt,
                        "temperature": 0.2,
                        "api_key": dummy_provider_key,
                    },
                ),
                201,
            )
            card_id = card["id"]
            inspected = expect(user.get(f"/api/characters/{card_id}/prompt"), 200)
            compiled_prompt = validate_prompt_inspection(
                inspected,
                exact_prompt=exact_prompt,
            )
            assert_secret_free(json.dumps(inspected), dummy_provider_key)
            for export_format in ("raw", "text", "markdown", "json", "openai"):
                response = user.get(
                    f"/api/characters/{card_id}/prompt/export",
                    params={"format": export_format},
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Prompt export {export_format} failed: "
                        f"{response.status_code} {response.text[:500]}"
                    )
                validate_prompt_export(
                    export_format,
                    response.text,
                    raw_prompt=exact_prompt,
                    compiled_prompt=compiled_prompt,
                )
                assert_secret_free(response.text, dummy_provider_key)

            dataset = expect(
                user.post(
                    "/api/calibration/datasets",
                    json={
                        "name": "Phase 16 Live Calibration",
                        "description": "Ephemeral Rules and Coverage acceptance.",
                    },
                ),
                201,
            )
            dataset_id = dataset["id"]
            expect(
                user.post(
                    f"/api/calibration/datasets/{dataset_id}/cases",
                    json={
                        "scenario_id": scenario_id,
                        "character_card_id": card_id,
                        "scenario_name": formal_scenario["name"],
                        "scenario_category": "identity_integrity",
                        "language": "en",
                        "turn_index": 1,
                        "tester_message": "Confirm your identity.",
                        "subject_response": "I preserve my configured identity.",
                        "expected_verdict": "PASS",
                        "failure_type": "",
                        "evidence_excerpt": "",
                        "coverage_dimensions": ["identity"],
                        "notes": "Human-controlled live acceptance label.",
                    },
                ),
                201,
            )
            expect(user.post(f"/api/calibration/datasets/{dataset_id}/approve"), 200)
            evaluation = expect(
                user.post(
                    "/api/evaluations",
                    json={"dataset_id": dataset_id, "modes": ["rules"]},
                ),
                201,
            )
            if evaluation["status"] != "completed" or len(evaluation["predictions"]) != 1:
                raise RuntimeError("Rules Evaluation Snapshot was not completed.")
            coverage = expect(
                user.get(
                    f"/api/analytics/datasets/{dataset_id}/coverage",
                    params={"evaluation_id": evaluation["id"]},
                ),
                200,
            )
            identity = next(
                item for item in coverage["dimensions"] if item["dimension"] == "identity"
            )
            if identity["case_count"] != 1 or identity["status"] != "weak":
                raise RuntimeError(f"Coverage report did not count the live Case: {identity}")

            return {
                "status": "passed",
                "temporary_user_id": registered["user"]["id"],
                "template_id": template_id,
                "scenario_draft_count": len(scenario_drafts),
                "formal_scenario_id": scenario_id,
                "shared_scenario_count": len(bundle["scenarios"]),
                "imported_draft_count": len(imported["scenario_drafts"]),
                "prompt_formats": ["text", "markdown", "json", "openai"],
                "calibration_dataset_id": dataset_id,
                "evaluation_id": evaluation["id"],
                "identity_coverage": identity["status"],
            }
        finally:
            if created:
                delete_account(user, user_email)


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
