from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows


def _ensure_normalized(table: Any) -> list[dict[str, Any]]:
    if isinstance(table, list) and table and isinstance(table[0], dict):
        if "speed_mph" in table[0]:
            return table
    return normalize_telemetry_rows(table)


from racelab_engine.analysis.constants import (
    SPLITTER_SCRAPE_MM,
    SPLITTER_CRITICAL_MM,
    SPLITTER_HIGH_MM,
    SPLITTER_WATCH_MM,
    PLATFORM_VALID_MIN_SPEED_MPH,
    PLATFORM_VALID_THROTTLE_PCT,
    LOW_BRAKE_PCT,
)
from racelab_engine.models.event import TelemetryEvent


def classify_splitter_height_mm(splitter_height_mm: float | None) -> str:
    if splitter_height_mm is None:
        return "unavailable"
    if splitter_height_mm <= SPLITTER_SCRAPE_MM:
        return "scrape"
    if splitter_height_mm <= SPLITTER_CRITICAL_MM:
        return "critical"
    if splitter_height_mm <= SPLITTER_HIGH_MM:
        return "high"
    return "watch" if splitter_height_mm <= SPLITTER_WATCH_MM else "safe"


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number * 100.0 if 0.0 <= number <= 1.5 else number


def detect_platform_events(table: Any, run_id: str = "unassigned") -> list[TelemetryEvent]:
    rows = [row for row in _ensure_normalized(table) if row.get("cfsr_height_mm") is not None]
    if not rows:
        return []

    grouped: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        lap_number = int(row.get("lap") or row.get("lap_number") or 0) or None
        grouped[lap_number].append(row)

    events: list[TelemetryEvent] = []
    for lap_number, lap_rows in sorted(grouped.items(), key=lambda item: item[0] or -1):
        min_row = min(lap_rows, key=lambda row: float(row["cfsr_height_mm"]))
        splitter = float(min_row["cfsr_height_mm"])
        severity = classify_splitter_height_mm(splitter)
        speed_mph = float(min_row.get("speed_mph") or 0.0)
        throttle_pct = float(min_row.get("throttle_pct") or 0.0)
        brake_pct = float(min_row.get("brake_pct") or 0.0)
        pct_values = [_pct(row.get("lap_dist_pct")) for row in lap_rows]
        pct_values_list = [value for value in pct_values if value is not None]
        pct_values_clean: list[float] = cast(list[float], pct_values_list)
        is_complete_lap = bool(pct_values_clean) and min(pct_values_clean) <= 2.0 and max(pct_values_clean) >= 98.0
        valid_for_tuning = (
            is_complete_lap
            and splitter >= SPLITTER_SCRAPE_MM
            and speed_mph >= PLATFORM_VALID_MIN_SPEED_MPH
            and throttle_pct >= PLATFORM_VALID_THROTTLE_PCT
            and brake_pct <= LOW_BRAKE_PCT
        )

        events.append(
            TelemetryEvent(
                event_id=f"{run_id}:platform:min-splitter:{lap_number or 'unknown'}",
                run_id=run_id,
                lap_number=lap_number,
                event_type="PLATFORM_SCRAPE" if splitter <= 0 else "PLATFORM_LOW",
                event_subtype=severity,
                lap_pct_start=_pct(min_row.get("lap_dist_pct")),
                lap_pct_end=_pct(min_row.get("lap_dist_pct")),
                lap_pct_peak=_pct(min_row.get("lap_dist_pct")),
                distance_m_peak=float(min_row["lap_dist_m"]) if min_row.get("lap_dist_m") is not None else None,
                zone_name=min_row.get("zone_name"),
                severity=severity,
                confidence_score=0.75 if valid_for_tuning else 0.35,
                valid_for_tuning=valid_for_tuning,
                primary_metric_name="cfsr_height_mm",
                primary_metric_value=splitter,
                evidence_json={
                    "speed_mph": speed_mph,
                    "throttle_pct": throttle_pct,
                    "brake_pct": brake_pct,
                    "splitter_height_mm": splitter,
                    "is_complete_lap": is_complete_lap,
                    "validity_rule": (
                        "complete high-speed full-throttle low-brake event"
                        if valid_for_tuning
                        else "not valid for tuning because context is incomplete, slowdown, braking, low-speed, or not full-throttle"
                    ),
                },
                related_setup_keys=["front_ride_height", "front_springs", "packers", "steering_offset"],
                recommended_actions=["Compare speed and splitter margin in the same lap-distance zone on the next controlled run."],
            )
        )
    return events
