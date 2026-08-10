from __future__ import annotations

import math

import polars as pl
import pytest
from pydantic import ValidationError

from racelab_engine.analysis.transient_awareness import (
    STEERING_WORKLOAD_CONTRACT,
    TRANSIENT_RESPONSE_CONTRACT,
    analyze_steering_workload,
    analyze_transient_response,
    compare_steering_workload,
)
from racelab_engine.models.engineering_context import (
    ControlMutationEvent,
    ControlMutationKind,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.transient_awareness import ExactAnalysisWindow
from racelab_engine.services.engineering_context_service import (
    build_steering_context_fingerprint,
)


def _window() -> ExactAnalysisWindow:
    return ExactAnalysisWindow(
        run_id="run-1",
        setup_id="setup-1",
        lap_number=4,
        context_id="context-1",
        phase="turn_in",
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        session_time_start=0.0,
        session_time_end=1.0,
    )


def _rows(*, torque_scale: float = 1.0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(61):
        time = index / 60.0
        steering = max(0.0, min(12.0, (time - 0.20) * 30.0))
        yaw = max(0.0, min(0.8, (time - 0.25) * 2.0))
        lateral = max(0.0, min(8.0, (time - 0.28) * 18.0))
        base_torque = torque_scale * (2.0 + 0.5 * math.sin(index * 0.8))
        rows.append(
            {
                "run_id": "run-1",
                "lap": 4,
                "lap_dist_pct_100": 20.0 + index / 6.0,
                "session_time": time,
                "engineering_phase": "turn_in",
                "steering_deg": steering,
                "yaw_rate": yaw,
                "lat_accel": lateral,
                "speed_mps": 55.0,
                "curvature_1_per_m": 0.004,
                "roll_rate": 0.0,
                "pitch_rate": 0.0,
                "steering_wheel_torque_nm": base_torque,
                "steering_wheel_torque_subtick_nm": [
                    base_torque + 0.08 * math.sin(sub_index * 1.7)
                    for sub_index in range(6)
                ],
            }
        )
    return rows


def _fingerprint(*, max_force: float = 40.0, complete: bool = True):
    row = {
        "SteeringWheelFFBEnabled": 1,
        "SteeringWheelMaxForceNm": max_force,
        "SteeringWheelUseLinear": 1,
        "SteeringWheelPctIntensity": 0.8,
        "SteeringWheelPctSmoothing": 0.1,
        "SteeringWheelPctDamper": 0.05,
        "SteeringWheelLimiter": 0.2,
    }
    if not complete:
        row.pop("SteeringWheelFFBEnabled")
    return build_steering_context_fingerprint([row])


def test_transient_response_reports_descriptive_delay_with_frame_row_parity() -> None:
    rows = _rows()
    row_report = analyze_transient_response(
        rows,
        window=_window(),
        lap_eligible=True,
    )
    frame_report = analyze_transient_response(
        pl.DataFrame(rows),
        window=_window(),
        lap_eligible=True,
    )

    assert row_report.status == "ready"
    assert row_report == frame_report
    assert row_report.descriptor is not None
    assert row_report.descriptor.observed_yaw_response_delay_ms > 0.0
    assert row_report.descriptor.descriptive_rise_time_ms is not None
    assert row_report.authority == "observation_only"
    serialized = str(row_report.model_dump()).casefold()
    assert "vehicle_time_constant" in serialized  # forbidden contract claim, not output
    assert "setup_target" not in serialized
    assert "caused_by" not in serialized


def test_transient_response_blocks_junk_laps_and_applied_mutations() -> None:
    junk = analyze_transient_response(
        _rows(),
        window=_window(),
        lap_eligible=False,
    )
    mutation = ControlMutationEvent(
        mutation_id="bias-change",
        run_id="run-1",
        control_key="applied_brake_bias",
        mutation_kind=ControlMutationKind.APPLIED_STATE,
        previous_value=52.0,
        new_value=54.0,
        session_time=0.5,
        lap=4,
        lap_pct=25.0,
        context_revision=2,
        evidence_state=EvidenceState.MEASURED,
    )
    split = analyze_transient_response(
        _rows(),
        window=_window(),
        lap_eligible=True,
        control_mutations=(mutation,),
    )

    assert junk.status == "blocked"
    assert split.status == "blocked"
    assert "mutation" in " ".join(split.blocker_reasons)


def test_subtick_workload_uses_all_360hz_samples_without_physical_overclaim() -> None:
    report = analyze_steering_workload(
        pl.DataFrame(_rows()),
        window=_window(),
        lap_eligible=True,
        ffb_fingerprint=_fingerprint(),
    )

    assert report.status == "ready"
    assert report.descriptor is not None
    assert report.descriptor.torque_sample_rate_hz == pytest.approx(360.0)
    assert report.descriptor.torque_sample_count == 366
    assert report.descriptor.steering_effort_work_proxy > 0.0
    assert report.descriptor.evidence_state is EvidenceState.ESTIMATED_PROXY
    assert report.descriptor.authority == "observation_only"
    forbidden = set(STEERING_WORKLOAD_CONTRACT.forbidden_claims)
    assert {"driver_fatigue", "tire_aligning_torque", "rack_work"} <= forbidden


def test_single_run_workload_can_be_limited_but_comparison_requires_full_ffb() -> None:
    limited_fingerprint = _fingerprint(complete=False)
    report = analyze_steering_workload(
        _rows(),
        window=_window(),
        lap_eligible=True,
        ffb_fingerprint=limited_fingerprint,
    )

    assert report.status == "limited"
    assert report.descriptor is not None
    comparison = compare_steering_workload(
        report.descriptor,
        report.descriptor,
        baseline_fingerprint=limited_fingerprint,
        test_fingerprint=limited_fingerprint,
        matched_physical_window=True,
        matched_speed_band=True,
        matched_driver_context=True,
        healthy_sub_tick_clock=True,
    )
    assert comparison.state == "unavailable"
    assert comparison.torque_rms_delta_nm is None


def test_material_max_force_change_blocks_workload_comparison() -> None:
    baseline_fingerprint = _fingerprint(max_force=40.0)
    test_fingerprint = _fingerprint(max_force=55.0)
    baseline_report = analyze_steering_workload(
        _rows(),
        window=_window(),
        lap_eligible=True,
        ffb_fingerprint=baseline_fingerprint,
    )
    test_report = analyze_steering_workload(
        _rows(torque_scale=1.2),
        window=_window(),
        lap_eligible=True,
        ffb_fingerprint=test_fingerprint,
    )
    assert baseline_report.descriptor is not None
    assert test_report.descriptor is not None

    comparison = compare_steering_workload(
        baseline_report.descriptor,
        test_report.descriptor,
        baseline_fingerprint=baseline_fingerprint,
        test_fingerprint=test_fingerprint,
        matched_physical_window=True,
        matched_speed_band=True,
        matched_driver_context=True,
        healthy_sub_tick_clock=True,
    )
    assert comparison.state == "not_comparable"
    assert comparison.torque_rms_delta_nm is None
    assert "force-feedback" in " ".join(comparison.blocker_reasons).casefold()


def test_matching_workload_context_produces_only_relative_proxy_deltas() -> None:
    fingerprint = _fingerprint()
    baseline = analyze_steering_workload(
        _rows(),
        window=_window(),
        lap_eligible=True,
        ffb_fingerprint=fingerprint,
    )
    test = analyze_steering_workload(
        _rows(torque_scale=1.2),
        window=_window(),
        lap_eligible=True,
        ffb_fingerprint=fingerprint,
    )
    assert baseline.descriptor is not None
    assert test.descriptor is not None
    comparison = compare_steering_workload(
        baseline.descriptor,
        test.descriptor,
        baseline_fingerprint=fingerprint,
        test_fingerprint=fingerprint,
        matched_physical_window=True,
        matched_speed_band=True,
        matched_driver_context=True,
        healthy_sub_tick_clock=True,
    )

    assert comparison.state == "comparable"
    assert comparison.torque_rms_delta_nm is not None
    assert comparison.torque_rms_delta_nm > 0.0
    assert comparison.authority == "observation_only"

    mismatched_payload = test.descriptor.model_dump()
    mismatched_payload["window"]["lap_pct_start"] = 21.0
    mismatched = type(test.descriptor).model_validate(mismatched_payload)
    blocked = compare_steering_workload(
        baseline.descriptor,
        mismatched,
        baseline_fingerprint=fingerprint,
        test_fingerprint=fingerprint,
        matched_physical_window=True,
        matched_speed_band=True,
        matched_driver_context=True,
        healthy_sub_tick_clock=True,
    )
    assert blocked.state == "unavailable"
    assert "exact physical phase window" in " ".join(blocked.blocker_reasons)


def test_transient_models_reject_setup_authority() -> None:
    report = analyze_transient_response(
        _rows(),
        window=_window(),
        lap_eligible=True,
    )
    with pytest.raises(ValidationError):
        type(report)(**{**report.model_dump(), "authority": "setup_authority"})
    assert TRANSIENT_RESPONSE_CONTRACT.authority_ceiling == "observation_only"


def test_invalid_phase_and_missing_subtick_torque_fail_closed() -> None:
    invalid_window = _window().model_copy(update={"phase": "unknown"})
    transient = analyze_transient_response(
        _rows(),
        window=invalid_window,
        lap_eligible=True,
    )
    no_subtick = [
        {key: value for key, value in row.items() if key != "steering_wheel_torque_subtick_nm"}
        for row in _rows()
    ]
    workload = analyze_steering_workload(
        no_subtick,
        window=_window(),
        lap_eligible=True,
        ffb_fingerprint=_fingerprint(),
    )

    assert transient.status == "blocked"
    assert "valid transient-response phase" in " ".join(transient.blocker_reasons)
    assert workload.status == "blocked"
    assert "sub-tick torque" in " ".join(workload.blocker_reasons)
