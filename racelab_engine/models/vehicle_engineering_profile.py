"""Versioned, source-backed vehicle engineering profile contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VehicleProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class VersionRange(VehicleProfileModel):
    minimum_inclusive: str = Field(min_length=1)
    maximum_inclusive: str = Field(min_length=1)

    @model_validator(mode="after")
    def range_is_ordered(self) -> VersionRange:
        if _version_key(self.maximum_inclusive) < _version_key(self.minimum_inclusive):
            raise ValueError("version range must be ordered")
        return self

    def contains(self, value: str) -> bool:
        key = _version_key(value)
        return _version_key(self.minimum_inclusive) <= key <= _version_key(
            self.maximum_inclusive
        )


class VehicleProfileProvenance(VehicleProfileModel):
    source_kind: Literal[
        "official_iracing_documentation",
        "ibt_session_yaml",
        "controlled_repository_evidence",
        "primary_engineering_reference",
    ]
    source_id: str = Field(min_length=1)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    description: str = Field(min_length=1)


class RideHeightSensorLocation(VehicleProfileModel):
    sensor_key: str = Field(min_length=1)
    longitudinal_m: float = Field(allow_inf_nan=False)
    lateral_m: float = Field(allow_inf_nan=False)
    vertical_m: float = Field(allow_inf_nan=False)


class DamperDiagnosticBand(VehicleProfileModel):
    band_key: str = Field(min_length=1)
    minimum_abs_velocity_mps: float = Field(ge=0.0, allow_inf_nan=False)
    maximum_abs_velocity_mps: float = Field(gt=0.0, allow_inf_nan=False)
    provenance_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def band_is_ordered(self) -> DamperDiagnosticBand:
        if self.maximum_abs_velocity_mps <= self.minimum_abs_velocity_mps:
            raise ValueError("damper diagnostic bands require a positive ordered range")
        return self


class VehicleEngineeringProfile(VehicleProfileModel):
    profile_id: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    car_path: str = Field(min_length=1)
    car_version_range: VersionRange
    iracing_build_range: VersionRange
    wheelbase_m: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    front_track_width_m: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    rear_track_width_m: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    driven_axle: Literal["front", "rear", "all"] | None = None
    steering_conversion_model: str | None = None
    ride_height_sensor_locations: tuple[RideHeightSensorLocation, ...] = ()
    shock_sign_convention: Literal[
        "compression_positive",
        "compression_negative",
    ] | None = None
    wheel_speed_semantics: str | None = None
    body_axis_convention: str | None = None
    damper_diagnostic_bands: tuple[DamperDiagnosticBand, ...] = ()
    supported_setup_controls: tuple[str, ...] = ()
    source_provenance: tuple[VehicleProfileProvenance, ...] = Field(min_length=1)
    profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def profile_is_source_backed_and_hash_stable(self) -> VehicleEngineeringProfile:
        sensor_keys = [item.sensor_key for item in self.ride_height_sensor_locations]
        band_keys = [item.band_key for item in self.damper_diagnostic_bands]
        provenance_ids = [item.source_id for item in self.source_provenance]
        for values, label in (
            (sensor_keys, "ride-height sensor"),
            (band_keys, "damper band"),
            (list(self.supported_setup_controls), "setup control"),
            (provenance_ids, "source provenance"),
        ):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"{label} values must be non-empty and unique")
        if self.profile_hash != vehicle_profile_hash(self.model_dump(exclude={"profile_hash"})):
            raise ValueError("vehicle profile hash does not match its source-backed content")
        return self


class VehicleProfileResolution(VehicleProfileModel):
    status: Literal["ready", "unavailable", "incompatible"]
    profile: VehicleEngineeringProfile | None = None
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def resolution_is_fail_closed(self) -> VehicleProfileResolution:
        if self.status == "ready" and (self.profile is None or self.blocker_reasons):
            raise ValueError("ready profile resolution requires one profile and no blockers")
        if self.status != "ready" and (self.profile is not None or not self.blocker_reasons):
            raise ValueError("blocked profile resolution requires blockers and no profile")
        return self


def vehicle_profile_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _version_key(value: str) -> tuple[int, tuple[int, ...] | tuple[str, ...]]:
    parts = value.split(".")
    if parts and all(part.isdigit() for part in parts):
        return (0, tuple(int(part) for part in parts))
    return (1, (value,))


def build_vehicle_engineering_profile(
    payload: dict[str, Any],
) -> VehicleEngineeringProfile:
    """Build a profile only after hashing the exact supplied source-backed fields."""
    if "profile_hash" in payload:
        raise ValueError("profile_hash is derived and cannot be caller-supplied")
    normalized = {
        "wheelbase_m": None,
        "front_track_width_m": None,
        "rear_track_width_m": None,
        "driven_axle": None,
        "steering_conversion_model": None,
        "ride_height_sensor_locations": [],
        "shock_sign_convention": None,
        "wheel_speed_semantics": None,
        "body_axis_convention": None,
        "damper_diagnostic_bands": [],
        "supported_setup_controls": [],
        **payload,
    }
    normalized["car_version_range"] = VersionRange.model_validate(
        normalized["car_version_range"]
    ).model_dump(mode="json")
    normalized["iracing_build_range"] = VersionRange.model_validate(
        normalized["iracing_build_range"]
    ).model_dump(mode="json")
    normalized["ride_height_sensor_locations"] = [
        RideHeightSensorLocation.model_validate(item).model_dump(mode="json")
        for item in normalized["ride_height_sensor_locations"]
    ]
    normalized["damper_diagnostic_bands"] = [
        DamperDiagnosticBand.model_validate(item).model_dump(mode="json")
        for item in normalized["damper_diagnostic_bands"]
    ]
    normalized["source_provenance"] = [
        VehicleProfileProvenance.model_validate(item).model_dump(mode="json")
        for item in normalized["source_provenance"]
    ]
    return VehicleEngineeringProfile(
        **normalized,
        profile_hash=vehicle_profile_hash(normalized),
    )


__all__ = [
    "DamperDiagnosticBand",
    "RideHeightSensorLocation",
    "VehicleEngineeringProfile",
    "VehicleProfileProvenance",
    "VehicleProfileResolution",
    "VersionRange",
    "build_vehicle_engineering_profile",
    "vehicle_profile_hash",
]
