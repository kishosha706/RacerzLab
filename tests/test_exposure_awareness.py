from __future__ import annotations

from copy import deepcopy

import polars as pl

from racelab_engine.analysis.exposure_awareness import (
    BRAKE_EXPOSURE_CONTRACT,
    CHASSIS_RESPONSE_CONTRACT,
    COMBINED_ACCELERATION_CONTRACT,
    RELATIVE_SLIP_EXPOSURE_CONTRACT,
    TIRE_THERMAL_RESPONSE_CONTRACT,
    TRACK_DISTURBANCE_CONTRACT,
    analyze_brake_pressure_velocity_exposure,
    analyze_chassis_response,
    analyze_combined_acceleration_occupancy,
    analyze_relative_slip_exposure,
    analyze_tire_thermal_response,
    build_track_disturbance_signature,
)
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.models.transient_awareness import ExactAnalysisWindow
from racelab_engine.models.vehicle_engineering_profile import (
    build_vehicle_engineering_profile,
)


def _window(lap: int = 4, *, start: float = 10.0) -> ExactAnalysisWindow:
    return ExactAnalysisWindow(
        run_id="run-a",
        setup_id="setup-a",
        lap_number=lap,
        context_id="atlanta:t1:10-11",
        phase="straight",
        lap_pct_start=10.0,
        lap_pct_end=11.0,
        session_time_start=start,
        session_time_end=start + 1.0,
    )


def _rows(lap: int = 4, *, start: float = 10.0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(11):
        fraction = index / 10.0
        row: dict[str, object] = {
            "run_id": "run-a",
            "lap": lap,
            "session_time": start + fraction,
            "lap_dist_pct_100": 10.0 + fraction,
            "speed_mps": 70.0 + fraction,
            "yaw_rate": 0.08,
            "lat_accel": 2.0 + fraction,
            "long_accel": -1.0 + fraction * 0.4,
            "vert_accel": [0.0, 0.2, 1.8, -0.8, 0.4, -0.15, 0.04, 0.02, 0.0, 0.0, 0.0][
                index
            ],
            "abs_active": 1.0 if index in {3, 4} else 0.0,
        }
        for offset, corner in enumerate(("lf", "rf", "lr", "rr")):
            row[f"{corner}_ride_height_mm"] = 50.0 + offset + fraction * (offset + 1)
            sequence = [
                0.0,
                1.0 + offset,
                5.0 - offset * 0.2,
                -2.0,
                1.0,
                -0.4,
                0.1,
                0.0,
                0.0,
                0.0,
                0.0,
            ]
            row[f"{corner}_shock_vel_in_s"] = sequence[(index - offset) % len(sequence)]
            row[f"{corner}_brake_line_pressure_bar"] = (40.0 - offset * 5.0) * fraction
            row[f"{corner}_temp_inner"] = 70.0 + offset + fraction * 2.0
            row[f"{corner}_temp_middle"] = 69.0 + offset + fraction * 1.5
            row[f"{corner}_temp_outer"] = 68.0 + offset + fraction
            row[f"{corner}_pressure"] = 160.0 + offset + fraction
            row[f"{corner}_tire_distance_m"] = 1000.0 + fraction * 70.0
            row[f"{corner}_carcass_temp_l"] = 55.0
            row[f"{corner}_wear_inner"] = 0.98
        for offset, raw in enumerate(("LFspeed", "RFspeed", "LRspeed", "RRspeed")):
            row[raw] = 70.0 + fraction + (offset - 1.5) * 0.1
        rows.append(row)
    return rows


def _geometry_profile():
    payload = {
        "profile_id": "verified-nextgen-test",
        "profile_version": 1,
        "car_path": "stockcars chevycamarozl12022",
        "car_version_range": {"minimum_inclusive": "1", "maximum_inclusive": "1"},
        "iracing_build_range": {"minimum_inclusive": "1", "maximum_inclusive": "1"},
        "front_track_width_m": 1.65,
        "rear_track_width_m": 1.64,
        "wheel_speed_semantics": "SI wheel peripheral speed at each corner",
        "body_axis_convention": "x forward, y left, z up; yaw positive left",
        "source_provenance": [
            {
                "source_kind": "controlled_repository_evidence",
                "source_id": "test-only-verified-geometry",
                "description": "Synthetic source-backed geometry for contract tests.",
            }
        ],
    }
    return build_vehicle_engineering_profile(payload)


def test_contracts_forbid_force_grip_and_thermal_overclaims() -> None:
    assert "wheel_load" in CHASSIS_RESPONSE_CONTRACT.forbidden_claims
    assert "tire_force" in RELATIVE_SLIP_EXPOSURE_CONTRACT.forbidden_claims
    assert "brake_energy" in BRAKE_EXPOSURE_CONTRACT.forbidden_claims
    assert "thermal_energy" in TIRE_THERMAL_RESPONSE_CONTRACT.forbidden_claims
    assert "friction_circle" in COMBINED_ACCELERATION_CONTRACT.forbidden_claims
    assert "damper_setup_recommendation" in TRACK_DISTURBANCE_CONTRACT.forbidden_claims
    assert all(
        contract.authority_ceiling == "observation_only"
        for contract in (
            CHASSIS_RESPONSE_CONTRACT,
            RELATIVE_SLIP_EXPOSURE_CONTRACT,
            BRAKE_EXPOSURE_CONTRACT,
            TIRE_THERMAL_RESPONSE_CONTRACT,
            COMBINED_ACCELERATION_CONTRACT,
            TRACK_DISTURBANCE_CONTRACT,
        )
    )


def test_chassis_response_is_limited_to_distributions_without_verified_bands() -> None:
    result = analyze_chassis_response(
        _rows(), window=_window(), lap_eligible=True, expected_sample_rate_hz=10.0
    )
    assert result.status == "limited"
    assert result.artifact is not None
    assert result.artifact.damper_band_classification_available is False
    dumped = result.artifact.model_dump_json()
    assert "wheel_load" not in dumped
    assert "spring_force" not in dumped


def test_corner_slip_fails_closed_without_geometry_but_straight_is_available() -> None:
    corner = _window().model_copy(update={"phase": "center"})
    blocked = analyze_relative_slip_exposure(
        _rows(), window=corner, lap_eligible=True, expected_sample_rate_hz=10.0
    )
    assert blocked.status == "blocked"
    assert any("track widths" in reason for reason in blocked.blocker_reasons)
    ready = analyze_relative_slip_exposure(
        _rows(), window=_window(), lap_eligible=True, expected_sample_rate_hz=10.0
    )
    assert ready.status == "ready"
    assert ready.artifact is not None
    assert ready.artifact.geometry_basis == "straight_line"


def test_corner_slip_requires_and_binds_verified_profile() -> None:
    corner = _window().model_copy(update={"phase": "center"})
    result = analyze_relative_slip_exposure(
        pl.DataFrame(_rows()),
        window=corner,
        lap_eligible=True,
        profile=_geometry_profile(),
        expected_sample_rate_hz=10.0,
    )
    assert result.status == "ready"
    assert result.artifact is not None
    assert result.artifact.geometry_basis == "verified_vehicle_profile"
    assert result.artifact.vehicle_profile_hash == _geometry_profile().profile_hash


def test_brake_exposure_is_pressure_velocity_not_energy() -> None:
    result = analyze_brake_pressure_velocity_exposure(
        _rows(), window=_window(), lap_eligible=True, expected_sample_rate_hz=10.0
    )
    assert result.status == "ready"
    assert result.artifact is not None
    assert result.artifact.front_exposure_fraction is not None
    assert 0.0 <= result.artifact.abs_intervention_fraction <= 1.0
    assert "energy" not in result.artifact.model_dump_json().lower()


def test_thermal_response_excludes_constant_and_snapshot_channels() -> None:
    semantics = {}
    for corner in ("lf", "rf", "lr", "rr"):
        for suffix in (
            "temp_inner",
            "temp_middle",
            "temp_outer",
            "pressure",
            "tire_distance_m",
        ):
            semantics[f"{corner}_{suffix}"] = ChannelUpdateSemantic.CONTINUOUS
        semantics[f"{corner}_carcass_temp_l"] = ChannelUpdateSemantic.CONSTANT
        semantics[f"{corner}_wear_inner"] = ChannelUpdateSemantic.PIT_SNAPSHOT
    result = analyze_tire_thermal_response(
        _rows(),
        window=_window(),
        lap_eligible=True,
        channel_semantics=semantics,
        associated_slip_artifact_ids=("slip:1",),
        expected_sample_rate_hz=10.0,
    )
    assert result.status == "limited"
    assert result.artifact is not None
    assert "rf_carcass_temp_l" in result.artifact.snapshot_channels_excluded
    assert "rr_wear_inner" in result.artifact.snapshot_channels_excluded
    assert not set(result.artifact.snapshot_channels_excluded) & set(
        result.artifact.continuous_source_channels
    )


def test_combined_acceleration_stays_raw_and_row_frame_parity() -> None:
    row_result = analyze_combined_acceleration_occupancy(
        _rows(), window=_window(), lap_eligible=True, expected_sample_rate_hz=10.0
    )
    frame_result = analyze_combined_acceleration_occupancy(
        pl.DataFrame(_rows()),
        window=_window(),
        lap_eligible=True,
        expected_sample_rate_hz=10.0,
    )
    assert row_result.artifact == frame_result.artifact
    assert row_result.artifact is not None
    assert row_result.artifact.gravity_compensated is False
    assert row_result.artifact.banking_compensated is False


def test_disturbance_requires_repetition_and_separates_observations() -> None:
    blocked = build_track_disturbance_signature(
        [(_window(), _rows())],
        lap_eligibility={4: True},
        track_identity="atlanta",
        build_identity="2026.02",
        source_artifact_ids=("lap4:event",),
        expected_sample_rate_hz=10.0,
    )
    assert blocked.status == "blocked"
    second_rows = deepcopy(_rows(lap=5, start=20.0))
    second = _window(lap=5, start=20.0)
    result = build_track_disturbance_signature(
        [(_window(), _rows()), (second, second_rows)],
        lap_eligibility={4: True, 5: True},
        track_identity="atlanta",
        build_identity="2026.02",
        source_artifact_ids=("lap4:event", "lap5:event"),
        expected_sample_rate_hz=10.0,
    )
    assert result.status == "ready"
    assert result.artifact is not None
    assert result.artifact.repetition_count == 2
    assert set(result.artifact.corner_response_sequence) == {"lf", "rf", "lr", "rr"}
    assert "not attributed" in result.artifact.driver_response_observation
    assert "not directly measured" in result.artifact.track_input_observation
    assert "recommend" not in result.artifact.model_dump_json().lower()


def test_junk_lap_cannot_create_any_exposure() -> None:
    result = analyze_combined_acceleration_occupancy(
        _rows(), window=_window(), lap_eligible=False, expected_sample_rate_hz=10.0
    )
    assert result.status == "blocked"
    assert result.artifact is None
