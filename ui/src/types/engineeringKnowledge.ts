export type EngineeringKnowledgeLevel =
  | "educational_knowledge"
  | "measurable_hypothesis"
  | "p19_testable_control"
  | "unsupported_remove";

export type ControlledKnowledgeHistory = {
  experience_id: string;
  workflow_id: string;
  component_family_id: string;
  control_key: string;
  transfer_level: "exact" | "compatible";
  mechanism_assessment: "supported" | "weakened" | "unchanged" | "inconclusive" | "invalid";
  control_response: "matched" | "missed" | "inconclusive" | "unavailable" | "invalid";
  policy_verdict: "keep" | "undo" | "retest" | "invalid";
  countereffects: string[];
  source_artifact_ids: string[];
  authority: "controlled_history_only";
  setup_authorized: false;
};

export type P19TestableControl = {
  effect_id: string;
  control_key: string;
  direction_sign: -1 | 1;
  experiment_factor_id: string;
  current_value: string;
  proposed_value: string;
  workflow_id: string;
  workflow_revision: string;
  source_event_ids: string[];
  authority: "exact_p19_projection";
};

export type CurrentKnowledgeHypothesis = {
  bridge_id: string;
  effect_id: string;
  setup_area: string;
  physical_role: string;
  direction_sign: -1 | 0 | 1;
  experiment_factor_id: string | null;
  level: EngineeringKnowledgeLevel;
  relevance: "supported_candidate" | "blocked_candidate" | "knowledge_only" | "inapplicable";
  p32_opportunity_id: string | null;
  p35_mechanism_ids: string[];
  p20_mechanism_ids: string[];
  possible_component_family_ids: string[];
  p26_component_family_ids: string[];
  current_candidate_component_ids: string[];
  current_supported_component_ids: string[];
  contradicted_component_ids: string[];
  blocked_component_ids: string[];
  unobservable_component_ids: string[];
  irrelevant_component_ids: string[];
  response_regimes: Array<"transient" | "steady_state" | "both">;
  relevant_phases: string[];
  expected_vehicle_response_ids: string[];
  expected_vehicle_state_ids: string[];
  validation_metric_ids: string[];
  countereffect_ids: string[];
  countereffect_state_ids: string[];
  protected_outcomes: string[];
  protected_performance_outcome_ids: string[];
  rollback_condition_ids: string[];
  inspection_tool_ids: string[];
  support_artifact_ids: string[];
  contradiction_artifact_ids: string[];
  discriminator_contract_ids: string[];
  missing_evidence: string[];
  controlled_history: ControlledKnowledgeHistory[];
  knowledge_applicability: "applicable" | "educational_only" | "blocked_by_build" | "unsupported";
  runtime_evidence_state: "unavailable" | "measured" | "calculated" | "estimated_proxy" | "observed_correlation" | "controlled_test_effect" | "blocked_by_context";
  p19_control: P19TestableControl | null;
  authority: "knowledge_only" | "measurement_only" | "exact_p19_projection";
  setup_authorized: boolean;
};

export type CurrentEngineeringKnowledgeProjection = {
  schema_version: "p352.current-engineering-knowledge.v1";
  projection_sha256: string;
  run_id: string;
  session_id: string;
  complaint_prior: string | null;
  p19_reasoning_snapshot_sha256: string;
  p20_state_revision: string;
  p26_knowledge_graph_sha256: string;
  p32_projection_sha256: string;
  p35_assessment_sha256: string;
  p33_projection_sha256: string;
  bridge_coverage_sha256: string;
  p32_opportunity_id: string | null;
  hypotheses: CurrentKnowledgeHypothesis[];
  leading_hypothesis_ids: string[];
  next_discriminator_contract_id: string | null;
  blocker_reasons: string[];
  terminal_authority: "p19_only";
  non_p19_setup_authorized: false;
};
