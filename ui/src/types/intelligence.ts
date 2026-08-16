import type { EvidenceState } from "./telemetry";
import type { VehicleSystemComponentId, VehicleSystemsProjection } from "./vehicleSystems";
import type { Workspace } from "../store/types";

export type IntelligenceStatus = "ready" | "unavailable";
export type IntelligenceDecisionStatus = "ready" | "measure" | "blocked";

export type IntelligenceCitationWorkspace = Extract<
  Workspace,
  "overview" | "laps" | "platform_trace" | "speed_delta" | "drag_scrub" | "setup_impact" | "dial_in"
>;

/** Exact, navigable provenance for a Smart Engineer claim. */
export type IntelligenceCitation = {
  citation_id: string;
  label: string;
  run_id: string;
  lap_number?: number | null;
  lap_pct?: number | null;
  event_id?: string | null;
  workspace: IntelligenceCitationWorkspace;
  source_channels: string[];
  evidence_state: EvidenceState;
  valid_for_tuning: boolean;
  phase: "braking" | "entry" | "center" | "exit" | "straight" | null;
  track_region_id?: string | null;
  track_region_label?: string | null;
  track_region_phase?: "entry" | "center" | "exit" | "straight" | null;
  track_region_confidence?: "section_geometry" | "centerline_geometry" | null;
};

/** A server-suggested evidence handoff. It is navigation-only by construction. */
export type IntelligenceQueryNavigationTarget = {
  workspace: IntelligenceCitationWorkspace;
  run_id: string;
  lap_number?: number | null;
  event_id?: string | null;
  lap_pct?: number | null;
};

export type IntelligenceAction = {
  kind: "controlled_test" | "measurement_mission" | "driver_focus" | "no_call";
  title: string;
  instruction: string;
  /** Only the server can authorize a setup action. */
  setup_authorized: boolean;
  control_key?: string | null;
  current_value?: string | null;
  proposed_value?: string | null;
  evidence_state: EvidenceState;
  source_event_ids: string[];
  mission_contract_id?: string | null;
  mission_contract_sha256?: string | null;
  blocker_reasons: string[];
};

export type IntelligenceBriefing = {
  issue?: string | null;
  action: IntelligenceAction;
  success_check?: string | null;
  confidence_label?: string | null;
  blocker_reasons: string[];
};

export type IntelligenceCauseState = "leading" | "possible" | "ruled_out" | "unresolved";

export type IntelligenceCause = {
  cause_id: string;
  label: string;
  state: IntelligenceCauseState;
  rank: number;
  evidence_state: EvidenceState;
  reason: string;
  evidence_for: IntelligenceCitation[];
  evidence_against: IntelligenceCitation[];
};

export type IntelligenceMindChangeCriterion = {
  criterion_id: string;
  cause_id: string;
  current_state: IntelligenceCauseState;
  evidence_kind: "controlled_test" | "measurement_mission" | "discriminator";
  run_id: string;
  session_id: string | null;
  metric: string;
  phase: "braking" | "entry" | "center" | "exit" | "straight";
  control_key?: string | null;
  threshold_source: string;
  acceptance_conditions: string[];
  falsification_conditions: string[];
  minimum_independent_evidence_units: number;
  minimum_evidence: string;
  requires_aba2: boolean;
  minimum_laps_per_stage?: number | null;
  countereffects: string[];
  next_state_if_accepted: IntelligenceCauseState;
  next_state_if_falsified: IntelligenceCauseState;
  next_state_if_inconclusive: "unresolved";
  source_event_ids: string[];
};

export type IntelligenceMeasurement = {
  mission_id: string;
  title: string;
  purpose: string;
  procedure: string[];
  required_laps?: number | null;
  acceptance_threshold?: string | null;
  stop_rule?: string | null;
  controlled_variables: string[];
  citations: IntelligenceCitation[];
};

export type IntelligenceContextMatch = {
  memory_id: string;
  label: string;
  relevance_label: string;
  outcome_summary: string;
  matching_context: string[];
  mismatches: string[];
  citations: IntelligenceCitation[];
};

export type IntelligenceCalibration = {
  status: "available" | "insufficient_history";
  summary: string;
  qualified_correct?: number | null;
  qualified_total?: number | null;
  caveat: string;
};

export type IntelligenceNarrativeEntry = {
  entry_id: string;
  label: string;
  summary: string;
  created_at?: string | null;
  citations: IntelligenceCitation[];
};

export type IntelligenceGraphNode = {
  node_id: string;
  label: string;
  kind: "claim" | "cause" | "evidence" | "blocker" | "test";
  evidence_state?: EvidenceState | null;
  citation_id?: string | null;
};

export type IntelligenceGraphEdge = {
  source_id: string;
  target_id: string;
  relation: "supports" | "contradicts" | "tests" | "blocks";
};

export type IntelligenceEvidenceGraph = {
  nodes: IntelligenceGraphNode[];
  edges: IntelligenceGraphEdge[];
};

export type IntelligenceDataQuality = {
  status: "ready" | "limited" | "blocked";
  summary: string;
  eligible_laps: number;
  total_laps: number;
  trusted_events: number;
  issues: string[];
  recovery_steps: string[];
  citations: IntelligenceCitation[];
};

export type IntelligenceDriverProfile = {
  preferred_mode?: string | null;
  terminology_level?: string | null;
  recurring_symptoms: string[];
  controlled_tests_completed: number;
  consistency_label?: string | null;
  /** Personalization is presentation-only and must always remain false. */
  affects_evidence_eligibility: false;
};

export type IntelligenceMoveWorkspace =
  | "overview"
  | "laps"
  | "platform"
  | "setup"
  | "engineer"
  | "dial_in";

/** Server-ranked next step. Rendering this action may only navigate; it never executes the step. */
export type IntelligenceNextTrustworthyMove = {
  move_id: string;
  kind: "recover" | "qualify" | "diagnose" | "measure" | "controlled_test" | "compare" | "decide";
  title: string;
  instruction: string;
  reason: string;
  workspace: IntelligenceMoveWorkspace;
  authority: "navigation_only" | "setup_authorized";
  run_id: string;
  workflow_id?: string | null;
  workflow_updated_at?: string | null;
  control_key?: string | null;
  lap_number?: number | null;
  window_start_lap?: number | null;
  window_end_lap?: number | null;
  lap_pct_start?: number | null;
  lap_pct_end?: number | null;
  source_event_ids: string[];
  blocker_reasons: string[];
};

export type IntelligenceTestPreflight = {
  workflow_id: string;
  stage: "A" | "B" | "A2" | "complete";
  status: "ready" | "blocked" | "complete";
  title: string;
  checks: Array<{
    check_id: string;
    label: string;
    state: "verified" | "required" | "blocked";
    detail: string;
  }>;
  blocker_reasons: string[];
};

export type IntelligenceRecoveryKind =
  | "select_eligible_lap"
  | "retry_resource"
  | "inspect_missing_channel"
  | "repeat_measurement"
  | "resume_workflow";

export type IntelligenceMeasurementDebt = {
  status: "clear" | "open" | "blocked";
  summary: string;
  items: Array<{
    debt_id: string;
    label: string;
    reason: string;
    recovery_kind: IntelligenceRecoveryKind;
    workspace: IntelligenceMoveWorkspace;
    required_channels: string[];
    resolves_cause_ids: string[];
    blocker_reasons: string[];
  }>;
};

export type IntelligenceObservationCitation = {
  run_id: string;
  lap_number: number;
  setup_id: string;
  lap_pct_start: number;
  lap_pct_end: number;
  lap_pct_peak: number;
  phase: string;
  evidence_state: EvidenceState;
  source_channels: string[];
  event_id: string | null;
  telemetry_sample_count: number;
  physical_segments: Array<{
    start_pct: number;
    end_pct: number;
    sample_count: number;
  }>;
};

export type IntelligenceOpportunitySignature = {
  signature_id: string;
  run_id: string;
  setup_id: string;
  phase: string;
  lap_pct_start: number;
  lap_pct_end: number;
  lap_pct_peak: number;
  evidence_state: "observed_correlation";
  authority: "observation_only";
  observational_label: "repeatable_same_setup_opportunity";
  eligible_lap_count: number;
  repetition_count: number;
  telemetry_sample_count: number;
  aligned_bin_count: number;
  median_opportunity_s: number;
  empirical_noise_s: number;
  source_channels: string[];
  citations: IntelligenceObservationCitation[];
  blocker_reasons: string[];
};

export type IntelligenceOpportunityReport = {
  status: "ready" | "no_finding" | "blocked";
  run_id: string;
  setup_id: string | null;
  evidence_state: EvidenceState;
  authority: "observation_only";
  observational_label: "same_setup_physical_position_scan";
  required_channels: string[];
  source_channels: string[];
  eligible_lap_numbers: number[];
  eligible_lap_count: number;
  telemetry_sample_count: number;
  signatures: IntelligenceOpportunitySignature[];
  blocker_reasons: string[];
};

export type IntelligenceMechanismKind =
  | "driver_execution"
  | "braking_response"
  | "corner_rotation"
  | "tire_state"
  | "damper_response"
  | "platform_response"
  | "resistance_scrub_like"
  | "powertrain_response"
  | "stint_trend"
  | "sim_integrity"
  | "unclassified";

export type IntelligenceMechanismObservation = {
  observation_id: string;
  producer_id: string;
  artifact_id: string;
  source_run_ids: string[];
  source_setup_ids: string[];
  sample_coverage: number;
  mechanism: IntelligenceMechanismKind;
  mechanism_kinds: IntelligenceMechanismKind[];
  run_id: string;
  setup_id: string | null;
  lap_number: number | null;
  phase: string | null;
  lap_pct_start: number | null;
  lap_pct_end: number | null;
  lap_pct_peak: number | null;
  summary: string;
  evidence_state: EvidenceState;
  authority: "observation_only";
  observational_label: "typed_mechanism_observation";
  qualified: boolean;
  source_channels: string[];
  required_channels: string[];
  supporting_evidence: string[];
  contradicting_evidence: string[];
  telemetry_sample_count: number;
  repetition_count: number;
  citations: IntelligenceObservationCitation[];
  blocker_reasons: string[];
};

export type IntelligenceMechanismObservationReport = {
  status: "ready" | "no_finding" | "blocked";
  run_id: string;
  setup_id: string | null;
  authority: "observation_only";
  observations: IntelligenceMechanismObservation[];
  blocker_reasons: string[];
};

export type IntelligenceDriverFocus = {
  status: "ready" | "no_finding" | "blocked";
  run_id: string;
  setup_id: string | null;
  evidence_state: EvidenceState;
  authority: "driver_coaching_only";
  observational_label: "same_setup_driver_repeatability";
  eligible_lap_numbers: number[];
  eligible_lap_count: number;
  telemetry_sample_count: number;
  required_channels: string[];
  source_channels: string[];
  channel_repeatability: Array<{
    channel: string;
    unit: string;
    median_robust_spread: number;
    p90_robust_spread: number;
    aligned_bin_count: number;
  }>;
  focus: {
    phase: string;
    lap_pct_start: number;
    lap_pct_end: number;
    channel: string;
    instruction: string;
    success_check: string;
    setup_authorized: false;
    citations: IntelligenceObservationCitation[];
  } | null;
  blocker_reasons: string[];
};

export type IntelligenceAnomaly = {
  anomaly_id: string;
  run_id: string;
  setup_id: string;
  lap_number: number;
  channel: string;
  direction: "above_envelope" | "below_envelope";
  phase: string;
  lap_pct_start: number;
  lap_pct_end: number;
  lap_pct_peak: number;
  evidence_state: "observed_correlation";
  authority: "observation_only";
  observational_label: "sustained_same_setup_anomaly";
  reference_lap_numbers: number[];
  repetition_count: number;
  telemetry_sample_count: number;
  aligned_bin_count: number;
  median_observed_value: number;
  median_reference_value: number;
  median_absolute_deviation: number;
  source_channels: string[];
  citations: IntelligenceObservationCitation[];
  blocker_reasons: string[];
};

export type IntelligenceAnomalyReport = {
  status: "ready" | "no_finding" | "blocked";
  run_id: string;
  setup_id: string | null;
  evidence_state: EvidenceState;
  authority: "observation_only";
  observational_label: "same_setup_robust_anomaly_scan";
  required_channels: string[];
  source_channels: string[];
  eligible_lap_numbers: number[];
  eligible_lap_count: number;
  reference_lap_count: number;
  telemetry_sample_count: number;
  anomalies: IntelligenceAnomaly[];
  blocker_reasons: string[];
};

export type IntelligenceSessionCitation = {
  kind: string;
  reference_id: string;
  run_id: string | null;
  lap_number: number | null;
};

export type IntelligenceSessionLedger = {
  session_id: string;
  session_scope_sha256: string;
  status: "ready" | "limited" | "blocked";
  ordered_run_ids: string[];
  run_evidence: Array<{
    run_id: string;
    source_file_sha256: string;
    telemetry_cache_sha256: string;
    compatibility_fingerprint: string;
    setup_id: string | null;
    eligible_lap_ids: string[];
  }>;
  entries: Array<{
    entry_id: string;
    state: "improved" | "regressed" | "recurring" | "resolved" | "not_comparable";
    observation_kind: "pace" | "recurring_issue" | "resolved_issue" | "comparability";
    baseline_run_id: string;
    test_run_id: string;
    description: string;
    evidence_scope: "position_aligned" | "whole_lap" | "event_signature" | "none";
    delta_s: number | null;
    start_pct: number | null;
    end_pct: number | null;
    phase: string | null;
    setup_changes: Array<{
      setup_key: string;
      label: string;
      baseline_value: unknown;
      test_value: unknown;
      delta: string | null;
    }>;
    attribution: "observation_only";
    causal_claim: false;
    citations: IntelligenceSessionCitation[];
    blocker_reasons: string[];
  }>;
  blocker_reasons: string[];
};

export type IntelligenceHypothesisLifecycle = {
  session_id: string;
  session_scope_sha256: string;
  status: "ready" | "limited" | "blocked";
  ordered_run_ids: string[];
  entries: Array<{
    workflow_id: string;
    hypothesis_fingerprint: string;
    lifecycle_state: "supported" | "contradicted" | "inconclusive" | "invalid" | "do_not_repeat";
    outcome_classification: "supported" | "contradicted" | "inconclusive" | "invalid";
    hypothesis: string;
    expected_mechanism: string | null;
    control_key: string | null;
    direction_sign: -1 | 1 | null;
    target_effect: {
      metric: string;
      phase: string;
      expected_direction: "decrease" | "increase" | null;
      expected_range_s: [number, number] | null;
      actual_effect_s: number | null;
      actual_direction: "decrease" | "increase" | "inconclusive" | "unavailable";
      direction_result: "matched" | "missed" | "inconclusive" | "unavailable";
      range_result: "inside" | "outside" | "inconclusive" | "unavailable";
    };
    countereffects: {
      criteria: string[];
      passed: boolean | null;
      observed_metrics: Record<string, number>;
    };
    protocol: {
      source_run_id: string;
      a_run_id: string | null;
      b_run_id: string | null;
      a2_run_id: string | null;
      eligible_lap_ids: string[];
      protocol_valid: boolean;
      evidence_score: number;
      verdict: "keep" | "undo" | "retest" | "invalid";
      blocker_reasons: string[];
    };
    do_not_repeat: boolean;
    do_not_repeat_reason: string | null;
    citations: IntelligenceSessionCitation[];
  }>;
  do_not_repeat_hypothesis_fingerprints: string[];
  blocker_reasons: string[];
};

export type IntelligenceAttentionItem = {
  attention_id: string;
  state: "new" | "changed" | "resolved";
  label: string;
  workspace: IntelligenceMoveWorkspace;
  run_id: string;
  fingerprint: string;
};

export type IntelligenceTelemetryHealthIdentity = {
  session_id: string;
  session_scope_sha256: string;
  run_id: string;
  source_file_sha256: string;
  telemetry_cache_sha256: string;
  manifest_sha256: string;
  schema_fingerprint: string;
  compatibility_fingerprint: string;
  manifest_schema_version: number;
  universal_archive_version: number;
  iracing_build_version: string;
};

export type IntelligenceTelemetryHealthSnapshot = {
  run_id: string;
  raw_name: string;
  canonical_name: string;
  archive_status: "cached" | "metadata_only";
  record_count: number;
  valid_record_count: number;
  coverage_fraction: number;
  missing_fraction: number;
  distinct_value_count: number;
  variation: "varying" | "constant" | "no_valid_samples" | "not_cached";
  observed_min: number | null;
  observed_max: number | null;
  observed_span: number | null;
  effective_sample_rate_hz: number | null;
  health_status: "healthy" | "warning" | "not_assessed";
  clipping_status: string;
  saturation_status: string;
  lower_bound_occupancy_fraction: number;
  upper_bound_occupancy_fraction: number;
  numeric_limit_hit_count: number;
};

export type IntelligenceTelemetryHealthRecovery = {
  action: "reimport_original_ibt" | "record_verification_run";
  run_id: string;
  instruction: string;
};

export type IntelligenceTelemetryHealthFinding = {
  finding_id: string;
  kind: "dropout" | "became_constant" | "became_saturated" | "range_shifted" | "effective_rate_changed";
  channel: string;
  current_run_id: string;
  baseline_run_ids: string[];
  source_raw_names: string[];
  observation: string;
  recovery: IntelligenceTelemetryHealthRecovery;
  authority: "measurement_health_only";
  vehicle_cause_attributed: false;
  setup_authorized: false;
};

export type IntelligenceTelemetryHealthReport = {
  status: "healthy" | "warning" | "insufficient_history" | "blocked";
  authority: "measurement_health_only";
  vehicle_cause_attributed: false;
  setup_authorized: false;
  session_id: string;
  ordered_session_run_ids: string[];
  session_scope_sha256: string;
  current_run_id: string;
  required_prior_run_count: 2;
  current_identity: IntelligenceTelemetryHealthIdentity | null;
  baseline_identities: IntelligenceTelemetryHealthIdentity[];
  comparisons: Array<{
    channel: string;
    current: IntelligenceTelemetryHealthSnapshot;
    baselines: IntelligenceTelemetryHealthSnapshot[];
    metrics_compared: ["coverage", "range", "variation", "effective_rate", "missingness"];
    findings: IntelligenceTelemetryHealthFinding[];
  }>;
  findings: IntelligenceTelemetryHealthFinding[];
  assessed_channels: string[];
  blocker_reasons: string[];
  recovery: IntelligenceTelemetryHealthRecovery[];
};

export type RunIntelligenceReport = {
  schema_version: "p19.run-intelligence.v1";
  run_id: string;
  session_id: string | null;
  reasoning_snapshot_sha256: string;
  setup_id: string | null;
  setup_snapshot_sha256: string | null;
  status: IntelligenceStatus;
  decision_status: IntelligenceDecisionStatus;
  generated_at?: string | null;
  briefing: IntelligenceBriefing;
  competing_causes: IntelligenceCause[];
  mind_change_criteria: IntelligenceMindChangeCriterion[];
  best_measurement?: IntelligenceMeasurement | null;
  context_matches: IntelligenceContextMatch[];
  calibration: IntelligenceCalibration;
  narrative: IntelligenceNarrativeEntry[];
  suggested_questions: string[];
  blocker_reasons: string[];
  evidence_graph?: IntelligenceEvidenceGraph | null;
  data_quality?: IntelligenceDataQuality | null;
  driver_profile?: IntelligenceDriverProfile | null;
  opportunity_signature?: IntelligenceOpportunityReport | null;
  mechanism_observations?: IntelligenceMechanismObservationReport | null;
  session_ledger?: IntelligenceSessionLedger | null;
  hypothesis_lifecycle?: IntelligenceHypothesisLifecycle | null;
  next_trustworthy_move?: IntelligenceNextTrustworthyMove | null;
  test_preflight?: IntelligenceTestPreflight | null;
  driver_focus?: IntelligenceDriverFocus | null;
  anomalies?: IntelligenceAnomalyReport | null;
  measurement_debt?: IntelligenceMeasurementDebt | null;
  attention_items?: IntelligenceAttentionItem[];
  telemetry_health?: IntelligenceTelemetryHealthReport | null;
  vehicle_systems?: VehicleSystemsProjection | null;
  mission_stage?: "qualify" | "diagnose" | "measure" | "test" | "compare" | "decide" | "certified" | null;
};

export type IntelligenceQueryRequest = {
  question: string;
  session_id?: string | null;
  selected_lap: number | null;
  selected_window_start_lap?: number | null;
  selected_window_end_lap?: number | null;
  selected_window_representative_lap?: number | null;
  /** Presentation preference only; the server must not use it for evidence eligibility. */
  presentation_mode: "race" | "learning";
};

export type IntelligenceQueryResponse = {
  schema_version: "p19.intelligence-query.v1";
  run_id: string;
  session_id: string | null;
  reasoning_snapshot_sha256: string;
  setup_id: string | null;
  setup_snapshot_sha256: string | null;
  scope_run_ids: string[];
  selected_lap?: number | null;
  status: IntelligenceStatus;
  question: string;
  headline: string;
  answer: string;
  interpreted_lap_number?: number | null;
  interpreted_window_start_lap?: number | null;
  interpreted_window_end_lap?: number | null;
  interpreted_window_representative_lap?: number | null;
  interpreted_phase?: "braking" | "entry" | "center" | "exit" | "straight" | null;
  interpreted_control_key?: string | null;
  interpreted_component_id?: VehicleSystemComponentId | null;
  interpreted_track_region_id?: string | null;
  interpreted_track_region_label?: string | null;
  clarification_required?: boolean;
  action_authorized: boolean;
  action_source_event_ids: string[];
  evidence_state: EvidenceState;
  citations: IntelligenceCitation[];
  suggested_navigation: IntelligenceQueryNavigationTarget[];
  mind_change_criteria: IntelligenceMindChangeCriterion[];
  blocker_reasons: string[];
  follow_up_questions: string[];
};
