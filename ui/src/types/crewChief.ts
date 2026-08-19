import type { EvidenceState } from "./telemetry";
import type {
  CornerPerformanceChain,
  DriverVehicleSeparation,
  LapTimeOpportunity,
  PerformanceIntelligenceProjection,
  PerformancePhaseState,
} from "./performanceIntelligence";
import type {
  CrewChiefLearningPrior,
  P19ReasoningMemory,
  ProblemFingerprint,
} from "./engineeringLearning";
import type { InvestigationImprovementProjection } from "./investigationImprovement";
import type {
  PerformanceMechanismAssessment,
  VehicleDynamicsFocusArtifact,
  VehicleDynamicsInspectionToolId,
} from "./vehicleDynamics";
import type { VehicleSystemsRuntimeIdentity } from "./vehicleSystems";
import type { EngineeringAwarenessProjection } from "./engineeringAwareness";
import type { CurrentEngineeringKnowledgeProjection } from "./engineeringKnowledge";
import type {
  CanonicalEngineeringCase,
  EngineeringResponseArtifact,
} from "./engineeringCase";

export type EngineeringObjective =
  | "qualifying_peak"
  | "race_long_run"
  | "tire_conservation"
  | "driver_confidence"
  | "traffic_robustness"
  | "superspeedway_stability"
  | "fuel_strategy";

export type CrewChiefPerformanceArtifactType =
  | "lap_time_opportunity"
  | "time_loss_origin"
  | "corner_performance_chain"
  | "exit_carry"
  | "path_efficiency"
  | "driver_vehicle_separation"
  | "track_demand"
  | "component_performance_link"
  | "objective_envelope";

export type CrewChiefPerformanceArtifact =
  | { artifact_type: "lap_time_opportunity"; opportunity: LapTimeOpportunity }
  | { artifact_type: "time_loss_origin"; opportunity: LapTimeOpportunity }
  | {
    artifact_type: "corner_performance_chain";
    start_pct: number;
    end_pct: number;
    chain: CornerPerformanceChain;
  }
  | { artifact_type: "exit_carry"; opportunity: LapTimeOpportunity }
  | {
    artifact_type: "path_efficiency";
    chain_id: string;
    phase_state: PerformancePhaseState;
  }
  | {
    artifact_type: "driver_vehicle_separation";
    chain_id: string;
    track_region: string;
    start_pct: number;
    end_pct: number;
    separation: DriverVehicleSeparation;
  }
  | {
    artifact_type: "track_demand";
    profile: PerformanceIntelligenceProjection["track_demand"];
  }
  | {
    artifact_type: "component_performance_link";
    influence: PerformanceIntelligenceProjection["component_influences"][number];
  }
  | {
    artifact_type: "objective_envelope";
    envelope: PerformanceIntelligenceProjection["objective_envelope"];
  }
  | {
    artifact_type: "unavailable";
    claimed_artifact_type: CrewChiefPerformanceArtifactType;
    blocker_reasons: string[];
  };

export type CrewChiefVehicleDynamicsFocusArtifact = {
  artifact_type: "vehicle_dynamics_focus";
  inspection_tool_id: VehicleDynamicsInspectionToolId;
  assessment_sha256: string;
  focus: VehicleDynamicsFocusArtifact;
};

export type CrewChiefEngineeringResponseArtifact = {
  artifact_type: "engineering_response";
  case_id: string;
  case_revision_sha256: string;
  assessment_sha256: string;
  response: EngineeringResponseArtifact;
};

export type CrewChiefEvidenceArtifact =
  | CrewChiefPerformanceArtifact
  | CrewChiefVehicleDynamicsFocusArtifact
  | CrewChiefEngineeringResponseArtifact;

export type CrewChiefWorkspaceIdentity = {
  run_id: string;
  session_id: string;
  selected_scope_hash: string;
  reasoning_snapshot_sha256: string;
  p20_state_revision: string;
  p20_projection_sha256: string;
  p20_profile_hash: string | null;
  p26_graph_version: string;
  p26_knowledge_graph_sha256: string;
  p26_reasoning_snapshot_sha256: string;
  p32_projection_sha256: string;
  p35_assessment_sha256: string;
  run_sentinel_sha256: string;
  learning_history_revision: string;
  learning_ledger_head_sha256: string | null;
  learning_projection_sha256: string;
  setup_id: string;
  setup_snapshot_sha256: string;
  vehicle_runtime_identity_hash: string;
  vehicle_runtime_identity: VehicleSystemsRuntimeIdentity | null;
  active_workflow_id: string | null;
  active_workflow_revision: string | null;
  objective_id: EngineeringObjective;
  investigation_id: string | null;
  workspace_revision: string;
};

export type CrewChiefEvidenceEntry = {
  artifact_id: string;
  producer_id: string;
  run_id: string;
  session_id: string;
  setup_id: string | null;
  workspace_run_id: string;
  workspace_session_id: string;
  workspace_setup_id: string;
  source_run_id: string;
  source_session_id: string | null;
  source_setup_id: string | null;
  source_setup_sha256: string | null;
  source_build_context_sha256: string | null;
  source_provenance_available: boolean;
  lap_numbers: number[];
  lap_pct_start: number | null;
  lap_pct_end: number | null;
  phase: string | null;
  mechanism_ids: string[];
  component_ids: string[];
  control_keys: string[];
  objective: EngineeringObjective;
  source_channels: string[];
  evidence_state: EvidenceState;
  polarity: "support" | "contradiction" | "neutral";
  blocker_reasons: string[];
  typed_artifact: CrewChiefEvidenceArtifact | null;
  authority_ceiling: "observation_only" | "context_only" | "measurement_only" | "p19_projection_only" | "attention_only";
};

export type CrewChiefTerminalDecision = {
  kind: "driver_question" | "driver_focus" | "measurement_mission" | "controlled_test" | "observe_only" | "no_call";
  title: string;
  instruction: string;
  authority: "context_only" | "measurement_only" | "p19_projection_only";
  control_key: string | null;
  setup_effect_id: string | null;
  experiment_factor_id: string | null;
  direction_sign: -1 | 1 | null;
  current_value: string | null;
  proposed_value: string | null;
  source_event_ids: string[];
  workflow_id: string | null;
  workflow_revision: string | null;
  blocker_reasons: string[];
};

export type CrewChiefToolDefinition = {
  tool_id: string;
  allowed_scope: "run" | "session" | "component" | "workflow";
  input_schema: string;
  output_artifact_type: string;
  authority_ceiling: "observation_only" | "context_only" | "measurement_only";
  required_sources: string[];
};

export type DriverAnswerInterpretation = {
  answer: string;
  phase_scope: string[];
  response_regime_scope: Array<"transient" | "steady_state">;
  traffic_scope: "all" | "disturbed_air" | "clean_air" | "compare_air_states";
  stint_scope: "all" | "immediate" | "migration";
  power_state_scope: "all" | "brake_applied" | "brake_release" | "pre_power" | "power_on";
  time_origin_scope: "all" | "local" | "exit_carry" | "following_straight";
  driver_demand_scope: string[];
  context_record_only: boolean;
};

export type CrewChiefInvestigation = {
  investigation_id: string;
  workspace_identity: CrewChiefWorkspaceIdentity;
  origin: "post_import" | "driver_report" | "manual_review";
  objective: EngineeringObjective;
  raw_driver_report: string;
  canonical_problem: string;
  opening_reasoning: P19ReasoningMemory;
  opening_problem: ProblemFingerprint;
  opened_at: string;
  consumption_baseline: null | {
    baseline_sha256: string;
    event_head: number;
    eligible_lap_ids: string[];
    measurement_attempt_ids: string[];
    workflow_id: string | null;
    workflow_revision: string | null;
    wall_clock_started_at: string;
  };
  status: "open" | "complete" | "stale" | "abandoned";
};

export type CrewChiefWorkspace = {
  schema_version: "p352.crew-chief-workspace.v1";
  identity: CrewChiefWorkspaceIdentity;
  generated_at: string;
  cache_state: "cold" | "warm";
  investigation: CrewChiefInvestigation | null;
  folded_state: null | {
    investigation_id: string;
    status: "open" | "complete" | "stale" | "abandoned";
    event_count: number;
    last_sequence: number;
    objective: EngineeringObjective;
    current_subgoal: string | null;
    completed_tool_ids: string[];
    pending_driver_question_id: string | null;
    driver_answers: string[];
    driver_answer_interpretations: DriverAnswerInterpretation[];
    hypotheses: Array<{
      cause_id: string;
      p19_state: "likely" | "possible" | "ruled_out" | "unresolved";
      progress:
        | "not_inspected"
        | "inspection_requested"
        | "inspected_no_evidence"
        | "support_found"
        | "contradiction_found"
        | "discriminator_pending"
        | "unresolved_after_inspection"
        | "p19_ruled_out"
        | "needs_driver_answer"
        | "needs_measurement"
        | "stale";
      component_ids: string[];
      support_artifact_ids: string[];
      contradiction_artifact_ids: string[];
    }>;
    latest_critique_outcome: "pass" | "blocked" | "reinvestigate" | "ask_driver" | null;
    last_decision_kind: string | null;
    stale_reason: string | null;
    accepted_workspace_revision: string;
  };
  evidence_index: {
    workspace_revision: string;
    entries: CrewChiefEvidenceEntry[];
    index_hash: string;
  };
  engineering_case: CanonicalEngineeringCase;
  available_tools: CrewChiefToolDefinition[];
  tool_eligibility: Array<{
    tool_id: string;
    currently_relevant: boolean;
    required_by_mandatory_gate: boolean;
    expected_to_separate: string[];
    available_artifact_types: string[];
    missing_inputs: string[];
    cost_class: "cheap" | "moderate";
    safe_priority_tier: string;
    skip_reason: string | null;
  }>;
  current_subgoal: null | {
    subgoal_id: string;
    title: string;
    selected_tool: string;
    why_this_tool: string;
    distinguishes_cause_ids: string[];
    mechanism_ids: string[];
    bridge_ids: string[];
    effect_ids: string[];
    opportunity_id: string | null;
    required_discriminator_id: string | null;
    exact_control_keys: string[];
    experiment_factor_ids: string[];
    driver_answer_interpretation: DriverAnswerInterpretation | null;
    required_evidence: string[];
    stop_condition: string;
    priority_rank: number;
  };
  latest_tool_result: null | {
    inspection_request_id: string | null;
    tool_id: string;
    workspace_revision: string;
    status: "complete" | "blocked" | "no_finding";
    summary: string;
    artifact_ids: string[];
    cause_ids: string[];
    component_ids: string[];
    blocker_reasons: string[];
    authority_ceiling: "observation_only" | "context_only" | "measurement_only";
    finding_kind: "support" | "contradiction" | "discriminator" | "negative_control" | "no_signal" | "unavailable";
    observed_finding: string | null;
    strongest_support_artifact_ids: string[];
    strongest_contradiction_artifact_ids: string[];
    missing_evidence: string[];
    ambiguity_before: number;
    ambiguity_after: number;
    cause_ids_actually_examined: string[];
    component_ids_actually_examined: string[];
    recommended_next_inspection: string | null;
    selection_receipt: null | {
      selection_policy_id: string;
      selection_sha256: string;
      candidate_count: number;
      selected_count: number;
      omitted_count: number;
      selected_artifact_ids: string[];
      selection_reasons: string[];
      required_artifact_ids: string[];
      required_artifacts_present: boolean;
    };
  };
  critique: {
    outcome: "pass" | "blocked" | "reinvestigate" | "ask_driver";
    passed: boolean;
    findings: string[];
    strongest_contradiction: string | null;
  };
  pending_driver_question: null | {
    question_id: string;
    workspace_revision: string;
    question: string;
    answer_options: string[];
    reason: string;
    authority: "context_only";
  };
  prospective_consumption: null | {
    baseline_sha256: string;
    accepted_lap_ids_after_open: string[];
    measurement_attempt_ids_after_open: string[];
    tool_request_event_ids: string[];
    tool_execution_duration_ms: number[];
    driver_question_ids: string[];
    continue_action_count: number;
    workflow_ids_opened_after_open: string[];
    authority: "operational_counts_only";
  };
  success_contract: null | {
    contract_id: string;
    workspace_revision: string;
    objective: EngineeringObjective;
    target_scope: string;
    primary_metric: { metric: string; threshold: string; threshold_source: string; hard_limit: boolean };
    minimum_repetitions: number;
    independence_unit: string;
    acceptance_rule: string;
    rejection_rule: string;
    stop_rule: string;
    rollback_rule: string;
  };
  p19_mission_contract: null | {
    schema_version: "p19.measurement-mission.v2";
    contract_id: string;
    contract_sha256: string;
    run_id: string;
    session_id: string | null;
    source_setup_id: string;
    setup_sha256: string;
    required_laps: number;
    acceptance_thresholds: string[];
    integrity_stop_rules: string[];
    purpose: string;
  };
  engineering_awareness: EngineeringAwarenessProjection;
  performance_intelligence: PerformanceIntelligenceProjection;
  vehicle_dynamics: PerformanceMechanismAssessment;
  engineering_knowledge: CurrentEngineeringKnowledgeProjection;
  learning_prior: CrewChiefLearningPrior;
  investigation_improvement: InvestigationImprovementProjection;
  run_sentinel: {
    mission_state: "collecting" | "blocked_by_p19" | "stopped_by_p19" | "awaiting_p19_score" | "collection_complete";
    p19_plan_kind: "controlled_test" | "measurement_mission" | "discriminator" | "stop_testing" | "blocked";
    mission: string;
    need: string;
    hold_constant: string[];
    watch: string[];
    success: string;
    stop: string[];
    required_laps: number | null;
    context_cleared_laps: number;
    mission_accepted_lap_ids: string[];
    measurement_attempt_ids: string[];
    mission_acceptance_basis: "unbound" | "p19_measurement_attempt" | "controlled_workflow_stage";
    collection_complete: boolean;
    stage: "measurement" | "A" | "B" | "A2" | "blocked" | "stopped" | "awaiting_score";
    laps: Array<{
      lap_id: string;
      lap_number: number;
      status: "context_cleared" | "rejected";
      reasons: string[];
      context_ordinal: number | null;
    }>;
    blocker_reasons: string[];
  };
  terminal_decision: CrewChiefTerminalDecision;
  response_history_ids: string[];
  driver_memory_ids: string[];
  p19_cause_ids: string[];
  p19_contradiction_artifact_ids: string[];
  p20_episode_ids: string[];
  p26_component_ids: string[];
  post_run_brief: string[];
  generative_boundary: {
    enabled: false;
    mode: "shadow_only";
    authority: "none";
    may_request_approved_tools: boolean;
    setup_values_visible: false;
    blocker_reason: string;
  };
  adaptive_research: {
    state: "data_locked";
    authority: "none";
    production_protocol: "one_factor_p19_aba2";
    candidate_methods: string[];
    activation_gate: string;
  };
  blocker_reasons: string[];
};
