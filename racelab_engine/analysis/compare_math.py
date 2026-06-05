from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ChannelDeltaStats, Corner, CornerDelta, Direction,
    PlatformComparison, TireComparison, ShockComparison,
    DriverComparison, PowertrainComparison, WholeCarIndex,
    build_lap_grid, interpolate_run_to_grid,
)
from racelab_engine.analysis.constants import WCI_WEIGHT_PROFILES, logistic_score


def _compute_direction(delta: float | None, higher_is: str) -> Direction | None:
    if delta is None or abs(delta) <= 1e-9:
        return None
    if higher_is == "better":
        return "better" if delta > 0 else "worse"
    if higher_is == "worse":
        return "worse" if delta > 0 else "better"
    return "neutral"


def aggregate_channel_stats(
    bl_grid: dict[str, list[float | None]],
    t_grid: dict[str, list[float | None]],
    channel: str, label: str | None = None,
    unit: str = "", higher_is: str = "better",
) -> ChannelDeltaStats:
    bl = [v for v in (bl_grid.get(channel) or []) if v is not None]
    t = [v for v in (t_grid.get(channel) or []) if v is not None]
    bl_avg = sum(bl) / len(bl) if bl else None
    t_avg = sum(t) / len(t) if t else None
    delta = (t_avg - bl_avg) if bl_avg is not None and t_avg is not None else None
    direction = _compute_direction(delta, higher_is)
    return ChannelDeltaStats(
        channel=channel, label=label or channel, unit=unit,
        baseline_avg=bl_avg, test_avg=t_avg, delta_avg=delta,
        baseline_min=min(bl, default=None),
        test_min=min(t, default=None),
        baseline_max=max(bl, default=None),
        test_max=max(t, default=None),
        direction=direction,
        interpretation=f"{label or channel}: {direction or 'unchanged'}",
        confidence=0.6 if (bl and t) else 0.0,
    )


def aggregate_platform_stats(
    bl_rows: list[dict], t_rows: list[dict],
    start: float = 0.0, end: float = 100.0,
) -> PlatformComparison:
    grid = build_lap_grid(start, end)
    chs = [
        "cfs_ride_height_in", "lf_ride_height_in", "rf_ride_height_in",
        "lr_ride_height_in", "rr_ride_height_in",
        "front_avg_rh_in", "rear_avg_rh_in",
        "center_rake_fs_in", "side_rake_in",
        "dynamic_pressure_psf", "cfs_risk_score",
    ]
    bl = interpolate_run_to_grid(bl_rows, chs, grid)
    t = interpolate_run_to_grid(t_rows, chs, grid)
    cfs = aggregate_channel_stats(bl, t, "cfs_ride_height_in", "CFS Ride Height", "in", "better")
    fr = aggregate_channel_stats(bl, t, "front_avg_rh_in", "Front Avg RH", "in", "better")
    rr = aggregate_channel_stats(bl, t, "rear_avg_rh_in", "Rear Avg RH", "in", "neutral")
    cr = aggregate_channel_stats(bl, t, "center_rake_fs_in", "Center Rake FS", "in", "neutral")
    sr = aggregate_channel_stats(bl, t, "side_rake_in", "Side Rake", "in", "neutral")
    dp = aggregate_channel_stats(bl, t, "dynamic_pressure_psf", "Dynamic Pressure", "psf", "neutral")
    risk = aggregate_channel_stats(bl, t, "cfs_risk_score", "CFS Risk Score", "score", "worse")
    cd = cfs.delta_avg
    if cd and cd > 0.001:
        rl = "improved"
    elif cd and cd < -0.001:
        rl = "worsened"
    else:
        rl = "unchanged"

    # Rake stability: if speed improved but rake changed significantly, flag as mixed
    rake_delta = cr.delta_avg
    rake_unstable = rake_delta is not None and abs(rake_delta) > 0.05
    pv = "mixed"  # default
    if rl == "improved" and rake_unstable:
        pv = "mixed"
    elif cd is not None and cd > 0:
        pv = "better"

    return PlatformComparison(
        cfs_height=cfs, front_avg_rh=fr, rear_avg_rh=rr,
        center_rake_fs=cr, side_rake=sr,
        dynamic_pressure=dp, cfs_risk_score=risk,
        platform_risk_delta_label=rl,
        platform_verdict=pv,
    )


def aggregate_driver_stats(
    bl_rows: list[dict], t_rows: list[dict],
    start: float = 0.0, end: float = 100.0,
) -> DriverComparison:
    grid = build_lap_grid(start, end)
    chs = ["throttle_pct", "brake_pct", "abs_steering_deg"]
    bl = interpolate_run_to_grid(bl_rows, chs, grid)
    t = interpolate_run_to_grid(t_rows, chs, grid)
    th = aggregate_channel_stats(bl, t, "throttle_pct", "Throttle", "%", "better")
    br = aggregate_channel_stats(bl, t, "brake_pct", "Brake", "%", "neutral")
    st = aggregate_channel_stats(bl, t, "abs_steering_deg", "Steering", "deg", "worse")
    changed = (th.delta_avg and abs(th.delta_avg) > 2) or (st.delta_avg and abs(st.delta_avg) > 0.5)
    return DriverComparison(
        avg_throttle_pct=th, avg_brake_pct=br, avg_abs_steering_deg=st,
        driver_changed_warning="Driver input changed — reduced comparison confidence." if changed else None,
        driver_verdict="changed" if changed else "consistent",
    )


def aggregate_powertrain_stats(
    bl_rows: list[dict], t_rows: list[dict],
    start: float = 0.0, end: float = 100.0,
) -> PowertrainComparison:
    grid = build_lap_grid(start, end)
    chs = ["rpm", "gear", "water_temp", "oil_temp", "speed_rate_mph_1000ft"]
    bl = interpolate_run_to_grid(bl_rows, chs, grid)
    t = interpolate_run_to_grid(t_rows, chs, grid)
    rpm = aggregate_channel_stats(bl, t, "rpm", "RPM", "rpm", "neutral")
    pull = aggregate_channel_stats(bl, t, "speed_rate_mph_1000ft", "Speed Rate/1000ft", "mph/1000ft", "better")
    return PowertrainComparison(avg_rpm=rpm, pull_score=pull, powertrain_verdict="context")


def aggregate_corner_stats(
    bl_rows: list[dict], t_rows: list[dict],
    start: float = 0.0, end: float = 100.0,
) -> dict[Corner, CornerDelta]:
    corners: list[Corner] = ["LF", "RF", "LR", "RR"]
    grid = build_lap_grid(start, end)
    result: dict[Corner, CornerDelta] = {}
    for c in corners:
        p = c.lower()
        # Tire pressure and wheel speed channels are not aliased — raw names
        pressure_raw = f"{c}pressure"
        speed_raw = f"{c}speed"
        cl = [
            f"{p}_ride_height_in", f"{p}_shock_defl_in",
            f"{p}_shock_vel_in_s", f"{p}_slip_ratio",
            speed_raw, pressure_raw,
        ]
        bl = interpolate_run_to_grid(bl_rows, cl, grid)
        t = interpolate_run_to_grid(t_rows, cl, grid)
        result[c] = CornerDelta(
            corner=c,
            ride_height_in=aggregate_channel_stats(bl, t, f"{p}_ride_height_in", f"{c} RH", "in", "better"),
            shock_defl_in=aggregate_channel_stats(bl, t, f"{p}_shock_defl_in", f"{c} Shock Defl", "in", "neutral"),
            shock_vel_in_s=aggregate_channel_stats(bl, t, f"{p}_shock_vel_in_s", f"{c} Shock Vel", "in/s", "neutral"),
            tire_pressure=aggregate_channel_stats(bl, t, pressure_raw, f"{c} Pressure", "kPa", "neutral"),
            wheel_speed=aggregate_channel_stats(bl, t, speed_raw, f"{c} Wheel Speed", "m/s", "neutral"),
            slip_ratio_proxy=aggregate_channel_stats(bl, t, f"{p}_slip_ratio", f"{c} Slip Ratio", "ratio", "worse"),
        )
    return result


def aggregate_tire_comparison(
    bl_rows: list[dict], t_rows: list[dict],
    start: float = 0.0, end: float = 100.0,
    lap_count: int = 0,
) -> TireComparison:
    """Build a TireComparison from baseline and test rows in the target zone.

    Returns available=false with explanation if tire data is missing.
    Short runs get low confidence.
    """
    grid = build_lap_grid(start, end)
    tire_channels = [
        "lf_pressure_gain", "rf_pressure_gain", "lr_pressure_gain", "rr_pressure_gain",
        "lf_temp_spread", "rf_temp_spread", "lr_temp_spread", "rr_temp_spread",
        "lf_wear_spread", "rf_wear_spread", "lr_wear_spread", "rr_wear_spread",
        "lf_camber_temp_bias_c", "rf_camber_temp_bias_c",
        "lr_camber_temp_bias_c", "rr_camber_temp_bias_c",
    ]
    bl = interpolate_run_to_grid(bl_rows, tire_channels, grid)
    t = interpolate_run_to_grid(t_rows, tire_channels, grid)

    # Check if any tire data exists
    has_tire_data = any(
        any(v is not None for v in (bl.get(ch) or []))
        for ch in ["lf_pressure_gain", "lf_temp_spread"]
    )
    if not has_tire_data:
        return TireComparison(
            corners={},
            tire_verdict=None,
            short_run_warning="Tire context unavailable — missing tire channels.",
        )

    # Compute aggregate deltas
    pg_channels = ["lf_pressure_gain", "rf_pressure_gain", "lr_pressure_gain", "rr_pressure_gain"]
    ts_channels = ["lf_temp_spread", "rf_temp_spread", "lr_temp_spread", "rr_temp_spread"]
    ws_channels = ["lf_wear_spread", "rf_wear_spread", "lr_wear_spread", "rr_wear_spread"]

    def _avg_delta(chs: list[str]) -> float | None:
        vals: list[float] = []
        for ch in chs:
            bl_v = [v for v in (bl.get(ch) or []) if v is not None]
            t_v = [v for v in (t.get(ch) or []) if v is not None]
            if bl_v and t_v:
                vals.append(sum(t_v) / len(t_v) - sum(bl_v) / len(bl_v))
        return sum(vals) / len(vals) if vals else None

    pg_delta = _avg_delta(pg_channels)
    ts_delta = _avg_delta(ts_channels)
    ws_delta = _avg_delta(ws_channels)
    # Determine tire stress change label
    is_short_run = lap_count < 10

    # Build warnings
    warnings: list[str] = []
    if is_short_run:
        warnings.append("Short run — tire falloff conclusions are low confidence.")
    if pg_delta is not None and abs(pg_delta) > 2.0:
        warnings.append(f"Pressure gain changed by {pg_delta:+.1f} psi.")
    if ts_delta is not None and abs(ts_delta) > 5.0:
        warnings.append(f"Temp spread changed by {ts_delta:+.1f}°C.")

    # Stress change label
    if pg_delta is None and ts_delta is None:
        stress_label = "unavailable"
    elif (pg_delta is not None and pg_delta < -0.5) or (ts_delta is not None and ts_delta < -2.0):
        stress_label = "improved"
    elif (pg_delta is not None and pg_delta > 0.5) or (ts_delta is not None and ts_delta > 2.0):
        stress_label = "worse"
    else:
        stress_label = "similar"

    # Explanation
    parts: list[str] = []
    if pg_delta is not None:
        parts.append(f"pressure gain {pg_delta:+.1f} psi")
    if ts_delta is not None:
        parts.append(f"temp spread {ts_delta:+.1f}°C")
    if ws_delta is not None:
        parts.append(f"wear spread {ws_delta:+.2f} mm")

    return TireComparison(
        corners={},
        tire_verdict=stress_label,
        short_run_warning=warnings[0] if warnings else None,
    )


def aggregate_shock_comparison(
    bl_rows: list[dict], t_rows: list[dict],
    start: float = 0.0, end: float = 100.0,
) -> ShockComparison:
    """Build a ShockComparison from baseline and test rows in the target zone.

    Returns available=false with explanation if shock data is missing.
    Treats damper energy as proxy.
    """
    grid = build_lap_grid(start, end)
    shock_channels = [
        "shock_activity_index", "shock_velocity_rms",
        "damper_energy_proxy", "damper_work_proxy",
        "lf_shock_velocity_rms", "rf_shock_velocity_rms",
        "lr_shock_velocity_rms", "rr_shock_velocity_rms",
        "lf_shock_activity_index", "rf_shock_activity_index",
        "lr_shock_activity_index", "rr_shock_activity_index",
    ]
    bl = interpolate_run_to_grid(bl_rows, shock_channels, grid)
    t = interpolate_run_to_grid(t_rows, shock_channels, grid)

    # Check if any shock data exists
    has_shock_data = any(
        any(v is not None for v in (bl.get(ch) or []))
        for ch in ["shock_activity_index", "shock_velocity_rms"]
    )
    if not has_shock_data:
        return ShockComparison(
            corners={},
            shock_verdict=None,
        )

    sai = aggregate_channel_stats(bl, t, "shock_activity_index", "Shock Activity", "index", "worse")
    svr = aggregate_channel_stats(bl, t, "shock_velocity_rms", "Shock Velocity RMS", "in/s", "worse")

    # Determine shock stress change label
    sai_d = sai.delta_avg
    svr_d = svr.delta_avg
    if sai_d is None and svr_d is None:
        shock_label = "unavailable"
    elif (sai_d is not None and sai_d < -0.5) and (svr_d is not None and svr_d < -0.1):
        shock_label = "improved"
    elif (sai_d is not None and sai_d > 0.5) or (svr_d is not None and svr_d > 0.1):
        shock_label = "worse"
    else:
        shock_label = "similar"

    return ShockComparison(
        corners={},
        shock_velocity_rms_avg=svr,
        shock_activity_index=sai,
        shock_verdict=shock_label,
    )


def _score_direction(d: ChannelDeltaStats | None, bv: float = 0.85, fb: float = 0.55) -> float:
    if d is None or d.direction is None:
        return 0.5
    if d.direction == "better":
        return bv
    return 0.2 if d.direction == "worse" else fb


def _overall_label(ov: float) -> str:
    if ov >= 85:
        return "Strong improvement"
    if ov >= 70:
        return "Likely improvement"
    if ov >= 55:
        return "Mixed / small gain"
    return "Inconclusive" if ov >= 40 else "Worse"


def compute_whole_car_index(
    platform: PlatformComparison,
    driver: DriverComparison,
    powertrain: PowertrainComparison | None = None,
    discipline_score: float = 50.0,
    context_problems: int = 0,
    track_type: str = "oval",
) -> WholeCarIndex:
    # Logistic scoring for continuous, analog sub-scores
    speed_delta = platform.dynamic_pressure.delta_avg if platform.dynamic_pressure else None
    si = logistic_score(delta=speed_delta, noise=0.05, steepness=2.5, higher_is_better=True)

    cfs_delta = platform.cfs_height.delta_avg if platform.cfs_height else None
    pi = logistic_score(delta=cfs_delta, noise=0.001, steepness=80.0, higher_is_better=True)

    steering_delta = driver.avg_abs_steering_deg.delta_avg if driver.avg_abs_steering_deg else None
    di = logistic_score(delta=steering_delta, noise=0.25, steepness=3.0, higher_is_better=False)

    pull_delta = powertrain.pull_score.delta_avg if powertrain and powertrain.pull_score else None
    pwi = logistic_score(delta=pull_delta, noise=0.05, steepness=2.0, higher_is_better=True) if pull_delta is not None else 50.0

    dici = min(100, discipline_score) if discipline_score else 50

    # Select weight profile by track type, fall back to oval
    weights = WCI_WEIGHT_PROFILES.get(track_type, WCI_WEIGHT_PROFILES["oval"])
    ov = (
        si * weights["speed"]
        + pi * weights["platform"]
        + di * weights["driver"]
        + pwi * weights["powertrain"]
        + dici * weights["discipline"]
    )
    ov = min(100, max(0, ov))
    lb = _overall_label(ov)
    return WholeCarIndex(
        speed_index=round(si, 1), platform_index=round(pi, 1),
        tire_index=None, shock_index=None,
        driver_index=round(di, 1), powertrain_index=round(pwi, 1),
        test_discipline_index=round(dici, 1),
        confidence_index=70.0 if context_problems == 0 else 45.0,
        overall_index=round(ov, 1), overall_label=lb,
    )
