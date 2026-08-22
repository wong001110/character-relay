"""Entity grounding and media identity association for Intelligence Core v3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    EntityV3View,
    EvidenceEdgeV3View,
    KnowledgeGapView,
)

EntityType = Literal[
    "person",
    "character",
    "game_character",
    "game",
    "project",
    "organization",
    "concept",
    "place",
    "media_work",
]


@dataclass(frozen=True, slots=True)
class EntityGroundingResult:
    entity: EntityV3View | None
    state: Literal["known", "provisional", "unresolved"]
    knowledge_gap: KnowledgeGapView | None = None


class EntityGroundingService:
    """Answer who/what a reference denotes without forcing unsupported identity."""

    def __init__(self, repository: EntityEvidenceRepository) -> None:
        self.repository = repository

    @staticmethod
    def _trigger_ref(triggered_by_ref: str, evidence_refs: tuple[str, ...]) -> str:
        if triggered_by_ref:
            return triggered_by_ref
        return evidence_refs[0] if evidence_refs else ""

    def resolve_or_provision(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        name: str,
        entity_type: EntityType,
        evidence_refs: tuple[str, ...],
        missing_fields: tuple[str, ...] = (),
        importance: float = 0.5,
        triggered_by_ref: str = "",
        now: datetime | None = None,
    ) -> EntityGroundingResult:
        current = now or datetime.now(UTC)
        existing = self.repository.find_entity(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            name=name,
            entity_type=entity_type,
        )
        if existing is not None:
            state: Literal["known", "provisional", "unresolved"] = (
                "known" if existing.status == "canonical" else "provisional"
            )
            gap: KnowledgeGapView | None = None
            if missing_fields:
                gap = self.repository.create_gap(
                    owner_id=owner_id,
                    connection_id=connection_id,
                    guild_id=guild_id,
                    entity_id=existing.id,
                    missing_fields=missing_fields,
                    triggered_by_ref=self._trigger_ref(triggered_by_ref, evidence_refs),
                    importance=importance,
                    possible_sources=("conversation", "wiki", "knowledge", "discovery"),
                    now=current,
                )
            return EntityGroundingResult(existing, state, gap)

        if not any(ref.strip() for ref in evidence_refs):
            return EntityGroundingResult(None, "unresolved")

        entity = self.repository.ensure_entity(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            name=name,
            entity_type=entity_type,
            status="provisional",
            source_refs=evidence_refs,
            now=current,
        )
        gap = None
        if missing_fields:
            gap = self.repository.create_gap(
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                entity_id=entity.id,
                missing_fields=missing_fields,
                triggered_by_ref=self._trigger_ref(triggered_by_ref, evidence_refs),
                importance=importance,
                possible_sources=("conversation", "wiki", "knowledge", "discovery"),
                now=current,
            )
        return EntityGroundingResult(entity, "provisional", gap)

    def confirm(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        entity_id: str,
        canonical_name: str = "",
        metadata: dict[str, str] | None = None,
        evidence_refs: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> EntityV3View:
        return self.repository.confirm_entity(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            entity_id=entity_id,
            canonical_name=canonical_name,
            metadata=metadata,
            source_refs=evidence_refs,
            now=now,
        )

    def associate_media(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        media_ref: str,
        entity_id: str,
        confidence: float,
        evidence_refs: tuple[str, ...],
        explicit_caption: bool = False,
        verified_reference: bool = False,
        source_model: str = "",
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        """Persist DEPICTS separately from objective media perception.

        A model-only visual match is tentative. Explicit same-message naming or a verified reference
        can raise authority, but even a high-confidence visual association remains revisable.
        """

        current = now or datetime.now(UTC)
        if explicit_caption:
            authority = "explicit_conversation_reference"
            status = "active"
            bounded = max(confidence, 0.95)
            source_kind = "conversation_grounding"
        elif verified_reference:
            authority = "verified_visual_reference"
            status = "active" if confidence >= 0.85 else "unresolved"
            bounded = confidence
            source_kind = "visual_reference_match"
        else:
            authority = "model_inference"
            status = "active" if confidence >= 0.92 else "unresolved"
            bounded = confidence
            source_kind = "media_entity_grounding"
        return self.repository.add_edge(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            source_ref_type="media",
            source_ref=media_ref,
            relation_type="DEPICTS",
            target_ref_type="entity",
            target_ref=entity_id,
            confidence=bounded,
            authority_class=authority,
            source_kind=source_kind,
            evidence_refs=evidence_refs,
            status=status,
            producer="entity_grounding_v3",
            source_model=source_model,
            valid_from=current,
            now=current,
        )

    def revise_media_association(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        previous_edge_id: str,
        media_ref: str,
        entity_id: str,
        confidence: float,
        evidence_refs: tuple[str, ...],
        authority_class: str = "user_correction",
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        current = now or datetime.now(UTC)
        return self.repository.add_edge(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            source_ref_type="media",
            source_ref=media_ref,
            relation_type="DEPICTS",
            target_ref_type="entity",
            target_ref=entity_id,
            confidence=confidence,
            authority_class=authority_class,
            source_kind="grounding_revision",
            evidence_refs=evidence_refs,
            status="active",
            supersedes_edge_id=previous_edge_id,
            producer="entity_grounding_v3",
            valid_from=current,
            now=current,
        )

    def reject_media_association(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        edge_id: str,
        now: datetime | None = None,
    ) -> EvidenceEdgeV3View:
        return self.repository.reject_edge(
            owner_id=owner_id,
            connection_id=connection_id,
            guild_id=guild_id,
            edge_id=edge_id,
            now=now,
        )

    def entity_prompt_context(self, entity: EntityV3View) -> str:
        known = [
            f"Entity: {entity.canonical_name}",
            f"Type: {entity.entity_type}",
            f"Identity status: {entity.status}",
        ]
        if entity.metadata:
            known.append("Known fields:")
            known.extend(f"- {key}: {value}" for key, value in sorted(entity.metadata.items()))
        if entity.status != "canonical":
            known.append("Do not invent canonical identity or lore not supported by evidence.")
        return "\n".join(known)


__all__ = [
    "EntityGroundingResult",
    "EntityGroundingService",
    "EntityType",
]
