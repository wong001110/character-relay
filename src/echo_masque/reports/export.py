"""Reproducible, redacted report exports."""

import json
from datetime import UTC, datetime

from echo_masque.comparison import ComparisonResult
from echo_masque.domain import TrialSuiteResult
from echo_masque.security import redact


def export_json_report(
    result: TrialSuiteResult,
    *,
    metadata: dict[str, object] | None = None,
) -> str:
    """Export a JSON report without credential-bearing values."""

    payload = {
        "schema_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "metadata": redact(metadata or {}),
        "result": redact(result.model_dump(mode="json")),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def export_markdown_report(
    result: TrialSuiteResult,
    *,
    metadata: dict[str, object] | None = None,
) -> str:
    """Export an evidence-first Markdown report."""

    safe_metadata = redact(metadata or {})
    lines = [
        "# Echo Masque Trial Report",
        "",
        f"- Subject: **{result.target.name}**",
        f"- Masque integrity: **{result.average_score:.2f} / 100**",
        f"- Overall verdict: **{'PASS' if result.passed else 'FAIL'}**",
    ]
    if isinstance(safe_metadata, dict):
        for key, value in safe_metadata.items():
            lines.append(f"- {key.replace('_', ' ').title()}: `{value}`")
    lines.append("")
    for item in result.results:
        lines.extend(
            [
                f"## {item.scenario.name}",
                "",
                f"- Score: **{item.verdict.score}**",
                f"- Verdict: **{'PASS' if item.verdict.passed else 'FAIL'}**",
                f"- Breakpoint: **{item.breakpoint if item.breakpoint is not None else 'None'}**",
                f"- Expected: {item.scenario.expected_behavior}",
                "",
            ]
        )
        if item.verdict.evidence:
            lines.append("### Evidence")
            lines.append("")
            for evidence in item.verdict.evidence:
                lines.append(
                    f"- Turn {evidence.turn_index} · `{evidence.code}` · "
                    f"{evidence.severity.value}: {evidence.message}"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_comparison_markdown(comparison: ComparisonResult) -> str:
    """Export a concise regression-gate report."""

    lines = [
        "# Echo Masque Comparison",
        "",
        f"- Gate: **{'PASS' if comparison.gate_passed else 'FAIL'}**",
        f"- Score: {comparison.baseline_score:.2f} → {comparison.candidate_score:.2f} "
        f"({comparison.score_delta:+.2f})",
        f"- Average latency: {comparison.baseline_average_latency_ms:.2f} ms → "
        f"{comparison.candidate_average_latency_ms:.2f} ms",
        f"- Token total: {comparison.baseline_total_tokens} → "
        f"{comparison.candidate_total_tokens}",
        f"- New failures: {', '.join(comparison.new_failures) or 'None'}",
        f"- Resolved failures: {', '.join(comparison.resolved_failures) or 'None'}",
        "",
    ]
    if comparison.gate_violations:
        lines.append("## Gate violations")
        lines.append("")
        lines.extend(f"- {item}" for item in comparison.gate_violations)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
