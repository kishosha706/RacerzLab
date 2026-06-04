"""Imported-data stint summaries and stint-to-stint comparison."""

from __future__ import annotations

import statistics
from typing import Iterable

from racelab_engine.analysis.lap_windows import _is_lap_valid_for_ranking, compute_best_windows
from racelab_engine.analysis.pace_quality import compute_pace_quality_score, score_consistency
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import (
    StintCompareResult,
    StintResponse,
    StintSummary,
)
from racelab_engine.models.session import SessionSummary

STINT_WINDOW_SIZES = [5, 10, 20, 30, 40]


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
        tire_trend_label=_tire_trend_label(valid),
        platform_trend_label=_platform_trend_label(valid),
        shock_trend_label=_shock_trend_label(valid),
        stint_label=label,
        warnings=sorted(set(stint_warnings)),
    )


def build_stint_response(laps: list[LapSummary], session: SessionSummary | None = None) -> StintResponse:
    if not laps:
        return StintResponse(run_id="", warnings=["No lap data available."])
    run_id = laps[0].run_id
    ordered = sorted(laps, key=lambda lap: lap.lap_number)
    stints: list[StintSummary] = []
    seen: set[tuple[int, int, int]] = set()

    valid = _valid_laps(ordered)
    valid_ratio = len(valid) / len(ordered) if ordered else 0.0
    warnings: list[str] = []
    if len(valid) < 5:
        warnings.append(f"Only {len(valid)} valid lap{'s' if len(valid) != 1 else ''}. Need 5+ for stint intelligence.")
    if valid_ratio < 0.6:
        warnings.append("Fewer than 60% of run laps are valid for stint analysis.")

    if len(valid) >= 5 and valid_ratio >= 0.6:
        summary = _build_stint_summary(run_id, f"stint_{run_id}_full_{ordered[0].lap_number}_{ordered[-1].lap_number}", ordered, session)
        if summary is not None:
            stints.append(summary)
            seen.add((summary.start_lap, summary.end_lap, summary.lap_count))

    for group in compute_best_windows(ordered, STINT_WINDOW_SIZES):
        for index, window in enumerate(group.windows):
            window_laps = [lap for lap in ordered if window.start_lap <= lap.lap_number <= window.end_lap]
            key = (window.start_lap, window.end_lap, window.window_size)
            if key in seen:
                continue
            summary = _build_stint_summary(
                run_id,
                f"stint_{run_id}_w{window.window_size}_{window.start_lap}_{window.end_lap}",
                window_laps,
                session,
                warnings=[f"Ranked #{index + 1} {window.window_size}-lap imported-data window."],
            )
            if summary is not None:
                stints.append(summary)
                seen.add(key)

    stints.sort(key=lambda item: (0 if "_full_" in item.stint_id else 1, -item.lap_count, item.avg_lap_time or 999999.0))
    if not stints and not warnings:
        warnings.append("No stint windows met the 60% valid-lap requirement.")
    return StintResponse(run_id=run_id, stints=stints, warnings=warnings)


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

    if baseline.valid_lap_count < 5 or test.valid_lap_count < 5:
        verdict = "Data is limited; need more clean laps."
    elif avg_delta is not None and avg_delta < -0.05 and falloff_delta is not None and falloff_delta > 0.15:
        verdict = "Test stint is faster early but falls off harder."
    elif avg_delta is not None and avg_delta > 0.05 and falloff_delta is not None and falloff_delta < -0.10:
        verdict = "Baseline is faster, but test is more stable over the run."
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
        falloff_delta=falloff_delta,
        consistency_delta=consistency_delta,
        tire_trend_delta=_trend_delta(test.tire_trend_label, baseline.tire_trend_label),
        platform_trend_delta=_trend_delta(test.platform_trend_label, baseline.platform_trend_label),
        shock_trend_delta=_trend_delta(test.shock_trend_label, baseline.shock_trend_label),
        verdict=verdict,
        summary=summary,
    )
