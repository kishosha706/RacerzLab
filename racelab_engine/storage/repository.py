from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from racelab_engine.io.file_fingerprint import FileFingerprint
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.models.segment import SegmentSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.storage.db import initialize_database

if TYPE_CHECKING:
    from racelab_engine.models.controlled_workflow import ControlledWorkflow


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _model_json(model: Any) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json()
    return model.json()


def _load_json(value: str | None, fallback: Any) -> Any:
    return json.loads(value) if value else fallback


class RaceLabRepository:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def initialize(self) -> None:
        connection = initialize_database(self.db_path)
        connection.close()

    def save_controlled_workflow(self, workflow: ControlledWorkflow) -> None:
        connection = initialize_database(self.db_path)
        with connection:
            connection.execute(
                """
                INSERT INTO controlled_test_workflows (
                  workflow_id, created_at, updated_at, status, source_run_id,
                  complaint, packet_json, stage_run_ids_json, stage_eligible_lap_numbers_json,
                  analysis_version, execution_json, reproduction_snapshot_json,
                  quality_json, learning_admitted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                  updated_at=excluded.updated_at,
                  status=excluded.status,
                  packet_json=excluded.packet_json,
                  stage_run_ids_json=excluded.stage_run_ids_json,
                  stage_eligible_lap_numbers_json=excluded.stage_eligible_lap_numbers_json,
                  analysis_version=excluded.analysis_version,
                  execution_json=excluded.execution_json,
                  reproduction_snapshot_json=excluded.reproduction_snapshot_json,
                  quality_json=excluded.quality_json,
                  learning_admitted=excluded.learning_admitted
                """,
                (
                    workflow.workflow_id,
                    workflow.created_at.isoformat(),
                    workflow.updated_at.isoformat(),
                    workflow.status,
                    workflow.source_run_id,
                    workflow.complaint,
                    workflow.packet.model_dump_json(),
                    _json(workflow.stage_run_ids),
                    _json(workflow.stage_eligible_lap_numbers),
                    workflow.analysis_version,
                    workflow.execution.model_dump_json() if workflow.execution else None,
                    _json(workflow.reproduction_snapshot),
                    workflow.quality.model_dump_json() if workflow.quality else None,
                    None if workflow.learning_admitted is None else int(workflow.learning_admitted),
                ),
            )
        connection.close()

    def get_controlled_workflow(self, workflow_id: str) -> ControlledWorkflow | None:
        connection = initialize_database(self.db_path)
        row = connection.execute(
            "SELECT * FROM controlled_test_workflows WHERE workflow_id = ?", (workflow_id,)
        ).fetchone()
        connection.close()
        return self._controlled_workflow_from_row(row) if row else None

    def list_controlled_workflows(self, *, active_only: bool = False) -> list[ControlledWorkflow]:
        connection = initialize_database(self.db_path)
        sql = "SELECT * FROM controlled_test_workflows"
        if active_only:
            sql += " WHERE status NOT IN ('scored', 'cancelled')"
        sql += " ORDER BY updated_at DESC"
        rows = connection.execute(sql).fetchall()
        connection.close()
        return [self._controlled_workflow_from_row(row) for row in rows]

    @staticmethod
    def _controlled_workflow_from_row(row: Any) -> ControlledWorkflow:
        from racelab_engine.analysis.crew_chief_packet import KaizenEvidencePacket
        from racelab_engine.analysis.test_director import TestExecution, TestQualityResult
        from racelab_engine.models.controlled_workflow import ControlledWorkflow

        return ControlledWorkflow(
            workflow_id=row["workflow_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
            source_run_id=row["source_run_id"],
            complaint=row["complaint"],
            packet=KaizenEvidencePacket.model_validate_json(row["packet_json"]),
            stage_run_ids=_load_json(row["stage_run_ids_json"], {}),
            stage_eligible_lap_numbers=_load_json(row["stage_eligible_lap_numbers_json"], {}),
            analysis_version=row["analysis_version"],
            execution=(
                TestExecution.model_validate_json(row["execution_json"])
                if row["execution_json"] else None
            ),
            reproduction_snapshot=_load_json(row["reproduction_snapshot_json"], {}),
            quality=(
                TestQualityResult.model_validate_json(row["quality_json"])
                if row["quality_json"] else None
            ),
            learning_admitted=(
                None if row["learning_admitted"] is None else bool(row["learning_admitted"])
            ),
        )

    def save_import(
        self,
        overview: RunOverview,
        fingerprint: FileFingerprint | None = None,
        *,
        analysis_mode: str | None = None,
    ) -> None:
        from racelab_engine.analysis import get_analysis_engine_mode

        connection = initialize_database(self.db_path)
        imported_at = utc_now_iso()
        session = overview.session

        with connection:
            connection.execute("DELETE FROM import_files WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM setup_snapshots WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM recommendations WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM events WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM laps WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM runs WHERE run_id = ?", (overview.run_id,))
            analyzed_at = utc_now_iso()
            connection.execute(
                """
                INSERT INTO runs (
                  run_id, source_file, file_hash, import_time, imported_at,
                  analysis_engine_version, analysis_config_hash, analysis_mode, analyzed_at,
                  sim_date_time,
                  car_name, car_path, track_name, track_display_name, track_id_or_path,
                  session_type, weather_summary, setup_name, setup_passed_tech,
                  setup_modified, telemetry_rate_hz, variable_count, record_count,
                  duration_seconds, air_temp, track_temp, wind_speed, wind_direction,
                  air_pressure, notes, primary_findings_json, warnings_json,
                  crew_chief_summary, next_test, session_json
                ) VALUES (
                  ?, ?, ?, ?, ?,
                  ?, ?, ?, ?,
                  ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    overview.run_id,
                    session.source_file or "",
                    session.file_hash,
                    session.import_time.isoformat() if hasattr(session.import_time, "isoformat") else str(session.import_time),
                    imported_at,
                    "1.0.0",  # analysis_engine_version
                    None,     # analysis_config_hash
                    analysis_mode or get_analysis_engine_mode(),
                    analyzed_at,
                    session.sim_date_time,
                    session.car_name,
                    session.car_path,
                    session.track_name,
                    session.track_display_name,
                    session.track_id_or_path,
                    session.session_type,
                    session.weather_summary,
                    session.setup_name,
                    int(session.setup_passed_tech) if session.setup_passed_tech is not None else None,
                    int(session.setup_modified) if session.setup_modified is not None else None,
                    session.telemetry_rate_hz,
                    session.variable_count,
                    session.record_count,
                    session.duration_seconds,
                    session.air_temp,
                    session.track_temp,
                    session.wind_speed,
                    session.wind_direction,
                    session.air_pressure,
                    _json(session.notes),
                    _json(overview.primary_findings),
                    _json(overview.warnings),
                    overview.crew_chief_summary,
                    overview.next_test,
                    _model_json(session),
                ),
            )

            for lap in overview.laps:
                connection.execute(
                    """
                    INSERT INTO laps (
                      lap_id, run_id, lap_number, lap_type, is_complete, is_useful,
                      start_time, end_time, lap_time, pct_min, pct_max, pct_span,
                      sample_count, avg_speed_mph, max_speed_mph, min_speed_mph,
                      avg_rpm, min_rpm, max_rpm, avg_throttle_pct, max_throttle_pct,
                      avg_brake_pct, max_brake_pct, min_splitter_mm, min_splitter_pct,
                      min_splitter_distance_m, min_splitter_speed_mph, max_abs_steering_deg,
                      avg_abs_steering_deg, classification_tags, lap_json
                    ) VALUES (
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        lap.lap_id,
                        lap.run_id,
                        lap.lap_number,
                        lap.lap_type,
                        int(lap.is_complete),
                        int(lap.is_useful),
                        lap.start_time,
                        lap.end_time,
                        lap.lap_time,
                        lap.pct_min,
                        lap.pct_max,
                        lap.pct_span,
                        lap.sample_count,
                        lap.avg_speed_mph,
                        lap.max_speed_mph,
                        lap.min_speed_mph,
                        lap.avg_rpm,
                        lap.min_rpm,
                        lap.max_rpm,
                        lap.avg_throttle_pct,
                        lap.max_throttle_pct,
                        lap.avg_brake_pct,
                        lap.max_brake_pct,
                        lap.min_splitter_mm,
                        lap.min_splitter_pct,
                        lap.min_splitter_distance_m,
                        lap.min_splitter_speed_mph,
                        lap.max_abs_steering_deg,
                        lap.avg_abs_steering_deg,
                        _json(lap.classification_tags),
                        _model_json(lap),
                    ),
                )

            for event in overview.events:
                connection.execute(
                    """
                    INSERT INTO events (
                      event_id, run_id, lap_number, event_type, event_subtype,
                      lap_pct_start, lap_pct_end, lap_pct_peak, distance_m_peak,
                      zone_name, severity, confidence_score, valid_for_tuning,
                      primary_metric_name, primary_metric_value, evidence_json,
                      related_setup_keys, recommended_actions, event_json, created_at
                    ) VALUES (
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        event.event_id,
                        event.run_id,
                        event.lap_number,
                        event.event_type,
                        event.event_subtype,
                        event.lap_pct_start,
                        event.lap_pct_end,
                        event.lap_pct_peak,
                        event.distance_m_peak,
                        event.zone_name,
                        event.severity,
                        event.confidence_score,
                        int(event.valid_for_tuning),
                        event.primary_metric_name,
                        event.primary_metric_value,
                        _json(event.evidence_json),
                        _json(event.related_setup_keys),
                        _json(event.recommended_actions),
                        _model_json(event),
                        imported_at,
                    ),
                )

            for recommendation in overview.recommendations:
                connection.execute(
                    """
                    INSERT INTO recommendations (
                      recommendation_id, run_id, priority_rank, issue, cause_bucket,
                      confidence_score, evidence_strength, recommendation_text,
                      success_metric, required_next_data, do_not_change_warnings,
                      evidence_event_ids, recommendation_json, created_at
                    ) VALUES (
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        recommendation.recommendation_id,
                        recommendation.run_id,
                        recommendation.priority_rank,
                        recommendation.issue,
                        recommendation.cause_bucket,
                        recommendation.confidence_score,
                        recommendation.evidence_strength,
                        recommendation.recommendation_text,
                        recommendation.success_metric,
                        _json(recommendation.required_next_data),
                        _json(recommendation.do_not_change_warnings),
                        _json(recommendation.evidence_event_ids),
                        _model_json(recommendation),
                        recommendation.created_at.isoformat()
                        if hasattr(recommendation.created_at, "isoformat")
                        else str(recommendation.created_at),
                    ),
                )

            if overview.setup_snapshot is not None:
                setup = overview.setup_snapshot
                connection.execute(
                    """
                    INSERT INTO setup_snapshots (
                      setup_id, run_id, setup_name, setup_json, snapshot_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        setup.setup_id,
                        setup.run_id,
                        setup.setup_name,
                        _json(setup.setup_json),
                        _model_json(setup),
                    ),
                )

            if fingerprint is not None:
                connection.execute(
                    """
                    INSERT INTO import_files (
                      file_id, run_id, file_type, source_path, file_hash, file_size,
                      modified_time, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{overview.run_id}:ibt:{fingerprint.sha256[:8]}",
                        overview.run_id,
                        "ibt",
                        fingerprint.path,
                        fingerprint.sha256,
                        fingerprint.file_size,
                        fingerprint.modified_time.isoformat(),
                        imported_at,
                    ),
                )
        connection.close()

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        connection = initialize_database(self.db_path)
        rows = connection.execute(
            """
            SELECT run_id, car_name, track_name, track_display_name, setup_name, imported_at
            FROM runs
            ORDER BY imported_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = [self._build_run_list_item(connection, row) for row in rows]
        connection.close()
        return items

    def get_run_list_item(self, run_id: str) -> dict[str, Any] | None:
        connection = initialize_database(self.db_path)
        row = connection.execute(
            """
            SELECT run_id, car_name, track_name, track_display_name, setup_name, imported_at
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            connection.close()
            return None
        item = self._build_run_list_item(connection, row)
        connection.close()
        return item

    def _build_run_list_item(self, connection: Any, row: Any) -> dict[str, Any]:
        best_lap = connection.execute(
            """
            SELECT lap_number, lap_time
            FROM laps
            WHERE run_id = ? AND is_useful = 1
            ORDER BY lap_time ASC
            LIMIT 1
            """,
            (row["run_id"],),
        ).fetchone()
        lap_count_row = connection.execute(
            "SELECT COUNT(*) as cnt FROM laps WHERE run_id = ?",
            (row["run_id"],),
        ).fetchone()
        has_setup = connection.execute(
            "SELECT 1 FROM setup_snapshots WHERE run_id = ? LIMIT 1",
            (row["run_id"],),
        ).fetchone()
        recommendation = connection.execute(
            """
            SELECT issue
            FROM recommendations
            WHERE run_id = ?
            ORDER BY priority_rank ASC
            LIMIT 1
            """,
            (row["run_id"],),
        ).fetchone()
        best_time = best_lap["lap_time"] if best_lap else None
        return {
            "run_id": row["run_id"],
            "car_name": row["car_name"],
            "track_name": row["track_display_name"] or row["track_name"],
            "setup_name": row["setup_name"],
            "imported_at": row["imported_at"],
            "best_lap_number": best_lap["lap_number"] if best_lap else None,
            "best_lap_time": best_time,
            "best_lap_time_s": best_time,
            "lap_count": lap_count_row["cnt"] if lap_count_row else None,
            "has_setup_snapshot": has_setup is not None,
            "primary_issue": recommendation["issue"] if recommendation else None,
        }

    def get_session(self, run_id: str) -> SessionSummary | None:
        connection = initialize_database(self.db_path)
        row = connection.execute("SELECT session_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        connection.close()
        if row is None:
            return None
        return SessionSummary.model_validate_json(row["session_json"])

    def get_laps(self, run_id: str) -> list[LapSummary]:
        connection = initialize_database(self.db_path)
        rows = connection.execute(
            "SELECT lap_json FROM laps WHERE run_id = ? ORDER BY lap_number ASC", (run_id,)
        ).fetchall()
        connection.close()
        return [LapSummary.model_validate_json(row["lap_json"]) for row in rows]

    def get_events(self, run_id: str, lap: int | None = None, event_type: str | None = None) -> list[TelemetryEvent]:
        connection = initialize_database(self.db_path)
        sql = "SELECT event_json FROM events WHERE run_id = ?"
        params: list[Any] = [run_id]
        if lap is not None:
            sql += " AND lap_number = ?"
            params.append(lap)
        if event_type is not None:
            sql += " AND UPPER(event_type) LIKE ?"
            params.append(f"{event_type.upper()}%")
        sql += " ORDER BY lap_number ASC, event_type ASC, lap_pct_peak ASC"
        rows = connection.execute(sql, params).fetchall()
        connection.close()
        return [TelemetryEvent.model_validate_json(row["event_json"]) for row in rows]

    def get_setup_snapshot(self, run_id: str) -> SetupSnapshot | None:
        connection = initialize_database(self.db_path)
        row = connection.execute(
            "SELECT snapshot_json FROM setup_snapshots WHERE run_id = ?", (run_id,)
        ).fetchone()
        connection.close()
        if row is None:
            return None
        return SetupSnapshot.model_validate_json(row["snapshot_json"])

    def get_recommendations(self, run_id: str) -> list[Recommendation]:
        connection = initialize_database(self.db_path)
        rows = connection.execute(
            """
            SELECT recommendation_json
            FROM recommendations
            WHERE run_id = ?
            ORDER BY priority_rank ASC
            """,
            (run_id,),
        ).fetchall()
        connection.close()
        return [Recommendation.model_validate_json(row["recommendation_json"]) for row in rows]

    # ── Segments ──────────────────────────────────────────────────

    def save_segments(self, run_id: str, segments: list[SegmentSummary]) -> None:
        """Save segment summaries, replacing any existing for this run."""
        connection = initialize_database(self.db_path)
        with connection:
            connection.execute("DELETE FROM segments WHERE run_id = ?", (run_id,))
            for segment in segments:
                connection.execute(
                    """
                    INSERT INTO segments (
                      segment_id, run_id, lap_number, segment_type, segment_name,
                      pct_start, pct_end, distance_start_m, distance_end_m,
                      avg_speed_mph, min_speed_mph, max_speed_mph, speed_delta_mph,
                      avg_rpm, rpm_delta, avg_throttle_pct, avg_brake_pct,
                      avg_abs_steering_deg, max_abs_steering_deg, avg_lat_accel,
                      min_splitter_mm, platform_risk_score, drag_scrub_score,
                      driver_input_score, powertrain_score, confidence_score,
                      segment_json
                    ) VALUES (
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        segment.segment_id,
                        segment.run_id,
                        segment.lap_number,
                        segment.segment_type,
                        segment.segment_name,
                        segment.pct_start,
                        segment.pct_end,
                        segment.distance_start_m,
                        segment.distance_end_m,
                        segment.avg_speed_mph,
                        segment.min_speed_mph,
                        segment.max_speed_mph,
                        segment.speed_delta_mph,
                        segment.avg_rpm,
                        segment.rpm_delta,
                        segment.avg_throttle_pct,
                        segment.avg_brake_pct,
                        segment.avg_abs_steering_deg,
                        segment.max_abs_steering_deg,
                        segment.avg_lat_accel,
                        segment.min_splitter_mm,
                        segment.platform_risk_score,
                        segment.drag_scrub_score,
                        segment.driver_input_score,
                        segment.powertrain_score,
                        segment.confidence_score,
                        _model_json(segment),
                    ),
                )
        connection.close()

    def list_segments(self, run_id: str, lap_number: int | None = None) -> list[SegmentSummary]:
        """Retrieve segment summaries for a run, optionally filtered by lap."""
        connection = initialize_database(self.db_path)
        sql = "SELECT segment_json FROM segments WHERE run_id = ?"
        params: list[Any] = [run_id]
        if lap_number is not None:
            sql += " AND lap_number = ?"
            params.append(lap_number)
        sql += " ORDER BY pct_start ASC"
        rows = connection.execute(sql, params).fetchall()
        connection.close()
        return [SegmentSummary.model_validate_json(row["segment_json"]) for row in rows]

    def get_segment(self, segment_id: str) -> SegmentSummary | None:
        """Retrieve a single segment by ID."""
        connection = initialize_database(self.db_path)
        row = connection.execute(
            "SELECT segment_json FROM segments WHERE segment_id = ?", (segment_id,)
        ).fetchone()
        connection.close()
        if row is None:
            return None
        return SegmentSummary.model_validate_json(row["segment_json"])

    def get_overview(self, run_id: str) -> RunOverview | None:
        connection = initialize_database(self.db_path)
        row = connection.execute(
            """
            SELECT session_json, primary_findings_json, warnings_json, crew_chief_summary, next_test
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        connection.close()
        if row is None:
            return None

        session = SessionSummary.model_validate_json(row["session_json"])
        laps = self.get_laps(run_id)
        useful_laps = eligible_laps(laps)
        best_lap = min(useful_laps, key=lambda lap: lap.lap_time or 999999.0) if useful_laps else None
        return RunOverview(
            run_id=run_id,
            session=session,
            best_useful_lap=best_lap,
            laps=laps,
            events=self.get_events(run_id),
            setup_snapshot=self.get_setup_snapshot(run_id),
            recommendations=self.get_recommendations(run_id),
            primary_findings=_load_json(row["primary_findings_json"], []),
            warnings=_load_json(row["warnings_json"], []),
            crew_chief_summary=row["crew_chief_summary"],
            next_test=row["next_test"],
        )
