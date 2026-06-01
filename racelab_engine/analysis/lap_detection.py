from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, cast

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.models.lap import LapSummary


def _ensure_normalized(table: Any) -> list[dict[str, Any]]:
    if isinstance(table, list) and table and isinstance(table[0], dict):
        if "speed_mph" in table[0]:
            return table
    return normalize_telemetry_rows(table)


def _numbers(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is not None:
            values.append(float(value))
    return values


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number * 100.0 if 0.0 <= number <= 1.5 else number


def _lap_number(row: dict[str, Any]) -> int | None:
    value = row.get("lap")
    if value is None:
        value = row.get("lap_number")
    return int(value) if value is not None else None


def detect_laps(table: Any, run_id: str = "unassigned") -> list[LapSummary]:
    rows = _ensure_normalized(table)
    if not rows:
        return []

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        lap_number = _lap_number(row)
        if lap_number is not None:
            grouped[lap_number].append(row)

    laps: list[LapSummary] = []
    for lap_number, lap_rows in sorted(grouped.items()):
        pct_values = [_pct(row.get("lap_dist_pct")) for row in lap_rows]
        pct_values = [value for value in pct_values if value is not None]
        pct_values_clean: list[float] = cast(list[float], pct_values)
        times = _numbers(lap_rows, "session_time")
        speeds = _numbers(lap_rows, "speed_mph")
        rpms = _numbers(lap_rows, "rpm")
        throttles = _numbers(lap_rows, "throttle_pct")
        brakes = _numbers(lap_rows, "brake_pct")
        splitters = _numbers(lap_rows, "cfsr_height_mm")
        steering = _numbers(lap_rows, "abs_steering_deg")

        pct_min = min(pct_values_clean) if pct_values_clean else None
        pct_max = max(pct_values_clean) if pct_values_clean else None
        pct_span = (pct_max - pct_min) if pct_min is not None and pct_max is not None else None
        is_complete = pct_min is not None and pct_max is not None and pct_min <= 2.0 and pct_max >= 98.0
        is_useful = is_complete and bool(speeds) and max(speeds) >= 30.0
        min_splitter = min(splitters) if splitters else None
        splitter_row = None
        if min_splitter is not None:
            splitter_row = min(lap_rows, key=lambda row: float(row.get("cfsr_height_mm", 1e9)))

        tags = ["SOLO_CLEAN"] if is_useful else ["PARTIAL"]
        if pct_span is not None and pct_span < 95.0:
            tags.append("SHORT_RUN")

        laps.append(
            LapSummary(
                lap_id=f"{run_id}:lap:{lap_number}",
                run_id=run_id,
                lap_number=lap_number,
                lap_type="complete" if is_complete else "partial",
                is_complete=is_complete,
                is_useful=is_useful,
                start_time=min(times) if times else None,
                end_time=max(times) if times else None,
                lap_time=(max(times) - min(times)) if len(times) >= 2 else None,
                pct_min=pct_min,
                pct_max=pct_max,
                pct_span=pct_span,
                sample_count=len(lap_rows),
                avg_speed_mph=mean(speeds) if speeds else None,
                max_speed_mph=max(speeds) if speeds else None,
                min_speed_mph=min(speeds) if speeds else None,
                avg_rpm=mean(rpms) if rpms else None,
                min_rpm=min(rpms) if rpms else None,
                max_rpm=max(rpms) if rpms else None,
                avg_throttle_pct=mean(throttles) if throttles else None,
                max_throttle_pct=max(throttles) if throttles else None,
                avg_brake_pct=mean(brakes) if brakes else None,
                max_brake_pct=max(brakes) if brakes else None,
                min_splitter_mm=min_splitter,
                min_splitter_pct=_pct(splitter_row.get("lap_dist_pct")) if splitter_row else None,
                min_splitter_distance_m=float(splitter_row.get("lap_dist_m", 0)) if splitter_row and splitter_row.get("lap_dist_m") is not None else None,
                min_splitter_speed_mph=float(splitter_row.get("speed_mph", 0)) if splitter_row and splitter_row.get("speed_mph") is not None else None,
                max_abs_steering_deg=max(steering) if steering else None,
                avg_abs_steering_deg=mean(steering) if steering else None,
                classification_tags=tags,
                confidence_notes=[] if is_complete else ["Lap does not span a full 0-100% distance range."],
            )
        )

    return laps
