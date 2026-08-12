"""Durable, fail-closed persistence for Crew Chief investigations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    ComponentResponseRecord,
    CrewChiefEffectivenessRecord,
    CrewChiefEvent,
    CrewChiefInvestigation,
    DriverKnowledgeRecord,
    EngineeringObjective,
    SuccessContract,
)
from racelab_engine.storage.db import initialize_database


def crew_chief_event_hash(event: CrewChiefEvent) -> str:
    payload = event.model_dump(mode="json", exclude={"event_hash"})
    return canonical_json_sha256(payload)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CrewChiefIntegrityError(ValueError):
    """Raised when durable investigation history cannot be trusted."""


class CrewChiefRepository:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    def save_investigation(self, investigation: CrewChiefInvestigation) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT investigation_json FROM crew_chief_investigations "
                "WHERE investigation_id = ?",
                (investigation.investigation_id,),
            ).fetchone()
            encoded = investigation.model_dump_json()
            if row is not None and row["investigation_json"] != encoded:
                raise CrewChiefIntegrityError(
                    "investigation identity already owns other data"
                )
            if row is None:
                connection.execute(
                    """
                    INSERT INTO crew_chief_investigations (
                      investigation_id, run_id, session_id, workspace_revision,
                      status, opened_at, investigation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        investigation.investigation_id,
                        investigation.workspace_identity.run_id,
                        investigation.workspace_identity.session_id,
                        investigation.workspace_identity.workspace_revision,
                        investigation.status,
                        investigation.opened_at.isoformat(),
                        encoded,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_investigation(self, investigation_id: str) -> CrewChiefInvestigation | None:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                "SELECT * FROM crew_chief_investigations WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        investigation = CrewChiefInvestigation.model_validate_json(
            row["investigation_json"]
        )
        if (
            investigation.investigation_id != row["investigation_id"]
            or investigation.workspace_identity.run_id != row["run_id"]
            or investigation.workspace_identity.session_id != row["session_id"]
            or investigation.workspace_identity.workspace_revision
            != row["workspace_revision"]
        ):
            raise CrewChiefIntegrityError("investigation row identity is corrupt")
        return investigation

    def latest_investigation(
        self, run_id: str, session_id: str
    ) -> CrewChiefInvestigation | None:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                """
                SELECT investigation_id FROM crew_chief_investigations
                WHERE run_id = ? AND session_id = ?
                ORDER BY opened_at DESC, investigation_id DESC LIMIT 1
                """,
                (run_id, session_id),
            ).fetchone()
        finally:
            connection.close()
        return self.get_investigation(row["investigation_id"]) if row else None

    def append_event(self, event: CrewChiefEvent) -> None:
        if crew_chief_event_hash(event) != event.event_hash:
            raise CrewChiefIntegrityError("Crew Chief event hash mismatch")
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT event_json FROM crew_chief_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            encoded = event.model_dump_json()
            if existing is not None:
                if existing["event_json"] != encoded:
                    raise CrewChiefIntegrityError(
                        "event identity already owns other data"
                    )
                connection.commit()
                return
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS last_sequence "
                "FROM crew_chief_events WHERE investigation_id = ?",
                (event.investigation_id,),
            ).fetchone()
            expected = int(row["last_sequence"]) + 1
            if event.sequence != expected:
                raise CrewChiefIntegrityError(
                    f"event sequence {event.sequence} does not follow {expected - 1}"
                )
            connection.execute(
                """
                INSERT INTO crew_chief_events (
                  event_id, investigation_id, sequence, workspace_revision,
                  created_at, event_hash, event_type, event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.investigation_id,
                    event.sequence,
                    event.workspace_revision,
                    event.created_at.isoformat(),
                    event.event_hash,
                    event.event_type,
                    encoded,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_events(self, investigation_id: str) -> tuple[CrewChiefEvent, ...]:
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                "SELECT * FROM crew_chief_events WHERE investigation_id = ? "
                "ORDER BY sequence, event_id",
                (investigation_id,),
            ).fetchall()
        finally:
            connection.close()
        events: list[CrewChiefEvent] = []
        for expected, row in enumerate(rows, start=1):
            event = CrewChiefEvent.model_validate_json(row["event_json"])
            if (
                event.investigation_id != investigation_id
                or event.event_id != row["event_id"]
                or event.sequence != expected
                or event.event_hash != row["event_hash"]
                or crew_chief_event_hash(event) != event.event_hash
            ):
                raise CrewChiefIntegrityError("Crew Chief event history is corrupt")
            events.append(event)
        return tuple(events)

    def save_objective(
        self,
        investigation_id: str,
        workspace_revision: str,
        objective: EngineeringObjective,
    ) -> None:
        objective_id = (
            f"cco_{canonical_json_sha256([investigation_id, objective])[:24]}"
        )
        connection = initialize_database(self.db_path)
        try:
            connection.execute(
                """
                INSERT INTO engineering_objectives (
                  objective_id, investigation_id, workspace_revision, selected_at,
                  objective_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                  objective_id=excluded.objective_id,
                  workspace_revision=excluded.workspace_revision,
                  selected_at=excluded.selected_at,
                  objective_json=excluded.objective_json
                """,
                (
                    objective_id,
                    investigation_id,
                    workspace_revision,
                    _now(),
                    f'{{"objective":"{objective.value}"}}',
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def save_success_contract(
        self, investigation_id: str, contract: SuccessContract
    ) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute(
                """
                INSERT INTO crew_chief_success_contracts (
                  contract_id, investigation_id, workspace_revision, created_at,
                  contract_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                  contract_id=excluded.contract_id,
                  workspace_revision=excluded.workspace_revision,
                  created_at=excluded.created_at,
                  contract_json=excluded.contract_json
                """,
                (
                    contract.contract_id,
                    investigation_id,
                    contract.workspace_revision,
                    _now(),
                    contract.model_dump_json(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def save_response_record(self, record: ComponentResponseRecord) -> None:
        connection = initialize_database(self.db_path)
        try:
            existing = connection.execute(
                "SELECT record_json FROM component_response_records "
                "WHERE source_workflow_id = ?",
                (record.source_workflow_id,),
            ).fetchone()
            encoded = record.model_dump_json()
            if existing and existing["record_json"] != encoded:
                raise CrewChiefIntegrityError("workflow response history is immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO component_response_records (
                  record_id, source_workflow_id, source_run_id, context_identity,
                  created_at, record_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.source_workflow_id,
                    record.source_run_ids[-1],
                    record.context_identity,
                    _now(),
                    encoded,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def list_response_records(
        self, context_identity: str
    ) -> tuple[ComponentResponseRecord, ...]:
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                "SELECT record_json FROM component_response_records "
                "WHERE context_identity = ? ORDER BY created_at, record_id",
                (context_identity,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            ComponentResponseRecord.model_validate_json(row[0]) for row in rows
        )

    def save_driver_memory(self, record: DriverKnowledgeRecord) -> None:
        connection = initialize_database(self.db_path)
        try:
            encoded = record.model_dump_json()
            existing = connection.execute(
                "SELECT record_json FROM crew_chief_driver_memory WHERE record_id = ?",
                (record.record_id,),
            ).fetchone()
            if existing and existing["record_json"] != encoded:
                raise CrewChiefIntegrityError("driver-memory identity is immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO crew_chief_driver_memory (
                  record_id, investigation_id, session_id, recorded_at, record_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.investigation_id,
                    record.session_id,
                    record.recorded_at.isoformat(),
                    encoded,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def list_driver_memory(self, session_id: str) -> tuple[DriverKnowledgeRecord, ...]:
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                "SELECT record_json FROM crew_chief_driver_memory "
                "WHERE session_id = ? ORDER BY recorded_at, record_id",
                (session_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(DriverKnowledgeRecord.model_validate_json(row[0]) for row in rows)

    def save_effectiveness(self, record: CrewChiefEffectivenessRecord) -> None:
        connection = initialize_database(self.db_path)
        try:
            connection.execute(
                """
                INSERT INTO crew_chief_effectiveness_records (
                  record_id, investigation_id, workspace_revision, recorded_at,
                  record_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                  record_id=excluded.record_id,
                  workspace_revision=excluded.workspace_revision,
                  recorded_at=excluded.recorded_at,
                  record_json=excluded.record_json
                """,
                (
                    record.record_id,
                    record.investigation_id,
                    record.workspace_revision,
                    record.recorded_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
            connection.commit()
        finally:
            connection.close()


__all__ = [
    "CrewChiefIntegrityError",
    "CrewChiefRepository",
    "crew_chief_event_hash",
]
