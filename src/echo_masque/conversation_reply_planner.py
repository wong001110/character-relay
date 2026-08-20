"""Select one primary Conversation Segment for one admitted Character turn."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.persistence.conversation_structure_repository import ConversationSegmentView
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.semantic_participation import (
    CharacterParticipationSemanticService,
    SemanticEmbeddingUnavailable,
)


@dataclass(frozen=True, slots=True)
class CharacterSegmentTarget:
    deployment_id: str
    segment_id: str
    semantic_thread_id: str
    score: float
    reason: str
    guidance: str


class CharacterSegmentReplyPlanner:
    """Keep one Character turn focused on one Segment instead of the whole Burst."""

    def __init__(self, semantic: CharacterParticipationSemanticService) -> None:
        self.semantic = semantic

    @staticmethod
    def _direct_pressure(signals: dict[str, float]) -> float:
        return max(
            float(signals.get("name_match", 0.0)),
            float(signals.get("recent_turn_match", 0.0)),
            float(signals.get("lightweight_follow_up", 0.0)),
            float(signals.get("trigger_phrase", 0.0)),
        )

    def select(
        self,
        *,
        deployment: CharacterDeploymentRecord,
        segments: tuple[ConversationSegmentView, ...],
        latest_message_id: str,
        deterministic_signals: dict[str, float],
    ) -> CharacterSegmentTarget | None:
        if not segments:
            return None
        direct_pressure = self._direct_pressure(deterministic_signals)
        direct_segments = (
            tuple(
                segment
                for segment in segments
                if latest_message_id and latest_message_id in segment.message_ids
            )
            if direct_pressure > 0
            else ()
        )
        # Explicit current-turn address/reply evidence is structural authority. Semantic
        # affinity may rank multiple direct candidates, but an unrelated Segment must not
        # steal a turn that was explicitly addressed to this Character.
        candidates = direct_segments or segments
        scores: list[tuple[float, ConversationSegmentView, str]] = []
        for segment in candidates:
            base = 0.05 if segment.kind in {"reaction", "side_comment"} else 0.20
            reason = "segment_fallback"
            if direct_segments:
                base += min(0.55, direct_pressure / 10.0)
                reason = "direct_current_segment"
            if segment.summary.strip() and self.semantic.enabled:
                try:
                    _, _, semantic_scores = self.semantic.score(
                        message=segment.summary,
                        deployments=[
                            (
                                deployment.id,
                                deployment.owner_id,
                                deployment.character_card_id,
                            )
                        ],
                    )
                    if semantic_scores and semantic_scores[0].profile_ready:
                        relevance = max(0.0, semantic_scores[0].relevance)
                        base += relevance
                        reason = (
                            "direct_and_semantic_segment"
                            if direct_segments
                            else "semantic_segment_relevance"
                        )
                except (SemanticEmbeddingUnavailable, KeyError, ValueError, RuntimeError):
                    pass
            if segment.thread_evidence:
                base += 0.05
            scores.append((base, segment, reason))
        scores.sort(key=lambda item: item[0], reverse=True)
        value, selected, reason = scores[0]
        if value < 0.12:
            return None
        summary = " ".join(selected.summary.split())[:150]
        guidance = (
            f"Focus this turn on the selected conversation segment: {summary}. "
            "Do not summarize or answer unrelated simultaneous discussions in the Burst."
        )[:240]
        return CharacterSegmentTarget(
            deployment_id=deployment.id,
            segment_id=selected.id,
            semantic_thread_id=selected.thread_id,
            score=round(value, 6),
            reason=reason,
            guidance=guidance,
        )


__all__ = ["CharacterSegmentReplyPlanner", "CharacterSegmentTarget"]
