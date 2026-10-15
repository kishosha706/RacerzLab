"""Typed handling-investigation projection: a derived, non-authoritative view.

P35.6 Milestone P2. This projection connects a qualified automatic handling
observation to the existing scientific intelligence spine:

    P35 mechanism graph -> P26 component awareness -> P32 measured performance
    -> alternative explanations -> next inspection.

It is strictly a DERIVED view of producer-owned truth. It never declares a
mechanism supported, never declares a component malfunction, never attributes
time loss to a component, never writes DriverIntent, and never authorizes a
setup change. The authority literal is structurally fixed; a client trust
validator can reject any drift.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.handling_balance import HandlingClassification

_ASSESSMENT_ID = r"^hba_[0-9a-f]{24}$"
_MECHANISM_ID = r"^mechanism:[a-z][a-z0-9_]+$"
_COMPONENT_ID = r"^[a-z][a-z0-9_]+$"
_SHA = r"^[0-9a-f]{64}$"


class HandlingInvestigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HandlingAssessmentRef(HandlingInvestigationModel):
    """Exact identity reference to one qualified producer assessment."""

    assessment_id: str = Field(pattern=_ASSESSMENT_ID)
    run_id: str = Field(min_length=1)
    phase: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    classification: HandlingClassification
    canonical_symptom_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9_.:-]*$"
    )
    corroborated: bool = False
    lap_numbers: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def symptom_requires_corroboration(self) -> HandlingAssessmentRef:
        if self.corroborated != (self.canonical_symptom_id is not None):
            raise ValueError(
                "a canonical symptom reference requires two-strand corroboration"
            )
        if len(self.lap_numbers) != len(set(self.lap_numbers)):
            raise ValueError("assessment reference lap numbers must be unique")
        return self


class HandlingMechanismRelation(HandlingInvestigationModel):
    """One applicable P35 mechanism and how the observation informs it."""

    mechanism_id: str = Field(pattern=_MECHANISM_ID)
    label: str = Field(min_length=1)
    relevance: Literal["applicable", "informed_by_observation", "blocked"]
    response_regime: str = Field(min_length=1)
    applicable_phases: tuple[str, ...] = Field(min_length=1)
    direction: Literal["deficit_aligned", "excess_aligned", "neutral", "none"]
    discriminator_contract_ids: tuple[str, ...] = ()
    p26_component_family_ids: tuple[str, ...] = ()
    required_channels: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    support_declared: Literal[False] = False


class HandlingComponentRelation(HandlingInvestigationModel):
    """One relevant P26 component family and its P26-owned state."""

    component_id: str = Field(pattern=_COMPONENT_ID)
    relevance: Literal[
        "mechanically_relevant",
        "observable",
        "supported",
        "contradicted",
        "unavailable",
    ]
    observability_states: tuple[str, ...] = ()
    source: Literal["p26_component_awareness"] = "p26_component_awareness"
    malfunction_declared: Literal[False] = False


class HandlingPerformanceAssociation(HandlingInvestigationModel):
    """A co-occurring, P32-owned measured performance consequence."""

    opportunity_id: str = Field(min_length=1)
    track_region: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    measured_delta_s: float | None = Field(default=None, allow_inf_nan=False)
    repeatability: str = Field(min_length=1)
    attribution_state: str = Field(min_length=1)
    wording: str = Field(min_length=1)
    causation_declared: Literal[False] = False


class HandlingAlternativeExplanation(HandlingInvestigationModel):
    """One evaluated competing explanation, with an explicit state."""

    explanation_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    statement: str = Field(min_length=1)
    state: Literal[
        "supported", "contradicted", "plausible_unresolved", "not_observable"
    ]
    basis: tuple[str, ...] = ()


class HandlingInvestigationFinding(HandlingInvestigationModel):
    """One WHAT/WHERE/DRIVER/RESPONSE/... reasoning chain for a qualified phase."""

    assessment_id: str = Field(pattern=_ASSESSMENT_ID)
    phase: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    what: str = Field(min_length=1)
    where: str = Field(min_length=1)
    driver: str = Field(min_length=1)
    response: str = Field(min_length=1)
    mechanisms: tuple[HandlingMechanismRelation, ...] = ()
    components: tuple[HandlingComponentRelation, ...] = ()
    performance: tuple[HandlingPerformanceAssociation, ...] = ()
    contradictions: tuple[str, ...] = ()
    uncertain: tuple[str, ...] = ()
    next: str = Field(min_length=1)
    next_evidence_channels: tuple[str, ...] = ()


class HandlingInvestigationProjection(HandlingInvestigationModel):
    """Run-level unified handling investigation projection."""

    schema_version: Literal["p356.handling-investigation.v1"] = (
        "p356.handling-investigation.v1"
    )
    projection_sha256: str = Field(pattern=_SHA)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    handling_report_classification: HandlingClassification
    assessment_refs: tuple[HandlingAssessmentRef, ...] = Field(min_length=1)
    evidence_dependence: tuple[str, ...] = Field(min_length=1)
    findings: tuple[HandlingInvestigationFinding, ...] = Field(min_length=1)
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
    def projection_is_closed(self) -> HandlingInvestigationProjection:
        ref_ids = {item.assessment_id for item in self.assessment_refs}
        if len(ref_ids) != len(self.assessment_refs):
            raise ValueError("handling assessment references must be unique")
        if any(
            item.run_id != self.run_id for item in self.assessment_refs
        ):
            raise ValueError(
                "handling assessment references must bind the projection run"
            )
        if any(
            item.assessment_id not in ref_ids for item in self.findings
        ):
            raise ValueError(
                "every handling finding must resolve a projected assessment"
            )
        finding_ids = [item.assessment_id for item in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("handling findings must be unique per assessment")
        if any(
            item.phase not in {
                ref.phase for ref in self.assessment_refs if ref.assessment_id == item.assessment_id
            }
            for item in self.findings
        ):
            raise ValueError("handling finding phases must match their assessment")
        body = self.model_dump(mode="json", exclude={"projection_sha256"})
        if canonical_json_sha256(body) != self.projection_sha256:
            raise ValueError("handling investigation projection identity is corrupt")
        return self


__all__ = [
    "HandlingAlternativeExplanation",
    "HandlingAssessmentRef",
    "HandlingComponentRelation",
    "HandlingInvestigationFinding",
    "HandlingInvestigationProjection",
    "HandlingMechanismRelation",
    "HandlingPerformanceAssociation",
]
