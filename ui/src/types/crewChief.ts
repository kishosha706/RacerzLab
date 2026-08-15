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

export type CrewChiefWorkspaceIdentity = {
  run_id: string;
  session_id: string;
  selected_scope_hash: string;
  reasoning_snapshot_sha256: string;
  p20_state_revision: string;
  p20_profile_hash: string | null;
  p26_graph_version: string;
  p26_knowledge_graph_sha256: string;
  p26_reasoning_snapshot_sha256: string;
  p32_projection_sha256: string;
  run_sentinel_sha256: string;
  learning_history_revision: string;
  learning_projection_sha256: string;
  setup_id: string;
  setup_snapshot_sha256: string;
  vehicle_runtime_identity_hash: string;
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
  typed_artifact: CrewChiefPerformanceArtifact | null;
  authority_ceiling: "observation_only" | "context_only" | "measurement_only" | "p19_projection_only" | "attention_only";
};

export type CrewChiefTerminalDecision = {
  kind: "driver_question" | "driver_focus" | "measurement_mission" | "controlled_test" | "observe_only" | "no_call";
  title: string;
  instruction: string;
  authority: "context_only" | "measurement_only" | "p19_projection_only";
  control_key: string | null;
  current_value: string | null;
  proposed_value: string | null;
  source_event_ids: string[];
  workflow_id: string | null;
  workflow_revision: string | null;
  blocker_reasons: string[];
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
  status: "open" | "complete" | "stale" | "abandoned";
};

export type CrewChiefWorkspace = {
  schema_version: "p33.crew-chief-workspace.v2";
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
    completed_tool_ids: string[];
    pending_driver_question_id: string | null;
    driver_answers: string[];
    last_decision_kind: string | null;
    accepted_workspace_revision: string;
  };
  evidence_index: {
    workspace_revision: string;
    entries: CrewChiefEvidenceEntry[];
    index_hash: string;
  };
  current_subgoal: null | {
    subgoal_id: string;
    title: string;
    selected_tool: string;
    why_this_tool: string;
    priority_rank: number;
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
  performance_intelligence: PerformanceIntelligenceProjection;
  learning_prior: CrewChiefLearningPrior;
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
