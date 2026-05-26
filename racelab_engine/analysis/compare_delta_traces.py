from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from racelab_engine.analysis.comparison import build_lap_grid, interpolate_run_to_grid, _safe_float
from racelab_engine.services.import_service import FORCE_PROXY_CHANNELS


# ── models ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class DeltaTraceChannel:
    channel: str
    label: str
    unit: str
    baseline_values: list[float | None]
    test_values: list[float | None]
    delta_values: list[float | None]
    baseline_min: float | None = None
    baseline_max: float | None = None
    test_min: float | None = None
    test_max: float | None = None
    delta_min: float | None = None
    delta_max: float | None = None
    delta_mean: float | None = None
    is_proxy: bool = False
    unavailable_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "label": self.label,
            "unit": self.unit,
            "baseline_values": self.baseline_values,
            "test_values": self.test_values,
            "delta_values": self.delta_values,
            "baseline_min": self.baseline_min,
            "baseline_max": self.baseline_max,
            "test_min": self.test_min,
            "test_max": self.test_max,
            "delta_min": self.delta_min,
            "delta_max": self.delta_max,
            "delta_mean": self.delta_mean,
            "is_proxy": self.is_proxy,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class DeltaTraceResponse:
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None
    test_lap: int | None
    x_axis: str
    x_unit: str
    x_values: list[float | None]
    lap_pct_values: list[float]
    target_zone_start_pct: float
    target_zone_end_pct: float
    channels: dict[str, DeltaTraceChannel] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing_channels: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline_run_id": self.baseline_run_id,
            "test_run_id": self.test_run_id,
            "baseline_lap": self.baseline_lap,
            "test_lap": self.test_lap,
            "x_axis": self.x_axis,
            "x_unit": self.x_unit,
            "x_values": self.x_values,
            "lap_pct_values": self.lap_pct_values,
            "target_zone_start_pct": self.target_zone_start_pct,
            "target_zone_end_pct": self.target_zone_end_pct,
            "channels": {k: v.as_dict() for k, v in self.channels.items()},
            "warnings": self.warnings,
            "missing_channels": self.missing_channels,
        }


# ── channel registry ─────────────────────────────────────────────

DELTA_TRACE_CHANNEL_META: dict[str, dict[str, Any]] = {
    "speed_mph": {"label": "Speed", "unit": "mph"},
    "cfs_ride_height_in": {"label": "CFS Ride Height", "unit": "in"},
    "center_rake_fs_in": {"label": "Center Rake FS", "unit": "in"},
    "side_rake_in": {"label": "Side Rake", "unit": "in"},
    "drag_scrub_suspicion": {"label": "Drag/Scrub Suspicion", "unit": "index"},
    "abs_steering_deg": {"label": "Steering", "unit": "deg"},
    "steering_deg": {"label": "Steering", "unit": "deg"},
    "rpm": {"label": "RPM", "unit": "rpm"},
    "dynamic_pressure_psf": {"label": "Dynamic Pressure", "unit": "psf"},
    "throttle_pct": {"label": "Throttle", "unit": "%"},
    "brake_pct": {"label": "Brake", "unit": "%"},
    "speed_rate_mph_1000ft": {"label": "Speed Rate/1000ft", "unit": "mph/1000ft"},
    "lf_ride_height_in": {"label": "LF Ride Height", "unit": "in"},
    "rf_ride_height_in": {"label": "RF Ride Height", "unit": "in"},
    "lr_ride_height_in": {"label": "LR Ride Height", "unit": "in"},
    "rr_ride_height_in": {"label": "RR Ride Height", "unit": "in"},
    "cfs_risk_score": {"label": "CFS Risk Score", "unit": "score"},
    "front_avg_rh_in": {"label": "Front Avg RH", "unit": "in"},
    "rear_avg_rh_in": {"label": "Rear Avg RH", "unit": "in"},
}

DEFAULT_DELTA_CHANNELS = [
    "speed_mph",
    "cfs_ride_height_in",
    "center_rake_fs_in",
    "side_rake_in",
    "drag_scrub_suspicion",
    "abs_steering_deg",
    "rpm",
    "dynamic_pressure_psf",
]


# ── analysis ─────────────────────────────────────────────────────


def _derive_x_values(
    bl_rows: list[dict[str, Any]],
    t_rows: list[dict[str, Any]],
    grid: list[float],
    x_axis: str,
) -> list[float | None]:
    """Derive x-axis values from baseline lap_dist_ft if available, else approximate from lap_pct."""
    if x_axis == "lap_dist_ft":
        bl_grid = interpolate_run_to_grid(bl_rows, ["lap_dist_ft"], grid)
        x_vals = bl_grid.get("lap_dist_ft", [None] * len(grid))
        # If all None, fall back to lap_pct
        if any(v is not None for v in x_vals):
            return x_vals
    # Fallback: use lap_pct values as x
    return list(grid)


def compute_delta_traces(
    baseline_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    *,
    channels: list[str] | None = None,
    x_axis: str = "lap_dist_ft",
    start_pct: float = 0.0,
    end_pct: float = 100.0,
    step_pct: float = 0.1,
    target_zone_start_pct: float = 55.0,
    target_zone_end_pct: float = 70.0,
) -> DeltaTraceResponse:
    selected = channels or DEFAULT_DELTA_CHANNELS
    grid = build_lap_grid(start_pct, end_pct, step_pct)

    # Interpolate both runs onto shared grid
    bl_grid = interpolate_run_to_grid(baseline_rows, selected, grid)
    t_grid = interpolate_run_to_grid(test_rows, selected, grid)

    # Derive x values
    x_values = _derive_x_values(baseline_rows, test_rows, grid, x_axis)
    x_unit = "ft" if x_axis == "lap_dist_ft" else "%"

    # Build channel payloads
    channel_map: dict[str, DeltaTraceChannel] = {}
    missing: list[str] = []
    warnings: list[str] = []

    for ch in selected:
        meta = DELTA_TRACE_CHANNEL_META.get(ch, {"label": ch, "unit": ""})
        bl_vals = bl_grid.get(ch, [None] * len(grid))
        t_vals = t_grid.get(ch, [None] * len(grid))

        # Check if channel is entirely unavailable
        bl_clean = [v for v in bl_vals if v is not None]
        t_clean = [v for v in t_vals if v is not None]

        if not bl_clean and not t_clean:
            missing.append(ch)
            channel_map[ch] = DeltaTraceChannel(
                channel=ch,
                label=meta["label"],
                unit=meta["unit"],
                baseline_values=[None] * len(grid),
                test_values=[None] * len(grid),
                delta_values=[None] * len(grid),
                is_proxy=ch in FORCE_PROXY_CHANNELS,
                unavailable_reason="Channel not available in either run.",
            )
            continue

        if not bl_clean:
            missing.append(ch)
            channel_map[ch] = DeltaTraceChannel(
                channel=ch,
                label=meta["label"],
                unit=meta["unit"],
                baseline_values=[None] * len(grid),
                test_values=t_vals,
                delta_values=[None] * len(grid),
                is_proxy=ch in FORCE_PROXY_CHANNELS,
                unavailable_reason="Channel not available in baseline run.",
            )
            continue

        if not t_clean:
            missing.append(ch)
            channel_map[ch] = DeltaTraceChannel(
                channel=ch,
                label=meta["label"],
                unit=meta["unit"],
                baseline_values=bl_vals,
                test_values=[None] * len(grid),
                delta_values=[None] * len(grid),
                is_proxy=ch in FORCE_PROXY_CHANNELS,
                unavailable_reason="Channel not available in test run.",
            )
            continue

        # Compute delta = test - baseline
        delta_vals: list[float | None] = []
        for b, t_val in zip(bl_vals, t_vals):
            if b is not None and t_val is not None:
                delta_vals.append(t_val - b)
            else:
                delta_vals.append(None)

        delta_clean = [d for d in delta_vals if d is not None]

        channel_map[ch] = DeltaTraceChannel(
            channel=ch,
            label=meta["label"],
            unit=meta["unit"],
            baseline_values=bl_vals,
            test_values=t_vals,
            delta_values=delta_vals,
            baseline_min=min(bl_clean, default=None),
            baseline_max=max(bl_clean, default=None),
            test_min=min(t_clean, default=None),
            test_max=max(t_clean, default=None),
            delta_min=min(delta_clean, default=None) if delta_clean else None,
            delta_max=max(delta_clean, default=None) if delta_clean else None,
            delta_mean=sum(delta_clean) / len(delta_clean) if delta_clean else None,
            is_proxy=ch in FORCE_PROXY_CHANNELS,
        )

    if missing:
        warnings.append(f"Channels not available: {', '.join(missing)}")

    return DeltaTraceResponse(
        baseline_run_id="",
        test_run_id="",
        baseline_lap=None,
        test_lap=None,
        x_axis=x_axis,
        x_unit=x_unit,
        x_values=x_values,
        lap_pct_values=grid,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
        channels=channel_map,
        warnings=warnings,
        missing_channels=missing,
    )
