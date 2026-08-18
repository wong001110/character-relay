"""Relationship/Social Intelligence v2 API contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RelationshipTargetType = Literal["actor", "deployment"]


class CharacterRelationshipPriorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_type: str = Field(default="other", max_length=80)
    description: str = Field(default="", max_length=4000)
    familiarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    affinity: float = Field(default=0.0, ge=-1.0, le=1.0)
    trust: float = Field(default=0.0, ge=-1.0, le=1.0)
    comfort: float = Field(default=0.0, ge=-1.0, le=1.0)


class CharacterRelationshipPriorView(CharacterRelationshipPriorUpdate):
    id: str
    source_character_card_id: str
    target_character_card_id: str


class CharacterRelationshipPriorList(BaseModel):
    items: list[CharacterRelationshipPriorView] = Field(default_factory=list)


class RelationshipGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_type: str = Field(default="other", max_length=80)
    description: str = Field(default="", max_length=4000)


class RelationshipGenerationView(CharacterRelationshipPriorUpdate):
    rationale: str = Field(default="", max_length=1000)
    provider_model: str = ""


class DeploymentRelationshipStateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_deployment_id: str
    target_type: RelationshipTargetType
    target_key: str
    familiarity: float
    affinity: float
    trust: float
    comfort: float
    familiarity_baseline: float
    affinity_baseline: float
    trust_baseline: float
    comfort_baseline: float
    last_evidence_at: str


class DeploymentRelationshipStateList(BaseModel):
    items: list[DeploymentRelationshipStateView] = Field(default_factory=list)


class PersonImpressionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: RelationshipTargetType
    target_key: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    observations: list[str] = Field(default_factory=list, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=16)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PersonImpressionView(PersonImpressionUpdate):
    pass


class DeploymentRelationshipCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_deployment_id: str
    target_character_card_id: str
    target_display_name: str
    canonical_prior: CharacterRelationshipPriorView | None = None
    dynamic_state: DeploymentRelationshipStateView | None = None
    impression: PersonImpressionView | None = None


class DeploymentRelationshipCandidateList(BaseModel):
    source_deployment_id: str
    source_character_card_id: str
    source_display_name: str
    items: list[DeploymentRelationshipCandidateView] = Field(default_factory=list)


class RelationshipEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: RelationshipTargetType
    target_key: str = Field(min_length=1, max_length=200)
    dimension: Literal["familiarity", "affinity", "trust", "comfort"]
    delta: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: str = Field(default="manual_evidence", max_length=120)
    source_message_id: str = Field(default="", max_length=200)
    source_burst_id: str = Field(default="", max_length=80)


__all__ = [
    "CharacterRelationshipPriorList",
    "CharacterRelationshipPriorUpdate",
    "CharacterRelationshipPriorView",
    "DeploymentRelationshipCandidateList",
    "DeploymentRelationshipCandidateView",
    "DeploymentRelationshipStateList",
    "DeploymentRelationshipStateView",
    "PersonImpressionUpdate",
    "PersonImpressionView",
    "RelationshipEvidenceRequest",
    "RelationshipGenerationRequest",
    "RelationshipGenerationView",
]
