"""Utility-assisted tie breaking for already plausible Smart Participation candidates."""

from __future__ import annotations

from dataclasses import dataclass

from echo_masque.config import Settings
from echo_masque.persistence.repository import Repository
from echo_masque.services.runtime import RuntimeService
from echo_masque.turn_intelligence import TurnIntelligenceService
from echo_masque.utility_gateway_live import ExistingProviderUtilityCaller
from echo_masque.utility_gateway_router import UtilityGatewayRouter

_TIE_MINIMUM_RELEVANCE = 0.75
_TIE_MAX_GAP = 0.04
_TIE_MAX_CANDIDATES = 3
_DEMOTED_RELEVANCE_CEILING = 0.74


@dataclass(frozen=True, slots=True)
class ParticipationTieCandidate:
    deployment_id: str
    character_card_id: str
    display_name: str
    semantic_summary: str
    relevance: float


@dataclass(frozen=True, slots=True)
class ParticipationTieBreakOutcome:
    adjusted_relevance: dict[str, float]
    selected_deployment_id: str = ""
    used: bool = False
    reason: str = "not_needed"


class ParticipationTieBreakService:
    """Reduce multi-Character E5 ties without ever granting participation eligibility.

    The chosen candidate keeps its original E5 relevance. Other tied candidates may only be
    demoted. Therefore Utility can remove semantic support from a candidate but cannot make a
    previously ineligible Character cross a deterministic participation threshold.
    """

    def __init__(
        self,
        repository: Repository,
        settings: Settings,
        *,
        utility_gateway: UtilityGatewayRouter | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self._utility_gateway_override = utility_gateway
        self._utility_gateway_live: UtilityGatewayRouter | None = None

    def _gateway(self) -> UtilityGatewayRouter:
        if self._utility_gateway_override is not None:
            return self._utility_gateway_override
        if self._utility_gateway_live is None:
            runtime = RuntimeService(self.repository, self.settings)
            self._utility_gateway_live = UtilityGatewayRouter(
                runtime,
                caller=ExistingProviderUtilityCaller(),
            )
        return self._utility_gateway_live

    @staticmethod
    def _capability_enabled(gateway: object) -> bool:
        runtime = getattr(gateway, "runtime", None)
        if runtime is None:
            return True
        config = runtime.config().utility_gateway
        return bool(
            config.enabled
            and any(
                member.enabled and "participation_tiebreak" in member.capabilities
                for member in config.members
            )
        )

    @staticmethod
    def _original(candidates: list[ParticipationTieCandidate]) -> dict[str, float]:
        return {item.deployment_id: item.relevance for item in candidates}

    @staticmethod
    def _speaker_evidence(item: ParticipationTieCandidate) -> str:
        return " | ".join(
            (
                f"e5_relevance={item.relevance:.6f}",
                f"character_card_id={item.character_card_id}",
                f"semantic_profile={item.semantic_summary[:900]}",
            )
        )

    def apply(
        self,
        *,
        message: str,
        candidates: list[ParticipationTieCandidate],
    ) -> ParticipationTieBreakOutcome:
        original = self._original(candidates)
        ranked = sorted(candidates, key=lambda item: (-item.relevance, item.deployment_id))
        if len(ranked) < 2:
            return ParticipationTieBreakOutcome(original, reason="fewer_than_two")
        top = ranked[0]
        second = ranked[1]
        if top.relevance < _TIE_MINIMUM_RELEVANCE:
            return ParticipationTieBreakOutcome(original, reason="e5_below_tie_floor")
        if top.relevance - second.relevance > _TIE_MAX_GAP:
            return ParticipationTieBreakOutcome(original, reason="clear_e5_winner")

        tied = [
            item
            for item in ranked
            if top.relevance - item.relevance <= _TIE_MAX_GAP
        ][:_TIE_MAX_CANDIDATES]
        if len(tied) < 2:
            return ParticipationTieBreakOutcome(original, reason="no_gray_zone")

        gateway = self._gateway()
        if not self._capability_enabled(gateway):
            return ParticipationTieBreakOutcome(original, reason="capability_disabled")

        decision = TurnIntelligenceService(
            gateway,
            capability="participation_tiebreak",
        ).decide(
            requested_tasks=("speaker",),
            current_burst=message,
            speaker_candidates=tuple(
                (
                    item.deployment_id,
                    item.display_name,
                    self._speaker_evidence(item),
                )
                for item in tied
            ),
        )
        selected = decision.speaker
        if selected is None:
            reason = decision.status["speaker"].reason
            return ParticipationTieBreakOutcome(
                original,
                reason=(
                    "utility_unavailable"
                    if reason == "utility_unavailable"
                    else "utility_rejected"
                ),
            )

        adjusted = dict(original)
        for item in tied:
            if item.deployment_id == selected.deployment_id:
                continue
            adjusted[item.deployment_id] = min(
                item.relevance,
                _DEMOTED_RELEVANCE_CEILING,
            )
        return ParticipationTieBreakOutcome(
            adjusted_relevance=adjusted,
            selected_deployment_id=selected.deployment_id,
            used=True,
            reason=selected.reason_code or "utility_tiebreak",
        )


__all__ = [
    "ParticipationTieBreakOutcome",
    "ParticipationTieBreakService",
    "ParticipationTieCandidate",
]
