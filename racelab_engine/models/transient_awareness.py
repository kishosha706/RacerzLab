"""Observation-only transient response and steering workload artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.engineering_awareness import DerivedMetricContract
from racelab_engine.models.evidence import EvidenceState


class TransientModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExactAnalysisWindow(TransientModel):
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    context_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    session_time_start: float = Field(ge=0.0, allow_inf_nan=False)
    session_time_end: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def window_is_ordered(self) -> ExactAnalysisWindow:
        if self.lap_pct_end < self.lap_pct_start:
            raise ValueError("analysis physical window must be ordered")
        if self.session_time_end < self.session_time_start:
            raise ValueError("analysis time window must be ordered")
        return self


class TransientResponseDescriptor(TransientModel):
    descriptor_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    window: ExactAnalysisWindow
    steering_onset_time_s: float = Field(ge=0.0, allow_inf_nan=False)
    yaw_onset_time_s: float = Field(ge=0.0, allow_inf_nan=False)
    lateral_accel_onset_time_s: float | None = Field(
        default=None, ge=0.0, allow_inf_nan=False
    )
    observed_yaw_response_delay_ms: float = Field(allow_inf_nan=False)
    observed_lateral_response_delay_ms: float | None = Field(
        default=None, allow_inf_nan=False
    )
    descriptive_rise_time_ms: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    peak_yaw_response_gain_proxy: float | None = Field(default=None, allow_inf_nan=False)
    overshoot_proxy_fraction: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    settling_time_s: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    steering_yaw_hysteresis_proxy: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    sample_count: int = Field(ge=3)
    sample_coverage: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    source_channels: tuple[str, ...] = Field(min_length=3)
    evidence_state: Literal[EvidenceState.CALCULATED] = EvidenceState.CALCULATED
    authority: Literal["observation_only"] = "observation_only"


class TransientResponseReport(TransientModel):
    status: Literal["ready", "limited", "blocked", "no_finding"]
    contract: DerivedMetricContract
    descriptor: TransientResponseDescriptor | None = None
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def response_status_matches_artifact(self) -> TransientResponseReport:
        if self.status == "ready" and (self.descriptor is None or self.blocker_reasons):
            raise ValueError("ready transient reports require one descriptor and no blockers")
        if self.status in {"blocked", "no_finding"} and self.descriptor is not None:
            raise ValueError("blocked/no-finding transient reports cannot carry a descriptor")
        if self.status in {"limited", "blocked"} and not self.blocker_reasons:
            raise ValueError("limited and blocked transient reports require blockers")
        return self


class SteeringWorkloadDescriptor(TransientModel):
    descriptor_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    window: ExactAnalysisWindow
    ffb_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    torque_sample_rate_hz: float = Field(gt=0.0, allow_inf_nan=False)
    torque_sample_count: int = Field(ge=3)
    sample_coverage: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    median_speed_mps: float = Field(ge=0.0, allow_inf_nan=False)
    torque_rms_nm: float = Field(ge=0.0, allow_inf_nan=False)
    torque_p95_nm: float = Field(ge=0.0, allow_inf_nan=False)
    peak_abs_torque_nm: float = Field(ge=0.0, allow_inf_nan=False)
    near_limiter_duty_fraction: float | None = Field(
        default=None, ge=0.0, le=1.0, allow_inf_nan=False
    )
    torque_reversal_rate_hz: float = Field(ge=0.0, allow_inf_nan=False)
    steering_rate_reversal_rate_hz: float = Field(ge=0.0, allow_inf_nan=False)
    high_frequency_variation_proxy_nm2: float = Field(ge=0.0, allow_inf_nan=False)
    steering_perturbation_index: float = Field(ge=0.0, allow_inf_nan=False)
    torque_angle_hysteresis_proxy_nm_rad: float = Field(ge=0.0, allow_inf_nan=False)
    steering_effort_work_proxy: float = Field(ge=0.0, allow_inf_nan=False)
    correction_density_per_s: float = Field(ge=0.0, allow_inf_nan=False)
    effort_per_achieved_curvature_proxy: float | None = Field(
        default=None, ge=0.0, allow_inf_nan=False
    )
    source_channels: tuple[str, ...] = Field(min_length=3)
    evidence_state: Literal[EvidenceState.ESTIMATED_PROXY] = EvidenceState.ESTIMATED_PROXY
    authority: Literal["observation_only"] = "observation_only"


class SteeringWorkloadReport(TransientModel):
    status: Literal["ready", "limited", "blocked", "no_finding"]
    contract: DerivedMetricContract
    descriptor: SteeringWorkloadDescriptor | None = None
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def workload_status_matches_artifact(self) -> SteeringWorkloadReport:
        if self.status == "ready" and (self.descriptor is None or self.blocker_reasons):
            raise ValueError("ready workload reports require one descriptor and no blockers")
        if self.status in {"blocked", "no_finding"} and self.descriptor is not None:
            raise ValueError("blocked/no-finding workload reports cannot carry a descriptor")
        if self.status in {"limited", "blocked"} and not self.blocker_reasons:
            raise ValueError("limited and blocked workload reports require blockers")
        return self


class SteeringWorkloadComparison(TransientModel):
    state: Literal["comparable", "not_comparable", "unavailable"]
    baseline_descriptor_id: str = Field(min_length=1)
    test_descriptor_id: str = Field(min_length=1)
    torque_rms_delta_nm: float | None = Field(default=None, allow_inf_nan=False)
    effort_work_proxy_delta: float | None = Field(default=None, allow_inf_nan=False)
    correction_density_delta_per_s: float | None = Field(default=None, allow_inf_nan=False)
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def comparison_is_fail_closed(self) -> SteeringWorkloadComparison:
        deltas = (
            self.torque_rms_delta_nm,
            self.effort_work_proxy_delta,
            self.correction_density_delta_per_s,
        )
        if self.state == "comparable" and (
            any(value is None for value in deltas) or self.blocker_reasons
        ):
            raise ValueError("comparable workload reports require deltas and no blockers")
        if self.state != "comparable" and (
            any(value is not None for value in deltas) or not self.blocker_reasons
        ):
            raise ValueError("blocked workload comparisons require blockers and no deltas")
        return self


__all__ = [
    "ExactAnalysisWindow",
    "SteeringWorkloadComparison",
    "SteeringWorkloadDescriptor",
    "SteeringWorkloadReport",
    "TransientResponseDescriptor",
    "TransientResponseReport",
]
