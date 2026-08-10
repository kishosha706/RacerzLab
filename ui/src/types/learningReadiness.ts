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

export type P23FirstActivationAudit = {
  audit_id: string;
  audit_hash: string;
  selected_capability: "steering_workload_envelope";
  selection_summary: string;
  protocol_id: string;
  protocol_hash: string;
  historical: { state: string; qualified_real_units: number; required_real_units: number; blockers: string[] };
  prospective: { state: string; qualified_real_units: number; required_real_units: number; blockers: string[] };
  negative_controls: { state: string; qualified_real_units: number; required_real_units: number; blockers: string[] };
  subgroups: { state: string; qualified_real_units: number; required_real_units: number; blockers: string[] };
  activation_decision: "no_activation_earned" | "historical_validation_passed" | "prospective_shadow_active" | "limited_activation_earned" | "blocked_by_evidence_deficit";
  exact_authority_envelope: string[];
  remaining_locks: string[];
  next_collection_missions: string[];
  p19_sole_reasoning_setup_authority: true;
  p20_sole_state_projection: true;
};

export type P23FlightRecorderEntry = {
  lap_number: number;
  state: "qualified" | "excluded" | "context_boundary" | "inventory";
  reasons: string[];
  applied_control_mutation_ids: string[];
  requested_control_mutation_ids: string[];
  nearby_context: "acceptable" | "rejected" | "unknown";
  sample_continuity: "pass" | "fail" | "unknown";
  sub_tick_coverage_fraction: number;
};

export type P25NullSessionRunCard = {
  card_id: string;
  card_hash: string;
  state: "ready" | "blocked";
  protocol_id: string;
  reference_run_id: string;
  car_identity: string;
  build_identity: string;
  track_identity: string;
  setup_identity: string;
  ffb_fingerprint_sha256: string;
  steering_conversion_model: string;
  minimum_warmup_laps: 1;
  minimum_eligible_laps: 10;
  fuel_band_minimum: number;
  fuel_band_maximum: number;
  tire_compound: string;
  tire_context_requirement: string;
  control_state_requirements: string[];
  telemetry_requirements: string[];
  null_expectation: string;
  qualification_criteria: string[];
  blocker_reasons: string[];
  observed_run_id: null;
  observed_qualification_state: null;
};

export type P23AcquisitionProgress = {
  total_attempts: number;
  qualified_attempts: number;
  historical_sessions: number;
  required_historical_sessions: 9;
  null_stints: number;
  required_null_stints: 10;
  negative_controls: number;
  required_negative_controls: 8;
  covered_subgroups: number;
  required_subgroups: 9;
  subgroup_memberships: string[];
  profile_status: "complete" | "incomplete";
  prospective_sessions: number;
  required_prospective_sessions: 10;
  prospective_status: "locked_until_historical_gate" | "available" | "collecting";
  rejected_attempts: number;
  next_best_collection_kind: "profile_validation" | "historical_exact_ffb" | "same_setup_null" | "negative_control" | "subgroup_coverage" | "historical_gate_review";
  next_best_collection: string;
  latest_certificate_id: string | null;
  latest_run_id: string | null;
  latest_qualification_state: "qualified" | "rejected" | "partial" | "inventory_only" | null;
  latest_eligible_laps: number;
  latest_excluded_laps: number;
  latest_blocker: string | null;
  latest_blockers: string[];
  latest_signal_truth_state: "ready" | "limited" | "scientific_debt" | "missing" | null;
  latest_ffb_fingerprint_state: "ready" | "limited" | "unavailable" | null;
  latest_ffb_fingerprint_sha256: string | null;
  latest_dataset_admissions: string[];
  latest_telemetry_ownership_state: "verified" | "blocked" | null;
  latest_null_run_card: P25NullSessionRunCard | null;
  latest_flight_recorder: P23FlightRecorderEntry[];
  latest_flight_recorder_total: number;
  latest_flight_recorder_truncated: boolean;
  activation_status: "no_activation_earned";
  p23_authority: "shadow_only";
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
  first_activation_audit: P23FirstActivationAudit | null;
  p23_acquisition: P23AcquisitionProgress | null;
  offline_evaluation_only: true;
};
