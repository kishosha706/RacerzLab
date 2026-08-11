from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import (
    DriverRepeatabilitySignature,
    MechanismObservationReport,
    OpportunitySignatureReport,
    SameSetupAnomalyReport,
)
from racelab_engine.models.session_intelligence import (
    HypothesisLifecycle,
    SessionEngineeringLedger,
)
from racelab_engine.models.smart_guidance import (
    AttentionItem,
    ControlledTestPreflight,
    MeasurementDebt,
    NextTrustworthyMove,
)
from racelab_engine.models.telemetry_health import TelemetryHealthBaselineReport
from racelab_engine.models.vehicle_systems import VehicleSystemsProjection

WITHHELD_STAGE_B_PREFLIGHT_TITLE = "Controlled workflow needs review"
WITHHELD_STAGE_B_PREFLIGHT_BLOCKER = (
    "The current report does not authorize this Stage B setup target."
)
WITHHELD_STAGE_B_PREFLIGHT_CHECK_LABEL = "Current controlled-test authority"
WITHHELD_STAGE_B_PREFLIGHT_CHECK_DETAIL = (
    "Do not record Stage B. Review, abandon, or rebuild this workflow from the "
    "current evidence-qualified report."
)
WITHHELD_STAGE_B_MOVE_TITLE = "Review the blocked controlled workflow"
WITHHELD_STAGE_B_MOVE_INSTRUCTION = (
    "Open Dial-In to review, abandon, or rebuild this workflow. Do not record "
    "Stage B from a withheld card."
)
WITHHELD_STAGE_B_MOVE_REASON = (
    "The exact Stage B target is withheld until current source-run evidence and "
    "workflow authority agree."
)


class IntelligenceApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


CitationWorkspace = Literal[
    "overview",
    "laps",
    "platform_trace",
    "speed_delta",
    "drag_scrub",
    "setup_impact",
    "dial_in",
]


class IntelligenceCitationResponse(IntelligenceApiModel):
    citation_id: str
    label: str
    run_id: str
    lap_number: int | None = None
    lap_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    event_id: str | None = None
    workspace: CitationWorkspace
    source_channels: list[str] = Field(default_factory=list)
    evidence_state: EvidenceState
    valid_for_tuning: bool = False
    track_region_id: str | None = None
    track_region_label: str | None = None
    track_region_phase: Literal["entry", "center", "exit", "straight"] | None = None
    track_region_confidence: Literal["section_geometry", "centerline_geometry"] | None = None


class IntelligenceActionResponse(IntelligenceApiModel):
    kind: Literal["controlled_test", "measurement_mission", "driver_focus", "no_call"]
    title: str
    instruction: str
    setup_authorized: bool = False
    control_key: str | None = None
    current_value: str | None = None
    proposed_value: str | None = None
    evidence_state: EvidenceState
    source_event_ids: list[str] = Field(default_factory=list)
    mission_contract_id: str | None = None
    mission_contract_sha256: str | None = None
    blocker_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def exact_setup_values_require_server_authorization(self) -> IntelligenceActionResponse:
        exact_values = (self.control_key, self.current_value, self.proposed_value)
        if (
            len(set(self.source_event_ids)) != len(self.source_event_ids)
            or any(
                not event_id or event_id.strip() != event_id
                for event_id in self.source_event_ids
            )
        ):
            raise ValueError("action source-event identities must be canonical and unique")
        if self.setup_authorized:
            if self.kind != "controlled_test" or any(
                not isinstance(value, str) or not value or value.strip() != value
                for value in exact_values
            ):
                raise ValueError("authorized setup actions require one complete controlled-test target")
            if not self.source_event_ids or self.blocker_reasons:
                raise ValueError("authorized setup actions require linked evidence and no blockers")
        elif any(value is not None for value in exact_values):
            raise ValueError("unauthorized actions cannot publish exact setup values")
        if (self.mission_contract_id is None) != (self.mission_contract_sha256 is None):
            raise ValueError("measurement contract identity and hash must be paired")
        return self


class MeasurementAttemptRequest(IntelligenceApiModel):
    session_id: str | None = Field(default=None, max_length=160)
    contract_id: str = Field(min_length=1, max_length=160)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_run_id: str | None = Field(default=None, min_length=1, max_length=160)
    outcome: Literal[
        "completed_clean",
        "no_signal",
        "failed_integrity",
        "infeasible",
        "abandoned",
    ]
    eligible_lap_ids: list[str] = Field(default_factory=list)
    observed_channels: list[str] = Field(default_factory=list)
    integrity_blockers: list[str] = Field(default_factory=list)
    outcome_reasons: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def attempt_identity_is_canonical(self) -> MeasurementAttemptRequest:
        for values, label in (
            (self.eligible_lap_ids, "eligible lap"),
            (self.observed_channels, "observed channel"),
            (self.integrity_blockers, "integrity blocker"),
            (self.outcome_reasons, "outcome reason"),
        ):
            if any(not value or value != value.strip() for value in values):
                raise ValueError(f"measurement-attempt {label} values must be canonical")
            if len(set(values)) != len(values):
                raise ValueError(f"measurement-attempt {label} values must be unique")
        return self


class MeasurementAttemptResponse(IntelligenceApiModel):
    attempt_id: str
    contract_id: str
    contract_sha256: str
    outcome: str


class IntelligenceBriefingResponse(IntelligenceApiModel):
    issue: str | None = None
    action: IntelligenceActionResponse
    success_check: str | None = None
    confidence_label: str | None = None
    blocker_reasons: list[str] = Field(default_factory=list)


class IntelligenceCauseResponse(IntelligenceApiModel):
    cause_id: str
    label: str
    state: Literal["leading", "possible", "ruled_out", "unresolved"]
    rank: int = Field(ge=1)
    evidence_state: EvidenceState
    reason: str
    evidence_for: list[IntelligenceCitationResponse] = Field(default_factory=list)
    evidence_against: list[IntelligenceCitationResponse] = Field(default_factory=list)


class IntelligenceMindChangeCriterionResponse(IntelligenceApiModel):
    criterion_id: str = Field(min_length=1)
    cause_id: str = Field(min_length=1)
    current_state: Literal["leading", "possible", "ruled_out", "unresolved"]
    evidence_kind: Literal["controlled_test", "measurement_mission", "discriminator"]
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    metric: str = Field(min_length=1)
    phase: Literal["braking", "entry", "center", "exit", "straight"]
    control_key: str | None = None
    threshold_source: str = Field(min_length=1)
    acceptance_conditions: list[str] = Field(min_length=1)
    falsification_conditions: list[str] = Field(min_length=1)
    minimum_independent_evidence_units: int = Field(ge=2)
    minimum_evidence: str = Field(min_length=1)
    requires_aba2: bool = False
    minimum_laps_per_stage: int | None = Field(default=None, ge=3)
    countereffects: list[str] = Field(default_factory=list)
    next_state_if_accepted: Literal["leading", "possible", "ruled_out", "unresolved"]
    next_state_if_falsified: Literal["leading", "possible", "ruled_out", "unresolved"]
    next_state_if_inconclusive: Literal["unresolved"] = "unresolved"
    source_event_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def criterion_is_complete_and_non_authorizing(
        self,
    ) -> IntelligenceMindChangeCriterionResponse:
        for values, label in (
            (self.acceptance_conditions, "acceptance condition"),
            (self.falsification_conditions, "falsification condition"),
            (self.countereffects, "countereffect"),
            (self.source_event_ids, "source event"),
        ):
            if any(not value or value.strip() != value for value in values) or len(
                values
            ) != len(set(values)):
                raise ValueError(
                    f"mind-change {label} values must be canonical and unique"
                )
        if self.requires_aba2:
            if (
                self.minimum_laps_per_stage is None
                or self.minimum_independent_evidence_units < 9
            ):
                raise ValueError("A/B/A2 criteria require three stages and at least nine laps")
        elif self.minimum_laps_per_stage is not None:
            raise ValueError("only A/B/A2 criteria may declare laps per stage")
        return self


class IntelligenceMeasurementResponse(IntelligenceApiModel):
    mission_id: str
    title: str
    purpose: str
    procedure: list[str] = Field(default_factory=list)
    required_laps: int | None = Field(default=None, ge=0)
    acceptance_threshold: str | None = None
    stop_rule: str | None = None
    controlled_variables: list[str] = Field(default_factory=list)
    citations: list[IntelligenceCitationResponse] = Field(default_factory=list)


class IntelligenceContextMatchResponse(IntelligenceApiModel):
    memory_id: str
    label: str
    relevance_label: str
    outcome_summary: str
    verdict: str
    matching_context: list[str] = Field(default_factory=list)
    mismatches: list[str] = Field(default_factory=list)
    citations: list[IntelligenceCitationResponse] = Field(default_factory=list)


class IntelligenceCalibrationResponse(IntelligenceApiModel):
    status: Literal["available", "insufficient_history"]
    summary: str
    qualified_correct: int | None = Field(default=None, ge=0)
    qualified_total: int | None = Field(default=None, ge=0)
    caveat: str

    @model_validator(mode="after")
    def observed_counts_are_consistent(self) -> IntelligenceCalibrationResponse:
        if (
            self.qualified_correct is not None
            and self.qualified_total is not None
            and self.qualified_correct > self.qualified_total
        ):
            raise ValueError("matching predictions cannot exceed graded predictions")
        return self


class IntelligenceNarrativeEntryResponse(IntelligenceApiModel):
    entry_id: str
    label: str
    summary: str
    outcome: str | None = None
    created_at: str | None = None
    citations: list[IntelligenceCitationResponse] = Field(default_factory=list)


class IntelligenceGraphNodeResponse(IntelligenceApiModel):
    node_id: str
    label: str
    kind: Literal["claim", "cause", "evidence", "blocker", "test"]
    evidence_state: EvidenceState | None = None
    citation_id: str | None = None


class IntelligenceGraphEdgeResponse(IntelligenceApiModel):
    source_id: str
    target_id: str
    relation: Literal["supports", "contradicts", "tests", "blocks"]


class IntelligenceEvidenceGraphResponse(IntelligenceApiModel):
    nodes: list[IntelligenceGraphNodeResponse] = Field(default_factory=list)
    edges: list[IntelligenceGraphEdgeResponse] = Field(default_factory=list)


class IntelligenceDataQualityResponse(IntelligenceApiModel):
    status: Literal["ready", "limited", "blocked"]
    summary: str
    eligible_laps: int = Field(ge=0)
    total_laps: int = Field(ge=0)
    trusted_events: int = Field(ge=0)
    issues: list[str] = Field(default_factory=list)
    recovery_steps: list[str] = Field(default_factory=list)
    citations: list[IntelligenceCitationResponse] = Field(default_factory=list)


class IntelligenceDriverProfileResponse(IntelligenceApiModel):
    preferred_mode: str | None = None
    terminology_level: str | None = None
    recurring_symptoms: list[str] = Field(default_factory=list)
    controlled_tests_completed: int = Field(default=0, ge=0)
    consistency_label: str | None = None
    affects_evidence_eligibility: Literal[False] = False


class RunIntelligenceResponse(IntelligenceApiModel):
    run_id: str
    session_id: str | None = None
    status: Literal["ready", "unavailable"]
    decision_status: Literal["ready", "measure", "blocked"]
    generated_at: str | None = None
    briefing: IntelligenceBriefingResponse
    competing_causes: list[IntelligenceCauseResponse] = Field(default_factory=list)
    mind_change_criteria: list[IntelligenceMindChangeCriterionResponse] = Field(
        default_factory=list
    )
    best_measurement: IntelligenceMeasurementResponse | None = None
    context_matches: list[IntelligenceContextMatchResponse] = Field(default_factory=list)
    calibration: IntelligenceCalibrationResponse
    narrative: list[IntelligenceNarrativeEntryResponse] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
    evidence_graph: IntelligenceEvidenceGraphResponse | None = None
    data_quality: IntelligenceDataQualityResponse | None = None
    driver_profile: IntelligenceDriverProfileResponse | None = None
    mission_stage: Literal[
        "qualify", "diagnose", "measure", "test", "compare", "decide", "certified"
    ] | None = None
    next_trustworthy_move: NextTrustworthyMove | None = None
    test_preflight: ControlledTestPreflight | None = None
    measurement_debt: MeasurementDebt | None = None
    attention_items: list[AttentionItem] = Field(default_factory=list)
    session_ledger: SessionEngineeringLedger | None = None
    hypothesis_lifecycle: HypothesisLifecycle | None = None
    opportunity_signature: OpportunitySignatureReport | None = None
    mechanism_observations: MechanismObservationReport | None = None
    anomalies: SameSetupAnomalyReport | None = None
    driver_focus: DriverRepeatabilitySignature | None = None
    telemetry_health: TelemetryHealthBaselineReport | None = None
    vehicle_systems: VehicleSystemsProjection | None = None

    @model_validator(mode="after")
    def mind_change_criteria_match_report_scope(self) -> RunIntelligenceResponse:
        if self.status != "ready" and self.decision_status == "ready":
            raise ValueError("an unavailable report cannot publish a ready decision")
        action = self.briefing.action
        if self.vehicle_systems is not None:
            if (
                self.vehicle_systems.run_id != self.run_id
                or self.vehicle_systems.session_id != self.session_id
                or self.vehicle_systems.setup_authorized != action.setup_authorized
            ):
                raise ValueError("vehicle-system projection must match report scope and authority")
            authorized_controls = {
                state.authorized_control_key
                for state in self.vehicle_systems.component_states
                if state.setup_authorized
            }
            if action.setup_authorized and authorized_controls != {action.control_key}:
                raise ValueError("vehicle-system projection must mirror the exact P19 control")
        action_event_ids = set(action.source_event_ids)
        qualified_states = {
            EvidenceState.MEASURED,
            EvidenceState.CALCULATED,
            EvidenceState.ESTIMATED_PROXY,
            EvidenceState.OBSERVED_CORRELATION,
            EvidenceState.CONTROLLED_TEST_EFFECT,
        }
        if action.setup_authorized and (
            self.status != "ready"
            or self.decision_status != "ready"
            or self.data_quality is None
            or self.data_quality.status != "ready"
            or self.data_quality.issues
            or self.blocker_reasons
            or self.briefing.blocker_reasons
            or action.blocker_reasons
            or action.evidence_state
            not in {*qualified_states, EvidenceState.NEEDS_CONFIRMATION}
        ):
            raise ValueError(
                "setup authorization requires a ready report, decision, and data-quality "
                "state with no report, briefing, quality, or action blockers"
            )
        report_citations = [
            citation
            for cause in self.competing_causes
            for citation in (*cause.evidence_for, *cause.evidence_against)
        ]
        if self.best_measurement is not None:
            report_citations.extend(self.best_measurement.citations)
        report_citations.extend(
            citation
            for context in self.context_matches
            for citation in context.citations
        )
        report_citations.extend(
            citation
            for entry in self.narrative
            for citation in entry.citations
        )
        if self.data_quality is not None:
            report_citations.extend(self.data_quality.citations)
        qualified_action_event_ids = {
            citation.event_id
            for citation in report_citations
            if citation.run_id == self.run_id
            and citation.event_id in action_event_ids
            and citation.valid_for_tuning
            and citation.source_channels
            and len(citation.source_channels) == len(set(citation.source_channels))
            and all(
                channel and channel.strip() == channel
                for channel in citation.source_channels
            )
            and citation.evidence_state in qualified_states
        }
        if action.setup_authorized and qualified_action_event_ids != action_event_ids:
            raise ValueError(
                "setup authorization requires the exact current-run tuning citation set"
            )
        controlled_measurement = bool(
            self.best_measurement is not None
            and self.best_measurement.mission_id.startswith("controlled-test:")
        )
        if action.setup_authorized and not controlled_measurement:
            raise ValueError(
                "setup authorization requires the exact controlled-test measurement protocol"
            )
        if controlled_measurement:
            assert self.best_measurement is not None
            measurement = self.best_measurement
            exact_values = (
                action.control_key,
                action.current_value,
                action.proposed_value,
            )
            expected_instruction = (
                f"{action.current_value} -> {action.proposed_value} "
                "(adjacent observed tech-passing option)"
            )
            control_spec = SETUP_CONTROL_SPECS.get(action.control_key or "")
            label = control_spec.label if control_spec is not None else None
            controlled_variable = (
                measurement.controlled_variables[0]
                if len(measurement.controlled_variables) == 1
                else None
            )
            expected_procedure = (
                [
                    f"Keep {label} at the recorded baseline value.",
                    f"Change only {label}: {action.instruction}.",
                    f"Keep {label} at the recorded baseline value.",
                ]
                if label is not None
                else None
            )
            measurement_citations = measurement.citations
            if (
                not action.setup_authorized
                or any(value is None for value in exact_values)
                or action.instruction != expected_instruction
                or measurement.mission_id != f"controlled-test:{action.control_key}"
                or measurement.procedure != expected_procedure
                or measurement.required_laps is None
                or measurement.required_laps < 1
                or not measurement.acceptance_threshold
                or measurement.acceptance_threshold.strip()
                != measurement.acceptance_threshold
                or not measurement.stop_rule
                or measurement.stop_rule.strip() != measurement.stop_rule
                or controlled_variable != f"Change only {label}."
                or len(measurement_citations) != len(action.source_event_ids)
                or {
                    citation.event_id for citation in measurement_citations
                } != action_event_ids
                or any(
                    citation.event_id is None
                    or citation.run_id != self.run_id
                    or not citation.valid_for_tuning
                    or citation.evidence_state not in qualified_states
                    or not citation.source_channels
                    or len(citation.source_channels) != len(set(citation.source_channels))
                    or any(
                        not channel or channel.strip() != channel
                        for channel in citation.source_channels
                    )
                    for citation in measurement_citations
                )
            ):
                raise ValueError(
                    "controlled-test measurement detail requires the exact authorized action"
                )
        move = self.next_trustworthy_move
        preflight = self.test_preflight
        if (
            move is not None
            and move.authority == "setup_authorized"
            and (
                not action.setup_authorized
                or move.run_id != self.run_id
                or move.instruction != action.instruction
                or move.control_key != action.control_key
                or len(move.source_event_ids) != len(action.source_event_ids)
                or set(move.source_event_ids) != action_event_ids
                or preflight is None
                or preflight.status != "ready"
                or preflight.workflow_id != move.workflow_id
            )
        ):
            raise ValueError(
                "setup-authorized guidance must match the exact current action and workflow"
            )
        workflow_bound = bool(
            preflight is not None
            or (
                move is not None
                and (move.workflow_id is not None or move.workflow_updated_at is not None)
            )
        )
        if action.setup_authorized and workflow_bound:
            setup_checks = (
                [check for check in preflight.checks if check.check_id == "setup-state"]
                if preflight is not None
                else []
            )
            expected_stage_b = (
                self.best_measurement.procedure[1]
                if self.best_measurement is not None
                and len(self.best_measurement.procedure) == 3
                else None
            )
            if (
                self.mission_stage != "test"
                or preflight is None
                or preflight.stage != "B"
                or preflight.status != "ready"
                or preflight.blocker_reasons
                or len(setup_checks) != 1
                or setup_checks[0].state != "required"
                or setup_checks[0].detail != expected_stage_b
                or move is None
                or move.authority != "setup_authorized"
                or move.workflow_id != preflight.workflow_id
                or move.workflow_updated_at is None
                or move.run_id != self.run_id
                or move.instruction != action.instruction
                or move.control_key != action.control_key
                or len(move.source_event_ids) != len(action.source_event_ids)
                or set(move.source_event_ids) != action_event_ids
                or move.blocker_reasons
            ):
                raise ValueError(
                    "setup-authorized guidance must match the exact ready Stage B workflow revision"
                )
        if preflight is not None and preflight.stage == "B" and not action.setup_authorized:
            checks = list(preflight.checks)
            if (
                self.mission_stage != "measure"
                or preflight.status != "blocked"
                or preflight.title != WITHHELD_STAGE_B_PREFLIGHT_TITLE
                or list(preflight.blocker_reasons)
                != [WITHHELD_STAGE_B_PREFLIGHT_BLOCKER]
                or len(checks) != 1
                or checks[0].check_id != "current-card-authority"
                or checks[0].label != WITHHELD_STAGE_B_PREFLIGHT_CHECK_LABEL
                or checks[0].state != "blocked"
                or checks[0].detail != WITHHELD_STAGE_B_PREFLIGHT_CHECK_DETAIL
            ):
                raise ValueError(
                    "unauthorized Stage B preflight must be blocked and redact exact setup detail"
                )
            if move is not None and (
                move.move_id != f"review-withheld:{preflight.workflow_id}:B"
                or move.kind != "recover"
                or move.title != WITHHELD_STAGE_B_MOVE_TITLE
                or move.instruction != WITHHELD_STAGE_B_MOVE_INSTRUCTION
                or move.reason != WITHHELD_STAGE_B_MOVE_REASON
                or move.workspace != "dial_in"
                or move.authority != "navigation_only"
                or move.run_id != self.run_id
                or move.workflow_id != preflight.workflow_id
                or move.workflow_updated_at is None
                or move.control_key is not None
                or move.source_event_ids
                or list(move.blocker_reasons)
                != [WITHHELD_STAGE_B_PREFLIGHT_BLOCKER]
            ):
                raise ValueError(
                    "unauthorized Stage B guidance must expose only canonical recovery"
                )
        cause_ids = {cause.cause_id for cause in self.competing_causes}
        criterion_ids = [item.criterion_id for item in self.mind_change_criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("mind-change criterion identities must be unique")
        if any(
            item.cause_id not in cause_ids
            or item.run_id != self.run_id
            or item.session_id != self.session_id
            for item in self.mind_change_criteria
        ):
            raise ValueError("mind-change criteria must match exact report cause and scope")
        return self


class IntelligenceQueryRequest(IntelligenceApiModel):
    question: str = Field(min_length=2, max_length=500)
    session_id: str | None = Field(default=None, max_length=160)
    selected_lap: int | None = Field(default=None, ge=1)
    selected_window_start_lap: int | None = Field(default=None, ge=1)
    selected_window_end_lap: int | None = Field(default=None, ge=1)
    selected_window_representative_lap: int | None = Field(default=None, ge=1)
    presentation_mode: Literal["race", "learning"] | None = None

    @model_validator(mode="after")
    def selected_scope_is_exact(self) -> IntelligenceQueryRequest:
        window_values = (
            self.selected_window_start_lap,
            self.selected_window_end_lap,
            self.selected_window_representative_lap,
        )
        supplied = [value is not None for value in window_values]
        if any(supplied) and not all(supplied):
            raise ValueError(
                "selected lap windows require start, end, and representative laps"
            )
        if all(supplied):
            start = self.selected_window_start_lap
            end = self.selected_window_end_lap
            representative = self.selected_window_representative_lap
            assert start is not None and end is not None and representative is not None
            if start > end or not start <= representative <= end:
                raise ValueError(
                    "selected lap windows require ordered bounds containing the representative lap"
                )
            if self.selected_lap != representative:
                raise ValueError(
                    "selected_lap must identify the selected window representative"
                )
        return self


class IntelligenceNavigationResponse(IntelligenceApiModel):
    """A navigation-only handoff. It never carries setup authority."""

    workspace: CitationWorkspace
    run_id: str = Field(min_length=1, max_length=160)
    lap_number: int | None = Field(default=None, ge=1)
    event_id: str | None = Field(default=None, min_length=1, max_length=240)
    lap_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class IntelligenceQueryResponse(IntelligenceApiModel):
    run_id: str
    session_id: str | None = None
    scope_run_ids: list[str] = Field(min_length=1)
    selected_lap: int | None = Field(default=None, ge=1)
    status: Literal["ready", "unavailable"]
    question: str
    headline: str
    answer: str
    interpreted_lap_number: int | None = Field(default=None, ge=1)
    interpreted_window_start_lap: int | None = Field(default=None, ge=1)
    interpreted_window_end_lap: int | None = Field(default=None, ge=1)
    interpreted_window_representative_lap: int | None = Field(default=None, ge=1)
    interpreted_phase: Literal["braking", "entry", "center", "exit", "straight"] | None = None
    interpreted_control_key: str | None = None
    interpreted_component_id: str | None = Field(
        default=None, min_length=1, max_length=120
    )
    interpreted_track_region_id: str | None = None
    interpreted_track_region_label: str | None = None
    clarification_required: bool = False
    action_authorized: bool = False
    action_source_event_ids: list[str] = Field(default_factory=list)
    evidence_state: EvidenceState
    citations: list[IntelligenceCitationResponse] = Field(default_factory=list)
    suggested_navigation: list[IntelligenceNavigationResponse] = Field(default_factory=list)
    mind_change_criteria: list[IntelligenceMindChangeCriterionResponse] = Field(
        default_factory=list
    )
    blocker_reasons: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def query_scope_and_authority_require_exact_citations(
        self,
    ) -> IntelligenceQueryResponse:
        if self.interpreted_component_id is not None and (
            self.interpreted_component_id.strip() != self.interpreted_component_id
        ):
            raise ValueError("interpreted component identity must be canonical")
        if (self.interpreted_track_region_id is None) != (
            self.interpreted_track_region_label is None
        ):
            raise ValueError("interpreted track-region identity and label must be supplied together")
        if (
            any(not run_id or run_id.strip() != run_id for run_id in self.scope_run_ids)
            or len(set(self.scope_run_ids)) != len(self.scope_run_ids)
            or self.run_id not in self.scope_run_ids
        ):
            raise ValueError("query run scope must be canonical, unique, and include the current run")
        if self.session_id is None and self.scope_run_ids != [self.run_id]:
            raise ValueError("run-only queries cannot admit cross-run evidence")
        if (self.interpreted_window_start_lap is None) != (
            self.interpreted_window_end_lap is None
        ):
            raise ValueError("interpreted query windows require both lap bounds")
        window_start = self.interpreted_window_start_lap
        window_end = self.interpreted_window_end_lap
        if window_start is not None and window_end is not None:
            if window_start > window_end:
                raise ValueError("interpreted query windows require ordered lap bounds")
            if self.selected_lap is not None and not (
                window_start <= self.selected_lap <= window_end
            ):
                raise ValueError("the selected representative lap must belong to the query window")
            if self.interpreted_lap_number is not None and not (
                window_start <= self.interpreted_lap_number <= window_end
            ):
                raise ValueError("the interpreted representative lap must belong to the query window")
            if self.interpreted_window_representative_lap is None:
                raise ValueError("interpreted query windows require an exact representative lap")
            if not (
                window_start
                <= self.interpreted_window_representative_lap
                <= window_end
            ):
                raise ValueError(
                    "the interpreted window representative must belong to the query window"
                )
            if self.selected_lap != self.interpreted_window_representative_lap:
                raise ValueError(
                    "the selected lap must match the interpreted window representative"
                )
        elif self.interpreted_window_representative_lap is not None:
            raise ValueError(
                "an interpreted window representative requires exact window bounds"
            )
        if (
            self.status == "ready"
            and self.selected_lap is not None
            and window_start is None
            and self.interpreted_lap_number != self.selected_lap
        ):
            raise ValueError("the interpreted representative lap must match the selected lap")

        scoped_lap = self.selected_lap or self.interpreted_lap_number
        if any(citation.run_id not in self.scope_run_ids for citation in self.citations):
            raise ValueError("query citations must belong to the exact run/session scope")
        current_run_citations = [
            citation for citation in self.citations if citation.run_id == self.run_id
        ]
        historical_citations = [
            citation for citation in self.citations if citation.run_id != self.run_id
        ]
        if (window_start is not None or scoped_lap is not None) and historical_citations:
            raise ValueError("lap-scoped query citations must belong to the current run")
        if window_start is not None and window_end is not None:
            if any(
                citation.lap_number is None
                or citation.lap_number < window_start
                or citation.lap_number > window_end
                for citation in current_run_citations
            ):
                raise ValueError("query citations must stay inside the interpreted lap window")
        elif scoped_lap is not None and any(
            citation.lap_number != scoped_lap for citation in self.citations
        ):
            raise ValueError("query citations must match the requested run and lap")

        current_run_navigation = [
            target for target in self.suggested_navigation if target.run_id == self.run_id
        ]
        if any(
            target.run_id not in self.scope_run_ids
            for target in self.suggested_navigation
        ):
            raise ValueError("query navigation must belong to the exact run/session scope")
        if window_start is not None and window_end is not None:
            if any(
                target.lap_number is not None
                and not window_start <= target.lap_number <= window_end
                for target in current_run_navigation
            ):
                raise ValueError("query navigation must stay inside the interpreted lap window")
        elif scoped_lap is not None and any(
            target.lap_number is not None and target.lap_number != scoped_lap
            for target in current_run_navigation
        ):
            raise ValueError("query navigation must match the requested lap")

        navigation_identities = [
            (
                target.workspace,
                target.run_id,
                target.lap_number,
                target.event_id,
                target.lap_pct,
            )
            for target in self.suggested_navigation
        ]
        if len(set(navigation_identities)) != len(navigation_identities):
            raise ValueError("query navigation targets must be unique")

        source_event_ids = self.action_source_event_ids
        cited_event_ids = [
            citation.event_id for citation in self.citations if citation.event_id is not None
        ]
        if self.action_authorized and (
            self.status != "ready"
            or self.clarification_required
            or self.blocker_reasons
            or self.evidence_state
            not in {
                EvidenceState.MEASURED,
                EvidenceState.CALCULATED,
                EvidenceState.ESTIMATED_PROXY,
                EvidenceState.OBSERVED_CORRELATION,
                EvidenceState.CONTROLLED_TEST_EFFECT,
            }
        ):
            raise ValueError(
                "authorized query actions require a ready, unambiguous, unblocked qualified answer"
            )
        if self.action_authorized and (
            not self.citations
            or any(
                citation.run_id != self.run_id
                or not citation.valid_for_tuning
                or citation.event_id is None
                or not citation.source_channels
                or citation.evidence_state
                not in {
                    EvidenceState.MEASURED,
                    EvidenceState.CALCULATED,
                    EvidenceState.ESTIMATED_PROXY,
                    EvidenceState.OBSERVED_CORRELATION,
                    EvidenceState.CONTROLLED_TEST_EFFECT,
                }
                for citation in self.citations
            )
        ):
            raise ValueError("authorized query actions require exact tuning citations")
        if self.action_authorized and (
            not source_event_ids
            or len(set(source_event_ids)) != len(source_event_ids)
            or any(not event_id or event_id.strip() != event_id for event_id in source_event_ids)
            or len(cited_event_ids) != len(source_event_ids)
            or set(cited_event_ids) != set(source_event_ids)
        ):
            raise ValueError("authorized query actions require the exact source event set")
        if not self.action_authorized and source_event_ids:
            raise ValueError("unauthorized query answers cannot publish action source events")
        criterion_ids = [item.criterion_id for item in self.mind_change_criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("mind-change criterion identities must be unique")
        if any(
            item.run_id != self.run_id or item.session_id != self.session_id
            for item in self.mind_change_criteria
        ):
            raise ValueError("mind-change criteria must match exact query scope")
        if self.clarification_required and self.mind_change_criteria:
            raise ValueError("ambiguous queries cannot publish mind-change criteria")
        if self.action_authorized and self.mind_change_criteria:
            raise ValueError("mind-change criteria cannot grant setup authority")
        return self


__all__ = [
    "IntelligenceMindChangeCriterionResponse",
    "IntelligenceNavigationResponse",
    "IntelligenceQueryRequest",
    "IntelligenceQueryResponse",
    "MeasurementAttemptRequest",
    "MeasurementAttemptResponse",
    "RunIntelligenceResponse",
]
