from __future__ import annotations

from typing import Any, cast

from racelab_engine.analysis.compare_delta_traces import (
    DEFAULT_DELTA_CHANNELS,
    compute_delta_traces,
)
from racelab_engine.analysis.confidence_weighted_verdict import (
    apply_confidence_weights,
)
from racelab_engine.analysis.correlation_analysis import correlate_delta_channels
from racelab_engine.analysis.sector_intelligence import compute_sector_deltas
from racelab_engine.analysis.target_zone_classifier import (
    classify_target_zone as classify_tz,
)
from racelab_engine.analysis.trace_annotations import annotate_delta_traces
from racelab_engine.models.comparison_insights import (
    ComparisonInsightsResponse,
    ConfidenceWeightedVerdict,
    CorrelationInsight,
    SectorDeltaSummary,
    TargetZoneClassification,
    TraceAnnotation,
)
from racelab_engine.models.comparison_insights import (
    AnnotationKind as AnnotationKindType,
    CorrelationStrength,
    CorrelationDirection,
    GainClass,
)


def _strength_label(r: float | None) -> CorrelationStrength:
    if r is None:
        return "none"
    abs_r = abs(r)
    return "strong" if abs_r >= 0.7 else "moderate" if abs_r >= 0.4 else "weak"


def _direction_label(r: float | None) -> CorrelationDirection:
    if r is None or abs(r) < 0.01:
        return "neutral"
    return "positive" if r > 0 else "negative"


def _annotation_kind(kind: str) -> AnnotationKindType:
    mapping: dict[str, AnnotationKindType] = {
        "SPEED_GAIN": "speed_gain",
        "SPEED_LOSS": "speed_loss",
        "CFS_COMPRESSION": "cfs_compression",
        "DRAG_SCRUB_SPIKE": "drag_scrub_spike",
        "STEERING_CORRECTION": "steering_correction",
        "RPM_FLATTENING": "rpm_flattening",
        "THROTTLE_LIFT": "throttle_lift",
    }
    return mapping.get(kind, "speed_gain")


def _gain_class(gc: str) -> GainClass:
    mapping: dict[str, GainClass] = {
        "stable_gain": "stable_gain",
        "risky_gain": "risky_gain",
        "platform_sensitive_gain": "platform_sensitive_gain",
        "driver_input_gain": "driver_input_gain",
        "drag_reduction": "drag_reduction",
        "mechanical_balance_improvement": "mechanical_balance_improvement",
        "inconclusive": "inconclusive",
    }
    return mapping.get(gc, "inconclusive")


def build_comparison_insights(
    comparison_id: str,
    baseline_run_id: str,
    test_run_id: str,
    baseline_lap: int | None,
    test_lap: int | None,
    baseline_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    *,
    target_zone_start_pct: float = 55.0,
    target_zone_end_pct: float = 70.0,
    discipline_label: str = "clean",
    discipline_score: int = 100,
    context_problems: int = 0,
    verdict_str: str = "inconclusive",
    base_confidence: float = 0.5,
    channels: list[str] | None = None,
) -> ComparisonInsightsResponse:
    """Run all insight engines and combine into one response."""
    selected = channels or DEFAULT_DELTA_CHANNELS
    warnings: list[str] = []
    missing: list[str] = []

    # ── 1. Delta traces (needed by annotations + correlations) ──
    delta_result = compute_delta_traces(
        baseline_rows, test_rows,
        channels=selected,
        x_axis="lap_dist_ft",
        start_pct=0.0,
        end_pct=100.0,
        step_pct=0.1,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
    )
    warnings.extend(delta_result.warnings)
    missing.extend(delta_result.missing_channels)

    # Build a dict of channel_name -> {delta_values, ...} for the engines
    delta_channel_dict: dict[str, dict[str, Any]] = {}
    for ch_name, ch_data in delta_result.channels.items():
        delta_channel_dict[ch_name] = {
            "delta_values": ch_data.delta_values,
            "baseline_values": ch_data.baseline_values,
            "test_values": ch_data.test_values,
            "label": ch_data.label,
            "unit": ch_data.unit,
            "is_proxy": ch_data.is_proxy,
        }

    # ── 2. Trace annotations ───────────────────────────────────
    annotation_result = annotate_delta_traces(
        delta_channel_dict,
        delta_result.lap_pct_values,
        delta_result.x_values,
    )
    annotations = [
        TraceAnnotation(
            id=f"ann_{i}",
            kind=_annotation_kind(a.kind),
            label=a.label,
            description=a.evidence,
            lap_pct=a.lap_pct,
            distance_ft=a.lap_dist_ft,
            channel=a.channel,
            value=a.value,
            severity=a.severity,
            confidence=0.7 if a.severity in ("critical", "high") else 0.5,
            recommendation=a.evidence,
        )
        for i, a in enumerate(annotation_result.annotations)
    ]

    # ── 3. Correlations ────────────────────────────────────────
    corr_result = correlate_delta_channels(delta_channel_dict)
    correlations = [
        CorrelationInsight(
            channel_a=p.channel_a,
            channel_b=p.channel_b,
            correlation=p.pearson_r,
            strength=_strength_label(p.pearson_r),
            direction=_direction_label(p.pearson_r),
            narrative=p.interpretation or "",
            confidence=0.6 if p.pearson_r is not None and abs(p.pearson_r) > 0.4 else 0.3,
        )
        for p in corr_result.pairs
    ]

    # ── 4. Target zone classification ──────────────────────────
    # Extract target-zone averages from delta traces
    tz_start_idx = round((target_zone_start_pct / 100) * (len(delta_result.lap_pct_values) - 1))
    tz_end_idx = round((target_zone_end_pct / 100) * (len(delta_result.lap_pct_values) - 1))

    def _tz_avg(ch: str) -> float | None:
        ch_data = delta_channel_dict.get(ch, {})
        vals = ch_data.get("delta_values", [])
        if not vals:
            return None
        slice_vals = [v for v in vals[tz_start_idx:tz_end_idx + 1] if v is not None]
        return sum(slice_vals) / len(slice_vals) if slice_vals else None

    def _tz_min(ch: str) -> float | None:
        ch_data = delta_channel_dict.get(ch, {})
        vals = ch_data.get("delta_values", [])
        if not vals:
            return None
        slice_vals = [v for v in vals[tz_start_idx:tz_end_idx + 1] if v is not None]
        return min(slice_vals) if slice_vals else None

    tz_speed = _tz_avg("speed_mph")
    tz_cfs_min = _tz_min("cfs_ride_height_in")
    tz_steer = _tz_avg("abs_steering_deg")
    tz_drag = _tz_avg("drag_scrub_suspicion")
    tz_rpm = _tz_avg("rpm")

    tz_class = classify_tz(tz_speed, tz_cfs_min, tz_steer, tz_drag, tz_rpm, discipline_label)
    tz_model = TargetZoneClassification(
        classification=_gain_class(tz_class.gain_class),
        confidence=tz_class.confidence,
        headline=tz_class.label,
        evidence=tz_class.reasoning,
        recommendation=tz_class.recommendation,
    )

    # ── 5. Confidence-weighted verdict ─────────────────────────
    cwv = apply_confidence_weights(
        verdict_str,
        base_confidence,
        discipline_label=discipline_label,
        context_problems=context_problems,
    )
    cwv_model = ConfidenceWeightedVerdict(
        original_verdict=cwv.verdict,
        adjusted_confidence=cwv.adjusted_confidence,
        confidence_tier=cwv.tier,
        penalties=cwv.penalties,
        boosts=cwv.boosts,
        final_recommendation=cwv.recommendation,
    )

    # ── 6. Sector intelligence ─────────────────────────────────
    sector_result = compute_sector_deltas(baseline_rows, test_rows, channels=selected)
    sectors = [
        SectorDeltaSummary(
            sector_id=f"sector_{i}",
            label=s.sector_name,
            start_pct=s.start_pct,
            end_pct=s.end_pct,
            avg_speed_delta_mph=s.avg_speed_delta,
            min_cfs_delta_in=s.min_cfs_delta,
            avg_steering_delta_deg=s.avg_steering_delta,
            avg_drag_scrub_delta=s.avg_drag_delta,
            avg_rpm_delta=s.avg_rpm_delta,
            classification=s.speed_direction,
        )
        for i, s in enumerate(sector_result.sectors)
    ]

    # ── 7. Summary headline + takeaways ────────────────────────
    summary_headline = tz_class.label if tz_class.confidence > 0.3 else "Inconclusive — review delta traces"
    key_takeaways: list[str] = []
    if annotation_result.summary:
        key_takeaways.append(annotation_result.summary)
    if corr_result.narrative:
        key_takeaways.append(corr_result.narrative)
    if sector_result.summary:
        key_takeaways.append(sector_result.summary)
    if cwv.recommendation:
        key_takeaways.append(cwv.recommendation)

    return ComparisonInsightsResponse(
        comparison_id=comparison_id,
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        baseline_lap=baseline_lap,
        test_lap=test_lap,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
        annotations=annotations,
        correlations=correlations,
        target_zone_classification=tz_model,
        confidence_weighted_verdict=cwv_model,
        sectors=sectors,
        summary_headline=summary_headline,
        key_takeaways=key_takeaways,
        warnings=warnings,
        missing_channels=missing,
    )
