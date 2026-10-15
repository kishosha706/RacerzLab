"""Typed handling-knowledge projection: display-only Dial-In context.

P35.6 Milestone P4. When a telemetry-observed handling observation travels
from Engineer to Dial-In, this projection carries exactly the display
material the Dial-In workspace needs:

- observed behavior (what the telemetry supports),
- relevant setup-catalog knowledge (P35.1 hypotheses whose reviewed
  mechanism families intersect the investigation finding),
- evidence status (satisfied or missing requirements per mechanism),
- countereffects (what would need protection during any future test),
- the next action (an inspection or measurement, unless P19 has already
  authorized an exact controlled experiment).

It is strictly a DERIVED view of producer-owned truth:

- It never writes DriverIntent and never fabricates driver wording. The
  observation origin is telemetry, and the driver's own complaint flow
  remains untouched.
- A canonical symptom appears only when the two-strand producer
  legitimately established it; otherwise `canonical_symptom_id` is None
  and the projection carries diagnostic wording only.
- The projection itself never authorizes setup. Per-hypothesis
  `setup_authorized` is True only when the knowledge spine mirrors an
  exact P19 projection (`p19_control` present); that is P19's authority,
  reported, not created, here.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.engineering_knowledge import (
    KnowledgeLevel,
    P19TestableControl,
)
from racelab_engine.models.handling_balance import HandlingClassification

_ASSESSMENT_ID = r"^hba_[0-9a-f]{24}$"
_MECHANISM_ID = r"^mechanism:[a-z][a-z0-9_]+$"
_SHA = r"^[0-9a-f]{64}$"


class HandlingKnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HandlingKnowledgeMechanismStatus(HandlingKnowledgeModel):
    """One mechanism the observation touched, and what it can and cannot say."""

    mechanism_id: str = Field(pattern=_MECHANISM_ID)
    label: str = Field(min_length=1)
    relevance: Literal["applicable", "informed_by_observation", "blocked"]
    missing_evidence: tuple[str, ...] = ()
    support_declared: Literal[False] = False


class HandlingKnowledgeHypothesis(HandlingKnowledgeModel):
    """One relevant P35.1 setup-catalog hypothesis, knowledge-only unless P19."""

    bridge_id: str = Field(pattern=r"^p351b_[0-9a-f]{24}$")
    effect_id: str = Field(pattern=r"^[a-z][a-z0-9_.:-]+$")
    setup_area: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    physical_role: str = Field(min_length=1)
    level: KnowledgeLevel
    relevance: Literal[
        "supported_candidate", "blocked_candidate", "knowledge_only"
    ]
    knowledge_applicability: Literal[
        "applicable", "educational_only", "blocked_by_build", "unsupported"
    ]
    p35_mechanism_ids: tuple[str, ...] = ()
    countereffect_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    authority: Literal[
        "knowledge_only", "measurement_only", "exact_p19_projection"
    ]
    setup_authorized: bool = False
    p19_control: P19TestableControl | None = None

    @model_validator(mode="after")
    def authority_is_exact(self) -> HandlingKnowledgeHypothesis:
        if self.p19_control is None:
            if self.setup_authorized or self.authority == "exact_p19_projection":
                raise ValueError(
                    "handling knowledge without an exact P19 control cannot "
                    "authorize setup"
                )
        else:
            if not self.setup_authorized or self.authority != "exact_p19_projection":
                raise ValueError(
                    "an exact P19 control must carry P19 authority"
                )
            if (
                self.p19_control.effect_id != self.effect_id
                or self.level != "p19_testable_control"
            ):
                raise ValueError(
                    "an exact P19 control must match its bridge identity"
                )
        return self


class HandlingKnowledgeNextAction(HandlingKnowledgeModel):
    kind: Literal[
        "inspect_evidence", "measure", "p19_authorized_experiment"
    ]
    instruction: str = Field(min_length=1)


class HandlingKnowledgeProjection(HandlingKnowledgeModel):
    """Run/assessment-level handling knowledge for one Dial-In handoff."""

    schema_version: Literal["p356.handling-knowledge.v1"] = (
        "p356.handling-knowledge.v1"
    )
    projection_sha256: str = Field(pattern=_SHA)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_revision_sha256: str = Field(pattern=_SHA)
    case_sha256: str = Field(pattern=_SHA)
    assessment_id: str = Field(pattern=_ASSESSMENT_ID)
    phase: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    classification: HandlingClassification
    canonical_symptom_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9_.:-]*$"
    )
    corroborated: bool = False
    observed_behavior: str = Field(min_length=1)
    evidence_qualification: str = Field(min_length=1)
    mechanisms: tuple[HandlingKnowledgeMechanismStatus, ...]
    relevant_knowledge: tuple[HandlingKnowledgeHypothesis, ...]
    countereffects: tuple[str, ...] = ()
    evidence_status: tuple[str, ...] = ()
    next_evidence_channels: tuple[str, ...] = ()
    next_action: HandlingKnowledgeNextAction
    authority: Literal["derived_observation_view"] = "derived_observation_view"
    setup_authorized: Literal[False] = False
    p19_authority_unchanged: Literal[True] = True

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("projection_sha256", None)
        provisional = cls.model_construct(
            **body,
            projection_sha256="0" * 64,
        )
        normalized = provisional.model_dump(mode="json")
        normalized.pop("projection_sha256", None)
        digest = canonical_json_sha256(normalized)
        return cls.model_validate(
            {**normalized, "projection_sha256": digest}
        )

    @model_validator(mode="after")
    def projection_is_closed(self) -> HandlingKnowledgeProjection:
        if self.corroborated != (self.canonical_symptom_id is not None):
            raise ValueError(
                "a canonical symptom requires two-strand corroboration"
            )
        if any(
            item.relevance == "blocked" and not item.missing_evidence
            for item in self.mechanisms
        ):
            raise ValueError("a blocked mechanism must name its missing evidence")
        mechanism_ids = {item.mechanism_id for item in self.mechanisms}
        if any(
            mechanism_id not in mechanism_ids
            for hypothesis in self.relevant_knowledge
            for mechanism_id in hypothesis.p35_mechanism_ids
        ):
            raise ValueError(
                "relevant knowledge mechanisms must resolve inside the projection"
            )
        body = self.model_dump(mode="json", exclude={"projection_sha256"})
        if canonical_json_sha256(body) != self.projection_sha256:
            raise ValueError("handling knowledge projection identity is corrupt")
        return self


__all__ = [
    "HandlingKnowledgeHypothesis",
    "HandlingKnowledgeMechanismStatus",
    "HandlingKnowledgeNextAction",
    "HandlingKnowledgeProjection",
]
