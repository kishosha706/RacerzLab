// -- Compare Tab TypeScript types ---------------------------
// Matches verified /api/compare response shape.

export interface ChannelDeltaStats {
  channel: string;
  label: string;
  unit: string;
  baseline_avg: number | null;
  test_avg: number | null;
  delta_avg: number | null;
  baseline_min: number | null;
  test_min: number | null;
  baseline_max: number | null;
  test_max: number | null;
  direction: "better" | "worse" | "neutral" | "context" | "mixed" | null;
  interpretation: string | null;
  confidence: number | null;
}

export interface CornerMetric {
  ride_height_in: ChannelDeltaStats | null;
  shock_defl_in: ChannelDeltaStats | null;
  shock_vel_in_s: ChannelDeltaStats | null;
  shock_velocity_rms: ChannelDeltaStats | null;
  shock_activity_index: ChannelDeltaStats | null;
  tire_pressure: ChannelDeltaStats | null;
  tire_pressure_gain: ChannelDeltaStats | null;
  tire_temp_inner: ChannelDeltaStats | null;
  tire_temp_middle: ChannelDeltaStats | null;
  tire_temp_outer: ChannelDeltaStats | null;
  temp_spread: ChannelDeltaStats | null;
  tire_wear: ChannelDeltaStats | null;
  wheel_speed: ChannelDeltaStats | null;
  slip_ratio_proxy: ChannelDeltaStats | null;
  corner_score: number | null;
  warnings: string[];
}

export type CornerName = "LF" | "RF" | "LR" | "RR";
export type CornerMatrix = Record<CornerName, CornerMetric>;

export interface PlatformComparison {
  cfs_height: ChannelDeltaStats | null;
  front_avg_rh: ChannelDeltaStats | null;
  rear_avg_rh: ChannelDeltaStats | null;
  left_avg_rh: ChannelDeltaStats | null;
  right_avg_rh: ChannelDeltaStats | null;
  center_rake_fs: ChannelDeltaStats | null;
  side_rake: ChannelDeltaStats | null;
  front_split: ChannelDeltaStats | null;
  rear_split: ChannelDeltaStats | null;
  dynamic_pressure: ChannelDeltaStats | null;
  cfs_risk_score: ChannelDeltaStats | null;
  platform_risk_delta_label: string;
  platform_verdict: string | null;
}

export interface TireComparison {
  corners: Partial<CornerMatrix>;
  front_pressure_balance: ChannelDeltaStats | null;
  rear_pressure_balance: ChannelDeltaStats | null;
  temp_spread_summary: string | null;
  wear_summary: string | null;
  tire_verdict: string | null;
  short_run_warning: string | null;
}

export interface ShockComparison {
  corners: Partial<CornerMatrix>;
  shock_velocity_rms_avg: ChannelDeltaStats | null;
  shock_activity_index: ChannelDeltaStats | null;
  shock_verdict: string | null;
}

export interface DriverComparison {
  avg_throttle_pct: ChannelDeltaStats | null;
  full_throttle_pct_time: ChannelDeltaStats | null;
  avg_brake_pct: ChannelDeltaStats | null;
  avg_abs_steering_deg: ChannelDeltaStats | null;
  max_abs_steering_deg: ChannelDeltaStats | null;
  throttle_mae_pct: number | null;
  brake_mae_pct: number | null;
  steering_mae_deg: number | null;
  repeatability_score: number | null;
  driver_changed_warning: string | null;
  driver_verdict: string | null;
}

export interface PaceComparison {
  baseline_selected_lap_time_s: number | null;
  test_selected_lap_time_s: number | null;
  selected_lap_delta_s: number | null;
  baseline_median_lap_time_s: number | null;
  test_median_lap_time_s: number | null;
  cohort_delta_s: number | null;
  baseline_eligible_laps: number;
  test_eligible_laps: number;
  noise_band_s: number | null;
  is_significant: boolean | null;
  direction: "faster" | "slower" | "no_clear_difference" | "insufficient_data";
  confidence_score: number;
  confidence_notes: string[];
}

export interface PowertrainComparison {
  avg_rpm: ChannelDeltaStats | null;
  min_rpm: ChannelDeltaStats | null;
  max_rpm: ChannelDeltaStats | null;
  gear_usage: string | null;
  speed_vs_rpm: string | null;
  pull_score: ChannelDeltaStats | null;
  water_temp: ChannelDeltaStats | null;
  oil_temp: ChannelDeltaStats | null;
  powertrain_verdict: string | null;
}

export interface WholeCarIndex {
  speed_index: number | null;
  platform_index: number | null;
  tire_index: number | null;
  shock_index: number | null;
  driver_index: number | null;
  powertrain_index: number | null;
  test_discipline_index: number | null;
  confidence_index: number | null;
  overall_index: number | null;
  overall_label: string | null;
}

export interface ComparisonObservation {
  observation_state: "observed_improvement" | "observed_regression" | "needs_confirmation" | "inconclusive";
  confidence_score: number;
  headline: string;
  evidence: string[];
  warnings: string[];
  evidence_state: import("./telemetry").EvidenceState;
  source_channels: string[];
  blocker_reasons: string[];
}

/** Non-authorizing observation states used by the legacy Compare surface. */
export type ObservationKind = "observed_improvement" | "observed_regression" | "needs_confirmation" | "inconclusive";

export interface TestDisciplineResult {
  score: number;
  label: string;
  positive_factors: string[];
  negative_factors: string[];
  measurement_note: string | null;
}

export interface SetupChange {
  setup_key: string;
  label: string;
  group: string;
  baseline_value: unknown;
  test_value: unknown;
  unit: string | null;
  delta: string | null;
  significance: "small" | "medium" | "large" | "unknown";
  magnitude_basis: string | null;
  relative_delta_percent: number | null;
  related_to_target_issue: boolean;
}

export interface ContextChange {
  key: string;
  label: string;
  baseline_value: unknown;
  test_value: unknown;
  warning: string | null;
  is_problem: boolean;
}

export interface TargetZoneChannelDelta {
  channel: string;
  label: string;
  unit: string;
  baseline_avg: number | null;
  test_avg: number | null;
  delta: number | null;
  baseline_min: number | null;
  test_min: number | null;
  baseline_max: number | null;
  test_max: number | null;
}

export interface TargetZoneComparison {
  start_pct: number;
  end_pct: number;
  channel_deltas: TargetZoneChannelDelta[];
  speed_gain_or_loss_label: string;
  platform_risk_delta_label: string;
}

export interface CompareResponse {
  comparison_id: string;
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap: number | null;
  test_lap: number | null;
  target_zone_start_pct: number;
  target_zone_end_pct: number;
  target_zone: TargetZoneComparison | null;
  whole_car_index: WholeCarIndex | null;
  pace_comparison: PaceComparison | null;
  platform: PlatformComparison | null;
  corner_matrix: Partial<CornerMatrix>;
  tire_comparison: TireComparison | null;
  shock_comparison: ShockComparison | null;
  driver_comparison: DriverComparison | null;
  powertrain_comparison: PowertrainComparison | null;
  setup_changes: SetupChange[];
  context_changes: ContextChange[];
  test_discipline: TestDisciplineResult | null;
  observation: ComparisonObservation | null;
  sim_integrity?: {
    baseline: Record<string, unknown>;
    test: Record<string, unknown>;
    comparison_clear: boolean | null;
    confidence_cap: number;
    warnings: string[];
  } | null;
  warnings: string[];
  confidence_score: number;
  compare_identity: CompareIdentity;
}

export interface CompareRunIdentity {
  run_id: string;
  source_file_sha256: string;
  telemetry_cache_sha256: string;
  compatibility_fingerprint: string;
  build_identity: Record<string, unknown>;
  setup_id: string | null;
  setup_sha256: string | null;
}

export interface CompareIdentity {
  schema_version: "p31.compare-identity.v1";
  baseline: CompareRunIdentity;
  test: CompareRunIdentity;
  baseline_lap: number | null;
  test_lap: number | null;
  target_zone_start_pct: number;
  target_zone_end_pct: number;
  identity_sha256: string;
}

// -- Delta Trace types --------------------------------------

export interface DeltaTraceRequest {
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap?: number | null;
  test_lap?: number | null;
  channels?: string[] | null;
  x_axis?: string;
  start_pct?: number;
  end_pct?: number;
  step_pct?: number;
  target_zone_start_pct?: number;
  target_zone_end_pct?: number;
}

export interface DeltaTraceChannel {
  channel: string;
  label: string;
  unit: string;
  baseline_values: (number | null)[];
  test_values: (number | null)[];
  delta_values: (number | null)[];
  baseline_min: number | null;
  baseline_max: number | null;
  test_min: number | null;
  test_max: number | null;
  delta_min: number | null;
  delta_max: number | null;
  delta_mean: number | null;
  is_proxy: boolean;
  unavailable_reason: string | null;
}

export interface DeltaTraceResponse {
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap: number | null;
  test_lap: number | null;
  x_axis: string;
  x_unit: string;
  x_values: (number | null)[];
  lap_pct_values: number[];
  target_zone_start_pct: number;
  target_zone_end_pct: number;
  channels: Record<string, DeltaTraceChannel>;
  warnings: string[];
  missing_channels: string[];
}

// -- Phase-aware physical-position time analysis -------------

export interface TimeAnalysisRequest {
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap?: number | null;
  test_lap?: number | null;
  start_pct?: number;
  end_pct?: number;
  step_pct?: number;
}

export interface EngineeringPhaseInterval {
  phase: string;
  start_pct: number;
  end_pct: number;
  confidence: number;
  source_channels: string[];
}

export interface LocalAlignmentPoint {
  lap_pct: number;
  aligned_test_pct: number | null;
  confidence: number;
  uncertainty_pct: number | null;
  methods: string[];
  is_gap: boolean;
  gap_reason: string | null;
}

export interface PhaseTimeEffect {
  phase: string;
  start_pct: number;
  end_pct: number;
  delta_s: number | null;
  cumulative_delta_s: number | null;
  alignment_confidence: number;
  evidence_state: "calculated" | "unavailable";
  source_channels: string[];
  calculation_basis: "reciprocal_speed_integration" | "aligned_timing_boundaries" | "mixed" | "unavailable";
  interpretation: string;
}

export interface LapLevelNoiseEstimate {
  experiment_unit: "eligible_lap";
  baseline_laps: number;
  test_laps: number;
  paired_lap_differences: number;
  median_effect_s: number | null;
  trimmed_mean_effect_s: number | null;
  bootstrap_low_s: number | null;
  bootstrap_high_s: number | null;
  contradiction_score: number | null;
  aba_consistency: "not_available_without_restored_baseline" | string;
  is_repeatable: boolean | null;
  context_complete: boolean;
  context_blockers: string[];
  context_key: Record<string, unknown>;
  phase_estimates: Record<string, {
    experiment_unit: "eligible_lap";
    baseline_laps: number;
    test_laps: number;
    paired_lap_differences: number;
    median_effect_s: number | null;
    empirical_noise_band_s: number;
    bootstrap_low_s: number | null;
    bootstrap_high_s: number | null;
    is_repeatable: boolean | null;
  }>;
  warnings: string[];
}

/**
 * All position-indexed arrays share grid_pct. Nulls are intentional rendering
 * gaps: charts must not connect or extrapolate across them. A cursor uses the
 * same index to synchronize time, phase, and local alignment uncertainty.
 */
export interface TimeAnalysisResponse {
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap: number;
  test_lap: number;
  grid_pct: number[];
  phase_by_position: (string | null)[];
  phases: EngineeringPhaseInterval[];
  alignment: LocalAlignmentPoint[];
  cumulative_delta_s: (number | null)[];
  incremental_delta_s: (number | null)[];
  incremental_basis: ("reciprocal_speed_integration" | "aligned_timing_boundaries" | null)[];
  baseline_elapsed_s: (number | null)[];
  test_elapsed_s: (number | null)[];
  phase_effects: PhaseTimeEffect[];
  phase_attribution: {
    entry_delta_s: number | null;
    center_delta_s: number | null;
    exit_delta_s: number | null;
    following_straight_carry_delta_s: number | null;
  };
  gain_origin_pct: number | null;
  gain_origin_phase: string | null;
  surrender_pct: number | null;
  gain_persistence_pct: number | null;
  selected_effect_s: number | null;
  time_delta_complete: boolean;
  theoretical_opportunity_s: number | null;
  repeatable_opportunity_s: number | null;
  noise: LapLevelNoiseEstimate;
  coverage_fraction: number;
  local_alignment_confidence: number;
  distance_basis: "reciprocal_speed_integration" | "aligned_timing_boundaries" | "mixed" | "unavailable";
  warnings: string[];
  source_channels: string[];
}

// -- Contract-gated driver, rotation, and platform systems --

export interface EngineeringGate {
  contract_key: string;
  eligible: boolean;
  confidence_cap: number;
  blocker_reasons: string[];
  needed_measurements: string[];
}

export interface EngineeringConclusion {
  key: string;
  summary: string;
  evidence_state: import("./telemetry").EvidenceState;
  confidence_score: number;
  source_channels: string[];
  supporting_evidence: string[];
  contradicting_evidence: string[];
  blocker_reasons: string[];
}

export interface EngineeringPhaseMetric {
  phase: string;
  coverage_fraction: number;
  sample_bins: number;
  metrics: Record<string, number | null>;
}

export interface DriverLineEngineeringReport {
  gate: EngineeringGate;
  phase_metrics: EngineeringPhaseMetric[];
  line_deviation_median_m: number | null;
  line_deviation_p95_m: number | null;
  throttle_mae_pct: number | null;
  brake_mae_pct: number | null;
  steering_mae_deg: number | null;
  driver_execution_changed: boolean | null;
  setup_attribution_allowed: boolean;
  conclusions: EngineeringConclusion[];
}

export interface CornerRotationEngineeringReport {
  gate: EngineeringGate;
  phase_metrics: EngineeringPhaseMetric[];
  conclusions: EngineeringConclusion[];
}

export interface PlatformSpeedBand {
  label: string;
  min_speed_mph: number;
  max_speed_mph: number | null;
  sample_bins: number;
  metrics: Record<string, number | null>;
}

export interface AeroPlatformEngineeringReport {
  gate: EngineeringGate;
  setup_attribution_allowed: boolean;
  baseline_speed_bands: PlatformSpeedBand[];
  test_speed_bands: PlatformSpeedBand[];
  comparison_metrics: {
    baseline?: Record<string, number | null>;
    test?: Record<string, number | null>;
    delta?: Record<string, number | string | boolean | null>;
  };
  lap_consistency: Record<string, Record<string, number | string | null>>;
  conclusions: EngineeringConclusion[];
}

export interface EngineeringSystemsResponse {
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap: number;
  test_lap: number;
  alignment_coverage_fraction: number;
  local_alignment_confidence: number;
  baseline_curvature_basis: string;
  test_curvature_basis: string;
  baseline_gps_geometry_healthy: boolean;
  test_gps_geometry_healthy: boolean;
  baseline_sim_integrity_status: string;
  test_sim_integrity_status: string;
  sim_integrity_clear: boolean | null;
  sim_integrity_confidence_cap: number;
  driver_line: DriverLineEngineeringReport;
  corner_rotation: CornerRotationEngineeringReport;
  aero_platform: AeroPlatformEngineeringReport;
  warnings: string[];
}

// -- Comparison Insights types ------------------------------

export interface TraceAnnotation {
  id: string;
  kind: "speed_gain" | "speed_loss" | "cfs_compression" | "drag_scrub_spike" | "steering_correction" | "rpm_flattening" | "throttle_lift";
  label: string;
  description: string;
  lap_pct: number | null;
  distance_ft: number | null;
  channel: string | null;
  value: number | null;
  severity: string;
  confidence: number;
  related_channels: string[];
}

export interface CorrelationInsight {
  channel_a: string;
  channel_b: string;
  correlation: number | null;
  strength: "strong" | "moderate" | "weak" | "none";
  direction: "positive" | "negative" | "neutral";
  narrative: string;
  confidence: number;
  warning: string | null;
}

export interface TargetZoneClassification {
  classification: "stable_gain" | "risky_gain" | "platform_sensitive_gain" | "driver_input_gain" | "drag_reduction" | "mechanical_balance_improvement" | "inconclusive";
  confidence: number;
  headline: string;
  evidence: string[];
  warnings: string[];
}

export interface ConfidenceWeightedObservation {
  observation_state: string;
  adjusted_confidence: number;
  confidence_tier: "high" | "medium" | "low";
  penalties: string[];
  boosts: string[];
  warning: string | null;
}

export interface SectorDeltaSummary {
  sector_id: string;
  label: string;
  start_pct: number;
  end_pct: number;
  avg_speed_delta_mph: number | null;
  min_cfs_delta_in: number | null;
  avg_steering_delta_deg: number | null;
  avg_drag_scrub_delta: number | null;
  avg_rpm_delta: number | null;
  classification: string;
  warnings: string[];
}

export interface ComparisonInsightsResponse {
  comparison_id: string;
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap: number | null;
  test_lap: number | null;
  target_zone_start_pct: number;
  target_zone_end_pct: number;
  annotations: TraceAnnotation[];
  correlations: CorrelationInsight[];
  target_zone_classification: TargetZoneClassification | null;
  confidence_weighted_observation: ConfidenceWeightedObservation | null;
  sectors: SectorDeltaSummary[];
  summary_headline: string | null;
  key_takeaways: string[];
  warnings: string[];
  missing_channels: string[];
  engine_states: Record<string, "finding" | "evaluated_clear" | "unavailable">;
}

// -- Notebook types -----------------------------------------

export interface NotebookFinding {
  finding_id: string;
  created_at: string;
  updated_at: string;
  car_name: string | null;
  track_name: string | null;
  setup_name: string | null;
  baseline_run_id: string | null;
  test_run_id: string | null;
  comparison_id: string | null;
  baseline_lap: number | null;
  test_lap: number | null;
  target_zone_start_pct: number;
  target_zone_end_pct: number;
  confidence_score: number;
  confidence_tier: string | null;
  test_discipline_score: number;
  target_zone_classification: string | null;
  summary_headline: string | null;
  key_takeaways: string[];
  evidence: string[];
  warnings: string[];
  sector_summaries: Record<string, unknown>[];
  context_changes: Record<string, unknown>[];
  improved_metrics: string[];
  worsened_metrics: string[];
  notes: string;
  tags: string[];
  status: "saved" | "archived";
}
