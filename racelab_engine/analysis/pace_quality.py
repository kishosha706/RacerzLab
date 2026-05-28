"""
Pace Quality scoring for lap windows and fastest-lap groups.

Uses weighted logistic component scoring for continuous signals
and deduction-based penalties for categorical trust issues.

Score labels:
  85-100: Excellent clean pace
  70-84:  Strong useful pace
  50-69:  Usable with caution
  25-49:  Low confidence
  0-24:   Not useful for setup decisions
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PaceQualityResult:
    score: float = 0.0
    label: str = "Not useful for setup decisions"
    component_scores: dict[str, float] = field(default_factory=dict)
    deductions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────

def clamp_score(value: float) -> float:
    """Clamp a score to 0-100."""
    return max(0.0, min(100.0, value))


def logistic_score(value: float, good: float, bad: float, invert: bool = False) -> float:
    """
    Compute a logistic score for a continuous signal.

    Args:
        value: The observed value.
        good: The value considered "good" (score near 100).
        bad: The value considered "bad" (score near 0).
        invert: If True, lower values are better (e.g., lap time std dev).

    Returns:
        Score from 0-100.
    """
    if good == bad:
        return 50.0

    if invert:
        # Lower is better
        if value <= good:
            return clamp_score(100 - (value / max(0.01, good)) * 15)
        if value >= bad:
            return clamp_score((max(0, bad * 2 - value) / max(0.01, bad)) * 15)
        return clamp_score(100 * (1.0 - (value - good) / max(0.01, bad - good)))
    # Higher is better
    if value >= good:
        return clamp_score(100 - (good / max(0.01, value)) * 5)
    if value <= bad:
        return clamp_score((value / max(0.01, bad)) * 15)
    return clamp_score(100 * (value - bad) / max(0.01, good - bad))


# ── Component scorers ─────────────────────────────────────────

def score_consistency(lap_time_std_dev: float | None) -> float:
    """Score consistency from lap time standard deviation."""
    if lap_time_std_dev is None:
        return 70.0
    return logistic_score(lap_time_std_dev, good=0.05, bad=0.35, invert=True)


def score_falloff(falloff_sec_per_lap: float | None) -> float:
    """Score falloff from seconds-per-lap degradation."""
    if falloff_sec_per_lap is None:
        return 70.0
    return logistic_score(falloff_sec_per_lap, good=0.01, bad=0.12, invert=True)


def score_validity(valid_lap_count: int, window_size: int) -> float:
    """Score validity based on what fraction of the window is valid."""
    if window_size <= 0:
        return 0.0
    ratio = valid_lap_count / window_size
    if ratio >= 1.0:
        return 100.0
    if ratio >= 0.9:
        return 85.0
    if ratio >= 0.75:
        return 65.0
    return 40.0 if ratio >= 0.6 else 10.0


def score_draft_confidence(draft_statuses: list[str]) -> float:
    """
    Score draft confidence from a list of draft statuses.

    Returns the lowest score found (most conservative).
    """
    if not draft_statuses:
        return 70.0  # UNKNOWN

    scores = []
    for status in draft_statuses:
        upper = status.upper()
        if upper in ("LIKELY_SOLO", "SOLO_CLEAN"):
            scores.append(100.0)
        elif upper == "UNKNOWN_DRAFT_STATUS":
            scores.append(70.0)
        elif upper == "POSSIBLE_DRAFT_ASSIST":
            scores.append(55.0)
        elif upper == "DRAFT_AFFECTED":
            scores.append(25.0)
        else:
            scores.append(70.0)

    return min(scores)  # Most conservative


def score_platform_safety(
    platform_risk_peak: float | None = None,
    rear_platform_risk_peak: float | None = None,
    whole_car_bottoming_peak: float | None = None,
) -> float:
    """Score platform safety from risk peaks."""
    scores: list[float] = []
    if platform_risk_peak is not None:
        scores.append(logistic_score(platform_risk_peak, good=0.30, bad=0.85, invert=True))
    if rear_platform_risk_peak is not None:
        scores.append(logistic_score(rear_platform_risk_peak, good=0.30, bad=0.85, invert=True))
    if whole_car_bottoming_peak is not None:
        scores.append(logistic_score(whole_car_bottoming_peak, good=0.30, bad=0.85, invert=True))
    if not scores:
        return 70.0  # Neutral when unavailable
    return min(scores)  # Most conservative


def score_tire_safety(
    temp_spread: float | None = None,
    pressure_gain: float | None = None,
    wear_spread: float | None = None,
    camber_bias: float | None = None,
) -> float:
    """Score tire safety from available metrics."""
    scores: list[float] = []
    if temp_spread is not None:
        scores.append(logistic_score(temp_spread, good=5.0, bad=20.0, invert=True))
    if pressure_gain is not None:
        scores.append(logistic_score(pressure_gain, good=1.0, bad=5.0, invert=True))
    if camber_bias is not None:
        scores.append(logistic_score(camber_bias, good=5.0, bad=20.0, invert=True))
    if wear_spread is not None:
        scores.append(logistic_score(wear_spread, good=1.0, bad=5.0, invert=True))
    if not scores:
        return 70.0  # Neutral when unavailable
    return min(scores)  # Most conservative


def score_shock_safety(shock_activity_index: float | None = None) -> float:
    """Score shock safety from activity index."""
    if shock_activity_index is None:
        return 70.0  # Neutral when unavailable
    return logistic_score(shock_activity_index, good=0.30, bad=0.90, invert=True)


# ── Deductions ────────────────────────────────────────────────

def compute_deductions(
    classification_tags: list[str],
    valid_lap_count: int,
    window_size: int,
    draft_statuses: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Compute deductions based on categorical trust issues.

    Returns:
        Tuple of (deductions list, warnings list).
    """
    deductions: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_deduction = 0.0

    upper_tags = [t.upper() for t in classification_tags]

    # Draft deductions
    if "DRAFT_AFFECTED" in upper_tags:
        deductions.append({"reason": "Draft affected", "amount": 20})
        total_deduction += 20
    elif "POSSIBLE_DRAFT_ASSIST" in upper_tags:
        deductions.append({"reason": "Possible draft assist", "amount": 10})
        total_deduction += 10

    # Mixed draft statuses
    unique_drafts = set(d.upper() for d in draft_statuses if d.upper() != "UNKNOWN_DRAFT_STATUS")
    if len(unique_drafts) > 1:
        deductions.append({"reason": "Mixed draft statuses", "amount": 10})
        total_deduction += 10

    # Invalid lap deductions
    invalid_count = sum(
        t in ("INVALID_SPEED_EVENT", "OUT_LAP", "COOLDOWN", "PIT_ROAD", "WRECK_OR_SPIN")
        for t in upper_tags
    )
    if invalid_count > 0:
        amount = min(25, invalid_count * 8)
        deductions.append({"reason": f"{invalid_count} invalid lap(s) in window", "amount": amount})
        total_deduction += amount

    # Missing lap deductions
    missing = window_size - valid_lap_count
    if missing > 0:
        amount = min(25, missing * 5)
        deductions.append({"reason": f"{missing} missing lap(s) from window", "amount": amount})
        total_deduction += amount

    # Short window deduction
    if window_size < 10:
        deductions.append({"reason": f"Window size {window_size} < 10 laps", "amount": 10})
        total_deduction += 10
        warnings.append("Window is shorter than 10 laps — long-run conclusions are limited.")

    # Fewer than 60% valid laps forces score cap
    if window_size > 0 and valid_lap_count / window_size < 0.6:
        warnings.append("Fewer than 60% of laps in this window are valid — score capped at 35.")

    return deductions, warnings


# ── Main scoring function ─────────────────────────────────────

def compute_pace_quality_score(
    # Required
    window_size: int,
    valid_lap_count: int,
    classification_tags: list[str],
    draft_statuses: list[str],
    # Optional continuous signals
    lap_time_std_dev: float | None = None,
    falloff_sec_per_lap: float | None = None,
    # Optional risk signals
    platform_risk_peak: float | None = None,
    rear_platform_risk_peak: float | None = None,
    whole_car_bottoming_peak: float | None = None,
    tire_temp_spread: float | None = None,
    tire_pressure_gain: float | None = None,
    tire_wear_spread: float | None = None,
    tire_camber_bias: float | None = None,
    shock_activity_index: float | None = None,
    # Flags
    is_fastest_group: bool = False,
) -> PaceQualityResult:
    """
    Compute a hybrid Pace Quality Score for a lap window or fastest-lap group.

    Uses weighted logistic component scoring for continuous signals
    and deduction-based penalties for categorical trust issues.
    """
    components: dict[str, float] = {}
    warnings: list[str] = []
    confidence_notes: list[str] = []

    # ── Component scores ───────────────────────────────────────
    consistency = score_consistency(lap_time_std_dev)
    components["consistency"] = consistency

    falloff = score_falloff(falloff_sec_per_lap)
    components["falloff"] = falloff

    validity = score_validity(valid_lap_count, window_size)
    components["validity"] = validity

    draft_conf = score_draft_confidence(draft_statuses)
    components["draft_confidence"] = draft_conf

    platform = score_platform_safety(platform_risk_peak, rear_platform_risk_peak, whole_car_bottoming_peak)
    components["platform_safety"] = platform

    tire = score_tire_safety(tire_temp_spread, tire_pressure_gain, tire_wear_spread, tire_camber_bias)
    components["tire_safety"] = tire

    shock = score_shock_safety(shock_activity_index)
    components["shock_safety"] = shock

    # Pace speed score — default to 70 when unavailable
    pace_speed = 70.0
    components["pace_speed"] = pace_speed
    if lap_time_std_dev is None and falloff_sec_per_lap is None:
        confidence_notes.append("Pace speed baseline unavailable — using default.")

    # ── Weighted base score ────────────────────────────────────
    base_score = (
        0.30 * components["pace_speed"]
        + 0.20 * components["consistency"]
        + 0.20 * components["falloff"]
        + 0.10 * components["validity"]
        + 0.10 * components["draft_confidence"]
        + 0.05 * components["platform_safety"]
        + 0.03 * components["tire_safety"]
        + 0.02 * components["shock_safety"]
    )

    # ── Deductions ─────────────────────────────────────────────
    deductions, ded_warnings = compute_deductions(
        classification_tags, valid_lap_count, window_size, draft_statuses,
    )
    warnings.extend(ded_warnings)

    total_deduction = sum(d["amount"] for d in deductions)
    score = base_score - total_deduction

    # ── Force cap for <60% valid ───────────────────────────────
    if window_size > 0 and valid_lap_count / window_size < 0.6:
        score = min(score, 35.0)

    # ── Fastest group warning ──────────────────────────────────
    if is_fastest_group:
        warnings.append("Fastest individual laps show peak pace, not sustained pace.")

    # ── Clamp ──────────────────────────────────────────────────
    score = clamp_score(score)

    # ── Label ──────────────────────────────────────────────────
    if score >= 85:
        label = "Excellent clean pace"
    elif score >= 70:
        label = "Strong useful pace"
    elif score >= 50:
        label = "Usable with caution"
    elif score >= 25:
        label = "Low confidence"
    else:
        label = "Not useful for setup decisions"

    return PaceQualityResult(
        score=score,
        label=label,
        component_scores=components,
        deductions=deductions,
        warnings=warnings,
        confidence_notes=confidence_notes,
    )
