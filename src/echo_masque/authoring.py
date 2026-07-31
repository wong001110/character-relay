"""Reviewable Scenario and Test Pack authoring draft contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from echo_masque.workspace import ScenarioFields, ScenarioView, TestPackView

DraftStatus = Literal["draft", "approved", "rejected"]
DraftSource = Literal["manual", "ai"]


class DraftProvenance(BaseModel):
    """Non-secret provenance retained with a reviewable authoring draft."""

    model_config = ConfigDict(extra="forbid")

    source: DraftSource = "manual"
    character_card_id: str | None = Field(default=None, max_length=64)
    source_model: str | None = Field(default=None, max_length=200)
    prompt_hash: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    risk_tags: list[str] = Field(default_factory=list, max_length=20)
    generated_at: datetime | None = None

    @model_validator(mode="after")
    def normalize_risk_tags(self) -> "DraftProvenance":
        normalized: list[str] = []
        for value in self.risk_tags:
            item = value.strip()
            if item and item not in normalized:
                normalized.append(item)
        self.risk_tags = normalized
        return self


class ScenarioDraftFields(ScenarioFields):
    provenance: DraftProvenance = Field(default_factory=DraftProvenance)
    review_notes: str = Field(default="", max_length=4000)


class ScenarioDraftCreate(ScenarioDraftFields):
    pass


class ScenarioDraftUpdate(ScenarioDraftFields):
    pass


class ScenarioDraftView(ScenarioDraftFields):
    id: str
    owner_id: str
    status: DraftStatus
    revision: int
    approved_scenario_id: str | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None


class PackDraftItemInput(BaseModel):
    """Reference either a formal Scenario or an approved Scenario Draft."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str | None = Field(default=None, max_length=64)
    scenario_draft_id: str | None = Field(default=None, max_length=64)
    enabled: bool = True

    @model_validator(mode="after")
    def exactly_one_reference(self) -> "PackDraftItemInput":
        if (self.scenario_id is None) == (self.scenario_draft_id is None):
            raise ValueError("Exactly one Scenario or Scenario Draft reference is required.")
        return self

    @property
    def reference_key(self) -> str:
        return f"scenario:{self.scenario_id}" if self.scenario_id else f"draft:{self.scenario_draft_id}"


class TestPackDraftFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=3000)
    items: list[PackDraftItemInput] = Field(default_factory=list, max_length=100)
    provenance: DraftProvenance = Field(default_factory=DraftProvenance)
    review_notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def unique_references(self) -> "TestPackDraftFields":
        references = [item.reference_key for item in self.items]
        if len(references) != len(set(references)):
            raise ValueError("A Scenario reference may appear only once in a Test Pack Draft.")
        return self


class TestPackDraftCreate(TestPackDraftFields):
    pass


class TestPackDraftUpdate(TestPackDraftFields):
    pass


class TestPackDraftView(TestPackDraftFields):
    id: str
    owner_id: str
    status: DraftStatus
    revision: int
    approved_test_pack_id: str | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None


class ScenarioDraftApproval(BaseModel):
    draft: ScenarioDraftView
    scenario: ScenarioView


class TestPackDraftApproval(BaseModel):
    draft: TestPackDraftView
    test_pack: TestPackView
