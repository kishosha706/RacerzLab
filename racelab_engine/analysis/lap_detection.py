from __future__ import annotations

from collections import defaultdict
import math
from statistics import mean, median
from typing import Any, cast

import polars as pl

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.models.lap import LapSummary


_YELLOW_FLAG_MASK = 0x0008 | 0x0100
_CAUTION_FLAG_MASK = 0x4000 | 0x8000
_MAX_CREDIBLE_FORWARD_PCT_GAP = 8.0
_MIN_CREDIBLE_LAP_DURATION_S = 5.0
_MIN_CREDIBLE_LAP_SAMPLES = 20
_MIN_CREDIBLE_SAMPLE_DENSITY_HZ = 2.0
_ABNORMAL_EVENT_MAX_SPEED_MPH = 25.0
_ABNORMAL_EVENT_MIN_YAW_RATE_RAD_S = 3.0
_ABNORMAL_EVENT_MIN_STEERING_DEG = 20.0
_INCIDENT_COUNT_COLUMNS = (
    ("player_incident_count", "PlayerCarMyIncidentCount"),
    ("player_driver_incident_count", "PlayerCarDriverIncidentCount"),
    ("player_team_incident_count", "PlayerCarTeamIncidentCount"),
)


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

    session_flags: list[int] = []
    for row in rows:
        flag_value = row.get("session_flags", row.get("SessionFlags"))
        try:
            if flag_value is not None:
                session_flags.append(int(flag_value))
        except (TypeError, ValueError, OverflowError):
            pass
    if any(value & _YELLOW_FLAG_MASK for value in session_flags):
        tags.add("YELLOW")
        notes.append("The simulator reported a yellow-flag state during this lap.")
    if any(value & _CAUTION_FLAG_MASK for value in session_flags):
        tags.add("CAUTION")
        notes.append("The simulator reported a caution state during this lap.")

    ticks: list[int] = []
    for row in rows:
        value = row.get("session_tick", row.get("SessionTick"))
        try:
            tick = int(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            tick = None
        if tick is not None:
            ticks.append(tick)
    if len(ticks) >= 2 and any(current - previous != 1 for previous, current in zip(ticks, ticks[1:])):
        tags.add("SAMPLE_DISCONTINUITY")
        notes.append("SessionTick was not continuous through this lap.")

    pct_sequence = [_pct(row.get("lap_dist_pct")) for row in rows]
    pct_sequence = [value for value in pct_sequence if value is not None]
    if len(pct_sequence) >= 2 and any(current < previous - 5.0 for previous, current in zip(pct_sequence, pct_sequence[1:])):
        tags.add("POSITION_DISCONTINUITY")
        notes.append("Lap position moved backward unexpectedly within this lap.")
    if len(pct_sequence) >= 2 and any(
        current - previous > _MAX_CREDIBLE_FORWARD_PCT_GAP
        for previous, current in zip(pct_sequence, pct_sequence[1:])
    ):
        tags.add("SPARSE_POSITION_COVERAGE")
        notes.append("Lap-position samples had implausibly large forward gaps.")

    times = _numbers(rows, "session_time")
    duration_s = max(times) - min(times) if len(times) >= 2 else None
    density_hz = len(rows) / duration_s if duration_s is not None and duration_s > 0 else None
    if (
        len(rows) < _MIN_CREDIBLE_LAP_SAMPLES
        or duration_s is None
        or duration_s < _MIN_CREDIBLE_LAP_DURATION_S
        or density_hz is None
        or density_hz < _MIN_CREDIBLE_SAMPLE_DENSITY_HZ
    ):
        tags.add("NON_CREDIBLE_LAP_SAMPLING")
        notes.append("Lap duration or telemetry sample density was too small for setup evidence.")

    for canonical, raw in _INCIDENT_COUNT_COLUMNS:
        values: list[float] = []
        for row in rows:
            value = row.get(canonical, row.get(raw))
            try:
                number = float(value) if value is not None else None
            except (TypeError, ValueError, OverflowError):
                number = None
            if number is not None and math.isfinite(number):
                values.append(number)
        if any(current > previous for previous, current in zip(values, values[1:])):
            tags.add("INCIDENT_COUNT_INCREASE")
            notes.append("The simulator incident count increased during this lap.")
            break

    speed_values: list[float] = []
    invalid_speed = False
    for row in rows:
        value = row.get("speed_mph")
        if value is None:
            continue
        try:
            speed = float(value)
        except (TypeError, ValueError, OverflowError):
            invalid_speed = True
            continue
        if not math.isfinite(speed) or speed < 0:
            invalid_speed = True
        else:
            speed_values.append(speed)
    if invalid_speed:
        tags.add("INVALID_SPEED_EVENT")
        notes.append("Invalid or negative speed samples were present during this lap.")

    # Fail closed only on a sustained, strong spin/wreck signature.  Steering or
    # yaw alone is normal in corners, so this requires all three signals to
    # coincide at very low speed across several samples.  It is deliberately a
    # setup-eligibility gate, not a claim about the exact incident cause.
    abnormal_samples = 0
    observed_signature_samples = 0
    for row in rows:
        speed = _finite(row.get("speed_mph"))
        yaw_rate = _finite(row.get("yaw_rate", row.get("YawRate")))
        steering = _finite(row.get("abs_steering_deg"))
        if steering is None:
            steering_rad = _finite(row.get("steering_rad", row.get("SteeringWheelAngle")))
            steering = abs(math.degrees(steering_rad)) if steering_rad is not None else None
        if speed is None or yaw_rate is None or steering is None:
            continue
        observed_signature_samples += 1
        if (
            speed <= _ABNORMAL_EVENT_MAX_SPEED_MPH
            and abs(yaw_rate) >= _ABNORMAL_EVENT_MIN_YAW_RATE_RAD_S
            and abs(steering) >= _ABNORMAL_EVENT_MIN_STEERING_DEG
        ):
            abnormal_samples += 1
    required_abnormal_samples = max(3, math.ceil(observed_signature_samples * 0.15))
    if observed_signature_samples and abnormal_samples >= required_abnormal_samples:
        tags.add("WRECK_OR_SPIN")
        notes.append(
            "Sustained low-speed, high-yaw, high-steering behavior made the lap unsafe for setup conclusions."
        )
    return tags, list(dict.fromkeys(notes))


def direct_invalid_context_tags(rows: list[dict[str, Any]]) -> frozenset[str]:
    """Expose canonical junk-context classifications to section analyzers."""
    tags, _notes = _direct_invalid_tags(rows)
    return frozenset(tags)


def _apply_relative_pace_filter(laps: list[LapSummary]) -> list[LapSummary]:
    """Conservatively reject obvious cooldown/invalid laps using within-run pace."""
    candidates = [
        lap for lap in laps
        if lap.is_useful and lap.lap_time is not None and math.isfinite(float(lap.lap_time))
    ]
    # Three laps are enough to reject one extreme low-demand outlier while two
    # laps remain ambiguous.  The demand check below prevents pace alone from
    # rejecting a merely slower but otherwise representative lap.
    if len(candidates) < 3:
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
            tags.discard("ELIGIBLE_FLYING_LAP")
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


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


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

        tags = ["ELIGIBLE_FLYING_LAP"] if is_useful else (["PARTIAL"] if not is_complete else [])
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
    required = {"lap_dist_pct", "session_time", "speed_mph"}
    if not required.issubset(df.columns) or not ({"lap", "lap_number"} & set(df.columns)):
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
    sequence_exprs: list[pl.Expr] = [
        pl.col("_lap_pct").diff().over("_lap_number").alias("_lap_pct_delta"),
    ]
    if "session_tick" in base.columns:
        sequence_exprs.append(
            pl.col("session_tick").cast(pl.Int64, strict=False).diff().over("_lap_number").alias("_session_tick_delta")
        )
    incident_columns = [
        column
        for canonical, raw in _INCIDENT_COUNT_COLUMNS
        for column in (canonical, raw)
        if column in base.columns
    ]
    for index, column in enumerate(dict.fromkeys(incident_columns)):
        sequence_exprs.append(
            pl.col(column)
            .cast(pl.Float64, strict=False)
            .diff()
            .over("_lap_number")
            .alias(f"_incident_delta_{index}")
        )
    base = base.with_columns(*sequence_exprs)
    agg_exprs: list[pl.Expr] = [
        pl.len().alias("sample_count"),
        pl.col("_lap_pct").min().alias("pct_min"),
        pl.col("_lap_pct").max().alias("pct_max"),
        pl.col("session_time").min().alias("start_time"),
        pl.col("session_time").max().alias("end_time"),
        pl.col("speed_mph").mean().alias("avg_speed_mph"),
        pl.col("speed_mph").max().alias("max_speed_mph"),
        pl.col("speed_mph").min().alias("min_speed_mph"),
        pl.col("_lap_pct_delta").min().alias("min_lap_pct_delta"),
        pl.col("_lap_pct_delta").max().alias("max_lap_pct_delta"),
        ((~pl.col("speed_mph").is_finite()) | (pl.col("speed_mph") < 0)).sum().alias("invalid_speed_samples"),
    ]
    optional_aggregates: dict[str, tuple[pl.Expr, ...]] = {
        "rpm": (
            pl.col("rpm").mean().alias("avg_rpm"),
            pl.col("rpm").min().alias("min_rpm"),
            pl.col("rpm").max().alias("max_rpm"),
        ),
        "throttle_pct": (
            pl.col("throttle_pct").mean().alias("avg_throttle_pct"),
            pl.col("throttle_pct").max().alias("max_throttle_pct"),
        ),
        "brake_pct": (
            pl.col("brake_pct").mean().alias("avg_brake_pct"),
            pl.col("brake_pct").max().alias("max_brake_pct"),
        ),
        "abs_steering_deg": (
            pl.col("abs_steering_deg").max().alias("max_abs_steering_deg"),
            pl.col("abs_steering_deg").mean().alias("avg_abs_steering_deg"),
        ),
    }
    for column, expressions in optional_aggregates.items():
        if column in base.columns:
            agg_exprs.extend(expressions)
    if {"yaw_rate", "abs_steering_deg"}.issubset(base.columns):
        abnormal_signature = (
            (pl.col("speed_mph") <= _ABNORMAL_EVENT_MAX_SPEED_MPH)
            & (pl.col("yaw_rate").abs() >= _ABNORMAL_EVENT_MIN_YAW_RATE_RAD_S)
            & (pl.col("abs_steering_deg").abs() >= _ABNORMAL_EVENT_MIN_STEERING_DEG)
        )
        signature_observed = (
            pl.col("speed_mph").is_not_null()
            & pl.col("yaw_rate").is_not_null()
            & pl.col("abs_steering_deg").is_not_null()
        )
        agg_exprs.extend(
            [
                abnormal_signature.sum().alias("abnormal_signature_samples"),
                signature_observed.sum().alias("signature_observed_samples"),
            ]
        )
    if "_session_tick_delta" in base.columns:
        agg_exprs.extend([
            pl.col("_session_tick_delta").min().alias("min_session_tick_delta"),
            pl.col("_session_tick_delta").max().alias("max_session_tick_delta"),
        ])
    for index in range(len(dict.fromkeys(incident_columns))):
        agg_exprs.append(pl.col(f"_incident_delta_{index}").max().alias(f"max_incident_delta_{index}"))
    if "on_pit_road" in base.columns:
        agg_exprs.append(pl.col("on_pit_road").cast(pl.Int8, strict=False).max().alias("any_on_pit_road"))
    if "is_on_track" in base.columns:
        agg_exprs.append(pl.col("is_on_track").cast(pl.Int8, strict=False).min().alias("all_on_track"))
    if "player_track_surface" in base.columns:
        agg_exprs.extend([
            pl.col("player_track_surface").cast(pl.Int64, strict=False).min().alias("min_track_surface"),
            pl.col("player_track_surface").cast(pl.Int64, strict=False).max().alias("max_track_surface"),
        ])
    session_flags_column = next(
        (column for column in ("session_flags", "SessionFlags") if column in base.columns),
        None,
    )
    if session_flags_column is not None:
        flags = pl.col(session_flags_column).cast(pl.Int64, strict=False).fill_null(0)
        agg_exprs.extend([
            ((flags & pl.lit(_YELLOW_FLAG_MASK)) != 0).max().alias("any_yellow_flag"),
            ((flags & pl.lit(_CAUTION_FLAG_MASK)) != 0).max().alias("any_caution_flag"),
        ])
    agg = base.group_by("_lap_number").agg(*agg_exprs).sort("_lap_number")
    joined = agg
    if "cfsr_height_mm" in base.columns:
        min_split = (
            base.filter(pl.col("cfsr_height_mm").is_not_null())
            .sort(["_lap_number", "cfsr_height_mm"])
            .group_by("_lap_number")
            .first()
            .select(
                "_lap_number",
                pl.col("cfsr_height_mm").alias("min_splitter_mm"),
                "_lap_pct",
                pl.col("lap_dist_m") if "lap_dist_m" in base.columns else pl.lit(None).alias("lap_dist_m"),
                "speed_mph",
            )
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
        min_tick_delta = rec.get("min_session_tick_delta")
        max_tick_delta = rec.get("max_session_tick_delta")
        if (
            (min_tick_delta is not None and int(min_tick_delta) != 1)
            or (max_tick_delta is not None and int(max_tick_delta) != 1)
        ):
            direct_tags.add("SAMPLE_DISCONTINUITY")
            direct_notes.append("SessionTick was not continuous through this lap.")
        min_pct_delta = rec.get("min_lap_pct_delta")
        if min_pct_delta is not None and float(min_pct_delta) < -5.0:
            direct_tags.add("POSITION_DISCONTINUITY")
            direct_notes.append("Lap position moved backward unexpectedly within this lap.")
        max_pct_delta = rec.get("max_lap_pct_delta")
        if max_pct_delta is not None and float(max_pct_delta) > _MAX_CREDIBLE_FORWARD_PCT_GAP:
            direct_tags.add("SPARSE_POSITION_COVERAGE")
            direct_notes.append("Lap-position samples had implausibly large forward gaps.")
        start_time = rec.get("start_time")
        end_time = rec.get("end_time")
        sample_count = int(rec.get("sample_count") or 0)
        duration_s = (
            float(end_time) - float(start_time)
            if start_time is not None and end_time is not None
            else None
        )
        density_hz = sample_count / duration_s if duration_s is not None and duration_s > 0 else None
        if (
            sample_count < _MIN_CREDIBLE_LAP_SAMPLES
            or duration_s is None
            or duration_s < _MIN_CREDIBLE_LAP_DURATION_S
            or density_hz is None
            or density_hz < _MIN_CREDIBLE_SAMPLE_DENSITY_HZ
        ):
            direct_tags.add("NON_CREDIBLE_LAP_SAMPLING")
            direct_notes.append("Lap duration or telemetry sample density was too small for setup evidence.")
        if any(float(rec.get(f"max_incident_delta_{index}") or 0.0) > 0.0 for index in range(len(dict.fromkeys(incident_columns)))):
            direct_tags.add("INCIDENT_COUNT_INCREASE")
            direct_notes.append("The simulator incident count increased during this lap.")
        if int(rec.get("invalid_speed_samples") or 0) > 0:
            direct_tags.add("INVALID_SPEED_EVENT")
            direct_notes.append("Invalid or negative speed samples were present during this lap.")
        observed_signature_samples = int(rec.get("signature_observed_samples") or 0)
        abnormal_signature_samples = int(rec.get("abnormal_signature_samples") or 0)
        if observed_signature_samples and abnormal_signature_samples >= max(
            3, math.ceil(observed_signature_samples * 0.15)
        ):
            direct_tags.add("WRECK_OR_SPIN")
            direct_notes.append(
                "Sustained low-speed, high-yaw, high-steering behavior made the lap unsafe for setup conclusions."
            )
        if rec.get("any_yellow_flag") is True:
            direct_tags.add("YELLOW")
            direct_notes.append("The simulator reported a yellow-flag state during this lap.")
        if rec.get("any_caution_flag") is True:
            direct_tags.add("CAUTION")
            direct_notes.append("The simulator reported a caution state during this lap.")
        is_useful = is_complete and max_speed is not None and float(max_speed) >= 30.0 and not direct_tags
        tags = ["ELIGIBLE_FLYING_LAP"] if is_useful else (["PARTIAL"] if not is_complete else [])
        tags.extend(sorted(direct_tags))
        if direct_tags:
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
                start_time=float(start_time) if start_time is not None else None,
                end_time=float(end_time) if end_time is not None else None,
                lap_time=(float(end_time) - float(start_time)) if start_time is not None and end_time is not None else None,
                pct_min=float(pct_min) if pct_min is not None else None,
                pct_max=float(pct_max) if pct_max is not None else None,
                pct_span=pct_span,
                sample_count=sample_count,
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
