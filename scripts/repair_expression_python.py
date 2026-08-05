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
repository.write_text(text, encoding="utf-8")

tests = Path("tests/test_expression_retrieval.py")
text = tests.read_text(encoding="utf-8")
text = text.replace("，", ",")
text = text.replace(
    '    assert [item.resource.key for item in ranked][0] == "emoji:peek"\n',
    '    assert next(item.resource.key for item in ranked) == "emoji:peek"\n',
)
tests.write_text(text, encoding="utf-8")
