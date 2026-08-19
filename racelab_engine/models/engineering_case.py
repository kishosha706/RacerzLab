"""P35.4.3 atomic engineering-case and closed-loop response contracts.

These receipts connect existing producer truth.  They do not rank causes,
authorize setup, or replace P19, P33, P34, or P36 ownership.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.vehicle_dynamics_knowledge import (
    OperationalResponseEvidence,
)


_SHA = r"^[0-9a-f]{64}$"
_ID = r"^[a-z0-9][a-z0-9_.:-]*$"


class EngineeringCaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EngineeringResponseArtifact(EngineeringCaseModel):
    """Globally addressable envelope for one P35.4 response observation."""

    artifact_type: Literal["engineering_response"] = "engineering_response"
    artifact_id: str = Field(pattern=r"^p3542\.response:[0-9a-f]{24}$")
    artifact_sha256: str = Field(pattern=_SHA)
    case_id: str = Field(pattern=r"^p3543case_[0-9a-f]{24}$")
    case_revision_sha256: str = Field(pattern=_SHA)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    source_recording_sha256: str = Field(pattern=_SHA)
    source_producer_id: str = Field(pattern=_ID)
    relation: str = Field(pattern=_ID)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    phase: str = Field(min_length=1)
    canonical_clock_contract: Literal["qualified_session_tick"] = (
        "qualified_session_tick"
    )
    source_lap_numbers: tuple[int, ...] = Field(min_length=2)
    reference_lap_numbers: tuple[int, ...] = ()
    independence_unit_ids: tuple[str, ...] = Field(min_length=2)
    operational_evidence: OperationalResponseEvidence
    applicability: Literal["exact_current_case"] = "exact_current_case"
    blocker_reasons: tuple[str, ...] = ()
    authority_ceiling: Literal["observation_only"] = "observation_only"
    p19_support_authorized: Literal[False] = False
    component_support_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("artifact_sha256", None)
        body.setdefault("artifact_type", "engineering_response")
        normalized = cls.model_construct(
            **body, artifact_sha256="0" * 64
        ).model_dump(mode="json")
        normalized.pop("artifact_sha256", None)
        return cls.model_validate(
            {**normalized, "artifact_sha256": canonical_json_sha256(normalized)}
        )

    @model_validator(mode="after")
    def response_artifact_is_exact(self) -> Self:
        evidence = self.operational_evidence
        if (
            self.artifact_id != evidence.evidence_id
            or self.relation != evidence.relation
            or self.lap_pct_start != evidence.lap_pct_start
            or self.lap_pct_end != evidence.lap_pct_end
            or self.phase != evidence.phase
            or self.source_lap_numbers != evidence.source_lap_numbers
        ):
            raise ValueError("response artifact must exactly mirror producer evidence")
        if self.lap_pct_end < self.lap_pct_start:
            raise ValueError("response artifact physical scope is reversed")
        for values in (
            self.source_lap_numbers,
            self.reference_lap_numbers,
            self.independence_unit_ids,
            self.blocker_reasons,
        ):
            if len(values) != len(set(values)):
                raise ValueError("response artifact identities must be unique")
        if set(self.source_lap_numbers) & set(self.reference_lap_numbers):
            raise ValueError("response source and reference laps must be distinct")
        if len(self.independence_unit_ids) != evidence.repetition_count:
            raise ValueError("response independence units must equal repetition count")
        body = self.model_dump(mode="json", exclude={"artifact_sha256"})
        if canonical_json_sha256(body) != self.artifact_sha256:
            raise ValueError("response artifact content identity is corrupt")
        return self


class P19ResponseCauseAssessment(EngineeringCaseModel):
    cause_id: str = Field(min_length=1)
    matched_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    result: Literal[
        "supports_existing_contract",
        "contradicts_existing_contract",
        "unresolved",
        "blocked",
    ]
    basis: str = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()
    rank_modified: Literal[False] = False
    setup_authorized: Literal[False] = False


class P19ResponseAdmission(EngineeringCaseModel):
    """P19-owned interpretation receipt; never a replacement reasoning snapshot."""

    admission_id: str = Field(pattern=r"^p19response_[0-9a-f]{24}$")
    admission_sha256: str = Field(pattern=_SHA)
    case_id: str = Field(pattern=r"^p3543case_[0-9a-f]{24}$")
    case_revision_sha256: str = Field(pattern=_SHA)
    response_artifact_id: str = Field(pattern=r"^p3542\.response:[0-9a-f]{24}$")
    p19_reasoning_snapshot_sha256: str = Field(pattern=_SHA)
    assessments: tuple[P19ResponseCauseAssessment, ...] = ()
    state: Literal["admitted", "unresolved", "blocked"]
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["p19_response_adapter_only"] = "p19_response_adapter_only"
    reasoning_rank_modified: Literal[False] = False
    terminal_action_modified: Literal[False] = False
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("admission_id", None)
        body.pop("admission_sha256", None)
        provisional = cls.model_construct(
            **body,
            admission_id="p19response_" + ("0" * 24),
            admission_sha256="0" * 64,
        )
        normalized = provisional.model_dump(mode="json")
        normalized.pop("admission_id", None)
        normalized.pop("admission_sha256", None)
        digest = canonical_json_sha256(normalized)
        return cls.model_validate(
            {
                **normalized,
                "admission_id": f"p19response_{digest[:24]}",
                "admission_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def admission_is_non_mutating(self) -> Self:
        cause_ids = tuple(item.cause_id for item in self.assessments)
        if len(cause_ids) != len(set(cause_ids)):
            raise ValueError("P19 response admission cause identities must be unique")
        if self.state == "admitted" and (
            not self.assessments
            or self.blocker_reasons
            or not any(
                item.result
                in {"supports_existing_contract", "contradicts_existing_contract"}
                for item in self.assessments
            )
        ):
            raise ValueError("admitted response evidence requires a contract result")
        if self.state == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked P19 response admission requires blockers")
        if self.state == "unresolved" and (
            self.blocker_reasons
            or any(item.result != "unresolved" for item in self.assessments)
        ):
            raise ValueError("unresolved response admission cannot hide a result")
        body = self.model_dump(
            mode="json", exclude={"admission_id", "admission_sha256"}
        )
        expected = canonical_json_sha256(body)
        if self.admission_sha256 != expected or self.admission_id != (
            f"p19response_{expected[:24]}"
        ):
            raise ValueError("P19 response admission identity is corrupt")
        return self


class ControlledStageResponseReceipt(EngineeringCaseModel):
    stage: Literal["A", "B", "A2"]
    run_id: str = Field(min_length=1)
    source_recording_sha256: str = Field(pattern=_SHA)
    setup_snapshot_sha256: str = Field(pattern=_SHA)
    response_artifact_ids: tuple[str, ...] = ()
    source_channels: tuple[str, ...] = ()
    eligible_lap_numbers: tuple[int, ...] = Field(min_length=3)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    speed_min_mps: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    speed_max_mps: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def stage_scope_is_exact(self) -> Self:
        if self.lap_pct_end <= self.lap_pct_start:
            raise ValueError("controlled response scope must be non-zero and ordered")
        if len(self.eligible_lap_numbers) != len(set(self.eligible_lap_numbers)):
            raise ValueError("controlled response laps must be unique")
        if len(self.response_artifact_ids) != len(set(self.response_artifact_ids)):
            raise ValueError("controlled response artifact identities must be unique")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("controlled response source channels must be unique")
        if (self.speed_min_mps is None) != (self.speed_max_mps is None):
            raise ValueError("controlled response speed band must be complete")
        if (
            self.speed_min_mps is not None
            and self.speed_max_mps is not None
            and self.speed_max_mps < self.speed_min_mps
        ):
            raise ValueError("controlled response speed band is reversed")
        return self


class ControlledResponseMetricDelta(EngineeringCaseModel):
    metric_id: str = Field(pattern=r"^p3543metric_[0-9a-f]{24}$")
    relation: str = Field(pattern=_ID)
    label: str = Field(min_length=1)
    units: str = Field(min_length=1)
    corner: Literal["lf", "rf", "lr", "rr"] | None = None
    stage_a_value: float = Field(allow_inf_nan=False)
    stage_b_value: float = Field(allow_inf_nan=False)
    stage_a2_value: float = Field(allow_inf_nan=False)
    baseline_repeat_delta: float = Field(ge=0.0, allow_inf_nan=False)
    observed_b_delta: float = Field(allow_inf_nan=False)
    source_artifact_ids: tuple[str, ...] = Field(min_length=3)
    evidence_state: Literal["controlled_test_effect"] = "controlled_test_effect"


class ControlledResponseReceipt(EngineeringCaseModel):
    """P19-owned separation of response, performance, and policy truth."""

    receipt_id: str = Field(pattern=r"^p3543receipt_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=_SHA)
    workflow_id: str = Field(min_length=1)
    control_key: str = Field(pattern=_ID)
    setup_effect_id: str = Field(pattern=_ID)
    experiment_factor_id: str = Field(pattern=_ID)
    direction_sign: Literal[-1, 1]
    stages: tuple[ControlledStageResponseReceipt, ...] = Field(
        min_length=3, max_length=3
    )
    expected_response_relation_ids: tuple[str, ...] = Field(min_length=1)
    observed_metric_deltas: tuple[ControlledResponseMetricDelta, ...] = ()
    performance_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    time_origin_phase: str | None = None
    time_origin_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    downstream_carry_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    countereffects: tuple[str, ...] = ()
    mechanism_assessment: Literal["inconclusive", "invalid"]
    control_response_assessment: Literal[
        "matched", "missed", "inconclusive", "unavailable", "invalid"
    ]
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    state: Literal["ready", "blocked"]
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["p19_controlled_response_receipt"] = (
        "p19_controlled_response_receipt"
    )
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("receipt_id", None)
        body.pop("receipt_sha256", None)
        draft = cls.model_construct(
            **body,
            receipt_id="p3543receipt_" + ("0" * 24),
            receipt_sha256="0" * 64,
        )
        normalized = draft.model_dump(mode="json")
        normalized.pop("receipt_id", None)
        normalized.pop("receipt_sha256", None)
        digest = canonical_json_sha256(normalized)
        return cls.model_validate(
            {
                **normalized,
                "receipt_id": f"p3543receipt_{digest[:24]}",
                "receipt_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def aba2_response_is_comparable(self) -> Self:
        if tuple(item.stage for item in self.stages) != ("A", "B", "A2"):
            raise ValueError("controlled response receipt requires ordered A/B/A2")
        run_ids = tuple(item.run_id for item in self.stages)
        recordings = tuple(item.source_recording_sha256 for item in self.stages)
        if len(set(run_ids)) != 3 or len(set(recordings)) != 3:
            raise ValueError("A/B/A2 response stages require distinct recordings")
        if (
            self.stages[0].setup_snapshot_sha256
            != self.stages[2].setup_snapshot_sha256
            or self.stages[1].setup_snapshot_sha256
            == self.stages[0].setup_snapshot_sha256
        ):
            raise ValueError("A/A2 must restore baseline and B must retain one change")
        scopes = {
            (item.phase, item.lap_pct_start, item.lap_pct_end)
            for item in self.stages
        }
        if len(scopes) != 1:
            raise ValueError("A/B/A2 response stages require one physical scope")
        speed_bands = tuple(
            (item.speed_min_mps, item.speed_max_mps)
            for item in self.stages
            if item.speed_min_mps is not None and item.speed_max_mps is not None
        )
        if speed_bands and (
            len(speed_bands) != 3
            or max(item[0] for item in speed_bands)
            > min(item[1] for item in speed_bands)
        ):
            raise ValueError("A/B/A2 response speed bands must overlap")
        all_artifacts = tuple(
            artifact_id
            for stage in self.stages
            for artifact_id in stage.response_artifact_ids
        )
        if len(all_artifacts) != len(set(all_artifacts)):
            raise ValueError("one physical response artifact cannot count twice")
        if self.state == "ready" and (
            self.blocker_reasons or not self.observed_metric_deltas
        ):
            raise ValueError("ready controlled response requires metric deltas")
        if self.state == "blocked" and (
            not self.blocker_reasons or self.observed_metric_deltas
        ):
            raise ValueError("blocked controlled response requires blockers only")
        if (self.time_origin_phase is None) != (self.time_origin_pct is None):
            raise ValueError("controlled response time origin must be paired")
        if self.policy_verdict == "invalid" and self.state != "blocked":
            raise ValueError("invalid policy cannot publish a ready response receipt")
        body = self.model_dump(mode="json", exclude={"receipt_id", "receipt_sha256"})
        expected = canonical_json_sha256(body)
        if self.receipt_sha256 != expected or self.receipt_id != (
            f"p3543receipt_{expected[:24]}"
        ):
            raise ValueError("controlled response receipt identity is corrupt")
        return self


EffectReadinessState = Literal[
    "knowledge_only",
    "measurement_ready",
    "response_evidence_ready",
    "p19_testable",
    "blocked",
]


class SetupEffectReadiness(EngineeringCaseModel):
    effect_id: str = Field(pattern=_ID)
    bridge_id: str = Field(pattern=r"^p351b_[0-9a-f]{24}$")
    state: EffectReadinessState
    response_artifact_ids: tuple[str, ...] = ()
    expected_response_relation_ids: tuple[str, ...] = ()
    exact_control_keys: tuple[str, ...] = ()
    experiment_factor_id: str | None = Field(default=None, pattern=_ID)
    countereffect_measurement_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    authority: Literal[
        "knowledge_only", "measurement_only", "exact_p19_projection"
    ]
    setup_authorized: bool = False

    @model_validator(mode="after")
    def readiness_cannot_create_action(self) -> Self:
        if self.state == "p19_testable":
            if self.authority != "exact_p19_projection" or not self.setup_authorized:
                raise ValueError("P19-testable readiness must mirror exact P19")
        elif self.setup_authorized or self.authority == "exact_p19_projection":
            raise ValueError("non-P19 readiness cannot authorize setup")
        if self.state == "response_evidence_ready" and not self.response_artifact_ids:
            raise ValueError("response-ready effects require exact response artifacts")
        if self.state == "blocked" and not self.missing_evidence:
            raise ValueError("blocked effect readiness requires missing evidence")
        return self


class CapabilityEvidenceResolution(EngineeringCaseModel):
    resolution_id: str = Field(pattern=r"^p3543cap_[0-9a-f]{24}$")
    missing_evidence: str = Field(min_length=1)
    required_channel_ids: tuple[str, ...] = ()
    status: Literal[
        "available_now", "requires_new_run", "pit_snapshot_only", "structurally_unavailable"
    ]
    recovery: str = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = ()
    authority: Literal["measurement_routing_only"] = "measurement_routing_only"
    setup_authorized: Literal[False] = False


class CaseQuantityObservability(EngineeringCaseModel):
    quantity_id: str = Field(pattern=_ID)
    component_family_ids: tuple[str, ...] = Field(min_length=1)
    response_artifact_ids: tuple[str, ...] = Field(min_length=1)
    state: Literal["currently_observable"] = "currently_observable"
    authority: Literal["quantity_observation_only"] = "quantity_observation_only"
    component_support_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False


class EngineeringSemanticFocusState(EngineeringCaseModel):
    case_id: str = Field(pattern=r"^p3543case_[0-9a-f]{24}$")
    case_revision_sha256: str = Field(pattern=_SHA)
    artifact_id: str | None = Field(default=None, pattern=_ID)
    lap_numbers: tuple[int, ...] = ()
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)
    phase: str | None = None
    mechanism_ids: tuple[str, ...] = ()
    response_relation_id: str | None = Field(default=None, pattern=_ID)
    component_ids: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()
    control_keys: tuple[str, ...] = ()
    p19_cause_ids: tuple[str, ...] = ()
    authority: Literal["navigation_only"] = "navigation_only"

    @model_validator(mode="after")
    def focus_scope_is_complete(self) -> Self:
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("semantic focus physical scope must be complete")
        return self


class EngineeringCaseCampaignCapture(EngineeringCaseModel):
    state: Literal["pending", "rejected", "qualified", "duplicate", "corrupt"]
    blocker_reasons: tuple[str, ...] = ()
    historical_count_credited: Literal[False] = False
    null_count_credited: Literal[False] = False
    negative_control_count_credited: Literal[False] = False
    subgroup_count_credited: Literal[False] = False
    authority: Literal["qualification_only"] = "qualification_only"


class CanonicalEngineeringCase(EngineeringCaseModel):
    schema_version: Literal["p3543.canonical-engineering-case.v1"] = (
        "p3543.canonical-engineering-case.v1"
    )
    case_id: str = Field(pattern=r"^p3543case_[0-9a-f]{24}$")
    case_sha256: str = Field(pattern=_SHA)
    case_revision_sha256: str = Field(pattern=_SHA)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    recording_sha256: str = Field(pattern=_SHA)
    setup_id: str = Field(min_length=1)
    setup_snapshot_sha256: str = Field(pattern=_SHA)
    objective_id: str = Field(min_length=1)
    condition_epoch_sha256: str = Field(pattern=_SHA)
    p19_reasoning_snapshot_sha256: str = Field(pattern=_SHA)
    p20_state_revision: str = Field(pattern=_SHA)
    p26_knowledge_graph_sha256: str = Field(pattern=_SHA)
    p32_projection_sha256: str = Field(pattern=_SHA)
    p35_assessment_sha256: str = Field(pattern=_SHA)
    p351_projection_sha256: str = Field(pattern=_SHA)
    p33_projection_sha256: str = Field(pattern=_SHA)
    evidence_index_sha256: str = Field(pattern=_SHA)
    primary_opportunity_id: str | None = None
    response_artifacts: tuple[EngineeringResponseArtifact, ...] = ()
    p19_response_admissions: tuple[P19ResponseAdmission, ...] = ()
    mechanism_ids: tuple[str, ...] = ()
    component_ids: tuple[str, ...] = ()
    effect_readiness: tuple[SetupEffectReadiness, ...] = Field(min_length=1)
    active_discriminator_id: str | None = Field(default=None, pattern=_ID)
    investigation_id: str | None = None
    workspace_revision: str = Field(pattern=_SHA)
    terminal_move_sha256: str = Field(pattern=_SHA)
    capability_resolutions: tuple[CapabilityEvidenceResolution, ...] = ()
    quantity_observability: tuple[CaseQuantityObservability, ...] = ()
    semantic_focus: EngineeringSemanticFocusState
    campaign_capture: EngineeringCaseCampaignCapture
    authority: Literal["case_receipt_only"] = "case_receipt_only"
    p19_authority_unchanged: Literal[True] = True
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("case_id", None)
        body.pop("case_sha256", None)
        draft = cls.model_construct(
            **body,
            case_id="p3543case_" + ("0" * 24),
            case_sha256="0" * 64,
        )
        normalized = draft.model_dump(mode="json")
        normalized.pop("case_id", None)
        normalized.pop("case_sha256", None)
        digest = canonical_json_sha256(normalized)
        expected_case_id = f"p3543case_{values['case_revision_sha256'][:24]}"
        return cls.model_validate(
            {**normalized, "case_id": expected_case_id, "case_sha256": digest}
        )

    @model_validator(mode="after")
    def case_is_atomic(self) -> Self:
        if self.case_id != f"p3543case_{self.case_revision_sha256[:24]}":
            raise ValueError("engineering case ID must bind its atomic revision")
        artifact_ids = tuple(item.artifact_id for item in self.response_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("engineering case response artifacts must be unique")
        if any(
            item.case_id != self.case_id
            or item.case_revision_sha256 != self.case_revision_sha256
            or item.run_id != self.run_id
            or item.session_id != self.session_id
            or item.setup_id != self.setup_id
            or item.source_recording_sha256 != self.recording_sha256
            for item in self.response_artifacts
        ):
            raise ValueError("engineering response artifact belongs to another case")
        if any(
            item.case_id != self.case_id
            or item.case_revision_sha256 != self.case_revision_sha256
            or item.response_artifact_id not in artifact_ids
            or item.p19_reasoning_snapshot_sha256
            != self.p19_reasoning_snapshot_sha256
            for item in self.p19_response_admissions
        ):
            raise ValueError("P19 response admission belongs to another case")
        admission_response_ids = tuple(
            item.response_artifact_id for item in self.p19_response_admissions
        )
        if (
            len(admission_response_ids) != len(set(admission_response_ids))
            or set(admission_response_ids) != set(artifact_ids)
        ):
            raise ValueError(
                "every response artifact requires exactly one P19-owned admission"
            )
        if (
            self.semantic_focus.case_id != self.case_id
            or self.semantic_focus.case_revision_sha256
            != self.case_revision_sha256
            or (
                self.semantic_focus.artifact_id is not None
                and self.semantic_focus.artifact_id not in artifact_ids
            )
        ):
            raise ValueError("semantic focus must belong to the current case")
        effect_ids = tuple(item.effect_id for item in self.effect_readiness)
        if len(effect_ids) != len(set(effect_ids)):
            raise ValueError("engineering case must project each setup effect once")
        quantity_ids = tuple(item.quantity_id for item in self.quantity_observability)
        if len(quantity_ids) != len(set(quantity_ids)) or any(
            not set(item.response_artifact_ids) <= set(artifact_ids)
            for item in self.quantity_observability
        ):
            raise ValueError(
                "case quantity observability must resolve through response artifacts"
            )
        body = self.model_dump(mode="json", exclude={"case_id", "case_sha256"})
        if canonical_json_sha256(body) != self.case_sha256:
            raise ValueError("engineering case content identity is corrupt")
        return self


__all__ = [name for name in globals() if not name.startswith("_")]
