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
    """Descriptive rotation-response signatures. Never "tight"/"loose" verdicts.

    Physics audit (2026-10-13): the residual speed x path-curvature - yaw_rate
    equals the planar sideslip RATE (d(beta)/dt), because course angle =
    heading + sideslip. It is therefore zero in steady-state cornering no
    matter how unbalanced the car is, and nonzero during transients without
    implying imbalance. A deficit/excess classification now requires a second,
    independent steering-demand-to-response strand to corroborate the residual
    under comparable conditions. The residual alone maps to no tight/loose
    symptom.
    """

    # No strand qualified beyond the run-local reference envelope. This is
    # not evidence of neutral balance: the kinematic residual is blind to a
    # constant sideslip angle.
    NO_SIGNIFICANT_IMBALANCE_QUALIFIED = "no_significant_imbalance_qualified"
    # The kinematic residual (planar sideslip-rate proxy) exceeds the run-local
    # noise envelope, but steering-demand-to-response evidence does not
    # corroborate it. Diagnostic only; no canonical symptom mapping.
    KINEMATIC_RESIDUAL_OBSERVATION = "kinematic_residual_observation"
    # Corroborated reduced rotation response: the kinematic residual is
    # positive beyond the noise envelope AND steering demand per achieved
    # curvature is independently elevated on comparable laps.
    ROTATION_RESPONSE_DEFICIT = "rotation_response_deficit"
    # Corroborated excess rotation-like response: residual negative beyond the
    # noise envelope AND steering demand per curvature independently reduced.
    ROTATION_RESPONSE_EXCESS = "rotation_response_excess"
    # Opposing qualified signatures in different canonical phases.
    MIXED_PHASE_DEPENDENT = "mixed_phase_dependent"
    # High-magnitude transient yaw development without a sustained phase deficit.
    TRANSIENT_ROTATION_ANOMALY = "transient_rotation_anomaly"
    # Elevated correction demand without a sustained response deficit.
    STEERING_RESPONSE_ANOMALY = "steering_response_anomaly"
    # Steering demand per achieved curvature diverges from the run-local
    # reference on comparable laps without a corroborating kinematic residual.
    # Diagnostic only; no canonical symptom mapping.
    STEERING_DEMAND_ANOMALY = "steering_demand_anomaly"
    # Evidence exists but cannot support any signature above.
    INCONCLUSIVE = "inconclusive"
    # Missing measurements or an ineligible recording.
    UNAVAILABLE = "unavailable"


class HandlingAuthority(str, Enum):
    OBSERVATION_ONLY = "observation_only"


class HandlingCorroboration(EngineeringModel):
    """Two-strand qualification status for one phase observation.

    Strand A is the kinematic residual (speed x path-curvature - yaw_rate),
    which equals the planar sideslip rate. Strand B is the steering-demand-to-
    response relationship (steering demand per achieved path curvature) at
    comparable speeds. Both strands must be qualified and aligned before a
    deficit/excess signature may carry a canonical tight/loose-family symptom.

    Dependence audit: the two strands share measured path curvature and the
    same run-local reference lap group. They are complementary relationships,
    not statistically independent evidence; corroboration qualifies the
    symptom mapping and can never inflate independent evidence-unit counts.
    """

    kinematic_residual_strand_qualified: bool = False
    steering_response_strand_qualified: bool = False
    steering_response_direction: str | None = Field(
        default=None, pattern=r"^(elevated|reduced)$",
    )
    aligned: bool = False
    corroborated: bool = False
    shared_input_channels: tuple[str, ...] = ("curvature_1_per_m",)
    shared_reference_laps: bool = True
    independence_qualification: str = Field(
        default=(
            "The kinematic residual and the steering-demand strand share "
            "measured path curvature and the same run-local reference lap "
            "group; they are complementary relationships, not statistically "
            "independent evidence."
        ),
        min_length=1,
    )


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
    steering_demand_per_curvature_median_deg_per_inv_m: float | None = Field(default=None, ge=0.0)
    steering_demand_relative_deviation_scale_units: float | None = None
    speed_median_mps: float | None = Field(default=None, ge=0.0)
    correction_count_median: float | None = Field(default=None, ge=0.0)
    max_yaw_rate_of_change_rad_s2: float | None = Field(default=None, ge=0.0)
    noise_scale_deficit_rad_s: float | None = Field(default=None, ge=0.0)
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    reference_lap_group: tuple[int, ...] = Field(default_factory=tuple)
    corroboration: HandlingCorroboration | None = None

    @model_validator(mode="after")
    def reference_laps_are_unique(self) -> HandlingPhaseObservation:
        if len(self.reference_lap_group) != len(set(self.reference_lap_group)):
            raise ValueError("reference lap group must be unique")
        return self


class HandlingBalanceAssessment(EngineeringModel):
    """One located, qualified handling observation with full provenance."""

    schema_version: str = "p-handling-balance.assessment.v2"
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
        if self.canonical_symptom_id is not None:
            if self.classification not in {
                HandlingClassification.ROTATION_RESPONSE_DEFICIT,
                HandlingClassification.ROTATION_RESPONSE_EXCESS,
            }:
                raise ValueError(
                    "a canonical symptom association requires a corroborated "
                    "deficit or excess signature; a kinematic residual or "
                    "steering-demand observation alone cannot carry one"
                )
            if not any(
                observation.corroboration is not None
                and observation.corroboration.corroborated
                for observation in self.phase_observations
            ):
                raise ValueError(
                    "a canonical symptom association requires two-strand "
                    "corroboration in the phase observations"
                )
        return self


class HandlingBalanceReport(EngineeringModel):
    """Run-level aggregation of handling-balance observations."""

    schema_version: str = "p-handling-balance.report.v2"
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
    "HandlingCorroboration",
    "HandlingPhaseObservation",
]
