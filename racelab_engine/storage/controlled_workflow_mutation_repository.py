from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.storage.db import initialize_database


WorkflowMutationAction = Literal["start", "cancel", "stage", "score"]


class ControlledWorkflowMutationIntegrityError(ValueError):
    """A durable workflow mutation receipt is corrupt or ambiguously rebound."""


class ControlledWorkflowMutationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mutation_id: str = Field(pattern=r"^cwm_[0-9a-f]{24}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: WorkflowMutationAction
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    request_workflow_id: str | None = None
    expected_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_workflow_id: str | None = None
    result_workflow_revision_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_at: datetime
    response_payload: dict[str, Any]


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    )


class ControlledWorkflowMutationRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path

    @staticmethod
    def _receipt_from_row(row: sqlite3.Row) -> ControlledWorkflowMutationReceipt:
        try:
            payload = json.loads(row["response_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation receipt response is unreadable or corrupt."
            ) from exc
        if not isinstance(payload, dict):
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation receipt response must be one canonical object."
            )
        if row["response_json"] != _canonical_json(payload):
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation receipt response is not canonical JSON."
            )
        response_sha256 = canonical_json_sha256(payload)
        if response_sha256 != row["response_sha256"]:
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation receipt response hash is corrupt."
            )
        try:
            receipt = ControlledWorkflowMutationReceipt(
                mutation_id=row["mutation_id"],
                request_sha256=row["request_sha256"],
                action=row["action"],
                run_id=row["run_id"],
                session_id=row["session_id"],
                request_workflow_id=row["request_workflow_id"],
                expected_case_sha256=row["expected_case_sha256"],
                result_case_sha256=row["result_case_sha256"],
                result_workflow_id=row["result_workflow_id"],
                result_workflow_revision_sha256=(
                    row["result_workflow_revision_sha256"]
                ),
                response_sha256=response_sha256,
                completed_at=row["completed_at"],
                response_payload=payload,
            )
        except (TypeError, ValueError) as exc:
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation receipt columns are invalid."
            ) from exc
        if (receipt.result_workflow_id is None) != (
            receipt.result_workflow_revision_sha256 is None
        ):
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation receipt result identity is incomplete."
            )
        return receipt

    @classmethod
    def receipt_in_transaction(
        cls,
        connection: sqlite3.Connection,
        mutation_id: str,
        *,
        request_sha256: str,
        action: WorkflowMutationAction,
        run_id: str,
        session_id: str,
        request_workflow_id: str | None,
        expected_case_sha256: str,
    ) -> ControlledWorkflowMutationReceipt | None:
        row = connection.execute(
            "SELECT * FROM controlled_workflow_mutation_receipts WHERE mutation_id = ?",
            (mutation_id,),
        ).fetchone()
        if row is None:
            return None
        receipt = cls._receipt_from_row(row)
        if (
            receipt.request_sha256 != request_sha256
            or receipt.action != action
            or receipt.run_id != run_id
            or receipt.session_id != session_id
            or receipt.request_workflow_id != request_workflow_id
            or receipt.expected_case_sha256 != expected_case_sha256
        ):
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation identity already owns another request or scope."
            )
        return receipt

    def receipt(
        self,
        mutation_id: str,
        **expectation: Any,
    ) -> ControlledWorkflowMutationReceipt | None:
        connection = initialize_database(self.db_path)
        try:
            return self.receipt_in_transaction(
                connection, mutation_id, **expectation
            )
        finally:
            connection.close()

    @classmethod
    def save_receipt_in_transaction(
        cls,
        connection: sqlite3.Connection,
        *,
        mutation_id: str,
        request_sha256: str,
        action: WorkflowMutationAction,
        run_id: str,
        session_id: str,
        request_workflow_id: str | None,
        expected_case_sha256: str,
        result_case_sha256: str,
        result_workflow_id: str | None,
        result_workflow_revision_sha256: str | None,
        response_payload: dict[str, Any],
    ) -> ControlledWorkflowMutationReceipt:
        existing = cls.receipt_in_transaction(
            connection,
            mutation_id,
            request_sha256=request_sha256,
            action=action,
            run_id=run_id,
            session_id=session_id,
            request_workflow_id=request_workflow_id,
            expected_case_sha256=expected_case_sha256,
        )
        response_sha256 = canonical_json_sha256(response_payload)
        if existing is not None:
            if (
                existing.result_case_sha256 != result_case_sha256
                or existing.result_workflow_id != result_workflow_id
                or existing.result_workflow_revision_sha256
                != result_workflow_revision_sha256
                or existing.response_sha256 != response_sha256
                or existing.response_payload != response_payload
            ):
                raise ControlledWorkflowMutationIntegrityError(
                    "Controlled-workflow mutation receipt cannot be rebound to another result."
                )
            return existing
        completed_at = datetime.now(UTC)
        response_json = _canonical_json(response_payload)
        connection.execute(
            """
            INSERT INTO controlled_workflow_mutation_receipts(
              mutation_id, request_sha256, action, run_id, session_id,
              request_workflow_id, expected_case_sha256, result_case_sha256,
              result_workflow_id, result_workflow_revision_sha256,
              response_sha256, completed_at, response_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mutation_id,
                request_sha256,
                action,
                run_id,
                session_id,
                request_workflow_id,
                expected_case_sha256,
                result_case_sha256,
                result_workflow_id,
                result_workflow_revision_sha256,
                response_sha256,
                completed_at.isoformat(),
                response_json,
            ),
        )
        saved = cls.receipt_in_transaction(
            connection,
            mutation_id,
            request_sha256=request_sha256,
            action=action,
            run_id=run_id,
            session_id=session_id,
            request_workflow_id=request_workflow_id,
            expected_case_sha256=expected_case_sha256,
        )
        if saved is None:
            raise ControlledWorkflowMutationIntegrityError(
                "Controlled-workflow mutation receipt was not durably written."
            )
        return saved


__all__ = [
    "ControlledWorkflowMutationIntegrityError",
    "ControlledWorkflowMutationReceipt",
    "ControlledWorkflowMutationRepository",
    "WorkflowMutationAction",
]
