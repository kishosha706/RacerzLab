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
  tape_percent?: number | null;
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
  recommended_actions: string[];
};

export type Recommendation = {
  recommendation_id: string;
  run_id: string;
  priority_rank: number;
  issue: string;
  cause_bucket: string;
  recommendation_text: string;
  confidence_score: number;
  evidence_strength: string;
  success_metric?: string | null;
  required_next_data: string[];
  do_not_change_warnings: string[];
  evidence_event_ids: string[];
  created_at?: string | null;
};

export type RunOverview = {
  run_id: string;
  session: SessionSummary;
  best_useful_lap?: LapSummary | null;
  laps: LapSummary[];
  events: TelemetryEvent[];
  setup_snapshot?: SetupSnapshot | null;
  recommendations: Recommendation[];
  primary_findings: string[];
  warnings: string[];
  crew_chief_summary?: string | null;
  next_test?: string | null;
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
  used_by_recommendations: string[];
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
};

export type PlatformEventSeverity = "info" | "watch" | "high" | "critical";
export type PlatformEventConfidence = "low" | "medium" | "high";

export type PlatformEventItem = {
  event_id: string;
  event_type: string;
  title: string;
  severity: PlatformEventSeverity;
  confidence: PlatformEventConfidence;
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
  recommended_action?: string | null;
  is_proxy_based: boolean;
  proxy_warning?: string | null;
  metadata: Record<string, unknown>;
};
