from __future__ import annotations

from dataclasses import replace
from typing import Any

from racelab_engine.analysis.compare_delta_traces import (
    DEFAULT_DELTA_CHANNELS,
    compute_delta_traces,
)
from racelab_engine.analysis.confidence_weighted_verdict import (
    apply_observation_confidence,
)
from racelab_engine.analysis.correlation_analysis import correlate_delta_channels
from racelab_engine.analysis.sector_intelligence import compute_sector_deltas
from racelab_engine.analysis.target_zone_classifier import (
    classify_target_zone as classify_tz,
)
from racelab_engine.analysis.trace_annotations import annotate_delta_traces
from racelab_engine.models.comparison_insights import (
    ComparisonInsightsResponse,
    ConfidenceWeightedObservation,
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


_NON_AUTHORITY_WARNING = (
    "Comparison insights are observational; only the controlled P19 workflow may "
    "authorize setup policy."
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
    observation_state: str = "inconclusive",
    base_confidence: float = 0.5,
    channels: list[str] | None = None,
    causal_attribution_blocked: bool = False,
    causal_block_reason: str | None = None,
    causal_block_reasons: list[str] | None = None,
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
            "paired_coverage": ch_data.paired_coverage,
            "unavailable_reason": ch_data.unavailable_reason,
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
            confidence=min(
                0.85,
                p.paired_coverage * (0.4 + 0.4 * abs(p.pearson_r or 0.0)),
            ),
            warning="Exploratory association only; it does not establish setup causality.",
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
        raw_slice = vals[tz_start_idx:tz_end_idx + 1]
        slice_vals = [v for v in raw_slice if v is not None]
        if not raw_slice or len(slice_vals) / len(raw_slice) < 0.90:
            return None
        return sum(slice_vals) / len(slice_vals) if slice_vals else None

    def _tz_min(ch: str) -> float | None:
        ch_data = delta_channel_dict.get(ch, {})
        vals = ch_data.get("delta_values", [])
        if not vals:
            return None
        raw_slice = vals[tz_start_idx:tz_end_idx + 1]
        slice_vals = [v for v in raw_slice if v is not None]
        if not raw_slice or len(slice_vals) / len(raw_slice) < 0.90:
            return None
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
    )
    if tz_speed is None and not causal_attribution_blocked:
        tz_model = TargetZoneClassification(
            classification="inconclusive",
            confidence=0.0,
            headline="Insufficient paired speed evidence",
            evidence=[
                "At least 90% paired positional speed coverage is required in the target zone."
            ],
        )
        warnings.append("Target-zone speed evidence is incomplete; no gain/loss conclusion was issued.")
    if causal_attribution_blocked:
        reasons = list(causal_block_reasons or [])
        if causal_block_reason and causal_block_reason not in reasons:
            reasons.append(causal_block_reason)
        if not reasons:
            reasons.append("External context prevents causal setup attribution.")
        tz_model = TargetZoneClassification(
            classification="inconclusive",
            confidence=min(tz_class.confidence, 0.3),
            headline="Observed change; setup cause not established",
            evidence=[*tz_class.reasoning, *reasons],
        )
        warnings.extend(reason for reason in reasons if reason not in warnings)
        correlations = [
            replace(
                correlation,
                narrative="Observed correlation only; causal setup attribution is blocked. "
                + correlation.narrative,
            )
            for correlation in correlations
        ]
        annotations = [
            replace(
                annotation,
                description="Observed telemetry only; setup attribution is blocked. "
                + annotation.description,
                confidence=min(annotation.confidence, 0.3),
            )
            for annotation in annotations
        ]

    # ── 5. Confidence-weighted observation ─────────────────────
    weighted = apply_observation_confidence(
        observation_state,
        base_confidence,
        discipline_label=discipline_label,
        context_problems=context_problems,
    )
    weighted_observation = ConfidenceWeightedObservation(
        observation_state=observation_state,
        adjusted_confidence=weighted.adjusted_confidence,
        confidence_tier=weighted.tier,
        penalties=weighted.penalties,
        boosts=weighted.boosts,
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
            warnings=[s.warning] if s.warning else [],
        )
        for i, s in enumerate(sector_result.sectors)
    ]
    if causal_attribution_blocked:
        sectors = [
            replace(
                sector,
                classification="observed_only",
                warnings=["Setup attribution is blocked; sector deltas are observational."],
            )
            for sector in sectors
        ]

    # ── 7. Summary headline + takeaways ────────────────────────
    if causal_attribution_blocked:
        summary_headline = "Observed change; setup cause not established"
    else:
        summary_headline = tz_model.headline if tz_model.confidence > 0.3 else "Inconclusive — review data coverage"
    key_takeaways: list[str] = []
    if causal_attribution_blocked:
        if annotation_result.summary:
            key_takeaways.append("Observed telemetry only: " + annotation_result.summary)
        key_takeaways.extend(list(causal_block_reasons or []))
        key_takeaways.append("No setup policy is authorized by this comparison.")
    else:
        if annotation_result.summary:
            key_takeaways.append(annotation_result.summary)
        if corr_result.narrative:
            key_takeaways.append(corr_result.narrative)
        if sector_result.summary:
            key_takeaways.append(sector_result.summary)
    warnings.append(_NON_AUTHORITY_WARNING)

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
        confidence_weighted_observation=weighted_observation,
        sectors=sectors,
        summary_headline=summary_headline,
        key_takeaways=key_takeaways,
        warnings=warnings,
        missing_channels=missing,
    )
