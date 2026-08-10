from __future__ import annotations

from datetime import datetime, timezone

import pytest

from racelab_engine.evaluation.dataset_registry import (
    build_evidence_dataset,
    register_evidence_dataset,
)
from racelab_engine.evaluation.first_activation import (
    P23FirstActivationAudit,
    build_first_activation_audit,
    capability_activation_matrix,
    first_activation_protocol,
    latest_first_activation_audit,
    save_first_activation_audit,
    save_first_activation_protocol,
)
from racelab_engine.evaluation.metric_evaluation import MetricThreshold


NOW = datetime(2026, 8, 10, 23, tzinfo=timezone.utc)


def _driver_dataset(
    run_id: str,
    artifact_id: str,
    *,
    source_fingerprint: str = "f" * 64,
    synthetic: bool = False,
):
    return build_evidence_dataset(
        {
            "dataset_kind": "driver_repeatability",
            "created_at": NOW,
            "manifest": {
                "schema_version": "p23-test-v1",
                "source_run_ids": (run_id,),
                "source_session_ids": (f"session:{run_id}",),
                "track_identities": ("short_track",),
                "iracing_build_identities": ("build-1",),
                "analysis_artifact_versions": ("driver-v1",),
                "context_distribution": {"short_track": 1},
                "lap_count": 10,
                "independence_unit_count": 1,
                "ground_truth_type": "same_setup_null",
                "allowed_evaluation_uses": ("driver_noise_envelope",),
                "forbidden_uses": ("setup_authority",),
            },
            "artifacts": (
                {
                    "artifact_id": artifact_id,
                    "artifact_kind": "session_summary",
                    "content_sha256": ("a" if run_id == "run-a" else "b") * 64,
                    "source_file_fingerprint": source_fingerprint,
                    "source_run_ids": (run_id,),
                    "artifact_version": "driver-v1",
                },
            ),
            "units": (
                {
                    "unit_id": f"unit:{run_id}",
                    "independence_level": "session",
                    "source_artifact_ids": (artifact_id,),
                    "source_file_fingerprints": (source_fingerprint,),
                    "source_run_ids": (run_id,),
                    "source_session_ids": (f"session:{run_id}",),
                    "lap_numbers": tuple(range(1, 11)),
                    "track_ids": ("short_track",),
                    "build_ids": ("build-1",),
                    "synthetic": synthetic,
                },
            ),
            "qualification": {
                "state": "qualified",
                "qualified_real_world_units": 0 if synthetic else 1,
                "qualified_synthetic_units": 1 if synthetic else 0,
            },
        }
    )


def test_all_candidates_are_ranked_before_low_risk_winner_is_selected(tmp_path):
    matrix = capability_activation_matrix(db_path=tmp_path / "audit.sqlite")
    assert len(matrix) == 15
    assert tuple(item.rank for item in matrix) == tuple(range(1, 16))
    assert {item.capability_key for item in matrix} >= {
        "steering_workload_envelope",
        "steering_yaw_transient_calibration",
        "geometry_wheel_disagreement",
        "gravity_compensation",
        "shadow_sideslip",
        "change_point",
        "response_model",
        "probability_calibration",
        "conformal_uncertainty",
        "hierarchical_transfer",
        "formal_information_gain",
        "bayesian_optimization",
        "multi_control_optimization",
    }
    selected = [item for item in matrix if item.selected]
    assert len(selected) == 1
    assert selected[0].capability_key == "steering_workload_envelope"
    assert selected[0].current_authority == "observation_only"
    assert selected[0].independent_unit_count == 0
    assert "no geometry dependency" in selected[0].selection_reason
    assert all(item.qualified_evidence_missing for item in matrix)


def test_protocol_is_content_addressed_frozen_and_keeps_authority_out(tmp_path):
    database = tmp_path / "protocol.sqlite"
    protocol = first_activation_protocol()
    assert protocol.formula_version == "p20.steering_workload.v1"
    assert protocol.independence_unit == "source_session"
    assert protocol.minimum_prospective_units == 10
    assert protocol.current_authority == "shadow_only"
    assert protocol.authority_ceiling == "limited_observation_overlay"
    assert "setup_value" in protocol.forbidden_outputs
    assert "cause_probability" in protocol.forbidden_outputs
    assert protocol.p19_authority_unchanged is True
    assert protocol.p20_authority_unchanged is True
    assert save_first_activation_protocol(protocol, db_path=database)
    assert not save_first_activation_protocol(protocol, db_path=database)
    changed_thresholds = (
        MetricThreshold(
            metric_key="absolute_envelope_coverage_gap",
            operator="lte",
            value=0.10,
        ),
        *protocol.thresholds[1:],
    )
    rewritten = protocol.model_copy(update={"thresholds": changed_thresholds})
    with pytest.raises(ValueError, match="thresholds are frozen"):
        save_first_activation_protocol(rewritten, db_path=database)


def test_empty_archive_scientifically_returns_no_activation_and_persists(tmp_path):
    database = tmp_path / "decision.sqlite"
    protocol = first_activation_protocol()
    save_first_activation_protocol(protocol, db_path=database)
    audit = build_first_activation_audit(db_path=database, created_at=NOW)
    assert audit.activation_decision == "no_activation_earned"
    assert audit.historical.state == "not_started"
    assert audit.prospective.state == "not_started"
    assert audit.negative_controls.state == "not_started"
    assert audit.subgroups.state == "not_started"
    assert audit.exact_authority_envelope == ()
    assert audit.p19_sole_reasoning_setup_authority is True
    assert audit.p20_sole_state_projection is True
    assert save_first_activation_audit(audit, db_path=database)
    assert not save_first_activation_audit(audit, db_path=database)
    assert latest_first_activation_audit(db_path=database) == audit


def test_aggregate_success_cannot_hide_unpassed_controls_or_subgroups(tmp_path):
    database = tmp_path / "hostile.sqlite"
    protocol = first_activation_protocol()
    save_first_activation_protocol(protocol, db_path=database)
    audit = build_first_activation_audit(db_path=database, created_at=NOW)
    payload = audit.model_dump(
        mode="python",
        exclude={"audit_id", "audit_hash"},
    )
    payload["activation_decision"] = "limited_activation_earned"
    payload["exact_authority_envelope"] = ("validated steering workload",)
    with pytest.raises(ValueError, match="every frozen gate"):
        P23FirstActivationAudit(
            audit_id="p23a-" + "0" * 20,
            audit_hash="0" * 64,
            **payload,
        )


def test_protocol_binds_build_profile_formula_and_real_prospective_boundary():
    protocol = first_activation_protocol()
    assert "new iRacing build blocks" in protocol.drift_criteria[0]
    assert any("profile/formula/code hash mismatch" in item for item in protocol.drift_criteria)
    assert "synthetic evidence presented as real field evidence" in protocol.exclusions
    assert "prospective units strictly after protocol freeze" in protocol.split_policy
    assert "source fingerprint deduplication" in protocol.split_policy
    assert "no adjacent-window independence" in protocol.split_policy
    assert set(protocol.negative_control_ids) >= {
        "stable_steering_response",
        "ffb_config_changed",
        "driver_line_changed",
        "traffic_context_mismatch",
        "sim_integrity_degraded",
        "profile_build_mismatch",
    }


def test_duplicate_source_file_cannot_inflate_activation_independence(tmp_path):
    database = tmp_path / "duplicates.sqlite"
    register_evidence_dataset(
        _driver_dataset("run-a", "artifact-a"), db_path=database
    )
    register_evidence_dataset(
        _driver_dataset("run-b", "artifact-b"), db_path=database
    )
    register_evidence_dataset(
        _driver_dataset(
            "synthetic-run",
            "artifact-synthetic",
            source_fingerprint="e" * 64,
            synthetic=True,
        ),
        db_path=database,
    )
    driver = next(
        item
        for item in capability_activation_matrix(db_path=database)
        if item.capability_key == "driver_noise_envelope"
    )
    assert driver.independent_unit_count == 1
