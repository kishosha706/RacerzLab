"""Observation-only chassis, tire, brake, acceleration, and disturbance artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.engineering_awareness import DerivedMetricContract
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.transient_awareness import ExactAnalysisWindow


class ExposureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CornerValue(ExposureModel):
    corner: Literal["lf", "rf", "lr", "rr"]
    value: float = Field(allow_inf_nan=False)


class ChassisResponseDescriptor(ExposureModel):
    metric_key: Literal["chassis_response_matrix"] = "chassis_response_matrix"
    artifact_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    window: ExactAnalysisWindow
    front_roll_motion_response_proxy: float | None = Field(
        default=None, allow_inf_nan=False
    )
    rear_roll_motion_response_proxy: float | None = Field(
        default=None, allow_inf_nan=False
    )
    pitch_motion_response_proxy: float | None = Field(default=None, allow_inf_nan=False)
    diagonal_motion_proxy: float = Field(allow_inf_nan=False)
    shock_abs_velocity_p50_by_corner: tuple[CornerValue, ...] = Field(
        min_length=4, max_length=4
    )
    shock_abs_velocity_p95_by_corner: tuple[CornerValue, ...] = Field(
        min_length=4, max_length=4
    )
    damper_band_classification_available: bool = False
    vehicle_profile_id: str | None = None
    vehicle_profile_hash: str | None = None
    sample_count: int = Field(ge=3)
    sample_coverage: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    evidence_state: Literal[EvidenceState.ESTIMATED_PROXY] = (
        EvidenceState.ESTIMATED_PROXY
    )
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def corners_and_profile_are_exact(self) -> ChassisResponseDescriptor:
        for values in (
            self.shock_abs_velocity_p50_by_corner,
            self.shock_abs_velocity_p95_by_corner,
        ):
            if {item.corner for item in values} != {"lf", "rf", "lr", "rr"}:
                raise ValueError(
                    "chassis response requires all four corners exactly once"
                )
        if (self.vehicle_profile_id is None) != (self.vehicle_profile_hash is None):
            raise ValueError("vehicle profile ID and hash must be present together")
        if (
            self.damper_band_classification_available
            and self.vehicle_profile_id is None
        ):
            raise ValueError(
                "damper-band classification requires a source-backed profile"
            )
        return self


class RelativeSlipExposureDescriptor(ExposureModel):
    metric_key: Literal["relative_slip_distance_exposure"] = (
        "relative_slip_distance_exposure"
    )
    artifact_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    window: ExactAnalysisWindow
    geometry_basis: Literal["straight_line", "verified_vehicle_profile"]
    exposure_m_by_corner: tuple[CornerValue, ...] = Field(min_length=4, max_length=4)
    vehicle_profile_id: str | None = None
    vehicle_profile_hash: str | None = None
    sample_count: int = Field(ge=3)
    evidence_state: Literal[EvidenceState.ESTIMATED_PROXY] = (
        EvidenceState.ESTIMATED_PROXY
    )
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def slip_basis_matches_profile(self) -> RelativeSlipExposureDescriptor:
        if {item.corner for item in self.exposure_m_by_corner} != {
            "lf",
            "rf",
            "lr",
            "rr",
        }:
            raise ValueError("slip exposure requires all four corners exactly once")
        has_profile = (
            self.vehicle_profile_id is not None
            and self.vehicle_profile_hash is not None
        )
        if self.geometry_basis == "verified_vehicle_profile" and not has_profile:
            raise ValueError(
                "corner-corrected slip exposure requires a verified profile"
            )
        if self.geometry_basis == "straight_line" and has_profile:
            raise ValueError("straight-line exposure cannot imply geometry correction")
        return self


class BrakePressureVelocityExposureDescriptor(ExposureModel):
    metric_key: Literal["brake_pressure_velocity_exposure"] = (
        "brake_pressure_velocity_exposure"
    )
    artifact_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    window: ExactAnalysisWindow
    exposure_bar_m_by_corner: tuple[CornerValue, ...] = Field(
        min_length=4, max_length=4
    )
    front_exposure_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    abs_intervention_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    sample_count: int = Field(ge=3)
    evidence_state: Literal[EvidenceState.ESTIMATED_PROXY] = (
        EvidenceState.ESTIMATED_PROXY
    )
    authority: Literal["observation_only"] = "observation_only"


class TireThermalCornerResponse(ExposureModel):
    corner: Literal["lf", "rf", "lr", "rr"]
    surface_temperature_change_c: float | None = Field(
        default=None, allow_inf_nan=False
    )
    running_pressure_change: float | None = Field(default=None, allow_inf_nan=False)
    tire_distance_change_m: float | None = Field(
        default=None, ge=0.0, allow_inf_nan=False
    )
    inner_middle_outer_gradient_change_c: float | None = Field(
        default=None, allow_inf_nan=False
    )


class TireThermalResponseDescriptor(ExposureModel):
    metric_key: Literal["tire_thermal_response"] = "tire_thermal_response"
    artifact_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    window: ExactAnalysisWindow
    corner_responses: tuple[TireThermalCornerResponse, ...] = Field(
        min_length=4, max_length=4
    )
    continuous_source_channels: tuple[str, ...] = Field(min_length=1)
    snapshot_channels_excluded: tuple[str, ...] = ()
    associated_slip_artifact_ids: tuple[str, ...] = ()
    associated_brake_artifact_ids: tuple[str, ...] = ()
    sample_count: int = Field(ge=3)
    evidence_state: Literal[EvidenceState.OBSERVED_CORRELATION] = (
        EvidenceState.OBSERVED_CORRELATION
    )
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def thermal_response_has_exact_corners(self) -> TireThermalResponseDescriptor:
        if {item.corner for item in self.corner_responses} != {"lf", "rf", "lr", "rr"}:
            raise ValueError("thermal response requires all four corners exactly once")
        if set(self.continuous_source_channels) & set(self.snapshot_channels_excluded):
            raise ValueError(
                "snapshot channels cannot become continuous thermal evidence"
            )
        return self


class CombinedAccelerationOccupancyDescriptor(ExposureModel):
    metric_key: Literal["observed_combined_acceleration_occupancy"] = (
        "observed_combined_acceleration_occupancy"
    )
    artifact_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    window: ExactAnalysisWindow
    point_count: int = Field(ge=3)
    lateral_abs_p95_mps2: float = Field(ge=0.0, allow_inf_nan=False)
    longitudinal_abs_p95_mps2: float = Field(ge=0.0, allow_inf_nan=False)
    combined_magnitude_p50_mps2: float = Field(ge=0.0, allow_inf_nan=False)
    combined_magnitude_p95_mps2: float = Field(ge=0.0, allow_inf_nan=False)
    gravity_compensated: Literal[False] = False
    banking_compensated: Literal[False] = False
    evidence_state: Literal[EvidenceState.CALCULATED] = EvidenceState.CALCULATED
    authority: Literal["observation_only"] = "observation_only"


class TrackDisturbanceSignature(ExposureModel):
    metric_key: Literal["track_disturbance_signature"] = "track_disturbance_signature"
    signature_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    track_identity: str = Field(min_length=1)
    build_identity: str = Field(min_length=1)
    lap_numbers: tuple[int, ...] = Field(min_length=2)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    first_affected_corner: Literal["lf", "rf", "lr", "rr"]
    corner_response_sequence: tuple[Literal["lf", "rf", "lr", "rr"], ...] = Field(
        min_length=4, max_length=4
    )
    vertical_acceleration_response_mps2: float = Field(ge=0.0, allow_inf_nan=False)
    shock_peak_abs_velocity_by_corner: tuple[CornerValue, ...] = Field(
        min_length=4, max_length=4
    )
    ride_height_response_by_corner: tuple[CornerValue, ...] = Field(
        min_length=4, max_length=4
    )
    oscillation_count: int = Field(ge=0)
    settling_time_s: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    repetition_count: int = Field(ge=2)
    track_input_observation: str = Field(min_length=1)
    vehicle_response_observation: str = Field(min_length=1)
    driver_response_observation: str = Field(min_length=1)
    performance_consequence_observation: str = Field(min_length=1)
    source_channels: tuple[str, ...] = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = Field(min_length=2)
    evidence_state: Literal[EvidenceState.OBSERVED_CORRELATION] = (
        EvidenceState.OBSERVED_CORRELATION
    )
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def disturbance_scope_is_repeatable_and_noncausal(
        self,
    ) -> TrackDisturbanceSignature:
        if len(self.lap_numbers) != len(set(self.lap_numbers)):
            raise ValueError("disturbance signatures require distinct eligible laps")
        if self.repetition_count != len(self.lap_numbers):
            raise ValueError("disturbance repetition count must equal exact cited laps")
        if (
            len(self.source_artifact_ids) != self.repetition_count
            or len(set(self.source_artifact_ids)) != self.repetition_count
        ):
            raise ValueError(
                "every disturbance repetition requires one distinct source artifact"
            )
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("disturbance peak must be inside its physical window")
        if set(self.corner_response_sequence) != {"lf", "rf", "lr", "rr"}:
            raise ValueError("disturbance response sequence requires every corner once")
        if "not directly measured" not in self.track_input_observation.lower():
            raise ValueError(
                "disturbance signatures must distinguish unmeasured track input from vehicle response"
            )
        return self


ExposureArtifact = (
    ChassisResponseDescriptor
    | RelativeSlipExposureDescriptor
    | BrakePressureVelocityExposureDescriptor
    | TireThermalResponseDescriptor
    | CombinedAccelerationOccupancyDescriptor
    | TrackDisturbanceSignature
)


class ExposureAnalysisResult(ExposureModel):
    status: Literal["ready", "limited", "blocked", "no_finding"]
    metric_key: str = Field(min_length=1)
    contract: DerivedMetricContract
    artifact: ExposureArtifact | None = None
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def result_status_matches_artifact(self) -> ExposureAnalysisResult:
        if self.status == "ready" and (self.artifact is None or self.blocker_reasons):
            raise ValueError(
                "ready exposure results require one artifact and no blockers"
            )
        if self.status in {"blocked", "no_finding"} and self.artifact is not None:
            raise ValueError(
                "blocked/no-finding exposure results cannot carry an artifact"
            )
        if self.status in {"limited", "blocked"} and not self.blocker_reasons:
            raise ValueError("limited/blocked exposure results require blockers")
        if self.artifact is not None and self.artifact.metric_key != self.metric_key:
            raise ValueError("exposure artifact metric identity must match its result")
        return self


__all__ = [
    "BrakePressureVelocityExposureDescriptor",
    "ChassisResponseDescriptor",
    "CombinedAccelerationOccupancyDescriptor",
    "CornerValue",
    "ExposureAnalysisResult",
    "RelativeSlipExposureDescriptor",
    "TireThermalCornerResponse",
    "TireThermalResponseDescriptor",
    "TrackDisturbanceSignature",
]
