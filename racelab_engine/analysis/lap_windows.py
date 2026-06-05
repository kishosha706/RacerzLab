"""
Lap window analysis: fastest individual laps, best consecutive windows, degradation.
"""

from __future__ import annotations

import statistics
from typing import Any

from racelab_engine.analysis.pace_quality import compute_pace_quality_score
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import (
    BestWindowGroup,
    FastestLapGroup,
    LapDegradationSummary,
    LapQualitySummary,
    LapWindowSummary,
    LapWindowsResponse,
)


def _is_lap_valid_for_ranking(lap: LapSummary) -> tuple[bool, str | None]:
    if not lap.is_complete:
        return False, "Incomplete lap"
    if not lap.is_useful:
        return False, "Not useful"
    tags = [t.upper() for t in lap.classification_tags]
    if "OUT_LAP" in tags:
        return False, "Out lap"
    if "COOLDOWN" in tags:
        return False, "Cooldown lap"
    if "PIT_ROAD" in tags:
        return False, "Pit road"
    if "WRECK_OR_SPIN" in tags:
        return False, "Wreck or spin"
    if "INVALID_SPEED_EVENT" in tags:
        return False, "Invalid speed event"
    if lap.lap_time is None or lap.lap_time <= 0:
        return False, "No lap time"
    return True, None


def _to_quality_summary(lap: LapSummary) -> LapQualitySummary:
    return LapQualitySummary(
        run_id=lap.run_id,
        lap_number=lap.lap_number,
        lap_time=lap.lap_time,
        lap_type=lap.lap_type,
        is_complete=lap.is_complete,
        is_useful=lap.is_useful,
        classification_tags=list(lap.classification_tags),
        avg_speed_mph=lap.avg_speed_mph,
        max_speed_mph=lap.max_speed_mph,
        min_speed_mph=lap.min_speed_mph,
        min_splitter_mm=lap.min_splitter_mm,
    )


def _compute_window_stats(laps: list[LapSummary]) -> dict[str, Any]:
    times = [la.lap_time for la in laps if la.lap_time is not None]
    if not times:
        return {"avg": None, "fastest": None, "slowest": None, "std": None}

    n = len(times)
    avg = sum(times) / n
    fastest = min(times)
    slowest = max(times)
    std = statistics.stdev(times) if n >= 2 else 0.0
    third = n // 3 or 1
    first_third = sum(times[:third]) / third
    last_third = sum(times[-third:]) / third
    falloff = last_third - first_third
    falloff_per_lap = falloff / n
    return {"avg": avg, "fastest": fastest, "slowest": slowest, "std": std, "falloff": falloff, "falloff_per_lap": falloff_per_lap}


def compute_fastest_groups(laps: list[LapSummary], sizes: list[int] | None = None) -> list[FastestLapGroup]:
    if sizes is None:
        sizes = [10, 20, 30, 40]

    valid = [lap for lap in laps if _is_lap_valid_for_ranking(lap)[0]]
    valid.sort(key=lambda la: la.lap_time or 999999.0)
    groups: list[FastestLapGroup] = []

    for size in sizes:
        selected = valid[:size]
        if len(selected) < size:
            groups.append(FastestLapGroup(
                label=f"Fastest {size} Laps",
                lap_count=size,
                is_available=False,
                warning=f"Unavailable - only {len(valid)} valid lap{'s' if len(valid) != 1 else ''}.",
            ))
            continue

        stats = _compute_window_stats(selected)
        tags = list({t for la in selected for t in la.classification_tags})
        pq = compute_pace_quality_score(
            window_size=size,
            valid_lap_count=len(selected),
            classification_tags=tags,
            avg_lap_time=stats["avg"],
            lap_time_std_dev=stats["std"],
            falloff_sec_per_lap=stats["falloff_per_lap"],
            is_fastest_group=True,
        )
        groups.append(FastestLapGroup(
            label=f"Fastest {size} Laps",
            lap_count=size,
            laps=[_to_quality_summary(la) for la in selected],
            average_lap_time=stats["avg"],
            fastest_lap_time=stats["fastest"],
            slowest_lap_time=stats["slowest"],
            is_available=True,
            pace_quality_score=pq.pace_quality_score,
            pace_quality_label=pq.pace_quality_label,
            evidence_confidence_score=pq.evidence_confidence_score,
            evidence_confidence_label=pq.evidence_confidence_label,
            setup_usefulness_score=pq.setup_usefulness_score,
            setup_usefulness_label=pq.setup_usefulness_label,
            pace_quality_warnings=pq.warnings,
            pace_quality_components=pq.component_scores,
        ))
    return groups


def compute_best_windows(laps: list[LapSummary], sizes: list[int] | None = None) -> list[BestWindowGroup]:
    if sizes is None:
        sizes = [5, 10, 20, 30, 40]
    sorted_laps = sorted(laps, key=lambda la: la.lap_number)
    valid_map: dict[int, bool] = {}
    reason_map: dict[int, str | None] = {}
    for lap in sorted_laps:
        ok, reason = _is_lap_valid_for_ranking(lap)
        valid_map[lap.lap_number] = ok
        reason_map[lap.lap_number] = reason

    groups: list[BestWindowGroup] = []
    for size in sizes:
        windows: list[LapWindowSummary] = []
        for i in range(len(sorted_laps) - size + 1):
            window_laps = sorted_laps[i:i + size]
            excluded: list[dict[str, Any]] = []
            valid_window_laps: list[LapSummary] = []
            for wl in window_laps:
                if valid_map.get(wl.lap_number, False):
                    valid_window_laps.append(wl)
                else:
                    excluded.append({"lap_number": wl.lap_number, "reason": reason_map.get(wl.lap_number, "Unknown")})
            if len(valid_window_laps) < size * 0.6:
                continue
            stats = _compute_window_stats(valid_window_laps)
            if stats["avg"] is None:
                continue
            tags: list[str] = []
            for wl in valid_window_laps:
                tags.extend(wl.classification_tags)
            tags = list(set(tags))
            pq = compute_pace_quality_score(
                window_size=size,
                valid_lap_count=len(valid_window_laps),
                classification_tags=tags,
                avg_lap_time=stats["avg"],
                lap_time_std_dev=stats["std"],
                falloff_sec_per_lap=stats["falloff_per_lap"],
            )
            windows.append(LapWindowSummary(
                window_id=f"window_{sorted_laps[0].run_id}_{window_laps[0].lap_number}_{window_laps[-1].lap_number}",
                run_id=sorted_laps[0].run_id,
                start_lap=window_laps[0].lap_number,
                end_lap=window_laps[-1].lap_number,
                window_size=size,
                total_time=sum(wl.lap_time for wl in valid_window_laps if wl.lap_time is not None),
                average_lap_time=stats["avg"],
                fastest_lap_time=stats["fastest"],
                slowest_lap_time=stats["slowest"],
                lap_time_std_dev=stats["std"],
                falloff_sec=stats["falloff"],
                falloff_sec_per_lap=stats["falloff_per_lap"],
                consistency_score=max(0, min(100, 100 - stats["std"] * 100)),
                valid_lap_count=len(valid_window_laps),
                excluded_laps=excluded,
                classification_tags=tags,
                pace_quality_score=pq.pace_quality_score,
                pace_quality_label=pq.pace_quality_label,
                evidence_confidence_score=pq.evidence_confidence_score,
                evidence_confidence_label=pq.evidence_confidence_label,
                setup_usefulness_score=pq.setup_usefulness_score,
                setup_usefulness_label=pq.setup_usefulness_label,
                pace_quality_warnings=pq.warnings,
                pace_quality_components=pq.component_scores,
            ))
        if not windows:
            groups.append(BestWindowGroup(label=f"Best {size}-Lap Window", window_size=size, is_available=False, warning=f"No valid {size}-lap consecutive window found."))
            continue
        windows.sort(key=lambda w: w.average_lap_time or 999999.0)
        groups.append(BestWindowGroup(
            label=f"Best {size}-Lap Window",
            window_size=size,
            windows=windows[:5],
            best_window=windows[0],
            is_available=True,
        ))
    return groups


def compute_degradation(laps: list[LapSummary]) -> LapDegradationSummary:
    sorted_laps = sorted(laps, key=lambda la: la.lap_number)
    valid = [la for la in sorted_laps if _is_lap_valid_for_ranking(la)[0]]
    n = len(valid)
    if n < 10:
        return LapDegradationSummary(
            run_id=sorted_laps[0].run_id if sorted_laps else "",
            lap_count=n,
            confidence_score=0.0,
            coaching_message=f"Need at least 10 valid laps for degradation analysis. Only {n} valid lap{'s' if n != 1 else ''}.",
        )

    third = n // 3 or 1
    early = valid[:third]
    middle = valid[third:2 * third]
    late = valid[2 * third:]
    early_times = [la.lap_time for la in early if la.lap_time is not None]
    middle_times = [la.lap_time for la in middle if la.lap_time is not None]
    late_times = [la.lap_time for la in late if la.lap_time is not None]
    early_avg = sum(early_times) / len(early_times) if early_times else None
    middle_avg = sum(middle_times) / len(middle_times) if middle_times else None
    late_avg = sum(late_times) / len(late_times) if late_times else None
    falloff = (late_avg - early_avg) if (late_avg is not None and early_avg is not None) else None
    falloff_per_lap = falloff / n if falloff is not None else None
    confidence = min(1.0, n / 40)
    coaching_message = "Limited falloff data - more laps needed for stronger conclusions."
    if falloff is not None:
        if falloff > 0.5 and n >= 20:
            coaching_message = "Long-run pace fell off significantly. Consider a smoother opening pace or reviewing tire/platform management."
        elif falloff > 0.2:
            coaching_message = "Early pace was stronger than later pace. Monitor tire spread and platform stability for falloff causes."
        elif falloff < 0.05:
            coaching_message = "Pace was consistent throughout the stint."
    return LapDegradationSummary(
        run_id=valid[0].run_id if valid else "",
        lap_count=n,
        early_window_laps=len(early),
        middle_window_laps=len(middle),
        late_window_laps=len(late),
        early_avg_lap_time=early_avg,
        middle_avg_lap_time=middle_avg,
        late_avg_lap_time=late_avg,
        falloff_early_to_late=falloff,
        falloff_slope_sec_per_lap=falloff_per_lap,
        confidence_score=confidence,
        coaching_message=coaching_message,
    )


def compute_lap_windows_response(laps: list[LapSummary]) -> LapWindowsResponse:
    if not laps:
        return LapWindowsResponse(run_id="", warnings=["No lap data available."])
    run_id = laps[0].run_id
    total = len(laps)
    valid = sum(_is_lap_valid_for_ranking(la)[0] for la in laps)
    fastest_groups = compute_fastest_groups(laps)
    best_windows = compute_best_windows(laps)
    degradation = compute_degradation(laps)
    warnings: list[str] = []
    if valid < 10:
        warnings.append(f"Only {valid} valid lap{'s' if valid != 1 else ''}. Need 10+ for meaningful window analysis.")
    return LapWindowsResponse(
        run_id=run_id,
        fastest_groups=fastest_groups,
        best_windows=best_windows,
        degradation=degradation,
        total_valid_laps=valid,
        total_laps=total,
        warnings=warnings,
    )
