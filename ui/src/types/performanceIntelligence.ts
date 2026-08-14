export type TimeOriginKind =
  | "local_generation"
  | "carried_in"
  | "amplified"
  | "recovered"
  | "surrendered"
  | "unavailable";

export type PerformancePhaseState = {
  phase: string;
  start_pct: number;
  end_pct: number;
  elapsed_delta_s: number | null;
  speed_delta_mph: number | null;
  throttle_delta_pct: number | null;
  brake_delta_pct: number | null;
  steering_delta_deg: number | null;
  yaw_rate_delta: number | null;
  long_accel_delta: number | null;
  path_delta_m: number | null;
  line_separation_m: number | null;
  driver_demand_source_coverage: number | null;
  driver_demand_reference_coverage: number | null;
  evidence_state: "measured" | "unavailable";
  source_channels: string[];
  blockers: string[];
};

export type DriverVehicleSeparation = {
  separation_id: string;
  phase: string;
  driver_demand_changed: boolean | null;
  vehicle_response_changed: boolean | null;
  line_changed: boolean | null;
  context_changed: boolean | null;
  time_changed: boolean | null;
  result:
    | "driver_execution_changed"
    | "vehicle_response_changed_with_matched_inputs"
    | "mixed_change"
    | "context_contaminated"
    | "unresolved";
  support: string[];
  contradictions: string[];
  blockers: string[];
  authority: "observation_only";
};

export type LapTimeOpportunity = {
  opportunity_id: string;
  start_pct: number;
  end_pct: number;
  track_region: string;
  turn: string | null;
  phase: string;
  local_delta_s: number | null;
  cumulative_delta_at_entry_s: number | null;
  cumulative_delta_at_exit_s: number | null;
  origin_kind: TimeOriginKind;
  persistence_distance_pct: number | null;
  following_phase_effect_s: number | null;
  following_phase_start_pct: number | null;
  following_phase_end_pct: number | null;
  repeatability: "repeatable" | "observed_once" | "below_noise" | "blocked";
  noise_basis: string;
  source_laps: number[];
  source_channels: string[];
  driver_execution_state: string;
  vehicle_response_state: string;
  context_state: string;
  attribution_state: "candidate_only" | "blocked_by_traffic" | "blocked_by_context";
  source_traffic_exposure_fraction: number | null;
  reference_traffic_exposure_fraction: number | null;
  mechanism_candidates: string[];
  component_candidates: string[];
  contradictions: string[];
  setup_authorized: false;
};

export type CornerPerformanceChain = {
  chain_id: string;
  track_region: string;
  turn: string | null;
  lap_numbers: number[];
  reference_lap_numbers: number[];
  approach_state: PerformancePhaseState | null;
  braking_state: PerformancePhaseState | null;
  entry_state: PerformancePhaseState | null;
  center_state: PerformancePhaseState | null;
  exit_state: PerformancePhaseState | null;
  carry_state: PerformancePhaseState | null;
  local_time_effect_s: number | null;
  downstream_time_effect_s: number | null;
  driver_vehicle_separation: DriverVehicleSeparation[];
  context: string[];
  contradictions: string[];
  authority: "observation_only";
};

export type PerformanceIntelligenceProjection = {
  schema_version: "p32.performance-intelligence.v1";
  projection_sha256: string;
  run_id: string;
  session_id: string;
  objective_id: string;
  knowledge_version: string;
  principles: Array<{
    principle_id: string;
    statement: string;
    applicable_phases: string[];
    applicable_objectives: string[];
    required_evidence: string[];
    forbidden_claims: string[];
    source_ids: string[];
    authority: "knowledge_only";
  }>;
  mechanisms: Array<{
    mechanism_id: string;
    statement: string;
    operating_phases: string[];
    required_telemetry: string[];
    derived_metrics: string[];
    driver_confounders: string[];
    context_blockers: string[];
    p20_mechanism_families: string[];
    p26_component_families: string[];
    performance_outcomes: string[];
    countereffects: string[];
    forbidden_claims: string[];
    source_ids: string[];
    authority: "knowledge_only";
  }>;
  outcomes: Array<{
    outcome_id: string;
    label: string;
    measured_by: string[];
    protected_outcomes: string[];
    authority: "measurement_only";
  }>;
  objective_envelope: {
    objective_id: string;
    primary_outcomes: string[];
    protected_outcomes: string[];
    countereffect_limits: string[];
    measurement_requirements: string[];
    policy_note: string;
    physics_changes: false;
    setup_authorized: false;
  };
  basis: {
    run_id: string;
    reference_run_id: string | null;
    setup_id: string;
    reference_setup_id: string | null;
    source_lap_numbers: number[];
    reference_lap_numbers: number[];
    physical_alignment_identity: string;
    qualified_phase_segments: number;
    sample_count: number;
    source_channels: string[];
    time_basis: string;
    path_basis: string;
    coverage: number;
    comparison_compatibility: "same_run" | "compatible" | "unavailable";
    context_blockers: string[];
    materialization: "narrow_run_owned_once";
  };
  opportunity_map: {
    run_id: string;
    reference_run_id: string | null;
    setup_id: string;
    reference_setup_id: string | null;
    physical_alignment_identity: string;
    opportunities: LapTimeOpportunity[];
    phase_totals_s: Array<[string, number]>;
    total_measured_delta_s: number | null;
    coverage: number;
    noise_basis: string;
    context_blockers: string[];
    theoretical_composite_s: number | null;
    theoretical_is_guaranteed: false;
    setup_authorized: false;
  };
  corner_chains: CornerPerformanceChain[];
  track_demand: {
    full_throttle_fraction: number | null;
    braking_fraction: number | null;
    cornering_fraction: number | null;
    speed_min_mph: number | null;
    speed_max_mph: number | null;
    median_corner_duration_s: number | null;
    following_straight_carry_lengths_pct: number[];
    combined_acceleration_fraction: number | null;
    platform_load_speed_bands_mph: number[];
    disturbance_exposure_fraction: number | null;
    traffic_exposure_fraction: number | null;
    tire_state_development: "observable" | "short_run" | "unavailable";
    shift_zones: string[];
    limiter_zones: string[];
    shift_limiter_zones: string[];
    dominant_measured_opportunity_ids: string[];
    source_channels: string[];
    blockers: string[];
    authority: "observation_only";
  };
  component_influences: Array<{
    influence_id: string;
    component_id: string;
    performance_mechanism_ids: string[];
    expected_state_ids: string[];
    measurable_through: string[];
    runtime_support_state: "mechanically_relevant" | "response_supported" | "controlled_response_observed";
    source_artifact_ids: string[];
    contradictions: string[];
    authority: "knowledge_only" | "observation_only" | "controlled_history";
    setup_authorized: false;
  }>;
  explanation_chain: {
    chain_id: string;
    node_ids: string[];
    edges: Array<{
      source_id: string;
      target_id: string;
      kind: "observed_precedes" | "co_observed_with" | "measured_time_consequence" | "time_effect_persists_into" | "expected_to_influence" | "controlled_response_observed" | "confounded_by" | "contradicted_by";
    }>;
    branched: boolean;
    strongest_contradiction: string;
    p19_next_move: string;
    setup_authority: "p19_only";
  };
  response_records: Array<{
    record_id: string;
    workflow_id: string;
    context_run_ids: string[];
    control: string;
    component: string;
    expected_state: string;
    observed_state: string;
    time_origin: string;
    time_origin_pct: number | null;
    phase_effect: string;
    phase_effect_s: number | null;
    downstream_carry: string;
    downstream_carry_s: number | null;
    performance_result: string;
    countereffects: string[];
    mechanism_assessment: string;
    control_response_assessment: string;
    policy_verdict: "keep" | "undo" | "retest";
    exact_context: true;
    setup_authorized: false;
  }>;
  speed_story: {
    what_costs_time: string;
    where_it_starts: string;
    what_carries: string;
    driver: string;
    car: string;
    systems: string;
    history: string;
    strongest_contradiction: string;
    next: string;
    observed_difference_s: number | null;
    observed_direction: "loss" | "gain" | "unavailable";
    attribution_state: "candidate_only" | "blocked_by_traffic" | "blocked_by_context" | "unavailable";
    attribution: string;
    source_context: string;
    reference_context: string;
    comparison_window: string;
    authority: "observation_and_p19_projection";
  };
  p19_reasoning_snapshot_sha256: string;
  p20_state_revision: string;
  p26_knowledge_graph_sha256: string;
  component_context_state: "available" | "unavailable";
  component_context_blockers: string[];
  authority: "observation_only";
  setup_authorized: false;
  optimization_state: "data_locked";
  blockers: string[];
};
