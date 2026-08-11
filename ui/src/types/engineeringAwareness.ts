import type { EvidenceState } from "./telemetry";

export type MechanismKind =
  | "driver_execution" | "braking_response" | "corner_rotation" | "tire_state"
  | "damper_response" | "platform_response" | "resistance_scrub_like"
  | "powertrain_response" | "stint_trend" | "sim_integrity";

export type TrustAxis = {
  state: "trusted" | "limited" | "blocked" | "unavailable";
  basis: string;
  blockers: string[];
  source_artifact_ids: string[];
};

export type TrustBudget = {
  data_health: TrustAxis;
  alignment_quality: TrustAxis;
  context_comparability: TrustAxis;
  driver_repeatability: TrustAxis;
  mechanism_separation: TrustAxis;
  controlled_response_validity: TrustAxis;
  policy_countereffect_risk: TrustAxis;
  history_completeness: TrustAxis;
};

export type PrimaryEngineeringState = {
  state_id: string;
  label: string;
  mechanism: MechanismKind;
  lap_number: number;
  phase: string;
  lap_pct_start: number;
  lap_pct_end: number;
  lap_pct_peak: number;
  evidence_state: EvidenceState;
  source_artifact_ids: string[];
  source_channels: string[];
  authority: "observation_only";
};

export type SubsystemAwarenessState = {
  mechanism: MechanismKind;
  status: "ready" | "blocked" | "no_finding" | "unavailable";
  summary: string;
  phase: string | null;
  lap_number: number | null;
  lap_pct_start: number | null;
  lap_pct_end: number | null;
  evidence_state: EvidenceState;
  source_artifact_ids: string[];
  source_channels: string[];
  blocker_reasons: string[];
  authority: "observation_only";
};

export type MechanismEpisode = {
  episode_id: string;
  run_id: string;
  setup_id: string;
  context_id: string;
  lap_scope: number[];
  phase: string;
  lap_pct_start: number;
  lap_pct_end: number;
  lap_pct_peak: number;
  state_frame_ids: string[];
  transition_ids: string[];
  supporting_mechanism_kinds: MechanismKind[];
  contradicting_mechanism_kinds: MechanismKind[];
  context_blockers: string[];
};

export type ExpectedVsObservedState = {
  workflow_id: string;
  control_key: string | null;
  metric: string;
  phase: string;
  mechanism_state: "supported" | "weakened" | "unchanged" | "inconclusive" | "invalid";
  control_response: "matched" | "missed" | "inconclusive" | "unavailable" | "invalid";
  mechanism_reason: string;
  control_response_reason: string;
};

export type EngineeringAwarenessProjection = {
  schema_version: "p20.awareness.v2";
  run_id: string;
  session_id: string | null;
  reasoning_snapshot_id: string;
  state_revision: string;
  request_identity: { run_id: string; session_id: string | null; reasoning_snapshot_id: string; state_revision: string };
  generated_at: string;
  cache_state: "cold" | "warm";
  build_duration_ms: number;
  profile_hash: string | null;
  authority: "observation_only";
  trust_budget: TrustBudget;
  primary_state: PrimaryEngineeringState | null;
  subsystem_states: SubsystemAwarenessState[];
  episodes: MechanismEpisode[];
  state_drift_status: "ready" | "no_finding" | "blocked" | "unavailable";
  state_drift_findings: unknown[];
  state_drift_blocker_reasons: string[];
  expected_vs_observed: ExpectedVsObservedState[];
  control_mutations: { mutation_id: string; control_key: string; mutation_kind: string; lap: number; lap_pct: number }[];
  knowledge_debt: string[];
  artifact_versions: { artifact_key: string; version: string }[];
  raw_trace_included: false;
};
