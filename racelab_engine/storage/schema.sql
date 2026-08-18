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
  engineering_blockers_json TEXT,
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
  event_json TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_setup_snapshots_run_id ON setup_snapshots(run_id);

-- Observational Notebook
--
-- Notebook is deliberately not setup memory.  It stores comparison context,
-- evidence, and user notes/tags, but never a setup-policy verdict, setup
-- change, or next-test plan.  P19 controlled workflows own that authority.

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
  confidence_score REAL DEFAULT 0.0,
  confidence_tier TEXT,
  test_discipline_score REAL DEFAULT 0.0,
  target_zone_classification TEXT,
  summary_headline TEXT,
  key_takeaways_json TEXT,
  evidence_json TEXT,
  warnings_json TEXT,
  sector_summaries_json TEXT,
  context_changes_json TEXT,
  improved_metrics_json TEXT,
  worsened_metrics_json TEXT,
  notes TEXT DEFAULT '',
  tags_json TEXT,
  status TEXT NOT NULL DEFAULT 'saved' CHECK (status IN ('saved', 'archived'))
);

-- Greenfield authority migration for existing local databases.  Rebuilding
-- physically discards legacy client-attested verdict/setup/next-step columns,
-- drops the test-plan store, and converts policy-like statuses to plain saved
-- observations.  Safe observation data survives the rebuild.
DROP TABLE IF EXISTS test_plans;
DROP TABLE IF EXISTS notebook_findings_observational_v2;
CREATE TABLE notebook_findings_observational_v2 (
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
  confidence_score REAL DEFAULT 0.0,
  confidence_tier TEXT,
  test_discipline_score REAL DEFAULT 0.0,
  target_zone_classification TEXT,
  summary_headline TEXT,
  key_takeaways_json TEXT,
  evidence_json TEXT,
  warnings_json TEXT,
  sector_summaries_json TEXT,
  context_changes_json TEXT,
  improved_metrics_json TEXT,
  worsened_metrics_json TEXT,
  notes TEXT DEFAULT '',
  tags_json TEXT,
  status TEXT NOT NULL DEFAULT 'saved' CHECK (status IN ('saved', 'archived'))
);
INSERT INTO notebook_findings_observational_v2 (
  finding_id, created_at, updated_at,
  car_name, track_name, setup_name,
  baseline_run_id, test_run_id, comparison_id,
  baseline_lap, test_lap,
  target_zone_start_pct, target_zone_end_pct,
  confidence_score, confidence_tier,
  test_discipline_score, target_zone_classification,
  summary_headline,
  key_takeaways_json, evidence_json, warnings_json,
  sector_summaries_json, context_changes_json,
  improved_metrics_json, worsened_metrics_json,
  notes, tags_json, status
)
SELECT
  finding_id, created_at, updated_at,
  car_name, track_name, setup_name,
  baseline_run_id, test_run_id, comparison_id,
  baseline_lap, test_lap,
  target_zone_start_pct, target_zone_end_pct,
  confidence_score, confidence_tier,
  test_discipline_score, target_zone_classification,
  summary_headline,
  key_takeaways_json, evidence_json, warnings_json,
  sector_summaries_json, context_changes_json,
  improved_metrics_json, worsened_metrics_json,
  notes, tags_json,
  CASE WHEN status = 'archived' THEN 'archived' ELSE 'saved' END
FROM notebook_findings;
DROP TABLE notebook_findings;
ALTER TABLE notebook_findings_observational_v2 RENAME TO notebook_findings;

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
CREATE INDEX IF NOT EXISTS idx_findings_status ON notebook_findings(status);

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
  stage_experiment_contexts_json TEXT NOT NULL DEFAULT '{}',
  analysis_version TEXT NOT NULL DEFAULT 'controlled-workflow-aba2-v1',
  execution_json TEXT,
  reproduction_snapshot_json TEXT NOT NULL DEFAULT '{}',
  quality_json TEXT,
  learning_admitted INTEGER,
  learning_capture_state TEXT NOT NULL DEFAULT 'not_applicable',
  learning_capture_experience_id TEXT,
  learning_capture_experience_sha256 TEXT,
  learning_capture_blocker_reason TEXT,
  FOREIGN KEY(source_run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_controlled_workflow_status
  ON controlled_test_workflows(status, updated_at);

CREATE TABLE IF NOT EXISTS controlled_workflow_run_index (
  workflow_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  role TEXT NOT NULL,
  PRIMARY KEY(workflow_id, run_id, role),
  FOREIGN KEY(workflow_id) REFERENCES controlled_test_workflows(workflow_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_controlled_workflow_run_lookup
  ON controlled_workflow_run_index(run_id, workflow_id);

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

CREATE TABLE IF NOT EXISTS evidence_campaigns (
  campaign_id TEXT PRIMARY KEY,
  campaign_hash TEXT NOT NULL UNIQUE,
  campaign_kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  campaign_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_campaign_attempts (
  attempt_id TEXT PRIMARY KEY,
  attempt_hash TEXT NOT NULL UNIQUE,
  campaign_id TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  independence_unit_id TEXT NOT NULL,
  attempt_json TEXT NOT NULL,
  FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_evidence_campaign_attempt
  ON evidence_campaign_attempts(campaign_id, recorded_at, attempt_id);

CREATE TABLE IF NOT EXISTS profile_validation_records (
  record_id TEXT PRIMARY KEY,
  record_hash TEXT NOT NULL UNIQUE,
  profile_id TEXT NOT NULL,
  profile_hash TEXT NOT NULL,
  car_path TEXT NOT NULL,
  field_key TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL,
  record_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_profile_validation_field
  ON profile_validation_records(profile_id, field_key, created_at, record_id);

CREATE TABLE IF NOT EXISTS shadow_model_contracts (
  model_id TEXT PRIMARY KEY,
  model_hash TEXT NOT NULL UNIQUE,
  model_key TEXT NOT NULL,
  version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  contract_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shadow_predictions (
  prediction_id TEXT PRIMARY KEY,
  prediction_hash TEXT NOT NULL UNIQUE,
  model_id TEXT NOT NULL,
  predicted_at TEXT NOT NULL,
  prospective INTEGER NOT NULL,
  prediction_json TEXT NOT NULL,
  FOREIGN KEY(model_id) REFERENCES shadow_model_contracts(model_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS shadow_prediction_outcomes (
  outcome_id TEXT PRIMARY KEY,
  outcome_hash TEXT NOT NULL UNIQUE,
  prediction_id TEXT NOT NULL UNIQUE,
  observed_at TEXT NOT NULL,
  outcome_json TEXT NOT NULL,
  FOREIGN KEY(prediction_id) REFERENCES shadow_predictions(prediction_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_shadow_prediction_model
  ON shadow_predictions(model_id, predicted_at, prediction_id);

CREATE TABLE IF NOT EXISTS activation_decisions (
  decision_id TEXT PRIMARY KEY,
  decision_hash TEXT NOT NULL UNIQUE,
  capability_key TEXT NOT NULL,
  state TEXT NOT NULL,
  evaluated_at TEXT NOT NULL,
  decision_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activation_decision_capability
  ON activation_decisions(capability_key, evaluated_at, decision_id);

-- P22 executes P21 campaigns as append-only prospective learning operations.
CREATE TABLE IF NOT EXISTS evidence_campaign_operations (
  operation_id TEXT PRIMARY KEY,
  operation_hash TEXT NOT NULL UNIQUE,
  campaign_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  operation_json TEXT NOT NULL,
  FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS evidence_campaign_operation_events (
  event_id TEXT PRIMARY KEY,
  event_hash TEXT NOT NULL UNIQUE,
  operation_id TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS evidence_campaign_run_assessments (
  assessment_id TEXT PRIMARY KEY,
  assessment_hash TEXT NOT NULL UNIQUE,
  operation_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  source_file_fingerprint TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  state TEXT NOT NULL,
  assessment_json TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
    ON DELETE RESTRICT,
  FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_campaign_operation_events
  ON evidence_campaign_operation_events(operation_id, recorded_at, event_id);

CREATE INDEX IF NOT EXISTS idx_campaign_run_assessment
  ON evidence_campaign_run_assessments(operation_id, recorded_at, assessment_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_run_assessment_scope
  ON evidence_campaign_run_assessments(operation_id, run_id);

CREATE TABLE IF NOT EXISTS prospective_test_predictions (
  prediction_id TEXT PRIMARY KEY,
  prediction_hash TEXT NOT NULL UNIQUE,
  operation_id TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  predicted_at TEXT NOT NULL,
  prediction_json TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS prospective_test_outcomes (
  outcome_id TEXT PRIMARY KEY,
  outcome_hash TEXT NOT NULL UNIQUE,
  prediction_id TEXT NOT NULL UNIQUE,
  workflow_id TEXT NOT NULL UNIQUE,
  observed_at TEXT NOT NULL,
  outcome_json TEXT NOT NULL,
  FOREIGN KEY(prediction_id) REFERENCES prospective_test_predictions(prediction_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_prospective_prediction_operation
  ON prospective_test_predictions(operation_id, predicted_at, prediction_id);

CREATE TABLE IF NOT EXISTS p23_validation_protocols (
  protocol_id TEXT PRIMARY KEY,
  protocol_hash TEXT NOT NULL UNIQUE,
  protocol_version TEXT NOT NULL,
  capability_key TEXT NOT NULL,
  created_at TEXT NOT NULL,
  protocol_json TEXT NOT NULL,
  UNIQUE(capability_key, protocol_version)
);

CREATE TABLE IF NOT EXISTS p23_activation_audits (
  audit_id TEXT PRIMARY KEY,
  audit_hash TEXT NOT NULL UNIQUE,
  protocol_id TEXT NOT NULL,
  activation_decision TEXT NOT NULL,
  created_at TEXT NOT NULL,
  audit_json TEXT NOT NULL,
  FOREIGN KEY(protocol_id) REFERENCES p23_validation_protocols(protocol_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_p23_activation_audit_decision
  ON p23_activation_audits(activation_decision, created_at, audit_id);

-- P24 post-import qualification is append-only.  Certificates, not a later
-- dataset rebuild, own the admission decision and its exact exclusion trail.
CREATE TABLE IF NOT EXISTS p24_steering_truth_audits (
  audit_id TEXT PRIMARY KEY,
  audit_hash TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  source_file_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  state TEXT NOT NULL,
  audit_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_p24_truth_source
  ON p24_steering_truth_audits(source_file_hash, created_at, audit_id);

CREATE TABLE IF NOT EXISTS p24_qualification_certificates (
  certificate_id TEXT PRIMARY KEY,
  certificate_hash TEXT NOT NULL UNIQUE,
  protocol_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  source_file_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  qualification_state TEXT NOT NULL,
  certificate_json TEXT NOT NULL,
  UNIQUE(operation_id, run_id),
  FOREIGN KEY(protocol_id) REFERENCES p23_validation_protocols(protocol_id)
    ON DELETE RESTRICT,
  FOREIGN KEY(campaign_id) REFERENCES evidence_campaigns(campaign_id)
    ON DELETE RESTRICT,
  FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_p24_certificate_progress
  ON p24_qualification_certificates(protocol_id, qualification_state, created_at);
CREATE INDEX IF NOT EXISTS idx_p24_certificate_source
  ON p24_qualification_certificates(source_file_hash, qualification_state);

CREATE TABLE IF NOT EXISTS p24_negative_control_expectations (
  expectation_id TEXT PRIMARY KEY,
  expectation_hash TEXT NOT NULL UNIQUE,
  operation_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  recipe_id TEXT NOT NULL,
  expectation_json TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS p24_negative_control_results (
  result_id TEXT PRIMARY KEY,
  result_hash TEXT NOT NULL UNIQUE,
  expectation_id TEXT NOT NULL UNIQUE,
  certificate_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  passed INTEGER NOT NULL,
  result_json TEXT NOT NULL,
  FOREIGN KEY(expectation_id) REFERENCES p24_negative_control_expectations(expectation_id)
    ON DELETE RESTRICT,
  FOREIGN KEY(certificate_id) REFERENCES p24_qualification_certificates(certificate_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS p24_certificate_admissions (
  admission_id TEXT PRIMARY KEY,
  admission_hash TEXT NOT NULL UNIQUE,
  certificate_id TEXT NOT NULL,
  dataset_id TEXT NOT NULL UNIQUE,
  admitted_at TEXT NOT NULL,
  admission_json TEXT NOT NULL,
  UNIQUE(certificate_id, dataset_id),
  FOREIGN KEY(certificate_id) REFERENCES p24_qualification_certificates(certificate_id)
    ON DELETE RESTRICT,
  FOREIGN KEY(dataset_id) REFERENCES evidence_datasets(dataset_id)
    ON DELETE RESTRICT
);

-- P25 freezes the first same-setup/null collection contract before driving.
-- Outcome fields remain empty in the immutable card; a later certificate owns
-- qualification and admission.
CREATE TABLE IF NOT EXISTS p25_null_session_run_cards (
  card_id TEXT PRIMARY KEY,
  card_hash TEXT NOT NULL UNIQUE,
  reference_run_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  state TEXT NOT NULL,
  card_json TEXT NOT NULL,
  UNIQUE(reference_run_id),
  FOREIGN KEY(operation_id) REFERENCES evidence_campaign_operations(operation_id)
    ON DELETE RESTRICT
);

-- P27-P29 Crew Chief state is event sourced.  Workspace projections are
-- reproducible from these immutable inputs and their exact authority hashes.
CREATE TABLE IF NOT EXISTS crew_chief_investigations (
  investigation_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  workspace_revision TEXT NOT NULL,
  status TEXT NOT NULL,
  opened_at TEXT NOT NULL,
  event_count INTEGER NOT NULL DEFAULT 0,
  event_head_hash TEXT,
  continue_action_count INTEGER NOT NULL DEFAULT 0,
  investigation_json TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crew_chief_investigation_scope
  ON crew_chief_investigations(run_id, session_id, opened_at, investigation_id);

CREATE TABLE IF NOT EXISTS crew_chief_events (
  event_id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  workspace_revision TEXT NOT NULL,
  created_at TEXT NOT NULL,
  event_hash TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  UNIQUE(investigation_id, sequence),
  FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crew_chief_event_fold
  ON crew_chief_events(investigation_id, sequence, event_id);

CREATE TABLE IF NOT EXISTS engineering_objectives (
  objective_id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL UNIQUE,
  workspace_revision TEXT NOT NULL,
  selected_at TEXT NOT NULL,
  objective_json TEXT NOT NULL,
  FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS crew_chief_success_contracts (
  contract_id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL UNIQUE,
  workspace_revision TEXT NOT NULL,
  created_at TEXT NOT NULL,
  contract_json TEXT NOT NULL,
  FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS component_response_records (
  record_id TEXT PRIMARY KEY,
  source_workflow_id TEXT NOT NULL UNIQUE,
  source_run_id TEXT NOT NULL,
  context_identity TEXT NOT NULL,
  created_at TEXT NOT NULL,
  record_json TEXT NOT NULL,
  FOREIGN KEY(source_run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_component_response_context
  ON component_response_records(context_identity, created_at, record_id);

CREATE TABLE IF NOT EXISTS crew_chief_driver_memory (
  record_id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  record_json TEXT NOT NULL,
  FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crew_chief_driver_memory_scope
  ON crew_chief_driver_memory(session_id, recorded_at, record_id);

CREATE TABLE IF NOT EXISTS crew_chief_effectiveness_records (
  record_id TEXT PRIMARY KEY,
  investigation_id TEXT NOT NULL UNIQUE,
  workspace_revision TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  record_json TEXT NOT NULL,
  FOREIGN KEY(investigation_id) REFERENCES crew_chief_investigations(investigation_id)
    ON DELETE CASCADE
);

-- P33 keeps one append-only engineering-experience ledger.  The companion
-- singleton is integrity metadata, not a second source of engineering facts;
-- it makes deleted or reordered ledger tails detectable after restart.
CREATE TABLE IF NOT EXISTS engineering_experience_stream_head (
  stream_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  head_sha256 TEXT
);

INSERT OR IGNORE INTO engineering_experience_stream_head (
  stream_id, schema_version, record_count, head_sha256
) VALUES ('p33.engineering-experience.v1', 'p33.engineering-experience.v1', 0, NULL);

CREATE TABLE IF NOT EXISTS engineering_experiences (
  sequence INTEGER PRIMARY KEY,
  experience_id TEXT NOT NULL UNIQUE,
  experience_sha256 TEXT NOT NULL UNIQUE,
  source_identity_sha256 TEXT NOT NULL UNIQUE,
  previous_entry_sha256 TEXT,
  entry_sha256 TEXT NOT NULL UNIQUE,
  source_kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  context_sha256 TEXT NOT NULL,
  run_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  driver_id TEXT,
  car_path TEXT NOT NULL,
  car_version TEXT NOT NULL,
  iracing_build TEXT NOT NULL,
  track TEXT NOT NULL,
  track_configuration TEXT NOT NULL,
  package_type TEXT NOT NULL,
  setup_family TEXT,
  setup_snapshot_sha256 TEXT NOT NULL,
  objective TEXT NOT NULL,
  phase TEXT NOT NULL,
  physical_region TEXT NOT NULL,
  problem_sha256 TEXT NOT NULL,
  source_investigation_id TEXT,
  source_workflow_id TEXT,
  record_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_engineering_experience_exact_context
  ON engineering_experiences(
    context_sha256, objective, phase, created_at DESC, experience_id
  );

CREATE INDEX IF NOT EXISTS idx_engineering_experience_problem
  ON engineering_experiences(
    problem_sha256, car_path, car_version, iracing_build,
    created_at DESC, experience_id
  );

CREATE INDEX IF NOT EXISTS idx_engineering_experience_vehicle_track
  ON engineering_experiences(
    car_path, car_version, iracing_build, track, track_configuration,
    phase, created_at DESC, experience_id
  );

CREATE INDEX IF NOT EXISTS idx_engineering_experience_driver
  ON engineering_experiences(
    driver_id, car_path, car_version, iracing_build, phase,
    created_at DESC, experience_id
  ) WHERE driver_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_engineering_experience_investigation
  ON engineering_experiences(source_investigation_id, experience_id)
  WHERE source_investigation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_engineering_experience_workflow
  ON engineering_experiences(source_workflow_id, experience_id)
  WHERE source_workflow_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS engineering_experiences_no_update
BEFORE UPDATE ON engineering_experiences
BEGIN
  SELECT RAISE(ABORT, 'engineering experiences are append-only');
END;

CREATE TRIGGER IF NOT EXISTS engineering_experiences_no_delete
BEFORE DELETE ON engineering_experiences
BEGIN
  SELECT RAISE(ABORT, 'engineering experiences are append-only');
END;

-- P34 freezes policy definitions and prospective paired investigation truth in
-- one append-only, content-addressed stream.  The indexed columns support
-- bounded 10,000-investigation inventories without replaying telemetry.
CREATE TABLE IF NOT EXISTS p34_authoritative_source_revision (
  singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
  revision INTEGER NOT NULL CHECK(revision >= 0)
);

INSERT OR IGNORE INTO p34_authoritative_source_revision (singleton_id, revision)
VALUES (1, 0);

CREATE TABLE IF NOT EXISTS investigation_adaptation_stream_head (
  stream_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  head_sha256 TEXT
);

INSERT OR IGNORE INTO investigation_adaptation_stream_head (
  stream_id, schema_version, record_count, head_sha256
) VALUES ('p34.investigation-adaptation.v1', 'p34.investigation-adaptation.v1', 0, NULL);

CREATE TABLE IF NOT EXISTS investigation_adaptation_records (
  sequence INTEGER PRIMARY KEY,
  record_id TEXT NOT NULL UNIQUE,
  record_sha256 TEXT NOT NULL UNIQUE,
  record_kind TEXT NOT NULL,
  previous_entry_sha256 TEXT,
  entry_sha256 TEXT NOT NULL UNIQUE,
  recorded_at TEXT NOT NULL,
  investigation_id TEXT,
  workspace_revision TEXT,
  step_number INTEGER,
  policy_id TEXT,
  protocol_id TEXT,
  record_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_kind_time
  ON investigation_adaptation_records(record_kind, recorded_at DESC, record_id);

CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_investigation
  ON investigation_adaptation_records(
    investigation_id, workspace_revision, step_number, record_kind, sequence DESC
  ) WHERE investigation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_protocol
  ON investigation_adaptation_records(protocol_id, record_kind, sequence DESC)
  WHERE protocol_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_workflow_certificate
  ON investigation_adaptation_records(
    protocol_id,
    record_kind,
    json_extract(record_json, '$.created_workflow_ids[0]'),
    sequence
  ) WHERE record_kind = 'outcome_certificate';

CREATE INDEX IF NOT EXISTS idx_investigation_adaptation_followup_parent
  ON investigation_adaptation_records(
    protocol_id,
    record_kind,
    investigation_id,
    json_extract(record_json, '$.certificate_id'),
    json_extract(record_json, '$.certificate_sha256'),
    json_extract(record_json, '$.source_workflow_id')
  ) WHERE record_kind = 'outcome_followup';

CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_adaptation_pair_source
  ON investigation_adaptation_records(
    investigation_id, workspace_revision, step_number
  ) WHERE record_kind = 'paired_decision';

CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_adaptation_outcome_source
  ON investigation_adaptation_records(investigation_id)
  WHERE record_kind = 'outcome_certificate';

CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_adaptation_comparison_source
  ON investigation_adaptation_records(investigation_id)
  WHERE record_kind = 'paired_comparison';

CREATE TRIGGER IF NOT EXISTS investigation_adaptation_records_no_update
BEFORE UPDATE ON investigation_adaptation_records
BEGIN
  SELECT RAISE(ABORT, 'investigation adaptation records are append-only');
END;

CREATE TRIGGER IF NOT EXISTS investigation_adaptation_records_no_delete
BEFORE DELETE ON investigation_adaptation_records
BEGIN
  SELECT RAISE(ABORT, 'investigation adaptation records are append-only');
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_p34_insert
AFTER INSERT ON investigation_adaptation_records
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_p34_update
AFTER UPDATE ON investigation_adaptation_records
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_p34_delete
AFTER DELETE ON investigation_adaptation_records
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_investigation_insert
AFTER INSERT ON crew_chief_investigations
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_investigation_update
AFTER UPDATE ON crew_chief_investigations
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_investigation_delete
AFTER DELETE ON crew_chief_investigations
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_event_insert
AFTER INSERT ON crew_chief_events
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_event_update
AFTER UPDATE ON crew_chief_events
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_crew_event_delete
AFTER DELETE ON crew_chief_events
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_p33_insert
AFTER INSERT ON engineering_experiences
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_p33_update
AFTER UPDATE ON engineering_experiences
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_p33_delete
AFTER DELETE ON engineering_experiences
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_workflow_insert
AFTER INSERT ON controlled_test_workflows
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_workflow_update
AFTER UPDATE ON controlled_test_workflows
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_workflow_delete
AFTER DELETE ON controlled_test_workflows
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_run_insert
AFTER INSERT ON runs
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_run_update
AFTER UPDATE ON runs
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;

CREATE TRIGGER IF NOT EXISTS p34_source_revision_run_delete
AFTER DELETE ON runs
BEGIN
  UPDATE p34_authoritative_source_revision SET revision = revision + 1
  WHERE singleton_id = 1;
END;
