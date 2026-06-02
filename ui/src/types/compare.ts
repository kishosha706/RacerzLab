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
  tire_pressure: ChannelDeltaStats | null;
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
  driver_changed_warning: string | null;
  driver_verdict: string | null;
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

export interface DidItWorkVerdict {
  verdict: "keep_direction" | "undo" | "retest" | "inconclusive";
  confidence_score: number;
  headline: string;
  evidence: string[];
  warnings: string[];
  next_step: string | null;
  success_metric?: string | null;
  cause_bucket?: string | null;
  required_next_data?: string[];
  do_not_change_warnings?: string[];
}

/** Extended verdict kind used by DidItWorkCard UI (includes frontend-only states). */
export type VerdictKind = "keep_direction" | "undo_partially" | "undo" | "retest" | "inconclusive" | "reference_mode";

export interface TestDisciplineResult {
  score: number;
  label: string;
  positive_factors: string[];
  negative_factors: string[];
  recommendation: string | null;
}

export interface SetupChange {
  setup_key: string;
  label: string;
  group: string;
  baseline_value: unknown;
  test_value: unknown;
  delta: string | null;
  significance: string;
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

export interface CompareResponse {
  comparison_id: string;
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap: number | null;
  test_lap: number | null;
  target_zone_start_pct: number;
  target_zone_end_pct: number;
  whole_car_index: WholeCarIndex | null;
  platform: PlatformComparison | null;
  corner_matrix: Partial<CornerMatrix>;
  tire_comparison: TireComparison | null;
  shock_comparison: ShockComparison | null;
  driver_comparison: DriverComparison | null;
  powertrain_comparison: PowertrainComparison | null;
  setup_changes: SetupChange[];
  context_changes: ContextChange[];
  test_discipline: TestDisciplineResult | null;
  verdict: DidItWorkVerdict | null;
  warnings: string[];
  confidence_score: number;
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
  recommendation: string | null;
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
  recommendation: string | null;
}

export interface ConfidenceWeightedVerdict {
  original_verdict: string;
  adjusted_confidence: number;
  confidence_tier: "high" | "medium" | "low";
  penalties: string[];
  boosts: string[];
  final_recommendation: string | null;
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
  confidence_weighted_verdict: ConfidenceWeightedVerdict | null;
  sectors: SectorDeltaSummary[];
  summary_headline: string | null;
  key_takeaways: string[];
  warnings: string[];
  missing_channels: string[];
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
  verdict: string | null;
  confidence_score: number;
  confidence_tier: string | null;
  test_discipline_score: number;
  target_zone_classification: string | null;
  summary_headline: string | null;
  key_takeaways: string[];
  evidence: string[];
  warnings: string[];
  sector_summaries: Record<string, unknown>[];
  setup_changes: Record<string, unknown>[];
  context_changes: Record<string, unknown>[];
  improved_metrics: string[];
  worsened_metrics: string[];
  next_step: string | null;
  notes: string;
  tags: string[];
  status: string;
}

export interface TestPlan {
  test_plan_id: string;
  created_at: string;
  updated_at: string;
  source_finding_id: string | null;
  car_name: string | null;
  track_name: string | null;
  setup_name: string | null;
  goal: string | null;
  change_to_try: string | null;
  do_not_change: string[];
  success_metric: string | null;
  target_zone_start_pct: number;
  target_zone_end_pct: number;
  planned_notes: string;
  status: string;
}

export interface SetupMemorySummary {
  car_name: string | null;
  track_name: string | null;
  total_findings: number;
  keep_count: number;
  undo_count: number;
  retest_count: number;
  inconclusive_count: number;
  confirmed_count: number;
  rejected_count: number;
  most_common_issue: string | null;
  best_known_target_zone: string | null;
  latest_finding: Record<string, unknown> | null;
  recommended_next_test: string | null;
}
