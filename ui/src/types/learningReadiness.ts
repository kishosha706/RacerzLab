export type ReadinessCount = {
  key: string;
  label: string;
  current: number;
  required: number;
  unit: string;
  qualified_only: true;
};

export type CampaignReadiness = {
  campaign_kind: string;
  label: string;
  usable_units: number;
  required_units: number;
  invalid_attempts: number;
  remaining_units: number;
  state: "not_started" | "collecting" | "complete";
};

export type CapabilityReadiness = {
  capability_key: string;
  label: string;
  state: "locked" | "shadow" | "descriptive_only" | "deterministic";
  summary: string;
  blockers: string[];
  authority: "p19_p20_unchanged";
};

export type LearningDebt = {
  debt_key: string;
  summary: string;
  collection_action: string;
};

export type CampaignOperationContext = {
  reference_run_id: string;
  car_path: string;
  track_id: string;
  iracing_build_version: string;
  fuel_band: { minimum: number; maximum: number } | null;
  track_temperature_band: { minimum: number; maximum: number } | null;
  air_temperature_band: { minimum: number; maximum: number } | null;
  maximum_traffic_exposure_fraction: number;
  minimum_clean_laps_per_unit: number;
};

export type CampaignOperationStartResponse = {
  operation_id: string;
  campaign_kind: string;
  context: CampaignOperationContext;
  authority: "data_collection_only";
};

export type ActiveCampaignProjection = {
  operation: {
    operation_id: string;
    campaign_kind: string;
    context: CampaignOperationContext;
    authority: "data_collection_only";
  };
  state: "active" | "paused" | "completed" | "abandoned";
  progress: {
    independent_units: number;
    eligible_laps: number;
    remaining_independent_units: number;
    remaining_eligible_laps: number;
    complete: boolean;
    blockers: string[];
  };
  latest_assessment: {
    run_id: string;
    state: "usable" | "rejected" | "pending_protocol" | "infeasible";
    accepted_lap_numbers: number[];
    rejected_lap_numbers: number[];
    lap_rejection_reasons: Record<string, string[]>;
    rejection_reasons: string[];
  } | null;
  prospective_prediction_count: number;
  unscored_prediction_count: number;
};

export type ProspectivePredictionResponse = {
  prediction_id: string;
  operation_id: string;
  source_run_id: string;
  predicted_at: string;
  reasoning_snapshot_id: string;
  predicted_mechanism: string;
  predicted_control_response: string;
  predicted_countereffects: string[];
  success_criteria: string[];
  failure_criteria: string[];
  prospective: true;
  authority: "shadow_only";
};

export type AcquisitionOption = {
  campaign_kind: string;
  label: string;
  state: "highest" | "candidate" | "infeasible";
  helps: string[];
  need_next: string[];
  blockers: string[];
  score: {
    deficit_fraction: number;
    rule_fit_estimate: number;
    gates_helped: number;
    estimated_driver_laps: number;
    deterministic_value: number;
    formal_information_gain: false;
  };
  authority: "collection_guidance_only";
};

export type LearningLedgerEntry = {
  ledger_key: string;
  section: "proven_guardrail" | "in_validation" | "failed_validation" | "locked";
  label: string;
  summary: string;
  current: number | null;
  required: number | null;
  evidence_basis: "verified_architecture" | "qualified_real_evidence" | "frozen_gate_policy";
};

export type AdvancedCapabilityReview = {
  decision: "remain_locked" | "eligible_for_limited_activation";
  eligible_capability_key: string | null;
  explanation: string;
  capabilities: Array<{
    capability_key: string;
    state: string;
    historical_gate: "pass" | "fail" | "pending";
    prospective_gate: "pass" | "fail" | "pending";
    subgroup_gate: "pass" | "fail" | "pending";
    negative_control_gate: "pass" | "fail" | "pending";
    blockers: string[];
  }>;
};

export type LearningReadinessProjection = {
  run_id: string;
  session_id: string | null;
  scope_key: string;
  generated_at: string;
  deterministic_authority: "P19 reasoning / P20 awareness";
  advanced_models_summary: "Shadow only";
  archived_sessions: number;
  archived_runs: number;
  counts: ReadinessCount[];
  campaigns: CampaignReadiness[];
  capabilities: CapabilityReadiness[];
  vehicle_profile_status: string;
  vehicle_profile_fields_ready: string[];
  vehicle_profile_fields_blocked: string[];
  debts: LearningDebt[];
  active_campaigns: ActiveCampaignProjection[];
  acquisition_options: AcquisitionOption[];
  learning_ledger: LearningLedgerEntry[];
  capability_review: AdvancedCapabilityReview | null;
  offline_evaluation_only: true;
};
