"""Versioned structured-output contracts for low-cost Utility inference."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def compact_json_schema(schema: type[SchemaT], *, maximum_chars: int = 6000) -> str:
    """Return a deterministic compact JSON Schema description for provider prompts.

    Runtime validation remains authoritative. This prompt contract is the compatibility path for
    providers that do not support native JSON Schema response formats.
    """

    value = json.dumps(
        schema.model_json_schema(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return value[: max(500, maximum_chars)]


def exact_json_contract(
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
