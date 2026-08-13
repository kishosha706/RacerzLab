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

const P20_HASH = /^[0-9a-f]{64}$/;
const P20_MECHANISMS = new Set<MechanismKind>([
  "driver_execution", "braking_response", "corner_rotation", "tire_state",
  "damper_response", "platform_response", "resistance_scrub_like",
  "powertrain_response", "stint_trend", "sim_integrity",
]);
const p20Record = (value: unknown): value is Record<string, unknown> => (
  typeof value === "object" && value !== null && !Array.isArray(value)
);
const p20Strings = (value: unknown): value is string[] => (
  Array.isArray(value) && value.every((item) => typeof item === "string" && item.length > 0)
);
const p20Finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

export function isEngineeringAwarenessProjection(
  value: unknown,
  expectation: { runId: string; sessionId: string | null },
): value is EngineeringAwarenessProjection {
  if (!p20Record(value) || !p20Record(value.request_identity) || !p20Record(value.trust_budget)) return false;
  if (value.schema_version !== "p20.awareness.v2"
    || value.run_id !== expectation.runId || value.session_id !== expectation.sessionId
    || value.authority !== "observation_only" || value.raw_trace_included !== false
    || typeof value.state_revision !== "string" || !P20_HASH.test(value.state_revision)
    || typeof value.reasoning_snapshot_id !== "string" || !P20_HASH.test(value.reasoning_snapshot_id)
    || value.request_identity.run_id !== expectation.runId
    || value.request_identity.session_id !== expectation.sessionId
    || value.request_identity.state_revision !== value.state_revision
    || value.request_identity.reasoning_snapshot_id !== value.reasoning_snapshot_id
    || !p20Finite(value.build_duration_ms) || value.build_duration_ms < 0
    || !(value.profile_hash === null || (typeof value.profile_hash === "string" && P20_HASH.test(value.profile_hash)))) return false;
  const trustAxes = [
    "data_health", "alignment_quality", "context_comparability", "driver_repeatability",
    "mechanism_separation", "controlled_response_validity", "policy_countereffect_risk", "history_completeness",
  ];
  const trustBudget = value.trust_budget as Record<string, unknown>;
  if (!trustAxes.every((axis) => {
    const item = trustBudget[axis];
    return p20Record(item) && ["trusted", "limited", "blocked", "unavailable"].includes(String(item.state))
      && typeof item.basis === "string" && item.basis.length > 0
      && p20Strings(item.blockers) && p20Strings(item.source_artifact_ids);
  })) return false;
  if (!Array.isArray(value.subsystem_states) || !value.subsystem_states.every((item) => (
    p20Record(item) && P20_MECHANISMS.has(item.mechanism as MechanismKind)
    && ["ready", "blocked", "no_finding", "unavailable"].includes(String(item.status))
    && item.authority === "observation_only" && p20Strings(item.source_artifact_ids)
    && p20Strings(item.source_channels) && p20Strings(item.blocker_reasons)
  ))) return false;
  if (!Array.isArray(value.episodes) || !value.episodes.every((episode) => (
    p20Record(episode) && episode.run_id === expectation.runId
    && typeof episode.setup_id === "string" && typeof episode.episode_id === "string"
    && p20Finite(episode.lap_pct_start) && p20Finite(episode.lap_pct_end)
    && episode.lap_pct_start >= 0 && episode.lap_pct_end <= 100
    && Array.isArray(episode.lap_scope) && episode.lap_scope.every(Number.isInteger)
    && Array.isArray(episode.supporting_mechanism_kinds)
    && episode.supporting_mechanism_kinds.every((kind) => P20_MECHANISMS.has(kind as MechanismKind))
    && p20Strings(episode.state_frame_ids) && p20Strings(episode.transition_ids)
  ))) return false;
  return p20Strings(value.knowledge_debt)
    && p20Strings(value.state_drift_blocker_reasons)
    && Array.isArray(value.expected_vs_observed)
    && Array.isArray(value.control_mutations)
    && value.control_mutations.every((mutation) => p20Record(mutation)
      && p20Finite(mutation.lap) && p20Finite(mutation.lap_pct))
    && Array.isArray(value.artifact_versions);
}
