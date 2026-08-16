from __future__ import annotations

import math

import pytest
import polars as pl

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame
from racelab_engine.analysis.braking_efficiency import analyze_braking_efficiency
from racelab_engine.analysis.damper_response import analyze_damper_response
from racelab_engine.analysis.sim_integrity import (
    build_sim_integrity_certificate,
    comparison_integrity_gate,
)
from racelab_engine.analysis.tire_state_energy import analyze_tire_state
from racelab_engine.analysis.evidence_contracts import EvidenceEvaluationInput, evaluate_evidence_contract
from racelab_engine.analysis.p3_contracts import (
    BRAKING_EFFICIENCY_CONTRACT,
    DAMPER_RESPONSE_CONTRACT,
    POWERTRAIN_GEARING_CONTRACT,
    STINT_STRATEGY_CONTRACT,
    TIRE_STATE_CONTRACT,
)
from racelab_engine.analysis.powertrain_gearing import analyze_powertrain_gearing
from racelab_engine.analysis.p3_common import bounded_confidence, lap_pct
from racelab_engine.analysis.relative_resistance import analyze_relative_resistance_aba
from racelab_engine.analysis.stint_strategy import analyze_stint_strategy
from racelab_engine.models.engineering import EngineeringConclusion
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS


def _laps(count: int) -> list[LapSummary]:
    return [
        LapSummary(
            lap_id=f"run:lap:{number}",
            run_id="run",
            lap_number=number,
            is_complete=True,
            is_useful=True,
            lap_time=50.0 + number * 0.01,
            classification_tags=["ELIGIBLE_FLYING_LAP"],
        )
        for number in range(1, count + 1)
    ]


def test_engineering_conclusion_rejects_deprecated_action_slot() -> None:
    with pytest.raises(ValueError, match="recommendation"):
        EngineeringConclusion(
            key="hostile_non_p19_action",
            summary="Observation only.",
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=0.5,
            source_channels=["speed_mph"],
            supporting_evidence=["Recorded speed."],
            recommendation="Lower a setup value.",
        )


def _one_eligible_two_pit_laps() -> list[LapSummary]:
    laps = _laps(3)
    return [
        laps[0],
        *[
            lap.model_copy(update={"classification_tags": ["PIT_ROAD", "NO_SETUP_CONCLUSION"]})
            for lap in laps[1:]
        ],
    ]


def _base_row(lap: int, index: int, phase: str) -> dict[str, float | int | str | bool]:
    return {
        "lap": lap,
        "lap_dist_pct": index / 100.0,
        "session_time": (lap - 1) * 60.0 + index * 0.1,
        "engineering_phase": phase,
        "session_tick": (lap - 1) * 101 + index,
    }


def test_lap_pct_does_not_rescale_early_percent_channel_values() -> None:
    assert lap_pct({"lap_dist_pct_100": 1.25, "lap_dist_pct": 0.0125}) == 1.25
    assert lap_pct({"lap_dist_pct": 0.0125}) == 1.25
    assert lap_pct({"lap_dist_pct_100": 101.0}) is None


def _brake_rows() -> list[dict]:
    rows = []
    for index in range(101):
        row = _base_row(1, index, "threshold_braking")
        brake = 80.0 - abs(50 - index) * 0.3
        front = 60.0 + index * 0.1
        rear = 40.0 + index * 0.06
        row.update({
            "brake_pct": brake,
            "brake_01": brake / 100.0,
            "lf_brake_line_pressure_bar": front,
            "rf_brake_line_pressure_bar": front,
            "lr_brake_line_pressure_bar": rear,
            "rr_brake_line_pressure_bar": rear,
            "lf_speed": 50.0 if index < 50 else 43.0,
            "rf_speed": 50.0,
            "lr_speed": 50.0,
            "rr_speed": 50.0,
            "lf_slip_ratio": -0.12 if index >= 50 else -0.01,
            "rf_slip_ratio": -0.02,
            "lr_slip_ratio": -0.01,
            "rr_slip_ratio": -0.01,
            "long_accel": -8.0,
            "yaw_rate": 0.05,
            "abs_steering_deg": 3.0,
            "brake_abs_active": index >= 55,
            "brake_abs_cut_01": 0.2 if index >= 55 else 0.0,
            "lf_pressure": 180.0,
            "rf_pressure": 180.0,
            "lr_pressure": 175.0,
            "rr_pressure": 175.0,
        })
        rows.append(row)
    return rows


def test_braking_engine_separates_bias_and_technique_without_mu_claim() -> None:
    report = analyze_braking_efficiency(
        _brake_rows(),
        _laps(3),
        selected_lap=1,
        sim_integrity_clear=True,
    )

    assert report.gate.eligible is True
    assert report.metrics is not None
    assert report.metrics.incipient_lock_corner == "LF"
    assert report.metrics.lock_evidence_tier == "abs_corroborated"
    assert report.metrics.effective_front_ratio is not None
    assert report.metrics.abs_active_duration_s is not None
    assert report.metrics.efficiency_proxy_unit == "m/s^2 per bar"
    text = " ".join(
        [item.summary for item in report.conclusions]
        + [evidence for item in report.conclusions for evidence in item.supporting_evidence]
    ).lower()
    assert "friction coefficient" in text
    assert "measured friction" not in text
    assert all(item.source_channels for item in report.conclusions)
    assert all(item.contradicting_evidence for item in report.conclusions)
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)
    assert "front brake-bias step" not in report.model_dump_json().lower()


def test_abs_false_with_constant_cut_does_not_create_abs_or_bias_evidence() -> None:
    rows = _brake_rows()
    for row in rows:
        row["brake_abs_active"] = False
        row["brake_abs_cut_01"] = 1.0

    report = analyze_braking_efficiency(rows, _laps(3), selected_lap=1, sim_integrity_clear=True)

    assert report.metrics is not None
    assert report.metrics.abs_active_duration_s == 0.0
    assert report.metrics.incipient_lock_corner is None
    assert report.metrics.lock_evidence_tier == "raw_wheel_speed_proxy"
    assert "mixed or incomplete" in report.conclusions[-1].summary


def test_non_overlapping_pressure_and_deceleration_withholds_efficiency() -> None:
    rows = _brake_rows()
    for index, row in enumerate(rows):
        if index < len(rows) // 2:
            row["long_accel"] = None
        else:
            for channel in (
                "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
                "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
            ):
                row[channel] = None

    report = analyze_braking_efficiency(rows, _laps(3), selected_lap=1, sim_integrity_clear=True)

    assert report.metrics is not None
    assert report.metrics.matched_deceleration_efficiency_proxy is None


def test_non_overlapping_tire_shoulders_withhold_profile_relationship() -> None:
    rows = _tire_rows(1)
    for index, row in enumerate(rows):
        row["lf_temp_inner"] = 90.0 if index < len(rows) // 2 else None
        row["lf_temp_middle"] = None if index < len(rows) // 2 else 100.0

    report = analyze_tire_state(rows, _laps(3), selected_lap=1, sim_integrity_clear=True)
    lf = next(state for state in report.corners if state.corner == "LF")

    assert lf.surface_inner is None
    assert lf.surface_middle is None
    assert lf.inner_outer_gradient is None
    assert lf.surface_profile_unavailable_reason is not None


def test_phase_engine_fails_closed_when_sim_integrity_is_unknown() -> None:
    report = analyze_braking_efficiency(
        _brake_rows(),
        _laps(3),
        selected_lap=1,
        sim_integrity_clear=None,
    )

    assert report.gate.eligible is False
    assert report.metrics is None
    assert report.conclusions[0].evidence_state == "blocked_by_context"
    assert any("integrity" in reason.lower() for reason in report.gate.blocker_reasons)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, None, "invalid"])
def test_nonfinite_confidence_is_fail_closed(value: object) -> None:
    assert bounded_confidence(value) == 0.0

    report = analyze_braking_efficiency(
        _brake_rows(),
        _laps(3),
        selected_lap=1,
        sim_integrity_clear=True,
        sim_integrity_confidence_cap=value,  # type: ignore[arg-type]
    )

    assert report.gate.confidence_cap == 0.0
    assert all(item.confidence_score == 0.0 for item in report.conclusions)


def _tire_rows(laps: int) -> list[dict]:
    rows: list[dict] = []
    for lap in range(1, laps + 1):
        for index in range(101):
            row = _base_row(lap, index, "center")
            row.update({"brake_pct": 5.0, "throttle_pct": 40.0, "lat_accel": 9.0, "long_accel": 0.0, "vert_accel_g": 1.1})
            for corner in ("lf", "rf", "lr", "rr"):
                row.update({
                    f"{corner}_pressure": 185.0,
                    f"{corner}_cold_pressure": 160.0,
                    f"{corner}_temp_inner": 90.0,
                    f"{corner}_temp_middle": 96.0,
                    f"{corner}_temp_outer": 90.0,
                    f"{corner}_carcass_temp_l": 88.0,
                    f"{corner}_carcass_temp_m": 89.0,
                    f"{corner}_carcass_temp_r": 88.0,
                    f"{corner}_wear_inner": 0.98,
                    f"{corner}_wear_middle": 0.97,
                    f"{corner}_wear_outer": 0.98,
                    f"{corner}_tire_distance_m": lap * 2000.0,
                    f"{corner}_slip_ratio": 0.02,
                })
            rows.append(row)
    return rows


def test_tire_pressure_pattern_remains_observational_with_snapshot_only_history() -> None:
    repeated = analyze_tire_state(
        _tire_rows(3), _laps(3), selected_lap=1, sim_integrity_clear=True,
    )
    short = analyze_tire_state(
        _tire_rows(1), _laps(1), selected_lap=1, sim_integrity_clear=True,
    )

    assert repeated.gate.eligible is True
    assert all("pressure_driven_heating" in corner.cause_classes for corner in repeated.corners)
    assert all(corner.carcass_update_semantic == "pit_snapshot" for corner in repeated.corners)
    assert all(corner.wear_update_semantic == "pit_snapshot" for corner in repeated.corners)
    assert all("recommendation" not in item.model_dump() for item in repeated.conclusions)
    assert all("recommendation" not in item.model_dump() for item in short.conclusions)
    assert all(
        any("Center-tread temperature alone" in evidence for evidence in item.contradicting_evidence)
        for item in repeated.conclusions
    )
    assert all(
        any("pit-boundary snapshots" in evidence for evidence in item.contradicting_evidence)
        for item in repeated.conclusions
    )


def test_varying_surface_and_pressure_cannot_promote_constant_snapshots_or_raw_falloff() -> None:
    rows = _tire_rows(12)
    for row in rows:
        position = float(row["lap_dist_pct"])
        for corner in ("lf", "rf", "lr", "rr"):
            row[f"{corner}_pressure"] = 182.0 + 4.0 * position
            row[f"{corner}_temp_inner"] = 88.0 + 3.0 * position
            row[f"{corner}_temp_middle"] = 94.0 + 4.0 * position
            row[f"{corner}_temp_outer"] = 89.0 + 2.0 * position
    degrading_laps = [
        lap.model_copy(update={"lap_time": 50.0 + 0.2 * lap.lap_number})
        for lap in _laps(12)
    ]

    report = analyze_tire_state(
        rows,
        degrading_laps,
        selected_lap=1,
        sim_integrity_clear=True,
    )

    snapshot_only_causes = {
        "surface_scrub", "carcass_heat", "aging", "saturation", "falloff",
    }
    assert report.gate.eligible is True
    assert all(corner.carcass_average is not None for corner in report.corners)
    assert all(corner.wear_inner is not None for corner in report.corners)
    assert all(not (snapshot_only_causes & set(corner.cause_classes)) for corner in report.corners)
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)
    assert all(
        any("traffic, fuel, weather, line" in evidence for evidence in item.contradicting_evidence)
        for item in report.conclusions
    )


def _damper_rows(laps: int = 2) -> list[dict]:
    rows = []
    for lap in range(1, laps + 1):
        for index in range(101):
            row = _base_row(lap, index, "bump_curb")
            row.update({
                "vert_accel_g": 1.0 + 0.5 * math.sin(index * 0.2),
                "speed_mph": 120.0,
                "brake_pct": 0.0,
                "throttle_pct": 100.0,
                "steering_deg": 2.0,
            })
            for offset, corner in enumerate(("lf", "rf", "lr", "rr")):
                row[f"{corner}_shock_vel_in_s"] = 6.0 * math.sin(index * 0.35 + offset * 0.1)
                row[f"{corner}_shock_defl_in"] = 2.0 + 0.2 * math.sin(index * 0.35 + offset * 0.1)
            rows.append(row)
    return rows


def test_damper_engine_requires_measured_regime_occupancy_and_never_claims_force() -> None:
    report = analyze_damper_response(
        _damper_rows(),
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        setup_snapshot_captured=True,
    )

    assert report.gate.eligible is True
    assert len(report.corners) == 4
    assert all(corner.velocity_histogram_pct for corner in report.corners)
    assert all(corner.low_speed_regime_pct > 0 for corner in report.corners)
    assert all(corner.high_speed_regime_pct > 0 for corner in report.corners)
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)
    assert report.fingerprint is not None
    assert report.fingerprint.bump_positions_pct
    text = " ".join(
        [item.summary for item in report.conclusions]
        + [evidence for item in report.conclusions for evidence in item.contradicting_evidence]
    ).lower()
    assert "do not measure damper force" in text
    assert "outside this observational producer" in text
    assert "controlled p19 workflow" in text


def test_damper_disjoint_velocity_and_time_returns_unavailable() -> None:
    rows = _damper_rows()
    for row in rows:
        if row["lap"] != 1:
            continue
        first_sample = row["session_tick"] == 0
        row["session_time"] = None if first_sample else row["session_time"]
        for corner in ("lf", "rf", "lr", "rr"):
            row[f"{corner}_shock_vel_in_s"] = 1.0 if first_sample else None

    report = analyze_damper_response(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        setup_snapshot_captured=True,
    )

    assert report.gate.eligible is False
    assert report.gate.confidence_cap == 0.0
    assert report.corners == []
    assert report.conclusions[0].evidence_state == "unavailable"
    assert all("paired shaft velocity and session time" in reason for reason in report.gate.blocker_reasons)


def test_damper_sparse_pairwise_coverage_on_one_corner_blocks_distribution_math() -> None:
    rows = _damper_rows()
    selected_rows = [row for row in rows if row["lap"] == 1]
    for row in selected_rows[20:]:
        row["rr_shock_vel_in_s"] = None

    report = analyze_damper_response(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        setup_snapshot_captured=True,
    )

    assert report.gate.eligible is False
    assert report.corners == []
    assert any(reason.startswith("RR damper response has 20/101") for reason in report.gate.blocker_reasons)
    assert report.gate.needed_measurements


def test_damper_regime_observation_records_insufficient_occupancy() -> None:
    rows = _damper_rows()
    for row in rows:
        for corner in ("lf", "rf", "lr", "rr"):
            row[f"{corner}_shock_vel_in_s"] = 0.5
    report = analyze_damper_response(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        setup_snapshot_captured=True,
    )

    assert all("recommendation" not in item.model_dump() for item in report.conclusions)
    assert all(
        any("less than 10%" in evidence for evidence in item.contradicting_evidence)
        for item in report.conclusions
    )


def test_pit_laps_cannot_promote_repetition_gated_observations() -> None:
    hostile_laps = _one_eligible_two_pit_laps()
    brake = analyze_braking_efficiency(
        _brake_rows(), hostile_laps, selected_lap=1, sim_integrity_clear=True,
    )
    tire = analyze_tire_state(
        _tire_rows(3), hostile_laps, selected_lap=1, sim_integrity_clear=True,
    )
    damper = analyze_damper_response(
        _damper_rows(3),
        hostile_laps,
        selected_lap=1,
        sim_integrity_clear=True,
        setup_snapshot_captured=True,
    )

    assert brake.gate.eligible is True
    assert "recommendation" not in brake.conclusions[-1].model_dump()
    assert tire.working_history_laps == 1
    assert all("recommendation" not in item.model_dump() for item in tire.conclusions)
    assert all("recommendation" not in item.model_dump() for item in damper.conclusions)
    assert damper.fingerprint is not None
    assert damper.fingerprint.observed_bump_positions_pct
    assert damper.fingerprint.bump_positions_pct == []
    assert damper.fingerprint.repeatability_fraction is None


def _power_rows(laps: int) -> list[dict]:
    rows = []
    for lap in range(1, laps + 1):
        for index in range(101):
            row = _base_row(lap, index, "straight")
            row.update({
                "speed_mph": 130.0 + index * 0.2,
                "rpm": 6950.0 + 20.0 * math.sin(index * 0.1),
                "gear": 4,
                "throttle_pct": 100.0,
                "long_accel": 2.0 + lap * 0.005,
                "fuel_level": 40.0 - lap,
                "water_temp": 100.0,
                "oil_temp": 110.0,
                "engine_warnings": 0.0,
            })
            rows.append(row)
    return rows


def test_powertrain_requires_repeatable_pull_rows_for_gearing_discriminator() -> None:
    hostile = analyze_powertrain_gearing(
        _power_rows(1),
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )
    repeated = analyze_powertrain_gearing(
        _power_rows(2),
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    assert hostile.pull_consistency_cv is None
    assert all("recommendation" not in item.model_dump() for item in hostile.conclusions)
    assert repeated.pull_consistency_cv is not None
    assert all("recommendation" not in item.model_dump() for item in repeated.conclusions)
    assert "taller gearing step" not in repeated.model_dump_json().lower()
    assert "shorter gearing step" not in repeated.model_dump_json().lower()
    text = " ".join(
        evidence for item in repeated.conclusions for evidence in item.contradicting_evidence
    ).lower()
    assert "do not measure engine horsepower" in text
    support = " ".join(
        evidence for item in repeated.conclusions for evidence in item.supporting_evidence
    ).lower()
    assert "user-declared or setup-derived" in support
    assert "near-redline occupancy" in support
    assert "headroom" in support
    assert "matched-lap near-redline occupancies" in support


def test_powertrain_limiter_dwell_uses_only_matched_powered_samples() -> None:
    rows = _power_rows(2)
    for row in rows:
        if row["lap_dist_pct"] < 0.89:
            row["throttle_pct"] = 0.0
            row["rpm"] = 7000.0
        else:
            row["rpm"] = 5000.0
    report = analyze_powertrain_gearing(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    assert report.near_redline_occupancy_pct == 0.0
    assert report.powered_repeatability_established is False
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)


def test_powertrain_does_not_match_one_unrelated_sample_on_second_lap() -> None:
    rows = _power_rows(1)
    unrelated = _base_row(2, 0, "initial_throttle")
    unrelated.update({
        "speed_mph": 40.0,
        "rpm": 6950.0,
        "gear": 1,
        "throttle_pct": 100.0,
        "long_accel": 2.0,
    })
    rows.append(unrelated)
    report = analyze_powertrain_gearing(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    assert report.pull_consistency_cv is None
    assert report.powered_repeatability_established is False
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)


def test_powertrain_api_shaped_rows_detect_and_repeat_phases_without_phase_column() -> None:
    rows = _power_rows(2)
    for row in rows:
        row.pop("engineering_phase")
        assert "lap_dist_pct_100" not in row
    report = analyze_powertrain_gearing(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    assert report.gate.eligible is True
    assert "straight" in report.phases
    assert report.powered_repeatability_established is True
    assert report.pull_consistency_cv is not None


def test_prompt_normal_upshift_near_redline_is_not_limiter_evidence() -> None:
    rows = _power_rows(2)
    for row in rows:
        index = round(row["lap_dist_pct"] * 100)
        if index < 56:
            row["rpm"] = 5000.0 + index * 30.0
            row["gear"] = 4
        elif index < 60:
            row["rpm"] = 6950.0
            row["gear"] = 4
        else:
            row["rpm"] = 5200.0 + (index - 60) * 20.0
            row["gear"] = 5
    report = analyze_powertrain_gearing(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    assert report.near_redline_occupancy_pct is not None
    assert report.near_redline_occupancy_pct > 1.0
    assert report.limiter_evidence_established is False
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)


def test_powertrain_never_invents_shift_across_excluded_phase_gap() -> None:
    rows = _power_rows(2)
    for row in rows:
        index = round(row["lap_dist_pct"] * 100)
        if index <= 10:
            row["engineering_phase"] = "straight"
            row["gear"] = 3
            row["rpm"] = 5000.0
        elif index < 90:
            row["engineering_phase"] = "threshold_braking"
            row["gear"] = 3
            row["rpm"] = 4000.0
        else:
            row["engineering_phase"] = "straight"
            row["gear"] = 4
            row["rpm"] = 5000.0
    report = analyze_powertrain_gearing(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    assert report.shift_events == []


def test_powertrain_context_diagnostics_bound_fuel_mass_and_clear_matched_runs() -> None:
    report = analyze_powertrain_gearing(
        _power_rows(2),
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    diagnostics = report.context_diagnostics
    assert diagnostics is not None
    assert diagnostics.context_comparable_for_observation is True
    assert "clear_for_gearing_action" not in diagnostics.model_dump()
    assert diagnostics.fuel_context_matched is True
    assert diagnostics.temperature_context_stable is True
    assert diagnostics.gear_context_matched is True
    assert diagnostics.matched_fuel_spread_l == pytest.approx(1.0)
    assert diagnostics.fuel_mass_spread_kg is None
    assert diagnostics.fuel_mass_evidence_state == "unavailable_without_supported_density"
    context = next(
        item for item in report.conclusions if item.key == "powertrain_context_diagnostics"
    )
    wording = " ".join(context.supporting_evidence + context.contradicting_evidence).lower()
    assert "fuel mass is unavailable" in wording
    assert "not calculated without a supported density source" in wording


def test_powertrain_context_blocks_hot_warning_fuel_and_gear_confounds() -> None:
    rows = _power_rows(3)
    for row in rows:
        lap = int(row["lap"])
        row["water_temp"] = 100.0 + lap * 1.0
        row["oil_temp"] = 110.0 + lap * 1.0
        row["fuel_level"] = 45.0 - lap * 4.0
        if lap == 2:
            row["gear"] = 5
            row["engine_warnings"] = 1.0
    report = analyze_powertrain_gearing(
        rows,
        _laps(3),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    diagnostics = report.context_diagnostics
    assert diagnostics is not None
    assert "clear_for_gearing_action" not in diagnostics.model_dump()
    assert diagnostics.temperature_context_stable is False
    assert diagnostics.fuel_context_matched is False
    assert diagnostics.gear_context_matched is False
    assert diagnostics.gear_mismatch_laps == [2]
    assert diagnostics.engine_warning_active_fraction_pct is not None
    assert diagnostics.engine_warning_active_fraction_pct > 0.0
    assert diagnostics.blocker_reasons
    gearing = next(item for item in report.conclusions if item.key == "gearing_discriminator_observation")
    assert "recommendation" not in gearing.model_dump()


def test_powertrain_context_rejects_sparse_or_implausible_diagnostic_samples() -> None:
    rows = _power_rows(2)
    for row in rows:
        if round(float(row["lap_dist_pct"]) * 100) != 50:
            row.pop("fuel_level")
            row.pop("water_temp")
            row.pop("oil_temp")
            row.pop("engine_warnings")
    report = analyze_powertrain_gearing(
        rows,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )

    diagnostics = report.context_diagnostics
    assert diagnostics is not None
    assert "clear_for_gearing_action" not in diagnostics.model_dump()
    assert all(
        coverage < 90.0
        for coverage in diagnostics.matched_phase_channel_coverage_pct.values()
    )
    assert "recommendation" not in report.conclusions[-1].model_dump()

    invalid = _power_rows(2)
    for row in invalid:
        row["fuel_level"] = -10.0
        row["water_temp"] = 1000.0
        row["oil_temp"] = -1000.0
        row["engine_warnings"] = 0.5
    invalid_report = analyze_powertrain_gearing(
        invalid,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )
    assert invalid_report.context_diagnostics is not None
    assert "clear_for_gearing_action" not in invalid_report.context_diagnostics.model_dump()
    assert "recommendation" not in invalid_report.conclusions[-1].model_dump()

    cooling_fast = _power_rows(2)
    for row in cooling_fast:
        lap = int(row["lap"])
        row["water_temp"] = 105.0 - lap
        row["oil_temp"] = 115.0 - lap
    cooling_report = analyze_powertrain_gearing(
        cooling_fast,
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=7000.0,
    )
    assert cooling_report.context_diagnostics is not None
    assert cooling_report.context_diagnostics.temperature_context_stable is False


def test_powertrain_ignores_isolated_gear_glitch_but_blocks_sustained_mismatch() -> None:
    isolated = _power_rows(2)
    next(
        row for row in isolated
        if row["lap"] == 2 and round(float(row["lap_dist_pct"]) * 100) == 50
    )["gear"] = 5
    isolated_report = analyze_powertrain_gearing(
        isolated, _laps(2), selected_lap=1, sim_integrity_clear=True, redline_rpm=7000.0,
    )
    assert isolated_report.context_diagnostics is not None
    assert isolated_report.context_diagnostics.gear_mismatch_laps == []

    sustained = _power_rows(2)
    for row in sustained:
        if row["lap"] == 2 and 40 <= float(row["lap_dist_pct"]) * 100 <= 60:
            row["gear"] = 5
    sustained_report = analyze_powertrain_gearing(
        sustained, _laps(2), selected_lap=1, sim_integrity_clear=True, redline_rpm=7000.0,
    )
    assert sustained_report.context_diagnostics is not None
    assert sustained_report.context_diagnostics.gear_mismatch_laps == [2]
    assert sustained_report.context_diagnostics.gear_context_matched is False


def _stint_rows(laps: int) -> list[dict]:
    rows = []
    for lap in range(1, laps + 1):
        for index in range(101):
            row = _base_row(lap, index, "straight")
            row["fuel_level"] = 50.0 - (lap - 1) * 2.0 - index / 100.0 * 2.0
            for corner in ("lf", "rf", "lr", "rr"):
                row[f"{corner}_temp_middle"] = 88.0 + min(lap, 4) * 0.2
                row[f"{corner}_pressure"] = 180.0
                row[f"{corner}_tire_distance_m"] = lap * 2000.0
            rows.append(row)
    return rows


def _stint_rows_with_wear(laps: int) -> list[dict]:
    rows = _stint_rows(laps)
    for row in rows:
        lap = int(row["lap"])
        for corner_index, corner in enumerate(("lf", "rf", "lr", "rr")):
            minimum_remaining = 99.5 - lap * (0.12 + corner_index * 0.01)
            row[f"{corner}_wear_inner"] = (minimum_remaining + 0.20) / 100.0
            row[f"{corner}_wear_middle"] = (minimum_remaining + 0.10) / 100.0
            row[f"{corner}_wear_outer"] = minimum_remaining / 100.0
        row["tire_sets_available"] = 2
        row["tire_sets_used"] = 1
        row["player_tire_compound"] = "dry"
        row["repair_required"] = 0.0
        row["repair_time_s"] = 0.0
    return rows


def test_stint_degradation_is_blocked_for_short_run_and_uses_only_eligible_laps() -> None:
    short = analyze_stint_strategy(
        _stint_rows(3), _laps(3), sim_integrity_clear=True,
    )
    long = analyze_stint_strategy(
        _stint_rows(12), _laps(12), sim_integrity_clear=True,
    )
    hostile = analyze_stint_strategy(
        _stint_rows(3), _one_eligible_two_pit_laps(), sim_integrity_clear=True,
    )

    assert short.gate.eligible is True
    assert short.degradation_s_per_lap is None
    assert short.conclusions[-1].evidence_state == "blocked_by_context"
    assert long.degradation_s_per_lap is not None
    assert long.eligible_lap_count == 12
    assert hostile.gate.eligible is False
    assert hostile.eligible_lap_count == 1


def test_stint_never_pools_disjoint_or_reset_segments_for_degradation() -> None:
    laps = _laps(12)
    laps[5] = laps[5].model_copy(update={"classification_tags": ["PIT_ROAD", "NO_SETUP_CONCLUSION"]})
    laps[6] = laps[6].model_copy(update={"classification_tags": ["PIT_ROAD", "NO_SETUP_CONCLUSION"]})
    rows = _stint_rows(12)
    for row in rows:
        if row["lap"] == 8:
            row["fuel_level"] += 20.0
            row["repair_required"] = 1.0
            for corner in ("lf", "rf", "lr", "rr"):
                row[f"{corner}_tire_distance_m"] = 50.0
    report = analyze_stint_strategy(rows, laps, sim_integrity_clear=True)

    assert report.eligible_lap_count == 5
    assert report.degradation_s_per_lap is None
    assert report.conclusions[-1].evidence_state == "blocked_by_context"
    assert report.fuel_pace_slope_s_per_unit is not None


@pytest.mark.parametrize(("laps", "repair_lap", "expected_clean_segment"), [(10, 1, 9), (15, 6, 9)])
def test_repair_lap_is_excluded_and_breaks_stint_history(
    laps: int,
    repair_lap: int,
    expected_clean_segment: int,
) -> None:
    rows = _stint_rows(laps)
    for row in rows:
        if row["lap"] == repair_lap:
            row["repair_required"] = 1.0
    report = analyze_stint_strategy(rows, _laps(laps), sim_integrity_clear=True)

    assert report.eligible_lap_count == expected_clean_segment
    assert report.degradation_s_per_lap is None
    assert report.conclusions[-1].evidence_state == "blocked_by_context"


def test_fuel_range_uses_active_segment_fuel_and_historical_burn() -> None:
    rows = _stint_rows(13)
    for row in rows:
        if row["lap"] >= 11:
            row["fuel_level"] += 100.0
    report = analyze_stint_strategy(rows, _laps(13), sim_integrity_clear=True)

    assert report.historical_segment_laps == list(range(1, 11))
    assert report.active_segment_laps == [11, 12, 13]
    assert report.median_fuel_burn_per_lap == pytest.approx(2.0)
    assert report.estimated_laps_remaining == pytest.approx(62.0)


def test_stint_metrics_are_invariant_to_telemetry_row_order() -> None:
    rows = _stint_rows(13)
    for row in rows:
        if row["lap"] >= 11:
            row["fuel_level"] += 100.0
    ordered = analyze_stint_strategy(rows, _laps(13), sim_integrity_clear=True)
    shuffled = analyze_stint_strategy(list(reversed(rows)), _laps(13), sim_integrity_clear=True)

    assert shuffled.historical_segment_laps == ordered.historical_segment_laps
    assert shuffled.active_segment_laps == ordered.active_segment_laps
    assert shuffled.median_fuel_burn_per_lap == pytest.approx(ordered.median_fuel_burn_per_lap)
    assert shuffled.estimated_laps_remaining == pytest.approx(ordered.estimated_laps_remaining)


def test_stint_blocks_partial_within_lap_fuel_traces() -> None:
    rows = [
        row for row in _stint_rows(3)
        if row["lap"] != 2 or 20 <= row["lap_dist_pct"] * 100.0 <= 80
    ]

    report = analyze_stint_strategy(rows, _laps(3), sim_integrity_clear=True)

    assert report.gate.eligible is False
    assert report.median_fuel_burn_per_lap is None
    assert any("fuel" in reason.lower() for reason in report.gate.blocker_reasons)


def test_stint_builds_observed_tire_life_curves_and_guarded_fuel_window() -> None:
    report = analyze_stint_strategy(
        _stint_rows_with_wear(12), _laps(12), sim_integrity_clear=True,
    )

    assert set(report.tire_life_curves) == {"LF", "RF", "LR", "RR"}
    assert all(curve.trend_established for curve in report.tire_life_curves.values())
    assert all(len(curve.points) == 12 for curve in report.tire_life_curves.values())
    assert all(
        curve.wear_loss_percentage_points_per_lap is not None
        and curve.wear_loss_percentage_points_per_lap > 0.0
        for curve in report.tire_life_curves.values()
    )
    assert all(curve.right_censored for curve in report.tire_life_curves.values())
    assert all(
        curve.wear_loss_percentage_points_per_1000m_range is not None
        for curve in report.tire_life_curves.values()
    )
    tire_conclusion = next(item for item in report.conclusions if item.key == "tire_life_curve")
    tire_text = " ".join(
        tire_conclusion.supporting_evidence + tire_conclusion.contradicting_evidence
    ).lower()
    assert "observed range" in tire_text
    assert "universal failure threshold" in tire_text

    assert report.pit_window is not None
    assert report.pit_window.status == "available"
    assert report.pit_window.limiting_factor == "fuel"
    assert report.pit_window.classification == "fuel_exhaustion_service_bound"
    assert report.pit_window.strategy_ready is False
    assert report.pit_window.measurement_mission is not None
    assert report.pit_strategy_context is not None
    assert report.pit_strategy_context.strategy_ready is False
    assert report.pit_window.available_tire_sets == 2
    assert report.pit_window.earliest_laps_from_now is not None
    assert report.pit_window.latest_laps_from_now is not None
    pit_text = " ".join(report.pit_window.basis + report.pit_window.caveats).lower()
    assert "reserves one observed lap" in pit_text
    assert "not a guaranteed race-strategy optimum" in pit_text
    assert "no universal unsafe-wear threshold" in pit_text
    assert "race horizon" in pit_text
    assert "pit-lane time loss" in pit_text


def test_stint_production_pit_window_requires_and_uses_server_race_context() -> None:
    rows = _stint_rows_with_wear(13)
    for row in rows:
        row["on_pit_road"] = False
        row["pitstop_active"] = False
        row["player_in_pit_stall"] = False
        row["player_pit_service_status"] = 0.0
        row["pits_open"] = True
        row["session_state"] = 4.0
        row["session_laps_remaining"] = 20.0
        row["session_time_remaining_s"] = 1000.0
        row["session_time_total_s"] = 1800.0
        row["lap_completed"] = int(row["lap"])
        if row["lap"] == 1:
            position_index = round(float(row["lap_dist_pct"]) * 100)
            if 20 <= position_index <= 40:
                row["session_time"] = (
                    float(row["session_time"]) + 30.0 * (position_index - 20) / 20.0
                )
            elif position_index > 40:
                row["session_time"] = float(row["session_time"]) + 30.0
            if 20 <= position_index <= 40:
                row["on_pit_road"] = True
            if 25 <= position_index <= 35:
                row["pitstop_active"] = True
                row["player_in_pit_stall"] = True
    laps = _laps(13)
    laps[0] = laps[0].model_copy(
        update={"classification_tags": ["PIT_ROAD", "NO_SETUP_CONCLUSION"]},
    )

    report = analyze_stint_strategy(
        rows,
        laps,
        sim_integrity_clear=True,
        session_type="Race",
    )

    assert report.historical_segment_laps == list(range(2, 14))
    assert report.pit_strategy_context is not None
    assert report.pit_strategy_context.strategy_ready is True
    assert report.pit_strategy_context.horizon_laps_remaining == 20
    assert report.pit_strategy_context.horizon_source == "session_laps_remaining"
    assert report.pit_strategy_context.measured_pit_loss_samples == 1
    assert report.pit_strategy_context.measured_pit_loss_s == pytest.approx(30.0, abs=0.2)
    assert report.pit_window is not None
    assert report.pit_window.classification == "strategy_window"
    assert report.pit_window.strategy_ready is True
    assert report.pit_window.measurement_mission is None
    assert report.pit_window.latest_laps_from_now == 11
    assert report.pit_window.earliest_laps_from_now == 10
    assert report.pit_window.recommendation is not None
    assert "do not exceed" in report.pit_window.recommendation.lower()
    conclusion = next(
        item for item in report.conclusions if item.key == "pit_window_recommendation"
    )
    assert conclusion.evidence_state == "calculated"
    assert "recommendation" not in conclusion.model_dump()
    assert "on_pit_road" in conclusion.source_channels

    for row in rows:
        row["session_laps_remaining"] = 5.0
    no_stop = analyze_stint_strategy(
        rows,
        laps,
        sim_integrity_clear=True,
        session_type="Race",
    )
    assert no_stop.pit_window is not None
    assert no_stop.pit_window.strategy_ready is True
    assert no_stop.pit_window.earliest_laps_from_now is None
    assert no_stop.pit_window.latest_laps_from_now is None
    assert no_stop.pit_window.recommendation is not None
    assert "no fuel stop is required" in no_stop.pit_window.recommendation.lower()
    no_stop_conclusion = next(
        item for item in no_stop.conclusions if item.key == "pit_window_recommendation"
    )
    assert "does not require" in no_stop_conclusion.summary.lower()


def test_stint_pit_strategy_fails_closed_when_latest_fuel_lap_is_stale() -> None:
    rows = _stint_rows_with_wear(12)
    for row in rows:
        row["pits_open"] = True
        row["session_state"] = 4.0
        row["session_laps_remaining"] = 10.0
    stale = _base_row(13, 50, "straight")
    stale.update({
        "pits_open": True,
        "session_state": 4.0,
        "session_laps_remaining": 10.0,
        "on_pit_road": False,
        "lap_completed": 11,
        "fuel_level": 20.0,
    })
    rows.append(stale)
    report = analyze_stint_strategy(
        rows, _laps(12), sim_integrity_clear=True, session_type="Race",
    )

    assert report.pit_strategy_context is not None
    assert report.pit_strategy_context.strategy_ready is False
    assert any(
        "lapcompleted" in reason.lower()
        for reason in report.pit_strategy_context.blocker_reasons
    )
    assert report.pit_window is not None
    assert report.pit_window.strategy_ready is False
    assert report.pit_window.recommendation is None
    assert report.pit_window.measurement_mission is not None


def test_stint_compound_set_and_single_corner_distance_changes_split_history() -> None:
    rows = _stint_rows_with_wear(12)
    for row in rows:
        if row["lap"] >= 6:
            row["player_tire_compound"] = "wet"
            row["tire_sets_used"] = 2
        if row["lap"] >= 10:
            row["lf_tire_distance_m"] = (int(row["lap"]) - 9) * 2000.0
    report = analyze_stint_strategy(rows, _laps(12), sim_integrity_clear=True)

    assert report.historical_segment_laps == list(range(1, 6))
    assert report.active_segment_laps == list(range(10, 13))
    assert report.tire_set_resets_observed == 2
    assert all(not curve.trend_established for curve in report.tire_life_curves.values())


def test_stint_counts_repeatable_tire_life_across_two_recorded_sets() -> None:
    rows = _stint_rows_with_wear(20)
    for row in rows:
        lap = int(row["lap"])
        set_age_lap = lap if lap <= 10 else lap - 10
        if lap >= 11:
            row["tire_sets_used"] = 2
        for corner_index, corner in enumerate(("lf", "rf", "lr", "rr")):
            row[f"{corner}_tire_distance_m"] = set_age_lap * 2000.0
            minimum_remaining = 99.5 - set_age_lap * (0.12 + corner_index * 0.01)
            row[f"{corner}_wear_inner"] = (minimum_remaining + 0.20) / 100.0
            row[f"{corner}_wear_middle"] = (minimum_remaining + 0.10) / 100.0
            row[f"{corner}_wear_outer"] = minimum_remaining / 100.0
    report = analyze_stint_strategy(rows, _laps(20), sim_integrity_clear=True)

    assert report.tire_set_resets_observed == 1
    assert all(curve.trend_established for curve in report.tire_life_curves.values())
    assert all(curve.replicated_tire_sets == 2 for curve in report.tire_life_curves.values())
    conclusion = next(item for item in report.conclusions if item.key == "tire_life_curve")
    text = " ".join(conclusion.contradicting_evidence).lower()
    assert "fewer than two comparable" not in text


def test_stint_withholds_tire_curve_on_short_history_and_pit_window_on_variable_burn() -> None:
    burns = {1: 1.0, 2: 3.0, 3: 1.0, 4: 3.0}
    rows: list[dict] = []
    fuel_start = 50.0
    for lap, burn in burns.items():
        for index in range(101):
            row = _base_row(lap, index, "straight")
            row["fuel_level"] = fuel_start - burn * index / 100.0
            for corner in ("lf", "rf", "lr", "rr"):
                row[f"{corner}_temp_middle"] = 88.0
                row[f"{corner}_pressure"] = 180.0
                row[f"{corner}_tire_distance_m"] = lap * 2000.0
                for position in ("inner", "middle", "outer"):
                    row[f"{corner}_wear_{position}"] = 0.99 - lap * 0.001
            rows.append(row)
        fuel_start -= burn
    report = analyze_stint_strategy(rows, _laps(4), sim_integrity_clear=True)

    assert report.gate.eligible is True
    assert report.pit_window is not None
    assert report.pit_window.status == "blocked"
    assert any("variability exceeds 15%" in reason for reason in report.pit_window.blocker_reasons)
    assert all(not curve.trend_established for curve in report.tire_life_curves.values())
    tire_conclusion = next(item for item in report.conclusions if item.key == "tire_life_curve")
    pit_conclusion = next(
        item for item in report.conclusions if item.key == "pit_window_recommendation"
    )
    assert tire_conclusion.evidence_state == "blocked_by_context"
    assert pit_conclusion.evidence_state == "blocked_by_context"


def _resistance_rows(loss: float, *, near_car: bool = False) -> list[dict]:
    rows = []
    for index in range(101):
        row = _base_row(1, index, "straight")
        row.update({
            "speed_mph": 150.0,
            "speed_rate_mph_s": -loss,
            "throttle_pct": 0.0,
            "brake_pct": 0.0,
            "rpm": 5000.0,
            "gear": 4,
            "abs_steering_deg": 0.1,
            "air_density": 1.2,
            "air_temp": 25.0,
            "track_temp": 35.0,
            "wind_vel": 0.0,
            "wind_dir": 0.0,
            "fuel_level": 30.0,
            "car_distance_ahead_m": 20.0 if near_car else 1000.0,
            "car_distance_behind_m": 1000.0,
            "lf_tire_distance_m": 2000.0,
            "rf_tire_distance_m": 2000.0,
            "lr_tire_distance_m": 2000.0,
            "rr_tire_distance_m": 2000.0,
            "long_accel": -0.4,
            "lf_slip_ratio": 0.0,
            "rf_slip_ratio": 0.0,
            "lr_slip_ratio": 0.0,
            "rr_slip_ratio": 0.0,
            "lf_brake_line_pressure_bar": 0.0,
            "rf_brake_line_pressure_bar": 0.0,
            "lr_brake_line_pressure_bar": 0.0,
            "rr_brake_line_pressure_bar": 0.0,
            "lap_dist_m": index * 20.0,
            "alt": 100.0 + index * 0.4,
        })
        rows.append(row)
    return rows


def test_relative_resistance_requires_clean_context_and_aba_return() -> None:
    report = analyze_relative_resistance_aba(
        _resistance_rows(0.8), _resistance_rows(1.0), _resistance_rows(0.82),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )
    blocked = analyze_relative_resistance_aba(
        _resistance_rows(0.8), _resistance_rows(1.0, near_car=True), _resistance_rows(0.82),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is True
    assert report.aba_confirmed is True
    assert report.relative_speed_loss_range_mph_s is not None
    text = " ".join(
        [item.summary for item in report.conclusions]
        + [evidence for item in report.conclusions for evidence in item.contradicting_evidence]
    ).lower()
    assert "not exact aerodynamic drag" in text
    assert "cda" in text
    cause = next(item for item in report.conclusions if item.key == "resistance_cause_hypothesis")
    assert "recommendation" not in cause.model_dump()
    assert {
        "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
        "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
        "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
        "air_temp", "track_temp", "wind_vel", "wind_dir", "fuel_level",
    }.issubset(cause.source_channels)
    assert blocked.gate.eligible is False
    assert blocked.conclusions[0].evidence_state == "blocked_by_context"


def test_relative_resistance_controls_measured_grade_before_cause_ranking() -> None:
    report = analyze_relative_resistance_aba(
        _resistance_rows(0.8), _resistance_rows(1.0), _resistance_rows(0.82),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
        grade_source_declared_healthy=True,
        grade_map_identity_matched=True,
    )

    assert report.grade_match is not None
    assert report.grade_match.available is True
    assert report.grade_match.matched is True
    assert report.grade_match.source_channels == ["lap_dist_pct", "lap_dist_m", "alt"]
    assert report.cause_scores["measured_grade_context"] == 0.0
    grade = next(item for item in report.conclusions if item.key == "measured_grade_context")
    assert grade.evidence_state == "calculated"
    wording = " ".join(grade.supporting_evidence + grade.contradicting_evidence).lower()
    assert "altitude-versus-distance" in wording
    assert "not surveyed track elevation" in wording


def test_relative_resistance_withholds_grade_when_measured_shape_disagrees() -> None:
    b = _resistance_rows(1.0)
    for row in b:
        row["alt"] = 100.0 + float(row["lap_dist_m"]) * 0.05
    report = analyze_relative_resistance_aba(
        _resistance_rows(0.8), b, _resistance_rows(0.82),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
        grade_source_declared_healthy=True,
        grade_map_identity_matched=True,
    )

    assert report.gate.eligible is True
    assert report.grade_match is not None
    assert report.grade_match.available is True
    assert report.grade_match.matched is False
    assert "measured_grade_context" not in report.cause_scores
    assert "measured_grade_context" in report.unavailable_cause_buckets
    grade = next(item for item in report.conclusions if item.key == "measured_grade_context")
    assert "recommendation" not in grade.model_dump()
    assert "withheld" in grade.summary.lower()


def test_relative_resistance_missing_altitude_never_invents_grade_context() -> None:
    row_sets = []
    for loss in (0.8, 1.0, 0.82):
        row_sets.append([
            {key: value for key, value in row.items() if key not in {"alt", "lap_dist_m"}}
            for row in _resistance_rows(loss)
        ])
    report = analyze_relative_resistance_aba(
        row_sets[0], row_sets[1], row_sets[2],
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is True
    assert report.grade_match is not None
    assert report.grade_match.available is False
    assert "measured_grade_context" not in report.cause_scores
    grade = next(item for item in report.conclusions if item.key == "measured_grade_context")
    assert grade.evidence_state == "blocked_by_context"
    assert "recommendation" not in grade.model_dump()


def test_relative_resistance_constant_alt_or_undeclared_units_cannot_certify_grade() -> None:
    constant_sets = []
    for loss in (0.8, 1.0, 0.82):
        rows = _resistance_rows(loss)
        for row in rows:
            row["alt"] = 0.0
        constant_sets.append(rows)
    report = analyze_relative_resistance_aba(
        constant_sets[0], constant_sets[1], constant_sets[2],
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
        grade_source_declared_healthy=True,
        grade_map_identity_matched=True,
    )
    assert report.grade_match is not None
    assert report.grade_match.available is False
    assert "measured_grade_context" not in report.cause_scores

    undeclared = analyze_relative_resistance_aba(
        _resistance_rows(0.8), _resistance_rows(1.0), _resistance_rows(0.82),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
        grade_source_declared_healthy=False,
        grade_map_identity_matched=True,
    )
    assert undeclared.grade_match is not None
    assert undeclared.grade_match.available is False
    assert "file-declared" in undeclared.grade_match.explanation


def test_relative_resistance_uses_only_exact_common_track_position_window() -> None:
    a1 = [row for row in _resistance_rows(0.8) if row["lap_dist_pct"] <= 0.60]
    b = [row for row in _resistance_rows(0.8) if row["lap_dist_pct"] >= 0.40]
    for row in b:
        if row["lap_dist_pct"] > 0.60:
            row["speed_rate_mph_s"] = -1.8
    report = analyze_relative_resistance_aba(
        a1, b, _resistance_rows(0.8),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is True
    assert report.aba_confirmed is False
    assert report.relative_speed_loss_delta_mph_s == pytest.approx(0.0)


def test_relative_resistance_blocks_recorded_weather_tire_and_fuel_mismatch() -> None:
    b = _resistance_rows(1.0)
    for row in b:
        row.update({
            "air_temp": 40.0,
            "track_temp": 60.0,
            "wind_dir": 180.0,
            "fuel_level": 5.0,
            "lf_tire_distance_m": 0.0,
            "rf_tire_distance_m": 0.0,
            "lr_tire_distance_m": 0.0,
            "rr_tire_distance_m": 0.0,
        })
    report = analyze_relative_resistance_aba(
        _resistance_rows(0.8), b, _resistance_rows(0.82),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is False
    assert any("fuel, tire age, and weather" in reason for reason in report.gate.blocker_reasons)


def test_relative_resistance_missing_context_cannot_unlock_causal_attribution() -> None:
    missing = {
        "air_temp", "track_temp", "wind_vel", "wind_dir", "fuel_level",
        "lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m",
    }
    row_sets = []
    for loss in (0.8, 1.0, 0.82):
        row_sets.append([
            {key: value for key, value in row.items() if key not in missing}
            for row in _resistance_rows(loss)
        ])
    report = analyze_relative_resistance_aba(
        row_sets[0], row_sets[1], row_sets[2],
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is False
    assert report.windows
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)
    assert any("fuel, tire age, and weather" in reason for reason in report.gate.blocker_reasons)
    assert report.gate.needed_measurements


def test_relative_resistance_missing_discriminators_withholds_platform_ranking() -> None:
    missing = {
        "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
        "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
        "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
    }
    row_sets = []
    for loss in (0.8, 1.0, 0.82):
        row_sets.append([
            {key: value for key, value in row.items() if key not in missing}
            for row in _resistance_rows(loss)
        ])
    report = analyze_relative_resistance_aba(
        row_sets[0], row_sets[1], row_sets[2],
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is True
    assert report.aba_confirmed is True
    assert "platform_or_aero_related_proxy" not in report.cause_scores
    assert "platform_or_aero_related_proxy" in report.unavailable_cause_buckets
    assert report.cause_scores["unknown_residual"] >= 0.8
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)


def test_relative_resistance_requires_pointwise_operating_match_not_equal_medians() -> None:
    a1 = _resistance_rows(0.8)
    b = _resistance_rows(1.0)
    a2 = _resistance_rows(0.82)
    for index, row in enumerate(a1):
        row["speed_mph"] = 100.0 + index * 0.1
        row["rpm"] = 4500.0 + index * 10.0
    for index, row in enumerate(a2):
        row["speed_mph"] = 100.0 + index * 0.1
        row["rpm"] = 4500.0 + index * 10.0
    for index, row in enumerate(b):
        row["speed_mph"] = 110.0 - index * 0.1
        row["rpm"] = 5500.0 - index * 10.0
    report = analyze_relative_resistance_aba(
        a1, b, a2,
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is False
    assert any("speed, RPM, gear" in reason for reason in report.gate.blocker_reasons)


def test_relative_resistance_tiny_delta_stays_observation_not_aba_effect() -> None:
    report = analyze_relative_resistance_aba(
        _resistance_rows(0.8), _resistance_rows(0.800001), _resistance_rows(0.8),
        lap_summaries=(_laps(1), _laps(1), _laps(1)),
        selected_laps=(1, 1, 1),
        sim_integrity_clear=(True, True, True),
        isolated_single_change=True,
    )

    assert report.gate.eligible is True
    assert report.relative_speed_loss_delta_mph_s == pytest.approx(0.000001)
    assert report.practical_minimum_mph_s is not None
    assert report.practical_minimum_mph_s >= 0.02
    assert report.aba_confirmed is False
    assert report.cause_scores == {"unknown_residual": 1.0}
    assert all("recommendation" not in item.model_dump() for item in report.conclusions)


def test_aba_setup_isolation_rejects_unmapped_raw_change() -> None:
    from api.routes_p3_engineering import _aba_setup_change_isolated

    controls = {key: 1.0 for key in SETUP_CONTROL_SPECS}
    a1 = {
        **controls,
        "rear_end_ratio": 3.5,
        "setup_json": {"Chassis": {"Rear": {"FinalDriveRatio": 3.5, "DiffPreload": "20 Nm"}}},
    }
    b = {
        **controls,
        "rear_end_ratio": 3.6,
        "setup_json": {"Chassis": {"Rear": {"FinalDriveRatio": 3.6, "DiffPreload": "30 Nm"}}},
    }
    a2 = {**a1, "setup_json": {"Chassis": {"Rear": {"FinalDriveRatio": 3.5, "DiffPreload": "20 Nm"}}}}

    assert _aba_setup_change_isolated([a1, b, a2]) is False


def test_aba_api_requires_complete_matching_three_run_identity(monkeypatch) -> None:
    import api.routes_p3_engineering as routes

    identity = {
        "driver_user_id": "driver",
        "car_id": "car",
        "car_path": "cars/car",
        "car_version": "1",
        "track_id": "track",
        "track_configuration_name": "oval",
        "track_version": "2",
        "iracing_build_version": "build",
        "session_type": "Practice",
    }
    identities = {run: dict(identity) for run in ("a1", "b", "a2")}
    monkeypatch.setattr(
        routes,
        "read_telemetry_manifest",
        lambda run_id: {"compatibility_identity": identities[run_id]},
    )
    routes._assert_aba_compatibility(("a1", "b", "a2"))

    identities["b"]["car_version"] = "different"
    with pytest.raises(Exception) as mismatch:
        routes._assert_aba_compatibility(("a1", "b", "a2"))
    assert getattr(mismatch.value, "status_code", None) == 400

    identities["b"] = dict(identity)
    identities["a2"].pop("track_configuration_name")
    with pytest.raises(Exception) as missing:
        routes._assert_aba_compatibility(("a1", "b", "a2"))
    assert getattr(missing.value, "status_code", None) == 409


def _integrity_rows(*, dropped_tick: bool = False, low_fps: bool = False) -> list[dict]:
    rows = []
    for index in range(120):
        tick = index + (2 if dropped_tick and index >= 60 else 0)
        rows.append({
            "session_tick": tick,
            "session_time": index / 60.0,
            "frame_rate": 35.0 if low_fps else 120.0,
            "cpu_usage_foreground": 0.45,
            "cpu_usage_background": 0.10,
            "gpu_usage": 0.55,
            "memory_page_faults_per_s": 20.0,
            "memory_soft_page_faults_per_s": 10.0,
            "channel_latency_s": 0.02,
            "channel_average_latency_s": 0.02,
            "channel_quality": 0.99,
        })
    return rows


def test_sim_integrity_certificate_blocks_dropped_ticks_and_caps_comparison() -> None:
    clean = build_sim_integrity_certificate(
        _integrity_rows(), expected_sample_rate_hz=60.0,
    )
    failed = build_sim_integrity_certificate(
        _integrity_rows(dropped_tick=True), expected_sample_rate_hz=60.0,
    )

    assert clean.status == "pass"
    assert clean.is_clear_for_analysis is True
    assert failed.status == "fail"
    assert failed.dropped_tick_count == 2
    assert failed.is_clear_for_analysis is False
    clear, cap, reasons = comparison_integrity_gate(clean, failed)
    assert clear is False
    assert cap <= 0.35
    assert reasons


def test_integrity_warning_confidence_cap_survives_engine_gate() -> None:
    rows = _integrity_rows()
    for row in rows:
        row["frame_rate"] = 55.0
    certificate = build_sim_integrity_certificate(rows, expected_sample_rate_hz=60.0)
    report = analyze_damper_response(
        _damper_rows(),
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=certificate.is_clear_for_analysis,
        sim_integrity_confidence_cap=certificate.confidence_cap,
        setup_snapshot_captured=True,
    )

    assert certificate.status == "warning"
    assert certificate.confidence_cap == 0.65
    assert report.gate.confidence_cap == 0.65
    assert all(item.confidence_score <= 0.65 for item in report.conclusions)


def test_integrity_cohort_cannot_hide_failed_repetition_lap() -> None:
    from api.routes_p3_engineering import _cohort_integrity

    rows = []
    for lap in (1, 2):
        for index, row in enumerate(_integrity_rows()):
            item = {**row, "lap": lap}
            if lap == 2:
                item["session_tick"] = 1
                item["session_time"] = 1.0 - index / 60.0
            rows.append(item)
    clear, cap = _cohort_integrity(rows, _laps(2), 60.0)

    assert clear is False
    assert cap <= 0.35


def test_sim_integrity_missing_clock_data_is_unknown_not_zero() -> None:
    certificate = build_sim_integrity_certificate(
        [{"frame_rate": 120.0}], expected_sample_rate_hz=60.0,
    )

    assert certificate.status == "unknown"
    assert certificate.is_clear_for_analysis is None
    assert certificate.dropped_tick_count is None
    assert certificate.non_monotonic_clock_count is None


def test_sim_integrity_normalizes_percent_communication_quality() -> None:
    poor_rows = _integrity_rows()
    for row in poor_rows:
        row["channel_quality"] = 50.0
    good_rows = _integrity_rows()
    for row in good_rows:
        row["channel_quality"] = 95.0

    poor = build_sim_integrity_certificate(poor_rows, expected_sample_rate_hz=60.0)
    good = build_sim_integrity_certificate(good_rows, expected_sample_rate_hz=60.0)
    poor_quality = next(check for check in poor.checks if check.key == "communication_quality")
    good_quality = next(check for check in good.checks if check.key == "communication_quality")

    assert poor_quality.observed == pytest.approx(0.5)
    assert poor_quality.status == "fail"
    assert poor.is_clear_for_analysis is False
    assert good_quality.observed == pytest.approx(0.95)
    assert good_quality.status == "pass"
    assert good_quality.raw_observed == pytest.approx(95.0)
    assert good_quality.normalization_provenance == "percent_0_to_100"


@pytest.mark.parametrize("value", [1.0004, 1.0069])
def test_sim_integrity_accepts_only_narrow_unity_jitter(value: float) -> None:
    rows = _integrity_rows()
    for row in rows:
        row["channel_quality"] = value

    certificate = build_sim_integrity_certificate(rows, expected_sample_rate_hz=60.0)
    quality = next(check for check in certificate.checks if check.key == "communication_quality")

    assert quality.status == "pass"
    assert quality.observed == pytest.approx(1.0)
    assert quality.raw_observed == pytest.approx(value)
    assert quality.normalization_provenance == "ratio_unity_jitter_clamped_1pct"
    assert certificate.is_clear_for_analysis is True


@pytest.mark.parametrize(
    ("channel", "value", "check_key"),
    [
        ("frame_rate", -1.0, "frame_rate"),
        ("cpu_usage_foreground", -0.1, "cpu_headroom"),
        ("gpu_usage", 101.0, "gpu_headroom"),
        ("memory_page_faults_per_s", -1.0, "memory_faults"),
        ("channel_latency_s", -0.01, "communication_latency"),
        ("channel_quality", 101.0, "communication_quality"),
        ("channel_quality", 1.2, "communication_quality"),
    ],
)
def test_sim_integrity_rejects_impossible_system_values(
    channel: str,
    value: float,
    check_key: str,
) -> None:
    rows = _integrity_rows()
    for row in rows:
        row[channel] = value

    certificate = build_sim_integrity_certificate(rows, expected_sample_rate_hz=60.0)
    check = next(item for item in certificate.checks if item.key == check_key)

    assert check.status == "fail"
    assert certificate.is_clear_for_analysis is False
    if channel == "channel_quality":
        assert check.raw_observed == pytest.approx(value)
        assert check.observed is None
        assert check.normalization_provenance == "invalid_or_ambiguous"


def test_sim_integrity_fails_incomplete_paired_clock_coverage() -> None:
    rows = _integrity_rows()
    del rows[60]["session_time"]

    certificate = build_sim_integrity_certificate(rows, expected_sample_rate_hz=60.0)
    coverage = next(check for check in certificate.checks if check.key == "clock_coverage")

    assert coverage.status == "fail"
    assert certificate.core_clock_coverage_pct == pytest.approx(119 / 120 * 100.0)
    assert certificate.is_clear_for_analysis is False


@pytest.mark.parametrize("invalid_redline", [math.nan, math.inf, -1.0, 100.0, 50_000.0])
def test_powertrain_ignores_invalid_redline_and_remains_observational(
    invalid_redline: float,
) -> None:
    report = analyze_powertrain_gearing(
        _power_rows(2),
        _laps(2),
        selected_lap=1,
        sim_integrity_clear=True,
        redline_rpm=invalid_redline,
    )

    assert report.near_redline_occupancy_pct is None
    assert report.gearing_headroom_rpm is None
    assert "recommendation" not in report.conclusions[-1].model_dump()
    text = " ".join(
        report.conclusions[0].supporting_evidence
        + report.conclusions[-1].contradicting_evidence
    ).lower()
    assert "invalid" in text
    assert "500 to 30,000 rpm" in text


@pytest.mark.parametrize("client_redline", [math.inf, 500.0, 7000.0])
def test_powertrain_route_rejects_client_redline_before_loading_run(
    client_redline: float,
) -> None:
    from fastapi import Request

    from api.routes_p3_engineering import get_powertrain_gearing

    request = Request({
        "type": "http",
        "query_string": f"redline_rpm={client_redline}".encode(),
        "headers": [],
    })
    with pytest.raises(Exception) as error:
        get_powertrain_gearing("not-loaded", request=request)

    assert getattr(error.value, "status_code", None) == 422
    assert "redline_rpm" in str(getattr(error.value, "detail", ""))


def test_server_setup_redline_requires_one_unambiguous_persisted_value() -> None:
    from api.routes_p3_engineering import _server_setup_redline_rpm

    setup = {"setup_json": {"Engine": {"RevLimiter": "7,250 rpm"}}}
    assert _server_setup_redline_rpm(setup) is None
    # Thousands separators are deliberately not guessed: malformed/ambiguous setup text cannot become context.
    assert _server_setup_redline_rpm({"setup_json": {"Engine": {"RevLimiter": "7250 rpm"}}}) == 7250.0
    assert _server_setup_redline_rpm({
        "setup_json": {"Engine": {"RevLimiter": "7250 rpm", "Redline": "7000 rpm"}},
    }) is None


def test_grade_manifest_health_requires_declared_varying_meter_sources() -> None:
    from api.routes_p3_engineering import _manifest_grade_source_healthy

    def channel(canonical: str) -> dict:
        return {
            "canonical_name": canonical,
            "unit": "m",
            "provenance": "ibt_variable_definition",
            "archive_status": "cached",
            "health_status": "healthy",
            "variation": "varying",
            "valid_record_count": 100,
        }

    manifest = {
        "record_count": 100,
        "channels": [channel("alt"), channel("lap_dist_m")],
    }
    assert _manifest_grade_source_healthy(manifest) is True
    manifest["channels"][0]["unit"] = "ft"
    assert _manifest_grade_source_healthy(manifest) is False
    manifest["channels"][0]["unit"] = "m"
    manifest["channels"][0]["variation"] = "constant"
    assert _manifest_grade_source_healthy(manifest) is False


def test_damper_endpoint_executes_setup_capture_path_without_type_error(monkeypatch) -> None:
    from types import SimpleNamespace

    import api.routes_p3_engineering as routes

    overview = SimpleNamespace(
        laps=_laps(2),
        session=SimpleNamespace(telemetry_rate_hz=60.0),
    )
    setup = SimpleNamespace(model_dump=lambda: {
        "setup_id": "s", "run_id": "run", "setup_name": "baseline",
        "setup_json": {"Chassis": {"Front": {"Spring": "500 lb/in"}}},
    })
    monkeypatch.setattr(routes, "_selected_lap", lambda _run, _lap: (overview, 1))
    monkeypatch.setattr(routes, "_rows", lambda _run, _contract, _extra: _damper_rows(2))
    monkeypatch.setattr(routes, "_cohort_integrity", lambda _rows, _laps, _rate: (True, 1.0))
    monkeypatch.setattr(
        routes, "repository", lambda: SimpleNamespace(get_setup_snapshot=lambda _run: setup),
    )

    report = routes.get_damper_response("run", lap=1)

    assert report.run_id == "run"
    assert report.selected_lap == 1
    assert report.gate.eligible is True


def test_stint_endpoint_passes_server_session_type_to_strategy_engine(monkeypatch) -> None:
    from types import SimpleNamespace

    import api.routes_p3_engineering as routes

    overview = SimpleNamespace(
        laps=_laps(3),
        session=SimpleNamespace(telemetry_rate_hz=60.0, session_type="Race"),
    )
    captured: dict[str, object] = {}

    def fake_analyze(rows, laps, **kwargs):
        captured.update({"rows": rows, "laps": laps, **kwargs})
        return "report"

    monkeypatch.setattr(routes, "get_run_or_404", lambda _run: overview)
    monkeypatch.setattr(routes, "_rows", lambda _run, _contract, _extra: [{"lap": 1}])
    monkeypatch.setattr(routes, "_cohort_integrity", lambda _rows, _laps, _rate: (True, 0.9))
    monkeypatch.setattr(routes, "analyze_stint_strategy", fake_analyze)

    assert routes.get_stint_strategy("run") == "report"
    assert captured["session_type"] == "Race"
    assert captured["sim_integrity_clear"] is True
    assert captured["sim_integrity_confidence_cap"] == 0.9


def test_sim_performance_aliases_have_row_frame_parity() -> None:
    raw = [{
        "FrameRate": 118.0,
        "CpuUsageFG": 0.4,
        "CpuUsageBG": 0.1,
        "GpuUsage": 0.6,
        "ChanQuality": 0.98,
        "ChanLatency": 0.02,
        "ChanAvgLatency": 0.03,
        "MemPageFaultSec": 12.0,
        "MemSoftPageFaultSec": 8.0,
    }]
    row = normalize_telemetry_rows(raw)[0]
    frame = normalize_telemetry_frame(pl.DataFrame(raw)).to_dicts()[0]

    for channel in (
        "frame_rate", "cpu_usage_foreground", "cpu_usage_background", "gpu_usage",
        "channel_quality", "channel_latency_s", "channel_average_latency_s",
        "memory_page_faults_per_s", "memory_soft_page_faults_per_s",
    ):
        assert row[channel] == frame[channel]


def test_strategy_context_aliases_have_row_frame_parity() -> None:
    raw = [{
        "SessionState": 4,
        "SessionFlags": 0,
        "SessionTimeRemain": 1200.0,
        "SessionLapsRemain": 21,
        "SessionLapsRemainEx": 20,
        "SessionTimeTotal": 1800.0,
        "SessionLapsTotal": 30,
        "PitsOpen": True,
        "PitstopActive": False,
        "PitRepairLeft": 0.0,
        "PitOptRepairLeft": 5.0,
        "PitSvFlags": 63,
        "PitSvFuel": 20.0,
    }]
    row = normalize_telemetry_rows(raw)[0]
    frame = normalize_telemetry_frame(pl.DataFrame(raw)).to_dicts()[0]

    for channel in (
        "session_state", "session_flags", "session_time_remaining_s",
        "session_laps_remaining_legacy", "session_laps_remaining",
        "session_time_total_s", "session_laps_total", "pits_open",
        "pitstop_active", "pit_repair_remaining_s",
        "pit_optional_repair_remaining_s", "pending_pit_service_flags",
        "pending_pit_fuel_add",
    ):
        assert row[channel] == frame[channel]


@pytest.mark.parametrize(
    ("contract", "forbidden"),
    [
        (BRAKING_EFFICIENCY_CONTRACT, "friction_coefficient"),
        (TIRE_STATE_CONTRACT, "universal_hot_pressure_rule"),
        (DAMPER_RESPONSE_CONTRACT, "measured_damper_force"),
        (POWERTRAIN_GEARING_CONTRACT, "measured_engine_power"),
        (STINT_STRATEGY_CONTRACT, "short_run_tire_degradation"),
    ],
)
def test_p3_contracts_reject_prohibited_claims(contract, forbidden: str) -> None:
    result = evaluate_evidence_contract(
        contract,
        EvidenceEvaluationInput(
            usable_channels=contract.required_channels | contract.preferred_channels,
            condition_results={item.key: True for item in contract.operating_conditions},
            blocker_results={item.key: False for item in contract.hard_blockers},
            repetitions=3,
            requested_outputs=frozenset({forbidden}),
        ),
    )

    assert result.eligible is False
    assert result.denied_outputs == frozenset({forbidden})
    assert result.blockers[0].code == "forbidden_output"


def test_p3_engineering_endpoints_are_registered() -> None:
    from api.main import app

    paths = set(app.openapi()["paths"])
    assert {
        "/api/runs/{run_id}/braking-efficiency",
        "/api/runs/{run_id}/tire-state",
        "/api/runs/{run_id}/damper-response",
        "/api/runs/{run_id}/sim-integrity",
        "/api/runs/{run_id}/powertrain-gearing",
        "/api/runs/{run_id}/stint-strategy",
        "/api/runs/relative-resistance/aba",
    }.issubset(paths)
