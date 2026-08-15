"""Append-only, integrity-checked persistence for P33 experience facts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.engineering_learning import (
    EngineeringExperienceContext,
    EngineeringExperienceRecord,
    ProblemFingerprint,
)
from racelab_engine.storage.db import initialize_database


_STREAM_ID = "p33.engineering-experience.v1"
LEARNING_CAPTURE_INTEGRITY_BLOCKER = (
    "P33 learning capture was blocked because engineering history failed integrity "
    "verification; no experience was appended."
)


class EngineeringLearningIntegrityError(ValueError):
    """Raised when persisted P33 history cannot be trusted."""


@dataclass(frozen=True)
class EngineeringLearningStreamState:
    record_count: int
    head_sha256: str | None
    history_revision: str


@dataclass(frozen=True)
class EngineeringExperienceQueryResult:
    records: tuple[EngineeringExperienceRecord, ...]
    blockers: tuple[str, ...]
    stream_state: EngineeringLearningStreamState


def _history_revision(record_count: int, head_sha256: str | None) -> str:
    return canonical_json_sha256(
        {
            "schema_version": _STREAM_ID,
            "record_count": record_count,
            "head_sha256": head_sha256,
        }
    )


def _indexed_identity(record: EngineeringExperienceRecord) -> dict[str, object]:
    context = record.context
    return {
        "experience_id": record.experience_id,
        "experience_sha256": record.experience_sha256,
        "source_identity_sha256": record.source_identity_sha256,
        "source_kind": record.source_kind,
        "created_at": record.created_at.isoformat(),
        "context_sha256": context.context_sha256,
        "run_id": context.run_id,
        "session_id": context.session_id,
        "driver_id": context.driver_id,
        "car_path": context.car_path,
        "car_version": context.car_version,
        "iracing_build": context.iracing_build,
        "track": context.track,
        "track_configuration": context.track_configuration,
        "package_type": context.package_type,
        "setup_family": context.setup_family,
        "setup_snapshot_sha256": context.setup_snapshot_sha256,
        "objective": context.objective,
        "phase": context.phase,
        "physical_region": context.physical_region,
        "problem_sha256": record.problem.problem_sha256,
        "source_investigation_id": record.source_investigation_id,
        "source_workflow_id": record.source_workflow_id,
    }


def _row_indexed_identity(row: sqlite3.Row) -> dict[str, object]:
    return {
        key: row[key]
        for key in (
            "experience_id",
            "experience_sha256",
            "source_identity_sha256",
            "source_kind",
            "created_at",
            "context_sha256",
            "run_id",
            "session_id",
            "driver_id",
            "car_path",
            "car_version",
            "iracing_build",
            "track",
            "track_configuration",
            "package_type",
            "setup_family",
            "setup_snapshot_sha256",
            "objective",
            "phase",
            "physical_region",
            "problem_sha256",
            "source_investigation_id",
            "source_workflow_id",
        )
    }


def _entry_sha256(
    sequence: int,
    previous_entry_sha256: str | None,
    indexed_identity: dict[str, object],
) -> str:
    return canonical_json_sha256(
        {
            "schema_version": _STREAM_ID,
            "sequence": sequence,
            "previous_entry_sha256": previous_entry_sha256,
            "indexed_identity": indexed_identity,
        }
    )


class EngineeringLearningRepository:
    """One immutable P33 ledger with bounded, index-first retrieval."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    @staticmethod
    def _stream_state(
        connection: sqlite3.Connection,
        *,
        validate_chain: bool,
        validate_payloads: bool = True,
    ) -> EngineeringLearningStreamState:
        head = connection.execute(
            "SELECT schema_version, record_count, head_sha256 "
            "FROM engineering_experience_stream_head WHERE stream_id = ?",
            (_STREAM_ID,),
        ).fetchone()
        if head is None or head["schema_version"] != _STREAM_ID:
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience stream head is missing or invalid"
            )
        raw_record_count = head["record_count"]
        if type(raw_record_count) is not int:
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience stream count is corrupt"
            )
        record_count = raw_record_count
        head_sha256 = head["head_sha256"]
        if head_sha256 is not None and (
            not isinstance(head_sha256, str)
            or len(head_sha256) != 64
            or any(character not in "0123456789abcdef" for character in head_sha256)
        ):
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience stream digest is corrupt"
            )
        if record_count < 0 or (record_count == 0) != (head_sha256 is None):
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience stream head is corrupt"
            )
        physical = connection.execute(
            "SELECT COUNT(*) AS row_count, MIN(sequence) AS first_sequence, "
            "MAX(sequence) AS last_sequence FROM engineering_experiences"
        ).fetchone()
        if (
            int(physical["row_count"]) != record_count
            or (record_count > 0 and int(physical["first_sequence"]) != 1)
            or (record_count > 0 and int(physical["last_sequence"]) != record_count)
        ):
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience stream contains a deleted or reordered row"
            )
        tail = connection.execute(
            "SELECT sequence, entry_sha256 FROM engineering_experiences "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if record_count == 0:
            if tail is not None:
                raise EngineeringLearningIntegrityError(
                    "P33 engineering-experience stream has an unbound tail"
                )
        elif (
            tail is None
            or int(tail["sequence"]) != record_count
            or tail["entry_sha256"] != head_sha256
        ):
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience stream tail is corrupt"
            )
        if validate_chain:
            rows = connection.execute(
                "SELECT * FROM engineering_experiences ORDER BY sequence"
            ).fetchall()
            previous: str | None = None
            for expected, row in enumerate(rows, start=1):
                if int(row["sequence"]) != expected:
                    raise EngineeringLearningIntegrityError(
                        "P33 engineering-experience sequence is corrupt"
                    )
                if row["previous_entry_sha256"] != previous:
                    raise EngineeringLearningIntegrityError(
                        "P33 engineering-experience chain link is corrupt"
                    )
                expected_entry = _entry_sha256(
                    expected,
                    previous,
                    _row_indexed_identity(row),
                )
                if row["entry_sha256"] != expected_entry:
                    raise EngineeringLearningIntegrityError(
                        "P33 engineering-experience indexed identity is corrupt"
                    )
                # Mutation preflights may validate the complete append-only
                # sequence/link/index chain without parsing unrelated payloads.
                # Exact retrieval/replay still validates every selected row,
                # and explicit maintenance audits keep payload validation on.
                if validate_payloads:
                    EngineeringLearningRepository._validate_row(row)
                previous = expected_entry
            if len(rows) != record_count or previous != head_sha256:
                raise EngineeringLearningIntegrityError(
                    "P33 engineering-experience stream tail is corrupt"
                )
        return EngineeringLearningStreamState(
            record_count=record_count,
            head_sha256=head_sha256,
            history_revision=_history_revision(record_count, head_sha256),
        )

    def stream_state(
        self,
        *,
        connection: sqlite3.Connection | None = None,
        validate_chain: bool = False,
        validate_payloads: bool = True,
    ) -> EngineeringLearningStreamState:
        owns_connection = connection is None
        active = connection or initialize_database(self.db_path)
        try:
            return self._stream_state(
                active,
                validate_chain=validate_chain,
                validate_payloads=validate_payloads,
            )
        finally:
            if owns_connection:
                active.close()

    def stream_revision(
        self, *, connection: sqlite3.Connection | None = None
    ) -> str:
        return self.stream_state(connection=connection).history_revision

    @staticmethod
    def append_experience_in_transaction(
        connection: sqlite3.Connection,
        record: EngineeringExperienceRecord,
    ) -> EngineeringLearningStreamState:
        """Append using a caller-owned transaction without commit or rollback."""

        encoded = record.model_dump_json()
        existing = connection.execute(
            "SELECT * FROM engineering_experiences "
            "WHERE source_identity_sha256 = ? OR experience_id = ?",
            (record.source_identity_sha256, record.experience_id),
        ).fetchone()
        if existing is not None:
            EngineeringLearningRepository._validate_row(existing)
            if existing["record_json"] != encoded:
                raise EngineeringLearningIntegrityError(
                    "P33 source identity already owns different experience data"
                )
            return EngineeringLearningRepository._stream_state(
                connection, validate_chain=False
            )

        state = EngineeringLearningRepository._stream_state(
            connection, validate_chain=False
        )
        sequence = state.record_count + 1
        indexed = _indexed_identity(record)
        entry_sha256 = _entry_sha256(sequence, state.head_sha256, indexed)
        connection.execute(
            """
            INSERT INTO engineering_experiences (
              sequence, experience_id, experience_sha256,
              source_identity_sha256, previous_entry_sha256, entry_sha256,
              source_kind, created_at, context_sha256, run_id, session_id,
              driver_id, car_path, car_version, iracing_build, track,
              track_configuration, package_type, setup_family,
              setup_snapshot_sha256, objective, phase, physical_region,
              problem_sha256, source_investigation_id, source_workflow_id,
              record_json
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                sequence,
                record.experience_id,
                record.experience_sha256,
                record.source_identity_sha256,
                state.head_sha256,
                entry_sha256,
                record.source_kind,
                record.created_at.isoformat(),
                record.context.context_sha256,
                record.context.run_id,
                record.context.session_id,
                record.context.driver_id,
                record.context.car_path,
                record.context.car_version,
                record.context.iracing_build,
                record.context.track,
                record.context.track_configuration,
                record.context.package_type,
                record.context.setup_family,
                record.context.setup_snapshot_sha256,
                record.context.objective,
                record.context.phase,
                record.context.physical_region,
                record.problem.problem_sha256,
                record.source_investigation_id,
                record.source_workflow_id,
                encoded,
            ),
        )
        updated = connection.execute(
            """
            UPDATE engineering_experience_stream_head
            SET record_count = ?, head_sha256 = ?
            WHERE stream_id = ? AND record_count = ?
              AND ((head_sha256 IS NULL AND ? IS NULL) OR head_sha256 = ?)
            """,
            (
                sequence,
                entry_sha256,
                _STREAM_ID,
                state.record_count,
                state.head_sha256,
                state.head_sha256,
            ),
        )
        if updated.rowcount != 1:
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience stream head changed during append"
            )
        return EngineeringLearningStreamState(
            record_count=sequence,
            head_sha256=entry_sha256,
            history_revision=_history_revision(sequence, entry_sha256),
        )

    _append_experience = append_experience_in_transaction

    def append_experience(
        self,
        record: EngineeringExperienceRecord,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> EngineeringLearningStreamState:
        if connection is not None:
            return self.append_experience_in_transaction(connection, record)
        active = initialize_database(self.db_path)
        try:
            active.execute("BEGIN IMMEDIATE")
            state = self.append_experience_in_transaction(active, record)
            active.commit()
            return state
        except Exception:
            active.rollback()
            raise
        finally:
            active.close()

    @staticmethod
    def _validate_row(row: sqlite3.Row) -> EngineeringExperienceRecord:
        expected_entry = _entry_sha256(
            int(row["sequence"]),
            row["previous_entry_sha256"],
            _row_indexed_identity(row),
        )
        if row["entry_sha256"] != expected_entry:
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience entry identity is corrupt"
            )
        try:
            record = EngineeringExperienceRecord.model_validate_json(
                row["record_json"]
            )
        except (TypeError, ValueError) as exc:
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience payload is corrupt"
            ) from exc
        if _indexed_identity(record) != _row_indexed_identity(row):
            raise EngineeringLearningIntegrityError(
                "P33 engineering-experience row identity is corrupt"
            )
        return record

    def query_relevant(
        self,
        context: EngineeringExperienceContext,
        *,
        problem: ProblemFingerprint | None = None,
        limit: int = 128,
        connection: sqlite3.Connection | None = None,
    ) -> EngineeringExperienceQueryResult:
        if limit < 1 or limit > 512:
            raise ValueError("P33 history limit must be between 1 and 512")
        owns_connection = connection is None
        active = connection or initialize_database(self.db_path)
        try:
            # GET projection reads verify one bounded index aggregate, the
            # head/tail, and every selected row. A full-chain payload audit
            # remains explicitly available through
            # ``stream_state(validate_chain=True)`` for maintenance and hostile
            # validation, never as a retrieval side effect.
            state = self._stream_state(active, validate_chain=False)
            branch_limit = min(limit, 128)
            branches: list[tuple[str, tuple[object, ...]]] = [
                (
                    "context_sha256 = ? AND objective = ? AND phase = ?",
                    (context.context_sha256, context.objective, context.phase),
                ),
                (
                    "car_path = ? AND car_version = ? AND iracing_build = ? "
                    "AND track = ? AND track_configuration = ? AND phase = ?",
                    (
                        context.car_path,
                        context.car_version,
                        context.iracing_build,
                        context.track,
                        context.track_configuration,
                        context.phase,
                    ),
                ),
            ]
            if problem is not None:
                branches.append(
                    ("problem_sha256 = ?", (problem.problem_sha256,))
                )
            if context.driver_id is not None:
                branches.append(
                    (
                        "driver_id = ? AND car_path = ? AND car_version = ? "
                        "AND iracing_build = ? AND phase = ?",
                        (
                            context.driver_id,
                            context.car_path,
                            context.car_version,
                            context.iracing_build,
                            context.phase,
                        ),
                    )
                )
            selected: dict[str, sqlite3.Row] = {}
            for predicate, parameters in branches:
                rows = active.execute(
                    "SELECT * FROM engineering_experiences WHERE "
                    f"{predicate} ORDER BY created_at DESC, experience_id LIMIT ?",
                    (*parameters, branch_limit),
                ).fetchall()
                for row in rows:
                    selected.setdefault(row["experience_id"], row)
            ordered = sorted(
                selected.values(),
                key=lambda row: (row["created_at"], row["experience_id"]),
                reverse=True,
            )[:limit]
            records: list[EngineeringExperienceRecord] = []
            blockers: list[str] = []
            for row in ordered:
                try:
                    records.append(self._validate_row(row))
                except EngineeringLearningIntegrityError as exc:
                    blockers.append(
                        f"Experience {row['experience_id']} withheld: {exc}"
                    )
            return EngineeringExperienceQueryResult(
                records=tuple(records),
                blockers=tuple(blockers),
                stream_state=state,
            )
        finally:
            if owns_connection:
                active.close()


__all__ = [
    "EngineeringExperienceQueryResult",
    "EngineeringLearningIntegrityError",
    "EngineeringLearningRepository",
    "EngineeringLearningStreamState",
    "LEARNING_CAPTURE_INTEGRITY_BLOCKER",
]
