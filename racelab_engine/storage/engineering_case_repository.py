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

    @classmethod
    def _validated_head_revision(
        cls, connection: sqlite3.Connection, head: sqlite3.Row
    ) -> EngineeringCaseRevision:
        rows = connection.execute(
            """
            SELECT * FROM engineering_case_revisions
            WHERE case_id = ? ORDER BY case_revision ASC
            """,
            (head["case_id"],),
        ).fetchall()
        if not rows:
            raise EngineeringCaseIntegrityError(
                "Engineering Case head points to a missing revision."
            )
        revisions = tuple(cls._revision_from_row(row) for row in rows)
        for expected_revision, revision in enumerate(revisions, start=1):
            previous = (
                revisions[expected_revision - 2] if expected_revision > 1 else None
            )
            if (
                revision.case_revision != expected_revision
                or revision.previous_case_sha256
                != (previous.case_sha256 if previous is not None else None)
            ):
                raise EngineeringCaseIntegrityError(
                    "Engineering Case revision hash chain is incomplete or reordered."
                )
        revision = revisions[-1]
        if (
            len(revisions) != int(head["current_revision"])
            or revision.case_revision != int(head["current_revision"])
            or revision.case_sha256 != head["current_case_sha256"]
            or revision.case.run_id != head["run_id"]
            or revision.case.session_id != head["session_id"]
        ):
            raise EngineeringCaseIntegrityError(
                "Engineering Case head identity and current revision disagree."
            )
        return revision

    @staticmethod
    def _intent_from_row(row: sqlite3.Row) -> DriverIntent:
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

    @classmethod
    def _intent_history_in_transaction(
        cls, connection: sqlite3.Connection, case_id: str
    ) -> tuple[DriverIntent, ...]:
        rows = connection.execute(
            """
            SELECT * FROM engineering_driver_intents
            WHERE case_id = ? ORDER BY intent_revision ASC
            """,
            (case_id,),
        ).fetchall()
        intents = tuple(cls._intent_from_row(row) for row in rows)
        for index, intent in enumerate(intents, start=1):
            previous = intents[index - 2] if index > 1 else None
            if intent.intent_revision != index or intent.supersedes_intent_id != (
                previous.intent_id if previous is not None else None
            ):
                raise EngineeringCaseIntegrityError(
                    "DriverIntent revision chain is incomplete or reordered."
                )
        return intents

    @classmethod
    def finalize_case_in_transaction(
        cls,
        connection: sqlite3.Connection,
        case: CanonicalEngineeringCase,
        *,
        change_category: CaseChangeCategory = "rebuild",
        created_at: datetime | None = None,
    ) -> EngineeringCaseRevision:
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
        current_revision = (
            None if head is None else cls._validated_head_revision(connection, head)
        )
        if current_revision is not None and (
            current_revision.case_sha256 == case.case_sha256
        ):
            return current_revision

        revision_number = 1 if head is None else int(head["current_revision"]) + 1
        previous_sha = (
            None if current_revision is None else current_revision.case_sha256
        )
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
            revision = self.finalize_case_in_transaction(
                connection,
                case,
                change_category=change_category,
                created_at=created_at,
            )
            connection.commit()
            return revision
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @classmethod
    def current_for_scope_in_transaction(
        cls, connection: sqlite3.Connection, run_id: str, session_id: str
    ) -> EngineeringCaseRevision | None:
        head = connection.execute(
            "SELECT * FROM engineering_cases WHERE run_id = ? AND session_id = ?",
            (run_id, session_id),
        ).fetchone()
        return None if head is None else cls._validated_head_revision(connection, head)

    def current_for_scope(
        self, run_id: str, session_id: str
    ) -> EngineeringCaseRevision | None:
        connection = initialize_database(self.db_path)
        try:
            head = connection.execute(
                """
                SELECT * FROM engineering_cases
                WHERE run_id = ? AND session_id = ?
                """,
                (run_id, session_id),
            ).fetchone()
            return (
                None
                if head is None
                else self._validated_head_revision(connection, head)
            )
        finally:
            connection.close()

    def current(self, case_id: str) -> EngineeringCaseRevision | None:
        connection = initialize_database(self.db_path)
        try:
            head = connection.execute(
                "SELECT * FROM engineering_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            return (
                None
                if head is None
                else self._validated_head_revision(connection, head)
            )
        finally:
            connection.close()

    def history(
        self, case_id: str, *, limit: int = 25
    ) -> tuple[EngineeringCaseRevisionSummary, ...]:
        bounded = max(1, min(limit, 100))
        connection = initialize_database(self.db_path)
        try:
            head = connection.execute(
                "SELECT * FROM engineering_cases WHERE case_id = ?", (case_id,)
            ).fetchone()
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
            if head is not None:
                current = self._validated_head_revision(connection, head)
                if not revisions or revisions[0] != current:
                    raise EngineeringCaseIntegrityError(
                        "Engineering Case history does not begin at the current head."
                    )
            elif revisions:
                raise EngineeringCaseIntegrityError(
                    "Engineering Case revisions exist without a lifecycle head."
                )
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
        history = EngineeringCaseRepository._intent_history_in_transaction(
            connection, case_id
        )
        previous = history[-1] if history else None
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
            return self.current_driver_intent_in_transaction(connection, case_id)
        finally:
            connection.close()

    @classmethod
    def current_driver_intent_in_transaction(
        cls, connection: sqlite3.Connection, case_id: str
    ) -> DriverIntent | None:
        history = cls._intent_history_in_transaction(connection, case_id)
        return history[-1] if history else None


__all__ = ["EngineeringCaseIntegrityError", "EngineeringCaseRepository"]
