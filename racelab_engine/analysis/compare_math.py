from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ChannelDeltaStats, CornerDelta, Corner, Direction,
    PlatformComparison, TireComparison, ShockComparison,
    DriverComparison, PowertrainComparison, WholeCarIndex,
    build_lap_grid, interpolate_run_to_grid,
)


def _delta_dict(d: ChannelDeltaStats | None) -> dict | None:
    if d is None:
        return None
    return {
        "channel": d.channel, "label": d.label, "unit": d.unit,
        "baseline_avg": d.baseline_avg, "test_avg": d.test_avg, "delta_avg": d.delta_avg,
        "baseline_min": d.baseline_min, "test_min": d.test_min,
        "baseline_max": d.baseline_max, "test_max": d.test_max,
        "direction": d.direction, "interpretation": d.interpretation, "confidence": d.confidence,
    }


def _corner_dict(c: CornerDelta) -> dict:
    return {
        "corner": c.corner,
        "ride_height_in": _delta_dict(c.ride_height_in),
        "shock_defl_in": _delta_dict(c.shock_defl_in),
        "shock_vel_in_s": _delta_dict(c.shock_vel_in_s),
        "tire_pressure": _delta_dict(c.tire_pressure),
        "wheel_speed": _delta_dict(c.wheel_speed),
        "slip_ratio_proxy": _delta_dict(c.slip_ratio_proxy),
        "corner_score": c.corner_score, "warnings": c.warnings,
    }


def _platform_dict(p: PlatformComparison) -> dict:
    return {
        "cfs_height": _delta_dict(p.cfs_height),
        "front_avg_rh": _delta_dict(p.front_avg_rh),
        "rear_avg_rh": _delta_dict(p.rear_avg_rh),
        "center_rake_fs": _delta_dict(p.center_rake_fs),
        "side_rake": _delta_dict(p.side_rake),
        "front_split": _delta_dict(p.front_split),
        "rear_split": _delta_dict(p.rear_split),
        "dynamic_pressure": _delta_dict(p.dynamic_pressure),
        "cfs_risk_score": _delta_dict(p.cfs_risk_score),
        "platform_risk_delta_label": p.platform_risk_delta_label,
        "platform_verdict": p.platform_verdict,
    }


def _tire_dict(t):
    return {
        "corners": {k: _corner_dict(v) for k, v in t.corners.items()},
        "temp_spread_summary": t.temp_spread_summary,
        "wear_summary": t.wear_summary,
        "tire_verdict": t.tire_verdict,
        "short_run_warning": t.short_run_warning,
    }


def _shock_dict(s):
    return {
        "corners": {k: _corner_dict(v) for k, v in s.corners.items()},
        "shock_velocity_rms_avg": _delta_dict(s.shock_velocity_rms_avg),
        "shock_activity_index": _delta_dict(s.shock_activity_index),
        "shock_verdict": s.shock_verdict,
    }


def _driver_dict(d):
    return {
        "avg_throttle_pct": _delta_dict(d.avg_throttle_pct),
        "full_throttle_pct_time": _delta_dict(d.full_throttle_pct_time),
        "avg_brake_pct": _delta_dict(d.avg_brake_pct),
        "avg_abs_steering_deg": _delta_dict(d.avg_abs_steering_deg),
        "max_abs_steering_deg": _delta_dict(d.max_abs_steering_deg),
        "driver_changed_warning": d.driver_changed_warning,
        "driver_verdict": d.driver_verdict,
    }


def _powertrain_dict(p):
    return {
        "avg_rpm": _delta_dict(p.avg_rpm),
        "min_rpm": _delta_dict(p.min_rpm),
        "max_rpm": _delta_dict(p.max_rpm),
        "gear_usage": p.gear_usage,
        "speed_vs_rpm": p.speed_vs_rpm,
        "pull_score": _delta_dict(p.pull_score),
        "water_temp": _delta_dict(p.water_temp),
        "oil_temp": _delta_dict(p.oil_temp),
        "powertrain_verdict": p.powertrain_verdict,
    }


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
    return PlatformComparison(
        cfs_height=cfs, front_avg_rh=fr, rear_avg_rh=rr,
        center_rake_fs=cr, side_rake=sr,
        dynamic_pressure=dp, cfs_risk_score=risk,
        platform_risk_delta_label=rl,
        platform_verdict="better" if (cd and cd > 0) else "mixed",
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
) -> WholeCarIndex:
    si = _score_direction(platform.dynamic_pressure, 0.8, 0.5) * 80 + 20
    pi = _score_direction(platform.cfs_height, 0.9, 0.5) * 85
    di = _score_direction(driver.avg_abs_steering_deg, 0.9, 0.7) * 90
    pwi = _score_direction(powertrain.pull_score, 0.85, 0.6) * 75 if powertrain else 50
    dici = min(100, discipline_score) if discipline_score else 50
    # Weighted average — tire/shock indices are null (not yet implemented),
    # so redistribute their weight across available subsystems.
    weights = {"speed": 0.30, "platform": 0.30, "driver": 0.18, "powertrain": 0.12, "discipline": 0.10}
    ov = si * weights["speed"] + pi * weights["platform"] + di * weights["driver"] + pwi * weights["powertrain"] + dici * weights["discipline"]
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
