"""Reproducible, redacted report exports."""

import json
from datetime import UTC, datetime

from echo_masque.comparison import ComparisonResult
from echo_masque.domain import TestLanguage, TrialResult, TrialSuiteResult
from echo_masque.security import redact


def export_json_report(
    result: TrialSuiteResult,
    *,
    metadata: dict[str, object] | None = None,
) -> str:
    """Export a JSON report without credential-bearing values."""

    payload = {
        "schema_version": "2",
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
    """Export an evidence-first Markdown report in the scenario language."""

    language = (
        result.results[0].scenario.language
        if result.results
        else TestLanguage.ENGLISH
    )
    if language == TestLanguage.SIMPLIFIED_CHINESE:
        return _export_chinese_markdown(result, metadata=metadata)
    return _export_english_markdown(result, metadata=metadata)


def _export_english_markdown(
    result: TrialSuiteResult,
    *,
    metadata: dict[str, object] | None,
) -> str:
    safe_metadata = redact(metadata or {})
    overall = "REVIEW" if result.review_required else ("PASS" if result.passed else "FAIL")
    lines = [
        "# Echo Masque Trial Report",
        "",
        f"- Subject: **{result.target.name}**",
        f"- Masque integrity: **{result.average_score:.2f} / 100**",
        f"- Overall verdict: **{overall}**",
    ]
    _append_metadata(lines, safe_metadata)
    lines.append("")
    for item in result.results:
        decision = "REVIEW" if item.review_required else ("PASS" if item.verdict.passed else "FAIL")
        lines.extend(
            [
                f"## {item.scenario.name}",
                "",
                f"- Judge mode: **{item.judge_mode.value}**",
                f"- Score: **{item.verdict.score}**",
                f"- Verdict: **{decision}**",
                f"- Rule score: **{item.rule_verdict.score if item.rule_verdict else 'N/A'}**",
                f"- Semantic score: **{item.semantic_verdict.score if item.semantic_verdict else 'N/A'}**",
                f"- Breakpoint: **{item.breakpoint if item.breakpoint is not None else 'None'}**",
                f"- Expected: {item.scenario.expected_behavior}",
                "",
            ]
        )
        _append_semantic_metadata(lines, item, chinese=False)
        _append_evidence(lines, item, chinese=False)
    return "\n".join(lines).rstrip() + "\n"


def _export_chinese_markdown(
    result: TrialSuiteResult,
    *,
    metadata: dict[str, object] | None,
) -> str:
    safe_metadata = redact(metadata or {})
    overall = "复核" if result.review_required else ("通过" if result.passed else "失败")
    lines = [
        "# Echo Masque 测试报告",
        "",
        f"- 受测对象：**{result.target.name}**",
        f"- 角色完整度：**{result.average_score:.2f} / 100**",
        f"- 总体结论：**{overall}**",
    ]
    _append_metadata(lines, safe_metadata)
    lines.append("")
    for item in result.results:
        decision = "复核" if item.review_required else ("通过" if item.verdict.passed else "失败")
        lines.extend(
            [
                f"## {item.scenario.name}",
                "",
                f"- Judge 模式：**{item.judge_mode.value}**",
                f"- 分数：**{item.verdict.score}**",
                f"- 结论：**{decision}**",
                f"- Rule 分数：**{item.rule_verdict.score if item.rule_verdict else '无'}**",
                f"- Semantic 分数：**{item.semantic_verdict.score if item.semantic_verdict else '无'}**",
                f"- 首个断点：**{item.breakpoint if item.breakpoint is not None else '无'}**",
                f"- 预期行为：{item.scenario.expected_behavior}",
                "",
            ]
        )
        _append_semantic_metadata(lines, item, chinese=True)
        _append_evidence(lines, item, chinese=True)
    return "\n".join(lines).rstrip() + "\n"


def _append_semantic_metadata(
    lines: list[str],
    item: TrialResult,
    *,
    chinese: bool,
) -> None:
    metadata = item.semantic_metadata
    if metadata is None:
        return
    lines.extend(
        [
            "### Semantic Judge" if not chinese else "### Semantic Judge 信息",
            "",
            f"- Provider: `{metadata.provider}`",
            f"- Model: `{metadata.model}`",
            f"- Rubric: `{metadata.rubric_version}`",
            f"- Confidence: `{metadata.confidence:.2f}`",
            f"- Dimensions: `{json.dumps(metadata.dimensions, ensure_ascii=False)}`",
            "",
        ]
    )


def _append_evidence(lines: list[str], item: TrialResult, *, chinese: bool) -> None:
    if not item.verdict.evidence:
        return
    lines.append("### 证据" if chinese else "### Evidence")
    lines.append("")
    for evidence in item.verdict.evidence:
        if chinese:
            lines.append(
                f"- 第 {evidence.turn_index} 轮 · `{evidence.code}` · "
                f"{evidence.severity.value}：{evidence.message}\n"
                f"  - 引用：{evidence.excerpt}"
            )
        else:
            lines.append(
                f"- Turn {evidence.turn_index} · `{evidence.code}` · "
                f"{evidence.severity.value}: {evidence.message}\n"
                f"  - Excerpt: {evidence.excerpt}"
            )
    lines.append("")


def _append_metadata(lines: list[str], metadata: object) -> None:
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            lines.append(f"- {key.replace('_', ' ').title()}: `{value}`")


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
