import type { EvidenceState } from "./telemetry";

export type VehicleDynamicsChainStageKind =
  | "driver_input"
  | "vehicle_demand"
  | "vehicle_response"
  | "tire_platform_state"
  | "time_consequence";

export type VehicleDynamicsResponseRegime = "transient" | "steady_state" | "both";

export type VehicleDynamicsInspectionToolId =
  | "inspect_tire_demand"
  | "inspect_load_transfer"
  | "inspect_roll_response"
  | "inspect_pitch_response"
  | "inspect_platform_state"
  | "inspect_transient_settling"
  | "inspect_steady_state_balance"
  | "inspect_brake_vehicle_response"
  | "inspect_power_on_response"
  | "inspect_differential_response"
  | "inspect_alignment_response"
  | "inspect_tire_state_migration"
  | "inspect_traffic_platform_response"
  | "inspect_gear_acceleration_response";

export type VehicleDynamicsChainStage = {
  stage: VehicleDynamicsChainStageKind;
  evidence_state: EvidenceState;
  source_artifact_ids: string[];
  source_channels: string[];
  summary: string;
  blocker_reasons: string[];
  authority: "observation_only";
};

export type PerformanceMechanismCandidate = {
  mechanism_id: string;
  p32_performance_mechanism_ids: string[];
  support_artifact_ids: string[];
  contradiction_artifact_ids: string[];
  discriminator_contract_ids: string[];
  component_family_ids: string[];
  blocker_reasons: string[];
  relevance: "candidate" | "blocked";
  authority: "candidate_only";
  component_cause_authorized: false;
  setup_authorized: false;
};

export type VehicleDynamicsFocusArtifact = {
  artifact_id: string;
  mechanism_id: string;
  observation_contract_id: string | null;
  inspection_tool_id: VehicleDynamicsInspectionToolId;
  stage: VehicleDynamicsChainStageKind;
  evidence_state: EvidenceState;
  source_artifact_ids: string[];
  source_channels: string[];
  lap_numbers: number[];
  lap_pct_start: number | null;
  lap_pct_end: number | null;
  phase: string | null;
  polarity: "support" | "contradiction" | "uncertainty" | "neutral";
  summary: string;
  blocker_reasons: string[];
  authority: "observation_only";
};

export type PhaseResponseMetric = {
  metric_id: string;
  quantity:
    | "elapsed_time_delta_s"
    | "speed_delta_mph"
    | "throttle_demand_delta_pct"
    | "brake_demand_delta_pct"
    | "steering_wheel_demand_delta_deg"
    | "yaw_rate_response_delta_rad_s"
    | "longitudinal_accel_response_delta_mps2"
    | "path_delta_m"
    | "line_separation_m";
  value: number;
  units: "s" | "mph" | "%" | "deg" | "rad/s" | "m/s^2" | "m";
  semantics: "measured_delta" | "calculated_delta";
  source_channels: string[];
  force_like: false;
  setup_authorized: false;
};

export type VehicleResponseObservation = {
  observation_id: string;
  opportunity_id: string;
  run_id: string;
  source_lap_numbers: number[];
  reference_lap_numbers: number[];
  phase: string;
  lap_pct_start: number;
  lap_pct_end: number;
  onset_pct: number;
  onset_resolution: "phase_boundary" | "canonical_clock";
  response_regime: VehicleDynamicsResponseRegime;
  driver_demand_state: "matched" | "changed" | "mixed" | "unavailable";
  vehicle_response_state: "changed" | "not_established" | "unavailable";
  line_state: "matched" | "changed" | "unavailable";
  context_state: "qualified" | "blocked" | "unavailable";
  persistence: "phase_local" | "carried_forward" | "recovered" | "unavailable";
  metrics: PhaseResponseMetric[];
  source_artifact_ids: string[];
  source_channels: string[];
  blocker_reasons: string[];
  evidence_state: "measured" | "blocked_by_context" | "needs_confirmation";
  authority: "observation_only";
  component_cause_authorized: false;
  setup_authorized: false;
};

export type VehicleProblemSignature = {
  signature_id: string;
  response_observation_id: string;
  opportunity_id: string;
  time_origin: "local_generation" | "carried_in" | "amplified" | "recovered" | "surrendered" | "unavailable";
  local_time_delta_s: number;
  phase: string;
  onset_pct: number;
  onset_resolution: "phase_boundary" | "canonical_clock";
  response_regime: VehicleDynamicsResponseRegime;
  driver_demand_state: "matched" | "changed" | "mixed" | "unavailable";
  vehicle_response_state: "changed" | "not_established" | "unavailable";
  line_state: "matched" | "changed" | "unavailable";
  speed_dependence: "not_established" | "bounded_to_observed_speed_band" | "observed_across_distinct_speed_bands";
  stint_dependence: "not_established" | "observed_migration";
  traffic_dependence: "blocked" | "clear" | "unavailable";
  surface_dependence: "not_established" | "repeated_physical_location";
  front_rear_corner_scope: "unresolved" | "four_corner_observed";
  strongest_contradiction: string;
  authority: "observation_only";
  component_cause_authorized: false;
  setup_authorized: false;
};

export type MechanismSeparationRow = {
  mechanism_id: string;
  response_observation_id: string;
  required_response_kpi_ids: string[];
  support_artifact_ids: string[];
  response_evidence_ids: string[];
  contradiction_artifact_ids: string[];
  missing_evidence: string[];
  discriminator_contract_ids: string[];
  protected_countereffects: string[];
  component_family_ids: string[];
  state: "alive" | "weakened" | "blocked";
  authority: "candidate_only";
  setup_authorized: false;
};

export type OperationalResponseMetric = {
  metric_id: string;
  label: string;
  value: number;
  units: string;
  lap_number: number | null;
  corner: "lf" | "rf" | "lr" | "rr" | null;
  source_channels: string[];
  authority: "observation_only";
  setup_authorized: false;
};

export type OperationalResponseEvidence = {
  evidence_id: string;
  relation: "brake_to_pressure" | "brake_to_deceleration" | "brake_to_yaw" | "brake_release_to_yaw" | "throttle_to_acceleration" | "throttle_to_yaw" | "steering_wheel_to_yaw" | "disturbance_to_chassis" | "stint_migration";
  phase: string;
  lap_pct_start: number;
  lap_pct_end: number;
  onset_pct: number;
  repetition_count: number;
  source_lap_numbers: number[];
  source_artifact_ids: string[];
  source_channels: string[];
  metrics: OperationalResponseMetric[];
  speed_min_mps: number | null;
  speed_median_mps: number | null;
  speed_max_mps: number | null;
  evidence_state: "calculated" | "observed_correlation";
  authority: "observation_only";
  cause_authorized: false;
  setup_authorized: false;
};

export type PerformanceMechanismAssessment = {
  schema_version: "p35.performance-mechanism-assessment.v1";
  p35_assessment_sha256: string;
  run_id: string;
  session_id: string;
  objective_id: string;
  car_path: string;
  car_version: string;
  iracing_build_version: string;
  track_package: string;
  vehicle_runtime_identity_sha256: string;
  graph_id: string;
  graph_version: string;
  knowledge_version: string;
  knowledge_graph_sha256: string;
  p19_reasoning_snapshot_sha256: string;
  p20_state_revision: string;
  p20_profile_hash: string | null;
  p26_graph_version: string;
  p26_knowledge_graph_sha256: string;
  p32_projection_sha256: string;
  p32_performance_mechanism_ids: string[];
  performance_opportunity_ids: string[];
  measured_time_consequence_available: boolean;
  chain: VehicleDynamicsChainStage[];
  tire_demand_state_ids: string[];
  load_path_ids: string[];
  response_regime: VehicleDynamicsResponseRegime | null;
  response_observations: VehicleResponseObservation[];
  problem_signature: VehicleProblemSignature | null;
  operational_response_evidence: OperationalResponseEvidence[];
  mechanism_separation: MechanismSeparationRow[];
  candidates: PerformanceMechanismCandidate[];
  focus_artifacts: VehicleDynamicsFocusArtifact[];
  strongest_support_artifact_id: string | null;
  strongest_contradiction_artifact_id: string | null;
  next_discriminator_contract_id: string | null;
  unavailable_quantity_ids: string[];
  traffic_blocked: boolean;
  applicability_state: "ready" | "unavailable" | "incompatible" | "unreviewed_build";
  applicability_blockers: string[];
  blocker_reasons: string[];
  observation_authority: "observation_only";
  mechanism_authority: "candidate_only";
  component_causal_claim_count: 0;
  setup_authorized: false;
  terminal_authority: "p19_only";
};
