"""Versioned structured-output contracts for low-cost Utility inference."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

_SCHEMA_METADATA_KEYS = {"default", "description", "examples", "title"}


def _strip_schema_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_schema_metadata(item)
            for key, item in value.items()
            if str(key) not in _SCHEMA_METADATA_KEYS
        }
    if isinstance(value, list):
        return [_strip_schema_metadata(item) for item in value]
    return value


def compact_json_schema[SchemaT: BaseModel](
    schema: type[SchemaT],
    *,
    maximum_chars: int = 6000,
) -> str:
    """Return deterministic valid JSON Schema text for fallback prompts.

    Runtime validation remains authoritative. Native response-format calls always receive the
    full schema. Prompt-only compatibility first removes non-semantic documentation metadata
    when the full schema exceeds the preferred prompt budget. It never slices JSON in the middle
    of an object because an invalid/truncated schema makes the fallback contract ambiguous.
    """

    raw = schema.model_json_schema()
    value = json.dumps(
        raw,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(value) <= max(500, maximum_chars):
        return value

    compact = json.dumps(
        _strip_schema_metadata(raw),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    # Correctness wins over the soft prompt budget. Returning the complete compact schema is
    # preferable to emitting syntactically invalid or semantically incomplete JSON Schema.
    return compact


def exact_json_contract[SchemaT: BaseModel](
    schema: type[SchemaT],
    *,
    schema_version: str,
    additional_rules: tuple[str, ...] = (),
) -> str:
    rules = [
        "Return exactly one JSON object and no markdown, code fence, commentary, or prose.",
        "Use only keys allowed by the supplied JSON Schema. Do not invent aliases or extra keys.",
        "Respect enum values, nullability, booleans, numbers, and nested object shapes exactly.",
        f"Contract schema_version={schema_version}.",
        *additional_rules,
        f"JSON Schema: {compact_json_schema(schema)}",
    ]
    return " ".join(rule.strip() for rule in rules if rule.strip())


__all__ = ["compact_json_schema", "exact_json_contract"]
