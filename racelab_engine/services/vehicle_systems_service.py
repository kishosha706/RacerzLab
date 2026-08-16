"""Compile P26 vehicle knowledge and project P19/P20 evidence onto it."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.io.telemetry_manifest import (
    MANIFEST_SCHEMA_VERSION,
    UNIVERSAL_ARCHIVE_VERSION,
    compatibility_fingerprint,
)
from racelab_engine.knowledge.setup import load_setup_knowledge
from racelab_engine.models.intelligence import InternalIntelligenceReport
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.models.vehicle_systems import (
    BuildApplicability,
    ComponentAwarenessState,
    ComponentControlledHistory,
    ComponentDefinition,
    ComponentInspectionResponse,
    ComponentInteraction,
    ComponentObservabilityContract,
    ComponentObservabilityState,
    ComponentObservationScope,
    ComponentRelevance,
    QuantityObservabilityCertificate,
    SetupExperimentFactor,
    VehicleSystemsEdge,
    VehicleSystemsEdgeKind,
    VehicleSystemsGraph,
    VehicleSystemsNode,
    VehicleSystemsNodeKind,
    VehicleSystemsProjection,
    VehicleSystemsRuntimeGraph,
    VehicleSystemsRuntimeIdentity,
)
from racelab_engine.services.import_service import build_telemetry_capability_payload
from racelab_engine.storage.repository import RaceLabRepository

_GRAPH_VERSION = "2026.08.next-gen.3"
_NEXT_GEN = BuildApplicability(
    car_family="next_gen",
    car_paths=(
        "stockcars chevycamarozl12022",
        "stockcars fordmustang2022",
        "stockcars toyotacamry2022",
    ),
    car_versions=("2026.06.08.02",),
    iracing_build_min="2026.01.00.00",
    iracing_build_max="2026.06.24.02",
    track_package_types=("oval",),
    source_version="reviewed-local-next-gen-manual-digest-v1",
)
_GENERAL = ("iracing_setup_guide", "nascar_nextgen_manual")


def _component(
    component_id: str,
    label: str,
    system_id: str,
    location: str,
    role: str,
    properties: tuple[str, ...],
    states: tuple[str, ...],
    symptoms: tuple[str, ...],
    setup_keys: tuple[str, ...],
    channels: tuple[str, ...],
    metrics: tuple[str, ...],
    unavailable: tuple[str, ...],
    coupled: tuple[str, ...],
    *,
    phases: tuple[str, ...] = ("braking", "entry", "center", "exit", "straight"),
    sources: tuple[str, ...] = _GENERAL,
) -> ComponentDefinition:
    return ComponentDefinition(
        component_id=component_id,
        system_id=system_id,
        label=label,
        physical_location=location,
        physical_role=role,
        applicability=_NEXT_GEN,
        adjustable_property_ids=properties,
        operating_phases=phases,
        speed_load_relevance="Interpret only in the exact phase, speed band, tire state, fuel state, line, traffic, and weather context.",
        setup_keys=setup_keys,
        coordinated_control_groups=tuple(
            (key,) for key in setup_keys
        ),
        observability=ComponentObservabilityContract(
            static_setting_channels=setup_keys,
            live_telemetry_channels=channels,
            derived_metrics=metrics,
            indirect_proxies=states,
            unavailable_quantities=unavailable,
            interpretation_blockers=(
                "No exact eligible-lap observation exists for the requested window.",
                "Traffic, line, fuel, tire, weather, damage, or simulator-integrity context is not comparable.",
            ),
        ),
        coupled_component_ids=coupled,
        compensating_control_keys=(),
        invariants=(
            "Hold every unrelated physical experimental factor constant.",
            "Compare eligible laps at matched physical track position and exact context.",
        ),
        expected_state_ids=states,
        symptom_ids=symptoms,
        performance_targets=("entry_time", "center_time", "exit_time", "repeatability", "driver_workload"),
        countereffects=("A target-phase gain may create an unacceptable countereffect in another phase.",),
        supporting_signatures=("A qualified P20 observation matches this component's declared mechanism family.",),
        contradicting_signatures=("Qualified exact-scope evidence contradicts the expected state response.",),
        confounders=("driver execution", "traffic", "tire state", "fuel state", "weather", "line", "damage"),
        measurement_requirements=("Use producer-owned P20 artifacts and preserve exact run/lap/window/phase provenance.",),
        rollback_conditions=("Undo when P19 policy rejects a countereffect or the controlled response misses its target.",),
        source_ids=sources,
    )


_COMPONENTS = (
    _component("tires", "Tires and pressures", "tires", "all four contact patches", "Support the car and develop pressure and thermal state through accumulated work.", ("pressure_support", "thermal_state", "loaded_tire_attitude"), ("tire_work", "pressure_development", "slip_exposure"), ("long_run_balance_change", "reduced_grip", "won_t_take_throttle"), (), ("lf_cold_pressure", "rf_cold_pressure", "lr_cold_pressure", "rr_cold_pressure", "lf_surface_temp_m", "rf_surface_temp_m", "lr_surface_temp_m", "rr_surface_temp_m"), ("tire_distance", "slip_exposure", "surface_temperature_spread"), ("tire force", "contact-patch pressure distribution", "universal optimum pressure"), ("alignment", "springs", "anti_roll_bars", "weight_distribution"), phases=("entry", "center", "exit", "straight")),
    _component("alignment", "Camber, caster, and toe", "alignment", "front and rear wheel alignment", "Set static wheel attitude and steering/scrub relationships.", ("camber_attitude", "toe_response", "caster_split"), ("loaded_tire_attitude", "steering_response", "scrub_like_resistance"), ("lazy_steering", "bound_up", "tight_center"), (), ("steering_wheel_angle", "yaw_rate", "speed", "rear_wheel_speed_mismatch"), ("steering_demand", "wheel_speed_disagreement"), ("live contact patch", "tire force", "exact scrub force"), ("tires", "steering", "anti_roll_bars")),
    _component("springs", "Springs", "suspension", "four suspension corners", "Provide vertical support and compliance while participating in roll, pitch, and platform control.", ("spring_rate", "vertical_support", "compliance"), ("platform_response", "roll_response", "pitch_response"), ("tight_center", "unstable_over_bumps", "snaps_loose_off"), ("lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm"), ("lf_shock_deflection", "rf_shock_deflection", "lr_shock_deflection", "rr_shock_deflection"), ("travel_response", "roll_response", "pitch_response"), ("wheel load", "spring force"), ("dampers", "anti_roll_bars", "platform", "weight_distribution")),
    _component("dampers", "Dampers", "suspension", "four suspension corners", "Control transient compression, rebound, settling, and disturbance response.", ("compression_resistance", "rebound_resistance", "high_speed_slope"), ("damper_response", "settling_response", "disturbance_response"), ("unstable_over_bumps", "lazy_response", "poor_recovery"), (), ("lf_shock_velocity", "rf_shock_velocity", "lr_shock_velocity", "rr_shock_velocity", "lf_shock_deflection", "rf_shock_deflection", "lr_shock_deflection", "rr_shock_deflection"), ("shaft_velocity_regime", "settling_time", "oscillation_count"), ("damper force", "damping coefficient"), ("springs", "platform", "anti_roll_bars"), sources=("shock_tuning_user_guide", "nascar_nextgen_manual")),
    _component("anti_roll_bars", "Anti-roll bars", "suspension", "front and rear left-right suspension coupling", "Couple left and right suspension motion and influence roll response.", ("roll_coupling", "bar_preload", "arm_position"), ("front_roll_response", "rear_roll_response", "initial_bar_state"), ("tight_center", "loose_center", "lazy_response"), (), ("lf_shock_deflection", "rf_shock_deflection", "lr_shock_deflection", "rr_shock_deflection", "yaw_rate", "steering_wheel_angle"), ("left_right_travel_split", "roll_response", "steering_demand"), ("bar torque", "bar load"), ("springs", "dampers", "weight_distribution", "platform")),
    _component("weight_distribution", "Weight distribution and crossweight", "chassis", "static whole-car distribution", "Describe static front/rear and diagonal setup relationships.", ("nose_weight", "static_diagonal_relationship"), ("entry_stability", "center_rotation", "exit_security"), ("loose_in", "tight_center", "snaps_loose_off"), ("nose_weight_percent", "cross_weight_percent"), ("yaw_rate", "steering_wheel_angle", "brake", "throttle"), ("phase_yaw_response", "steering_demand", "throttle_pickup"), ("dynamic wheel load", "dynamic crossweight"), ("springs", "anti_roll_bars", "platform", "brakes")),
    _component("platform", "Ride height and platform", "platform", "four chassis corners and underbody operating window", "Define chassis height, rake, clearance, and platform operating window.", ("front_platform_height", "rear_platform_height", "rake_relationship", "clearance"), ("platform_response", "clearance_margin", "rake_migration"), ("tight_center", "unstable_at_speed", "bottoming"), ("lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"), ("lf_ride_height", "rf_ride_height", "lr_ride_height", "rr_ride_height", "dcfs_ride_height", "cfs_ride_height"), ("front_height_distribution", "rear_height_distribution", "rake", "clearance_proxy"), ("downforce", "aero-balance percentage", "absolute aerodynamic load"), ("springs", "dampers", "anti_roll_bars", "weight_distribution")),
    _component("brakes", "Brake hydraulic system", "brakes", "front/rear and four-wheel hydraulic circuit", "Distribute brake pressure and shape braking stability and lock behavior.", ("front_rear_pressure_distribution", "line_pressure_response"), ("braking_response", "entry_stability", "wheel_lock_response"), ("loose_in", "won_t_rotate_on_brake", "brake_instability"), ("front_brake_bias_percent",), ("lf_brake_line_pressure", "rf_brake_line_pressure", "lr_brake_line_pressure", "rr_brake_line_pressure", "brake", "yaw_rate"), ("pressure_distribution", "lock_event", "braking_yaw_response"), ("brake torque", "friction coefficient"), ("weight_distribution", "tires"), phases=("braking", "entry")),
    _component("differential", "Differential", "powertrain", "rear axle coupling", "Couple rear wheel speeds under power and deceleration according to differential settings.", ("locking_resistance", "preload"), ("rear_wheel_coupling", "power_on_rotation", "deceleration_rotation"), ("bound_up", "won_t_take_throttle", "loose_off"), (), ("lr_wheel_speed", "rr_wheel_speed", "throttle", "yaw_rate"), ("rear_wheel_speed_disagreement", "throttle_yaw_response"), ("internal differential torque",), ("final_drive", "tires"), phases=("entry", "center", "exit")),
    _component("final_drive", "Final drive and gearing", "powertrain", "rear-end ratio and transmission", "Set the RPM, acceleration, and speed relationship across available gears.", ("final_drive_ratio", "gear_headroom"), ("rpm_acceleration_relationship", "limiter_headroom", "shift_response"), ("lazy_acceleration", "hits_limiter", "poor_straight_carry"), ("rear_end_ratio",), ("rpm", "gear", "speed", "long_accel", "throttle"), ("rpm_headroom", "acceleration_response", "shift_timing"), ("horsepower", "engine torque"), ("differential", "tires"), phases=("exit", "straight")),
    _component("steering", "Steering rack and driver interface", "steering", "steering wheel, pinion/rack, and offset", "Set steering travel per wheel revolution and expose steering response/workload context.", ("steering_ratio", "rack_travel", "steering_offset"), ("steering_response", "driver_workload", "yaw_response"), ("lazy_steering", "nervous_steering", "high_workload"), ("steering_ratio", "steering_offset_deg"), ("steering_wheel_angle", "steering_wheel_torque", "yaw_rate"), ("steering_rate", "steering_demand", "yaw_response_lag"), ("steering effort without verified FFB context", "rack force"), ("alignment", "tires")),
    _component("cooling_configuration", "Cooling configuration", "cooling", "front grille/tape configuration", "Trade cooling margin against a configuration-dependent resistance and platform response.", ("cooling_opening",), ("cooling_margin", "temperature_response", "straight_response"), ("overheating", "poor_straight_carry"), ("tape_percent",), ("water_temp", "oil_temp", "speed", "long_accel"), ("temperature_margin", "straight_response"), ("exact aerodynamic drag", "drag coefficient", "downforce"), ("platform", "final_drive"), phases=("straight",)),
)


_COMPONENT_SETTING_SPECS: dict[str, tuple[tuple[str, str, str | None, int], ...]] = {
    "tires": tuple(
        (f"{corner}.cold_pressure_kpa", f"{corner.upper()} cold pressure", "kPa", 1)
        for corner in ("lf", "rf", "lr", "rr")
    ),
    "alignment": tuple(
        (f"{corner}.{field}", f"{corner.upper()} {label}", unit, 1)
        for corner in ("lf", "rf", "lr", "rr")
        for field, label, unit in (
            ("camber_deg", "camber", "deg"),
            ("caster_deg", "caster", "deg"),
            ("toe_in_mm", "toe-in", "mm"),
        )
    ),
    "springs": (
        ("lf_front_spring_n_per_mm", "LF spring rate", "N/mm", 1),
        ("rf_front_spring_n_per_mm", "RF spring rate", "N/mm", 1),
        ("lr_rear_spring_n_per_mm", "LR spring rate", "N/mm", 1),
        ("rr_rear_spring_n_per_mm", "RR spring rate", "N/mm", 1),
    ) + tuple(
        (f"{corner}.shock_collar_offset_mm", f"{corner.upper()} shock collar", "mm", 1)
        for corner in ("lf", "rf", "lr", "rr")
    ),
    "dampers": tuple(
        (f"{corner}.{field}", f"{corner.upper()} {label}", unit, decimals)
        for corner in ("lf", "rf", "lr", "rr")
        for field, label, unit, decimals in (
            ("ls_compression", "LS compression", "clicks", 0),
            ("hs_compression", "HS compression", "clicks", 0),
            ("hs_comp_slope", "HS compression slope", "clicks", 0),
            ("ls_rebound", "LS rebound", "clicks", 0),
            ("hs_rebound", "HS rebound", "clicks", 0),
            ("hs_reb_slope", "HS rebound slope", "clicks", 0),
        )
    ),
    "anti_roll_bars": (
        ("front_arb_diameter_mm", "Front ARB diameter", "mm", 1),
        ("front_arb_arm_position", "Front ARB arm", None, 0),
        ("front_arb_preload_nm", "Front ARB preload", "Nm", 1),
        ("front_arb_attach", "Front ARB attach", None, 0),
        ("rear_arb_diameter_mm", "Rear ARB diameter", "mm", 1),
        ("rear_arb_arm_position", "Rear ARB arm", None, 0),
        ("rear_arb_preload_nm", "Rear ARB preload", "Nm", 1),
        ("rear_arb_attach", "Rear ARB attach", None, 0),
    ),
    "weight_distribution": (
        ("nose_weight_percent", "Nose weight", "%", 1),
        ("cross_weight_percent", "Cross weight", "%", 1),
    ),
    "platform": (
        ("lf_ride_height_mm", "LF ride height", "mm", 2),
        ("rf_ride_height_mm", "RF ride height", "mm", 2),
        ("lr_ride_height_mm", "LR ride height", "mm", 2),
        ("rr_ride_height_mm", "RR ride height", "mm", 2),
    ),
    "brakes": (
        ("front_brake_bias_percent", "Front brake bias", "%", 1),
        ("front_mc_mm", "Front master cylinder", "mm", 1),
        ("rear_mc_mm", "Rear master cylinder", "mm", 1),
    ),
    "differential": (("diff_preload_nm", "Differential preload", "Nm", 1),),
    "final_drive": (("final_drive_ratio", "Final drive ratio", ":1", 3),),
    "steering": (
        ("steering_ratio", "Steering ratio / pinion", None, 1),
        ("steering_offset_deg", "Steering offset", "deg", 1),
    ),
    "cooling_configuration": (("tape_percent", "Tape", "%", 1),),
}

_COMPONENT_LIVE_CHANNEL_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "tires": (
        ("lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure"),
        ("lf_temp_middle", "rf_temp_middle", "lr_temp_middle", "rr_temp_middle"),
    ),
    "alignment": (("steering_rad", "yaw_rate", "speed_mps"),),
    "springs": (("lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in"),),
    "dampers": (("lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"),),
    "anti_roll_bars": (("lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in", "yaw_rate"),),
    "weight_distribution": (("yaw_rate", "steering_rad", "brake_01", "throttle_01"),),
    "platform": (("lf_ride_height_m", "rf_ride_height_m", "lr_ride_height_m", "rr_ride_height_m", "cfs_ride_height_m"),),
    "brakes": (("brake_01", "yaw_rate"),),
    "differential": (("LRspeed", "RRspeed", "throttle_01", "yaw_rate"),),
    "final_drive": (("rpm", "gear", "speed_mps", "throttle_01"),),
    "steering": (("steering_rad", "steering_wheel_torque_nm", "yaw_rate"),),
    "cooling_configuration": (("water_temp", "oil_temp", "speed_mps"),),
}

_QUANTITY_NAMES: dict[str, tuple[str, ...]] = {
    "tires": ("hot_pressure_envelope", "surface_temperature_profile"),
    "brakes": ("pedal_yaw_screen", "hydraulic_line_pressure_distribution"),
}
_QUANTITY_CHANNEL_OVERRIDES: dict[tuple[str, str], tuple[str, ...]] = {
    ("brakes", "hydraulic_line_pressure_distribution"): (
        "brake_01", "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
        "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
    ),
}

_COMPONENTS = tuple(
    definition.model_copy(update={
        "observability": definition.observability.model_copy(update={
            "static_setting_channels": tuple(
                path for path, _label, _unit, _decimals
                in _COMPONENT_SETTING_SPECS[definition.component_id]
            ),
            "live_telemetry_channels": tuple(dict.fromkeys(
                channel
                for group in _COMPONENT_LIVE_CHANNEL_GROUPS[definition.component_id]
                for channel in group
            )),
        }),
    })
    for definition in _COMPONENTS
)


_MECHANISM_COMPONENTS: dict[MechanismKind, tuple[str, ...]] = {
    MechanismKind.BRAKING_RESPONSE: ("brakes", "weight_distribution", "tires"),
    MechanismKind.CORNER_ROTATION: ("anti_roll_bars", "springs", "weight_distribution", "alignment", "differential", "tires"),
    MechanismKind.TIRE_STATE: ("tires", "alignment"),
    MechanismKind.DAMPER_RESPONSE: ("dampers", "springs"),
    MechanismKind.PLATFORM_RESPONSE: ("platform", "springs", "dampers", "anti_roll_bars"),
    MechanismKind.RESISTANCE_SCRUB_LIKE: ("alignment", "tires", "cooling_configuration"),
    MechanismKind.POWERTRAIN_RESPONSE: ("differential", "final_drive", "tires"),
    MechanismKind.STINT_TREND: ("tires", "cooling_configuration"),
}

_MECHANISM_KEY_COMPONENTS: dict[str, tuple[str, ...]] = {
    **{mechanism.value: components for mechanism, components in _MECHANISM_COMPONENTS.items()},
    "braking": ("brakes", "weight_distribution", "tires"),
    "corner_balance": ("anti_roll_bars", "springs", "weight_distribution", "alignment"),
    "cross_weight": ("weight_distribution",),
    "platform": ("platform", "springs", "dampers", "anti_roll_bars"),
    "platform_balance": ("platform", "springs", "dampers", "anti_roll_bars"),
    "platform_risk": ("platform", "springs", "dampers", "anti_roll_bars"),
    "damping": ("dampers",),
    "damper": ("dampers",),
    "shock": ("dampers",),
    "spring": ("springs",),
    "geometry": ("alignment", "steering"),
    "resistance": ("alignment", "tires", "cooling_configuration"),
    "scrub": ("alignment", "tires"),
    "traction": ("differential", "tires"),
    "throttle": ("differential", "final_drive", "tires"),
    "rotation": ("anti_roll_bars", "springs", "weight_distribution", "alignment", "differential", "tires"),
    "stability": ("weight_distribution", "brakes", "differential", "tires"),
    "mechanical_balance": ("anti_roll_bars", "springs", "weight_distribution"),
}

_AREA_COMPONENTS = {
    **{key: "tires" for key in ("tire_pressure", "pressure_split", "pressure_gain", "tire_temp_spread", "tire_wear")},
    **{key: "alignment" for key in ("camber", "caster", "toe", "front_toe_response", "rear_toe_stability")},
    **{key: "springs" for key in ("spring_rate", "spring_perch", "front_spring_support", "rear_spring_support", "spring_split")},
    "shock_collar": "springs",
    **{key: "dampers" for key in ("ls_compression", "hs_compression", "hs_comp_slope", "ls_rebound", "hs_rebound", "hs_reb_slope", "shock_histogram", "shock_velocity_rms", "shock_deflection_delta")},
    **{key: "anti_roll_bars" for key in ("front_arb_diameter", "front_arb_arm", "front_arb_preload", "front_arb_attach", "rear_arb_diameter", "rear_arb_arm", "rear_arb_preload", "rear_arb_attach")},
    **{key: "weight_distribution" for key in ("cross_weight", "nose_weight", "corner_weight", "ballast")},
    **{key: "platform" for key in ("ride_height", "front_ride_height_platform", "rear_ride_height_platform", "diffuser_platform", "cfs/front_splitter/rub_block_reference", "platform_contact", "front_platform_contact")},
    **{key: "brakes" for key in ("brake_bias", "front_master_cylinder", "rear_master_cylinder")},
    "diff_preload": "differential",
    **{key: "final_drive" for key in ("final_drive", "gear_ratio")},
}

_CONTROL_PROPERTY = {
    "lf_ride_height_mm": "front_platform_height", "rf_ride_height_mm": "front_platform_height",
    "lr_ride_height_mm": "rear_platform_height", "rr_ride_height_mm": "rear_platform_height",
    "lf_front_spring_n_per_mm": "spring_rate", "rf_front_spring_n_per_mm": "spring_rate",
    "lr_rear_spring_n_per_mm": "spring_rate", "rr_rear_spring_n_per_mm": "spring_rate",
    "nose_weight_percent": "nose_weight", "cross_weight_percent": "static_diagonal_relationship",
    "tape_percent": "cooling_opening", "rear_end_ratio": "final_drive_ratio",
    "front_brake_bias_percent": "front_rear_pressure_distribution",
    "steering_ratio": "steering_ratio", "steering_offset_deg": "steering_offset",
}

_AREA_PROPERTY = {
    "tire_pressure": "pressure_support", "pressure_split": "pressure_support",
    "pressure_gain": "thermal_state", "tire_temp_spread": "thermal_state", "tire_wear": "thermal_state",
    "camber": "camber_attitude", "caster": "caster_split", "toe": "toe_response",
    "front_toe_response": "toe_response", "rear_toe_stability": "toe_response",
    "spring_rate": "spring_rate", "spring_perch": "vertical_support",
    "front_spring_support": "vertical_support", "rear_spring_support": "vertical_support", "spring_split": "spring_rate",
    "shock_collar": "vertical_support", "ls_compression": "compression_resistance",
    "hs_compression": "compression_resistance", "hs_comp_slope": "high_speed_slope",
    "ls_rebound": "rebound_resistance", "hs_rebound": "rebound_resistance", "hs_reb_slope": "high_speed_slope",
    "shock_histogram": "compression_resistance", "shock_velocity_rms": "high_speed_slope",
    "shock_deflection_delta": "rebound_resistance",
    "front_arb_diameter": "roll_coupling", "front_arb_arm": "arm_position",
    "front_arb_preload": "bar_preload", "front_arb_attach": "roll_coupling",
    "rear_arb_diameter": "roll_coupling", "rear_arb_arm": "arm_position",
    "rear_arb_preload": "bar_preload", "rear_arb_attach": "roll_coupling",
    "cross_weight": "static_diagonal_relationship", "nose_weight": "nose_weight",
    "corner_weight": "static_diagonal_relationship", "ballast": "nose_weight",
    "ride_height": "clearance", "front_ride_height_platform": "front_platform_height",
    "rear_ride_height_platform": "rear_platform_height", "diffuser_platform": "rake_relationship",
    "cfs/front_splitter/rub_block_reference": "clearance", "platform_contact": "clearance",
    "front_platform_contact": "front_platform_height",
    "brake_bias": "front_rear_pressure_distribution", "front_master_cylinder": "line_pressure_response",
    "rear_master_cylinder": "line_pressure_response", "diff_preload": "preload",
    "final_drive": "final_drive_ratio", "gear_ratio": "gear_headroom",
}

_EFFECT_DIRECTION_INCREASE = {
    "add_crossweight_small", "add_rf_spring_small", "add_lr_pressure_small",
    "add_rear_stability_pressure_swing", "stiffen_front_arb_arm", "switch_front_arb_to_stiff_bar",
    "stiffen_rear_arb_arm", "add_front_brake_bias_small", "reduce_front_platform_support",
    "add_rear_platform_support", "add_ls_compression_front", "add_ls_rebound_front",
    "add_ls_rebound_rear", "add_hs_compression", "add_hs_rebound", "add_rear_toe_stability",
    "increase_diff_preload", "shorter_final_drive", "improve_front_feed_window",
    "inspect_diffuser_choke_or_scrape", "reduce_platform_contact_small",
    "stiffen_front_arb_arm_one_position", "stiffen_rear_arb_arm_one_position",
    "raise_front_shock_collar_small", "raise_rear_shock_collar_small", "add_left_rear_pressure_small",
    "add_right_front_pressure_support", "pressure_split_stability_swing", "add_lr_spring_support",
    "spring_package_platform_support", "add_front_response_toe_swing", "caster_driver_feel_entry",
    "add_lf_ls_rebound", "add_rf_ls_compression", "add_rear_ls_rebound", "add_rear_ls_compression",
    "add_hs_compression_for_bumps", "add_hs_rebound_control", "switch_rear_arb_to_stiff_bar",
}
_EFFECT_DIRECTION_DECREASE = {
    "reduce_crossweight_small", "reduce_rf_spring_small", "reduce_lf_pressure_small",
    "soften_front_arb_arm", "switch_front_arb_to_soft_bar", "soften_rear_arb_arm",
    "reduce_front_brake_bias_small", "add_front_platform_support", "reduce_rear_platform_support",
    "reduce_ls_compression_front", "reduce_ls_rebound_front", "reduce_ls_rebound_rear",
    "reduce_hs_compression", "reduce_hs_rebound", "reduce_toe_scrub", "reduce_diff_preload",
    "taller_final_drive", "soften_front_arb_arm_one_position", "soften_rear_arb_arm_one_position",
    "lower_front_shock_collar_small", "lower_rear_shock_collar_small", "protect_rf_long_run_pressure",
    "protect_rr_long_run_pressure", "tune_diff_preload_for_center_exit", "reduce_left_front_pressure_small",
    "reduce_right_front_pressure_grip", "long_run_pressure_protection", "reduce_lr_spring_for_drive",
    "spring_package_compliance", "reduce_rear_toe_bind", "reduce_camber_for_long_run",
    "reduce_lf_ls_rebound", "reduce_rf_ls_compression", "reduce_rear_ls_rebound",
    "reduce_rear_ls_compression", "reduce_hs_compression_for_compliance", "reduce_hs_rebound_recovery",
    "reduce_front_toe_scrub", "switch_rear_arb_to_soft_bar",
}
_EFFECT_DIRECTION_UNSPECIFIED = {
    "adjust_front_arb_preload_small", "adjust_rear_arb_preload_small", "add_bumpy_track_compliance",
    "inspect_toe_scrub_baseline", "avoid_static_rake_only_call", "camber_for_center_grip",
    "slope_more_linear_bumpy", "slope_more_digressive_smooth",
}


def _component_for_area(area: str) -> str:
    try:
        return _AREA_COMPONENTS[area.casefold()]
    except KeyError as exc:
        raise ValueError(f"Next Gen setup area lacks an explicit component mapping: {area}") from exc


def _version_tuple(value: str) -> tuple[int, int, int, int]:
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\.\d{2}", value):
        raise ValueError(f"Invalid iRacing build version: {value}")
    year, season, patch, revision = (int(part) for part in value.split("."))
    return year, season, patch, revision


def _sha256(value: object) -> str | None:
    text = str(value or "").strip().casefold()
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else None


def _usable_manifest_channel(entry: object) -> bool:
    if not isinstance(entry, Mapping):
        return False
    try:
        valid_records = int(entry.get("valid_record_count") or 0)
    except (TypeError, ValueError):
        return False
    return (
        entry.get("archive_status") == "cached"
        and valid_records > 0
        and entry.get("health_status") not in {"blocked", "unavailable"}
    )


def vehicle_systems_runtime_identity(
    run_id: str,
) -> VehicleSystemsRuntimeIdentity:
    session = RaceLabRepository().get_session(run_id)
    source_file_sha256 = _sha256(session.file_hash if session is not None else None)
    if session is None or session.run_id != run_id or source_file_sha256 is None:
        raise ValueError(f"Vehicle Systems cannot verify stored source ownership for run {run_id}.")
    try:
        payload = build_telemetry_capability_payload(
            run_id,
            expected_source_file_sha256=source_file_sha256,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Vehicle Systems could not verify telemetry artifact ownership for run {run_id}."
        ) from exc
    if payload.get("run_id") != run_id:
        raise ValueError(f"Vehicle Systems telemetry ownership does not match run {run_id}.")
    manifest_identity = payload.get("manifest_identity")
    if not isinstance(manifest_identity, Mapping) or manifest_identity.get("status") != "verified":
        raise ValueError(f"Vehicle Systems requires verified telemetry artifact ownership for run {run_id}.")
    if manifest_identity.get("run_id") != run_id:
        raise ValueError(f"Vehicle Systems telemetry cache does not belong to run {run_id}.")
    if _sha256(manifest_identity.get("source_file_sha256")) != source_file_sha256:
        raise ValueError(f"Vehicle Systems manifest source does not belong to run {run_id}.")
    telemetry_cache_sha256 = _sha256(manifest_identity.get("telemetry_cache_sha256"))
    cache_compatibility = payload.get("cache_compatibility")
    if (
        source_file_sha256 is None
        or telemetry_cache_sha256 is None
        or not isinstance(cache_compatibility, Mapping)
        or cache_compatibility.get("status") != "current"
    ):
        raise ValueError(f"Vehicle Systems requires the current verified telemetry archive for run {run_id}.")
    if _sha256(payload.get("source_file_sha256")) != source_file_sha256:
        raise ValueError(f"Vehicle Systems source-file ownership changed for run {run_id}.")
    if payload.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Vehicle Systems requires the current telemetry manifest schema for run {run_id}.")
    if payload.get("universal_archive_version") != UNIVERSAL_ARCHIVE_VERSION:
        raise ValueError(f"Vehicle Systems requires the current universal telemetry archive for run {run_id}.")
    identity = payload.get("compatibility_identity")
    if not isinstance(identity, Mapping):
        raise ValueError(  # noqa: TRY004 - all runtime identity failures share one API boundary
            f"Vehicle Systems requires a verified telemetry manifest for run {run_id}."
        )
    if identity.get("missing_required_fields"):
        raise ValueError(f"Vehicle Systems runtime identity is incomplete for run {run_id}.")
    car_path = str(identity.get("car_path") or "")
    build = str(identity.get("iracing_build_version") or "")
    car_version = str(identity.get("car_version") or "")
    track_configuration = str(identity.get("track_configuration_name") or "")
    if car_path.casefold() not in _NEXT_GEN.car_paths:
        raise ValueError(f"Vehicle Systems graph {_GRAPH_VERSION} is unavailable for car path {car_path}.")
    if car_version not in _NEXT_GEN.car_versions:
        raise ValueError(
            f"Vehicle Systems graph {_GRAPH_VERSION} requires review for car version {car_version}."
        )
    if _NEXT_GEN.iracing_build_min is None or _NEXT_GEN.iracing_build_max is None:
        raise ValueError("Vehicle Systems graph requires a closed iRacing build range.")
    if _version_tuple(build) < _version_tuple(_NEXT_GEN.iracing_build_min):
        raise ValueError(f"Vehicle Systems graph {_GRAPH_VERSION} does not cover iRacing build {build}.")
    if _version_tuple(build) > _version_tuple(_NEXT_GEN.iracing_build_max):
        raise ValueError(
            f"Vehicle Systems graph {_GRAPH_VERSION} requires review for future iRacing build {build}."
        )
    if track_configuration.casefold() not in _NEXT_GEN.track_package_types:
        raise ValueError(f"Vehicle Systems requires an oval track configuration, got {track_configuration}.")
    schema_fingerprint = _sha256(payload.get("schema_fingerprint"))
    declared_fingerprint = _sha256(payload.get("compatibility_fingerprint"))
    if schema_fingerprint is None or declared_fingerprint is None:
        raise ValueError(f"Vehicle Systems telemetry fingerprints are malformed for run {run_id}.")
    if compatibility_fingerprint(schema_fingerprint, dict(identity)) != declared_fingerprint:
        raise ValueError(f"Vehicle Systems compatibility identity failed integrity verification for run {run_id}.")
    channel_entries = payload.get("channels")
    if not isinstance(channel_entries, list):
        raise ValueError(  # noqa: TRY004 - all runtime identity failures share one API boundary
            f"Vehicle Systems requires a verified channel manifest for run {run_id}."
        )
    available_channels = tuple(sorted({
        channel_id
        for entry in channel_entries
        if _usable_manifest_channel(entry)
        and isinstance(entry, Mapping)
        for channel_id in (entry.get("name"), entry.get("canonical_name"))
        if isinstance(channel_id, str) and channel_id and channel_id.strip() == channel_id
    }))
    if not available_channels:
        raise ValueError(f"Vehicle Systems found no usable telemetry channels for run {run_id}.")
    return VehicleSystemsRuntimeIdentity(
        run_id=run_id,
        car_path=car_path,
        car_version=car_version,
        iracing_build_version=build,
        track_configuration_name=track_configuration,
        source_file_sha256=source_file_sha256,
        telemetry_cache_sha256=telemetry_cache_sha256,
        schema_fingerprint=schema_fingerprint,
        compatibility_fingerprint=declared_fingerprint,
        available_telemetry_channels=available_channels,
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")[:96] or "unknown"


@lru_cache(maxsize=1)
def compile_vehicle_systems_graph() -> VehicleSystemsGraph:
    """Compile accepted Dial-In types into an immutable, typed Next Gen graph."""
    knowledge = load_setup_knowledge()
    accepted_sources = {
        source.source_id for source in knowledge.guide_sources if source.status in {"reviewed", "accepted"}
    }
    next_gen_areas = tuple(
        area
        for area in knowledge.setup_areas
        if "next_gen" not in area.disabled_for
        and ("all" in area.applies_to or "next_gen" in area.applies_to)
    )
    next_gen_area_ids = {area.setup_area.casefold() for area in next_gen_areas}
    unmapped_area_ids = sorted(next_gen_area_ids - set(_AREA_COMPONENTS))
    if unmapped_area_ids:
        raise ValueError(
            f"Next Gen setup areas require explicit component mappings: {unmapped_area_ids}"
        )
    if next_gen_area_ids != set(_AREA_PROPERTY):
        raise ValueError("every Next Gen engineering area requires one explicit component property")
    component_by_id = {item.component_id: item for item in _COMPONENTS}
    if any(not set(item.source_ids) <= accepted_sources for item in _COMPONENTS):
        raise ValueError("component definitions require reviewed source provenance")

    nodes: dict[str, VehicleSystemsNode] = {}
    edges: dict[str, VehicleSystemsEdge] = {}

    def add_node(
        node_id: str,
        kind: VehicleSystemsNodeKind,
        label: str,
        component_id: str | None,
        source_ids: tuple[str, ...],
        authority: str = "knowledge_only",
        *,
        description: str | None = None,
        engineering_area_mode: str | None = None,
    ) -> None:
        candidate = VehicleSystemsNode(
            node_id=node_id,
            kind=kind,
            label=label,
            description=description,
            component_id=component_id,
            engineering_area_mode=engineering_area_mode,
            source_ids=tuple(dict.fromkeys(source_ids)),
            authority=authority,
        )
        existing = nodes.get(node_id)
        if existing is None:
            nodes[node_id] = candidate
            return
        if (
            existing.kind != candidate.kind
            or existing.label != candidate.label
            or existing.description != candidate.description
            or existing.component_id != candidate.component_id
            or existing.engineering_area_mode != candidate.engineering_area_mode
            or existing.authority != candidate.authority
        ):
            raise ValueError(f"vehicle-system node identity collision: {node_id}")
        nodes[node_id] = existing.model_copy(update={
            "source_ids": tuple(dict.fromkeys((*existing.source_ids, *candidate.source_ids))),
        })

    def add_edge(source: str, target: str, kind: VehicleSystemsEdgeKind, source_ids: tuple[str, ...], *, direction: str | None = None, authority: str = "engineering_expectation_only", interaction_type: str | None = None) -> None:
        digest = hashlib.sha256(f"{source}|{target}|{kind.value}|{direction}|{interaction_type}".encode()).hexdigest()[:20]
        candidate = VehicleSystemsEdge(edge_id=f"vse:{digest}", source_node_id=source, target_node_id=target, kind=kind, direction=direction, interaction_type=interaction_type, source_ids=tuple(dict.fromkeys(source_ids)), authority=authority)
        existing = edges.get(digest)
        if existing is None:
            edges[digest] = candidate
            return
        if (
            existing.source_node_id != candidate.source_node_id
            or existing.target_node_id != candidate.target_node_id
            or existing.kind != candidate.kind
            or existing.direction != candidate.direction
            or existing.interaction_type != candidate.interaction_type
            or existing.authority != candidate.authority
        ):
            raise ValueError(f"vehicle-system edge identity collision: {candidate.edge_id}")
        edges[digest] = existing.model_copy(update={
            "source_ids": tuple(dict.fromkeys((*existing.source_ids, *candidate.source_ids))),
        })

    for definition in _COMPONENTS:
        component_node = f"component:{definition.component_id}"
        add_node(component_node, VehicleSystemsNodeKind.COMPONENT, definition.label, definition.component_id, definition.source_ids)
        for property_id in definition.adjustable_property_ids:
            property_node = f"property:{definition.component_id}:{property_id}"
            add_node(property_node, VehicleSystemsNodeKind.COMPONENT_PROPERTY, property_id.replace("_", " ").title(), definition.component_id, definition.source_ids)
        for state_id in definition.expected_state_ids:
            state_node = f"state:{state_id}"
            add_node(state_node, VehicleSystemsNodeKind.VEHICLE_STATE, state_id.replace("_", " ").title(), None, definition.source_ids)
            for property_id in definition.adjustable_property_ids:
                add_edge(f"property:{definition.component_id}:{property_id}", state_node, VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE, definition.source_ids)
            observation_node = f"observation:{definition.component_id}:{state_id}"
            add_node(observation_node, VehicleSystemsNodeKind.OBSERVATION, f"Qualified {state_id.replace('_', ' ')} observation", definition.component_id, definition.source_ids, "observation_only")
            add_edge(state_node, observation_node, VehicleSystemsEdgeKind.STATE_OBSERVABLE_BY, definition.source_ids)
        for symptom_id in definition.symptom_ids:
            symptom_node = f"symptom:{symptom_id}"
            add_node(symptom_node, VehicleSystemsNodeKind.SYMPTOM, symptom_id.replace("_", " ").title(), None, definition.source_ids)
            for state_id in definition.expected_state_ids:
                add_edge(f"state:{state_id}", symptom_node, VehicleSystemsEdgeKind.STATE_MAY_PRESENT_AS_SYMPTOM, definition.source_ids)
        for key in definition.setup_keys:
            spec = SETUP_CONTROL_SPECS[key]
            control_node = f"control:{key}"
            add_node(control_node, VehicleSystemsNodeKind.CONTROL, spec.label, definition.component_id, definition.source_ids)
            property_id = _CONTROL_PROPERTY[key]
            add_edge(control_node, f"property:{definition.component_id}:{property_id}", VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY, definition.source_ids, direction="bidirectional")
            for invariant in definition.invariants:
                context_node = f"context:invariant:{_slug(invariant)}"
                add_node(context_node, VehicleSystemsNodeKind.CONTEXT, invariant, None, definition.source_ids)
                add_edge(control_node, context_node, VehicleSystemsEdgeKind.CONTROL_REQUIRES_INVARIANT, definition.source_ids)

    interactions: list[ComponentInteraction] = []
    seen_pairs: set[tuple[str, str]] = set()
    for definition in _COMPONENTS:
        for target in definition.coupled_component_ids:
            pair = tuple(sorted((definition.component_id, target)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            interaction = ComponentInteraction(
                interaction_id=f"interaction:{pair[0]}:{pair[1]}",
                source_component_id=pair[0], target_component_id=pair[1],
                interaction_type="mechanically_coupled",
                description=f"{component_by_id[pair[0]].label} and {component_by_id[pair[1]].label} can change the same whole-car response; isolate them with exact evidence.",
                applicability=_NEXT_GEN, source_ids=_GENERAL,
            )
            interactions.append(interaction)
            add_edge(f"component:{pair[0]}", f"component:{pair[1]}", VehicleSystemsEdgeKind.COMPONENT_COUPLES_WITH_COMPONENT, _GENERAL, direction="bidirectional", interaction_type=interaction.interaction_type)

    # Explicitly represent the current garage's post-update spring compensation.
    interactions.append(ComponentInteraction(
        interaction_id="interaction:springs:platform:auto_ride_height",
        source_component_id="springs", target_component_id="platform",
        interaction_type="garage_autocompensated",
        description="For the scoped 2026 Next Gen garage, a spring-rate change automatically maintains configured ride height; platform response still requires validation.",
        applicability=_NEXT_GEN, source_ids=("nascar_nextgen_manual",),
    ))
    add_edge("component:springs", "component:platform", VehicleSystemsEdgeKind.COMPONENT_COUPLES_WITH_COMPONENT, ("nascar_nextgen_manual",), direction="bidirectional", interaction_type="garage_autocompensated")

    # Preserve every current Next Gen engineering area without pretending a
    # derived/live diagnostic area is itself an adjustable control.
    for area in next_gen_areas:
        component_id = _component_for_area(area.setup_area)
        sources = component_by_id[component_id].source_ids
        area_node = f"area:{area.setup_area.casefold()}"
        add_node(
            area_node,
            VehicleSystemsNodeKind.ENGINEERING_AREA,
            area.setup_area.replace("_", " ").title(),
            component_id,
            sources,
            description=area.what_it_changes,
            engineering_area_mode=area.static_or_live,
        )
        add_edge(
            f"component:{component_id}",
            area_node,
            VehicleSystemsEdgeKind.COMPONENT_HAS_ENGINEERING_AREA,
            sources,
        )

    # SetupEffect adapters are exact effect identities with explicit property
    # and direction metadata. No prose inference or first-property fallback.
    next_gen_effects = [
        effect for effect in knowledge.setup_effects
        if "next_gen" not in effect.disabled_for
        and ("all" in effect.applies_to or "next_gen" in effect.applies_to)
    ]
    if any(
        effect.review_status != "accepted"
        or not effect.source_ids
        or not set(effect.source_ids) <= accepted_sources
        for effect in next_gen_effects
    ):
        raise ValueError("Next Gen setup effects require accepted, exact source provenance")
    effect_ids = {effect.effect_id for effect in next_gen_effects}
    declared_direction_ids = (
        _EFFECT_DIRECTION_INCREASE
        | _EFFECT_DIRECTION_DECREASE
        | _EFFECT_DIRECTION_UNSPECIFIED
    )
    if effect_ids != declared_direction_ids or (
        _EFFECT_DIRECTION_INCREASE & _EFFECT_DIRECTION_DECREASE
        or _EFFECT_DIRECTION_INCREASE & _EFFECT_DIRECTION_UNSPECIFIED
        or _EFFECT_DIRECTION_DECREASE & _EFFECT_DIRECTION_UNSPECIFIED
    ):
        raise ValueError("every Next Gen setup effect requires one explicit direction contract")
    for effect in next_gen_effects:
        component_id = _component_for_area(effect.setup_area)
        sources = tuple(effect.source_ids)
        area_node = f"area:{effect.setup_area.casefold()}"
        control_node = f"control:effect:{effect.effect_id}"
        add_node(control_node, VehicleSystemsNodeKind.CONTROL, effect.direction, component_id, sources)
        add_edge(area_node, control_node, VehicleSystemsEdgeKind.ENGINEERING_AREA_HAS_CONTROL, sources)
        property_id = _AREA_PROPERTY[effect.setup_area.casefold()]
        if property_id not in component_by_id[component_id].adjustable_property_ids:
            raise ValueError(
                f"engineering area {effect.setup_area} maps outside component {component_id}"
            )
        property_node = f"property:{component_id}:{property_id}"
        direction = (
            "increase" if effect.effect_id in _EFFECT_DIRECTION_INCREASE
            else "decrease" if effect.effect_id in _EFFECT_DIRECTION_DECREASE
            else None
        )
        add_edge(control_node, property_node, VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY, sources, direction=direction)
        state_node = f"state:effect:{effect.effect_id}"
        add_node(state_node, VehicleSystemsNodeKind.VEHICLE_STATE, effect.effect, component_id, sources)
        add_edge(property_node, state_node, VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE, sources, direction=direction)
        for phrase in effect.driver_phrase:
            symptom_node = f"symptom:effect:{effect.effect_id}:{_slug(phrase)}"
            add_node(symptom_node, VehicleSystemsNodeKind.SYMPTOM, phrase, component_id, sources)
            add_edge(state_node, symptom_node, VehicleSystemsEdgeKind.STATE_MAY_PRESENT_AS_SYMPTOM, sources)
        outcome_node = f"outcome:countereffect:{effect.effect_id}"
        add_node(outcome_node, VehicleSystemsNodeKind.OUTCOME, effect.counter_effect, component_id, sources)
        add_edge(control_node, outcome_node, VehicleSystemsEdgeKind.CONTROL_HAS_COUNTEREFFECT, sources, direction=direction)

    mapped_keys = {key for definition in _COMPONENTS for key in definition.setup_keys}
    if mapped_keys != set(SETUP_CONTROL_SPECS):
        missing = sorted(set(SETUP_CONTROL_SPECS) - mapped_keys)
        extra = sorted(mapped_keys - set(SETUP_CONTROL_SPECS))
        raise ValueError(f"setup controls must map exactly once to components; missing={missing}, extra={extra}")
    if set(_CONTROL_PROPERTY) != set(SETUP_CONTROL_SPECS):
        raise ValueError("every setup control requires one typed component property")
    graph_items = (*_COMPONENTS, *interactions, *nodes.values(), *edges.values())
    sources = tuple(sorted({source for item in graph_items for source in item.source_ids}))
    content_payload = {
        "components": [item.model_dump(mode="json") for item in _COMPONENTS],
        "interactions": [item.model_dump(mode="json") for item in interactions],
        "nodes": [item.model_dump(mode="json") for item in nodes.values()],
        "edges": [item.model_dump(mode="json") for item in edges.values()],
        "source_ids": sources,
    }
    content_sha256 = hashlib.sha256(
        json.dumps(content_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return VehicleSystemsGraph(
        graph_version=f"{_GRAPH_VERSION}:{content_sha256[:12]}",
        content_sha256=content_sha256,
        components=_COMPONENTS,
        interactions=tuple(interactions),
        nodes=tuple(nodes.values()),
        edges=tuple(edges.values()),
        source_ids=sources,
    )


@lru_cache(maxsize=1)
def _experiment_factors() -> tuple[SetupExperimentFactor, ...]:
    common_preconditions = ("P19 identifies one exact control target and authorizes the controlled test.", "Eligible A/B/A2 laps can hold context and driver line comparable.")
    return (
        SetupExperimentFactor(factor_id="factor:front_platform_height", component_id="platform", physical_property_id="front_platform_height", primary_controls=("lf_ride_height_mm",), coordinated_controls=("rf_ride_height_mm",), invariants_to_hold=("Hold LF-to-RF height split fixed.", "Recheck crossweight and leave unrelated controls unchanged."), preconditions=common_preconditions, expected_component_response=("Front chassis operating height moves by one sourced adjacent option.",), expected_vehicle_response=("Front clearance and platform response change in the target speed band.",), countereffects=("Bottoming, steering-demand growth, or an adverse balance shift." ,), success_metrics=("CFS clearance proxy", "front height distribution", "yaw response", "center phase time"), rollback_rule="Undo if clearance, stability, or a protected phase worsens.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:rear_platform_height", component_id="platform", physical_property_id="rear_platform_height", primary_controls=("lr_ride_height_mm",), coordinated_controls=("rr_ride_height_mm",), invariants_to_hold=("Hold LR-to-RR height split fixed.", "Recheck crossweight and leave unrelated controls unchanged."), preconditions=common_preconditions, expected_component_response=("Rear chassis operating height moves by one sourced adjacent option.",), expected_vehicle_response=("Rear platform and rake relationship change in the target speed band.",), countereffects=("Exit instability, bottoming, or an adverse high-speed balance shift.",), success_metrics=("rear height distribution", "rake proxy", "yaw response", "exit phase time"), rollback_rule="Undo if stability, clearance, or a protected phase worsens.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:rf_spring_rate", component_id="springs", physical_property_id="spring_rate", primary_controls=("rf_front_spring_n_per_mm",), automatic_sim_compensations=("The scoped 2026 Next Gen garage maintains configured ride height when spring rate changes.",), required_manual_compensations=("Recheck platform response and crossweight; automatic height maintenance is not response validation.",), invariants_to_hold=("Hold dampers, ARBs, alignment, pressures, and driver line fixed.",), preconditions=common_preconditions, expected_component_response=("RF travel/support response changes under comparable load.",), expected_vehicle_response=("Front platform and roll response may change in the target phase.",), countereffects=("Reduced bump compliance or worse sustained center balance.",), success_metrics=("RF travel response", "front roll response", "steering demand", "phase time"), rollback_rule="Undo if P19 rejects compliance, stability, or phase-time countereffects.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:lr_spring_rate", component_id="springs", physical_property_id="spring_rate", primary_controls=("lr_rear_spring_n_per_mm",), automatic_sim_compensations=("The scoped 2026 Next Gen garage maintains configured ride height when spring rate changes.",), required_manual_compensations=("Recheck platform response and crossweight; automatic height maintenance is not response validation.",), invariants_to_hold=("Hold dampers, ARBs, alignment, pressures, and driver line fixed.",), preconditions=common_preconditions, expected_component_response=("LR travel/support response changes under comparable load.",), expected_vehicle_response=("Rear platform, drive support, and compliance may change in the target phase.",), countereffects=("Reduced bump compliance, traction, or worse sustained balance.",), success_metrics=("LR travel response", "rear platform response", "throttle pickup", "phase time"), rollback_rule="Undo if P19 rejects compliance, traction, or phase-time countereffects.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:crossweight", component_id="weight_distribution", physical_property_id="static_diagonal_relationship", primary_controls=("cross_weight_percent",), invariants_to_hold=("Hold ride height, spring rates, ARB preload, tire pressures, and driver line fixed.",), preconditions=common_preconditions, expected_component_response=("The recorded static diagonal relationship changes by one sourced adjacent option.",), expected_vehicle_response=("Entry stability, center rotation, or exit security may respond.",), countereffects=("A center gain may create unacceptable exit instability or braking response.",), success_metrics=("steering demand", "yaw response", "throttle pickup", "entry/center/exit phase time"), rollback_rule="Undo when P19 policy rejects any protected-phase countereffect.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:front_brake_distribution", component_id="brakes", physical_property_id="front_rear_pressure_distribution", primary_controls=("front_brake_bias_percent",), invariants_to_hold=("Hold braking point, pressure application, line, tires, and chassis setup fixed.",), preconditions=common_preconditions, expected_component_response=("Front/rear line-pressure distribution changes under comparable pedal input.",), expected_vehicle_response=("Braking stability or rotation response may change.",), countereffects=("Front lock, rear instability, or longer braking phase.",), success_metrics=("four line pressures", "lock/ABS evidence", "braking yaw response", "braking phase time"), rollback_rule="Undo if braking safety, stability, or time worsens.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:final_drive_ratio", component_id="final_drive", physical_property_id="final_drive_ratio", primary_controls=("rear_end_ratio",), invariants_to_hold=("Hold engine map, tires, line, shifts, weather, and traffic context fixed.",), preconditions=common_preconditions, expected_component_response=("RPM-to-speed relationship changes by one sourced legal option.",), expected_vehicle_response=("Acceleration and limiter headroom respond without implying horsepower.",), countereffects=("Limiter contact, extra shift, or reduced straight carry.",), success_metrics=("RPM headroom", "longitudinal acceleration", "exit/straight time"), rollback_rule="Undo if limiter, shift, or straight-time countereffects outweigh the target response.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:whole_platform_height", component_id="platform", physical_property_id="whole_platform_height", primary_controls=("lf_ride_height_mm",), coordinated_controls=("rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"), invariants_to_hold=("Move all four sourced adjacent ride-height options together.", "Preserve front-to-rear rake and side-to-side height differences, then recheck crossweight."), preconditions=common_preconditions, expected_component_response=("The complete chassis operating-height envelope moves by one sourced adjacent option.",), expected_vehicle_response=("Whole-platform clearance changes while the recorded rake relationship is protected.",), countereffects=("Unexpected balance migration, bottoming, or loss of platform response." ,), success_metrics=("four-corner height distribution", "clearance proxy", "yaw response", "phase time"), rollback_rule="Undo if clearance, balance, or any protected phase worsens.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:steering_ratio", component_id="steering", physical_property_id="steering_ratio", primary_controls=("steering_ratio",), invariants_to_hold=("Hold steering offset, alignment, FFB context, line, and chassis setup fixed.",), preconditions=common_preconditions, expected_component_response=("Rack travel per steering-wheel revolution changes by one sourced legal option.",), expected_vehicle_response=("Steering rate and workload context respond; offset remains a comfort control.",), countereffects=("Nervous response or greater correction workload.",), success_metrics=("steering rate", "yaw response lag", "correction workload", "phase time"), rollback_rule="Undo if workload or stability worsens.", source_ids=_GENERAL),
    )


def _captured_setup_value(snapshot: SetupSnapshot, path: str) -> Any | None:
    value: Any = snapshot.extracted_values
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            value = None
            break
        value = value[part]
    if value is None and "." not in path:
        value = getattr(snapshot, path, None)
    return value


def _captured_component_settings(
    component_id: str,
    snapshot: SetupSnapshot | None,
) -> tuple[str, ...]:
    if snapshot is None:
        return ()
    settings: list[str] = []
    for path, label, unit, decimals in _COMPONENT_SETTING_SPECS[component_id]:
        value = _captured_setup_value(snapshot, path)
        if value is None:
            continue
        if isinstance(value, bool):
            display = "attached" if value else "detached"
        elif isinstance(value, (int, float)):
            display = f"{float(value):.{decimals}f}"
        else:
            display = str(value)
        suffix = f" {unit}" if unit else ""
        settings.append(f"{label}: {display}{suffix}")
    return tuple(settings)


def _quantity_requirements(component_id: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    groups = _COMPONENT_LIVE_CHANNEL_GROUPS[component_id]
    names = _QUANTITY_NAMES.get(
        component_id,
        tuple(f"live_response_{index + 1}" for index in range(len(groups))),
    )
    pairs = list(zip(names, groups, strict=False))
    if component_id == "brakes":
        pairs.append((
            "hydraulic_line_pressure_distribution",
            _QUANTITY_CHANNEL_OVERRIDES[(component_id, "hydraulic_line_pressure_distribution")],
        ))
    return tuple(pairs)


def _quantity_certificates(
    component_id: str,
    available_channels: set[str],
    observations: tuple[object, ...],
) -> tuple[QuantityObservabilityCertificate, ...]:
    certificates: list[QuantityObservabilityCertificate] = []
    for quantity_id, required in _quantity_requirements(component_id):
        available = tuple(channel for channel in required if channel in available_channels)
        missing = tuple(channel for channel in required if channel not in available_channels)
        qualified = tuple(
            observation for observation in observations
            if bool(getattr(observation, "qualified", False))
            and not tuple(getattr(observation, "blocker_reasons", ()))
            and set(required) <= set(getattr(observation, "source_channels", ()))
        )
        coverage = max(
            (float(getattr(item, "sample_coverage", 0.0)) for item in qualified),
            default=None,
        )
        if coverage is not None and coverage >= 0.7:
            state = "observed"
            basis = "qualified_producer"
            blockers: tuple[str, ...] = ()
        elif not missing:
            state = "screenable"
            basis = "manifest_presence_only"
            blockers = ()
        else:
            state = "unavailable"
            basis = "missing"
            blockers = ("Missing required channels: " + ", ".join(missing) + ".",)
        certificates.append(QuantityObservabilityCertificate(
            quantity_id=quantity_id,
            required_channels=required,
            available_channels=available,
            missing_channels=missing,
            health_basis=basis,
            minimum_coobserved_coverage=0.7,
            coobserved_coverage=coverage,
            state=state,
            producer_artifact_ids=tuple(item.artifact_id for item in qualified),
            supported_derived_outputs=tuple(item.observation_id for item in qualified),
            blocker_reasons=blockers,
        ))
    return tuple(certificates)


def build_component_awareness(
    report: InternalIntelligenceReport,
    *,
    runtime_identity: VehicleSystemsRuntimeIdentity,
    setup_snapshot: SetupSnapshot | None = None,
) -> VehicleSystemsProjection:
    """Project immutable P20 observations and P19 outcomes without recomputation."""
    if runtime_identity.run_id != report.run_id:
        raise ValueError("Vehicle Systems runtime identity does not match the reasoning run.")
    if setup_snapshot is not None and setup_snapshot.run_id != report.run_id:
        raise ValueError("Vehicle Systems setup snapshot does not match the reasoning run.")
    graph = compile_vehicle_systems_graph()
    observation_report = report.mechanism_observations
    if observation_report is not None:
        if observation_report.run_id != report.run_id:
            raise ValueError("Vehicle Systems P20 observation report belongs to another run.")
        if (
            setup_snapshot is not None
            and observation_report.setup_id is not None
            and observation_report.setup_id != setup_snapshot.setup_id
        ):
            raise ValueError("Vehicle Systems P20 observations belong to another setup snapshot.")
    observations = tuple(
        item
        for item in (observation_report.observations if observation_report else ())
        if item.qualified
    )
    for observation in observations:
        if observation.run_id != report.run_id:
            raise ValueError("Vehicle Systems cannot project a foreign P20 observation.")
        if observation_report is not None and observation.setup_id != observation_report.setup_id:
            raise ValueError("Vehicle Systems P20 observation setup ownership is inconsistent.")
    authority = report.reasoning_snapshot.authority
    snapshot_hash = canonical_json_sha256(report.reasoning_snapshot)
    setup_snapshot_hash = (
        canonical_json_sha256(setup_snapshot)
        if setup_snapshot is not None
        else None
    )
    control_components = {
        key: definition.component_id
        for definition in graph.components
        for key in definition.setup_keys
    }
    cause_component_ids: dict[str, frozenset[str]] = {}
    directly_related_cause_ids: dict[str, frozenset[str]] = {}
    for cause in report.reasoning_snapshot.causes:
        cause_id = str(getattr(cause, "cause_id", "unknown"))
        related_controls = tuple(getattr(cause, "related_control_keys", ()))
        direct_components = {
            control_components[key] for key in related_controls if key in control_components
        }
        direct_components.update(
            control_components[outcome.control_key]
            for outcome in cause.controlled_outcomes
            if outcome.control_key in control_components
        )
        mechanism_components = {
            component_id
            for mechanism_key in (
                getattr(cause, "mechanism_keys", ())
                or (str(getattr(cause, "mechanism_key", "")),)
            )
            for component_id in _MECHANISM_KEY_COMPONENTS.get(
                str(mechanism_key).casefold(), ()
            )
        }
        cause_component_ids[cause_id] = frozenset(direct_components | mechanism_components)
        directly_related_cause_ids[cause_id] = frozenset(direct_components)

    states: list[ComponentAwarenessState] = []
    unique_histories: dict[tuple[str, str], ComponentControlledHistory] = {}

    for definition in graph.components:
        relevant_observations = tuple(
            item
            for item in observations
            if any(
                definition.component_id in _MECHANISM_COMPONENTS.get(mechanism, ())
                for mechanism in (
                    getattr(item, "mechanism_kinds", ()) or (item.mechanism,)
                )
            )
        )
        relevant_causes = tuple(
            cause
            for cause in report.reasoning_snapshot.causes
            if definition.component_id
            in cause_component_ids[str(getattr(cause, "cause_id", "unknown"))]
        )
        histories_by_key: dict[tuple[str, str], ComponentControlledHistory] = {}
        for cause in report.reasoning_snapshot.causes:
            for outcome in cause.controlled_outcomes:
                if outcome.control_key not in definition.setup_keys:
                    continue
                stage_run_ids = tuple(getattr(outcome, "stage_run_ids", ()))
                eligible_lap_ids = tuple(getattr(outcome, "eligible_lap_ids", ()))
                metric = str(getattr(outcome, "metric", None) or "unscoped")
                phase = str(getattr(outcome, "phase", None) or "unscoped")
                blocker_reasons = tuple(getattr(outcome, "blocker_reasons", ()))
                history = ComponentControlledHistory(
                    workflow_id=outcome.workflow_id,
                    source_run_id=str(getattr(outcome, "source_run_id", None) or report.run_id),
                    stage_run_ids=stage_run_ids,
                    eligible_lap_ids=eligible_lap_ids,
                    control_key=outcome.control_key or "unknown",
                    metric=metric,
                    phase=phase,
                    actual_effect_s=getattr(outcome, "actual_effect_s", None),
                    time_origin_phase=getattr(outcome, "time_origin_phase", None),
                    time_origin_pct=getattr(outcome, "time_origin_pct", None),
                    downstream_carry_effect_s=getattr(outcome, "downstream_carry_effect_s", None),
                    mechanism_state=outcome.outcome,
                    control_response=outcome.control_direction_result or "unavailable",
                    policy_verdict=outcome.verdict,
                    countereffects=outcome.countereffects,
                    blocker_reasons=blocker_reasons,
                    diagnostic_validity=str(
                        getattr(outcome, "diagnostic_validity", "control_response_only")
                    ),
                    exact_context=(
                        outcome.outcome != "invalid"
                        and outcome.verdict != "invalid"
                        and not blocker_reasons
                        and bool(stage_run_ids)
                        and bool(eligible_lap_ids)
                        and metric != "unscoped"
                        and phase != "unscoped"
                    ),
                )
                history_key = (history.workflow_id, history.control_key)
                existing = histories_by_key.get(history_key)
                if existing is not None and existing != history:
                    raise ValueError(
                        "Conflicting controlled history exists for one workflow and control."
                    )
                histories_by_key[history_key] = history
                global_existing = unique_histories.get(history_key)
                if global_existing is not None and global_existing != history:
                    raise ValueError(
                        "Controlled history cannot change meaning across component causes."
                    )
                unique_histories[history_key] = history
        histories = tuple(histories_by_key.values())
        settings = _captured_component_settings(definition.component_id, setup_snapshot)
        setting_keys = tuple(path for path, _label, _unit, _decimals in _COMPONENT_SETTING_SPECS[definition.component_id])
        present_setting_keys = tuple(
            key for key in setting_keys
            if setup_snapshot is not None and _captured_setup_value(setup_snapshot, key) is not None
        )
        missing_setting_keys = tuple(key for key in setting_keys if key not in present_setting_keys)
        supporting_artifact_ids = tuple(dict.fromkeys(
            item.artifact_id for item in relevant_observations
        ))
        supporting_citation_ids = tuple(dict.fromkeys(
            citation.citation_id for cause in relevant_causes for citation in cause.supporting_evidence
        ))
        contradicting_citation_ids = tuple(dict.fromkeys(
            citation.citation_id for cause in relevant_causes for citation in cause.contradicting_evidence
        ))
        supporting_cause_ids = tuple(dict.fromkeys(
            str(getattr(cause, "cause_id", "unknown"))
            for cause in relevant_causes if cause.supporting_evidence
        ))
        contradicting_cause_ids = tuple(dict.fromkeys(
            str(getattr(cause, "cause_id", "unknown"))
            for cause in relevant_causes if cause.contradicting_evidence
        ))
        p19_authorized = bool(
            authority.setup_authorized
            and authority.control_key in definition.setup_keys
        )
        blocked_control_keys = tuple(dict.fromkeys(
            history.control_key
            for history in histories
            if history.exact_context and history.policy_verdict == "undo"
            # P19 already compares the complete material policy identity before
            # authorizing a test. An older Undo for the same garage control can
            # remain visible as history, but P26 must not broaden it into a
            # component-level veto of a newly authorized, different policy.
            and not (p19_authorized and history.control_key == authority.control_key)
        ))
        testable_control_keys = tuple(
            key for key in definition.setup_keys if key not in blocked_control_keys
        )
        policy_blocked = bool(definition.setup_keys) and not testable_control_keys
        usable_histories = tuple(
            history for history in histories
            if history.exact_context
            and history.policy_verdict != "invalid"
            and history.mechanism_state != "invalid"
        )
        response_known = any(
            history.control_response in {"matched", "missed"}
            for history in usable_histories
        )
        policy_known = any(
            history.policy_verdict in {"keep", "undo", "retest"}
            for history in usable_histories
        )
        if policy_blocked:
            relevance = ComponentRelevance.BLOCKED
        elif usable_histories:
            relevance = ComponentRelevance.TESTED
        elif contradicting_citation_ids and not supporting_artifact_ids and not supporting_citation_ids:
            relevance = ComponentRelevance.CONTRADICTED
        elif any(
            cause.status == "likely"
            and definition.component_id
            in directly_related_cause_ids[str(getattr(cause, "cause_id", "unknown"))]
            for cause in relevant_causes
        ):
            relevance = ComponentRelevance.SUPPORTED
        elif relevant_observations or relevant_causes:
            relevance = ComponentRelevance.CANDIDATE
        else:
            relevance = ComponentRelevance.IRRELEVANT

        observability: list[ComponentObservabilityState] = [ComponentObservabilityState.DEFINITION_KNOWN]
        if settings and not missing_setting_keys:
            observability.append(ComponentObservabilityState.SETUP_CAPTURED)
        available_channel_set = set(runtime_identity.available_telemetry_channels)
        quantity_certificates = _quantity_certificates(
            definition.component_id, available_channel_set, relevant_observations
        )
        available_live_channels = tuple(dict.fromkeys(
            channel for certificate in quantity_certificates for channel in certificate.available_channels
        ))
        if any(item.state == "observed" for item in quantity_certificates):
            observability.append(ComponentObservabilityState.LIVE_RESPONSE_OBSERVABLE)
        if relevant_observations:
            observability.append(ComponentObservabilityState.CURRENT_RESPONSE_OBSERVED)
        if relevance is ComponentRelevance.SUPPORTED:
            observability.append(ComponentObservabilityState.MECHANISM_SUPPORTED)
        if response_known:
            observability.append(ComponentObservabilityState.CONTROLLED_RESPONSE_KNOWN)
        if policy_known:
            observability.append(ComponentObservabilityState.EXACT_CONTEXT_POLICY_KNOWN)

        component_discriminator = next(
            (
                cause.discriminator.instruction
                for cause in sorted(
                    relevant_causes,
                    key=lambda item: (item.ordinal_rank, item.cause_id),
                )
                if cause.discriminator is not None
            ),
            definition.measurement_requirements[0],
        )
        if p19_authorized:
            component_discriminator = report.best_measurement.instruction
        states.append(ComponentAwarenessState(
            component_id=definition.component_id,
            run_id=report.run_id,
            observation_scopes=tuple(
                ComponentObservationScope(
                    artifact_id=observation.artifact_id,
                    observation_id=observation.observation_id,
                    lap_number=observation.lap_number,
                    phase=observation.phase,
                    lap_pct_start=observation.lap_pct_start,
                    lap_pct_end=observation.lap_pct_end,
                )
                for observation in relevant_observations
            ),
            current_settings=settings,
            present_setting_keys=present_setting_keys,
            missing_setting_keys=missing_setting_keys,
            current_setting_provenance=(
                (f"setup_snapshot:{setup_snapshot.setup_id}:{setup_snapshot_hash}",)
                if settings and setup_snapshot is not None and setup_snapshot_hash is not None
                else ()
            ),
            observability_states=tuple(observability),
            quantity_observability=quantity_certificates,
            current_response_state=(
                "observed" if relevant_observations
                else "not_observed" if any(item.state == "screenable" for item in quantity_certificates)
                else "unavailable"
            ),
            relevance=relevance,
            supporting_artifact_ids=supporting_artifact_ids,
            supporting_citation_ids=supporting_citation_ids,
            contradicting_citation_ids=contradicting_citation_ids,
            supporting_cause_ids=supporting_cause_ids,
            contradicting_cause_ids=contradicting_cause_ids,
            confounders=definition.confounders,
            unavailable_quantities=definition.observability.unavailable_quantities,
            measurement_requirements=definition.measurement_requirements,
            coupled_component_ids=definition.coupled_component_ids,
            interaction_summaries=tuple(
                f"{(interaction.target_component_id if interaction.source_component_id == definition.component_id else interaction.source_component_id).replace('_', ' ')} — {interaction.interaction_type.replace('_', ' ')}: {interaction.description}"
                for interaction in graph.interactions
                if definition.component_id
                in {interaction.source_component_id, interaction.target_component_id}
            ),
            controlled_history=histories,
            blocked_control_keys=blocked_control_keys,
            testable_control_keys=testable_control_keys,
            authorized_control_key=authority.control_key if p19_authorized else None,
            available_live_channel_ids=available_live_channels,
            live_response_blocker_reasons=tuple(dict.fromkeys(
                blocker
                for certificate in quantity_certificates
                for blocker in certificate.blocker_reasons
            )),
            next_discriminator=component_discriminator,
            current_testability="p19_authorized" if p19_authorized else "policy_blocked" if policy_blocked else "measurement_only",
            authority_state="p19_authorized" if p19_authorized else "controlled_history" if usable_histories else "observation_only" if supporting_artifact_ids or supporting_citation_ids or contradicting_citation_ids else "knowledge_only",
            evidence_states=tuple(dict.fromkeys(item.evidence_state for item in relevant_observations)),
            blocker_reasons=(
                "Exact controlled history blocks these controls from generic reopening: "
                + ", ".join(blocked_control_keys)
                + ".",
            ) if blocked_control_keys else (),
            setup_authorized=p19_authorized,
        ))

    rank = {ComponentRelevance.SUPPORTED: 0, ComponentRelevance.TESTED: 1, ComponentRelevance.CANDIDATE: 2, ComponentRelevance.CONTRADICTED: 3, ComponentRelevance.BLOCKED: 4, ComponentRelevance.IRRELEVANT: 5}

    def component_priority(item: ComponentAwarenessState) -> tuple[int, int, int, int]:
        cause_ranks = [
            cause.ordinal_rank
            for cause in report.reasoning_snapshot.causes
            if item.component_id
            in cause_component_ids[str(getattr(cause, "cause_id", "unknown"))]
        ]
        direct_ranks = [
            cause.ordinal_rank
            for cause in report.reasoning_snapshot.causes
            if item.component_id
            in directly_related_cause_ids[str(getattr(cause, "cause_id", "unknown"))]
        ]
        return (
            rank[item.relevance],
            min(direct_ranks, default=9999),
            min(cause_ranks, default=9999),
            -len(item.supporting_artifact_ids),
        )

    ordered = sorted(states, key=lambda item: (*component_priority(item), item.component_id))
    leading = next((item for item in ordered if item.relevance in {ComponentRelevance.SUPPORTED, ComponentRelevance.TESTED, ComponentRelevance.CANDIDATE}), None)
    candidates = [item for item in ordered if item.relevance is ComponentRelevance.CANDIDATE]
    if not any(item.relevance in {ComponentRelevance.SUPPORTED, ComponentRelevance.TESTED} for item in ordered) and len(candidates) > 1:
        suspension_family = {"springs", "dampers", "anti_roll_bars", "platform"}
        leading_label = (
            "Platform / suspension component family"
            if len(suspension_family & {item.component_id for item in candidates}) >= 2
            else "Multiple component families unresolved"
        )
    else:
        leading_label = next((item.label for item in graph.components if leading and item.component_id == leading.component_id), "No component isolated")
    next_discriminator = leading.next_discriminator if leading is not None else report.best_measurement.instruction
    leading_component_ids = tuple(
        item.component_id for item in ordered
        if leading is not None and component_priority(item) == component_priority(leading)
    ) if leading is not None else ()
    contradiction_scope = set(leading_component_ids)
    strongest_contradiction = next(
        (
            citation.summary
            for cause in sorted(
                report.reasoning_snapshot.causes,
                key=lambda item: (
                    int(getattr(item, "ordinal_rank", 9999)),
                    str(getattr(item, "cause_id", "unknown")),
                ),
            )
            if not contradiction_scope
            or bool(
                cause_component_ids[str(getattr(cause, "cause_id", "unknown"))]
                & contradiction_scope
            )
            for citation in cause.contradicting_evidence
        ),
        "No qualified contradiction is present in the exact reasoning snapshot.",
    )
    runtime_nodes: dict[str, VehicleSystemsNode] = {}
    runtime_edges: dict[str, VehicleSystemsEdge] = {}

    def add_runtime_node(node: VehicleSystemsNode) -> None:
        existing = runtime_nodes.get(node.node_id)
        if existing is None:
            runtime_nodes[node.node_id] = node
            return
        if (
            existing.kind != node.kind
            or existing.label != node.label
            or existing.component_id != node.component_id
            or existing.authority != node.authority
        ):
            raise ValueError(f"runtime vehicle-system node identity collision: {node.node_id}")
        runtime_nodes[node.node_id] = existing.model_copy(update={
            "source_ids": tuple(dict.fromkeys((*existing.source_ids, *node.source_ids))),
        })

    def add_runtime_edge(edge: VehicleSystemsEdge) -> None:
        existing = runtime_edges.get(edge.edge_id)
        if existing is not None and existing != edge:
            raise ValueError(f"runtime vehicle-system edge identity collision: {edge.edge_id}")
        runtime_edges[edge.edge_id] = edge

    for observation in observations:
        observation_id = f"runtime:observation:{observation.artifact_id}"
        state_id = f"runtime:state:{observation.mechanism.value}"
        add_runtime_node(VehicleSystemsNode(
            node_id=observation_id, kind=VehicleSystemsNodeKind.OBSERVATION,
            label=str(getattr(observation, "summary", observation.mechanism.value)),
            source_ids=(observation.artifact_id,), authority="observation_only",
        ))
        add_runtime_node(VehicleSystemsNode(
            node_id=state_id, kind=VehicleSystemsNodeKind.VEHICLE_STATE,
            label=observation.mechanism.value.replace("_", " ").title(),
            source_ids=(observation.artifact_id,), authority="observation_only",
        ))
        edge_kind = VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE
        add_runtime_edge(VehicleSystemsEdge(
            edge_id=f"runtime-edge:{hashlib.sha256(f'{observation_id}|{state_id}|{edge_kind.value}'.encode()).hexdigest()[:20]}",
            source_node_id=observation_id, target_node_id=state_id,
            kind=edge_kind,
            direction="observed", source_ids=(observation.artifact_id,), authority="observation_only",
        ))
    for cause in report.reasoning_snapshot.causes:
        mechanism_key = str(getattr(cause, "mechanism_key", "unresolved"))
        state_id = f"runtime:state:{mechanism_key}"
        for edge_kind, cause_citations in (
            (VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE, cause.supporting_evidence),
            (VehicleSystemsEdgeKind.OBSERVATION_CONTRADICTS_STATE, cause.contradicting_evidence),
        ):
            for citation in cause_citations:
                observation_id = f"runtime:citation:{citation.citation_id}"
                citation_authority = (
                    "controlled_history"
                    if citation.evidence_state.value == "controlled_test_effect"
                    else "observation_only"
                )
                add_runtime_node(VehicleSystemsNode(
                    node_id=observation_id,
                    kind=VehicleSystemsNodeKind.OBSERVATION,
                    label=citation.summary,
                    source_ids=(citation.citation_id,),
                    authority=citation_authority,
                ))
                add_runtime_node(VehicleSystemsNode(
                    node_id=state_id,
                    kind=VehicleSystemsNodeKind.VEHICLE_STATE,
                    label=mechanism_key.replace("_", " ").title(),
                    source_ids=(citation.citation_id,),
                    authority="observation_only",
                ))
                edge_id = f"runtime-edge:{hashlib.sha256(f'{observation_id}|{state_id}|{edge_kind.value}'.encode()).hexdigest()[:20]}"
                add_runtime_edge(VehicleSystemsEdge(
                    edge_id=edge_id,
                    source_node_id=observation_id,
                    target_node_id=state_id,
                    kind=edge_kind,
                    direction="observed",
                    source_ids=(citation.citation_id,),
                    authority=citation_authority,
                ))
    for history in unique_histories.values():
        if not history.exact_context or history.control_response not in {"matched", "missed"}:
            continue
        component_id = control_components[history.control_key]
        control_id = f"runtime:control:{history.control_key}"
        outcome_id = f"runtime:outcome:{history.workflow_id}:{history.control_key}"
        add_runtime_node(VehicleSystemsNode(
            node_id=control_id, kind=VehicleSystemsNodeKind.CONTROL,
            label=SETUP_CONTROL_SPECS[history.control_key].label,
            component_id=component_id, source_ids=(history.workflow_id,),
            authority="controlled_history",
        ))
        add_runtime_node(VehicleSystemsNode(
            node_id=outcome_id, kind=VehicleSystemsNodeKind.OUTCOME,
            label=f"{history.control_response}; {history.policy_verdict}",
            component_id=component_id, source_ids=(history.workflow_id,),
            authority="controlled_history",
        ))
        edge_kind = VehicleSystemsEdgeKind.CONTROLLED_TEST_OBSERVED_RESPONSE
        add_runtime_edge(VehicleSystemsEdge(
            edge_id=f"runtime-edge:{hashlib.sha256(f'{control_id}|{outcome_id}'.encode()).hexdigest()[:20]}",
            source_node_id=control_id, target_node_id=outcome_id,
            kind=edge_kind,
            direction="observed", source_ids=(history.workflow_id,), authority="controlled_history",
        ))
        if history.policy_verdict == "undo":
            policy_id = f"runtime:outcome:policy:{history.workflow_id}:{history.control_key}"
            add_runtime_node(VehicleSystemsNode(
                node_id=policy_id, kind=VehicleSystemsNodeKind.OUTCOME,
                label="Undo preserved after unacceptable countereffect or missed target",
                component_id=component_id, source_ids=(history.workflow_id,),
                authority="controlled_history",
            ))
            add_runtime_edge(VehicleSystemsEdge(
                edge_id=f"runtime-edge:{hashlib.sha256(f'{outcome_id}|{policy_id}'.encode()).hexdigest()[:20]}",
                source_node_id=outcome_id, target_node_id=policy_id,
                kind=VehicleSystemsEdgeKind.POLICY_REJECTED_DUE_TO_COUNTEREFFECT,
                direction="observed", source_ids=(history.workflow_id,), authority="controlled_history",
            ))
    runtime_graph = VehicleSystemsRuntimeGraph(
        reasoning_snapshot_sha256=snapshot_hash,
        nodes=tuple(runtime_nodes.values()), edges=tuple(runtime_edges.values()),
    )
    return VehicleSystemsProjection(
        run_id=report.run_id,
        session_id=getattr(report, "session_id", None),
        graph_version=graph.graph_version,
        knowledge_graph_sha256=graph.content_sha256,
        reasoning_snapshot_sha256=snapshot_hash,
        setup_id=setup_snapshot.setup_id if setup_snapshot is not None else None,
        setup_snapshot_sha256=setup_snapshot_hash,
        runtime_identity=runtime_identity,
        leading_system=leading_label,
        leading_component_ids=leading_component_ids,
        next_discriminator=next_discriminator,
        strongest_contradiction=strongest_contradiction,
        knowledge_debt=tuple(dict.fromkeys(
            quantity for item in ordered[:3] for quantity in item.unavailable_quantities
        )),
        component_states=tuple(states),
        experiment_factors=_experiment_factors(),
        runtime_graph=runtime_graph,
        setup_authorized=any(item.setup_authorized for item in states),
    )


def inspect_component(component_id: str, projection: VehicleSystemsProjection) -> ComponentInspectionResponse:
    graph = compile_vehicle_systems_graph()
    definition = next((item for item in graph.components if item.component_id == component_id), None)
    if definition is None:
        raise ValueError(f"Unknown vehicle-system component: {component_id}")
    state = next((item for item in projection.component_states if item.component_id == component_id), None)
    if state is None:
        raise ValueError(f"Component {component_id} is outside projection {projection.run_id}.")
    return ComponentInspectionResponse(
        run_id=projection.run_id,
        session_id=projection.session_id,
        graph_version=projection.graph_version,
        knowledge_graph_sha256=projection.knowledge_graph_sha256,
        reasoning_snapshot_sha256=projection.reasoning_snapshot_sha256,
        setup_id=projection.setup_id,
        setup_snapshot_sha256=projection.setup_snapshot_sha256,
        runtime_identity=projection.runtime_identity,
        component_id=component_id,
        definition=definition,
        state=state,
        interactions=tuple(
            item for item in graph.interactions
            if component_id in {item.source_component_id, item.target_component_id}
        ),
        controls=definition.setup_keys,
    )


def trace_control_mechanism(control_key: str) -> tuple[VehicleSystemsEdge, ...]:
    graph = compile_vehicle_systems_graph()
    if control_key not in SETUP_CONTROL_SPECS:
        raise ValueError(f"Unknown setup control: {control_key}")
    start = f"control:{control_key}"
    property_ids = {edge.target_node_id for edge in graph.edges if edge.source_node_id == start and edge.kind is VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY}
    state_ids = {edge.target_node_id for edge in graph.edges if edge.source_node_id in property_ids and edge.kind is VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE}
    return tuple(edge for edge in graph.edges if edge.source_node_id == start or edge.source_node_id in property_ids or edge.source_node_id in state_ids)


__all__ = ["build_component_awareness", "compile_vehicle_systems_graph", "inspect_component", "trace_control_mechanism", "vehicle_systems_runtime_identity"]
