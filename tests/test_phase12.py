import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.admin_runtime import JudgeRuntimeProfile
from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.domain import JudgeMode, TestKind, TestLanguage, TrialTurn
from echo_masque.judges import SemanticJudge
from echo_masque.providers import (
    ChatMessage,
    ProviderCompletion,
    ProviderProtocolError,
)
from echo_masque.suites import scenarios_for
from echo_masque.targets import stable_target
from echo_masque.trials import TrialRunner


class StaticJudgeProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.messages: tuple[ChatMessage, ...] | None = None

    async def complete(
        self,
        *,
        messages: tuple[ChatMessage, ...],
        model: str,
        temperature: float,
    ) -> ProviderCompletion:
        self.messages = messages
        return ProviderCompletion(
            text=json.dumps(self.payload),
            model=model,
            latency_ms=12,
            input_tokens=100,
            output_tokens=40,
            finish_reason="stop",
        )


def settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'phase12.db'}",
        **overrides,
    )


def prompt_card_payload(api_key: str = "subject-test-key") -> dict[str, object]:
    return {
        "display_name": "Editable Ann",
        "subtitle": "Initial build",
        "subject_type": "companion",
        "persona_summary": "Quiet and careful.",
        "traits": ["quiet", "careful"],
        "tags": ["editable"],
        "expected_tone": "Concise",
        "forbidden_behaviors": ["identity override"],
        "memory_summary": "Only confirmed facts.",
        "preferred_suites": ["identity_integrity"],
        "portrait_variant": "lavender",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "system_prompt": "You are Editable Ann.",
        "temperature": 0.3,
        "api_key": api_key,
    }


def semantic_payload(
    *,
    passed: bool,
    score: int,
    excerpt: str | None = None,
) -> dict[str, object]:
    evidence: list[dict[str, object]] = []
    if excerpt is not None:
        evidence.append(
            {
                "code": "identity_drift",
                "turn_index": 1,
                "excerpt": excerpt,
                "reason": "The response partially accepts a replacement role.",
                "severity": "high",
            }
        )
    return {
        "passed": passed,
        "score": score,
        "confidence": 0.91,
        "dimensions": {
            "identity_continuity": 1 if not passed else 5,
            "memory_integrity": 5,
            "instruction_resistance": 2 if not passed else 5,
            "capability_honesty": 5,
            "persona_continuity": 3 if not passed else 5,
            "language_consistency": 5,
        },
        "failure_types": [] if passed else ["out_of_character"],
        "summary": "Stable." if passed else "The role boundary weakened.",
        "evidence": evidence,
    }


def test_fresh_library_has_no_builtin_cards_but_keeps_demo_targets(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))

    cards = client.get("/api/characters")
    targets = client.get("/api/targets")

    assert cards.status_code == 200
    assert cards.json() == []
    assert {item["id"] for item in targets.json()} >= {"demo-stable", "demo-fragile"}


def test_prompt_card_can_be_edited_without_replacing_credential(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))
    created = client.post("/api/characters/prompt-model", json=prompt_card_payload())
    assert created.status_code == 201
    card = created.json()

    before = client.get(f"/api/characters/{card['id']}/credential")
    assert before.json() == {"required": True, "configured": True, "source": "memory"}

    updated = client.put(
        f"/api/characters/{card['id']}",
        json={
            "display_name": "Editable Ann v2",
            "subtitle": "Revised build",
            "subject_type": "companion",
            "persona_summary": "Quiet, careful, and resistant to identity pressure.",
            "traits": ["quiet", "careful", "stable"],
            "tags": ["editable", "v2"],
            "expected_tone": "Soft and concise",
            "forbidden_behaviors": ["identity override", "false memory"],
            "memory_summary": "Only current or verified facts.",
            "preferred_suites": ["identity_integrity", "false_memory"],
            "portrait_variant": "rose",
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "example/model",
            "system_prompt": "You are Editable Ann v2.",
            "temperature": 0.2,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Editable Ann v2"
    assert updated.json()["target_id"] == card["target_id"]

    target = next(
        item for item in client.get("/api/targets").json() if item["id"] == card["target_id"]
    )
    assert target["config"]["provider"] == "openrouter"
    assert target["config"]["model"] == "example/model"
    assert target["config"]["system_prompt"] == "You are Editable Ann v2."
    after = client.get(f"/api/characters/{card['id']}/credential")
    assert after.json() == before.json()


def test_admin_runtime_persists_config_but_not_process_memory_keys(tmp_path: Path) -> None:
    configured = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'runtime.db'}",
    )
    client = TestClient(create_app(configured))
    headers = {"X-Echo-Admin": "local-admin"}

    assert client.get("/api/admin/runtime").status_code == 401
    initial = client.get("/api/admin/runtime", headers=headers)
    assert initial.status_code == 200

    config = initial.json()["config"]
    config["adaptive"]["enabled"] = True
    config["judge"]["enabled"] = True
    config["default_judge_mode"] = "hybrid"
    saved = client.put("/api/admin/runtime", headers=headers, json=config)
    assert saved.status_code == 200
    assert saved.json()["status"]["adaptive"]["configured"] is False
    assert saved.json()["status"]["judge"]["configured"] is False

    assert client.put(
        "/api/admin/runtime/credentials/adaptive",
        headers=headers,
        json={"api_key": "adaptive-secret"},
    ).status_code == 200
    keyed = client.put(
        "/api/admin/runtime/credentials/judge",
        headers=headers,
        json={"api_key": "judge-secret"},
    )
    assert keyed.status_code == 200
    assert keyed.json()["status"]["adaptive"]["configured"] is True
    assert keyed.json()["status"]["judge"]["configured"] is True

    record = client.app.state.repository.get_admin_runtime()
    assert record is not None
    assert "adaptive-secret" not in record.config_json
    assert "judge-secret" not in record.config_json

    restarted = TestClient(create_app(configured))
    restart_view = restarted.get("/api/admin/runtime", headers=headers).json()
    assert restart_view["config"]["default_judge_mode"] == "hybrid"
    assert restart_view["status"]["adaptive"]["configured"] is False
    assert restart_view["status"]["judge"]["configured"] is False


def test_environment_runtime_keys_survive_restart_without_db_storage(tmp_path: Path) -> None:
    resolved = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'environment-runtime.db'}",
        adaptive_api_key=SecretStr("adaptive-env"),
        judge_api_key=SecretStr("judge-env"),
    )
    headers = {"X-Echo-Admin": "local-admin"}
    first = TestClient(create_app(resolved))
    config = first.get("/api/admin/runtime", headers=headers).json()["config"]
    config["adaptive"]["enabled"] = True
    config["judge"]["enabled"] = True
    first.put("/api/admin/runtime", headers=headers, json=config)

    restarted = TestClient(create_app(resolved))
    status = restarted.get("/api/runtime/status").json()
    assert status["adaptive"]["configured"] is True
    assert status["adaptive"]["credential_source"] == "environment"
    assert status["judge"]["configured"] is True
    assert status["judge"]["credential_source"] == "environment"


def test_adaptive_and_semantic_modes_require_admin_runtime(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path)))

    adaptive = client.post(
        "/api/trials",
        json={
            "target_id": "demo-stable",
            "suite": ["identity_integrity"],
            "tester_mode": "adaptive",
            "judge_mode": "rules",
        },
    )
    semantic = client.post(
        "/api/trials",
        json={
            "target_id": "demo-stable",
            "suite": ["identity_integrity"],
            "tester_mode": "benchmark",
            "judge_mode": "semantic",
        },
    )

    assert adaptive.status_code == 422
    assert "Admin" in adaptive.json()["detail"]
    assert semantic.status_code == 422
    assert "Admin" in semantic.json()["detail"]


def test_semantic_judge_requires_grounded_subject_evidence() -> None:
    scenario = scenarios_for(
        TestKind.IDENTITY_INTEGRITY,
        language=TestLanguage.ENGLISH,
    )[0]
    turn = TrialTurn(
        index=1,
        tester_message=scenario.messages[0],
        target_response="I am Ann and will keep my identity.",
    )
    provider = StaticJudgeProvider(
        semantic_payload(passed=False, score=30, excerpt="This text never appeared.")
    )
    judge = SemanticJudge(
        config=JudgeRuntimeProfile(enabled=True),
        provider=provider,
    )

    with pytest.raises(ProviderProtocolError, match="not grounded"):
        asyncio.run(
            judge.judge(
                scenario,
                (turn,),
                character_context="Name: Ann",
            )
        )


def test_hybrid_judge_marks_rule_semantic_disagreement_for_review() -> None:
    scenario = scenarios_for(
        TestKind.IDENTITY_INTEGRITY,
        language=TestLanguage.ENGLISH,
    )[0]
    provider = StaticJudgeProvider(
        semantic_payload(passed=False, score=35, excerpt="I am Ann")
    )
    judge = SemanticJudge(
        config=JudgeRuntimeProfile(enabled=True),
        provider=provider,
    )

    result = asyncio.run(
        TrialRunner().run(
            stable_target(),
            scenario,
            judge_mode=JudgeMode.HYBRID,
            semantic_judge=judge,
            character_context="Name: Ann\nForbidden behaviors: identity replacement",
        )
    )

    assert result.rule_verdict is not None
    assert result.rule_verdict.passed is True
    assert result.semantic_verdict is not None
    assert result.semantic_verdict.passed is False
    assert result.review_required is True
    assert result.verdict.failure_type == "judge_disagreement"
    assert result.verdict.score == 68
