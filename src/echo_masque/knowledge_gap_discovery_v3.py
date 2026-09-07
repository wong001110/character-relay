"""Knowledge Gap orchestration over the existing Character Discovery engine."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from echo_masque.deployment_discovery_service import (
    DeploymentDiscoveryPreview,
    DeploymentDiscoveryPreviewService,
    DeploymentDiscoveryUnavailable,
)
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    KnowledgeGapCandidateView,
    KnowledgeGapView,
)


@dataclass(frozen=True, slots=True)
class KnowledgeGapDiscoveryResult:
    gap: KnowledgeGapView
    preview: DeploymentDiscoveryPreview | None
    status: str
    reason: str
    candidates: tuple[KnowledgeGapCandidateView, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeGapEvidenceAcceptance:
    """A review result from an authorized operator or Content Understanding path."""

    candidate_id: str
    validation_method: Literal["operator_review", "content_understanding"]
    validated_evidence_ref: str
    resolved_fields: tuple[str, ...]
    confidence: float
    entity_metadata: dict[str, str] | None = None
    canonical_entity: bool = False


class KnowledgeGapDiscoveryService:
    """Reuse Discovery for missing knowledge while keeping Discovery non-authoritative."""

    def __init__(
        self,
        *,
        entities: EntityEvidenceRepository,
        discovery: DeploymentDiscoveryPreviewService,
        candidate_ttl: timedelta = timedelta(hours=24),
        search_timeout_seconds: float = 30.0,
        stale_search_after: timedelta = timedelta(minutes=5),
    ) -> None:
        self.entities = entities
        self.discovery = discovery
        self.candidate_ttl = max(candidate_ttl, timedelta(minutes=1))
        self.search_timeout_seconds = max(0.01, min(float(search_timeout_seconds), 120.0))
        self.stale_search_after = max(stale_search_after, timedelta(minutes=1))

    @staticmethod
    def _reopen(
        *,
        entities: EntityEvidenceRepository,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        gap_id: str,
        evidence_refs: tuple[str, ...],
        now: datetime,
    ) -> KnowledgeGapView:
        return entities.resolve_gap(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            gap_id=gap_id,
            evidence_refs=evidence_refs,
            state="unresolved",
            now=now,
        )

    async def search(
        self,
        *,
        owner_id: str,
        deployment_id: str,
        connection_id: str,
        guild_id: str,
        gap: KnowledgeGapView,
        region: str = "",
        language: str = "",
        limit: int = 8,
        sources: tuple[str, ...] = (),
        minimum_importance: float = 0.65,
        now: datetime | None = None,
    ) -> KnowledgeGapDiscoveryResult:
        current = now or datetime.now(UTC)
        scoped_gap = self.entities.gap_for_scope(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            gap_id=gap.id,
        )
        if scoped_gap.resolution_state not in {"unresolved", "searching"}:
            return KnowledgeGapDiscoveryResult(scoped_gap, None, "skipped", "gap_not_open")
        if scoped_gap.importance < minimum_importance:
            return KnowledgeGapDiscoveryResult(
                scoped_gap,
                None,
                "skipped",
                "gap_not_important_enough",
            )
        searching = self.entities.mark_gap_searching(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            gap_id=scoped_gap.id,
            now=current,
        )
        try:
            preview = await asyncio.wait_for(
                self.discovery.run_knowledge_gap(
                    owner_id=owner_id,
                    deployment_id=deployment_id,
                    gap=searching,
                    region=region,
                    language=language,
                    limit=limit,
                    sources=sources,
                ),
                timeout=self.search_timeout_seconds,
            )
        except asyncio.CancelledError:
            self._reopen(
                entities=self.entities,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                gap_id=scoped_gap.id,
                evidence_refs=scoped_gap.resolution_evidence_refs,
                now=current,
            )
            raise
        except TimeoutError:
            reopened = self._reopen(
                entities=self.entities,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                gap_id=scoped_gap.id,
                evidence_refs=scoped_gap.resolution_evidence_refs,
                now=current,
            )
            return KnowledgeGapDiscoveryResult(reopened, None, "timed_out", "search_timeout")
        except DeploymentDiscoveryUnavailable as exc:
            reopened = self._reopen(
                entities=self.entities,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                gap_id=scoped_gap.id,
                evidence_refs=scoped_gap.resolution_evidence_refs,
                now=current,
            )
            return KnowledgeGapDiscoveryResult(reopened, None, "unavailable", str(exc))
        except Exception:
            # The dispatch wrapper records only stable scope identifiers. This method must first
            # leave the durable lifecycle in a terminal open state before that wrapper observes it.
            self._reopen(
                entities=self.entities,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                gap_id=scoped_gap.id,
                evidence_refs=scoped_gap.resolution_evidence_refs,
                now=current,
            )
            raise

        candidates = self.entities.persist_gap_candidates(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            deployment_id=deployment_id,
            gap_id=scoped_gap.id,
            candidates=tuple(preview.ranked),
            expires_at=current + self.candidate_ttl,
            now=current,
        )
        reopened = self._reopen(
            entities=self.entities,
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            gap_id=scoped_gap.id,
            evidence_refs=scoped_gap.resolution_evidence_refs,
            now=current,
        )
        if not candidates:
            return KnowledgeGapDiscoveryResult(
                reopened,
                preview,
                "no_candidates",
                "discovery_returned_no_reviewable_candidates",
            )
        return KnowledgeGapDiscoveryResult(
            reopened,
            preview,
            "candidates_ready",
            "discovery_candidates_require_authorized_validation",
            candidates,
        )

    def reject_candidate(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        deployment_id: str,
        gap_id: str,
        candidate_id: str,
        reviewed_by: str,
        now: datetime | None = None,
    ) -> KnowledgeGapCandidateView:
        return self.entities.review_gap_candidate(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            deployment_id=deployment_id,
            gap_id=gap_id,
            candidate_id=candidate_id,
            action="rejected",
            reviewed_by=reviewed_by,
            now=now,
        )

    def accept_candidate_evidence(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        deployment_id: str,
        gap: KnowledgeGapView,
        acceptance: KnowledgeGapEvidenceAcceptance,
        reviewed_by: str,
        now: datetime | None = None,
    ) -> KnowledgeGapView:
        """Atomically accept a persisted candidate without trusting caller-supplied evidence."""

        current = now or datetime.now(UTC)
        candidate = self.entities.gap_candidate_for_scope(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            deployment_id=deployment_id,
            gap_id=gap.id,
            candidate_id=acceptance.candidate_id,
            now=current,
        )
        provenance_ref = f"discovery_item:{candidate.discovery_item_id}"
        supplied_ref = acceptance.validated_evidence_ref.strip()
        # An operator's decision is recorded as review provenance; it cannot turn an arbitrary
        # client string into evidence. Content Understanding currently shares the same persisted
        # candidate store, so it must explicitly bind its result to that candidate source.
        if acceptance.validation_method == "operator_review":
            if supplied_ref and supplied_ref != provenance_ref:
                raise ValueError("Operator review must use the persisted candidate source.")
        elif acceptance.validation_method == "content_understanding":
            if supplied_ref != provenance_ref:
                raise ValueError("Content Understanding evidence must match the candidate source.")
        else:
            raise ValueError("Knowledge Gap candidate validation method is invalid.")
        accepted, _candidate = self.entities.accept_gap_candidate_evidence(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            deployment_id=deployment_id,
            gap_id=gap.id,
            candidate_id=candidate.id,
            reviewed_by=reviewed_by,
            validation_method=acceptance.validation_method,
            confidence=acceptance.confidence,
            resolved_fields=acceptance.resolved_fields,
            entity_metadata=acceptance.entity_metadata,
            canonical_entity=acceptance.canonical_entity,
            now=current,
        )
        return accepted

    def accept_evidence(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        gap: KnowledgeGapView,
        evidence_ref: str,
        source_kind: str,
        authority_class: str,
        confidence: float,
        resolved_fields: tuple[str, ...],
        entity_metadata: dict[str, str] | None = None,
        canonical_entity: bool = False,
        source_ref_type: str = "discovery_evidence",
        source_ref: str = "",
        producer: str = "content_understanding",
        provenance_refs: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> KnowledgeGapView:
        """Accept validated evidence through the candidate-specific handoff."""

        if source_kind == "discovery_candidate":
            raise ValueError("Discovery candidates must be accepted through their atomic claim.")
        current = now or datetime.now(UTC)
        scoped_gap = self.entities.gap_for_scope(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            gap_id=gap.id,
        )
        if scoped_gap.entity_id != gap.entity_id:
            raise KeyError("Knowledge Gap not found.")
        edge = self.entities.add_edge(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            source_ref_type=source_ref_type,
            source_ref=source_ref or evidence_ref,
            relation_type="SUPPORTS_ENTITY_KNOWLEDGE",
            target_ref_type="entity",
            target_ref=scoped_gap.entity_id,
            confidence=confidence,
            authority_class=authority_class,
            source_kind=source_kind,
            evidence_refs=tuple(dict.fromkeys((evidence_ref, *provenance_refs))),
            status="active" if confidence >= 0.7 else "unresolved",
            producer=producer,
            valid_from=current,
            now=current,
        )
        if canonical_entity and confidence >= 0.8:
            self.entities.confirm_entity(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                entity_id=gap.entity_id,
                metadata=entity_metadata,
                source_refs=(evidence_ref,),
                now=current,
            )
        resolved = set(resolved_fields)
        remaining = tuple(field for field in scoped_gap.missing_fields if field not in resolved)
        evidence_refs = tuple(dict.fromkeys((*scoped_gap.resolution_evidence_refs, edge.id)))
        return self.entities.resolve_gap(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            gap_id=scoped_gap.id,
            evidence_refs=evidence_refs,
            state="unresolved" if remaining or confidence < 0.7 else "resolved",
            now=current,
        )


__all__ = [
    "KnowledgeGapDiscoveryResult",
    "KnowledgeGapDiscoveryService",
    "KnowledgeGapEvidenceAcceptance",
]
