from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from racelab_engine.services.import_service import FORCE_PROXY_WARNING

EventType = Literal[
    "MIN_SPLITTER",
    "WORST_SPEED_LOSS",
    "WORST_DRAG_SCRUB",
    "HIGHEST_RAKE",
    "HIGHEST_PLATFORM_COMPRESSION",
    "HIGHEST_SHOCK_ACTIVITY",
    "MAX_DYNAMIC_PRESSURE",
]

Severity = Literal["info", "watch", "high", "critical"]
Confidence = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class PlatformEvent:
    event_id: str
    event_type: EventType
    title: str
    severity: Severity
    confidence: Confidence

    lap: int | None
    sample_index: int
    lap_dist_ft: float | None
    lap_pct: float | None
    track_x_ft: float | None = None
    track_y_ft: float | None = None

    primary_value: float | None = None
    primary_unit: str | None = None

    channels_used: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    recommended_action: str | None = None

    is_proxy_based: bool = False
    proxy_warning: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "lap": self.lap,
            "sample_index": self.sample_index,
            "lap_dist_ft": self.lap_dist_ft,
            "lap_pct": self.lap_pct,
            "track_x_ft": self.track_x_ft,
            "track_y_ft": self.track_y_ft,
            "primary_value": self.primary_value,
            "primary_unit": self.primary_unit,
            "channels_used": self.channels_used,
            "evidence": self.evidence,
            "recommended_action": self.recommended_action,
            "is_proxy_based": self.is_proxy_based,
            "proxy_warning": self.proxy_warning,
            "metadata": self.metadata,
        }


# ── shared helpers ──────────────────────────────────────────────


def _sample_value(row: dict[str, Any], name: str) -> Any:
    value = row.get(name)
    try:
        if value != value:  # NaN check
            return None
    except Exception:
        return None
    return value


def _event_location(row: dict[str, Any], sample_index: int) -> dict[str, Any]:
    return {
        "lap": int(row["lap"]) if "lap" in row and row.get("lap") == row.get("lap") else None,
        "sample_index": sample_index,
        "lap_dist_ft": _sample_value(row, "lap_dist_ft"),
        "lap_pct": _sample_value(row, "lap_dist_pct_100"),
        "track_x_ft": _sample_value(row, "track_x_ft"),
        "track_y_ft": _sample_value(row, "track_y_ft"),
    }


def _make_event_id(event_type: str, row: dict[str, Any], sample_index: int) -> str:
    lap = int(row["lap"]) if "lap" in row and row.get("lap") == row.get("lap") else "x"
    return f"{event_type.lower()}_lap{lap}_sample{sample_index}"


def _cfs_severity(cfs_in: float | None) -> Severity:
    if cfs_in is None:
        return "info"
    if cfs_in <= 0:
        return "critical"
    if cfs_in <= 0.118:
        return "critical"
    if cfs_in <= 0.236:
        return "high"
    if cfs_in <= 0.394:
        return "watch"
    return "info"


# ── detectors ────────────────────────────────────────────────────


def detect_min_splitter(rows: list[dict[str, Any]]) -> PlatformEvent | None:
    candidates = [
        (i, row) for i, row in enumerate(rows)
        if _sample_value(row, "cfs_ride_height_in") is not None
    ]
    if not candidates:
        return None

    idx, row = min(candidates, key=lambda item: float(item[1]["cfs_ride_height_in"]))
    cfs_in = float(row["cfs_ride_height_in"])
    cfs_mm = _sample_value(row, "cfs_ride_height_mm")
    loc = _event_location(row, idx)
    speed = _sample_value(row, "speed_mph")
    throttle = _sample_value(row, "throttle_pct")
    brake = _sample_value(row, "brake_pct")

    evidence = []
    if speed is not None:
        evidence.append(f"Speed: {speed:.1f} mph")
    if throttle is not None:
        evidence.append(f"Throttle: {throttle:.1f}%")
    if brake is not None:
        evidence.append(f"Brake: {brake:.1f}%")
    if cfs_mm is not None:
        evidence.append(f"CFS splitter height: {cfs_mm:.2f} mm ({cfs_in:.3f} in)")
    evidence.append(f"Location: {loc['lap_pct']:.1f}% lap" if loc["lap_pct"] is not None else "Location unknown")

    return PlatformEvent(
        event_id=_make_event_id("min_splitter", row, idx),
        event_type="MIN_SPLITTER",
        title="Minimum Splitter Height",
        severity=_cfs_severity(cfs_in),
        confidence="high" if speed is not None and throttle is not None and brake is not None else "medium",
        lap=loc["lap"],
        sample_index=idx,
        lap_dist_ft=loc["lap_dist_ft"],
        lap_pct=loc["lap_pct"],
        track_x_ft=loc["track_x_ft"],
        track_y_ft=loc["track_y_ft"],
        primary_value=cfs_in,
        primary_unit="in",
        channels_used=["cfs_ride_height_in", "cfs_ride_height_mm", "speed_mph", "throttle_pct", "brake_pct"],
        evidence=evidence,
        recommended_action="Compare target-zone speed and splitter margin before changing multiple setup areas.",
    )


def detect_worst_speed_loss(rows: list[dict[str, Any]]) -> PlatformEvent | None:
    candidates = [
        (i, row) for i, row in enumerate(rows)
        if _sample_value(row, "throttle_pct") is not None
        and float(row["throttle_pct"]) >= 98
        and _sample_value(row, "brake_pct") is not None
        and float(row["brake_pct"]) <= 1
        and _sample_value(row, "speed_mph") is not None
        and float(row["speed_mph"]) >= 150
        and (
            _sample_value(row, "speed_rate_mph_1000ft") is not None
            or _sample_value(row, "speed_rate_mph_s") is not None
        )
    ]
    if not candidates:
        return None

    # Use speed_rate_mph_1000ft preferentially, fall back to speed_rate_mph_s
    def _rate_key(item: tuple[int, dict]) -> float:
        _i, r = item
        rate = _sample_value(r, "speed_rate_mph_1000ft")
        if rate is None:
            rate = _sample_value(r, "speed_rate_mph_s")
        return float(rate) if rate is not None else 0.0

    idx, row = min(candidates, key=_rate_key)
    rate_1000ft = _sample_value(row, "speed_rate_mph_1000ft")
    rate_s = _sample_value(row, "speed_rate_mph_s")
    loc = _event_location(row, idx)
    speed = _sample_value(row, "speed_mph")

    evidence = ["Speed was falling while throttle was high and brake was low."]
    if rate_1000ft is not None:
        evidence.append(f"Speed loss rate: {rate_1000ft:.2f} mph/1000ft")
    if rate_s is not None:
        evidence.append(f"Speed loss rate: {rate_s:.3f} mph/s")
    if speed is not None:
        evidence.append(f"Speed: {speed:.1f} mph")
    if loc["lap_pct"] is not None:
        evidence.append(f"Location: {loc['lap_pct']:.1f}% lap")

    worst_rate = abs(rate_1000ft if rate_1000ft is not None else rate_s or 0)
    severity: Severity = "critical" if worst_rate > 3 else ("high" if worst_rate > 1.5 else "watch")

    return PlatformEvent(
        event_id=_make_event_id("worst_speed_loss", row, idx),
        event_type="WORST_SPEED_LOSS",
        title="Worst Speed Loss",
        severity=severity,
        confidence="high" if rate_1000ft is not None else "medium",
        lap=loc["lap"],
        sample_index=idx,
        lap_dist_ft=loc["lap_dist_ft"],
        lap_pct=loc["lap_pct"],
        track_x_ft=loc["track_x_ft"],
        track_y_ft=loc["track_y_ft"],
        primary_value=rate_1000ft or rate_s,
        primary_unit="mph/1000ft" if rate_1000ft is not None else "mph/s",
        channels_used=["speed_rate_mph_1000ft", "speed_rate_mph_s", "speed_mph", "throttle_pct", "brake_pct"],
        evidence=evidence,
        recommended_action="Investigate platform, scrub, gearing, wind, or draft behavior. Compare speed at same track position on next run.",
    )


def detect_worst_drag_scrub(rows: list[dict[str, Any]]) -> PlatformEvent | None:
    candidates = [
        (i, row) for i, row in enumerate(rows)
        if _sample_value(row, "drag_scrub_suspicion") is not None
        and float(row["drag_scrub_suspicion"]) > 0
    ]
    if not candidates:
        return None

    idx, row = max(candidates, key=lambda item: float(item[1]["drag_scrub_suspicion"]))
    score = float(row["drag_scrub_suspicion"])
    loc = _event_location(row, idx)
    resistance = _sample_value(row, "full_throttle_resistance_index")
    steering = _sample_value(row, "abs_steering_deg")
    lat_accel = _sample_value(row, "abs_lat_accel")
    cfs_in = _sample_value(row, "cfs_ride_height_in")

    evidence = ["Drag/scrub suspicion peaked here."]
    if resistance is not None:
        evidence.append(f"Full-throttle resistance index: {resistance:.2f}")
    if steering is not None:
        evidence.append(f"Steering angle: {steering:.1f} deg")
    if lat_accel is not None:
        evidence.append(f"Lateral acceleration: {lat_accel:.2f} m/s²")
    if cfs_in is not None:
        evidence.append(f"CFS height: {cfs_in:.3f} in")
    if loc["lap_pct"] is not None:
        evidence.append(f"Location: {loc['lap_pct']:.1f}% lap")

    severity: Severity = "critical" if score > 0.7 else ("high" if score > 0.4 else "watch")

    return PlatformEvent(
        event_id=_make_event_id("worst_drag_scrub", row, idx),
        event_type="WORST_DRAG_SCRUB",
        title="Worst Drag / Scrub Suspicion",
        severity=severity,
        confidence="medium",
        lap=loc["lap"],
        sample_index=idx,
        lap_dist_ft=loc["lap_dist_ft"],
        lap_pct=loc["lap_pct"],
        track_x_ft=loc["track_x_ft"],
        track_y_ft=loc["track_y_ft"],
        primary_value=score,
        primary_unit="index",
        channels_used=["drag_scrub_suspicion", "full_throttle_resistance_index", "abs_steering_deg", "abs_lat_accel", "cfs_ride_height_in"],
        evidence=evidence,
        recommended_action="Compare one controlled platform or line change and watch target-zone speed, steering, and CFS height.",
        is_proxy_based=True,
        proxy_warning=FORCE_PROXY_WARNING,
    )


def detect_highest_rake(rows: list[dict[str, Any]]) -> PlatformEvent | None:
    candidates = [
        (i, row) for i, row in enumerate(rows)
        if _sample_value(row, "center_rake_fs_in") is not None
    ]
    if not candidates:
        return None

    idx, row = max(candidates, key=lambda item: float(item[1]["center_rake_fs_in"]))
    rake = float(row["center_rake_fs_in"])
    loc = _event_location(row, idx)
    rear_avg = _sample_value(row, "rear_avg_rh_in")
    cfs_in = _sample_value(row, "cfs_ride_height_in")
    side_rake = _sample_value(row, "side_rake_in")

    evidence = ["Rear average ride height was much higher than center front splitter height."]
    if rear_avg is not None and cfs_in is not None:
        evidence.append(f"Rear avg: {rear_avg:.2f} in, CFS: {cfs_in:.3f} in → rake: {rake:.2f} in")
    if side_rake is not None:
        evidence.append(f"Side rake: {side_rake:.3f} in")
    if loc["lap_pct"] is not None:
        evidence.append(f"Location: {loc['lap_pct']:.1f}% lap")

    severity: Severity = "watch"

    return PlatformEvent(
        event_id=_make_event_id("highest_rake", row, idx),
        event_type="HIGHEST_RAKE",
        title="Highest Center Rake",
        severity=severity,
        confidence="medium",
        lap=loc["lap"],
        sample_index=idx,
        lap_dist_ft=loc["lap_dist_ft"],
        lap_pct=loc["lap_pct"],
        track_x_ft=loc["track_x_ft"],
        track_y_ft=loc["track_y_ft"],
        primary_value=rake,
        primary_unit="in",
        channels_used=["center_rake_fs_in", "rear_avg_rh_in", "cfs_ride_height_in", "side_rake_in"],
        evidence=evidence,
        recommended_action="Review whether this rake state coincides with speed loss, low CFS height, or platform instability.",
    )


def detect_highest_platform_compression(rows: list[dict[str, Any]]) -> PlatformEvent | None:
    candidates = [
        (i, row) for i, row in enumerate(rows)
        if _sample_value(row, "platform_compression_index") is not None
        and float(row["platform_compression_index"]) > 0
    ]
    if not candidates:
        return None

    idx, row = max(candidates, key=lambda item: float(item[1]["platform_compression_index"]))
    score = float(row["platform_compression_index"])
    loc = _event_location(row, idx)
    cfs_in = _sample_value(row, "cfs_ride_height_in")
    cfs_risk = _sample_value(row, "cfs_risk_score")
    drag_susp = _sample_value(row, "drag_scrub_suspicion")

    evidence = ["Platform compression index peaked here."]
    if cfs_in is not None:
        evidence.append(f"CFS height: {cfs_in:.3f} in")
    if cfs_risk is not None:
        evidence.append(f"CFS risk score: {cfs_risk:.2f}")
    if drag_susp is not None:
        evidence.append(f"Drag/scrub suspicion: {drag_susp:.2f}")
    if loc["lap_pct"] is not None:
        evidence.append(f"Location: {loc['lap_pct']:.1f}% lap")

    severity: Severity = "critical" if score > 0.7 else ("high" if score > 0.4 else "watch")

    return PlatformEvent(
        event_id=_make_event_id("highest_platform_compression", row, idx),
        event_type="HIGHEST_PLATFORM_COMPRESSION",
        title="Highest Platform Compression",
        severity=severity,
        confidence="medium",
        lap=loc["lap"],
        sample_index=idx,
        lap_dist_ft=loc["lap_dist_ft"],
        lap_pct=loc["lap_pct"],
        track_x_ft=loc["track_x_ft"],
        track_y_ft=loc["track_y_ft"],
        primary_value=score,
        primary_unit="index",
        channels_used=["platform_compression_index", "cfs_risk_score", "drag_scrub_suspicion", "cfs_ride_height_in"],
        evidence=evidence,
        recommended_action="Check CFS height, shock activity, and speed rate at the same track position.",
        is_proxy_based=True,
        proxy_warning=FORCE_PROXY_WARNING,
    )


def detect_highest_shock_activity(rows: list[dict[str, Any]]) -> PlatformEvent | None:
    candidates = [
        (i, row) for i, row in enumerate(rows)
        if _sample_value(row, "shock_activity_index") is not None
        and float(row["shock_activity_index"]) > 0
    ]
    if not candidates:
        return None

    idx, row = max(candidates, key=lambda item: float(item[1]["shock_activity_index"]))
    score = float(row["shock_activity_index"])
    loc = _event_location(row, idx)
    lf_rms = _sample_value(row, "lf_shock_velocity_rms")
    rf_rms = _sample_value(row, "rf_shock_velocity_rms")
    lr_rms = _sample_value(row, "lr_shock_velocity_rms")
    rr_rms = _sample_value(row, "rr_shock_velocity_rms")

    evidence = ["Shock activity peaked here, suggesting platform motion or disturbance."]
    if lf_rms is not None:
        evidence.append(f"LF shock RMS: {lf_rms:.3f} in/s, RF: {rf_rms:.3f}" if rf_rms else f"LF shock RMS: {lf_rms:.3f} in/s")
    if lr_rms is not None:
        evidence.append(f"LR shock RMS: {lr_rms:.3f} in/s, RR: {rr_rms:.3f}" if rr_rms else f"LR shock RMS: {lr_rms:.3f} in/s")
    if loc["lap_pct"] is not None:
        evidence.append(f"Location: {loc['lap_pct']:.1f}% lap")

    severity: Severity = "critical" if score > 5 else ("high" if score > 2 else "watch")

    return PlatformEvent(
        event_id=_make_event_id("highest_shock_activity", row, idx),
        event_type="HIGHEST_SHOCK_ACTIVITY",
        title="Highest Shock Activity",
        severity=severity,
        confidence="medium",
        lap=loc["lap"],
        sample_index=idx,
        lap_dist_ft=loc["lap_dist_ft"],
        lap_pct=loc["lap_pct"],
        track_x_ft=loc["track_x_ft"],
        track_y_ft=loc["track_y_ft"],
        primary_value=score,
        primary_unit="index",
        channels_used=["shock_activity_index", "lf_shock_velocity_rms", "rf_shock_velocity_rms", "lr_shock_velocity_rms", "rr_shock_velocity_rms"],
        evidence=evidence,
        recommended_action="Inspect shock velocity traces and compare against CFS/rake stability.",
        is_proxy_based=True,
        proxy_warning=FORCE_PROXY_WARNING,
    )


def detect_max_dynamic_pressure(rows: list[dict[str, Any]]) -> PlatformEvent | None:
    candidates = [
        (i, row) for i, row in enumerate(rows)
        if _sample_value(row, "dynamic_pressure_psf") is not None
    ]
    if not candidates:
        return None

    idx, row = max(candidates, key=lambda item: float(item[1]["dynamic_pressure_psf"]))
    dp_psf = float(row["dynamic_pressure_psf"])
    loc = _event_location(row, idx)
    speed = _sample_value(row, "speed_mph")
    air_density = _sample_value(row, "air_density")
    cfs_in = _sample_value(row, "cfs_ride_height_in")

    evidence = ["Dynamic pressure peaked here due to speed and air density."]
    if speed is not None:
        evidence.append(f"Speed: {speed:.1f} mph")
    if air_density is not None:
        evidence.append(f"Air density: {air_density:.3f} kg/m³")
    if cfs_in is not None:
        evidence.append(f"CFS height: {cfs_in:.3f} in")
    if loc["lap_pct"] is not None:
        evidence.append(f"Location: {loc['lap_pct']:.1f}% lap")

    return PlatformEvent(
        event_id=_make_event_id("max_dynamic_pressure", row, idx),
        event_type="MAX_DYNAMIC_PRESSURE",
        title="Maximum Dynamic Pressure",
        severity="info",
        confidence="high",
        lap=loc["lap"],
        sample_index=idx,
        lap_dist_ft=loc["lap_dist_ft"],
        lap_pct=loc["lap_pct"],
        track_x_ft=loc["track_x_ft"],
        track_y_ft=loc["track_y_ft"],
        primary_value=dp_psf,
        primary_unit="psf",
        channels_used=["dynamic_pressure_psf", "speed_mph", "air_density", "cfs_ride_height_in"],
        evidence=evidence,
        recommended_action="Check whether maximum dynamic pressure correlates with CFS collapse or speed loss.",
    )


# ── entrypoint ───────────────────────────────────────────────────


def detect_platform_events(
    rows: list[dict[str, Any]],
    *,
    lap: int | None = None,
    event_types: list[str] | None = None,
) -> list[PlatformEvent]:
    """Detect structured platform diagnostic events from normalized telemetry rows."""

    working = rows
    if lap is not None:
        working = [row for row in working if row.get("lap") == lap]
    if not working:
        return []

    detectors = [
        detect_min_splitter,
        detect_worst_speed_loss,
        detect_worst_drag_scrub,
        detect_highest_rake,
        detect_highest_platform_compression,
        detect_highest_shock_activity,
        detect_max_dynamic_pressure,
    ]

    if event_types:
        type_set = set(event_types)
        detectors = [d for d in detectors if d.__name__.replace("detect_", "").upper() in type_set]

    events: list[PlatformEvent] = []
    for detector in detectors:
        event = detector(working)
        if event is not None:
            events.append(event)

    return events
