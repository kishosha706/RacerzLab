from __future__ import annotations

from collections import defaultdict
import math
from statistics import mean, median
from typing import Any, cast

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.models.lap import LapSummary
import polars as pl


def _truthy(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on"}:
            return True
        if normalized in {"false", "no", "off"}:
            return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return bool(value)
    return bool(number) if math.isfinite(number) else None


def _direct_invalid_tags(rows: list[dict[str, Any]]) -> tuple[set[str], list[str]]:
    tags: set[str] = set()
    notes: list[str] = []
    pit_values = [_truthy(row.get("on_pit_road", row.get("OnPitRoad"))) for row in rows]
    if any(value is True for value in pit_values):
        tags.add("PIT_ROAD")
        notes.append("Pit-road telemetry was present during this lap.")

    on_track_values = [_truthy(row.get("is_on_track", row.get("IsOnTrack"))) for row in rows]
    if any(value is False for value in on_track_values):
        tags.add("OFF_TRACK")
        notes.append("The simulator reported off-track samples during this lap.")

    surfaces: list[int] = []
    for row in rows:
        value = row.get("player_track_surface", row.get("PlayerTrackSurface"))
        try:
            number = int(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        if number is not None:
            surfaces.append(number)
    if any(value in {1, 2} for value in surfaces):
        tags.add("PIT_ROAD")
        notes.append("The simulator track-surface state entered the pit lane or pit stall.")
    if any(value <= 0 for value in surfaces):
        tags.add("OFF_TRACK")
        notes.append("The simulator track-surface state left the racing surface.")
    return tags, list(dict.fromkeys(notes))


def _apply_relative_pace_filter(laps: list[LapSummary]) -> list[LapSummary]:
    """Conservatively reject obvious cooldown/invalid laps using within-run pace."""
    candidates = [
        lap for lap in laps
        if lap.is_useful and lap.lap_time is not None and math.isfinite(float(lap.lap_time))
    ]
    if len(candidates) < 4:
        return laps
    median_time = median(float(lap.lap_time) for lap in candidates if lap.lap_time is not None)
    throttle_values = [lap.avg_throttle_pct for lap in candidates if lap.avg_throttle_pct is not None]
    speed_values = [lap.avg_speed_mph for lap in candidates if lap.avg_speed_mph is not None]
    median_throttle = median(throttle_values) if throttle_values else None
    median_speed = median(speed_values) if speed_values else None

    result: list[LapSummary] = []
    for lap in laps:
        if lap not in candidates or lap.lap_time is None:
            result.append(lap)
            continue
        tags = {tag.upper() for tag in lap.classification_tags}
        notes = list(lap.confidence_notes)
        lap_time = float(lap.lap_time)
        abnormally_slow = lap_time > max(median_time * 1.15, median_time + 3.0)
        low_throttle = (
            median_throttle is not None
            and lap.avg_throttle_pct is not None
            and lap.avg_throttle_pct < median_throttle * 0.85
        )
        low_speed = (
            median_speed is not None
            and lap.avg_speed_mph is not None
            and lap.avg_speed_mph < median_speed * 0.82
        )
        implausibly_fast = lap_time < median_time * 0.72
        if implausibly_fast:
            tags.update({"INVALID_SPEED_EVENT", "NO_SETUP_CONCLUSION"})
            notes.append("Lap time was implausibly fast relative to the clean-lap cohort.")
        elif abnormally_slow and (low_throttle or low_speed):
            tags.update({"COOLDOWN", "NO_SETUP_CONCLUSION"})
            notes.append("Lap pace and driver demand were outside the clean-lap cohort.")
        if tags & {"COOLDOWN", "INVALID_SPEED_EVENT"}:
            tags.discard("SOLO_CLEAN")
            result.append(lap.model_copy(update={
                "is_useful": False,
                "lap_type": "invalid",
                "classification_tags": sorted(tags),
                "confidence_notes": list(dict.fromkeys(notes)),
            }))
        else:
            result.append(lap)
    return result


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
            number = float(value)
            if math.isfinite(number):
                values.append(number)
    return values


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number * 100.0 if 0.0 <= number <= 1.5 else number


def _lap_number(row: dict[str, Any]) -> int | None:
    value = row.get("lap")
    if value is None:
        value = row.get("lap_number")
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) else None


def detect_laps(table: Any, run_id: str = "unassigned") -> list[LapSummary]:
    if isinstance(table, pl.DataFrame):
        return _detect_laps_frame(table, run_id=run_id)
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
        direct_invalid_tags, direct_notes = _direct_invalid_tags(lap_rows)
        is_useful = is_complete and bool(speeds) and max(speeds) >= 30.0 and not direct_invalid_tags
        min_splitter = min(splitters) if splitters else None
        splitter_row = None
        if min_splitter is not None:
            splitter_row = min(lap_rows, key=lambda row: float(row.get("cfsr_height_mm", 1e9)))

        tags = ["SOLO_CLEAN"] if is_useful else (["PARTIAL"] if not is_complete else [])
        tags.extend(sorted(direct_invalid_tags))
        if direct_invalid_tags:
            tags.append("NO_SETUP_CONCLUSION")
        if pct_span is not None and pct_span < 95.0:
            tags.append("SHORT_RUN")

        laps.append(
            LapSummary(
                lap_id=f"{run_id}:lap:{lap_number}",
                run_id=run_id,
                lap_number=lap_number,
                lap_type="timed" if is_useful else ("complete_invalid" if is_complete else "partial"),
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
                confidence_notes=([] if is_complete else ["Lap does not span a full 0-100% distance range."]) + direct_notes,
            )
        )

    return _apply_relative_pace_filter(laps)


def _detect_laps_frame(df: pl.DataFrame, run_id: str = "unassigned") -> list[LapSummary]:
    if df.is_empty():
        return []
    lap_expr = (
        pl.coalesce([pl.col("lap"), pl.col("lap_number")])
        if "lap_number" in df.columns
        else pl.col("lap")
    )
    base = df.with_columns(
        lap_expr.cast(pl.Int64, strict=False).alias("_lap_number"),
        pl.when((pl.col("lap_dist_pct").is_not_null()) & (pl.col("lap_dist_pct") <= 1.5))
        .then(pl.col("lap_dist_pct") * 100.0)
        .otherwise(pl.col("lap_dist_pct"))
        .alias("_lap_pct"),
    ).filter(pl.col("_lap_number").is_not_null())
    if base.is_empty():
        return []
    agg_exprs: list[pl.Expr] = [
        pl.len().alias("sample_count"),
        pl.col("_lap_pct").min().alias("pct_min"),
        pl.col("_lap_pct").max().alias("pct_max"),
        pl.col("session_time").min().alias("start_time"),
        pl.col("session_time").max().alias("end_time"),
        pl.col("speed_mph").mean().alias("avg_speed_mph"),
        pl.col("speed_mph").max().alias("max_speed_mph"),
        pl.col("speed_mph").min().alias("min_speed_mph"),
        pl.col("rpm").mean().alias("avg_rpm"),
        pl.col("rpm").min().alias("min_rpm"),
        pl.col("rpm").max().alias("max_rpm"),
        pl.col("throttle_pct").mean().alias("avg_throttle_pct"),
        pl.col("throttle_pct").max().alias("max_throttle_pct"),
        pl.col("brake_pct").mean().alias("avg_brake_pct"),
        pl.col("brake_pct").max().alias("max_brake_pct"),
        pl.col("abs_steering_deg").max().alias("max_abs_steering_deg"),
        pl.col("abs_steering_deg").mean().alias("avg_abs_steering_deg"),
    ]
    if "on_pit_road" in base.columns:
        agg_exprs.append(pl.col("on_pit_road").cast(pl.Int8, strict=False).max().alias("any_on_pit_road"))
    if "is_on_track" in base.columns:
        agg_exprs.append(pl.col("is_on_track").cast(pl.Int8, strict=False).min().alias("all_on_track"))
    if "player_track_surface" in base.columns:
        agg_exprs.extend([
            pl.col("player_track_surface").cast(pl.Int64, strict=False).min().alias("min_track_surface"),
            pl.col("player_track_surface").cast(pl.Int64, strict=False).max().alias("max_track_surface"),
        ])
    agg = base.group_by("_lap_number").agg(*agg_exprs).sort("_lap_number")
    min_split = (
        base.filter(pl.col("cfsr_height_mm").is_not_null())
        .sort(["_lap_number", "cfsr_height_mm"])
        .group_by("_lap_number")
        .first()
        .select("_lap_number", pl.col("cfsr_height_mm").alias("min_splitter_mm"), "_lap_pct", "lap_dist_m", "speed_mph")
    )
    joined = agg.join(min_split, on="_lap_number", how="left")
    laps: list[LapSummary] = []
    for rec in joined.to_dicts():
        lap_number = int(rec["_lap_number"])
        pct_min = rec.get("pct_min")
        pct_max = rec.get("pct_max")
        pct_span = (float(pct_max) - float(pct_min)) if pct_min is not None and pct_max is not None else None
        is_complete = pct_min is not None and pct_max is not None and float(pct_min) <= 2.0 and float(pct_max) >= 98.0
        max_speed = rec.get("max_speed_mph")
        direct_tags: set[str] = set()
        direct_notes: list[str] = []
        if rec.get("any_on_pit_road") == 1:
            direct_tags.add("PIT_ROAD")
            direct_notes.append("Pit-road telemetry was present during this lap.")
        if rec.get("all_on_track") == 0:
            direct_tags.add("OFF_TRACK")
            direct_notes.append("The simulator reported off-track samples during this lap.")
        surface_min = rec.get("min_track_surface")
        surface_max = rec.get("max_track_surface")
        if surface_min is not None and surface_max is not None:
            surface_values = range(int(surface_min), int(surface_max) + 1)
            if any(value in {1, 2} for value in surface_values):
                direct_tags.add("PIT_ROAD")
            if int(surface_min) <= 0:
                direct_tags.add("OFF_TRACK")
        is_useful = is_complete and max_speed is not None and float(max_speed) >= 30.0 and not direct_tags
        tags = ["SOLO_CLEAN"] if is_useful else (["PARTIAL"] if not is_complete else [])
        tags.extend(sorted(direct_tags))
        if direct_tags:
            tags.append("NO_SETUP_CONCLUSION")
        if pct_span is not None and pct_span < 95.0:
            tags.append("SHORT_RUN")
        start_time = rec.get("start_time")
        end_time = rec.get("end_time")
        laps.append(
            LapSummary(
                lap_id=f"{run_id}:lap:{lap_number}",
                run_id=run_id,
                lap_number=lap_number,
                lap_type="timed" if is_useful else ("complete_invalid" if is_complete else "partial"),
                is_complete=is_complete,
                is_useful=is_useful,
                start_time=float(start_time) if start_time is not None else None,
                end_time=float(end_time) if end_time is not None else None,
                lap_time=(float(end_time) - float(start_time)) if start_time is not None and end_time is not None else None,
                pct_min=float(pct_min) if pct_min is not None else None,
                pct_max=float(pct_max) if pct_max is not None else None,
                pct_span=pct_span,
                sample_count=int(rec.get("sample_count") or 0),
                avg_speed_mph=float(rec["avg_speed_mph"]) if rec.get("avg_speed_mph") is not None else None,
                max_speed_mph=float(max_speed) if max_speed is not None else None,
                min_speed_mph=float(rec["min_speed_mph"]) if rec.get("min_speed_mph") is not None else None,
                avg_rpm=float(rec["avg_rpm"]) if rec.get("avg_rpm") is not None else None,
                min_rpm=float(rec["min_rpm"]) if rec.get("min_rpm") is not None else None,
                max_rpm=float(rec["max_rpm"]) if rec.get("max_rpm") is not None else None,
                avg_throttle_pct=float(rec["avg_throttle_pct"]) if rec.get("avg_throttle_pct") is not None else None,
                max_throttle_pct=float(rec["max_throttle_pct"]) if rec.get("max_throttle_pct") is not None else None,
                avg_brake_pct=float(rec["avg_brake_pct"]) if rec.get("avg_brake_pct") is not None else None,
                max_brake_pct=float(rec["max_brake_pct"]) if rec.get("max_brake_pct") is not None else None,
                min_splitter_mm=float(rec["min_splitter_mm"]) if rec.get("min_splitter_mm") is not None else None,
                min_splitter_pct=float(rec["_lap_pct"]) if rec.get("_lap_pct") is not None else None,
                min_splitter_distance_m=float(rec["lap_dist_m"]) if rec.get("lap_dist_m") is not None else None,
                min_splitter_speed_mph=float(rec["speed_mph"]) if rec.get("speed_mph") is not None else None,
                max_abs_steering_deg=float(rec["max_abs_steering_deg"]) if rec.get("max_abs_steering_deg") is not None else None,
                avg_abs_steering_deg=float(rec["avg_abs_steering_deg"]) if rec.get("avg_abs_steering_deg") is not None else None,
                classification_tags=tags,
                confidence_notes=([] if is_complete else ["Lap does not span a full 0-100% distance range."]) + direct_notes,
            )
        )
    return _apply_relative_pace_filter(laps)
