export interface RaceLabSession {
  session_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  track_name: string | null;
  car_name: string | null;
  run_ids: string[];
  last_opened_run_id: string | null;
  last_selected_lap: number | null;
  last_workspace: string | null;
  notebook_finding_ids: string[];
  status: "active" | "archived";
}

export interface LapSummaryItem {
  lap_id: string;
  run_id: string;
  lap_number: number;
  label: string;
  lap_type: "out" | "timed" | "in" | "unknown";
  lap_time_s: number | null;
  lap_time_display: string;
  delta_s: number | null;
  delta_display: string;
  is_valid: boolean;
  is_useful: boolean;
  invalid_reasons: string[];
  sample_count: number;
  distance_ft: number | null;
  distance_pct_min: number | null;
  distance_pct_max: number | null;
  start_sample_index: number | null;
  end_sample_index: number | null;
  start_time_s: number | null;
  end_time_s: number | null;
  has_telemetry: boolean;
  warnings: string[];
}

export interface RunLapList {
  run_id: string;
  display_name: string;
  track_name: string | null;
  car_name: string | null;
  setup_name: string | null;
  session_name: string | null;
  imported_at: string;
  laps: LapSummaryItem[];
  best_lap_number: number | null;
  best_lap_time_s: number | null;
  useful_lap_numbers: number[];
  warnings: string[];
}
