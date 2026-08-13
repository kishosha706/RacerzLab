from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from racelab_engine.io.file_fingerprint import FileFingerprint
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.segment import SegmentSummary
from racelab_engine.models.session import RunOverview, SessionSummary, ShiftLightRpmThresholds
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.analysis.lap_detection import apply_relative_pace_filter
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.storage.db import initialize_database

if TYPE_CHECKING:
    from racelab_engine.models.controlled_workflow import ControlledWorkflow
    from racelab_engine.models.experiment import (
        MeasurementAttempt,
        MeasurementMissionContract,
    )


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


def _load_string_list(value: str | None) -> tuple[list[str], bool]:
    if not value:
        return [], True
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return [], False
    if not isinstance(payload, list) or any(not isinstance(item, str) for item in payload):
        return [], False
    return payload, True


def _session_from_run_row(row: Any) -> SessionSummary:
    """Build session context from the normalized run columns, not mutable JSON."""
    notes, notes_valid = _load_string_list(row["notes"])
    try:
        session_payload = _load_json(row["session_json"], {})
        threshold_payload = (
            session_payload.get("shift_light_rpm_thresholds")
            if isinstance(session_payload, dict) else None
        )
        shift_thresholds = (
            ShiftLightRpmThresholds.model_validate(threshold_payload)
            if threshold_payload is not None else None
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("stored shift-light threshold provenance is invalid") from exc
    return SessionSummary(
        run_id=row["run_id"],
        source_file=row["source_file"] or None,
        file_hash=row["file_hash"],
        import_time=row["import_time"],
        sim_date_time=row["sim_date_time"],
        car_name=row["car_name"],
        car_path=row["car_path"],
        track_name=row["track_name"],
        track_display_name=row["track_display_name"],
        track_id_or_path=row["track_id_or_path"],
        session_type=row["session_type"],
        weather_summary=row["weather_summary"],
        air_temp=row["air_temp"],
        track_temp=row["track_temp"],
        wind_speed=row["wind_speed"],
        wind_direction=row["wind_direction"],
        air_pressure=row["air_pressure"],
        telemetry_rate_hz=row["telemetry_rate_hz"],
        variable_count=row["variable_count"],
        record_count=row["record_count"],
        duration_seconds=row["duration_seconds"],
        setup_name=row["setup_name"],
        setup_passed_tech=(
            None if row["setup_passed_tech"] is None else bool(row["setup_passed_tech"])
        ),
        setup_modified=(
            None if row["setup_modified"] is None else bool(row["setup_modified"])
        ),
        shift_light_rpm_thresholds=shift_thresholds,
        notes=notes if notes_valid else [],
    )


_LAP_ELIGIBILITY_VERSION = "relative-pace-v2"
_ACTIONABLE_EVIDENCE_STATES = frozenset({
    EvidenceState.MEASURED,
    EvidenceState.CALCULATED,
    EvidenceState.ESTIMATED_PROXY,
    EvidenceState.OBSERVED_CORRELATION,
    EvidenceState.CONTROLLED_TEST_EFFECT,
})

_LAP_INTEGRITY_WARNING = (
    "Evidence integrity: a stored lap summary was malformed or identity-mismatched and withheld."
)
_EVENT_INTEGRITY_WARNING = (
    "Evidence integrity: a stored telemetry event was malformed or identity-mismatched and withheld."
)


class StoredEvidenceIntegrityError(ValueError):
    """Raised when a direct evidence read cannot safely return a complete scope."""


def _lap_from_storage_row(row: Any, *, requested_run_id: str | None = None) -> LapSummary:
    lap = LapSummary.model_validate_json(row["lap_json"])
    if (
        lap.lap_id != row["lap_id"]
        or lap.run_id != row["run_id"]
        or (requested_run_id is not None and lap.run_id != requested_run_id)
        or lap.lap_number != row["lap_number"]
    ):
        raise ValueError("lap identity mismatch")
    return lap


def _event_from_storage_row(
    row: Any,
    *,
    requested_run_id: str | None = None,
) -> TelemetryEvent:
    event = TelemetryEvent.model_validate_json(row["event_json"])
    if (
        event.event_id != row["event_id"]
        or event.run_id != row["run_id"]
        or (requested_run_id is not None and event.run_id != requested_run_id)
        or event.lap_number != row["lap_number"]
    ):
        raise ValueError("event identity mismatch")
    return event


def _qualify_events_for_current_laps(
    events: list[TelemetryEvent],
    laps: list[LapSummary],
) -> list[TelemetryEvent]:
    eligible_lap_numbers = {
        lap.lap_number for lap in eligible_laps(laps) if lap.lap_number is not None
    }
    qualified: list[TelemetryEvent] = []
    for event in events:
        reasons = list(event.blocker_reasons)
        lap_blocked = event.lap_number is not None and event.lap_number not in eligible_lap_numbers
        if lap_blocked:
            reasons.append("The linked lap is not eligible for engineering observations.")
        if event.evidence_state not in _ACTIONABLE_EVIDENCE_STATES:
            reasons.append("The event does not have an actionable evidence state.")
        if not event.source_channels:
            reasons.append("Evidence source channels were not recorded.")
        evidence_ready = not reasons
        if event.valid_for_tuning and evidence_ready:
            qualified.append(event)
            continue
        qualified.append(event.model_copy(update={
            "valid_for_tuning": False,
            "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT if lap_blocked else event.evidence_state,
            "blocker_reasons": list(dict.fromkeys(reasons)),
        }))
    return qualified


_RUN_LIST_SELECT = """
    SELECT
      runs.run_id,
      runs.car_name,
      runs.track_name,
      runs.track_display_name,
      runs.setup_name,
      runs.imported_at,
      runs.lap_eligibility_version,
      (
        SELECT laps.lap_number
        FROM laps
        WHERE laps.run_id = runs.run_id AND laps.is_useful = 1
        ORDER BY laps.lap_time ASC, laps.lap_number ASC
        LIMIT 1
      ) AS best_lap_number,
      (
        SELECT laps.lap_time
        FROM laps
        WHERE laps.run_id = runs.run_id AND laps.is_useful = 1
        ORDER BY laps.lap_time ASC, laps.lap_number ASC
        LIMIT 1
      ) AS best_lap_time,
      (SELECT COUNT(*) FROM laps WHERE laps.run_id = runs.run_id) AS lap_count,
      EXISTS(
        SELECT 1 FROM setup_snapshots
        WHERE setup_snapshots.run_id = runs.run_id
      ) AS has_setup_snapshot,
      (
        SELECT events.event_type
        FROM events
        WHERE events.run_id = runs.run_id
          AND events.valid_for_tuning = 1
        ORDER BY events.confidence_score DESC,
                 events.event_id ASC
        LIMIT 1
      ) AS primary_issue
    FROM runs
"""
_RUN_LIST_QUERY_CHUNK_SIZE = 500


class RaceLabRepository:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def initialize(self) -> None:
        connection = initialize_database(self.db_path)
        connection.close()

    @staticmethod
    def _write_controlled_workflow(connection: Any, workflow: ControlledWorkflow) -> None:
        connection.execute(
                """
                INSERT INTO controlled_test_workflows (
                  workflow_id, created_at, updated_at, status, source_run_id,
                  complaint, packet_json, stage_run_ids_json, stage_eligible_lap_numbers_json,
                  stage_experiment_contexts_json,
                  analysis_version, execution_json, reproduction_snapshot_json,
                  quality_json, learning_admitted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                  updated_at=excluded.updated_at,
                  status=excluded.status,
                  packet_json=excluded.packet_json,
                  stage_run_ids_json=excluded.stage_run_ids_json,
                  stage_eligible_lap_numbers_json=excluded.stage_eligible_lap_numbers_json,
                  stage_experiment_contexts_json=excluded.stage_experiment_contexts_json,
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
                    _json({
                        stage: context.model_dump(mode="json")
                        for stage, context in workflow.stage_experiment_contexts.items()
                    }),
                    workflow.analysis_version,
                    workflow.execution.model_dump_json() if workflow.execution else None,
                    _json(workflow.reproduction_snapshot),
                    workflow.quality.model_dump_json() if workflow.quality else None,
                    None if workflow.learning_admitted is None else int(workflow.learning_admitted),
                ),
            )
        connection.execute(
            "DELETE FROM controlled_workflow_run_index WHERE workflow_id = ?",
            (workflow.workflow_id,),
        )
        bindings = [(workflow.workflow_id, workflow.source_run_id, "source")]
        bindings.extend(
            (workflow.workflow_id, run_id, stage)
            for stage, run_id in workflow.stage_run_ids.items()
        )
        connection.executemany(
            "INSERT INTO controlled_workflow_run_index(workflow_id, run_id, role) VALUES (?, ?, ?)",
            bindings,
        )

    def save_controlled_workflow(self, workflow: ControlledWorkflow) -> None:
        connection = initialize_database(self.db_path)
        with connection:
            self._write_controlled_workflow(connection, workflow)
        connection.close()

    def create_controlled_workflow_if_scope_available(
        self,
        workflow: ControlledWorkflow,
        scope_run_ids: tuple[str, ...],
    ) -> None:
        """Atomically reserve one active workflow slot for an explicit run scope.

        Session membership is dynamic application state, so SQLite cannot express
        this invariant as a static unique index. ``BEGIN IMMEDIATE`` serializes the
        scope check and insert, closing the check-then-save race between concurrent
        workflow requests.
        """
        scope = {run_id for run_id in scope_run_ids if run_id}
        if not scope:
            raise ValueError("A controlled workflow requires an explicit run scope.")
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in scope)
            rows = connection.execute(
                f"SELECT DISTINCT workflow.workflow_id "
                "FROM controlled_test_workflows AS workflow "
                "JOIN controlled_workflow_run_index AS binding "
                "ON binding.workflow_id = workflow.workflow_id "
                f"WHERE binding.run_id IN ({placeholders}) "
                "AND workflow.status NOT IN ('scored', 'cancelled')",
                tuple(scope),
            ).fetchall()
            for row in rows:
                raise ValueError(
                    "Finish or explicitly abandon the active controlled workflow "
                    f"{row['workflow_id']} before starting another workflow in this session."
                )
            self._write_controlled_workflow(connection, workflow)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_controlled_workflow_if_scope_exclusive(
        self,
        workflow: ControlledWorkflow,
        scope_run_ids: tuple[str, ...],
    ) -> None:
        """Atomically recheck scope exclusivity and persist an active transition."""
        scope = {run_id for run_id in scope_run_ids if run_id}
        if not scope:
            raise ValueError("A controlled workflow transition requires an explicit run scope.")
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in scope)
            rows = connection.execute(
                f"SELECT DISTINCT active.workflow_id "
                "FROM controlled_test_workflows AS active "
                "JOIN controlled_workflow_run_index AS binding "
                "ON binding.workflow_id = active.workflow_id "
                f"WHERE binding.run_id IN ({placeholders}) "
                "AND active.status NOT IN ('scored', 'cancelled') AND active.workflow_id <> ?",
                (*tuple(scope), workflow.workflow_id),
            ).fetchall()
            for row in rows:
                raise ValueError(
                    "Finish or explicitly abandon the active controlled workflow "
                    f"{row['workflow_id']} before continuing another workflow in this session."
                )
            self._write_controlled_workflow(connection, workflow)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_controlled_workflow(self, workflow_id: str) -> ControlledWorkflow | None:
        connection = initialize_database(self.db_path)
        row = connection.execute(
            "SELECT * FROM controlled_test_workflows WHERE workflow_id = ?", (workflow_id,)
        ).fetchone()
        connection.close()
        return self._controlled_workflow_from_row(row) if row else None

    def save_measurement_mission_contract(self, contract: MeasurementMissionContract) -> None:
        """Persist one immutable mission identity without replacing its original record."""
        connection = initialize_database(self.db_path)
        try:
            with connection:
                existing = connection.execute(
                    "SELECT contract_sha256 FROM measurement_mission_contracts "
                    "WHERE contract_id = ? OR contract_sha256 = ?",
                    (contract.contract_id, contract.contract_sha256),
                ).fetchone()
                if existing is not None:
                    if existing["contract_sha256"] != contract.contract_sha256:
                        raise ValueError("mission-contract identity conflicts with durable history")
                    return
                connection.execute(
                    """
                    INSERT INTO measurement_mission_contracts (
                      contract_id, contract_sha256, created_at, contract_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        contract.contract_id,
                        contract.contract_sha256,
                        contract.created_at.isoformat(),
                        contract.model_dump_json(),
                    ),
                )
        finally:
            connection.close()

    def record_measurement_mission_attempt(
        self,
        contract: MeasurementMissionContract,
        attempt: MeasurementAttempt,
    ) -> None:
        """Append a server-validated attempt; duplicate identities must be identical."""
        from racelab_engine.models.experiment import MeasurementAttempt

        if (
            attempt.contract_id != contract.contract_id
            or attempt.contract_sha256 != contract.contract_sha256
            or attempt.run_id not in contract.session_run_ids
            or attempt.setup_sha256 != contract.setup_sha256
            or attempt.compatibility_fingerprint
            != contract.compatibility_fingerprint
        ):
            raise ValueError("measurement attempt does not bind the supplied mission contract")
        self.save_measurement_mission_contract(contract)
        connection = initialize_database(self.db_path)
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT attempt_json FROM measurement_mission_attempts WHERE attempt_id = ?",
                    (attempt.attempt_id,),
                ).fetchone()
                if existing is not None:
                    stored = MeasurementAttempt.model_validate_json(existing["attempt_json"])
                    if stored != attempt:
                        raise ValueError("measurement-attempt identity conflicts with durable history")
                    return
                prior_rows = connection.execute(
                    "SELECT attempt_json FROM measurement_mission_attempts "
                    "WHERE contract_id = ?",
                    (contract.contract_id,),
                ).fetchall()
                attempt_laps = set(attempt.eligible_lap_ids)
                for prior_row in prior_rows:
                    try:
                        prior = MeasurementAttempt.model_validate_json(
                            prior_row["attempt_json"]
                        )
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            "durable measurement-attempt history is corrupt"
                        ) from exc
                    prior_laps = set(prior.eligible_lap_ids)
                    if attempt_laps and prior_laps and attempt_laps & prior_laps:
                        raise ValueError(
                            "measurement attempts require non-overlapping eligible-lap cohorts"
                        )
                    if (
                        not attempt_laps
                        and not prior_laps
                        and attempt.run_id == prior.run_id
                    ):
                        raise ValueError(
                            "unscoped measurement attempts require a distinct run identity"
                        )
                connection.execute(
                    """
                    INSERT INTO measurement_mission_attempts (
                      attempt_id, contract_id, contract_sha256, run_id, completed_at,
                      outcome, attempt_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt.attempt_id,
                        attempt.contract_id,
                        attempt.contract_sha256,
                        attempt.run_id,
                        attempt.completed_at.isoformat(),
                        attempt.outcome,
                        attempt.model_dump_json(),
                    ),
                )
        finally:
            connection.close()

    def list_measurement_mission_attempts(
        self,
        contract: MeasurementMissionContract,
    ) -> tuple[MeasurementAttempt, ...]:
        """Reload exact-contract attempts and reject any identity or row corruption."""
        from racelab_engine.models.experiment import (
            MeasurementAttempt,
            MeasurementMissionContract,
        )

        connection = initialize_database(self.db_path)
        try:
            stored_contract = connection.execute(
                "SELECT contract_sha256, contract_json FROM measurement_mission_contracts "
                "WHERE contract_id = ?",
                (contract.contract_id,),
            ).fetchone()
            if stored_contract is None:
                return ()
            if stored_contract["contract_sha256"] != contract.contract_sha256:
                raise ValueError("durable mission contract hash does not match the current contract")
            try:
                stored_contract_model = MeasurementMissionContract.model_validate_json(
                    stored_contract["contract_json"]
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("durable mission contract content is corrupt") from exc
            if (
                stored_contract_model.contract_id != contract.contract_id
                or stored_contract_model.contract_sha256 != contract.contract_sha256
            ):
                raise ValueError("durable mission contract content does not match storage")
            historical_contracts = connection.execute(
                "SELECT contract_id, contract_json FROM measurement_mission_contracts "
                "WHERE contract_id != ?",
                (contract.contract_id,),
            ).fetchall()
            for historical in historical_contracts:
                try:
                    payload = json.loads(historical["contract_json"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "durable mission history contains unreadable contract content"
                    ) from exc
                if not isinstance(payload, dict):
                    raise ValueError(
                        "durable mission history contains malformed contract content"
                    )
                same_planning_scope = (
                    payload.get("candidate_id") == contract.candidate_id
                    and payload.get("run_id") == contract.run_id
                    and payload.get("session_id") == contract.session_id
                )
                if same_planning_scope and payload.get("schema_version") != contract.schema_version:
                    raise ValueError(
                        "durable mission history for this planning scope uses an unsupported contract schema"
                    )
            rows = connection.execute(
                """
                SELECT attempt_id, contract_id, contract_sha256, run_id, completed_at,
                       outcome, attempt_json
                FROM measurement_mission_attempts
                WHERE contract_id = ?
                ORDER BY completed_at ASC, attempt_id ASC
                """,
                (contract.contract_id,),
            ).fetchall()
        finally:
            connection.close()
        attempts: list[MeasurementAttempt] = []
        for row in rows:
            attempt = MeasurementAttempt.model_validate_json(row["attempt_json"])
            if (
                attempt.attempt_id != row["attempt_id"]
                or attempt.contract_id != contract.contract_id
                or attempt.contract_sha256 != contract.contract_sha256
                or attempt.run_id != row["run_id"]
                or attempt.outcome != row["outcome"]
                or attempt.completed_at.isoformat() != row["completed_at"]
            ):
                raise ValueError("durable measurement-attempt identity does not match storage")
            attempts.append(attempt)
        return tuple(attempts)

    def list_controlled_workflows(self, *, active_only: bool = False) -> list[ControlledWorkflow]:
        connection = initialize_database(self.db_path)
        sql = "SELECT * FROM controlled_test_workflows"
        if active_only:
            sql += " WHERE status NOT IN ('scored', 'cancelled')"
        sql += " ORDER BY updated_at DESC"
        rows = connection.execute(sql).fetchall()
        connection.close()
        return [self._controlled_workflow_from_row(row) for row in rows]

    def list_controlled_workflow_catalog_for_run_scope(
        self,
        run_ids: tuple[str, ...],
        *,
        scored_run_ids: tuple[str, ...] | None = None,
    ) -> tuple[list[ControlledWorkflow], tuple[str, ...]]:
        """Return active scoped workflows plus one latest scoped scored record.

        The normalized run index keeps this read proportional to the requested
        session scope, not total historical workflow count. Relevant malformed
        rows remain explicit blockers; unrelated rows are never deserialized.
        """
        scope = tuple(dict.fromkeys(run_id for run_id in run_ids if run_id))
        if not scope:
            return [], ("Controlled-workflow catalog requires an exact run scope.",)
        placeholders = ",".join("?" for _ in scope)
        scored_scope = tuple(dict.fromkeys(
            run_id for run_id in (scored_run_ids or scope) if run_id
        ))
        scored_placeholders = ",".join("?" for _ in scored_scope)
        connection = initialize_database(self.db_path)
        try:
            active_rows = connection.execute(
                f"""
                SELECT DISTINCT workflow.*
                FROM controlled_test_workflows AS workflow
                JOIN controlled_workflow_run_index AS binding
                  ON binding.workflow_id = workflow.workflow_id
                WHERE binding.run_id IN ({scored_placeholders})
                  AND workflow.status NOT IN ('scored', 'cancelled')
                ORDER BY workflow.updated_at DESC, workflow.workflow_id
                """,
                scored_scope,
            ).fetchall()
            scored_rows = connection.execute(
                f"""
                SELECT DISTINCT workflow.*
                FROM controlled_test_workflows AS workflow
                JOIN controlled_workflow_run_index AS binding
                  ON binding.workflow_id = workflow.workflow_id
                WHERE binding.run_id IN ({placeholders})
                  AND workflow.status = 'scored'
                ORDER BY workflow.updated_at DESC, workflow.workflow_id
                LIMIT 1
                """,
                scope,
            ).fetchall()
        finally:
            connection.close()
        workflows: list[ControlledWorkflow] = []
        blockers: list[str] = []
        for row in (*active_rows, *scored_rows):
            try:
                workflows.append(self._controlled_workflow_from_row(row))
            except (KeyError, TypeError, ValueError):
                blockers.append(
                    "A controlled-workflow record in the requested session failed integrity validation."
                )
        return workflows, tuple(dict.fromkeys(blockers))

    def list_controlled_workflows_for_run_scope(
        self,
        run_ids: tuple[str, ...],
        *,
        active_only: bool = False,
    ) -> tuple[list[ControlledWorkflow], tuple[str, ...]]:
        """Read related workflows without letting one malformed row break intelligence.

        The regular workflow API remains strict. The internal intelligence reader is
        scope-aware and fail-closed: malformed rows in the requested run/session scope
        are withheld and reported as integrity blockers, while unrelated corrupt rows
        cannot take down the current report.
        """
        scope = tuple(dict.fromkeys(run_id for run_id in run_ids if run_id))
        if not scope:
            return [], ()
        placeholders = ",".join("?" for _ in scope)
        connection = initialize_database(self.db_path)
        sql = (
            "SELECT DISTINCT workflow.* FROM controlled_test_workflows AS workflow "
            "JOIN controlled_workflow_run_index AS binding "
            "ON binding.workflow_id = workflow.workflow_id "
            f"WHERE binding.run_id IN ({placeholders})"
        )
        if active_only:
            sql += " AND workflow.status NOT IN ('scored', 'cancelled')"
        sql += " ORDER BY workflow.updated_at DESC"
        rows = connection.execute(sql, scope).fetchall()
        connection.close()

        workflows: list[ControlledWorkflow] = []
        blockers: list[str] = []
        for row in rows:
            try:
                workflow = self._controlled_workflow_from_row(row)
                if (
                    not workflow.workflow_id.strip()
                    or workflow.workflow_id != workflow.workflow_id.strip()
                    or not workflow.source_run_id.strip()
                    or workflow.source_run_id != workflow.source_run_id.strip()
                ):
                    raise ValueError("workflow identities must be canonical")
            except (KeyError, TypeError, ValueError):
                blockers.append(
                    "A controlled-workflow record in this scope failed integrity validation."
                )
                continue
            workflows.append(workflow)
        return workflows, tuple(dict.fromkeys(blockers))

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
            stage_experiment_contexts=_load_json(row["stage_experiment_contexts_json"], {}),
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

        qualified_laps = apply_relative_pace_filter(overview.laps)
        connection = initialize_database(self.db_path)
        imported_at = utc_now_iso()
        session = overview.session

        with connection:
            connection.execute("DELETE FROM import_files WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM setup_snapshots WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM events WHERE run_id = ?", (overview.run_id,))
            connection.execute("DELETE FROM laps WHERE run_id = ?", (overview.run_id,))
            # Segments are import-owned derived evidence. Clear them in the same
            # transaction so a reimport that yields no segments cannot expose
            # stale geometry from the previous file, while the parent run row
            # (and workflow foreign keys) remain intact.
            connection.execute("DELETE FROM segments WHERE run_id = ?", (overview.run_id,))
            analyzed_at = utc_now_iso()
            connection.execute(
                """
                INSERT INTO runs (
                  run_id, source_file, file_hash, import_time, imported_at,
                  analysis_engine_version, lap_eligibility_version,
                  analysis_config_hash, analysis_mode, analyzed_at,
                  sim_date_time,
                  car_name, car_path, track_name, track_display_name, track_id_or_path,
                  session_type, weather_summary, setup_name, setup_passed_tech,
                  setup_modified, telemetry_rate_hz, variable_count, record_count,
                  duration_seconds, air_temp, track_temp, wind_speed, wind_direction,
                  air_pressure, notes, primary_findings_json, warnings_json, session_json
                ) VALUES (
                  ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?,
                  ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?
                )
                ON CONFLICT(run_id) DO UPDATE SET
                  source_file=excluded.source_file,
                  file_hash=excluded.file_hash,
                  import_time=excluded.import_time,
                  imported_at=excluded.imported_at,
                  analysis_engine_version=excluded.analysis_engine_version,
                  lap_eligibility_version=excluded.lap_eligibility_version,
                  analysis_config_hash=excluded.analysis_config_hash,
                  analysis_mode=excluded.analysis_mode,
                  analyzed_at=excluded.analyzed_at,
                  sim_date_time=excluded.sim_date_time,
                  car_name=excluded.car_name,
                  car_path=excluded.car_path,
                  track_name=excluded.track_name,
                  track_display_name=excluded.track_display_name,
                  track_id_or_path=excluded.track_id_or_path,
                  session_type=excluded.session_type,
                  weather_summary=excluded.weather_summary,
                  setup_name=excluded.setup_name,
                  setup_passed_tech=excluded.setup_passed_tech,
                  setup_modified=excluded.setup_modified,
                  telemetry_rate_hz=excluded.telemetry_rate_hz,
                  variable_count=excluded.variable_count,
                  record_count=excluded.record_count,
                  duration_seconds=excluded.duration_seconds,
                  air_temp=excluded.air_temp,
                  track_temp=excluded.track_temp,
                  wind_speed=excluded.wind_speed,
                  wind_direction=excluded.wind_direction,
                  air_pressure=excluded.air_pressure,
                  notes=excluded.notes,
                  primary_findings_json=excluded.primary_findings_json,
                  warnings_json=excluded.warnings_json,
                  session_json=excluded.session_json
                """,
                (
                    overview.run_id,
                    session.source_file or "",
                    session.file_hash,
                    session.import_time.isoformat() if hasattr(session.import_time, "isoformat") else str(session.import_time),
                    imported_at,
                    "1.0.0",  # analysis_engine_version
                    _LAP_ELIGIBILITY_VERSION,
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
                    _model_json(session),
                ),
            )

            for lap in qualified_laps:
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
                      related_setup_keys, event_json, created_at
                    ) VALUES (
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                        _model_json(event),
                        imported_at,
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

    @staticmethod
    def _requalify_persisted_laps(connection: Any, run_ids: list[str]) -> None:
        unique_run_ids = list(dict.fromkeys(run_ids))
        if not unique_run_ids:
            return
        placeholders = ",".join("?" for _ in unique_run_ids)
        rows = connection.execute(
            f"SELECT lap_id, run_id, lap_number, lap_json FROM laps WHERE run_id IN ({placeholders}) ORDER BY run_id, lap_number",
            unique_run_ids,
        ).fetchall()
        by_run_id: dict[str, list[LapSummary]] = {run_id: [] for run_id in unique_run_ids}
        for row in rows:
            try:
                lap = _lap_from_storage_row(row)
            except (TypeError, ValueError):
                continue
            by_run_id[str(row["run_id"])].append(lap)
        with connection:
            for run_id, stored_laps in by_run_id.items():
                for lap in apply_relative_pace_filter(stored_laps):
                    connection.execute(
                        """
                        UPDATE laps
                        SET lap_type = ?, is_useful = ?, classification_tags = ?, lap_json = ?
                        WHERE lap_id = ?
                        """,
                        (
                            lap.lap_type,
                            int(lap.is_useful),
                            _json(lap.classification_tags),
                            _model_json(lap),
                            lap.lap_id,
                        ),
                    )
                connection.execute(
                    "UPDATE runs SET lap_eligibility_version = ? WHERE run_id = ?",
                    (_LAP_ELIGIBILITY_VERSION, run_id),
                )

    @classmethod
    def _refresh_stale_run_list_rows(
        cls,
        connection: Any,
        sql: str,
        params: list[Any] | tuple[Any, ...],
    ) -> list[Any]:
        rows = connection.execute(sql, params).fetchall()
        stale_run_ids = [
            str(row["run_id"])
            for row in rows
            if row["lap_eligibility_version"] != _LAP_ELIGIBILITY_VERSION
        ]
        if stale_run_ids:
            cls._requalify_persisted_laps(connection, stale_run_ids)
            rows = connection.execute(sql, params).fetchall()
        return rows

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        connection = initialize_database(self.db_path)
        try:
            rows = self._refresh_stale_run_list_rows(
                connection,
                _RUN_LIST_SELECT + " ORDER BY runs.imported_at DESC LIMIT ?",
                (limit,),
            )
        finally:
            connection.close()
        return [self._run_list_item_from_row(row) for row in rows]

    def get_run_list_item(self, run_id: str) -> dict[str, Any] | None:
        connection = initialize_database(self.db_path)
        try:
            rows = self._refresh_stale_run_list_rows(
                connection,
                _RUN_LIST_SELECT + " WHERE runs.run_id = ?",
                (run_id,),
            )
            row = rows[0] if rows else None
        finally:
            connection.close()
        return self._run_list_item_from_row(row) if row is not None else None

    def get_run_list_items(self, run_ids: list[str]) -> list[dict[str, Any]]:
        """Return summaries for a session's runs without an N+1 connection loop."""
        ordered_ids = list(dict.fromkeys(run_ids))
        if not ordered_ids:
            return []

        connection = initialize_database(self.db_path)
        def load_rows(connection: Any) -> list[Any]:
            rows: list[Any] = []
            for start in range(0, len(ordered_ids), _RUN_LIST_QUERY_CHUNK_SIZE):
                chunk = ordered_ids[start : start + _RUN_LIST_QUERY_CHUNK_SIZE]
                placeholders = ",".join("?" for _ in chunk)
                rows.extend(
                    connection.execute(
                        _RUN_LIST_SELECT
                        + f" WHERE runs.run_id IN ({placeholders})",
                        chunk,
                    ).fetchall()
                )
            return rows

        try:
            rows = load_rows(connection)
            stale_run_ids = [
                str(row["run_id"])
                for row in rows
                if row["lap_eligibility_version"] != _LAP_ELIGIBILITY_VERSION
            ]
            if stale_run_ids:
                self._requalify_persisted_laps(connection, stale_run_ids)
                rows = load_rows(connection)
        finally:
            connection.close()

        by_run_id = {
            row["run_id"]: self._run_list_item_from_row(row)
            for row in rows
        }
        return [by_run_id[run_id] for run_id in ordered_ids if run_id in by_run_id]

    def list_tech_passing_setup_candidates(
        self,
        *,
        car_path: str | None,
        track_id_or_path: str | None,
        session_type: str | None,
    ) -> list[tuple[str, SetupSnapshot]]:
        """Return every stored tech-passing setup in one bounded database read.

        The indexed fields are a cheap first-stage context gate.  Callers must
        still verify the complete file-declared compatibility identity before
        treating a returned snapshot as a legal option because car/build and
        track-version fields intentionally remain owned by the telemetry
        manifest.
        """
        filters = ["runs.setup_passed_tech = 1"]
        params: list[str] = []
        for column, value in (
            ("car_path", car_path),
            ("track_id_or_path", track_id_or_path),
            ("session_type", session_type),
        ):
            if value is not None:
                filters.append(f"runs.{column} = ?")
                params.append(value)

        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                """
                SELECT runs.run_id AS candidate_run_id,
                       setup_snapshots.setup_id,
                       setup_snapshots.run_id AS snapshot_run_id,
                       setup_snapshots.snapshot_json
                FROM runs
                JOIN setup_snapshots ON setup_snapshots.run_id = runs.run_id
                WHERE """
                + " AND ".join(filters)
                + " AND setup_snapshots.snapshot_json IS NOT NULL"
                + " ORDER BY runs.imported_at DESC, runs.run_id ASC",
                params,
            ).fetchall()
        finally:
            connection.close()
        candidates: list[tuple[str, SetupSnapshot]] = []
        for row in rows:
            try:
                snapshot = SetupSnapshot.model_validate_json(row["snapshot_json"])
                candidate_run_id = str(row["candidate_run_id"])
                if (
                    snapshot.setup_id != row["setup_id"]
                    or snapshot.run_id != row["snapshot_run_id"]
                    or snapshot.run_id != candidate_run_id
                ):
                    raise ValueError("setup candidate identity mismatch")
            except (TypeError, ValueError):
                continue
            candidates.append((candidate_run_id, snapshot))
        return candidates

    @staticmethod
    def _run_list_item_from_row(row: Any) -> dict[str, Any]:
        best_time = row["best_lap_time"]
        return {
            "run_id": row["run_id"],
            "car_name": row["car_name"],
            "track_name": row["track_display_name"] or row["track_name"],
            "setup_name": row["setup_name"],
            "imported_at": row["imported_at"],
            "best_lap_number": row["best_lap_number"],
            "best_lap_time": best_time,
            "best_lap_time_s": best_time,
            "lap_count": row["lap_count"],
            "has_setup_snapshot": bool(row["has_setup_snapshot"]),
            "primary_issue": row["primary_issue"],
        }

    def get_session(self, run_id: str) -> SessionSummary | None:
        connection = initialize_database(self.db_path)
        row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        connection.close()
        if row is None:
            return None
        return _session_from_run_row(row)

    def get_laps(self, run_id: str) -> list[LapSummary]:
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                """
                SELECT lap_id, run_id, lap_number, lap_json
                FROM laps
                WHERE run_id = ?
                ORDER BY lap_number ASC
                """,
                (run_id,),
            ).fetchall()
        finally:
            connection.close()
        try:
            laps = [
                _lap_from_storage_row(row, requested_run_id=run_id)
                for row in rows
            ]
        except (TypeError, ValueError) as exc:
            raise StoredEvidenceIntegrityError(
                "Evidence integrity: one or more stored lap summaries were malformed or "
                "identity-mismatched; lap-derived metrics are unavailable."
            ) from exc
        return apply_relative_pace_filter(laps)

    def get_events(self, run_id: str, lap: int | None = None, event_type: str | None = None) -> list[TelemetryEvent]:
        connection = initialize_database(self.db_path)
        sql = "SELECT event_id, run_id, lap_number, event_json FROM events WHERE run_id = ?"
        params: list[Any] = [run_id]
        if lap is not None:
            sql += " AND lap_number = ?"
            params.append(lap)
        if event_type is not None:
            sql += " AND UPPER(event_type) LIKE ?"
            params.append(f"{event_type.upper()}%")
        sql += " ORDER BY lap_number ASC, event_type ASC, lap_pct_peak ASC"
        try:
            rows = connection.execute(sql, params).fetchall()
        finally:
            connection.close()
        try:
            events = [
                _event_from_storage_row(row, requested_run_id=run_id)
                for row in rows
            ]
        except (TypeError, ValueError) as exc:
            raise StoredEvidenceIntegrityError(
                "Evidence integrity: one or more stored telemetry events were malformed or "
                "identity-mismatched; event-derived conclusions are unavailable."
            ) from exc
        return _qualify_events_for_current_laps(events, self.get_laps(run_id))

    def get_setup_snapshot(self, run_id: str) -> SetupSnapshot | None:
        connection = initialize_database(self.db_path)
        row = connection.execute(
            """
            SELECT setup_id, run_id, snapshot_json
            FROM setup_snapshots
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        connection.close()
        if row is None:
            return None
        try:
            snapshot = SetupSnapshot.model_validate_json(row["snapshot_json"])
            if (
                snapshot.setup_id != row["setup_id"]
                or snapshot.run_id != row["run_id"]
                or snapshot.run_id != run_id
            ):
                raise ValueError("setup snapshot identity mismatch")
        except (TypeError, ValueError):
            return None
        return snapshot

    def get_setup_snapshots(self, run_ids: tuple[str, ...]) -> dict[str, SetupSnapshot]:
        """Batch exact setup provenance for evidence projection."""

        scope = tuple(dict.fromkeys(run_id for run_id in run_ids if run_id))
        if not scope:
            return {}
        placeholders = ",".join("?" for _ in scope)
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                f"SELECT setup_id, run_id, snapshot_json FROM setup_snapshots "
                f"WHERE run_id IN ({placeholders})",
                scope,
            ).fetchall()
        finally:
            connection.close()
        snapshots: dict[str, SetupSnapshot] = {}
        for row in rows:
            try:
                snapshot = SetupSnapshot.model_validate_json(row["snapshot_json"])
                if snapshot.setup_id != row["setup_id"] or snapshot.run_id != row["run_id"]:
                    raise ValueError("setup snapshot identity mismatch")
            except (TypeError, ValueError):
                continue
            snapshots[snapshot.run_id] = snapshot
        return snapshots

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
        try:
            row = connection.execute(
                """
                SELECT *
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            lap_rows = connection.execute(
                """
                SELECT lap_id, run_id, lap_number, lap_json
                FROM laps
                WHERE run_id = ?
                ORDER BY lap_number ASC
                """,
                (run_id,),
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT event_id, run_id, lap_number, event_json
                FROM events
                WHERE run_id = ?
                ORDER BY lap_number ASC, event_type ASC, lap_pct_peak ASC
                """,
                (run_id,),
            ).fetchall()
            setup_row = connection.execute(
                """
                SELECT setup_id, run_id, snapshot_json
                FROM setup_snapshots
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None

        session = _session_from_run_row(row)
        if row["run_id"] != run_id or session.run_id != run_id:
            raise ValueError("The stored session identity does not match the requested run.")
        integrity_warnings: list[str] = []
        parsed_laps: list[LapSummary] = []
        for item in lap_rows:
            try:
                parsed_laps.append(_lap_from_storage_row(item, requested_run_id=run_id))
            except (TypeError, ValueError):
                integrity_warnings.append(_LAP_INTEGRITY_WARNING)
        laps = apply_relative_pace_filter(parsed_laps)

        parsed_events: list[TelemetryEvent] = []
        for item in event_rows:
            try:
                parsed_events.append(_event_from_storage_row(item, requested_run_id=run_id))
            except (TypeError, ValueError):
                integrity_warnings.append(_EVENT_INTEGRITY_WARNING)
        events = _qualify_events_for_current_laps(
            parsed_events,
            laps,
        )

        setup_snapshot = None
        if setup_row is not None:
            try:
                candidate = SetupSnapshot.model_validate_json(setup_row["snapshot_json"])
                if (
                    candidate.setup_id != setup_row["setup_id"]
                    or candidate.run_id != setup_row["run_id"]
                    or candidate.run_id != run_id
                ):
                    raise ValueError("setup snapshot identity mismatch")
                setup_snapshot = candidate
            except (TypeError, ValueError):
                integrity_warnings.append(
                    "Evidence integrity: the stored setup snapshot was malformed or identity-mismatched and withheld."
                )

        primary_findings, primary_findings_valid = _load_string_list(
            row["primary_findings_json"]
        )
        if not primary_findings_valid:
            integrity_warnings.append(
                "Evidence integrity: the stored primary findings were malformed and withheld."
            )
        stored_warnings, stored_warnings_valid = _load_string_list(row["warnings_json"])
        if not stored_warnings_valid:
            integrity_warnings.append(
                "Evidence integrity: the stored warning collection was malformed and withheld."
            )
        qualified_event_ids = {event.event_id for event in events if event.valid_for_tuning}
        useful_laps = eligible_laps(laps)
        best_lap = min(useful_laps, key=lambda lap: lap.lap_time or 999999.0) if useful_laps else None
        return RunOverview(
            run_id=run_id,
            session=session,
            best_useful_lap=best_lap,
            laps=laps,
            events=events,
            setup_snapshot=setup_snapshot,
            primary_findings=(
                primary_findings
                if qualified_event_ids else []
            ),
            warnings=list(dict.fromkeys([
                *stored_warnings,
                *integrity_warnings,
            ])),
        )
