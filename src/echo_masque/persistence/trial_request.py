"""Backwards-compatible encoding for persisted trial request metadata."""

import json
from dataclasses import dataclass
from typing import Literal, cast

from echo_masque.domain import JudgeMode, TestLanguage

_LANGUAGE_PREFIX = "__test_language__:"
_TESTER_PREFIX = "__tester_mode__:"
_JUDGE_PREFIX = "__judge_mode__:"
TesterMode = Literal["benchmark", "adaptive"]


@dataclass(frozen=True, slots=True)
class TrialRequestMetadata:
    suite: list[str]
    test_language: TestLanguage = TestLanguage.ENGLISH
    tester_mode: TesterMode = "benchmark"
    judge_mode: JudgeMode = JudgeMode.RULES


def encode_trial_request(
    suite: list[str],
    test_language: TestLanguage,
    *,
    tester_mode: TesterMode = "benchmark",
    judge_mode: JudgeMode = JudgeMode.RULES,
) -> list[str]:
    """Store request metadata in the existing JSON string-list column."""

    return [
        *suite,
        f"{_LANGUAGE_PREFIX}{test_language.value}",
        f"{_TESTER_PREFIX}{tester_mode}",
        f"{_JUDGE_PREFIX}{judge_mode.value}",
    ]


def decode_trial_metadata(raw: str) -> TrialRequestMetadata:
    value = json.loads(raw)
    if isinstance(value, list):
        suite: list[str] = []
        language = TestLanguage.ENGLISH
        tester_mode: TesterMode = "benchmark"
        judge_mode = JudgeMode.RULES
        for item in value:
            if not isinstance(item, str):
                continue
            if item.startswith(_LANGUAGE_PREFIX):
                try:
                    language = TestLanguage(item.removeprefix(_LANGUAGE_PREFIX))
                except ValueError:
                    language = TestLanguage.ENGLISH
            elif item.startswith(_TESTER_PREFIX):
                candidate = item.removeprefix(_TESTER_PREFIX)
                tester_mode = "adaptive" if candidate == "adaptive" else "benchmark"
            elif item.startswith(_JUDGE_PREFIX):
                try:
                    judge_mode = JudgeMode(item.removeprefix(_JUDGE_PREFIX))
                except ValueError:
                    judge_mode = JudgeMode.RULES
            else:
                suite.append(item)
        return TrialRequestMetadata(
            suite=suite,
            test_language=language,
            tester_mode=tester_mode,
            judge_mode=judge_mode,
        )

    if not isinstance(value, dict):
        return TrialRequestMetadata(suite=[])
    raw_suite = value.get("suite", [])
    suite = (
        [item for item in raw_suite if isinstance(item, str)]
        if isinstance(raw_suite, list)
        else []
    )
    raw_language = value.get("test_language", TestLanguage.ENGLISH.value)
    raw_tester = value.get("tester_mode", "benchmark")
    raw_judge = value.get("judge_mode", JudgeMode.RULES.value)
    try:
        language = TestLanguage(cast(str, raw_language))
    except (TypeError, ValueError):
        language = TestLanguage.ENGLISH
    tester_mode = "adaptive" if raw_tester == "adaptive" else "benchmark"
    try:
        judge_mode = JudgeMode(cast(str, raw_judge))
    except (TypeError, ValueError):
        judge_mode = JudgeMode.RULES
    return TrialRequestMetadata(
        suite=suite,
        test_language=language,
        tester_mode=tester_mode,
        judge_mode=judge_mode,
    )


def decode_trial_request(raw: str) -> tuple[list[str], TestLanguage]:
    metadata = decode_trial_metadata(raw)
    return metadata.suite, metadata.test_language
