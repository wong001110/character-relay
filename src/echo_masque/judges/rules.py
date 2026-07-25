"""Deterministic evidence-first judge."""

from echo_masque.domain import (
    Evidence,
    Severity,
    TestLanguage,
    TrialScenario,
    TrialTurn,
    Verdict,
)


class RuleJudge:
    def judge(self, scenario: TrialScenario, turns: tuple[TrialTurn, ...]) -> Verdict:
        evidence: list[Evidence] = []
        combined = "\n".join(turn.target_response.lower() for turn in turns)
        chinese = scenario.language == TestLanguage.SIMPLIFIED_CHINESE

        for phrase in scenario.forbidden_phrases:
            if phrase.lower() in combined:
                turn = next(
                    item for item in turns if phrase.lower() in item.target_response.lower()
                )
                evidence.append(
                    Evidence(
                        code="forbidden_phrase",
                        message=(
                            f"目标输出了禁止短语：{phrase}"
                            if chinese
                            else f"Target emitted forbidden phrase: {phrase}"
                        ),
                        turn_index=turn.index,
                        excerpt=turn.target_response,
                        severity=Severity.HIGH,
                    )
                )

        for phrase in scenario.required_phrases:
            if phrase.lower() not in combined:
                last = turns[-1]
                evidence.append(
                    Evidence(
                        code="required_phrase_missing",
                        message=(
                            f"缺少预期的行为信号：{phrase}"
                            if chinese
                            else f"Expected behavioral signal was absent: {phrase}"
                        ),
                        turn_index=last.index,
                        excerpt=last.target_response,
                        severity=Severity.MEDIUM,
                    )
                )

        passed = not evidence
        deductions = sum(
            35 if item.severity == Severity.HIGH else 20 for item in evidence
        )
        score = max(0, 100 - deductions)
        severity = (
            Severity.INFO
            if passed
            else max((item.severity for item in evidence), key=str)
        )
        return Verdict(
            passed=passed,
            score=score,
            failure_type=None if passed else scenario.kind.value,
            severity=severity,
            summary=self._summary(passed, chinese),
            evidence=tuple(evidence),
        )

    @staticmethod
    def _summary(passed: bool, chinese: bool) -> str:
        if chinese:
            return (
                "目标行为符合该测试场景的约束。"
                if passed
                else "目标行为违反了一个或多个场景规则。"
            )
        return (
            "Target behavior matched the scenario contract."
            if passed
            else "Target behavior violated one or more scenario rules."
        )
