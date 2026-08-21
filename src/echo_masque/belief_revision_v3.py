"""Current-turn Belief revision, authority policy, and Correction Shield."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from echo_masque.persistence.belief_repository import BeliefRepository, BeliefV3View

ClaimDomain = Literal["personal", "canonical", "general"]
ClaimSource = Literal[
    "self_report",
    "user_correction",
    "system_observation",
    "official_source",
    "verified_source",
    "third_party",
    "character_observation",
    "media_inference",
    "llm_inference",
]

_CORRECTION_CUE = re.compile(
    r"(?:你記錯了|你记错了|不是(?:啦|啊|的)?|我沒有|我没有|其實是|其实是|"
    r"不是\s*.+?[，, ]?是|no[, ]|actually|you(?:'|’)re wrong|you remembered wrong)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class BeliefAuthority:
    authority_class: str
    score: float
    default_confidence: float


@dataclass(frozen=True, slots=True)
class CorrectionShield:
    blocked_belief_ids: tuple[str, ...]
    replacement_belief_id: str
    notice: str

    @property
    def active(self) -> bool:
        return bool(self.blocked_belief_ids)


@dataclass(frozen=True, slots=True)
class BeliefRevisionResult:
    action: Literal["created", "reinforced", "superseded", "disputed", "ignored"]
    belief: BeliefV3View | None
    previous_belief_ids: tuple[str, ...]
    shield: CorrectionShield
    reason: str


class BeliefAuthorityPolicy:
    """Domain-sensitive evidence authority; self-report is not universal canon authority."""

    @staticmethod
    def resolve(*, domain: ClaimDomain, source: ClaimSource) -> BeliefAuthority:
        if domain == "personal":
            values = {
                "user_correction": BeliefAuthority("personal_self_correction", 1.0, 0.98),
                "self_report": BeliefAuthority("personal_self_report", 0.95, 0.95),
                "system_observation": BeliefAuthority("system_observation", 0.85, 0.9),
                "third_party": BeliefAuthority("third_party_report", 0.55, 0.65),
                "character_observation": BeliefAuthority("character_observation", 0.4, 0.55),
                "media_inference": BeliefAuthority("media_inference", 0.35, 0.5),
                "llm_inference": BeliefAuthority("llm_inference", 0.2, 0.4),
                "official_source": BeliefAuthority("official_source", 0.7, 0.75),
                "verified_source": BeliefAuthority("verified_source", 0.7, 0.75),
            }
            return values[source]
        if domain == "canonical":
            values = {
                "official_source": BeliefAuthority("official_canon", 1.0, 0.99),
                "verified_source": BeliefAuthority("verified_reference", 0.9, 0.92),
                "system_observation": BeliefAuthority("system_observation", 0.75, 0.8),
                "self_report": BeliefAuthority("participant_statement", 0.55, 0.65),
                "user_correction": BeliefAuthority("participant_correction", 0.6, 0.7),
                "third_party": BeliefAuthority("participant_statement", 0.5, 0.6),
                "character_observation": BeliefAuthority("character_observation", 0.4, 0.5),
                "media_inference": BeliefAuthority("media_inference", 0.45, 0.55),
                "llm_inference": BeliefAuthority("llm_inference", 0.2, 0.35),
            }
            return values[source]
        values = {
            "official_source": BeliefAuthority("official_source", 0.95, 0.95),
            "verified_source": BeliefAuthority("verified_source", 0.85, 0.9),
            "system_observation": BeliefAuthority("system_observation", 0.85, 0.9),
            "self_report": BeliefAuthority("direct_statement", 0.7, 0.75),
            "user_correction": BeliefAuthority("direct_correction", 0.8, 0.85),
            "third_party": BeliefAuthority("third_party_report", 0.55, 0.65),
            "character_observation": BeliefAuthority("character_observation", 0.4, 0.55),
            "media_inference": BeliefAuthority("media_inference", 0.4, 0.55),
            "llm_inference": BeliefAuthority("llm_inference", 0.2, 0.4),
        }
        return values[source]


class BeliefRevisionService:
    """Apply one extracted claim without letting first-pass interpretation become permanent truth."""

    def __init__(self, repository: BeliefRepository) -> None:
        self.repository = repository

    @staticmethod
    def is_explicit_correction(text: str) -> bool:
        return bool(_CORRECTION_CUE.search(" ".join(text.split())[:4000]))

    @staticmethod
    def _same_value(left: str, right: str) -> bool:
        return " ".join(left.casefold().split()) == " ".join(right.casefold().split())

    @staticmethod
    def _empty_shield() -> CorrectionShield:
        return CorrectionShield((), "", "")

    def apply_claim(
        self,
        *,
        owner_id: str,
        character_card_id: str,
        connection_id: str,
        guild_id: str,
        subject_entity_id: str,
        subject_ref: str,
        predicate: str,
        value_text: str,
        domain: ClaimDomain,
        source: ClaimSource,
        evidence_refs: tuple[str, ...],
        source_message_id: str = "",
        dependency_edge_ids: tuple[str, ...] = (),
        explicit_correction: bool = False,
        importance: float = 0.6,
        scope: str = "server",
        now: datetime | None = None,
    ) -> BeliefRevisionResult:
        current = now or datetime.now(UTC)
        compact_value = " ".join(value_text.split())[:8000]
        if not compact_value or not predicate.strip() or not (subject_entity_id or subject_ref):
            return BeliefRevisionResult(
                "ignored",
                None,
                (),
                self._empty_shield(),
                "incomplete_claim",
            )
        authority = BeliefAuthorityPolicy.resolve(domain=domain, source=source)
        existing = self.repository.active_for_claim(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            subject_entity_id=subject_entity_id,
            subject_ref=subject_ref,
            predicate=predicate,
            character_card_id=character_card_id,
        )
        same = tuple(item for item in existing if self._same_value(item.value_text, compact_value))
        if same:
            chosen = max(same, key=lambda item: (item.authority_score, item.confidence))
            reinforced = self.repository.reinforce(
                owner_id=owner_id,
                belief_id=chosen.id,
                confidence=authority.default_confidence,
                evidence_refs=evidence_refs,
                now=current,
            )
            self.repository.record_revision_event(
                owner_id=owner_id,
                belief_id=reinforced.id,
                previous_belief_id=chosen.id,
                subject_ref=subject_ref or subject_entity_id,
                predicate=predicate,
                action="reinforce",
                reason=f"supporting_{authority.authority_class}",
                source_message_id=source_message_id,
                now=current,
            )
            return BeliefRevisionResult(
                "reinforced",
                reinforced,
                (chosen.id,),
                self._empty_shield(),
                "same_value_support",
            )

        conflicts = tuple(
            item
            for item in existing
            if item.status in {"active", "provisional", "disputed"}
            and not self._same_value(item.value_text, compact_value)
        )
        highest = max(conflicts, key=lambda item: item.authority_score, default=None)
        can_supersede = bool(
            highest is not None
            and not highest.authored
            and (
                authority.score > highest.authority_score
                or (
                    explicit_correction
                    and domain == "personal"
                    and source in {"self_report", "user_correction"}
                    and authority.score >= highest.authority_score
                )
            )
        )
        if can_supersede and highest is not None:
            replacement = self.repository.create(
                owner_id=owner_id,
                character_card_id=character_card_id,
                connection_id=connection_id,
                guild_id=guild_id,
                subject_entity_id=subject_entity_id,
                subject_ref=subject_ref,
                predicate=predicate,
                value_text=compact_value,
                scope=scope,
                authority_class=authority.authority_class,
                authority_score=authority.score,
                origin=source,
                confidence=authority.default_confidence,
                importance=importance,
                status="active" if authority.score >= 0.7 else "provisional",
                evidence_refs=evidence_refs,
                supersedes_belief_id=highest.id,
                dependency_edge_ids=dependency_edge_ids,
                valid_from=current,
                now=current,
            )
            self.repository.record_revision_event(
                owner_id=owner_id,
                belief_id=replacement.id,
                previous_belief_id=highest.id,
                subject_ref=subject_ref or subject_entity_id,
                predicate=predicate,
                action="supersede",
                reason=f"higher_authority_{authority.authority_class}",
                source_message_id=source_message_id,
                now=current,
            )
            blocked = tuple(item.id for item in conflicts if item.id == highest.id)
            shield = CorrectionShield(
                blocked_belief_ids=blocked,
                replacement_belief_id=replacement.id,
                notice=(
                    "MEMORY REVISION NOTICE\n"
                    "Current evidence explicitly corrects an earlier remembered claim. "
                    "Do not rely on the superseded claim in this turn."
                ),
            )
            return BeliefRevisionResult(
                "superseded",
                replacement,
                (highest.id,),
                shield,
                "higher_authority_correction",
            )

        if conflicts:
            new_belief = self.repository.create(
                owner_id=owner_id,
                character_card_id=character_card_id,
                connection_id=connection_id,
                guild_id=guild_id,
                subject_entity_id=subject_entity_id,
                subject_ref=subject_ref,
                predicate=predicate,
                value_text=compact_value,
                scope=scope,
                authority_class=authority.authority_class,
                authority_score=authority.score,
                origin=source,
                confidence=authority.default_confidence,
                importance=importance,
                status="disputed",
                evidence_refs=evidence_refs,
                dependency_edge_ids=dependency_edge_ids,
                valid_from=current,
                now=current,
            )
            disputed_ids = tuple(item.id for item in conflicts if not item.authored)
            self.repository.mark_disputed(
                owner_id=owner_id,
                belief_ids=disputed_ids,
                now=current,
            )
            self.repository.record_revision_event(
                owner_id=owner_id,
                belief_id=new_belief.id,
                previous_belief_id=highest.id if highest is not None else "",
                subject_ref=subject_ref or subject_entity_id,
                predicate=predicate,
                action="dispute",
                reason="conflicting_evidence_without_authority_to_overwrite",
                source_message_id=source_message_id,
                now=current,
            )
            shield = self._empty_shield()
            if explicit_correction and domain == "personal" and conflicts:
                shield = CorrectionShield(
                    blocked_belief_ids=tuple(item.id for item in conflicts),
                    replacement_belief_id=new_belief.id,
                    notice=(
                        "MEMORY REVISION NOTICE\n"
                        "Current speaker disputes earlier memory. Treat the conflict as unresolved "
                        "for this turn rather than asserting the old claim as fact."
                    ),
                )
            return BeliefRevisionResult(
                "disputed",
                new_belief,
                tuple(item.id for item in conflicts),
                shield,
                "conflicting_evidence",
            )

        status = "active" if authority.score >= 0.7 else "provisional"
        created = self.repository.create(
            owner_id=owner_id,
            character_card_id=character_card_id,
            connection_id=connection_id,
            guild_id=guild_id,
            subject_entity_id=subject_entity_id,
            subject_ref=subject_ref,
            predicate=predicate,
            value_text=compact_value,
            scope=scope,
            authority_class=authority.authority_class,
            authority_score=authority.score,
            origin=source,
            confidence=authority.default_confidence,
            importance=importance,
            status=status,
            evidence_refs=evidence_refs,
            dependency_edge_ids=dependency_edge_ids,
            valid_from=current,
            now=current,
        )
        self.repository.record_revision_event(
            owner_id=owner_id,
            belief_id=created.id,
            previous_belief_id="",
            subject_ref=subject_ref or subject_entity_id,
            predicate=predicate,
            action="create",
            reason=f"new_{authority.authority_class}",
            source_message_id=source_message_id,
            now=current,
        )
        return BeliefRevisionResult(
            "created",
            created,
            (),
            self._empty_shield(),
            "new_claim",
        )

    @staticmethod
    def apply_shield(
        beliefs: tuple[BeliefV3View, ...],
        shield: CorrectionShield,
    ) -> tuple[BeliefV3View, ...]:
        blocked = set(shield.blocked_belief_ids)
        return tuple(item for item in beliefs if item.id not in blocked)


__all__ = [
    "BeliefAuthority",
    "BeliefAuthorityPolicy",
    "BeliefRevisionResult",
    "BeliefRevisionService",
    "ClaimDomain",
    "ClaimSource",
    "CorrectionShield",
]
