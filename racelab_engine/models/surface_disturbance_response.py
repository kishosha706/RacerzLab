"""Observation-only response signatures for repeated surface disturbances.

The contracts in this module deliberately describe measured channel response.
They cannot identify the track input, select a damper row, or carry setup
authority.  A physical lap plus a qualified canonical clock is required for
every episode.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.engineering_awareness import DerivedMetricContract
from racelab_engine.models.evidence import EngineeringBlocker, EvidenceState


Corner = Literal["lf", "rf", "lr", "rr"]


class SurfaceDisturbanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PhysicalLapScope(SurfaceDisturbanceModel):
    """One immutable, non-wrapping physical window on one qualified lap."""

    run_id: str = Field(min_length=1)
    source_file_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Server-verified SHA-256 of the original immutable telemetry file.",
    )
    source_artifact_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    track_identity: str = Field(min_length=1)
    build_identity: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_is_complete: bool
    lap_is_eligible: bool
    context_blockers: tuple[EngineeringBlocker, ...] = ()

    @model_validator(mode="after")
    def physical_scope_is_bounded(self) -> Self:
        if self.lap_pct_end <= self.lap_pct_start:
            raise ValueError("surface-response scope must be a non-empty physical window")
        return self


class EmpiricalNoiseFloor(SurfaceDisturbanceModel):
    channel: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    baseline_sample_count: int = Field(ge=5)
    baseline_center: float = Field(allow_inf_nan=False)
    robust_noise_floor: float = Field(ge=0.0, allow_inf_nan=False)
    observed_baseline_excursion: float = Field(ge=0.0, allow_inf_nan=False)
    onset_excursion_threshold: float = Field(gt=0.0, allow_inf_nan=False)


class CornerSettlingResponse(SurfaceDisturbanceModel):
    corner: Corner
    shock_velocity_onset_canonical_time_s: float = Field(allow_inf_nan=False)
    shock_travel_onset_canonical_time_s: float = Field(allow_inf_nan=False)
    observed_velocity_lag_s: float = Field(ge=0.0, allow_inf_nan=False)
    observed_travel_lag_s: float = Field(ge=0.0, allow_inf_nan=False)
    peak_abs_shock_velocity_in_s: float = Field(ge=0.0, allow_inf_nan=False)
    peak_abs_shock_travel_delta_in: float = Field(ge=0.0, allow_inf_nan=False)
    shock_velocity_overshoot_fraction: float = Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    shock_travel_overshoot_fraction: float = Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    velocity_settling_duration_s: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    travel_settling_duration_s: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    velocity_oscillation_count: int = Field(ge=0)
    travel_oscillation_count: int = Field(ge=0)
    settling_right_censored: bool
    source_channels: tuple[str, str]

    @model_validator(mode="after")
    def censored_state_matches_settling(self) -> Self:
        missing = (
            self.velocity_settling_duration_s is None
            or self.travel_settling_duration_s is None
        )
        if self.settling_right_censored != missing:
            raise ValueError("corner settling censor state must match observed durations")
        if len(set(self.source_channels)) != 2:
            raise ValueError("corner response requires distinct velocity and travel channels")
        return self


class PlatformYawSettlingResponse(SurfaceDisturbanceModel):
    platform_basis: Literal["four_corner_shock_travel_proxy"] = (
        "four_corner_shock_travel_proxy"
    )
    platform_response_onset_canonical_time_s: float = Field(allow_inf_nan=False)
    yaw_response_onset_canonical_time_s: float = Field(allow_inf_nan=False)
    observed_platform_lag_s: float = Field(ge=0.0, allow_inf_nan=False)
    observed_yaw_lag_s: float = Field(ge=0.0, allow_inf_nan=False)
    peak_platform_motion_proxy_in: float = Field(ge=0.0, allow_inf_nan=False)
    peak_front_heave_proxy_in: float = Field(ge=0.0, allow_inf_nan=False)
    peak_rear_heave_proxy_in: float = Field(ge=0.0, allow_inf_nan=False)
    peak_pitch_proxy_in: float = Field(ge=0.0, allow_inf_nan=False)
    peak_front_roll_proxy_in: float = Field(ge=0.0, allow_inf_nan=False)
    peak_rear_roll_proxy_in: float = Field(ge=0.0, allow_inf_nan=False)
    peak_abs_yaw_rate_delta_rad_s: float = Field(ge=0.0, allow_inf_nan=False)
    platform_overshoot_fraction: float = Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    yaw_overshoot_fraction: float = Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    platform_settling_duration_s: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    yaw_settling_duration_s: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    platform_oscillation_count: int = Field(ge=0)
    yaw_correction_count: int = Field(ge=0)
    settling_right_censored: bool
    source_channels: tuple[str, ...] = Field(min_length=5)
    evidence_state: Literal[EvidenceState.ESTIMATED_PROXY] = (
        EvidenceState.ESTIMATED_PROXY
    )

    @model_validator(mode="after")
    def platform_proxy_is_complete(self) -> Self:
        missing = (
            self.platform_settling_duration_s is None
            or self.yaw_settling_duration_s is None
        )
        if self.settling_right_censored != missing:
            raise ValueError("platform/yaw censor state must match observed durations")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("platform/yaw source channels must be unique")
        return self


class SurfaceDisturbanceEpisodeSignature(SurfaceDisturbanceModel):
    episode_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    telemetry_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: PhysicalLapScope
    disturbance_onset_canonical_time_s: float = Field(allow_inf_nan=False)
    disturbance_onset_lap_pct: float = Field(
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
    )
    peak_vertical_acceleration_delta_mps2: float = Field(
        ge=0.0,
        allow_inf_nan=False,
    )
    corner_responses: tuple[CornerSettlingResponse, ...] = Field(
        min_length=4,
        max_length=4,
    )
    platform_yaw_response: PlatformYawSettlingResponse
    median_speed_mps: float = Field(ge=0.0, allow_inf_nan=False)
    speed_min_mps: float = Field(ge=0.0, allow_inf_nan=False)
    speed_max_mps: float = Field(ge=0.0, allow_inf_nan=False)
    physical_sample_resolution_pct: float = Field(gt=0.0, allow_inf_nan=False)
    sample_count: int = Field(ge=16)
    sample_coverage: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    noise_floor_by_channel: tuple[EmpiricalNoiseFloor, ...] = Field(min_length=10)
    source_channels: tuple[str, ...] = Field(min_length=13)
    clock_source_channels: tuple[str, ...] = Field(min_length=1)
    clock_primary: Literal["session_tick"] = "session_tick"
    clock_state: Literal["qualified"] = "qualified"
    track_input_directly_measured: Literal[False] = False
    nominal_vehicle_constants_used: Literal[False] = False
    evidence_state: Literal[EvidenceState.OBSERVED_CORRELATION] = (
        EvidenceState.OBSERVED_CORRELATION
    )
    authority: Literal["observation_only"] = "observation_only"
    cause_attribution_available: Literal[False] = False
    setup_direction_available: Literal[False] = False

    @property
    def independence_unit_id(self) -> str:
        return f"{self.scope.source_file_sha256}:lap:{self.scope.lap_number}"

    @property
    def telemetry_content_unit_id(self) -> str:
        return f"{self.telemetry_content_sha256}:lap:{self.scope.lap_number}"

    @model_validator(mode="after")
    def episode_is_exact_and_non_authoritative(self) -> Self:
        if {item.corner for item in self.corner_responses} != {"lf", "rf", "lr", "rr"}:
            raise ValueError("surface response requires every shock corner exactly once")
        if not (
            self.scope.lap_pct_start
            <= self.disturbance_onset_lap_pct
            <= self.scope.lap_pct_end
        ):
            raise ValueError("disturbance onset must be inside the physical scope")
        if self.speed_min_mps > self.median_speed_mps or self.median_speed_mps > self.speed_max_mps:
            raise ValueError("episode speed context is not ordered")
        noise_channels = [item.channel for item in self.noise_floor_by_channel]
        if len(noise_channels) != len(set(noise_channels)):
            raise ValueError("episode noise floors require unique channel identities")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("episode source channels must be unique")
        if len(self.clock_source_channels) != len(set(self.clock_source_channels)):
            raise ValueError("episode clock source channels must be unique")
        return self


class SurfaceDisturbanceEpisodeResult(SurfaceDisturbanceModel):
    status: Literal["qualified", "limited", "unavailable"]
    episode: SurfaceDisturbanceEpisodeSignature | None = None
    blockers: tuple[EngineeringBlocker, ...] = ()
    required_measurements: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def result_is_fail_closed(self) -> Self:
        if self.status == "qualified" and (self.episode is None or self.blockers):
            raise ValueError("qualified episodes require one artifact and no blockers")
        if self.status == "limited" and (self.episode is None or not self.blockers):
            raise ValueError("limited episodes require an artifact and blockers")
        if self.status == "unavailable" and (self.episode is not None or not self.blockers):
            raise ValueError("unavailable episodes require blockers and no artifact")
        return self


class SurfaceDisturbanceSettlingSignature(SurfaceDisturbanceModel):
    signature_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    track_identity: str = Field(min_length=1)
    build_identity: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    episodes: tuple[SurfaceDisturbanceEpisodeSignature, ...] = Field(min_length=2)
    repetition_count: int = Field(ge=2)
    disturbance_onset_median_lap_pct: float = Field(
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
    )
    disturbance_onset_span_pct: float = Field(ge=0.0, allow_inf_nan=False)
    physical_repetition_tolerance_pct: float = Field(gt=0.0, allow_inf_nan=False)
    median_speed_mps: float = Field(ge=0.0, allow_inf_nan=False)
    speed_min_mps: float = Field(ge=0.0, allow_inf_nan=False)
    speed_max_mps: float = Field(ge=0.0, allow_inf_nan=False)
    aggregate_noise_floor_by_channel: tuple[EmpiricalNoiseFloor, ...] = Field(
        min_length=10
    )
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_file_sha256s: tuple[str, ...] = Field(min_length=1)
    telemetry_content_sha256s: tuple[str, ...] = Field(min_length=1)
    independence_unit_ids: tuple[str, ...] = Field(min_length=2)
    source_channels: tuple[str, ...] = Field(min_length=13)
    clock_source_channels: tuple[str, ...] = Field(min_length=1)
    track_input_directly_measured: Literal[False] = False
    nominal_vehicle_constants_used: Literal[False] = False
    evidence_state: Literal[EvidenceState.OBSERVED_CORRELATION] = (
        EvidenceState.OBSERVED_CORRELATION
    )
    authority: Literal["observation_only"] = "observation_only"
    cause_attribution_available: Literal[False] = False
    setup_direction_available: Literal[False] = False

    @model_validator(mode="after")
    def signature_uses_independent_physical_repetitions(self) -> Self:
        if self.repetition_count != len(self.episodes):
            raise ValueError("repetition count must equal the exact episode cohort")
        if len({item.episode_id for item in self.episodes}) != len(self.episodes):
            raise ValueError("settling signatures require unique episode identities")
        expected_units = tuple(item.independence_unit_id for item in self.episodes)
        if self.independence_unit_ids != expected_units or len(set(expected_units)) != len(
            expected_units
        ):
            raise ValueError("settling repetitions require distinct recording/lap units")
        expected_source_files = tuple(
            dict.fromkeys(item.scope.source_file_sha256 for item in self.episodes)
        )
        if self.source_file_sha256s != expected_source_files:
            raise ValueError("signature source-file hashes must match the episode cohort")
        expected_content = tuple(
            dict.fromkeys(item.telemetry_content_sha256 for item in self.episodes)
        )
        if self.telemetry_content_sha256s != expected_content:
            raise ValueError("signature telemetry-content hashes must match the cohort")
        if self.disturbance_onset_span_pct > self.physical_repetition_tolerance_pct:
            raise ValueError("disturbance episodes are not repeated at one physical location")
        if self.speed_min_mps > self.median_speed_mps or self.median_speed_mps > self.speed_max_mps:
            raise ValueError("signature speed context is not ordered")
        return self


class SurfaceDisturbanceSettlingReport(SurfaceDisturbanceModel):
    status: Literal["ready", "limited", "unavailable"]
    contract: DerivedMetricContract
    signature: SurfaceDisturbanceSettlingSignature | None = None
    blockers: tuple[EngineeringBlocker, ...] = ()
    required_measurements: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"
    cause_attribution_available: Literal[False] = False
    setup_direction_available: Literal[False] = False

    @model_validator(mode="after")
    def report_is_fail_closed(self) -> Self:
        if self.status == "ready" and (self.signature is None or self.blockers):
            raise ValueError("ready settling reports require a signature and no blockers")
        if self.status == "limited" and (self.signature is None or not self.blockers):
            raise ValueError("limited settling reports require a signature and blockers")
        if self.status == "unavailable" and (
            self.signature is not None or not self.blockers
        ):
            raise ValueError("unavailable settling reports require blockers and no signature")
        return self


__all__ = [
    "CornerSettlingResponse",
    "EmpiricalNoiseFloor",
    "PhysicalLapScope",
    "PlatformYawSettlingResponse",
    "SurfaceDisturbanceEpisodeResult",
    "SurfaceDisturbanceEpisodeSignature",
    "SurfaceDisturbanceSettlingReport",
    "SurfaceDisturbanceSettlingSignature",
]
