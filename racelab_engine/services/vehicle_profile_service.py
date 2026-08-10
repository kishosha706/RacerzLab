"""Load and resolve immutable source-backed vehicle engineering profiles."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from racelab_engine.models.vehicle_engineering_profile import (
    VehicleEngineeringProfile,
    VehicleProfileResolution,
)


_DEFAULT_PROFILE_DIR = Path(__file__).resolve().parents[1] / "knowledge" / "vehicle_profiles"


def load_vehicle_profiles(
    directory: str | Path = _DEFAULT_PROFILE_DIR,
) -> tuple[VehicleEngineeringProfile, ...]:
    root = Path(directory)
    if not root.exists():
        return ()
    profiles: list[VehicleEngineeringProfile] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            profiles.append(VehicleEngineeringProfile.model_validate(payload))
        except (OSError, TypeError, ValueError, ValidationError) as exc:
            raise ValueError(f"Vehicle profile could not be validated: {path.name}: {exc}") from exc
    identities = [(profile.profile_id, profile.profile_version) for profile in profiles]
    if len(identities) != len(set(identities)):
        raise ValueError("Vehicle profile identity/version pairs must be unique")
    return tuple(profiles)


def resolve_vehicle_profile(
    *,
    car_path: str | None,
    car_version: str | None,
    iracing_build_version: str | None,
    profiles: tuple[VehicleEngineeringProfile, ...] | None = None,
) -> VehicleProfileResolution:
    if not car_path or not car_version or not iracing_build_version:
        return VehicleProfileResolution(
            status="unavailable",
            blocker_reasons=(
                "Car path, car version, and iRacing build are required for vehicle-profile resolution.",
            ),
        )
    candidates = tuple(
        profile
        for profile in (profiles if profiles is not None else load_vehicle_profiles())
        if profile.car_path == car_path
    )
    if not candidates:
        return VehicleProfileResolution(
            status="unavailable",
            blocker_reasons=(f"No source-backed vehicle profile exists for {car_path}.",),
        )
    matching = tuple(
        profile
        for profile in candidates
        if profile.car_version_range.contains(car_version)
        and profile.iracing_build_range.contains(iracing_build_version)
    )
    if not matching:
        return VehicleProfileResolution(
            status="incompatible",
            blocker_reasons=(
                "Available vehicle profiles do not cover this car version and iRacing build.",
            ),
        )
    if len(matching) != 1:
        return VehicleProfileResolution(
            status="incompatible",
            blocker_reasons=(
                "Multiple vehicle profiles overlap this car version/build; resolution is ambiguous.",
            ),
        )
    return VehicleProfileResolution(status="ready", profile=matching[0])


__all__ = ["load_vehicle_profiles", "resolve_vehicle_profile"]
