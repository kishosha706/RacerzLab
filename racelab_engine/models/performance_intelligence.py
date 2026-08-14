"""P32 measured lap-time mechanics and speed-intelligence contracts.

P32 explains measured elapsed-time consequences.  It does not simulate an
optimal lap, estimate unavailable forces, establish observational causation,
or authorize setup changes.  P19 remains the only setup-policy authority.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PerformanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TimeOriginKind(str, Enum):
    LOCAL_GENERATION = "local_generation"
    CARRIED_IN = "carried_in"
    AMPLIFIED = "amplified"
    RECOVERED = "recovered"
    SURRENDERED = "surrendered"
    UNAVAILABLE = "unavailable"


class DriverVehicleResult(str, Enum):
    DRIVER_EXECUTION_CHANGED = "driver_execution_changed"
    VEHICLE_RESPONSE_CHANGED_WITH_MATCHED_INPUTS = (
        "vehicle_response_changed_with_matched_inputs"
    )
    MIXED_CHANGE = "mixed_change"
    CONTEXT_CONTAMINATED = "context_contaminated"
    UNRESOLVED = "unresolved"


class PerformancePrinciple(PerformanceModel):
    principle_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    applicable_phases: tuple[str, ...] = Field(min_length=1)
    applicable_objectives: tuple[str, ...] = Field(min_length=1)
    required_evidence: tuple[str, ...] = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["knowledge_only"] = "knowledge_only"


class PerformanceMechanismDefinition(PerformanceModel):
    mechanism_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    operating_phases: tuple[str, ...] = Field(min_length=1)
    required_telemetry: tuple[str, ...] = Field(min_length=1)
    derived_metrics: tuple[str, ...] = Field(min_length=1)
    driver_confounders: tuple[str, ...] = Field(min_length=1)
    context_blockers: tuple[str, ...] = Field(min_length=1)
    p20_mechanism_families: tuple[str, ...] = ()
    p26_component_families: tuple[str, ...] = ()
    performance_outcomes: tuple[str, ...] = Field(min_length=1)
    countereffects: tuple[str, ...] = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["knowledge_only"] = "knowledge_only"


class PerformanceOutcome(PerformanceModel):
    outcome_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    measured_by: tuple[str, ...] = Field(min_length=1)
    protected_outcomes: tuple[str, ...] = ()
    authority: Literal["measurement_only"] = "measurement_only"


class PerformanceObjectiveEnvelope(PerformanceModel):
    objective_id: str = Field(min_length=1)
    primary_outcomes: tuple[str, ...] = Field(min_length=1)
    protected_outcomes: tuple[str, ...] = Field(min_length=1)
    countereffect_limits: tuple[str, ...] = Field(min_length=1)
    measurement_requirements: tuple[str, ...] = Field(min_length=1)
    policy_note: str = Field(min_length=1)
    physics_changes: Literal[False] = False
    setup_authorized: Literal[False] = False


class RunPerformanceBasis(PerformanceModel):
    run_id: str = Field(min_length=1)
    reference_run_id: str | None = Field(default=None, min_length=1)
    setup_id: str = Field(min_length=1)
    reference_setup_id: str | None = Field(default=None, min_length=1)
    source_lap_numbers: tuple[int, ...] = ()
    reference_lap_numbers: tuple[int, ...] = ()
    physical_alignment_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualified_phase_segments: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    source_channels: tuple[str, ...] = ()
    time_basis: str = Field(min_length=1)
    path_basis: str = Field(min_length=1)
    coverage: float = Field(ge=0, le=1, allow_inf_nan=False)
    comparison_compatibility: Literal["same_run", "compatible", "unavailable"] = (
        "unavailable"
    )
    context_blockers: tuple[str, ...] = ()
    materialization: Literal["narrow_run_owned_once"] = "narrow_run_owned_once"


class TrackDemandProfile(PerformanceModel):
    full_throttle_fraction: float | None = Field(default=None, ge=0, le=1)
    braking_fraction: float | None = Field(default=None, ge=0, le=1)
    cornering_fraction: float | None = Field(default=None, ge=0, le=1)
    speed_min_mph: float | None = Field(default=None, ge=0)
    speed_max_mph: float | None = Field(default=None, ge=0)
    median_corner_duration_s: float | None = Field(default=None, ge=0)
    following_straight_carry_lengths_pct: tuple[float, ...] = ()
    combined_acceleration_fraction: float | None = Field(default=None, ge=0, le=1)
    platform_load_speed_bands_mph: tuple[float, ...] = ()
    disturbance_exposure_fraction: float | None = Field(default=None, ge=0, le=1)
    traffic_exposure_fraction: float | None = Field(default=None, ge=0, le=1)
    tire_state_development: Literal["observable", "short_run", "unavailable"]
    shift_zones: tuple[str, ...] = ()
    limiter_zones: tuple[str, ...] = ()
    # Retained for wire compatibility.  It contains limiter candidates only;
    # ordinary gear changes live in ``shift_zones``.
    shift_limiter_zones: tuple[str, ...] = ()
    dominant_measured_opportunity_ids: tuple[str, ...] = ()
    source_channels: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def legacy_limiter_view_is_truthful(self) -> TrackDemandProfile:
        if self.shift_limiter_zones != self.limiter_zones:
            raise ValueError("shift_limiter_zones may contain limiter candidates only")
        return self


class PerformancePhaseState(PerformanceModel):
    phase: str = Field(min_length=1)
    start_pct: float = Field(ge=0, le=100)
    end_pct: float = Field(ge=0, le=100)
    elapsed_delta_s: float | None = Field(default=None, allow_inf_nan=False)
    speed_delta_mph: float | None = Field(default=None, allow_inf_nan=False)
    throttle_delta_pct: float | None = Field(default=None, allow_inf_nan=False)
    brake_delta_pct: float | None = Field(default=None, allow_inf_nan=False)
    steering_delta_deg: float | None = Field(default=None, allow_inf_nan=False)
    yaw_rate_delta: float | None = Field(default=None, allow_inf_nan=False)
    long_accel_delta: float | None = Field(default=None, allow_inf_nan=False)
    path_delta_m: float | None = Field(default=None, allow_inf_nan=False)
    line_separation_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    driver_demand_source_coverage: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    driver_demand_reference_coverage: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    evidence_state: Literal["measured", "unavailable"]
    source_channels: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def window_and_state_match(self) -> PerformancePhaseState:
        if self.end_pct < self.start_pct:
            raise ValueError("performance phase window is reversed")
        measured = any(
            value is not None
            for value in (
                self.elapsed_delta_s,
                self.speed_delta_mph,
                self.throttle_delta_pct,
                self.brake_delta_pct,
                self.steering_delta_deg,
                self.yaw_rate_delta,
                self.long_accel_delta,
                self.path_delta_m,
                self.line_separation_m,
            )
        )
        if (self.evidence_state == "measured") != measured:
            raise ValueError(
                "performance phase evidence state must match measured values"
            )
        if self.evidence_state == "unavailable" and not self.blockers:
            raise ValueError("unavailable phase state requires blockers")
        return self


class DriverVehicleSeparation(PerformanceModel):
    separation_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    driver_demand_changed: bool | None
    vehicle_response_changed: bool | None
    line_changed: bool | None
    context_changed: bool | None
    time_changed: bool | None
    result: DriverVehicleResult
    support: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def contaminated_or_unresolved_has_debt(self) -> DriverVehicleSeparation:
        if (
            self.result
            in {
                DriverVehicleResult.CONTEXT_CONTAMINATED,
                DriverVehicleResult.UNRESOLVED,
            }
            and not self.blockers
        ):
            raise ValueError("contaminated or unresolved separation requires blockers")
        return self


class LapTimeOpportunity(PerformanceModel):
    opportunity_id: str = Field(min_length=1)
    start_pct: float = Field(ge=0, le=100)
    end_pct: float = Field(ge=0, le=100)
    track_region: str = Field(min_length=1)
    turn: str | None = None
    phase: str = Field(min_length=1)
    local_delta_s: float | None = Field(default=None, allow_inf_nan=False)
    cumulative_delta_at_entry_s: float | None = Field(default=None, allow_inf_nan=False)
    cumulative_delta_at_exit_s: float | None = Field(default=None, allow_inf_nan=False)
    origin_kind: TimeOriginKind
    persistence_distance_pct: float | None = Field(default=None, ge=0, le=100)
    following_phase_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    following_phase_start_pct: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False
    )
    following_phase_end_pct: float | None = Field(
        default=None, ge=0, le=100, allow_inf_nan=False
    )
    repeatability: Literal["repeatable", "observed_once", "below_noise", "blocked"]
    noise_basis: str = Field(min_length=1)
    source_laps: tuple[int, ...] = ()
    source_channels: tuple[str, ...] = ()
    driver_execution_state: str = Field(min_length=1)
    vehicle_response_state: str = Field(min_length=1)
    context_state: str = Field(min_length=1)
    attribution_state: Literal[
        "candidate_only",
        "blocked_by_traffic",
        "blocked_by_context",
    ] = "candidate_only"
    source_traffic_exposure_fraction: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    reference_traffic_exposure_fraction: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    mechanism_candidates: tuple[str, ...] = ()
    component_candidates: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = Field(min_length=1)
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def opportunity_is_elapsed_time_not_peak_speed(self) -> LapTimeOpportunity:
        if self.end_pct < self.start_pct:
            raise ValueError("opportunity physical window is reversed")
        if (
            self.origin_kind is TimeOriginKind.UNAVAILABLE
            and self.local_delta_s is not None
        ):
            raise ValueError("unavailable origins cannot publish a local time effect")
        if self.attribution_state == "blocked_by_traffic" and not any(
            "traffic" in item.casefold() for item in self.contradictions
        ):
            raise ValueError("traffic-blocked opportunity requires a traffic contradiction")
        if self.attribution_state.startswith("blocked_by_") and self.component_candidates:
            raise ValueError(
                "context-blocked opportunities cannot publish component candidates"
            )
        if self.attribution_state != "candidate_only" and self.component_candidates:
            raise ValueError(
                "context-blocked opportunity cannot publish component candidates"
            )
        following_scope = (
            self.following_phase_start_pct,
            self.following_phase_end_pct,
        )
        if self.following_phase_effect_s is None:
            if any(value is not None for value in following_scope):
                raise ValueError(
                    "following-phase scope cannot exist without a measured carry effect"
                )
        elif any(value is None for value in following_scope):
            raise ValueError(
                "measured following-phase carry requires its exact physical window"
            )
        elif self.following_phase_end_pct < self.following_phase_start_pct:
            raise ValueError("following-phase physical window is reversed")
        return self


class LapTimeOpportunityMap(PerformanceModel):
    run_id: str = Field(min_length=1)
    reference_run_id: str | None = Field(default=None, min_length=1)
    setup_id: str = Field(min_length=1)
    reference_setup_id: str | None = Field(default=None, min_length=1)
    physical_alignment_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    opportunities: tuple[LapTimeOpportunity, ...] = ()
    phase_totals_s: tuple[tuple[str, float], ...] = ()
    total_measured_delta_s: float | None = Field(default=None, allow_inf_nan=False)
    coverage: float = Field(ge=0, le=1)
    noise_basis: str = Field(min_length=1)
    context_blockers: tuple[str, ...] = ()
    theoretical_composite_s: float | None = Field(default=None, ge=0)
    theoretical_is_guaranteed: Literal[False] = False
    setup_authorized: Literal[False] = False


class CornerPerformanceChain(PerformanceModel):
    chain_id: str = Field(min_length=1)
    track_region: str = Field(min_length=1)
    turn: str | None = None
    lap_numbers: tuple[int, ...] = ()
    reference_lap_numbers: tuple[int, ...] = ()
    approach_state: PerformancePhaseState | None = None
    braking_state: PerformancePhaseState | None = None
    entry_state: PerformancePhaseState | None = None
    center_state: PerformancePhaseState | None = None
    exit_state: PerformancePhaseState | None = None
    carry_state: PerformancePhaseState | None = None
    local_time_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    downstream_time_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    driver_vehicle_separation: tuple[DriverVehicleSeparation, ...] = ()
    context: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = Field(min_length=1)
    authority: Literal["observation_only"] = "observation_only"


class ComponentPerformanceInfluence(PerformanceModel):
    influence_id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    performance_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    expected_state_ids: tuple[str, ...] = Field(min_length=1)
    measurable_through: tuple[str, ...] = Field(min_length=1)
    runtime_support_state: Literal[
        "mechanically_relevant", "response_supported", "controlled_response_observed"
    ]
    source_artifact_ids: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = Field(min_length=1)
    authority: Literal["knowledge_only", "observation_only", "controlled_history"]
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def support_state_matches_authority(self) -> ComponentPerformanceInfluence:
        expected = {
            "mechanically_relevant": "knowledge_only",
            "response_supported": "observation_only",
            "controlled_response_observed": "controlled_history",
        }[self.runtime_support_state]
        if self.authority != expected:
            raise ValueError(
                "component performance support cannot exceed its evidence authority"
            )
        return self


class PerformanceExplanationEdge(PerformanceModel):
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    kind: Literal[
        "observed_precedes",
        "co_observed_with",
        "measured_time_consequence",
        "time_effect_persists_into",
        "expected_to_influence",
        "controlled_response_observed",
        "confounded_by",
        "contradicted_by",
    ]


class PerformanceExplanationChain(PerformanceModel):
    chain_id: str = Field(min_length=1)
    node_ids: tuple[str, ...] = Field(min_length=1)
    edges: tuple[PerformanceExplanationEdge, ...] = ()
    branched: bool = False
    strongest_contradiction: str = Field(min_length=1)
    p19_next_move: str = Field(min_length=1)
    setup_authority: Literal["p19_only"] = "p19_only"


class PerformanceResponseRecord(PerformanceModel):
    record_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    context_run_ids: tuple[str, ...] = Field(min_length=1)
    control: str = Field(min_length=1)
    component: str = Field(min_length=1)
    expected_state: str = Field(min_length=1)
    observed_state: str = Field(min_length=1)
    time_origin: str = Field(min_length=1)
    time_origin_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    phase_effect: str = Field(min_length=1)
    phase_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    downstream_carry: str = Field(min_length=1)
    downstream_carry_s: float | None = Field(default=None, allow_inf_nan=False)
    performance_result: str = Field(min_length=1)
    countereffects: tuple[str, ...] = ()
    mechanism_assessment: str = Field(min_length=1)
    control_response_assessment: str = Field(min_length=1)
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    exact_context: bool
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def only_exact_valid_history_is_publishable(self) -> PerformanceResponseRecord:
        if not self.exact_context or self.policy_verdict == "invalid":
            raise ValueError(
                "P32 response records require exact non-invalid controlled history"
            )
        if (self.time_origin_pct is None) != (
            self.time_origin == "not_materialized_in_legacy_record"
        ):
            raise ValueError("P32 response time-origin value and position disagree")
        if (self.downstream_carry_s is None) != (
            self.downstream_carry == "not_materialized_in_legacy_record"
        ):
            raise ValueError("P32 response carry label and measured value disagree")
        return self


class SpeedStory(PerformanceModel):
    what_costs_time: str = Field(min_length=1)
    where_it_starts: str = Field(min_length=1)
    what_carries: str = Field(min_length=1)
    driver: str = Field(min_length=1)
    car: str = Field(min_length=1)
    systems: str = Field(min_length=1)
    history: str = Field(min_length=1)
    strongest_contradiction: str = Field(min_length=1)
    next: str = Field(min_length=1)
    observed_difference_s: float | None = Field(default=None, allow_inf_nan=False)
    observed_direction: Literal["loss", "gain", "unavailable"] = "unavailable"
    attribution_state: Literal[
        "candidate_only",
        "blocked_by_traffic",
        "blocked_by_context",
        "unavailable",
    ] = "unavailable"
    attribution: str = "Attribution unavailable."
    source_context: str = "Source context unavailable."
    reference_context: str = "Reference context unavailable."
    comparison_window: str = "Comparison window unavailable."
    authority: Literal["observation_and_p19_projection"] = (
        "observation_and_p19_projection"
    )

    @model_validator(mode="after")
    def story_cannot_smuggle_setup_authority(self) -> SpeedStory:
        text = " ".join(
            (
                self.what_costs_time,
                self.where_it_starts,
                self.what_carries,
                self.driver,
                self.car,
                self.systems,
                self.history,
                self.strongest_contradiction,
            )
        ).casefold()
        forbidden = ("optimal setup", "guaranteed achievable")
        if any(term in text for term in forbidden):
            raise ValueError(
                "Speed Story cannot claim optimization, guarantee, or causation"
            )
        causal_patterns = (
            r"\bcaused?\b",
            r"\bdue to\b",
            r"\bbecause of\b",
            r"\bproves?\b",
            r"\bcreated? (?:the |this )?(?:loss|gain|deficit|time)\b",
            r"\bproduc(?:e|ed|es|ing)\b",
            r"\bgenerat(?:e|ed|es|ing)\b",
            r"\bresult(?:ed|s|ing)?\s+(?:in|from)\b",
            r"\bresponsible for\b",
        )
        stripped = re.sub(
            r"\b(?:does not|do not|did not|cannot|can not|is not|are not|was not|were not|no|none is)\s+(?:establish(?:ed)?|prove(?:d)?|show(?:n)?|claim(?:ed)?)?\s*(?:as )?(?:a |the )?(?:component )?(?:cause|causation)\b",
            " ",
            text,
        )
        stripped = re.sub(
            r"\b(?:does not|do not|did not|cannot|can not|is not|are not|was not|were not)\s+"
            r"(?:produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from))\b",
            " ",
            stripped,
        )
        if any(re.search(pattern, stripped) for pattern in causal_patterns):
            raise ValueError("Speed Story cannot claim affirmative causation")
        if self.observed_difference_s is None:
            if self.observed_direction != "unavailable":
                raise ValueError("missing observed difference requires unavailable direction")
        elif self.observed_difference_s > 0 and self.observed_direction != "loss":
            raise ValueError("positive elapsed-time difference must be a loss")
        elif self.observed_difference_s < 0 and self.observed_direction != "gain":
            raise ValueError("negative elapsed-time difference must be a gain")
        elif self.observed_difference_s == 0 and self.observed_direction != "unavailable":
            raise ValueError("zero elapsed-time difference has no gain/loss direction")
        if self.attribution_state.startswith("blocked_by_"):
            if "blocked" not in self.attribution.casefold():
                raise ValueError("blocked Speed Story requires explicit attribution language")
            if "costs" in self.what_costs_time.casefold():
                raise ValueError(
                    "blocked observed differences cannot be narrated as attributable costs"
                )
        if self.attribution_state == "blocked_by_traffic" and "traffic" not in (
            self.strongest_contradiction.casefold()
        ):
            raise ValueError("traffic must be the strongest contradiction when it blocks attribution")
        return self


class PerformanceIntelligenceProjection(PerformanceModel):
    schema_version: Literal["p32.performance-intelligence.v1"] = (
        "p32.performance-intelligence.v1"
    )
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    knowledge_version: str = Field(min_length=1)
    principles: tuple[PerformancePrinciple, ...] = Field(min_length=12, max_length=12)
    mechanisms: tuple[PerformanceMechanismDefinition, ...] = Field(min_length=1)
    outcomes: tuple[PerformanceOutcome, ...] = Field(min_length=1)
    objective_envelope: PerformanceObjectiveEnvelope
    basis: RunPerformanceBasis
    opportunity_map: LapTimeOpportunityMap
    corner_chains: tuple[CornerPerformanceChain, ...] = ()
    track_demand: TrackDemandProfile
    component_influences: tuple[ComponentPerformanceInfluence, ...] = ()
    explanation_chain: PerformanceExplanationChain
    response_records: tuple[PerformanceResponseRecord, ...] = ()
    speed_story: SpeedStory
    p19_reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p20_state_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    p26_knowledge_graph_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    component_context_state: Literal["available", "unavailable"] = "available"
    component_context_blockers: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"
    setup_authorized: Literal[False] = False
    optimization_state: Literal["data_locked"] = "data_locked"
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def nested_scope_and_identity_are_atomic(self) -> PerformanceIntelligenceProjection:
        if (
            self.basis.run_id != self.run_id
            or self.opportunity_map.run_id != self.run_id
            or self.basis.physical_alignment_identity
            != self.opportunity_map.physical_alignment_identity
            or self.objective_envelope.objective_id != self.objective_id
        ):
            raise ValueError(
                "P32 nested artifacts must share one exact run/objective basis"
            )
        principle_ids = [item.principle_id for item in self.principles]
        mechanism_ids = [item.mechanism_id for item in self.mechanisms]
        if len(principle_ids) != len(set(principle_ids)) or len(mechanism_ids) != len(
            set(mechanism_ids)
        ):
            raise ValueError("P32 knowledge identities must be unique")
        if self.component_context_state == "unavailable":
            if self.component_influences or self.response_records:
                raise ValueError(
                    "unavailable P26 context cannot emit component influence or history"
                )
            if not self.component_context_blockers:
                raise ValueError("unavailable P26 context requires an explicit blocker")
        elif self.component_context_blockers:
            raise ValueError("available P26 context cannot carry availability blockers")
        return self


__all__ = [name for name in globals() if not name.startswith("_")]
