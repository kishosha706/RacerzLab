from __future__ import annotations

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.stint_strategy import StintPaceDrift, analyze_stint_strategy
from racelab_engine.models.lap import LapSummary


def _laps(lap_times: list[float]) -> list[LapSummary]:
    return [
        LapSummary(
            lap_id=f"run:lap:{number}",
            run_id="run",
            lap_number=number,
            is_complete=True,
            is_useful=True,
            lap_time=lap_time,
            avg_throttle_pct=72.0 + number * 0.02,
            avg_brake_pct=8.0 + number * 0.01,
            avg_abs_steering_deg=5.0 + number * 0.01,
            classification_tags=["ELIGIBLE_FLYING_LAP"],
        )
        for number, lap_time in enumerate(lap_times, start=1)
    ]


def _rows(lap_count: int, *, complete_covariates: bool = True) -> list[dict]:
    rows: list[dict] = []
    for lap in range(1, lap_count + 1):
        fuel_start = 50.0 - (lap - 1)
        for sample in range(21):
            position = sample / 20.0
            row = {
                "lap": lap,
                "lap_dist_pct": position,
                "session_time": (lap - 1) * 60.0 + sample * 0.5,
                "fuel_level": fuel_start - position,
                "on_pit_road": False,
                "pitstop_active": False,
                "player_in_pit_stall": False,
                "enter_exit_reset_state": 0,
                "under_caution": False,
                "pace_mode_active": False,
                "session_flags": 0,
                "repair_required": 0.0,
                "repair_time_s": 0.0,
            }
            if complete_covariates:
                row.update({
                    "air_temp": 24.0 + lap * 0.02,
                    "track_temp": 34.0 + lap * 0.05,
                    "wind_vel": 2.0 + lap * 0.01,
                    "throttle_pct": 72.0 + lap * 0.02,
                    "brake_pct": 8.0 + lap * 0.01,
                    "abs_steering_deg": 5.0 + lap * 0.01,
                    "player_tire_compound": "dry",
                    "tire_sets_used": 1,
                })
                for corner_index, corner in enumerate(("lf", "rf", "lr", "rr")):
                    row[f"{corner}_tire_distance_m"] = lap * 2000.0 + sample * 10.0
                    row[f"{corner}_temp_middle"] = 88.0 + lap * 0.08 + corner_index * 0.1
                    remaining = 99.5 - lap * (0.10 + corner_index * 0.01)
                    row[f"{corner}_wear_inner"] = (remaining + 0.20) / 100.0
                    row[f"{corner}_wear_middle"] = (remaining + 0.10) / 100.0
                    row[f"{corner}_wear_outer"] = remaining / 100.0
            rows.append(row)
    return rows


def _pace_conclusion(report):
    return next(item for item in report.conclusions if item.key == "stint_pace_drift")


def test_stint_state_detects_robust_level_change_without_tire_causality() -> None:
    lap_times = [50.0 + lap * 0.01 + (0.80 if lap >= 7 else 0.0) for lap in range(1, 13)]
    report = analyze_stint_strategy(
        _rows(12),
        _laps(lap_times),
        sim_integrity_clear=True,
    )

    assert report.pace_drift is not None
    assert report.pace_drift.status == "observed"
    assert report.pace_drift.evidence_state == "observed_correlation"
    assert report.pace_drift.change_points
    assert report.pace_drift.change_points[0].after_lap == 7
    assert len(report.pace_drift.segments) == 2
    assert report.pace_drift.attribution == "unresolved_observational"
    assert {item.key for item in report.pace_drift.covariates} == {
        "fuel_level",
        "tire_distance",
        "tire_temperature",
        "tire_wear_remaining",
        "air_temperature",
        "track_temperature",
        "wind_speed",
        "driver_throttle",
        "driver_brake",
        "driver_steering",
    }
    assert report.pace_drift.right_censored is True
    assert report.pace_drift.extrapolation_allowed is False
    conclusion = _pace_conclusion(report)
    assert conclusion.evidence_state == "observed_correlation"
    assert conclusion.recommendation is None
    assert "does not isolate a tire or setup cause" in " ".join(
        conclusion.contradicting_evidence
    ).lower()


def test_injected_fuel_pace_relationship_remains_an_unresolved_association() -> None:
    rows = _rows(12)
    fuel_midpoints = [49.5 - (lap - 1) for lap in range(1, 13)]
    lap_times = [48.0 + fuel * 0.05 for fuel in fuel_midpoints]
    report = analyze_stint_strategy(rows, _laps(lap_times), sim_integrity_clear=True)

    assert report.pace_drift is not None
    fuel = next(
        item for item in report.pace_drift.covariates if item.key == "fuel_level"
    )
    assert fuel.pace_ordinal_association > 0.95
    assert fuel.attribution == "unresolved_observational"
    assert report.pace_drift.attribution == "unresolved_observational"
    assert all(not hasattr(item, "causal_contribution") for item in report.pace_drift.covariates)


def test_refuel_splits_history_and_prevents_pooling_two_short_halves() -> None:
    rows = _rows(18)
    for row in rows:
        if row["lap"] >= 10:
            row["fuel_level"] += 30.0
    report = analyze_stint_strategy(
        rows,
        _laps([50.0 + lap * 0.03 for lap in range(1, 19)]),
        sim_integrity_clear=True,
    )

    assert report.historical_segment_laps == list(range(1, 10))
    assert report.active_segment_laps == list(range(10, 19))
    assert report.pace_drift is not None
    assert report.pace_drift.status == "blocked"
    assert report.degradation_s_per_lap is None


def test_within_lap_refuel_is_removed_as_a_service_boundary() -> None:
    rows = _rows(15)
    for row in rows:
        if row["lap"] == 6 and row["lap_dist_pct"] >= 0.50:
            row["fuel_level"] += 5.0
    report = analyze_stint_strategy(
        rows,
        _laps([50.0 + lap * 0.02 for lap in range(1, 16)]),
        sim_integrity_clear=True,
    )

    assert report.historical_segment_laps == list(range(7, 16))
    assert 6 not in report.historical_segment_laps
    assert report.pace_drift is not None
    assert report.pace_drift.status == "blocked"


@pytest.mark.parametrize(
    ("channel", "value"),
    [
        ("on_pit_road", True),
        ("enter_exit_reset_state", 2),
        ("repair_required", 1.0),
        ("session_flags", 0x4000),
    ],
)
def test_pit_reset_repair_and_caution_laps_break_observational_stint(
    channel: str,
    value: object,
) -> None:
    rows = _rows(15)
    for row in rows:
        if row["lap"] == 6:
            row[channel] = value
    report = analyze_stint_strategy(
        rows,
        _laps([50.0 + lap * 0.02 for lap in range(1, 16)]),
        sim_integrity_clear=True,
    )

    assert 6 not in report.historical_segment_laps
    assert report.historical_segment_laps == list(range(7, 16))
    assert report.pace_drift is not None
    assert report.pace_drift.status == "blocked"


def test_short_run_and_right_censor_contract_fail_closed() -> None:
    short = analyze_stint_strategy(
        _rows(9),
        _laps([50.0 + lap * 0.03 for lap in range(1, 10)]),
        sim_integrity_clear=True,
    )

    assert short.pace_drift is not None
    assert short.pace_drift.status == "blocked"
    assert short.pace_drift.evidence_state == "blocked_by_context"
    assert short.pace_drift.robust_slope_s_per_lap is None
    assert short.pace_drift.right_censored is True
    assert short.pace_drift.extrapolation_allowed is False
    assert "at least 10" in " ".join(short.pace_drift.blocker_reasons).lower()


def test_missing_covariate_channels_are_disclosed_and_never_zero_filled() -> None:
    rows = _rows(12, complete_covariates=False)
    laps = _laps([50.0 + lap * 0.02 for lap in range(1, 13)])
    laps = [
        lap.model_copy(update={
            "avg_throttle_pct": None,
            "avg_brake_pct": None,
            "avg_abs_steering_deg": None,
        })
        for lap in laps
    ]
    report = analyze_stint_strategy(rows, laps, sim_integrity_clear=True)

    assert report.pace_drift is not None
    assert report.pace_drift.status == "observed"
    assert [item.key for item in report.pace_drift.covariates] == ["fuel_level"]
    assert set(report.pace_drift.missing_covariates) == {
        "tire_distance",
        "tire_temperature",
        "tire_wear_remaining",
        "air_temperature",
        "track_temperature",
        "wind_speed",
        "driver_throttle",
        "driver_brake",
        "driver_steering",
    }
    assert report.pace_drift.source_channels == ["fuel_level", "lap_summary.lap_time"]
    assert _pace_conclusion(report).confidence_score <= 0.55


def test_failed_parent_contract_never_leaks_an_observed_pace_finding() -> None:
    rows = _rows(12)
    for row in rows:
        row.pop("fuel_level")
    report = analyze_stint_strategy(
        rows,
        _laps([50.0 + lap * 0.02 for lap in range(1, 13)]),
        sim_integrity_clear=True,
    )

    assert report.gate.eligible is False
    assert report.pace_drift is not None
    assert report.pace_drift.status == "blocked"
    assert report.pace_drift.robust_slope_s_per_lap is None
    assert report.pace_drift.segments == []
    assert report.pace_drift.change_points == []


def test_stint_pace_model_rejects_unsupported_observed_or_repeated_set_claims() -> None:
    with pytest.raises(ValidationError, match="minimum eligible lap history"):
        StintPaceDrift(
            status="observed",
            evidence_state="observed_correlation",
            lap_numbers=[1, 2, 3],
            robust_slope_s_per_lap=0.1,
            source_channels=["lap_summary.lap_time"],
            caveats=["Observational only."],
        )
    with pytest.raises(ValidationError, match="exact evidence IDs"):
        StintPaceDrift(
            status="observed",
            evidence_state="observed_correlation",
            lap_numbers=list(range(1, 11)),
            robust_slope_s_per_lap=0.1,
            empirical_lap_noise_s=0.01,
            direction="slowing",
            segments=[{
                "start_lap": 1,
                "end_lap": 10,
                "lap_numbers": list(range(1, 11)),
                "robust_slope_s_per_lap": 0.1,
                "observed_change_s": 0.9,
                "direction": "slowing",
            }],
            source_channels=["lap_summary.lap_time"],
            caveats=["Observational only."],
            attribution="repeated_tire_set_observation",
            repeated_comparable_tire_sets=2,
        )
