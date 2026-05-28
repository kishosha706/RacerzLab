"""
Pace Quality scoring for lap windows and fastest-lap groups.

Splits scoring into three dimensions:
1. Pace Quality — how strong the pace was
2. Evidence Confidence — whether the data is trustworthy
3. Setup Usefulness — combined score for setup decisions

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
    # Backward-compatible aliases
    score: float = 0.0
    label: str = "Not useful for setup decisions"
    # New split scores
    pace_quality_score: float = 0.0
    pace_quality_label: str = "Not useful for setup decisions"
    evidence_confidence_score: float = 0.0
    evidence_confidence_label: str = "Not useful for setup decisions"
    setup_usefulness_score: float = 0.0
    setup_usefulness_label: str = "Not useful for setup decisions"
    # Details
    component_scores: dict[str, float] = field(default_factory=dict)
    deductions: list[dict[str, Any]] = field(default_factory=list)
    caps: list[dict[str, Any]] = field(default_factory=list)
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
        if value <= good:
            return clamp_score(100 - (value / max(0.01, good)) * 15)
        if value >= bad:
            return clamp_score((max(0, bad * 2 - value) / max(0.01, bad)) * 15)
        return clamp_score(100 * (1.0 - (value - good) / max(0.01, bad - good)))
    if value >= good:
        return clamp_score(100 - (good / max(0.01, value)) * 5)
    if value <= bad:
        return clamp_score((value / max(0.01, bad)) * 15)
    return clamp_score(100 * (value - bad) / max(0.01, good - bad))


def _score_label(value: float) -> str:
    """Map a score to a label."""
    if value >= 85:
        return "Excellent clean pace"
    if value >= 70:
        return "Strong useful pace"
    if value >= 50:
        return "Usable with caution"
    if value >= 25:
        return "Low confidence"
    return "Not useful for setup decisions"


# ── Component scorers ─────────────────────────────────────────

def score_pace_speed(avg_lap_time: float | None, reference_lap_time: float | None) -> float:
    """
    Score pace speed relative to a reference lap time.

    Reference source order:
    1. Best theoretical lap from valid segments
    2. Fastest clean useful lap in current run
    3. Fallback neutral 70 with warning
    """
    if avg_lap_time is None or avg_lap_time <= 0:
        return 70.0
    if reference_lap_time is None or reference_lap_time <= 0:
        return 70.0
    pace_delta_pct = (avg_lap_time - reference_lap_time) / reference_lap_time
    return logistic_score(pace_delta_pct, good=0.0025, bad=0.0300, invert=True)


def score_consistency(lap_time_std_dev: float | None, avg_lap_time: float | None = None) -> float:
    """Score consistency from lap time standard deviation (percentage-based)."""
    if lap_time_std_dev is None or avg_lap_time is None or avg_lap_time <= 0:
        return 70.0
    lap_time_std_pct = lap_time_std_dev / avg_lap_time
    return logistic_score(lap_time_std_pct, good=0.001, bad=0.007, invert=True)


def score_falloff(falloff_sec_per_lap: float | None, avg_lap_time: float | None = None) -> float:
    """Score falloff from seconds-per-lap degradation (percentage-based)."""
    if falloff_sec_per_lap is None or avg_lap_time is None or avg_lap_time <= 0:
        return 70.0
    falloff_pct_per_lap = falloff_sec_per_lap / avg_lap_time
    return logistic_score(falloff_pct_per_lap, good=0.0002, bad=0.0020, invert=True)


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
    """Score draft confidence from a list of draft statuses (most conservative)."""
    if not draft_statuses:
        return 70.0
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
    return min(scores)


def score_data_completeness(
    has_platform_data: bool = False,
    has_tire_data: bool = False,
    has_shock_data: bool = False,
) -> float:
    """Score data completeness based on available sensor channels."""
    available = sum([has_platform_data, has_tire_data, has_shock_data])
    if available >= 3:
        return 100.0
    if available >= 2:
        return 85.0
    if available >= 1:
        return 65.0
    return 40.0


def score_window_size_confidence(window_size: int) -> float:
    """Score confidence based on window size."""
    if window_size >= 40:
        return 100.0
    if window_size >= 20:
        return 85.0
    if window_size >= 10:
        return 65.0
    if window_size >= 5:
        return 40.0
    return 15.0


def score_context_consistency(classification_tags: list[str]) -> float:
    """Score context consistency from classification tags."""
    upper = [t.upper() for t in classification_tags]
    has_conflict = any(t in upper for t in ("WRECK_OR_SPIN", "PIT_ROAD", "INVALID_SPEED_EVENT"))
    if has_conflict:
        return 20.0
    has_issue = any(t in upper for t in ("COOLDOWN", "OUT_LAP"))
    if has_issue:
        return 40.0
    return 90.0


def score_weather_confidence(weather_changed: bool = False) -> float:
    """Score weather confidence."""
    return 50.0 if weather_changed else 90.0


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
    return 70.0 if not scores else min(scores)


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
    return 70.0 if not scores else min(scores)


def score_shock_safety(shock_activity_index: float | None = None) -> float:
    """Score shock safety from activity index."""
    if shock_activity_index is None:
        return 70.0
    return logistic_score(shock_activity_index, good=0.30, bad=0.90, invert=True)


# ── Pace–trust relationship classifier ────────────────────────

def classify_pace_trust_relationship(
    pace_quality_score: float,
    evidence_confidence_score: float,
    setup_usefulness_score: float,
    warnings: list[str],
) -> str:
    """
    Classify the relationship between pace and trust into a human-readable label.

    Returns a short string describing the relationship, e.g.
    "Fast but not trustworthy", "Clean but not fast", etc.
    """
    upper_warnings = [w.upper() for w in warnings]
    if any("DRAFT" in w for w in upper_warnings):
        return "Draft-affected: setup conclusions limited"
    if any("60%" in w or "INSUFFICIENT" in w or "ONLY" in w for w in upper_warnings):
        return "Insufficient valid laps"
    if pace_quality_score >= 70 and evidence_confidence_score < 50:
        return "Fast but not trustworthy"
    if evidence_confidence_score >= 70 and pace_quality_score < 50:
        return "Clean but not fast"
    if pace_quality_score >= 70 and evidence_confidence_score >= 70:
        return "Strong clean pace"
    if pace_quality_score < 30 and evidence_confidence_score < 30:
        return "Not useful for setup decisions"
    return "Usable with caution"


# ── Evidence confidence deductions ────────────────────────────

def compute_evidence_deductions(
    classification_tags: list[str],
    valid_lap_count: int,
    window_size: int,
    draft_statuses: list[str],
    has_platform_data: bool = False,
    has_tire_data: bool = False,
    has_shock_data: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Compute deductions for evidence confidence score.

    Returns:
        Tuple of (deductions list, warnings list).
    """
    deductions: list[dict[str, Any]] = []
    warnings: list[str] = []
    upper_tags = [t.upper() for t in classification_tags]

    if "POSSIBLE_DRAFT_ASSIST" in upper_tags:
        deductions.append({"reason": "Possible draft assist", "amount": 12})
    if "UNKNOWN_DRAFT_STATUS" in [d.upper() for d in draft_statuses]:
        deductions.append({"reason": "Unknown draft status", "amount": 5})
    unique_drafts = set(d.upper() for d in draft_statuses if d.upper() != "UNKNOWN_DRAFT_STATUS")
    if len(unique_drafts) > 1:
        deductions.append({"reason": "Mixed draft statuses", "amount": 12})
    invalid_count = sum(t in ("INVALID_SPEED_EVENT", "OUT_LAP", "COOLDOWN", "PIT_ROAD", "WRECK_OR_SPIN") for t in upper_tags)
    if invalid_count > 0:
        deductions.append({"reason": f"{invalid_count} invalid lap(s) in window", "amount": min(25, invalid_count * 8)})
    missing = window_size - valid_lap_count
    if missing > 0:
        deductions.append({"reason": f"{missing} missing lap(s) from window", "amount": min(25, missing * 5)})
    if not has_tire_data:
        deductions.append({"reason": "Missing tire data", "amount": 5})
    if not has_shock_data:
        deductions.append({"reason": "Missing shock data", "amount": 3})
    if not has_platform_data:
        deductions.append({"reason": "Missing platform data", "amount": 8})
    if window_size < 10:
        deductions.append({"reason": f"Window size {window_size} < 10 laps", "amount": 10})
        warnings.append("Window is shorter than 10 laps — long-run conclusions are limited.")
    if window_size > 0 and valid_lap_count / window_size < 0.6:
        warnings.append("Fewer than 60% of laps in this window are valid.")

    return deductions, warnings


# ── Main scoring function ─────────────────────────────────────

def compute_pace_quality_score(
    window_size: int,
    valid_lap_count: int,
    classification_tags: list[str],
    draft_statuses: list[str],
    avg_lap_time: float | None = None,
    reference_lap_time: float | None = None,
    lap_time_std_dev: float | None = None,
    falloff_sec_per_lap: float | None = None,
    platform_risk_peak: float | None = None,
    rear_platform_risk_peak: float | None = None,
    whole_car_bottoming_peak: float | None = None,
    tire_temp_spread: float | None = None,
    tire_pressure_gain: float | None = None,
    tire_wear_spread: float | None = None,
    tire_camber_bias: float | None = None,
    shock_activity_index: float | None = None,
    weather_changed: bool = False,
    is_fastest_group: bool = False,
) -> PaceQualityResult:
    """
    Compute Pace Quality, Evidence Confidence, and Setup Usefulness scores.

    Pace Quality measures how strong the pace was.
    Evidence Confidence measures whether the data is trustworthy.
    Setup Usefulness combines both for setup decisions.
    """
    components: dict[str, float] = {}
    warnings: list[str] = []
    confidence_notes: list[str] = []
    caps: list[dict[str, Any]] = []
    upper_tags = [t.upper() for t in classification_tags]

    has_platform = platform_risk_peak is not None or rear_platform_risk_peak is not None or whole_car_bottoming_peak is not None
    has_tire = tire_temp_spread is not None or tire_pressure_gain is not None
    has_shock = shock_activity_index is not None

    # ── Pace Quality components ────────────────────────────────
    pace_speed = score_pace_speed(avg_lap_time, reference_lap_time)
    components["pace_speed"] = pace_speed
    if reference_lap_time is None:
        confidence_notes.append("Pace speed reference unavailable — using neutral score.")

    consistency = score_consistency(lap_time_std_dev, avg_lap_time)
    components["consistency"] = consistency

    falloff = score_falloff(falloff_sec_per_lap, avg_lap_time)
    components["falloff"] = falloff

    platform = score_platform_safety(platform_risk_peak, rear_platform_risk_peak, whole_car_bottoming_peak)
    components["platform_safety"] = platform

    tire = score_tire_safety(tire_temp_spread, tire_pressure_gain, tire_wear_spread, tire_camber_bias)
    components["tire_safety"] = tire

    shock = score_shock_safety(shock_activity_index)
    components["shock_safety"] = shock

    # ── Evidence Confidence components ─────────────────────────
    validity = score_validity(valid_lap_count, window_size)
    components["validity"] = validity

    draft_conf = score_draft_confidence(draft_statuses)
    components["draft_confidence"] = draft_conf

    data_completeness = score_data_completeness(has_platform, has_tire, has_shock)
    components["data_completeness"] = data_completeness

    window_conf = score_window_size_confidence(window_size)
    components["window_size_confidence"] = window_conf

    context_consistency = score_context_consistency(classification_tags)
    components["context_consistency"] = context_consistency

    weather_conf = score_weather_confidence(weather_changed)
    components["weather_confidence"] = weather_conf

    # ── Weighted scores ────────────────────────────────────────
    pace_quality = clamp_score(
        0.35 * pace_speed
        + 0.25 * consistency
        + 0.20 * falloff
        + 0.08 * platform
        + 0.07 * tire
        + 0.05 * shock
    )

    evidence_base = clamp_score(
        0.35 * validity
        + 0.25 * draft_conf
        + 0.15 * data_completeness
        + 0.10 * window_conf
        + 0.10 * context_consistency
        + 0.05 * weather_conf
    )

    # ── Evidence deductions ────────────────────────────────────
    ded, ded_warnings = compute_evidence_deductions(
        classification_tags, valid_lap_count, window_size, draft_statuses,
        has_platform, has_tire, has_shock,
    )
    warnings.extend(ded_warnings)
    total_ded = sum(d["amount"] for d in ded)
    evidence_confidence = clamp_score(evidence_base - total_ded)

    # ── Caps ───────────────────────────────────────────────────
    if "WRECK_OR_SPIN" in upper_tags:
        pace_quality = min(pace_quality, 20.0)
        evidence_confidence = min(evidence_confidence, 10.0)
        caps.append({"reason": "Wreck or spin present", "pace_cap": 20, "evidence_cap": 10})
    if "PIT_ROAD" in upper_tags:
        pace_quality = min(pace_quality, 25.0)
        evidence_confidence = min(evidence_confidence, 15.0)
        caps.append({"reason": "Pit road present", "pace_cap": 25, "evidence_cap": 15})
    if window_size > 0 and valid_lap_count / window_size < 0.6:
        evidence_confidence = min(evidence_confidence, 35.0)
        caps.append({"reason": "Fewer than 60% valid laps", "evidence_cap": 35})
    if "DRAFT_AFFECTED" in upper_tags:
        evidence_confidence = min(evidence_confidence, 40.0)
        caps.append({"reason": "Draft affected", "evidence_cap": 40})

    # ── Setup Usefulness ───────────────────────────────────────
    setup_usefulness = clamp_score(0.60 * evidence_confidence + 0.40 * pace_quality)

    # ── Fastest group warning ──────────────────────────────────
    if is_fastest_group:
        warnings.append("Fastest individual laps show peak pace, not sustained pace.")

    # ── Labels ─────────────────────────────────────────────────
    pq_label = _score_label(pace_quality)
    ev_label = _score_label(evidence_confidence)
    su_label = _score_label(setup_usefulness)

    return PaceQualityResult(
        score=setup_usefulness,
        label=su_label,
        pace_quality_score=pace_quality,
        pace_quality_label=pq_label,
        evidence_confidence_score=evidence_confidence,
        evidence_confidence_label=ev_label,
        setup_usefulness_score=setup_usefulness,
        setup_usefulness_label=su_label,
        component_scores=components,
        deductions=ded,
        caps=caps,
        warnings=warnings,
        confidence_notes=confidence_notes,
    )
