from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from pydantic import ValidationError

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame
from racelab_engine.models.engineering_context import (
    ControlMutationEvent,
    ControlMutationKind,
)
from racelab_engine.models.engineering_awareness import ChannelRole
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.vehicle_engineering_profile import (
    build_vehicle_engineering_profile,
)
from racelab_engine.services.engineering_context_service import (
    build_steering_context_fingerprint,
    build_vehicle_compatibility_context,
    compare_steering_contexts,
    compare_vehicle_compatibility,
    confirm_requested_service,
    detect_control_mutations,
    engineering_channel_role,
)
from racelab_engine.services.vehicle_profile_service import (
    load_vehicle_profiles,
    resolve_vehicle_profile,
)


def _ffb_row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "SteeringWheelFFBEnabled": 1,
        "SteeringWheelMaxForceNm": 40.0,
        "SteeringWheelUseLinear": 1,
        "SteeringWheelPctIntensity": 0.8,
        "SteeringWheelPctSmoothing": 0.1,
        "SteeringWheelPctDamper": 0.05,
        "SteeringWheelLimiter": 0.2,
    }
    row.update(updates)
    return row


def _identity(**updates: object) -> dict[str, object]:
    identity: dict[str, object] = {
        "car_path": "stockcars chevycamarozl12022",
        "car_version": "2026.01.30.02",
        "iracing_build_version": "2026.02.02.02",
        "track_id": 447,
        "track_version": "2025.12.29.01",
    }
    identity.update(updates)
    return identity


def _compatibility(
    run_id: str,
    *,
    identity_updates: dict[str, object] | None = None,
    weight: float = 0.0,
    power: float = 0.0,
):
    return build_vehicle_compatibility_context(
        run_id=run_id,
        identity=_identity(**(identity_updates or {})),
        rows=[
            {
                "PlayerCarWeightPenalty": weight,
                "PlayerCarPowerAdjust": power,
                "PlayerTireCompound": 0,
            }
        ],
        source_artifact_ids=(f"manifest:{run_id}",),
    )


def test_new_context_aliases_have_row_vector_parity_and_keep_raw_inputs_separate() -> None:
    raw = {
        "SessionTime": 10.0,
        "Lap": 2,
        "LapDistPct": 0.5,
        "Throttle": 0.7,
        "ThrottleRaw": 0.8,
        "Brake": 0.1,
        "BrakeRaw": 0.2,
        "Clutch": 0.9,
        "ClutchRaw": 0.85,
        "Shifter": 4,
        "SteeringWheelMaxForceNm": 40.0,
        "SteeringWheelUseLinear": 1,
        "SteeringWheelPctIntensity": 0.8,
        "SteeringWheelPctSmoothing": 0.1,
        "SteeringWheelPctDamper": 0.05,
        "SteeringWheelLimiter": 0.2,
        "dcBrakeBias": 54.0,
        "dpRFTireColdPress": 165_000.0,
        "dpRTireChange": 1,
        "dpFuelAddKg": 20.0,
        "PlayerCarWeightPenalty": 15.0,
        "PlayerCarPowerAdjust": -2.0,
        "TireRF_RumblePitch": 120.0,
    }
    row = normalize_telemetry_rows([raw])[0]
    frame_row = normalize_telemetry_frame(pl.DataFrame([raw])).to_dicts()[0]
    aliases = (
        "throttle_raw_01",
        "brake_raw_01",
        "shifter_input",
        "steering_ffb_max_force_nm",
        "steering_ffb_use_linear",
        "steering_ffb_intensity_01",
        "steering_ffb_smoothing_01",
        "steering_ffb_damper_01",
        "steering_ffb_limiter_01",
        "applied_brake_bias",
        "requested_rf_tire_cold_pressure_pa",
        "requested_right_tire_change",
        "requested_fuel_add_kg",
        "player_car_weight_penalty_kg",
        "player_car_power_adjust_pct",
        "rf_rumble_pitch_hz",
    )

    assert all(row[name] == frame_row[name] for name in aliases)
    assert row["throttle_raw_01"] == 0.8
    assert row["throttle_01"] == 0.7
    assert row["brake_raw_01"] == 0.2
    assert row["brake_01"] == 0.1
    assert row["clutch_raw"] == 0.85
    assert row["clutch"] == 0.9
    assert (
        engineering_channel_role("steering_wheel_torque_subtick_nm")
        is ChannelRole.SUB_TICK_MEASUREMENT
    )
    assert (
        engineering_channel_role("requested_rf_tire_cold_pressure_pa")
        is ChannelRole.CONTROL_REQUEST
    )
    assert engineering_channel_role("future_unknown_channel") is None


def test_ffb_max_force_or_any_material_setting_mismatch_blocks_effort_comparison() -> None:
    baseline = build_steering_context_fingerprint([_ffb_row()])
    changed = build_steering_context_fingerprint(
        [_ffb_row(SteeringWheelMaxForceNm=55.0)]
    )
    same = build_steering_context_fingerprint([_ffb_row()])

    assert compare_steering_contexts(baseline, same).state == "comparable"
    assessment = compare_steering_contexts(baseline, changed)
    assert assessment.state == "not_comparable"
    assert assessment.steering_effort_comparison_allowed is False
    assert "max_force_nm" in assessment.material_mismatches


def test_incomplete_or_mutating_ffb_context_fails_closed() -> None:
    incomplete = build_steering_context_fingerprint(
        [{"SteeringWheelMaxForceNm": 40.0}]
    )
    mutating = build_steering_context_fingerprint(
        [_ffb_row(), _ffb_row(SteeringWheelPctSmoothing=0.3)]
    )

    assert incomplete.state == "limited"
    assert mutating.state == "limited"
    assert "smoothing_01" in mutating.missing_fields
    assert (
        compare_steering_contexts(incomplete, mutating).steering_effort_comparison_allowed
        is False
    )


def test_requested_pit_control_is_not_applied_without_independent_confirmation() -> None:
    rows = [
        {
            "session_time": 10.0,
            "lap": 2,
            "lap_dist_pct_100": 20.0,
            "dcBrakeBias": 52.0,
            "dpRFTireColdPress": 160_000.0,
        },
        {
            "session_time": 11.0,
            "lap": 2,
            "lap_dist_pct_100": 1.0,
            "dcBrakeBias": 54.0,
            "dpRFTireColdPress": 165_000.0,
        },
    ]
    events = detect_control_mutations(rows, run_id="run-1")
    applied = next(item for item in events if item.control_key == "applied_brake_bias")
    requested = next(
        item
        for item in events
        if item.control_key == "requested_rf_tire_cold_pressure_pa"
    )

    assert applied.mutation_kind is ControlMutationKind.APPLIED_STATE
    assert applied.context_revision == 2
    assert requested.mutation_kind is ControlMutationKind.REQUESTED_STATE
    assert requested.lap_pct == 1.0
    assert requested.applied_state_confirmed is False
    assert requested.confirmation_artifact_ids == ()
    with pytest.raises(ValueError, match="confirmation artifacts"):
        confirm_requested_service(
            requested,
            confirmation_artifact_ids=(),
            session_time=30.0,
            lap=3,
            lap_pct=1.0,
            context_revision=3,
        )
    confirmed = confirm_requested_service(
        requested,
        confirmation_artifact_ids=("tire-odometer-reset:rf", "pit-service-complete:3"),
        session_time=30.0,
        lap=3,
        lap_pct=1.0,
        context_revision=3,
    )
    assert confirmed.mutation_kind is ControlMutationKind.CONFIRMED_SERVICE
    assert confirmed.applied_state_confirmed is True


def test_control_contract_cannot_label_a_request_as_confirmed_service() -> None:
    with pytest.raises(ValidationError, match="requires confirmation artifacts"):
        ControlMutationEvent(
            mutation_id="mutation-1",
            run_id="run-1",
            control_key="requested_rf_tire_cold_pressure_pa",
            mutation_kind=ControlMutationKind.CONFIRMED_SERVICE,
            previous_value=160_000.0,
            new_value=165_000.0,
            session_time=11.0,
            lap=2,
            lap_pct=25.0,
            context_revision=2,
            evidence_state=EvidenceState.CALCULATED,
        )


@pytest.mark.parametrize(
    ("change", "field"),
    (
        ({"weight": 25.0}, "weight_penalty_kg"),
        ({"power": -3.0}, "power_adjust_pct"),
        (
            {"identity_updates": {"iracing_build_version": "2026.03.01.01"}},
            "iracing_build_version",
        ),
    ),
)
def test_weight_power_or_build_mismatch_blocks_causal_attribution(
    change: dict[str, object],
    field: str,
) -> None:
    baseline = _compatibility("run-a")
    test = _compatibility("run-b", **change)  # type: ignore[arg-type]
    assessment = compare_vehicle_compatibility(baseline, test)

    assert assessment.state == "not_comparable"
    assert field in assessment.material_mismatches
    assert assessment.observed_telemetry_allowed is True
    assert assessment.setup_attribution_allowed is False
    assert assessment.powertrain_attribution_allowed is False


def test_missing_bop_context_blocks_attribution_without_erasing_observation() -> None:
    baseline = _compatibility("run-a")
    missing = build_vehicle_compatibility_context(
        run_id="run-b",
        identity=_identity(),
        rows=[{}],
        source_artifact_ids=("manifest:run-b",),
    )
    assessment = compare_vehicle_compatibility(baseline, missing)

    assert assessment.state == "unavailable"
    assert assessment.observed_telemetry_allowed is True
    assert assessment.setup_attribution_allowed is False


def test_identity_only_next_gen_profile_leaves_geometry_missing_and_is_build_scoped() -> None:
    profiles = load_vehicle_profiles()
    resolution = resolve_vehicle_profile(
        car_path="stockcars chevycamarozl12022",
        car_version="2026.01.30.02",
        iracing_build_version="2026.02.02.02",
        profiles=profiles,
    )

    assert resolution.status == "ready"
    assert resolution.profile is not None
    assert resolution.profile.wheelbase_m is None
    assert resolution.profile.front_track_width_m is None
    assert resolution.profile.rear_track_width_m is None
    assert resolution.profile.steering_conversion_model is None
    incompatible = resolve_vehicle_profile(
        car_path="stockcars chevycamarozl12022",
        car_version="2026.01.30.02",
        iracing_build_version="2026.03.01.01",
        profiles=profiles,
    )
    assert incompatible.status == "incompatible"


def test_vehicle_profile_rejects_guessed_fields_and_hash_tampering() -> None:
    source = {
        "profile_id": "test-profile",
        "profile_version": 1,
        "car_path": "test-car",
        "car_version_range": {
            "minimum_inclusive": "1.0",
            "maximum_inclusive": "1.0",
        },
        "iracing_build_range": {
            "minimum_inclusive": "1.0",
            "maximum_inclusive": "1.0",
        },
        "source_provenance": [
            {
                "source_kind": "controlled_repository_evidence",
                "source_id": "fixture-1",
                "description": "Identity evidence only.",
            }
        ],
    }
    profile = build_vehicle_engineering_profile(source)
    with pytest.raises(ValidationError, match="hash does not match"):
        type(profile)(**{**profile.model_dump(), "profile_hash": "0" * 64})
    with pytest.raises(ValidationError):
        type(profile)(**{**profile.model_dump(), "total_vehicle_width_m": 1.9})


def test_profile_directory_is_repository_owned() -> None:
    profile_path = Path(
        "racelab_engine/knowledge/vehicle_profiles/"
        "stockcars_chevycamarozl12022_identity.json"
    )
    assert profile_path.exists()
