"""Typed contract for the automatic handling-balance assessment.

This is an observation-only producer. It cannot authorize, direct, or size a
setup change; it has no Keep/Undo/Retest voice; it never writes DriverIntent.
The single authority field is a fixed `observation_only` literal so a client
trust validator can reject any future drift structurally.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState


class HandlingClassification(str, Enum):
    """Descriptive rotation-response signatures. Never "tight"/"loose" verdicts."""

    # Rotation demand is satisfied within the run-local reference envelope.
    NO_SIGNIFICANT_IMBALANCE_QUALIFIED = "no_significant_imbalance_qualified"
    # Sustained positive response deficit (car rotates less than the
    # path-kinematic reference) beyond the run-local noise envelope.
    ROTATION_RESPONSE_DEFICIT = "rotation_response_deficit"
    # Sustained negative response deficit beyond the run-local noise envelope.
    ROTATION_RESPONSE_EXCESS = "rotation_response_excess"
    # Opposing qualified signatures in different canonical phases.
    MIXED_PHASE_DEPENDENT = "mixed_phase_dependent"
    # High-magnitude transient yaw development without a sustained phase deficit.
    TRANSIENT_ROTATION_ANOMALY = "transient_rotation_anomaly"
    # Elevated correction demand without a sustained response deficit.
    STEERING_RESPONSE_ANOMALY = "steering_response_anomaly"
    # Evidence exists but cannot support any signature above.
    INCONCLUSIVE = "inconclusive"
    # Missing measurements or an ineligible recording.
    UNAVAILABLE = "unavailable"


class HandlingAuthority(str, Enum):
    OBSERVATION_ONLY = "observation_only"


class HandlingPhaseObservation(EngineeringModel):
    """Phase-local response diagnostics aggregated over the eligible lap group."""

    phase: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    eligible_laps: int = Field(ge=0)
    sample_bins: int = Field(ge=0)
    steering_demand_median_deg: float | None = Field(default=None, ge=0.0)
    steering_demand_floor_deg: float = Field(default=3.0, gt=0.0)
    path_kinematic_expected_yaw_median_rad_s: float | None = None
    measured_yaw_median_rad_s: float | None = None
    rotation_response_deficit_median_rad_s: float | None = None
    rotation_response_deficit_abs_p90_rad_s: float | None = Field(default=None, ge=0.0)
    rotation_response_ratio_median: float | None = Field(default=None, ge=0.0)
    steering_efficiency_median_curvature_per_rad: float | None = Field(default=None, ge=0.0)
    correction_count_median: float | None = Field(default=None, ge=0.0)
    max_yaw_rate_of_change_rad_s2: float | None = Field(default=None, ge=0.0)
    sideslip_rate_proxy_median_rad_s: float | None = None
    noise_scale_deficit_rad_s: float | None = Field(default=None, ge=0.0)
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    reference_lap_group: tuple[int, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def reference_laps_are_unique(self) -> HandlingPhaseObservation:
        if len(self.reference_lap_group) != len(set(self.reference_lap_group)):
            raise ValueError("reference lap group must be unique")
        return self


class HandlingBalanceAssessment(EngineeringModel):
    """One located, qualified handling observation with full provenance."""

    schema_version: str = "p-handling-balance.assessment.v1"
    assessment_id: str
    run_id: str
    session_id: str | None = None
    lap_numbers: tuple[int, ...] = Field(default_factory=tuple)
    phase: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]+$")
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)
    classification: HandlingClassification
    canonical_symptom_id: str | None = None
    observation_text: str = Field(min_length=1)
    evidence_state: EvidenceState
    confidence_score: float = Field(ge=0.0, le=1.0)
    repeatability: str = Field(min_length=1)
    source_channels: tuple[str, ...] = Field(default_factory=tuple)
    supporting_evidence: tuple[str, ...] = Field(default_factory=tuple)
    contradicting_evidence: tuple[str, ...] = Field(default_factory=tuple)
    alternative_explanations: tuple[str, ...] = Field(default_factory=tuple)
    blocker_reasons: tuple[str, ...] = Field(default_factory=tuple)
    phase_observations: tuple[HandlingPhaseObservation, ...] = Field(default_factory=tuple)
    authority: HandlingAuthority = HandlingAuthority.OBSERVATION_ONLY
    setup_authorized: bool = False
    driver_feedback_source: bool = False

    @model_validator(mode="after")
    def fail_closed_authority(self) -> HandlingBalanceAssessment:
        if self.authority != HandlingAuthority.OBSERVATION_ONLY:
            raise ValueError("the handling assessment is observation-only by contract")
        if self.setup_authorized:
            raise ValueError("the handling assessment cannot authorize setup")
        if self.driver_feedback_source:
            raise ValueError("machine observations are never driver feedback")
        if self.lap_numbers and len(self.lap_numbers) != len(set(self.lap_numbers)):
            raise ValueError("assessment lap numbers must be unique")
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("assessment windows require both bounds")
        if (
            self.lap_pct_start is not None
            and self.lap_pct_end is not None
            and self.lap_pct_end <= self.lap_pct_start
        ):
            raise ValueError("assessment window is reversed")
        if (
            self.classification == HandlingClassification.UNAVAILABLE
            and not self.blocker_reasons
        ):
            raise ValueError("unavailable assessments require blocker_reasons")
        return self


class HandlingBalanceReport(EngineeringModel):
    """Run-level aggregation of handling-balance observations."""

    schema_version: str = "p-handling-balance.report.v1"
    run_id: str
    session_id: str | None = None
    selected_lap: int | None = None
    eligible_laps: int = Field(ge=0)
    reference_lap_count: int = Field(ge=0)
    classification: HandlingClassification
    assessments: tuple[HandlingBalanceAssessment, ...] = Field(default_factory=tuple)
    conclusions: tuple[EngineeringConclusion, ...] = Field(default_factory=tuple)
    gate: EngineGate | None = None
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    authority: HandlingAuthority = HandlingAuthority.OBSERVATION_ONLY
    setup_authorized: bool = False

    @model_validator(mode="after")
    def fail_closed_authority(self) -> HandlingBalanceReport:
        if self.authority != HandlingAuthority.OBSERVATION_ONLY:
            raise ValueError("the handling report is observation-only by contract")
        if self.setup_authorized:
            raise ValueError("the handling report cannot authorize setup")
        return self


__all__ = [
    "HandlingAuthority",
    "HandlingBalanceAssessment",
    "HandlingBalanceReport",
    "HandlingClassification",
    "HandlingPhaseObservation",
]
