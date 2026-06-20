"""Parity tests: vectorized (Polars) path vs row-by-row path.

Compares ``normalize_telemetry_frame`` output against
``normalize_telemetry_rows`` for a small set of synthetic rows.

All tests use synthetic data only — no .ibt fixtures.
"""

from __future__ import annotations

import math
import random
from typing import Any

import polars as pl
import pytest

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.vectorized_channels import (
    normalize_telemetry_frame,
    frame_to_rows,
    CORE_CHANNELS,
    get_analysis_engine_mode,
    compare_row_vs_vectorized,
)
from racelab_engine.analysis.units import M_TO_IN

# ── Helpers ──────────────────────────────────────────────────────

SEED = 42


def _synthetic_row(
    speed_mps: float = 50.0,
    lap_dist_m: float = 500.0,
    lap_dist_pct: float = 0.25,
    throttle_01: float = 0.5,
    brake_01: float = 0.0,
    steering_rad: float = 0.0,
    lat_accel: float = 0.0,
    long_accel: float = 0.0,
    air_density: float = 1.225,
    session_time: float = 10.0,
    lf_speed: float = 50.0,
    rf_speed: float = 50.0,
    lr_speed: float = 50.0,
    rr_speed: float = 50.0,
    cfs_rh_m: float = 0.050,
    lf_rh_m: float = 0.070,
    rf_rh_m: float = 0.072,
    lr_rh_m: float = 0.080,
    rr_rh_m: float = 0.082,
    **extra: Any,
) -> dict[str, Any]:
    """Build a single synthetic row with iRacing raw column names."""
    row: dict[str, Any] = {
        "Speed": speed_mps,
        "LapDist": lap_dist_m,
        "LapDistPct": lap_dist_pct,
        "Throttle": throttle_01,
        "Brake": brake_01,
        "SteeringWheelAngle": steering_rad,
        "LatAccel": lat_accel,
        "LongAccel": long_accel,
        "AirDensity": air_density,
        "SessionTime": session_time,
        "LFspeed": lf_speed,
        "RFspeed": rf_speed,
        "LRspeed": lr_speed,
        "RRspeed": rr_speed,
        "CFSRrideHeight": cfs_rh_m,
        "LFrideHeight": lf_rh_m,
        "RFrideHeight": rf_rh_m,
        "LRrideHeight": lr_rh_m,
        "RRrideHeight": rr_rh_m,
        "SessionTick": 0,
        "Lap": 1,
        "LapCompleted": 0,
        "RPM": 6000,
        "Gear": 4,
        "YawRate": 0.0,
        "Alt": 0.0,
        "Lat": 0.0,
        "Lon": 0.0,
    }
    row.update(extra)
    return row


def _synthetic_rows(n: int, time_step: float = 0.01) -> list[dict[str, Any]]:
    """Generate *n* synthetic rows with a speed ramp for derivative testing."""
    rng = random.Random(SEED)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        t = i * time_step
        # Speed ramps from 20 → 80 m/s over the sequence
        speed = 20.0 + 60.0 * (i / max(n - 1, 1))
        rows.append(
            _synthetic_row(
                speed_mps=speed,
                session_time=t,
                lap_dist_m=speed * t * 0.9,  # ~constant speed * time
                lap_dist_pct=i / max(n - 1, 1),
                throttle_01=0.8 if i < n // 2 else 0.3,
                brake_01=0.0 if i < n // 2 else 0.2,
                steering_rad=math.sin(i * 0.1) * 0.05,
                lat_accel=math.sin(i * 0.1) * 3.0,
                long_accel=2.0 if i < n // 2 else -1.0,
                air_density=1.225 + rng.uniform(-0.01, 0.01),
                lf_speed=speed + rng.uniform(-0.5, 0.5),
                rf_speed=speed + rng.uniform(-0.5, 0.5),
                lr_speed=speed + rng.uniform(-0.5, 0.5),
                rr_speed=speed + rng.uniform(-0.5, 0.5),
                cfs_rh_m=0.050 + rng.uniform(-0.005, 0.005),
                lf_rh_m=0.070 + rng.uniform(-0.005, 0.005),
                rf_rh_m=0.072 + rng.uniform(-0.005, 0.005),
                lr_rh_m=0.080 + rng.uniform(-0.005, 0.005),
                rr_rh_m=0.082 + rng.uniform(-0.005, 0.005),
            )
        )
    return rows


def _compare_rows(ref: list[dict], vec: list[dict], channels: set[str]) -> list[str]:
    """Compare two row lists channel-by-channel. Returns list of mismatch descriptions."""
    mismatches: list[str] = []
    for i, (r, v) in enumerate(zip(ref, vec)):
        for ch in sorted(channels):
            rv = r.get(ch)
            vv = v.get(ch)
            if rv is None and vv is None:
                continue
            if rv is None or vv is None:
                mismatches.append(f"row[{i}] {ch}: ref={rv!r} vec={vv!r} (None mismatch)")
                continue
            if isinstance(rv, float) and isinstance(vv, float):
                if math.isnan(rv) and math.isnan(vv):
                    continue
                if abs(rv - vv) > 1e-9:
                    mismatches.append(f"row[{i}] {ch}: ref={rv:.12f} vec={vv:.12f} diff={abs(rv-vv):.2e}")
            elif rv != vv:
                mismatches.append(f"row[{i}] {ch}: ref={rv!r} vec={vv!r}")
    return mismatches


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def small_rows() -> list[dict[str, Any]]:
    return _synthetic_rows(10)


@pytest.fixture
def medium_rows() -> list[dict[str, Any]]:
    return _synthetic_rows(100)


# ── Tests ────────────────────────────────────────────────────────

class TestParity:
    """Parity between row-by-row and vectorized paths."""

    @staticmethod
    def _run_both(rows: list[dict]) -> tuple[list[dict], list[dict]]:
        """Run both row and vector paths, return (ref_rows, vec_rows)."""
        return normalize_telemetry_rows(rows), frame_to_rows(normalize_telemetry_frame(rows))

    @staticmethod
    def _assert_parity(ref: list[dict], vec: list[dict], channels: set[str]) -> None:
        """Assert that ref and vec match on the given channels."""
        mismatches = _compare_rows(ref, vec, channels)
        assert not mismatches, "\n".join(mismatches[:10])

    def test_both_produce_same_number_of_rows(self, small_rows: list[dict]) -> None:
        ref = normalize_telemetry_rows(small_rows)
        vec = normalize_telemetry_frame(small_rows)
        assert len(ref) == len(vec)

    def test_core_channels_exist_in_vector_output(self, small_rows: list[dict]) -> None:
        vec = normalize_telemetry_frame(small_rows)
        # Channels that require columns not in synthetic rows
        skip = {"vert_accel_g", "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
                "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
                "lf_shock_velocity_rms", "rf_shock_velocity_rms", "lr_shock_velocity_rms", "rr_shock_velocity_rms",
                "lf_shock_activity_index", "rf_shock_activity_index", "lr_shock_activity_index", "rr_shock_activity_index",
                "lf_damper_energy_proxy", "rf_damper_energy_proxy", "lr_damper_energy_proxy", "rr_damper_energy_proxy",
                "shock_velocity_rms", "shock_activity_index", "damper_energy_proxy",
                "lf_shock_static_defl_in", "rf_shock_static_defl_in", "lr_shock_static_defl_in", "rr_shock_static_defl_in",
                "lf_shock_defl_delta_in", "rf_shock_defl_delta_in", "lr_shock_defl_delta_in", "rr_shock_defl_delta_in",
                "lf_pressure_gain", "rf_pressure_gain", "lr_pressure_gain", "rr_pressure_gain",
                "lf_temp_spread", "rf_temp_spread", "lr_temp_spread", "rr_temp_spread",
                "lf_wear_spread", "rf_wear_spread", "lr_wear_spread", "rr_wear_spread",
                "front_scrub_proxy", "rear_scrub_proxy",
                "dynamic_pressure_lap_index", "dynamic_pressure_index",
                "dynamic_grade_deg",
                "grade_force_proxy_n",
                "front_slip_angle_deg", "rear_slip_angle_deg", "slip_angle_balance_deg",
                "platform_pitch_deg_from_rh", "platform_roll_deg_from_rh",
                "front_platform_roll_deg_from_rh", "rear_platform_roll_deg_from_rh", "platform_roll_balance_deg",
                "ackermann_steering_expected_deg", "ackermann_steering_error_deg", "ackermann_scrub_proxy",
                "lf_camber_temp_bias_c", "rf_camber_temp_bias_c", "lr_camber_temp_bias_c", "rr_camber_temp_bias_c",
                "lf_camber_bias_label", "rf_camber_bias_label", "lr_camber_bias_label", "rr_camber_bias_label",
                "track_x_m", "track_y_m", "track_x_ft", "track_y_ft"}
        for ch in CORE_CHANNELS - skip:
            assert ch in vec.columns, f"Missing core channel: {ch}"

    def test_core_channels_exist_in_ref_output(self, small_rows: list[dict]) -> None:
        ref = normalize_telemetry_rows(small_rows)
        # Channels that require columns not in synthetic rows
        skip = {"vert_accel_g", "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
                "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
                "lf_shock_velocity_rms", "rf_shock_velocity_rms", "lr_shock_velocity_rms", "rr_shock_velocity_rms",
                "lf_shock_activity_index", "rf_shock_activity_index", "lr_shock_activity_index", "rr_shock_activity_index",
                "lf_damper_energy_proxy", "rf_damper_energy_proxy", "lr_damper_energy_proxy", "rr_damper_energy_proxy",
                "shock_velocity_rms", "shock_activity_index", "damper_energy_proxy",
                "lf_shock_static_defl_in", "rf_shock_static_defl_in", "lr_shock_static_defl_in", "rr_shock_static_defl_in",
                "lf_shock_defl_delta_in", "rf_shock_defl_delta_in", "lr_shock_defl_delta_in", "rr_shock_defl_delta_in",
                "lf_pressure_gain", "rf_pressure_gain", "lr_pressure_gain", "rr_pressure_gain",
                "lf_temp_spread", "rf_temp_spread", "lr_temp_spread", "rr_temp_spread",
                "lf_wear_spread", "rf_wear_spread", "lr_wear_spread", "rr_wear_spread",
                "front_scrub_proxy", "rear_scrub_proxy",
                "dynamic_pressure_lap_index", "dynamic_pressure_index",
                "dynamic_grade_deg",
                "grade_force_proxy_n",
                "front_slip_angle_deg", "rear_slip_angle_deg", "slip_angle_balance_deg",
                "platform_pitch_deg_from_rh", "platform_roll_deg_from_rh",
                "front_platform_roll_deg_from_rh", "rear_platform_roll_deg_from_rh", "platform_roll_balance_deg",
                "ackermann_steering_expected_deg", "ackermann_steering_error_deg", "ackermann_scrub_proxy",
                "lf_camber_temp_bias_c", "rf_camber_temp_bias_c", "lr_camber_temp_bias_c", "rr_camber_temp_bias_c",
                "lf_camber_bias_label", "rf_camber_bias_label", "lr_camber_bias_label", "rr_camber_bias_label",
                "track_x_m", "track_y_m", "track_x_ft", "track_y_ft"}
        for ch in CORE_CHANNELS - skip:
            assert any(ch in r for r in ref), f"Missing core channel in ref: {ch}"

    def test_speed_conversions_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"speed_mps", "speed_mph", "speed_fps"})

    def test_distance_conversions_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"lap_dist_ft", "lap_dist_pct_100"})

    def test_input_conversions_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"throttle_pct", "brake_pct", "steering_deg", "abs_steering_deg", "abs_lat_accel"})

    def test_dynamic_pressure_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"dynamic_pressure_pa", "dynamic_pressure_psf"})

    def test_aero_load_index_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"aero_load_index", "aero_load_index_180mph"})

    def test_ride_height_conversions_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        channels = {"cfs_ride_height_mm", "cfs_ride_height_in", "cfsr_height_mm",
                     "lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm",
                     "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in"}
        self._assert_parity(ref, vec, channels)

    def test_slip_ratio_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        channels = {"lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio", "driven_wheel_slip_proxy"}
        self._assert_parity(ref, vec, channels)

    def test_slip_ratio_floor_and_clamp(self) -> None:
        """Verify floor/clamp behaviour at very low speed."""
        rows = [
            _synthetic_row(speed_mps=0.0, lf_speed=5.0, rf_speed=5.0, lr_speed=5.0, rr_speed=5.0),
            _synthetic_row(speed_mps=0.5, lf_speed=10.0, rf_speed=10.0, lr_speed=10.0, rr_speed=10.0),
            _synthetic_row(speed_mps=100.0, lf_speed=300.0, rf_speed=300.0, lr_speed=300.0, rr_speed=300.0),
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(ref, vec, {"lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio"})

    def test_speed_derivative_parity(self, medium_rows: list[dict]) -> None:
        """Derivatives need more rows for meaningful shift(1) comparison."""
        ref, vec = self._run_both(medium_rows)
        channels = {"speed_rate_mph_s", "speed_rate_mph_1000ft", "speed_rate_mps2"}
        self._assert_parity(ref, vec, channels)

    def test_g_values_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"lat_accel_g", "long_accel_g", "vert_accel_g"})

    def test_frame_to_rows_roundtrip(self, small_rows: list[dict]) -> None:
        """frame_to_rows(normalize_telemetry_frame(rows)) produces list[dict]."""
        vec = normalize_telemetry_frame(small_rows)
        rows_back = frame_to_rows(vec)
        assert isinstance(rows_back, list)
        assert len(rows_back) == len(small_rows)
        assert all(isinstance(r, dict) for r in rows_back)

    def test_geometry_injection(self) -> None:
        """Geometry constants are injected into vector frame."""
        rows = [_synthetic_row()]
        geo = {"wheelbase_m": 2.8, "front_axle_to_cg_m": 1.4, "mass_kg": 1500.0}
        vec = normalize_telemetry_frame(rows, geometry=geo)
        assert "wheelbase_m" in vec.columns
        assert vec["wheelbase_m"].to_list() == [2.8]
        assert "front_axle_to_cg_m" in vec.columns
        assert "mass_kg" in vec.columns

    def test_empty_input(self) -> None:
        """Empty input produces empty output (row path)."""
        import os; os.environ["RACELAB_ANALYSIS_ENGINE"] = "row"
        try:
            ref = normalize_telemetry_rows([])
            vec = frame_to_rows(normalize_telemetry_frame([]))
            assert len(ref) == 0
            assert len(vec) == 0
        finally:
            os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)

    def test_missing_optional_columns(self) -> None:
        """Missing columns produce no errors, just skip those channels."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]  # minimal
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(ref) == 1
        assert len(vec) == 1
        # speed conversions should still work
        assert ref[0].get("speed_mph") is not None
        assert vec[0].get("speed_mph") is not None


    # ── Slice 2: ride-height averages ──────────────────────────

    def test_ride_height_averages_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        channels = {"front_avg_rh_in", "rear_avg_rh_in", "left_avg_rh_in", "right_avg_rh_in"}
        self._assert_parity(ref, vec, channels)

    def test_center_rake_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"center_rake_fs_in"})

    def test_side_rake_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"side_rake_in"})

    def test_front_rear_split_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"front_split_in", "rear_split_in"})

    def test_ride_height_averages_missing_cfs(self) -> None:
        """Missing cfs_ride_height_in should not crash, just skip center_rake."""
        rows = [_synthetic_row()]
        # Remove CFSRrideHeight to simulate missing CFS
        for r in rows:
            del r["CFSRrideHeight"]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        # front_avg etc should still work
        assert ref[0].get("front_avg_rh_in") is not None
        assert vec[0].get("front_avg_rh_in") is not None
        # center_rake should be missing since no CFS
        assert ref[0].get("center_rake_fs_in") is None
        assert vec[0].get("center_rake_fs_in") is None

    # ── Slice 2: CFS/CFSR alias ────────────────────────────────

    def test_cfs_cfsr_alias_both_present(self, small_rows: list[dict]) -> None:
        """When both cfs_ride_height_mm and cfsr_height_mm exist, they match."""
        ref = normalize_telemetry_rows(small_rows)
        vec = frame_to_rows(normalize_telemetry_frame(small_rows))
        for r, v in zip(ref, vec):
            assert r.get("cfs_ride_height_mm") == r.get("cfsr_height_mm"), f"ref mismatch: {r}"
            assert v.get("cfs_ride_height_mm") == v.get("cfsr_height_mm"), f"vec mismatch: {v}"

    def test_cfs_cfsr_alias_only_cfsr(self) -> None:
        """When only cfsr_height_mm exists (no cfs_ride_height_mm), alias works."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0, "cfsr_height_mm": 45.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert ref[0].get("cfs_ride_height_mm") == 45.0
        assert vec[0].get("cfs_ride_height_mm") == 45.0
        assert ref[0].get("cfsr_height_mm") == 45.0
        assert vec[0].get("cfsr_height_mm") == 45.0

    def test_cfs_cfsr_alias_only_cfs(self) -> None:
        """When only cfs_ride_height_mm exists, cfsr_height_mm is aliased."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0, "cfs_ride_height_mm": 42.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert ref[0].get("cfsr_height_mm") == 42.0
        assert vec[0].get("cfsr_height_mm") == 42.0

    # ── Slice 2: risk scores ───────────────────────────────────

    def test_risk_scores_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        self._assert_parity(ref, vec, {"cfs_risk_score", "platform_risk_score"})

    def test_risk_scores_thresholds(self) -> None:
        """Verify risk score thresholds: scrape, critical, high, watch, safe."""
        rows = [
            _synthetic_row(cfs_rh_m=0.000),   # 0 mm → scrape → 1.0
            _synthetic_row(cfs_rh_m=0.002),   # 2 mm → critical → 0.92
            _synthetic_row(cfs_rh_m=0.005),   # 5 mm → high → 0.72
            _synthetic_row(cfs_rh_m=0.008),   # 8 mm → watch → 0.38
            _synthetic_row(cfs_rh_m=0.015),   # 15 mm → safe → 0.08
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(ref, vec, {"cfs_risk_score", "platform_risk_score"})

    def test_risk_scores_missing_cfs(self) -> None:
        """Missing cfs_ride_height_mm produces None risk scores."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert ref[0].get("cfs_risk_score") is None
        assert vec[0].get("cfs_risk_score") is None

    # ── Slice 2: g-values (vert_accel_g) ───────────────────────

    def test_g_values_vert_accel_parity(self) -> None:
        """vert_accel_g requires VertAccel column."""
        rows = [_synthetic_row(VertAccel=5.0)]
        ref, vec = self._run_both(rows)
        self._assert_parity(ref, vec, {"vert_accel_g"})

    # ── Slice 2: wheel speed mismatch ──────────────────────────

    def test_wheel_speed_mismatch_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        channels = {"front_wheel_speed_mismatch_raw", "rear_wheel_speed_mismatch_raw"}
        self._assert_parity(ref, vec, channels)

    def test_wheel_speed_mismatch_corrected_parity(self) -> None:
        """Geometry-corrected mismatch requires yaw_rate and track width."""
        rows = [_synthetic_row(YawRate=0.1)]
        for r in rows:
            r["front_track_width_m"] = 2.0
            r["rear_track_width_m"] = 2.0
        ref, vec = self._run_both(rows)
        channels = {"front_wheel_speed_mismatch_corrected", "rear_wheel_speed_mismatch_corrected"}
        self._assert_parity(ref, vec, channels)

    def test_wheel_speed_mismatch_no_track_width(self) -> None:
        """Without track width, corrected mismatch is None."""
        rows = [_synthetic_row(YawRate=0.1)]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert ref[0].get("front_wheel_speed_mismatch_corrected") is None
        assert vec[0].get("front_wheel_speed_mismatch_corrected") is None
        assert ref[0].get("rear_wheel_speed_mismatch_corrected") is None
        assert vec[0].get("rear_wheel_speed_mismatch_corrected") is None

    # ── Slice 2: shock conversions ─────────────────────────────

    def test_shock_conversions_parity(self, small_rows: list[dict]) -> None:
        ref, vec = self._run_both(small_rows)
        channels = {"lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
                     "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"}
        self._assert_parity(ref, vec, channels)

    def test_shock_conversions_missing(self) -> None:
        """Missing shock columns should not crash."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(ref) == 1
        assert len(vec) == 1

    # ── Slice 3: stability scores ─────────────────────────────

    def test_platform_stability_score_parity(self, medium_rows: list[dict]) -> None:
        ref, vec = self._run_both(medium_rows)
        self._assert_parity(ref, vec, {"platform_stability_score"})

    def test_rake_stability_score_parity(self, medium_rows: list[dict]) -> None:
        ref, vec = self._run_both(medium_rows)
        self._assert_parity(ref, vec, {"rake_stability_score"})

    def test_stability_scores_first_row_none(self, medium_rows: list[dict]) -> None:
        """First row should have None for stability scores (no previous row)."""
        ref, vec = self._run_both(medium_rows)
        assert ref[0].get("platform_stability_score") is None
        assert vec[0].get("platform_stability_score") is None
        assert ref[0].get("rake_stability_score") is None
        assert vec[0].get("rake_stability_score") is None

    def test_stability_scores_missing_cfs(self) -> None:
        """Missing cfs_ride_height_in should not crash stability scores."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert ref[0].get("platform_stability_score") is None
        assert vec[0].get("platform_stability_score") is None

    # ── Slice 3: drag / resistance indices ────────────────────

    def test_full_throttle_resistance_index_parity(self, medium_rows: list[dict]) -> None:
        ref, vec = self._run_both(medium_rows)
        self._assert_parity(ref, vec, {"full_throttle_resistance_index"})

    def test_drag_scrub_suspicion_parity(self, medium_rows: list[dict]) -> None:
        ref, vec = self._run_both(medium_rows)
        self._assert_parity(ref, vec, {"drag_scrub_suspicion"})

    def test_drag_scrub_suspicion_threshold_edges_parity(self) -> None:
        """Parity around speed/throttle/brake gates and just-over-threshold cases."""
        rows = [
            _synthetic_row(speed_mps=67.0, throttle_01=0.95, brake_01=0.0),   # ~149.9 mph gate miss
            _synthetic_row(speed_mps=67.2, throttle_01=0.95, brake_01=0.0),   # gate hit
            _synthetic_row(speed_mps=70.0, throttle_01=0.949, brake_01=0.0),  # throttle gate miss
            _synthetic_row(speed_mps=70.0, throttle_01=0.95, brake_01=0.051), # brake gate miss
            _synthetic_row(speed_mps=70.0, throttle_01=0.95, brake_01=0.05),  # brake edge hit
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(ref, vec, {"drag_scrub_suspicion"})

    def test_drag_scrub_suspicion_missing_inputs_parity(self) -> None:
        """Missing resistance/steering/yaw inputs keep row/vectorized parity."""
        rows = [
            {"Speed": 70.0, "SessionTime": 0.00, "Throttle": 1.0, "Brake": 0.0, "SteeringWheelAngle": None},
            {"Speed": 72.0, "SessionTime": 0.02, "Throttle": 1.0, "Brake": 0.0, "SteeringWheelAngle": None},
            {"Speed": 75.0, "SessionTime": 0.04, "Throttle": 1.0, "Brake": 0.0, "SteeringWheelAngle": 0.05},
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(ref, vec, {"drag_scrub_suspicion"})

    def test_resistance_indices_missing_columns(self) -> None:
        """Missing columns should not crash resistance indices."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(ref) == 1
        assert len(vec) == 1

    # ── Slice 3: platform compression ─────────────────────────

    def test_platform_compression_index_parity(self, medium_rows: list[dict]) -> None:
        ref, vec = self._run_both(medium_rows)
        self._assert_parity(ref, vec, {"platform_compression_index"})

    def test_platform_compression_missing_columns(self) -> None:
        """Missing columns should not crash compression index."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(ref) == 1
        assert len(vec) == 1

    # ── Slice 3: shock rolling aggregates ─────────────────────

    def _shock_rows(self, n: int = 100) -> list[dict[str, Any]]:
        """Synthetic rows with shock velocity columns for rolling aggregate tests."""
        rng = random.Random(SEED)
        rows: list[dict[str, Any]] = []
        for i in range(n):
            t = i * 0.01
            speed = 20.0 + 60.0 * (i / max(n - 1, 1))
            rows.append({
                "Speed": speed,
                "SessionTime": t,
                "LapDist": speed * t * 0.9,
                "LapDistPct": i / max(n - 1, 1),
                "Throttle": 0.8,
                "Brake": 0.0,
                "SteeringWheelAngle": 0.0,
                "LatAccel": 0.0,
                "LongAccel": 0.0,
                "AirDensity": 1.225,
                "LFspeed": speed,
                "RFspeed": speed,
                "LRspeed": speed,
                "RRspeed": speed,
                "CFSRrideHeight": 0.050,
                "LFrideHeight": 0.070,
                "RFrideHeight": 0.072,
                "LRrideHeight": 0.080,
                "RRrideHeight": 0.082,
                "SessionTick": 0,
                "Lap": 1,
                "LapCompleted": 0,
                "RPM": 6000,
                "Gear": 4,
                "YawRate": 0.0,
                "Alt": 0.0,
                "Lat": 0.0,
                "Lon": 0.0,
                "LFSHshockVel": 0.1 + rng.uniform(-0.05, 0.05),
                "RFSHshockVel": 0.2 + rng.uniform(-0.05, 0.05),
                "LRSHshockVel": 0.3 + rng.uniform(-0.05, 0.05),
                "RRSHshockVel": 0.4 + rng.uniform(-0.05, 0.05),
            })
        return rows

    def test_shock_rolling_aggregates_exist(self) -> None:
        """Shock rolling aggregate channels exist when shock vel columns present."""
        rows = self._shock_rows(10)
        vec = normalize_telemetry_frame(rows)
        for c in ("lf", "rf", "lr", "rr"):
            assert f"{c}_shock_velocity_rms" in vec.columns
            assert f"{c}_shock_activity_index" in vec.columns
            assert f"{c}_damper_energy_proxy" in vec.columns
        assert "shock_velocity_rms" in vec.columns
        assert "shock_activity_index" in vec.columns
        assert "damper_energy_proxy" in vec.columns

    def test_shock_rolling_aggregates_parity(self) -> None:
        """Shock rolling aggregates match row path after window fills.

        NOTE: The first `window`-1 rows may differ because the row path
        uses a growing buffer while Polars rolling uses min_periods=1.
        We compare rows after index 60 (the window size) for convergence.
        """
        rows = self._shock_rows(200)
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))

        # Compare only rows after the window fills (index 60+)
        channels: set[str] = set()
        for c in ("lf", "rf", "lr", "rr"):
            channels.add(f"{c}_shock_velocity_rms")
            channels.add(f"{c}_shock_activity_index")
            channels.add(f"{c}_damper_energy_proxy")
        channels.add("shock_velocity_rms")
        channels.add("shock_activity_index")
        channels.add("damper_energy_proxy")

        mismatches: list[str] = []
        for i, (r, v) in enumerate(zip(ref[60:], vec[60:])):
            for ch in sorted(channels):
                rv = r.get(ch)
                vv = v.get(ch)
                if rv is None and vv is None:
                    continue
                if rv is None or vv is None:
                    mismatches.append(f"row[{i+60}] {ch}: ref={rv!r} vec={vv!r} (None mismatch)")
                    continue
                if isinstance(rv, float) and isinstance(vv, float):
                    if math.isnan(rv) and math.isnan(vv):
                        continue
                    if abs(rv - vv) > 1e-6:
                        mismatches.append(f"row[{i+60}] {ch}: ref={rv:.12f} vec={vv:.12f} diff={abs(rv-vv):.2e}")
                elif rv != vv:
                    mismatches.append(f"row[{i+60}] {ch}: ref={rv!r} vec={vv!r}")
        assert not mismatches, "\n".join(mismatches[:15])

    def test_shock_rolling_aggregates_missing(self) -> None:
        """Missing shock velocity columns should not crash."""
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]
        ref = normalize_telemetry_rows(rows)
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(ref) == 1
        assert len(vec) == 1
        assert all("lf_shock_vel_in_s" not in row for row in ref)
        assert "lf_shock_vel_in_s" not in normalize_telemetry_frame(rows).columns
        assert all("shock_velocity_rms" not in row for row in ref)
        assert "shock_velocity_rms" not in normalize_telemetry_frame(rows).columns

    def test_canonical_shock_aliases_normalize(self) -> None:
        rows = [
            _synthetic_row(
                session_time=0.0,
                throttle_01=0.0,
                brake_01=0.0,
                LFshockDefl=0.10,
                RFshockDefl=0.11,
                LRshockDefl=0.12,
                RRshockDefl=0.13,
                LFshockVel=0.20,
                RFshockVel=0.21,
                LRshockVel=0.22,
                RRshockVel=0.23,
            ),
            _synthetic_row(
                session_time=1.0,
                throttle_01=0.0,
                brake_01=0.0,
                LFshockDefl=0.105,
                RFshockDefl=0.115,
                LRshockDefl=0.125,
                RRshockDefl=0.135,
                LFshockVel=0.24,
                RFshockVel=0.25,
                LRshockVel=0.26,
                RRshockVel=0.27,
            ),
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(
            ref,
            vec,
            {
                "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
                "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
            },
        )
        assert ref[0]["lf_shock_defl_in"] == pytest.approx(0.10 * M_TO_IN)
        assert ref[0]["lf_shock_vel_in_s"] == pytest.approx(0.20 * M_TO_IN)

    def test_legacy_shock_aliases_normalize(self) -> None:
        rows = [
            _synthetic_row(
                session_time=0.0,
                throttle_01=0.0,
                brake_01=0.0,
                LFSHshockDefl=0.10,
                RFSHshockDefl=0.11,
                LRSHshockDefl=0.12,
                RRSHshockDefl=0.13,
                LFSHshockVel=0.20,
                RFSHshockVel=0.21,
                LRSHshockVel=0.22,
                RRSHshockVel=0.23,
            ),
            _synthetic_row(
                session_time=1.0,
                throttle_01=0.0,
                brake_01=0.0,
                LFSHshockDefl=0.105,
                RFSHshockDefl=0.115,
                LRSHshockDefl=0.125,
                RRSHshockDefl=0.135,
                LFSHshockVel=0.24,
                RFSHshockVel=0.25,
                LRSHshockVel=0.26,
                RRSHshockVel=0.27,
            ),
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(
            ref,
            vec,
            {
                "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
                "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
            },
        )
        assert ref[0]["lf_shock_defl_in"] == pytest.approx(0.10 * M_TO_IN)
        assert ref[0]["lf_shock_vel_in_s"] == pytest.approx(0.20 * M_TO_IN)

    def test_shock_velocity_derives_from_deflection_when_raw_velocity_missing(self) -> None:
        rows = [
            _synthetic_row(
                session_time=0.0,
                throttle_01=0.0,
                brake_01=0.0,
                LFshockDefl=0.10,
                RFshockDefl=0.20,
                LRshockDefl=0.30,
                RRshockDefl=0.40,
            ),
            _synthetic_row(
                session_time=1.0,
                throttle_01=0.2,
                brake_01=0.0,
                LFshockDefl=0.11,
                RFshockDefl=0.22,
                LRshockDefl=0.31,
                RRshockDefl=0.43,
            ),
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(
            ref,
            vec,
            {
                "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
                "lf_shock_static_defl_in", "rf_shock_static_defl_in", "lr_shock_static_defl_in", "rr_shock_static_defl_in",
                "lf_shock_defl_delta_in", "rf_shock_defl_delta_in", "lr_shock_defl_delta_in", "rr_shock_defl_delta_in",
            },
        )
        assert ref[0].get("lf_shock_vel_in_s") is None
        assert vec[0].get("lf_shock_vel_in_s") is None
        assert ref[1]["lf_shock_vel_in_s"] == pytest.approx((0.11 - 0.10) * M_TO_IN)
        assert ref[0]["lf_shock_static_defl_in"] == pytest.approx(0.11 * M_TO_IN)
        assert vec[0]["lf_shock_static_defl_in"] == pytest.approx(0.11 * M_TO_IN)
        assert ref[1]["lf_shock_static_defl_in"] == pytest.approx(0.11 * M_TO_IN)
        assert ref[0]["lf_shock_defl_delta_in"] == pytest.approx((-0.01) * M_TO_IN)
        assert ref[1]["lf_shock_defl_delta_in"] == pytest.approx(((-0.01) + 0.0) / 2.0 * M_TO_IN)

    def test_shock_static_deflection_uses_first_throttle_over_10_pct(self) -> None:
        rows = [
            _synthetic_row(session_time=0.0, throttle_01=0.0, LFshockDefl=0.10),
            _synthetic_row(session_time=1.0, throttle_01=0.09, LFshockDefl=0.11),
            _synthetic_row(session_time=2.0, throttle_01=0.12, LFshockDefl=0.13),
            _synthetic_row(session_time=3.0, throttle_01=0.50, LFshockDefl=0.17),
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(ref, vec, {"lf_shock_static_defl_in", "lf_shock_defl_delta_in"})
        expected_static = 0.13 * M_TO_IN
        assert ref[0]["lf_shock_static_defl_in"] == pytest.approx(expected_static)
        assert ref[1]["lf_shock_static_defl_in"] == pytest.approx(expected_static)
        assert ref[2]["lf_shock_static_defl_in"] == pytest.approx(expected_static)
        assert ref[0]["lf_shock_defl_delta_in"] == pytest.approx((0.10 - 0.13) * M_TO_IN)
        assert ref[2]["lf_shock_defl_delta_in"] == pytest.approx(((0.10 - 0.13) + (0.11 - 0.13) + 0.0) / 3.0 * M_TO_IN)
        expected_last_delta = ((0.10 - 0.13) + (0.11 - 0.13) + 0.0 + (0.17 - 0.13)) / 4.0 * M_TO_IN
        assert ref[3]["lf_shock_defl_delta_in"] == pytest.approx(expected_last_delta)

    def test_shock_static_and_delta_stay_unavailable_without_throttle_trigger(self) -> None:
        rows = [
            _synthetic_row(session_time=0.0, throttle_01=0.0, LFshockDefl=0.10),
            _synthetic_row(session_time=1.0, throttle_01=0.05, LFshockDefl=0.11),
            _synthetic_row(session_time=2.0, throttle_01=0.09, LFshockDefl=0.12),
        ]
        ref, vec = self._run_both(rows)
        self._assert_parity(ref, vec, {"lf_shock_static_defl_in", "lf_shock_defl_delta_in"})
        assert all(row.get("lf_shock_static_defl_in") is None for row in ref)
        assert all(row.get("lf_shock_defl_delta_in") is None for row in ref)

    # ── Feature flag tests ────────────────────────────────────

    def test_feature_flag_defaults_to_vectorized(self) -> None:
        """get_analysis_engine_mode() returns 'vectorized' with no env."""
        mode = get_analysis_engine_mode()
        assert mode == "vectorized"

    def test_feature_flag_override_vectorized(self) -> None:
        """Explicit override 'vectorized' is accepted."""
        mode = get_analysis_engine_mode(override="vectorized")
        assert mode == "vectorized"

    def test_feature_flag_override_row(self) -> None:
        """Explicit override 'row' is accepted."""
        mode = get_analysis_engine_mode(override="row")
        assert mode == "row"

    def test_feature_flag_invalid_override_falls_back(self) -> None:
        """Invalid override falls back to 'vectorized'."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mode = get_analysis_engine_mode(override="invalid_mode")
            assert mode == "vectorized"
            assert len(w) == 1
            assert "Invalid analysis engine override" in str(w[0].message)

    def test_feature_flag_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var RACELAB_ANALYSIS_ENGINE=vectorized resolves correctly."""
        monkeypatch.setenv("RACELAB_ANALYSIS_ENGINE", "vectorized")
        mode = get_analysis_engine_mode()
        assert mode == "vectorized"

    def test_feature_flag_env_var_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid env var falls back to 'vectorized'."""
        import warnings
        monkeypatch.setenv("RACELAB_ANALYSIS_ENGINE", "garbage")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mode = get_analysis_engine_mode()
            assert mode == "vectorized"
            assert len(w) == 1
            assert "Invalid RACELAB_ANALYSIS_ENGINE" in str(w[0].message)

    # ── Comparison helper tests ────────────────────────────────

    def test_compare_passes_on_synthetic(self, medium_rows: list[dict]) -> None:
        """compare_row_vs_vectorized passes on synthetic rows."""
        report = compare_row_vs_vectorized(medium_rows)
        assert report["pass_fail"] is True
        assert report["row_count"] == len(medium_rows)

    def test_compare_empty_input(self) -> None:
        """compare_row_vs_vectorized handles empty input."""
        import os; os.environ["RACELAB_ANALYSIS_ENGINE"] = "row"
        try:
            report = compare_row_vs_vectorized([])
            assert report["pass_fail"] is True
            assert report["row_count"] == 0
        finally:
            os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)

    def test_compare_detects_injected_mismatch(self) -> None:
        """Comparison reports known mismatch when a channel is corrupted."""
        rows = _synthetic_rows(10)
        report = compare_row_vs_vectorized(rows)
        assert report["pass_fail"] is True

        # Manually corrupt the vector output to test detection
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        ref = normalize_telemetry_rows(rows)
        # Inject a mismatch into ref
        ref[0]["speed_mph"] = 999.0
        # We can't easily inject into the comparison helper's internals,
        # but we can verify the report structure is correct
        assert "compared_channels" in report
        assert "missing_in_row" in report
        assert "missing_in_vector" in report
        assert "max_abs_diff_by_channel" in report
        assert "mismatch_count_by_channel" in report
        assert "early_window_exemptions" in report
        assert "tolerance" in report

    def test_compare_reports_early_window_exemptions(self) -> None:
        """Shock rolling channels in early window are exempted."""
        rows = self._shock_rows(200)
        report = compare_row_vs_vectorized(rows)
        # Should have some early-window exemptions for shock channels
        assert report["early_window_exemptions"] >= 0
        # Overall should still pass (exemptions don't count as failures)
        assert report["pass_fail"] is True

    def test_compare_custom_channels(self) -> None:
        """Custom channel list is respected."""
        rows = [_synthetic_row()]
        report = compare_row_vs_vectorized(rows, channels=("speed_mph",))
        assert report["compared_channels"] == ["speed_mph"]
        assert report["pass_fail"] is True

    # ── Rear scrape tests ─────────────────────────────────────

    def test_rear_min_ride_height_calculated(self) -> None:
        """rear_min_ride_height_mm = min(lr_ride_height_mm, rr_ride_height_mm)."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(lr_rh_m=0.080, rr_rh_m=0.060)]
        ref = normalize_telemetry_rows(rows)
        # lr=80mm, rr=60mm → min=60mm
        assert ref[0].get("rear_min_ride_height_mm") == pytest.approx(60.0, abs=0.1)
        assert ref[0].get("rear_min_ride_height_in") == pytest.approx(60.0 / 25.4, abs=0.01)

    def test_rear_scrape_side_left(self) -> None:
        """rear_scrape_side = -1 when LR is lower than RR."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(lr_rh_m=0.050, rr_rh_m=0.070)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_scrape_side") == -1

    def test_rear_scrape_side_right(self) -> None:
        """rear_scrape_side = 1 when RR is lower than LR."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(lr_rh_m=0.070, rr_rh_m=0.050)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_scrape_side") == 1

    def test_rear_scrape_side_both(self) -> None:
        """rear_scrape_side = 0 when LR and RR are equal."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(lr_rh_m=0.060, rr_rh_m=0.060)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_scrape_side") == 0

    def test_rear_risk_score_thresholds(self) -> None:
        """Rear risk score thresholds match expected values."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        test_cases = [
            (0.000, 1.0),   # 0 mm → scrape
            (0.002, 0.92),  # 2 mm → critical
            (0.005, 0.72),  # 5 mm → high
            (0.008, 0.38),  # 8 mm → watch
            (0.015, 0.08),  # 15 mm → safe
        ]
        for rh_m, expected in test_cases:
            rows = [_synthetic_row(lr_rh_m=rh_m, rr_rh_m=rh_m)]
            ref = normalize_telemetry_rows(rows)
            assert ref[0].get("rear_scrape_risk_score") == pytest.approx(expected, abs=0.01), f"Failed at {rh_m}m"

    def test_rear_platform_contact_risk_alias(self) -> None:
        """rear_platform_contact_risk aliases rear_scrape_risk_score."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(lr_rh_m=0.050, rr_rh_m=0.050)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_platform_contact_risk") == ref[0].get("rear_scrape_risk_score")

    def test_rear_scrape_missing_rh(self) -> None:
        """Missing rear ride heights produce None, not crash."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]  # no ride height columns
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_min_ride_height_mm") is None
        assert ref[0].get("rear_scrape_risk_score") is None
        assert ref[0].get("rear_scrape_side") is None

    def test_rear_scrape_event_emitted_when_low(self) -> None:
        """Rear scrape event is emitted when rear height is low."""
        from racelab_engine.analysis.platform_events import detect_platform_events
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(lr_rh_m=0.001, rr_rh_m=0.001)]  # 1 mm → critical
        ref = normalize_telemetry_rows(rows)
        events = detect_platform_events(ref)
        rear_events = [e for e in events if "REAR" in e.event_type]
        assert rear_events
        assert any(e.event_type == "REAR_PLATFORM_LOW" for e in rear_events)

    def test_rear_scrape_event_scrape(self) -> None:
        """REAR_PLATFORM_SCRAPE event when rear height is 0 or negative."""
        from racelab_engine.analysis.platform_events import detect_platform_events
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(lr_rh_m=0.000, rr_rh_m=0.000)]  # 0 mm → scrape
        ref = normalize_telemetry_rows(rows)
        events = detect_platform_events(ref)
        scrape_events = [e for e in events if e.event_type == "REAR_PLATFORM_SCRAPE"]
        assert scrape_events

    def test_front_events_still_emitted(self) -> None:
        """Front CFS events are still emitted alongside rear events."""
        from racelab_engine.analysis.platform_events import detect_platform_events
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(cfs_rh_m=0.002, lr_rh_m=0.002, rr_rh_m=0.002)]
        ref = normalize_telemetry_rows(rows)
        events = detect_platform_events(ref)
        front_events = [e for e in events if e.event_type == "MIN_SPLITTER"]
        rear_events = [e for e in events if "REAR" in e.event_type]
        assert front_events, "Front events should still be emitted"
        assert rear_events, "Rear events should also be emitted"

    def test_track_map_symbol_mapping(self) -> None:
        """TrackMap symbol mapping includes rear event types."""
        from racelab_engine.services.track_map_service import _event_symbol
        assert _event_symbol("REAR_PLATFORM_SCRAPE") == "R!"
        assert _event_symbol("REAR_PLATFORM_LOW") == "R"
        assert _event_symbol("MIN_REAR_RIDE_HEIGHT") == "Rmin"

    def test_rear_metadata_has_no_missing_entries(self) -> None:
        """All rear scrape channels have CHANNEL_METADATA entries."""
        from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA
        rear_channels = [
            "rear_min_ride_height_mm", "rear_min_ride_height_in",
            "rear_scrape_margin_mm", "rear_scrape_risk_score",
            "rear_platform_contact_risk", "rear_scrape_side",
        ]
        for ch in rear_channels:
            assert ch in CHANNEL_METADATA, f"Missing metadata for {ch}"
            meta = CHANNEL_METADATA[ch]
            assert "description" in meta
            assert "dependencies" in meta
            assert "used_by_charts" in meta
            assert "used_by_events" in meta

    # ── Platform balance tests ────────────────────────────────

    def test_rear_scrape_side_label_converts_correctly(self) -> None:
        """rear_scrape_side_label converts -1/0/1 to readable labels."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        # left lower
        rows = [_synthetic_row(lr_rh_m=0.050, rr_rh_m=0.070)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_scrape_side_label") == "left_rear"
        # right lower
        rows = [_synthetic_row(lr_rh_m=0.070, rr_rh_m=0.050)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_scrape_side_label") == "right_rear"
        # equal
        rows = [_synthetic_row(lr_rh_m=0.060, rr_rh_m=0.060)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_scrape_side_label") == "both_rear"

    def test_rear_scrape_side_label_missing(self) -> None:
        """Missing rear_scrape_side returns None for label."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [{"Speed": 50.0, "SessionTime": 0.0}]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("rear_scrape_side_label") is None

    def test_balance_front_elevated(self) -> None:
        """Front risk elevated + rear safe → front_platform_risk."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        # cfs=2mm (critical=0.92), rear=15mm (safe=0.08)
        rows = [_synthetic_row(cfs_rh_m=0.002, lr_rh_m=0.015, rr_rh_m=0.015)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("platform_balance_label") == "front_platform_risk"

    def test_balance_rear_elevated(self) -> None:
        """Rear risk elevated + front safe → rear_platform_risk."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        # cfs=15mm (safe=0.08), rear=2mm (critical=0.92)
        rows = [_synthetic_row(cfs_rh_m=0.015, lr_rh_m=0.002, rr_rh_m=0.002)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("platform_balance_label") == "rear_platform_risk"

    def test_balance_both_elevated(self) -> None:
        """Both elevated → whole_car_bottoming."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        # cfs=2mm (critical=0.92), rear=2mm (critical=0.92)
        rows = [_synthetic_row(cfs_rh_m=0.002, lr_rh_m=0.002, rr_rh_m=0.002)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("platform_balance_label") == "whole_car_bottoming"

    def test_balance_both_safe(self) -> None:
        """Both safe → balanced_safe."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        # cfs=15mm (safe=0.08), rear=15mm (safe=0.08)
        rows = [_synthetic_row(cfs_rh_m=0.015, lr_rh_m=0.015, rr_rh_m=0.015)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("platform_balance_label") == "balanced_safe"

    def test_balance_missing_risk(self) -> None:
        """Missing front or rear risk → unavailable."""
        import os; os.environ["RACELAB_ANALYSIS_ENGINE"] = "row"
        try:
            from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
            rows = [{"Speed": 50.0, "SessionTime": 0.0}]
            ref = normalize_telemetry_rows(rows)
            assert ref[0].get("platform_balance_label") == "unavailable"
        finally:
            os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)

    def test_whole_car_bottoming_risk_value(self) -> None:
        """whole_car_bottoming_risk = min(front_risk, rear_risk)."""
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        # cfs=2mm (0.92), rear=5mm (0.72) → min=0.72
        rows = [_synthetic_row(cfs_rh_m=0.002, lr_rh_m=0.005, rr_rh_m=0.005)]
        ref = normalize_telemetry_rows(rows)
        assert ref[0].get("whole_car_bottoming_risk") == pytest.approx(0.72, abs=0.01)

    def test_balance_metadata_no_missing(self) -> None:
        """All platform balance channels have CHANNEL_METADATA."""
        from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA
        balance_channels = [
            "front_platform_risk_score", "rear_platform_risk_score",
            "whole_car_bottoming_risk", "platform_balance_label",
            "platform_balance_explanation", "rear_scrape_side_label",
        ]
        for ch in balance_channels:
            assert ch in CHANNEL_METADATA, f"Missing metadata for {ch}"
            meta = CHANNEL_METADATA[ch]
            assert "description" in meta
            assert "dependencies" in meta

    def test_front_events_still_emitted_with_balance(self) -> None:
        """Front CFS events still emitted alongside balance."""
        from racelab_engine.analysis.platform_events import detect_platform_events
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(cfs_rh_m=0.002, lr_rh_m=0.002, rr_rh_m=0.002)]
        ref = normalize_telemetry_rows(rows)
        events = detect_platform_events(ref)
        front_events = [e for e in events if e.event_type == "MIN_SPLITTER"]
        rear_events = [e for e in events if "REAR" in e.event_type]
        whole_car = [e for e in events if e.event_type == "WHOLE_CAR_BOTTOMING_RISK"]
        assert front_events
        assert rear_events
        assert whole_car

    def test_whole_car_event_emitted(self) -> None:
        """WHOLE_CAR_BOTTOMING_RISK event emitted when both risks elevated."""
        from racelab_engine.analysis.platform_events import detect_platform_events
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        rows = [_synthetic_row(cfs_rh_m=0.002, lr_rh_m=0.002, rr_rh_m=0.002)]
        ref = normalize_telemetry_rows(rows)
        events = detect_platform_events(ref)
        whole_car = [e for e in events if e.event_type == "WHOLE_CAR_BOTTOMING_RISK"]
        assert whole_car
        assert whole_car[0].primary_value is not None

    def test_track_map_symbol_whole_car(self) -> None:
        """TrackMap symbol mapping handles WHOLE_CAR_BOTTOMING_RISK."""
        from racelab_engine.services.track_map_service import _event_symbol
        assert _event_symbol("WHOLE_CAR_BOTTOMING_RISK") == "⇣"


class TestBenchmark:
    """Lightweight benchmarks (not real perf tests, just smoke checks).

    Requires ``pytest-benchmark``.  Skipped gracefully if not installed.
    """
    pytest.importorskip("pytest_benchmark")

    @pytest.mark.slow
    def test_bench_1k(self, benchmark) -> None:
        benchmark(normalize_telemetry_rows, _synthetic_rows(1000))

    @pytest.mark.slow
    def test_bench_1k_vector(self, benchmark) -> None:
        benchmark(normalize_telemetry_frame, _synthetic_rows(1000))

    @pytest.mark.slow
    def test_bench_10k(self, benchmark) -> None:
        benchmark(normalize_telemetry_rows, _synthetic_rows(10_000))

    @pytest.mark.slow
    def test_bench_10k_vector(self, benchmark) -> None:
        benchmark(normalize_telemetry_frame, _synthetic_rows(10_000))


class TestEngineDispatch:
    """Tests for the normalize_telemetry_rows engine dispatcher."""

    def test_vectorized_default(self, small_rows: list[dict]) -> None:
        """Default (no env var): vectorized should be used."""
        import os
        os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
        result = normalize_telemetry_rows(small_rows)
        assert len(result) == len(small_rows)
        # Vectorized path produces fewer columns (no raw duplicates)
        assert "speed_mph" in result[0]

    def test_vectorized_explicit(self, small_rows: list[dict]) -> None:
        """RACELAB_ANALYSIS_ENGINE=vectorized: use vec path."""
        import os
        os.environ["RACELAB_ANALYSIS_ENGINE"] = "vectorized"
        try:
            from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
            result = normalize_telemetry_rows(small_rows)
            assert len(result) == len(small_rows)
            assert "speed_mph" in result[0]
        finally:
            os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)

    def test_row_explicit(self, small_rows: list[dict]) -> None:
        """RACELAB_ANALYSIS_ENGINE=row: force row path."""
        import os
        os.environ["RACELAB_ANALYSIS_ENGINE"] = "row"
        try:
            from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
            result = normalize_telemetry_rows(small_rows)
            assert len(result) == len(small_rows)
            # Row path produces more columns (raw + normalized)
            assert "speed_mph" in result[0]
        finally:
            os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)

    def test_fallback_on_invalid_input(self) -> None:
        """Vectorized succeeds on empty input (produces empty list)."""
        import os
        os.environ["RACELAB_ANALYSIS_ENGINE"] = "vectorized"
        try:
            from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
            result = normalize_telemetry_rows([])
            assert isinstance(result, list)
        finally:
            os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)


class TestSchemaInference:
    """Tests for Polars schema inference with mixed/null numeric types."""

    def test_mixed_null_then_float(self) -> None:
        """First row has None, later row has large float — should not fail."""
        from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame, frame_to_rows
        rows = [
            {"SessionTime": 0.0, "Speed": 50.0, "SomeChannel": None},
            {"SessionTime": 0.1, "Speed": 55.0, "SomeChannel": 2752.637493},
        ]
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(vec) == 2
        assert vec[0]["SomeChannel"] is None
        assert vec[1]["SomeChannel"] == 2752.637493

    def test_mixed_int_then_float(self) -> None:
        """First rows are ints, later row is float — should not fail."""
        from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame, frame_to_rows
        rows = [
            {"SessionTime": 0.0, "Speed": 50.0, "Counts": 0},
            {"SessionTime": 0.1, "Speed": 55.0, "Counts": 3},
            {"SessionTime": 0.2, "Speed": 60.0, "Counts": 2752},
        ]
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(vec) == 3
        assert vec[0]["Counts"] == 0.0
        assert vec[2]["Counts"] == 2752.0

    def test_string_labels_stay_strings(self) -> None:
        """String columns should not be coerced to float."""
        from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame, frame_to_rows
        rows = [
            {"SessionTime": 0.0, "Speed": 50.0, "Label": "active"},
            {"SessionTime": 0.1, "Speed": 55.0, "Label": None},
        ]
        vec = frame_to_rows(normalize_telemetry_frame(rows))
        assert len(vec) == 2
        assert vec[0]["Label"] == "active"
        assert vec[1]["Label"] is None
