export type InvestigationImprovementState = "available" | "unavailable";

export type InvestigationMemoryPolicyState = "shadow_only" | "limited_attention";

export type InvestigationCounterfactualState =
  | "pending"
  | "directly_observed"
  | "counterfactual_observable"
  | "counterfactual_unobservable"
  | "invalid";

export type InvestigationDecisionKind =
  | "inspect_tool"
  | "ask_driver"
  | "surface_prior"
  | "observe_only"
  | "no_call";

export type InvestigationPriorityTier =
  | "identity_integrity"
  | "context_qualification"
  | "driver_car_confounders"
  | "strongest_contradiction"
  | "unresolved_p19_mechanisms"
  | "component_family_separation"
  | "exact_history"
  | "measurement_debt"
  | "terminal";

export type InvestigationPhysicalProblemFamily =
  | "braking"
  | "entry"
  | "center"
  | "exit"
  | "straight"
  | "long_run"
  | "mixed"
  | "unresolved";

export type InvestigationContextTransferClass =
  | "none"
  | "exact"
  | "compatible"
  | "weak"
  | "blocked";

export type InvestigationProblemOrientation =
  | "driver"
  | "vehicle"
  | "combined"
  | "unresolved";

export type InvestigationTrackClass =
  | "short_track"
  | "intermediate"
  | "superspeedway"
  | "road_course"
  | "unknown";

export type InvestigationNegativeControlCondition =
  | "no_relevant_history"
  | "incompatible_history"
  | "corrupt_history"
  | "generic_component_knowledge_only"
  | "same_words_different_physical_scope"
  | "material_driver_drift"
  | "future_memory_record";

export type InvestigationP19CauseState = {
  cause_id: string;
  state: "likely" | "possible" | "ruled_out" | "unresolved";
};

export type InvestigationNegativeControlEvidence = {
  condition: InvestigationNegativeControlCondition;
  p33_projection_sha256: string;
  p33_state: "available" | "insufficient_history" | "blocked";
  context_transfer_record_ids: string[];
  context_transfer_levels: Exclude<InvestigationContextTransferClass, "none">[];
  useful_prior_experience_ids: string[];
  component_history_experience_ids: string[];
  physical_scope_mismatch_dimensions: string[];
  recurrence_class:
    | "new_problem"
    | "possible_recurrence"
    | "strong_recurrence"
    | "exact_context_recurrence";
  corruption_blocker_sha256s: string[];
  future_memory_record_ids: string[];
  future_memory_record_completed_ats: string[];
  driver_drift_state: "stable" | "material_drift" | "unknown";
};

export type InvestigationDecision = {
  decision_kind: InvestigationDecisionKind;
  action_id: string;
  priority_tier: InvestigationPriorityTier;
  safe_reorder_group: string | null;
  baseline_ordinal: number;
  selected_ordinal: number;
  reason: string;
  mandatory_check_ids: string[];
  source_memory_record_ids: string[];
  setup_authorized: false;
  terminal_policy_authorized: false;
};

export type PairedInvestigationDecision = {
  schema_version: "p34.paired-investigation-decision.v1";
  pair_id: string;
  pair_sha256: string;
  investigation_id: string;
  investigation_opened_at: string;
  run_id: string;
  session_id: string;
  workspace_revision: string;
  authority_revision: string;
  step_number: number;
  baseline_policy_id: string;
  baseline_policy_sha256: string;
  memory_policy_id: string;
  memory_policy_sha256: string;
  activation_protocol_id: string;
  activation_protocol_sha256: string;
  activation_state: InvestigationMemoryPolicyState;
  activation_decision_id: string | null;
  activation_decision_sha256: string | null;
  production_policy_kind: "deterministic_baseline" | "limited_attention";
  baseline_decision: InvestigationDecision;
  memory_decision: InvestigationDecision;
  production_decision: InvestigationDecision;
  available_tool_ids: string[];
  eligible_tool_ids: string[];
  completed_tool_ids: string[];
  available_artifact_ids: string[];
  qualified_available_artifact_ids: string[];
  qualified_available_artifact_evidence_states: Array<
    "measured" | "calculated" | "controlled_test_effect"
  >;
  qualified_available_artifact_provenance_sha256s: string[];
  current_evidence_pinned_tool_ids: string[];
  current_truth_sha256: string;
  p19_snapshot_sha256: string;
  p20_projection_sha256: string;
  p26_projection_sha256: string;
  p32_projection_sha256: string;
  current_p19_cause_ids: string[];
  current_p19_cause_states: InvestigationP19CauseState[];
  current_contradiction_ids: string[];
  strongest_contradiction_id: string | null;
  current_objective: string;
  p33_projection_sha256: string;
  p33_history_revision: string;
  p33_ledger_head_sha256: string | null;
  p33_context_sha256: string;
  p33_problem_sha256: string;
  track: string;
  track_configuration: string;
  package_type: string;
  iracing_build: string;
  problem_family: InvestigationPhysicalProblemFamily;
  problem_orientation: InvestigationProblemOrientation;
  track_class: InvestigationTrackClass;
  phase: string;
  context_subgroup_keys: string[];
  build_review_state: "same_build" | "reviewed_compatible_build" | "future_unreviewed_build";
  driver_drift_state: "stable" | "material_drift" | "unknown";
  negative_control_condition: InvestigationNegativeControlCondition | null;
  negative_control_evidence: InvestigationNegativeControlEvidence | null;
  future_memory_record_ids: string[];
  memory_records_consulted: string[];
  context_transfer_class: InvestigationContextTransferClass;
  decision_frozen_at: string;
  outcome_exposed: false;
  p19_rank_unchanged: true;
  p19_authority_unchanged: true;
  p19_terminal_action_unchanged: true;
  setup_authorized: false;
};

export type PairedInvestigationComparison = {
  schema_version: "p34.paired-investigation-comparison.v1";
  comparison_id: string;
  comparison_sha256: string;
  investigation_id: string;
  pair_id: string;
  pair_sha256: string;
  activation_protocol_id: string;
  activation_protocol_sha256: string;
  certificate_id: string;
  certificate_sha256: string;
  discriminator_outcome_id: string | null;
  discriminator_outcome_sha256: string | null;
  outcome_followup_id: string | null;
  outcome_followup_sha256: string | null;
  counterfactual_source_certificate_id: string | null;
  counterfactual_source_certificate_sha256: string | null;
  independently_observed_artifact_ids: string[];
  decision_frozen_at: string;
  observability: InvestigationCounterfactualState;
  context_identity_sha256: string;
  problem_family: string;
  objective: string;
  context_transfer_class: InvestigationContextTransferClass;
  subgroup_keys: string[];
  baseline_tool_steps: number;
  memory_path_metrics_observed: boolean;
  bounded_reorder_observed: boolean;
  bounded_discriminator_step_advance: 0 | 1;
  bounded_discriminator_step_delay: 0 | 1;
  bounded_dead_end_promoted: boolean;
  memory_tool_steps: number | null;
  baseline_elapsed_seconds: number;
  memory_elapsed_seconds: number | null;
  baseline_consumption_metrics_observed: boolean;
  memory_consumption_metrics_observed: boolean;
  baseline_laps: number | null;
  memory_laps: number | null;
  baseline_questions: number;
  memory_questions: number | null;
  baseline_dead_ends: number;
  memory_dead_ends: number | null;
  baseline_measurement_missions: number | null;
  memory_measurement_missions: number | null;
  baseline_repeated_no_findings: number;
  memory_repeated_no_findings: number | null;
  baseline_useful_discriminator_step: number | null;
  memory_useful_discriminator_step: number | null;
  baseline_unresolved_or_abandoned: boolean;
  memory_unresolved_or_abandoned: boolean | null;
  useful_discriminator_hit: boolean;
  strongest_contradiction_handled: boolean;
  recurrence_match_correct: boolean | null;
  context_transfer_correct: boolean | null;
  driver_car_separation_correct: boolean | null;
  eventual_p19_resolution: boolean | null;
  no_call_stable: boolean | null;
  authority_violations: number;
  p19_action_mismatches: number;
  stale_workspace_actions: number;
  mandatory_check_violations: number;
  hidden_contradiction_failures: number;
  incompatible_history_transfers: number;
  driver_memory_mechanical_diagnoses: number;
  memory_only_terminal_actions: number;
  prospective: boolean;
  synthetic: boolean;
  qualified: boolean;
  blockers: string[];
  compared_at: string;
  setup_authorized: false;
};

export type InvestigationImprovementReadiness = {
  production_policy: "deterministic_baseline" | "limited_attention";
  memory_policy_state: InvestigationMemoryPolicyState;
  activation_decision: "no_activation_earned" | "limited_attention_earned";
  evaluation_decision: "no_activation_earned" | "limited_attention_earned";
  effective_activation_decision_id: string | null;
  effective_activation_decision_sha256: string | null;
  qualified_historical_investigations: number;
  qualified_prospective_investigations: number;
  observable_comparisons: number;
  unobservable_comparisons: number;
  historical_deficit: number;
  prospective_deficit: number;
  exact_recurrence_deficit: number;
  compatible_recurrence_deficit: number;
  context_deficit: number;
  problem_family_deficit: number;
  objective_deficit: number;
  safety_gate_passed: boolean;
  negative_controls_passed: boolean;
  subgroup_gate_passed: boolean;
  blockers: string[];
  remaining_collection_missions: string[];
  authority_ceiling: "attention_only";
  setup_authorized: false;
};

export type InvestigationAdaptationContext = {
  schema_version: "p34.investigation-adaptation-context.v1";
  context_binding_sha256: string;
  run_id: string;
  session_id: string;
  workspace_revision: string;
  current_truth_sha256: string;
  p19_snapshot_sha256: string;
  p20_projection_sha256: string;
  p26_projection_sha256: string;
  p32_projection_sha256: string;
  p33_projection_sha256: string;
  p33_context_sha256: string;
  p33_problem_sha256: string;
  qualified_available_artifact_ids: string[];
  qualified_available_artifact_evidence_states: Array<
    "measured" | "calculated" | "controlled_test_effect"
  >;
  qualified_available_artifact_provenance_sha256s: string[];
  current_evidence_pinned_tool_ids: string[];
  track: string;
  track_configuration: string;
  package_type: string;
  iracing_build: string;
  problem_family: InvestigationPhysicalProblemFamily;
  problem_orientation: InvestigationProblemOrientation;
  track_class: InvestigationTrackClass;
  phase: string;
  current_objective: string;
  build_review_state: "same_build" | "reviewed_compatible_build" | "future_unreviewed_build";
  driver_drift_state: "stable" | "material_drift" | "unknown";
  context_subgroup_keys: string[];
  negative_control_condition: InvestigationNegativeControlCondition | null;
  negative_control_evidence_sha256: string | null;
};

export type InvestigationImprovementProjection = {
  schema_version: "p34.investigation-improvement-projection.v1";
  projection_sha256: string;
  run_id: string;
  session_id: string;
  workspace_revision: string;
  state: InvestigationImprovementState;
  production_policy: "deterministic_baseline" | "limited_attention";
  memory_policy_state: InvestigationMemoryPolicyState;
  current_pair: PairedInvestigationDecision | null;
  current_context: InvestigationAdaptationContext | null;
  current_pair_status: "pending" | null;
  latest_completed_pair: PairedInvestigationDecision | null;
  latest_completed_comparison: PairedInvestigationComparison | null;
  latest_outcome_status: InvestigationCounterfactualState | null;
  decisions_differ: boolean;
  difference_explanation: string;
  memory_evidence_record_ids: string[];
  context_transfer_class: InvestigationContextTransferClass;
  readiness: InvestigationImprovementReadiness;
  safety_blockers: string[];
  p19_authority_unchanged: true;
  setup_authorized: false;
};
