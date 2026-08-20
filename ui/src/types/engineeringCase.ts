import type { OperationalResponseEvidence } from "./vehicleDynamics";

export type EvidenceDeficitCode =
  | "CHANNEL_MISSING" | "CHANNEL_UNHEALTHY" | "WRONG_UPDATE_SEMANTIC"
  | "PIT_SNAPSHOT_ONLY" | "INSUFFICIENT_REPETITION" | "INSUFFICIENT_CLEAN_LAPS"
  | "TRAFFIC_CONTAMINATED" | "SPEED_BAND_MISMATCH" | "PHASE_MISMATCH"
  | "SETUP_MISMATCH" | "CASE_REVISION_MISMATCH" | "RECORDING_NOT_INDEPENDENT"
  | "REQUIRED_COUNTEREFFECT_MISSING" | "EXACT_SEMANTIC_BRIDGE_MISSING"
  | "EXACT_LEGAL_OPTION_MISSING" | "P19_AUTHORITY_REQUIRED"
  | "BUILD_APPLICABILITY_BLOCKED" | "STRUCTURALLY_UNAVAILABLE";

export type EngineeringResponseArtifact = {
  artifact_type: "engineering_response";
  artifact_id: string;
  artifact_sha256: string;
  case_id: string;
  case_revision_sha256: string;
  run_id: string;
  session_id: string;
  setup_id: string;
  source_recording_sha256: string;
  source_producer_id: string;
  source_producer_version: string;
  relation: string;
  lap_pct_start: number;
  lap_pct_end: number;
  phase: string;
  canonical_clock_contract: "qualified_session_tick";
  source_lap_numbers: number[];
  reference_lap_numbers: number[];
  independence_unit_ids: string[];
  physical_episode_sha256: string;
  speed_min_mps: number | null;
  speed_median_mps: number | null;
  speed_max_mps: number | null;
  metric_channel_lineage: Array<{ metric_id: string; source_channel_ids: string[] }>;
  operational_evidence: OperationalResponseEvidence;
  evidence_state: "calculated" | "observed_correlation";
  applicability: "exact_current_case";
  blocker_reasons: string[];
  authority_ceiling: "observation_only";
  p19_support_authorized: false;
  component_support_authorized: false;
  setup_authorized: false;
};

export type DriverIntent = {
  schema_version: "p3544.driver-intent.v1";
  intent_id: string;
  intent_sha256: string;
  case_id: string;
  intent_revision: number;
  raw_driver_wording: string;
  canonical_symptom: string | null;
  phase_scope: string | null;
  response_regime_scope: "transient" | "steady_state" | "migration" | "unknown" | "context_only";
  traffic_context: "clear" | "exposed" | "unknown" | "context_only";
  stint_context: string | null;
  power_state_context: string | null;
  time_origin_scope: string | null;
  driver_demand_scope: string | null;
  objective: string;
  source: "manual" | "crew_question" | "dial_in" | "smart_engineer" | "session_restore";
  created_at: string;
  supersedes_intent_id: string | null;
  typed_interpretation_provenance: string[];
  authority: "driver_context_only";
  physical_truth_modified: false;
  setup_authorized: false;
};

export type EngineeringMission = {
  what: string;
  where: string;
  why_it_matters: string;
  uncertain: string;
  next: string;
  done_when: string;
  source_authority: "p19_exact_mirror" | "p19_measurement_mirror" | "navigation_only";
  terminal_move_sha256: string;
  source_artifact_ids: string[];
  setup_authorized: boolean;
};

export type CanonicalEngineeringCase = {
  schema_version: "p3544.unified-engineering-case.v1";
  case_id: string;
  case_sha256: string;
  case_revision_sha256: string;
  run_id: string;
  session_id: string;
  recording_sha256: string;
  setup_id: string;
  setup_snapshot_sha256: string;
  objective_id: string;
  condition_epoch_sha256: string;
  p19_reasoning_snapshot_sha256: string;
  p20_state_revision: string;
  p26_knowledge_graph_sha256: string;
  p32_projection_sha256: string;
  p35_assessment_sha256: string;
  p351_projection_sha256: string;
  p33_projection_sha256: string;
  semantic_registry_sha256: string;
  evidence_index_sha256: string;
  driver_intent: DriverIntent | null;
  crew_event_head_sha256: string | null;
  crew_current_subgoal: string | null;
  crew_critic_state: "pass" | "blocked" | "reinvestigate" | "ask_driver" | "unavailable";
  active_workflow_id: string | null;
  active_workflow_revision: string | null;
  primary_opportunity_id: string | null;
  response_artifacts: EngineeringResponseArtifact[];
  response_expectation_contracts: Array<{
    expectation_contract_id: string;
    expectation_sha256: string;
    owning_effect_id: string;
    owning_mechanism_ids: string[];
    relation_id: string;
    metric_id: string;
    authority_ceiling: "relationship_only";
    setup_authorized: false;
    [key: string]: unknown;
  }>;
  response_expectation_evaluations: Array<{
    evaluation_id: string;
    evaluation_sha256: string;
    expectation_contract_id: string;
    response_artifact_id: string;
    result: "matched" | "contradicted" | "inconclusive" | "blocked" | "unavailable";
    matched_metric_ids: string[];
    blocker_reasons: string[];
    setup_authorized: false;
  }>;
  p19_response_admissions: Array<{
    admission_id: string;
    admission_sha256: string;
    case_id: string;
    case_revision_sha256: string;
    response_artifact_id: string;
    p19_reasoning_snapshot_sha256: string;
    assessments: Array<{
      cause_id: string;
      matched_mechanism_ids: string[];
      expectation_contract_ids: string[];
      evaluation_ids: string[];
      result: "support" | "contradiction" | "unresolved" | "blocked";
      basis: string;
      blocker_reasons: string[];
      rank_modified: false;
      setup_authorized: false;
    }>;
    state: "admitted" | "unresolved" | "blocked";
    blocker_reasons: string[];
    authority: "p19_response_adapter_only";
    reasoning_rank_modified: false;
    terminal_action_modified: false;
    setup_authorized: false;
  }>;
  mechanism_ids: string[];
  component_ids: string[];
  effect_readiness: Array<{
    effect_id: string;
    bridge_id: string;
    state: "knowledge_only" | "measurement_ready" | "response_evidence_ready" | "p19_testable" | "blocked";
    response_artifact_ids: string[];
    expected_response_relation_ids: string[];
    exact_control_keys: string[];
    experiment_factor_id: string | null;
    countereffect_measurement_ids: string[];
    missing_evidence: string[];
    deficit_ids: string[];
    authority: "knowledge_only" | "measurement_only" | "exact_p19_projection";
    setup_authorized: boolean;
  }>;
  active_discriminator_id: string | null;
  investigation_id: string | null;
  workspace_revision: string;
  terminal_move_sha256: string;
  mission: EngineeringMission;
  evidence_deficits: Array<{
    deficit_id: string;
    deficit_sha256: string;
    code: EvidenceDeficitCode;
    affected_contract_ids: string[];
    affected_effect_ids: string[];
    affected_mechanism_ids: string[];
    affected_tool_ids: string[];
    required_channel_ids: string[];
    current_channel_capability_ids: string[];
    blocker_reasons: string[];
    recovery_mode: "use_current_data" | "collect_more_laps" | "collect_new_run" | "pit_snapshot" | "controlled_test" | "unavailable";
    mission_eligible: boolean;
    authority: "measurement_routing_only";
    setup_authorized: false;
  }>;
  capability_resolutions: Array<{
    resolution_id: string;
    missing_evidence: string;
    deficit_id: string;
    deficit_code: EvidenceDeficitCode;
    required_channel_ids: string[];
    status: "available_now" | "requires_more_laps" | "requires_new_run" | "pit_snapshot_only" | "controlled_test_required" | "structurally_unavailable";
    recovery: string;
    recovery_mode: "use_current_data" | "collect_more_laps" | "collect_new_run" | "pit_snapshot" | "controlled_test" | "unavailable";
    source_artifact_ids: string[];
    authority: "measurement_routing_only";
    setup_authorized: false;
  }>;
  quantity_observability: Array<{
    quantity_id: string;
    component_family_ids: string[];
    response_artifact_ids: string[];
    state: "currently_observable";
    authority: "quantity_observation_only";
    component_support_authorized: false;
    setup_authorized: false;
  }>;
  semantic_focus: {
    case_id: string;
    case_revision_sha256: string;
    artifact_id: string | null;
    lap_numbers: number[];
    lap_pct_start: number | null;
    lap_pct_end: number | null;
    phase: string | null;
    mechanism_ids: string[];
    response_relation_id: string | null;
    component_ids: string[];
    effect_ids: string[];
    control_keys: string[];
    p19_cause_ids: string[];
    authority: "navigation_only";
  };
  campaign_capture: {
    state: "pending" | "rejected" | "qualified" | "duplicate" | "corrupt";
    blocker_reasons: string[];
    historical_count_credited: false;
    null_count_credited: false;
    negative_control_count_credited: false;
    subgroup_count_credited: false;
    authority: "qualification_only";
  };
  authority: "case_receipt_only";
  p19_authority_unchanged: true;
  setup_authorized: false;
};

export type EngineeringCaseRevision = {
  schema_version: "p3544.engineering-case-revision.v1";
  case_id: string;
  case_revision: number;
  case_sha256: string;
  previous_case_sha256: string | null;
  created_at: string;
  change_category: "initial" | "evidence" | "driver_intent" | "investigation" | "workflow" | "controlled_outcome" | "history" | "setup" | "scope" | "rebuild";
  source_workspace_revision: string;
  case: CanonicalEngineeringCase;
  delivery_diagnostics: null | {
    route_duration_ms: number;
    run_intelligence_build_count_delta: number;
    crew_workspace_build_count_delta: number;
    case_projection_build_count_delta: number;
    response_bytes: number | null;
    authority: "delivery_only";
  };
};
