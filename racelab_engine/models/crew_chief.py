"""Typed, non-authoritative contracts for the P27-P33 Crew Chief executive.

The executive may decide what to inspect, ask, or measure.  Exact setup and
policy authority remains structurally owned by the canonical P19 snapshot;
P33 history may influence attention order only.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.evidence import EvidenceState
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


class CrewChiefModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


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


class InvestigationProgress(str, Enum):
    UNINSPECTED = "uninspected"
    INSPECTION_PENDING = "inspection_pending"
    INSPECTED = "inspected"
    NEEDS_DRIVER_ANSWER = "needs_driver_answer"
    NEEDS_MEASUREMENT = "needs_measurement"
    COMPLETE = "complete"
    STALE = "stale"


class CrewChiefWorkspaceIdentity(CrewChiefModel):
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    selected_scope_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p20_state_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    p20_profile_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    p26_graph_version: str = Field(min_length=1)
    p26_knowledge_graph_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p26_reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p32_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    learning_history_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    learning_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    setup_id: str = Field(min_length=1)
    setup_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    vehicle_runtime_identity_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_workflow_id: str | None = None
    active_workflow_revision: str | None = None
    objective_id: EngineeringObjective
    investigation_id: str | None = None
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def workflow_identity_is_complete(self) -> CrewChiefWorkspaceIdentity:
        if (self.active_workflow_id is None) != (self.active_workflow_revision is None):
            raise ValueError("workflow identity and revision must be present together")
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
    question_id: str | None = None
    answer: str | None = None
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
            self.event_type not in {"decision_emitted", "investigation_abandoned"}
            and payload.learning_capture_state != "not_applicable"
        ):
            raise ValueError(
                "P33 learning capture metadata is exclusive to terminal Crew events"
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
    hypotheses: tuple[HypothesisInspectionState, ...] = ()
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
    typed_artifact: CrewChiefPerformanceArtifact | None = None
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
        if expected_type is None:
            if self.typed_artifact is not None:
                raise ValueError("only P32 evidence may carry a performance artifact")
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
        return self


class CrewChiefToolDefinition(CrewChiefModel):
    tool_id: str = Field(min_length=1)
    allowed_scope: Literal["run", "session", "component", "workflow"]
    input_schema: str = Field(min_length=1)
    output_artifact_type: str = Field(min_length=1)
    authority_ceiling: Literal["observation_only", "context_only", "measurement_only"]
    required_sources: tuple[str, ...] = ()


class CrewChiefToolResult(CrewChiefModel):
    tool_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["complete", "blocked", "no_finding"]
    summary: str = Field(min_length=1)
    artifact_ids: tuple[str, ...] = ()
    cause_ids: tuple[str, ...] = ()
    component_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    authority_ceiling: Literal["observation_only", "context_only", "measurement_only"]


class InvestigationSubgoal(CrewChiefModel):
    subgoal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    selected_tool: str = Field(min_length=1)
    why_this_tool: str = Field(min_length=1)
    distinguishes_cause_ids: tuple[str, ...] = ()
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
    lap_number: int = Field(ge=0)
    status: Literal["accepted", "rejected"]
    reasons: tuple[str, ...] = ()
    accepted_ordinal: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def accepted_laps_have_an_ordinal(self) -> RunSentinelLap:
        if self.status == "accepted" and (
            self.accepted_ordinal is None or self.reasons
        ):
            raise ValueError(
                "accepted sentinel laps require an ordinal and no rejection"
            )
        if self.status == "rejected" and (
            not self.reasons or self.accepted_ordinal is not None
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
    accepted_laps: int = Field(ge=0)
    collection_complete: bool
    stage: Literal[
        "measurement", "A", "B", "A2", "blocked", "stopped", "awaiting_score"
    ]
    laps: tuple[RunSentinelLap, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def progress_matches_laps(self) -> RunSentinelState:
        if self.accepted_laps != sum(item.status == "accepted" for item in self.laps):
            raise ValueError("sentinel accepted count must match exact lap decisions")
        expected_complete = (
            self.required_laps is not None
            and self.accepted_laps >= self.required_laps
            and self.mission_state
            not in {"blocked_by_p19", "stopped_by_p19", "awaiting_p19_score"}
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
    current_value: str | None = None
    proposed_value: str | None = None
    source_event_ids: tuple[str, ...] = ()
    workflow_id: str | None = None
    workflow_revision: str | None = None
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def setup_fields_are_p19_projection_only(self) -> CrewChiefTerminalDecision:
        setup_values = (self.control_key, self.current_value, self.proposed_value)
        if self.kind == "controlled_test":
            if self.authority != "p19_projection_only" or any(
                value is None for value in setup_values
            ):
                raise ValueError("controlled tests require one complete P19 projection")
            if (
                not self.source_event_ids
                or not self.workflow_id
                or not self.workflow_revision
            ):
                raise ValueError(
                    "controlled tests require exact evidence and workflow revision"
                )
        elif any(value is not None for value in setup_values):
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
    schema_version: Literal["p33.crew-chief-workspace.v1"] = (
        "p33.crew-chief-workspace.v1"
    )
    identity: CrewChiefWorkspaceIdentity
    generated_at: datetime
    cache_state: Literal["cold", "warm"] = "cold"
    investigation: CrewChiefInvestigation | None = None
    folded_state: FoldedInvestigationState | None = None
    evidence_index: EngineeringEvidenceIndex
    available_tools: tuple[CrewChiefToolDefinition, ...]
    current_subgoal: InvestigationSubgoal | None = None
    latest_tool_result: CrewChiefToolResult | None = None
    critique: CrewChiefCritique
    pending_driver_question: DriverDiagnosticQuestion | None = None
    success_contract: SuccessContract | None = None
    p19_mission_contract: MeasurementMissionContract | None = None
    performance_intelligence: PerformanceIntelligenceProjection
    learning_prior: CrewChiefLearningPrior
    run_sentinel: RunSentinelState
    terminal_decision: CrewChiefTerminalDecision
    response_history_ids: tuple[str, ...] = ()
    driver_memory_ids: tuple[str, ...] = ()
    p19_cause_ids: tuple[str, ...] = ()
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
