"""Compile P26 vehicle knowledge and project P19/P20 evidence onto it."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import hashlib
import json
import re
from typing import Any

from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS, format_setup_value
from racelab_engine.knowledge.setup import load_setup_knowledge
from racelab_engine.io.telemetry_manifest import compatibility_fingerprint
from racelab_engine.models.intelligence import InternalIntelligenceReport
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.models.vehicle_systems import (
    BuildApplicability,
    ComponentAwarenessState,
    ComponentInspectionResponse,
    ComponentControlledHistory,
    ComponentDefinition,
    ComponentInteraction,
    ComponentObservabilityContract,
    ComponentObservabilityState,
    ComponentRelevance,
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
from racelab_engine.services.import_service import read_telemetry_manifest


_GRAPH_VERSION = "2026.08.next-gen.2"
_NEXT_GEN = BuildApplicability(
    car_family="next_gen",
    car_paths=(
        "stockcars chevycamarozl12022",
        "stockcars fordmustang2022",
        "stockcars toyotacamry2022",
    ),
    iracing_build_min="2026.1",
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


_MECHANISM_COMPONENTS: dict[MechanismKind, tuple[str, ...]] = {
    MechanismKind.BRAKING_RESPONSE: ("brakes", "weight_distribution", "tires"),
    MechanismKind.CORNER_ROTATION: ("anti_roll_bars", "springs", "weight_distribution", "alignment", "differential", "tires"),
    MechanismKind.TIRE_STATE: ("tires", "alignment"),
    MechanismKind.DAMPER_RESPONSE: ("dampers", "springs"),
    MechanismKind.PLATFORM_RESPONSE: ("platform", "springs", "dampers", "anti_roll_bars"),
    MechanismKind.RESISTANCE_SCRUB_LIKE: ("alignment", "tires", "cooling_configuration"),
    MechanismKind.POWERTRAIN_RESPONSE: ("differential", "final_drive", "tires"),
    MechanismKind.STINT_TREND: ("tires", "cooling_configuration"),
    MechanismKind.DRIVER_EXECUTION: ("steering",),
}

_MECHANISM_KEY_COMPONENTS: dict[str, tuple[str, ...]] = {
    "tire_state": ("tires", "alignment"),
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
    "driver_execution": ("steering",),
}

_AREA_COMPONENTS = {
    **{key: "tires" for key in ("tire_pressure", "pressure_split", "pressure_gain", "tire_temp_spread", "tire_wear")},
    **{key: "alignment" for key in ("camber", "caster", "toe", "front_toe_response", "rear_toe_stability")},
    **{key: "springs" for key in ("spring_rate", "spring_perch", "front_spring_support", "rear_spring_support", "spring_split")},
    **{key: "dampers" for key in ("shock_collar", "ls_compression", "hs_compression", "hs_comp_slope", "ls_rebound", "hs_rebound", "hs_reb_slope", "shock_histogram", "shock_velocity_rms", "shock_deflection_delta")},
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


def _component_for_area(area: str) -> str:
    try:
        return _AREA_COMPONENTS[area.casefold()]
    except KeyError as exc:
        raise ValueError(f"Next Gen setup area lacks an explicit component mapping: {area}") from exc


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in re.findall(r"\d+", value))
    if not parts:
        raise ValueError(f"Invalid iRacing build version: {value}")
    return parts


def vehicle_systems_runtime_identity(
    run_id: str,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> VehicleSystemsRuntimeIdentity:
    payload = dict(manifest) if manifest is not None else read_telemetry_manifest(run_id)
    identity = payload.get("compatibility_identity")
    if not isinstance(identity, Mapping):
        raise ValueError(f"Vehicle Systems requires a verified telemetry manifest for run {run_id}.")
    if identity.get("missing_required_fields"):
        raise ValueError(f"Vehicle Systems runtime identity is incomplete for run {run_id}.")
    car_path = str(identity.get("car_path") or "")
    build = str(identity.get("iracing_build_version") or "")
    track_configuration = str(identity.get("track_configuration_name") or "")
    if car_path.casefold() not in _NEXT_GEN.car_paths:
        raise ValueError(f"Vehicle Systems graph {_GRAPH_VERSION} is unavailable for car path {car_path}.")
    if _version_tuple(build) < _version_tuple(_NEXT_GEN.iracing_build_min):
        raise ValueError(f"Vehicle Systems graph {_GRAPH_VERSION} does not cover iRacing build {build}.")
    if not any(value in track_configuration.casefold() for value in _NEXT_GEN.track_package_types):
        raise ValueError(f"Vehicle Systems requires an oval track configuration, got {track_configuration}.")
    schema_fingerprint = str(payload.get("schema_fingerprint") or "")
    declared_fingerprint = str(payload.get("compatibility_fingerprint") or "")
    if compatibility_fingerprint(schema_fingerprint, dict(identity)) != declared_fingerprint:
        raise ValueError(f"Vehicle Systems compatibility identity failed integrity verification for run {run_id}.")
    return VehicleSystemsRuntimeIdentity(
        car_path=car_path,
        car_version=str(identity.get("car_version") or ""),
        iracing_build_version=build,
        track_configuration_name=track_configuration,
        compatibility_fingerprint=declared_fingerprint,
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
    next_gen_area_ids = {
        area.setup_area.casefold()
        for area in knowledge.setup_areas
        if "next_gen" not in area.disabled_for
        and ("all" in area.applies_to or "next_gen" in area.applies_to)
    }
    unmapped_area_ids = sorted(next_gen_area_ids - set(_AREA_COMPONENTS))
    if unmapped_area_ids:
        raise ValueError(
            f"Next Gen setup areas require explicit component mappings: {unmapped_area_ids}"
        )
    component_by_id = {item.component_id: item for item in _COMPONENTS}
    if any(not set(item.source_ids) <= accepted_sources for item in _COMPONENTS):
        raise ValueError("component definitions require reviewed source provenance")

    nodes: dict[str, VehicleSystemsNode] = {}
    edges: dict[str, VehicleSystemsEdge] = {}

    def add_node(node_id: str, kind: VehicleSystemsNodeKind, label: str, component_id: str | None, source_ids: tuple[str, ...], authority: str = "knowledge_only") -> None:
        nodes.setdefault(node_id, VehicleSystemsNode(node_id=node_id, kind=kind, label=label, component_id=component_id, source_ids=source_ids, authority=authority))

    def add_edge(source: str, target: str, kind: VehicleSystemsEdgeKind, source_ids: tuple[str, ...], *, direction: str | None = None, authority: str = "engineering_expectation_only", interaction_type: str | None = None) -> None:
        digest = hashlib.sha256(f"{source}|{target}|{kind.value}|{direction}|{interaction_type}".encode()).hexdigest()[:20]
        edges.setdefault(digest, VehicleSystemsEdge(edge_id=f"vse:{digest}", source_node_id=source, target_node_id=target, kind=kind, direction=direction, interaction_type=interaction_type, source_ids=source_ids, authority=authority))

    for definition in _COMPONENTS:
        component_node = f"component:{definition.component_id}"
        add_node(component_node, VehicleSystemsNodeKind.COMPONENT, definition.label, definition.component_id, definition.source_ids)
        for property_id in definition.adjustable_property_ids:
            property_node = f"property:{definition.component_id}:{property_id}"
            add_node(property_node, VehicleSystemsNodeKind.COMPONENT_PROPERTY, property_id.replace("_", " ").title(), definition.component_id, definition.source_ids)
        for state_id in definition.expected_state_ids:
            state_node = f"state:{state_id}"
            add_node(state_node, VehicleSystemsNodeKind.VEHICLE_STATE, state_id.replace("_", " ").title(), definition.component_id, definition.source_ids)
            for property_id in definition.adjustable_property_ids:
                add_edge(f"property:{definition.component_id}:{property_id}", state_node, VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE, definition.source_ids)
            observation_node = f"observation:{definition.component_id}:{state_id}"
            add_node(observation_node, VehicleSystemsNodeKind.OBSERVATION, f"Qualified {state_id.replace('_', ' ')} observation", definition.component_id, definition.source_ids, "observation_only")
            add_edge(state_node, observation_node, VehicleSystemsEdgeKind.STATE_OBSERVABLE_BY, definition.source_ids)
        for symptom_id in definition.symptom_ids:
            symptom_node = f"symptom:{symptom_id}"
            add_node(symptom_node, VehicleSystemsNodeKind.SYMPTOM, symptom_id.replace("_", " ").title(), definition.component_id, definition.source_ids)
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
                add_node(context_node, VehicleSystemsNodeKind.CONTEXT, invariant, definition.component_id, definition.source_ids)
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

    # SetupArea and SetupEffect adapters preserve every Next Gen-applicable record as typed identities.
    next_gen_effects = [
        effect for effect in knowledge.setup_effects
        if "next_gen" not in effect.disabled_for
        and ("all" in effect.applies_to or "next_gen" in effect.applies_to)
    ]
    for effect in next_gen_effects:
        component_id = _component_for_area(effect.setup_area)
        sources = tuple(source for source in effect.source_ids if source in accepted_sources) or component_by_id[component_id].source_ids
        control_node = f"control:setup_area:{effect.setup_area}"
        add_node(control_node, VehicleSystemsNodeKind.CONTROL, effect.setup_area.replace("_", " ").title(), component_id, sources)
        property_node = f"property:{component_id}:{component_by_id[component_id].adjustable_property_ids[0]}"
        direction_text = effect.direction.casefold()
        direction = "decrease" if any(word in direction_text for word in ("reduce", "lower", "soften", "taller")) else "increase" if any(word in direction_text for word in ("add", "raise", "increase", "stiffen", "shorter")) else "bidirectional"
        add_edge(control_node, property_node, VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY, sources, direction=direction)
        state_node = f"state:effect:{effect.effect_id}"
        add_node(state_node, VehicleSystemsNodeKind.VEHICLE_STATE, effect.effect, component_id, sources)
        add_edge(property_node, state_node, VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE, sources, direction=direction)
        for phrase in effect.driver_phrase:
            symptom_node = f"symptom:effect:{_slug(phrase)}"
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
    sources = tuple(sorted({source for item in _COMPONENTS for source in item.source_ids}))
    return VehicleSystemsGraph(graph_version=_GRAPH_VERSION, components=_COMPONENTS, interactions=tuple(interactions), nodes=tuple(nodes.values()), edges=tuple(edges.values()), source_ids=sources)


@lru_cache(maxsize=1)
def _experiment_factors() -> tuple[SetupExperimentFactor, ...]:
    common_preconditions = ("P19 identifies one exact control target and authorizes the controlled test.", "Eligible A/B/A2 laps can hold context and driver line comparable.")
    return (
        SetupExperimentFactor(factor_id="factor:front_platform_height", component_id="platform", physical_property_id="front_platform_height", primary_controls=("lf_ride_height_mm",), coordinated_controls=("rf_ride_height_mm",), invariants_to_hold=("Hold LF-to-RF height split fixed.", "Recheck crossweight and leave unrelated controls unchanged."), preconditions=common_preconditions, expected_component_response=("Front chassis operating height moves by one sourced adjacent option.",), expected_vehicle_response=("Front clearance and platform response change in the target speed band.",), countereffects=("Bottoming, steering-demand growth, or an adverse balance shift." ,), success_metrics=("CFS clearance proxy", "front height distribution", "yaw response", "center phase time"), rollback_rule="Undo if clearance, stability, or a protected phase worsens.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:rear_platform_height", component_id="platform", physical_property_id="rear_platform_height", primary_controls=("lr_ride_height_mm",), coordinated_controls=("rr_ride_height_mm",), invariants_to_hold=("Hold LR-to-RR height split fixed.", "Recheck crossweight and leave unrelated controls unchanged."), preconditions=common_preconditions, expected_component_response=("Rear chassis operating height moves by one sourced adjacent option.",), expected_vehicle_response=("Rear platform and rake relationship change in the target speed band.",), countereffects=("Exit instability, bottoming, or an adverse high-speed balance shift.",), success_metrics=("rear height distribution", "rake proxy", "yaw response", "exit phase time"), rollback_rule="Undo if stability, clearance, or a protected phase worsens.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:rf_spring_rate", component_id="springs", physical_property_id="spring_rate", primary_controls=("rf_front_spring_n_per_mm",), automatic_sim_compensations=("The scoped 2026 Next Gen garage maintains configured ride height when spring rate changes.",), required_manual_compensations=("Recheck platform response and crossweight; automatic height maintenance is not response validation.",), invariants_to_hold=("Hold dampers, ARBs, alignment, pressures, and driver line fixed.",), preconditions=common_preconditions, expected_component_response=("RF travel/support response changes under comparable load.",), expected_vehicle_response=("Front platform and roll response may change in the target phase.",), countereffects=("Reduced bump compliance or worse sustained center balance.",), success_metrics=("RF travel response", "front roll response", "steering demand", "phase time"), rollback_rule="Undo if P19 rejects compliance, stability, or phase-time countereffects.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:crossweight", component_id="weight_distribution", physical_property_id="static_diagonal_relationship", primary_controls=("cross_weight_percent",), invariants_to_hold=("Hold ride height, spring rates, ARB preload, tire pressures, and driver line fixed.",), preconditions=common_preconditions, expected_component_response=("The recorded static diagonal relationship changes by one sourced adjacent option.",), expected_vehicle_response=("Entry stability, center rotation, or exit security may respond.",), countereffects=("A center gain may create unacceptable exit instability or braking response.",), success_metrics=("steering demand", "yaw response", "throttle pickup", "entry/center/exit phase time"), rollback_rule="Undo when P19 policy rejects any protected-phase countereffect.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:front_brake_distribution", component_id="brakes", physical_property_id="front_rear_pressure_distribution", primary_controls=("front_brake_bias_percent",), invariants_to_hold=("Hold braking point, pressure application, line, tires, and chassis setup fixed.",), preconditions=common_preconditions, expected_component_response=("Front/rear line-pressure distribution changes under comparable pedal input.",), expected_vehicle_response=("Braking stability or rotation response may change.",), countereffects=("Front lock, rear instability, or longer braking phase.",), success_metrics=("four line pressures", "lock/ABS evidence", "braking yaw response", "braking phase time"), rollback_rule="Undo if braking safety, stability, or time worsens.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:final_drive_ratio", component_id="final_drive", physical_property_id="final_drive_ratio", primary_controls=("rear_end_ratio",), invariants_to_hold=("Hold engine map, tires, line, shifts, weather, and traffic context fixed.",), preconditions=common_preconditions, expected_component_response=("RPM-to-speed relationship changes by one sourced legal option.",), expected_vehicle_response=("Acceleration and limiter headroom respond without implying horsepower.",), countereffects=("Limiter contact, extra shift, or reduced straight carry.",), success_metrics=("RPM headroom", "longitudinal acceleration", "exit/straight time"), rollback_rule="Undo if limiter, shift, or straight-time countereffects outweigh the target response.", source_ids=_GENERAL),
        SetupExperimentFactor(factor_id="factor:steering_ratio", component_id="steering", physical_property_id="steering_ratio", primary_controls=("steering_ratio",), invariants_to_hold=("Hold steering offset, alignment, FFB context, line, and chassis setup fixed.",), preconditions=common_preconditions, expected_component_response=("Rack travel per steering-wheel revolution changes by one sourced legal option.",), expected_vehicle_response=("Steering rate and workload context respond; offset remains a comfort control.",), countereffects=("Nervous response or greater correction workload.",), success_metrics=("steering rate", "yaw response lag", "correction workload", "phase time"), rollback_rule="Undo if workload or stability worsens.", source_ids=_GENERAL),
    )


def build_component_awareness(
    report: InternalIntelligenceReport,
    *,
    setup_snapshot: SetupSnapshot | None = None,
    car_path: str | None = None,
    runtime_identity: VehicleSystemsRuntimeIdentity | None = None,
) -> VehicleSystemsProjection:
    """Project immutable P20 observations and P19 outcomes without recomputation."""
    scoped_car_path = runtime_identity.car_path if runtime_identity is not None else car_path
    if scoped_car_path is not None and scoped_car_path.casefold() not in _NEXT_GEN.car_paths:
        raise ValueError(
            f"Vehicle Systems graph {_GRAPH_VERSION} is unavailable for car path {scoped_car_path}."
        )
    if runtime_identity is not None and car_path is not None and runtime_identity.car_path != car_path:
        raise ValueError("Vehicle Systems runtime identity does not match the requested car path.")
    graph = compile_vehicle_systems_graph()
    observations = tuple(
        item for item in (report.mechanism_observations.observations if report.mechanism_observations else ()) if item.qualified
    )
    authority = report.reasoning_snapshot.authority
    snapshot_payload = (
        report.reasoning_snapshot.model_dump(mode="json")
        if hasattr(report.reasoning_snapshot, "model_dump")
        else vars(report.reasoning_snapshot)
    )
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    setup_values: Mapping[str, Any] = setup_snapshot.model_dump() if setup_snapshot is not None else {}
    control_components = {
        key: definition.component_id
        for definition in graph.components
        for key in definition.setup_keys
    }
    states: list[ComponentAwarenessState] = []

    for definition in graph.components:
        relevant_observations = tuple(
            item for item in observations if definition.component_id in _MECHANISM_COMPONENTS.get(item.mechanism, ())
        )
        relevant_causes = []
        directly_related_cause_ids: set[str] = set()
        for cause in report.reasoning_snapshot.causes:
            related_controls = tuple(getattr(cause, "related_control_keys", ()))
            direct_components = {
                control_components[key] for key in related_controls if key in control_components
            }
            direct_components.update(
                control_components[outcome.control_key]
                for outcome in cause.controlled_outcomes
                if outcome.control_key in control_components
            )
            mechanism_components = set(
                _MECHANISM_KEY_COMPONENTS.get(str(getattr(cause, "mechanism_key", "")).casefold(), ())
            )
            if definition.component_id in direct_components | mechanism_components:
                relevant_causes.append(cause)
            if definition.component_id in direct_components:
                directly_related_cause_ids.add(str(getattr(cause, "cause_id", "unknown")))
        relevant_causes = tuple(relevant_causes)
        histories: list[ComponentControlledHistory] = []
        for cause in report.reasoning_snapshot.causes:
            for outcome in cause.controlled_outcomes:
                if outcome.control_key not in definition.setup_keys:
                    continue
                histories.append(ComponentControlledHistory(
                    workflow_id=outcome.workflow_id,
                    source_run_id=str(getattr(outcome, "source_run_id", None) or report.run_id),
                    control_key=outcome.control_key or "unknown",
                    phase=str(getattr(outcome, "phase", None) or "unscoped"),
                    mechanism_state=outcome.outcome,
                    control_response=outcome.control_direction_result or "unavailable",
                    policy_verdict=outcome.verdict,
                    countereffects=outcome.countereffects,
                ))
        settings = tuple(
            f"{SETUP_CONTROL_SPECS[key].label}: {format_setup_value(key, setup_values[key])}"
            for key in definition.setup_keys if setup_values.get(key) is not None
        )
        support_ids = tuple(dict.fromkeys(
            [item.artifact_id for item in relevant_observations]
            + [citation.citation_id for cause in relevant_causes for citation in cause.supporting_evidence]
        ))
        contradict_ids = tuple(dict.fromkeys(
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
        policy_blocked = any(history.policy_verdict == "undo" for history in histories)
        p19_authorized = bool(authority.setup_authorized and authority.control_key in definition.setup_keys)
        if policy_blocked:
            relevance = ComponentRelevance.BLOCKED
        elif histories:
            relevance = ComponentRelevance.TESTED
        elif contradict_ids and not support_ids:
            relevance = ComponentRelevance.CONTRADICTED
        elif any(
            cause.status == "likely"
            and str(getattr(cause, "cause_id", "unknown")) in directly_related_cause_ids
            for cause in relevant_causes
        ):
            relevance = ComponentRelevance.SUPPORTED
        elif relevant_observations or relevant_causes:
            relevance = ComponentRelevance.CANDIDATE
        else:
            relevance = ComponentRelevance.IRRELEVANT

        observability: list[ComponentObservabilityState] = [ComponentObservabilityState.DEFINITION_KNOWN]
        if settings:
            observability.append(ComponentObservabilityState.SETUP_CAPTURED)
        if definition.observability.live_telemetry_channels:
            observability.append(ComponentObservabilityState.LIVE_RESPONSE_OBSERVABLE)
        if relevant_observations:
            observability.append(ComponentObservabilityState.CURRENT_RESPONSE_OBSERVED)
        if relevance is ComponentRelevance.SUPPORTED:
            observability.append(ComponentObservabilityState.MECHANISM_SUPPORTED)
        if histories:
            observability.append(ComponentObservabilityState.CONTROLLED_RESPONSE_KNOWN)
            observability.append(ComponentObservabilityState.EXACT_CONTEXT_POLICY_KNOWN)

        primary = relevant_observations[0] if relevant_observations else None
        states.append(ComponentAwarenessState(
            component_id=definition.component_id,
            run_id=report.run_id,
            lap_number=primary.lap_number if primary else None,
            phase=primary.phase if primary else None,
            lap_pct_start=primary.lap_pct_start if primary else None,
            lap_pct_end=primary.lap_pct_end if primary else None,
            current_settings=settings,
            current_setting_provenance=((f"setup_snapshot:{setup_snapshot.setup_id}",) if settings and setup_snapshot is not None else ()),
            observability_states=tuple(observability),
            current_response_state="observed" if relevant_observations else "unavailable",
            relevance=relevance,
            supporting_artifact_ids=support_ids,
            contradicting_artifact_ids=contradict_ids,
            supporting_cause_ids=supporting_cause_ids,
            contradicting_cause_ids=contradicting_cause_ids,
            confounders=definition.confounders,
            unavailable_quantities=definition.observability.unavailable_quantities,
            measurement_requirements=definition.measurement_requirements,
            coupled_component_ids=definition.coupled_component_ids,
            controlled_history=tuple(histories),
            current_testability="p19_authorized" if p19_authorized else "policy_blocked" if policy_blocked else "measurement_only",
            authority_state="p19_authorized" if p19_authorized else "controlled_history" if histories else "observation_only" if support_ids or contradict_ids else "knowledge_only",
            evidence_states=tuple(dict.fromkeys(item.evidence_state for item in relevant_observations)),
            blocker_reasons=("Exact controlled history contains an Undo policy; generic component knowledge cannot reopen it.",) if policy_blocked else (),
            setup_authorized=p19_authorized,
        ))

    rank = {ComponentRelevance.SUPPORTED: 0, ComponentRelevance.TESTED: 1, ComponentRelevance.CANDIDATE: 2, ComponentRelevance.CONTRADICTED: 3, ComponentRelevance.BLOCKED: 4, ComponentRelevance.IRRELEVANT: 5}
    ordered = sorted(states, key=lambda item: (rank[item.relevance], -len(item.supporting_artifact_ids), item.component_id))
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
    next_discriminator = (
        report.best_measurement.instruction
        if not report.best_measurement.setup_authorized
        else f"P19 authorized the exact {authority.control_key} controlled factor; preserve its experiment invariants."
    )
    leading_component_ids = tuple(
        item.component_id for item in ordered
        if item.relevance == (leading.relevance if leading is not None else ComponentRelevance.IRRELEVANT)
    ) if leading is not None else ()
    strongest_contradiction = next(
        (
            citation.summary
            for cause in report.reasoning_snapshot.causes
            for citation in cause.contradicting_evidence
        ),
        "No qualified contradiction is present in the exact reasoning snapshot.",
    )
    runtime_nodes: dict[str, VehicleSystemsNode] = {}
    runtime_edges: list[VehicleSystemsEdge] = []
    for observation in observations:
        observation_id = f"runtime:observation:{observation.artifact_id}"
        state_id = f"runtime:state:{observation.mechanism.value}"
        runtime_nodes.setdefault(observation_id, VehicleSystemsNode(
            node_id=observation_id, kind=VehicleSystemsNodeKind.OBSERVATION,
            label=str(getattr(observation, "summary", observation.mechanism.value)),
            source_ids=(observation.artifact_id,), authority="observation_only",
        ))
        runtime_nodes.setdefault(state_id, VehicleSystemsNode(
            node_id=state_id, kind=VehicleSystemsNodeKind.VEHICLE_STATE,
            label=observation.mechanism.value.replace("_", " ").title(),
            source_ids=(observation.artifact_id,), authority="observation_only",
        ))
        runtime_edges.append(VehicleSystemsEdge(
            edge_id=f"runtime-edge:{hashlib.sha256(f'{observation_id}|{state_id}'.encode()).hexdigest()[:20]}",
            source_node_id=observation_id, target_node_id=state_id,
            kind=VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE,
            direction="observed", source_ids=(observation.artifact_id,), authority="observation_only",
        ))
    for component_state in states:
        for history in component_state.controlled_history:
            control_id = f"runtime:control:{history.control_key}"
            outcome_id = f"runtime:outcome:{history.workflow_id}:{history.control_key}"
            runtime_nodes.setdefault(control_id, VehicleSystemsNode(
                node_id=control_id, kind=VehicleSystemsNodeKind.CONTROL,
                label=SETUP_CONTROL_SPECS[history.control_key].label,
                component_id=component_state.component_id, source_ids=(history.workflow_id,),
                authority="controlled_history",
            ))
            runtime_nodes.setdefault(outcome_id, VehicleSystemsNode(
                node_id=outcome_id, kind=VehicleSystemsNodeKind.OUTCOME,
                label=f"{history.control_response}; {history.policy_verdict}",
                component_id=component_state.component_id, source_ids=(history.workflow_id,),
                authority="controlled_history",
            ))
            runtime_edges.append(VehicleSystemsEdge(
                edge_id=f"runtime-edge:{hashlib.sha256(f'{control_id}|{outcome_id}'.encode()).hexdigest()[:20]}",
                source_node_id=control_id, target_node_id=outcome_id,
                kind=VehicleSystemsEdgeKind.CONTROLLED_TEST_OBSERVED_RESPONSE,
                direction="observed", source_ids=(history.workflow_id,), authority="controlled_history",
            ))
            if history.policy_verdict == "undo":
                policy_id = f"runtime:outcome:policy:{history.workflow_id}:{history.control_key}"
                runtime_nodes.setdefault(policy_id, VehicleSystemsNode(
                    node_id=policy_id, kind=VehicleSystemsNodeKind.OUTCOME,
                    label="Undo preserved after unacceptable countereffect or missed target",
                    component_id=component_state.component_id, source_ids=(history.workflow_id,),
                    authority="controlled_history",
                ))
                runtime_edges.append(VehicleSystemsEdge(
                    edge_id=f"runtime-edge:{hashlib.sha256(f'{outcome_id}|{policy_id}'.encode()).hexdigest()[:20]}",
                    source_node_id=outcome_id, target_node_id=policy_id,
                    kind=VehicleSystemsEdgeKind.POLICY_REJECTED_DUE_TO_COUNTEREFFECT,
                    direction="observed", source_ids=(history.workflow_id,), authority="controlled_history",
                ))
    runtime_graph = VehicleSystemsRuntimeGraph(
        reasoning_snapshot_sha256=snapshot_hash,
        nodes=tuple(runtime_nodes.values()), edges=tuple(runtime_edges),
    )
    return VehicleSystemsProjection(
        run_id=report.run_id,
        graph_version=graph.graph_version,
        reasoning_snapshot_sha256=snapshot_hash,
        runtime_identity=runtime_identity,
        version_scope_state="verified" if runtime_identity is not None else "unavailable",
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


def inspect_component(component_id: str, projection: VehicleSystemsProjection | None = None) -> ComponentInspectionResponse:
    graph = compile_vehicle_systems_graph()
    definition = next((item for item in graph.components if item.component_id == component_id), None)
    if definition is None:
        raise ValueError(f"Unknown vehicle-system component: {component_id}")
    state = next((item for item in projection.component_states if item.component_id == component_id), None) if projection else None
    return ComponentInspectionResponse(definition=definition, state=state, interactions=tuple(item for item in graph.interactions if component_id in {item.source_component_id, item.target_component_id}), controls=definition.setup_keys)


def trace_control_mechanism(control_key: str) -> tuple[VehicleSystemsEdge, ...]:
    graph = compile_vehicle_systems_graph()
    if control_key not in SETUP_CONTROL_SPECS:
        raise ValueError(f"Unknown setup control: {control_key}")
    start = f"control:{control_key}"
    property_ids = {edge.target_node_id for edge in graph.edges if edge.source_node_id == start and edge.kind is VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY}
    state_ids = {edge.target_node_id for edge in graph.edges if edge.source_node_id in property_ids and edge.kind is VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE}
    return tuple(edge for edge in graph.edges if edge.source_node_id == start or edge.source_node_id in property_ids or edge.source_node_id in state_ids)


__all__ = ["build_component_awareness", "compile_vehicle_systems_graph", "inspect_component", "trace_control_mechanism", "vehicle_systems_runtime_identity"]
