"""Append-only, integrity-checked persistence for P34 investigation evidence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, cast

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.investigation_adaptation import (
    DiscriminatorOutcome,
    InvestigationNegativeTransfer,
    InvestigationOutcomeCertificate,
    InvestigationOutcomeFollowup,
    InvestigationPolicy,
    InvestigationPolicyEvaluation,
    P34ActivationDecision,
    P34InvestigationActivationProtocol,
    P34NegativeControlResult,
    PairedInvestigationComparison,
    PairedInvestigationDecision,
)
from racelab_engine.storage.db import connect_read_only, initialize_database


_STREAM_ID = "p34.investigation-adaptation.v1"
MAX_EVALUATION_RECORDS = 10_000
AdaptationRecordKind = Literal[
    "policy",
    "paired_decision",
    "outcome_certificate",
    "outcome_followup",
    "paired_comparison",
    "discriminator_outcome",
    "negative_transfer",
    "negative_control_result",
    "activation_protocol",
    "policy_evaluation",
    "activation_decision",
]
AdaptationRecord: TypeAlias = (
    InvestigationPolicy
    | PairedInvestigationDecision
    | InvestigationOutcomeCertificate
    | InvestigationOutcomeFollowup
    | PairedInvestigationComparison
    | DiscriminatorOutcome
    | InvestigationNegativeTransfer
    | P34NegativeControlResult
    | P34InvestigationActivationProtocol
    | InvestigationPolicyEvaluation
    | P34ActivationDecision
)


class InvestigationAdaptationIntegrityError(ValueError):
    """Raised when relevant persisted P34 truth cannot be verified."""


@dataclass(frozen=True)
class InvestigationAdaptationStreamState:
    record_count: int
    head_sha256: str | None
    ledger_revision: str


@dataclass(frozen=True)
class InvestigationAdaptationQueryResult:
    records: tuple[AdaptationRecord, ...]
    blockers: tuple[str, ...]
    stream_state: InvestigationAdaptationStreamState


@dataclass(frozen=True)
class _RecordMetadata:
    record_id: str
    record_sha256: str
    record_kind: AdaptationRecordKind
    recorded_at: str
    investigation_id: str | None
    workspace_revision: str | None
    step_number: int | None
    policy_id: str | None
    protocol_id: str | None


_MODEL_BY_KIND: dict[AdaptationRecordKind, type[AdaptationRecord]] = {
    "policy": InvestigationPolicy,
    "paired_decision": PairedInvestigationDecision,
    "outcome_certificate": InvestigationOutcomeCertificate,
    "outcome_followup": InvestigationOutcomeFollowup,
    "paired_comparison": PairedInvestigationComparison,
    "discriminator_outcome": DiscriminatorOutcome,
    "negative_transfer": InvestigationNegativeTransfer,
    "negative_control_result": P34NegativeControlResult,
    "activation_protocol": P34InvestigationActivationProtocol,
    "policy_evaluation": InvestigationPolicyEvaluation,
    "activation_decision": P34ActivationDecision,
}


def _ledger_revision(record_count: int, head_sha256: str | None) -> str:
    return canonical_json_sha256(
        {
            "schema_version": _STREAM_ID,
            "record_count": record_count,
            "head_sha256": head_sha256,
        }
    )


def _metadata(record: AdaptationRecord) -> _RecordMetadata:
    if isinstance(record, InvestigationPolicy):
        return _RecordMetadata(
            record.policy_id,
            record.policy_sha256,
            "policy",
            record.created_at.isoformat(),
            None,
            None,
            None,
            record.policy_id,
            None,
        )
    if isinstance(record, PairedInvestigationDecision):
        return _RecordMetadata(
            record.pair_id,
            record.pair_sha256,
            "paired_decision",
            record.decision_frozen_at.isoformat(),
            record.investigation_id,
            record.workspace_revision,
            record.step_number,
            record.baseline_policy_id,
            record.activation_protocol_id,
        )
    if isinstance(record, InvestigationOutcomeCertificate):
        return _RecordMetadata(
            record.certificate_id,
            record.certificate_sha256,
            "outcome_certificate",
            record.certified_at.isoformat(),
            record.investigation_id,
            record.ending_workspace_revision,
            None,
            None,
            record.activation_protocol_id,
        )
    if isinstance(record, InvestigationOutcomeFollowup):
        return _RecordMetadata(
            record.followup_id,
            record.followup_sha256,
            "outcome_followup",
            record.observed_at.isoformat(),
            record.investigation_id,
            None,
            None,
            None,
            record.activation_protocol_id,
        )
    if isinstance(record, PairedInvestigationComparison):
        return _RecordMetadata(
            record.comparison_id,
            record.comparison_sha256,
            "paired_comparison",
            record.compared_at.isoformat(),
            record.investigation_id,
            None,
            None,
            None,
            record.activation_protocol_id,
        )
    if isinstance(record, DiscriminatorOutcome):
        return _RecordMetadata(
            record.outcome_id,
            record.outcome_sha256,
            "discriminator_outcome",
            record.evaluated_at.isoformat(),
            record.investigation_id,
            record.workspace_revision,
            None,
            None,
            record.activation_protocol_id,
        )
    if isinstance(record, InvestigationNegativeTransfer):
        return _RecordMetadata(
            record.transfer_id,
            record.transfer_sha256,
            "negative_transfer",
            record.detected_at.isoformat(),
            record.investigation_id,
            None,
            None,
            None,
            record.activation_protocol_id,
        )
    if isinstance(record, P34NegativeControlResult):
        return _RecordMetadata(
            record.result_id,
            record.result_sha256,
            "negative_control_result",
            record.evaluated_at.isoformat(),
            record.investigation_id,
            None,
            None,
            None,
            record.protocol_id,
        )
    if isinstance(record, P34InvestigationActivationProtocol):
        return _RecordMetadata(
            record.protocol_id,
            record.protocol_sha256,
            "activation_protocol",
            record.frozen_at.isoformat(),
            None,
            None,
            None,
            record.baseline_policy_id,
            record.protocol_id,
        )
    if isinstance(record, InvestigationPolicyEvaluation):
        return _RecordMetadata(
            record.evaluation_id,
            record.evaluation_sha256,
            "policy_evaluation",
            record.evaluated_at.isoformat(),
            None,
            None,
            None,
            record.baseline_policy_id,
            record.protocol_id,
        )
    if isinstance(record, P34ActivationDecision):
        return _RecordMetadata(
            record.decision_id,
            record.decision_sha256,
            "activation_decision",
            record.decided_at.isoformat(),
            None,
            None,
            None,
            None,
            record.protocol_id,
        )
    raise TypeError(f"Unsupported P34 adaptation record: {type(record)!r}")


def _indexed_identity(metadata: _RecordMetadata) -> dict[str, object]:
    return {
        "record_id": metadata.record_id,
        "record_sha256": metadata.record_sha256,
        "record_kind": metadata.record_kind,
        "recorded_at": metadata.recorded_at,
        "investigation_id": metadata.investigation_id,
        "workspace_revision": metadata.workspace_revision,
        "step_number": metadata.step_number,
        "policy_id": metadata.policy_id,
        "protocol_id": metadata.protocol_id,
    }


def _row_indexed_identity(row: sqlite3.Row) -> dict[str, object]:
    return {
        key: row[key]
        for key in (
            "record_id",
            "record_sha256",
            "record_kind",
            "recorded_at",
            "investigation_id",
            "workspace_revision",
            "step_number",
            "policy_id",
            "protocol_id",
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


class InvestigationAdaptationRepository:
    """One immutable P34 stream with bounded index-first retrieval."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = db_path

    @staticmethod
    def _stream_state(
        connection: sqlite3.Connection,
        *,
        validate_chain: bool,
        validate_payloads: bool = True,
    ) -> InvestigationAdaptationStreamState:
        head = connection.execute(
            "SELECT schema_version, record_count, head_sha256 "
            "FROM investigation_adaptation_stream_head WHERE stream_id = ?",
            (_STREAM_ID,),
        ).fetchone()
        if head is None or head["schema_version"] != _STREAM_ID:
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation stream head is missing or invalid"
            )
        raw_count = head["record_count"]
        if type(raw_count) is not int or raw_count < 0:
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation stream count is corrupt"
            )
        count = raw_count
        digest = head["head_sha256"]
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation stream digest is corrupt"
            )
        if (count == 0) != (digest is None):
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation stream head is corrupt"
            )
        first = connection.execute(
            "SELECT sequence FROM investigation_adaptation_records "
            "ORDER BY sequence LIMIT 1"
        ).fetchone()
        tail = connection.execute(
            "SELECT sequence, entry_sha256 FROM investigation_adaptation_records "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if count == 0:
            if first is not None or tail is not None:
                raise InvestigationAdaptationIntegrityError(
                    "P34 investigation-adaptation stream has an unbound tail"
                )
        elif (
            first is None
            or int(first["sequence"]) != 1
            or
            tail is None
            or int(tail["sequence"]) != count
            or tail["entry_sha256"] != digest
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation stream tail is corrupt"
            )
        if validate_chain:
            rows = connection.execute(
                "SELECT * FROM investigation_adaptation_records ORDER BY sequence"
            ).fetchall()
            if len(rows) != count:
                raise InvestigationAdaptationIntegrityError(
                    "P34 investigation-adaptation stream contains a deleted row"
                )
            previous: str | None = None
            for expected_sequence, row in enumerate(rows, start=1):
                if row["sequence"] != expected_sequence:
                    raise InvestigationAdaptationIntegrityError(
                        "P34 investigation-adaptation sequence is corrupt"
                    )
                if row["previous_entry_sha256"] != previous:
                    raise InvestigationAdaptationIntegrityError(
                        "P34 investigation-adaptation chain link is corrupt"
                    )
                expected_entry = _entry_sha256(
                    expected_sequence,
                    previous,
                    _row_indexed_identity(row),
                )
                if row["entry_sha256"] != expected_entry:
                    raise InvestigationAdaptationIntegrityError(
                        "P34 investigation-adaptation indexed identity is corrupt"
                    )
                if validate_payloads:
                    self_record = InvestigationAdaptationRepository._validate_row(row)
                    if _metadata(self_record).record_sha256 != row["record_sha256"]:
                        raise InvestigationAdaptationIntegrityError(
                            "P34 investigation-adaptation payload digest is corrupt"
                        )
                previous = expected_entry
            if previous != digest or len(rows) != count:
                raise InvestigationAdaptationIntegrityError(
                    "P34 investigation-adaptation stream tail is corrupt"
                )
        return InvestigationAdaptationStreamState(
            record_count=count,
            head_sha256=digest,
            ledger_revision=_ledger_revision(count, digest),
        )

    def stream_state(
        self,
        *,
        connection: sqlite3.Connection | None = None,
        validate_chain: bool = False,
        validate_payloads: bool = True,
    ) -> InvestigationAdaptationStreamState:
        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            return self._stream_state(
                active,
                validate_chain=validate_chain,
                validate_payloads=validate_payloads,
            )
        finally:
            if owns_connection:
                active.close()

    @staticmethod
    def _validate_row(row: sqlite3.Row) -> AdaptationRecord:
        kind = row["record_kind"]
        model = _MODEL_BY_KIND.get(kind)
        if model is None:
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation record kind is unknown"
            )
        expected_entry = _entry_sha256(
            int(row["sequence"]),
            row["previous_entry_sha256"],
            _row_indexed_identity(row),
        )
        if row["entry_sha256"] != expected_entry:
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation entry identity is corrupt"
            )
        try:
            record = model.model_validate_json(row["record_json"])
        except (TypeError, ValueError) as exc:
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation payload is corrupt"
            ) from exc
        if _indexed_identity(_metadata(record)) != _row_indexed_identity(row):
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation indexed payload identity is corrupt"
            )
        return record

    @classmethod
    def append_record_in_transaction(
        cls,
        connection: sqlite3.Connection,
        record: AdaptationRecord,
    ) -> InvestigationAdaptationStreamState:
        metadata = _metadata(record)
        encoded = record.model_dump_json()
        existing = connection.execute(
            "SELECT * FROM investigation_adaptation_records "
            "WHERE record_id = ? OR record_sha256 = ?",
            (metadata.record_id, metadata.record_sha256),
        ).fetchone()
        if existing is not None:
            validated = cls._validate_row(existing)
            if (
                _metadata(validated) != metadata
                or existing["record_json"] != encoded
            ):
                raise InvestigationAdaptationIntegrityError(
                    "P34 immutable record identity already owns different evidence"
                )
            return cls._stream_state(connection, validate_chain=False)
        if metadata.record_kind == "paired_decision":
            source = connection.execute(
                "SELECT * FROM investigation_adaptation_records "
                "WHERE record_kind = 'paired_decision' AND investigation_id = ? "
                "AND workspace_revision = ? AND step_number = ?",
                (
                    metadata.investigation_id,
                    metadata.workspace_revision,
                    metadata.step_number,
                ),
            ).fetchone()
            if source is not None:
                cls._validate_row(source)
                raise InvestigationAdaptationIntegrityError(
                    "P34 investigation revision already owns a different frozen pair"
                )
        if metadata.record_kind == "outcome_certificate":
            source = connection.execute(
                "SELECT * FROM investigation_adaptation_records "
                "WHERE record_kind = 'outcome_certificate' AND investigation_id = ?",
                (metadata.investigation_id,),
            ).fetchone()
            if source is not None:
                cls._validate_row(source)
                raise InvestigationAdaptationIntegrityError(
                    "P34 investigation already owns a different outcome certificate"
                )
        if metadata.record_kind == "paired_comparison":
            source = connection.execute(
                "SELECT * FROM investigation_adaptation_records "
                "WHERE record_kind = 'paired_comparison' AND investigation_id = ?",
                (metadata.investigation_id,),
            ).fetchone()
            if source is not None:
                cls._validate_row(source)
                raise InvestigationAdaptationIntegrityError(
                    "P34 investigation already owns a different paired comparison"
                )
        state = cls._stream_state(connection, validate_chain=False)
        sequence = state.record_count + 1
        entry_sha256 = _entry_sha256(
            sequence,
            state.head_sha256,
            _indexed_identity(metadata),
        )
        connection.execute(
            """
            INSERT INTO investigation_adaptation_records (
              sequence, record_id, record_sha256, record_kind,
              previous_entry_sha256, entry_sha256, recorded_at,
              investigation_id, workspace_revision, step_number,
              policy_id, protocol_id, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sequence,
                metadata.record_id,
                metadata.record_sha256,
                metadata.record_kind,
                state.head_sha256,
                entry_sha256,
                metadata.recorded_at,
                metadata.investigation_id,
                metadata.workspace_revision,
                metadata.step_number,
                metadata.policy_id,
                metadata.protocol_id,
                encoded,
            ),
        )
        updated = connection.execute(
            """
            UPDATE investigation_adaptation_stream_head
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
            raise InvestigationAdaptationIntegrityError(
                "P34 investigation-adaptation stream changed during append"
            )
        return InvestigationAdaptationStreamState(
            record_count=sequence,
            head_sha256=entry_sha256,
            ledger_revision=_ledger_revision(sequence, entry_sha256),
        )

    def append_record(
        self,
        record: AdaptationRecord,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> InvestigationAdaptationStreamState:
        if connection is not None:
            return self.append_record_in_transaction(connection, record)
        active = initialize_database(self.db_path)
        try:
            active.execute("BEGIN IMMEDIATE")
            state = self.append_record_in_transaction(active, record)
            active.commit()
            return state
        except Exception:
            active.rollback()
            raise
        finally:
            active.close()

    append_policy_in_transaction = append_record_in_transaction
    append_paired_decision_in_transaction = append_record_in_transaction
    append_outcome_in_transaction = append_record_in_transaction
    append_outcome_followup_in_transaction = append_record_in_transaction
    append_comparison_in_transaction = append_record_in_transaction
    append_discriminator_outcome_in_transaction = append_record_in_transaction
    append_negative_transfer_in_transaction = append_record_in_transaction
    append_negative_control_result_in_transaction = append_record_in_transaction
    append_evaluation_in_transaction = append_record_in_transaction
    append_activation_decision_in_transaction = append_record_in_transaction

    append_policy = append_record
    append_paired_decision = append_record
    append_outcome = append_record
    append_outcome_followup = append_record
    append_comparison = append_record
    append_discriminator_outcome = append_record
    append_negative_transfer = append_record
    append_negative_control_result = append_record
    append_evaluation = append_record
    append_activation_decision = append_record

    def query_records(
        self,
        *,
        record_kinds: tuple[AdaptationRecordKind, ...] | None = None,
        investigation_id: str | None = None,
        workspace_revision: str | None = None,
        protocol_id: str | None = None,
        max_sequence: int | None = None,
        limit: int = 512,
        connection: sqlite3.Connection | None = None,
    ) -> InvestigationAdaptationQueryResult:
        if limit < 1 or limit > MAX_EVALUATION_RECORDS:
            raise ValueError("P34 record limit must be between 1 and 10000")
        if record_kinds is not None:
            if not record_kinds or len(record_kinds) != len(set(record_kinds)):
                raise ValueError("P34 record-kind filters must be non-empty and unique")
            unknown = set(record_kinds) - set(_MODEL_BY_KIND)
            if unknown:
                raise ValueError("P34 record-kind filter is unknown")
        if max_sequence is not None and max_sequence < 1:
            raise ValueError("P34 maximum sequence must be positive")
        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            state = self._stream_state(active, validate_chain=False)
            predicates: list[str] = []
            parameters: list[object] = []
            if record_kinds is not None:
                placeholders = ",".join("?" for _ in record_kinds)
                predicates.append(f"record_kind IN ({placeholders})")
                parameters.extend(record_kinds)
            if investigation_id is not None:
                predicates.append("investigation_id = ?")
                parameters.append(investigation_id)
            if workspace_revision is not None:
                predicates.append("workspace_revision = ?")
                parameters.append(workspace_revision)
            if protocol_id is not None:
                predicates.append("protocol_id = ?")
                parameters.append(protocol_id)
            if max_sequence is not None:
                predicates.append("sequence <= ?")
                parameters.append(max_sequence)
            where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
            rows = active.execute(
                "SELECT * FROM investigation_adaptation_records "
                f"{where} ORDER BY sequence DESC LIMIT ?",
                (*parameters, limit),
            ).fetchall()
            records: list[AdaptationRecord] = []
            blockers: list[str] = []
            for row in rows:
                try:
                    records.append(self._validate_row(row))
                except InvestigationAdaptationIntegrityError as exc:
                    blockers.append(f"P34 record {row['record_id']} withheld: {exc}")
            return InvestigationAdaptationQueryResult(
                records=tuple(records),
                blockers=tuple(blockers),
                stream_state=state,
            )
        finally:
            if owns_connection:
                active.close()

    def get_paired_decision(
        self,
        pair_sha256: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> PairedInvestigationDecision | None:
        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            row = active.execute(
                "SELECT * FROM investigation_adaptation_records "
                "WHERE record_kind = 'paired_decision' AND record_sha256 = ?",
                (pair_sha256,),
            ).fetchone()
            if row is None:
                return None
            return cast(PairedInvestigationDecision, self._validate_row(row))
        finally:
            if owns_connection:
                active.close()

    def query_records_by_ids(
        self,
        record_ids: tuple[str, ...],
        *,
        max_sequence: int | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[AdaptationRecord, ...]:
        """Resolve a bounded exact parent set without scanning unrelated rows."""

        if len(record_ids) > MAX_EVALUATION_RECORDS:
            raise ValueError("P34 exact-parent query exceeds the 10000-record bound")
        if not record_ids:
            return ()
        if len(record_ids) != len(set(record_ids)) or any(not item for item in record_ids):
            raise ValueError("P34 exact-parent identities must be non-empty and unique")
        if max_sequence is not None and max_sequence < 1:
            raise ValueError("P34 maximum sequence must be positive")
        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            rows: list[sqlite3.Row] = []
            for offset in range(0, len(record_ids), 500):
                chunk = record_ids[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows.extend(
                    active.execute(
                        "SELECT * FROM investigation_adaptation_records "
                        f"WHERE record_id IN ({placeholders})"
                        + (" AND sequence <= ?" if max_sequence is not None else ""),
                        (*chunk, max_sequence)
                        if max_sequence is not None
                        else chunk,
                    ).fetchall()
                )
            by_id = {
                row["record_id"]: self._validate_row(row)
                for row in rows
            }
            return tuple(by_id[item] for item in record_ids if item in by_id)
        finally:
            if owns_connection:
                active.close()

    def latest_pair(
        self,
        investigation_id: str,
        workspace_revision: str | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> PairedInvestigationDecision | None:
        result = self.query_records(
            record_kinds=("paired_decision",),
            investigation_id=investigation_id,
            workspace_revision=workspace_revision,
            limit=1,
            connection=connection,
        )
        if result.blockers:
            raise InvestigationAdaptationIntegrityError(result.blockers[0])
        return cast(
            PairedInvestigationDecision | None,
            result.records[0] if result.records else None,
        )

    def query_pairs(
        self,
        *,
        limit: int = 512,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[PairedInvestigationDecision, ...]:
        result = self.query_records(
            record_kinds=("paired_decision",),
            limit=limit,
            connection=connection,
        )
        if result.blockers:
            raise InvestigationAdaptationIntegrityError(result.blockers[0])
        return cast(tuple[PairedInvestigationDecision, ...], result.records)

    def query_canonical_pairs(
        self,
        *,
        protocol_id: str,
        investigation_ids: tuple[str, ...] | None = None,
        max_sequence: int | None = None,
        limit: int = MAX_EVALUATION_RECORDS,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[PairedInvestigationDecision, ...]:
        """Return one preregistered canonical pair per investigation.

        Ranking is executed by indexed investigation identity in SQLite, so
        completed revisions do not consume the 10,000-investigation bound.
        Every selected payload is still fully content/chain validated.
        """

        if limit < 1 or limit > MAX_EVALUATION_RECORDS:
            raise ValueError("P34 pair limit must be between 1 and 10000")
        if max_sequence is not None and max_sequence < 1:
            raise ValueError("P34 maximum sequence must be positive")
        if investigation_ids is not None:
            if any(not item for item in investigation_ids) or len(
                investigation_ids
            ) != len(set(investigation_ids)):
                raise ValueError(
                    "P34 canonical-pair investigation IDs must be non-empty and unique"
                )
            if not investigation_ids:
                return ()
        encoded_investigations = (
            json.dumps(investigation_ids) if investigation_ids is not None else None
        )
        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            rows = active.execute(
                """
                WITH ranked AS (
                  SELECT records.*,
                    ROW_NUMBER() OVER (
                      PARTITION BY investigation_id
                      ORDER BY
                        CASE
                          WHEN json_extract(record_json, '$.baseline_decision.decision_kind') = 'inspect_tool'
                           AND json_extract(record_json, '$.memory_decision.decision_kind') = 'inspect_tool'
                           AND (
                             json_extract(record_json, '$.baseline_decision.decision_kind')
                               IS NOT json_extract(record_json, '$.memory_decision.decision_kind')
                             OR json_extract(record_json, '$.baseline_decision.action_id')
                               IS NOT json_extract(record_json, '$.memory_decision.action_id')
                             OR json_extract(record_json, '$.baseline_decision.priority_tier')
                               IS NOT json_extract(record_json, '$.memory_decision.priority_tier')
                             OR json_extract(record_json, '$.baseline_decision.safe_reorder_group')
                               IS NOT json_extract(record_json, '$.memory_decision.safe_reorder_group')
                             OR json_extract(record_json, '$.baseline_decision.selected_ordinal')
                               IS NOT json_extract(record_json, '$.memory_decision.selected_ordinal')
                           ) THEN 0
                          WHEN json_extract(record_json, '$.baseline_decision.decision_kind') = 'inspect_tool'
                           AND json_extract(record_json, '$.memory_decision.decision_kind') = 'inspect_tool'
                            THEN 1
                          ELSE 2
                        END,
                        step_number,
                        sequence,
                        record_id
                    ) AS canonical_rank
                  FROM investigation_adaptation_records AS records
                  WHERE record_kind = 'paired_decision' AND protocol_id = ?
                    AND (? IS NULL OR sequence <= ?)
                    AND (
                      ? IS NULL OR investigation_id IN (
                        SELECT value FROM json_each(?)
                      )
                    )
                )
                SELECT * FROM ranked
                WHERE canonical_rank = 1
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (
                    protocol_id,
                    max_sequence,
                    max_sequence,
                    encoded_investigations,
                    encoded_investigations,
                    limit,
                ),
            ).fetchall()
            return tuple(
                cast(PairedInvestigationDecision, self._validate_row(row))
                for row in rows
            )
        finally:
            if owns_connection:
                active.close()

    def query_pending_outcome_certificates(
        self,
        *,
        protocol_id: str,
        limit: int = 512,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[InvestigationOutcomeCertificate, ...]:
        """Return only exact-protocol certificates lacking a follow-up.

        This indexed anti-join is the restart recovery marker.  It avoids an
        unbounded controlled-workflow catalog scan on every Crew mutation.
        """

        if limit < 1 or limit > MAX_EVALUATION_RECORDS:
            raise ValueError("P34 pending-followup limit must be between 1 and 10000")
        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            rows = active.execute(
                "SELECT certificate.* "
                "FROM controlled_test_workflows AS workflow "
                "JOIN investigation_adaptation_records AS certificate "
                "ON certificate.record_kind = 'outcome_certificate' "
                "AND certificate.protocol_id = ? "
                "AND json_extract("
                "certificate.record_json, '$.created_workflow_ids[0]'"
                ") = workflow.workflow_id "
                "WHERE workflow.status = 'scored' "
                "AND NOT EXISTS ("
                "SELECT 1 FROM investigation_adaptation_records AS followup "
                "WHERE followup.record_kind = 'outcome_followup' "
                "AND followup.protocol_id = certificate.protocol_id "
                "AND followup.investigation_id = certificate.investigation_id "
                "AND json_extract(followup.record_json, '$.certificate_id') "
                "= certificate.record_id "
                "AND json_extract(followup.record_json, '$.certificate_sha256') "
                "= certificate.record_sha256 "
                "AND json_extract(followup.record_json, '$.source_workflow_id') "
                "= workflow.workflow_id"
                ") ORDER BY certificate.sequence LIMIT ?",
                (protocol_id, limit),
            ).fetchall()
            return tuple(
                cast(InvestigationOutcomeCertificate, self._validate_row(row))
                for row in rows
            )
        finally:
            if owns_connection:
                active.close()

    def get_outcome_certificate_for_workflow(
        self,
        *,
        protocol_id: str,
        workflow_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> InvestigationOutcomeCertificate | None:
        """Resolve one exact workflow parent without scanning the P34 cohort."""

        if not workflow_id:
            raise ValueError("P34 workflow identity must be non-empty")
        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            rows = active.execute(
                "SELECT * FROM investigation_adaptation_records "
                "WHERE record_kind = 'outcome_certificate' "
                "AND protocol_id = ? "
                "AND json_extract(record_json, '$.created_workflow_ids[0]') = ? "
                "ORDER BY sequence LIMIT 2",
                (protocol_id, workflow_id),
            ).fetchall()
            if len(rows) > 1:
                raise InvestigationAdaptationIntegrityError(
                    "P34 workflow is ambiguously bound to multiple investigations"
                )
            if not rows:
                return None
            return cast(InvestigationOutcomeCertificate, self._validate_row(rows[0]))
        finally:
            if owns_connection:
                active.close()

    def evaluation_capacity_overflow(
        self,
        *,
        protocol_id: str,
        record_kinds: tuple[AdaptationRecordKind, ...],
        max_sequence: int | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[str, ...]:
        """Fail closed when a bounded activation snapshot would omit evidence."""

        owns_connection = connection is None
        active = connection or connect_read_only(self.db_path)
        try:
            if max_sequence is not None and max_sequence < 1:
                raise ValueError("P34 maximum sequence must be positive")
            overflow: list[str] = []
            for kind in record_kinds:
                row = active.execute(
                    "SELECT 1 FROM investigation_adaptation_records "
                    "WHERE record_kind = ? AND protocol_id = ? "
                    "AND (? IS NULL OR sequence <= ?) LIMIT 1 OFFSET ?",
                    (
                        kind,
                        protocol_id,
                        max_sequence,
                        max_sequence,
                        MAX_EVALUATION_RECORDS,
                    ),
                ).fetchone()
                if row is not None:
                    overflow.append(kind)
            pair_row = active.execute(
                "SELECT 1 FROM ("
                "SELECT investigation_id FROM investigation_adaptation_records "
                "WHERE record_kind = 'paired_decision' AND protocol_id = ? "
                "AND (? IS NULL OR sequence <= ?) "
                "GROUP BY investigation_id LIMIT 1 OFFSET ?"
                ")",
                (
                    protocol_id,
                    max_sequence,
                    max_sequence,
                    MAX_EVALUATION_RECORDS,
                ),
            ).fetchone()
            if pair_row is not None:
                overflow.append("canonical_investigation")
            return tuple(overflow)
        finally:
            if owns_connection:
                active.close()


__all__ = [
    "AdaptationRecord",
    "AdaptationRecordKind",
    "InvestigationAdaptationIntegrityError",
    "InvestigationAdaptationQueryResult",
    "InvestigationAdaptationRepository",
    "InvestigationAdaptationStreamState",
    "MAX_EVALUATION_RECORDS",
]
