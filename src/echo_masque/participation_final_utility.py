"""Final bounded Utility ordering for genuinely ambiguous Smart Participation plans."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.participation_context_rerank import (
    ParticipationContextPlanItem,
    ParticipationContextScore,
)
from echo_masque.turn_intelligence import TurnIntelligenceService

_FINAL_GRAY_GAP = 0.35


@dataclass(frozen=True, slots=True)
class ParticipationFinalUtilityResult:
    plan: tuple[ParticipationContextPlanItem, ...]
    used: bool
    accepted: bool
    selected_primary_id: str
    reason: str
    attempts: int = 0
    latency_ms: int = 0


class ParticipationFinalUtilityResolver:
    """Ask Utility only after deterministic, E5, Graph and Learned evidence are settled.

    Utility cannot introduce a deployment. For multi-speaker plans it only decides primary order;
    for one-speaker plans it is unnecessary. This keeps Runtime admission authority outside the LLM.
    """

    def __init__(self, service: TurnIntelligenceService) -> None:
        self.service = service

    def resolve(
        self,
        *,
        current_burst: str,
        plan: tuple[ParticipationContextPlanItem, ...],
        scores: tuple[ParticipationContextScore, ...],
        display_names: dict[str, str],
    ) -> ParticipationFinalUtilityResult:
        if len(plan) < 2:
            return ParticipationFinalUtilityResult(plan, False, False, "", "not_ambiguous")

        score_by_id = {item.deployment_id: item for item in scores}
        ranked = [score_by_id.get(item.deployment_id) for item in plan]
        if len(ranked) < 2 or ranked[0] is None or ranked[1] is None:
            return ParticipationFinalUtilityResult(plan, False, False, "", "score_missing")
        gap = abs(ranked[0].contextual_final_score - ranked[1].contextual_final_score)
        if gap > _FINAL_GRAY_GAP:
            return ParticipationFinalUtilityResult(plan, False, False, "", "final_gap_clear")

        candidates: list[tuple[str, str, str]] = []
        for item in plan[:3]:
            score = score_by_id.get(item.deployment_id)
            if score is None:
                continue
            evidence = (
                ",".join(f"{entry.name}:{entry.adjustment:+.3f}" for entry in score.evidence)
                or "no_context_adjustment"
            )
            candidates.append(
                (
                    item.deployment_id,
                    display_names.get(item.deployment_id, item.deployment_id),
                    (
                        f"contextual_score={score.contextual_final_score:.3f};"
                        f"base_score={score.base_final_score:.3f};{evidence}"
                    ),
                )
            )
        if len(candidates) < 2:
            return ParticipationFinalUtilityResult(plan, False, False, "", "candidate_missing")

        result = self.service.decide(
            requested_tasks=("speaker",),
            current_burst=current_burst,
            speaker_candidates=tuple(candidates),
        )
        inference = result.inference
        attempts = inference.attempts if inference is not None else 0
        latency = inference.latency_ms if inference is not None else 0
        selected = result.speaker.deployment_id if result.speaker is not None else ""
        allowed = {item.deployment_id for item in plan}
        if not selected or selected not in allowed:
            return ParticipationFinalUtilityResult(
                plan,
                True,
                False,
                "",
                result.status["speaker"].reason,
                attempts,
                latency,
            )

        ordered_ids = [
            selected,
            *(item.deployment_id for item in plan if item.deployment_id != selected),
        ]
        reordered = tuple(
            ParticipationContextPlanItem(
                deployment_id=deployment_id,
                turn_role="primary" if index == 0 else "complement",
                reason="final_utility_primary" if index == 0 else "context_rerank",
            )
            for index, deployment_id in enumerate(ordered_ids)
        )
        return ParticipationFinalUtilityResult(
            reordered,
            True,
            True,
            selected,
            "accepted",
            attempts,
            latency,
        )


__all__ = ["ParticipationFinalUtilityResolver", "ParticipationFinalUtilityResult"]
