from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from racelab_engine.evaluation.shadow import (
    append_shadow_outcome,
    build_shadow_model_contract,
    build_shadow_outcome,
    build_shadow_prediction,
    geometry_corrected_wheel_disagreement_shadow,
    gravity_compensated_acceleration_shadow,
    research_shadow_contracts,
    save_shadow_model_contract,
    save_shadow_prediction,
)


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _contract(version: str = "v1"):
    return build_shadow_model_contract(
        {
            "model_key": "test_shadow",
            "version": version,
            "created_at": NOW,
            "implementation_state": "prospective_shadow",
            "input_keys": ("signal",),
            "required_context_keys": ("track",),
            "output_keys": ("predicted_direction",),
            "allowed_claims": ("shadow direction",),
            "forbidden_claims": ("setup authority",),
            "negative_control_ids": ("same_setup_unchanged",),
            "ground_truth_types": ("prospective_observed_outcome",),
        }
    )


def _prediction(contract, *, when: datetime = NOW):
    return build_shadow_prediction(
        contract,
        {
            "predicted_at": when,
            "source_run_ids": ("run-1",),
            "source_session_ids": ("session-1",),
            "inputs": {"signal": 1.0},
            "context": {"track": "atlanta"},
            "prediction": {"predicted_direction": "increase"},
            "prospective": True,
        },
    )


def test_research_observers_remain_blocked_prerequisites():
    contracts = research_shadow_contracts(created_at=NOW)
    assert {contract.model_key for contract in contracts} == {
        "shadow_body_sideslip_proxy",
        "gravity_compensated_accel_shadow",
        "geometry_corrected_wheel_disagreement_shadow",
    }
    assert all(contract.implementation_state == "blocked_prerequisites" for contract in contracts)
    assert all(contract.authority == "shadow_only" for contract in contracts)


def test_shadow_payload_cannot_carry_p19_authority():
    contract = _contract()
    with pytest.raises(ValueError, match="prohibited authority"):
        build_shadow_prediction(
            contract,
            {
                "predicted_at": NOW,
                "source_run_ids": ("run-1",),
                "source_session_ids": ("session-1",),
                "inputs": {"signal": 1.0, "cause_rank": "leading"},
                "context": {"track": "atlanta"},
                "prediction": {"predicted_direction": "increase"},
                "prospective": True,
            },
        )


def test_prospective_prediction_must_precede_ground_truth():
    contract = _contract()
    with pytest.raises(ValueError, match="precede ground truth"):
        build_shadow_prediction(
            contract,
            {
                "predicted_at": NOW,
                "source_run_ids": ("run-1",),
                "source_session_ids": ("session-1",),
                "inputs": {"signal": 1.0},
                "context": {"track": "atlanta"},
                "prediction": {"predicted_direction": "increase"},
                "prospective": True,
                "ground_truth_available_at_prediction": True,
            },
        )


def test_prediction_and_later_outcome_are_append_only(tmp_path):
    database = tmp_path / "shadow.sqlite"
    contract = _contract()
    prediction = _prediction(contract)
    outcome = build_shadow_outcome(
        prediction,
        {
            "observed_at": NOW + timedelta(hours=1),
            "outcome": {"actual_direction": "increase"},
            "ground_truth_type": "prospective_observed_outcome",
            "evidence_artifact_ids": ("artifact-1",),
            "gradable": True,
        },
    )
    assert save_shadow_model_contract(contract, db_path=database)
    assert save_shadow_prediction(prediction, db_path=database)
    assert append_shadow_outcome(outcome, db_path=database)
    assert not append_shadow_outcome(outcome, db_path=database)
    edited = build_shadow_outcome(
        prediction,
        {
            "observed_at": NOW + timedelta(hours=2),
            "outcome": {"actual_direction": "decrease"},
            "ground_truth_type": "prospective_observed_outcome",
            "evidence_artifact_ids": ("artifact-2",),
            "gradable": True,
        },
    )
    with pytest.raises(ValueError, match="immutable once recorded"):
        append_shadow_outcome(edited, db_path=database)


def test_model_version_change_invalidates_shadow_identity():
    first = _contract("v1")
    second = _contract("v2")
    assert first.model_id != second.model_id
    assert _prediction(first).prediction_id != _prediction(second).prediction_id


def test_geometry_correction_is_separate_descriptive_shadow():
    result = geometry_corrected_wheel_disagreement_shadow(
        vehicle_speed_mps=50.0,
        yaw_rate_rad_s=0.2,
        wheelbase_m=2.8,
        track_width_m=1.6,
        left_speed_mps=49.7,
        right_speed_mps=50.3,
    )
    assert result.authority == "shadow_only"
    assert result.raw_disagreement_mps == pytest.approx(0.6)
    assert result.geometry_expected_disagreement_mps == pytest.approx(0.32)
    assert result.residual_disagreement_mps == pytest.approx(0.28)


def test_gravity_compensation_never_overwrites_raw_acceleration():
    result = gravity_compensated_acceleration_shadow(
        raw_long_accel_mps2=1.0,
        raw_lat_accel_mps2=2.0,
        raw_vert_accel_mps2=9.80665,
        roll_rad=0.0,
        pitch_rad=0.0,
    )
    assert result.raw_long_accel_mps2 == 1.0
    assert result.raw_lat_accel_mps2 == 2.0
    assert result.raw_vert_accel_mps2 == 9.80665
    assert result.compensated_vert_accel_mps2 == pytest.approx(0.0)
    assert result.authority == "shadow_only"
