"""Typed, non-authoritative contracts for the P27-P33 Crew Chief executive.

The executive may decide what to inspect, ask, or measure.  Exact setup and
policy authority remains structurally owned by the canonical P19 snapshot;
P33 history may influence attention order only.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.engineering_projection import EngineeringAwarenessProjection
from racelab_engine.models.engineering_knowledge import (
    CurrentEngineeringKnowledgeProjection,
)
from racelab_engine.models.investigation_adaptation import (
    InvestigationImprovementProjection,
)
from racelab_engine.models.engineering_learning import (
    CrewChiefLearningPrior,
    P19ReasoningMemory,
    ProblemFingerprint,
)
from racelab_engine.models.experiment import MeasurementMissionContract
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.models.performance_intelligence import (
    ComponentPerformanceInfluence,
    CornerPerformanceChain,
    DriverVehicleSeparation,
    LapTimeOpportunity,
    PerformanceIntelligenceProjection,
    PerformanceObjectiveEnvelope,
    PerformancePhaseState,
    TrackDemandProfile,
)
from racelab_engine.models.vehicle_dynamics_knowledge import (
    PerformanceMechanismAssessment,
    VehicleDynamicsFocusArtifact,
)
from racelab_engine.models.vehicle_systems import VehicleSystemsRuntimeIdentity


class CrewChiefModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


_P20_DELIVERY_ONLY_FIELDS = {
    "generated_at",
    "cache_state",
    "build_duration_ms",
}


def engineering_awareness_scientific_sha256(
    projection: EngineeringAwarenessProjection,
) -> str:
    """Hash the complete P20 scientific projection, excluding delivery metadata."""

    payload = projection.model_dump(
        mode="json",
        exclude=_P20_DELIVERY_ONLY_FIELDS,
    )
    for mutation in payload["control_mutations"]:
        for field_name in ("previous_value", "new_value"):
            value = mutation[field_name]
            if not isinstance(value, bool) and isinstance(value, (int, float)):
                mutation[field_name] = float(value)
    return canonical_json_sha256(payload)


class EngineeringObjective(str, Enum):
    QUALIFYING_PEAK = "qualifying_peak"
    RACE_LONG_RUN = "race_long_run"
    TIRE_CONSERVATION = "tire_conservation"
    DRIVER_CONFIDENCE = "driver_confidence"
    TRAFFIC_ROBUSTNESS = "traffic_robustness"
    SUPERSPEEDWAY_STABILITY = "superspeedway_stability"
    FUEL_STRATEGY = "fuel_strategy"


PerformanceArtifactType = Literal[
    "lap_time_opportunity",
    "time_loss_origin",
    "corner_performance_chain",
    "exit_carry",
    "path_efficiency",
    "driver_vehicle_separation",
    "track_demand",
    "component_performance_link",
    "objective_envelope",
]

_P34_PERFORMANCE_MEASUREMENT_ORDER = (
    "inspect_lap_time_opportunity",
    "inspect_time_loss_origin",
    "inspect_corner_performance_chain",
    "inspect_exit_carry",
    "inspect_path_efficiency",
    "inspect_driver_vehicle_separation",
    "inspect_track_demand",
)


class CrewChiefLapTimeOpportunityArtifact(CrewChiefModel):
    artifact_type: Literal["lap_time_opportunity"] = "lap_time_opportunity"
    opportunity: LapTimeOpportunity


class CrewChiefTimeLossOriginArtifact(CrewChiefModel):
    artifact_type: Literal["time_loss_origin"] = "time_loss_origin"
    opportunity: LapTimeOpportunity


class CrewChiefCornerPerformanceChainArtifact(CrewChiefModel):
    artifact_type: Literal["corner_performance_chain"] = "corner_performance_chain"
    start_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    end_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    chain: CornerPerformanceChain

    @model_validator(mode="after")
    def physical_window_is_ordered(self) -> CrewChiefCornerPerformanceChainArtifact:
        if self.end_pct < self.start_pct:
            raise ValueError("corner-chain artifact physical window is reversed")
        return self


class CrewChiefExitCarryArtifact(CrewChiefModel):
    artifact_type: Literal["exit_carry"] = "exit_carry"
    opportunity: LapTimeOpportunity

    @model_validator(mode="after")
    def exact_following_scope_is_materialized(self) -> CrewChiefExitCarryArtifact:
        if (
            self.opportunity.following_phase_effect_s is None
            or self.opportunity.following_phase_start_pct is None
            or self.opportunity.following_phase_end_pct is None
        ):
            raise ValueError(
                "exit-carry artifacts require a measured effect and exact following-phase window"
            )
        return self


class CrewChiefPathEfficiencyArtifact(CrewChiefModel):
    artifact_type: Literal["path_efficiency"] = "path_efficiency"
    chain_id: str = Field(min_length=1)
    phase_state: PerformancePhaseState

    @model_validator(mode="after")
    def measured_path_is_materialized(self) -> CrewChiefPathEfficiencyArtifact:
        if self.phase_state.path_delta_m is None:
            raise ValueError("path-efficiency artifacts require a measured path delta")
        return self


class CrewChiefDriverVehicleSeparationArtifact(CrewChiefModel):
    artifact_type: Literal["driver_vehicle_separation"] = "driver_vehicle_separation"
    chain_id: str = Field(min_length=1)
    track_region: str = Field(min_length=1)
    start_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    end_pct: float = Field(ge=0, le=100, allow_inf_nan=False)
    separation: DriverVehicleSeparation

    @model_validator(mode="after")
    def physical_window_is_ordered(self) -> CrewChiefDriverVehicleSeparationArtifact:
        if self.end_pct < self.start_pct:
            raise ValueError("driver/vehicle artifact physical window is reversed")
        return self


class CrewChiefTrackDemandArtifact(CrewChiefModel):
    artifact_type: Literal["track_demand"] = "track_demand"
    profile: TrackDemandProfile


class CrewChiefComponentPerformanceLinkArtifact(CrewChiefModel):
    artifact_type: Literal["component_performance_link"] = "component_performance_link"
    influence: ComponentPerformanceInfluence


class CrewChiefObjectiveEnvelopeArtifact(CrewChiefModel):
    artifact_type: Literal["objective_envelope"] = "objective_envelope"
    envelope: PerformanceObjectiveEnvelope


class CrewChiefUnavailablePerformanceArtifact(CrewChiefModel):
    artifact_type: Literal["unavailable"] = "unavailable"
    claimed_artifact_type: PerformanceArtifactType
    blocker_reasons: tuple[str, ...] = Field(min_length=1)


CrewChiefPerformanceArtifact = Annotated[
    CrewChiefLapTimeOpportunityArtifact
    | CrewChiefTimeLossOriginArtifact
    | CrewChiefCornerPerformanceChainArtifact
    | CrewChiefExitCarryArtifact
    | CrewChiefPathEfficiencyArtifact
    | CrewChiefDriverVehicleSeparationArtifact
    | CrewChiefTrackDemandArtifact
    | CrewChiefComponentPerformanceLinkArtifact
    | CrewChiefObjectiveEnvelopeArtifact
    | CrewChiefUnavailablePerformanceArtifact,
    Field(discriminator="artifact_type"),
]


VehicleDynamicsInspectionToolId = Literal[
    "inspect_tire_demand",
    "inspect_load_transfer",
    "inspect_roll_response",
    "inspect_pitch_response",
    "inspect_platform_state",
    "inspect_transient_settling",
    "inspect_steady_state_balance",
    "inspect_brake_vehicle_response",
    "inspect_power_on_response",
    "inspect_differential_response",
    "inspect_alignment_response",
    "inspect_tire_state_migration",
    "inspect_traffic_platform_response",
    "inspect_gear_acceleration_response",
]
_P35_INSPECTION_TOOL_IDS = (
    "inspect_tire_demand",
    "inspect_load_transfer",
    "inspect_roll_response",
    "inspect_pitch_response",
    "inspect_platform_state",
    "inspect_transient_settling",
    "inspect_steady_state_balance",
    "inspect_brake_vehicle_response",
    "inspect_power_on_response",
    "inspect_differential_response",
    "inspect_alignment_response",
    "inspect_tire_state_migration",
    "inspect_traffic_platform_response",
    "inspect_gear_acceleration_response",
)
_P351_INSPECTION_TOOL_IDS = (
    "inspect_setup_knowledge_for_mechanism",
    "inspect_control_experiment_contract",
)
_P34_EXCLUDED_INSPECTION_TOOL_IDS = (
    *_P35_INSPECTION_TOOL_IDS,
    *_P351_INSPECTION_TOOL_IDS,
)


class CrewChiefVehicleDynamicsFocusArtifact(CrewChiefModel):
    """One P35 focus target, bound to its complete runtime assessment."""

    artifact_type: Literal["vehicle_dynamics_focus"] = "vehicle_dynamics_focus"
    inspection_tool_id: VehicleDynamicsInspectionToolId
    assessment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    focus: VehicleDynamicsFocusArtifact

    @model_validator(mode="after")
    def focus_tool_is_exact(self) -> CrewChiefVehicleDynamicsFocusArtifact:
        if self.focus.inspection_tool_id.value != self.inspection_tool_id:
            raise ValueError(
                "P35 focus envelope must preserve the producer-owned inspection tool"
            )
        return self


CrewChiefEvidenceArtifact = Annotated[
    CrewChiefLapTimeOpportunityArtifact
    | CrewChiefTimeLossOriginArtifact
    | CrewChiefCornerPerformanceChainArtifact
    | CrewChiefExitCarryArtifact
    | CrewChiefPathEfficiencyArtifact
    | CrewChiefDriverVehicleSeparationArtifact
    | CrewChiefTrackDemandArtifact
    | CrewChiefComponentPerformanceLinkArtifact
    | CrewChiefObjectiveEnvelopeArtifact
    | CrewChiefUnavailablePerformanceArtifact
    | CrewChiefVehicleDynamicsFocusArtifact,
    Field(discriminator="artifact_type"),
]


class InvestigationProgress(str, Enum):
    NOT_INSPECTED = "not_inspected"
    INSPECTION_REQUESTED = "inspection_requested"
    INSPECTED_NO_EVIDENCE = "inspected_no_evidence"
    SUPPORT_FOUND = "support_found"
    CONTRADICTION_FOUND = "contradiction_found"
    DISCRIMINATOR_PENDING = "discriminator_pending"
    UNRESOLVED_AFTER_INSPECTION = "unresolved_after_inspection"
    P19_RULED_OUT = "p19_ruled_out"
    NEEDS_DRIVER_ANSWER = "needs_driver_answer"
    NEEDS_MEASUREMENT = "needs_measurement"
    STALE = "stale"


InspectionFindingKind = Literal[
    "support",
    "contradiction",
    "discriminator",
    "negative_control",
    "no_signal",
    "unavailable",
]


class DriverAnswerInterpretation(CrewChiefModel):
    answer: str = Field(min_length=1)
    phase_scope: tuple[str, ...] = ()
    response_regime_scope: tuple[Literal["transient", "steady_state"], ...] = ()
    traffic_scope: Literal[
        "all", "disturbed_air", "clean_air", "compare_air_states"
    ] = "all"
    stint_scope: Literal["all", "immediate", "migration"] = "all"
    power_state_scope: Literal[
        "all", "brake_applied", "brake_release", "pre_power", "power_on"
    ] = "all"
    time_origin_scope: Literal[
        "all", "local", "exit_carry", "following_straight"
    ] = "all"
    driver_demand_scope: tuple[str, ...] = ()
    context_record_only: bool = False

    @model_validator(mode="after")
    def every_answer_has_one_semantic_consequence(self) -> DriverAnswerInterpretation:
        changed_scope = bool(
            self.phase_scope
            or self.response_regime_scope
            or self.traffic_scope != "all"
            or self.stint_scope != "all"
            or self.power_state_scope != "all"
            or self.time_origin_scope != "all"
            or self.driver_demand_scope
        )
        if changed_scope == self.context_record_only:
            raise ValueError(
                "driver answers must either change typed investigation scope or be explicitly context-only"
            )
        return self


class CrewChiefWorkspaceIdentity(CrewChiefModel):
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    selected_scope_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p20_state_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    p20_profile_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    p20_projection_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    p26_graph_version: str = Field(min_length=1)
    p26_knowledge_graph_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p26_reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p32_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Optional only so pre-P35 persisted investigation identities remain
    # readable. Every current public Crew workspace requires an exact value in
    # projection_scope_is_atomic.
    p35_assessment_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    run_sentinel_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    learning_history_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    learning_ledger_head_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    learning_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    setup_id: str = Field(min_length=1)
    setup_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    vehicle_runtime_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    vehicle_runtime_identity: VehicleSystemsRuntimeIdentity | None = None
    active_workflow_id: str | None = None
    active_workflow_revision: str | None = None
    objective_id: EngineeringObjective
    investigation_id: str | None = None
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def workflow_identity_is_complete(self) -> CrewChiefWorkspaceIdentity:
        if (self.active_workflow_id is None) != (self.active_workflow_revision is None):
            raise ValueError("workflow identity and revision must be present together")
        if (
            self.vehicle_runtime_identity is not None
            and canonical_json_sha256(self.vehicle_runtime_identity)
            != self.vehicle_runtime_identity_hash
        ):
            raise ValueError(
                "vehicle runtime identity hash must bind the complete producer payload"
            )
        return self

    @property
    def authority_revision(self) -> str:
        """Producer-owned truth hash; attention and presentation are excluded."""

        return canonical_json_sha256(
            self.model_dump(
                mode="json",
                exclude={
                    "objective_id",
                    "investigation_id",
                    "workspace_revision",
                    "learning_history_revision",
                    "learning_ledger_head_sha256",
                    "learning_projection_sha256",
                    "run_sentinel_sha256",
                    "p35_assessment_sha256",
                    # P20 scientific content changes the workspace/cache revision,
                    # but P34 v1 authority remains bound to the already-frozen
                    # P20 state revision.
                    "p20_projection_sha256",
                    # The existing full runtime hash already owns this producer
                    # truth. Excluding its newly exposed typed mirror preserves
                    # the pre-P35 P34 authority revision byte-for-byte.
                    "vehicle_runtime_identity",
                },
            )
        )


class CrewChiefConsumptionBaseline(CrewChiefModel):
    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_head: int = Field(ge=0)
    eligible_lap_ids: tuple[str, ...] = ()
    measurement_attempt_ids: tuple[str, ...] = ()
    workflow_id: str | None = Field(default=None, min_length=1)
    workflow_revision: str | None = Field(default=None, min_length=1)
    wall_clock_started_at: datetime

    @classmethod
    def build(cls, **values: object) -> CrewChiefConsumptionBaseline:
        draft = cls.model_construct(**values, baseline_sha256="0" * 64)
        digest = canonical_json_sha256(
            draft.model_dump(mode="json", exclude={"baseline_sha256"})
        )
        return cls.model_validate({**values, "baseline_sha256": digest})

    @model_validator(mode="after")
    def baseline_is_content_addressed(self) -> CrewChiefConsumptionBaseline:
        if (self.workflow_id is None) != (self.workflow_revision is None):
            raise ValueError("consumption workflow head must be complete")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"baseline_sha256"})
        )
        if self.baseline_sha256 != expected:
            raise ValueError("Crew Chief consumption baseline identity is corrupt")
        return self


class CrewChiefProspectiveConsumption(CrewChiefModel):
    baseline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_lap_ids_after_open: tuple[str, ...] = ()
    measurement_attempt_ids_after_open: tuple[str, ...] = ()
    tool_request_event_ids: tuple[str, ...] = ()
    tool_execution_duration_ms: tuple[float, ...] = ()
    driver_question_ids: tuple[str, ...] = ()
    continue_action_count: int = Field(ge=0)
    workflow_ids_opened_after_open: tuple[str, ...] = ()
    authority: Literal["operational_counts_only"] = "operational_counts_only"

    @model_validator(mode="after")
    def timing_aligns_with_requests(self) -> CrewChiefProspectiveConsumption:
        if len(self.tool_request_event_ids) != len(self.tool_execution_duration_ms):
            raise ValueError("prospective tool timing must align with exact request events")
        if any(value < 0 for value in self.tool_execution_duration_ms):
            raise ValueError("prospective tool duration cannot be negative")
        return self


class CrewChiefInvestigation(CrewChiefModel):
    investigation_id: str = Field(min_length=1)
    workspace_identity: CrewChiefWorkspaceIdentity
    origin: Literal["post_import", "driver_report", "manual_review"]
    objective: EngineeringObjective
    raw_driver_report: str = Field(min_length=1)
    canonical_problem: str = Field(min_length=1)
    opening_reasoning: P19ReasoningMemory
    opening_problem: ProblemFingerprint
    opened_at: datetime
    consumption_baseline: CrewChiefConsumptionBaseline | None = None
    status: Literal["open", "complete", "stale", "abandoned"] = "open"

    @model_validator(mode="after")
    def opening_truth_matches_workspace(self) -> CrewChiefInvestigation:
        if (
            self.objective != self.workspace_identity.objective_id
            or self.opening_problem.objective != self.objective.value
            or self.opening_reasoning.reasoning_snapshot_sha256
            != self.workspace_identity.reasoning_snapshot_sha256
        ):
            raise ValueError(
                "Crew Chief opening reasoning/problem must match the immutable workspace truth"
            )
        if (
            self.consumption_baseline is not None
            and self.consumption_baseline.wall_clock_started_at != self.opened_at
        ):
            raise ValueError(
                "Crew Chief consumption timing must freeze at investigation open"
            )
        return self


class CrewChiefSelectionReceipt(CrewChiefModel):
    selection_policy_id: str = Field(min_length=1)
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0, le=16)
    omitted_count: int = Field(ge=0)
    selected_artifact_ids: tuple[str, ...] = ()
    selection_reasons: tuple[str, ...] = ()
    required_artifact_ids: tuple[str, ...] = ()
    required_artifacts_present: bool

    @classmethod
    def build(cls, **values: object) -> CrewChiefSelectionReceipt:
        draft = cls.model_construct(**values, selection_sha256="0" * 64)
        digest = canonical_json_sha256(
            draft.model_dump(mode="json", exclude={"selection_sha256"})
        )
        return cls.model_validate({**values, "selection_sha256": digest})

    @model_validator(mode="after")
    def receipt_binds_the_complete_selection(self) -> CrewChiefSelectionReceipt:
        if (
            self.selected_count != len(self.selected_artifact_ids)
            or self.omitted_count != self.candidate_count - self.selected_count
            or self.omitted_count < 0
            or len(self.selected_artifact_ids) != len(set(self.selected_artifact_ids))
            or len(self.required_artifact_ids) != len(set(self.required_artifact_ids))
        ):
            raise ValueError("Crew Chief selection receipt counts or identities disagree")
        expected_required = set(self.required_artifact_ids) <= set(
            self.selected_artifact_ids
        )
        if self.required_artifacts_present != expected_required:
            raise ValueError("required-artifact receipt state is inconsistent")
        expected = canonical_json_sha256(
            self.model_dump(mode="json", exclude={"selection_sha256"})
        )
        if self.selection_sha256 != expected:
            raise ValueError("Crew Chief selection receipt identity is corrupt")
        return self


CrewChiefEventType = Literal[
    "problem_interpreted",
    "hypothesis_registered",
    "hypothesis_inspected",
    "tool_invoked",
    "tool_result_attached",
    "contradiction_recorded",
    "subgoal_completed",
    "driver_question_asked",
    "driver_answer_recorded",
    "critique_completed",
    "decision_emitted",
    "objective_selected",
    "workspace_rebased",
    "investigation_abandoned",
]


class CrewChiefEventPayload(CrewChiefModel):
    message: str = Field(min_length=1)
    cause_ids: tuple[str, ...] = ()
    component_ids: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()
    workflow_ids: tuple[str, ...] = ()
    requested_measurement_ids: tuple[str, ...] = ()
    completed_measurement_ids: tuple[str, ...] = ()
    tool_id: str | None = None
    inspection_request_id: str | None = Field(
        default=None, pattern=r"^ccir_[0-9a-f]{24}$"
    )
    tool_execution_duration_ms: float | None = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    finding_kind: InspectionFindingKind | None = None
    strongest_support_artifact_ids: tuple[str, ...] = ()
    strongest_contradiction_artifact_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    ambiguity_before: int | None = Field(default=None, ge=0)
    ambiguity_after: int | None = Field(default=None, ge=0)
    recommended_next_inspection: str | None = Field(default=None, min_length=1)
    selection_receipt: CrewChiefSelectionReceipt | None = None
    question_id: str | None = None
    answer: str | None = None
    answer_interpretation: DriverAnswerInterpretation | None = None
    critique_outcome: Literal["pass", "blocked", "reinvestigate", "ask_driver"] | None = None
    decision_kind: str | None = None
    objective: EngineeringObjective | None = None
    previous_workspace_revision: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    new_workspace_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    previous_authority_revision: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    new_authority_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    adaptation_prediction_pair_id: str | None = Field(
        default=None, pattern=r"^p34pair_[0-9a-f]{24}$"
    )
    adaptation_prediction_pair_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    adaptation_prediction_source_snapshot_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    adaptation_rebase_source_snapshot_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    learning_capture_state: Literal["not_applicable", "captured", "blocked"] = (
        "not_applicable"
    )
    learning_capture_experience_id: str | None = Field(
        default=None, pattern=r"^p33x_[0-9a-f]{24}$"
    )
    learning_capture_experience_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    learning_capture_blocker_reason: str | None = Field(
        default=None, min_length=1, max_length=240
    )
    adaptation_capture_state: Literal["not_applicable", "captured", "blocked"] = (
        "not_applicable"
    )
    adaptation_capture_certificate_id: str | None = Field(
        default=None, pattern=r"^p34out_[0-9a-f]{24}$"
    )
    adaptation_capture_certificate_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    adaptation_capture_blocker_reason: str | None = Field(
        default=None, min_length=1, max_length=240
    )
    findings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identities_are_unique(self) -> CrewChiefEventPayload:
        for values, label in (
            (self.cause_ids, "cause"),
            (self.component_ids, "component"),
            (self.artifact_ids, "artifact"),
            (self.workflow_ids, "workflow"),
            (self.requested_measurement_ids, "requested measurement"),
            (self.completed_measurement_ids, "completed measurement"),
            (self.findings, "finding"),
            (self.strongest_support_artifact_ids, "strongest support artifact"),
            (
                self.strongest_contradiction_artifact_ids,
                "strongest contradiction artifact",
            ),
            (self.missing_evidence, "missing evidence"),
        ):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError(
                    f"Crew Chief {label} values must be non-empty and unique"
                )
        for previous, current, label in (
            (
                self.previous_workspace_revision,
                self.new_workspace_revision,
                "workspace",
            ),
            (
                self.previous_authority_revision,
                self.new_authority_revision,
                "authority",
            ),
        ):
            if (previous is None) != (current is None):
                raise ValueError(
                    f"Crew Chief {label} revisions must be present together"
                )
        prediction_identity = (
            self.adaptation_prediction_pair_id,
            self.adaptation_prediction_pair_sha256,
            self.adaptation_prediction_source_snapshot_sha256,
        )
        if any(item is None for item in prediction_identity) and any(
            item is not None for item in prediction_identity
        ):
            raise ValueError(
                "Crew Chief P34 prediction-pair identity and source snapshot must be complete"
            )
        has_experience_identity = (
            self.learning_capture_experience_id is not None
            and self.learning_capture_experience_sha256 is not None
        )
        if (self.learning_capture_experience_id is None) != (
            self.learning_capture_experience_sha256 is None
        ):
            raise ValueError(
                "Crew Chief P33 capture experience identity must be complete"
            )
        if self.learning_capture_state == "not_applicable" and (
            has_experience_identity or self.learning_capture_blocker_reason is not None
        ):
            raise ValueError(
                "non-attempted Crew Chief P33 capture cannot claim experience truth"
            )
        if self.learning_capture_state == "captured" and (
            not has_experience_identity
            or self.learning_capture_blocker_reason is not None
        ):
            raise ValueError(
                "captured Crew Chief P33 memory requires its exact experience"
            )
        if self.learning_capture_state == "blocked" and (
            not has_experience_identity or self.learning_capture_blocker_reason is None
        ):
            raise ValueError(
                "blocked Crew Chief P33 memory requires its attempted experience and blocker"
            )
        has_certificate_identity = (
            self.adaptation_capture_certificate_id is not None
            and self.adaptation_capture_certificate_sha256 is not None
        )
        if (self.adaptation_capture_certificate_id is None) != (
            self.adaptation_capture_certificate_sha256 is None
        ):
            raise ValueError(
                "Crew Chief P34 capture certificate identity must be complete"
            )
        if self.adaptation_capture_state == "not_applicable" and (
            has_certificate_identity
            or self.adaptation_capture_blocker_reason is not None
        ):
            raise ValueError(
                "non-attempted Crew Chief P34 capture cannot claim adaptation truth"
            )
        if self.adaptation_capture_state == "captured" and (
            not has_certificate_identity
            or self.adaptation_capture_blocker_reason is not None
        ):
            raise ValueError(
                "captured Crew Chief P34 outcome requires its exact certificate"
            )
        if self.adaptation_capture_state == "blocked" and (
            not has_certificate_identity
            or self.adaptation_capture_blocker_reason is None
        ):
            raise ValueError(
                "blocked Crew Chief P34 outcome requires its attempted certificate and blocker"
            )
        if (self.ambiguity_before is None) != (self.ambiguity_after is None):
            raise ValueError("Crew Chief ambiguity bounds must be present together")
        if self.ambiguity_after is not None and self.ambiguity_before is not None:
            if self.ambiguity_after > self.ambiguity_before:
                raise ValueError("one inspection cannot silently increase Crew ambiguity")
        return self


class CrewChiefEvent(CrewChiefModel):
    event_id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    event_type: CrewChiefEventType
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: CrewChiefEventPayload

    @model_validator(mode="after")
    def event_type_matches_payload(self) -> CrewChiefEvent:
        payload = self.payload
        if self.event_type in {"tool_invoked", "tool_result_attached"}:
            if payload.tool_id is None:
                raise ValueError("Crew Chief tool events require one tool identity")
        elif payload.tool_id is not None:
            raise ValueError("Crew Chief tool identity is exclusive to tool events")
        if self.event_type == "tool_invoked":
            if (
                payload.requested_measurement_ids != (payload.tool_id,)
                or payload.completed_measurement_ids
            ):
                raise ValueError(
                    "Crew Chief tool invocation must request its exact tool measurement"
                )
        elif self.event_type == "tool_result_attached":
            if (
                payload.requested_measurement_ids
                or payload.completed_measurement_ids != (payload.tool_id,)
            ):
                raise ValueError(
                    "Crew Chief tool result must complete its exact tool measurement"
                )
        elif payload.completed_measurement_ids:
            raise ValueError(
                "completed measurement identities are exclusive to tool results"
            )
        typed_inspection = payload.finding_kind is not None
        if self.event_type == "tool_invoked":
            if payload.inspection_request_id is None:
                # Persisted pre-P35.3 events remain readable.
                pass
            elif any(
                (
                    typed_inspection,
                    payload.selection_receipt is not None,
                    bool(payload.strongest_support_artifact_ids),
                    bool(payload.strongest_contradiction_artifact_ids),
                )
            ):
                raise ValueError("tool invocation cannot carry an inspection outcome")
        elif self.event_type == "tool_result_attached" and typed_inspection:
            if (
                payload.inspection_request_id is None
                or payload.tool_execution_duration_ms is None
                or payload.selection_receipt is None
                or payload.ambiguity_before is None
                or payload.ambiguity_after is None
                or payload.selection_receipt.selected_artifact_ids
                != payload.artifact_ids
            ):
                raise ValueError(
                    "typed tool results require their request, receipt, ambiguity, and exact artifacts"
                )
        elif self.event_type == "hypothesis_inspected":
            if typed_inspection and (
                payload.inspection_request_id is None
                or not payload.cause_ids
                or not payload.artifact_ids
            ):
                raise ValueError(
                    "hypothesis inspection requires an exact result/artifact/cause relationship"
                )
        elif self.event_type in {"contradiction_recorded", "subgoal_completed"}:
            if payload.inspection_request_id is None:
                raise ValueError(
                    "cognitive inspection events require their exact request identity"
                )
        elif payload.inspection_request_id is not None:
            raise ValueError(
                "inspection request identity is exclusive to inspection trace events"
            )
        if (
            payload.tool_execution_duration_ms is not None
            and self.event_type != "tool_result_attached"
        ):
            raise ValueError("tool execution duration is exclusive to tool results")
        if self.event_type not in {"tool_result_attached", "hypothesis_inspected"} and (
            payload.finding_kind is not None
            or payload.tool_execution_duration_ms is not None
            or payload.selection_receipt is not None
            or payload.strongest_support_artifact_ids
            or payload.strongest_contradiction_artifact_ids
            or payload.missing_evidence
            or payload.ambiguity_before is not None
            or payload.ambiguity_after is not None
            or payload.recommended_next_inspection is not None
        ):
            raise ValueError("inspection outcome fields are exclusive to result cognition")
        if self.event_type == "driver_question_asked":
            if payload.question_id is None or payload.answer is not None:
                raise ValueError(
                    "driver-question events require one unanswered question"
                )
        elif self.event_type == "driver_answer_recorded":
            if payload.question_id is None or payload.answer is None:
                raise ValueError(
                    "driver-answer events require the exact question and answer"
                )
        elif payload.question_id is not None or payload.answer is not None:
            raise ValueError("driver dialogue fields are exclusive to driver events")
        if payload.answer_interpretation is not None and (
            self.event_type != "driver_answer_recorded"
            or payload.answer_interpretation.answer != payload.answer
        ):
            raise ValueError(
                "typed driver-answer semantics are exclusive to their exact answer event"
            )
        if (self.event_type == "critique_completed") != (
            payload.critique_outcome is not None
        ):
            raise ValueError(
                "critic outcome is exclusive and required for critique events"
            )
        if (self.event_type == "decision_emitted") != (
            payload.decision_kind is not None
        ):
            raise ValueError(
                "decision identity is exclusive and required for decision events"
            )
        if payload.decision_kind == "measurement_mission":
            if len(payload.requested_measurement_ids) != 1:
                raise ValueError(
                    "measurement-mission decisions require the exact P19 mission contract"
                )
        elif self.event_type != "tool_invoked" and payload.requested_measurement_ids:
            raise ValueError(
                "measurement requests are exclusive to tool invocation or P19 missions"
            )
        if self.event_type != "decision_emitted" and payload.workflow_ids:
            raise ValueError(
                "workflow identities are exclusive to terminal decision events"
            )
        if payload.decision_kind == "controlled_test":
            if len(payload.workflow_ids) != 1:
                raise ValueError(
                    "controlled-test decisions require the exact workflow identity"
                )
        elif payload.workflow_ids:
            raise ValueError(
                "non-controlled Crew Chief decisions cannot claim workflow authority"
            )
        if (self.event_type == "objective_selected") != (payload.objective is not None):
            raise ValueError(
                "objective identity is exclusive and required for objective events"
            )
        if (
            payload.adaptation_prediction_pair_id is not None
            and self.event_type
            not in {"tool_invoked", "driver_question_asked", "decision_emitted"}
        ):
            raise ValueError(
                "P34 prediction-pair receipts are exclusive to executable Crew events"
            )
        if (self.event_type == "workspace_rebased") != (
            payload.adaptation_rebase_source_snapshot_sha256 is not None
        ):
            raise ValueError(
                "P34 rebase source snapshots are exclusive and required for rebase events"
            )
        if (
            self.event_type not in {"decision_emitted", "investigation_abandoned"}
            and (
                payload.learning_capture_state != "not_applicable"
                or payload.adaptation_capture_state != "not_applicable"
            )
        ):
            raise ValueError(
                "P33/P34 capture metadata is exclusive to terminal Crew events"
            )
        has_rebase = payload.previous_workspace_revision is not None
        if (self.event_type == "workspace_rebased") != has_rebase:
            raise ValueError(
                "workspace revisions are exclusive and required for rebase events"
            )
        return self


class HypothesisInspectionState(CrewChiefModel):
    cause_id: str = Field(min_length=1)
    p19_state: Literal["likely", "possible", "ruled_out", "unresolved"]
    progress: InvestigationProgress
    component_ids: tuple[str, ...] = ()
    support_artifact_ids: tuple[str, ...] = ()
    contradiction_artifact_ids: tuple[str, ...] = ()


class FoldedInvestigationState(CrewChiefModel):
    investigation_id: str = Field(min_length=1)
    status: Literal["open", "complete", "stale", "abandoned"]
    event_count: int = Field(ge=0)
    last_sequence: int = Field(ge=0)
    objective: EngineeringObjective
    current_subgoal: str | None = None
    completed_tool_ids: tuple[str, ...] = ()
    pending_driver_question_id: str | None = None
    driver_answers: tuple[str, ...] = ()
    driver_answer_interpretations: tuple[DriverAnswerInterpretation, ...] = ()
    hypotheses: tuple[HypothesisInspectionState, ...] = ()
    latest_critique_outcome: Literal[
        "pass", "blocked", "reinvestigate", "ask_driver"
    ] | None = None
    last_decision_kind: str | None = None
    stale_reason: str | None = None
    accepted_workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class EngineeringEvidenceIndexEntry(CrewChiefModel):
    artifact_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    setup_id: str | None = Field(default=None, min_length=1)
    workspace_run_id: str = Field(min_length=1)
    workspace_session_id: str = Field(min_length=1)
    workspace_setup_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    source_session_id: str | None = Field(default=None, min_length=1)
    source_setup_id: str | None = Field(default=None, min_length=1)
    source_setup_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_build_context_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    source_provenance_available: bool
    lap_numbers: tuple[int, ...] = ()
    lap_pct_start: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    lap_pct_end: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    phase: str | None = None
    mechanism_ids: tuple[MechanismKind, ...] = ()
    component_ids: tuple[str, ...] = ()
    control_keys: tuple[str, ...] = ()
    objective: EngineeringObjective
    source_channels: tuple[str, ...] = ()
    evidence_state: EvidenceState
    polarity: Literal["support", "contradiction", "neutral"]
    blocker_reasons: tuple[str, ...] = ()
    typed_artifact: CrewChiefEvidenceArtifact | None = None
    authority_ceiling: Literal[
        "observation_only",
        "context_only",
        "measurement_only",
        "p19_projection_only",
        "attention_only",
    ]

    @model_validator(mode="after")
    def exact_window_is_complete(self) -> EngineeringEvidenceIndexEntry:
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("evidence index windows require both bounds")
        if self.lap_pct_start is not None and self.lap_pct_start > self.lap_pct_end:
            raise ValueError("evidence index window bounds are reversed")
        if self.run_id != self.source_run_id or self.setup_id != self.source_setup_id:
            raise ValueError("legacy evidence scope must equal explicit source scope")
        complete = all(
            (
                self.source_session_id,
                self.source_setup_id,
                self.source_setup_sha256,
                self.source_build_context_sha256,
            )
        )
        if self.source_provenance_available != bool(complete):
            raise ValueError(
                "source provenance availability must match exact source identity"
            )
        if not complete and "source identity unavailable" not in self.blocker_reasons:
            raise ValueError(
                "incomplete source identity must block exact-context interpretation"
            )
        performance_types: dict[str, PerformanceArtifactType] = {
            "p32.lap_time_opportunity": "lap_time_opportunity",
            "p32.time_loss_origin": "time_loss_origin",
            "p32.corner_performance_chain": "corner_performance_chain",
            "p32.exit_carry": "exit_carry",
            "p32.path_efficiency": "path_efficiency",
            "p32.driver_vehicle_separation": "driver_vehicle_separation",
            "p32.track_demand": "track_demand",
            "p32.component_performance_link": "component_performance_link",
            "p32.objective_envelope": "objective_envelope",
        }
        expected_type = performance_types.get(self.producer_id)
        dynamics_tools: dict[str, VehicleDynamicsInspectionToolId] = {
            f"p35.{tool_id.removeprefix('inspect_')}": tool_id
            for tool_id in _P35_INSPECTION_TOOL_IDS
        }
        expected_dynamics_tool = dynamics_tools.get(self.producer_id)
        if expected_type is None and expected_dynamics_tool is None:
            if self.typed_artifact is not None:
                raise ValueError("only typed P32/P35 evidence may carry an artifact")
            return self
        if expected_dynamics_tool is not None:
            if not isinstance(
                self.typed_artifact, CrewChiefVehicleDynamicsFocusArtifact
            ):
                raise ValueError("P35 evidence requires its typed focus artifact")
            focus = self.typed_artifact.focus
            if (
                self.typed_artifact.inspection_tool_id != expected_dynamics_tool
                or focus.inspection_tool_id.value != expected_dynamics_tool
                or self.artifact_id != focus.artifact_id
                or self.evidence_state != focus.evidence_state
                or self.source_channels != focus.source_channels
                or self.blocker_reasons != focus.blocker_reasons
            ):
                raise ValueError(
                    "P35 producer, focus identity, state, channels, and blockers must agree"
                )
            return self
        if self.typed_artifact is None:
            raise ValueError(
                "P32 evidence requires the typed artifact it claims to inspect"
            )
        actual_type = self.typed_artifact.artifact_type
        if actual_type == "unavailable":
            if (
                self.typed_artifact.claimed_artifact_type != expected_type
                or self.evidence_state != EvidenceState.UNAVAILABLE
                or not self.blocker_reasons
            ):
                raise ValueError(
                    "unavailable P32 artifacts must match their claim, state, and blockers"
                )
            return self
        if (
            actual_type != expected_type
            or self.evidence_state == EvidenceState.UNAVAILABLE
        ):
            raise ValueError(
                "P32 producer, typed artifact, and evidence state disagree"
            )
        artifact_start: float | None = None
        artifact_end: float | None = None
        artifact_id: str | None = None
        if isinstance(self.typed_artifact, CrewChiefLapTimeOpportunityArtifact):
            opportunity = self.typed_artifact.opportunity
            artifact_start = opportunity.start_pct
            artifact_end = opportunity.end_pct
            artifact_id = opportunity.opportunity_id
        elif isinstance(self.typed_artifact, CrewChiefTimeLossOriginArtifact):
            opportunity = self.typed_artifact.opportunity
            artifact_start = opportunity.start_pct
            artifact_end = opportunity.end_pct
            artifact_id = f"{opportunity.opportunity_id}:time-origin"
        elif isinstance(self.typed_artifact, CrewChiefExitCarryArtifact):
            opportunity = self.typed_artifact.opportunity
            artifact_start = opportunity.following_phase_start_pct
            artifact_end = opportunity.following_phase_end_pct
            artifact_id = f"{opportunity.opportunity_id}:exit-carry"
        elif isinstance(self.typed_artifact, CrewChiefCornerPerformanceChainArtifact):
            artifact_start = self.typed_artifact.start_pct
            artifact_end = self.typed_artifact.end_pct
            artifact_id = self.typed_artifact.chain.chain_id
        elif isinstance(self.typed_artifact, CrewChiefPathEfficiencyArtifact):
            artifact_start = self.typed_artifact.phase_state.start_pct
            artifact_end = self.typed_artifact.phase_state.end_pct
            artifact_id = (
                f"{self.typed_artifact.chain_id}:path:"
                f"{self.typed_artifact.phase_state.phase}"
            )
        elif isinstance(self.typed_artifact, CrewChiefDriverVehicleSeparationArtifact):
            artifact_start = self.typed_artifact.start_pct
            artifact_end = self.typed_artifact.end_pct
            artifact_id = self.typed_artifact.separation.separation_id
        elif isinstance(self.typed_artifact, CrewChiefComponentPerformanceLinkArtifact):
            artifact_id = self.typed_artifact.influence.influence_id
        elif isinstance(self.typed_artifact, CrewChiefTrackDemandArtifact):
            artifact_id = (
                f"p32-track-demand:"
                f"{canonical_json_sha256(self.typed_artifact.profile)[:20]}"
            )
        elif isinstance(self.typed_artifact, CrewChiefObjectiveEnvelopeArtifact):
            artifact_id = (
                f"p32-objective:"
                f"{canonical_json_sha256(self.typed_artifact.envelope)[:20]}"
            )
        if artifact_start is not None and (
            self.lap_pct_start != artifact_start or self.lap_pct_end != artifact_end
        ):
            raise ValueError("P32 evidence window must equal its typed artifact window")
        if artifact_id is not None and self.artifact_id != artifact_id:
            raise ValueError(
                "P32 evidence identity must equal its typed artifact identity"
            )
        return self


class EngineeringEvidenceIndex(CrewChiefModel):
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: tuple[EngineeringEvidenceIndexEntry, ...] = ()
    index_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def artifacts_are_unique(self) -> EngineeringEvidenceIndex:
        ids = [entry.artifact_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence index artifact identities must be unique")
        expected_hash = canonical_json_sha256(
            [entry.model_dump(mode="json") for entry in self.entries]
        )
        if self.index_hash != expected_hash:
            raise ValueError(
                "evidence index hash must bind the ordered complete entry payloads"
            )
        return self


P34QualifiedArtifactEvidenceState = Literal[
    "measured",
    "calculated",
    "controlled_test_effect",
]


def _p34_qualified_current_artifact_entries(
    identity: CrewChiefWorkspaceIdentity,
    evidence_index: EngineeringEvidenceIndex,
) -> tuple[EngineeringEvidenceIndexEntry, ...]:
    """Select blocker-free exact-provenance evidence from the current workspace."""

    qualified_states = {
        EvidenceState.MEASURED,
        EvidenceState.CALCULATED,
        EvidenceState.CONTROLLED_TEST_EFFECT,
    }
    return tuple(
        item
        for item in evidence_index.entries
        if not getattr(item, "producer_id", "").startswith("p35.")
        and item.evidence_state in qualified_states
        and not item.blocker_reasons
        and item.source_provenance_available
        and item.run_id == identity.run_id
        and item.session_id == identity.session_id
        and item.setup_id == identity.setup_id
        and item.workspace_run_id == identity.run_id
        and item.workspace_session_id == identity.session_id
        and item.workspace_setup_id == identity.setup_id
        and item.source_run_id == identity.run_id
        and item.source_session_id == identity.session_id
        and item.source_setup_id == identity.setup_id
        and item.source_setup_sha256 == identity.setup_snapshot_sha256
        and item.source_build_context_sha256
        == identity.vehicle_runtime_identity_hash
    )


def p34_qualified_current_artifact_cohort(
    identity: CrewChiefWorkspaceIdentity,
    evidence_index: EngineeringEvidenceIndex,
) -> tuple[
    tuple[str, ...],
    tuple[P34QualifiedArtifactEvidenceState, ...],
    tuple[str, ...],
]:
    """Return the aligned, preregistered P34 evidence cohort and provenance."""

    entries = _p34_qualified_current_artifact_entries(identity, evidence_index)
    return (
        tuple(item.artifact_id for item in entries),
        tuple(
            cast(P34QualifiedArtifactEvidenceState, item.evidence_state.value)
            for item in entries
        ),
        tuple(
            canonical_json_sha256(item.model_dump(mode="json"))
            for item in entries
        ),
    )


def p34_qualified_current_artifact_ids(
    identity: CrewChiefWorkspaceIdentity,
    evidence_index: EngineeringEvidenceIndex,
) -> tuple[str, ...]:
    """Return only blocker-free, exact-provenance current measured evidence IDs."""

    return tuple(
        item.artifact_id
        for item in _p34_qualified_current_artifact_entries(identity, evidence_index)
    )


class CrewChiefToolDefinition(CrewChiefModel):
    tool_id: str = Field(min_length=1)
    allowed_scope: Literal["run", "session", "component", "workflow"]
    input_schema: str = Field(min_length=1)
    output_artifact_type: str = Field(min_length=1)
    authority_ceiling: Literal["observation_only", "context_only", "measurement_only"]
    required_sources: tuple[str, ...] = ()


class CrewChiefToolEligibility(CrewChiefModel):
    tool_id: str = Field(min_length=1)
    currently_relevant: bool
    required_by_mandatory_gate: bool = False
    expected_to_separate: tuple[str, ...] = ()
    available_artifact_types: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    cost_class: Literal["cheap", "moderate"] = "cheap"
    safe_priority_tier: Literal[
        "integrity_context",
        "measured_problem",
        "driver_car_confounder",
        "contradiction",
        "mechanism_separator",
        "component_separator",
        "history",
        "measurement_debt",
        "p19_terminal",
    ]
    skip_reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def relevance_matches_skip_state(self) -> CrewChiefToolEligibility:
        if self.currently_relevant == (self.skip_reason is not None):
            raise ValueError("tool eligibility relevance and skip reason disagree")
        return self


class CrewChiefToolResult(CrewChiefModel):
    inspection_request_id: str | None = Field(
        default=None, pattern=r"^ccir_[0-9a-f]{24}$"
    )
    tool_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["complete", "blocked", "no_finding"]
    summary: str = Field(min_length=1)
    artifact_ids: tuple[str, ...] = ()
    cause_ids: tuple[str, ...] = ()
    component_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    authority_ceiling: Literal["observation_only", "context_only", "measurement_only"]
    finding_kind: InspectionFindingKind = "no_signal"
    observed_finding: str | None = Field(default=None, min_length=1)
    strongest_support_artifact_ids: tuple[str, ...] = ()
    strongest_contradiction_artifact_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    ambiguity_before: int = Field(default=0, ge=0)
    ambiguity_after: int = Field(default=0, ge=0)
    cause_ids_actually_examined: tuple[str, ...] = ()
    component_ids_actually_examined: tuple[str, ...] = ()
    recommended_next_inspection: str | None = Field(default=None, min_length=1)
    selection_receipt: CrewChiefSelectionReceipt | None = None

    @model_validator(mode="after")
    def typed_outcome_is_bounded(self) -> CrewChiefToolResult:
        if self.ambiguity_after > self.ambiguity_before:
            raise ValueError("inspection result cannot silently increase ambiguity")
        if self.cause_ids != self.cause_ids_actually_examined:
            raise ValueError("legacy cause IDs must equal causes actually examined")
        if self.component_ids != self.component_ids_actually_examined:
            raise ValueError("legacy component IDs must equal components actually examined")
        if self.selection_receipt is not None and (
            self.selection_receipt.selected_artifact_ids != self.artifact_ids
        ):
            raise ValueError("inspection result must equal its selection receipt")
        return self


class InvestigationSubgoal(CrewChiefModel):
    subgoal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    selected_tool: str = Field(min_length=1)
    why_this_tool: str = Field(min_length=1)
    distinguishes_cause_ids: tuple[str, ...] = ()
    mechanism_ids: tuple[str, ...] = ()
    bridge_ids: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()
    opportunity_id: str | None = Field(default=None, min_length=1)
    required_discriminator_id: str | None = Field(default=None, min_length=1)
    exact_control_keys: tuple[str, ...] = ()
    experiment_factor_ids: tuple[str, ...] = ()
    driver_answer_interpretation: DriverAnswerInterpretation | None = None
    required_evidence: tuple[str, ...] = ()
    stop_condition: str = Field(min_length=1)
    priority_rank: int = Field(ge=1)


class CrewChiefCritique(CrewChiefModel):
    outcome: Literal["pass", "blocked", "reinvestigate", "ask_driver"]
    passed: bool
    findings: tuple[str, ...] = ()
    forbidden_decision_kinds: tuple[str, ...] = ()
    required_next_investigation: str | None = None
    strongest_contradiction: str | None = None

    @model_validator(mode="after")
    def pass_state_matches_findings(self) -> CrewChiefCritique:
        if self.passed != (self.outcome == "pass"):
            raise ValueError("critic pass flag must match its outcome")
        if not self.passed and not self.findings:
            raise ValueError("a failed critic requires findings")
        return self


class DriverDiagnosticQuestion(CrewChiefModel):
    question_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    question: str = Field(min_length=1)
    answer_type: Literal["single_choice"] = "single_choice"
    answer_options: tuple[str, ...] = Field(min_length=2)
    distinguishes_cause_ids: tuple[str, ...] = ()
    distinguishes_component_ids: tuple[str, ...] = ()
    reason: str = Field(min_length=1)
    authority: Literal["context_only"] = "context_only"


class SuccessMetric(CrewChiefModel):
    metric: str = Field(min_length=1)
    threshold: str = Field(min_length=1)
    threshold_source: str = Field(min_length=1)
    hard_limit: bool = True


class SuccessContract(CrewChiefModel):
    contract_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective: EngineeringObjective
    target_scope: str = Field(min_length=1)
    primary_metric: SuccessMetric
    minimum_repetitions: int = Field(ge=1)
    independence_unit: str = Field(min_length=1)
    protected_metrics: tuple[SuccessMetric, ...] = Field(min_length=1)
    context_invariants: tuple[str, ...] = Field(min_length=1)
    driver_invariants: tuple[str, ...] = Field(min_length=1)
    setup_invariants: tuple[str, ...] = Field(min_length=1)
    acceptance_rule: str = Field(min_length=1)
    rejection_rule: str = Field(min_length=1)
    retest_rule: str = Field(min_length=1)
    stop_rule: str = Field(min_length=1)
    rollback_rule: str = Field(min_length=1)
    authority: Literal["p19_evaluation_contract"] = "p19_evaluation_contract"


class RunSentinelLap(CrewChiefModel):
    lap_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    status: Literal["context_cleared", "rejected"]
    reasons: tuple[str, ...] = ()
    context_ordinal: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def context_cleared_laps_have_an_ordinal(self) -> RunSentinelLap:
        if self.status == "context_cleared" and (
            self.context_ordinal is None or self.reasons
        ):
            raise ValueError(
                "context-cleared sentinel laps require an ordinal and no rejection"
            )
        if self.status == "rejected" and (
            not self.reasons or self.context_ordinal is not None
        ):
            raise ValueError("rejected sentinel laps require exact reasons only")
        return self


class RunSentinelState(CrewChiefModel):
    mission_state: Literal[
        "collecting",
        "blocked_by_p19",
        "stopped_by_p19",
        "awaiting_p19_score",
        "collection_complete",
    ]
    p19_plan_kind: Literal[
        "controlled_test",
        "measurement_mission",
        "discriminator",
        "stop_testing",
        "blocked",
    ]
    mission: str = Field(min_length=1)
    need: str = Field(min_length=1)
    hold_constant: tuple[str, ...] = Field(min_length=1)
    watch: tuple[str, ...] = Field(min_length=1)
    success: str = Field(min_length=1)
    stop: tuple[str, ...] = Field(min_length=1)
    required_laps: int | None = Field(default=None, ge=1)
    context_cleared_laps: int = Field(ge=0)
    mission_accepted_lap_ids: tuple[str, ...] = ()
    measurement_attempt_ids: tuple[str, ...] = ()
    mission_acceptance_basis: Literal[
        "unbound",
        "p19_measurement_attempt",
        "controlled_workflow_stage",
    ] = "unbound"
    collection_complete: bool
    stage: Literal[
        "measurement", "A", "B", "A2", "blocked", "stopped", "awaiting_score"
    ]
    laps: tuple[RunSentinelLap, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def progress_matches_laps(self) -> RunSentinelState:
        if self.context_cleared_laps != sum(
            item.status == "context_cleared" for item in self.laps
        ):
            raise ValueError(
                "sentinel context-cleared count must match exact lap decisions"
            )
        for values, label in (
            (self.mission_accepted_lap_ids, "mission-accepted lap"),
            (self.measurement_attempt_ids, "measurement-attempt"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"sentinel {label} identities must be non-empty and unique")
        if self.mission_acceptance_basis == "unbound" and (
            self.mission_accepted_lap_ids or self.measurement_attempt_ids
        ):
            raise ValueError("unbound sentinel progress cannot claim accepted evidence")
        if self.mission_acceptance_basis == "p19_measurement_attempt" and (
            self.p19_plan_kind not in {"measurement_mission", "discriminator"}
            or not self.mission_accepted_lap_ids
            or not self.measurement_attempt_ids
        ):
            raise ValueError(
                "P19 mission acceptance requires exact attempts and accepted laps"
            )
        if self.mission_acceptance_basis == "controlled_workflow_stage" and (
            self.p19_plan_kind != "controlled_test"
            or not self.mission_accepted_lap_ids
            or self.measurement_attempt_ids
            or not set(self.mission_accepted_lap_ids).issubset(
                {
                    item.lap_id
                    for item in self.laps
                    if item.status == "context_cleared"
                }
            )
        ):
            raise ValueError(
                "controlled-stage acceptance requires exact stage laps only"
            )
        expected_complete = (
            self.required_laps is not None
            and len(self.mission_accepted_lap_ids) >= self.required_laps
            and self.mission_state
            not in {"blocked_by_p19", "stopped_by_p19"}
        )
        if self.collection_complete != expected_complete:
            raise ValueError(
                "sentinel collection completion must match accepted evidence"
            )
        if self.mission_state == "collection_complete" and not self.collection_complete:
            raise ValueError("collection-complete state requires a complete collection")
        if self.mission_state == "blocked_by_p19" and self.stage != "blocked":
            raise ValueError("blocked P19 state requires a blocked sentinel")
        if self.mission_state == "stopped_by_p19" and self.stage != "stopped":
            raise ValueError("stopped P19 state requires a stopped sentinel")
        if (
            self.mission_state == "awaiting_p19_score"
            and self.stage != "awaiting_score"
        ):
            raise ValueError("awaiting-score state requires its exact sentinel stage")
        return self


class CrewChiefTerminalDecision(CrewChiefModel):
    kind: Literal[
        "driver_question",
        "driver_focus",
        "measurement_mission",
        "controlled_test",
        "observe_only",
        "no_call",
    ]
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    authority: Literal["context_only", "measurement_only", "p19_projection_only"]
    control_key: str | None = None
    setup_effect_id: str | None = None
    experiment_factor_id: str | None = None
    direction_sign: Literal[-1, 1] | None = None
    current_value: str | None = None
    proposed_value: str | None = None
    source_event_ids: tuple[str, ...] = ()
    workflow_id: str | None = None
    workflow_revision: str | None = None
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def setup_fields_are_p19_projection_only(self) -> CrewChiefTerminalDecision:
        setup_values = (self.control_key, self.current_value, self.proposed_value)
        semantic_identity = (
            self.setup_effect_id,
            self.experiment_factor_id,
            self.direction_sign,
        )
        if self.kind == "controlled_test":
            if self.authority != "p19_projection_only" or any(
                value is None for value in setup_values
            ) or any(value is None for value in semantic_identity):
                raise ValueError("controlled tests require one complete P19 projection")
            if (
                not self.source_event_ids
                or not self.workflow_id
                or not self.workflow_revision
            ):
                raise ValueError(
                    "controlled tests require exact evidence and workflow revision"
                )
        elif any(value is not None for value in (*setup_values, *semantic_identity)):
            raise ValueError(
                "non-controlled Crew Chief decisions cannot expose setup values"
            )
        elif self.authority == "p19_projection_only":
            raise ValueError(
                "P19 projection authority is exclusive to controlled tests"
            )
        if (self.workflow_id is None) != (self.workflow_revision is None):
            raise ValueError("terminal workflow identity requires its revision")
        if self.kind != "controlled_test" and self.workflow_id is not None:
            raise ValueError(
                "non-controlled decisions cannot expose workflow authority"
            )
        if len(self.source_event_ids) != len(set(self.source_event_ids)):
            raise ValueError("terminal evidence identities must be unique")
        return self


class ComponentResponseRecord(CrewChiefModel):
    record_id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    control_key: str = Field(min_length=1)
    direction: Literal["increase", "decrease", "unchanged", "unknown"]
    magnitude_class: Literal["adjacent", "small", "medium", "large", "unknown"]
    car_path: str = Field(min_length=1)
    car_version: str = Field(min_length=1)
    iracing_build: str = Field(min_length=1)
    track_package: str = Field(min_length=1)
    objective: EngineeringObjective
    target_phase: str = Field(min_length=1)
    physical_window: str = Field(min_length=1)
    mechanism_result: str = Field(min_length=1)
    control_response_result: str = Field(min_length=1)
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    source_workflow_id: str = Field(min_length=1)
    source_run_ids: tuple[str, ...] = Field(min_length=3)
    evidence_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority: Literal["controlled_history_only"] = "controlled_history_only"


class DriverKnowledgeRecord(CrewChiefModel):
    record_id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    complaint_phrase: str = Field(min_length=1)
    contextual_answer: str | None = None
    associated_cause_ids: tuple[str, ...] = ()
    source_event_ids: tuple[str, ...] = ()
    recorded_at: datetime
    authority: Literal["complaint_prior_only"] = "complaint_prior_only"


class CrewChiefEffectivenessRecord(CrewChiefModel):
    record_id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: datetime
    opened_at: datetime
    resolved_at: datetime
    elapsed_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    interaction_count: int = Field(ge=0)
    questions_asked: int = Field(ge=0)
    questions_answered: int = Field(ge=0)
    inspections_performed: int = Field(ge=0)
    collection_complete: bool
    linked_workflow_ids: tuple[str, ...] = ()
    scored_workflow_ids: tuple[str, ...] = ()
    resolution: Literal["decision_emitted", "abandoned"]
    measurement_missions_completed: int = Field(ge=0)
    controlled_tests_completed: int = Field(ge=0)
    rejected_laps: int = Field(ge=0)
    prior_undo_policies_blocked: int = Field(ge=0)
    countereffects_caught: int = Field(ge=0)
    terminal_decision_kind: str = Field(min_length=1)
    authority: Literal["operational_counts_only"] = "operational_counts_only"


class GenerativeExecutiveBoundary(CrewChiefModel):
    enabled: Literal[False] = False
    mode: Literal["shadow_only"] = "shadow_only"
    authority: Literal["none"] = "none"
    may_request_approved_tools: bool = False
    setup_values_visible: Literal[False] = False
    blocker_reason: str = "No generative executive is active; deterministic planning and P19 authority remain complete."


class AdaptiveResearchBoundary(CrewChiefModel):
    state: Literal["data_locked"] = "data_locked"
    authority: Literal["none"] = "none"
    production_protocol: Literal["one_factor_p19_aba2"] = "one_factor_p19_aba2"
    candidate_methods: tuple[str, ...] = (
        "hybrid physics/data observers",
        "active experiment selection",
        "DOE interaction screening",
        "causal time-series methods",
        "Bayesian optimization",
    )
    activation_gate: str = "P21/P22 held-out and prospective evidence gates must pass before any activation."


class CrewChiefWorkspace(CrewChiefModel):
    schema_version: Literal["p352.crew-chief-workspace.v1"] = (
        "p352.crew-chief-workspace.v1"
    )
    identity: CrewChiefWorkspaceIdentity
    generated_at: datetime
    cache_state: Literal["cold", "warm"] = "cold"
    investigation: CrewChiefInvestigation | None = None
    folded_state: FoldedInvestigationState | None = None
    evidence_index: EngineeringEvidenceIndex
    available_tools: tuple[CrewChiefToolDefinition, ...]
    tool_eligibility: tuple[CrewChiefToolEligibility, ...] = ()
    current_subgoal: InvestigationSubgoal | None = None
    latest_tool_result: CrewChiefToolResult | None = None
    critique: CrewChiefCritique
    pending_driver_question: DriverDiagnosticQuestion | None = None
    prospective_consumption: CrewChiefProspectiveConsumption | None = None
    success_contract: SuccessContract | None = None
    p19_mission_contract: MeasurementMissionContract | None = None
    engineering_awareness: EngineeringAwarenessProjection | None = None
    performance_intelligence: PerformanceIntelligenceProjection
    vehicle_dynamics: PerformanceMechanismAssessment
    engineering_knowledge: CurrentEngineeringKnowledgeProjection
    learning_prior: CrewChiefLearningPrior
    investigation_improvement: InvestigationImprovementProjection
    run_sentinel: RunSentinelState
    terminal_decision: CrewChiefTerminalDecision
    response_history_ids: tuple[str, ...] = ()
    driver_memory_ids: tuple[str, ...] = ()
    p19_cause_ids: tuple[str, ...] = ()
    p19_contradiction_artifact_ids: tuple[str, ...] = ()
    p20_episode_ids: tuple[str, ...] = ()
    p26_component_ids: tuple[str, ...] = ()
    post_run_brief: tuple[str, ...] = Field(min_length=1)
    generative_boundary: GenerativeExecutiveBoundary = Field(
        default_factory=GenerativeExecutiveBoundary
    )
    adaptive_research: AdaptiveResearchBoundary = Field(
        default_factory=AdaptiveResearchBoundary
    )
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def projection_scope_is_atomic(self) -> CrewChiefWorkspace:
        if self.evidence_index.workspace_revision != self.identity.workspace_revision:
            raise ValueError("evidence index must match the workspace revision")
        tool_ids = tuple(item.tool_id for item in self.available_tools)
        eligibility_ids = tuple(item.tool_id for item in self.tool_eligibility)
        if (
            not self.tool_eligibility
            or len(tool_ids) != len(set(tool_ids))
            or eligibility_ids != tool_ids
        ):
            raise ValueError(
                "every advertised Crew tool requires one ordered server-owned eligibility record"
            )
        if self.current_subgoal is not None and not any(
            item.tool_id == self.current_subgoal.selected_tool
            and item.currently_relevant
            for item in self.tool_eligibility
        ):
            raise ValueError("the active Crew subgoal must be currently executable")
        latest_driver_scope = (
            self.folded_state.driver_answer_interpretations[-1]
            if self.folded_state is not None
            and self.folded_state.driver_answer_interpretations
            else None
        )
        if self.current_subgoal is not None and (
            self.current_subgoal.driver_answer_interpretation != latest_driver_scope
        ):
            raise ValueError(
                "the active Crew subgoal must carry the exact latest driver-answer scope"
            )
        if (
            self.folded_state is not None
            and self.folded_state.status == "open"
            and self.folded_state.latest_critique_outcome is not None
            and self.folded_state.latest_critique_outcome != self.critique.outcome
        ):
            raise ValueError(
                "the persisted Crew critic result must equal the reconstructed open-workspace critic"
            )
        baseline = (
            self.investigation.consumption_baseline
            if self.investigation is not None
            else None
        )
        if baseline is not None and (
            self.prospective_consumption is None
            or self.prospective_consumption.baseline_sha256
            != baseline.baseline_sha256
        ):
            raise ValueError(
                "prospective consumption must bind the exact at-open baseline"
            )
        if baseline is None and self.prospective_consumption is not None:
            raise ValueError(
                "prospective consumption cannot exist without an at-open baseline"
            )
        if canonical_json_sha256(self.run_sentinel) != self.identity.run_sentinel_sha256:
            raise ValueError("run sentinel must match the atomic workspace identity")
        awareness = self.engineering_awareness
        if (
            awareness is None
            or self.identity.p20_projection_sha256 is None
            or engineering_awareness_scientific_sha256(awareness)
            != self.identity.p20_projection_sha256
            or awareness.run_id != self.identity.run_id
            or awareness.session_id != self.identity.session_id
            or awareness.reasoning_snapshot_id
            != self.identity.reasoning_snapshot_sha256
            or awareness.request_identity.run_id != self.identity.run_id
            or awareness.request_identity.session_id != self.identity.session_id
            or awareness.request_identity.reasoning_snapshot_id
            != self.identity.reasoning_snapshot_sha256
            or awareness.state_revision != self.identity.p20_state_revision
            or awareness.request_identity.state_revision
            != self.identity.p20_state_revision
            or awareness.profile_hash != self.identity.p20_profile_hash
            or awareness.authority != "observation_only"
            or awareness.raw_trace_included
        ):
            raise ValueError(
                "P20 scientific projection must match the atomic Crew Chief workspace"
            )
        if (
            self.performance_intelligence.projection_sha256
            != self.identity.p32_projection_sha256
            or self.performance_intelligence.run_id != self.identity.run_id
            or self.performance_intelligence.session_id != self.identity.session_id
            or self.performance_intelligence.objective_id
            != self.identity.objective_id.value
            or self.performance_intelligence.p19_reasoning_snapshot_sha256
            != self.identity.reasoning_snapshot_sha256
            or self.performance_intelligence.p20_state_revision
            != self.identity.p20_state_revision
            or self.performance_intelligence.p26_knowledge_graph_sha256
            != self.identity.p26_knowledge_graph_sha256
        ):
            raise ValueError(
                "P32 projection must match the atomic Crew Chief workspace"
            )
        dynamics = self.vehicle_dynamics
        from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
            compile_next_gen_oval_knowledge_graph,
            compile_next_gen_oval_runtime_trust_manifest,
            resolve_next_gen_oval_knowledge_graph,
        )
        from racelab_engine.services.vehicle_dynamics_service import (
            _augment_vehicle_response_with_p20,
            _comparison_context_truth,
            _driver_input_stage,
            _focus_id,
            _matched_driver_vehicle_separation,
            _matching_chain,
            _matching_phase_state,
            _phase_kind,
            _response_regime,
            _runtime_unavailable_quantities,
            _runtime_support_contract_blockers,
            _time_stage,
            _tire_platform_stage,
            _vehicle_demand_stage,
            _vehicle_response_stage,
        )

        canonical_dynamics_graph = compile_next_gen_oval_knowledge_graph()
        runtime_trust = compile_next_gen_oval_runtime_trust_manifest()
        producer_runtime = self.identity.vehicle_runtime_identity
        expected_car_path = (
            producer_runtime.car_path if producer_runtime is not None else "unavailable"
        )
        expected_car_version = (
            producer_runtime.car_version
            if producer_runtime is not None
            else "unavailable"
        )
        expected_build = (
            producer_runtime.iracing_build_version
            if producer_runtime is not None
            else "unavailable"
        )
        expected_track_package = (
            "oval"
            if producer_runtime is not None
            and producer_runtime.track_configuration_name.casefold() == "oval"
            else "unavailable"
        )
        canonical_resolution = resolve_next_gen_oval_knowledge_graph(
            car_path=(
                None if dynamics.car_path == "unavailable" else dynamics.car_path
            ),
            car_version=(
                None if dynamics.car_version == "unavailable" else dynamics.car_version
            ),
            iracing_build_version=(
                None
                if dynamics.iracing_build_version == "unavailable"
                else dynamics.iracing_build_version
            ),
            track_package=(
                None
                if dynamics.track_package == "unavailable"
                else dynamics.track_package
            ),
        )
        if (
            dynamics.p35_assessment_sha256
            != self.identity.p35_assessment_sha256
            or dynamics.run_id != self.identity.run_id
            or dynamics.session_id != self.identity.session_id
            or dynamics.objective_id != self.identity.objective_id.value
            or dynamics.vehicle_runtime_identity_sha256
            != self.identity.vehicle_runtime_identity_hash
            or dynamics.car_path != expected_car_path
            or dynamics.car_version != expected_car_version
            or dynamics.iracing_build_version != expected_build
            or dynamics.track_package != expected_track_package
            or dynamics.p19_reasoning_snapshot_sha256
            != self.identity.reasoning_snapshot_sha256
            or dynamics.p20_state_revision != self.identity.p20_state_revision
            or dynamics.p20_profile_hash != self.identity.p20_profile_hash
            or dynamics.p26_graph_version != self.identity.p26_graph_version
            or dynamics.p26_knowledge_graph_sha256
            != self.identity.p26_knowledge_graph_sha256
            or dynamics.p32_projection_sha256
            != self.identity.p32_projection_sha256
            or dynamics.observation_authority != "observation_only"
            or dynamics.mechanism_authority != "candidate_only"
            or dynamics.component_causal_claim_count != 0
            or dynamics.setup_authorized
            or dynamics.terminal_authority != "p19_only"
            or dynamics.graph_id != canonical_dynamics_graph.graph_id
            or dynamics.graph_version != canonical_dynamics_graph.graph_version
            or dynamics.knowledge_version
            != canonical_dynamics_graph.knowledge_version
            or dynamics.knowledge_graph_sha256
            != canonical_dynamics_graph.content_sha256
            or runtime_trust.graph_id != canonical_dynamics_graph.graph_id
            or runtime_trust.graph_version != canonical_dynamics_graph.graph_version
            or runtime_trust.knowledge_version
            != canonical_dynamics_graph.knowledge_version
            or runtime_trust.knowledge_graph_sha256
            != canonical_dynamics_graph.content_sha256
            or dynamics.applicability_state != canonical_resolution.status
            or dynamics.applicability_blockers
            != canonical_resolution.blocker_reasons
        ):
            raise ValueError(
                "P35 assessment must match the atomic non-authoritative Crew workspace"
            )
        measured_opportunities = tuple(
            item
            for item in self.performance_intelligence.opportunity_map.opportunities
            if item.local_delta_s is not None
            and item.source_channels
            and item.source_laps
        )
        loss_opportunities = tuple(
            item
            for item in measured_opportunities
            if (item.local_delta_s or 0.0) > 0.0
        )
        opportunity_cohort = loss_opportunities or measured_opportunities
        leading_opportunity = min(
            opportunity_cohort,
            key=lambda item: (
                -(
                    item.local_delta_s
                    if loss_opportunities
                    else abs(item.local_delta_s or 0.0)
                ),
                item.start_pct,
                item.opportunity_id,
            ),
            default=None,
        )
        expected_opportunity_ids = (
            (leading_opportunity.opportunity_id,)
            if leading_opportunity is not None
            else ()
        )
        expected_mechanism_ids = (
            tuple(dict.fromkeys(leading_opportunity.mechanism_candidates))
            if leading_opportunity is not None
            else ()
        )
        time_stage = dynamics.chain[-1]
        if (
            dynamics.performance_opportunity_ids != expected_opportunity_ids
            or dynamics.p32_performance_mechanism_ids != expected_mechanism_ids
            or (
                leading_opportunity is not None
                and (
                    time_stage.evidence_state != EvidenceState.MEASURED
                    or time_stage.source_artifact_ids
                    != (leading_opportunity.opportunity_id,)
                    or time_stage.source_channels
                    != leading_opportunity.source_channels
                    or not dynamics.measured_time_consequence_available
                )
            )
            or (
                leading_opportunity is None
                and (
                    time_stage.evidence_state != EvidenceState.UNAVAILABLE
                    or time_stage.source_artifact_ids
                    or dynamics.measured_time_consequence_available
                )
            )
        ):
            raise ValueError(
                "P35 must preserve the deterministic leading P32 opportunity and time truth"
            )
        current_phase = (
            _phase_kind(leading_opportunity.phase)
            if leading_opportunity is not None
            else None
        )
        expected_response_regime = (
            _response_regime(current_phase) if current_phase is not None else None
        )
        if dynamics.response_regime != expected_response_regime:
            raise ValueError("P35 response regime must derive from the exact P32 phase")
        current_chain = _matching_chain(
            self.performance_intelligence, leading_opportunity
        )
        current_phase_state = _matching_phase_state(
            current_chain, leading_opportunity
        )
        separation_matched, _separation_blocker = (
            _matched_driver_vehicle_separation(
                current_chain, leading_opportunity
            )
        )
        context_truth = _comparison_context_truth(
            self.performance_intelligence, leading_opportunity
        )
        derived_driver_stage = _driver_input_stage(
            current_chain, current_phase_state
        )
        derived_response_stage = _vehicle_response_stage(
            current_chain, current_phase_state
        )
        positive_states = {
            EvidenceState.MEASURED,
            EvidenceState.CALCULATED,
            EvidenceState.ESTIMATED_PROXY,
            EvidenceState.OBSERVED_CORRELATION,
            EvidenceState.CONTROLLED_TEST_EFFECT,
        }
        support_prerequisites_met = bool(
            context_truth.qualified
            and separation_matched
            and derived_driver_stage.evidence_state in positive_states
            and derived_response_stage.evidence_state in positive_states
        )
        base_support_chain = (
            derived_driver_stage,
            _vehicle_demand_stage(self.performance_intelligence),
            derived_response_stage,
            _tire_platform_stage(
                self.performance_intelligence,
                traffic_blocked=context_truth.traffic_blocked,
                context_blockers=context_truth.blockers,
            ),
            _time_stage(leading_opportunity),
        )
        if dynamics.traffic_blocked != context_truth.traffic_blocked:
            raise ValueError(
                "P35 traffic state must derive from the complete typed P32 context"
            )
        expected_mechanisms = ()
        if (
            dynamics.applicability_state == "ready"
            and leading_opportunity is not None
            and current_phase is not None
            and expected_response_regime is not None
            and leading_opportunity.source_channels
            and len(leading_opportunity.source_laps) >= 2
            and leading_opportunity.local_delta_s != 0.0
        ):
            requested_mechanisms = set(expected_mechanism_ids)
            expected_mechanisms = tuple(
                mechanism
                for mechanism in canonical_dynamics_graph.mechanisms
                if requested_mechanisms.intersection(
                    mechanism.p32_performance_mechanism_ids
                )
                and current_phase in mechanism.relevant_phases
                and leading_opportunity.origin_kind
                in mechanism.allowed_time_origin_kinds
                and (
                    expected_response_regime.value == "both"
                    or mechanism.response_regime.value
                    in {expected_response_regime.value, "both"}
                )
            )[:6]
        if tuple(item.mechanism_id for item in dynamics.candidates) != tuple(
            item.definition_id for item in expected_mechanisms
        ):
            raise ValueError(
                "P35 candidate inventory must equal the canonical graph-filtered cohort"
            )
        trust_by_mechanism = {
            item.mechanism_id: item for item in runtime_trust.mechanisms
        }
        for candidate, mechanism in zip(
            dynamics.candidates, expected_mechanisms, strict=True
        ):
            trust = trust_by_mechanism.get(candidate.mechanism_id)
            expected_p32_ids = tuple(
                mechanism_id
                for mechanism_id in mechanism.p32_performance_mechanism_ids
                if mechanism_id in set(expected_mechanism_ids)
            )
            if (
                trust is None
                or candidate.p32_performance_mechanism_ids != expected_p32_ids
                or candidate.component_family_ids != trust.component_family_ids
                or candidate.discriminator_contract_ids
                != trust.discriminator_observation_contract_ids
                or mechanism.inspection_tool_id != trust.inspection_tool_id
                or mechanism.p20_mechanism_ids != trust.p20_mechanism_ids
                or mechanism.p32_performance_mechanism_ids
                != trust.p32_performance_mechanism_ids
                or mechanism.allowed_time_origin_kinds
                != trust.allowed_time_origin_kinds
                or mechanism.relevant_phases != trust.relevant_phases
                or mechanism.response_regime != trust.response_regime
                or mechanism.p26_component_family_ids
                != trust.component_family_ids
            ):
                raise ValueError(
                    "P35 candidate relationships must match the canonical runtime trust manifest"
                )
        indexed_dynamics = {
            item.artifact_id: item
            for item in self.evidence_index.entries
            if item.producer_id.startswith("p35.")
        }
        focus_by_id = {item.artifact_id: item for item in dynamics.focus_artifacts}
        expected_focus_ids: set[str] = set()
        if leading_opportunity is not None:
            for candidate in dynamics.candidates:
                trust = trust_by_mechanism[candidate.mechanism_id]
                tool_id = trust.inspection_tool_id.value
                uncertainty_id = _focus_id(
                    tool_id,
                    leading_opportunity.opportunity_id,
                    candidate.mechanism_id,
                    "uncertainty",
                )
                if candidate.contradiction_artifact_ids != (uncertainty_id,):
                    raise ValueError(
                        "P35 uncertainty identity must use the canonical producer formula"
                    )
                uncertainty = focus_by_id.get(uncertainty_id)
                if (
                    uncertainty is None
                    or uncertainty.mechanism_id != candidate.mechanism_id
                    or uncertainty.inspection_tool_id != trust.inspection_tool_id
                    or uncertainty.observation_contract_id is not None
                    or uncertainty.stage.value != "tire_platform_state"
                    or uncertainty.polarity != "uncertainty"
                    or uncertainty.source_artifact_ids
                    != (leading_opportunity.opportunity_id,)
                ):
                    raise ValueError(
                        "P35 uncertainty focus must match its canonical mechanism and tool"
                    )
                expected_focus_ids.add(uncertainty_id)

                discriminator_contract_id = (
                    trust.discriminator_observation_contract_ids[0]
                )
                discriminator_id = _focus_id(
                    tool_id,
                    leading_opportunity.opportunity_id,
                    candidate.mechanism_id,
                    discriminator_contract_id,
                    "discriminator",
                )
                discriminator = focus_by_id.get(discriminator_id)
                if (
                    discriminator is None
                    or discriminator.mechanism_id != candidate.mechanism_id
                    or discriminator.inspection_tool_id != trust.inspection_tool_id
                    or discriminator.observation_contract_id
                    != discriminator_contract_id
                    or discriminator_contract_id
                    not in trust.discriminator_observation_contract_ids
                    or discriminator.stage.value != "tire_platform_state"
                    or discriminator.polarity != "neutral"
                    or discriminator.source_artifact_ids
                    != (leading_opportunity.opportunity_id,)
                ):
                    raise ValueError(
                        "P35 discriminator focus must match its canonical contract group"
                    )
                expected_focus_ids.add(discriminator_id)

                if candidate.relevance == "candidate":
                    if len(candidate.support_artifact_ids) != 1:
                        raise ValueError(
                            "unblocked P35 candidates require one canonical support focus"
                        )
                    support_id = candidate.support_artifact_ids[0]
                    support = focus_by_id.get(support_id)
                    if support is None or len(support.source_artifact_ids) != 1:
                        raise ValueError(
                            "P35 support requires one exact producer artifact"
                        )
                    expected_support_id = _focus_id(
                        tool_id,
                        leading_opportunity.opportunity_id,
                        candidate.mechanism_id,
                        support.source_artifact_ids[0],
                        "support",
                    )
                    if (
                        support_id != expected_support_id
                        or support.mechanism_id != candidate.mechanism_id
                        or support.inspection_tool_id != trust.inspection_tool_id
                        or support.observation_contract_id is not None
                        or support.stage.value != "vehicle_response"
                        or support.polarity != "support"
                    ):
                        raise ValueError(
                            "P35 support focus must use the canonical producer formula and tool"
                        )
                    expected_focus_ids.add(support_id)
                elif candidate.support_artifact_ids:
                    raise ValueError("blocked P35 candidates cannot retain support focus")
        if set(focus_by_id) != expected_focus_ids:
            raise ValueError(
                "P35 focus inventory must exactly match canonical candidate evidence"
            )
        leading_candidate = next(
            (
                item
                for item in dynamics.candidates
                if item.relevance == "candidate"
            ),
            dynamics.candidates[0] if dynamics.candidates else None,
        )
        if (
            dynamics.strongest_support_artifact_id
            != (
                leading_candidate.support_artifact_ids[0]
                if leading_candidate is not None
                and leading_candidate.support_artifact_ids
                else None
            )
            or dynamics.strongest_contradiction_artifact_id
            != (
                leading_candidate.contradiction_artifact_ids[0]
                if leading_candidate is not None
                else None
            )
            or dynamics.next_discriminator_contract_id
            != (
                leading_candidate.discriminator_contract_ids[0]
                if leading_candidate is not None
                else None
            )
        ):
            raise ValueError(
                "P35 strongest evidence and next discriminator must follow canonical candidate order"
            )
        if set(indexed_dynamics) != set(focus_by_id):
            raise ValueError(
                "P35 focus artifacts must exactly equal their evidence-index targets"
            )
        qualified_support_mechanisms: set[str] = set()

        def p20_entry_is_projection_owned(
            entry: EngineeringEvidenceIndexEntry,
        ) -> bool:
            """Require a support entry to equal the hashed P20 state that owns it."""

            matched_mechanisms: set[str] = set()
            primary = awareness.primary_state
            if (
                primary is not None
                and entry.artifact_id in primary.source_artifact_ids
                and entry.lap_numbers == (primary.lap_number,)
                and entry.lap_pct_start == primary.lap_pct_start
                and entry.lap_pct_end == primary.lap_pct_end
                and entry.phase == primary.phase
                and entry.evidence_state == primary.evidence_state
                and entry.source_channels == primary.source_channels
            ):
                matched_mechanisms.add(primary.mechanism.value)
            for state in awareness.subsystem_states:
                if (
                    state.status == "ready"
                    and not state.blocker_reasons
                    and entry.artifact_id in state.source_artifact_ids
                    and state.lap_number is not None
                    and entry.lap_numbers == (state.lap_number,)
                    and entry.lap_pct_start == state.lap_pct_start
                    and entry.lap_pct_end == state.lap_pct_end
                    and entry.phase == state.phase
                    and entry.evidence_state == state.evidence_state
                    and entry.source_channels == state.source_channels
                ):
                    matched_mechanisms.add(state.mechanism.value)
            entry_mechanisms = {item.value for item in entry.mechanism_ids}
            return bool(entry_mechanisms) and entry_mechanisms <= matched_mechanisms

        for artifact_id, focus in focus_by_id.items():
            entry = indexed_dynamics[artifact_id]
            source_entries = tuple(
                item
                for item in self.evidence_index.entries
                if item.artifact_id in focus.source_artifact_ids
                and not item.producer_id.startswith("p35.")
            )
            source_windows = tuple(
                dict.fromkeys(
                    (item.lap_pct_start, item.lap_pct_end)
                    for item in source_entries
                )
            )
            source_lap_scopes = tuple(
                dict.fromkeys(item.lap_numbers for item in source_entries)
            )
            source_phases = tuple(
                dict.fromkeys(item.phase for item in source_entries)
            )
            positive_focus = focus.evidence_state in {
                EvidenceState.MEASURED,
                EvidenceState.CALCULATED,
                EvidenceState.ESTIMATED_PROXY,
                EvidenceState.OBSERVED_CORRELATION,
                EvidenceState.CONTROLLED_TEST_EFFECT,
            }
            source_channels = {
                channel for item in source_entries for channel in item.source_channels
            }
            trust = trust_by_mechanism.get(focus.mechanism_id)
            if trust is None:
                raise ValueError("P35 focus mechanism is absent from runtime trust")
            if focus.polarity == "support" and (
                leading_opportunity is None
                or not leading_opportunity.source_laps
                or len(source_entries) != 1
                or source_entries[0].producer_id != "p20.mechanism_observation"
                or not source_entries[0].mechanism_ids
                or any(
                    mechanism_id.value not in trust.p20_mechanism_ids
                    for mechanism_id in source_entries[0].mechanism_ids
                )
                or source_entries[0].lap_numbers
                != (leading_opportunity.source_laps[0],)
                or source_entries[0].lap_pct_start
                != leading_opportunity.start_pct
                or source_entries[0].lap_pct_end != leading_opportunity.end_pct
                or source_entries[0].phase != leading_opportunity.phase
                or source_entries[0].polarity != "support"
                or source_entries[0].evidence_state not in positive_states
                or bool(source_entries[0].blocker_reasons)
                or focus.source_channels != source_entries[0].source_channels
                or not p20_entry_is_projection_owned(source_entries[0])
                or bool(
                    _runtime_support_contract_blockers(
                        trust,
                        base_support_chain,
                        focus.source_channels,
                    )
                )
            ):
                raise ValueError(
                    "P35 support must resolve to the exact hashed P20 mechanism observation"
                )
            if focus.polarity == "support":
                qualified_support_mechanisms.add(focus.mechanism_id)
            if (
                not isinstance(
                    entry.typed_artifact, CrewChiefVehicleDynamicsFocusArtifact
                )
                or entry.typed_artifact.assessment_sha256
                != dynamics.p35_assessment_sha256
                or entry.typed_artifact.focus != focus
                or entry.run_id != self.identity.run_id
                or entry.session_id != self.identity.session_id
                or entry.setup_id != self.identity.setup_id
                or entry.source_run_id != self.identity.run_id
                or entry.source_session_id != self.identity.session_id
                or entry.source_setup_id != self.identity.setup_id
                or entry.source_setup_sha256
                != self.identity.setup_snapshot_sha256
                or entry.source_build_context_sha256
                != self.identity.vehicle_runtime_identity_hash
                or not entry.source_provenance_available
                or entry.authority_ceiling != "observation_only"
                or len(source_entries) != len(focus.source_artifact_ids)
                or len(source_windows) != 1
                or len(source_lap_scopes) != 1
                or len(source_phases) != 1
                or focus.lap_numbers != source_lap_scopes[0]
                or (focus.lap_pct_start, focus.lap_pct_end)
                != source_windows[0]
                or focus.phase != source_phases[0]
                or entry.lap_numbers != focus.lap_numbers
                or (entry.lap_pct_start, entry.lap_pct_end)
                != (focus.lap_pct_start, focus.lap_pct_end)
                or entry.phase != focus.phase
                or not set(focus.source_channels) <= source_channels
                or (
                    positive_focus
                    and any(
                        item.blocker_reasons
                        or item.evidence_state
                        in {
                            EvidenceState.UNAVAILABLE,
                            EvidenceState.BLOCKED_BY_CONTEXT,
                            EvidenceState.NEEDS_CONFIRMATION,
                        }
                        for item in source_entries
                    )
                )
            ):
                raise ValueError(
                    "P35 evidence navigation must preserve exact current provenance"
                )
        for candidate in dynamics.candidates:
            should_be_candidate = bool(
                support_prerequisites_met
                and candidate.mechanism_id in qualified_support_mechanisms
            )
            if (candidate.relevance == "candidate") != should_be_candidate:
                raise ValueError(
                    "P35 candidate relevance must derive from current P20/P32 support gates"
                )
        expected_chain = base_support_chain
        expected_chain = _augment_vehicle_response_with_p20(
            expected_chain, dynamics.focus_artifacts
        )
        if dynamics.chain != expected_chain:
            raise ValueError(
                "P35 five-stage evidence chain must derive exactly from current P20/P32 truth"
            )
        if (
            dynamics.tire_demand_state_ids
            or dynamics.load_path_ids
            or dynamics.unavailable_quantity_ids
            != _runtime_unavailable_quantities(
                canonical_dynamics_graph, self.performance_intelligence
            )
        ):
            raise ValueError(
                "P35 runtime states and unavailable quantities must match the frozen contract"
            )
        candidate_focus_ids = {
            artifact_id
            for candidate in dynamics.candidates
            for artifact_id in (
                *candidate.support_artifact_ids,
                *candidate.contradiction_artifact_ids,
            )
        }
        if not candidate_focus_ids.issubset(focus_by_id):
            raise ValueError(
                "P35 candidate support and contradiction must resolve to focus evidence"
            )
        entry_polarities = {
            artifact_id: indexed_dynamics[artifact_id].polarity
            for artifact_id in indexed_dynamics
        }
        if any(
            entry_polarities[artifact_id] != "support"
            for candidate in dynamics.candidates
            for artifact_id in candidate.support_artifact_ids
        ) or any(
            entry_polarities[artifact_id] != "contradiction"
            for candidate in dynamics.candidates
            for artifact_id in candidate.contradiction_artifact_ids
        ):
            raise ValueError(
                "P35 candidate evidence polarity must match its typed relationship"
            )
        if (
            dynamics.strongest_support_artifact_id is not None
            and entry_polarities[dynamics.strongest_support_artifact_id] != "support"
        ) or (
            dynamics.strongest_contradiction_artifact_id is not None
            and entry_polarities[dynamics.strongest_contradiction_artifact_id]
            != "contradiction"
        ):
            raise ValueError("P35 strongest evidence polarity is inconsistent")
        if dynamics.next_discriminator_contract_id is not None and not any(
            item.observation_contract_id == dynamics.next_discriminator_contract_id
            for item in dynamics.focus_artifacts
        ):
            raise ValueError(
                "P35 next discriminator must resolve to one typed focus artifact"
            )
        prior = self.learning_prior
        if (
            prior.run_id != self.identity.run_id
            or prior.session_id != self.identity.session_id
            or prior.objective_id != self.identity.objective_id.value
            or prior.selected_scope_hash != self.identity.selected_scope_hash
            or prior.p19_reasoning_snapshot_sha256
            != self.identity.reasoning_snapshot_sha256
            or prior.p32_projection_sha256 != self.identity.p32_projection_sha256
            or prior.history_revision != self.identity.learning_history_revision
            or prior.projection_sha256 != self.identity.learning_projection_sha256
            or prior.authority != "attention_only"
            or prior.setup_authorized
            or prior.p19_rank_modified
        ):
            raise ValueError("P33 prior must match the atomic attention-only workspace")
        improvement = self.investigation_improvement
        if (
            improvement.run_id != self.identity.run_id
            or improvement.session_id != self.identity.session_id
            or improvement.workspace_revision != self.identity.workspace_revision
        ):
            raise ValueError(
                "P34 investigation improvement must match the atomic baseline workspace"
            )
        pair = improvement.current_pair
        if pair is not None and (
            pair.investigation_id != self.identity.investigation_id
            or pair.authority_revision != self.identity.authority_revision
            or pair.p19_snapshot_sha256
            != self.identity.reasoning_snapshot_sha256
            or pair.p20_projection_sha256 != self.identity.p20_state_revision
            or pair.p26_projection_sha256
            != self.identity.p26_knowledge_graph_sha256
            or pair.p32_projection_sha256 != self.identity.p32_projection_sha256
            or pair.p33_history_revision
            != self.identity.learning_history_revision
            or pair.p33_ledger_head_sha256
            != self.identity.learning_ledger_head_sha256
            or pair.p33_context_sha256 != prior.current_context_sha256
            or pair.p33_problem_sha256 != prior.current_problem_sha256
        ):
            raise ValueError(
                "P34 paired decision must bind the exact pre-outcome Crew truth"
            )
        if pair is not None:
            if self.folded_state is None or self.folded_state.status != "open":
                raise ValueError("P34 pairs are exclusive to open Crew revisions")
            tool_ids = tuple(
                item.tool_id
                for item in self.available_tools
                if item.tool_id not in _P34_EXCLUDED_INSPECTION_TOOL_IDS
            )
            baseline_decision = pair.baseline_decision
            eligible_tool_ids: tuple[str, ...] = ()
            if baseline_decision.decision_kind == "inspect_tool":
                live = tuple(
                    tool_id
                    for tool_id in _P34_PERFORMANCE_MEASUREMENT_ORDER
                    if tool_id not in set(self.folded_state.completed_tool_ids)
                )
                eligible = [baseline_decision.action_id]
                if (
                    baseline_decision.safe_reorder_group
                    == "performance_measurement"
                    and baseline_decision.action_id in live
                ):
                    position = live.index(baseline_decision.action_id)
                    if position + 1 < len(live):
                        eligible.append(live[position + 1])
                eligible_tool_ids = tuple(eligible)
            artifact_ids = tuple(
                item.artifact_id
                for item in self.evidence_index.entries
                if not item.producer_id.startswith("p35.")
            )
            (
                qualified_artifact_ids,
                qualified_artifact_states,
                qualified_artifact_provenance_sha256s,
            ) = p34_qualified_current_artifact_cohort(
                self.identity,
                self.evidence_index,
            )
            contradiction_ids = self.p19_contradiction_artifact_ids
            if (
                len(contradiction_ids) != len(set(contradiction_ids))
                or not set(contradiction_ids).issubset(artifact_ids)
            ):
                raise ValueError("ranked P19 contradiction identities must be unique")
            current_truth_sha256 = canonical_json_sha256(
                {
                    "identity": self.identity,
                    "evidence_index_sha256": self.evidence_index.index_hash,
                    "terminal_decision": self.terminal_decision,
                    "p19_cause_ids": self.p19_cause_ids,
                    "p19_cause_states": tuple(
                        (item.cause_id, item.p19_state)
                        for item in self.folded_state.hypotheses
                    ),
                    "p19_contradiction_artifact_ids": (
                        self.p19_contradiction_artifact_ids
                    ),
                }
            )
            if (
                pair.step_number != self.folded_state.last_sequence
                or pair.available_tool_ids != tool_ids
                or pair.eligible_tool_ids != eligible_tool_ids
                or pair.completed_tool_ids
                != tuple(
                    tool_id
                    for tool_id in self.folded_state.completed_tool_ids
                    if tool_id not in _P34_EXCLUDED_INSPECTION_TOOL_IDS
                )
                or pair.available_artifact_ids != artifact_ids
                or pair.qualified_available_artifact_ids != qualified_artifact_ids
                or pair.qualified_available_artifact_evidence_states
                != qualified_artifact_states
                or pair.qualified_available_artifact_provenance_sha256s
                != qualified_artifact_provenance_sha256s
                or pair.current_truth_sha256 != current_truth_sha256
                or pair.current_p19_cause_ids != self.p19_cause_ids
                or tuple(
                    (item.cause_id, item.state)
                    for item in pair.current_p19_cause_states
                )
                != tuple(
                    (item.cause_id, item.p19_state)
                    for item in self.folded_state.hypotheses
                )
                or pair.current_contradiction_ids != contradiction_ids
                or pair.strongest_contradiction_id
                != (contradiction_ids[0] if contradiction_ids else None)
                or pair.current_objective != self.identity.objective_id.value
            ):
                raise ValueError("P34 pair does not equal the current Crew evidence")
            production = pair.production_decision
            if self.current_subgoal is not None:
                expected_kind = "inspect_tool"
                expected_action = self.current_subgoal.selected_tool
            elif (
                self.folded_state.pending_driver_question_id is not None
                or not self.folded_state.driver_answers
            ):
                expected_kind = "ask_driver"
                expected_action = (
                    self.folded_state.pending_driver_question_id
                    or "ccq_"
                    + canonical_json_sha256(
                        [
                            self.folded_state.investigation_id,
                            self.folded_state.last_sequence + 1,
                        ]
                    )[:20]
                )
            else:
                expected_kind = (
                    "no_call"
                    if self.terminal_decision.kind == "no_call"
                    else "observe_only"
                )
                expected_action = (
                    f"terminal:{self.terminal_decision.kind}:"
                    f"{canonical_json_sha256([self.terminal_decision.kind, self.terminal_decision.instruction])[:24]}"
                )
            if (
                production.decision_kind != expected_kind
                or production.action_id != expected_action
                or production.decision_kind == "surface_prior"
            ):
                raise ValueError(
                    "Crew production action must equal the exact active P34 decision"
                )
        learning_references = {
            item.reference_id: item
            for item in prior.evidence_references
            if item.state == "available"
        }
        indexed_learning = {
            item.artifact_id: item
            for item in self.evidence_index.entries
            if item.producer_id == "p33.engineering_experience"
        }
        if set(learning_references) != set(indexed_learning):
            raise ValueError(
                "available P33 history must equal its canonical evidence-index targets"
            )
        for reference_id, reference in learning_references.items():
            source = reference.provenance
            entry = indexed_learning[reference_id]
            if (
                entry.run_id != source.run_id
                or entry.session_id != source.session_id
                or entry.setup_id != source.setup_id
                or entry.source_run_id != source.run_id
                or entry.source_session_id != source.session_id
                or entry.source_setup_id != source.setup_id
                or entry.source_setup_sha256 != source.setup_snapshot_sha256
                or entry.source_build_context_sha256 != source.build_context_sha256
                or entry.lap_numbers != source.lap_numbers
                or entry.lap_pct_start != source.lap_pct_start
                or entry.lap_pct_end != source.lap_pct_end
                or entry.phase != source.phase
                or entry.source_channels != source.source_channels
                or entry.evidence_state != source.evidence_state
                or entry.polarity != source.polarity
                or entry.authority_ceiling != "attention_only"
                or entry.typed_artifact is not None
            ):
                raise ValueError(
                    "P33 evidence navigation must preserve exact source provenance"
                )
        for item in (
            self.latest_tool_result,
            self.pending_driver_question,
            self.success_contract,
        ):
            if (
                item is not None
                and item.workspace_revision != self.identity.workspace_revision
            ):
                raise ValueError(
                    "nested Crew Chief artifacts must match workspace revision"
                )
        decision = self.terminal_decision
        if decision.kind == "controlled_test" and (
            decision.workflow_id != self.identity.active_workflow_id
            or decision.workflow_revision != self.identity.active_workflow_revision
        ):
            raise ValueError(
                "controlled decision must match the active workflow revision"
            )
        knowledge = self.engineering_knowledge
        if (
            knowledge.run_id != self.identity.run_id
            or knowledge.session_id != self.identity.session_id
            or knowledge.p19_reasoning_snapshot_sha256
            != self.identity.reasoning_snapshot_sha256
            or knowledge.p20_state_revision != self.identity.p20_state_revision
            or knowledge.p26_knowledge_graph_sha256
            != self.identity.p26_knowledge_graph_sha256
            or knowledge.p32_projection_sha256
            != self.identity.p32_projection_sha256
            or knowledge.p35_assessment_sha256
            != self.identity.p35_assessment_sha256
            or knowledge.p33_projection_sha256
            != self.identity.learning_projection_sha256
            or knowledge.p32_opportunity_id
            != (
                dynamics.performance_opportunity_ids[0]
                if dynamics.performance_opportunity_ids
                else None
            )
            or knowledge.next_discriminator_contract_id
            != dynamics.next_discriminator_contract_id
            or knowledge.terminal_authority != "p19_only"
            or knowledge.non_p19_setup_authorized
        ):
            raise ValueError(
                "P35.1 knowledge must match the atomic P19/P20/P26/P32/P33/P35 workspace"
            )
        from types import SimpleNamespace

        from racelab_engine.services.engineering_knowledge_service import (
            build_current_engineering_knowledge,
        )

        component_partitions: dict[str, str] = {}
        for hypothesis in knowledge.hypotheses:
            for partition, component_ids in (
                ("candidate", hypothesis.current_candidate_component_ids),
                ("supported", hypothesis.current_supported_component_ids),
                ("contradicted", hypothesis.contradicted_component_ids),
                ("blocked", hypothesis.blocked_component_ids),
                ("unobservable", hypothesis.unobservable_component_ids),
                ("irrelevant", hypothesis.irrelevant_component_ids),
            ):
                for component_id in component_ids:
                    prior_partition = component_partitions.setdefault(
                        component_id, partition
                    )
                    if prior_partition != partition:
                        raise ValueError(
                            "P35.2 component relevance must be globally consistent"
                        )

        def _component_state(component_id: str) -> SimpleNamespace:
            partition = component_partitions.get(component_id, "irrelevant")
            return SimpleNamespace(
                component_id=component_id,
                relevance=(
                    "candidate" if partition == "unobservable" else partition
                ),
                observability_states=(
                    ("unavailable",)
                    if partition == "unobservable"
                    else ("measured",)
                ),
                current_response_state=(
                    "unavailable"
                    if partition == "unobservable"
                    else "observed_correlation"
                ),
            )

        expected_knowledge = build_current_engineering_knowledge(
            run_id=self.identity.run_id,
            session_id=self.identity.session_id,
            complaint_prior=(
                self.investigation.raw_driver_report
                if self.investigation is not None
                else None
            ),
            p20=awareness,
            p26=SimpleNamespace(
                run_id=self.identity.run_id,
                session_id=self.identity.session_id,
                reasoning_snapshot_sha256=self.identity.p26_reasoning_snapshot_sha256,
                knowledge_graph_sha256=self.identity.p26_knowledge_graph_sha256,
                component_states=tuple(
                    _component_state(component_id)
                    for component_id in self.p26_component_ids
                ),
                experiment_factors=(
                    (
                        SimpleNamespace(
                            factor_id=decision.experiment_factor_id,
                            primary_controls=(decision.control_key,),
                            coordinated_controls=(),
                        ),
                    )
                    if decision.kind == "controlled_test"
                    and decision.experiment_factor_id is not None
                    and decision.control_key is not None
                    else ()
                ),
            ),
            p32=self.performance_intelligence,
            p35=dynamics,
            p33=prior,
            p19_terminal_decision=decision,
        )
        if knowledge != expected_knowledge:
            raise ValueError(
                "P35.1 knowledge must equal its canonical producer-derived projection"
            )
        return self


__all__ = [
    name
    for name in globals()
    if name.startswith("CrewChief")
    or name
    in {
        "ComponentResponseRecord",
        "DriverDiagnosticQuestion",
        "DriverKnowledgeRecord",
        "EngineeringEvidenceIndex",
        "EngineeringEvidenceIndexEntry",
        "EngineeringObjective",
        "engineering_awareness_scientific_sha256",
        "GenerativeExecutiveBoundary",
        "AdaptiveResearchBoundary",
        "FoldedInvestigationState",
        "HypothesisInspectionState",
        "InvestigationProgress",
        "InvestigationSubgoal",
        "RunSentinelLap",
        "RunSentinelState",
        "SuccessContract",
        "SuccessMetric",
    }
]
