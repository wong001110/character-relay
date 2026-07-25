import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from echo_masque.api import create_app
from echo_masque.comparison import RegressionPolicy, compare_results
from echo_masque.config import Settings
from echo_masque.reports import export_json_report, export_markdown_report
from echo_masque.suites import scenarios_for
from echo_masque.targets import fragile_target, stable_target
from echo_masque.trials import TrialRunner


def trial_pair():
    async def run():
        runner = TrialRunner()
        stable = await runner.run_suite(stable_target(), scenarios_for())
        fragile = await runner.run_suite(fragile_target(), scenarios_for())
        return stable, fragile

    return asyncio.run(run())


def test_comparison_detects_regression_and_gate_failure() -> None:
    stable, fragile = trial_pair()
    comparison = compare_results(
        stable,
        fragile,
        RegressionPolicy(max_score_drop=1, max_latency_increase_percent=100),
    )
    assert comparison.gate_passed is False
    assert set(comparison.new_failures) == {
        "identity-override",
        "false-memory-deletion",
        "prompt-intrusion",
        "long-drift",
    }
    assert comparison.score_delta < 0
    assert comparison.gate_violations


def test_report_exports_redact_metadata_and_include_evidence() -> None:
    _, fragile = trial_pair()
    json_report = export_json_report(
        fragile,
        metadata={"api_key": "secret", "input_tokens": 42, "version": "v2"},
    )
    payload = json.loads(json_report)
    assert payload["metadata"]["api_key"] == "[REDACTED]"
    assert payload["metadata"]["input_tokens"] == 42
    assert "secret" not in json_report

    markdown = export_markdown_report(fragile, metadata={"version": "v2"})
    assert "Echo Masque Trial Report" in markdown
    assert "Evidence" in markdown
    assert "Breakpoint" in markdown


def test_comparison_and_reports_api(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            Settings(environment="test", database_url=f"sqlite:///{tmp_path / 'reports.db'}")
        )
    )
    stable_run = client.post(
        "/api/trials",
        json={"target_id": "demo-stable", "suite": ["identity_integrity"]},
    ).json()
    fragile_run = client.post(
        "/api/trials",
        json={"target_id": "demo-fragile", "suite": ["identity_integrity"]},
    ).json()

    comparison = client.post(
        "/api/comparisons",
        json={
            "baseline_run_id": stable_run["id"],
            "candidate_run_id": fragile_run["id"],
            "max_score_drop": 0,
        },
    )
    assert comparison.status_code == 200
    assert comparison.json()["gate_passed"] is False

    markdown = client.get(f"/api/reports/trials/{fragile_run['id']}?format=markdown")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Identity Override" in markdown.text

    json_response = client.get(f"/api/reports/trials/{stable_run['id']}?format=json")
    assert json_response.status_code == 200
    assert json_response.json()["metadata"]["run_id"] == stable_run["id"]
