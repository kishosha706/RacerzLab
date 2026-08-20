"""Immutable P35.4.4 Engineering Case and DriverIntent persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from racelab_engine.models.engineering_case import (
    CanonicalEngineeringCase,
    CaseChangeCategory,
    DriverIntent,
    EngineeringCaseRevision,
    EngineeringCaseRevisionSummary,
)
from racelab_engine.storage.db import initialize_database


class EngineeringCaseIntegrityError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class EngineeringCaseRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path

    @staticmethod
    def _revision_from_row(row: sqlite3.Row) -> EngineeringCaseRevision:
        try:
            revision = EngineeringCaseRevision.model_validate_json(
                row["revision_json"]
            )
        except (TypeError, ValueError) as exc:
            raise EngineeringCaseIntegrityError(
                "Stored Engineering Case revision is unreadable or corrupt."
            ) from exc
        if (
            revision.case_id != row["case_id"]
            or revision.case_revision != row["case_revision"]
            or revision.case_sha256 != row["case_sha256"]
            or revision.previous_case_sha256 != row["previous_case_sha256"]
            or revision.created_at.isoformat() != row["created_at"]
            or revision.change_category != row["change_category"]
            or revision.source_workspace_revision
            != row["source_workspace_revision"]
        ):
            raise EngineeringCaseIntegrityError(
                "Stored Engineering Case revision columns and payload disagree."
            )
        return revision

    def finalize_case(
        self,
        case: CanonicalEngineeringCase,
        *,
        change_category: CaseChangeCategory = "rebuild",
        created_at: datetime | None = None,
    ) -> EngineeringCaseRevision:
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            head = connection.execute(
                "SELECT * FROM engineering_cases WHERE case_id = ?",
                (case.case_id,),
            ).fetchone()
            scope = connection.execute(
                "SELECT case_id FROM engineering_cases WHERE run_id = ? AND session_id = ?",
                (case.run_id, case.session_id),
            ).fetchone()
            if scope is not None and scope["case_id"] != case.case_id:
                raise EngineeringCaseIntegrityError(
                    "Engineering Case scope is already owned by another lifecycle identity."
                )
            if head is not None and head["current_case_sha256"] == case.case_sha256:
                row = connection.execute(
                    "SELECT * FROM engineering_case_revisions WHERE case_id = ? AND case_revision = ?",
                    (case.case_id, head["current_revision"]),
                ).fetchone()
                if row is None:
                    raise EngineeringCaseIntegrityError(
                        "Engineering Case head points to a missing revision."
                    )
                revision = self._revision_from_row(row)
                connection.commit()
                return revision

            revision_number = 1 if head is None else int(head["current_revision"]) + 1
            previous_sha = None if head is None else str(head["current_case_sha256"])
            revision = EngineeringCaseRevision(
                case_id=case.case_id,
                case_revision=revision_number,
                case_sha256=case.case_sha256,
                previous_case_sha256=previous_sha,
                created_at=created_at or _now(),
                change_category="initial" if head is None else change_category,
                source_workspace_revision=case.workspace_revision,
                case=case,
            )
            if head is None:
                connection.execute(
                    """
                    INSERT INTO engineering_cases(
                      case_id, run_id, session_id, created_at,
                      current_revision, current_case_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case.case_id,
                        case.run_id,
                        case.session_id,
                        revision.created_at.isoformat(),
                        revision.case_revision,
                        revision.case_sha256,
                    ),
                )
            connection.execute(
                """
                INSERT INTO engineering_case_revisions(
                  case_id, case_revision, case_sha256, previous_case_sha256,
                  created_at, change_category, source_workspace_revision, revision_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision.case_id,
                    revision.case_revision,
                    revision.case_sha256,
                    revision.previous_case_sha256,
                    revision.created_at.isoformat(),
                    revision.change_category,
                    revision.source_workspace_revision,
                    revision.model_dump_json(),
                ),
            )
            if head is not None:
                updated = connection.execute(
                    """
                    UPDATE engineering_cases
                    SET current_revision = ?, current_case_sha256 = ?
                    WHERE case_id = ? AND current_revision = ? AND current_case_sha256 = ?
                    """,
                    (
                        revision.case_revision,
                        revision.case_sha256,
                        revision.case_id,
                        revision.case_revision - 1,
                        revision.previous_case_sha256,
                    ),
                )
                if updated.rowcount != 1:
                    raise EngineeringCaseIntegrityError(
                        "Engineering Case head changed during revision publication."
                    )
            connection.commit()
            return revision
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def current_for_scope(
        self, run_id: str, session_id: str
    ) -> EngineeringCaseRevision | None:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                """
                SELECT revision.*
                FROM engineering_cases AS head
                JOIN engineering_case_revisions AS revision
                  ON revision.case_id = head.case_id
                 AND revision.case_revision = head.current_revision
                WHERE head.run_id = ? AND head.session_id = ?
                """,
                (run_id, session_id),
            ).fetchone()
            return None if row is None else self._revision_from_row(row)
        finally:
            connection.close()

    def current(self, case_id: str) -> EngineeringCaseRevision | None:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                """
                SELECT revision.*
                FROM engineering_cases AS head
                JOIN engineering_case_revisions AS revision
                  ON revision.case_id = head.case_id
                 AND revision.case_revision = head.current_revision
                WHERE head.case_id = ?
                """,
                (case_id,),
            ).fetchone()
            return None if row is None else self._revision_from_row(row)
        finally:
            connection.close()

    def history(
        self, case_id: str, *, limit: int = 25
    ) -> tuple[EngineeringCaseRevisionSummary, ...]:
        bounded = max(1, min(limit, 100))
        connection = initialize_database(self.db_path)
        try:
            rows = connection.execute(
                """
                SELECT * FROM engineering_case_revisions
                WHERE case_id = ?
                ORDER BY case_revision DESC
                LIMIT ?
                """,
                (case_id, bounded),
            ).fetchall()
            revisions = tuple(self._revision_from_row(row) for row in rows)
            for newer, older in zip(revisions, revisions[1:], strict=False):
                if (
                    newer.case_revision != older.case_revision + 1
                    or newer.previous_case_sha256 != older.case_sha256
                ):
                    raise EngineeringCaseIntegrityError(
                        "Engineering Case revision hash chain is incomplete or reordered."
                    )
            return tuple(
                EngineeringCaseRevisionSummary(
                    case_id=item.case_id,
                    case_revision=item.case_revision,
                    case_sha256=item.case_sha256,
                    previous_case_sha256=item.previous_case_sha256,
                    created_at=item.created_at,
                    change_category=item.change_category,
                    source_workspace_revision=item.source_workspace_revision,
                )
                for item in revisions
            )
        finally:
            connection.close()

    @staticmethod
    def append_driver_intent_in_transaction(
        connection: sqlite3.Connection,
        *,
        case_id: str,
        raw_driver_wording: str,
        objective: str,
        source: str,
        canonical_symptom: str | None = None,
        phase_scope: str | None = None,
        response_regime_scope: str = "unknown",
        traffic_context: str = "unknown",
        stint_context: str | None = None,
        power_state_context: str | None = None,
        time_origin_scope: str | None = None,
        driver_demand_scope: str | None = None,
        typed_interpretation_provenance: tuple[str, ...] = (),
        created_at: datetime | None = None,
    ) -> DriverIntent:
        head = connection.execute(
            "SELECT case_id FROM engineering_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if head is None:
            raise ValueError("DriverIntent requires an existing Engineering Case.")
        previous_row = connection.execute(
            """
            SELECT intent_json FROM engineering_driver_intents
            WHERE case_id = ? ORDER BY intent_revision DESC LIMIT 1
            """,
            (case_id,),
        ).fetchone()
        previous = (
            None
            if previous_row is None
            else DriverIntent.model_validate_json(previous_row["intent_json"])
        )
        intent = DriverIntent.build(
            case_id=case_id,
            intent_revision=1 if previous is None else previous.intent_revision + 1,
            raw_driver_wording=raw_driver_wording,
            canonical_symptom=canonical_symptom,
            phase_scope=phase_scope,
            response_regime_scope=response_regime_scope,
            traffic_context=traffic_context,
            stint_context=stint_context,
            power_state_context=power_state_context,
            time_origin_scope=time_origin_scope,
            driver_demand_scope=driver_demand_scope,
            objective=objective,
            source=source,
            created_at=created_at or _now(),
            supersedes_intent_id=(previous.intent_id if previous is not None else None),
            typed_interpretation_provenance=typed_interpretation_provenance,
        )
        connection.execute(
            """
            INSERT INTO engineering_driver_intents(
              intent_id, intent_sha256, case_id, intent_revision,
              supersedes_intent_id, created_at, intent_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                intent.intent_id,
                intent.intent_sha256,
                intent.case_id,
                intent.intent_revision,
                intent.supersedes_intent_id,
                intent.created_at.isoformat(),
                intent.model_dump_json(),
            ),
        )
        return intent

    def append_driver_intent(self, **values: Any) -> DriverIntent:
        connection = initialize_database(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            intent = self.append_driver_intent_in_transaction(connection, **values)
            connection.commit()
            return intent
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def current_driver_intent(self, case_id: str) -> DriverIntent | None:
        connection = initialize_database(self.db_path)
        try:
            row = connection.execute(
                """
                SELECT * FROM engineering_driver_intents
                WHERE case_id = ? ORDER BY intent_revision DESC LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                return None
            try:
                intent = DriverIntent.model_validate_json(row["intent_json"])
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise EngineeringCaseIntegrityError(
                    "Stored DriverIntent is unreadable or corrupt."
                ) from exc
            if (
                intent.intent_id != row["intent_id"]
                or intent.intent_sha256 != row["intent_sha256"]
                or intent.case_id != row["case_id"]
                or intent.intent_revision != row["intent_revision"]
                or intent.supersedes_intent_id != row["supersedes_intent_id"]
                or intent.created_at.isoformat() != row["created_at"]
            ):
                raise EngineeringCaseIntegrityError(
                    "Stored DriverIntent columns and payload disagree."
                )
            return intent
        finally:
            connection.close()


__all__ = ["EngineeringCaseIntegrityError", "EngineeringCaseRepository"]
