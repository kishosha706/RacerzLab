import type { EngineeringObjective } from "./crewChief";
import type { EvidenceState } from "./telemetry";

export type ContextTransferLevel = "exact" | "compatible" | "weak" | "blocked";

export type LearningStrength =
  | "single_case"
  | "repeated_same_context"
  | "repeated_multi_session"
  | "controlled_repeated"
  | "cross_context_supported"
  | "conflicted"
  | "insufficient";

export type EvidenceUnitCounts = {
  observation_count: number;
  independent_episode_count: number;
  independent_workflow_count: number;
  distinct_session_count: number;
  distinct_context_count: number;
};

export type P19CauseMemory = {
  cause_id: string;
  status: "likely" | "possible" | "ruled_out" | "unresolved";
  ordinal_rank: number;
  mechanism_family: string | null;
};

export type P19ReasoningMemory = {
  reasoning_snapshot_sha256: string;
  causes: P19CauseMemory[];
  measurement_plan_kind: string;
  discriminator_ids: string[];
  authority_level: "observation" | "measurement" | "controlled_setup" | "blocked";
  setup_authorized: boolean;
};

export type ProblemFingerprint = {
  problem_sha256: string;
  physical_episode_id: string | null;
  performance_opportunity_id: string | null;
  phase: string;
  physical_region: string;
  time_origin_class: string;
  carry_behavior: string;
  driver_demand_state: string;
  vehicle_response_state: string;
  p20_mechanism_families: string[];
  p26_component_families: string[];
  traffic_context_state: string;
  tire_stint_state: string;
  objective: EngineeringObjective;
  source_artifact_ids: string[];
};

export type DriverMetric =
  | "brake_onset_consistency"
  | "brake_release_timing_consistency"
  | "steering_onset_consistency"
  | "steering_workload"
  | "correction_frequency"
  | "throttle_pickup_timing"
  | "throttle_realization"
  | "line_repeatability"
  | "phase_time_repeatability"
  | "short_run_long_run_behavior"
  | "traffic_execution"
  | "controlled_test_execution_consistency"
  | "driver_vehicle_separation";

export type DriverFingerprintContribution = {
  contribution_id: string;
  metric: DriverMetric;
  tendency: "repeatable_tendency" | "context_dependent_tendency" | "insufficient_history" | "changed_behavior";
  statement: string;
  physical_episode_ids: string[];
  source_artifact_ids: string[];
  source_lap_count: number;
  authority: "driver_context_only";
  setup_authorized: false;
};

export type PerformanceResponseFact = {
  performance_opportunity_id: string | null;
  observed_delta_s: number | null;
  observed_direction: "loss" | "gain" | "unavailable";
  attribution_state: "candidate_only" | "blocked_by_traffic" | "blocked_by_context" | "unavailable";
  time_origin: string;
  phase_effect_s: number | null;
  carry_effect_s: number | null;
  recovery_surrender: string;
  source_response_record_id: string | null;
  source_artifact_ids: string[];
};

export type CarResponseFact = {
  response_id: string;
  component: string;
  control: string;
  direction: "increase" | "decrease" | "unchanged" | "unknown";
  magnitude_class: "adjacent" | "small" | "medium" | "large" | "unknown";
  expected_vehicle_response: string;
  observed_vehicle_response: string;
  p32_time_origin: string;
  phase_time_effect_s: number | null;
  carry_effect_s: number | null;
  recovery_surrender: string;
  countereffects: string[];
  p19_mechanism_assessment: "supported" | "weakened" | "unchanged" | "inconclusive" | "invalid";
  control_response_assessment: "matched" | "missed" | "inconclusive" | "unavailable" | "invalid";
  policy_verdict: "keep" | "undo" | "retest" | "invalid";
  source_workflow_id: string;
  source_response_record_id: string | null;
  source_artifact_ids: string[];
  setup_authorized: false;
};

export type InvestigationPathFact = {
  investigation_id: string;
  started_at: string;
  completed_at: string;
  initial_cause_ids: string[];
  tools_inspected: string[];
  driver_question_ids: string[];
  driver_answers: string[];
  requested_measurement_ids: string[];
  completed_measurement_ids: string[];
  strongest_contradiction: string;
  eliminated_cause_ids: string[];
  unresolved_cause_ids: string[];
  terminal_decision: "controlled_test" | "retest" | "no_call" | "driver_focus" | "measurement_only" | "abandoned";
  workflow_ids: string[];
  elapsed_seconds: number;
  laps_consumed: number;
  tool_steps_consumed: number;
  driver_questions_consumed: number;
  successful_discriminator_ids: string[];
  source_artifact_ids: string[];
  historical_retrieval_used: boolean;
  historical_match_confirmed: boolean | null;
};

export type MindChangeFact = {
  mind_change_id: string;
  before_reasoning: P19ReasoningMemory;
  after_reasoning: P19ReasoningMemory;
  new_artifact_ids: string[];
  new_evidence_states: string[];
  causes_promoted: string[];
  causes_demoted: string[];
  causes_ruled_out: string[];
  measurement_discriminator_id: string | null;
  evidence_discriminated: boolean;
  driver_question_involved: boolean;
  controlled_evidence_involved: boolean;
  context_gate_involved: boolean;
};

export type DeadEndFact = {
  dead_end_id: string;
  kind:
    | "failed_investigation"
    | "non_discriminating_measurement"
    | "repeated_no_finding_tool"
    | "repeated_undo_policy"
    | "irrelevant_component_family"
    | "context_invalidated_comparison";
  tool_id: string | null;
  component_family: string | null;
  control: string | null;
  statement: string;
  source_artifact_ids: string[];
  source_workflow_ids: string[];
  current_evidence_may_override: true;
  authority: "attention_only";
};

export type ContextTransferAssessment = {
  experience_id: string;
  level: ContextTransferLevel;
  matching_dimensions: string[];
  mismatched_dimensions: string[];
  drift_reasons: string[];
  blocker_reasons: string[];
};

export type EngineeringSourceProvenance = {
  provenance_sha256: string;
  artifact_id: string;
  producer_id: string;
  run_id: string;
  session_id: string;
  setup_id: string;
  setup_snapshot_sha256: string;
  build_context_sha256: string;
  lap_numbers: number[];
  lap_pct_start: number | null;
  lap_pct_end: number | null;
  phase: string | null;
  source_channels: string[];
  evidence_state: EvidenceState;
  polarity: "support" | "contradiction" | "neutral";
};

export type LearningEvidenceReference = {
  reference_id: string;
  experience_id: string;
  provenance: EngineeringSourceProvenance;
  state: "available" | "unavailable";
  blocker_reasons: string[];
  authority: "attention_only";
  setup_authorized: false;
};

export type RecurringProblemMatch = {
  recurrence_id: string;
  classification: "new_problem" | "possible_recurrence" | "strong_recurrence" | "exact_context_recurrence";
  problem_sha256s: string[];
  experience_ids: string[];
  investigation_ids: string[];
  statement: string;
  useful_discriminator: string | null;
  prior_dead_end: string | null;
  strongest_contradiction: string;
  transfer: ContextTransferAssessment | null;
  counts: EvidenceUnitCounts;
  strength: LearningStrength;
  authority: "attention_only";
  setup_authorized: false;
};

export type DriverPerformanceFingerprint = {
  fingerprint_id: string;
  driver_id: string;
  transfer_level: ContextTransferLevel;
  state: "repeatable_tendency" | "context_dependent_tendency" | "insufficient_history" | "changed_behavior";
  tendencies: DriverFingerprintContribution[];
  counts: EvidenceUnitCounts;
  source_experience_ids: string[];
  contradictions: string[];
  authority: "driver_context_only";
  setup_authorized: false;
};

export type CarResponseFingerprint = {
  fingerprint_id: string;
  transfer_level: ContextTransferLevel;
  response: CarResponseFact;
  counts: EvidenceUnitCounts;
  source_experience_ids: string[];
  source_workflow_ids: string[];
  contradictions: string[];
  statement: string;
  authority: "controlled_history_only";
  setup_authorized: false;
};

export type InvestigationOutcomeRecord = {
  outcome_id: string;
  experience_id: string;
  transfer_level: ContextTransferLevel;
  outcome: InvestigationPathFact;
  counts: EvidenceUnitCounts;
  useful: boolean;
  explanation: string;
  authority: "attention_only";
};

export type MindChangeRecord = {
  experience_id: string;
  transfer_level: ContextTransferLevel;
  fact: MindChangeFact;
  statement: string;
  authority: "attention_only";
};

export type EngineeringDeadEndRecord = {
  experience_ids: string[];
  transfer_level: ContextTransferLevel;
  fact: DeadEndFact;
  counts: EvidenceUnitCounts;
  may_deprioritize_within_band: boolean;
  may_veto_current_evidence: false;
};

export type AttentionOrderItem = {
  tool_id: string;
  safety_band: string;
  learned_rank_within_band: number;
  baseline_rank_within_band: number;
  reason: string;
  transfer_level: "exact" | "compatible";
  source_experience_ids: string[];
  investigation_count: number;
  session_count: number;
  independent_workflow_count: number;
  authority: "attention_only";
};

export type EngineeringLearningLedger = {
  investigations_opened: number;
  investigations_resolved: number;
  no_call_outcomes: number;
  driver_focus_outcomes: number;
  measurement_missions: number;
  controlled_tests: number;
  keep_outcomes: number;
  undo_outcomes: number;
  retest_outcomes: number;
  average_tool_steps_before_resolution: number | null;
  laps_consumed_before_resolution: number;
  questions_asked: number;
  repeated_dead_end_tools: string[];
  successful_discriminators: string[];
  recurring_problem_count: number;
  recurrence_resolved_faster_count: number;
  claims_lap_time_improvement: false;
};

export type PostRunLearningBrief = {
  state: "available" | "insufficient_history" | "blocked";
  what_we_learned: string[];
  what_changed_our_mind: string[];
  what_did_not_work: string[];
  next_attention: string[];
  blocker_reasons: string[];
  authority: "attention_only";
  setup_authorized: false;
};

export type CrewChiefLearningPrior = {
  schema_version: "p33.engineering-learning.v1";
  projection_sha256: string;
  history_revision: string;
  run_id: string;
  session_id: string;
  objective_id: EngineeringObjective;
  selected_scope_hash: string;
  p19_reasoning_snapshot_sha256: string;
  p32_projection_sha256: string;
  current_context_sha256: string;
  current_problem_sha256: string;
  state: "available" | "insufficient_history" | "blocked";
  recurrence: RecurringProblemMatch;
  useful_prior_investigations: InvestigationOutcomeRecord[];
  known_dead_ends: EngineeringDeadEndRecord[];
  driver_tendencies: DriverPerformanceFingerprint[];
  car_response_history: CarResponseFingerprint[];
  mind_change_history: MindChangeRecord[];
  recommended_attention_order: AttentionOrderItem[];
  context_transfers: ContextTransferAssessment[];
  evidence_references: LearningEvidenceReference[];
  context_transfer_level: ContextTransferLevel;
  strength: LearningStrength;
  counts: EvidenceUnitCounts;
  ledger: EngineeringLearningLedger;
  post_run_brief: PostRunLearningBrief;
  blocker_reasons: string[];
  authority: "attention_only";
  setup_authorized: false;
  p19_rank_modified: false;
};
