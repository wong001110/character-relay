"""Pure source-version policy; no judge, retrieval, or tool execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from echo_masque.character_turn_context_types import CharacterContextTraceView
from echo_masque.room_sources import FocusedContext

_CORRECTION = re.compile(
    r"^(?:actually\b|correction\b|wait\b|never\s*mind\b|instead\b|"
    r"更正|等等|等一下|不用了|不需要了|不是|改成|改為|改为|其實|其实)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DraftDecision:
    action: Literal["keep", "refresh", "drop", "blocked"]
    reason: str
    changed_message_ids: tuple[str, ...] = ()


def assess_draft(
    trace: CharacterContextTraceView,
    current: FocusedContext,
    *,
    writable: bool,
    expired: bool = False,
) -> DraftDecision:
    optional = trace.source_origin in {"ambient", "continuation"}
    stop: Literal["drop", "blocked"] = "drop" if optional else "blocked"
    if not writable:
        return DraftDecision("blocked", "destination_not_writable")
    if expired:
        return DraftDecision(stop, "draft_deadline_exceeded")
    if (
        not trace.source_target_message_id
        or trace.source_target_message_id != current.target_message_id
    ):
        return DraftDecision("blocked", "draft_source_binding_missing")
    if trace.source_origin == "continuation" and any(
        item.room_revision > trace.source_snapshot_revision
        and item.message.message_id not in trace.source_revisions
        and not item.message.author_is_bot
        for item in current.sources
    ):
        return DraftDecision("drop", "human_priority_over_optional_continuation")
    previous = trace.source_revisions
    changed: list[str] = []
    anchors = set(trace.source_anchor_ids) or {trace.source_target_message_id}
    # Missing old context from the bounded window is not deletion. Explicitly changed
    # context and anchored followups are relevant; unrelated new messages are not.
    for stored in current.sources:
        message = stored.message
        mid = message.message_id
        if mid in previous:
            prior_hash = trace.source_content_hashes.get(mid)
            materially_changed = (
                message.draft_fingerprint() != prior_hash
                if prior_hash
                else stored.revision != previous[mid]
            )
            if materially_changed:
                changed.append(mid)
            continue
        if stored.room_revision <= trace.source_snapshot_revision or message.author_is_bot:
            continue
        if message.reply_to_message_id in anchors or (
            message.author_id == trace.source_requester_id
            and _CORRECTION.match(message.text.strip())
        ):
            changed.append(mid)
    if not changed:
        return DraftDecision("keep", "source_unchanged")
    if trace.source_refresh_count:
        return DraftDecision(stop, "draft_obsolete_after_refresh", tuple(changed))
    return DraftDecision("refresh", "relevant_source_change", tuple(changed))
