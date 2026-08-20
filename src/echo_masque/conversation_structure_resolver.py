"""Hard-cutover Conversation Structure resolver for Intelligence Core v3.

This module narrows the transitional ConversationSegmentationService so semantic similarity can
retrieve/rank Thread candidates but can never be the sole positive authority for Thread attachment.
The legacy implementation remains importable only while downstream code is migrated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from echo_masque.api.smart_participation_v4_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationResolveRequest,
)
from echo_masque.conversation_segmentation import (
    ConversationJudgeResult,
    ConversationJudgeSegment,
    ConversationSegmentationService,
    ThreadAction,
)
from echo_masque.persistence.conversation_structure_repository import ConversationThreadView

_IMMEDIATE_CONTINUITY = timedelta(minutes=2)


class ConversationStructureResolver(ConversationSegmentationService):
    """Resolve Segments/Threads with structure-first positive authority.

    Positive deterministic attachment requires independent structural evidence (currently an
    explicit reply to a prior Segment, or immediate participant continuity). Semantic score is
    used only to retrieve/rank candidates and to reject implausible structural continuations.
    """

    @staticmethod
    def _participant_ids(
        cluster: tuple[SmartParticipationBurstMessage, ...],
    ) -> frozenset[str]:
        return frozenset(item.author_id for item in cluster if item.author_id)

    @staticmethod
    def _recent_enough(thread: ConversationThreadView, *, now: datetime) -> bool:
        observed = thread.last_active_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        return now - observed.astimezone(UTC) <= _IMMEDIATE_CONTINUITY

    def _structural_candidates(
        self,
        *,
        cluster: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[ConversationThreadView, ...],
        now: datetime,
    ) -> tuple[ConversationThreadView, ...]:
        participants = self._participant_ids(cluster)
        if not participants:
            return ()
        return tuple(
            thread
            for thread in threads
            if self._recent_enough(thread, now=now)
            and bool(participants.intersection(thread.participant_ids))
        )

    def _fallback(
        self,
        *,
        messages: tuple[SmartParticipationBurstMessage, ...],
        threads: tuple[ConversationThreadView, ...],
        owner_id: str,
        payload: SmartParticipationResolveRequest,
    ) -> ConversationJudgeResult:
        now = datetime.now(UTC)
        results: list[ConversationJudgeSegment] = []
        for cluster in self._hard_clusters(messages):
            summary = self._summary(cluster)
            context_only = self._context_only(cluster)
            reply_thread = self._reply_thread_hint(
                cluster=cluster,
                owner_id=owner_id,
                payload=payload,
            )
            if reply_thread is not None:
                results.append(
                    ConversationJudgeSegment(
                        message_ids=tuple(item.message_id for item in cluster),
                        kind="reaction" if context_only else "discussion",
                        summary=summary,
                        thread_action="context_only" if context_only else "attach",
                        thread_id=reply_thread.id,
                        thread_evidence=not context_only,
                        confidence=0.99,
                        reason="explicit_reply_to_prior_thread",
                    )
                )
                continue

            ranked = self._rank_threads(summary, threads) if summary else ()
            score_by_id = {thread.id: score for thread, score in ranked}
            structural = self._structural_candidates(
                cluster=cluster,
                threads=threads,
                now=now,
            )
            structural_ranked = sorted(
                (
                    (thread, score_by_id.get(thread.id, 0.0))
                    for thread in structural
                ),
                key=lambda item: item[1],
                reverse=True,
            )
            best_any_score = ranked[0][1] if ranked else 0.0

            action: ThreadAction
            thread_id = ""
            evidence = False
            confidence = 0.0
            reason = ""

            if not threads:
                action = "context_only" if context_only else "create"
                evidence = not context_only
                confidence = 0.82 if not context_only else 0.72
                reason = "no_prior_thread"
            elif structural_ranked:
                best_thread, best_score = structural_ranked[0]
                second_score = structural_ranked[1][1] if len(structural_ranked) > 1 else 0.0
                margin = best_score - second_score
                if context_only and best_score >= 0.25 and (
                    len(structural_ranked) == 1 or margin >= 0.10
                ):
                    action = "context_only"
                    thread_id = best_thread.id
                    confidence = min(0.94, max(0.72, 0.62 + best_score * 0.25))
                    reason = "immediate_participant_context"
                elif not context_only and best_score >= 0.35 and (
                    len(structural_ranked) == 1 or margin >= 0.12
                ):
                    action = "attach"
                    thread_id = best_thread.id
                    evidence = True
                    confidence = min(0.95, max(0.74, 0.66 + best_score * 0.25))
                    reason = "immediate_participant_continuity"
                elif not context_only and best_score <= 0.15:
                    # Structural proximity exists, but the content does not support continuity.
                    # This is negative candidate evidence, so a new Thread is safe.
                    action = "create"
                    evidence = True
                    confidence = 0.72
                    reason = "structural_candidate_rejected"
                else:
                    action = "unresolved"
                    confidence = max(0.40, min(0.68, best_score))
                    reason = "ambiguous_structural_candidates"
            elif context_only:
                # A reaction with no structural anchor is allowed to remain unassigned. Similarity
                # cannot attach it to a Thread by itself.
                action = "context_only"
                confidence = 0.64
                reason = "context_without_structural_anchor"
            elif best_any_score <= 0.30:
                # Candidate retrieval found no plausible prior Thread. Semantic distance may rule
                # candidates out, but it cannot positively select one.
                action = "create"
                evidence = True
                confidence = 0.72
                reason = "no_plausible_thread_candidate"
            else:
                # High semantic similarity without independent structure is deliberately not an
                # attachment decision. Utility may resolve this; otherwise it remains unresolved.
                action = "unresolved"
                confidence = max(0.40, min(0.68, best_any_score))
                reason = "semantic_candidate_without_structural_authority"

            results.append(
                ConversationJudgeSegment(
                    message_ids=tuple(item.message_id for item in cluster),
                    kind="reaction" if context_only else "discussion",
                    summary=summary,
                    thread_action=action,
                    thread_id=thread_id,
                    thread_evidence=evidence,
                    confidence=round(confidence, 6),
                    reason=reason,
                )
            )
        return ConversationJudgeResult(segments=tuple(results))


__all__ = ["ConversationStructureResolver"]
