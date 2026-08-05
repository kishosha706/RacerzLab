"""API models for phase-aware P3 engineering systems."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel


class PhaseMetric(EngineeringModel):
    phase: str
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    sample_bins: int = Field(ge=0)
    metrics: dict[str, float | int | None] = Field(default_factory=dict)


class DriverLineReport(EngineeringModel):
    gate: EngineGate
    phase_metrics: list[PhaseMetric] = Field(default_factory=list)
    line_deviation_median_m: float | None = None
    line_deviation_p95_m: float | None = None
    throttle_mae_pct: float | None = None
    brake_mae_pct: float | None = None
    steering_mae_deg: float | None = None
    driver_execution_changed: bool | None = None
    setup_attribution_allowed: bool = False
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


class CornerRotationReport(EngineeringModel):
    gate: EngineGate
    phase_metrics: list[PhaseMetric] = Field(default_factory=list)
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


class PlatformSpeedBand(EngineeringModel):
    label: str
    min_speed_mph: float
    max_speed_mph: float | None = None
    sample_bins: int = Field(ge=0)
    metrics: dict[str, float | None] = Field(default_factory=dict)


class AeroPlatformReport(EngineeringModel):
    gate: EngineGate
    setup_attribution_allowed: bool = False
    baseline_speed_bands: list[PlatformSpeedBand] = Field(default_factory=list)
    test_speed_bands: list[PlatformSpeedBand] = Field(default_factory=list)
    comparison_metrics: dict[str, Any] = Field(default_factory=dict)
    lap_consistency: dict[str, Any] = Field(default_factory=dict)
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


class EngineeringSystemsResponse(EngineeringModel):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int
    test_lap: int
    alignment_coverage_fraction: float = Field(ge=0.0, le=1.0)
    local_alignment_confidence: float = Field(ge=0.0, le=1.0)
    baseline_curvature_basis: str
    test_curvature_basis: str
    baseline_gps_geometry_healthy: bool
    test_gps_geometry_healthy: bool
    baseline_sim_integrity_status: str
    test_sim_integrity_status: str
    sim_integrity_clear: bool | None = None
    sim_integrity_confidence_cap: float = Field(ge=0.0, le=1.0)
    driver_line: DriverLineReport
    corner_rotation: CornerRotationReport
    aero_platform: AeroPlatformReport
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "AeroPlatformReport",
    "CornerRotationReport",
    "DriverLineReport",
    "EngineeringSystemsResponse",
    "PhaseMetric",
    "PlatformSpeedBand",
]
