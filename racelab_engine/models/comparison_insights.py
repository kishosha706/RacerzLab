from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AnnotationKind = Literal[
    "speed_gain", "speed_loss", "cfs_compression",
    "drag_scrub_spike", "steering_correction",
    "rpm_flattening", "throttle_lift",
]

CorrelationStrength = Literal["strong", "moderate", "weak", "none"]
CorrelationDirection = Literal["positive", "negative", "neutral"]

GainClass = Literal[
    "stable_gain", "risky_gain", "platform_sensitive_gain",
    "driver_input_gain", "drag_reduction",
    "mechanical_balance_improvement", "inconclusive",
]

ConfidenceTier = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class TraceAnnotation:
    id: str
    kind: AnnotationKind
    label: str
    description: str
    lap_pct: float | None
    distance_ft: float | None
    channel: str | None
    value: float | None
    severity: str
    confidence: float
    related_channels: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "lap_pct": self.lap_pct,
            "distance_ft": self.distance_ft,
            "channel": self.channel,
            "value": self.value,
            "severity": self.severity,
            "confidence": self.confidence,
            "related_channels": self.related_channels,
        }


@dataclass(frozen=True)
class CorrelationInsight:
    channel_a: str
    channel_b: str
    correlation: float | None
    strength: CorrelationStrength
    direction: CorrelationDirection
    narrative: str
    confidence: float
    warning: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel_a": self.channel_a,
            "channel_b": self.channel_b,
            "correlation": self.correlation,
            "strength": self.strength,
            "direction": self.direction,
            "narrative": self.narrative,
            "confidence": self.confidence,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class TargetZoneClassification:
    classification: GainClass
    confidence: float
    headline: str
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "headline": self.headline,
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class ConfidenceWeightedObservation:
    observation_state: str
    adjusted_confidence: float
    confidence_tier: ConfidenceTier
    penalties: list[str] = field(default_factory=list)
    boosts: list[str] = field(default_factory=list)
    warning: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_state": self.observation_state,
            "adjusted_confidence": self.adjusted_confidence,
            "confidence_tier": self.confidence_tier,
            "penalties": self.penalties,
            "boosts": self.boosts,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class SectorDeltaSummary:
    sector_id: str
    label: str
    start_pct: float
    end_pct: float
    avg_speed_delta_mph: float | None = None
    min_cfs_delta_in: float | None = None
    avg_steering_delta_deg: float | None = None
    avg_drag_scrub_delta: float | None = None
    avg_rpm_delta: float | None = None
    classification: str = "unchanged"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sector_id": self.sector_id,
            "label": self.label,
            "start_pct": self.start_pct,
            "end_pct": self.end_pct,
            "avg_speed_delta_mph": self.avg_speed_delta_mph,
            "min_cfs_delta_in": self.min_cfs_delta_in,
            "avg_steering_delta_deg": self.avg_steering_delta_deg,
            "avg_drag_scrub_delta": self.avg_drag_scrub_delta,
            "avg_rpm_delta": self.avg_rpm_delta,
            "classification": self.classification,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class ComparisonInsightsResponse:
    comparison_id: str
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None
    test_lap: int | None
    target_zone_start_pct: float
    target_zone_end_pct: float
    annotations: list[TraceAnnotation] = field(default_factory=list)
    correlations: list[CorrelationInsight] = field(default_factory=list)
    target_zone_classification: TargetZoneClassification | None = None
    confidence_weighted_observation: ConfidenceWeightedObservation | None = None
    sectors: list[SectorDeltaSummary] = field(default_factory=list)
    summary_headline: str | None = None
    key_takeaways: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_channels: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "baseline_run_id": self.baseline_run_id,
            "test_run_id": self.test_run_id,
            "baseline_lap": self.baseline_lap,
            "test_lap": self.test_lap,
            "target_zone_start_pct": self.target_zone_start_pct,
            "target_zone_end_pct": self.target_zone_end_pct,
            "annotations": [a.as_dict() for a in self.annotations],
            "correlations": [c.as_dict() for c in self.correlations],
            "target_zone_classification": self.target_zone_classification.as_dict() if self.target_zone_classification else None,
            "confidence_weighted_observation": self.confidence_weighted_observation.as_dict() if self.confidence_weighted_observation else None,
            "sectors": [s.as_dict() for s in self.sectors],
            "summary_headline": self.summary_headline,
            "key_takeaways": self.key_takeaways,
            "warnings": self.warnings,
            "missing_channels": self.missing_channels,
        }
