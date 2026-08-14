export type SessionSummary = {
  run_id: string;
  source_file?: string | null;
  file_hash?: string | null;
  import_time?: string | null;
  sim_date_time?: string | null;
  car_name?: string | null;
  car_path?: string | null;
  track_name?: string | null;
  track_display_name?: string | null;
  track_id_or_path?: string | null;
  session_type?: string | null;
  weather_summary?: string | null;
  air_temp?: number | null;
  track_temp?: number | null;
  wind_speed?: number | null;
  wind_direction?: number | null;
  air_pressure?: number | null;
  telemetry_rate_hz?: number | null;
  variable_count?: number | null;
  record_count?: number | null;
  duration_seconds?: number | null;
  setup_name?: string | null;
  setup_passed_tech?: boolean | null;
  setup_modified?: boolean | null;
  notes: string[];
};

export type RunListItem = {
  run_id: string;
  car_name?: string | null;
  track_name?: string | null;
  setup_name?: string | null;
  imported_at?: string | null;
  best_lap_number?: number | null;
  best_lap_time?: number | null;
  best_lap_time_s?: number | null;
  lap_count?: number | null;
  has_setup_snapshot?: boolean;
  primary_issue?: string | null;
};

export type LapSummary = {
  lap_id: string;
  run_id: string;
  lap_number: number;
  lap_type: string;
  is_complete: boolean;
  is_useful: boolean;
  start_time?: number | null;
  end_time?: number | null;
  lap_time?: number | null;
  pct_min?: number | null;
  pct_max?: number | null;
  pct_span?: number | null;
  sample_count: number;
  avg_speed_mph?: number | null;
  max_speed_mph?: number | null;
  min_speed_mph?: number | null;
  avg_rpm?: number | null;
  min_rpm?: number | null;
  max_rpm?: number | null;
  avg_throttle_pct?: number | null;
  max_throttle_pct?: number | null;
  avg_brake_pct?: number | null;
  max_brake_pct?: number | null;
  min_splitter_mm?: number | null;
  min_splitter_pct?: number | null;
  min_splitter_distance_m?: number | null;
  min_splitter_speed_mph?: number | null;
  max_abs_steering_deg?: number | null;
  avg_abs_steering_deg?: number | null;
  classification_tags: string[];
  confidence_notes: string[];
};

export type SetupSnapshot = {
  setup_id: string;
  run_id: string;
  setup_name?: string | null;
  tape_percent?: number | string | null;
  rear_end_ratio?: number | null;
  lf_ride_height_mm?: number | null;
  rf_ride_height_mm?: number | null;
  lr_ride_height_mm?: number | null;
  rr_ride_height_mm?: number | null;
  lf_front_spring_n_per_mm?: number | null;
  rf_front_spring_n_per_mm?: number | null;
  lr_rear_spring_n_per_mm?: number | null;
  rr_rear_spring_n_per_mm?: number | null;
  nose_weight_percent?: number | null;
  cross_weight_percent?: number | null;
  front_brake_bias_percent?: number | null;
  steering_ratio?: string | null;
  steering_offset_deg?: number | null;
  extracted_values?: Record<string, unknown>;
};

export type EvidenceState =
  | "measured"
  | "calculated"
  | "estimated_proxy"
  | "observed_correlation"
  | "controlled_test_effect"
  | "unavailable"
  | "blocked_by_context"
  | "needs_confirmation";

export type TelemetryEvent = {
  event_id: string;
  run_id: string;
  lap_number?: number | null;
  event_type: string;
  event_subtype?: string | null;
  lap_pct_start?: number | null;
  lap_pct_end?: number | null;
  lap_pct_peak?: number | null;
  distance_m_peak?: number | null;
  zone_name?: string | null;
  severity: string;
  confidence_score: number;
  valid_for_tuning: boolean;
  primary_metric_name?: string | null;
  primary_metric_value?: number | null;
  evidence_json: Record<string, unknown>;
  related_setup_keys: string[];
  evidence_state: EvidenceState;
  source_channels: string[];
  observed_evidence_flags: string[];
  supporting_event_ids: string[];
  blocker_reasons: string[];
};

export type RunOverview = {
  run_id: string;
  session: SessionSummary;
  best_useful_lap?: LapSummary | null;
  laps: LapSummary[];
  events: TelemetryEvent[];
  setup_snapshot?: SetupSnapshot | null;
  primary_findings: string[];
  warnings: string[];
};

export type CanonicalMappingKind =
  | "exact_alias"
  | "unit_converted_alias"
  | "derived_fallback"
  | "incompatible_similarly_named_channel"
  | "unknown";

export type TelemetryCacheCompatibility = {
  status: "current" | "missing_cache" | "reimport_required" | "app_upgrade_required";
  reason: string;
  required_action: "none" | "reimport_original_ibt" | "upgrade_racerzlab";
  automatic_migration_supported: boolean;
  replacement_policy: string;
};

export type TelemetryCapabilitySummary = {
  declared_channels: number;
  cached_channels: number;
  unmapped_channels: number;
  warning_channels: number;
  lossless_archive_complete: boolean;
  analysis_readiness_counts: Record<string, number>;
};

export type TelemetryCapabilitiesResponse = {
  run_id: string;
  manifest_schema_version?: number;
  universal_archive_version?: number;
  cache_compatibility: TelemetryCacheCompatibility;
  capability_summary: TelemetryCapabilitySummary;
};

export type DialInClarification = {
  needed: boolean;
  question?: string | null;
  options: string[];
};

export type DialInSwing = {
  id: string;
  title: string;
  setup_area: string;
  candidate_control_label: string;
  related_control_keys: string[];
  influence_label: string;
  strength_label: string;
  risk_label: string;
  mechanism_to_verify: string;
  counter_effect_to_watch: string;
  validate_with: string[];
  validate_with_labels?: string[];
  watch_for: string[];
  watch_for_labels?: string[];
  readiness_label: string;
  measurement_needed: string;
  evidence_state: EvidenceState;
  source_channels: string[];
  observed_evidence_flags: string[];
  supporting_event_ids: string[];
  blocker_reasons: string[];
};

export type HiddenEvidenceSummary = {
  evidence_flags: string[];
  evidence_groups?: unknown[];
  present_evidence: string[];
  missing_evidence: string[];
  readiness_by_candidate?: unknown[];
  ranking_reasons?: Record<string, string[]>;
  disabled_by_capability?: Array<Record<string, string>>;
  capability_flags?: string[];
  observed_mechanism_flags?: string[];
  supporting_event_ids?: string[];
};

export type DialInEvidenceStrength = {
  level: "unavailable" | "capability_only" | "observed_mechanism";
  readiness: "blocked" | "measurement_required" | "test_hypothesis_ready";
  capability_flags: string[];
  observed_mechanism_flags: string[];
  supporting_event_ids: string[];
  setup_test_ready: boolean;
  requires_controlled_test: boolean;
  reason: string;
};

export type DialInResponse = {
  run_id: string;
  complaint_raw: string;
  interpreted_symptom?: string | null;
  interpreted_phase?: string | null;
  balance_direction?: string | null;
  confidence_label: string;
  readiness_label: string;
  driver_message: string;
  top_swings: DialInSwing[];
  next_step?: string | null;
  clarification: DialInClarification;
  hidden_evidence_summary?: HiddenEvidenceSummary | null;
  warnings: string[];
  evidence_state: EvidenceState;
  source_channels: string[];
  blocker_reasons: string[];
  evidence_strength?: DialInEvidenceStrength | null;
};

export type DialInRequest = {
  complaint: string;
  selected_lap?: number | null;
  selected_zone_start_pct?: number | null;
  selected_zone_end_pct?: number | null;
  selected_zone_label?: string | null;
  selected_phase?: string | null;
  objective?: DialInObjective;
  priority?: DialInPriority;
  baseline_run_id?: string | null;
  test_run_id?: string | null;
  car_family?: string | null;
  track_family?: string | null;
  package_archetype?: string | null;
  limit?: number;
  include_debug_evidence?: boolean;
};

export type DialInObjective = "race-pace" | "qualifying" | "long-run" | "tire-conservation" | "driver-confidence";

export type DialInPriority =
  | "overall-pace"
  | "entry-security"
  | "center-rotation"
  | "exit-drive"
  | "tire-life"
  | "platform-margin";

export type DialInDecisionContext = {
  selected_zone_start_pct?: number | null;
  selected_zone_end_pct?: number | null;
  selected_zone_label?: string | null;
  selected_phase?: string | null;
  objective?: DialInObjective;
  priority?: DialInPriority;
};

export type ControlledTestStage = {
  stage: "A" | "B" | "A2";
  setup_instruction: string;
  warmup_laps: number;
  required_flying_laps: number;
  purpose: string;
};

export type ControlledTestCard = {
  hypothesis: string;
  control_key: string;
  control_label: string;
  exact_change: string;
  change_size: string;
  target_phase: string;
  expected_mechanism: string;
  success_metrics: string[];
  countereffects: string[];
  rollback_rule: string;
  keep_rule: string;
  stop_rule: string;
  stages: ControlledTestStage[];
};

export type MeasurementMission = {
  purpose: string;
  procedure: string[];
  required_laps_or_passes: number;
  target_phase: string;
  acceptance_thresholds: string[];
  stop_rule: string;
  blockers: string[];
};

export type KaizenEvidencePacket = {
  decision: "test" | "measure";
  confidence_score: number;
  confidence_is_calibrated_probability: boolean;
  confidence_basis: string;
  recommendation_score_components?: Record<string, number>;
  recommendation_score_basis?: string | null;
  blockers: string[];
  primary_test?: ControlledTestCard | null;
  measurement_mission?: MeasurementMission | null;
  race_mode_summary: string;
  learning_mode_explanation: string;
};

export type TestQualityResult = {
  protocol_valid: boolean;
  score: number;
  verdict: "keep" | "undo" | "retest" | "invalid";
  blockers: string[];
  supporting_evidence: string[];
  contradictory_evidence: string[];
  controlled_effect_eligible: boolean;
};

export type LearningCaptureState = "not_applicable" | "captured" | "blocked";

export type ControlledWorkflow = {
  workflow_id: string;
  created_at: string;
  updated_at: string;
  status: "planned" | "a_recorded" | "b_recorded" | "a2_recorded" | "scored" | "cancelled";
  source_run_id: string;
  complaint: string;
  packet: KaizenEvidencePacket;
  stage_run_ids: Partial<Record<"A" | "B" | "A2", string>>;
  stage_eligible_lap_numbers: Partial<Record<"A" | "B" | "A2", number[]>>;
  stage_experiment_contexts: Partial<Record<"A" | "B" | "A2", Record<string, unknown>>>;
  analysis_version: string;
  execution: {
    phase_effect_b_vs_a_s?: number | null;
    phase_effect_b_vs_a2_s?: number | null;
    empirical_noise_s?: number | null;
    empirical_noise_observations?: number;
    minimum_alignment_confidence?: number | null;
    target_effect_distributions_consistent?: boolean | null;
    target_effect_distribution_state?: "faster" | "slower" | "inconclusive" | "inconsistent" | null;
    countereffect_passed?: boolean | null;
    countereffect_noise_by_phase_s?: Record<string, number>;
    control_guardrails_passed?: boolean | null;
    control_guardrail_metrics?: Record<string, number>;
  } | null;
  reproduction_snapshot: Record<string, unknown>;
  quality: TestQualityResult | null;
  learning_admitted: boolean | null;
  learning_capture_state: LearningCaptureState;
  learning_capture_experience_id: string | null;
  learning_capture_experience_sha256: string | null;
  learning_capture_blocker_reason: string | null;
};

export type TelemetryCursor = {
  selected_run_id?: string | null;
  selected_lap?: number | null;
  selected_sample_index?: number | null;
  selected_lap_dist_ft?: number | null;
  selected_lap_pct?: number | null;
  selected_event_id?: string | null;
};

export type TrackMapResolution = {
  status: "matched" | "ambiguous" | "missing" | "manual_required";
  map_id?: string | null;
  map_name?: string | null;
  confidence?: string;
  message?: string | null;
};

export type ImportIbtResponse = {
  run_id?: string | null;
  status: {
    status: string;
    message: string;
    implemented: string[];
    remaining: string[];
    warnings: string[];
  };
  cache?: {
    path?: string | null;
    format?: string | null;
    used_fallback: boolean;
  } | null;
  track_map?: TrackMapResolution | null;
  analysis_status?: string | null;
  existing_run_updated?: boolean;
};

export type ChannelCatalogItem = {
  name: string;
  label?: string | null;
  description?: string | null;
  unit?: string | null;
  type?: string | null;
  count: number;
  is_raw: boolean;
  is_calculated: boolean;
  is_proxy: boolean;
  formula?: string | null;
  dependencies: string[];
  used_by_charts: string[];
  used_by_events: string[];
  used_by_analyses: string[];
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  sample_value?: unknown;
  missing_status?: string | null;
  group?: string | null;
  source?: string | null;
};

export type ChannelSummaryItem = {
  name: string;
  label?: string | null;
  description?: string | null;
  unit?: string | null;
  type?: string | null;
  count?: number;
  is_raw: boolean;
  is_calculated: boolean;
  is_proxy: boolean;
  missing_status?: string | null;
  group?: string | null;
  source?: string | null;
};

export type TraceChannelPayload = {
  unit?: string | null;
  values: Array<number | string | null>;
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  missing_status?: string | null;
};

export type TraceResponse = {
  run_id: string;
  lap?: number | null;
  x_name?: string | null;
  x_unit?: string | null;
  x: Array<number | null> | {
    lap_dist_ft?: Array<number | null>;
    lap_dist_pct?: Array<number | null>;
  };
  x_by_name?: Record<string, Array<number | null>> | null;
  channels: Record<string, Array<number | null> | TraceChannelPayload>;
  events?: TelemetryEvent[];
  sample_count: number;
  downsample: number | string;
  preserve_extrema?: boolean;
  trace_meta?: {
    raw_resolution?: boolean;
    raw_source_row_count?: number;
    returned_row_count?: number;
    downsample_applied?: boolean;
    downsample?: number | string;
    bucket_size?: number;
    window_start_ft?: number | null;
    window_end_ft?: number | null;
    session_time_delta_s_mean?: number | null;
    sample_index_delta_mean?: number | null;
    distance_delta_ft_mean?: number | null;
    approx_hz?: number | null;
    distance_duplicate_count?: number;
    distance_rounded_or_deduped?: boolean;
    sample_identity?: string;
    lr_ride_height_offset_applied?: boolean;
    lr_ride_height_offset_in?: number | null;
    lr_ride_height_offset_reason?: string | null;
    lr_ride_height_offset_car_path?: string | null;
  } | null;
};

export type PlatformEventSeverity = "info" | "watch" | "high" | "critical";
export type PlatformEventConfidence = "low" | "medium" | "high";
export type PlatformEventDisplayScope = "actionable" | "watch" | "internal";
export type PlatformEventVisibilityMode = "actionable" | "proxy" | "all";
export type PlatformDiagnosticState = "finding" | "clear_check" | "context";
export type PlatformEventsEvidenceStatus = "findings" | "clear" | "unavailable";

export type PlatformEventItem = {
  event_id: string;
  event_type: string;
  title: string;
  severity: PlatformEventSeverity;
  confidence: PlatformEventConfidence;
  display_scope: PlatformEventDisplayScope;
  is_visible_default: boolean;
  reason_for_hidden?: string | null;
  diagnostic_state: PlatformDiagnosticState;
  contributes_to_backend_evidence: boolean;
  lap?: number | null;
  sample_index?: number | null;
  lap_dist_ft?: number | null;
  lap_pct?: number | null;
  track_x_ft?: number | null;
  track_y_ft?: number | null;
  primary_value?: number | null;
  primary_unit?: string | null;
  channels_used: string[];
  evidence: string[];
  is_proxy_based: boolean;
  proxy_warning?: string | null;
  metadata: Record<string, unknown>;
  evidence_state: EvidenceState;
  source_channels: string[];
  blocker_reasons: string[];
};

export type PlatformEventsReport = {
  run_id: string;
  lap: number | null;
  evidence_status: PlatformEventsEvidenceStatus;
  events: PlatformEventItem[];
  blocker_reasons: string[];
};
