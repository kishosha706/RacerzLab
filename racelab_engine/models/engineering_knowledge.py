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
    schema_version: Literal["p352.mechanism-setup-bridge.v1"] = (
        "p352.mechanism-setup-bridge.v1"
    )
    bridge_id: str = Field(pattern=r"^p351b_[0-9a-f]{24}$")
    bridge_sha256: str = Field(pattern=_SHA)
    effect_id: str = Field(pattern=_ID)
    setup_area: str = Field(pattern=_ID)
    knowledge_version: str = Field(min_length=1)
    p35_knowledge_graph_sha256: str = Field(pattern=_SHA)
    p35_runtime_trust_sha256: str = Field(pattern=_SHA)
    catalog_classification: KnowledgeLevel
    direction_sign: Literal[-1, 0, 1]
    experiment_factor_id: str | None = Field(default=None, pattern=_ID)
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
    expected_vehicle_state_ids: tuple[str, ...] = Field(min_length=1)
    validation_metric_ids: tuple[str, ...] = Field(min_length=1)
    countereffect_state_ids: tuple[str, ...] = Field(min_length=1)
    protected_performance_outcome_ids: tuple[str, ...] = Field(min_length=1)
    rollback_condition_ids: tuple[str, ...] = Field(min_length=1)
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
            self.expected_vehicle_state_ids,
            self.validation_metric_ids,
            self.countereffect_state_ids,
            self.protected_performance_outcome_ids,
            self.rollback_condition_ids,
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
        testable = self.catalog_classification == "p19_testable_control"
        if testable != bool(
            self.related_control_keys
            and self.direction_sign in {-1, 1}
            and self.experiment_factor_id is not None
        ):
            raise ValueError(
                "P19-testable bridges require one explicit control direction and experiment factor"
            )
        dumped = self.model_dump(mode="json")
        expected = canonical_json_sha256(self._body(dumped))
        if self.bridge_sha256 != expected or self.bridge_id != f"p351b_{expected[:24]}":
            raise ValueError("P35.1 bridge identity is corrupt")
        return self


class EngineeringKnowledgeCoverageReport(EngineeringKnowledgeModel):
    schema_version: Literal["p352.knowledge-coverage.v1"] = (
        "p352.knowledge-coverage.v1"
    )
    report_sha256: str = Field(pattern=_SHA)
    catalog_effect_count: int = Field(ge=1)
    bridge_count: int = Field(ge=1)
    educational_count: int = Field(ge=0)
    measurable_count: int = Field(ge=0)
    testable_effect_count: int = Field(ge=0)
    distinct_control_count: int = Field(ge=0)
    distinct_control_direction_count: int = Field(ge=0)
    distinct_experiment_factor_count: int = Field(ge=0)
    coordinated_multi_control_contract_count: int = Field(ge=0)
    current_action_ready_count: Literal[0] = 0
    identity_coverage_count: int = Field(ge=0)
    semantic_precision_count: int = Field(ge=0)
    runtime_observability_contract_count: int = Field(ge=0)
    experiment_coverage_count: int = Field(ge=0)
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
            + self.testable_effect_count
            + self.unsupported_remove_count
            != self.catalog_effect_count
        ):
            raise ValueError("P35.1 coverage classifications must partition the catalog")
        if self.identity_coverage_count != self.catalog_effect_count:
            raise ValueError("identity coverage must include every catalog effect")
        if self.semantic_precision_count != self.catalog_effect_count:
            raise ValueError("semantic precision must be explicit for every catalog effect")
        if self.experiment_coverage_count != self.testable_effect_count:
            raise ValueError("every structurally testable effect needs an experiment factor")
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
    effect_id: str = Field(pattern=_ID)
    control_key: str = Field(pattern=_ID)
    direction_sign: Literal[-1, 1]
    experiment_factor_id: str = Field(pattern=_ID)
    current_value: str = Field(min_length=1)
    proposed_value: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    workflow_revision: str = Field(min_length=1)
    source_event_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["exact_p19_projection"] = "exact_p19_projection"


class CanonicalPhysicalSegment(EngineeringKnowledgeModel):
    start_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    end_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def segment_is_nonwrapping(self) -> Self:
        if self.end_pct <= self.start_pct:
            raise ValueError("canonical physical segments must be non-zero and ordered")
        return self


class CanonicalPerformanceOpportunityBinding(EngineeringKnowledgeModel):
    """Immutable workflow receipt for the exact P32 opportunity used by P19."""

    schema_version: Literal["p352.workflow-performance-opportunity.v1"] = (
        "p352.workflow-performance-opportunity.v1"
    )
    binding_sha256: str = Field(pattern=_SHA)
    p32_projection_sha256: str = Field(pattern=_SHA)
    p32_opportunity_id: str = Field(min_length=1)
    engineering_knowledge_projection_sha256: str = Field(pattern=_SHA)
    start_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    end_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    phase: str = Field(min_length=1)
    physical_segment_set_sha256: str = Field(pattern=_SHA)
    segments: tuple[CanonicalPhysicalSegment, ...] = Field(min_length=1)
    circular_scope: bool
    independence_unit: Literal["one_contiguous_physical_window"]
    observed_time_effect_s: float = Field(gt=0.0, allow_inf_nan=False)
    authority: Literal["observation_only"] = "observation_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def binding_is_canonical(self) -> Self:
        if self.end_pct <= self.start_pct:
            raise ValueError("canonical P32 opportunity window must be non-zero")
        if self.circular_scope or self.segments != (
            CanonicalPhysicalSegment(start_pct=self.start_pct, end_pct=self.end_pct),
        ):
            raise ValueError(
                "P35.2 fails closed until P32 owns a disjoint or circular segment set"
            )
        segment_body = {
            "schema_version": "p352.physical-segment-set.v1",
            "segments": [item.model_dump(mode="json") for item in self.segments],
            "circular_scope": self.circular_scope,
            "independence_unit": self.independence_unit,
        }
        if canonical_json_sha256(segment_body) != self.physical_segment_set_sha256:
            raise ValueError("canonical physical-segment identity is corrupt")
        body = self.model_dump(mode="json", exclude={"binding_sha256"})
        if canonical_json_sha256(body) != self.binding_sha256:
            raise ValueError("canonical P32 opportunity binding is corrupt")
        return self


class CurrentKnowledgeHypothesis(EngineeringKnowledgeModel):
    bridge_id: str = Field(pattern=r"^p351b_[0-9a-f]{24}$")
    effect_id: str = Field(pattern=_ID)
    setup_area: str = Field(pattern=_ID)
    physical_role: str = Field(min_length=1)
    direction_sign: Literal[-1, 0, 1]
    experiment_factor_id: str | None = Field(default=None, pattern=_ID)
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
    possible_component_family_ids: tuple[str, ...] = ()
    p26_component_family_ids: tuple[str, ...] = ()
    current_candidate_component_ids: tuple[str, ...] = ()
    current_supported_component_ids: tuple[str, ...] = ()
    contradicted_component_ids: tuple[str, ...] = ()
    blocked_component_ids: tuple[str, ...] = ()
    unobservable_component_ids: tuple[str, ...] = ()
    irrelevant_component_ids: tuple[str, ...] = ()
    response_regimes: tuple[Literal["transient", "steady_state", "both"], ...] = ()
    relevant_phases: tuple[str, ...] = ()
    expected_vehicle_response_ids: tuple[str, ...] = ()
    expected_vehicle_state_ids: tuple[str, ...] = ()
    validation_metric_ids: tuple[str, ...] = ()
    countereffect_ids: tuple[str, ...] = ()
    countereffect_state_ids: tuple[str, ...] = ()
    protected_outcomes: tuple[str, ...] = ()
    protected_performance_outcome_ids: tuple[str, ...] = ()
    rollback_condition_ids: tuple[str, ...] = ()
    inspection_tool_ids: tuple[str, ...] = ()
    support_artifact_ids: tuple[str, ...] = ()
    contradiction_artifact_ids: tuple[str, ...] = ()
    discriminator_contract_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    controlled_history: tuple[ControlledKnowledgeHistory, ...] = ()
    knowledge_applicability: Literal[
        "applicable", "educational_only", "blocked_by_build", "unsupported"
    ]
    runtime_evidence_state: Literal[
        "unavailable",
        "measured",
        "calculated",
        "estimated_proxy",
        "observed_correlation",
        "controlled_test_effect",
        "blocked_by_context",
    ]
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
            self.possible_component_family_ids,
            self.p26_component_family_ids,
            self.current_candidate_component_ids,
            self.current_supported_component_ids,
            self.contradicted_component_ids,
            self.blocked_component_ids,
            self.unobservable_component_ids,
            self.irrelevant_component_ids,
            self.response_regimes,
            self.relevant_phases,
            self.expected_vehicle_response_ids,
            self.expected_vehicle_state_ids,
            self.validation_metric_ids,
            self.countereffect_ids,
            self.countereffect_state_ids,
            self.protected_outcomes,
            self.protected_performance_outcome_ids,
            self.rollback_condition_ids,
            self.inspection_tool_ids,
            self.support_artifact_ids,
            self.contradiction_artifact_ids,
            self.discriminator_contract_ids,
            self.missing_evidence,
        )
        if any(len(values) != len(set(values)) for values in sequences):
            raise ValueError("current P35.1 hypothesis relations must be unique")
        component_partitions = (
            set(self.current_candidate_component_ids),
            set(self.current_supported_component_ids),
            set(self.contradicted_component_ids),
            set(self.blocked_component_ids),
            set(self.unobservable_component_ids),
            set(self.irrelevant_component_ids),
        )
        if any(left & right for index, left in enumerate(component_partitions) for right in component_partitions[index + 1 :]):
            raise ValueError("current P26 component truth partitions cannot overlap")
        current_relevant = tuple(
            dict.fromkeys(
                (*self.current_candidate_component_ids, *self.current_supported_component_ids)
            )
        )
        if self.p26_component_family_ids != current_relevant:
            raise ValueError("legacy P26 component field must equal current candidate/support truth")
        if not set().union(*component_partitions) <= set(self.possible_component_family_ids):
            raise ValueError("current P26 component truth must remain inside the static possibility map")
        if self.level == "p19_testable_control":
            if (
                self.p19_control is None
                or self.authority != "exact_p19_projection"
                or not self.setup_authorized
                or self.relevance
                not in {"supported_candidate", "blocked_candidate"}
            ):
                raise ValueError("level-three knowledge must exactly mirror P19")
            if (
                self.p19_control.effect_id != self.effect_id
                or self.p19_control.direction_sign != self.direction_sign
                or self.p19_control.experiment_factor_id != self.experiment_factor_id
            ):
                raise ValueError("level-three semantics must equal the exact bridge identity")
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
    schema_version: Literal["p352.current-engineering-knowledge.v1"] = (
        "p352.current-engineering-knowledge.v1"
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
    "CanonicalPhysicalSegment",
    "CanonicalPerformanceOpportunityBinding",
    "CurrentEngineeringKnowledgeProjection",
    "CurrentKnowledgeHypothesis",
    "EngineeringKnowledgeCoverageReport",
    "KnowledgeLevel",
    "MechanismSetupBridge",
    "P19TestableControl",
]
