"""Exact control, steering, and compatibility context for P20 awareness."""

from __future__ import annotations

from enum import Enum
import hashlib
import json
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.evidence import EvidenceState


ContextValue: TypeAlias = float | int | bool | str


class EngineeringContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ControlMutationKind(str, Enum):
    APPLIED_STATE = "applied_state"
    REQUESTED_STATE = "requested_state"
    CONFIRMED_SERVICE = "confirmed_service"


class ControlMutationEvent(EngineeringContextModel):
    mutation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    control_key: str = Field(min_length=1)
    mutation_kind: ControlMutationKind
    previous_value: ContextValue | None = None
    new_value: ContextValue
    session_time: float = Field(ge=0.0, allow_inf_nan=False)
    lap: int = Field(ge=0)
    lap_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    confirmation_artifact_ids: tuple[str, ...] = ()
    context_revision: int = Field(ge=1)
    evidence_state: Literal[EvidenceState.MEASURED, EvidenceState.CALCULATED]
    authority: Literal["context_only"] = "context_only"
    applied_state_confirmed: bool = False

    @model_validator(mode="after")
    def requested_state_never_becomes_applied_by_wording(self) -> ControlMutationEvent:
        if self.previous_value == self.new_value:
            raise ValueError("a control mutation requires a material value change")
        if len(self.confirmation_artifact_ids) != len(
            set(self.confirmation_artifact_ids)
        ) or any(not item for item in self.confirmation_artifact_ids):
            raise ValueError("confirmation artifact identities must be non-empty and unique")
        if self.mutation_kind is ControlMutationKind.CONFIRMED_SERVICE:
            if not self.confirmation_artifact_ids or not self.applied_state_confirmed:
                raise ValueError("confirmed service requires confirmation artifacts")
        elif self.applied_state_confirmed:
            raise ValueError("only confirmed service may claim service application")
        if (
            self.mutation_kind is ControlMutationKind.REQUESTED_STATE
            and self.confirmation_artifact_ids
        ):
            raise ValueError("a request cannot carry proof of completed service")
        return self


class SteeringContextFingerprint(EngineeringContextModel):
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["ready", "limited", "unavailable"]
    ffb_enabled: bool | None = None
    max_force_nm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    use_linear: bool | None = None
    intensity_01: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    smoothing_01: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    damper_01: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    limiter_01: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    steering_conversion_model: str | None = None
    source_channels: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["context_only"] = "context_only"

    @model_validator(mode="after")
    def fingerprint_status_is_fail_closed(self) -> SteeringContextFingerprint:
        for values, label in (
            (self.source_channels, "source channel"),
            (self.missing_fields, "missing field"),
            (self.blocker_reasons, "blocker"),
        ):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"{label} values must be non-empty and unique")
        if self.state == "ready" and (self.missing_fields or self.blocker_reasons):
            raise ValueError("ready steering fingerprints cannot carry missing fields or blockers")
        if self.state in {"limited", "unavailable"} and not self.blocker_reasons:
            raise ValueError("limited and unavailable steering fingerprints require blockers")
        if self.state == "unavailable" and self.source_channels:
            raise ValueError("unavailable steering fingerprints cannot claim source channels")
        if self.fingerprint_sha256 != steering_fingerprint_hash(
            ffb_enabled=self.ffb_enabled,
            max_force_nm=self.max_force_nm,
            use_linear=self.use_linear,
            intensity_01=self.intensity_01,
            smoothing_01=self.smoothing_01,
            damper_01=self.damper_01,
            limiter_01=self.limiter_01,
            steering_conversion_model=self.steering_conversion_model,
        ):
            raise ValueError("steering fingerprint hash does not match its configuration")
        return self


class SteeringComparability(EngineeringContextModel):
    state: Literal["comparable", "not_comparable", "unavailable"]
    material_mismatches: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    steering_effort_comparison_allowed: bool
    authority: Literal["context_gate"] = "context_gate"

    @model_validator(mode="after")
    def comparison_state_matches_gate(self) -> SteeringComparability:
        if self.state == "comparable" and (
            not self.steering_effort_comparison_allowed
            or self.material_mismatches
            or self.blocker_reasons
        ):
            raise ValueError("comparable steering context cannot carry mismatches")
        if self.state != "comparable" and self.steering_effort_comparison_allowed:
            raise ValueError("blocked steering context cannot allow effort comparison")
        if self.state != "comparable" and not self.blocker_reasons:
            raise ValueError("blocked steering comparability requires explicit blockers")
        return self


class VehicleCompatibilityContext(EngineeringContextModel):
    context_id: str = Field(min_length=1)
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    car_path: str | None = None
    car_version: str | None = None
    iracing_build_version: str | None = None
    track_id: str | None = None
    track_version: str | None = None
    session_regulations_id: str | None = None
    tire_compound: str | None = None
    weight_penalty_kg: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    power_adjust_pct: float | None = Field(default=None, allow_inf_nan=False)
    repair_state: str | None = None
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    missing_fields: tuple[str, ...] = ()
    authority: Literal["context_only"] = "context_only"

    @model_validator(mode="after")
    def compatibility_sources_are_canonical(self) -> VehicleCompatibilityContext:
        for values, label in (
            (self.source_artifact_ids, "source artifact"),
            (self.missing_fields, "missing field"),
        ):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"{label} values must be non-empty and unique")
        if self.context_sha256 != vehicle_compatibility_hash(
            run_id=self.run_id,
            car_path=self.car_path,
            car_version=self.car_version,
            iracing_build_version=self.iracing_build_version,
            track_id=self.track_id,
            track_version=self.track_version,
            session_regulations_id=self.session_regulations_id,
            tire_compound=self.tire_compound,
            weight_penalty_kg=self.weight_penalty_kg,
            power_adjust_pct=self.power_adjust_pct,
            repair_state=self.repair_state,
        ):
            raise ValueError("compatibility context hash does not match its exact values")
        return self


class CompatibilityAssessment(EngineeringContextModel):
    state: Literal["compatible", "not_comparable", "unavailable"]
    material_mismatches: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    observed_telemetry_allowed: Literal[True] = True
    setup_attribution_allowed: bool
    powertrain_attribution_allowed: bool
    authority: Literal["context_gate"] = "context_gate"

    @model_validator(mode="after")
    def attribution_gate_matches_state(self) -> CompatibilityAssessment:
        if self.state == "compatible" and (
            not self.setup_attribution_allowed
            or not self.powertrain_attribution_allowed
            or self.material_mismatches
            or self.blocker_reasons
        ):
            raise ValueError("compatible contexts cannot carry attribution blockers")
        if self.state != "compatible" and (
            self.setup_attribution_allowed or self.powertrain_attribution_allowed
        ):
            raise ValueError("incompatible or unavailable context must block attribution")
        if self.state != "compatible" and not self.blocker_reasons:
            raise ValueError("blocked compatibility requires explicit blockers")
        return self


def _sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def steering_fingerprint_hash(
    *,
    ffb_enabled: bool | None,
    max_force_nm: float | None,
    use_linear: bool | None,
    intensity_01: float | None,
    smoothing_01: float | None,
    damper_01: float | None,
    limiter_01: float | None,
    steering_conversion_model: str | None,
) -> str:
    return _sha256(
        {
            "ffb_enabled": ffb_enabled,
            "max_force_nm": max_force_nm,
            "use_linear": use_linear,
            "intensity_01": intensity_01,
            "smoothing_01": smoothing_01,
            "damper_01": damper_01,
            "limiter_01": limiter_01,
            "steering_conversion_model": steering_conversion_model,
        }
    )


def vehicle_compatibility_hash(
    *,
    run_id: str,
    car_path: str | None,
    car_version: str | None,
    iracing_build_version: str | None,
    track_id: str | None,
    track_version: str | None,
    session_regulations_id: str | None,
    tire_compound: str | None,
    weight_penalty_kg: float | None,
    power_adjust_pct: float | None,
    repair_state: str | None,
) -> str:
    return _sha256(
        {
            "run_id": run_id,
            "car_path": car_path,
            "car_version": car_version,
            "iracing_build_version": iracing_build_version,
            "track_id": track_id,
            "track_version": track_version,
            "session_regulations_id": session_regulations_id,
            "tire_compound": tire_compound,
            "weight_penalty_kg": weight_penalty_kg,
            "power_adjust_pct": power_adjust_pct,
            "repair_state": repair_state,
        }
    )


__all__ = [
    "CompatibilityAssessment",
    "ContextValue",
    "ControlMutationEvent",
    "ControlMutationKind",
    "SteeringComparability",
    "SteeringContextFingerprint",
    "VehicleCompatibilityContext",
    "steering_fingerprint_hash",
    "vehicle_compatibility_hash",
]
