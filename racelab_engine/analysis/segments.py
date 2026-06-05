from __future__ import annotations

import time
from statistics import mean
from typing import Any, Optional

from pydantic import BaseModel
import polars as pl

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.constants import SEGMENT_WIDTH_PCT
from racelab_engine.analysis.drag_scrub import compute_drag_scrub_index
from racelab_engine.analysis.platform import classify_splitter_height_mm


def _ensure_normalized(table: Any) -> list[dict[str, Any]]:
    """Normalize if needed; skip if already a list of normalized row dicts."""
    if isinstance(table, list) and table and isinstance(table[0], dict):
        if "speed_mph" in table[0]:
            return table  # already normalized
    return normalize_telemetry_rows(table)


class SegmentSummary(BaseModel):
    segment_id: str
    run_id: str
    lap_number: Optional[int] = None
    segment_type: str = "fixed_pct"
    segment_name: str
    pct_start: float
    pct_end: float
    distance_start_m: Optional[float] = None
    distance_end_m: Optional[float] = None
    avg_speed_mph: Optional[float] = None
    min_speed_mph: Optional[float] = None
    max_speed_mph: Optional[float] = None
    speed_delta_mph: Optional[float] = None
    avg_rpm: Optional[float] = None
    rpm_delta: Optional[float] = None
    avg_throttle_pct: Optional[float] = None
    avg_brake_pct: Optional[float] = None
    avg_abs_steering_deg: Optional[float] = None
    max_abs_steering_deg: Optional[float] = None
    avg_lat_accel: Optional[float] = None
    min_splitter_mm: Optional[float] = None
    platform_risk_score: float = 0.0
    drag_scrub_score: float = 0.0
    driver_input_score: float = 0.0
    powertrain_score: float = 0.0
    confidence_score: float = 0.0


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number * 100.0 if 0.0 <= number <= 1.5 else number


def _values(rows: list[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in rows if row.get(key) is not None]


def _score_platform(splitter_mm: float | None) -> float:
    severity = classify_splitter_height_mm(splitter_mm)
    return {
        "scrape": 1.0,
        "critical": 0.9,
        "high": 0.75,
        "watch": 0.45,
        "safe": 0.1,
        "unavailable": 0.0,
    }[severity]


def build_fixed_pct_segments(
    table: Any,
    run_id: str = "unassigned",
    lap_number: int | None = None,
    profile_out: dict[str, float] | None = None,
) -> list[SegmentSummary]:
    if isinstance(table, pl.DataFrame):
        return _build_fixed_pct_segments_frame(table, run_id=run_id, lap_number=lap_number, profile_out=profile_out)
    t_total = time.perf_counter()
    t0 = time.perf_counter()
    rows = _ensure_normalized(table)
    if profile_out is not None:
        profile_out["normalize_guard_s"] = time.perf_counter() - t0
    if not rows:
        if profile_out is not None:
            profile_out["total_s"] = time.perf_counter() - t_total
        return []

    t0 = time.perf_counter()
    if lap_number is not None:
        rows = [row for row in rows if int(row.get("lap") or row.get("lap_number") or -1) == lap_number]
    if profile_out is not None:
        profile_out["lap_filter_s"] = time.perf_counter() - t0
    if not rows:
        if profile_out is not None:
            profile_out["total_s"] = time.perf_counter() - t_total
        return []

    t0 = time.perf_counter()
    step = int(SEGMENT_WIDTH_PCT)
    bucket_rows: dict[int, list[dict[str, Any]]] = {start: [] for start in range(0, 100, step)}
    for row in rows:
        pct = _pct(row.get("lap_dist_pct"))
        if pct is None:
            continue
        start = int(pct // step) * step
        if start < 0:
            start = 0
        elif start >= 100:
            start = 100 - step
        if start in bucket_rows:
            bucket_rows[start].append(row)
    if profile_out is not None:
        profile_out["segment_boundary_bucket_s"] = time.perf_counter() - t0

    segments: list[SegmentSummary] = []
    t0 = time.perf_counter()
    for start in range(0, 100, step):
        end = start + step
        segment_rows = bucket_rows.get(start, [])
        if not segment_rows:
            continue

        speeds = _values(segment_rows, "speed_mph")
        rpms = _values(segment_rows, "rpm")
        throttles = _values(segment_rows, "throttle_pct")
        brakes = _values(segment_rows, "brake_pct")
        steering = _values(segment_rows, "abs_steering_deg")
        lat_accel = _values(segment_rows, "lat_accel")
        splitters = _values(segment_rows, "cfsr_height_mm")
        distances = _values(segment_rows, "lap_dist_m")

        speed_delta = speeds[-1] - speeds[0] if len(speeds) >= 2 else None
        rpm_delta = rpms[-1] - rpms[0] if len(rpms) >= 2 else None
        avg_throttle = mean(throttles) if throttles else None
        avg_brake = mean(brakes) if brakes else None
        avg_steering = mean(steering) if steering else None
        min_splitter = min(splitters) if splitters else None
        platform_score = _score_platform(min_splitter)
        driver_input_score = 1.0 if (avg_brake or 0.0) > 5.0 or (avg_throttle is not None and avg_throttle < 95.0) else 0.0
        # Use canonical drag/scrub index from the shared module
        drag_scrub_score = 0.0
        for row in segment_rows:
            dsi = compute_drag_scrub_index(row)
            if dsi > drag_scrub_score:
                drag_scrub_score = dsi

        segments.append(
            SegmentSummary(
                segment_id=f"{run_id}:segment:{lap_number or 'all'}:{start}-{end}",
                run_id=run_id,
                lap_number=lap_number,
                segment_name=f"{start}-{end}%",
                pct_start=float(start),
                pct_end=float(end),
                distance_start_m=min(distances) if distances else None,
                distance_end_m=max(distances) if distances else None,
                avg_speed_mph=mean(speeds) if speeds else None,
                min_speed_mph=min(speeds) if speeds else None,
                max_speed_mph=max(speeds) if speeds else None,
                speed_delta_mph=speed_delta,
                avg_rpm=mean(rpms) if rpms else None,
                rpm_delta=rpm_delta,
                avg_throttle_pct=avg_throttle,
                avg_brake_pct=avg_brake,
                avg_abs_steering_deg=avg_steering,
                max_abs_steering_deg=max(steering) if steering else None,
                avg_lat_accel=mean(lat_accel) if lat_accel else None,
                min_splitter_mm=min_splitter,
                platform_risk_score=platform_score,
                drag_scrub_score=drag_scrub_score,
                driver_input_score=driver_input_score,
                powertrain_score=0.0,
                confidence_score=0.6 if len(segment_rows) >= 2 else 0.25,
            )
        )

    if profile_out is not None:
        profile_out["segment_aggregate_s"] = time.perf_counter() - t0
        profile_out["total_s"] = time.perf_counter() - t_total
    return segments


def _build_fixed_pct_segments_frame(
    df: pl.DataFrame,
    run_id: str = "unassigned",
    lap_number: int | None = None,
    profile_out: dict[str, float] | None = None,
) -> list[SegmentSummary]:
    t_total = time.perf_counter()
    t0 = time.perf_counter()
    if df.is_empty():
        return []
    work = df
    if profile_out is not None:
        profile_out["normalize_guard_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    if lap_number is not None:
        lap_expr = (
            pl.coalesce([pl.col("lap"), pl.col("lap_number")])
            if "lap_number" in work.columns
            else pl.col("lap")
        )
        work = work.filter(lap_expr.cast(pl.Int64, strict=False) == lap_number)
    if profile_out is not None:
        profile_out["lap_filter_s"] = time.perf_counter() - t0
    if work.is_empty():
        return []
    t0 = time.perf_counter()
    step = int(SEGMENT_WIDTH_PCT)
    with_pct = work.with_columns(
        pl.when((pl.col("lap_dist_pct").is_not_null()) & (pl.col("lap_dist_pct") <= 1.5))
        .then(pl.col("lap_dist_pct") * 100.0)
        .otherwise(pl.col("lap_dist_pct"))
        .alias("_lap_pct")
    ).filter(pl.col("_lap_pct").is_not_null())
    with_pct = with_pct.with_columns(
        (((pl.col("_lap_pct") / step).floor() * step).clip(0, 100 - step)).cast(pl.Int64).alias("_seg_start"),
    )
    if profile_out is not None:
        profile_out["segment_boundary_bucket_s"] = time.perf_counter() - t0
    if with_pct.is_empty():
        return []
    t0 = time.perf_counter()
    drag_scores: dict[int, float] = {}
    for row in with_pct.select(
        "_seg_start",
        "speed_mph",
        "throttle_pct",
        "brake_pct",
        "speed_rate_mph_s",
        "dynamic_pressure_psf",
        "abs_steering_deg",
        "yaw_rate",
        "cfs_risk_score",
    ).iter_rows(named=True):
        seg = int(row["_seg_start"])
        score = compute_drag_scrub_index(row)
        if score > drag_scores.get(seg, 0.0):
            drag_scores[seg] = score
    agg = with_pct.group_by("_seg_start").agg(
        pl.col("speed_mph").mean().alias("avg_speed_mph"),
        pl.col("speed_mph").min().alias("min_speed_mph"),
        pl.col("speed_mph").max().alias("max_speed_mph"),
        (pl.col("speed_mph").drop_nulls().last() - pl.col("speed_mph").drop_nulls().first()).alias("speed_delta_mph"),
        pl.col("rpm").mean().alias("avg_rpm"),
        (pl.col("rpm").drop_nulls().last() - pl.col("rpm").drop_nulls().first()).alias("rpm_delta"),
        pl.col("throttle_pct").mean().alias("avg_throttle_pct"),
        pl.col("brake_pct").mean().alias("avg_brake_pct"),
        pl.col("abs_steering_deg").mean().alias("avg_abs_steering_deg"),
        pl.col("abs_steering_deg").max().alias("max_abs_steering_deg"),
        pl.col("lat_accel").mean().alias("avg_lat_accel"),
        pl.col("cfsr_height_mm").min().alias("min_splitter_mm"),
        pl.col("lap_dist_m").min().alias("distance_start_m"),
        pl.col("lap_dist_m").max().alias("distance_end_m"),
        pl.len().alias("sample_count"),
    ).sort("_seg_start")
    segments: list[SegmentSummary] = []
    for rec in agg.to_dicts():
        start = int(rec["_seg_start"])
        end = start + step
        min_splitter = float(rec["min_splitter_mm"]) if rec.get("min_splitter_mm") is not None else None
        avg_brake = float(rec["avg_brake_pct"]) if rec.get("avg_brake_pct") is not None else None
        avg_throttle = float(rec["avg_throttle_pct"]) if rec.get("avg_throttle_pct") is not None else None
        driver_input_score = 1.0 if (avg_brake or 0.0) > 5.0 or (avg_throttle is not None and avg_throttle < 95.0) else 0.0
        segments.append(
            SegmentSummary(
                segment_id=f"{run_id}:segment:{lap_number or 'all'}:{start}-{end}",
                run_id=run_id,
                lap_number=lap_number,
                segment_name=f"{start}-{end}%",
                pct_start=float(start),
                pct_end=float(end),
                distance_start_m=float(rec["distance_start_m"]) if rec.get("distance_start_m") is not None else None,
                distance_end_m=float(rec["distance_end_m"]) if rec.get("distance_end_m") is not None else None,
                avg_speed_mph=float(rec["avg_speed_mph"]) if rec.get("avg_speed_mph") is not None else None,
                min_speed_mph=float(rec["min_speed_mph"]) if rec.get("min_speed_mph") is not None else None,
                max_speed_mph=float(rec["max_speed_mph"]) if rec.get("max_speed_mph") is not None else None,
                speed_delta_mph=float(rec["speed_delta_mph"]) if rec.get("speed_delta_mph") is not None else None,
                avg_rpm=float(rec["avg_rpm"]) if rec.get("avg_rpm") is not None else None,
                rpm_delta=float(rec["rpm_delta"]) if rec.get("rpm_delta") is not None else None,
                avg_throttle_pct=avg_throttle,
                avg_brake_pct=avg_brake,
                avg_abs_steering_deg=float(rec["avg_abs_steering_deg"]) if rec.get("avg_abs_steering_deg") is not None else None,
                max_abs_steering_deg=float(rec["max_abs_steering_deg"]) if rec.get("max_abs_steering_deg") is not None else None,
                avg_lat_accel=float(rec["avg_lat_accel"]) if rec.get("avg_lat_accel") is not None else None,
                min_splitter_mm=min_splitter,
                platform_risk_score=_score_platform(min_splitter),
                drag_scrub_score=float(drag_scores.get(start, 0.0)),
                driver_input_score=driver_input_score,
                powertrain_score=0.0,
                confidence_score=0.6 if int(rec.get("sample_count") or 0) >= 2 else 0.25,
            )
        )
    if profile_out is not None:
        profile_out["segment_aggregate_s"] = time.perf_counter() - t0
        profile_out["total_s"] = time.perf_counter() - t_total
    return segments
