from __future__ import annotations

import math
from dataclasses import replace

from racelab_engine.analysis.phase_engineering import _speed_bands, analyze_phase_engineering_systems
from racelab_engine.analysis.sim_integrity import (
    build_sim_integrity_certificate,
    comparison_integrity_gate,
)
from racelab_engine.analysis.phase_engineering_contracts import (
    AERO_PLATFORM_WINDOW_CONTRACT,
    CORNER_ROTATION_CONTRACT,
    DRIVER_LINE_CONTRACT,
)
from racelab_engine.analysis.time_alignment import analyze_time_alignment
from racelab_engine.models.evidence import EvidenceState


def _rows(*, driver_shift: bool = False, yaw_spike: bool = False, omit_geometry: bool = False) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []
    elapsed = 0.0
    for pct in range(101):
        angle = 2 * math.pi * pct / 100.0
        speed = 35.0 + 40.0 * (0.5 + 0.5 * math.sin(angle - math.pi / 2))
        if pct:
            elapsed += (100.0 / 3.280839895) / speed
        brake = 75.0 if 18 <= pct <= 23 else max(0.0, 75.0 - (pct - 23) * 12.0) if 24 <= pct <= 29 else 0.0
        throttle = 0.0 if 18 <= pct <= 30 else min(100.0, (pct - 30) * 12.0) if 31 <= pct <= 39 else 100.0
        steering = 12.0 if 20 <= pct <= 38 else 5.0
        if driver_shift:
            throttle = max(0.0, throttle - 8.0)
            brake = min(100.0, brake + (5.0 if 18 <= pct <= 29 else 0.0))
            steering += 2.5
        yaw = speed * 0.01
        if yaw_spike and pct == 32:
            yaw += 5.0
        row = {
            "lap_dist_pct_100": float(pct),
            "lap_dist_ft": pct * 100.0,
            "session_time": elapsed,
            "speed_mps": speed,
            "speed_mph": speed * 2.2369362920544,
            "throttle_pct": throttle,
            "brake_pct": brake,
            "steering_deg": steering,
            "yaw_rate": yaw,
            "lat_accel": speed * speed * 0.01,
            "long_accel": 0.0,
            "curvature_1_per_m": 0.01,
            "cfs_ride_height_in": 0.32 - speed * 0.0032,
            "front_avg_rh_in": 2.2 - speed * 0.005,
            "rear_avg_rh_in": 2.7 - speed * 0.003,
            "center_rake_fs_in": 0.5 + speed * 0.002,
            "side_rake_in": 0.015 * math.sin(2 * angle),
            "dynamic_pressure_psf": speed * speed * 0.014,
            "cfs_risk_score": max(0.0, (0.12 - (0.32 - speed * 0.0032)) * 10.0),
            "lf_ride_height_in": 2.2 - speed * 0.005 + 0.01,
            "rf_ride_height_in": 2.2 - speed * 0.005 - 0.01,
            "lr_ride_height_in": 2.7 - speed * 0.003 + 0.01,
            "rr_ride_height_in": 2.7 - speed * 0.003 - 0.01,
        }
        if not omit_geometry:
            row["lat"] = 33.0 + 0.001 * math.sin(angle)
            row["lon"] = -84.0 + 0.001 * math.cos(angle)
        result.append(row)
    return result


def _report(
    baseline: list[dict[str, float]],
    test: list[dict[str, float]],
    *,
    isolated: bool = True,
):
    alignment = analyze_time_alignment(baseline, test, step_pct=1.0)
    return analyze_phase_engineering_systems(
        baseline,
        test,
        alignment,
        baseline_run_id="baseline",
        test_run_id="test",
        baseline_lap=2,
        test_lap=2,
        eligible_laps=True,
        repetitions=3,
        setup_change_isolated=isolated,
        sim_integrity_clear=True,
        sim_integrity_confidence_cap=0.9,
        baseline_sim_integrity_status="pass",
        test_sim_integrity_status="pass",
        baseline_platform_laps=[baseline, baseline, baseline],
        test_platform_laps=[test, test, test],
    )


def test_three_systems_declare_proxy_safe_contracts() -> None:
    assert "setup_caused_driver_gain" in DRIVER_LINE_CONTRACT.forbidden_outputs
    assert "measured_sideslip_angle" in CORNER_ROTATION_CONTRACT.forbidden_outputs
    assert "measured_downforce" in AERO_PLATFORM_WINDOW_CONTRACT.forbidden_outputs
    assert "exact_aero_load" in AERO_PLATFORM_WINDOW_CONTRACT.forbidden_outputs
    states = {output.evidence_state for output in AERO_PLATFORM_WINDOW_CONTRACT.allowed_outputs}
    assert states == {EvidenceState.CALCULATED, EvidenceState.ESTIMATED_PROXY}


def test_driver_engine_reports_phase_metrics_and_allows_matched_execution() -> None:
    report = _report(_rows(), _rows())

    assert report.driver_line.gate.eligible is True
    assert report.driver_line.phase_metrics
    assert report.driver_line.driver_execution_changed is False
    assert report.driver_line.setup_attribution_allowed is True
    assert report.driver_line.throttle_mae_pct == 0.0
    assert report.driver_line.line_deviation_median_m == 0.0
    assert all(conclusion.source_channels for conclusion in report.driver_line.conclusions)


def test_driver_change_blocks_setup_attribution_and_rotation_claims() -> None:
    report = _report(_rows(), _rows(driver_shift=True))

    assert report.driver_line.driver_execution_changed is True
    assert report.driver_line.setup_attribution_allowed is False
    assert all(
        conclusion.evidence_state is EvidenceState.BLOCKED_BY_CONTEXT
        for conclusion in report.corner_rotation.conclusions
    )
    assert all(conclusion.blocker_reasons for conclusion in report.corner_rotation.conclusions)


def test_rotation_engine_is_sustained_phase_local_and_proxy_safe() -> None:
    report = _report(_rows(), _rows(yaw_spike=True))

    assert report.corner_rotation.gate.eligible is True
    assert report.corner_rotation.phase_metrics
    proxy = next(item for item in report.corner_rotation.conclusions if item.key == "balance_signature_proxy")
    assert proxy.evidence_state is EvidenceState.ESTIMATED_PROXY
    assert "not a measured" in proxy.summary
    assert not any("loose" in item.summary.lower() or "tight" in item.summary.lower() for item in report.corner_rotation.conclusions)
    # One yaw spike must not dominate a sustained median signature.
    errors = [
        metric.metrics.get("test_sustained_yaw_error_median_rad_s")
        for metric in report.corner_rotation.phase_metrics
    ]
    assert all(value is None or abs(float(value)) < 0.1 for value in errors)


def test_platform_engine_reports_speed_bands_risk_and_lap_consistency() -> None:
    report = _report(_rows(), _rows())
    platform = report.aero_platform

    assert platform.gate.eligible is True
    assert len(platform.baseline_speed_bands) >= 2
    assert platform.comparison_metrics["baseline"]["front_response_in_per_psf"] is not None
    assert "rake_hysteresis_proxy_in" in platform.comparison_metrics["baseline"]
    assert platform.comparison_metrics["baseline"]["rake_hysteresis_proxy_in"] == 0.0
    assert "settling_time_median_s" in platform.comparison_metrics["baseline"]
    assert "left_right_asymmetry_median_in" in platform.comparison_metrics["baseline"]
    assert platform.lap_consistency["baseline"]["eligible_laps"] == 3
    assert platform.lap_consistency["baseline"]["evidence_state"] == "calculated"
    proxy = next(item for item in platform.conclusions if item.key == "platform_risk_proxy")
    assert proxy.evidence_state is EvidenceState.ESTIMATED_PROXY
    assert "no aerodynamic load" in proxy.summary.lower()


def test_missing_geometry_blocks_driver_and_rotation_contracts() -> None:
    baseline = _rows(omit_geometry=True)
    test = _rows(omit_geometry=True)
    for row in [*baseline, *test]:
        row.pop("curvature_1_per_m", None)
    report = _report(baseline, test)

    assert report.driver_line.gate.eligible is False
    assert report.corner_rotation.gate.eligible is False
    assert any("geometric_curvature_1_per_m" in reason for reason in report.driver_line.gate.blocker_reasons)


def test_flatlined_direct_curvature_falls_back_to_healthy_gps_geometry() -> None:
    baseline = _rows()
    test = _rows()
    for row in [*baseline, *test]:
        row["curvature_1_per_m"] = 0.0

    report = _report(baseline, test)

    assert report.baseline_curvature_basis == "gps_fallback_direct_unhealthy"
    assert report.test_curvature_basis == "gps_fallback_direct_unhealthy"
    assert report.baseline_gps_geometry_healthy is True
    assert report.test_gps_geometry_healthy is True
    assert report.corner_rotation.gate.eligible is True
    expected_yaw = [
        metric.metrics["baseline_expected_yaw_rate_median_rad_s"]
        for metric in report.corner_rotation.phase_metrics
    ]
    assert any(value is not None and abs(float(value)) > 0.05 for value in expected_yaw)
    rotation_sources = {
        source
        for conclusion in report.corner_rotation.conclusions
        for source in conclusion.source_channels
    }
    assert {"lat", "lon"} <= rotation_sources
    assert "curvature_1_per_m" not in rotation_sources
    assert any("GPS-derived curvature" in warning for warning in report.warnings)


def test_flatlined_gps_blocks_line_similarity_and_setup_attribution() -> None:
    baseline = _rows()
    test = _rows()
    for row in [*baseline, *test]:
        row["lat"] = 33.0
        row["lon"] = -84.0

    report = _report(baseline, test)

    assert report.baseline_curvature_basis == "direct_curvature"
    assert report.test_curvature_basis == "direct_curvature"
    assert report.baseline_gps_geometry_healthy is False
    assert report.test_gps_geometry_healthy is False
    assert report.driver_line.gate.eligible is False
    assert report.driver_line.line_deviation_median_m is None
    assert report.driver_line.driver_execution_changed is None
    assert report.driver_line.setup_attribution_allowed is False
    assert all(
        conclusion.evidence_state is EvidenceState.BLOCKED_BY_CONTEXT
        for conclusion in report.corner_rotation.conclusions
    )
    assert any("GPS geometry is flatlined" in warning for warning in report.warnings)


def test_unexamined_lap_summaries_cannot_inflate_pair_confidence() -> None:
    report = _report(_rows(), _rows())

    # The helper advertises three repetitions, but this engine analyzed one
    # position-matched pair. Unexamined summaries cannot earn repetition credit.
    assert report.driver_line.gate.confidence_cap == 0.7
    assert report.corner_rotation.gate.confidence_cap == 0.7
    # Platform separately examines the supplied three-lap cohorts.
    assert report.aero_platform.gate.confidence_cap == 0.85


def test_unisolated_setup_change_blocks_all_three_contracts() -> None:
    report = _report(_rows(), _rows(), isolated=False)

    assert report.driver_line.gate.eligible is False
    assert report.corner_rotation.gate.eligible is False
    assert report.aero_platform.gate.eligible is False
    assert any("more than one mapped control" in reason for reason in report.aero_platform.gate.blocker_reasons)


def test_partial_alignment_blocks_system_outputs_instead_of_extrapolating() -> None:
    report = _report(_rows(), [row for row in _rows() if not 40 <= row["lap_dist_pct_100"] <= 60])

    assert report.alignment_coverage_fraction < 0.9
    assert report.driver_line.gate.eligible is False
    assert report.corner_rotation.gate.eligible is False
    assert report.aero_platform.gate.eligible is False


def test_staggered_missing_driver_samples_block_setup_attribution() -> None:
    baseline = _rows()
    test = _rows()
    for row in baseline:
        if row["lap_dist_pct_100"] >= 91:
            for channel in ("throttle_pct", "brake_pct", "steering_deg"):
                row.pop(channel)
    for row in test:
        if row["lap_dist_pct_100"] <= 9:
            for channel in ("throttle_pct", "brake_pct", "steering_deg"):
                row.pop(channel)

    report = _report(baseline, test)

    assert report.driver_line.gate.eligible is True
    assert report.driver_line.throttle_mae_pct is None
    assert report.driver_line.brake_mae_pct is None
    assert report.driver_line.steering_mae_deg is None
    assert report.driver_line.driver_execution_changed is None
    assert report.driver_line.setup_attribution_allowed is False
    similarity = next(
        item for item in report.driver_line.conclusions
        if item.key == "driver_execution_similarity"
    )
    assert similarity.evidence_state is EvidenceState.BLOCKED_BY_CONTEXT
    assert all(
        item.evidence_state is EvidenceState.BLOCKED_BY_CONTEXT
        for item in report.corner_rotation.conclusions
    )
    assert report.aero_platform.setup_attribution_allowed is False
    assert any("must not be credited" in warning for warning in report.warnings)


def test_failed_sim_integrity_blocks_all_three_systems() -> None:
    baseline = _rows()
    test = _rows()
    for index, row in enumerate(baseline):
        row.update({
            "session_tick": index if index < 50 else index + 4,
            "frame_rate": 20.0,
            "channel_quality": 0.0,
        })
    for index, row in enumerate(test):
        row.update({"session_tick": index, "frame_rate": 60.0, "channel_quality": 1.0})
    baseline_certificate = build_sim_integrity_certificate(baseline, expected_sample_rate_hz=20.0)
    test_certificate = build_sim_integrity_certificate(test, expected_sample_rate_hz=20.0)
    clear, cap, warnings = comparison_integrity_gate(baseline_certificate, test_certificate)
    alignment = analyze_time_alignment(baseline, test, step_pct=1.0)
    report = analyze_phase_engineering_systems(
        baseline,
        test,
        alignment,
        baseline_run_id="baseline",
        test_run_id="test",
        baseline_lap=2,
        test_lap=2,
        eligible_laps=True,
        repetitions=3,
        setup_change_isolated=True,
        sim_integrity_clear=clear,
        sim_integrity_confidence_cap=cap,
        baseline_sim_integrity_status=baseline_certificate.status,
        test_sim_integrity_status=test_certificate.status,
        sim_integrity_warnings=warnings,
    )

    assert baseline_certificate.status == "fail"
    assert report.sim_integrity_clear is False
    assert report.driver_line.gate.eligible is False
    assert report.corner_rotation.gate.eligible is False
    assert report.aero_platform.gate.eligible is False
    assert all(
        any("integrity" in reason.lower() for reason in system.gate.blocker_reasons)
        for system in (report.driver_line, report.corner_rotation, report.aero_platform)
    )


def test_integrity_warning_caps_every_system_and_conclusion() -> None:
    baseline = _rows()
    test = _rows()
    for rows in (baseline, test):
        for index, row in enumerate(rows):
            row.update({
                "session_time": index / 60.0,
                "session_tick": index,
                "frame_rate": 55.0,
                "channel_quality": 1.0,
            })
    baseline_certificate = build_sim_integrity_certificate(baseline, expected_sample_rate_hz=60.0)
    test_certificate = build_sim_integrity_certificate(test, expected_sample_rate_hz=60.0)
    clear, cap, warnings = comparison_integrity_gate(baseline_certificate, test_certificate)
    alignment = analyze_time_alignment(baseline, test, step_pct=1.0)
    report = analyze_phase_engineering_systems(
        baseline,
        test,
        alignment,
        baseline_run_id="baseline",
        test_run_id="test",
        baseline_lap=2,
        test_lap=2,
        eligible_laps=True,
        repetitions=3,
        setup_change_isolated=True,
        sim_integrity_clear=clear,
        sim_integrity_confidence_cap=cap,
        baseline_sim_integrity_status=baseline_certificate.status,
        test_sim_integrity_status=test_certificate.status,
        sim_integrity_warnings=warnings,
    )

    assert baseline_certificate.status == "warning"
    assert clear is True
    assert cap == 0.65
    for system in (report.driver_line, report.corner_rotation, report.aero_platform):
        assert system.gate.eligible is True
        assert system.gate.confidence_cap <= 0.65
        assert all(conclusion.confidence_score <= 0.65 for conclusion in system.conclusions)


def test_missing_values_are_not_counted_as_safe_platform_samples() -> None:
    run = {
        "speed_mph": [120.0] * 6,
        "cfs_ride_height_in": [None, None, None, 0.08, 0.20, None],
        "front_avg_rh_in": [2.0] * 6,
        "rear_avg_rh_in": [2.5] * 6,
        "center_rake_fs_in": [0.5] * 6,
    }

    bands = _speed_bands(run)

    assert len(bands) == 1
    assert bands[0].metrics["near_contact_proxy_duty"] == 0.5


def test_platform_tradeoff_flags_faster_run_with_lower_clearance_proxy() -> None:
    baseline = _rows()
    test = _rows()
    for row in test:
        row["session_time"] *= 0.99
        row["cfs_ride_height_in"] -= 0.04
    alignment = replace(analyze_time_alignment(baseline, test, step_pct=1.0), selected_effect_s=-0.12)
    report = analyze_phase_engineering_systems(
        baseline,
        test,
        alignment,
        baseline_run_id="baseline",
        test_run_id="test",
        baseline_lap=2,
        test_lap=2,
        eligible_laps=True,
        repetitions=3,
        setup_change_isolated=True,
        sim_integrity_clear=True,
        sim_integrity_confidence_cap=0.9,
        baseline_sim_integrity_status="pass",
        test_sim_integrity_status="pass",
        baseline_platform_laps=[baseline, baseline, baseline],
        test_platform_laps=[test, test, test],
    )
    delta = report.aero_platform.comparison_metrics["delta"]

    assert delta["selected_time_effect_s"] < 0
    assert delta["cfs_p05_in_delta"] < -0.01
    assert delta["tech_risk_proxy_delta"] > 0
    assert delta["time_platform_tradeoff"] == "faster_higher_platform_risk_proxy"
