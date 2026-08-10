from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from racelab_engine.evaluation.dataset_registry import (
    EvidenceDataset,
    build_evidence_dataset,
    get_evidence_dataset,
    register_evidence_dataset,
)
from racelab_engine.evaluation.leakage import evaluate_dataset_leakage
from racelab_engine.evaluation.split_policy import build_split_policy


SHA_A = "a" * 64
SHA_B = "b" * 64


def _dataset_payload(*, duplicate_source: bool = False, synthetic: bool = False):
    second_source = SHA_A if duplicate_source else SHA_B
    return {
        "dataset_kind": "synthetic_injection" if synthetic else "driver_repeatability",
        "created_at": datetime(2026, 8, 10, tzinfo=timezone.utc),
        "manifest": {
            "schema_version": "p21-dataset-v1",
            "source_run_ids": ("run-a", "run-b"),
            "source_session_ids": ("session-a", "session-b"),
            "car_identities": ("nextgen",),
            "track_identities": ("atlanta",),
            "iracing_build_identities": ("2026.08",),
            "vehicle_profile_hashes": (),
            "analysis_artifact_versions": ("p20-v1",),
            "setup_identities": ("setup-a",),
            "context_distribution": {"atlanta": 2},
            "lap_count": 20,
            "independence_unit_count": 2,
            "ground_truth_type": (
                "synthetic_known_signal" if synthetic else "same_setup_null"
            ),
            "allowed_evaluation_uses": ("driver_noise",),
            "forbidden_uses": ("setup_authority", "probability_authority"),
        },
        "artifacts": (
            {
                "artifact_id": "artifact-a",
                "artifact_kind": "telemetry_archive",
                "content_sha256": SHA_A,
                "source_file_fingerprint": SHA_A,
                "source_run_ids": ("run-a",),
                "artifact_version": "v1",
            },
            {
                "artifact_id": "artifact-b",
                "artifact_kind": "telemetry_archive",
                "content_sha256": SHA_B,
                "source_file_fingerprint": second_source,
                "source_run_ids": ("run-b",),
                "artifact_version": "v1",
            },
        ),
        "units": (
            {
                "unit_id": "session-a",
                "independence_level": "session",
                "source_artifact_ids": ("artifact-a",),
                "source_file_fingerprints": (SHA_A,),
                "source_run_ids": ("run-a",),
                "source_session_ids": ("session-a",),
                "lap_numbers": tuple(range(1, 11)),
                "setup_fingerprints": ("setup-a",),
                "context_fingerprints": ("context-a",),
                "synthetic": synthetic,
            },
            {
                "unit_id": "session-b",
                "independence_level": "session",
                "source_artifact_ids": ("artifact-b",),
                "source_file_fingerprints": (second_source,),
                "source_run_ids": ("run-b",),
                "source_session_ids": ("session-b",),
                "lap_numbers": tuple(range(1, 11)),
                "setup_fingerprints": ("setup-a",),
                "context_fingerprints": ("context-a",),
                "synthetic": synthetic,
            },
        ),
        "splits": (
            {"split_id": "train", "partition": "train", "unit_ids": ("session-a",)},
            {
                "split_id": "evaluation",
                "partition": "evaluation",
                "unit_ids": ("session-b",),
            },
        ),
        "qualification": {
            "state": "qualified",
            "qualified_real_world_units": 0 if synthetic else 2,
            "qualified_synthetic_units": 2 if synthetic else 0,
        },
    }


def test_dataset_identity_is_content_addressed_and_persistent(tmp_path):
    dataset = build_evidence_dataset(_dataset_payload())
    assert dataset.dataset_id == f"eds-{dataset.dataset_hash[:20]}"
    assert register_evidence_dataset(dataset, db_path=tmp_path / "lab.sqlite")
    assert not register_evidence_dataset(dataset, db_path=tmp_path / "lab.sqlite")
    assert get_evidence_dataset(
        dataset.dataset_id,
        db_path=tmp_path / "lab.sqlite",
    ) == dataset


def test_dataset_mutation_invalidates_identity():
    dataset = build_evidence_dataset(_dataset_payload())
    changed = dataset.model_dump(mode="json")
    changed["manifest"]["lap_count"] = 21
    with pytest.raises(ValidationError, match="identity"):
        EvidenceDataset.model_validate(changed)


def test_telemetry_samples_cannot_be_independent_units():
    payload = _dataset_payload()
    payload["units"][0]["independence_level"] = "sample"
    with pytest.raises(ValidationError, match="telemetry samples"):
        build_evidence_dataset(payload)


def test_same_source_file_under_two_run_ids_fails_leakage():
    dataset = build_evidence_dataset(_dataset_payload(duplicate_source=True))
    policy = build_split_policy(
        {
            "policy_version": "v1",
            "kind": "whole_session",
            "required_independence_level": "session",
        }
    )
    report = evaluate_dataset_leakage(dataset, policy)
    assert not report.valid
    assert "duplicate_source_file" in {finding.code for finding in report.findings}


def test_adjacent_laps_cannot_satisfy_session_independence():
    payload = _dataset_payload()
    payload["units"][0]["independence_level"] = "lap"
    dataset = build_evidence_dataset(payload)
    policy = build_split_policy(
        {
            "policy_version": "v1",
            "kind": "whole_session",
            "required_independence_level": "session",
        }
    )
    report = evaluate_dataset_leakage(dataset, policy)
    assert not report.valid
    assert "independence_level_too_fine" in {
        finding.code for finding in report.findings
    }


def test_synthetic_dataset_cannot_satisfy_real_activation():
    dataset = build_evidence_dataset(_dataset_payload(synthetic=True))
    policy = build_split_policy(
        {
            "policy_version": "v1",
            "kind": "whole_session",
            "required_independence_level": "session",
        }
    )
    report = evaluate_dataset_leakage(dataset, policy)
    assert not report.valid
    assert "synthetic_only_activation" in {finding.code for finding in report.findings}


def test_workflow_stages_cannot_cross_partitions():
    payload = _dataset_payload()
    payload["manifest"]["source_workflow_ids"] = ("workflow-1",)
    for unit in payload["units"]:
        unit["independence_level"] = "controlled_workflow"
        unit["source_workflow_ids"] = ("workflow-1",)
    dataset = build_evidence_dataset(payload)
    policy = build_split_policy(
        {
            "policy_version": "v1",
            "kind": "whole_workflow",
            "required_independence_level": "controlled_workflow",
        }
    )
    report = evaluate_dataset_leakage(dataset, policy)
    assert not report.valid
    assert "workflow_split_or_duplicated" in {
        finding.code for finding in report.findings
    }
