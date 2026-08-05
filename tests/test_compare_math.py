from __future__ import annotations

import math
from pathlib import Path

import pytest

from racelab_engine.analysis.compare_math import (
    aggregate_channel_stats,
    aggregate_driver_stats,
    aggregate_platform_stats,
    aggregate_shock_comparison,
    aggregate_tire_comparison,
    compute_whole_car_index,
)
from racelab_engine.analysis.comparison import (
    ChannelDeltaStats,
    DriverComparison,
    PlatformComparison,
    PowertrainComparison,
    _shock_dict,
    _tire_dict,
)


def _trace_row(pct: float, **values: float) -> dict[str, float]:
    return {"lap_dist_pct_100": pct, **values}


def test_channel_aggregation_ignores_nan_and_infinity() -> None:
    stats = aggregate_channel_stats(
        {"speed_mph": [100.0] * 9 + [math.nan]},
        {"speed_mph": [101.0] * 9 + [999.0]},
        "speed_mph",
        "Speed",
        "mph",
    )

    assert stats.baseline_avg == 100.0
    assert stats.test_avg == 101.0
    assert stats.delta_avg == 1.0
    assert stats.direction == "better"


def test_channel_aggregation_missing_side_stays_unavailable_not_zero() -> None:
    stats = aggregate_channel_stats({"speed_mph": [100.0]}, {}, "speed_mph", "Speed", "mph")

    assert stats.test_avg is None
    assert stats.delta_avg is None
    assert stats.confidence == 0.0


def test_channel_delta_uses_only_paired_track_positions() -> None:
    baseline = {"speed_mph": [None, *([0.0] * 8), 100.0]}
    test = {"speed_mph": [*([0.0] * 9), None]}

    stats = aggregate_channel_stats(baseline, test, "speed_mph", "Speed", "mph")

    assert stats.delta_avg is None
    assert stats.confidence == 0.0


def test_platform_aggregation_with_missing_channel_keeps_null_delta() -> None:
    baseline = [_trace_row(float(pct), cfs_ride_height_in=0.50) for pct in range(101)]
    test = [_trace_row(float(pct), cfs_ride_height_in=0.55) for pct in range(101)]

    platform = aggregate_platform_stats(baseline, test)

    assert platform.cfs_height is not None
    assert platform.cfs_height.delta_avg == pytest.approx(0.05)
    assert platform.front_avg_rh is not None
    assert platform.front_avg_rh.delta_avg is None


def test_tire_comparison_populates_measured_corner_contract_with_exact_units() -> None:
    baseline = []
    test = []
    for pct in range(101):
        baseline_values: dict[str, float] = {}
        test_values: dict[str, float] = {}
        for corner in ("lf", "rf", "lr", "rr"):
            baseline_values.update({
                f"{corner}_pressure_gain": 2.0,
                f"{corner}_temp_spread": 4.0,
                f"{corner}_wear_spread": 0.5,
            })
            test_values.update({
                f"{corner}_pressure_gain": 3.0,
                f"{corner}_temp_spread": 5.0,
                f"{corner}_wear_spread": 0.75,
            })
        baseline.append(_trace_row(float(pct), **baseline_values))
        test.append(_trace_row(float(pct), **test_values))

    comparison = aggregate_tire_comparison(baseline, test, lap_count=10)
    payload = _tire_dict(comparison)

    assert set(comparison.corners) == {"LF", "RF", "LR", "RR"}
    assert comparison.corners["LF"].tire_pressure_gain is not None
    assert comparison.corners["LF"].tire_pressure_gain.channel == "lf_pressure_gain"
    assert comparison.corners["LF"].tire_pressure_gain.unit == "psi"
    assert comparison.corners["LF"].temp_spread is not None
    assert comparison.corners["LF"].temp_spread.unit == "°C"
    assert comparison.corners["LF"].tire_wear is not None
    assert comparison.corners["LF"].tire_wear.unit == "percentage points"
    assert any("stored in kPa" in warning for warning in comparison.corners["LF"].warnings)
    assert payload["corners"]["LF"]["tire_pressure_gain"]["channel"] == "lf_pressure_gain"


def test_shock_comparison_populates_measured_corner_contract_without_force_claim() -> None:
    baseline = []
    test = []
    for pct in range(101):
        baseline_values = {"shock_activity_index": 2.0, "shock_velocity_rms": 1.0}
        test_values = {"shock_activity_index": 2.2, "shock_velocity_rms": 1.1}
        for corner in ("lf", "rf", "lr", "rr"):
            baseline_values[f"{corner}_shock_velocity_rms"] = 1.0
            baseline_values[f"{corner}_shock_activity_index"] = 2.0
            test_values[f"{corner}_shock_velocity_rms"] = 1.1
            test_values[f"{corner}_shock_activity_index"] = 2.2
        baseline.append(_trace_row(float(pct), **baseline_values))
        test.append(_trace_row(float(pct), **test_values))

    comparison = aggregate_shock_comparison(baseline, test)
    payload = _shock_dict(comparison)

    assert set(comparison.corners) == {"LF", "RF", "LR", "RR"}
    assert comparison.corners["RF"].shock_velocity_rms is not None
    assert comparison.corners["RF"].shock_velocity_rms.unit == "in/s"
    assert comparison.corners["RF"].shock_activity_index is not None
    assert comparison.corners["RF"].shock_activity_index.unit == "index"
    assert any("neither is measured damper force" in warning for warning in comparison.corners["RF"].warnings)
    assert payload["corners"]["RF"]["shock_activity_index"]["channel"] == "rf_shock_activity_index"


def test_raw_tire_pressure_ui_metadata_uses_canonical_kpa_unit() -> None:
    metadata = (
        Path(__file__).resolve().parents[1] / "ui/src/utils/channelMeta.ts"
    ).read_text(encoding="utf-8")

    for corner in ("lf", "rf", "lr", "rr"):
        line = next(
            item for item in metadata.splitlines()
            if item.strip().startswith(f"{corner}_pressure:")
        )
        assert 'unit: "kPa"' in line
        assert 'unit: "psi"' not in line


def test_platform_label_cannot_hide_localized_cfs_compression_behind_positive_mean() -> None:
    baseline = [_trace_row(float(pct), cfs_ride_height_in=0.20) for pct in range(101)]
    test = [
        _trace_row(
            float(pct),
            cfs_ride_height_in=0.10 if 45 <= pct <= 55 else 0.22,
        )
        for pct in range(101)
    ]

    platform = aggregate_platform_stats(baseline, test)

    assert platform.cfs_height is not None
    assert platform.cfs_height.delta_avg is not None
    assert platform.cfs_height.delta_avg > 0
    assert platform.cfs_height.delta_low_p05 is not None
    assert platform.cfs_height.delta_low_p05 < -0.01
    assert platform.platform_risk_delta_label == "worsened"
    assert platform.platform_verdict != "better"


def test_whole_car_index_aggregates_available_scores_without_fake_zero() -> None:
    platform = PlatformComparison(
        dynamic_pressure=ChannelDeltaStats("dynamic_pressure_psf", "Dynamic Pressure", "psf", delta_avg=0.2),
        cfs_height=ChannelDeltaStats("cfs_ride_height_in", "CFS", "in", delta_avg=0.02),
    )
    driver = DriverComparison(
        avg_abs_steering_deg=ChannelDeltaStats("abs_steering_deg", "Steering", "deg", delta_avg=-0.4)
    )
    powertrain = PowertrainComparison(
        pull_score=ChannelDeltaStats("speed_rate_mph_1000ft", "Pull", "mph/1000ft", delta_avg=None)
    )

    index = compute_whole_car_index(
        platform,
        driver,
        powertrain,
        discipline_score=88.0,
        context_problems=0,
        speed_delta_mph=0.2,
    )

    assert index.speed_index is not None and index.speed_index > 50.0
    assert index.powertrain_index is None
    assert index.confidence_index < 70.0
    assert index.overall_index is not None


def test_whole_car_index_withholds_result_without_speed_evidence() -> None:
    index = compute_whole_car_index(
        PlatformComparison(
            cfs_height=ChannelDeltaStats("cfs_ride_height_in", "CFS", "in", delta_avg=0.02),
        ),
        DriverComparison(),
        discipline_score=100.0,
        speed_delta_mph=None,
    )

    assert index.speed_index is None
    assert index.overall_index is None
    assert index.overall_label == "Unavailable — speed evidence missing"
    assert index.confidence_index <= 25.0


def test_driver_repeatability_uses_signed_steering_by_track_position() -> None:
    baseline = [
        _trace_row(float(pct), throttle_pct=100.0, brake_pct=0.0, steering_deg=2.0, abs_steering_deg=2.0)
        for pct in range(101)
    ]
    test = [
        _trace_row(float(pct), throttle_pct=100.0, brake_pct=0.0, steering_deg=-2.0, abs_steering_deg=2.0)
        for pct in range(101)
    ]

    driver = aggregate_driver_stats(baseline, test)

    assert driver.steering_mae_deg == 4.0
    assert driver.driver_verdict == "changed"


def test_missing_driver_inputs_stay_unavailable_instead_of_perfectly_repeatable() -> None:
    rows = [_trace_row(0.0, speed_mph=180.0), _trace_row(100.0, speed_mph=181.0)]

    driver = aggregate_driver_stats(rows, rows)

    assert driver.throttle_mae_pct is None
    assert driver.brake_mae_pct is None
    assert driver.steering_mae_deg is None
    assert driver.repeatability_score is None
    assert driver.driver_verdict == "unavailable"
    assert "incomplete" in (driver.driver_changed_warning or "")
