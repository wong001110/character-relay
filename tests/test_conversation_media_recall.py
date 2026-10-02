from __future__ import annotations

from echo_masque.conversation_media import (
    ConversationMediaMemory,
    ConversationMediaReferenceService,
)
from echo_masque.live_media import LiveMediaContext


def _context(source_key: str = "image:storage") -> LiveMediaContext:
    return LiveMediaContext(
        source_key=source_key,
        kind="image",
        label="storage screenshot",
        summary="A game storage screen with a full 30/30 storage device.",
        visible_text="寄物装置 容量: 30/30 今日可取用次数: 5/5 UID: 800478718",
        notable_details=("The storage device is full.", "The inventory contains materials."),
    )


def test_guidance_defaults_to_single_summary_without_duplicate_details_or_ocr() -> None:
    memory = ConversationMediaMemory(
        message_id="media-1",
        context=_context(),
        recall_query="你觉得这个怎么样?",
    )

    guidance = "\n".join(ConversationMediaReferenceService.guidance((memory,)))

    assert "Summary:" in guidance
    assert "Relevant readable excerpt:" not in guidance
    assert "Notable details:" not in guidance
    assert "UID: 800478718" not in guidance


def test_guidance_lazily_includes_readable_text_for_text_specific_followup() -> None:
    memory = ConversationMediaMemory(
        message_id="media-1",
        context=_context(),
        recall_query="那张图的容量是多少?",
    )

    guidance = "\n".join(ConversationMediaReferenceService.guidance((memory,)))

    assert "Summary:" in guidance
    assert "Relevant readable excerpt:" in guidance
    assert "容量: 30/30" in guidance
    assert "Notable details:" not in guidance
