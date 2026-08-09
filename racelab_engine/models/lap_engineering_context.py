"""Typed per-lap engineering context with explicit channel update semantics."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ChannelUpdateSemantic(str, Enum):
    CONTINUOUS = "continuous"
    PIT_SNAPSHOT = "pit_snapshot"
    CONSTANT = "constant"
    MISSING = "missing"
    UNHEALTHY = "unhealthy"


class ChannelSemantic(ContextModel):
    channel: str = Field(min_length=1)
    source_raw_names: tuple[str, ...] = ()
    semantic: ChannelUpdateSemantic
    sample_count: int = Field(ge=0)
    finite_sample_count: int = Field(ge=0)
    distinct_value_count: int = Field(ge=0)
    finite_coverage_fraction: float = Field(ge=0.0, le=1.0)
    start_value: float | None = Field(default=None, allow_inf_nan=False)
    end_value: float | None = Field(default=None, allow_inf_nan=False)
    minimum_value: float | None = Field(default=None, allow_inf_nan=False)
    maximum_value: float | None = Field(default=None, allow_inf_nan=False)
    observation_timing: Literal["live", "pit_boundary", "session_constant", "none"]
    health_reason: str | None = None

    @model_validator(mode="after")
    def semantics_match_observed_values(self) -> ChannelSemantic:
        if self.finite_sample_count > self.sample_count:
            raise ValueError("finite samples cannot exceed total samples")
        if self.semantic is ChannelUpdateSemantic.MISSING and (
            self.finite_sample_count or self.distinct_value_count or self.observation_timing != "none"
        ):
            raise ValueError("missing channels cannot expose observed values")
        if self.semantic in {ChannelUpdateSemantic.MISSING, ChannelUpdateSemantic.UNHEALTHY}:
            if not self.health_reason:
                raise ValueError("missing and unhealthy channels require a health reason")
        if self.semantic is ChannelUpdateSemantic.PIT_SNAPSHOT and self.observation_timing != "pit_boundary":
            raise ValueError("snapshot channels must declare pit-boundary timing")
        if self.semantic is ChannelUpdateSemantic.CONTINUOUS and self.distinct_value_count < 2:
            raise ValueError("continuous channels require observed variation")
        return self


class TireCornerEngineeringContext(ContextModel):
    corner: Literal["lf", "rf", "lr", "rr"]
    surface_temperatures: tuple[ChannelSemantic, ...]
    carcass_temperatures: tuple[ChannelSemantic, ...]
    wear: tuple[ChannelSemantic, ...]
    pressure: ChannelSemantic
    odometer: ChannelSemantic


class WheelSpeedMismatchContext(ContextModel):
    corrected: ChannelSemantic
    raw: ChannelSemantic
    authority: Literal[
        "geometry_corrected",
        "geometry_contaminated_proxy",
        "unavailable",
    ]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def corrected_authority_requires_coverage(self) -> WheelSpeedMismatchContext:
        if (
            self.authority == "geometry_corrected"
            and self.corrected.semantic
            in {ChannelUpdateSemantic.MISSING, ChannelUpdateSemantic.UNHEALTHY}
        ):
            raise ValueError("corrected authority requires a healthy corrected channel")
        return self


class LapEngineeringContext(ContextModel):
    run_id: str = Field(min_length=1)
    lap_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    eligible: Literal[True] = True
    sample_count: int = Field(ge=1)
    fuel_level: ChannelSemantic
    air_temperature: ChannelSemantic
    track_temperature: ChannelSemantic
    wind_speed: ChannelSemantic
    wind_direction: ChannelSemantic
    tire_compound: str | None = None
    proximity_state: Literal[
        "no_nearby_car_reported",
        "nearby_car_ahead",
        "nearby_car_behind",
        "nearby_cars_ahead_and_behind",
        "context_unknown",
    ]
    proximity_coverage_fraction: float = Field(ge=0.0, le=1.0)
    nearby_traffic_exposure_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    tire_corners: tuple[TireCornerEngineeringContext, ...] = Field(min_length=4, max_length=4)
    rear_wheel_speed_mismatch: WheelSpeedMismatchContext
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def all_tire_corners_are_present_once(self) -> LapEngineeringContext:
        if {item.corner for item in self.tire_corners} != {"lf", "rf", "lr", "rr"}:
            raise ValueError("lap context requires all four tire corners exactly once")
        return self


class LapEngineeringContextReport(ContextModel):
    run_id: str = Field(min_length=1)
    status: Literal["ready", "limited", "blocked"]
    contexts: tuple[LapEngineeringContext, ...] = ()
    excluded_lap_numbers: tuple[int, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def report_scope_is_consistent(self) -> LapEngineeringContextReport:
        if any(item.run_id != self.run_id for item in self.contexts):
            raise ValueError("lap engineering contexts must match the report run")
        if self.status == "blocked" and (self.contexts or not self.blocker_reasons):
            raise ValueError("blocked context reports require blockers and no contexts")
        if self.status == "ready" and (not self.contexts or self.blocker_reasons):
            raise ValueError("ready context reports require contexts and no blockers")
        return self


__all__ = [
    "ChannelSemantic",
    "ChannelUpdateSemantic",
    "LapEngineeringContext",
    "LapEngineeringContextReport",
    "TireCornerEngineeringContext",
    "WheelSpeedMismatchContext",
]
