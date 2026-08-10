"""Pure builders for P20 steering, control, and compatibility context."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

from racelab_engine.models.engineering_awareness import ChannelRole
from racelab_engine.models.engineering_context import (
    CompatibilityAssessment,
    ContextValue,
    ControlMutationEvent,
    ControlMutationKind,
    SteeringComparability,
    SteeringContextFingerprint,
    VehicleCompatibilityContext,
    steering_fingerprint_hash,
    vehicle_compatibility_hash,
)
from racelab_engine.models.evidence import EvidenceState

_FFB_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ffb_enabled", ("steering_ffb_enabled", "SteeringWheelFFBEnabled")),
    ("max_force_nm", ("steering_ffb_max_force_nm", "SteeringWheelMaxForceNm")),
    ("use_linear", ("steering_ffb_use_linear", "SteeringWheelUseLinear")),
    ("intensity_01", ("steering_ffb_intensity_01", "SteeringWheelPctIntensity")),
    ("smoothing_01", ("steering_ffb_smoothing_01", "SteeringWheelPctSmoothing")),
    ("damper_01", ("steering_ffb_damper_01", "SteeringWheelPctDamper")),
    ("limiter_01", ("steering_ffb_limiter_01", "SteeringWheelLimiter")),
)
P23_STEERING_FINGERPRINT_FIELDS: tuple[str, ...] = (
    "max_force_nm",
    "use_linear",
    "intensity_01",
    "smoothing_01",
    "damper_01",
    "limiter_01",
)
_CONTROL_SPECS: tuple[tuple[str, ControlMutationKind, tuple[str, ...]], ...] = (
    (
        "applied_brake_bias",
        ControlMutationKind.APPLIED_STATE,
        ("applied_brake_bias", "dcBrakeBias"),
    ),
    (
        "requested_lf_tire_cold_pressure_pa",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_lf_tire_cold_pressure_pa", "dpLFTireColdPress"),
    ),
    (
        "requested_rf_tire_cold_pressure_pa",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_rf_tire_cold_pressure_pa", "dpRFTireColdPress"),
    ),
    (
        "requested_lr_tire_cold_pressure_pa",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_lr_tire_cold_pressure_pa", "dpLRTireColdPress"),
    ),
    (
        "requested_rr_tire_cold_pressure_pa",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_rr_tire_cold_pressure_pa", "dpRRTireColdPress"),
    ),
    (
        "requested_left_tire_change",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_left_tire_change", "dpLTireChange"),
    ),
    (
        "requested_right_tire_change",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_right_tire_change", "dpRTireChange"),
    ),
    (
        "requested_fuel_fill",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_fuel_fill", "dpFuelFill"),
    ),
    (
        "requested_fuel_add_kg",
        ControlMutationKind.REQUESTED_STATE,
        ("requested_fuel_add_kg", "dpFuelAddKg"),
    ),
)
_CHANNEL_ROLES: dict[str, ChannelRole] = {
    "steering_ffb_enabled": ChannelRole.CONTEXT,
    "steering_ffb_max_force_nm": ChannelRole.CONTEXT,
    "steering_ffb_use_linear": ChannelRole.CONTEXT,
    "steering_ffb_intensity_01": ChannelRole.CONTEXT,
    "steering_ffb_smoothing_01": ChannelRole.CONTEXT,
    "steering_ffb_damper_01": ChannelRole.CONTEXT,
    "steering_ffb_limiter_01": ChannelRole.CONTEXT,
    "steering_wheel_torque_nm": ChannelRole.MEASUREMENT,
    "steering_wheel_torque_subtick_nm": ChannelRole.SUB_TICK_MEASUREMENT,
    "throttle_raw_01": ChannelRole.CONTROL_STATE,
    "brake_raw_01": ChannelRole.CONTROL_STATE,
    "clutch_raw": ChannelRole.CONTROL_STATE,
    "throttle_01": ChannelRole.CONTROL_STATE,
    "brake_01": ChannelRole.CONTROL_STATE,
    "clutch": ChannelRole.CONTROL_STATE,
    "shifter_input": ChannelRole.CONTROL_STATE,
    "applied_brake_bias": ChannelRole.CONTROL_STATE,
    "requested_lf_tire_cold_pressure_pa": ChannelRole.CONTROL_REQUEST,
    "requested_rf_tire_cold_pressure_pa": ChannelRole.CONTROL_REQUEST,
    "requested_lr_tire_cold_pressure_pa": ChannelRole.CONTROL_REQUEST,
    "requested_rr_tire_cold_pressure_pa": ChannelRole.CONTROL_REQUEST,
    "requested_left_tire_change": ChannelRole.CONTROL_REQUEST,
    "requested_right_tire_change": ChannelRole.CONTROL_REQUEST,
    "requested_fuel_fill": ChannelRole.CONTROL_REQUEST,
    "requested_fuel_add_kg": ChannelRole.CONTROL_REQUEST,
    "requested_fuel_auto_fill_enabled": ChannelRole.CONTROL_REQUEST,
    "requested_fuel_auto_fill_active": ChannelRole.CONTROL_REQUEST,
    "player_car_weight_penalty_kg": ChannelRole.COMPATIBILITY_IDENTITY,
    "player_car_power_adjust_pct": ChannelRole.COMPATIBILITY_IDENTITY,
    "player_track_surface": ChannelRole.CONTEXT,
    "player_track_surface_material": ChannelRole.CONTEXT,
    "lf_rumble_pitch_hz": ChannelRole.CONTEXT,
    "rf_rumble_pitch_hz": ChannelRole.CONTEXT,
    "lr_rumble_pitch_hz": ChannelRole.CONTEXT,
    "rr_rumble_pitch_hz": ChannelRole.CONTEXT,
}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def engineering_channel_role(channel: str) -> ChannelRole | None:
    """Return a known P20 role; unsupported channels deliberately remain unknown."""
    return _CHANNEL_ROLES.get(channel)


def _first_present(row: Mapping[str, Any], names: Sequence[str]) -> tuple[str | None, Any]:
    for name in names:
        if name in row and row[name] is not None:
            return name, row[name]
    return None, None


def _distinct_values(rows: Sequence[Mapping[str, Any]], names: Sequence[str]) -> tuple[str | None, tuple[Any, ...]]:
    source_name: str | None = None
    values: list[Any] = []
    for row in rows:
        name, value = _first_present(row, names)
        if name is None:
            continue
        source_name = source_name or name
        if not any(value == existing for existing in values):
            values.append(value)
    return source_name, tuple(values)


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    number = _finite(value)
    if number in {0.0, 1.0}:
        return bool(number)
    return None


def build_steering_context_fingerprint(
    rows: Sequence[Mapping[str, Any]],
    *,
    steering_conversion_model: str | None = None,
    required_fields: Sequence[str] | None = None,
) -> SteeringContextFingerprint:
    known_fields = {field_name for field_name, _names in _FFB_FIELDS}
    required = known_fields if required_fields is None else set(required_fields)
    unknown_required = required - known_fields
    if unknown_required:
        raise ValueError(
            "Unknown steering fingerprint field(s): "
            + ", ".join(sorted(unknown_required))
        )
    values: dict[str, Any] = {}
    source_channels: list[str] = []
    missing: list[str] = []
    blockers: list[str] = []
    for field_name, names in _FFB_FIELDS:
        source_name, distinct = _distinct_values(rows, names)
        if source_name is None or not distinct:
            values[field_name] = None
            if field_name in required:
                missing.append(field_name)
            continue
        source_channels.append(source_name)
        if len(distinct) != 1:
            values[field_name] = None
            missing.append(field_name)
            blockers.append(f"{field_name} changed inside the steering context window.")
            continue
        raw = distinct[0]
        if field_name in {"ffb_enabled", "use_linear"}:
            parsed: Any = _bool_value(raw)
        else:
            parsed = _finite(raw)
        if parsed is None or (
            field_name == "max_force_nm" and parsed <= 0.0
        ) or (
            field_name.endswith("_01") and not 0.0 <= parsed <= 1.0
        ):
            values[field_name] = None
            missing.append(field_name)
            blockers.append(f"{field_name} has an invalid or unsupported value.")
            continue
        values[field_name] = parsed
    if not source_channels:
        state = "unavailable"
        blockers.append("No force-feedback configuration channels are available.")
    elif missing or blockers:
        state = "limited"
        blockers.append("The complete material FFB configuration is not available.")
    else:
        state = "ready"
    fingerprint = steering_fingerprint_hash(
        **values,
        steering_conversion_model=steering_conversion_model,
    )
    return SteeringContextFingerprint(
        fingerprint_sha256=fingerprint,
        state=state,
        **values,
        steering_conversion_model=steering_conversion_model,
        source_channels=tuple(dict.fromkeys(source_channels)),
        missing_fields=tuple(dict.fromkeys(missing)),
        blocker_reasons=tuple(dict.fromkeys(blockers)),
    )


def compare_steering_contexts(
    baseline: SteeringContextFingerprint,
    test: SteeringContextFingerprint,
) -> SteeringComparability:
    if baseline.state != "ready" or test.state != "ready":
        blockers = tuple(
            dict.fromkeys(
                (
                    *baseline.blocker_reasons,
                    *test.blocker_reasons,
                    "Complete matching FFB fingerprints are required for steering-effort comparison.",
                )
            )
        )
        return SteeringComparability(
            state="unavailable",
            blocker_reasons=blockers,
            steering_effort_comparison_allowed=False,
        )
    field_names = (
        "ffb_enabled",
        "max_force_nm",
        "use_linear",
        "intensity_01",
        "smoothing_01",
        "damper_01",
        "limiter_01",
        "steering_conversion_model",
    )
    mismatches = tuple(
        name for name in field_names if getattr(baseline, name) != getattr(test, name)
    )
    if mismatches or baseline.fingerprint_sha256 != test.fingerprint_sha256:
        return SteeringComparability(
            state="not_comparable",
            material_mismatches=mismatches or ("fingerprint_sha256",),
            blocker_reasons=(
                (
                    "Material force-feedback configuration differs; steering workload "
                    "and effort proxies are not comparable."
                ),
            ),
            steering_effort_comparison_allowed=False,
        )
    return SteeringComparability(
        state="comparable",
        steering_effort_comparison_allowed=True,
    )


def _context_value(value: Any) -> ContextValue | None:
    if isinstance(value, (bool, str)):
        return value
    number = _finite(value)
    return number


def _value_changed(previous: ContextValue, current: ContextValue) -> bool:
    if isinstance(previous, (int, float)) and isinstance(current, (int, float)):
        return not math.isclose(float(previous), float(current), rel_tol=0.0, abs_tol=1e-9)
    return previous != current


def detect_control_mutations(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
) -> tuple[ControlMutationEvent, ...]:
    """Detect requests and applied control changes without conflating the two."""
    ordered = sorted(
        rows,
        key=lambda row: _finite(row.get("session_time", row.get("SessionTime")))
        if _finite(row.get("session_time", row.get("SessionTime"))) is not None
        else float("inf"),
    )
    events: list[ControlMutationEvent] = []
    context_revision = 1
    for control_key, mutation_kind, names in _CONTROL_SPECS:
        previous: ContextValue | None = None
        for row in ordered:
            _source, raw = _first_present(row, names)
            current = _context_value(raw)
            if current is None:
                continue
            if previous is None:
                previous = current
                continue
            if not _value_changed(previous, current):
                continue
            session_time = _finite(row.get("session_time", row.get("SessionTime")))
            lap = _finite(row.get("lap", row.get("lap_number", row.get("Lap"))))
            canonical_lap_pct = _finite(row.get("lap_dist_pct_100"))
            raw_lap_pct = _finite(row.get("LapDistPct"))
            lap_pct = canonical_lap_pct if canonical_lap_pct is not None else raw_lap_pct
            if (
                session_time is None
                or lap is None
                or not lap.is_integer()
                or lap_pct is None
            ):
                previous = current
                continue
            if canonical_lap_pct is None and 0.0 <= lap_pct <= 1.5:
                lap_pct *= 100.0
            if not 0.0 <= lap_pct <= 100.0:
                previous = current
                continue
            if mutation_kind is ControlMutationKind.APPLIED_STATE:
                context_revision += 1
            identity = (
                f"{run_id}|{control_key}|{session_time:.9f}|{lap:.0f}|{lap_pct:.9f}|"
                f"{previous!r}|{current!r}|{mutation_kind.value}"
            )
            mutation_id = "control:" + hashlib.sha256(identity.encode()).hexdigest()[:24]
            events.append(
                ControlMutationEvent(
                    mutation_id=mutation_id,
                    run_id=run_id,
                    control_key=control_key,
                    mutation_kind=mutation_kind,
                    previous_value=previous,
                    new_value=current,
                    session_time=session_time,
                    lap=int(lap),
                    lap_pct=lap_pct,
                    context_revision=context_revision,
                    evidence_state=EvidenceState.MEASURED,
                )
            )
            previous = current
    return tuple(sorted(events, key=lambda event: (event.session_time, event.control_key)))


def confirm_requested_service(
    request: ControlMutationEvent,
    *,
    confirmation_artifact_ids: Sequence[str],
    session_time: float,
    lap: int,
    lap_pct: float,
    context_revision: int,
) -> ControlMutationEvent:
    if request.mutation_kind is not ControlMutationKind.REQUESTED_STATE:
        raise ValueError("only a requested state can be linked to confirmed service")
    artifacts = tuple(dict.fromkeys(confirmation_artifact_ids))
    if not artifacts:
        raise ValueError("confirmed service requires independent confirmation artifacts")
    mutation_id = "service:" + hashlib.sha256(
        f"{request.mutation_id}|{'|'.join(artifacts)}".encode()
    ).hexdigest()[:24]
    return ControlMutationEvent(
        mutation_id=mutation_id,
        run_id=request.run_id,
        control_key=request.control_key,
        mutation_kind=ControlMutationKind.CONFIRMED_SERVICE,
        previous_value=request.previous_value,
        new_value=request.new_value,
        session_time=session_time,
        lap=lap,
        lap_pct=lap_pct,
        confirmation_artifact_ids=artifacts,
        context_revision=context_revision,
        evidence_state=EvidenceState.CALCULATED,
        applied_state_confirmed=True,
    )


def _constant_number(
    rows: Sequence[Mapping[str, Any]], names: Sequence[str]
) -> float | None:
    _source, values = _distinct_values(rows, names)
    parsed = {_finite(value) for value in values}
    parsed.discard(None)
    return next(iter(parsed)) if len(parsed) == 1 else None


def _constant_text(
    rows: Sequence[Mapping[str, Any]], names: Sequence[str]
) -> str | None:
    _source, values = _distinct_values(rows, names)
    parsed = {str(value).strip() for value in values if str(value).strip()}
    return next(iter(parsed)) if len(parsed) == 1 else None


def build_vehicle_compatibility_context(
    *,
    run_id: str,
    identity: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    source_artifact_ids: Sequence[str],
) -> VehicleCompatibilityContext:
    values: dict[str, Any] = {
        "car_path": identity.get("car_path"),
        "car_version": identity.get("car_version"),
        "iracing_build_version": identity.get("iracing_build_version"),
        "track_id": str(identity["track_id"]) if identity.get("track_id") is not None else None,
        "track_version": identity.get("track_version"),
        "session_regulations_id": identity.get("session_regulations_id"),
        "tire_compound": _constant_text(
            rows, ("player_tire_compound", "PlayerTireCompound")
        ),
        "weight_penalty_kg": _constant_number(
            rows,
            ("player_car_weight_penalty_kg", "PlayerCarWeightPenalty"),
        ),
        "power_adjust_pct": _constant_number(
            rows,
            ("player_car_power_adjust_pct", "PlayerCarPowerAdjust"),
        ),
        "repair_state": _constant_text(rows, ("repair_state",)),
    }
    missing = tuple(
        key
        for key in ("car_path", "car_version", "iracing_build_version")
        if not values[key]
    )
    context_sha = vehicle_compatibility_hash(run_id=run_id, **values)
    return VehicleCompatibilityContext(
        context_id=f"vehicle-context:{context_sha[:24]}",
        context_sha256=context_sha,
        run_id=run_id,
        **values,
        source_artifact_ids=tuple(dict.fromkeys(source_artifact_ids)),
        missing_fields=missing,
    )


def compare_vehicle_compatibility(
    baseline: VehicleCompatibilityContext,
    test: VehicleCompatibilityContext,
) -> CompatibilityAssessment:
    required = (
        "car_path",
        "car_version",
        "iracing_build_version",
        "weight_penalty_kg",
        "power_adjust_pct",
    )
    missing = tuple(
        f"{side}.{field}"
        for side, context in (("baseline", baseline), ("test", test))
        for field in required
        if getattr(context, field) is None
    )
    if missing:
        return CompatibilityAssessment(
            state="unavailable",
            blocker_reasons=(
                "Compatibility identity is incomplete for: " + ", ".join(missing) + ".",
            ),
            setup_attribution_allowed=False,
            powertrain_attribution_allowed=False,
        )
    compared_fields = (
        "car_path",
        "car_version",
        "iracing_build_version",
        "track_id",
        "track_version",
        "session_regulations_id",
        "tire_compound",
        "weight_penalty_kg",
        "power_adjust_pct",
        "repair_state",
    )
    mismatches = tuple(
        field for field in compared_fields if getattr(baseline, field) != getattr(test, field)
    )
    if mismatches:
        return CompatibilityAssessment(
            state="not_comparable",
            material_mismatches=mismatches,
            blocker_reasons=(
                (
                    "Material vehicle, build, regulation, or operating context differs; "
                    "setup and powertrain causal attribution are blocked."
                ),
            ),
            setup_attribution_allowed=False,
            powertrain_attribution_allowed=False,
        )
    return CompatibilityAssessment(
        state="compatible",
        setup_attribution_allowed=True,
        powertrain_attribution_allowed=True,
    )


__all__ = [
    "build_steering_context_fingerprint",
    "build_vehicle_compatibility_context",
    "compare_steering_contexts",
    "compare_vehicle_compatibility",
    "confirm_requested_service",
    "detect_control_mutations",
    "engineering_channel_role",
]
