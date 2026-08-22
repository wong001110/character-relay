"""Knowledge Gap orchestration over the existing Character Discovery engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from echo_masque.deployment_discovery_service import (
    DeploymentDiscoveryPreview,
    DeploymentDiscoveryPreviewService,
    DeploymentDiscoveryUnavailable,
)
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    KnowledgeGapView,
)


@dataclass(frozen=True, slots=True)
class KnowledgeGapDiscoveryResult:
    gap: KnowledgeGapView
    preview: DeploymentDiscoveryPreview | None
    status: str
    reason: str


class KnowledgeGapDiscoveryService:
    """Reuse Discovery for missing knowledge while keeping Discovery non-authoritative."""

    def __init__(
        self,
        *,
        entities: EntityEvidenceRepository,
        discovery: DeploymentDiscoveryPreviewService,
    ) -> None:
        self.entities = entities
        self.discovery = discovery

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
            preview = await self.discovery.run_knowledge_gap(
                owner_id=owner_id,
                deployment_id=deployment_id,
                gap=searching,
                region=region,
                language=language,
                limit=limit,
                sources=sources,
            )
        except DeploymentDiscoveryUnavailable as exc:
            reopened = self.entities.resolve_gap(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                gap_id=scoped_gap.id,
                evidence_refs=(),
                state="unresolved",
                now=current,
            )
            return KnowledgeGapDiscoveryResult(reopened, None, "unavailable", str(exc))
        # Candidate retrieval does not resolve knowledge. Content Understanding must turn one or
        # more candidates into evidence and explicitly call accept_evidence().
        return KnowledgeGapDiscoveryResult(
            searching,
            preview,
            "candidates_ready",
            "discovery_candidates_are_not_knowledge_authority",
        )

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
        now: datetime | None = None,
    ) -> KnowledgeGapView:
        """Accept Content-Understanding evidence, not a raw Discovery candidate."""

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
            source_ref_type="discovery_evidence",
            source_ref=evidence_ref,
            relation_type="SUPPORTS_ENTITY_KNOWLEDGE",
            target_ref_type="entity",
            target_ref=scoped_gap.entity_id,
            confidence=confidence,
            authority_class=authority_class,
            source_kind=source_kind,
            evidence_refs=(evidence_ref,),
            status="active" if confidence >= 0.7 else "unresolved",
            producer="content_understanding",
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
        evidence_refs = tuple(
            dict.fromkeys((*scoped_gap.resolution_evidence_refs, edge.id))
        )
        if remaining or confidence < 0.7:
            return self.entities.resolve_gap(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                gap_id=scoped_gap.id,
                evidence_refs=evidence_refs,
                state="unresolved",
                now=current,
            )
        return self.entities.resolve_gap(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            gap_id=scoped_gap.id,
            evidence_refs=evidence_refs,
            state="resolved",
            now=current,
        )


__all__ = ["KnowledgeGapDiscoveryResult", "KnowledgeGapDiscoveryService"]
