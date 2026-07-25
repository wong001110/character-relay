"""Backwards-compatible encoding for persisted trial suite requests."""

import json
from typing import cast

from echo_masque.domain import TestLanguage


def encode_trial_request(suite: list[str], test_language: TestLanguage) -> str:
    return json.dumps(
        {
            "suite": suite,
            "test_language": test_language.value,
        }
    )


def decode_trial_request(raw: str) -> tuple[list[str], TestLanguage]:
    value = json.loads(raw)
    if isinstance(value, list):
        suite = [item for item in value if isinstance(item, str)]
        return suite, TestLanguage.ENGLISH
    if not isinstance(value, dict):
        return [], TestLanguage.ENGLISH

    raw_suite = value.get("suite", [])
    suite = (
        [item for item in raw_suite if isinstance(item, str)]
        if isinstance(raw_suite, list)
        else []
    )
    raw_language = value.get("test_language", TestLanguage.ENGLISH.value)
    try:
        language = TestLanguage(cast(str, raw_language))
    except (TypeError, ValueError):
        language = TestLanguage.ENGLISH
    return suite, language
