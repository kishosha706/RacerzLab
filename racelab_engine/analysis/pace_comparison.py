from __future__ import annotations

import math
from statistics import median

from racelab_engine.analysis.comparison import PaceComparison
from racelab_engine.analysis.lap_eligibility import eligible_laps, find_lap
from racelab_engine.models.lap import LapSummary


def _finite_times(laps: list[LapSummary]) -> list[float]:
    return [
        float(lap.lap_time)
        for lap in sorted(eligible_laps(laps), key=lambda item: item.lap_number)
        if lap.lap_time is not None and math.isfinite(float(lap.lap_time))
    ]


def _robust_sigma(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    center = median(values)
    mad = median(abs(value - center) for value in values)
    if mad > 0:
        return 1.4826 * mad
    spread = max(values) - min(values)
    return spread / 1.349 if spread > 0 else 0.0


def build_pace_comparison(
    baseline_laps: list[LapSummary],
    test_laps: list[LapSummary],
    baseline_lap_number: int | None,
    test_lap_number: int | None,
) -> PaceComparison:
    """Compare repeatable whole-lap pace using robust within-run noise estimates."""
    all_baseline_times = _finite_times(baseline_laps)
    all_test_times = _finite_times(test_laps)
    cohort_size = min(len(all_baseline_times), len(all_test_times))
    # Compare matching stint phase. Extra late-run laps must not make the
    # longer run look slower when the other setup has no equivalent laps.
    baseline_times = all_baseline_times[:cohort_size]
    test_times = all_test_times[:cohort_size]
    baseline_selected = find_lap(baseline_laps, baseline_lap_number) if baseline_lap_number is not None else None
    test_selected = find_lap(test_laps, test_lap_number) if test_lap_number is not None else None
    baseline_selected_time = float(baseline_selected.lap_time) if baseline_selected and baseline_selected.lap_time is not None else None
    test_selected_time = float(test_selected.lap_time) if test_selected and test_selected.lap_time is not None else None
    selected_delta = (
        test_selected_time - baseline_selected_time
        if baseline_selected_time is not None and test_selected_time is not None
        else None
    )

    baseline_median = median(baseline_times) if baseline_times else None
    test_median = median(test_times) if test_times else None
    cohort_delta = test_median - baseline_median if baseline_median is not None and test_median is not None else None
    notes: list[str] = []
    if len(all_baseline_times) != len(all_test_times):
        notes.append(
            f"Pace cohorts were balanced to the first {cohort_size} eligible laps in each run."
        )
    enough_data = len(baseline_times) >= 3 and len(test_times) >= 3
    if not enough_data:
        notes.append("Need at least three eligible laps in both runs for a repeatable pace verdict.")

    noise_band: float | None = None
    significant: bool | None = None
    direction = "insufficient_data"
    if enough_data and cohort_delta is not None:
        baseline_sigma = _robust_sigma(baseline_times)
        test_sigma = _robust_sigma(test_times)
        standard_error = math.sqrt(
            (baseline_sigma ** 2 / len(baseline_times))
            + (test_sigma ** 2 / len(test_times))
        )
        noise_band = max(0.05, 1.96 * standard_error)
        significant = abs(cohort_delta) > noise_band
        if significant:
            direction = "faster" if cohort_delta < 0 else "slower"
        else:
            direction = "no_clear_difference"
            notes.append("Median pace delta is inside the run-to-run noise band.")

    sample_score = min(1.0, min(len(baseline_times), len(test_times)) / 5.0)
    if baseline_median and test_median:
        variability_ratio = max(
            _robust_sigma(baseline_times) / baseline_median if baseline_times else 1.0,
            _robust_sigma(test_times) / test_median if test_times else 1.0,
        )
        consistency_score = max(0.0, min(1.0, 1.0 - variability_ratio / 0.02))
    else:
        consistency_score = 0.0
    confidence = 0.65 * sample_score + 0.35 * consistency_score
    if not enough_data:
        confidence = min(confidence, 0.35)

    return PaceComparison(
        baseline_selected_lap_time_s=baseline_selected_time,
        test_selected_lap_time_s=test_selected_time,
        selected_lap_delta_s=selected_delta,
        baseline_median_lap_time_s=baseline_median,
        test_median_lap_time_s=test_median,
        cohort_delta_s=cohort_delta,
        baseline_eligible_laps=len(all_baseline_times),
        test_eligible_laps=len(all_test_times),
        noise_band_s=noise_band,
        is_significant=significant,
        direction=direction,
        confidence_score=round(max(0.0, min(1.0, confidence)), 3),
        confidence_notes=notes,
    )
