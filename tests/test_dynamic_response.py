from __future__ import annotations

import math
from typing import Mapping

import pytest

from racelab_engine.analysis.dynamic_response import (
    BRAKE_THROTTLE_RESPONSE_CONTRACTS,
    VEHICLE_INPUT_RESPONSE_CONTRACTS,
    analyze_brake_throttle_dynamic_response,
)
from racelab_engine.models.dynamic_response import DynamicResponseSignature
from racelab_engine.services.p3_observation_bridge import p3_observation_columns


_RATE_HZ = 60.0
_SAMPLES = 140


def _brake(index: int) -> float:
    if index < 20:
        return 0.0
    if index < 30:
        return float((index - 19) * 8)
    if index < 50:
        return 80.0
    if index < 60:
        return float(max(0, 80 - (index - 49) * 8))
    return 0.0


def _throttle(index: int) -> float:
    if index < 75:
        return 0.0
    if index < 85:
        return float((index - 74) * 10)
    return 100.0


def _steering(index: int) -> float:
    if index < 8:
        return 0.0
    if index < 16:
        return float((index - 7) * 1.25)
    if index < 28:
        return 10.0
    if index < 36:
        return float(max(0.0, 10.0 - (index - 27) * 1.25))
    return 0.0


def _phase(index: int) -> str:
    if 8 <= index < 20:
        return "turn_in"
    if 20 <= index < 50:
        return "brake_application"
    if 50 <= index < 70:
        return "brake_release"
    if index >= 75:
        return "initial_throttle"
    return "straight"


def _rows(
    *,
    lap_count: int = 2,
    omit: str | None = None,
    nonfinite: str | None = None,
    tick_gap: bool = False,
    duplicate_session_time: bool = True,
    inactive_laps: tuple[int, ...] = (),
    profile_shift_by_lap: Mapping[int, int] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    pressure_factors = {
        "lf_brake_line_pressure_bar": 1.00,
        "rf_brake_line_pressure_bar": 0.98,
        "lr_brake_line_pressure_bar": 0.72,
        "rr_brake_line_pressure_bar": 0.70,
    }
    for lap_number in range(1, lap_count + 1):
        inactive = lap_number in inactive_laps
        profile_shift = (profile_shift_by_lap or {}).get(lap_number, 0)
        lap_start = (lap_number - 1) * 10.0
        for index in range(_SAMPLES):
            profile_index = index - profile_shift
            brake_pressure_input = (
                0.0 if inactive else _brake(max(0, profile_index - 2))
            )
            brake_accel_input = (
                0.0 if inactive else _brake(max(0, profile_index - 3))
            )
            throttle_accel_input = (
                0.0 if inactive else _throttle(max(0, profile_index - 2))
            )
            yaw_brake_input = (
                0.0 if inactive else _brake(max(0, profile_index - 4))
            )
            yaw_throttle_input = (
                0.0 if inactive else _throttle(max(0, profile_index - 3))
            )
            steering_yaw_input = (
                0.0 if inactive else _steering(max(0, profile_index - 2))
            )
            session_time = lap_start + index / _RATE_HZ
            if duplicate_session_time and index == 26:
                session_time = lap_start + (index - 1) / _RATE_HZ
            tick = (lap_number - 1) * _SAMPLES + index
            if tick_gap and lap_number == 2 and index >= 40:
                tick += 1
            row: dict[str, object] = {
                "run_id": "run-response",
                "lap": lap_number,
                "lap_number": lap_number,
                "session_tick": tick,
                "session_time": session_time,
                "lap_dist_pct_100": index / (_SAMPLES - 1) * 100.0,
                "speed_mps": 42.0 + 0.01 * index,
                "brake_pct": 0.0 if inactive else _brake(profile_index),
                "throttle_pct": 0.0 if inactive else _throttle(profile_index),
                "steering_deg": 0.0 if inactive else _steering(profile_index),
                "long_accel": (
                    -0.04 * brake_accel_input + 0.025 * throttle_accel_input
                ),
                "yaw_rate": (
                    0.01 * yaw_brake_input
                    + 0.002 * yaw_throttle_input
                    + 0.01 * steering_yaw_input
                ),
                "engineering_phase": (
                    "straight" if inactive else _phase(profile_index)
                ),
            }
            row.update({
                channel: factor * brake_pressure_input
                for channel, factor in pressure_factors.items()
            })
            if omit is not None:
                row.pop(omit, None)
            if nonfinite is not None and 18 <= index <= 110:
                row[nonfinite] = math.nan
            rows.append(row)
    return rows


def _analyze(rows: list[dict[str, object]], *, laps: tuple[int, ...] = (1, 2)):
    return analyze_brake_throttle_dynamic_response(
        rows,
        run_id="run-response",
        setup_id="setup-response",
        eligible_lap_numbers=laps,
        expected_sample_rate_hz=_RATE_HZ,
    )


def _signatures(report) -> tuple[DynamicResponseSignature, ...]:
    return tuple(
        signature
        for path in report.paths
        for signature in path.signatures
    )


def test_existing_p3_projection_owns_every_dynamic_response_source_channel() -> None:
    projected = set(p3_observation_columns())
    required = {
        channel
        for contract in BRAKE_THROTTLE_RESPONSE_CONTRACTS
        for channel in contract.required_channels
    }

    assert required <= projected


def test_brake_throttle_signatures_use_qualified_clock_and_distinct_laps() -> None:
    report = _analyze(_rows())

    assert report.status == "ready"
    assert len(report.paths) == len(VEHICLE_INPUT_RESPONSE_CONTRACTS) == 14
    assert all(binding.clock_state == "qualified" for binding in report.clock_bindings)
    assert all(binding.primary_clock == "session_tick" for binding in report.clock_bindings)
    assert all(not binding.blockers for binding in report.clock_bindings)
    # Duplicate simulator timestamps are retained by the qualified clock but do
    # not erase contiguous tick-clock response timing.
    assert all(
        binding.clock_id.startswith("telemetry-clock:")
        for binding in report.clock_bindings
    )

    signatures = _signatures(report)
    assert len(signatures) == 14
    for signature in signatures:
        assert signature.repeatability.independent_lap_numbers == (1, 2)
        assert signature.repeatability.independent_lap_count == 2
        assert len(signature.episodes) == 2
        assert signature.canonical_clock_blockers == ()
        assert signature.median_observed_lag_s >= 0.0
        assert signature.median_peak_gain is not None
        assert signature.gain_unit.endswith("/%")
        assert signature.speed_band.minimum_mps > 0.0
        assert signature.physical_scope.lap_pct_start <= (
            signature.physical_scope.input_onset_lap_pct
        ) <= signature.physical_scope.lap_pct_end
        for episode in signature.episodes:
            assert episode.response_onset_time_s - episode.input_onset_time_s == (
                pytest.approx(episode.observed_lag_s)
            )
            assert episode.canonical_clock_state == "qualified"
            assert episode.canonical_clock_blockers == ()
            assert episode.sample_count >= 3


def test_missing_response_channel_blocks_only_its_exact_paths() -> None:
    report = _analyze(_rows(omit="rr_brake_line_pressure_bar"))

    assert report.status == "partial"
    rr_paths = [
        path
        for path in report.paths
        if path.contract.response_channel == "rr_brake_line_pressure_bar"
    ]
    assert len(rr_paths) == 2
    assert all(path.status == "blocked" for path in rr_paths)
    assert all(
        "missing_required_channel:rr_brake_line_pressure_bar"
        in path.blocker_reasons
        for path in rr_paths
    )
    assert any(path.status == "ready" for path in report.paths)
    assert not any(
        signature.contract.response_channel == "rr_brake_line_pressure_bar"
        for signature in _signatures(report)
    )


def test_tick_discontinuity_blocks_every_timing_signature() -> None:
    report = _analyze(_rows(tick_gap=True))

    assert report.status == "blocked"
    assert not _signatures(report)
    blocked_clock = next(
        binding for binding in report.clock_bindings if binding.lap_number == 2
    )
    assert blocked_clock.clock_state == "blocked"
    assert "tick_discontinuity" in blocked_clock.blockers
    assert any("tick_discontinuity" in reason for reason in report.blocker_reasons)


def test_nonfinite_response_never_becomes_a_numeric_signature() -> None:
    report = _analyze(_rows(nonfinite="yaw_rate"))

    assert report.status == "partial"
    yaw_paths = [
        path for path in report.paths if path.contract.response_channel == "yaw_rate"
    ]
    assert len(yaw_paths) == 4
    assert all(path.status == "blocked" for path in yaw_paths)
    assert not any(
        signature.contract.response_channel == "yaw_rate"
        for signature in _signatures(report)
    )
    serialized = report.model_dump(mode="json")
    assert "NaN" not in str(serialized)


def test_rows_and_one_lap_episode_do_not_create_repeatability() -> None:
    report = _analyze(_rows(inactive_laps=(2,)))

    assert report.status == "blocked"
    assert not _signatures(report)
    measured_paths = [
        path for path in report.paths if path.detected_episode_count > 0
    ]
    assert measured_paths
    assert all(path.independent_lap_count == 1 for path in measured_paths)
    assert all(
        any("requires_2_distinct_eligible_laps" in reason for reason in path.blocker_reasons)
        for path in measured_paths
    )


def test_far_apart_same_phase_events_cannot_form_a_ready_signature() -> None:
    report = _analyze(_rows(profile_shift_by_lap={2: 60}))

    lf_application = next(
        path
        for path in report.paths
        if ".brake_application.lf_brake_line_pressure_bar."
        in path.contract.contract_id
    )
    assert lf_application.detected_episode_count == 2
    assert lf_application.independent_lap_count == 2
    assert lf_application.status == "blocked"
    assert not lf_application.signatures
    assert any(
        "insufficient_physically_corresponding_episodes" in reason
        for reason in lf_application.blocker_reasons
    )


def test_dynamic_response_artifacts_cannot_gain_cause_or_setup_authority() -> None:
    report = _analyze(_rows())

    assert report.authority == "observation_only"
    assert report.cause_authorized is False
    assert report.setup_authorized is False
    for signature in _signatures(report):
        assert signature.authority == "observation_only"
        assert signature.cause_authorized is False
        assert signature.setup_authorized is False
        for episode in signature.episodes:
            assert episode.authority == "observation_only"
            assert episode.cause_authorized is False
            assert episode.setup_authorized is False

    payload = _signatures(report)[0].model_dump(mode="json")
    payload["setup_authorized"] = True
    with pytest.raises(ValueError):
        DynamicResponseSignature.model_validate(payload)
