"""Claim-bounded validation contracts for P20 descriptive proxies."""

from __future__ import annotations

from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


ProxyRelationship = Literal[
    "increase_with_reference",
    "decrease_with_reference",
    "same_direction",
    "known_delay",
    "known_onset",
]


class ProxyValidationContract(EvidenceLabModel):
    proxy_key: str = Field(min_length=1)
    proxy_version: str = Field(min_length=1)
    allowed_claim: str = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = Field(min_length=1)
    expected_physical_relationship: ProxyRelationship
    reference_measurements: tuple[str, ...] = Field(min_length=1)
    negative_control_ids: tuple[str, ...] = Field(min_length=1)
    sensitivity_test_ids: tuple[str, ...] = Field(min_length=1)
    context_dependencies: tuple[str, ...] = Field(min_length=1)
    failure_modes: tuple[str, ...] = Field(min_length=1)
    required_profile_fields: tuple[str, ...] = ()
    allowed_reference_semantics: tuple[
        Literal["continuous", "event_updated", "pit_snapshot"] , ...
    ] = ("continuous", "event_updated")
    independence_unit: Literal["event", "lap", "stint", "run", "session"]
    authority_ceiling: Literal["descriptive_proxy"] = "descriptive_proxy"

    @model_validator(mode="after")
    def validation_contract_is_canonical(self) -> ProxyValidationContract:
        for values, label in (
            (self.forbidden_claims, "forbidden claim"),
            (self.reference_measurements, "reference measurement"),
            (self.negative_control_ids, "negative control"),
            (self.sensitivity_test_ids, "sensitivity test"),
            (self.context_dependencies, "context dependency"),
            (self.failure_modes, "failure mode"),
            (self.required_profile_fields, "profile field"),
            (self.allowed_reference_semantics, "reference semantic"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique")
        return self


class ProxyValidationCase(EvidenceLabModel):
    case_id: str = Field(min_length=1)
    independence_unit_id: str = Field(min_length=1)
    context_key: str = Field(min_length=1)
    proxy_value: float | None = Field(default=None, allow_inf_nan=False)
    reference_value: float | None = Field(default=None, allow_inf_nan=False)
    expected_direction: Literal[-1, 0, 1] | None = None
    observed_direction: Literal[-1, 0, 1] | None = None
    localization_error: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    negative_control: bool = False
    proxy_fired: bool = False
    profile_fields_ready: bool = True
    context_ready: bool = True
    synthetic: bool = False
    reference_update_semantic: Literal[
        "continuous",
        "event_updated",
        "pit_snapshot",
        "constant",
        "missing",
        "unhealthy",
    ] = "continuous"


class ProxyValidationResult(EvidenceLabModel):
    proxy_key: str
    proxy_version: str
    case_count: int = Field(ge=0)
    independent_unit_count: int = Field(ge=0)
    real_world_unit_count: int = Field(ge=0)
    synthetic_unit_count: int = Field(ge=0)
    direction_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    negative_control_false_positive_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    median_localization_error: float | None = Field(default=None, ge=0.0)
    subgroup_results: dict[str, dict[str, float | int | None]]
    passed_mechanics: bool
    eligible_for_real_world_validation: bool
    blockers: tuple[str, ...]
    authority_ceiling: Literal["validation_only"] = "validation_only"


def evaluate_proxy_cases(
    contract: ProxyValidationContract,
    cases: tuple[ProxyValidationCase, ...],
) -> ProxyValidationResult:
    blockers: list[str] = []
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        blockers.append("Proxy validation case identities are duplicated.")
    blocked_cases = [
        case
        for case in cases
        if not case.profile_fields_ready
        or not case.context_ready
        or case.reference_update_semantic not in contract.allowed_reference_semantics
    ]
    if blocked_cases:
        blockers.append("Profile or context prerequisites failed for one or more cases.")
    direction_cases = [
        case
        for case in cases
        if case.expected_direction is not None and case.observed_direction is not None
    ]
    direction_accuracy = (
        None
        if not direction_cases
        else sum(
            case.expected_direction == case.observed_direction for case in direction_cases
        )
        / len(direction_cases)
    )
    negative_cases = [case for case in cases if case.negative_control]
    false_positive_rate = (
        None
        if not negative_cases
        else sum(case.proxy_fired for case in negative_cases) / len(negative_cases)
    )
    localization = [
        case.localization_error
        for case in cases
        if case.localization_error is not None
    ]
    units = {case.independence_unit_id for case in cases}
    real_units = {
        case.independence_unit_id for case in cases if not case.synthetic
    }
    synthetic_units = units - real_units
    subgroups: dict[str, dict[str, float | int | None]] = {}
    for context in sorted({case.context_key for case in cases}):
        group = [case for case in cases if case.context_key == context]
        group_direction = [
            case
            for case in group
            if case.expected_direction is not None and case.observed_direction is not None
        ]
        group_negative = [case for case in group if case.negative_control]
        subgroups[context] = {
            "independent_units": len(
                {case.independence_unit_id for case in group}
            ),
            "direction_accuracy": (
                None
                if not group_direction
                else sum(
                    case.expected_direction == case.observed_direction
                    for case in group_direction
                )
                / len(group_direction)
            ),
            "negative_control_false_positive_rate": (
                None
                if not group_negative
                else sum(case.proxy_fired for case in group_negative)
                / len(group_negative)
            ),
        }
    if not direction_cases:
        blockers.append("No direction-gradable proxy cases are available.")
    if not negative_cases:
        blockers.append("No proxy negative controls are available.")
    passed_mechanics = (
        direction_accuracy is not None
        and direction_accuracy == 1.0
        and false_positive_rate == 0.0
        and not blocked_cases
        and len(case_ids) == len(set(case_ids))
    )
    return ProxyValidationResult(
        proxy_key=contract.proxy_key,
        proxy_version=contract.proxy_version,
        case_count=len(cases),
        independent_unit_count=len(units),
        real_world_unit_count=len(real_units),
        synthetic_unit_count=len(synthetic_units),
        direction_accuracy=direction_accuracy,
        negative_control_false_positive_rate=false_positive_rate,
        median_localization_error=median(localization) if localization else None,
        subgroup_results=subgroups,
        passed_mechanics=passed_mechanics,
        eligible_for_real_world_validation=passed_mechanics and bool(real_units),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def p20_proxy_contracts() -> tuple[ProxyValidationContract, ...]:
    shared_forbidden = ("setup_target", "cause_probability", "tire_force")
    return (
        ProxyValidationContract(
            proxy_key="relative_slip_distance_exposure",
            proxy_version="p20-v1",
            allowed_claim="Relative wheel/vehicle speed disagreement exposure.",
            forbidden_claims=(
                *shared_forbidden,
                "friction_coefficient",
                "tire_wear",
                "tire_energy",
            ),
            expected_physical_relationship="increase_with_reference",
            reference_measurements=("labeled_wheel_slip_or_lock_event",),
            negative_control_ids=("no_wheel_slip", "geometry_missing"),
            sensitivity_test_ids=("known_slip_onset", "known_braking_lock"),
            context_dependencies=("phase", "yaw", "bank", "driven_axle"),
            failure_modes=("turn_geometry", "missing_track_width", "wheel_speed_semantics"),
            required_profile_fields=("wheel_speed_semantics",),
            allowed_reference_semantics=("continuous", "event_updated"),
            independence_unit="event",
        ),
        ProxyValidationContract(
            proxy_key="steering_effort_work_proxy",
            proxy_version="p20-v1",
            allowed_claim="Relative steering activity/work under one FFB fingerprint.",
            forbidden_claims=(*shared_forbidden, "driver_strength", "aligning_torque"),
            expected_physical_relationship="increase_with_reference",
            reference_measurements=("steering_torque_activity",),
            negative_control_ids=("stable_steering_response", "ffb_config_changed"),
            sensitivity_test_ids=("known_steering_activity_increase",),
            context_dependencies=("exact_ffb_fingerprint", "track_position"),
            failure_modes=("ffb_mismatch", "missing_ffb_enabled_state"),
            required_profile_fields=("steering_conversion",),
            independence_unit="session",
        ),
        ProxyValidationContract(
            proxy_key="yaw_response_delay",
            proxy_version="p20-v1",
            allowed_claim="Observed delay between steering demand and yaw response.",
            forbidden_claims=(*shared_forbidden, "body_sideslip"),
            expected_physical_relationship="known_delay",
            reference_measurements=("synthetic_known_yaw_delay", "external_yaw_reference"),
            negative_control_ids=("stable_steering_response",),
            sensitivity_test_ids=("known_yaw_lag",),
            context_dependencies=("sampling_integrity", "phase"),
            failure_modes=("input_filtering", "traffic", "track_transition"),
            required_profile_fields=("body_axes", "steering_conversion"),
            independence_unit="event",
        ),
        ProxyValidationContract(
            proxy_key="chassis_motion_response",
            proxy_version="p20-v1",
            allowed_claim="Relative chassis-motion response to an observed input.",
            forbidden_claims=(*shared_forbidden, "absolute_tire_load"),
            expected_physical_relationship="same_direction",
            reference_measurements=("ride_height_and_shock_response",),
            negative_control_ids=("constant_ride_height", "profile_build_mismatch"),
            sensitivity_test_ids=("known_ride_height_shift",),
            context_dependencies=("phase", "surface", "speed"),
            failure_modes=("sensor_location_unknown", "shock_sign_unknown"),
            required_profile_fields=("ride_height_sensor_interpretation",),
            independence_unit="event",
        ),
        ProxyValidationContract(
            proxy_key="thermal_response_lag",
            proxy_version="p20-v1",
            allowed_claim="Observed lag in dynamic thermal channels.",
            forbidden_claims=(*shared_forbidden, "tire_wear", "tire_energy"),
            expected_physical_relationship="known_delay",
            reference_measurements=("dynamic_surface_temperature",),
            negative_control_ids=("constant_carcass_temp", "constant_tread_wear"),
            sensitivity_test_ids=("known_thermal_lag",),
            context_dependencies=("channel_update_semantics", "pit_boundary"),
            failure_modes=("snapshot_channel_used_as_continuous",),
            allowed_reference_semantics=("continuous", "event_updated"),
            independence_unit="stint",
        ),
        ProxyValidationContract(
            proxy_key="combined_acceleration_occupancy",
            proxy_version="p20-v1",
            allowed_claim="Relative occupancy of observed acceleration combinations.",
            forbidden_claims=(*shared_forbidden, "friction_circle", "available_grip"),
            expected_physical_relationship="increase_with_reference",
            reference_measurements=("raw_acceleration_occupancy",),
            negative_control_ids=("stable_acceleration", "profile_build_mismatch"),
            sensitivity_test_ids=("known_acceleration_shift",),
            context_dependencies=("body_axes", "bank", "gravity"),
            failure_modes=("gravity_contamination", "axis_mismatch"),
            required_profile_fields=("body_axes",),
            independence_unit="lap",
        ),
        ProxyValidationContract(
            proxy_key="disturbance_settling",
            proxy_version="p20-v1",
            allowed_claim="Relative time for observed signals to return inside a noise band.",
            forbidden_claims=(*shared_forbidden, "damper_optimum"),
            expected_physical_relationship="known_delay",
            reference_measurements=("known_disturbance_and_recovery",),
            negative_control_ids=("no_real_setup_change",),
            sensitivity_test_ids=("known_settling_delay",),
            context_dependencies=("noise_floor", "phase", "surface"),
            failure_modes=("unbounded_noise", "new_disturbance_before_recovery"),
            independence_unit="event",
        ),
        ProxyValidationContract(
            proxy_key="platform_balance_migration",
            proxy_version="p20-v1",
            allowed_claim="Relative front/rear platform proxy migration within a clean stint.",
            forbidden_claims=(*shared_forbidden, "aerodynamic_balance", "downforce"),
            expected_physical_relationship="same_direction",
            reference_measurements=("matched_position_ride_height_state",),
            negative_control_ids=("same_setup_unchanged", "pit_context_boundary"),
            sensitivity_test_ids=("known_ride_height_shift",),
            context_dependencies=("fuel", "tire_state", "traffic", "weather"),
            failure_modes=("context_contamination", "sensor_interpretation_unknown"),
            required_profile_fields=("ride_height_sensor_interpretation",),
            independence_unit="stint",
        ),
    )


__all__ = [
    "ProxyValidationCase",
    "ProxyValidationContract",
    "ProxyValidationResult",
    "evaluate_proxy_cases",
    "p20_proxy_contracts",
]
