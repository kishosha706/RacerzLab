"""P35.1 unified, non-authorizing engineering-knowledge contracts.

The static bridge connects reviewed Dial-In effects to the canonical P20/P26/
P32/P35 ontology.  Runtime projections may describe current relevance and may
mirror one exact P19 controlled test, but they cannot create setup authority.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.identity import canonical_json_sha256


_SHA = r"^[0-9a-f]{64}$"
_ID = r"^[a-z0-9][a-z0-9_.:-]*$"


class EngineeringKnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


KnowledgeLevel = Literal[
    "educational_knowledge",
    "measurable_hypothesis",
    "p19_testable_control",
    "unsupported_remove",
]


class MechanismSetupBridge(EngineeringKnowledgeModel):
    schema_version: Literal["p351.mechanism-setup-bridge.v1"] = (
        "p351.mechanism-setup-bridge.v1"
    )
    bridge_id: str = Field(pattern=r"^p351b_[0-9a-f]{24}$")
    bridge_sha256: str = Field(pattern=_SHA)
    effect_id: str = Field(pattern=_ID)
    setup_area: str = Field(pattern=_ID)
    knowledge_version: str = Field(min_length=1)
    p35_knowledge_graph_sha256: str = Field(pattern=_SHA)
    p35_runtime_trust_sha256: str = Field(pattern=_SHA)
    catalog_classification: KnowledgeLevel
    physical_role: str = Field(min_length=1)
    car_applicability: tuple[str, ...] = Field(min_length=1)
    disabled_car_families: tuple[str, ...] = ()
    p35_mechanism_ids: tuple[str, ...] = ()
    p20_mechanism_ids: tuple[str, ...] = ()
    p26_component_family_ids: tuple[str, ...] = ()
    p32_performance_mechanism_ids: tuple[str, ...] = ()
    response_regimes: tuple[Literal["transient", "steady_state", "both"], ...] = ()
    relevant_phases: tuple[str, ...] = ()
    inspection_tool_ids: tuple[str, ...] = ()
    discriminator_contract_ids: tuple[str, ...] = ()
    required_evidence_layers: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = Field(min_length=1)
    validation_targets: tuple[str, ...] = Field(min_length=1)
    countereffect_targets: tuple[str, ...] = Field(min_length=1)
    protected_outcomes: tuple[str, ...] = Field(min_length=1)
    related_control_keys: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["knowledge_only"] = "knowledge_only"
    setup_authorized: Literal[False] = False
    exact_action_exposed: Literal[False] = False

    @staticmethod
    def _body(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key not in {"bridge_id", "bridge_sha256"}
        }

    @classmethod
    def build(cls, **values: Any) -> Self:
        draft = cls.model_construct(
            **values,
            bridge_id="p351b_" + ("0" * 24),
            bridge_sha256="0" * 64,
        )
        normalized = draft.model_dump(mode="json")
        digest = canonical_json_sha256(cls._body(normalized))
        return cls.model_validate(
            {
                **normalized,
                "bridge_id": f"p351b_{digest[:24]}",
                "bridge_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def bridge_is_closed_and_content_addressed(self) -> Self:
        sequences = (
            self.car_applicability,
            self.disabled_car_families,
            self.p35_mechanism_ids,
            self.p20_mechanism_ids,
            self.p26_component_family_ids,
            self.p32_performance_mechanism_ids,
            self.response_regimes,
            self.relevant_phases,
            self.inspection_tool_ids,
            self.discriminator_contract_ids,
            self.required_evidence_layers,
            self.evidence_requirements,
            self.validation_targets,
            self.countereffect_targets,
            self.protected_outcomes,
            self.related_control_keys,
            self.source_ids,
        )
        if any(len(values) != len(set(values)) for values in sequences):
            raise ValueError("P35.1 bridge relations must be unique")
        unsupported = self.catalog_classification == "unsupported_remove"
        if unsupported != (not self.p35_mechanism_ids):
            raise ValueError(
                "unsupported effects must be the only bridges without P35 mechanisms"
            )
        if unsupported and not self.disabled_car_families:
            raise ValueError("unsupported effects require an explicit car-family exclusion")
        dumped = self.model_dump(mode="json")
        expected = canonical_json_sha256(self._body(dumped))
        if self.bridge_sha256 != expected or self.bridge_id != f"p351b_{expected[:24]}":
            raise ValueError("P35.1 bridge identity is corrupt")
        return self


class EngineeringKnowledgeCoverageReport(EngineeringKnowledgeModel):
    schema_version: Literal["p351.knowledge-coverage.v1"] = (
        "p351.knowledge-coverage.v1"
    )
    report_sha256: str = Field(pattern=_SHA)
    catalog_effect_count: int = Field(ge=1)
    bridge_count: int = Field(ge=1)
    educational_count: int = Field(ge=0)
    measurable_count: int = Field(ge=0)
    structurally_p19_testable_count: int = Field(ge=0)
    unsupported_remove_count: int = Field(ge=0)
    mapped_effect_ids: tuple[str, ...] = Field(min_length=1)
    unmapped_effect_ids: tuple[str, ...] = ()
    duplicate_effect_ids: tuple[str, ...] = ()
    legacy_forbidden_effect_ids: tuple[str, ...] = ()
    bridge_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def coverage_is_complete(self) -> Self:
        if self.catalog_effect_count != self.bridge_count:
            raise ValueError("every setup effect must have exactly one P35.1 bridge")
        if self.unmapped_effect_ids or self.duplicate_effect_ids:
            raise ValueError("P35.1 coverage cannot omit or duplicate catalog effects")
        if len(self.mapped_effect_ids) != self.catalog_effect_count:
            raise ValueError("P35.1 mapped inventory must equal the catalog")
        if len(self.bridge_ids) != self.bridge_count:
            raise ValueError("P35.1 bridge identities must be complete")
        if (
            self.educational_count
            + self.measurable_count
            + self.structurally_p19_testable_count
            + self.unsupported_remove_count
            != self.catalog_effect_count
        ):
            raise ValueError("P35.1 coverage classifications must partition the catalog")
        body = self.model_dump(mode="json", exclude={"report_sha256"})
        if canonical_json_sha256(body) != self.report_sha256:
            raise ValueError("P35.1 coverage report identity is corrupt")
        return self


class ControlledKnowledgeHistory(EngineeringKnowledgeModel):
    experience_id: str = Field(pattern=r"^p33x_[0-9a-f]{24}$")
    workflow_id: str = Field(min_length=1)
    component_family_id: str = Field(pattern=_ID)
    control_key: str = Field(pattern=_ID)
    transfer_level: Literal["exact", "compatible"]
    mechanism_assessment: Literal[
        "supported", "weakened", "unchanged", "inconclusive", "invalid"
    ]
    control_response: Literal[
        "matched", "missed", "inconclusive", "unavailable", "invalid"
    ]
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    countereffects: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = ()
    authority: Literal["controlled_history_only"] = "controlled_history_only"
    setup_authorized: Literal[False] = False


class P19TestableControl(EngineeringKnowledgeModel):
    control_key: str = Field(pattern=_ID)
    current_value: str = Field(min_length=1)
    proposed_value: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    workflow_revision: str = Field(min_length=1)
    source_event_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["exact_p19_projection"] = "exact_p19_projection"


class CanonicalPerformanceOpportunityBinding(EngineeringKnowledgeModel):
    """Immutable workflow receipt for the exact P32 opportunity used by P19."""

    schema_version: Literal["p351.workflow-performance-opportunity.v1"] = (
        "p351.workflow-performance-opportunity.v1"
    )
    binding_sha256: str = Field(pattern=_SHA)
    p32_projection_sha256: str = Field(pattern=_SHA)
    p32_opportunity_id: str = Field(min_length=1)
    engineering_knowledge_projection_sha256: str = Field(pattern=_SHA)
    start_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    end_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    phase: str = Field(min_length=1)
    observed_time_effect_s: float = Field(gt=0.0, allow_inf_nan=False)
    authority: Literal["observation_only"] = "observation_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def binding_is_canonical(self) -> Self:
        if self.end_pct <= self.start_pct:
            raise ValueError("canonical P32 opportunity window must be non-zero")
        body = self.model_dump(mode="json", exclude={"binding_sha256"})
        if canonical_json_sha256(body) != self.binding_sha256:
            raise ValueError("canonical P32 opportunity binding is corrupt")
        return self


class CurrentKnowledgeHypothesis(EngineeringKnowledgeModel):
    bridge_id: str = Field(pattern=r"^p351b_[0-9a-f]{24}$")
    effect_id: str = Field(pattern=_ID)
    setup_area: str = Field(pattern=_ID)
    physical_role: str = Field(min_length=1)
    level: KnowledgeLevel
    relevance: Literal[
        "supported_candidate",
        "blocked_candidate",
        "knowledge_only",
        "inapplicable",
    ]
    p32_opportunity_id: str | None = None
    p35_mechanism_ids: tuple[str, ...] = ()
    p20_mechanism_ids: tuple[str, ...] = ()
    p26_component_family_ids: tuple[str, ...] = ()
    response_regimes: tuple[Literal["transient", "steady_state", "both"], ...] = ()
    relevant_phases: tuple[str, ...] = ()
    expected_vehicle_response_ids: tuple[str, ...] = ()
    countereffect_ids: tuple[str, ...] = ()
    protected_outcomes: tuple[str, ...] = ()
    inspection_tool_ids: tuple[str, ...] = ()
    support_artifact_ids: tuple[str, ...] = ()
    contradiction_artifact_ids: tuple[str, ...] = ()
    discriminator_contract_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    controlled_history: tuple[ControlledKnowledgeHistory, ...] = ()
    p19_control: P19TestableControl | None = None
    authority: Literal[
        "knowledge_only", "measurement_only", "exact_p19_projection"
    ]
    setup_authorized: bool = False

    @model_validator(mode="after")
    def level_preserves_authority(self) -> Self:
        sequences = (
            self.p35_mechanism_ids,
            self.p20_mechanism_ids,
            self.p26_component_family_ids,
            self.response_regimes,
            self.relevant_phases,
            self.expected_vehicle_response_ids,
            self.countereffect_ids,
            self.protected_outcomes,
            self.inspection_tool_ids,
            self.support_artifact_ids,
            self.contradiction_artifact_ids,
            self.discriminator_contract_ids,
            self.missing_evidence,
        )
        if any(len(values) != len(set(values)) for values in sequences):
            raise ValueError("current P35.1 hypothesis relations must be unique")
        if self.level == "p19_testable_control":
            if (
                self.p19_control is None
                or self.authority != "exact_p19_projection"
                or not self.setup_authorized
                or self.relevance
                not in {"supported_candidate", "blocked_candidate"}
            ):
                raise ValueError("level-three knowledge must exactly mirror P19")
        elif (
            self.p19_control is not None
            or self.authority == "exact_p19_projection"
            or self.setup_authorized
        ):
            raise ValueError("level-one/two knowledge cannot expose a setup action")
        if self.level == "measurable_hypothesis" and self.authority != "measurement_only":
            raise ValueError("measurable hypotheses have measurement authority only")
        if self.level in {"educational_knowledge", "unsupported_remove"} and (
            self.authority != "knowledge_only"
        ):
            raise ValueError("educational knowledge has no current-run authority")
        return self


class CurrentEngineeringKnowledgeProjection(EngineeringKnowledgeModel):
    schema_version: Literal["p351.current-engineering-knowledge.v1"] = (
        "p351.current-engineering-knowledge.v1"
    )
    projection_sha256: str = Field(pattern=_SHA)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    complaint_prior: str | None = None
    p19_reasoning_snapshot_sha256: str = Field(pattern=_SHA)
    p20_state_revision: str = Field(pattern=_SHA)
    p26_knowledge_graph_sha256: str = Field(pattern=_SHA)
    p32_projection_sha256: str = Field(pattern=_SHA)
    p35_assessment_sha256: str = Field(pattern=_SHA)
    p33_projection_sha256: str = Field(pattern=_SHA)
    bridge_coverage_sha256: str = Field(pattern=_SHA)
    p32_opportunity_id: str | None = None
    hypotheses: tuple[CurrentKnowledgeHypothesis, ...] = Field(min_length=1)
    leading_hypothesis_ids: tuple[str, ...] = ()
    next_discriminator_contract_id: str | None = None
    blocker_reasons: tuple[str, ...] = ()
    terminal_authority: Literal["p19_only"] = "p19_only"
    non_p19_setup_authorized: Literal[False] = False

    @staticmethod
    def _body(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key != "projection_sha256"}

    @classmethod
    def build(cls, **values: Any) -> Self:
        draft = cls.model_construct(**values, projection_sha256="0" * 64)
        normalized = draft.model_dump(mode="json")
        return cls.model_validate(
            {
                **normalized,
                "projection_sha256": canonical_json_sha256(cls._body(normalized)),
            }
        )

    @model_validator(mode="after")
    def projection_is_atomic(self) -> Self:
        effect_ids = tuple(item.effect_id for item in self.hypotheses)
        if len(effect_ids) != len(set(effect_ids)):
            raise ValueError("current knowledge may project each catalog effect once")
        if not set(self.leading_hypothesis_ids) <= set(effect_ids):
            raise ValueError("leading knowledge identities must resolve in the projection")
        level_three = tuple(
            item for item in self.hypotheses if item.level == "p19_testable_control"
        )
        if len(level_three) > 1:
            raise ValueError("P35.1 may mirror at most one exact P19 setup action")
        dumped = self.model_dump(mode="json")
        if canonical_json_sha256(self._body(dumped)) != self.projection_sha256:
            raise ValueError("current engineering knowledge identity is corrupt")
        return self


__all__ = [
    "ControlledKnowledgeHistory",
    "CanonicalPerformanceOpportunityBinding",
    "CurrentEngineeringKnowledgeProjection",
    "CurrentKnowledgeHypothesis",
    "EngineeringKnowledgeCoverageReport",
    "KnowledgeLevel",
    "MechanismSetupBridge",
    "P19TestableControl",
]
