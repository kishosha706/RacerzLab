from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from racelab_engine.analysis.constants import LAP_WRAP_DROP_THRESHOLD_PCT

# ── types ───────────────────────────────────────────────────────

VerdictKind = Literal["keep_direction", "undo", "retest", "inconclusive"]
Significance = Literal["minor", "moderate", "major"]
SetupGroup = Literal[
    "front_platform", "rear_platform", "tires", "shocks", "springs",
    "aero_cooling", "gearing", "weight_distribution", "alignment", "unknown",
]
Corner = Literal["LF", "RF", "LR", "RR"]
Direction = Literal["better", "worse", "neutral", "context", "mixed"]


# ── models ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ComparedChannelDelta:
    channel: str
    label: str
    unit: str
    baseline_avg: float | None = None
    test_avg: float | None = None
    delta: float | None = None
    baseline_min: float | None = None
    test_min: float | None = None
    baseline_max: float | None = None
    test_max: float | None = None


@dataclass(frozen=True)
class ChannelDeltaStats:
    channel: str
    label: str
    unit: str
    baseline_avg: float | None = None
    test_avg: float | None = None
    delta_avg: float | None = None
    baseline_min: float | None = None
    test_min: float | None = None
    baseline_max: float | None = None
    test_max: float | None = None
    direction: Direction | None = None
    interpretation: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class CornerDelta:
    corner: Corner
    ride_height_in: ChannelDeltaStats | None = None
    shock_defl_in: ChannelDeltaStats | None = None
    shock_vel_in_s: ChannelDeltaStats | None = None
    shock_velocity_rms: ChannelDeltaStats | None = None
    tire_pressure: ChannelDeltaStats | None = None
    tire_temp_inner: ChannelDeltaStats | None = None
    tire_temp_middle: ChannelDeltaStats | None = None
    tire_temp_outer: ChannelDeltaStats | None = None
    temp_spread: ChannelDeltaStats | None = None
    tire_wear: ChannelDeltaStats | None = None
    wheel_speed: ChannelDeltaStats | None = None
    slip_ratio_proxy: ChannelDeltaStats | None = None
    corner_score: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlatformComparison:
    cfs_height: ChannelDeltaStats | None = None
    front_avg_rh: ChannelDeltaStats | None = None
    rear_avg_rh: ChannelDeltaStats | None = None
    left_avg_rh: ChannelDeltaStats | None = None
    right_avg_rh: ChannelDeltaStats | None = None
    center_rake_fs: ChannelDeltaStats | None = None
    side_rake: ChannelDeltaStats | None = None
    front_split: ChannelDeltaStats | None = None
    rear_split: ChannelDeltaStats | None = None
    dynamic_pressure: ChannelDeltaStats | None = None
    cfs_risk_score: ChannelDeltaStats | None = None
    platform_risk_delta_label: str = "unavailable"
    platform_verdict: str | None = None


@dataclass(frozen=True)
class TireComparison:
    corners: dict[Corner, CornerDelta] = field(default_factory=dict)
    front_pressure_balance: ChannelDeltaStats | None = None
    rear_pressure_balance: ChannelDeltaStats | None = None
    temp_spread_summary: str | None = None
    wear_summary: str | None = None
    tire_verdict: str | None = None
    short_run_warning: str | None = None


@dataclass(frozen=True)
class ShockComparison:
    corners: dict[Corner, CornerDelta] = field(default_factory=dict)
    shock_velocity_rms_avg: ChannelDeltaStats | None = None
    shock_activity_index: ChannelDeltaStats | None = None
    shock_verdict: str | None = None


@dataclass(frozen=True)
class DriverComparison:
    avg_throttle_pct: ChannelDeltaStats | None = None
    full_throttle_pct_time: ChannelDeltaStats | None = None
    avg_brake_pct: ChannelDeltaStats | None = None
    avg_abs_steering_deg: ChannelDeltaStats | None = None
    max_abs_steering_deg: ChannelDeltaStats | None = None
    driver_changed_warning: str | None = None
    driver_verdict: str | None = None


@dataclass(frozen=True)
class PowertrainComparison:
    avg_rpm: ChannelDeltaStats | None = None
    min_rpm: ChannelDeltaStats | None = None
    max_rpm: ChannelDeltaStats | None = None
    gear_usage: str | None = None
    speed_vs_rpm: str | None = None
    pull_score: ChannelDeltaStats | None = None
    water_temp: ChannelDeltaStats | None = None
    oil_temp: ChannelDeltaStats | None = None
    powertrain_verdict: str | None = None


@dataclass(frozen=True)
class WholeCarIndex:
    speed_index: float | None = None
    platform_index: float | None = None
    tire_index: float | None = None
    shock_index: float | None = None
    driver_index: float | None = None
    powertrain_index: float | None = None
    test_discipline_index: float | None = None
    confidence_index: float | None = None
    overall_index: float | None = None
    overall_label: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in
                ["speed_index", "platform_index", "tire_index", "shock_index",
                 "driver_index", "powertrain_index", "test_discipline_index",
                 "confidence_index", "overall_index", "overall_label"]}


@dataclass(frozen=True)
class EnhancedComparisonSummary:
    comparison_id: str
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None
    test_lap: int | None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0
    whole_car_index: WholeCarIndex | None = None
    platform: PlatformComparison | None = None
    corner_matrix: dict[Corner, CornerDelta] = field(default_factory=dict)
    tire_comparison: TireComparison | None = None
    shock_comparison: ShockComparison | None = None
    driver_comparison: DriverComparison | None = None
    powertrain_comparison: PowertrainComparison | None = None
    setup_changes: list[dict] = field(default_factory=list)
    context_changes: list[dict] = field(default_factory=list)
    test_discipline: dict | None = None
    verdict: dict | None = None
    warnings: list[str] = field(default_factory=list)
    confidence_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "baseline_run_id": self.baseline_run_id,
            "test_run_id": self.test_run_id,
            "baseline_lap": self.baseline_lap,
            "test_lap": self.test_lap,
            "target_zone_start_pct": self.target_zone_start_pct,
            "target_zone_end_pct": self.target_zone_end_pct,
            "whole_car_index": self.whole_car_index.as_dict() if self.whole_car_index else None,
            "platform": _platform_dict(self.platform) if self.platform else None,
            "corner_matrix": {k: _corner_dict(v) for k, v in (self.corner_matrix or {}).items()},
            "tire_comparison": _tire_dict(self.tire_comparison) if self.tire_comparison else None,
            "shock_comparison": _shock_dict(self.shock_comparison) if self.shock_comparison else None,
            "driver_comparison": _driver_dict(self.driver_comparison) if self.driver_comparison else None,
            "powertrain_comparison": _powertrain_dict(self.powertrain_comparison) if self.powertrain_comparison else None,
            "setup_changes": self.setup_changes,
            "context_changes": self.context_changes,
            "test_discipline": self.test_discipline,
            "verdict": self.verdict,
            "warnings": self.warnings,
            "confidence_score": self.confidence_score,
        }


@dataclass(frozen=True)
class SetupChange:
    setup_key: str
    label: str
    group: SetupGroup
    baseline_value: Any = None
    test_value: Any = None
    unit: str | None = None
    delta: str | None = None
    significance: Significance = "minor"
    related_to_target_issue: bool = False


@dataclass(frozen=True)
class ContextChange:
    key: str
    label: str
    baseline_value: Any = None
    test_value: Any = None
    warning: str | None = None
    is_problem: bool = False


@dataclass(frozen=True)
class TargetZoneComparison:
    start_pct: float
    end_pct: float
    channel_deltas: list[ComparedChannelDelta] = field(default_factory=list)
    speed_gain_or_loss_label: str = "unchanged"
    platform_risk_delta_label: str = "unchanged"


@dataclass(frozen=True)
class TestDisciplineResult:
    score: int
    label: str
    positive_factors: list[str] = field(default_factory=list)
    negative_factors: list[str] = field(default_factory=list)
    recommendation: str | None = None

    @property
    def is_reliable(self) -> bool:
        """Whether this discipline result indicates a controlled, trustworthy test."""
        from racelab_engine.analysis.constants import RELIABLE_DISCIPLINES
        return self.label in RELIABLE_DISCIPLINES


@dataclass(frozen=True)
class DidItWorkVerdict:
    verdict: VerdictKind
    confidence_score: float
    headline: str
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_step: str | None = None


@dataclass(frozen=True)
class RunComparisonSummary:
    comparison_id: str
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None
    test_lap: int | None
    target_zone: TargetZoneComparison | None = None
    setup_changes: list[SetupChange] = field(default_factory=list)
    context_changes: list[ContextChange] = field(default_factory=list)
    test_discipline: TestDisciplineResult | None = None
    verdict: DidItWorkVerdict | None = None
    warnings: list[str] = field(default_factory=list)
    confidence_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "baseline_run_id": self.baseline_run_id,
            "test_run_id": self.test_run_id,
            "baseline_lap": self.baseline_lap,
            "test_lap": self.test_lap,
            "target_zone": _zone_dict(self.target_zone) if self.target_zone else None,
            "setup_changes": [_setup_change_dict(c) for c in self.setup_changes],
            "context_changes": [_context_change_dict(c) for c in self.context_changes],
            "test_discipline": _discipline_dict(self.test_discipline) if self.test_discipline else None,
            "verdict": _verdict_dict(self.verdict) if self.verdict else None,
            "warnings": self.warnings,
            "confidence_score": self.confidence_score,
        }


def _zone_dict(z: TargetZoneComparison) -> dict[str, Any]:
    return {
        "start_pct": z.start_pct,
        "end_pct": z.end_pct,
        "channel_deltas": [
            {"channel": d.channel, "label": d.label, "unit": d.unit,
             "baseline_avg": d.baseline_avg, "test_avg": d.test_avg, "delta": d.delta,
             "baseline_min": d.baseline_min, "test_min": d.test_min,
             "baseline_max": d.baseline_max, "test_max": d.test_max}
            for d in z.channel_deltas
        ],
        "speed_gain_or_loss_label": z.speed_gain_or_loss_label,
        "platform_risk_delta_label": z.platform_risk_delta_label,
    }


def _setup_change_dict(c: SetupChange) -> dict[str, Any]:
    return {
        "setup_key": c.setup_key, "label": c.label, "group": c.group,
        "baseline_value": c.baseline_value, "test_value": c.test_value,
        "unit": c.unit, "delta": c.delta, "significance": c.significance,
        "related_to_target_issue": c.related_to_target_issue,
    }


def _context_change_dict(c: ContextChange) -> dict[str, Any]:
    return {"key": c.key, "label": c.label, "baseline_value": c.baseline_value,
            "test_value": c.test_value, "warning": c.warning, "is_problem": c.is_problem}


def _discipline_dict(d: TestDisciplineResult) -> dict[str, Any]:
    return {"score": d.score, "label": d.label, "positive_factors": d.positive_factors,
            "negative_factors": d.negative_factors, "recommendation": d.recommendation}


def _verdict_dict(v: DidItWorkVerdict) -> dict[str, Any]:
    return {"verdict": v.verdict, "confidence_score": v.confidence_score,
            "headline": v.headline, "evidence": v.evidence, "warnings": v.warnings,
            "next_step": v.next_step}


# ── serializer helpers (used by EnhancedComparisonSummary.as_dict) ──

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
        "shock_velocity_rms": _delta_dict(c.shock_velocity_rms),
        "tire_pressure": _delta_dict(c.tire_pressure),
        "tire_temp_inner": _delta_dict(c.tire_temp_inner),
        "tire_temp_middle": _delta_dict(c.tire_temp_middle),
        "tire_temp_outer": _delta_dict(c.tire_temp_outer),
        "temp_spread": _delta_dict(c.temp_spread),
        "tire_wear": _delta_dict(c.tire_wear),
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


def _tire_dict(t: Any) -> dict:
    return {
        "corners": {k: _corner_dict(v) for k, v in t.corners.items()},
        "front_pressure_balance": _delta_dict(t.front_pressure_balance),
        "rear_pressure_balance": _delta_dict(t.rear_pressure_balance),
        "temp_spread_summary": t.temp_spread_summary,
        "wear_summary": t.wear_summary,
        "tire_verdict": t.tire_verdict,
        "short_run_warning": t.short_run_warning,
    }


def _shock_dict(s: Any) -> dict:
    return {
        "corners": {k: _corner_dict(v) for k, v in s.corners.items()},
        "shock_velocity_rms_avg": _delta_dict(s.shock_velocity_rms_avg),
        "shock_activity_index": _delta_dict(s.shock_activity_index),
        "shock_verdict": s.shock_verdict,
    }


def _driver_dict(d: Any) -> dict:
    return {
        "avg_throttle_pct": _delta_dict(d.avg_throttle_pct),
        "full_throttle_pct_time": _delta_dict(d.full_throttle_pct_time),
        "avg_brake_pct": _delta_dict(d.avg_brake_pct),
        "avg_abs_steering_deg": _delta_dict(d.avg_abs_steering_deg),
        "max_abs_steering_deg": _delta_dict(d.max_abs_steering_deg),
        "driver_changed_warning": d.driver_changed_warning,
        "driver_verdict": d.driver_verdict,
    }


def _powertrain_dict(p: Any) -> dict:
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


# ── interpolation engine ─────────────────────────────────────────

COMPARE_CHANNELS = [
    "speed_mph", "speed_rate_mph_1000ft", "rpm", "throttle_pct", "brake_pct",
    "steering_deg", "cfs_ride_height_in", "center_rake_fs_in", "side_rake_in",
    "dynamic_pressure_psf", "drag_scrub_suspicion", "cfs_risk_score",
]

CHANNEL_LABELS: dict[str, str] = {
    "speed_mph": "Speed", "speed_rate_mph_1000ft": "Speed Rate/1000ft",
    "rpm": "RPM", "throttle_pct": "Throttle", "brake_pct": "Brake",
    "steering_deg": "Steering", "cfs_ride_height_in": "CFS Ride Height",
    "center_rake_fs_in": "Center Rake", "side_rake_in": "Side Rake",
    "dynamic_pressure_psf": "Dynamic Pressure", "drag_scrub_suspicion": "Drag/Scrub",
    "cfs_risk_score": "CFS Risk",
}

CHANNEL_UNITS: dict[str, str] = {
    "speed_mph": "mph", "speed_rate_mph_1000ft": "mph/1000ft",
    "rpm": "rpm", "throttle_pct": "%", "brake_pct": "%",
    "steering_deg": "deg", "cfs_ride_height_in": "in", "center_rake_fs_in": "in",
    "side_rake_in": "in", "dynamic_pressure_psf": "psf",
    "drag_scrub_suspicion": "index", "cfs_risk_score": "score",
}


def build_lap_grid(start_pct: float = 0.0, end_pct: float = 100.0, step_pct: float = 0.1) -> list[float]:
    grid: list[float] = []
    pct = start_pct
    while pct <= end_pct + 1e-9:
        grid.append(round(pct, 2))
        pct += step_pct
    return grid


def _interp(x: float, xs: list[float], ys: list[float]) -> float | None:
    """Linear interpolation at x given sorted xs and corresponding ys."""
    if not xs or len(xs) != len(ys):
        return None
    xs_list = list(xs)
    if x <= xs_list[0]:
        return ys[0]
    if x >= xs_list[-1]:
        return ys[-1]
    for i in range(len(xs_list) - 1):
        if xs_list[i] <= x <= xs_list[i + 1]:
            t = (x - xs_list[i]) / (xs_list[i + 1] - xs_list[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return None


def _split_monotonic_segments(
    xs: list[float], ys: list[float],
) -> list[tuple[list[float], list[float]]]:
    """Split (xs, ys) into monotonic segments at wraparound boundaries.

    A wraparound is detected when x drops by more than
    LAP_WRAP_DROP_THRESHOLD_PCT (e.g. 99.9 -> 0.1 at start/finish).
    Returns list of (segment_x, segment_y) tuples, each monotonic.
    """
    if not xs:
        return []
    segments: list[tuple[list[float], list[float]]] = []
    seg_x: list[float] = [xs[0]]
    seg_y: list[float] = [ys[0]]
    for i in range(1, len(xs)):
        if xs[i] < xs[i - 1] + LAP_WRAP_DROP_THRESHOLD_PCT:
            segments.append((seg_x, seg_y))
            seg_x = [xs[i]]
            seg_y = [ys[i]]
        else:
            seg_x.append(xs[i])
            seg_y.append(ys[i])
    if seg_x:
        segments.append((seg_x, seg_y))
    return segments


def interpolate_run_to_grid(
    rows: list[dict[str, Any]],
    channels: list[str],
    grid: list[float],
) -> dict[str, list[float | None]]:
    """Interpolate each channel's values onto a shared lap-percent grid.

    Handles start/finish wraparound by splitting data into monotonic
    segments whenever lap percent drops by more than LAP_WRAP_DROP_THRESHOLD_PCT.
    Each segment is interpolated independently; the segment overlapping the
    requested grid range is used.
    """
    xs_raw = [row.get("lap_dist_pct_100") for row in rows]
    result: dict[str, list[float | None]] = {}
    for ch in channels:
        ys_raw = [_safe_float(row.get(ch)) for row in rows]
        valid = [(x, y) for x, y in zip(xs_raw, ys_raw) if x is not None and y is not None]
        if len(valid) < 2:
            result[ch] = [None] * len(grid)
            continue

        vx = [p[0] for p in valid]
        vy = [p[1] for p in valid]
        segments = _split_monotonic_segments(vx, vy)

        if len(segments) == 1:
            # No wraparound — simple interpolation
            result[ch] = [_interp(g, vx, vy) for g in grid]
        else:
            # Multiple segments — pick the one that overlaps the grid range
            grid_start = min(grid)
            grid_end = max(grid)
            best_seg: tuple[list[float], list[float]] | None = None
            best_overlap = -1.0
            for sx, sy in segments:
                if not sx:
                    continue
                seg_start = min(sx)
                seg_end = max(sx)
                overlap = max(0.0, min(grid_end, seg_end) - max(grid_start, seg_start))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_seg = (sx, sy)
            if best_seg and best_overlap > 0:
                sx, sy = best_seg
                result[ch] = [_interp(g, sx, sy) for g in grid]
            else:
                result[ch] = [None] * len(grid)
    return result


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
        return None if (f != f or f == float("inf") or f == float("-inf")) else f
    except (TypeError, ValueError):
        return None


def _channel_delta(
    ch: str, bl_data: dict[str, list[float | None]], t_data: dict[str, list[float | None]]
) -> ComparedChannelDelta:
    bl = [v for v in (bl_data.get(ch) or []) if v is not None]
    t = [v for v in (t_data.get(ch) or []) if v is not None]
    bl_avg = sum(bl) / len(bl) if bl else None
    t_avg = sum(t) / len(t) if t else None
    return ComparedChannelDelta(
        channel=ch,
        label=CHANNEL_LABELS.get(ch, ch),
        unit=CHANNEL_UNITS.get(ch, ""),
        baseline_avg=bl_avg,
        test_avg=t_avg,
        delta=(t_avg - bl_avg) if bl_avg is not None and t_avg is not None else None,
        baseline_min=min(bl, default=None),
        test_min=min(t, default=None),
        baseline_max=max(bl, default=None),
        test_max=max(t, default=None),
    )


def compare_target_zone(  # sourcery skip
    baseline_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    start_pct: float = 55.0,
    end_pct: float = 70.0,
    channels: list[str] | None = None,
) -> TargetZoneComparison:
    selected = channels or COMPARE_CHANNELS
    grid = build_lap_grid(start_pct, end_pct, 0.1)
    bl_grid = interpolate_run_to_grid(baseline_rows, selected, grid)
    t_grid = interpolate_run_to_grid(test_rows, selected, grid)
    deltas = [_channel_delta(ch, bl_grid, t_grid) for ch in selected]

    speed_delta = next((d for d in deltas if d.channel == "speed_mph"), None)
    cfs_delta = next((d for d in deltas if d.channel == "cfs_ride_height_in"), None)

    if speed_delta and speed_delta.delta is not None:
        sd = speed_delta.delta
        if sd > 0.05:
            speed_label = "gained"
        elif sd < -0.05:
            speed_label = "lost"
        else:
            speed_label = "unchanged"
    else:
        speed_label = "unavailable"

    if cfs_delta and cfs_delta.delta is not None:
        cd = cfs_delta.delta
        if cd > 0.001:
            risk_label = "improved"
        elif cd < -0.001:
            risk_label = "worsened"
        else:
            risk_label = "unchanged"
    else:
        risk_label = "unavailable"

    return TargetZoneComparison(
        start_pct=start_pct,
        end_pct=end_pct,
        channel_deltas=deltas,
        speed_gain_or_loss_label=speed_label,
        platform_risk_delta_label=risk_label,
    )
