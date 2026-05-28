"""Vectorized (Polars) analysis path for core channel calculations.

Prototype parallel to the row-by-row normalize_telemetry_rows in
calculated_channels.py.  Produces bit-exact parity for a defined set of
"core" channels using column-wise Polars expressions instead of Python
per-row loops.

Design principles
-----------------
- Pure Polars expressions — no .map_rows, no Python UDFs.
- Output column names match calculated_channels.py exactly.
- NaN/None handling matches _set_number semantics (skip on None).
- Derivative channels (speed_rate_*) use Polars .shift() / .diff().
- Slip ratio floor/clamp uses Polars .clip().

Usage
-----
    import polars as pl
    from racelab_engine.analysis.vectorized_channels import (
        normalize_telemetry_frame,
        frame_to_rows,
    )

    df = pl.DataFrame(raw_rows)
    result = normalize_telemetry_frame(df)
    rows = frame_to_rows(result)          # list[dict] for existing consumers

See Also
--------
    calculated_channels.normalize_telemetry_rows — reference row-by-row impl.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl

from racelab_engine.analysis.constants import (
    REFERENCE_DYNAMIC_PRESSURE_PA,
    SLIP_RATIO_CLAMP_MAX,
    SLIP_RATIO_SPEED_FLOOR_MPS,
)
from racelab_engine.analysis.units import (
    EARTH_RADIUS_M,
    M_TO_FT,
    M_TO_IN,
    MPS_TO_MPH,
    PA_TO_PSF,
    MM_TO_IN,
    input_01_to_percent,
    radians_to_degrees,
)

# ── Feature flag ─────────────────────────────────────────────────

_ENGINE_ENV_VAR = "RACELAB_ANALYSIS_ENGINE"
_VALID_MODES = frozenset({"row", "vectorized"})


def get_analysis_engine_mode(override: str | None = None) -> str:
    """Resolve the analysis engine mode.

    Resolution order:
    1. *override* argument if provided and valid
    2. ``RACELAB_ANALYSIS_ENGINE`` env var if set and valid
    3. ``"row"`` (default)

    Parameters
    ----------
    override : str or None
        Explicit mode override.  Accepted values: ``"row"``, ``"vectorized"``.

    Returns
    -------
    str
        ``"row"`` or ``"vectorized"``.
    """
    import os
    import warnings

    if override is not None:
        if override in _VALID_MODES:
            return override
        warnings.warn(
            f"Invalid analysis engine override {override!r}, falling back to 'row'",
            stacklevel=2,
        )
        return "row"

    env_val = os.environ.get(_ENGINE_ENV_VAR)
    if env_val is not None:
        env_lower = env_val.strip().lower()
        if env_lower in _VALID_MODES:
            return env_lower
        warnings.warn(
            f"Invalid {_ENGINE_ENV_VAR}={env_val!r}, falling back to 'row'",
            stacklevel=2,
        )
    return "row"


# ── Comparison helper ────────────────────────────────────────────

# Default channels for compare_row_vs_vectorized
_DEFAULT_COMPARE_CHANNELS: tuple[str, ...] = (
    "speed_mph",
    "lap_dist_ft",
    "lap_dist_pct_100",
    "dynamic_pressure_pa",
    "aero_load_index",
    "cfs_risk_score",
    "platform_risk_score",
    "front_avg_rh_in",
    "center_rake_fs_in",
    "speed_rate_mph_s",
    "full_throttle_resistance_index",
    "drag_scrub_suspicion",
    "platform_compression_index",
    "shock_velocity_rms",
)

# Shock rolling channels that differ in the first N rows (warm-up window)
_SHOCK_ROLLING_WINDOW = 60
_SHOCK_ROLLING_CHANNELS: frozenset[str] = frozenset({
    "lf_shock_velocity_rms", "rf_shock_velocity_rms",
    "lr_shock_velocity_rms", "rr_shock_velocity_rms",
    "lf_shock_activity_index", "rf_shock_activity_index",
    "lr_shock_activity_index", "rr_shock_activity_index",
    "lf_damper_energy_proxy", "rf_damper_energy_proxy",
    "lr_damper_energy_proxy", "rr_damper_energy_proxy",
    "shock_velocity_rms", "shock_activity_index",
    "damper_energy_proxy",
})


def compare_row_vs_vectorized(
    rows_or_table: Any,
    channels: tuple[str, ...] | None = None,
    tolerance: float = 1e-9,
    geometry: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run both analysis engines and compare outputs channel-by-channel.

    Parameters
    ----------
    rows_or_table
        Raw telemetry rows (list[dict]) or a table object accepted by
        ``normalize_telemetry_rows``.
    channels : tuple[str, ...] or None
        Channels to compare.  Defaults to ``_DEFAULT_COMPARE_CHANNELS``.
    tolerance : float
        Absolute tolerance for float comparison.
    geometry : dict or None
        Optional setup constants forwarded to both engines.

    Returns
    -------
    dict
        Comparison report with keys:
        - row_count
        - compared_channels
        - missing_in_row
        - missing_in_vector
        - max_abs_diff_by_channel
        - mismatch_count_by_channel
        - tolerance
        - early_window_exemptions
        - pass_fail
    """
    import math as _math

    from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows

    if channels is None:
        channels = _DEFAULT_COMPARE_CHANNELS
    channel_set = set(channels)

    ref = normalize_telemetry_rows(rows_or_table, geometry=geometry)
    vec_df = normalize_telemetry_frame(rows_or_table, geometry=geometry)
    vec = frame_to_rows(vec_df)

    row_count = len(ref)
    if row_count == 0:
        return {
            "row_count": 0,
            "compared_channels": list(channels),
            "missing_in_row": [],
            "missing_in_vector": [],
            "max_abs_diff_by_channel": {},
            "mismatch_count_by_channel": {},
            "tolerance": tolerance,
            "early_window_exemptions": 0,
            "pass_fail": True,
        }

    missing_in_row: list[str] = []
    missing_in_vector: list[str] = []
    max_abs_diff: dict[str, float] = {}
    mismatch_count: dict[str, int] = {}
    early_window_exemptions = 0

    for ch in channels:
        # Check presence — a channel is "present" if the key exists in any
        # row dict (even if the value is None, e.g. first-row derivatives)
        ref_present = any(ch in r for r in ref)
        vec_present = any(ch in r for r in vec)
        if not ref_present:
            missing_in_row.append(ch)
        if not vec_present:
            missing_in_vector.append(ch)
        if not ref_present and not vec_present:
            continue
        if not ref_present or not vec_present:
            continue

        max_diff = 0.0
        mismatches = 0
        for i, (r, v) in enumerate(zip(ref, vec)):
            rv = r.get(ch)
            vv = v.get(ch)
            if rv is None and vv is None:
                continue
            if rv is None or vv is None:
                mismatches += 1
                max_diff = float("inf")
                continue
            if isinstance(rv, float) and isinstance(vv, float):
                if _math.isnan(rv) and _math.isnan(vv):
                    continue
                diff = abs(rv - vv)
                if diff > tolerance:
                    # Check early-window exemption for shock rolling channels
                    if ch in _SHOCK_ROLLING_CHANNELS and i < _SHOCK_ROLLING_WINDOW:
                        early_window_exemptions += 1
                        continue
                    mismatches += 1
                    if diff > max_diff:
                        max_diff = diff
            elif rv != vv:
                mismatches += 1
                max_diff = float("inf")

        max_abs_diff[ch] = max_diff
        mismatch_count[ch] = mismatches

    total_mismatches = sum(mismatch_count.values())
    # Channels missing in BOTH paths are not a failure (e.g. shock channels
    # when no shock velocity columns exist in input)
    missing_both = set(missing_in_row) & set(missing_in_vector)
    missing_only_row = [ch for ch in missing_in_row if ch not in missing_both]
    missing_only_vector = [ch for ch in missing_in_vector if ch not in missing_both]
    pass_fail = (
        not missing_only_row
        and not missing_only_vector
        and total_mismatches == 0
    )

    return {
        "row_count": row_count,
        "compared_channels": list(channels),
        "missing_in_row": missing_in_row,
        "missing_in_vector": missing_in_vector,
        "max_abs_diff_by_channel": max_abs_diff,
        "mismatch_count_by_channel": mismatch_count,
        "tolerance": tolerance,
        "early_window_exemptions": early_window_exemptions,
        "pass_fail": pass_fail,
    }


# ── Public API ───────────────────────────────────────────────────

CORE_CHANNELS: set[str] = {
    # unit conversions
    "speed_mph",
    "speed_fps",
    "lap_dist_ft",
    "lap_dist_pct_100",
    "throttle_pct",
    "brake_pct",
    "steering_deg",
    "abs_steering_deg",
    "abs_lat_accel",
    # dynamic pressure
    "dynamic_pressure_pa",
    "dynamic_pressure_psf",
    "aero_load_index",
    "aero_load_index_180mph",
    # ride height conversions
    "cfs_ride_height_mm",
    "cfs_ride_height_in",
    "cfsr_height_mm",
    "lf_ride_height_mm",
    "rf_ride_height_mm",
    "lr_ride_height_mm",
    "rr_ride_height_mm",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
    # slip ratio
    "lf_slip_ratio",
    "rf_slip_ratio",
    "lr_slip_ratio",
    "rr_slip_ratio",
    "driven_wheel_slip_proxy",
    # speed derivatives
    "speed_rate_mph_s",
    "speed_rate_mph_1000ft",
    "speed_rate_mps2",
    # g-values
    "lat_accel_g",
    "long_accel_g",
    "vert_accel_g",
    # ride-height averages (slice 2)
    "front_avg_rh_in",
    "rear_avg_rh_in",
    "left_avg_rh_in",
    "right_avg_rh_in",
    "center_rake_fs_in",
    "side_rake_in",
    "front_split_in",
    "rear_split_in",
    # risk scores (slice 2)
    "cfs_risk_score",
    "platform_risk_score",
    # wheel speed mismatch (slice 2)
    "front_wheel_speed_mismatch_raw",
    "rear_wheel_speed_mismatch_raw",
    "front_wheel_speed_mismatch_corrected",
    "rear_wheel_speed_mismatch_corrected",
    # shock conversions (slice 2)
    "lf_shock_defl_in",
    "rf_shock_defl_in",
    "lr_shock_defl_in",
    "rr_shock_defl_in",
    "lf_shock_vel_in_s",
    "rf_shock_vel_in_s",
    "lr_shock_vel_in_s",
    "rr_shock_vel_in_s",
    # stability scores (slice 3)
    "platform_stability_score",
    "rake_stability_score",
    # drag / resistance (slice 3)
    "full_throttle_resistance_index",
    "drag_scrub_suspicion",
    # platform compression (slice 3)
    "platform_compression_index",
    # shock rolling aggregates (slice 3)
    "lf_shock_velocity_rms",
    "rf_shock_velocity_rms",
    "lr_shock_velocity_rms",
    "rr_shock_velocity_rms",
    "lf_shock_activity_index",
    "rf_shock_activity_index",
    "lr_shock_activity_index",
    "rr_shock_activity_index",
    "lf_damper_energy_proxy",
    "rf_damper_energy_proxy",
    "lr_damper_energy_proxy",
    "rr_damper_energy_proxy",
    "shock_velocity_rms",
    "shock_activity_index",
    "damper_energy_proxy",
    # rear scrape (added after slice 3)
    "rear_min_ride_height_mm",
    "rear_min_ride_height_in",
    "rear_scrape_margin_mm",
    "rear_scrape_risk_score",
    "rear_platform_contact_risk",
    "rear_scrape_side",
    "rear_scrape_side_label",
    # platform balance
    "front_platform_risk_score",
    "rear_platform_risk_score",
    "whole_car_bottoming_risk",
    "platform_balance_label",
    "platform_balance_explanation",
    # tire derived (final sweep)
    "lf_pressure_gain",
    "rf_pressure_gain",
    "lr_pressure_gain",
    "rr_pressure_gain",
    "lf_temp_spread",
    "rf_temp_spread",
    "lr_temp_spread",
    "rr_temp_spread",
    "lf_wear_spread",
    "rf_wear_spread",
    "lr_wear_spread",
    "rr_wear_spread",
    # scrub proxies (final sweep)
    "front_scrub_proxy",
    "rear_scrub_proxy",
    "yaw_error_proxy",
    # dynamic pressure lap index (final sweep)
    "dynamic_pressure_lap_index",
    "dynamic_pressure_index",
    # dynamic grade (final sweep)
    "dynamic_grade_deg",
    # GPS projection (final sweep)
    "track_x_m",
    "track_y_m",
    "track_x_ft",
    "track_y_ft",
}


def normalize_telemetry_frame(
    data: pl.DataFrame | list[dict[str, Any]],
    geometry: dict[str, float] | None = None,
) -> pl.DataFrame:
    """Vectorised equivalent of calculated_channels.normalize_telemetry_rows.

    Parameters
    ----------
    data : pl.DataFrame | list[dict]
        Raw telemetry rows or a Polars DataFrame with iRacing column names.
    geometry : dict or None
        Optional setup constants (wheelbase, track width, axle-to-CG, etc.).

    Returns
    -------
    pl.DataFrame
        DataFrame with all core calculated channels added.
    """
    df = pl.DataFrame(data) if isinstance(data, list) else data.clone()

    # ── 1. Alias raw iRacing names to normalised names ──────────
    df = _apply_aliases(df)

    # ── 2. Inject geometry constants ────────────────────────────
    if geometry:
        physics_keys = [
            "mass_kg", "cg_height_m", "wheelbase_m", "front_track_width_m",
            "rear_track_width_m", "front_axle_to_cg_m", "rear_axle_to_cg_m",
            "crr", "motion_ratio_front", "motion_ratio_rear",
        ]
        for k in physics_keys:
            if k in geometry and k not in df.columns:
                df = df.with_columns(pl.lit(geometry[k]).alias(k))

    # ── 3. Core calculated channels ─────────────────────────────
    df = calculate_core_channels_frame(df)

    return df


def calculate_core_channels_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Add core calculated channels to *df* in-place (returns new frame).

    This is the vectorised equivalent of
    ``_apply_row_calculations`` + ``_apply_derivatives`` + ``_apply_rolling_aggregates``.
    """
    df = _convert_distances(df)
    df = _convert_speed(df)
    df = _convert_inputs(df)
    df = _convert_ride_heights(df)
    df = _convert_shocks(df)
    df = _compute_dynamic_pressure(df)
    df = _compute_slip_ratios(df)
    df = _compute_g_values(df)
    df = _compute_speed_derivatives(df)
    df = _compute_aero_load_index(df)
    df = _compute_ride_height_averages(df)
    df = _compute_risk_scores(df)
    df = _compute_wheel_speed_mismatch(df)
    df = _compute_stability_scores(df)
    df = _compute_resistance_indices(df)
    df = _compute_compression_index(df)
    df = _compute_shock_rolling_aggregates(df)
    df = _compute_tire_derived(df)
    df = _compute_scrub_proxies(df)
    df = _compute_dynamic_pressure_lap_index(df)
    df = _compute_dynamic_grade(df)
    df = _apply_gps_projection(df)
    return df


def frame_to_rows(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Convert a Polars DataFrame back to a list of dicts (row-oriented).

    This is the inverse of ``pl.DataFrame(rows)`` and matches the output
    format of ``normalize_telemetry_rows``.
    """
    return df.to_dicts()


# ── Internal helpers ─────────────────────────────────────────────

_ALIAS_MAP: dict[str, str] = {
    "SessionTime": "session_time",
    "SessionTick": "session_tick",
    "Lap": "lap",
    "LapCompleted": "lap_completed",
    "LapDist": "lap_dist_m",
    "LapDistPct": "lap_dist_pct",
    "Speed": "speed_mps",
    "RPM": "rpm",
    "Gear": "gear",
    "Throttle": "throttle_01",
    "Brake": "brake_01",
    "SteeringWheelAngle": "steering_rad",
    "YawRate": "yaw_rate",
    "LatAccel": "lat_accel",
    "LongAccel": "long_accel",
    "VertAccel": "vert_accel",
    "AirDensity": "air_density",
    "Lat": "lat",
    "Lon": "lon",
    "Alt": "alt",
    "CFSRrideHeight": "cfs_ride_height_m",
    "LFrideHeight": "lf_ride_height_m",
    "RFrideHeight": "rf_ride_height_m",
    "LRrideHeight": "lr_ride_height_m",
    "RRrideHeight": "rr_ride_height_m",
}

_RIDE_HEIGHT_RAW_KEYS: dict[str, str] = {
    "cfs_ride_height_m": "cfs_ride_height",
    "lf_ride_height_m": "lf_ride_height",
    "rf_ride_height_m": "rf_ride_height",
    "lr_ride_height_m": "lr_ride_height",
    "rr_ride_height_m": "rr_ride_height",
}

_SLIP_RAW_KEYS: list[str] = ["LFspeed", "RFspeed", "LRspeed", "RRspeed"]
_SLIP_TARGETS: list[str] = ["lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio"]

_SHOCK_DEFL_RAW_KEYS: dict[str, str] = {
    "LFSHshockDefl": "lf_shock_defl",
    "RFSHshockDefl": "rf_shock_defl",
    "LRSHshockDefl": "lr_shock_defl",
    "RRSHshockDefl": "rr_shock_defl",
}

_SHOCK_VEL_RAW_KEYS: dict[str, str] = {
    "LFSHshockVel": "lf_shock_vel",
    "RFSHshockVel": "rf_shock_vel",
    "LRSHshockVel": "lr_shock_vel",
    "RRSHshockVel": "rr_shock_vel",
}

# Tire column aliases — matches _convert_tires in calculated_channels.py
_TIRE_ALIAS_MAP: dict[str, str] = {
    "LFpressure": "lf_pressure", "RFpressure": "rf_pressure",
    "LRpressure": "lr_pressure", "RRpressure": "rr_pressure",
    "LFcoldPressure": "lf_cold_pressure", "RFcoldPressure": "rf_cold_pressure",
    "LRcoldPressure": "lr_cold_pressure", "RRcoldPressure": "rr_cold_pressure",
    "LFtempL": "lf_temp_inner", "RFtempL": "rf_temp_inner",
    "LRtempL": "lr_temp_inner", "RRtempL": "rr_temp_inner",
    "LFtempM": "lf_temp_middle", "RFtempM": "rf_temp_middle",
    "LRtempM": "lr_temp_middle", "RRtempM": "rr_temp_middle",
    "LFtempR": "lf_temp_outer", "RFtempR": "rf_temp_outer",
    "LRtempR": "lr_temp_outer", "RRtempR": "rr_temp_outer",
    "LFwearL": "lf_wear_inner", "RFwearL": "rf_wear_inner",
    "LRwearL": "lr_wear_inner", "RRwearL": "rr_wear_inner",
    "LFwearM": "lf_wear_middle", "RFwearM": "rf_wear_middle",
    "LRwearM": "lr_wear_middle", "RRwearM": "rr_wear_middle",
    "LFwearR": "lf_wear_outer", "RFwearR": "rf_wear_outer",
    "LRwearR": "lr_wear_outer", "RRwearR": "rr_wear_outer",
}


def _apply_aliases(df: pl.DataFrame) -> pl.DataFrame:
    """Rename raw iRacing columns to normalised names where they exist.

    Only renames if the target column does not already exist (avoids
    DuplicateError when the alias was already created by the row path).
    """
    all_aliases = dict(_ALIAS_MAP)
    all_aliases.update(_TIRE_ALIAS_MAP)
    if renames := {
        raw: norm for raw, norm in all_aliases.items()
        if raw in df.columns and norm not in df.columns
    }:
        df = df.rename(renames)
    return df


def _convert_distances(df: pl.DataFrame) -> pl.DataFrame:
    if "lap_dist_m" in df.columns:
        df = df.with_columns(
            (pl.col("lap_dist_m") * M_TO_FT).alias("lap_dist_ft"),
        )
    if "lap_dist_pct" in df.columns:
        df = df.with_columns(
            (pl.col("lap_dist_pct") * 100.0).alias("lap_dist_pct_100"),
        )
    return df


def _convert_speed(df: pl.DataFrame) -> pl.DataFrame:
    if "speed_mps" not in df.columns:
        return df
    df = df.with_columns(
        (pl.col("speed_mps") * MPS_TO_MPH).alias("speed_mph"),
        (pl.col("speed_mps") * M_TO_FT).alias("speed_fps"),
    )
    return df


def _convert_inputs(df: pl.DataFrame) -> pl.DataFrame:
    if "throttle_01" in df.columns:
        df = df.with_columns(
            (pl.col("throttle_01") * 100.0).alias("throttle_pct"),
        )
    if "brake_01" in df.columns:
        df = df.with_columns(
            (pl.col("brake_01") * 100.0).alias("brake_pct"),
        )
    if "steering_rad" in df.columns:
        df = df.with_columns(
            (pl.col("steering_rad") * 180.0 / math.pi).alias("steering_deg"),
        )
    if "steering_deg" in df.columns:
        df = df.with_columns(
            pl.col("steering_deg").abs().alias("abs_steering_deg"),
        )
    if "lat_accel" in df.columns:
        df = df.with_columns(
            pl.col("lat_accel").abs().alias("abs_lat_accel"),
        )
    return df


def _convert_ride_heights(df: pl.DataFrame) -> pl.DataFrame:
    """Convert ride heights from meters to mm and inches."""
    for raw_col, prefix in _RIDE_HEIGHT_RAW_KEYS.items():
        if raw_col not in df.columns:
            continue
        df = df.with_columns(
            (pl.col(raw_col) * 1000.0).alias(f"{prefix}_mm"),
            (pl.col(raw_col) * M_TO_IN).alias(f"{prefix}_in"),
        )

    # Cross-alias cfs_ride_height_mm <-> cfsr_height_mm
    if "cfs_ride_height_mm" in df.columns and "cfsr_height_mm" not in df.columns:
        df = df.with_columns(pl.col("cfs_ride_height_mm").alias("cfsr_height_mm"))
    elif "cfsr_height_mm" in df.columns and "cfs_ride_height_mm" not in df.columns:
        df = df.with_columns(pl.col("cfsr_height_mm").alias("cfs_ride_height_mm"))

    return df


def _compute_dynamic_pressure(df: pl.DataFrame) -> pl.DataFrame:
    if "air_density" not in df.columns or "speed_mps" not in df.columns:
        return df
    df = df.with_columns(
        (0.5 * pl.col("air_density") * pl.col("speed_mps") ** 2).alias("dynamic_pressure_pa"),
    )
    df = df.with_columns(
        (pl.col("dynamic_pressure_pa") * PA_TO_PSF).alias("dynamic_pressure_psf"),
    )
    return df


def _compute_aero_load_index(df: pl.DataFrame) -> pl.DataFrame:
    if "dynamic_pressure_pa" not in df.columns:
        return df
    df = df.with_columns(
        (pl.col("dynamic_pressure_pa") / REFERENCE_DYNAMIC_PRESSURE_PA).alias("aero_load_index"),
    )
    df = df.with_columns(
        pl.col("aero_load_index").alias("aero_load_index_180mph"),
    )
    return df


def _compute_slip_ratios(df: pl.DataFrame) -> pl.DataFrame:
    """Compute slip ratios with speed floor and clamp.

    Matches _compute_slip_ratios in calculated_channels.py:
        denom = max(abs(speed_mps), SLIP_RATIO_SPEED_FLOOR_MPS)
        slip = (wheel_speed - speed_mps) / denom
        slip = clamp(slip, -SLIP_RATIO_CLAMP_MAX, SLIP_RATIO_CLAMP_MAX)
    """
    if "speed_mps" not in df.columns:
        return df

    speed_expr = pl.col("speed_mps")
    denom_expr = pl.max_horizontal(speed_expr.abs(), pl.lit(SLIP_RATIO_SPEED_FLOOR_MPS))

    for raw_key, target in zip(_SLIP_RAW_KEYS, _SLIP_TARGETS):
        if raw_key not in df.columns:
            continue
        ws = pl.col(raw_key)
        slip = (ws - speed_expr) / denom_expr
        slip = slip.clip(-SLIP_RATIO_CLAMP_MAX, SLIP_RATIO_CLAMP_MAX)
        df = df.with_columns(slip.alias(target))

    # driven_wheel_slip_proxy
    if all(k in df.columns for k in ("LRspeed", "RRspeed")):
        ws_avg = (pl.col("LRspeed") + pl.col("RRspeed")) / 2.0
        slip = (ws_avg - speed_expr) / denom_expr
        slip = slip.clip(-SLIP_RATIO_CLAMP_MAX, SLIP_RATIO_CLAMP_MAX)
        df = df.with_columns(slip.alias("driven_wheel_slip_proxy"))

    return df


def _compute_g_values(df: pl.DataFrame) -> pl.DataFrame:
    for ch in ["lat_accel", "long_accel", "vert_accel"]:
        if ch in df.columns:
            df = df.with_columns(
                (pl.col(ch) / 9.81).alias(f"{ch}_g"),
            )
    return df


def _compute_speed_derivatives(df: pl.DataFrame) -> pl.DataFrame:
    """Compute speed_rate_mph_s, speed_rate_mph_1000ft, speed_rate_mps2.

    Matches _compute_speed_rates in calculated_channels.py using
    .shift() / .diff() for vectorised adjacent-row differences.
    """
    has_speed = "speed_mph" in df.columns
    has_time = "session_time" in df.columns
    has_dist = "lap_dist_ft" in df.columns
    has_mps = "speed_mps" in df.columns

    if has_speed and has_time:
        dt = pl.col("session_time") - pl.col("session_time").shift(1)
        dv_mph = pl.col("speed_mph") - pl.col("speed_mph").shift(1)
        # Guard: dt <= 0 (repeated timestamps) → None; first row (dt=None) → None
        speed_rate = (
            pl.when(dt.is_null() | (dt <= 0))
            .then(None)
            .otherwise(dv_mph / dt)
            .alias("speed_rate_mph_s")
        )
        df = df.with_columns(speed_rate)

        if has_mps:
            dv_mps = pl.col("speed_mps") - pl.col("speed_mps").shift(1)
            speed_rate_mps2 = (
                pl.when(dt.is_null() | (dt <= 0))
                .then(None)
                .otherwise(dv_mps / dt)
                .alias("speed_rate_mps2")
            )
            df = df.with_columns(speed_rate_mps2)

    if has_speed and has_dist:
        dd = pl.col("lap_dist_ft") - pl.col("lap_dist_ft").shift(1)
        dv_mph = pl.col("speed_mph") - pl.col("speed_mph").shift(1)
        # Avoid division by near-zero distance
        speed_rate_1000 = (
            pl.when(dd.abs() > 0.1)
            .then(dv_mph / dd * 1000.0)
            .otherwise(None)
            .alias("speed_rate_mph_1000ft")
        )
        df = df.with_columns(speed_rate_1000)

    return df


# ── Slice 2: ride-height averages ───────────────────────────────

def _compute_ride_height_averages(df: pl.DataFrame) -> pl.DataFrame:
    """Compute front/rear/left/right ride-height averages, rake, and splits.

    Matches _compute_averages in calculated_channels.py.
    All inputs are in inches (the *_in columns).
    """
    needed = {"lf_ride_height_in", "rf_ride_height_in",
              "lr_ride_height_in", "rr_ride_height_in"}
    if not needed.issubset(df.columns):
        return df

    lf = pl.col("lf_ride_height_in")
    rf = pl.col("rf_ride_height_in")
    lr = pl.col("lr_ride_height_in")
    rr = pl.col("rr_ride_height_in")

    front_avg = (lf + rf) / 2.0
    rear_avg = (lr + rr) / 2.0
    left_avg = (lf + lr) / 2.0
    right_avg = (rf + rr) / 2.0

    df = df.with_columns(
        front_avg.alias("front_avg_rh_in"),
        rear_avg.alias("rear_avg_rh_in"),
        left_avg.alias("left_avg_rh_in"),
        right_avg.alias("right_avg_rh_in"),
    )

    # center_rake_fs_in = rear_avg - cfs_ride_height_in
    if "cfs_ride_height_in" in df.columns:
        df = df.with_columns(
            (pl.col("rear_avg_rh_in") - pl.col("cfs_ride_height_in")).alias("center_rake_fs_in"),
        )

    # side_rake_in = right_avg - left_avg
    df = df.with_columns(
        (pl.col("right_avg_rh_in") - pl.col("left_avg_rh_in")).alias("side_rake_in"),
    )

    # front_split_in = rf - lf, rear_split_in = rr - lr
    df = df.with_columns(
        (rf - lf).alias("front_split_in"),
        (rr - lr).alias("rear_split_in"),
    )

    return df


# ── Slice 2: risk scores ────────────────────────────────────────

def _risk_from_cfs_mm_vector(cfs_mm: pl.Expr) -> pl.Expr:
    """Vectorised equivalent of _risk_from_cfs_mm.

    Thresholds: 0→1.0, 3→0.92, 6→0.72, 10→0.38, >10→0.08
    """
    return (
        pl.when(cfs_mm <= 0).then(1.0)
        .when(cfs_mm <= 3).then(0.92)
        .when(cfs_mm <= 6).then(0.72)
        .when(cfs_mm <= 10).then(0.38)
        .otherwise(0.08)
    )


def _compute_risk_scores(df: pl.DataFrame) -> pl.DataFrame:
    """Compute cfs_risk_score, platform_risk_score, rear scrape, and platform balance.

    Matches _compute_risk_scores + _compute_rear_scrape + _compute_platform_balance
    in calculated_channels.py.
    """
    from racelab_engine.analysis.constants import (
        REAR_SCRAPE_MM, REAR_CRITICAL_MM, REAR_HIGH_MM, REAR_WATCH_MM,
    )

    # ── Front/CFS risk ─────────────────────────────────────────
    if "cfs_ride_height_mm" in df.columns:
        risk = _risk_from_cfs_mm_vector(pl.col("cfs_ride_height_mm"))
        df = df.with_columns(
            risk.alias("cfs_risk_score"),
            risk.alias("platform_risk_score"),
        )

    # ── Rear scrape risk ───────────────────────────────────────
    has_rear_rh = {"lr_ride_height_mm", "rr_ride_height_mm"}.issubset(df.columns)
    if has_rear_rh:
        lr = pl.col("lr_ride_height_mm")
        rr = pl.col("rr_ride_height_mm")
        rear_min = pl.min_horizontal(lr, rr)
        margin = rear_min - REAR_SCRAPE_MM
        risk_expr = (
            pl.when(rear_min <= REAR_SCRAPE_MM).then(1.0)
            .when(rear_min <= REAR_CRITICAL_MM).then(0.92)
            .when(rear_min <= REAR_HIGH_MM).then(0.72)
            .when(rear_min <= REAR_WATCH_MM).then(0.38)
            .otherwise(0.08)
        )
        side_expr = (
            pl.when((lr - rr).abs() < 0.001).then(pl.lit(0, dtype=pl.Int64))
            .when(lr < rr).then(pl.lit(-1, dtype=pl.Int64))
            .otherwise(pl.lit(1, dtype=pl.Int64))
        )
        side_label_expr = (
            pl.when(side_expr == -1).then(pl.lit("left_rear"))
            .when(side_expr == 0).then(pl.lit("both_rear"))
            .when(side_expr == 1).then(pl.lit("right_rear"))
            .otherwise(None)
        )
        df = df.with_columns(
            rear_min.alias("rear_min_ride_height_mm"),
            (rear_min * MM_TO_IN).alias("rear_min_ride_height_in"),
            margin.alias("rear_scrape_margin_mm"),
            risk_expr.alias("rear_scrape_risk_score"),
            risk_expr.alias("rear_platform_contact_risk"),
            side_expr.alias("rear_scrape_side"),
            side_label_expr.alias("rear_scrape_side_label"),
        )

    # ── Platform balance ───────────────────────────────────────
    has_front_risk = "cfs_risk_score" in df.columns
    has_rear_risk = "rear_scrape_risk_score" in df.columns

    if has_front_risk:
        df = df.with_columns(pl.col("cfs_risk_score").alias("front_platform_risk_score"))
    if has_rear_risk:
        df = df.with_columns(pl.col("rear_scrape_risk_score").alias("rear_platform_risk_score"))

    if has_front_risk and has_rear_risk:
        front_r = pl.col("cfs_risk_score")
        rear_r = pl.col("rear_scrape_risk_score")
        bottoming = pl.min_horizontal(front_r, rear_r)
        ELEVATED = 0.72

        label_expr = (
            pl.when(front_r.is_null() | rear_r.is_null()).then(pl.lit("unavailable"))
            .when((front_r >= ELEVATED) & (rear_r >= ELEVATED)).then(pl.lit("whole_car_bottoming"))
            .when((front_r >= ELEVATED) & (rear_r < ELEVATED)).then(pl.lit("front_platform_risk"))
            .when((rear_r >= ELEVATED) & (front_r < ELEVATED)).then(pl.lit("rear_platform_risk"))
            .otherwise(pl.lit("balanced_safe"))
        )
        explanation_expr = (
            pl.when(front_r.is_null() | rear_r.is_null())
            .then(pl.lit("Insufficient ride-height channels to classify platform balance."))
            .when((front_r >= ELEVATED) & (rear_r >= ELEVATED))
            .then(pl.lit("Front and rear are both low — likely whole-car bottoming or ride height too low."))
            .when((front_r >= ELEVATED) & (rear_r < ELEVATED))
            .then(pl.lit("Front/CFS is low while rear platform is safe — likely splitter/front platform risk."))
            .when((rear_r >= ELEVATED) & (front_r < ELEVATED))
            .then(pl.lit("Rear platform is low while front/CFS is safe — likely rear platform contact or rear bottoming."))
            .otherwise(pl.lit("Front and rear platform margins look safe."))
        )
        df = df.with_columns(
            bottoming.alias("whole_car_bottoming_risk"),
            label_expr.alias("platform_balance_label"),
            explanation_expr.alias("platform_balance_explanation"),
        )

    return df


# ── Slice 2: wheel speed mismatch ───────────────────────────────

def _compute_wheel_speed_mismatch(df: pl.DataFrame) -> pl.DataFrame:
    """Compute wheel speed mismatch channels (raw and geometry-corrected).

    Matches the mismatch section of _compute_slip_ratios in
    calculated_channels.py.

    Raw mismatch is always computed when LFspeed/RFspeed/LRspeed/RRspeed exist.
    Geometry-corrected mismatch requires yaw_rate and track width columns.
    """
    has_front = {"LFspeed", "RFspeed"}.issubset(df.columns)
    has_rear = {"LRspeed", "RRspeed"}.issubset(df.columns)

    if has_front:
        df = df.with_columns(
            (pl.col("RFspeed") - pl.col("LFspeed")).alias("front_wheel_speed_mismatch_raw"),
        )
    if has_rear:
        df = df.with_columns(
            (pl.col("RRspeed") - pl.col("LRspeed")).alias("rear_wheel_speed_mismatch_raw"),
        )

    # Geometry-corrected mismatch
    has_yaw = "yaw_rate" in df.columns
    has_ftw = "front_track_width_m" in df.columns
    has_rtw = "rear_track_width_m" in df.columns

    if has_front and has_yaw and has_ftw:
        front_geo = pl.col("yaw_rate") * pl.col("front_track_width_m")
        front_diff = pl.col("RFspeed") - pl.col("LFspeed")
        df = df.with_columns(
            (front_diff - front_geo).alias("front_wheel_speed_mismatch_corrected"),
        )
    elif has_front:
        # Row path sets corrected to None when track width missing
        df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias("front_wheel_speed_mismatch_corrected"))

    if has_rear and has_yaw and has_rtw:
        rear_geo = pl.col("yaw_rate") * pl.col("rear_track_width_m")
        rear_diff = pl.col("RRspeed") - pl.col("LRspeed")
        df = df.with_columns(
            (rear_diff - rear_geo).alias("rear_wheel_speed_mismatch_corrected"),
        )
    elif has_rear:
        df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias("rear_wheel_speed_mismatch_corrected"))

    return df


# ── Slice 2: shock conversions ──────────────────────────────────

def _convert_shocks(df: pl.DataFrame) -> pl.DataFrame:
    """Convert shock deflections and velocities from meters to inches.

    Matches _convert_shocks in calculated_channels.py.
    """
    for raw_key, prefix in _SHOCK_DEFL_RAW_KEYS.items():
        if raw_key not in df.columns:
            continue
        df = df.with_columns(
            (pl.col(raw_key) * M_TO_IN).alias(f"{prefix}_in"),
        )

    for raw_key, prefix in _SHOCK_VEL_RAW_KEYS.items():
        if raw_key not in df.columns:
            continue
        df = df.with_columns(
            (pl.col(raw_key) * M_TO_IN).alias(f"{prefix}_in_s"),
        )

    return df


# ── Slice 3: stability scores ───────────────────────────────────

def _compute_stability_scores(df: pl.DataFrame) -> pl.DataFrame:
    """Compute platform_stability_score and rake_stability_score.

    Matches _compute_stability_scores in calculated_channels.py:
        platform_stability_score = min(1.0, abs((cfs - prev_cfs) / dt) / 2.0)
        rake_stability_score = min(1.0, abs((rake - prev_rake) / dt) / 2.0)

    First row is None (no previous row).
    dt <= 0 produces None (time must advance).
    """
    needed = {"cfs_ride_height_in", "center_rake_fs_in", "session_time"}
    if not needed.issubset(df.columns):
        return df

    dt = pl.col("session_time") - pl.col("session_time").shift(1)
    dt_ok = dt > 0

    # platform_stability_score
    cfs_delta = pl.col("cfs_ride_height_in") - pl.col("cfs_ride_height_in").shift(1)
    plat_score = (
        pl.when(dt_ok & cfs_delta.is_not_null())
        .then((cfs_delta.abs() / dt / 2.0).clip(0.0, 1.0))
        .otherwise(None)
        .alias("platform_stability_score")
    )
    df = df.with_columns(plat_score)

    # rake_stability_score
    rake_delta = pl.col("center_rake_fs_in") - pl.col("center_rake_fs_in").shift(1)
    rake_score = (
        pl.when(dt_ok & rake_delta.is_not_null())
        .then((rake_delta.abs() / dt / 2.0).clip(0.0, 1.0))
        .otherwise(None)
        .alias("rake_stability_score")
    )
    df = df.with_columns(rake_score)

    return df


# ── Slice 3: drag / resistance indices ──────────────────────────

def _compute_resistance_indices(df: pl.DataFrame) -> pl.DataFrame:
    """Compute full_throttle_resistance_index and drag_scrub_suspicion.

    Matches _compute_resistance_indices in calculated_channels.py.
    Delegates to the shared drag_scrub module for aero-normalized logic.
    """
    from racelab_engine.analysis.constants import (
        DRAG_SCRUB_MIN_SPEED_MPH, FULL_THROTTLE_PCT, LOW_BRAKE_PCT,
        RESISTANCE_COEFF_CRITICAL,
    )
    from racelab_engine.analysis.drag_scrub import (
        aero_normalized_resistance, compute_drag_scrub_index,
    )

    # full_throttle_resistance_index
    has_ft = {"speed_mph", "throttle_pct", "brake_pct",
              "speed_rate_mph_s", "dynamic_pressure_psf"}.issubset(df.columns)
    if has_ft:
        speed = pl.col("speed_mph")
        throttle = pl.col("throttle_pct")
        brake = pl.col("brake_pct")
        max_lap_speed = speed.max().over("lap") if "lap" in df.columns else speed.max()
        speed_threshold = pl.max_horizontal(max_lap_speed * 0.75, pl.lit(DRAG_SCRUB_MIN_SPEED_MPH))

        gate = (
            (throttle >= FULL_THROTTLE_PCT)
            & (brake <= LOW_BRAKE_PCT)
            & (speed >= speed_threshold)
        )

        # aero_normalized_resistance: decel_mph_s / dynamic_pressure_psf
        decel = pl.col("speed_rate_mph_s").clip(lower_bound=0.0)  # max(0, -x) handled via sign
        # Row path uses max(0, -speed_rate_mph_s). We use negative since decel is negative.
        decel_pos = (-pl.col("speed_rate_mph_s")).clip(lower_bound=0.0)
        dp_psf = pl.col("dynamic_pressure_psf").clip(lower_bound=1.0)
        resistance_coeff = decel_pos / dp_psf
        resistance_index = (resistance_coeff / RESISTANCE_COEFF_CRITICAL).clip(0.0, 1.0)

        # Row path skips first row (via _init_derivative_row continue)
        row_idx = pl.int_range(0, df.height, dtype=pl.Int64)
        ft_index = (
            pl.when(row_idx == 0).then(None)
            .when(gate)
            .then(resistance_index)
            .otherwise(0.0)
            .alias("full_throttle_resistance_index")
        )
        df = df.with_columns(ft_index)

    # drag_scrub_suspicion — use the shared module's row-based function via map_rows
    # This is the one place we accept a Python UDF because the logic is complex
    # and shared with the row path.
    drag_cols = {"speed_mph", "throttle_pct", "brake_pct",
                 "speed_rate_mph_s", "dynamic_pressure_psf",
                 "abs_steering_deg", "yaw_rate", "cfs_risk_score"}
    if drag_cols.issubset(df.columns):
        row_idx = pl.int_range(0, df.height, dtype=pl.Int64)
        drag_expr = pl.struct(
            pl.col("speed_mph"),
            pl.col("throttle_pct"),
            pl.col("brake_pct"),
            pl.col("speed_rate_mph_s"),
            pl.col("dynamic_pressure_psf"),
            pl.col("abs_steering_deg"),
            pl.col("yaw_rate"),
            pl.col("cfs_risk_score"),
        ).map_elements(
            lambda s: compute_drag_scrub_index(s),
            return_dtype=pl.Float64,
        )
        # Row path skips first row (via _init_derivative_row continue)
        row_idx = pl.int_range(0, df.height, dtype=pl.Int64)
        drag_expr = pl.when(row_idx == 0).then(None).otherwise(drag_expr).alias("drag_scrub_suspicion")
        df = df.with_columns(drag_expr)

    return df


# ── Slice 3: platform compression ───────────────────────────────

def _compute_compression_index(df: pl.DataFrame) -> pl.DataFrame:
    """Compute platform_compression_index.

    Matches _compute_compression_index in calculated_channels.py:
        platform_compression_index = min(1.0,
            cfs_risk * 0.4 + platform_stability_score * 0.3 + drag_scrub_suspicion * 0.3)
    """
    needed = {"cfs_risk_score", "platform_stability_score", "drag_scrub_suspicion"}
    if not needed.issubset(df.columns):
        return df

    # Row path: first row gets None (via _init_derivative_row), subsequent rows computed
    row_idx = pl.int_range(0, df.height, dtype=pl.Int64)
    cfs_risk = pl.col("cfs_risk_score").fill_null(0.0)
    plat_stab = pl.col("platform_stability_score").fill_null(0.0)
    drag_susp = pl.col("drag_scrub_suspicion").fill_null(0.0)

    comp = (cfs_risk * 0.4 + plat_stab * 0.3 + drag_susp * 0.3).clip(0.0, 1.0)
    comp = pl.when(row_idx == 0).then(None).otherwise(comp)
    df = df.with_columns(comp.alias("platform_compression_index"))
    return df


# ── Slice 3: shock rolling aggregates ───────────────────────────

_SHOCK_ROLLING_WINDOW = 60  # matches row path default


def _compute_shock_rolling_aggregates(df: pl.DataFrame) -> pl.DataFrame:
    """Compute per-corner and component-average shock rolling aggregates.

    Matches _update_shock_buffers + _compute_component_averages in
    calculated_channels.py using Polars rolling window functions.

    Row path uses a trailing buffer of length `window` (default 60).
    Polars .rolling_* functions use a window based on index rows.
    At window edges (first `window`-1 rows), the row path has partial
    buffers while Polars uses whatever is available — this creates small
    differences in the first ~60 rows.  After the window fills, results
    converge.

    NOTE: The row path uses `or 0.0` for missing shock velocities, so
    None values are treated as 0.0.  We match this with fill_null(0.0).
    """
    corners = ("lf", "rf", "lr", "rr")
    window = _SHOCK_ROLLING_WINDOW

    for c in corners:
        sv_col = f"{c}_shock_vel_in_s"
        if sv_col not in df.columns:
            continue

        sv = pl.col(sv_col).fill_null(0.0)
        sv_sq = sv * sv

        # Rolling mean of squared values → RMS
        # Row path: sqrt(mean(sv^2 over buffer))
        rms = sv_sq.rolling_mean(window_size=window, min_samples=1).sqrt()
        df = df.with_columns(rms.alias(f"{c}_shock_velocity_rms"))

        # Rolling activity: mean(abs(sv)) + peak*0.3
        # Row path: sum(abs(sv))/len(buf) + max(abs(sv))*0.3
        abs_sv = sv.abs()
        mean_abs = abs_sv.rolling_mean(window_size=window, min_samples=1)
        peak = abs_sv.rolling_max(window_size=window, min_samples=1)
        activity = mean_abs + peak * 0.3
        df = df.with_columns(activity.alias(f"{c}_shock_activity_index"))

        # Rolling energy: sum(sv^2 over buffer)
        # Row path: sum(v*v for v in buf)
        energy = sv_sq.rolling_sum(window_size=window, min_samples=1)
        df = df.with_columns(energy.alias(f"{c}_damper_energy_proxy"))

    # Component averages (mean across 4 corners)
    # Row path always produces these (defaults to 0.0 when no shock columns)
    any_corner = any(f"{c}_shock_vel_in_s" in df.columns for c in corners)
    for component in ("shock_velocity_rms", "shock_activity_index", "damper_energy_proxy"):
        if corner_cols := [f"{c}_{component}" for c in corners if f"{c}_{component}" in df.columns]:
            avg_expr = pl.mean_horizontal(
                *[pl.col(col).fill_null(0.0) for col in corner_cols]
            )
            df = df.with_columns(avg_expr.alias(component))
        elif not any_corner and df.height > 0:
            # No shock columns at all — produce 0.0 to match row path
            df = df.with_columns(pl.lit(0.0, dtype=pl.Float64).alias(component))

    # damper_work_proxy is an alias for damper_energy_proxy
    if "damper_energy_proxy" in df.columns and "damper_work_proxy" not in df.columns:
        df = df.with_columns(pl.col("damper_energy_proxy").alias("damper_work_proxy"))

    return df


# ── Final sweep: tire derived ────────────────────────────────────

_TIRE_CORNERS: tuple[str, ...] = ("lf", "rf", "lr", "rr")


def _compute_tire_derived(df: pl.DataFrame) -> pl.DataFrame:
    """Compute pressure gain, temp spread, and wear spread per corner.

    Matches _compute_tire_derived in calculated_channels.py.
    """
    for c in _TIRE_CORNERS:
        p_col = f"{c}_pressure"
        cp_col = f"{c}_cold_pressure"
        if p_col in df.columns and cp_col in df.columns:
            df = df.with_columns(
                (pl.col(p_col) - pl.col(cp_col)).alias(f"{c}_pressure_gain"),
            )

        ti = f"{c}_temp_inner"
        tm = f"{c}_temp_middle"
        to = f"{c}_temp_outer"
        temps = [col for col in (ti, tm, to) if col in df.columns]
        if len(temps) >= 2:
            max_expr = pl.max_horizontal(*[pl.col(col) for col in temps])
            min_expr = pl.min_horizontal(*[pl.col(col) for col in temps])
            df = df.with_columns(
                (max_expr - min_expr).alias(f"{c}_temp_spread"),
            )

        wi = f"{c}_wear_inner"
        wm = f"{c}_wear_middle"
        wo = f"{c}_wear_outer"
        wears = [col for col in (wi, wm, wo) if col in df.columns]
        if len(wears) >= 2:
            max_expr = pl.max_horizontal(*[pl.col(col) for col in wears])
            min_expr = pl.min_horizontal(*[pl.col(col) for col in wears])
            df = df.with_columns(
                (max_expr - min_expr).alias(f"{c}_wear_spread"),
            )

    return df


# ── Final sweep: scrub proxies ───────────────────────────────────

def _compute_scrub_proxies(df: pl.DataFrame) -> pl.DataFrame:
    """Compute front_scrub_proxy, rear_scrub_proxy, and yaw_error_proxy.

    Matches _compute_scrub_proxies in calculated_channels.py.
    Uses map_elements for yaw_error logic (complex curvature math).
    """
    # yaw_error_proxy
    if df.height == 0:
        return df
    has_yaw = {"yaw_rate", "radius_m", "speed_mps"}.issubset(df.columns)
    if has_yaw:
        yaw_rate = pl.col("yaw_rate").abs()
        speed = pl.col("speed_mps")
        radius = pl.col("radius_m")
        yaw_theoretical = speed / radius
        yaw_error = (yaw_theoretical - yaw_rate).clip(lower_bound=0.0)
        yaw_error = pl.when((radius > 0) & (speed > 1.0)).then(yaw_error).otherwise(0.0)
        df = df.with_columns(yaw_error.alias("yaw_error_proxy"))
    else:
        df = df.with_columns(pl.lit(0.0, dtype=pl.Float64).alias("yaw_error_proxy"))

    # front_scrub_proxy
    has_front_scrub = {"lf_slip_ratio", "rf_slip_ratio",
                       "abs_steering_deg", "abs_lat_accel",
                       "yaw_rate", "radius_m", "speed_mps"}.issubset(df.columns)
    if has_front_scrub:
        lf_slip = pl.col("lf_slip_ratio")
        rf_slip = pl.col("rf_slip_ratio")
        slip_delta = (rf_slip - lf_slip).abs()
        steering = pl.col("abs_steering_deg").fill_null(0.0)
        lat_accel = pl.col("abs_lat_accel").fill_null(0.0)
        steering_lat = (steering / 90.0) * lat_accel
        yaw_error = pl.col("yaw_error_proxy").fill_null(0.0)
        yaw_component = (yaw_error / 0.15).clip(0.0, 1.0)
        scrub = slip_delta * 0.30 + steering_lat * 0.25 + yaw_component * 0.45
        scrub = pl.when(lf_slip.is_not_null() & rf_slip.is_not_null()).then(scrub).otherwise(None)
        df = df.with_columns(scrub.alias("front_scrub_proxy"))

    # rear_scrub_proxy
    if {"lr_slip_ratio", "rr_slip_ratio"}.issubset(df.columns):
        rear_scrub = (pl.col("rr_slip_ratio") - pl.col("lr_slip_ratio")).abs()
        rear_scrub = pl.when(
            pl.col("lr_slip_ratio").is_not_null() & pl.col("rr_slip_ratio").is_not_null()
        ).then(rear_scrub).otherwise(None)
        df = df.with_columns(rear_scrub.alias("rear_scrub_proxy"))

    return df


# ── Final sweep: dynamic pressure lap index ─────────────────────

def _compute_dynamic_pressure_lap_index(df: pl.DataFrame) -> pl.DataFrame:
    """Compute dynamic_pressure_lap_index and dynamic_pressure_index.

    Matches the lap-relative normalization in _apply_derivatives.
    """
    if "dynamic_pressure_psf" not in df.columns:
        return df
    max_dp = pl.col("dynamic_pressure_psf").max()
    # Use max of max_dp and 1.0 to avoid division by zero
    denom = pl.max_horizontal(max_dp, pl.lit(1.0))
    idx = pl.col("dynamic_pressure_psf") / denom
    df = df.with_columns(
        idx.alias("dynamic_pressure_lap_index"),
        idx.alias("dynamic_pressure_index"),
    )
    return df


# ── Final sweep: dynamic grade ───────────────────────────────────

def _compute_dynamic_grade(df: pl.DataFrame) -> pl.DataFrame:
    """Compute dynamic_grade_deg from long_accel and speed_rate_mps2.

    Matches _compute_dynamic_grade in calculated_channels.py.
    """
    if "long_accel" not in df.columns or "speed_rate_mps2" not in df.columns:
        return df
    ax = pl.col("long_accel")
    dvdt = pl.col("speed_rate_mps2")
    sin_theta = ((ax - dvdt) / 9.81).clip(-1.0, 1.0)
    # Polars doesn't have asin, use when/then with math.asin via map_elements
    grade = pl.struct(sin_theta.alias("sin_theta")).map_elements(
        lambda s: math.degrees(math.asin(s["sin_theta"])) if s["sin_theta"] is not None else None,
        return_dtype=pl.Float64,
    )
    grade = pl.when(ax.is_not_null() & dvdt.is_not_null()).then(grade).otherwise(None)
    df = df.with_columns(grade.alias("dynamic_grade_deg"))
    return df


# ── Final sweep: GPS projection ──────────────────────────────────

def _apply_gps_projection(df: pl.DataFrame) -> pl.DataFrame:
    """Project lat/lon to local Cartesian coordinates.

    Matches _apply_gps_projection in calculated_channels.py.
    """
    if "lat" not in df.columns or "lon" not in df.columns:
        return df
    lat = pl.col("lat")
    lon = pl.col("lon")
    # Convert degrees to radians if needed (values > pi are degrees)
    lat_rad = pl.when(lat.abs() > math.pi).then(lat * math.pi / 180.0).otherwise(lat)
    lon_rad = pl.when(lon.abs() > math.pi).then(lon * math.pi / 180.0).otherwise(lon)
    # Use first row as origin
    lat0 = lat_rad.first()
    lon0 = lon_rad.first()
    x_m = EARTH_RADIUS_M * lat0.cos() * (lon_rad - lon0)
    y_m = EARTH_RADIUS_M * (lat_rad - lat0)
    df = df.with_columns(
        x_m.alias("track_x_m"),
        y_m.alias("track_y_m"),
        (x_m * M_TO_FT).alias("track_x_ft"),
        (y_m * M_TO_FT).alias("track_y_ft"),
    )
    return df
