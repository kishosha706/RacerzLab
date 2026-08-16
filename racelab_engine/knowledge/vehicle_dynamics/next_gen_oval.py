"""Reviewed, version-bound NASCAR Next Gen oval vehicle-dynamics artifact."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

from racelab_engine.analysis.channel_registry import RAW_TO_CANONICAL
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.vehicle_dynamics_knowledge import (
    ChassisResponseState,
    ComponentInfluence,
    DriverVehicleResponseChain,
    DynamicObservationContract,
    DynamicResponseRegime,
    DynamicsChainStageKind,
    ExternalIdentityNamespace,
    ForbiddenVehicleControl,
    KnowledgeSourceTier,
    LoadPath,
    MechanismInteraction,
    OvalTrackDemandModel,
    QuantitySemantics,
    StaticLoadDistributionKnowledge,
    SteadyStateResponse,
    TireDemandLevel,
    TireDemandState,
    TireStateEvolution,
    TransientResponse,
    VehicleDynamicDefinition,
    VehicleDynamicMechanism,
    VehicleDynamicQuantity,
    VehicleDynamicsApplicability,
    VehicleDynamicsEdgeKind,
    VehicleDynamicsGraphEdge,
    VehicleDynamicsGraphNode,
    VehicleDynamicsKnowledgeGraph,
    VehicleDynamicsKnowledgeResolution,
    VehicleDynamicsInspectionToolId,
    VehicleDynamicsNodeKind,
    VehicleDynamicsPhase,
    VehicleDynamicsRuntimeMechanismTrust,
    VehicleDynamicsRuntimeChannelAlternative,
    VehicleDynamicsRuntimeChannelRequirement,
    VehicleDynamicsRuntimeTrustManifest,
    VehicleDynamicsSource,
    build_vehicle_dynamics_knowledge_graph,
    build_vehicle_dynamics_runtime_trust_manifest,
)
from racelab_engine.models.performance_intelligence import TimeOriginKind


_KNOWLEDGE_VERSION = "2026.08.p35-next-gen-oval.v1"
_APP = VehicleDynamicsApplicability(
    applicability_id="applicability:next_gen_oval:2026_s2_s3p2",
    car_paths=(
        "stockcars chevycamarozl12022",
        "stockcars fordmustang2022",
        "stockcars toyotacamry2022",
    ),
    car_version_min="2026.06.08.02",
    car_version_max="2026.06.08.02",
    iracing_build_min="2026.03.09.03",
    iracing_build_max="2026.06.24.02",
    track_packages=("oval", "short_oval", "intermediate_oval", "superspeedway_oval"),
    knowledge_version=_KNOWLEDGE_VERSION,
    source_version="reviewed-offline-synthesis-2026-08-15",
)

_UNAVAILABLE = (
    "quantity:exact_tire_force",
    "quantity:exact_wheel_load",
    "quantity:exact_spring_force",
    "quantity:exact_damper_force",
    "quantity:exact_arb_torque",
    "quantity:exact_aerodynamic_downforce",
    "quantity:exact_aerodynamic_balance",
    "quantity:exact_aerodynamic_drag_force",
    "quantity:exact_drag_coefficient",
    "quantity:exact_differential_torque",
    "quantity:exact_contact_patch_distribution",
    "quantity:exact_friction_coefficient",
)

_COMMON_DRIVER_CONFOUNDERS = (
    "brake, steering, throttle, line, or correction timing changed",
    "driver demand is missing or not co-observed in the same physical window",
)
_COMMON_CONTEXT_CONFOUNDERS = (
    "traffic, damage, tire, fuel, weather, or setup context is not comparable",
    "lap is junk, partial, pit-road, out-lap, cooldown, wreck, or invalid-speed",
)

_EXTERNAL_IDENTITY_NAMESPACES = (
    ExternalIdentityNamespace(
        namespace_id="telemetry_channel",
        field_names=(
            "required_measured_channels",
            "manifest_validity_required_channels",
        ),
        owner="verified telemetry manifest and P20 observation producers",
        registry_mode="runtime_manifest_bound",
        policy="Canonical channel IDs are external and become usable only when the exact runtime manifest and producer evidence bind them.",
    ),
    ExternalIdentityNamespace(
        namespace_id="p20_mechanism",
        field_names=("p20_mechanism_ids",),
        owner="P20 Engineering State Awareness",
        registry_mode="closed_registry",
        allowed_ids=(
            "driver_execution", "braking_response", "corner_rotation", "tire_state",
            "damper_response", "platform_response", "resistance_scrub_like",
            "powertrain_response", "stint_trend", "sim_integrity",
        ),
        policy="P35 expectations may bridge only to the frozen P20 observation-family vocabulary; they never become observations.",
    ),
    ExternalIdentityNamespace(
        namespace_id="p26_component_family",
        field_names=("relevant_component_ids", "p26_component_family_ids", "component_id"),
        owner="P26 Vehicle Systems Intelligence",
        registry_mode="closed_registry",
        allowed_ids=(
            "tires", "alignment", "springs", "dampers", "anti_roll_bars",
            "weight_distribution", "platform", "brakes", "differential",
            "final_drive", "steering", "cooling_configuration",
        ),
        policy="P35 maps candidate mechanisms to P26 component families without creating current component relevance or cause.",
    ),
    ExternalIdentityNamespace(
        namespace_id="p32_performance_mechanism",
        field_names=("p32_performance_mechanism_ids", "performance_dimension_id"),
        owner="P32 Lap-Time Mechanics and Speed Intelligence",
        registry_mode="closed_registry",
        allowed_ids=(
            "braking_realization", "brake_release_transition", "turn_in_response",
            "entry_rotation", "center_rotation", "speed_retention",
            "throttle_realization", "exit_traction", "exit_carry",
            "straight_acceleration", "gearing_headroom", "path_efficiency",
            "stability_workload", "tire_state_migration", "platform_consistency",
            "disturbance_compliance", "traffic_robustness",
        ),
        policy="P35 bridges to measured P32 dimensions and time-origin kinds; it does not duplicate P32 performance definitions.",
    ),
)


def _source(
    source_id: str,
    tier: KnowledgeSourceTier,
    publisher: str,
    title: str,
    source_version: str,
    source_uri: str,
    reviewed_claims: tuple[str, ...],
    publication_date: str | None,
) -> VehicleDynamicsSource:
    return VehicleDynamicsSource(
        source_id=source_id,
        tier=tier,
        publisher=publisher,
        title=title,
        source_version=source_version,
        publication_date=publication_date,
        reviewed_at="2026-08-15",
        source_uri=source_uri,
        local_digest=canonical_json_sha256(
            {
                "source_id": source_id,
                "source_version": source_version,
                "reviewed_claims": reviewed_claims,
                "reviewed_at": "2026-08-15",
            }
        ),
    )


_SOURCES = (
    _source(
        "iracing_next_gen_manual_v2",
        KnowledgeSourceTier.OFFICIAL_IRACING,
        "iRacing",
        "NASCAR Next Gen Cars Manual V2",
        "v2",
        "https://s100.iracing.com/wp-content/uploads/2024/03/NASCAR-NextGen-Cars-Manual-V2.pdf",
        (
            "Reviewed garage controls and component relationships on pages 11-17.",
            "Spring, damper, alignment, crossweight, anti-roll-bar, differential, and final-drive statements remain expectation-only.",
        ),
        None,
    ),
    _source(
        "iracing_shock_tuning_guide_2021_08",
        KnowledgeSourceTier.OFFICIAL_IRACING,
        "iRacing",
        "Shock Tuning User Guide",
        "2021-08",
        "https://s100.iracing.com/wp-content/uploads/2021/08/Shock-Tuning-User-Guide.pdf",
        (
            "Reviewed low/high-speed compression and rebound as shaft-velocity regimes.",
            "Damper knowledge requires transient shaft-motion evidence and cannot establish settled center balance alone.",
        ),
        None,
    ),
    _source(
        "iracing_2026_s2_initial_2026_03_09_03",
        KnowledgeSourceTier.OFFICIAL_IRACING,
        "iRacing",
        "2026 Season 2 Initial Release Notes",
        "2026.03.09.03",
        "https://support.iracing.com/support/solutions/articles/31000178217-2026-season-2-initial-release-notes-2026-03-09-03-",
        (
            "Reviewed Next Gen superspeedway package update and 2026 rear-window package.",
            "Reviewed final-drive guidance and automatic ride-height maintenance after spring changes.",
        ),
        "2026-03-09",
    ),
    _source(
        "iracing_2026_s3_initial_2026_06_09_01",
        KnowledgeSourceTier.OFFICIAL_IRACING,
        "iRacing",
        "2026 Season 3 Initial Release Notes",
        "2026.06.09.01",
        "https://support.iracing.com/support/solutions/articles/31000179016-2026-season-3-initial-release-notes-2026-06-09-01-",
        ("Reviewed Cup Gen 7 setup refresh with no documented class physics change.",),
        "2026-06-09",
    ),
    _source(
        "iracing_2026_s3_patch2_2026_06_24_02",
        KnowledgeSourceTier.OFFICIAL_IRACING,
        "iRacing",
        "2026 Season 3 Patch 2 Release Notes",
        "2026.06.24.02",
        "https://support.iracing.com/support/solutions/articles/31000179073-2026-season-3-patch-2-release-notes-2026-06-24-02-",
        ("Reviewed through the current build; no Cup Gen 7 physics change is documented.",),
        "2026-06-24",
    ),
    _source(
        "nascar_next_gen_architecture_2021_05_05",
        KnowledgeSourceTier.OFFICIAL_NASCAR,
        "NASCAR",
        "NASCAR, manufacturers unveil Next Gen models for 2022",
        "2021-05-05",
        "https://www.nascar.com/news-media/2021/05/05/stock-reborn-nascar-manufacturers-unveil-next-gen-models-for-2022-cup-series/",
        (
            "Reviewed independent rear suspension replacing the solid axle and removal of the track bar.",
            "Reviewed rack-and-pinion steering, larger brakes, 18-inch wheels, wider tires, and sequential transaxle architecture.",
        ),
        "2021-05-05",
    ),
    _source(
        "nascar_next_gen_overview_pdf_2021",
        KnowledgeSourceTier.OFFICIAL_NASCAR,
        "NASCAR",
        "Next Gen Overview",
        "2021",
        "https://media.ndms.nascar.com/nascar/2021/NextGen/NextGen-Overview.pdf",
        (
            "Reviewed IRS, rack steering, larger brakes, transaxle, sealed underwing/diffuser, and wider 18-inch tire architecture.",
        ),
        None,
    ),
    _source(
        "nascar_next_gen_irs_camber_2022_05_17",
        KnowledgeSourceTier.OFFICIAL_NASCAR,
        "NASCAR",
        "Next Gen analysis: tire pressure, rear loading and dynamic camber at Kansas",
        "2022-05-17",
        "https://www.nascar.com/news-media/2022/05/17/next-gen-analysis-overtightening-lug-nuts-tire-pressure-battles-and-more-at-kansas/",
        (
            "Reviewed event-specific LR loading context and dynamic rear camber enabled by IRS.",
            "Event observations are not universal exact-load rules.",
        ),
        "2022-05-17",
    ),
    _source(
        "nascar_next_gen_suspension_config_2022_03_23",
        KnowledgeSourceTier.OFFICIAL_NASCAR,
        "NASCAR",
        "Next Gen analysis: suspension configuration and camber",
        "2022-03-23",
        "https://www.nascar.com/news-media/2022/03/23/next-gen-analysis-how-new-features-impact-flexibility-of-road-course-setups/",
        (
            "Reviewed independent rear control-arm, toe-link, upright, camber, and abutment-plate architecture.",
            "Road-course configuration details are not transferred into oval setup directions.",
        ),
        "2022-03-23",
    ),
    _source(
        "sae_2011_01_0094_combined_tire_demand",
        KnowledgeSourceTier.PEER_REVIEWED,
        "SAE International",
        "Tire Force Ellipse (Friction Ellipse) and Tire Characteristics",
        "SAE 2011-01-0094",
        "https://saemobilus.sae.org/papers/tire-force-ellipse-friction-ellipse-tire-characteristics-2011-01-0094",
        (
            "Reviewed friction ellipse as qualitative combined braking/steering knowledge.",
            "A circle or ellipse is not an adequate quantitative tire-force model without validated nonlinear tire data.",
        ),
        None,
    ),
    _source(
        "sae_2000_01_3570_banked_track_demand",
        KnowledgeSourceTier.PEER_REVIEWED,
        "SAE International",
        "Sensitivity of Cornering Speeds to Banking and Aerodynamics",
        "SAE 2000-01-3570",
        "https://saemobilus.sae.org/papers/sensitivity-cornering-speeds-banking-aerodynamics-2000-01-3570",
        (
            "Reviewed banked-track demand as a multi-parameter vehicle-model problem.",
            "Banking alone cannot produce exact wheel loads.",
        ),
        None,
    ),
    _source(
        "sae_962531_suspension_asymmetry",
        KnowledgeSourceTier.PEER_REVIEWED,
        "SAE International",
        "Effects of Suspension Geometry and Stiffness Asymmetries on Wheel Loads",
        "SAE 962531",
        "https://saemobilus.sae.org/papers/effects-suspension-geometry-stiffness-asymmetries-wheel-loads-steady-cornering-a-winston-cup-car-962531",
        (
            "Reviewed wheel loading as dependent on validated geometry, stiffness, and operating state.",
            "Static crossweight is not dynamic wheel load.",
        ),
        None,
    ),
    _source(
        "racerzlab_vehicle_dynamics_synthesis_v1",
        KnowledgeSourceTier.REVIEWED_SYNTHESIS,
        "RacerZLab",
        "P35 Next Gen Oval Vehicle Dynamics Reviewed Synthesis",
        "2026.08.v1",
        "repo://racelab_engine/knowledge/vehicle_dynamics/next_gen_oval.py",
        (
            "Reviewed qualitative load transfer, load paths, roll couple, driver-demand, and mechanism-discriminator vocabulary.",
            "All exact unavailable physics, observation, causal, component, and setup authority remain locked.",
        ),
        "2026-08-15",
    ),
)

_SRC_SYNTH = ("racerzlab_vehicle_dynamics_synthesis_v1",)
_SRC_MANUAL = ("iracing_next_gen_manual_v2", *_SRC_SYNTH)
_SRC_DAMPER = ("iracing_shock_tuning_guide_2021_08", *_SRC_MANUAL)
_SRC_ARCH = (
    "nascar_next_gen_architecture_2021_05_05",
    "nascar_next_gen_overview_pdf_2021",
    "nascar_next_gen_suspension_config_2022_03_23",
    "nascar_next_gen_irs_camber_2022_05_17",
    *_SRC_SYNTH,
)
_SRC_PACKAGE = (
    "iracing_2026_s2_initial_2026_03_09_03",
    "iracing_2026_s3_initial_2026_06_09_01",
    "iracing_2026_s3_patch2_2026_06_24_02",
    *_SRC_SYNTH,
)


def _base(
    definition_id: str,
    label: str,
    physical_meaning: str,
    *,
    units: str | None = None,
    created_by: tuple[str, ...] = ("context:driver_input",),
    affected_by: tuple[str, ...] = ("context:track_geometry",),
    affects: tuple[str, ...] = ("performance:measured_elapsed_time",),
    channels: tuple[str, ...] = (),
    derived: tuple[str, ...] = (),
    proxies: tuple[str, ...] = (),
    phases: tuple[VehicleDynamicsPhase, ...] = tuple(VehicleDynamicsPhase),
    components: tuple[str, ...] = ("tires",),
    sources: tuple[str, ...] = _SRC_SYNTH,
    forbidden: tuple[str, ...] = ("Generic knowledge establishes current cause.",),
) -> dict[str, Any]:
    return {
        "definition_id": definition_id,
        "label": label,
        "physical_meaning": physical_meaning,
        "units": units,
        "created_by_ids": created_by,
        "affected_by_ids": affected_by,
        "affects_ids": affects,
        "required_measured_channels": channels,
        "derived_quantity_ids": derived,
        "valid_proxy_ids": proxies,
        "unavailable_quantity_ids": _UNAVAILABLE,
        "driver_confounders": _COMMON_DRIVER_CONFOUNDERS,
        "track_context_confounders": _COMMON_CONTEXT_CONFOUNDERS,
        "relevant_phases": phases,
        "relevant_component_ids": components,
        "source_ids": sources,
        "applicability": _APP,
        "forbidden_inferences": forbidden,
    }


def _quantity(
    quantity_id: str,
    label: str,
    meaning: str,
    semantics: QuantitySemantics,
    units: str | None = None,
    channels: tuple[str, ...] = (),
    components: tuple[str, ...] = ("tires",),
    phases: tuple[VehicleDynamicsPhase, ...] = tuple(VehicleDynamicsPhase),
    sources: tuple[str, ...] = _SRC_SYNTH,
    exact: bool = False,
    manifest_validity_required_channels: tuple[str, ...] = (),
) -> VehicleDynamicQuantity:
    publishable = semantics is not QuantitySemantics.UNAVAILABLE
    return VehicleDynamicQuantity(
        **_base(
            quantity_id,
            label,
            meaning,
            units=units,
            channels=channels,
            components=components,
            phases=phases,
            sources=sources,
            forbidden=(
                "This quantity establishes an unavailable force, load, torque, coefficient, contact-patch distribution, or setup cause.",
            ),
        ),
        semantics=semantics,
        runtime_publishable=publishable,
        exact_value_authorized=exact,
        manifest_validity_required_channels=manifest_validity_required_channels,
    )


def _quantities() -> tuple[VehicleDynamicQuantity, ...]:
    measured_specs = (
        ("quantity:steering_input", "Steering input", "Driver steering-wheel demand.", QuantitySemantics.MEASURED_NUMERIC, "deg", ("steering_wheel_angle",), ("steering", "tires")),
        ("quantity:brake_input", "Brake input", "Driver brake demand.", QuantitySemantics.MEASURED_NUMERIC, "%", ("brake_01",), ("brakes", "tires")),
        ("quantity:front_brake_line_pressure_state", "Front brake line-pressure state", "Observed left/right front hydraulic line pressure; this is not brake torque, tire force, or a setup-cause claim.", QuantitySemantics.DERIVED_NUMERIC, "bar", ("lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar"), ("brakes", "tires")),
        ("quantity:rear_brake_line_pressure_state", "Rear brake line-pressure state", "Observed left/right rear hydraulic line pressure; this is not brake torque, tire force, or a setup-cause claim.", QuantitySemantics.DERIVED_NUMERIC, "bar", ("lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar"), ("brakes", "tires")),
        ("quantity:relative_front_rear_brake_pressure_distribution", "Relative front/rear brake pressure distribution", "Observed front-versus-rear line-pressure relationship in one exact braking window; it does not reconstruct pad force, tire force, or universal brake balance.", QuantitySemantics.RELATIVE_STATE, "% observed pressure share", ("lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar", "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar"), ("brakes", "tires", "weight_distribution")),
        ("quantity:wheel_lock_evidence_state", "Wheel-lock evidence state", "Brake-pressure and individual-wheel-speed evidence may identify a lock-like response only after vehicle speed, corner geometry, and sensor validity are separated; it is not exact available grip.", QuantitySemantics.QUALITATIVE_PROXY, None, ("lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar", "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar", "lf_speed", "rf_speed", "lr_speed", "rr_speed", "speed_mph"), ("brakes", "tires")),
        ("quantity:throttle_input", "Throttle input", "Driver accelerator demand.", QuantitySemantics.MEASURED_NUMERIC, "%", ("throttle",), ("differential", "final_drive", "tires")),
        ("quantity:vehicle_speed", "Vehicle speed", "Measured speed at physical track position.", QuantitySemantics.MEASURED_NUMERIC, "m/s", ("speed_mph",), ("tires", "platform", "final_drive")),
        ("quantity:yaw_rate", "Yaw rate", "Measured body yaw response.", QuantitySemantics.MEASURED_NUMERIC, "rad/s", ("yaw_rate",), ("tires", "steering")),
        ("quantity:lateral_acceleration", "Lateral acceleration", "Measured lateral vehicle response.", QuantitySemantics.MEASURED_NUMERIC, "m/s^2", ("lat_accel",), ("tires",)),
        ("quantity:longitudinal_acceleration", "Longitudinal acceleration", "Measured acceleration or deceleration response.", QuantitySemantics.MEASURED_NUMERIC, "m/s^2", ("long_accel",), ("tires", "brakes", "final_drive")),
        ("quantity:vertical_acceleration", "Vertical acceleration", "Measured vertical disturbance response after gravity-baseline removal.", QuantitySemantics.MEASURED_NUMERIC, "m/s^2", ("vert_accel",), ("springs", "dampers", "platform")),
        ("quantity:shock_displacement", "Shock displacement", "Four-corner suspension travel observation.", QuantitySemantics.MEASURED_NUMERIC, "m", ("lf_shock_deflection", "rf_shock_deflection", "lr_shock_deflection", "rr_shock_deflection"), ("springs", "dampers", "anti_roll_bars")),
        ("quantity:shock_velocity", "Shock velocity", "Four-corner suspension shaft velocity observation.", QuantitySemantics.MEASURED_NUMERIC, "m/s", ("lf_shock_velocity", "rf_shock_velocity", "lr_shock_velocity", "rr_shock_velocity"), ("dampers",)),
        ("quantity:ride_height_state", "Ride-height state", "Measured or derived four-corner platform height state.", QuantitySemantics.RELATIVE_STATE, "m", ("lf_ride_height", "rf_ride_height", "lr_ride_height", "rr_ride_height", "cfs_ride_height"), ("platform",)),
        ("quantity:rear_wheel_speed_relationship", "Rear wheel-speed relationship", "Geometry-contaminated rear wheel-speed relationship used only as a proxy.", QuantitySemantics.QUALITATIVE_PROXY, None, ("lr_wheel_speed", "rr_wheel_speed"), ("differential", "tires")),
        ("quantity:rpm", "Engine RPM", "Measured engine-speed state.", QuantitySemantics.MEASURED_NUMERIC, "rpm", ("rpm",), ("final_drive",)),
        ("quantity:gear", "Selected gear", "Measured selected transmission gear.", QuantitySemantics.MEASURED_NUMERIC, "index", ("gear",), ("final_drive",)),
        ("quantity:tire_pressure_state", "Tire pressure state", "Available tire-pressure state or snapshot in exact context.", QuantitySemantics.RELATIVE_STATE, "kPa", ("lf_cold_pressure", "rf_cold_pressure", "lr_cold_pressure", "rr_cold_pressure"), ("tires",)),
        ("quantity:tire_temperature_state", "Tire temperature state", "Available relative tire-temperature state in exact context.", QuantitySemantics.RELATIVE_STATE, "degC", ("lf_surface_temp_m", "rf_surface_temp_m", "lr_surface_temp_m", "rr_surface_temp_m"), ("tires", "alignment")),
        ("quantity:tire_wear_state", "Tire wear state", "Available relative wear snapshot or migration state.", QuantitySemantics.RELATIVE_STATE, "%", ("lf_tread_remaining", "rf_tread_remaining", "lr_tread_remaining", "rr_tread_remaining"), ("tires",)),
        ("quantity:elapsed_time_difference", "Elapsed-time difference", "Measured signed time difference over qualified physical scope.", QuantitySemantics.DERIVED_NUMERIC, "s", ("session_time", "speed_mph"), ("tires", "platform", "brakes", "final_drive")),
        ("quantity:static_crossweight_percent", "Static crossweight", "Garage static diagonal load-distribution percentage; not live wheel load.", QuantitySemantics.MEASURED_NUMERIC, "%", ("cross_weight_percent",), ("weight_distribution",)),
        ("quantity:static_nose_weight_percent", "Static nose weight", "Garage static front weight-distribution percentage.", QuantitySemantics.MEASURED_NUMERIC, "%", ("nose_weight_percent",), ("weight_distribution",)),
    )
    result = [
        _quantity(*spec, exact=spec[3] in {QuantitySemantics.MEASURED_NUMERIC, QuantitySemantics.DERIVED_NUMERIC})
        for spec in measured_specs
    ]
    result.append(
        _quantity(
            "quantity:abs_intervention_state",
            "ABS intervention state",
            "Observed ABS active/cut state is usable only when the exact runtime telemetry manifest explicitly declares both ABS channels valid; missing, unsupported, or unknown validity remains unavailable and never implies ABS-equipped behavior.",
            QuantitySemantics.QUALITATIVE_PROXY,
            units=None,
            channels=("brake_abs_active", "brake_abs_cut_01"),
            components=("brakes", "tires"),
            manifest_validity_required_channels=(
                "brake_abs_active",
                "brake_abs_cut_01",
            ),
        )
    )
    relative_specs = (
        ("quantity:longitudinal_demand", "Longitudinal demand", "Relative braking or acceleration demand inferred from matched input/response."),
        ("quantity:lateral_demand", "Lateral demand", "Relative turning demand inferred from steering, curvature, speed, and response."),
        ("quantity:combined_tire_demand", "Combined tire demand", "Qualitative overlap of longitudinal and lateral tire demand."),
        ("quantity:sustained_lateral_demand", "Sustained lateral demand", "Relative center-phase demand after transient settling."),
        ("quantity:rear_combined_demand", "Rear combined demand", "Relative rear lateral-plus-power demand during pickup and exit."),
        ("quantity:exit_speed", "Exit speed carry", "Measured exit speed handed into the following straight."),
        ("quantity:steering_demand_growth", "Steering-demand growth", "Relative increase in steering demand over matched laps or a sustained window."),
        ("quantity:yaw_response_change", "Yaw-response change", "Relative yaw response at matched steering, speed, line, and context."),
        ("quantity:tire_slip_exposure", "Tire slip exposure", "Proxy exposure to speed disagreement or steering/yaw mismatch; not tire force."),
        ("quantity:platform_migration", "Platform migration", "Relative pitch, roll, heave, or ride-height change over a phase."),
        ("quantity:relative_longitudinal_load_transfer", "Relative longitudinal load transfer", "Conceptual forward/rearward dynamic tire-loading migration under braking or acceleration; not exact wheel load."),
        ("quantity:relative_lateral_load_transfer", "Relative lateral load transfer", "Conceptual left/right dynamic tire-loading migration under cornering; not exact wheel load."),
        ("quantity:relative_diagonal_loading", "Relative diagonal loading", "Conceptual diagonal dynamic loading relationship; distinct from static crossweight."),
        ("quantity:relative_roll_load_transfer", "Relative roll load transfer", "Conceptual roll-related redistribution supported by tires, springs, bars, and platform constraints."),
        ("quantity:relative_pitch_load_transfer", "Relative pitch load transfer", "Conceptual pitch-related redistribution during braking, release, and acceleration."),
        ("quantity:front_rear_roll_couple", "Front/rear roll-couple relationship", "Qualitative front-versus-rear roll-support relationship; no exact bar torque or wheel loads."),
        ("quantity:relative_load_sensitivity_regime", "Relative tire load-sensitivity regime", "Qualitative knowledge that tire capability does not scale linearly with vertical load; no exact tire-force curve."),
        ("quantity:spring_force_displacement_relationship", "Spring force/displacement relationship", "Spring rate describes force change with displacement and shapes support/compliance; exact live spring force remains unavailable."),
        ("quantity:damper_force_velocity_relationship", "Damper force/velocity relationship", "Compression/rebound damping shapes force with shaft velocity and transient response; exact live damper force remains unavailable."),
    )
    result.extend(
        _quantity(
            quantity_id,
            label,
            meaning,
            QuantitySemantics.RELATIVE_STATE,
            components=("tires", "platform"),
        )
        for quantity_id, label, meaning in relative_specs
    )
    unavailable_labels = {
        "quantity:exact_tire_force": "Exact tire force",
        "quantity:exact_wheel_load": "Exact dynamic wheel load",
        "quantity:exact_spring_force": "Exact spring force",
        "quantity:exact_damper_force": "Exact damper force",
        "quantity:exact_arb_torque": "Exact anti-roll-bar torque",
        "quantity:exact_aerodynamic_downforce": "Exact aerodynamic downforce",
        "quantity:exact_aerodynamic_balance": "Exact aerodynamic balance",
        "quantity:exact_aerodynamic_drag_force": "Exact aerodynamic drag force",
        "quantity:exact_drag_coefficient": "Exact drag coefficient",
        "quantity:exact_differential_torque": "Exact differential torque",
        "quantity:exact_contact_patch_distribution": "Exact contact-patch distribution",
        "quantity:exact_friction_coefficient": "Exact friction coefficient",
    }
    result.extend(
        _quantity(
            quantity_id,
            label,
            f"{label} remains unavailable without validated measured inputs and a complete vehicle/tire model.",
            QuantitySemantics.UNAVAILABLE,
            sources=_SRC_SYNTH,
        )
        for quantity_id, label in unavailable_labels.items()
    )
    return tuple(result)


_MECHANISM_SPECS: tuple[
    tuple[str, str, DynamicResponseRegime, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str, str], ...
] = (
    ("front_tire_saturation_like", "Front tire demand limitation candidate", DynamicResponseRegime.BOTH, ("tires", "alignment", "steering"), ("tire_state", "corner_rotation"), ("turn_in_response", "center_rotation"), ("steering_deg", "yaw_rate", "lat_accel", "speed_mph"), "Steering demand rises while matched yaw response weakens.", "Yaw response remains proportional after context and tire state are matched.", "Separate tire-state migration from roll/platform support with temperature, travel, and sustained-window evidence."),
    ("rear_tire_saturation_like", "Rear tire demand limitation candidate", DynamicResponseRegime.BOTH, ("tires", "differential"), ("tire_state", "powertrain_response"), ("exit_traction", "throttle_realization"), ("throttle_pct", "yaw_rate", "long_accel", "lr_wheel_speed", "rr_wheel_speed"), "Matched throttle produces weaker acceleration or unstable yaw with rear slip-like exposure.", "Matched power response is stable with no rear disagreement proxy.", "Separate tire demand from differential coupling and driver throttle timing."),
    ("front_roll_support_limitation", "Front roll-support limitation candidate", DynamicResponseRegime.BOTH, ("springs", "anti_roll_bars", "tires"), ("corner_rotation", "platform_response"), ("center_rotation", "platform_consistency"), ("steering_deg", "yaw_rate", "shock_deflection"), "Sustained left-right travel and steering/yaw mismatch repeat after settling.", "Center response is unchanged despite matched roll/platform state.", "Compare settled roll response against tire-state migration; component remains unresolved."),
    ("rear_roll_support_limitation", "Rear roll-support limitation candidate", DynamicResponseRegime.BOTH, ("springs", "anti_roll_bars", "tires"), ("corner_rotation", "platform_response"), ("center_rotation", "exit_traction"), ("yaw_rate", "shock_deflection", "throttle_pct"), "Rear roll response co-occurs with rotation or exit-security change.", "Rear response remains stable across the matched roll state.", "Separate rear spring, rear ARB, tire, and platform contribution."),
    ("platform_pitch_migration", "Platform pitch migration candidate", DynamicResponseRegime.BOTH, ("platform", "springs"), ("platform_response", "braking_response"), ("braking_realization", "platform_consistency"), ("ride_height", "shock_deflection", "brake_pct", "speed_mph"), "Pitch/height state migrates with braking or speed and response changes in the same window.", "Response changes without a repeatable platform migration.", "Separate transient damper settling from sustained spring/platform state."),
    ("platform_roll_migration", "Platform roll migration candidate", DynamicResponseRegime.BOTH, ("platform", "springs", "anti_roll_bars"), ("platform_response", "corner_rotation"), ("center_rotation", "platform_consistency"), ("ride_height", "shock_deflection", "steering_deg", "speed_mph"), "Left-right platform migration repeats with steering/yaw response change.", "No repeatable platform migration exists at matched speed and line.", "Separate traffic disturbance, transient settling, and sustained roll support."),
    ("brake_entry_instability", "Brake-entry instability candidate", DynamicResponseRegime.TRANSIENT, ("brakes", "tires", "weight_distribution"), ("braking_response", "corner_rotation"), ("braking_realization", "entry_rotation"), ("brake_01", "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar", "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar", "lf_speed", "rf_speed", "lr_speed", "rr_speed", "yaw_rate", "steering_deg"), "Yaw instability begins while brake remains applied at matched driver demand and observed front/rear line-pressure and wheel-speed relationships are retained separately.", "Yaw change begins only after release or after driver steering changes, with no supporting pressure-distribution or wheel-lock evidence.", "Locate onset relative to driver brake input, four-corner line pressure, wheel-lock evidence, release, steering, and yaw; ABS state is optional and usable only with manifest-validated channels."),
    ("brake_release_rotation_deficit", "Brake-release rotation deficit candidate", DynamicResponseRegime.TRANSIENT, ("brakes", "dampers", "tires"), ("braking_response", "corner_rotation", "damper_response"), ("brake_release_transition", "entry_rotation"), ("brake_01", "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar", "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar", "steering_deg", "yaw_rate", "shock_velocity"), "Rotation fails to develop during a matched driver-input and observed line-pressure release transition.", "Rotation is normal through the pressure release and weakens only after settling.", "Separate driver brake release, observed front/rear pressure decay, optional manifest-valid ABS evidence, and transient chassis settling."),
    ("center_rotation_deficit", "Settled center-rotation deficit candidate", DynamicResponseRegime.STEADY_STATE, ("tires", "alignment", "springs", "anti_roll_bars", "platform", "weight_distribution", "differential", "steering"), ("corner_rotation", "tire_state", "platform_response"), ("center_rotation", "speed_retention"), ("steering_deg", "yaw_rate", "speed_mph", "lat_accel"), "After settling, steering demand rises while matched yaw response weakens and time loss begins before throttle.", "The response deficit exists only during transition or driver demand differs.", "Separate front demand, roll support, tire state, platform, and differential candidates without selecting a component."),
    ("power_on_rotation_excess", "Power-on rotation excess candidate", DynamicResponseRegime.TRANSIENT, ("tires", "differential", "springs", "anti_roll_bars"), ("powertrain_response", "corner_rotation"), ("throttle_realization", "exit_traction"), ("throttle_pct", "yaw_rate", "long_accel", "wheel_speed"), "Yaw response increases abruptly after matched throttle pickup.", "Yaw change starts before throttle or follows a driver correction.", "Separate rear tire demand, differential coupling, and platform transition."),
    ("power_on_rotation_deficit", "Power-on rotation deficit candidate", DynamicResponseRegime.BOTH, ("tires", "differential", "springs", "anti_roll_bars"), ("powertrain_response", "corner_rotation"), ("throttle_realization", "exit_traction"), ("throttle_pct", "yaw_rate", "long_accel", "wheel_speed"), "Matched throttle produces weaker yaw/acceleration response after pickup.", "Deficit is fully carried from center before throttle begins.", "Separate carried center loss from power-on vehicle response."),
    ("traction_limitation_like", "Traction limitation-like candidate", DynamicResponseRegime.BOTH, ("tires", "differential"), ("powertrain_response", "tire_state"), ("exit_traction", "straight_acceleration"), ("throttle_pct", "long_accel", "wheel_speed", "yaw_rate"), "Full or rising throttle co-occurs with reduced acceleration and slip-like rear relationship.", "Acceleration difference is explained by lower exit speed or throttle demand.", "Separate tire demand from differential response and carried exit speed."),
    ("tire_state_migration", "Tire-state migration candidate", DynamicResponseRegime.BOTH, ("tires", "alignment"), ("tire_state", "stint_trend"), ("tire_state_migration", "stability_workload"), ("lap", "steering_deg", "yaw_rate", "tire_temperature", "tire_pressure", "tire_wear"), "Qualified repeated laps show pressure/temperature/wear/slip and balance-response migration.", "Short run or unchanged exact-context response cannot support migration.", "Separate pressure, thermal, wear, driver, and platform migration without an exact grip-loss claim."),
    ("scrub_like_resistance", "Scrub-like resistance candidate", DynamicResponseRegime.STEADY_STATE, ("alignment", "tires"), ("resistance_scrub_like", "powertrain_response"), ("straight_acceleration", "path_efficiency"), ("steering_deg", "speed_mph", "long_accel", "wheel_speed"), "Matched entry-to-straight state shows resistance-like acceleration response with alignment/tire proxies.", "The straight deficit is fully carried from exit or traffic differs.", "Separate exit carry, gearing, driver demand, traffic, and scrub-like response."),
    ("gearing_headroom_limitation", "Gearing-headroom limitation candidate", DynamicResponseRegime.STEADY_STATE, ("final_drive",), ("powertrain_response",), ("gearing_headroom", "straight_acceleration"), ("rpm", "gear", "speed_mph", "throttle_pct", "long_accel"), "Matched straight entry and throttle show limiter/headroom or gear-acceleration evidence.", "The speed deficit begins before throttle or is carried from exit.", "Require matched exit carry, gear, RPM, limiter, and acceleration response."),
    ("disturbance_compliance_issue", "Disturbance-compliance candidate", DynamicResponseRegime.TRANSIENT, ("dampers", "springs", "platform", "tires"), ("damper_response", "platform_response"), ("disturbance_compliance", "stability_workload"), ("vert_accel", "shock_velocity", "shock_deflection", "yaw_rate"), "A bump/banking transition produces repeatable oscillation, settling, or recovery response.", "The problem occurs only after the chassis has settled with no disturbance exposure.", "Separate high-speed shaft response, spring travel support, tire response, and traffic disturbance."),
)


_DISCRIMINATOR_PAIRS = {
    "front_tire_saturation_like": "front_roll_support_limitation",
    "rear_tire_saturation_like": "traction_limitation_like",
    "front_roll_support_limitation": "platform_roll_migration",
    "rear_roll_support_limitation": "power_on_rotation_deficit",
    "platform_pitch_migration": "brake_release_rotation_deficit",
    "platform_roll_migration": "disturbance_compliance_issue",
    "brake_entry_instability": "brake_release_rotation_deficit",
    "brake_release_rotation_deficit": "brake_entry_instability",
    "center_rotation_deficit": "front_tire_saturation_like",
    "power_on_rotation_excess": "rear_tire_saturation_like",
    "power_on_rotation_deficit": "traction_limitation_like",
    "traction_limitation_like": "power_on_rotation_deficit",
    "tire_state_migration": "platform_roll_migration",
    "scrub_like_resistance": "gearing_headroom_limitation",
    "gearing_headroom_limitation": "scrub_like_resistance",
    "disturbance_compliance_issue": "platform_roll_migration",
}

_MECHANISM_TO_TOOL = {
    "front_tire_saturation_like": VehicleDynamicsInspectionToolId.INSPECT_TIRE_DEMAND,
    "rear_tire_saturation_like": VehicleDynamicsInspectionToolId.INSPECT_LOAD_TRANSFER,
    "front_roll_support_limitation": VehicleDynamicsInspectionToolId.INSPECT_ROLL_RESPONSE,
    "rear_roll_support_limitation": VehicleDynamicsInspectionToolId.INSPECT_PLATFORM_STATE,
    "platform_pitch_migration": VehicleDynamicsInspectionToolId.INSPECT_PITCH_RESPONSE,
    "platform_roll_migration": VehicleDynamicsInspectionToolId.INSPECT_TRAFFIC_PLATFORM_RESPONSE,
    "brake_entry_instability": VehicleDynamicsInspectionToolId.INSPECT_BRAKE_VEHICLE_RESPONSE,
    "brake_release_rotation_deficit": VehicleDynamicsInspectionToolId.INSPECT_TRANSIENT_SETTLING,
    "center_rotation_deficit": VehicleDynamicsInspectionToolId.INSPECT_STEADY_STATE_BALANCE,
    "power_on_rotation_excess": VehicleDynamicsInspectionToolId.INSPECT_POWER_ON_RESPONSE,
    "power_on_rotation_deficit": VehicleDynamicsInspectionToolId.INSPECT_DIFFERENTIAL_RESPONSE,
    "traction_limitation_like": VehicleDynamicsInspectionToolId.INSPECT_TIRE_DEMAND,
    "tire_state_migration": VehicleDynamicsInspectionToolId.INSPECT_TIRE_STATE_MIGRATION,
    "scrub_like_resistance": VehicleDynamicsInspectionToolId.INSPECT_ALIGNMENT_RESPONSE,
    "gearing_headroom_limitation": VehicleDynamicsInspectionToolId.INSPECT_GEAR_ACCELERATION_RESPONSE,
    "disturbance_compliance_issue": VehicleDynamicsInspectionToolId.INSPECT_TRANSIENT_SETTLING,
}

_MECHANISM_PHASES = {
    "front_tire_saturation_like": (VehicleDynamicsPhase.TURN_IN, VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.CENTER),
    "rear_tire_saturation_like": (VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.CENTER, VehicleDynamicsPhase.THROTTLE_PICKUP, VehicleDynamicsPhase.EXIT),
    "front_roll_support_limitation": (VehicleDynamicsPhase.TURN_IN, VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.CENTER),
    "rear_roll_support_limitation": (VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.CENTER, VehicleDynamicsPhase.THROTTLE_PICKUP, VehicleDynamicsPhase.EXIT),
    "platform_pitch_migration": (VehicleDynamicsPhase.BRAKE, VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.THROTTLE_PICKUP),
    "platform_roll_migration": (VehicleDynamicsPhase.TURN_IN, VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.CENTER, VehicleDynamicsPhase.EXIT),
    "brake_entry_instability": (VehicleDynamicsPhase.BRAKE, VehicleDynamicsPhase.ENTRY),
    "brake_release_rotation_deficit": (VehicleDynamicsPhase.ENTRY,),
    "center_rotation_deficit": (VehicleDynamicsPhase.CENTER,),
    "power_on_rotation_excess": (VehicleDynamicsPhase.THROTTLE_PICKUP, VehicleDynamicsPhase.EXIT),
    "power_on_rotation_deficit": (VehicleDynamicsPhase.THROTTLE_PICKUP, VehicleDynamicsPhase.EXIT),
    "traction_limitation_like": (VehicleDynamicsPhase.THROTTLE_PICKUP, VehicleDynamicsPhase.EXIT, VehicleDynamicsPhase.FOLLOWING_STRAIGHT),
    "tire_state_migration": (VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.CENTER, VehicleDynamicsPhase.EXIT, VehicleDynamicsPhase.FOLLOWING_STRAIGHT),
    "scrub_like_resistance": (VehicleDynamicsPhase.STRAIGHT, VehicleDynamicsPhase.FOLLOWING_STRAIGHT),
    "gearing_headroom_limitation": (VehicleDynamicsPhase.STRAIGHT, VehicleDynamicsPhase.FOLLOWING_STRAIGHT),
    "disturbance_compliance_issue": (VehicleDynamicsPhase.TRANSITION, VehicleDynamicsPhase.TURN_IN, VehicleDynamicsPhase.ENTRY, VehicleDynamicsPhase.EXIT),
}


_CHANNEL_CANONICAL_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "brake_01": ("brake_01",),
    "brake_pct": ("brake_01", "brake_pct"),
    "gear": ("gear",),
    "lap": ("lap",),
    "lat_accel": ("lat_accel",),
    "lf_brake_line_pressure_bar": ("lf_brake_line_pressure_bar",),
    "lf_ride_height": ("lf_ride_height_m", "lf_ride_height"),
    "lf_shock_deflection": ("lf_shock_defl_in", "lf_shock_deflection"),
    "lf_speed": ("lf_speed",),
    "lf_wheel_speed": (
        "lf_speed",
        "lf_wheel_speed",
        "front_wheel_speed_mismatch",
        "front_wheel_speed_mismatch_raw",
        "front_wheel_speed_mismatch_corrected",
    ),
    "long_accel": ("long_accel",),
    "lr_brake_line_pressure_bar": ("lr_brake_line_pressure_bar",),
    "lr_ride_height": ("lr_ride_height_m", "lr_ride_height"),
    "lr_shock_deflection": ("lr_shock_defl_in", "lr_shock_deflection"),
    "lr_speed": ("lr_speed",),
    "lr_wheel_speed": (
        "lr_speed",
        "lr_wheel_speed",
        "rear_wheel_speed_mismatch",
        "rear_wheel_speed_mismatch_raw",
        "rear_wheel_speed_mismatch_corrected",
    ),
    "rear_wheel_speed_mismatch": (
        "rear_wheel_speed_mismatch",
        "rear_wheel_speed_mismatch_raw",
        "rear_wheel_speed_mismatch_corrected",
    ),
    "front_wheel_speed_mismatch": (
        "front_wheel_speed_mismatch",
        "front_wheel_speed_mismatch_raw",
        "front_wheel_speed_mismatch_corrected",
    ),
    "rf_brake_line_pressure_bar": ("rf_brake_line_pressure_bar",),
    "rf_ride_height": ("rf_ride_height_m", "rf_ride_height"),
    "rf_shock_deflection": ("rf_shock_defl_in", "rf_shock_deflection"),
    "rf_speed": ("rf_speed",),
    "rf_wheel_speed": (
        "rf_speed",
        "rf_wheel_speed",
        "front_wheel_speed_mismatch",
        "front_wheel_speed_mismatch_raw",
        "front_wheel_speed_mismatch_corrected",
    ),
    "rpm": ("rpm",),
    "rr_brake_line_pressure_bar": ("rr_brake_line_pressure_bar",),
    "rr_ride_height": ("rr_ride_height_m", "rr_ride_height"),
    "rr_shock_deflection": ("rr_shock_defl_in", "rr_shock_deflection"),
    "rr_speed": ("rr_speed",),
    "rr_wheel_speed": (
        "rr_speed",
        "rr_wheel_speed",
        "rear_wheel_speed_mismatch",
        "rear_wheel_speed_mismatch_raw",
        "rear_wheel_speed_mismatch_corrected",
    ),
    "ride_height": (
        "cfs_ride_height_m",
        "lf_ride_height_m",
        "rf_ride_height_m",
        "lr_ride_height_m",
        "rr_ride_height_m",
        "ride_height",
    ),
    "shock_deflection": (
        "lf_shock_defl_in",
        "rf_shock_defl_in",
        "lr_shock_defl_in",
        "rr_shock_defl_in",
        "shock_deflection",
    ),
    "shock_velocity": (
        "lf_shock_vel_in_s",
        "rf_shock_vel_in_s",
        "lr_shock_vel_in_s",
        "rr_shock_vel_in_s",
        "shock_velocity",
    ),
    "speed_mph": ("speed_mps", "speed_mph"),
    "steering_deg": ("steering_rad", "steering_deg"),
    "throttle_pct": ("throttle_01", "throttle_pct"),
    "tire_pressure": (
        "lf_pressure",
        "rf_pressure",
        "lr_pressure",
        "rr_pressure",
        "tire_pressure",
    ),
    "tire_temperature": (
        "lf_temp_left",
        "lf_temp_middle",
        "lf_temp_right",
        "rf_temp_left",
        "rf_temp_middle",
        "rf_temp_right",
        "lr_temp_left",
        "lr_temp_middle",
        "lr_temp_right",
        "rr_temp_left",
        "rr_temp_middle",
        "rr_temp_right",
        "tire_temperature",
    ),
    "tire_wear": (
        "lf_wear_left",
        "lf_wear_middle",
        "lf_wear_right",
        "rf_wear_left",
        "rf_wear_middle",
        "rf_wear_right",
        "lr_wear_left",
        "lr_wear_middle",
        "lr_wear_right",
        "rr_wear_left",
        "rr_wear_middle",
        "rr_wear_right",
        "tire_wear",
    ),
    "vert_accel": ("vert_accel",),
    "wheel_speed": (
        "lf_speed",
        "rf_speed",
        "lr_speed",
        "rr_speed",
        "front_wheel_speed_mismatch",
        "front_wheel_speed_mismatch_raw",
        "front_wheel_speed_mismatch_corrected",
        "rear_wheel_speed_mismatch",
        "rear_wheel_speed_mismatch_raw",
        "rear_wheel_speed_mismatch_corrected",
        "wheel_speed",
    ),
    "yaw_rate": ("yaw_rate",),
}

_DRIVER_INPUT_CHANNEL_IDS = frozenset(
    {"brake_01", "brake_pct", "steering_deg", "throttle_pct"}
)
_TIRE_PLATFORM_CHANNEL_IDS = frozenset(
    {
        "lf_ride_height",
        "lf_shock_deflection",
        "lr_ride_height",
        "lr_shock_deflection",
        "rf_ride_height",
        "rf_shock_deflection",
        "ride_height",
        "rr_ride_height",
        "rr_shock_deflection",
        "shock_deflection",
        "shock_velocity",
        "tire_pressure",
        "tire_temperature",
        "tire_wear",
    }
)


def _accepted_source_channel_ids(channel_id: str) -> tuple[str, ...]:
    equivalents = _CHANNEL_CANONICAL_EQUIVALENTS.get(channel_id)
    if equivalents is None:
        raise ValueError(f"No reviewed runtime channel aliases exist for {channel_id}")
    accepted = tuple(
        dict.fromkeys(
            (
                channel_id,
                *equivalents,
                *tuple(
                    sorted(
                        raw
                        for raw, canonical in RAW_TO_CANONICAL.items()
                        if canonical in set(equivalents)
                    )
                ),
            )
        )
    )
    return accepted


def _channel_alternative(
    channel_id: str,
) -> VehicleDynamicsRuntimeChannelAlternative:
    return VehicleDynamicsRuntimeChannelAlternative(
        channel_id=channel_id,
        accepted_source_channel_ids=_accepted_source_channel_ids(channel_id),
    )


def _channel_layers(channel_id: str) -> tuple[DynamicsChainStageKind, ...]:
    if channel_id in _DRIVER_INPUT_CHANNEL_IDS:
        return (DynamicsChainStageKind.DRIVER_INPUT,)
    if channel_id in _TIRE_PLATFORM_CHANNEL_IDS:
        return (
            DynamicsChainStageKind.VEHICLE_RESPONSE,
            DynamicsChainStageKind.TIRE_PLATFORM_STATE,
        )
    return (DynamicsChainStageKind.VEHICLE_RESPONSE,)


def _channel_requirement(
    requirement_id: str,
    channel_ids: tuple[str, ...],
    *,
    evidence_layer_ids: tuple[DynamicsChainStageKind, ...] | None = None,
    minimum_alternatives: int = 1,
) -> VehicleDynamicsRuntimeChannelRequirement:
    return VehicleDynamicsRuntimeChannelRequirement(
        requirement_id=f"support_channel:{requirement_id}",
        evidence_layer_ids=(
            evidence_layer_ids
            if evidence_layer_ids is not None
            else _channel_layers(channel_ids[0])
        ),
        alternatives=tuple(_channel_alternative(item) for item in channel_ids),
        minimum_alternatives=minimum_alternatives,
    )


def _brake_support_channel_groups(
    *,
    include_wheel_response: bool,
    include_shock_velocity: bool,
) -> tuple[VehicleDynamicsRuntimeChannelRequirement, ...]:
    groups = [
        _channel_requirement("brake_input", ("brake_01",)),
        _channel_requirement(
            "front_brake_pressure",
            ("lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar"),
            minimum_alternatives=2,
        ),
        _channel_requirement(
            "rear_brake_pressure",
            ("lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar"),
            minimum_alternatives=2,
        ),
    ]
    if include_wheel_response:
        groups.extend(
            (
                _channel_requirement(
                    "front_wheel_response",
                    ("lf_speed", "rf_speed"),
                    minimum_alternatives=2,
                ),
                _channel_requirement(
                    "rear_wheel_response",
                    ("lr_speed", "rr_speed"),
                    minimum_alternatives=2,
                ),
            )
        )
    groups.extend(
        (
            _channel_requirement("yaw_response", ("yaw_rate",)),
            _channel_requirement("steering_input", ("steering_deg",)),
        )
    )
    if include_shock_velocity:
        groups.append(_channel_requirement("shock_velocity", ("shock_velocity",)))
    return tuple(groups)


def _mechanism_support_channel_groups(
    mechanism: VehicleDynamicMechanism,
) -> tuple[VehicleDynamicsRuntimeChannelRequirement, ...]:
    mechanism_name = mechanism.definition_id.removeprefix("mechanism:")
    if mechanism_name == "brake_entry_instability":
        return _brake_support_channel_groups(
            include_wheel_response=True,
            include_shock_velocity=False,
        )
    if mechanism_name == "brake_release_rotation_deficit":
        return _brake_support_channel_groups(
            include_wheel_response=False,
            include_shock_velocity=True,
        )
    if mechanism_name == "front_roll_support_limitation":
        return (
            _channel_requirement("steering_deg", ("steering_deg",)),
            _channel_requirement("yaw_rate", ("yaw_rate",)),
            _channel_requirement(
                "front_shock_deflection_pair",
                ("lf_shock_deflection", "rf_shock_deflection"),
                minimum_alternatives=2,
            ),
        )
    if mechanism_name == "rear_roll_support_limitation":
        return (
            _channel_requirement("yaw_rate", ("yaw_rate",)),
            _channel_requirement(
                "rear_shock_deflection_pair",
                ("lr_shock_deflection", "rr_shock_deflection"),
                minimum_alternatives=2,
            ),
            _channel_requirement("throttle_pct", ("throttle_pct",)),
        )
    if mechanism_name == "platform_pitch_migration":
        return (
            _channel_requirement(
                "front_ride_height",
                ("lf_ride_height", "rf_ride_height"),
            ),
            _channel_requirement(
                "rear_ride_height",
                ("lr_ride_height", "rr_ride_height"),
            ),
            _channel_requirement(
                "front_shock_deflection",
                ("lf_shock_deflection", "rf_shock_deflection"),
            ),
            _channel_requirement(
                "rear_shock_deflection",
                ("lr_shock_deflection", "rr_shock_deflection"),
            ),
            _channel_requirement("brake_pct", ("brake_pct",)),
            _channel_requirement("speed_mph", ("speed_mph",)),
        )
    if mechanism_name == "platform_roll_migration":
        return (
            _channel_requirement(
                "left_ride_height",
                ("lf_ride_height", "lr_ride_height"),
            ),
            _channel_requirement(
                "right_ride_height",
                ("rf_ride_height", "rr_ride_height"),
            ),
            _channel_requirement(
                "left_shock_deflection",
                ("lf_shock_deflection", "lr_shock_deflection"),
            ),
            _channel_requirement(
                "right_shock_deflection",
                ("rf_shock_deflection", "rr_shock_deflection"),
            ),
            _channel_requirement("steering_deg", ("steering_deg",)),
            _channel_requirement("speed_mph", ("speed_mph",)),
        )
    groups: list[VehicleDynamicsRuntimeChannelRequirement] = []
    for channel_id in mechanism.required_measured_channels:
        if channel_id != "wheel_speed":
            groups.append(_channel_requirement(channel_id, (channel_id,)))
            continue
        if mechanism_name == "scrub_like_resistance":
            groups.extend(
                (
                    _channel_requirement(
                        "front_wheel_speed_relationship",
                        ("lf_wheel_speed", "rf_wheel_speed"),
                        minimum_alternatives=2,
                    ),
                    _channel_requirement(
                        "rear_wheel_speed_relationship",
                        ("lr_wheel_speed", "rr_wheel_speed"),
                        minimum_alternatives=2,
                    ),
                )
            )
        else:
            groups.append(
                _channel_requirement(
                    "rear_wheel_speed_relationship",
                    ("lr_wheel_speed", "rr_wheel_speed"),
                    minimum_alternatives=2,
                )
            )
    return tuple(groups)


def runtime_support_channel_requirement_satisfied(
    requirement: VehicleDynamicsRuntimeChannelRequirement,
    source_channels_by_layer: Mapping[
        DynamicsChainStageKind | str, Sequence[str]
    ],
) -> bool:
    """Match only explicit, case-sensitive aliases; never widen with prose/substrings."""

    available: set[str] = set()
    for layer in requirement.evidence_layer_ids:
        available.update(source_channels_by_layer.get(layer, ()))
        available.update(source_channels_by_layer.get(layer.value, ()))
    matched = sum(
        bool(set(alternative.accepted_source_channel_ids) & available)
        for alternative in requirement.alternatives
    )
    return matched >= requirement.minimum_alternatives


def unmet_runtime_support_channel_requirement_ids(
    trust: VehicleDynamicsRuntimeMechanismTrust,
    source_channels_by_layer: Mapping[
        DynamicsChainStageKind | str, Sequence[str]
    ],
) -> tuple[str, ...]:
    """Return every closed support-channel group absent from current typed evidence."""

    return tuple(
        requirement.requirement_id
        for requirement in trust.support_required_channel_groups
        if not runtime_support_channel_requirement_satisfied(
            requirement, source_channels_by_layer
        )
    )


def _mechanisms() -> tuple[VehicleDynamicMechanism, ...]:
    result: list[VehicleDynamicMechanism] = []
    for (
        mechanism_id,
        label,
        regime,
        components,
        p20_ids,
        p32_ids,
        channels,
        support,
        contradiction,
        discriminator,
    ) in _MECHANISM_SPECS:
        sources = _SRC_MANUAL
        if "damper" in components:
            sources = _SRC_DAMPER
        if mechanism_id in {"front_tire_saturation_like", "rear_tire_saturation_like", "traction_limitation_like"}:
            sources = ("sae_2011_01_0094_combined_tire_demand", *_SRC_MANUAL)
        if mechanism_id.startswith("platform_"):
            sources = _SRC_PACKAGE
        prefix = f"observation:{mechanism_id}"
        brake_proxies = (
            (
                "quantity:front_brake_line_pressure_state",
                "quantity:rear_brake_line_pressure_state",
                "quantity:relative_front_rear_brake_pressure_distribution",
                "quantity:wheel_lock_evidence_state",
                "quantity:abs_intervention_state",
            )
            if mechanism_id
            in {"brake_entry_instability", "brake_release_rotation_deficit"}
            else ()
        )
        result.append(
            VehicleDynamicMechanism(
                **_base(
                    f"mechanism:{mechanism_id}",
                    label,
                    f"Candidate physical mechanism: {label.casefold()}. It becomes current truth only through P19-qualified evidence.",
                    channels=channels,
                    proxies=brake_proxies,
                    phases=_MECHANISM_PHASES[mechanism_id],
                    components=components,
                    sources=sources,
                    forbidden=(
                        "This candidate identifies a current component cause.",
                        "This candidate authorizes a setup change or exact setup value.",
                        "This candidate fabricates unavailable force, load, torque, coefficient, or aerodynamic quantity.",
                    ),
                ),
                response_regime=regime,
                inspection_tool_id=_MECHANISM_TO_TOOL[mechanism_id],
                allowed_time_origin_kinds=(
                    (TimeOriginKind.LOCAL_GENERATION,)
                    if mechanism_id in {"gearing_headroom_limitation", "scrub_like_resistance"}
                    else (
                        TimeOriginKind.LOCAL_GENERATION,
                        TimeOriginKind.AMPLIFIED,
                        TimeOriginKind.SURRENDERED,
                    )
                ),
                support_contract_ids=(f"{prefix}:support_discriminator",),
                contradiction_contract_ids=(f"{prefix}:contradiction",),
                discriminator_contract_ids=(
                    f"{prefix}:support_discriminator",
                    f"{prefix}:contradiction",
                ),
                p20_mechanism_ids=p20_ids,
                p26_component_family_ids=components,
                p32_performance_mechanism_ids=p32_ids,
                expected_countereffects=(
                    "A response improvement in one phase can worsen stability, tire state, platform consistency, workload, or downstream time.",
                ),
            )
        )
    return tuple(result)


def _observation_contracts(
    mechanisms: tuple[VehicleDynamicMechanism, ...],
) -> tuple[DynamicObservationContract, ...]:
    specs_by_id = {f"mechanism:{item[0]}": item for item in _MECHANISM_SPECS}
    result: list[DynamicObservationContract] = []
    for mechanism in mechanisms:
        spec = specs_by_id[mechanism.definition_id]
        mechanism_name = mechanism.definition_id.removeprefix("mechanism:")
        paired_id = f"mechanism:{_DISCRIMINATOR_PAIRS[mechanism_name]}"
        channels, support, contradiction, discriminator = spec[6], spec[7], spec[8], spec[9]
        regime = mechanism.response_regime
        common = {
            "required_evidence_layers": (
                "driver_input",
                "vehicle_demand",
                "vehicle_response",
                "tire_platform_state",
                "time_consequence",
            ),
            "traffic_clean_required": mechanism_name.startswith("platform_"),
            "transient_evidence_required": regime is DynamicResponseRegime.TRANSIENT,
            "steady_state_evidence_required": regime is DynamicResponseRegime.STEADY_STATE,
        }
        for polarity in ("support_discriminator", "contradiction"):
            is_support = polarity == "support_discriminator"
            contract_id = f"observation:{mechanism_name}:{polarity}"
            result.append(
                DynamicObservationContract(
                    **_base(
                        contract_id,
                        f"{mechanism.label} {polarity.replace('_', ' ')}",
                        support if is_support else contradiction,
                        channels=channels,
                        proxies=mechanism.valid_proxy_ids,
                        phases=mechanism.relevant_phases,
                        components=mechanism.p26_component_family_ids,
                        sources=mechanism.source_ids,
                        forbidden=(
                            "Expected relationships are current observations.",
                            "One observation establishes cause, component blame, or setup authority.",
                        ),
                    ),
                    inspection_tool_id=mechanism.inspection_tool_id,
                    supports_mechanism_ids=(mechanism.definition_id,) if is_support else (),
                    contradicts_mechanism_ids=() if is_support else (mechanism.definition_id,),
                    discriminates_mechanism_ids=(mechanism.definition_id, paired_id),
                    support_requirements=(support,),
                    contradiction_requirements=(contradiction,),
                    discriminator_requirements=(discriminator,),
                    **common,
                )
            )
    return tuple(result)


def _tire_demand_states() -> tuple[TireDemandState, ...]:
    specs = (
        ("low_relative_demand", TireDemandLevel.LOW, ("lateral", "longitudinal")),
        ("moderate_relative_demand", TireDemandLevel.MODERATE, ("lateral", "longitudinal")),
        ("high_relative_demand", TireDemandLevel.HIGH, ("lateral", "longitudinal")),
        ("increasing_demand", TireDemandLevel.INCREASING, ("lateral", "longitudinal")),
        ("decreasing_demand", TireDemandLevel.DECREASING, ("lateral", "longitudinal")),
        ("thermal_migration", TireDemandLevel.THERMAL_MIGRATION, ("vertical", "lateral", "longitudinal")),
        ("pressure_migration", TireDemandLevel.PRESSURE_MIGRATION, ("vertical", "lateral", "longitudinal")),
        ("possible_combined_demand_limitation", TireDemandLevel.POSSIBLE_COMBINED_DEMAND_LIMITATION, ("combined", "lateral", "longitudinal")),
    )
    return tuple(
        TireDemandState(
            **_base(
                f"tire_demand:{state_id}",
                state_id.replace("_", " ").title(),
                "Qualitative relative tire-demand state; no friction-circle size, tire force, or exact grip limit is inferred.",
                created_by=("quantity:combined_tire_demand",),
                affected_by=("context:track_geometry", "context:tire_fuel_weather"),
                components=("tires",),
                sources=("sae_2011_01_0094_combined_tire_demand", *_SRC_SYNTH),
                forbidden=(
                    "This state publishes exact tire force, friction coefficient, grip limit, or contact-patch distribution.",
                ),
            ),
            demand_level=level,
            demand_axes=axes,
            response_regime=DynamicResponseRegime.BOTH,
        )
        for state_id, level, axes in specs
    )


def _chassis_states() -> tuple[ChassisResponseState, ...]:
    specs = (
        ("braking_pitch_yaw", "Braking pitch and yaw response", ("pitch", "yaw", "stability"), DynamicResponseRegime.TRANSIENT, ("brakes", "platform", "tires")),
        ("steering_yaw_response", "Steering-to-yaw response", ("steering", "yaw"), DynamicResponseRegime.BOTH, ("steering", "tires")),
        ("power_on_yaw_acceleration", "Power-on yaw and acceleration response", ("yaw", "acceleration", "stability"), DynamicResponseRegime.BOTH, ("differential", "final_drive", "tires")),
        ("roll_response", "Roll response", ("roll", "yaw"), DynamicResponseRegime.BOTH, ("springs", "anti_roll_bars", "platform")),
        ("pitch_response", "Pitch response", ("pitch", "heave"), DynamicResponseRegime.BOTH, ("springs", "dampers", "platform")),
        ("platform_state", "Platform state", ("roll", "pitch", "heave"), DynamicResponseRegime.BOTH, ("platform", "springs", "dampers", "anti_roll_bars")),
        ("independent_rear_wheel_motion", "Independent rear wheel motion", ("roll", "heave", "yaw"), DynamicResponseRegime.BOTH, ("springs", "dampers", "alignment", "differential")),
        ("rear_camber_toe_response", "Rear camber and toe response", ("roll", "yaw", "stability"), DynamicResponseRegime.BOTH, ("alignment", "tires", "differential")),
    )
    return tuple(
        ChassisResponseState(
            **_base(
                f"chassis_response:{state_id}",
                label,
                f"Observed or relative {label.casefold()} under exact driver and track demand.",
                components=components,
                sources=(
                    _SRC_ARCH
                    if state_id in {"independent_rear_wheel_motion", "rear_camber_toe_response"}
                    else _SRC_MANUAL
                ),
            ),
            response_regime=regime,
            response_axes=axes,
        )
        for state_id, label, axes, regime, components in specs
    )


def _load_paths() -> tuple[LoadPath, ...]:
    specs = (
        ("straight", ("quantity:vehicle_speed",), ("quantity:vehicle_speed",), "tire_demand:low_relative_demand"),
        ("lift_brake", ("quantity:vehicle_speed", "quantity:brake_input"), ("quantity:longitudinal_demand",), "tire_demand:increasing_demand"),
        ("turn_in", ("quantity:longitudinal_demand", "quantity:steering_input"), ("quantity:lateral_demand",), "tire_demand:possible_combined_demand_limitation"),
        ("entry", ("quantity:lateral_demand", "quantity:brake_input"), ("quantity:combined_tire_demand",), "tire_demand:possible_combined_demand_limitation"),
        ("center", ("quantity:combined_tire_demand",), ("quantity:sustained_lateral_demand",), "tire_demand:high_relative_demand"),
        ("throttle_pickup", ("quantity:sustained_lateral_demand", "quantity:throttle_input"), ("quantity:rear_combined_demand",), "tire_demand:possible_combined_demand_limitation"),
        ("exit", ("quantity:rear_combined_demand",), ("quantity:exit_speed",), "tire_demand:decreasing_demand"),
        ("following_straight", ("quantity:exit_speed",), ("quantity:vehicle_speed",), "tire_demand:low_relative_demand"),
    )
    phase_map = {
        "straight": VehicleDynamicsPhase.STRAIGHT,
        "lift_brake": VehicleDynamicsPhase.BRAKE,
        "turn_in": VehicleDynamicsPhase.TURN_IN,
        "entry": VehicleDynamicsPhase.ENTRY,
        "center": VehicleDynamicsPhase.CENTER,
        "throttle_pickup": VehicleDynamicsPhase.THROTTLE_PICKUP,
        "exit": VehicleDynamicsPhase.EXIT,
        "following_straight": VehicleDynamicsPhase.FOLLOWING_STRAIGHT,
    }
    return tuple(
        LoadPath(
            **_base(
                f"load_path:{name}",
                name.replace("_", " ").title(),
                f"Connected oval load-path state for {name.replace('_', ' ')}; it inherits demand from the prior phase and hands state to the next.",
                created_by=inputs,
                affected_by=("context:track_geometry", "context:driver_input"),
                affects=outputs,
                phases=(phase_map[name],),
                components=("tires", "platform", "springs", "dampers"),
            ),
            sequence_index=index,
            input_quantity_ids=inputs,
            output_quantity_ids=outputs,
            demand_state_ids=(demand_state,),
            prior_load_path_id=f"load_path:{specs[index - 1][0]}" if index else None,
            next_load_path_id=f"load_path:{specs[index + 1][0]}" if index + 1 < len(specs) else None,
        )
        for index, (name, inputs, outputs, demand_state) in enumerate(specs)
    )


def _responses() -> tuple[tuple[TransientResponse, ...], tuple[SteadyStateResponse, ...]]:
    transient = tuple(
        TransientResponse(
            **_base(
                f"transient_response:{name}",
                label,
                meaning,
                channels=channels,
                phases=phases,
                components=components,
                sources=_SRC_DAMPER if "dampers" in components else _SRC_MANUAL,
                forbidden=("A transient observation establishes a settled steady-state cause.",),
            )
        )
        for name, label, meaning, channels, phases, components in (
            ("turn_in_settling", "Turn-in settling", "Yaw, roll, and steering response while the chassis develops lateral load.", ("steering_deg", "yaw_rate", "shock_velocity"), (VehicleDynamicsPhase.TURN_IN, VehicleDynamicsPhase.ENTRY), ("dampers", "springs", "anti_roll_bars", "tires")),
            ("brake_release_transition", "Brake-release transition", "Pitch/yaw response during brake release rather than after settling.", ("brake_pct", "yaw_rate", "shock_velocity"), (VehicleDynamicsPhase.ENTRY,), ("brakes", "dampers", "tires")),
            ("throttle_pickup_transition", "Throttle-pickup transition", "Rear demand, yaw, and acceleration response as throttle is applied.", ("throttle_pct", "yaw_rate", "long_accel"), (VehicleDynamicsPhase.THROTTLE_PICKUP,), ("differential", "tires", "dampers")),
            ("disturbance_recovery", "Disturbance recovery", "Suspension/platform settling after bump or banking transition.", ("vert_accel", "shock_velocity", "shock_deflection"), (VehicleDynamicsPhase.TRANSITION,), ("dampers", "springs", "platform")),
        )
    )
    steady = tuple(
        SteadyStateResponse(
            **_base(
                f"steady_state_response:{name}",
                label,
                meaning,
                channels=channels,
                phases=phases,
                components=components,
                sources=_SRC_MANUAL,
                forbidden=("A transient-only damper signature establishes this settled response.",),
            )
        )
        for name, label, meaning, channels, phases, components in (
            ("settled_center_balance", "Settled center balance", "Sustained steering/yaw/speed response after the chassis has settled.", ("steering_deg", "yaw_rate", "speed_mph"), (VehicleDynamicsPhase.CENTER,), ("tires", "alignment", "springs", "anti_roll_bars", "platform")),
            ("settled_straight_acceleration", "Settled straight acceleration", "Full-throttle acceleration response after exact exit carry is matched.", ("throttle_pct", "speed_mph", "long_accel", "rpm", "gear"), (VehicleDynamicsPhase.FOLLOWING_STRAIGHT,), ("final_drive", "differential", "tires")),
            ("sustained_platform_state", "Sustained platform state", "Speed-correlated ride-height/roll/pitch state over a sustained physical window.", ("ride_height", "shock_deflection", "speed_mph"), (VehicleDynamicsPhase.CENTER, VehicleDynamicsPhase.STRAIGHT), ("platform", "springs", "anti_roll_bars")),
        )
    )
    return transient, steady


def _component_influences(
    mechanisms: tuple[VehicleDynamicMechanism, ...],
) -> tuple[ComponentInfluence, ...]:
    by_component: dict[str, list[str]] = {}
    for mechanism in mechanisms:
        for component in mechanism.p26_component_family_ids:
            by_component.setdefault(component, []).append(mechanism.definition_id)
    physical_roles = {
        "tires": "Tires support vertical load while sharing lateral and longitudinal demand; load sensitivity, slip exposure, pressure, temperature, wear, and attitude require relative exact-context evidence rather than exact force claims.",
        "alignment": "Static camber, caster, and toe influence loaded tire attitude, steering response/stability, and scrub-like resistance; telemetry cannot directly reconstruct the contact patch or tire force.",
        "springs": "Spring rate shapes force versus displacement, vertical support, compliance, roll/pitch contribution, and platform support; it is physically distinct from damper force versus velocity.",
        "dampers": "Low/high-speed compression and rebound, slopes, and blow-off shape transient shaft-motion, settling, disturbance, and recovery response; they cannot support generic settled-balance causal explanations without transient evidence.",
        "anti_roll_bars": "Front and rear bars couple left/right suspension motion through stiffness, arm position, preload, and attachment state, affecting roll response and tire-demand distribution without exposing exact bar torque.",
        "weight_distribution": "Nose weight and crossweight describe static front/rear and diagonal relationships; phase behavior remains multi-effect and static values never become live wheel loads.",
        "platform": "Ride height, rake, pitch, roll, heave, clearance/contact, speed, and traffic shape an empirical platform regime without yielding exact downforce, aero balance, or drag.",
        "brakes": "Brake bias and available line-pressure response redistribute front/rear braking demand; driver input, hydraulic response, wheel behavior, and vehicle yaw remain separate evidence layers.",
        "differential": "Preload and locking tendency can influence coast, center, and power-on rear wheel-speed/yaw/traction relationships; wheel-speed disagreement alone is not differential failure.",
        "final_drive": "Gear, RPM, final drive, shift point, limiter headroom, and acceleration response matter only after exit-speed carry and driver throttle demand are separated.",
        "steering": "Rack-and-pinion ratio/offset and caster relationships shape steering demand and response; steering torque cannot be converted into exact tire load.",
    }
    mechanism_ids = tuple(item.definition_id for item in mechanisms)
    result = []
    for component, ids in sorted(by_component.items()):
        countereffects = tuple(item for item in mechanism_ids if item not in ids)[:2]
        mapped_mechanisms = tuple(
            item for item in mechanisms if item.definition_id in ids
        )
        phases = tuple(
            phase
            for phase in VehicleDynamicsPhase
            if any(phase in item.relevant_phases for item in mapped_mechanisms)
        )
        regimes = {item.response_regime for item in mapped_mechanisms}
        influence_regime = (
            DynamicResponseRegime.TRANSIENT
            if component == "dampers"
            else next(iter(regimes))
            if len(regimes) == 1
            else DynamicResponseRegime.BOTH
        )
        result.append(
            ComponentInfluence(
                **_base(
                    f"component_influence:{component}",
                    f"{component.replace('_', ' ').title()} candidate influence",
                    physical_roles[component],
                    components=(component,),
                    phases=phases,
                    sources=(
                        _SRC_DAMPER
                        if component == "dampers"
                        else _SRC_PACKAGE
                        if component == "platform"
                        else _SRC_ARCH
                        if component == "steering"
                        else _SRC_MANUAL
                    ),
                    forbidden=(
                        "Component relevance becomes current component causality.",
                        "Component relevance authorizes a setup value or direction.",
                    ),
                ),
                component_id=component,
                mechanism_ids=tuple(ids),
                countereffect_mechanism_ids=countereffects,
                influence_regime=influence_regime,
            )
        )
    return tuple(result)


def _interactions(
    mechanisms: tuple[VehicleDynamicMechanism, ...],
) -> tuple[MechanismInteraction, ...]:
    mechanism_ids = tuple(item.definition_id for item in mechanisms)
    return tuple(
        MechanismInteraction(
            **_base(
                f"interaction:{index}:{source.removeprefix('mechanism:')}:{target.removeprefix('mechanism:')}",
                f"{source.removeprefix('mechanism:').replace('_', ' ')} and {target.removeprefix('mechanism:').replace('_', ' ')}",
                "These candidate mechanisms can influence or mask the same observed response and require a discriminator.",
                components=("tires", "platform"),
                sources=_SRC_SYNTH,
                forbidden=("A generic interaction edge becomes a runtime cause edge.",),
            ),
            source_mechanism_id=source,
            target_mechanism_id=target,
            edge_kind=(
                VehicleDynamicsEdgeKind.COUPLES_WITH
                if index % 2
                else VehicleDynamicsEdgeKind.PHYSICALLY_INFLUENCES
            ),
            interaction_regime=DynamicResponseRegime.BOTH,
            tradeoffs=(
                "Improving one response can increase demand, instability, workload, tire migration, or platform sensitivity elsewhere.",
            ),
        )
        for index, source in enumerate(mechanism_ids)
        for target in (mechanism_ids[(index + 1) % len(mechanism_ids)],)
    )


def _special_knowledge() -> tuple[
    OvalTrackDemandModel,
    StaticLoadDistributionKnowledge,
    TireStateEvolution,
    tuple[DriverVehicleResponseChain, ...],
]:
    oval = OvalTrackDemandModel(
        **_base(
            "oval_track_demand:empirical_v1",
            "Empirical oval track demand",
            "Run-specific banking, radius, curvature, speed, line, transition, straight, and duration context changes lateral-support and platform demand regimes.",
            created_by=("context:track_geometry", "quantity:vehicle_speed"),
            affected_by=("context:line", "context:traffic"),
            affects=("quantity:lateral_demand", "quantity:platform_migration"),
            components=("tires", "platform", "springs", "anti_roll_bars"),
            sources=("sae_2000_01_3570_banked_track_demand", "sae_962531_suspension_asymmetry", *_SRC_SYNTH),
            forbidden=(
                "Banking or radius alone yields exact tire force or dynamic wheel load.",
                "A generic track rule overrides run-specific empirical demand.",
            ),
        ),
        geometry_inputs=("banking", "corner_radius", "curvature", "speed", "line", "transition_severity", "straight_length", "corner_duration"),
        empirical_outputs=("relative_lateral_support_regime", "relative_platform_demand_regime", "corner_duration_context"),
    )
    static = StaticLoadDistributionKnowledge(
        **_base(
            "static_load_distribution:next_gen_v1",
            "Static load distribution",
            "Crossweight and nose weight describe static garage distribution; they do not equal live corner load.",
            created_by=("quantity:static_crossweight_percent", "quantity:static_nose_weight_percent"),
            affected_by=("context:setup_state",),
            affects=("quantity:combined_tire_demand",),
            channels=("cross_weight_percent", "nose_weight_percent"),
            components=("weight_distribution",),
            sources=("sae_962531_suspension_asymmetry", *_SRC_MANUAL),
            forbidden=(
                "Static crossweight becomes dynamic wheel load.",
                "More crossweight is universally tighter in every phase and context.",
            ),
        ),
        static_quantity_ids=("quantity:static_crossweight_percent", "quantity:static_nose_weight_percent"),
        prohibited_dynamic_equivalents=("quantity:exact_wheel_load",),
    )
    evolution = TireStateEvolution(
        **_base(
            "tire_state_evolution:relative_exact_context_v1",
            "Relative tire-state evolution",
            "Pressure, temperature, wear, slip exposure, steering demand, balance, and lap-time may migrate over a qualified run.",
            created_by=("quantity:tire_pressure_state", "quantity:tire_temperature_state", "quantity:tire_wear_state"),
            affected_by=("context:tire_fuel_weather", "quantity:combined_tire_demand"),
            affects=("mechanism:tire_state_migration", "performance:tire_state_migration"),
            channels=("lap", "steering_deg", "yaw_rate", "speed_mph"),
            components=("tires", "alignment"),
            sources=_SRC_MANUAL,
            forbidden=(
                "A short run establishes degradation or cooling behavior.",
                "Relative state migration yields a universal optimum pressure/temperature or exact grip loss.",
            ),
        ),
        evolution_axes=("pressure_rise", "temperature_change", "wear", "slip_exposure", "steering_demand_growth", "balance_migration", "lap_time_falloff"),
    )
    chains = tuple(
        DriverVehicleResponseChain(
            **_base(
                f"driver_chain:{name}",
                label,
                meaning,
                created_by=(driver_input,),
                affected_by=("context:track_geometry", "context:tire_fuel_weather"),
                affects=(performance,),
                components=components,
                sources=_SRC_SYNTH,
                forbidden=("One chain stage is narrated as present without typed existing evidence.",),
            ),
            driver_input_id=driver_input,
            vehicle_demand_id=demand,
            vehicle_response_id=response,
            tire_platform_state_id=tire_state,
            performance_dimension_id=performance,
        )
        for name, label, meaning, driver_input, demand, response, tire_state, performance, components in (
            ("brake", "Brake demand-response chain", "Brake input to longitudinal demand, pitch/yaw response, combined tire state, and measured braking time.", "quantity:brake_input", "quantity:longitudinal_demand", "chassis_response:braking_pitch_yaw", "tire_demand:possible_combined_demand_limitation", "performance:braking_realization", ("brakes", "tires", "platform")),
            ("steering", "Steering demand-response chain", "Steering input to lateral demand, yaw response, front-demand state, and measured center time.", "quantity:steering_input", "quantity:lateral_demand", "chassis_response:steering_yaw_response", "tire_demand:high_relative_demand", "performance:center_rotation", ("steering", "tires", "platform")),
            ("throttle", "Throttle demand-response chain", "Throttle input to rear combined demand, power-on response, rear-demand state, and measured exit time.", "quantity:throttle_input", "quantity:rear_combined_demand", "chassis_response:power_on_yaw_acceleration", "tire_demand:possible_combined_demand_limitation", "performance:exit_traction", ("differential", "final_drive", "tires")),
        )
    )
    return oval, static, evolution, chains


def _nodes(
    definitions: tuple[VehicleDynamicDefinition, ...],
) -> tuple[VehicleDynamicsGraphNode, ...]:
    kind_by_type = {
        VehicleDynamicQuantity: VehicleDynamicsNodeKind.QUANTITY,
        VehicleDynamicMechanism: VehicleDynamicsNodeKind.MECHANISM,
        LoadPath: VehicleDynamicsNodeKind.LOAD_PATH,
        TireDemandState: VehicleDynamicsNodeKind.TIRE_DEMAND_STATE,
        ChassisResponseState: VehicleDynamicsNodeKind.CHASSIS_RESPONSE_STATE,
        TransientResponse: VehicleDynamicsNodeKind.TRANSIENT_RESPONSE,
        SteadyStateResponse: VehicleDynamicsNodeKind.STEADY_STATE_RESPONSE,
        ComponentInfluence: VehicleDynamicsNodeKind.COMPONENT_INFLUENCE,
        MechanismInteraction: VehicleDynamicsNodeKind.MECHANISM,
        DynamicObservationContract: VehicleDynamicsNodeKind.OBSERVATION_CONTRACT,
        OvalTrackDemandModel: VehicleDynamicsNodeKind.LOAD_PATH,
        StaticLoadDistributionKnowledge: VehicleDynamicsNodeKind.LOAD_PATH,
        TireStateEvolution: VehicleDynamicsNodeKind.TIRE_DEMAND_STATE,
        DriverVehicleResponseChain: VehicleDynamicsNodeKind.LOAD_PATH,
    }
    nodes = [
        VehicleDynamicsGraphNode(
            node_id=item.definition_id,
            kind=kind_by_type[type(item)],
            label=item.label,
            definition_id=item.definition_id,
            source_ids=item.source_ids,
        )
        for item in definitions
    ]
    components = sorted(
        {component for item in definitions for component in item.relevant_component_ids}
    )
    nodes.extend(
        VehicleDynamicsGraphNode(
            node_id=f"component:{component}",
            kind=VehicleDynamicsNodeKind.COMPONENT_FAMILY,
            label=component.replace("_", " ").title(),
            source_ids=_SRC_MANUAL,
        )
        for component in components
    )
    contexts = (
        "driver_input", "track_geometry", "line", "traffic", "tire_fuel_weather",
        "setup_state", "build_applicability", "missing_validated_model",
    )
    nodes.extend(
        VehicleDynamicsGraphNode(
            node_id=f"context:{context}",
            kind=VehicleDynamicsNodeKind.CONTEXT,
            label=context.replace("_", " ").title(),
            source_ids=_SRC_SYNTH,
        )
        for context in contexts
    )
    nodes.extend(
        VehicleDynamicsGraphNode(
            node_id=f"phase:{phase.value}",
            kind=VehicleDynamicsNodeKind.PHASE,
            label=phase.value.replace("_", " ").title(),
            source_ids=_SRC_SYNTH,
        )
        for phase in VehicleDynamicsPhase
    )
    performance_ids = sorted(
        {p32 for item in definitions if isinstance(item, VehicleDynamicMechanism) for p32 in item.p32_performance_mechanism_ids}
        | {"measured_elapsed_time"}
    )
    nodes.extend(
        VehicleDynamicsGraphNode(
            node_id=f"performance:{performance_id}",
            kind=VehicleDynamicsNodeKind.PERFORMANCE_DIMENSION,
            label=performance_id.replace("_", " ").title(),
            source_ids=_SRC_SYNTH,
        )
        for performance_id in performance_ids
    )
    nodes.extend(
        VehicleDynamicsGraphNode(
            node_id=f"context:source:{source.source_id}",
            kind=VehicleDynamicsNodeKind.CONTEXT,
            label=f"Reviewed source {source.source_id}",
            source_ids=(source.source_id,),
        )
        for source in _SOURCES
    )
    return tuple(nodes)


def _edges(
    mechanisms: tuple[VehicleDynamicMechanism, ...],
    component_influences: tuple[ComponentInfluence, ...],
    tire_states: tuple[TireDemandState, ...],
) -> tuple[VehicleDynamicsGraphEdge, ...]:
    records: list[tuple[str, str, VehicleDynamicsEdgeKind, tuple[str, ...]]] = []
    for mechanism in mechanisms:
        records.extend(
            (
                ("context:driver_input", mechanism.definition_id, VehicleDynamicsEdgeKind.PHYSICALLY_INFLUENCES, mechanism.source_ids),
                (mechanism.definition_id, f"performance:{mechanism.p32_performance_mechanism_ids[0]}", VehicleDynamicsEdgeKind.EXPECTED_TO_AFFECT, mechanism.source_ids),
                (mechanism.definition_id, "quantity:vehicle_speed", VehicleDynamicsEdgeKind.REQUIRES_MEASUREMENT_OF, mechanism.source_ids),
                (mechanism.definition_id, "context:traffic", VehicleDynamicsEdgeKind.CONFOUNDED_BY, mechanism.source_ids),
            )
        )
    for influence in component_influences:
        records.append((f"component:{influence.component_id}", influence.mechanism_ids[0], VehicleDynamicsEdgeKind.COUPLES_WITH, influence.source_ids))
    for tire_state in tire_states:
        records.append(("quantity:combined_tire_demand", tire_state.definition_id, VehicleDynamicsEdgeKind.CHANGES_DEMAND_ON, tire_state.source_ids))
    unique: dict[tuple[str, str, VehicleDynamicsEdgeKind], tuple[str, ...]] = {}
    for source, target, kind, source_ids in records:
        key = (source, target, kind)
        unique[key] = tuple(dict.fromkeys((*unique.get(key, ()), *source_ids)))
    return tuple(
        VehicleDynamicsGraphEdge(
            edge_id=f"vdedge:{canonical_json_sha256((source, target, kind.value))[:24]}",
            source_node_id=source,
            target_node_id=target,
            kind=kind,
            source_ids=source_ids,
        )
        for (source, target, kind), source_ids in sorted(
            unique.items(), key=lambda item: (item[0][0], item[0][1], item[0][2].value)
        )
    )


@lru_cache(maxsize=1)
def compile_next_gen_oval_knowledge_graph() -> VehicleDynamicsKnowledgeGraph:
    """Compile one immutable reviewed graph; runtime performs no network access."""
    quantities = _quantities()
    mechanisms = _mechanisms()
    observations = _observation_contracts(mechanisms)
    load_paths = _load_paths()
    tire_states = _tire_demand_states()
    chassis_states = _chassis_states()
    transient, steady = _responses()
    influences = _component_influences(mechanisms)
    interactions = _interactions(mechanisms)
    oval, static, evolution, chains = _special_knowledge()
    definitions: tuple[VehicleDynamicDefinition, ...] = (
        *quantities,
        *mechanisms,
        *load_paths,
        *tire_states,
        *chassis_states,
        *transient,
        *steady,
        *influences,
        *interactions,
        *observations,
        oval,
        static,
        evolution,
        *chains,
    )
    nodes = _nodes(definitions)
    edges = _edges(mechanisms, influences, tire_states)
    return build_vehicle_dynamics_knowledge_graph(
        {
            "knowledge_version": _KNOWLEDGE_VERSION,
            "applicability": _APP,
            "sources": _SOURCES,
            "external_identity_namespaces": _EXTERNAL_IDENTITY_NAMESPACES,
            "quantities": quantities,
            "mechanisms": mechanisms,
            "load_paths": load_paths,
            "tire_demand_states": tire_states,
            "chassis_response_states": chassis_states,
            "transient_responses": transient,
            "steady_state_responses": steady,
            "component_influences": influences,
            "mechanism_interactions": interactions,
            "observation_contracts": observations,
            "oval_track_demand_model": oval,
            "static_load_distribution": static,
            "tire_state_evolution": evolution,
            "driver_response_chains": chains,
            "forbidden_controls": (
                ForbiddenVehicleControl(
                    control_id="track_bar",
                    physical_reason="The Next Gen independent rear suspension replaces the solid axle and has no live rear track-bar adjustment.",
                    source_ids=("nascar_next_gen_architecture_2021_05_05",),
                    applicability=_APP,
                ),
                ForbiddenVehicleControl(
                    control_id="truck_arm_mount",
                    physical_reason="Next Gen rear wheel control uses independent suspension; legacy solid-axle truck-arm geometry is not a live control.",
                    source_ids=("nascar_next_gen_architecture_2021_05_05",),
                    applicability=_APP,
                ),
            ),
            "nodes": nodes,
            "edges": edges,
            "unavailable_quantity_ids": _UNAVAILABLE,
        }
    )


@lru_cache(maxsize=1)
def compile_next_gen_oval_runtime_trust_manifest(
) -> VehicleDynamicsRuntimeTrustManifest:
    """Project the compact runtime authenticity surface from the frozen graph."""
    graph = compile_next_gen_oval_knowledge_graph()
    runtime_mechanisms: list[VehicleDynamicsRuntimeMechanismTrust] = []
    for mechanism in sorted(graph.mechanisms, key=lambda item: item.definition_id):
        support_contracts = tuple(
            graph.observation_contract(contract_id)
            for contract_id in mechanism.support_contract_ids
        )
        support_layers = support_contracts[0].required_evidence_layers
        if any(
            contract.required_evidence_layers != support_layers
            or contract.required_measured_channels
            != mechanism.required_measured_channels
            for contract in support_contracts
        ):
            raise ValueError(
                "runtime trust requires reciprocal support-contract layers and channels"
            )
        runtime_mechanisms.append(
            VehicleDynamicsRuntimeMechanismTrust(
                mechanism_id=mechanism.definition_id,
                p20_mechanism_ids=mechanism.p20_mechanism_ids,
                p32_performance_mechanism_ids=(
                    mechanism.p32_performance_mechanism_ids
                ),
                allowed_time_origin_kinds=mechanism.allowed_time_origin_kinds,
                relevant_phases=mechanism.relevant_phases,
                response_regime=mechanism.response_regime,
                component_family_ids=mechanism.p26_component_family_ids,
                inspection_tool_id=mechanism.inspection_tool_id,
                support_observation_contract_ids=mechanism.support_contract_ids,
                contradiction_observation_contract_ids=(
                    mechanism.contradiction_contract_ids
                ),
                discriminator_observation_contract_ids=(
                    mechanism.discriminator_contract_ids
                ),
                support_required_evidence_layers=support_layers,
                support_required_channel_groups=(
                    _mechanism_support_channel_groups(mechanism)
                ),
                focus_artifact_prefix=(
                    f"p35.focus."
                    f"{mechanism.inspection_tool_id.value.removeprefix('inspect_')}:"
                ),
            )
        )
    mechanisms = tuple(runtime_mechanisms)
    return build_vehicle_dynamics_runtime_trust_manifest(
        {
            "graph_id": graph.graph_id,
            "graph_version": graph.graph_version,
            "knowledge_version": graph.knowledge_version,
            "knowledge_graph_sha256": graph.content_sha256,
            "mechanisms": mechanisms,
        }
    )


def resolve_next_gen_oval_knowledge_graph(
    *,
    car_path: str | None,
    car_version: str | None,
    iracing_build_version: str | None,
    track_package: str | None,
) -> VehicleDynamicsKnowledgeResolution:
    requested = {
        "requested_car_path": car_path or "unavailable",
        "requested_car_version": car_version or "unavailable",
        "requested_iracing_build_version": iracing_build_version or "unavailable",
        "requested_track_package": track_package or "unavailable",
    }
    if not all((car_path, car_version, iracing_build_version, track_package)):
        return VehicleDynamicsKnowledgeResolution(
            status="unavailable",
            blocker_reasons=("Exact car path, car version, iRacing build, and track package are required.",),
            **requested,
        )
    graph = compile_next_gen_oval_knowledge_graph()
    if car_path not in graph.applicability.car_paths or track_package not in graph.applicability.track_packages:
        return VehicleDynamicsKnowledgeResolution(
            status="incompatible",
            blocker_reasons=("The reviewed P35 graph does not cover this car path or track package.",),
            **requested,
        )
    if (
        _version_key(car_version) < _version_key(graph.applicability.car_version_min)
        or _version_key(car_version) > _version_key(graph.applicability.car_version_max)
        or _version_key(iracing_build_version)
        < _version_key(graph.applicability.iracing_build_min)
        or _version_key(iracing_build_version)
        > _version_key(graph.applicability.iracing_build_max)
    ):
        return VehicleDynamicsKnowledgeResolution(
            status="unreviewed_build",
            blocker_reasons=("The exact car version/build is outside reviewed P35 applicability and requires review.",),
            **requested,
        )
    if not graph.applicability.covers(
        car_path=car_path,
        car_version=car_version,
        iracing_build_version=iracing_build_version,
        track_package=track_package,
    ):
        return VehicleDynamicsKnowledgeResolution(
            status="incompatible",
            blocker_reasons=("The reviewed P35 graph cannot resolve the supplied exact applicability.",),
            **requested,
        )
    return VehicleDynamicsKnowledgeResolution(status="ready", graph=graph, **requested)


def _version_key(value: str) -> tuple[int, tuple[int, ...] | tuple[str, ...]]:
    parts = value.split(".")
    if parts and all(part.isdigit() for part in parts):
        return (0, tuple(int(part) for part in parts))
    return (1, (value,))


__all__ = [
    "compile_next_gen_oval_knowledge_graph",
    "resolve_next_gen_oval_knowledge_graph",
]
