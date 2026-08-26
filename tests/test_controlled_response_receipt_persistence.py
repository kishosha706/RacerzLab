from __future__ import annotations

import inspect
import sqlite3
from datetime import datetime, timezone

import pytest
from test_controlled_workflow_service import _overview, _packet

from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.engineering_case import (
    ControlledResponseReceipt,
    ControlledStageResponseReceipt,
)
from racelab_engine.storage.repository import RaceLabRepository
from racelab_engine.services import controlled_workflow_service


def _blocked_response_receipt(workflow_id: str) -> ControlledResponseReceipt:
    stages = tuple(
        ControlledStageResponseReceipt(
            stage=stage,
            run_id=run_id,
            source_recording_sha256=recording,
            setup_snapshot_sha256=setup,
            source_channels=("steering_deg", "yaw_rate"),
            eligible_lap_numbers=(1, 2, 3),
            phase="entry",
            lap_pct_start=20.0,
            lap_pct_end=30.0,
            blocker_reasons=(
                "No reviewed response expectation contract is available.",
            ),
        )
        for stage, run_id, recording, setup in (
            ("A", "source", "1" * 64, "7" * 64),
            ("B", "source-b", "2" * 64, "8" * 64),
            ("A2", "source-a2", "3" * 64, "7" * 64),
        )
    )
    return ControlledResponseReceipt.build(
        workflow_id=workflow_id,
        control_key="cross_weight_percent",
        setup_effect_id="add_crossweight_small",
        experiment_factor_id="factor:crossweight",
        direction_sign=1,
        stages=stages,
        expected_response_relation_ids=(),
        expected_response_contract_ids=(),
        observed_metric_deltas=(),
        mechanism_assessment="inconclusive",
        control_response_assessment="unavailable",
        policy_verdict="retest",
        state="blocked",
        blocker_reasons=(
            "No reviewed response expectation contract is available.",
        ),
    )


def _persist_scored_workflow(db_path, workflow_id: str) -> RaceLabRepository:
    repo = RaceLabRepository(db_path)
    for run_id, timestamp in (
        ("source", "2026-08-04T10:00:00+00:00"),
        ("source-b", "2026-08-04T10:30:00+00:00"),
        ("source-a2", "2026-08-04T11:00:00+00:00"),
    ):
        overview = _overview(run_id, timestamp)
        overview.session.source_file = f"{run_id}.ibt"
        repo.save_import(overview)
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    repo.save_controlled_workflow(
        ControlledWorkflow(
            workflow_id=workflow_id,
            created_at=now,
            updated_at=now,
            status="scored",
            source_run_id="source",
            complaint="tight entry",
            packet=_packet(),
            stage_run_ids={"A": "source", "B": "source-b", "A2": "source-a2"},
            stage_eligible_lap_numbers={
                "A": (1, 2, 3),
                "B": (1, 2, 3),
                "A2": (1, 2, 3),
            },
            controlled_response_receipt=_blocked_response_receipt(workflow_id),
            learning_admitted=False,
        )
    )
    return repo


def test_repository_round_trips_controlled_response_receipt_across_restart(
    tmp_path,
) -> None:
    db_path = tmp_path / "workflow-response-receipt.sqlite"
    receipt = _blocked_response_receipt("aba-response-roundtrip")
    _persist_scored_workflow(db_path, receipt.workflow_id)

    loaded = RaceLabRepository(db_path).get_controlled_workflow(receipt.workflow_id)

    assert loaded is not None
    assert loaded.controlled_response_receipt == receipt
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT controlled_response_receipt_json, controlled_response_receipt_state "
            "FROM controlled_test_workflows WHERE workflow_id = ?",
            (receipt.workflow_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row == (receipt.model_dump_json(), "persisted")


def test_repository_fails_closed_on_response_receipt_state_mismatch(tmp_path) -> None:
    db_path = tmp_path / "workflow-response-receipt-corrupt.sqlite"
    workflow_id = "aba-response-corrupt"
    repo = _persist_scored_workflow(db_path, workflow_id)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE controlled_test_workflows "
            "SET controlled_response_receipt_json = NULL WHERE workflow_id = ?",
            (workflow_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="persistence state is corrupt"):
        repo.get_controlled_workflow(workflow_id)


def test_score_receipt_never_labels_raw_operational_evidence_as_artifact_hashes() -> None:
    source = inspect.getsource(
        controlled_workflow_service._build_controlled_response_receipt
    )

    assert "canonical_json_sha256(item) for item in projected" not in source
    assert "item.artifact_sha256 for item in exact_artifacts" in source
    assert "Exact current-case EngineeringResponseArtifact envelopes" in source
    assert "if exact_envelopes_resolved" in source
