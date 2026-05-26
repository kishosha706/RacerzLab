PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  source_file TEXT NOT NULL,
  file_hash TEXT,
  import_time TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  sim_date_time TEXT,
  car_name TEXT,
  car_path TEXT,
  track_name TEXT,
  track_display_name TEXT,
  track_id_or_path TEXT,
  session_type TEXT,
  weather_summary TEXT,
  setup_name TEXT,
  setup_passed_tech INTEGER,
  setup_modified INTEGER,
  telemetry_rate_hz INTEGER,
  variable_count INTEGER,
  record_count INTEGER,
  duration_seconds REAL,
  air_temp REAL,
  track_temp REAL,
  wind_speed REAL,
  wind_direction REAL,
  air_pressure REAL,
  notes TEXT,
  primary_findings_json TEXT,
  warnings_json TEXT,
  crew_chief_summary TEXT,
  next_test TEXT,
  session_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS laps (
  lap_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  lap_number INTEGER,
  lap_type TEXT,
  is_complete INTEGER,
  is_useful INTEGER,
  start_time REAL,
  end_time REAL,
  lap_time REAL,
  pct_min REAL,
  pct_max REAL,
  pct_span REAL,
  sample_count INTEGER,
  avg_speed_mph REAL,
  max_speed_mph REAL,
  min_speed_mph REAL,
  avg_rpm REAL,
  min_rpm REAL,
  max_rpm REAL,
  avg_throttle_pct REAL,
  max_throttle_pct REAL,
  avg_brake_pct REAL,
  max_brake_pct REAL,
  min_splitter_mm REAL,
  min_splitter_pct REAL,
  min_splitter_distance_m REAL,
  min_splitter_speed_mph REAL,
  max_abs_steering_deg REAL,
  avg_abs_steering_deg REAL,
  classification_tags TEXT,
  lap_json TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  lap_number INTEGER,
  event_type TEXT,
  event_subtype TEXT,
  lap_pct_start REAL,
  lap_pct_end REAL,
  lap_pct_peak REAL,
  distance_m_peak REAL,
  zone_name TEXT,
  severity TEXT,
  confidence_score REAL,
  valid_for_tuning INTEGER,
  primary_metric_name TEXT,
  primary_metric_value REAL,
  evidence_json TEXT,
  related_setup_keys TEXT,
  recommended_actions TEXT,
  event_json TEXT NOT NULL,
  created_at TEXT,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recommendations (
  recommendation_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  priority_rank INTEGER,
  issue TEXT,
  cause_bucket TEXT,
  confidence_score REAL,
  evidence_strength TEXT,
  recommendation_text TEXT,
  success_metric TEXT,
  required_next_data TEXT,
  do_not_change_warnings TEXT,
  evidence_event_ids TEXT,
  recommendation_json TEXT NOT NULL,
  created_at TEXT,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS setup_snapshots (
  setup_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  setup_name TEXT,
  setup_json TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS import_files (
  file_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  file_type TEXT NOT NULL,
  source_path TEXT NOT NULL,
  file_hash TEXT,
  file_size INTEGER,
  modified_time TEXT,
  imported_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_runs_imported_at ON runs(imported_at);
CREATE INDEX IF NOT EXISTS idx_laps_run_id ON laps(run_id);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_lap_type ON events(run_id, lap_number, event_type);
CREATE INDEX IF NOT EXISTS idx_recommendations_run_id ON recommendations(run_id);

-- Notebook / Setup Memory tables

CREATE TABLE IF NOT EXISTS notebook_findings (
  finding_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  car_name TEXT,
  track_name TEXT,
  setup_name TEXT,
  baseline_run_id TEXT,
  test_run_id TEXT,
  comparison_id TEXT,
  baseline_lap INTEGER,
  test_lap INTEGER,
  target_zone_start_pct REAL DEFAULT 55.0,
  target_zone_end_pct REAL DEFAULT 70.0,
  verdict TEXT,
  confidence_score REAL DEFAULT 0.0,
  confidence_tier TEXT,
  test_discipline_score REAL DEFAULT 0.0,
  target_zone_classification TEXT,
  summary_headline TEXT,
  key_takeaways_json TEXT,
  evidence_json TEXT,
  warnings_json TEXT,
  sector_summaries_json TEXT,
  setup_changes_json TEXT,
  context_changes_json TEXT,
  improved_metrics_json TEXT,
  worsened_metrics_json TEXT,
  next_step TEXT,
  notes TEXT DEFAULT '',
  tags_json TEXT,
  status TEXT DEFAULT 'saved'
);

CREATE TABLE IF NOT EXISTS test_plans (
  test_plan_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  source_finding_id TEXT,
  car_name TEXT,
  track_name TEXT,
  setup_name TEXT,
  goal TEXT,
  change_to_try TEXT,
  do_not_change_json TEXT,
  success_metric TEXT,
  target_zone_start_pct REAL DEFAULT 55.0,
  target_zone_end_pct REAL DEFAULT 70.0,
  planned_notes TEXT DEFAULT '',
  status TEXT DEFAULT 'planned',
  FOREIGN KEY(source_finding_id) REFERENCES notebook_findings(finding_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_car_track ON notebook_findings(car_name, track_name);
CREATE INDEX IF NOT EXISTS idx_findings_verdict ON notebook_findings(verdict);
CREATE INDEX IF NOT EXISTS idx_findings_status ON notebook_findings(status);
CREATE INDEX IF NOT EXISTS idx_test_plans_status ON test_plans(status);
