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
