from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PaceQualityResult:
    score: float = 0.0
    label: str = "Not useful for setup decisions"
    pace_quality_score: float = 0.0
    pace_quality_label: str = "Not useful for setup decisions"
    evidence_confidence_score: float = 0.0
    evidence_confidence_label: str = "Not useful for setup decisions"
    setup_usefulness_score: float = 0.0
    setup_usefulness_label: str = "Not useful for setup decisions"
    component_scores: dict[str, float | None] = field(default_factory=dict)
    deductions: list[dict[str, Any]] = field(default_factory=list)
    caps: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def logistic_score(value: float, good: float, bad: float, invert: bool = False) -> float:
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
    if value >= 85:
        return "Excellent clean pace"
    if value >= 70:
        return "Strong useful pace"
    if value >= 50:
        return "Usable with caution"
    return "Low confidence" if value >= 25 else "Not useful for setup decisions"


def score_pace_speed(avg_lap_time: float | None, reference_lap_time: float | None) -> float | None:
    if avg_lap_time is None or avg_lap_time <= 0:
        return None
    if reference_lap_time is None or reference_lap_time <= 0:
        return None
    pace_delta_pct = (avg_lap_time - reference_lap_time) / reference_lap_time
    return logistic_score(pace_delta_pct, good=0.0025, bad=0.0300, invert=True)


def score_consistency(lap_time_std_dev: float | None, avg_lap_time: float | None = None) -> float | None:
    if lap_time_std_dev is None or avg_lap_time is None or avg_lap_time <= 0:
        return None
    lap_time_std_pct = lap_time_std_dev / avg_lap_time
    return logistic_score(lap_time_std_pct, good=0.001, bad=0.007, invert=True)


def score_falloff(falloff_sec_per_lap: float | None, avg_lap_time: float | None = None) -> float | None:
    if falloff_sec_per_lap is None or avg_lap_time is None or avg_lap_time <= 0:
        return None
    falloff_pct_per_lap = falloff_sec_per_lap / avg_lap_time
    return logistic_score(falloff_pct_per_lap, good=0.0002, bad=0.0020, invert=True)


def score_validity(valid_lap_count: int, window_size: int) -> float:
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


def score_data_completeness(has_platform_data: bool = False, has_tire_data: bool = False, has_shock_data: bool = False) -> float:
    available = sum([has_platform_data, has_tire_data, has_shock_data])
    if available >= 3:
        return 100.0
    if available >= 2:
        return 85.0
    return 65.0 if available >= 1 else 40.0


def score_window_size_confidence(window_size: int) -> float:
    if window_size >= 40:
        return 100.0
    if window_size >= 20:
        return 85.0
    if window_size >= 10:
        return 65.0
    return 40.0 if window_size >= 5 else 15.0


def score_context_consistency(classification_tags: list[str]) -> float:
    upper = [t.upper() for t in classification_tags]
    has_conflict = any(t in upper for t in ("WRECK_OR_SPIN", "PIT_ROAD", "INVALID_SPEED_EVENT"))
    if has_conflict:
        return 20.0
    has_issue = any(t in upper for t in ("COOLDOWN", "OUT_LAP"))
    return 40.0 if has_issue else 90.0


def score_weather_confidence(weather_changed: bool = False) -> float:
    return 50.0 if weather_changed else 90.0


def score_platform_safety(platform_risk_peak: float | None = None, rear_platform_risk_peak: float | None = None, whole_car_bottoming_peak: float | None = None) -> float | None:
    scores: list[float] = []
    if platform_risk_peak is not None:
        scores.append(logistic_score(platform_risk_peak, good=0.30, bad=0.85, invert=True))
    if rear_platform_risk_peak is not None:
        scores.append(logistic_score(rear_platform_risk_peak, good=0.30, bad=0.85, invert=True))
    if whole_car_bottoming_peak is not None:
        scores.append(logistic_score(whole_car_bottoming_peak, good=0.30, bad=0.85, invert=True))
    return min(scores) if scores else None


def score_tire_safety(temp_spread: float | None = None, pressure_gain: float | None = None, wear_spread: float | None = None, camber_bias: float | None = None) -> float | None:
    scores: list[float] = []
    if temp_spread is not None:
        scores.append(logistic_score(temp_spread, good=5.0, bad=20.0, invert=True))
    if pressure_gain is not None:
        scores.append(logistic_score(pressure_gain, good=1.0, bad=5.0, invert=True))
    if camber_bias is not None:
        scores.append(logistic_score(camber_bias, good=5.0, bad=20.0, invert=True))
    if wear_spread is not None:
        scores.append(logistic_score(wear_spread, good=1.0, bad=5.0, invert=True))
    return min(scores) if scores else None


def score_shock_safety(shock_activity_index: float | None = None) -> float | None:
    if shock_activity_index is None:
        return None
    return logistic_score(shock_activity_index, good=0.30, bad=0.90, invert=True)


def classify_pace_trust_relationship(
    pace_quality_score: float,
    evidence_confidence_score: float,
    setup_usefulness_score: float,
    warnings: list[str],
) -> str:
    upper_warnings = [w.upper() for w in warnings]
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


def compute_evidence_deductions(
    classification_tags: list[str],
    valid_lap_count: int,
    window_size: int,
    has_platform_data: bool = False,
    has_tire_data: bool = False,
    has_shock_data: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    deductions: list[dict[str, Any]] = []
    warnings: list[str] = []
    upper_tags = [t.upper() for t in classification_tags]
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
        warnings.append("Window is shorter than 10 laps - long-run conclusions are limited.")
    if window_size > 0 and valid_lap_count / window_size < 0.6:
        warnings.append("Fewer than 60% of laps in this window are valid.")
    return deductions, warnings


def compute_pace_quality_score(
    window_size: int,
    valid_lap_count: int,
    classification_tags: list[str],
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
    upper_tags = [t.upper() for t in classification_tags]
    components: dict[str, float | None] = {}
    warnings: list[str] = []
    confidence_notes: list[str] = []
    caps: list[dict[str, Any]] = []

    has_platform = platform_risk_peak is not None or rear_platform_risk_peak is not None or whole_car_bottoming_peak is not None
    has_tire = tire_temp_spread is not None or tire_pressure_gain is not None
    has_shock = shock_activity_index is not None

    pace_speed = score_pace_speed(avg_lap_time, reference_lap_time)
    components["pace_speed"] = pace_speed
    if reference_lap_time is None:
        confidence_notes.append("Pace speed reference unavailable; no neutral score was substituted.")
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
    validity = score_validity(valid_lap_count, window_size)
    components["validity"] = validity
    data_completeness = score_data_completeness(has_platform, has_tire, has_shock)
    components["data_completeness"] = data_completeness
    window_conf = score_window_size_confidence(window_size)
    components["window_size_confidence"] = window_conf
    context_consistency = score_context_consistency(classification_tags)
    components["context_consistency"] = context_consistency
    weather_conf = score_weather_confidence(weather_changed)
    components["weather_confidence"] = weather_conf

    pace_inputs = (
        (pace_speed, 0.35),
        (consistency, 0.25),
        (falloff, 0.20),
        (platform, 0.08),
        (tire, 0.07),
        (shock, 0.05),
    )
    available_weight = sum(weight for score, weight in pace_inputs if score is not None)
    pace_quality = clamp_score(
        sum(float(score) * weight for score, weight in pace_inputs if score is not None) / available_weight
        if available_weight > 0
        else 0.0
    )
    evidence_base = clamp_score(0.45 * validity + 0.20 * data_completeness + 0.15 * window_conf + 0.15 * context_consistency + 0.05 * weather_conf)

    ded, ded_warnings = compute_evidence_deductions(
        classification_tags, valid_lap_count, window_size, has_platform, has_tire, has_shock,
    )
    warnings.extend(ded_warnings)
    total_ded = sum(d["amount"] for d in ded)
    evidence_confidence = clamp_score(evidence_base - total_ded)

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

    setup_usefulness = clamp_score(0.60 * evidence_confidence + 0.40 * pace_quality)
    missing_safety = [
        label
        for label, present in (
            ("platform", has_platform),
            ("tire", has_tire),
            ("shock", has_shock),
        )
        if not present
    ]
    if missing_safety:
        setup_cap = 35.0 if len(missing_safety) == 3 else 49.0
        setup_usefulness = min(setup_usefulness, setup_cap)
        caps.append({
            "reason": f"Missing {', '.join(missing_safety)} safety evidence",
            "setup_usefulness_cap": setup_cap,
        })
        warnings.append(
            f"Missing {', '.join(missing_safety)} safety evidence; setup usefulness is capped."
        )
    if window_size < 10:
        setup_usefulness = min(setup_usefulness, 35.0)
        caps.append({"reason": "Short run cannot support strong degradation or cooling conclusions", "setup_usefulness_cap": 35})
    if is_fastest_group:
        warnings.append("Fastest individual laps show peak pace, not sustained pace.")

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
