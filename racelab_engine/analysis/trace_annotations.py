from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AnnotationKind = Literal[
    "SPEED_GAIN",
    "SPEED_LOSS",
    "CFS_COMPRESSION",
    "DRAG_SCRUB_SPIKE",
    "STEERING_CORRECTION",
    "RPM_FLATTENING",
    "THROTTLE_LIFT",
]


@dataclass(frozen=True)
class TraceAnnotation:
    kind: AnnotationKind
    label: str
    symbol: str
    lap_pct: float
    lap_dist_ft: float | None
    value: float | None
    unit: str | None
    severity: str  # "info" | "watch" | "high" | "critical"
    evidence: str
    channel: str | None = None


@dataclass(frozen=True)
class AnnotationResult:
    annotations: list[TraceAnnotation] = field(default_factory=list)
    summary: str | None = None


def _find_extreme(
    values: list[float | None],
    xs_pct: list[float],
    xs_ft: list[float | None],
    kind: AnnotationKind,
    label: str,
    symbol: str,
    unit: str | None,
    find_max: bool,
    threshold: float = 0.0,
) -> TraceAnnotation | None:
    """Find the single most extreme value in a delta trace and annotate it."""
    candidates = [(i, v) for i, v in enumerate(values) if v is not None and abs(v) >= threshold]
    if not candidates:
        return None

    if find_max:
        idx, val = max(candidates, key=lambda item: item[1])
    else:
        idx, val = min(candidates, key=lambda item: item[1])

    pct = xs_pct[idx] if idx < len(xs_pct) else 0.0
    ft = xs_ft[idx] if idx < len(xs_ft) else None

    abs_val = abs(val)
    severity: str = "critical" if abs_val > 1.0 else "high" if abs_val > 0.5 else "watch" if abs_val > 0.1 else "info"

    return TraceAnnotation(
        kind=kind,
        label=label,
        symbol=symbol,
        lap_pct=pct,
        lap_dist_ft=ft,
        value=val,
        unit=unit,
        severity=severity,
        evidence=f"{label}: {val:+.3f}{unit or ''} at {pct:.1f}%",
        channel=None,
    )


def annotate_delta_traces(
    delta_channels: dict[str, dict[str, Any]],
    lap_pct_values: list[float],
    x_values: list[float | None],
) -> AnnotationResult:
    """Auto-annotate key events on delta traces."""
    annotations: list[TraceAnnotation] = []

    # Speed gain/loss
    speed = delta_channels.get("speed_mph", {})
    if speed_deltas := speed.get("delta_values", []):
        if gain := _find_extreme(speed_deltas, lap_pct_values, x_values, "SPEED_GAIN", "Biggest Speed Gain", "▲", " mph", True, 0.05):
            annotations.append(gain)
        if loss := _find_extreme(speed_deltas, lap_pct_values, x_values, "SPEED_LOSS", "Biggest Speed Loss", "▼", " mph", False, -0.05):
            annotations.append(loss)

    # CFS compression (negative delta = worse)
    cfs = delta_channels.get("cfs_ride_height_in", {})
    if cfs_deltas := cfs.get("delta_values", []):
        if cfs_worst := _find_extreme(cfs_deltas, lap_pct_values, x_values, "CFS_COMPRESSION", "Worst CFS Compression", "⬇", " in", False, -0.001):
            annotations.append(cfs_worst)

    # Drag/scrub spike (positive delta = worse)
    drag = delta_channels.get("drag_scrub_suspicion", {})
    if drag_deltas := drag.get("delta_values", []):
        if drag_spike := _find_extreme(drag_deltas, lap_pct_values, x_values, "DRAG_SCRUB_SPIKE", "Drag/Scrub Spike", "⚠", " index", True, 0.05):
            annotations.append(drag_spike)

    # Steering correction
    steering = delta_channels.get("abs_steering_deg", {}) or delta_channels.get("steering_deg", {})
    if steer_deltas := steering.get("delta_values", []):
        if steer_max := _find_extreme(steer_deltas, lap_pct_values, x_values, "STEERING_CORRECTION", "Largest Steering Correction", "↔", " deg", True, 0.5):
            annotations.append(steer_max)

    # RPM flattening (negative delta = losing RPM)
    rpm = delta_channels.get("rpm", {})
    if rpm_deltas := rpm.get("delta_values", []):
        if rpm_loss := _find_extreme(rpm_deltas, lap_pct_values, x_values, "RPM_FLATTENING", "RPM Flattening", "◊", " rpm", False, -50):
            annotations.append(rpm_loss)

    # Throttle lift (negative delta = lifting earlier)
    throttle = delta_channels.get("throttle_pct", {})
    if throttle_deltas := throttle.get("delta_values", []):
        if lift := _find_extreme(throttle_deltas, lap_pct_values, x_values, "THROTTLE_LIFT", "Throttle Lift", "○", " %", False, -2):
            annotations.append(lift)

    # Build summary
    if annotations:
        summary = f"{len(annotations)} events detected: " + ", ".join(
            f"{a.symbol} {a.label}" for a in annotations[:5]
        )
    else:
        summary = "No significant delta events detected."

    return AnnotationResult(annotations=annotations, summary=summary)
