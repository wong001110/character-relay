"""Static hard-cutover guard: runtime/schema/UI/tests cannot retain Topic authority."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (ROOT / "src" / "echo_masque", ROOT / "web" / "src", ROOT / "tests")
SELF = Path(__file__).resolve()

FORBIDDEN = (
    "ConversationTopic",
    "conversation_topic",
    "topic_id",
    "topic_local",
    "topic.search",
    "ACTIVE_TOPIC",
    "TOPIC_EVIDENCE",
    "TurnTopicDecision",
    "source_topic_ids",
    "utility_topic_runtime",
    "topic_intelligence",
    "upsert_topic_page",
    "mark_topic_stale",
    "get_topic_page",
    "signal_topic",
    "consolidate_topic",
)

TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}


def test_legacy_topic_authority_is_absent() -> None:
    hits: list[str] = []
    for root in SCAN_ROOTS:
        for path in root.rglob("*"):
            if path == SELF or not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            # The reset allowlist is inert schema data, not a runtime authority. Validate
            # its entire shape before exempting literal names, never skip a runtime file.
            allowed_lines: set[int] = set()
            if path == ROOT / "src/echo_masque/retired_chat_tables.py":
                module = ast.parse(text)
                assert len(module.body) == 2 and isinstance(module.body[0], ast.Expr)
                declaration = module.body[1]
                assert isinstance(declaration, ast.AnnAssign)
                assert isinstance(declaration.target, ast.Name)
                assert declaration.target.id == "RETIRED_CHAT_TABLES"
                value = declaration.value
                assert isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                assert value.func.id == "frozenset" and len(value.args) == 1
                assert not value.keywords and isinstance(value.args[0], ast.Set)
                assert all(isinstance(item, ast.Constant) and isinstance(item.value, str)
                           for item in value.args[0].elts)
                allowed_lines = {item.lineno for item in value.args[0].elts}
            for line_number, line in enumerate(text.splitlines(), start=1):
                if line_number in allowed_lines:
                    continue
                for token in FORBIDDEN:
                    if token in line:
                        relative = path.relative_to(ROOT)
                        hits.append(f"{relative}:{line_number}: {token}")
    assert not hits, "Legacy Topic authority remains:\n" + "\n".join(hits)
