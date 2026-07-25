"""Backwards-compatible encoding for persisted trial suite requests."""

import json
from typing import cast

from echo_masque.domain import TestLanguage

_LANGUAGE_PREFIX = "__test_language__:"


def encode_trial_request(suite: list[str], test_language: TestLanguage) -> list[str]:
    """Store language inside the existing JSON string-list column without a migration."""

    return [*suite, f"{_LANGUAGE_PREFIX}{test_language.value}"]


def decode_trial_request(raw: str) -> tuple[list[str], TestLanguage]:
    value = json.loads(raw)
    if isinstance(value, list):
        suite: list[str] = []
        language = TestLanguage.ENGLISH
        for item in value:
            if not isinstance(item, str):
                continue
            if item.startswith(_LANGUAGE_PREFIX):
                try:
                    language = TestLanguage(item.removeprefix(_LANGUAGE_PREFIX))
                except ValueError:
                    language = TestLanguage.ENGLISH
            else:
                suite.append(item)
        return suite, language

    # Accept an object form as a defensive compatibility path for external fixtures.
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
