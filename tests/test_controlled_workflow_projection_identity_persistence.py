from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from test_controlled_workflow_service import _overview, _packet

from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.storage import db as database
from racelab_engine.storage.repository import RaceLabRepository


P32_OPPORTUNITY_ID = "p32-opportunity-exact"
P32_PROJECTION_SHA256 = "a" * 64
KNOWLEDGE_PROJECTION_SHA256 = "b" * 64


def _performance_binding() -> dict[str, object]:
    return {
        "schema_version": "p352.workflow-performance-opportunity.v1",
        "p32_opportunity_id": P32_OPPORTUNITY_ID,
        "p32_projection_sha256": P32_PROJECTION_SHA256,
        "engineering_knowledge_projection_sha256": KNOWLEDGE_PROJECTION_SHA256,
    }


def _workflow() -> ControlledWorkflow:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    return ControlledWorkflow(
        workflow_id="projection-bound-workflow",
        created_at=now,
        updated_at=now,
        status="planned",
        source_run_id="source",
        complaint="tight center",
        packet=_packet(),
        p32_opportunity_id=P32_OPPORTUNITY_ID,
        p32_projection_sha256=P32_PROJECTION_SHA256,
        engineering_knowledge_projection_sha256=KNOWLEDGE_PROJECTION_SHA256,
        reproduction_snapshot={
            "p352_performance_opportunity_binding": _performance_binding()
        },
    )


def _write_v6_database(path, *, binding: object) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE schema_migrations (
          version INTEGER PRIMARY KEY,
          checksum TEXT NOT NULL,
          applied_at TEXT NOT NULL
        )
        """
    )
    connection.executemany(
        "INSERT INTO schema_migrations(version, checksum, applied_at) "
        "VALUES (?, ?, ?)",
        tuple(
            (version, database._LIGHTWEIGHT_MIGRATION_CHECKSUMS[version], "legacy-v6")
            for version in range(2, 7)
        ),
    )
    connection.execute(
        """
        CREATE TABLE controlled_test_workflows (
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
          controlled_response_receipt_json TEXT,
          controlled_response_receipt_state TEXT NOT NULL DEFAULT 'not_applicable',
          learning_admitted INTEGER,
          learning_capture_state TEXT NOT NULL DEFAULT 'not_applicable',
          learning_capture_experience_id TEXT,
          learning_capture_experience_sha256 TEXT,
          learning_capture_blocker_reason TEXT
        )
        """
    )
    workflow = _workflow()
    snapshot = {"p352_performance_opportunity_binding": binding}
    connection.execute(
        """
        INSERT INTO controlled_test_workflows (
          workflow_id, created_at, updated_at, status, source_run_id, complaint,
          packet_json, reproduction_snapshot_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workflow.workflow_id,
            workflow.created_at.isoformat(),
            workflow.updated_at.isoformat(),
            workflow.status,
            workflow.source_run_id,
            workflow.complaint,
            workflow.packet.model_dump_json(),
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
        ),
    )
    connection.commit()
    connection.close()


def test_repository_round_trips_exact_workflow_projection_identity(tmp_path) -> None:
    db_path = tmp_path / "workflow-projection-identity.sqlite"
    repository = RaceLabRepository(db_path)
    repository.save_import(_overview("source", "2026-08-26T11:00:00+00:00"))
    workflow = _workflow()

    repository.save_controlled_workflow(workflow)
    database._INITIALIZED_DATABASES.clear()
    loaded = RaceLabRepository(db_path).get_controlled_workflow(workflow.workflow_id)

    assert loaded == workflow
    connection = database.initialize_database(db_path)
    row = connection.execute(
        "SELECT p32_opportunity_id, p32_projection_sha256, "
        "engineering_knowledge_projection_sha256 "
        "FROM controlled_test_workflows WHERE workflow_id = ?",
        (workflow.workflow_id,),
    ).fetchone()
    connection.close()
    assert tuple(row) == (
        P32_OPPORTUNITY_ID,
        P32_PROJECTION_SHA256,
        KNOWLEDGE_PROJECTION_SHA256,
    )


def test_v7_migration_restores_projection_identity_from_exact_receipt(tmp_path) -> None:
    db_path = tmp_path / "workflow-projection-v6.sqlite"
    _write_v6_database(db_path, binding=_performance_binding())

    database._INITIALIZED_DATABASES.clear()
    connection = database.initialize_database(db_path)
    row = connection.execute(
        "SELECT p32_opportunity_id, p32_projection_sha256, "
        "engineering_knowledge_projection_sha256 "
        "FROM controlled_test_workflows WHERE workflow_id = ?",
        (_workflow().workflow_id,),
    ).fetchone()
    versions = tuple(
        item["version"]
        for item in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    )
    connection.close()

    assert tuple(row) == (
        P32_OPPORTUNITY_ID,
        P32_PROJECTION_SHA256,
        KNOWLEDGE_PROJECTION_SHA256,
    )
    assert versions == tuple(range(2, 8))
    loaded = RaceLabRepository(db_path).get_controlled_workflow(
        _workflow().workflow_id
    )
    assert loaded == _workflow()


def test_v7_migration_fails_closed_on_partial_projection_receipt(tmp_path) -> None:
    db_path = tmp_path / "workflow-projection-v6-partial.sqlite"
    partial = _performance_binding()
    partial.pop("engineering_knowledge_projection_sha256")
    _write_v6_database(db_path, binding=partial)

    database._INITIALIZED_DATABASES.clear()
    with pytest.raises(RuntimeError, match="projection identity receipt is incomplete"):
        database.initialize_database(db_path)
