PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  source_file TEXT NOT NULL,
  file_hash TEXT,
  import_time TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  analysis_engine_version TEXT DEFAULT '1.0.0',
  lap_eligibility_version TEXT,
  analysis_config_hash TEXT,
  analysis_mode TEXT DEFAULT 'row',
  analyzed_at TEXT,
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
CREATE INDEX IF NOT EXISTS idx_runs_tech_setup_context
  ON runs(setup_passed_tech, car_path, track_id_or_path, session_type, imported_at);
CREATE INDEX IF NOT EXISTS idx_laps_run_id ON laps(run_id);
CREATE INDEX IF NOT EXISTS idx_laps_run_useful_time
  ON laps(run_id, is_useful, lap_time, lap_number);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_lap_type ON events(run_id, lap_number, event_type);
CREATE INDEX IF NOT EXISTS idx_recommendations_run_id ON recommendations(run_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_run_priority
  ON recommendations(run_id, priority_rank);
CREATE INDEX IF NOT EXISTS idx_setup_snapshots_run_id ON setup_snapshots(run_id);

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

CREATE TABLE IF NOT EXISTS segments (
  segment_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  lap_number INTEGER,
  segment_type TEXT DEFAULT 'fixed_pct',
  segment_name TEXT,
  pct_start REAL,
  pct_end REAL,
  distance_start_m REAL,
  distance_end_m REAL,
  avg_speed_mph REAL,
  min_speed_mph REAL,
  max_speed_mph REAL,
  speed_delta_mph REAL,
  avg_rpm REAL,
  rpm_delta REAL,
  avg_throttle_pct REAL,
  avg_brake_pct REAL,
  avg_abs_steering_deg REAL,
  max_abs_steering_deg REAL,
  avg_lat_accel REAL,
  min_splitter_mm REAL,
  platform_risk_score REAL DEFAULT 0.0,
  drag_scrub_score REAL DEFAULT 0.0,
  driver_input_score REAL DEFAULT 0.0,
  powertrain_score REAL DEFAULT 0.0,
  confidence_score REAL DEFAULT 0.0,
  segment_json TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_segments_run_id ON segments(run_id);
CREATE INDEX IF NOT EXISTS idx_segments_run_lap ON segments(run_id, lap_number);

CREATE INDEX IF NOT EXISTS idx_findings_car_track ON notebook_findings(car_name, track_name);
CREATE INDEX IF NOT EXISTS idx_findings_verdict ON notebook_findings(verdict);
CREATE INDEX IF NOT EXISTS idx_findings_status ON notebook_findings(status);
CREATE INDEX IF NOT EXISTS idx_test_plans_status ON test_plans(status);

-- Internal setup-response learning. This is deliberately not a user-facing notebook.
CREATE TABLE IF NOT EXISTS setup_response_observations (
  observation_id TEXT PRIMARY KEY,
  comparison_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  car_name TEXT,
  track_name TEXT,
  response_context_key TEXT,
  response_context_json TEXT,
  environment_context_key TEXT,
  surrounding_setup_fingerprint TEXT,
  source_run_provenance_key TEXT,
  baseline_run_id TEXT NOT NULL,
  test_run_id TEXT NOT NULL,
  baseline_lap INTEGER,
  test_lap INTEGER,
  setup_key TEXT NOT NULL,
  setup_label TEXT,
  setup_group TEXT,
  direction_sign INTEGER,
  baseline_value TEXT,
  test_value TEXT,
  numeric_delta REAL,
  magnitude_label TEXT,
  relative_delta_percent REAL,
  verdict TEXT NOT NULL,
  confidence_score REAL DEFAULT 0.0,
  discipline_score REAL DEFAULT 0.0,
  target_zone_start_pct REAL,
  target_zone_end_pct REAL,
  median_lap_delta_s REAL,
  pace_noise_band_s REAL,
  target_speed_delta_mph REAL,
  cfs_delta_in REAL,
  driver_repeatability_score REAL,
  context_problem_count INTEGER DEFAULT 0,
  baseline_setup_passed_tech INTEGER,
  test_setup_passed_tech INTEGER,
  setup_unit TEXT,
  setup_value_kind TEXT,
  evidence_json TEXT,
  UNIQUE(comparison_id, setup_key, target_zone_start_pct, target_zone_end_pct)
);

CREATE INDEX IF NOT EXISTS idx_setup_response_car_track
  ON setup_response_observations(car_name, track_name, setup_key);
CREATE INDEX IF NOT EXISTS idx_setup_response_verdict
  ON setup_response_observations(verdict);
-- Qualified multi-factor DOE responses. These rows are admitted only after the
-- advanced experimentation unlock and retain their exact context/evidence.
CREATE TABLE IF NOT EXISTS setup_interaction_observations (
  experiment_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  response_context_key TEXT NOT NULL,
  response_context_json TEXT NOT NULL,
  factor_deltas_json TEXT NOT NULL,
  outcomes_json TEXT NOT NULL,
  uncertainty REAL NOT NULL,
  setup_passed_tech INTEGER NOT NULL,
  evidence_packet_ids_json TEXT NOT NULL,
  source_run_ids_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_setup_interaction_context
  ON setup_interaction_observations(response_context_key);

-- Server-owned A/B/A2 workflow state. Clients may attach run identifiers but
-- cannot assert lap eligibility, setup deltas, effects, or evidence quality.
CREATE TABLE IF NOT EXISTS controlled_test_workflows (
  workflow_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  complaint TEXT NOT NULL,
  packet_json TEXT NOT NULL,
  stage_run_ids_json TEXT NOT NULL DEFAULT '{}',
  stage_eligible_lap_numbers_json TEXT NOT NULL DEFAULT '{}',
  analysis_version TEXT NOT NULL DEFAULT 'controlled-workflow-aba2-v1',
  execution_json TEXT,
  reproduction_snapshot_json TEXT NOT NULL DEFAULT '{}',
  quality_json TEXT,
  learning_admitted INTEGER,
  FOREIGN KEY(source_run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_controlled_workflow_status
  ON controlled_test_workflows(status, updated_at);

-- Append-only internal engineering memory. These records intentionally avoid
-- run foreign keys: re-import may replace import-owned evidence rows, but it
-- must never cascade-delete a prediction, grade, narrative, or presentation
-- observation that cites the prior immutable workflow/run identity.
CREATE TABLE IF NOT EXISTS engineering_prediction_contracts (
  contract_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  contract_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engineering_prediction_grades (
  grade_id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL UNIQUE,
  workflow_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  grade_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engineering_narrative_entries (
  entry_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  session_id TEXT,
  entry_type TEXT NOT NULL,
  workflow_id TEXT NOT NULL,
  run_ids_json TEXT NOT NULL,
  entry_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_engineering_narrative_scope
  ON engineering_narrative_entries(scope_id, created_at, entry_id);
CREATE INDEX IF NOT EXISTS idx_engineering_narrative_workflow
  ON engineering_narrative_entries(workflow_id, created_at, entry_id);

-- Immutable mission identity and append-only outcomes. These deliberately do
-- not reference import-owned runs: a re-import must not erase the reason a
-- measurement was stopped or the evidence history that earned that stop.
CREATE TABLE IF NOT EXISTS measurement_mission_contracts (
  contract_id TEXT PRIMARY KEY,
  contract_sha256 TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  contract_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS measurement_mission_attempts (
  attempt_id TEXT PRIMARY KEY,
  contract_id TEXT NOT NULL,
  contract_sha256 TEXT NOT NULL,
  run_id TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  attempt_json TEXT NOT NULL,
  FOREIGN KEY(contract_id) REFERENCES measurement_mission_contracts(contract_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_measurement_attempt_contract
  ON measurement_mission_attempts(contract_id, completed_at, attempt_id);

-- A quarantine is an explicit operator decision, never an implicit response to
-- read failure. It lets the durable-policy scanner distinguish acknowledged
-- unavailable history from history that must still block repeat authority.
CREATE TABLE IF NOT EXISTS session_intelligence_quarantines (
  session_id TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  quarantined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS driver_presentation_observations (
  observation_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  source_key TEXT NOT NULL UNIQUE,
  profile_id TEXT NOT NULL,
  driver_id TEXT NOT NULL,
  context_key TEXT NOT NULL,
  kind TEXT NOT NULL,
  run_id TEXT,
  workflow_id TEXT,
  observation_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_driver_presentation_profile
  ON driver_presentation_observations(profile_id, created_at, observation_id);

-- P21 evidence datasets are content-addressed and immutable.  Evaluation
-- artifacts refer to the stored hash rather than mutable import filenames.
CREATE TABLE IF NOT EXISTS evidence_datasets (
  dataset_id TEXT PRIMARY KEY,
  dataset_hash TEXT NOT NULL UNIQUE,
  dataset_kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  dataset_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_dataset_kind
  ON evidence_datasets(dataset_kind, created_at, dataset_id);

CREATE TABLE IF NOT EXISTS evaluation_artifacts (
  evaluation_id TEXT PRIMARY KEY,
  evaluation_hash TEXT NOT NULL UNIQUE,
  capability_key TEXT NOT NULL,
  dataset_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  evaluation_json TEXT NOT NULL,
  FOREIGN KEY(dataset_id) REFERENCES evidence_datasets(dataset_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_evaluation_artifact_dataset
  ON evaluation_artifacts(dataset_id, created_at, evaluation_id);
