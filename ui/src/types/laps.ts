/** Lap analysis types matching backend models. */

export interface LapQualitySummary {
  run_id: string;
  lap_number: number;
  lap_time: number | null;
  lap_type: string;
  is_complete: boolean;
  is_useful: boolean;
  classification_tags: string[];
  draft_status: string;
  valid_for_compare: boolean;
  invalid_reasons: string[];
  avg_speed_mph: number | null;
  max_speed_mph: number | null;
  min_speed_mph: number | null;
  min_splitter_mm: number | null;
  min_rear_ride_height_mm: number | null;
  front_platform_risk_score: number | null;
  rear_platform_risk_score: number | null;
  whole_car_bottoming_risk: number | null;
  drag_scrub_suspicion_peak: number | null;
  shock_activity_index_avg: number | null;
  tire_temp_spread_avg: number | null;
  tire_pressure_gain_avg: number | null;
  camber_bias_max: number | null;
  grade_context_label: string | null;
  setup_name: string | null;
  track_name: string | null;
  car_name: string | null;
  session_date: string | null;
}

export interface LapWindowSummary {
  window_id: string;
  run_id: string;
  car_name: string | null;
  track_name: string | null;
  start_lap: number;
  end_lap: number;
  window_size: number;
  total_time: number | null;
  average_lap_time: number | null;
  fastest_lap_time: number | null;
  slowest_lap_time: number | null;
  lap_time_std_dev: number | null;
  falloff_sec: number | null;
  falloff_sec_per_lap: number | null;
  consistency_score: number;
  valid_lap_count: number;
  excluded_laps: Array<{ lap_number: number; reason: string }>;
  classification_tags: string[];
  draft_status_summary: string;
  platform_risk_peak: number | null;
  rear_platform_risk_peak: number | null;
  whole_car_bottoming_peak: number | null;
  tire_stress_score: number;
  shock_stress_score: number;
  confidence_score: number;
  warnings: string[];
  recommendation: string | null;
}

export interface LapDegradationSummary {
  run_id: string;
  lap_count: number;
  early_window_laps: number;
  middle_window_laps: number;
  late_window_laps: number;
  early_avg_lap_time: number | null;
  middle_avg_lap_time: number | null;
  late_avg_lap_time: number | null;
  falloff_early_to_late: number | null;
  falloff_slope_sec_per_lap: number | null;
  tire_stress_trend: string;
  platform_stress_trend: string;
  cooling_stress_trend: string;
  draft_warning: string | null;
  confidence_score: number;
  coaching_message: string | null;
}

export interface FastestLapGroup {
  label: string;
  lap_count: number;
  laps: LapQualitySummary[];
  average_lap_time: number | null;
  fastest_lap_time: number | null;
  slowest_lap_time: number | null;
  is_available: boolean;
  warning: string | null;
}

export interface BestWindowGroup {
  label: string;
  window_size: number;
  windows: LapWindowSummary[];
  best_window: LapWindowSummary | null;
  is_available: boolean;
  warning: string | null;
}

export interface LapWindowsResponse {
  run_id: string;
  fastest_groups: FastestLapGroup[];
  best_windows: BestWindowGroup[];
  degradation: LapDegradationSummary | null;
  total_valid_laps: number;
  total_laps: number;
  warnings: string[];
}
