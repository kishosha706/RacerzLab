"""Imported-data stint summaries and stint-to-stint comparison."""

from __future__ import annotations

import statistics
from typing import Iterable

from racelab_engine.analysis.lap_windows import _is_lap_valid_for_ranking, compute_best_windows
from racelab_engine.analysis.pace_quality import compute_pace_quality_score, score_consistency
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import (
    StintBucket,
    StintBucketDelta,
    StintCompareResult,
    StintResponse,
    StintRunSummary,
    StintSummary,
)
from racelab_engine.models.session import SessionSummary

STINT_WINDOW_SIZES = [5, 10, 20, 30, 40]
STINT_BUCKET_SIZE = 5
STINT_BUCKET_COUNT = 8


def _avg(values: Iterable[float]) -> float | None:
    items = [value for value in values if value is not None]
    return sum(items) / len(items) if items else None


def _valid_laps(laps: Iterable[LapSummary]) -> list[LapSummary]:
    return [lap for lap in laps if _is_lap_valid_for_ranking(lap)[0]]


def _times(laps: Iterable[LapSummary]) -> list[float]:
    return [lap.lap_time for lap in laps if lap.lap_time is not None]


def _best_rolling_average(laps: list[LapSummary], size: int) -> float | None:
    if len(laps) < size:
        return None
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    best: float | None = None
    for index in range(len(ordered) - size + 1):
        window = ordered[index:index + size]
        values = _times(window)
        if len(values) < size:
            continue
        candidate = sum(values) / size
        best = candidate if best is None else min(best, candidate)
    return best


def _bucket_averages(laps: list[LapSummary]) -> list[StintBucket]:
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    buckets: list[StintBucket] = []
    for bucket_index in range(STINT_BUCKET_COUNT):
        start_offset = bucket_index * STINT_BUCKET_SIZE + 1
        end_offset = start_offset + STINT_BUCKET_SIZE - 1
        bucket_laps = ordered[bucket_index * STINT_BUCKET_SIZE:(bucket_index + 1) * STINT_BUCKET_SIZE]
        valid = _valid_laps(bucket_laps)
        avg = _avg(_times(valid)) if len(valid) == STINT_BUCKET_SIZE else None
        warning = None
        if not bucket_laps:
            warning = "No laps in bucket."
        elif len(valid) < STINT_BUCKET_SIZE:
            warning = f"Need {STINT_BUCKET_SIZE} valid laps for this bucket."
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
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _max_optional(laps: list[LapSummary], *names: str) -> float | None:
    values = [
        value
        for lap in laps
        if (value := _optional_number(lap, *names)) is not None
    ]
    return max(values) if values else None


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
    if abs(falloff_per_lap) <= 0.015 and (setup_usefulness_score or 0) >= 50:
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

    values = _times(valid)
    avg = _avg(values)
    best = min(values) if values else None
    worst = max(values) if values else None
    std = statistics.stdev(values) if len(values) >= 2 else (0.0 if values else None)
    early_avg, middle_avg, late_avg = _third_averages(valid)
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
    meta = _metadata(session)
    return StintSummary(
        stint_id=stint_id,
        run_id=run_id,
        **meta,
        start_lap=ordered[0].lap_number,
        end_lap=ordered[-1].lap_number,
        lap_count=lap_count,
        valid_lap_count=valid_count,
        avg_lap_time=avg,
        best_lap_time=best,
        worst_lap_time=worst,
        lap_time_std_dev=std,
        rolling_5_avg_best=_best_rolling_average(valid, 5),
        rolling_10_avg_best=_best_rolling_average(valid, 10),
        rolling_20_avg_best=_best_rolling_average(valid, 20),
        rolling_30_avg_best=_best_rolling_average(valid, 30),
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
        is_primary_summary=is_primary_summary,
        is_best_for_size=is_best_for_size,
        display_group=display_group,
        display_label_short=display_label_short,
        rank_reason=rank_reason,
        tire_trend_label=_tire_trend_label(valid),
        platform_trend_label=_platform_trend_label(valid),
        shock_trend_label=_shock_trend_label(valid),
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
    return StintRunSummary(
        run_id=run_id,
        setup_name=session.setup_name if session else None,
        car_name=session.car_name if session else None,
        track_name=session.track_display_name or session.track_name if session else None,
        session_date=session.import_time.isoformat() if session else None,
        total_laps=len(ordered),
        valid_laps=len(valid),
        best_lap_time=min(_times(valid), default=None),
        full_stint_avg=full_stint.avg_lap_time if full_stint else None,
        falloff_total=full_stint.falloff_total if full_stint else None,
        best_5_avg=card_by_size.get(5).avg_lap_time if card_by_size.get(5) else None,
        best_10_avg=card_by_size.get(10).avg_lap_time if card_by_size.get(10) else None,
        best_20_avg=card_by_size.get(20).avg_lap_time if card_by_size.get(20) else None,
        best_30_avg=card_by_size.get(30).avg_lap_time if card_by_size.get(30) else None,
        best_40_avg=card_by_size.get(40).avg_lap_time if card_by_size.get(40) else None,
        data_status="Ready" if full_stint is not None and len(warnings) == 0 else "Limited",
        warnings=warnings,
    )


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
    if len(valid) < 5:
        warnings.append(f"No eligible stint windows yet. Only {len(valid)} valid lap{'s' if len(valid) != 1 else ''}; need at least 5 valid laps for short windows.")
        warnings.append("Need 10+ valid laps for a useful long-run read.")
        warnings.append("Out laps, pit laps, cooldowns, wrecks, and invalid laps are excluded.")
        warnings.append("Import or select a longer clean run to unlock Stint Intelligence.")
    if valid_ratio < 0.6:
        warnings.append("Fewer than 60% of run laps are valid for stint analysis.")

    if len(valid) >= 5 and valid_ratio >= 0.6:
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

    size_order = {"full_run": 0, "best_5": 1, "best_10": 2, "best_20": 3, "best_30": 4, "best_40": 5}
    stint_rows.sort(key=lambda item: (size_order.get(item.display_group, 99), item.avg_lap_time or 999999.0))
    best_window_cards.sort(key=lambda item: (size_order.get(item.display_group, 99), item.avg_lap_time or 999999.0))
    all_windows.sort(key=lambda item: (size_order.get(item.display_group, 99), item.avg_lap_time or 999999.0))
    if not stint_rows and not warnings:
        warnings.append("No eligible stint windows yet.")
        warnings.append("Need at least 5 valid laps for short windows.")
        warnings.append("Need 10+ valid laps for a useful long-run read.")
        warnings.append("Out laps, pit laps, cooldowns, wrecks, and invalid laps are excluded.")
        warnings.append("Import or select a longer clean run to unlock Stint Intelligence.")
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
    if test is None or baseline is None:
        return None
    return test - baseline


def _trend_delta(test: str, baseline: str) -> str:
    if "limited" in test or "limited" in baseline:
        return "limited"
    if test == baseline:
        return f"similar: {test}"
    return f"{baseline} -> {test}"


def compare_stints(baseline: StintSummary, test: StintSummary) -> StintCompareResult:
    avg_delta = _delta(test.avg_lap_time, baseline.avg_lap_time)
    best_delta = _delta(test.best_lap_time, baseline.best_lap_time)
    rolling_5_delta = _delta(test.rolling_5_avg_best, baseline.rolling_5_avg_best)
    rolling_10_delta = _delta(test.rolling_10_avg_best, baseline.rolling_10_avg_best)
    rolling_20_delta = _delta(test.rolling_20_avg_best, baseline.rolling_20_avg_best)
    falloff_delta = _delta(test.falloff_total, baseline.falloff_total)
    consistency_delta = _delta(test.consistency_score, baseline.consistency_score)
    baseline_buckets = {bucket.label: bucket for bucket in baseline.bucket_averages}
    test_buckets = {bucket.label: bucket for bucket in test.bucket_averages}
    labels = [bucket.label for bucket in baseline.bucket_averages] or [bucket.label for bucket in test.bucket_averages]
    bucket_deltas: list[StintBucketDelta] = []
    for label in labels:
        baseline_bucket = baseline_buckets.get(label)
        test_bucket = test_buckets.get(label)
        baseline_avg = baseline_bucket.avg_lap_time if baseline_bucket else None
        test_avg = test_bucket.avg_lap_time if test_bucket else None
        warning = None if baseline_avg is not None and test_avg is not None else "Bucket delta unavailable."
        bucket_deltas.append(StintBucketDelta(
            label=label,
            baseline_avg=baseline_avg,
            test_avg=test_avg,
            delta=_delta(test_avg, baseline_avg),
            warning=warning,
        ))
    best_bucket_delta = min((bucket.delta for bucket in bucket_deltas if bucket.delta is not None), default=None)

    if baseline.valid_lap_count < 5 or test.valid_lap_count < 5:
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
    summary = " ".join(summary_parts) if summary_parts else "Stint comparison is limited by available clean lap data."

    return StintCompareResult(
        baseline_stint=baseline,
        test_stint=test,
        avg_delta=avg_delta,
        best_delta=best_delta,
        rolling_5_delta=rolling_5_delta,
        rolling_10_delta=rolling_10_delta,
        rolling_20_delta=rolling_20_delta,
        bucket_deltas=bucket_deltas,
        falloff_delta=falloff_delta,
        consistency_delta=consistency_delta,
        tire_trend_delta=_trend_delta(test.tire_trend_label, baseline.tire_trend_label),
        platform_trend_delta=_trend_delta(test.platform_trend_label, baseline.platform_trend_label),
        shock_trend_delta=_trend_delta(test.shock_trend_label, baseline.shock_trend_label),
        verdict=verdict,
        summary=summary,
    )
