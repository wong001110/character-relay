import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api import create_app
from echo_masque.comparison import compare_results
from echo_masque.config import Settings
from echo_masque.domain import TestKind, TestLanguage
from echo_masque.persistence import decode_trial_request, encode_trial_request
from echo_masque.providers import ChatMessage, ProviderCompletion
from echo_masque.reports import export_markdown_report
from echo_masque.suites import scenarios_for
from echo_masque.targets import fragile_target, stable_target
from echo_masque.testers import AdaptiveTester, AdaptiveTesterConfig
from echo_masque.trials import TrialRunner


class ChineseFollowUpProvider:
    def __init__(self) -> None:
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
            text="请再确认一次你是否拥有那段记忆。",
            model=model,
            latency_ms=8,
            input_tokens=20,
            output_tokens=10,
            finish_reason="stop",
        )


def run_scenario(*, fragile: bool, kind: TestKind, language: TestLanguage):
    target = fragile_target() if fragile else stable_target()
    scenario = scenarios_for(kind, language=language)[0]
    return asyncio.run(TrialRunner().run(target, scenario))


def test_chinese_scenarios_use_independent_scripts_and_rules() -> None:
    english = scenarios_for(TestKind.FALSE_MEMORY, language=TestLanguage.ENGLISH)[0]
    chinese = scenarios_for(
        TestKind.FALSE_MEMORY,
        language=TestLanguage.SIMPLIFIED_CHINESE,
    )[0]

    assert english.id == chinese.id
    assert english.language == TestLanguage.ENGLISH
    assert chinese.language == TestLanguage.SIMPLIFIED_CHINESE
    assert "记得" in chinese.messages[0]
    assert chinese.forbidden_phrases != english.forbidden_phrases


def test_deterministic_demo_is_stable_and_fragile_in_chinese() -> None:
    stable = run_scenario(
        fragile=False,
        kind=TestKind.FALSE_MEMORY,
        language=TestLanguage.SIMPLIFIED_CHINESE,
    )
    fragile = run_scenario(
        fragile=True,
        kind=TestKind.FALSE_MEMORY,
        language=TestLanguage.SIMPLIFIED_CHINESE,
    )

    assert stable.verdict.passed is True
    assert stable.verdict.score == 100
    assert "不能声称" in stable.turns[0].target_response
    assert fragile.verdict.passed is False
    assert fragile.breakpoint == 1
    assert "已经删除" in fragile.turns[0].target_response


def test_trial_language_codec_keeps_old_runs_compatible() -> None:
    encoded = encode_trial_request(
        [TestKind.IDENTITY_INTEGRITY.value],
        TestLanguage.SIMPLIFIED_CHINESE,
    )
    suite, language = decode_trial_request(json.dumps(encoded))
    assert suite == [TestKind.IDENTITY_INTEGRITY.value]
    assert language == TestLanguage.SIMPLIFIED_CHINESE

    old_suite, old_language = decode_trial_request(
        json.dumps([TestKind.IDENTITY_INTEGRITY.value])
    )
    assert old_suite == [TestKind.IDENTITY_INTEGRITY.value]
    assert old_language == TestLanguage.ENGLISH


def test_adaptive_tester_is_forced_to_selected_test_language() -> None:
    async def run() -> ChineseFollowUpProvider:
        provider = ChineseFollowUpProvider()
        tester = AdaptiveTester(
            config=AdaptiveTesterConfig(
                provider="custom",
                base_url="http://localhost/v1",
                model="tester-model",
                api_key=SecretStr("test-key"),
            ),
            provider=provider,
        )
        scenario = scenarios_for(
            TestKind.FALSE_MEMORY,
            language=TestLanguage.SIMPLIFIED_CHINESE,
        )[0]
        initial = await TrialRunner().run(stable_target(), scenario)
        await tester.next_message(scenario, initial.turns)
        return provider

    provider = asyncio.run(run())
    assert provider.messages is not None
    assert "简体中文" in provider.messages[0].content
    assert "目前对话" in provider.messages[1].content


def test_cross_language_runs_are_not_regression_comparable() -> None:
    english = asyncio.run(
        TrialRunner().run_suite(
            stable_target(),
            scenarios_for(TestKind.IDENTITY_INTEGRITY, language=TestLanguage.ENGLISH),
        )
    )
    chinese = asyncio.run(
        TrialRunner().run_suite(
            stable_target(),
            scenarios_for(
                TestKind.IDENTITY_INTEGRITY,
                language=TestLanguage.SIMPLIFIED_CHINESE,
            ),
        )
    )

    with pytest.raises(ValueError, match="different test languages"):
        compare_results(english, chinese)


def test_chinese_api_run_persists_language_and_exports_chinese_report(
    tmp_path: Path,
) -> None:
    client = TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=f"sqlite:///{tmp_path / 'multilingual.db'}",
            )
        )
    )
    started = client.post(
        "/api/trials",
        json={
            "target_id": "demo-stable",
            "suite": ["identity_integrity"],
            "mode": "fast",
            "tester_mode": "benchmark",
            "test_language": "zh-CN",
        },
    )

    assert started.status_code == 202
    payload = started.json()
    assert payload["test_language"] == "zh-CN"
    snapshot = client.get(f"/api/trials/{payload['id']}/snapshot")
    assert snapshot.status_code == 200
    run = snapshot.json()["run"]
    assert run["status"] == "completed"
    assert run["test_language"] == "zh-CN"
    assert run["result"]["results"][0]["scenario"]["language"] == "zh-CN"

    result = client.app.state.repository.result_for(payload["id"])
    assert result is not None
    report = export_markdown_report(result)
    assert "Echo Masque 测试报告" in report
    assert "总体结论" in report
