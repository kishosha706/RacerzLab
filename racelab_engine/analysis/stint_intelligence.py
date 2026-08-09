"""Imported-data stint summaries and stint-to-stint comparison."""

from __future__ import annotations

import math
import statistics
from typing import Iterable

from racelab_engine.analysis.lap_windows import (
    _is_lap_valid_for_ranking,
    _lap_numbers_are_consecutive,
    compute_best_windows,
)
from racelab_engine.analysis.pace_quality import compute_pace_quality_score, score_consistency
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import (
    StintBucket,
    StintBucketDelta,
    StintCompareResult,
    StintGraphPoint,
    StintResponse,
    StintRunSummary,
    StintSummary,
)
from racelab_engine.models.session import SessionSummary

STINT_WINDOW_SIZES = [3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60]
STINT_BUCKET_SIZE = 5
STINT_BUCKET_COUNT = 12
MIN_LONG_RUN_WINDOW_SIZE = 20


def _avg(values: Iterable[float]) -> float | None:
    items = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(items) / len(items) if items else None


def _valid_laps(laps: Iterable[LapSummary]) -> list[LapSummary]:
    return [lap for lap in laps if _is_lap_valid_for_ranking(lap)[0]]


def _times(laps: Iterable[LapSummary]) -> list[float]:
    return [float(lap.lap_time) for lap in laps if lap.lap_time is not None and math.isfinite(float(lap.lap_time))]


def _best_rolling_average(laps: list[LapSummary], size: int) -> float | None:
    if len(laps) < size:
        return None
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    best: float | None = None
    for index in range(len(ordered) - size + 1):
        window = ordered[index:index + size]
        if not _lap_numbers_are_consecutive(window):
            continue
        if not all(_is_lap_valid_for_ranking(lap)[0] for lap in window):
            continue
        values = _times(window)
        if len(values) != size:
            continue
        candidate = sum(values) / size
        best = candidate if best is None else min(best, candidate)
    return best


def _best_average_map(laps: list[LapSummary]) -> dict[str, float | None]:
    return {str(size): _best_rolling_average(laps, size) for size in STINT_WINDOW_SIZES}


def _bucket_averages(laps: list[LapSummary]) -> list[StintBucket]:
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    first_lap_number = ordered[0].lap_number if ordered else 0
    buckets: list[StintBucket] = []
    for bucket_index in range(STINT_BUCKET_COUNT):
        start_offset = bucket_index * STINT_BUCKET_SIZE + 1
        end_offset = start_offset + STINT_BUCKET_SIZE - 1
        bucket_laps = [
            lap
            for lap in ordered
            if start_offset <= lap.lap_number - first_lap_number + 1 <= end_offset
        ]
        valid = _valid_laps(bucket_laps)
        consecutive = _lap_numbers_are_consecutive(bucket_laps)
        avg = _avg(_times(valid)) if len(valid) == STINT_BUCKET_SIZE and consecutive else None
        warning = None
        if not bucket_laps:
            warning = "No laps in bucket."
        elif len(valid) < STINT_BUCKET_SIZE or not consecutive:
            warning = f"Need {STINT_BUCKET_SIZE} consecutive valid laps for this bucket."
        buckets.append(StintBucket(
            label=f"L{start_offset}-{end_offset}",
            start_offset=start_offset,
            end_offset=end_offset,
            avg_lap_time=avg,
            lap_count=len(bucket_laps),
            valid_lap_count=len(valid),
            warning=warning,
        ))

    available = [bucket.avg_lap_time for bucket in buckets if bucket.avg_lap_time is not None]
    if not available:
        return buckets
    fastest = min(available)
    return [
        bucket.model_copy(update={
            "is_fastest_bucket": bucket.avg_lap_time is not None and abs(bucket.avg_lap_time - fastest) < 0.0005,
            "delta_from_best_bucket": (bucket.avg_lap_time - fastest) if bucket.avg_lap_time is not None else None,
        })
        for bucket in buckets
    ]


def _graph_points(laps: list[LapSummary]) -> list[StintGraphPoint]:
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    first_lap_number = ordered[0].lap_number if ordered else 0
    valid_times = [
        lap.lap_time
        for lap in ordered
        if lap.lap_time is not None and _is_lap_valid_for_ranking(lap)[0]
    ]
    best_time = min(valid_times, default=None)
    rolling_source: list[float | None] = []
    points: list[StintGraphPoint] = []
    previous_lap_number: int | None = None
    for lap in ordered:
        if previous_lap_number is not None and lap.lap_number != previous_lap_number + 1:
            rolling_source = []
        valid, warning = _is_lap_valid_for_ranking(lap)
        lap_time = lap.lap_time if lap.lap_time is not None else None
        fuel = next(
            (
                float(value)
                for name in ("fuel", "fuel_left", "fuel_level", "fuel_remaining", "fuel_remaining_l")
                if isinstance((value := getattr(lap, name, None)), (int, float))
            ),
            None,
        )
        rolling_source.append(lap_time if valid else None)
        rolling_5 = None
        if len(rolling_source) >= 5:
            window = rolling_source[-5:]
            if all(value is not None for value in window):
                rolling_5 = sum(value for value in window if value is not None) / 5
        points.append(StintGraphPoint(
            stint_lap=lap.lap_number - first_lap_number + 1,
            lap_number=lap.lap_number,
            lap_time=lap_time,
            valid=valid,
            delta_to_best=lap_time - best_time if lap_time is not None and best_time is not None and valid else None,
            rolling_5=rolling_5,
            avg_speed_mph=lap.avg_speed_mph,
            max_speed_mph=lap.max_speed_mph,
            min_speed_mph=lap.min_speed_mph,
            fuel=fuel,
            invalid_reason=None if valid else warning,
            warning=None if valid else warning,
        ))
        previous_lap_number = lap.lap_number
    return points


def _third_averages(laps: list[LapSummary]) -> tuple[float | None, float | None, float | None]:
    if not laps:
        return None, None, None
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    third = max(1, len(ordered) // 3)
    early = ordered[:third]
    middle = ordered[third:2 * third]
    late = ordered[2 * third:]
    return _avg(_times(early)), _avg(_times(middle)), _avg(_times(late))


def _optional_number(lap: LapSummary, *names: str) -> float | None:
    for name in names:
        value = getattr(lap, name, None)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return None


def _max_optional(laps: list[LapSummary], *names: str) -> float | None:
    values = [
        value
        for lap in laps
        if (value := _optional_number(lap, *names)) is not None
    ]
    return max(values, default=None)


def _rising_trend(values: list[float], stable_label: str, rising_label: str, limited_label: str, threshold: float) -> str:
    if len(values) < 6:
        return limited_label
    third = max(1, len(values) // 3)
    early = _avg(values[:third])
    late = _avg(values[-third:])
    if early is None or late is None:
        return limited_label
    return rising_label if late - early > threshold else stable_label


def _inverse_rising_trend(values: list[float], stable_label: str, rising_label: str, limited_label: str, threshold: float) -> str:
    if len(values) < 6:
        return limited_label
    third = max(1, len(values) // 3)
    early = _avg(values[:third])
    late = _avg(values[-third:])
    if early is None or late is None:
        return limited_label
    return rising_label if early - late > threshold else stable_label


def _tire_trend_label(laps: list[LapSummary]) -> str:
    values = [
        value
        for lap in sorted(laps, key=lambda item: item.lap_number)
        if (value := _optional_number(lap, "tire_stress_score", "tire_temp_spread_avg", "tire_pressure_gain_avg")) is not None
    ]
    return _rising_trend(values, "tire stable", "RF tire work rising", "tire data limited", 0.25)


def _platform_trend_label(laps: list[LapSummary]) -> str:
    risk_values = [
        value
        for lap in sorted(laps, key=lambda item: item.lap_number)
        if (value := _optional_number(lap, "platform_risk_peak", "front_platform_risk_score", "whole_car_bottoming_peak")) is not None
    ]
    if risk_values:
        return _rising_trend(risk_values, "platform stable", "front contact rising", "platform data limited", 0.15)
    splitter_values = [
        value
        for lap in sorted(laps, key=lambda item: item.lap_number)
        if (value := _optional_number(lap, "min_splitter_mm")) is not None
    ]
    return _inverse_rising_trend(splitter_values, "platform stable", "front contact rising", "platform data limited", 2.0)


def _shock_trend_label(laps: list[LapSummary]) -> str:
    values = [
        value
        for lap in sorted(laps, key=lambda item: item.lap_number)
        if (value := _optional_number(lap, "shock_stress_score", "shock_activity_index_avg")) is not None
    ]
    return _rising_trend(values, "shock activity stable", "shock activity rising", "shock data limited", 0.15)


def _falloff_label(
    valid_lap_count: int,
    avg_lap_time: float | None,
    lap_time_std_dev: float | None,
    falloff_per_lap: float | None,
    early_avg: float | None,
    late_avg: float | None,
    pace_quality_score: float | None,
    setup_usefulness_score: float | None,
) -> str:
    if valid_lap_count < 10:
        return "insufficient laps"
    if avg_lap_time is None or falloff_per_lap is None:
        return "insufficient laps"
    std_ratio = (lap_time_std_dev / avg_lap_time) if lap_time_std_dev is not None and avg_lap_time > 0 else 0.0
    falloff_total = (late_avg - early_avg) if early_avg is not None and late_avg is not None else None
    if falloff_per_lap > 0.025 and valid_lap_count >= 20:
        return "late falloff"
    if falloff_total is not None and falloff_total > 0.45 and valid_lap_count < 20:
        return "strong short-run / poor long-run"
    if falloff_total is not None and falloff_total > 0.30 and (pace_quality_score or 0) < 65:
        return "early fade"
    if std_ratio > 0.007:
        return "inconsistent / noisy"
    if (
        abs(falloff_per_lap) <= 0.015
        and setup_usefulness_score is not None
        and setup_usefulness_score >= 50
    ):
        return "stable long-run"
    return "usable with caution"


def _metadata(session: SessionSummary | None) -> dict[str, str | None]:
    if session is None:
        return {
            "setup_name": None,
            "car_name": None,
            "track_name": None,
            "session_date": None,
        }
    return {
        "setup_name": session.setup_name,
        "car_name": session.car_name,
        "track_name": session.track_display_name or session.track_name,
        "session_date": session.sim_date_time or (
            session.import_time.isoformat() if hasattr(session.import_time, "isoformat") else str(session.import_time)
        ),
    }


def _build_stint_summary(
    run_id: str,
    stint_id: str,
    source_laps: list[LapSummary],
    session: SessionSummary | None,
    *,
    warnings: list[str] | None = None,
    is_primary_summary: bool = False,
    is_best_for_size: bool = False,
    display_group: str = "windows",
    display_label_short: str = "Window",
    rank_reason: str | None = None,
) -> StintSummary | None:
    if not source_laps:
        return None
    ordered = sorted(source_laps, key=lambda lap: lap.lap_number)
    valid = _valid_laps(ordered)
    lap_count = len(ordered)
    valid_count = len(valid)
    if lap_count <= 0 or valid_count / lap_count < 0.6:
        return None

    best_avg_by_size = _best_average_map(ordered)
    values = _times(valid)
    avg = _avg(values)
    best = min(values) if values else None
    worst = max(values) if values else None
    last_lap_time = next((lap.lap_time for lap in reversed(ordered) if lap.lap_time is not None), None)
    std = statistics.stdev(values) if len(values) >= 2 else (0.0 if values else None)
    continuous_valid_scope = valid_count == lap_count and _lap_numbers_are_consecutive(ordered)
    early_avg, middle_avg, late_avg = _third_averages(valid) if continuous_valid_scope else (None, None, None)
    falloff_total = (late_avg - early_avg) if early_avg is not None and late_avg is not None else None
    falloff_per_lap = falloff_total / max(1, valid_count) if falloff_total is not None else None

    tags = sorted({tag for lap in valid for tag in lap.classification_tags})
    pq = compute_pace_quality_score(
        window_size=lap_count,
        valid_lap_count=valid_count,
        classification_tags=tags,
        avg_lap_time=avg,
        lap_time_std_dev=std,
        falloff_sec_per_lap=falloff_per_lap,
        platform_risk_peak=_max_optional(valid, "platform_risk_peak", "front_platform_risk_score"),
        shock_activity_index=_max_optional(valid, "shock_activity_index_avg"),
        tire_temp_spread=_max_optional(valid, "tire_temp_spread_avg"),
        tire_pressure_gain=_max_optional(valid, "tire_pressure_gain_avg"),
    )
    consistency = score_consistency(std, avg) if std is not None else None
    stint_warnings = list(warnings or [])
    if valid_count < 10:
        stint_warnings.append("Window is shorter than 10 valid laps - long-run conclusions are limited.")
    if valid_count < lap_count:
        stint_warnings.append(f"{lap_count - valid_count} lap(s) excluded from stint summary.")
    if not _lap_numbers_are_consecutive(ordered):
        stint_warnings.append(
            "Missing lap numbers split this scope; uninterrupted falloff and component trends are withheld."
        )
    stint_warnings.extend(pq.warnings)

    label = _falloff_label(
        valid_count,
        avg,
        std,
        falloff_per_lap,
        early_avg,
        late_avg,
        pq.pace_quality_score,
        pq.setup_usefulness_score,
    )
    return StintSummary(
        stint_id=stint_id,
        run_id=run_id,
        setup_name=session.setup_name if session else None,
        car_name=session.car_name if session else None,
        track_name=(session.track_display_name or session.track_name) if session else None,
        session_date=(
            session.sim_date_time
            or (
                session.import_time.isoformat()
                if hasattr(session.import_time, "isoformat")
                else str(session.import_time)
            )
            if session
            else None
        ),
        start_lap=ordered[0].lap_number,
        end_lap=ordered[-1].lap_number,
        lap_count=lap_count,
        valid_lap_count=valid_count,
        last_lap_time=last_lap_time,
        avg_lap_time=avg,
        best_lap_time=best,
        worst_lap_time=worst,
        lap_time_std_dev=std,
        best_avg_by_size=best_avg_by_size,
        rolling_3_avg_best=best_avg_by_size["3"],
        rolling_5_avg_best=best_avg_by_size["5"],
        rolling_7_avg_best=best_avg_by_size["7"],
        rolling_10_avg_best=best_avg_by_size["10"],
        rolling_15_avg_best=best_avg_by_size["15"],
        rolling_20_avg_best=best_avg_by_size["20"],
        rolling_25_avg_best=best_avg_by_size["25"],
        rolling_30_avg_best=best_avg_by_size["30"],
        rolling_40_avg_best=best_avg_by_size["40"],
        rolling_50_avg_best=best_avg_by_size["50"],
        rolling_60_avg_best=best_avg_by_size["60"],
        falloff_total=falloff_total,
        falloff_per_lap=falloff_per_lap,
        early_avg=early_avg,
        middle_avg=middle_avg,
        late_avg=late_avg,
        consistency_score=consistency,
        pace_quality_score=pq.pace_quality_score,
        evidence_confidence_score=pq.evidence_confidence_score,
        setup_usefulness_score=pq.setup_usefulness_score,
        bucket_averages=_bucket_averages(ordered),
        lap_points=_graph_points(ordered),
        is_primary_summary=is_primary_summary,
        is_best_for_size=is_best_for_size,
        display_group=display_group,
        display_label_short=display_label_short,
        rank_reason=rank_reason,
        tire_trend_label=_tire_trend_label(valid) if continuous_valid_scope else "tire data limited",
        platform_trend_label=_platform_trend_label(valid) if continuous_valid_scope else "platform data limited",
        shock_trend_label=_shock_trend_label(valid) if continuous_valid_scope else "shock data limited",
        stint_label=label,
        warnings=sorted(set(stint_warnings)),
    )


def _build_run_summary(
    *,
    run_id: str,
    ordered: list[LapSummary],
    valid: list[LapSummary],
    session: SessionSummary | None,
    full_stint: StintSummary | None,
    best_window_cards: list[StintSummary],
    warnings: list[str],
) -> StintRunSummary:
    card_by_size = {card.lap_count: card for card in best_window_cards if card.is_best_for_size}
    best_avg_by_size = {
        str(size): (card.avg_lap_time if (card := card_by_size.get(size)) is not None else None)
        for size in STINT_WINDOW_SIZES
    }
    return StintRunSummary(
        run_id=run_id,
        setup_name=session.setup_name if session else None,
        car_name=session.car_name if session else None,
        track_name=session.track_display_name or session.track_name if session else None,
        session_date=session.import_time.isoformat() if session else None,
        total_laps=len(ordered),
        valid_laps=len(valid),
        best_lap_time=min(_times(valid), default=None),
        full_stint_avg=None if full_stint is None else full_stint.avg_lap_time,
        falloff_total=None if full_stint is None else full_stint.falloff_total,
        best_avg_by_size=best_avg_by_size,
        best_3_avg=best_avg_by_size["3"],
        best_5_avg=best_avg_by_size["5"],
        best_7_avg=best_avg_by_size["7"],
        best_10_avg=best_avg_by_size["10"],
        best_15_avg=best_avg_by_size["15"],
        best_20_avg=best_avg_by_size["20"],
        best_25_avg=best_avg_by_size["25"],
        best_30_avg=best_avg_by_size["30"],
        best_40_avg=best_avg_by_size["40"],
        best_50_avg=best_avg_by_size["50"],
        best_60_avg=best_avg_by_size["60"],
        data_status="Ready" if full_stint is not None and len(warnings) == 0 else "Limited",
        warnings=warnings,
    )


def _with_highlight_metadata(stints: list[StintSummary]) -> list[StintSummary]:
    if not stints:
        return stints
    best_lap = min((stint.best_lap_time for stint in stints if stint.best_lap_time is not None), default=None)
    top_ev = max((stint.setup_usefulness_score for stint in stints if stint.setup_usefulness_score is not None), default=None)
    long_run_size = max(
        (
            size
            for size in STINT_WINDOW_SIZES
            if size >= MIN_LONG_RUN_WINDOW_SIZE
            if any(stint.best_avg_by_size.get(str(size)) is not None for stint in stints)
        ),
        default=None,
    )
    best_by_size = {
        size: min(
            (
                value
                for stint in stints
                if (value := stint.best_avg_by_size.get(str(size))) is not None
            ),
            default=None,
        )
        for size in STINT_WINDOW_SIZES
    }
    highlighted: list[StintSummary] = []
    for stint in stints:
        tags = set(stint.highlight_tags)
        size_flags = set(stint.best_average_size_flags)
        if best_lap is not None and stint.best_lap_time is not None and abs(stint.best_lap_time - best_lap) < 0.0005:
            tags.add("fastest_lap")
        for size, best_avg in best_by_size.items():
            value = stint.best_avg_by_size.get(str(size))
            if best_avg is not None and value is not None and abs(value - best_avg) < 0.0005:
                tags.add(f"best_{size}")
                size_flags.add(size)
        is_best_long_run = False
        if long_run_size is not None:
            value = stint.best_avg_by_size.get(str(long_run_size))
            long_best = best_by_size.get(long_run_size)
            is_best_long_run = value is not None and long_best is not None and abs(value - long_best) < 0.0005
            if is_best_long_run:
                tags.add("best_long_run")
        if top_ev is not None and stint.setup_usefulness_score is not None and abs(stint.setup_usefulness_score - top_ev) < 0.0005:
            tags.add("top_setup_ev")
        highlighted.append(stint.model_copy(update={
            "is_best_fastest_lap": "fastest_lap" in tags,
            "best_average_size_flags": sorted(size_flags),
            "is_best_long_run": is_best_long_run,
            "highlight_tags": sorted(tags),
        }))
    return highlighted


def build_stint_response(laps: list[LapSummary], session: SessionSummary | None = None) -> StintResponse:
    if not laps:
        return StintResponse(run_id="", warnings=["No lap data available."])
    run_id = laps[0].run_id
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    stint_rows: list[StintSummary] = []
    best_window_cards: list[StintSummary] = []
    all_windows: list[StintSummary] = []
    seen_windows: set[tuple[int, int, int]] = set()

    valid = _valid_laps(ordered)
    valid_ratio = len(valid) / len(ordered) if ordered else 0.0
    warnings: list[str] = []
    if len(valid) < 3:
        warnings.extend([
            f"No eligible stint windows yet. Only {len(valid)} valid lap{'s' if len(valid) != 1 else ''}; need at least 3 valid laps for short windows.",
            "Need at least 3 valid laps to start short-run averages.",
            "Need 10+ uninterrupted valid laps for a preliminary tire and pace review.",
            "Need 20+ uninterrupted valid laps before race-run or best-long-run labels.",
            "Need 50/60 valid laps for 50/60-lap averages.",
            "Out laps, pit laps, cooldowns, wrecks, and invalid laps are excluded.",
            "Import or select a longer clean run to unlock Stint Intelligence.",
        ])
    if valid_ratio < 0.6:
        warnings.append("Fewer than 60% of run laps are valid for stint analysis.")

    if len(valid) >= 3 and valid_ratio >= 0.6:
        summary = _build_stint_summary(
            run_id,
            f"stint_{run_id}_full_{ordered[0].lap_number}_{ordered[-1].lap_number}",
            ordered,
            session,
            is_primary_summary=True,
            display_group="full_run",
            display_label_short="Full run",
            rank_reason="Full imported run with valid-lap filtering.",
        )
        if summary is not None:
            stint_rows.append(summary)

    for group in compute_best_windows(ordered, STINT_WINDOW_SIZES):
        for index, window in enumerate(group.windows):
            window_laps = [lap for lap in ordered if window.start_lap <= lap.lap_number <= window.end_lap]
            key = (window.start_lap, window.end_lap, window.window_size)
            if key in seen_windows:
                continue
            summary = _build_stint_summary(
                run_id,
                f"stint_{run_id}_w{window.window_size}_{window.start_lap}_{window.end_lap}",
                window_laps,
                session,
                warnings=[f"Ranked #{index + 1} {window.window_size}-lap imported-data window."],
                is_primary_summary=index == 0,
                is_best_for_size=index == 0,
                display_group=f"best_{window.window_size}",
                display_label_short=f"Best {window.window_size}",
                rank_reason=f"Best average {window.window_size}-lap window." if index == 0 else f"Alternate #{index + 1} {window.window_size}-lap window.",
            )
            if summary is not None:
                all_windows.append(summary)
                if index == 0:
                    best_window_cards.append(summary)
                seen_windows.add(key)

    size_order = {"full_run": 0, **{f"best_{size}": index + 1 for index, size in enumerate(STINT_WINDOW_SIZES)}}
    stint_rows.sort(key=lambda item: (size_order.get(item.display_group, 99), item.avg_lap_time or 999999.0))
    best_window_cards.sort(key=lambda item: (size_order.get(item.display_group, 99), item.avg_lap_time or 999999.0))
    all_windows.sort(key=lambda item: (size_order.get(item.display_group, 99), item.avg_lap_time or 999999.0))
    if not stint_rows and not warnings:
        warnings.append("No eligible stint windows yet.")
        warnings.append("Need at least 3 valid laps to start short-run averages.")
        warnings.append("Need 10+ uninterrupted valid laps for a preliminary tire and pace review.")
        warnings.append("Need 20+ uninterrupted valid laps before race-run or best-long-run labels.")
        warnings.append("Need 50/60 valid laps for 50/60-lap averages.")
        warnings.append("Out laps, pit laps, cooldowns, wrecks, and invalid laps are excluded.")
        warnings.append("Import or select a longer clean run to unlock Stint Intelligence.")
    highlighted = _with_highlight_metadata([*stint_rows, *best_window_cards])
    highlighted_by_id = {stint.stint_id: stint for stint in highlighted}
    stint_rows = [highlighted_by_id.get(stint.stint_id, stint) for stint in stint_rows]
    best_window_cards = [highlighted_by_id.get(stint.stint_id, stint) for stint in best_window_cards]
    all_windows = [
        highlighted_by_id.get(stint.stint_id, stint.model_copy(update={
            "best_average_size_flags": [stint.lap_count] if stint.is_best_for_size else [],
            "highlight_tags": [f"best_{stint.lap_count}"] if stint.is_best_for_size else [],
        }))
        for stint in all_windows
    ]
    run_summary = _build_run_summary(
        run_id=run_id,
        ordered=ordered,
        valid=valid,
        session=session,
        full_stint=stint_rows[0] if stint_rows else None,
        best_window_cards=best_window_cards,
        warnings=warnings,
    )
    return StintResponse(
        run_id=run_id,
        stints=stint_rows,
        stint_rows=stint_rows,
        best_window_cards=best_window_cards,
        primary_stints=stint_rows,
        all_windows=all_windows,
        run_summary=run_summary,
        warnings=warnings,
    )


def _delta(test: float | None, baseline: float | None) -> float | None:
    return None if test is None or baseline is None else test - baseline


def _trend_delta(test: str, baseline: str) -> str:
    if "limited" in test or "limited" in baseline:
        return "limited"
    return f"similar: {test}" if test == baseline else f"{baseline} -> {test}"


def _stint_scope_is_uninterrupted(stint: StintSummary) -> bool:
    if (
        stint.valid_lap_count != stint.lap_count
        or stint.end_lap - stint.start_lap + 1 != stint.lap_count
    ):
        return False
    if not stint.lap_points:
        return True
    ordered_points = sorted(stint.lap_points, key=lambda point: point.lap_number)
    return (
        len(ordered_points) == stint.lap_count
        and ordered_points[0].lap_number == stint.start_lap
        and ordered_points[-1].lap_number == stint.end_lap
        and all(point.valid for point in ordered_points)
        and all(
            current.lap_number == previous.lap_number + 1
            for previous, current in zip(ordered_points, ordered_points[1:])
        )
    )


def compare_stints(baseline: StintSummary, test: StintSummary) -> StintCompareResult:
    uninterrupted = _stint_scope_is_uninterrupted(baseline) and _stint_scope_is_uninterrupted(test)
    avg_delta = _delta(test.avg_lap_time, baseline.avg_lap_time) if uninterrupted else None
    best_delta = _delta(test.best_lap_time, baseline.best_lap_time)
    rolling_5_delta = _delta(test.rolling_5_avg_best, baseline.rolling_5_avg_best) if uninterrupted else None
    rolling_10_delta = _delta(test.rolling_10_avg_best, baseline.rolling_10_avg_best) if uninterrupted else None
    rolling_20_delta = _delta(test.rolling_20_avg_best, baseline.rolling_20_avg_best) if uninterrupted else None
    rolling_delta_by_size = {
        str(size): (
            _delta(test.best_avg_by_size.get(str(size)), baseline.best_avg_by_size.get(str(size)))
            if uninterrupted
            else None
        )
        for size in STINT_WINDOW_SIZES
    }
    comparison_warnings: list[str] = []
    if not uninterrupted:
        comparison_warnings.append(
            "Uninterrupted stint comparison is unavailable; select consecutive clean windows without missing or excluded laps."
        )
    same_length_avg_delta = avg_delta if uninterrupted and baseline.lap_count == test.lap_count else None
    if baseline.lap_count != test.lap_count:
        comparison_warnings.append(
            f"Overall average delta is cross-length ({baseline.lap_count} laps vs {test.lap_count} laps); same-length average delta is unavailable."
        )
    falloff_delta = _delta(test.falloff_total, baseline.falloff_total) if uninterrupted else None
    consistency_delta = _delta(test.consistency_score, baseline.consistency_score) if uninterrupted else None
    baseline_buckets = {bucket.label: bucket for bucket in baseline.bucket_averages}
    test_buckets = {bucket.label: bucket for bucket in test.bucket_averages}
    labels = [bucket.label for bucket in baseline.bucket_averages] or [bucket.label for bucket in test.bucket_averages]
    bucket_deltas: list[StintBucketDelta] = []
    for label in labels:
        baseline_bucket = baseline_buckets.get(label)
        test_bucket = test_buckets.get(label)
        baseline_avg = baseline_bucket.avg_lap_time if baseline_bucket else None
        test_avg = test_bucket.avg_lap_time if test_bucket else None
        warning = (
            None
            if uninterrupted and baseline_avg is not None and test_avg is not None
            else "Bucket delta unavailable for a split or incomplete stint scope."
        )
        bucket_deltas.append(StintBucketDelta(
            label=label,
            baseline_avg=baseline_avg,
            test_avg=test_avg,
            delta=_delta(test_avg, baseline_avg) if uninterrupted else None,
            warning=warning,
        ))
    best_bucket_delta = min((bucket.delta for bucket in bucket_deltas if bucket.delta is not None), default=None)

    if not uninterrupted:
        verdict = "Stint comparison withheld; select uninterrupted clean windows."
    elif baseline.valid_lap_count < 5 or test.valid_lap_count < 5:
        verdict = "Data is limited; need more clean laps."
    elif avg_delta is not None and avg_delta < -0.05 and falloff_delta is not None and falloff_delta > 0.15:
        verdict = "Test stint is faster early but falls off harder."
    elif avg_delta is not None and avg_delta > 0.05 and falloff_delta is not None and falloff_delta < -0.10:
        verdict = "Baseline is faster, but test is more stable over the run."
    elif rolling_20_delta is not None and rolling_20_delta < -0.05 and (falloff_delta is None or abs(falloff_delta) <= 0.20):
        verdict = "Test keeps better 20-lap pace."
    elif rolling_10_delta is not None and rolling_10_delta < -0.05 and (falloff_delta is None or abs(falloff_delta) <= 0.15):
        verdict = "Test shows better 10-lap pace with similar falloff."
    elif consistency_delta is not None and consistency_delta > 5 and (avg_delta is None or avg_delta > -0.05):
        verdict = "Test is more consistent, but pace gain is not clear."
    elif avg_delta is not None and avg_delta < -0.05:
        verdict = "Test stint is faster on average."
    elif avg_delta is not None and avg_delta > 0.05:
        verdict = "Baseline stint is faster on average."
    else:
        verdict = "Stints are closely matched with available data."

    summary_parts: list[str] = []
    if avg_delta is not None:
        summary_parts.append(f"Average delta {avg_delta:+.3f}s.")
    if rolling_10_delta is not None:
        summary_parts.append(f"Best 10-lap delta {rolling_10_delta:+.3f}s.")
    if best_bucket_delta is not None:
        summary_parts.append(f"Best bucket delta {best_bucket_delta:+.3f}s.")
    if falloff_delta is not None:
        summary_parts.append(f"Falloff delta {falloff_delta:+.3f}s.")
    summary = (
        "Stint comparison is withheld because at least one scope contains a missing or excluded lap."
        if not uninterrupted
        else " ".join(summary_parts)
        if summary_parts
        else "Stint comparison is limited by available clean lap data."
    )

    return StintCompareResult(
        baseline_stint=baseline,
        test_stint=test,
        avg_delta=avg_delta,
        best_delta=best_delta,
        rolling_5_delta=rolling_5_delta,
        rolling_10_delta=rolling_10_delta,
        rolling_20_delta=rolling_20_delta,
        same_length_avg_delta=same_length_avg_delta,
        rolling_delta_by_size=rolling_delta_by_size,
        comparison_warnings=comparison_warnings,
        bucket_deltas=bucket_deltas,
        falloff_delta=falloff_delta,
        consistency_delta=consistency_delta,
        tire_trend_delta=_trend_delta(test.tire_trend_label, baseline.tire_trend_label),
        platform_trend_delta=_trend_delta(test.platform_trend_label, baseline.platform_trend_label),
        shock_trend_delta=_trend_delta(test.shock_trend_label, baseline.shock_trend_label),
        verdict=verdict,
        summary=summary,
    )
