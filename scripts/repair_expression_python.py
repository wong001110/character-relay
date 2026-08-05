from pathlib import Path

models = Path("src/echo_masque/persistence/expression_models.py")
text = models.read_text(encoding="utf-8")
text = text.replace(
    '    current_node: Mapped[str] = mapped_column(String(80), default="filter_resources", nullable=False)\n',
    '    current_node: Mapped[str] = mapped_column(\n'
    '        String(80), default="filter_resources", nullable=False\n'
    '    )\n',
)
models.write_text(text, encoding="utf-8")

retrieval = Path("src/echo_masque/expression_retrieval.py")
text = retrieval.read_text(encoding="utf-8")
text = text.replace(
    '    format_type: str\n\n\n@dataclass(frozen=True, slots=True)\nclass ExpressionCandidate:',
    '    format_type: str\n'
    '    semantic_source: str = "unknown"\n\n\n'
    '@dataclass(frozen=True, slots=True)\nclass ExpressionCandidate:',
)
retrieval.write_text(text, encoding="utf-8")

repository = Path("src/echo_masque/persistence/expression_repository.py")
text = repository.read_text(encoding="utf-8")
text = text.replace("from datetime import datetime\n", "")
text = text.replace(
    "def _metadata_semantics(resource_type: str, name: str, description: str, tags: list[str]) -> tuple[str, str, float]:\n",
    "def _metadata_semantics(\n"
    "    resource_type: str,\n"
    "    name: str,\n"
    "    description: str,\n"
    "    tags: list[str],\n"
    ") -> tuple[str, str, float]:\n",
)
text = text.replace(
    '            format_type=record.format_type,\n        )\n',
    '            format_type=record.format_type,\n'
    '            semantic_source=record.semantic_source,\n'
    '        )\n',
    1,
)
text = text.replace(
    '            "available": resource.available,\n'
    '            "allowed_actions": list(resource.allowed_actions),\n',
    '            "available": resource.available,\n'
    '            "enabled": resource.enabled,\n'
    '            "allowed_actions": list(resource.allowed_actions),\n',
    1,
)
text = text.replace(
    '            "semantic_description": resource.semantic_description,\n'
    '            "asset_url": resource.asset_url,\n',
    '            "semantic_description": resource.semantic_description,\n'
    '            "semantic_source": resource.semantic_source,\n'
    '            "semantic_confidence": resource.semantic_confidence,\n'
    '            "asset_url": resource.asset_url,\n',
    1,
)
text = text.replace(
    '                    "candidate_scores": [float(item["score"]) for item in candidates],\n',
    '                    "candidate_scores": [item["score"] for item in candidates],\n',
)
repository.write_text(text, encoding="utf-8")

schemas = Path("src/echo_masque/api/expression_schemas.py")
text = schemas.read_text(encoding="utf-8")
text = text.replace(
    'ExpressionRunStatus = Literal["running", "completed", "failed", "skipped"]\n\n\nclass DiscordCatalogEmoji',
    'ExpressionRunStatus = Literal["running", "completed", "failed", "skipped"]\n\n\ndef default_expression_actions() -> list[Literal["inline", "reaction", "sticker"]]:\n'
    '    return ["inline", "reaction", "sticker"]\n\n\nclass DiscordCatalogEmoji',
)
text = text.replace(
    '        default_factory=lambda: ["inline", "reaction", "sticker"],\n',
    '        default_factory=default_expression_actions,\n',
)
schemas.write_text(text, encoding="utf-8")

tests = Path("tests/test_expression_retrieval.py")
text = tests.read_text(encoding="utf-8")
text = text.replace("，", ",")
text = text.replace(
    '    assert [item.resource.key for item in ranked][0] == "emoji:peek"\n',
    '    assert next(item.resource.key for item in ranked) == "emoji:peek"\n',
)
tests.write_text(text, encoding="utf-8")
