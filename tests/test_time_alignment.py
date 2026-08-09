from __future__ import annotations

import math

import pytest
from fastapi import HTTPException

from racelab_engine.analysis.time_alignment import (
    analyze_time_alignment,
    build_layered_alignment,
    detect_engineering_phases,
    estimate_driver_noise,
    nearest_sorted_index,
)


def _lap_rows(
    *,
    speed_mps: float = 50.0,
    start_pct: int = 0,
    end_pct: int = 100,
    with_geometry: bool = True,
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    elapsed = 0.0
    previous_distance_m = start_pct * 100.0 / 3.280839895
    for pct in range(start_pct, end_pct + 1):
        distance_ft = pct * 100.0
        distance_m = distance_ft / 3.280839895
        elapsed += (distance_m - previous_distance_m) / speed_mps
        previous_distance_m = distance_m
        row = {
            "lap_dist_pct_100": float(pct),
            "lap_dist_ft": distance_ft,
            "session_time": elapsed,
            "speed_mps": speed_mps,
            "throttle_pct": 100.0,
            "brake_pct": 0.0,
            "steering_deg": 0.0,
            "yaw_rate": 0.0,
            "lat_accel": 0.0,
            "vert_accel": 9.80665,
        }
        if with_geometry:
            angle = 2 * math.pi * pct / 100.0
            row.update({
                "lat": 33.0 + 0.001 * math.sin(angle),
                "lon": -84.0 + 0.001 * math.cos(angle),
                "alt": 300.0 + math.sin(3 * angle),
            })
        rows.append(row)
    return rows


def _fractional_lap_rows(
    *,
    speed_mps: float,
    start_pct: float,
    end_pct: float,
    step_pct: float,
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    pct = start_pct
    while pct <= end_pct + 1e-9:
        distance_ft = pct * 100.0
        angle = 2 * math.pi * pct / 100.0
        rows.append({
            "lap_dist_pct_100": round(pct, 6),
            "lap_dist_ft": distance_ft,
            "session_time": (distance_ft / 3.280839895) / speed_mps,
            "speed_mps": speed_mps,
            "throttle_pct": 100.0,
            "brake_pct": 0.0,
            "steering_deg": 0.0,
            "yaw_rate": 0.0,
            "lat_accel": 0.0,
            "vert_accel": 9.80665,
            "lat": 33.0 + 0.001 * math.sin(angle),
            "lon": -84.0 + 0.001 * math.cos(angle),
            "alt": 300.0 + math.sin(3 * angle),
        })
        pct += step_pct
    return rows


def _noise_context() -> dict[str, object]:
    return {
        "baseline_driver_identity": "driver-7",
        "test_driver_identity": "driver-7",
        "car": "car-1",
        "car_version": "v1",
        "track": "track-1",
        "track_configuration": "oval",
        "track_version": "v2",
        "baseline_setup_fingerprint": "setup-a",
        "test_setup_fingerprint": "setup-b",
        "baseline_tire_age_range_m": [1000.0, 1200.0],
        "test_tire_age_range_m": [1000.0, 1200.0],
        "baseline_fuel_range": [30.0, 31.0],
        "test_fuel_range": [30.0, 31.0],
        "baseline_weather_range": {"air_temp": [20.0, 21.0], "track_temp": [30.0, 31.0], "wind_vel": [1.0, 2.0]},
        "test_weather_range": {"air_temp": [20.0, 21.0], "track_temp": [30.0, 31.0], "wind_vel": [1.0, 2.0]},
        "run_type": "Test",
        "phase": "per_phase",
        "controlled_setup_change_count": 1,
        "unmapped_setup_changes": False,
    }


@pytest.mark.parametrize(
    ("target", "expected"),
    [(-1.0, 0), (0.0, 0), (0.49, 0), (0.5, 0), (0.51, 1), (2.0, 2), (3.0, 2)],
)
def test_nearest_sorted_index_is_bounded_and_resolves_ties_low(
    target: float,
    expected: int,
) -> None:
    assert nearest_sorted_index([0.0, 1.0, 2.0], target) == expected


def test_phase_engine_detects_sustained_brake_corner_apex_and_exit() -> None:
    rows = _lap_rows()
    for row in rows:
        pct = row["lap_dist_pct_100"]
        if 20 <= pct < 24:
            row["throttle_pct"] = 0.0
        if 24 <= pct < 29:
            row["throttle_pct"] = 0.0
            row["brake_pct"] = 80.0 if pct <= 26 else 25.0
        if 27 <= pct <= 39:
            row["steering_deg"] = 12.0
            row["yaw_rate"] = 0.25
            row["lat_accel"] = 7.0
            row["speed_mps"] = 35.0 + abs(pct - 33.0)
            row["throttle_pct"] = max(0.0, (pct - 32.0) * 14.0)
        if pct == 60:
            row["vert_accel"] = 18.0
            row["lf_shock_vel_in_s"] = 14.0

    phase_by_position, intervals, _channels = detect_engineering_phases(
        rows,
        grid=[float(value) for value in range(101)],
    )

    observed = set(phase_by_position)
    assert "threshold_braking" in observed
    assert "entry" in observed or "turn_in" in observed
    assert "apex_region" in observed
    assert "initial_throttle" in observed
    assert "full_throttle_exit" in observed
    assert "following_straight_carry" in observed
    assert "bump_curb" not in observed  # one-bin transient cannot dominate a phase
    assert all(interval.end_pct >= interval.start_pct for interval in intervals)


def test_layered_alignment_is_monotonic_and_reports_physical_methods() -> None:
    grid = [float(value) for value in range(101)]
    baseline = _lap_rows()
    test = _lap_rows()
    for rows in (baseline, test):
        for row in rows:
            pct = row["lap_dist_pct_100"]
            row["yaw_rate"] = 0.3 * math.sin(4 * math.pi * pct / 100.0)
            row["vert_accel"] = 9.80665 + math.sin(10 * math.pi * pct / 100.0)
            row["brake_pct"] = 70.0 if 20 <= pct <= 25 else 0.0
    points, _baseline, _test = build_layered_alignment(baseline, test, grid)

    aligned = [point.aligned_test_pct for point in points if point.aligned_test_pct is not None]
    assert aligned == sorted(aligned)
    assert all(not point.is_gap for point in points)
    assert all("lap_percentage" in point.methods for point in points)
    assert any("gps_geometry" in point.methods for point in points)
    assert any("yaw_curvature" in point.methods for point in points)
    assert any("road_profile" in point.methods for point in points)
    assert any("braking_onset_anchor" in point.methods for point in points)
    assert all(point.uncertainty_pct is not None for point in points)


def test_local_spike_does_not_inflate_road_profile_confidence_around_whole_lap() -> None:
    baseline = _lap_rows(with_geometry=False)
    test = _lap_rows(with_geometry=False)
    for row in [*baseline, *test]:
        row["lf_shock_defl_in"] = 0.0
    baseline[50]["lf_shock_defl_in"] = 0.5
    test[50]["lf_shock_defl_in"] = 0.5
    points, _baseline, _test = build_layered_alignment(
        baseline,
        test,
        [float(value) for value in range(101)],
    )

    assert "road_profile" in points[50].methods
    assert all("road_profile" not in point.methods for point in points[:40])
    assert all("road_profile" not in point.methods for point in points[61:])


def test_distant_gps_spike_does_not_inflate_local_geometry_confidence() -> None:
    baseline = _lap_rows(with_geometry=False)
    test = _lap_rows(with_geometry=False)
    for row in [*baseline, *test]:
        row.pop("lap_dist_ft", None)
        row["lat"] = 33.0
        row["lon"] = -84.0
    baseline[50].update({"lat": 33.001, "lon": -84.001})
    test[50].update({"lat": 33.001, "lon": -84.001})
    points, _baseline, _test = build_layered_alignment(
        baseline,
        test,
        [float(value) for value in range(101)],
    )

    assert all("gps_geometry" not in point.methods for point in points[:40])
    assert all("gps_geometry" not in point.methods for point in points[61:])


def test_controlled_many_to_one_alignment_recovers_from_local_geometric_shift() -> None:
    baseline = _lap_rows()
    test = _lap_rows()
    for row in [*baseline, *test]:
        row.pop("lap_dist_ft", None)
    shifted = [(test[min(index + 1, 100)]["lat"], test[min(index + 1, 100)]["lon"]) for index in range(101)]
    for row, (lat, lon) in zip(test, shifted):
        row["lat"] = lat
        row["lon"] = lon

    points, _baseline, _test = build_layered_alignment(
        baseline,
        test,
        [float(value) for value in range(101)],
    )
    aligned = [point.aligned_test_pct for point in points]

    assert all(value is not None for value in aligned)
    assert aligned == sorted(aligned)  # type: ignore[type-var]
    assert len(set(aligned)) < len(aligned)  # controlled local reuse, not a forced end gap


def test_alignment_never_extrapolates_and_preserves_honest_gaps() -> None:
    result = analyze_time_alignment(
        _lap_rows(),
        _lap_rows(start_pct=10, end_pct=90),
        step_pct=1.0,
    )

    assert result.coverage_fraction < 0.9
    assert result.alignment[0].is_gap
    assert result.alignment[-1].is_gap
    assert result.cumulative_delta_s[0] is None
    assert result.cumulative_delta_s[-1] is None
    assert any("remain gaps" in warning for warning in result.warnings)


def test_sampling_sized_full_lap_boundary_is_admitted_by_bounded_circular_rule() -> None:
    result = analyze_time_alignment(
        _fractional_lap_rows(speed_mps=50.0, start_pct=0.2, end_pct=99.8, step_pct=0.2),
        _fractional_lap_rows(speed_mps=52.0, start_pct=0.2, end_pct=99.8, step_pct=0.2),
        step_pct=1.0,
    )

    assert result.time_delta_complete is True
    assert not result.alignment[0].is_gap
    assert not result.alignment[-1].is_gap
    assert "bounded_circular_boundary" in result.alignment[0].methods
    assert "bounded_circular_boundary" in result.alignment[-1].methods
    assert result.alignment[0].confidence <= 0.7


def test_wide_full_lap_boundary_omission_remains_a_gap() -> None:
    result = analyze_time_alignment(
        _fractional_lap_rows(speed_mps=50.0, start_pct=2.0, end_pct=98.0, step_pct=0.2),
        _fractional_lap_rows(speed_mps=52.0, start_pct=2.0, end_pct=98.0, step_pct=0.2),
        step_pct=1.0,
    )

    assert result.time_delta_complete is False
    assert result.alignment[0].is_gap
    assert result.alignment[-1].is_gap
    assert "bounded_circular_boundary" not in result.source_channels


def test_circular_boundary_rule_never_repairs_an_interior_gap() -> None:
    baseline = _fractional_lap_rows(speed_mps=50.0, start_pct=0.2, end_pct=99.8, step_pct=0.2)
    test = [
        row for row in _fractional_lap_rows(
            speed_mps=52.0, start_pct=0.2, end_pct=99.8, step_pct=0.2,
        )
        if not 40.0 <= row["lap_dist_pct_100"] <= 60.0
    ]
    result = analyze_time_alignment(baseline, test, step_pct=1.0)

    assert result.time_delta_complete is False
    assert not result.alignment[0].is_gap
    assert not result.alignment[-1].is_gap
    assert any(point.is_gap for point in result.alignment[40:61])


def test_interior_gap_cannot_emit_a_complete_or_theoretical_lap_effect() -> None:
    test_rows = [
        row for row in _lap_rows(speed_mps=52.0)
        if not 40 <= row["lap_dist_pct_100"] <= 60
    ]
    result = analyze_time_alignment(
        _lap_rows(speed_mps=50.0),
        test_rows,
        step_pct=1.0,
    )

    assert result.time_delta_complete is False
    assert result.selected_effect_s is None
    assert result.theoretical_opportunity_s is None
    assert any(point.is_gap for point in result.alignment[40:61])


def test_cumulative_time_integrates_reciprocal_speed_at_physical_positions() -> None:
    result = analyze_time_alignment(
        _lap_rows(speed_mps=50.0),
        _lap_rows(speed_mps=52.0),
        baseline_lap_times_s=[61.0, 60.9, 61.1, 61.0],
        test_lap_times_s=[60.7, 60.6, 60.8, 60.7],
        step_pct=1.0,
    )

    expected = (10_000.0 / 3.280839895) * (1 / 52.0 - 1 / 50.0)
    assert result.selected_effect_s == pytest.approx(expected, abs=0.01)
    assert result.selected_effect_s is not None and result.selected_effect_s < 0
    assert result.gain_origin_pct is not None
    assert result.theoretical_opportunity_s == pytest.approx(abs(expected), abs=0.01)
    assert result.distance_basis == "reciprocal_speed_integration"
    assert result.phase_effects
    assert all(effect.evidence_state == "calculated" for effect in result.phase_effects if effect.delta_s is not None)
    assert all(effect.source_channels for effect in result.phase_effects)


def test_time_basis_reports_actual_timing_fallback_when_speed_is_missing() -> None:
    baseline = _lap_rows(speed_mps=50.0)
    test = _lap_rows(speed_mps=52.0)
    for row in [*baseline, *test]:
        row.pop("speed_mps", None)
        row.pop("speed_mph", None)
    result = analyze_time_alignment(baseline, test, step_pct=1.0)

    assert result.distance_basis == "aligned_timing_boundaries"
    assert {basis for basis in result.incremental_basis if basis is not None} == {"aligned_timing_boundaries"}
    assert all(
        effect.calculation_basis == "aligned_timing_boundaries"
        for effect in result.phase_effects
        if effect.delta_s is not None
    )
    assert all("speed_mps" not in effect.source_channels for effect in result.phase_effects)


def test_slower_test_has_no_gain_origin_or_repeatable_opportunity() -> None:
    result = analyze_time_alignment(
        _lap_rows(speed_mps=52.0),
        _lap_rows(speed_mps=50.0),
        baseline_lap_times_s=[59.7, 59.8, 59.6, 59.7],
        test_lap_times_s=[60.0, 60.1, 59.9, 60.0],
        step_pct=1.0,
    )

    assert result.selected_effect_s is not None and result.selected_effect_s > 0
    assert result.gain_origin_pct is None
    assert result.gain_origin_phase is None
    assert result.theoretical_opportunity_s is None
    assert result.repeatable_opportunity_s is None


def test_repeatable_cohort_cannot_override_zero_selected_physical_effect() -> None:
    result = analyze_time_alignment(
        _lap_rows(speed_mps=50.0),
        _lap_rows(speed_mps=50.0),
        baseline_lap_times_s=[60.0, 60.0, 60.0],
        test_lap_times_s=[59.0, 59.0, 59.0],
        noise_context_key=_noise_context(),
        step_pct=1.0,
    )

    assert result.selected_effect_s == 0.0
    assert result.noise.is_repeatable is True
    assert result.repeatable_opportunity_s is None


def test_reset_action_state_alone_does_not_prove_a_reset_phase() -> None:
    rows = _lap_rows()
    for row in rows[40:46]:
        row["enter_exit_reset_state"] = 2.0

    phases, _intervals, _channels = detect_engineering_phases(
        rows,
        grid=[float(value) for value in range(101)],
    )

    assert "reset" not in phases


def test_reset_phase_requires_action_state_and_position_discontinuity() -> None:
    rows = _lap_rows()
    rows[45]["enter_exit_reset_state"] = 2.0
    rows[45]["lap_dist_pct_100"] = 10.0

    phases, _intervals, _channels = detect_engineering_phases(
        rows,
        grid=[float(value) for value in range(101)],
    )

    assert "reset" in phases


def test_enter_exit_state_is_not_misclassified_as_reset() -> None:
    rows = _lap_rows()
    rows[45]["enter_exit_reset_state"] = 1.0
    rows[45]["lap_dist_pct_100"] = 10.0

    phases, _intervals, _channels = detect_engineering_phases(
        rows,
        grid=[float(value) for value in range(101)],
    )

    assert "reset" not in phases


def test_boolean_pit_state_is_preserved_by_phase_sampling() -> None:
    rows = _lap_rows()
    for row in rows[10:16]:
        row["on_pit_road"] = True

    phases, _intervals, _channels = detect_engineering_phases(
        rows,
        grid=[float(value) for value in range(101)],
    )

    assert "pit" in phases


def test_noise_floor_uses_paired_laps_not_telemetry_samples() -> None:
    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9, 60.0, 60.05],
        [59.7, 59.8, 59.6, 59.7, 59.75],
        context_key=_noise_context(),
    )

    assert noise.experiment_unit == "eligible_lap"
    assert noise.paired_lap_differences == 5
    assert noise.median_effect_s == pytest.approx(-0.3)
    assert noise.bootstrap_high_s is not None and noise.bootstrap_high_s < 0
    assert noise.is_repeatable is True
    assert noise.aba_consistency == "not_available_without_restored_baseline"


def test_phase_noise_uses_lap_level_cohorts_and_context_key() -> None:
    baseline_laps = [_lap_rows(speed_mps=speed) for speed in (49.9, 50.0, 50.1, 50.0)]
    test_laps = [_lap_rows(speed_mps=speed) for speed in (51.9, 52.0, 52.1, 52.0)]
    result = analyze_time_alignment(
        baseline_laps[1],
        test_laps[1],
        baseline_lap_times_s=[61.1, 61.0, 60.9, 61.0],
        test_lap_times_s=[58.8, 58.7, 58.6, 58.7],
        baseline_lap_rows=baseline_laps,
        test_lap_rows=test_laps,
        noise_context_key=_noise_context(),
        step_pct=1.0,
    )

    straight = result.noise.phase_estimates["straight"]
    assert straight["experiment_unit"] == "eligible_lap"
    assert straight["paired_lap_differences"] == 4
    assert result.noise.context_key["baseline_driver_identity"] == "driver-7"
    assert not any("do not pool" in warning for warning in result.noise.warnings)


def test_noise_floor_refuses_strong_claim_from_two_laps() -> None:
    noise = estimate_driver_noise([60.0, 60.0], [59.0, 59.0])

    assert noise.is_repeatable is None
    assert noise.bootstrap_low_s is None
    assert any("three paired eligible laps" in warning for warning in noise.warnings)


def test_repeatability_fails_closed_when_context_key_is_incomplete() -> None:
    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9, 60.0],
        [59.7, 59.8, 59.6, 59.7],
        context_key={"baseline_driver_identity": "driver-7", "test_driver_identity": "driver-7", "car": "car-1"},
    )

    assert noise.bootstrap_high_s is not None and noise.bootstrap_high_s < 0
    assert noise.is_repeatable is None
    assert noise.context_complete is False
    assert "track identity" in noise.context_blockers
    assert any("Repeatability is blocked" in warning for warning in noise.warnings)


def test_repeatability_fails_closed_when_fuel_context_is_not_matched() -> None:
    context = _noise_context()
    context["test_fuel_range"] = [24.0, 25.0]
    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9, 60.0],
        [59.7, 59.8, 59.6, 59.7],
        context_key=context,
    )

    assert noise.is_repeatable is None
    assert "matched fuel range" in noise.context_blockers


def test_repeatability_fails_closed_for_different_drivers() -> None:
    context = _noise_context()
    context["test_driver_identity"] = "driver-8"
    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9],
        [59.7, 59.8, 59.6],
        context_key=context,
    )

    assert noise.is_repeatable is None
    assert "same driver" in noise.context_blockers


def test_repeatability_fails_closed_for_uncontrolled_fuel_span() -> None:
    context = _noise_context()
    context["baseline_fuel_range"] = [0.0, 100.0]
    context["test_fuel_range"] = [0.0, 100.0]
    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9],
        [59.7, 59.8, 59.6],
        context_key=context,
    )

    assert noise.is_repeatable is None
    assert "narrow baseline fuel range" in noise.context_blockers
    assert "narrow test fuel range" in noise.context_blockers


@pytest.mark.parametrize(
    ("path", "invalid_value", "expected_blocker"),
    [
        (("baseline_tire_age_range_m",), [math.nan, 1_200.0], "baseline tire age"),
        (("test_tire_age_range_m",), [1_000.0, math.inf], "test tire age"),
        (("baseline_fuel_range",), ["30.0", 31.0], "baseline fuel range"),
        (("test_fuel_range",), [30.0], "test fuel range"),
        (("baseline_fuel_range",), [True, 31.0], "baseline fuel range"),
        (("baseline_weather_range", "air_temp"), [21.0, 20.0], "baseline weather range"),
        (("test_weather_range", "track_temp"), [30.0, None], "test weather range"),
        (("baseline_weather_range", "wind_vel"), [-1.0, 1.0], "baseline weather range"),
        (("test_weather_range", "air_temp"), [-101.0, 20.0], "test weather range"),
    ],
)
def test_repeatability_fails_closed_for_invalid_numeric_context_ranges(
    path: tuple[str, ...],
    invalid_value: object,
    expected_blocker: str,
) -> None:
    context = _noise_context()
    target = context
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = invalid_value

    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9, 60.0],
        [59.7, 59.8, 59.6, 59.7],
        context_key=context,
    )

    assert noise.context_complete is False
    assert noise.is_repeatable is None
    assert noise.context_blockers == [expected_blocker]
    assert any("Repeatability is blocked" in warning for warning in noise.warnings)


def test_repeatability_fails_closed_when_weather_channel_range_is_missing() -> None:
    context = _noise_context()
    weather = context["baseline_weather_range"]
    assert isinstance(weather, dict)
    weather.pop("wind_vel")

    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9, 60.0],
        [59.7, 59.8, 59.6, 59.7],
        context_key=context,
    )

    assert noise.context_complete is False
    assert noise.is_repeatable is None
    assert noise.context_blockers == ["baseline weather range"]


def test_boolean_setup_change_count_cannot_pass_the_one_change_gate() -> None:
    context = _noise_context()
    context["controlled_setup_change_count"] = True

    noise = estimate_driver_noise(
        [60.0, 60.1, 59.9],
        [59.7, 59.8, 59.6],
        context_key=context,
    )

    assert noise.context_complete is False
    assert noise.is_repeatable is None
    assert "exactly one mapped setup change" in noise.context_blockers


def test_time_analysis_api_fails_closed_on_missing_compatibility_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api import routes_compare

    class _Repository:
        def get_overview(self, _run_id: str) -> object:
            return object()

    monkeypatch.setattr(routes_compare, "repository", lambda: _Repository())
    monkeypatch.setattr(routes_compare, "_assert_run_compatibility", lambda *_args: ["car version"])

    with pytest.raises(HTTPException) as raised:
        routes_compare.get_time_analysis(routes_compare.TimeAnalysisRequest(
            baseline_run_id="baseline",
            test_run_id="test",
        ))

    assert raised.value.status_code == 400
    assert "complete compatibility identity" in str(raised.value.detail)
