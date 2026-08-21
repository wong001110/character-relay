"""Static hard-cutover guard: runtime/schema/UI/tests cannot retain Topic authority."""

from __future__ import annotations

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
            for line_number, line in enumerate(text.splitlines(), start=1):
                for token in FORBIDDEN:
                    if token in line:
                        relative = path.relative_to(ROOT)
                        hits.append(f"{relative}:{line_number}: {token}")
    assert not hits, "Legacy Topic authority remains:\n" + "\n".join(hits)
