from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
    compile_next_gen_oval_knowledge_graph,
    compile_next_gen_oval_runtime_trust_manifest,
    resolve_next_gen_oval_knowledge_graph,
    unmet_runtime_support_channel_requirement_ids,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.performance_intelligence import TimeOriginKind
from racelab_engine.models.vehicle_dynamics_knowledge import (
    DynamicsChainStageKind,
    PhaseResponseMetric,
    PerformanceMechanismAssessment,
    QuantitySemantics,
    TireDemandLevel,
    VehicleDynamicsChainStage,
    VehicleDynamicsEdgeKind,
    VehicleDynamicsFocusArtifact,
    VehicleDynamicsInspectionToolId,
    VehicleDynamicsKnowledgeGraph,
    VehicleDynamicsNodeKind,
    VehicleDynamicsPhase,
    VehicleDynamicsRuntimeTrustManifest,
    VehicleResponseObservation,
    build_performance_mechanism_assessment,
    build_vehicle_dynamics_knowledge_graph,
    performance_mechanism_assessment_hash,
    vehicle_dynamics_graph_hash,
    vehicle_dynamics_runtime_trust_hash,
)


SHA = "a" * 64


def _graph_payload() -> dict[str, object]:
    return compile_next_gen_oval_knowledge_graph().model_dump(mode="json")


def _stage(
    stage: DynamicsChainStageKind,
    artifact_id: str,
    channel: str,
    *,
    state: EvidenceState = EvidenceState.MEASURED,
) -> VehicleDynamicsChainStage:
    return VehicleDynamicsChainStage(
        stage=stage,
        evidence_state=state,
        source_artifact_ids=(artifact_id,),
        source_channels=(channel,),
        summary=f"Typed {stage.value} evidence.",
    )


def _assessment() -> PerformanceMechanismAssessment:
    graph = compile_next_gen_oval_knowledge_graph()
    mechanism = graph.mechanism("mechanism:center_rotation_deficit")
    discriminator = mechanism.discriminator_contract_ids[0]
    chain = (
        _stage(DynamicsChainStageKind.DRIVER_INPUT, "crew:driver", "steering_deg"),
        _stage(DynamicsChainStageKind.VEHICLE_DEMAND, "crew:demand", "steering_deg"),
        _stage(DynamicsChainStageKind.VEHICLE_RESPONSE, "crew:response", "yaw_rate"),
        _stage(
            DynamicsChainStageKind.TIRE_PLATFORM_STATE,
            "crew:tire",
            "steering_deg",
            state=EvidenceState.ESTIMATED_PROXY,
        ),
        _stage(
            DynamicsChainStageKind.TIME_CONSEQUENCE,
            "opportunity:center",
            "session_time",
        ),
    )
    support = VehicleDynamicsFocusArtifact(
        artifact_id=f"p35.focus.steady_state_balance:{'1' * 24}",
        mechanism_id=mechanism.definition_id,
        inspection_tool_id=mechanism.inspection_tool_id,
        stage=DynamicsChainStageKind.VEHICLE_RESPONSE,
        evidence_state=EvidenceState.MEASURED,
        source_artifact_ids=("crew:response",),
        source_channels=("yaw_rate",),
        lap_numbers=(4, 8),
        lap_pct_start=32.0,
        lap_pct_end=41.0,
        phase="center",
        polarity="support",
        summary="Matched steering demand co-occurs with weaker center yaw response.",
    )
    uncertainty = VehicleDynamicsFocusArtifact(
        artifact_id=f"p35.focus.steady_state_balance:{'2' * 24}",
        mechanism_id=mechanism.definition_id,
        observation_contract_id=discriminator,
        inspection_tool_id=mechanism.inspection_tool_id,
        stage=DynamicsChainStageKind.TIRE_PLATFORM_STATE,
        evidence_state=EvidenceState.NEEDS_CONFIRMATION,
        source_artifact_ids=("crew:tire",),
        source_channels=("steering_deg",),
        polarity="uncertainty",
        summary="Tire-state and roll-platform candidates remain unresolved.",
        blocker_reasons=("The required tire/platform discriminator is incomplete.",),
    )
    return build_performance_mechanism_assessment(
        {
            "run_id": "run-1",
            "session_id": "session-1",
            "objective_id": "race_long_run",
            "car_path": "stockcars chevycamarozl12022",
            "car_version": "2026.06.08.02",
            "iracing_build_version": "2026.06.24.02",
            "track_package": "oval",
            "vehicle_runtime_identity_sha256": SHA,
            "graph_id": graph.graph_id,
            "graph_version": graph.graph_version,
            "knowledge_version": graph.knowledge_version,
            "knowledge_graph_sha256": graph.content_sha256,
            "p19_reasoning_snapshot_sha256": "b" * 64,
            "p20_state_revision": "c" * 64,
            "p20_profile_hash": None,
            "p26_graph_version": "p26.vehicle-systems.v3",
            "p26_knowledge_graph_sha256": "d" * 64,
            "p32_projection_sha256": "e" * 64,
            "p32_performance_mechanism_ids": ("center_rotation",),
            "performance_opportunity_ids": ("opportunity:center",),
            "measured_time_consequence_available": True,
            "chain": chain,
            "tire_demand_state_ids": ("tire_demand:high_relative_demand",),
            "load_path_ids": ("load_path:center",),
            "response_regime": "steady_state",
            "candidates": (
                {
                    "mechanism_id": mechanism.definition_id,
                    "p32_performance_mechanism_ids": ("center_rotation",),
                    "support_artifact_ids": (support.artifact_id,),
                    "contradiction_artifact_ids": (uncertainty.artifact_id,),
                    "discriminator_contract_ids": mechanism.discriminator_contract_ids,
                    "component_family_ids": mechanism.p26_component_family_ids,
                    "relevance": "candidate",
                },
            ),
            "focus_artifacts": (support, uncertainty),
            "strongest_support_artifact_id": support.artifact_id,
            "strongest_contradiction_artifact_id": uncertainty.artifact_id,
            "next_discriminator_contract_id": discriminator,
            "unavailable_quantity_ids": graph.unavailable_quantity_ids,
            "traffic_blocked": False,
            "applicability_state": "ready",
        }
    )


def test_reviewed_graph_is_deterministic_typed_and_non_authoritative() -> None:
    first = compile_next_gen_oval_knowledge_graph()
    compile_next_gen_oval_knowledge_graph.cache_clear()
    second = compile_next_gen_oval_knowledge_graph()

    assert first == second
    assert first.content_sha256 == vehicle_dynamics_graph_hash(first)
    assert first.graph_id == f"p35vdg_{first.content_sha256[:24]}"
    assert first.graph_version.endswith(first.content_sha256[:12])
    assert len(first.sources) == 13
    assert len(first.quantities) == 56
    assert len(first.mechanisms) == 16
    assert len(first.load_paths) == 8
    assert len(first.observation_contracts) == 32
    assert len(first.driver_response_chains) == 3
    assert first.authority == "candidate_mechanism_knowledge_only"
    assert first.setup_authorized is False
    assert first.p19_terminal_authority is True


def test_every_static_statement_is_reviewed_build_scoped_and_content_addressed() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    assert {source.tier.value for source in graph.sources} == {
        "official_iracing_documentation",
        "official_nascar_technical_documentation",
        "peer_reviewed_vehicle_dynamics_research",
        "reviewed_racerzlab_engineering_synthesis",
    }
    assert all(source.review_status == "reviewed" for source in graph.sources)
    assert all(re.fullmatch(r"[0-9a-f]{64}", source.local_digest) for source in graph.sources)
    assert all(source.source_uri.startswith(("https://", "repo://")) for source in graph.sources)
    assert graph.applicability.car_version_min == graph.applicability.car_version_max == "2026.06.08.02"
    assert graph.applicability.iracing_build_max == "2026.06.24.02"
    definitions = (
        *graph.quantities,
        *graph.mechanisms,
        *graph.load_paths,
        *graph.tire_demand_states,
        *graph.chassis_response_states,
        *graph.transient_responses,
        *graph.steady_state_responses,
        *graph.component_influences,
        *graph.mechanism_interactions,
        *graph.observation_contracts,
        graph.oval_track_demand_model,
        graph.static_load_distribution,
        graph.tire_state_evolution,
        *graph.driver_response_chains,
    )
    assert all(item.applicability == graph.applicability for item in definitions)
    assert all(item.source_ids and item.forbidden_inferences for item in definitions)


def test_runtime_trust_manifest_is_compact_deterministic_and_graph_derived() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    first = compile_next_gen_oval_runtime_trust_manifest()
    compile_next_gen_oval_runtime_trust_manifest.cache_clear()
    second = compile_next_gen_oval_runtime_trust_manifest()

    assert first == second
    assert first.graph_id == graph.graph_id
    assert first.graph_version == graph.graph_version
    assert first.knowledge_version == graph.knowledge_version
    assert first.knowledge_graph_sha256 == graph.content_sha256
    assert first.runtime_trust_sha256 == vehicle_dynamics_runtime_trust_hash(first)
    assert len(first.mechanisms) == len(graph.mechanisms)
    assert tuple(item.mechanism_id for item in first.mechanisms) == tuple(
        sorted(item.definition_id for item in graph.mechanisms)
    )
    for trust in first.mechanisms:
        mechanism = graph.mechanism(trust.mechanism_id)
        assert trust.p20_mechanism_ids == mechanism.p20_mechanism_ids
        assert trust.p32_performance_mechanism_ids == (
            mechanism.p32_performance_mechanism_ids
        )
        assert trust.allowed_time_origin_kinds == mechanism.allowed_time_origin_kinds
        assert trust.relevant_phases == mechanism.relevant_phases
        assert trust.response_regime is mechanism.response_regime
        assert trust.component_family_ids == mechanism.p26_component_family_ids
        assert trust.inspection_tool_id is mechanism.inspection_tool_id
        assert trust.support_observation_contract_ids == mechanism.support_contract_ids
        assert (
            trust.contradiction_observation_contract_ids
            == mechanism.contradiction_contract_ids
        )
        assert (
            trust.discriminator_observation_contract_ids
            == mechanism.discriminator_contract_ids
        )
        support_contract = graph.observation_contract(
            mechanism.support_contract_ids[0]
        )
        assert (
            trust.support_required_evidence_layers
            == support_contract.required_evidence_layers
            == tuple(DynamicsChainStageKind)
        )
        assert trust.support_required_channel_groups
        assert trust.focus_artifact_prefix == (
            f"p35.focus.{mechanism.inspection_tool_id.value.removeprefix('inspect_')}:"
        )

    tampered = first.model_dump(mode="json")
    tampered["mechanisms"][0]["relevant_phases"] = ["straight"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="hash does not match"):
        VehicleDynamicsRuntimeTrustManifest.model_validate(tampered)


def test_runtime_trust_brake_support_requires_real_brake_pressure_and_wheel_groups() -> None:
    manifest = compile_next_gen_oval_runtime_trust_manifest()
    trust = next(
        item
        for item in manifest.mechanisms
        if item.mechanism_id == "mechanism:brake_entry_instability"
    )
    hostile = {
        DynamicsChainStageKind.DRIVER_INPUT: ("SteeringWheelAngle",),
        DynamicsChainStageKind.VEHICLE_RESPONSE: ("YawRate",),
    }

    blockers = unmet_runtime_support_channel_requirement_ids(trust, hostile)

    assert {
        "support_channel:brake_input",
        "support_channel:front_brake_pressure",
        "support_channel:rear_brake_pressure",
        "support_channel:front_wheel_response",
        "support_channel:rear_wheel_response",
    } <= set(blockers)
    assert not blockers == ()
    assert unmet_runtime_support_channel_requirement_ids(
        trust,
        {
            DynamicsChainStageKind.DRIVER_INPUT: (
                "Brake",
                "SteeringWheelAngle",
            ),
            DynamicsChainStageKind.VEHICLE_RESPONSE: (
                "LFbrakeLinePress",
                "RFbrakeLinePress",
                "LRbrakeLinePress",
                "RRbrakeLinePress",
                "LFspeed",
                "RFspeed",
                "LRspeed",
                "RRspeed",
                "YawRate",
            ),
        },
    ) == ()

    complete_response = (
        "LFbrakeLinePress",
        "RFbrakeLinePress",
        "LRbrakeLinePress",
        "RRbrakeLinePress",
        "LFspeed",
        "RFspeed",
        "LRspeed",
        "RRspeed",
        "YawRate",
    )
    expected_group = {
        "LFbrakeLinePress": "support_channel:front_brake_pressure",
        "RFbrakeLinePress": "support_channel:front_brake_pressure",
        "LRbrakeLinePress": "support_channel:rear_brake_pressure",
        "RRbrakeLinePress": "support_channel:rear_brake_pressure",
        "LFspeed": "support_channel:front_wheel_response",
        "RFspeed": "support_channel:front_wheel_response",
        "LRspeed": "support_channel:rear_wheel_response",
        "RRspeed": "support_channel:rear_wheel_response",
    }
    for missing_channel, blocker_id in expected_group.items():
        missing_one = tuple(
            channel for channel in complete_response if channel != missing_channel
        )
        assert blocker_id in unmet_runtime_support_channel_requirement_ids(
            trust,
            {
                DynamicsChainStageKind.DRIVER_INPUT: (
                    "Brake",
                    "SteeringWheelAngle",
                ),
                DynamicsChainStageKind.VEHICLE_RESPONSE: missing_one,
            },
        )


def test_runtime_trust_non_brake_support_requires_typed_powertrain_channels() -> None:
    manifest = compile_next_gen_oval_runtime_trust_manifest()
    trust = next(
        item
        for item in manifest.mechanisms
        if item.mechanism_id == "mechanism:gearing_headroom_limitation"
    )

    blockers = unmet_runtime_support_channel_requirement_ids(
        trust,
        {
            DynamicsChainStageKind.DRIVER_INPUT: ("SteeringWheelAngle",),
            DynamicsChainStageKind.VEHICLE_RESPONSE: ("YawRate",),
        },
    )

    assert {
        "support_channel:throttle_pct",
        "support_channel:rpm",
        "support_channel:gear",
        "support_channel:speed_mph",
        "support_channel:long_accel",
    } == set(blockers)
    assert unmet_runtime_support_channel_requirement_ids(
        trust,
        {
            DynamicsChainStageKind.DRIVER_INPUT: ("Throttle",),
            DynamicsChainStageKind.VEHICLE_RESPONSE: (
                "RPM",
                "Gear",
                "Speed",
                "LongAccel",
            ),
        },
    ) == ()


def test_runtime_trust_roll_support_rejects_one_corner_shock_evidence() -> None:
    manifest = compile_next_gen_oval_runtime_trust_manifest()
    trust = next(
        item
        for item in manifest.mechanisms
        if item.mechanism_id == "mechanism:front_roll_support_limitation"
    )
    one_corner = {
        DynamicsChainStageKind.DRIVER_INPUT: ("SteeringWheelAngle",),
        DynamicsChainStageKind.VEHICLE_RESPONSE: ("YawRate", "LFshockDefl"),
    }

    assert "support_channel:front_shock_deflection_pair" in (
        unmet_runtime_support_channel_requirement_ids(trust, one_corner)
    )
    assert unmet_runtime_support_channel_requirement_ids(
        trust,
        {
            DynamicsChainStageKind.DRIVER_INPUT: ("SteeringWheelAngle",),
            DynamicsChainStageKind.VEHICLE_RESPONSE: (
                "YawRate",
                "LFshockDefl",
                "RFshockDefl",
            ),
        },
    ) == ()


def test_runtime_trust_channel_groups_reject_duplicates_and_unknown_widening() -> None:
    manifest = compile_next_gen_oval_runtime_trust_manifest()
    payload = manifest.model_dump(mode="json")
    first_group = payload["mechanisms"][0]["support_required_channel_groups"][0]
    first_alias = first_group["alternatives"][0]["accepted_source_channel_ids"][0]
    first_group["alternatives"][0]["accepted_source_channel_ids"].append(first_alias)
    with pytest.raises(ValidationError, match="source-channel identities"):
        VehicleDynamicsRuntimeTrustManifest.model_validate(payload)

    brake = next(
        item
        for item in manifest.mechanisms
        if item.mechanism_id == "mechanism:brake_entry_instability"
    )
    assert unmet_runtime_support_channel_requirement_ids(
        brake,
        {
            DynamicsChainStageKind.DRIVER_INPUT: ("BrakeLikeMagic",),
            DynamicsChainStageKind.VEHICLE_RESPONSE: (
                "SomePressureSubstring",
                "WheelSpeedGuess",
                "YawRate",
                "SteeringWheelAngle",
            ),
        },
    )


def test_graph_uses_only_six_noncausal_edge_kinds_and_all_are_exercised() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    assert {edge.kind for edge in graph.edges} == set(VehicleDynamicsEdgeKind)
    assert all(edge.authority == "engineering_expectation_only" for edge in graph.edges)
    assert all(edge.runtime_cause_authorized is False for edge in graph.edges)
    assert "causes" not in graph.model_dump_json().casefold()


def test_unavailable_physics_remains_explicit_and_unpublishable() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    required = {
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
    }
    assert required == set(graph.unavailable_quantity_ids)
    for quantity_id in required:
        quantity = graph.quantity(quantity_id)
        assert quantity.semantics is QuantitySemantics.UNAVAILABLE
        assert quantity.runtime_publishable is False
        assert quantity.exact_value_authorized is False


def test_crossweight_is_static_and_cannot_become_dynamic_wheel_load() -> None:
    knowledge = compile_next_gen_oval_knowledge_graph().static_load_distribution
    assert "quantity:static_crossweight_percent" in knowledge.static_quantity_ids
    assert knowledge.prohibited_dynamic_equivalents == ("quantity:exact_wheel_load",)
    assert knowledge.universal_balance_direction_authorized is False
    assert "do not equal live corner load" in knowledge.physical_meaning


def test_spring_and_damper_roles_do_not_collapse_steady_center_reasoning() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    center = graph.mechanism("mechanism:center_rotation_deficit")
    disturbance = graph.mechanism("mechanism:disturbance_compliance_issue")
    assert center.response_regime.value == "steady_state"
    assert "dampers" not in center.p26_component_family_ids
    assert center.inspection_tool_id is VehicleDynamicsInspectionToolId.INSPECT_STEADY_STATE_BALANCE
    assert disturbance.response_regime.value == "transient"
    assert disturbance.inspection_tool_id is VehicleDynamicsInspectionToolId.INSPECT_TRANSIENT_SETTLING
    damper = next(item for item in graph.component_influences if item.component_id == "dampers")
    assert damper.influence_regime.value == "transient"
    assert VehicleDynamicsPhase.CENTER not in damper.relevant_phases
    assert graph.quantity(
        "quantity:spring_force_displacement_relationship"
    ).definition_id != graph.quantity(
        "quantity:damper_force_velocity_relationship"
    ).definition_id
    assert all(item.settling_evidence_required for item in graph.transient_responses)
    assert all(item.sustained_window_required for item in graph.steady_state_responses)


def test_carried_exit_loss_cannot_become_gearing_diagnosis() -> None:
    gearing = compile_next_gen_oval_knowledge_graph().mechanism(
        "mechanism:gearing_headroom_limitation"
    )
    contradiction = compile_next_gen_oval_knowledge_graph().observation_contract(
        gearing.contradiction_contract_ids[0]
    )
    assert gearing.allowed_time_origin_kinds == (TimeOriginKind.LOCAL_GENERATION,)
    assert TimeOriginKind.CARRIED_IN not in gearing.allowed_time_origin_kinds
    assert "carried from exit" in contradiction.physical_meaning
    assert gearing.inspection_tool_id is VehicleDynamicsInspectionToolId.INSPECT_GEAR_ACCELERATION_RESPONSE
    assert gearing.relevant_phases == (
        VehicleDynamicsPhase.STRAIGHT,
        VehicleDynamicsPhase.FOLLOWING_STRAIGHT,
    )
    brake = compile_next_gen_oval_knowledge_graph().mechanism(
        "mechanism:brake_entry_instability"
    )
    assert brake.relevant_phases == (
        VehicleDynamicsPhase.BRAKE,
        VehicleDynamicsPhase.ENTRY,
    )
    assert VehicleDynamicsPhase.CENTER not in brake.relevant_phases


def test_brake_response_is_typed_without_inventing_force_or_abs_validity() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    front = graph.quantity("quantity:front_brake_line_pressure_state")
    rear = graph.quantity("quantity:rear_brake_line_pressure_state")
    distribution = graph.quantity(
        "quantity:relative_front_rear_brake_pressure_distribution"
    )
    lock = graph.quantity("quantity:wheel_lock_evidence_state")
    abs_state = graph.quantity("quantity:abs_intervention_state")

    assert front.required_measured_channels == (
        "lf_brake_line_pressure_bar",
        "rf_brake_line_pressure_bar",
    )
    assert rear.required_measured_channels == (
        "lr_brake_line_pressure_bar",
        "rr_brake_line_pressure_bar",
    )
    assert distribution.semantics is QuantitySemantics.RELATIVE_STATE
    assert distribution.required_measured_channels == (
        *front.required_measured_channels,
        *rear.required_measured_channels,
    )
    assert lock.semantics is QuantitySemantics.QUALITATIVE_PROXY
    assert {
        "lf_speed",
        "rf_speed",
        "lr_speed",
        "rr_speed",
        "speed_mph",
    } <= set(lock.required_measured_channels)
    assert abs_state.semantics is QuantitySemantics.QUALITATIVE_PROXY
    assert abs_state.exact_value_authorized is False
    assert abs_state.manifest_validity_required_channels == (
        "brake_abs_active",
        "brake_abs_cut_01",
    )

    brake = graph.mechanism("mechanism:brake_entry_instability")
    required_brake_proxies = {
        front.definition_id,
        rear.definition_id,
        distribution.definition_id,
        lock.definition_id,
        abs_state.definition_id,
    }
    assert required_brake_proxies <= set(brake.valid_proxy_ids)
    for contract_id in brake.discriminator_contract_ids:
        contract = graph.observation_contract(contract_id)
        assert required_brake_proxies <= set(contract.valid_proxy_ids)
        assert set(distribution.required_measured_channels) <= set(
            contract.required_measured_channels
        )


def test_abs_evidence_fails_closed_without_exact_manifest_validity_contract() -> None:
    missing_gate = _graph_payload()
    abs_state = next(
        item
        for item in missing_gate["quantities"]  # type: ignore[union-attr]
        if item["definition_id"] == "quantity:abs_intervention_state"
    )
    abs_state["manifest_validity_required_channels"] = []
    with pytest.raises(
        ValidationError, match="explicit runtime-manifest channel validity"
    ):
        VehicleDynamicsKnowledgeGraph.model_validate(
            missing_gate, context={"skip_content_hash": True}
        )

    unknown_gate = _graph_payload()
    abs_state = next(
        item
        for item in unknown_gate["quantities"]  # type: ignore[union-attr]
        if item["definition_id"] == "quantity:abs_intervention_state"
    )
    abs_state["manifest_validity_required_channels"] = ["invented_abs_validity"]
    with pytest.raises(ValidationError, match="manifest-validity channels"):
        VehicleDynamicsKnowledgeGraph.model_validate(
            unknown_gate, context={"skip_content_hash": True}
        )


def test_higher_steering_lower_yaw_is_candidate_not_component_cause() -> None:
    mechanism = compile_next_gen_oval_knowledge_graph().mechanism(
        "mechanism:center_rotation_deficit"
    )
    assert len(mechanism.p26_component_family_ids) > 1
    assert mechanism.current_cause_authorized is False
    assert mechanism.component_cause_authorized is False
    assert mechanism.setup_authorized is False


def test_next_gen_irs_has_no_legacy_solid_axle_runtime_path() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    response_ids = {item.definition_id for item in graph.chassis_response_states}
    assert "chassis_response:independent_rear_wheel_motion" in response_ids
    assert "chassis_response:rear_camber_toe_response" in response_ids
    assert any(
        item.component_id == "steering" for item in graph.component_influences
    )
    assert {item.control_id for item in graph.forbidden_controls} == {
        "track_bar",
        "truck_arm_mount",
    }
    graph_without_forbidden = graph.model_dump_json(
        exclude={"forbidden_controls"}
    ).casefold()
    assert "track_bar" not in graph_without_forbidden
    assert "track bar" not in graph_without_forbidden
    assert "truck_arm" not in graph_without_forbidden
    assert "truck arm" not in graph_without_forbidden


def test_current_build_resolves_and_later_build_fails_closed() -> None:
    current = resolve_next_gen_oval_knowledge_graph(
        car_path="stockcars chevycamarozl12022",
        car_version="2026.06.08.02",
        iracing_build_version="2026.06.24.02",
        track_package="oval",
    )
    later = resolve_next_gen_oval_knowledge_graph(
        car_path="stockcars chevycamarozl12022",
        car_version="2026.06.08.02",
        iracing_build_version="2026.06.24.03",
        track_package="oval",
    )
    assert current.status == "ready" and current.graph is not None
    assert later.status == "unreviewed_build" and later.graph is None
    assert later.blocker_reasons


def test_banking_and_combined_demand_are_qualitative_only() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    oval = graph.oval_track_demand_model
    combined = next(
        item
        for item in graph.tire_demand_states
        if item.demand_level is TireDemandLevel.POSSIBLE_COMBINED_DEMAND_LIMITATION
    )
    assert oval.run_specific is True
    assert oval.exact_wheel_load_authorized is False
    assert oval.exact_tire_force_authorized is False
    assert combined.exact_tire_force_authorized is False
    assert combined.exact_grip_limit_authorized is False
    assert "quantity:exact_friction_coefficient" in combined.unavailable_quantity_ids


def test_traffic_blocks_platform_attribution_in_typed_contracts() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    platform = graph.mechanism("mechanism:platform_roll_migration")
    contracts = tuple(graph.observation_contract(item) for item in platform.discriminator_contract_ids)
    assert all(item.traffic_clean_required for item in contracts)
    assert platform.inspection_tool_id is VehicleDynamicsInspectionToolId.INSPECT_TRAFFIC_PLATFORM_RESPONSE


def test_tire_state_evolution_cannot_claim_exact_grip_loss_or_universal_optimum() -> None:
    evolution = compile_next_gen_oval_knowledge_graph().tire_state_evolution
    assert evolution.exact_context_required is True
    assert evolution.universal_optimum_authorized is False
    assert evolution.exact_grip_loss_authorized is False
    assert len(evolution.evolution_axes) == 7


def test_p20_p26_p32_and_p19_authority_boundaries_are_explicit() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    assert all(item.p20_observation_remains_distinct for item in graph.observation_contracts)
    assert all(item.current_observation_authorized is False for item in graph.observation_contracts)
    assert all(item.candidate_mapping_only for item in graph.component_influences)
    assert all(not item.setup_authorized for item in graph.component_influences)
    assert all(item.p32_performance_mechanism_ids for item in graph.mechanisms)
    assert graph.p19_terminal_authority is True
    assert graph.setup_authorized is False


def test_load_paths_are_connected_by_identity_and_physical_quantity() -> None:
    paths = compile_next_gen_oval_knowledge_graph().load_paths
    assert [item.sequence_index for item in paths] == list(range(8))
    for index, item in enumerate(paths):
        assert item.prior_load_path_id == (paths[index - 1].definition_id if index else None)
        assert item.next_load_path_id == (
            paths[index + 1].definition_id if index + 1 < len(paths) else None
        )
        if index + 1 < len(paths):
            assert set(item.output_quantity_ids) & set(paths[index + 1].input_quantity_ids)


def test_driver_response_chains_have_exact_five_semantic_node_kinds() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    nodes = {item.node_id: item for item in graph.nodes}
    for chain in graph.driver_response_chains:
        assert nodes[chain.driver_input_id].kind is VehicleDynamicsNodeKind.QUANTITY
        assert nodes[chain.vehicle_demand_id].kind is VehicleDynamicsNodeKind.QUANTITY
        assert nodes[chain.vehicle_response_id].kind is VehicleDynamicsNodeKind.CHASSIS_RESPONSE_STATE
        assert nodes[chain.tire_platform_state_id].kind is VehicleDynamicsNodeKind.TIRE_DEMAND_STATE
        assert nodes[chain.performance_dimension_id].kind is VehicleDynamicsNodeKind.PERFORMANCE_DIMENSION


def test_mechanism_observation_mappings_are_reciprocal_and_separate() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    for mechanism in graph.mechanisms:
        for contract_id in mechanism.support_contract_ids:
            assert mechanism.definition_id in graph.observation_contract(contract_id).supports_mechanism_ids
        for contract_id in mechanism.contradiction_contract_ids:
            assert mechanism.definition_id in graph.observation_contract(contract_id).contradicts_mechanism_ids
        for contract_id in mechanism.discriminator_contract_ids:
            assert mechanism.definition_id in graph.observation_contract(contract_id).discriminates_mechanism_ids
    assert all(
        not (set(item.supports_mechanism_ids) & set(item.contradicts_mechanism_ids))
        for item in graph.observation_contracts
    )


def test_graph_rejects_duplicate_definition_nodes_and_broken_load_handoff() -> None:
    duplicate = _graph_payload()
    copied = dict(duplicate["nodes"][0])  # type: ignore[index]
    copied["node_id"] = "quantity:duplicate_node"
    duplicate["nodes"].append(copied)  # type: ignore[union-attr]
    with pytest.raises(ValidationError, match="exactly one graph node"):
        VehicleDynamicsKnowledgeGraph.model_validate(
            duplicate, context={"skip_content_hash": True}
        )

    broken = _graph_payload()
    broken["load_paths"][0]["output_quantity_ids"] = ["quantity:rpm"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="physical quantity handoff"):
        VehicleDynamicsKnowledgeGraph.model_validate(
            broken, context={"skip_content_hash": True}
        )

    wrong_phases = _graph_payload()
    damper = next(
        item
        for item in wrong_phases["component_influences"]  # type: ignore[union-attr]
        if item["component_id"] == "dampers"
    )
    damper["relevant_phases"] = ["center"]
    with pytest.raises(ValidationError, match="mechanism phase union"):
        VehicleDynamicsKnowledgeGraph.model_validate(
            wrong_phases, context={"skip_content_hash": True}
        )


def test_graph_rejects_nonreciprocal_contract_and_hash_tamper() -> None:
    nonreciprocal = _graph_payload()
    first_mechanism = nonreciprocal["mechanisms"][0]  # type: ignore[index]
    support_id = first_mechanism["support_contract_ids"][0]
    contract = next(
        item
        for item in nonreciprocal["observation_contracts"]  # type: ignore[union-attr]
        if item["definition_id"] == support_id
    )
    contract["supports_mechanism_ids"] = []
    with pytest.raises(ValidationError, match="support mappings must be reciprocal"):
        VehicleDynamicsKnowledgeGraph.model_validate(
            nonreciprocal, context={"skip_content_hash": True}
        )

    tampered = _graph_payload()
    tampered["knowledge_version"] = "forged"
    with pytest.raises(ValidationError, match="content hash does not match"):
        VehicleDynamicsKnowledgeGraph.model_validate(tampered)


def test_rehashed_graph_cannot_introduce_free_form_physics_references() -> None:
    payload = compile_next_gen_oval_knowledge_graph().model_dump(
        mode="json", exclude={"content_sha256", "graph_id", "graph_version"}
    )
    payload["mechanisms"][0]["created_by_ids"] = ["quantity:invented_magic"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown graph identities"):
        build_vehicle_dynamics_knowledge_graph(payload)

    payload = compile_next_gen_oval_knowledge_graph().model_dump(
        mode="json", exclude={"content_sha256", "graph_id", "graph_version"}
    )
    payload["mechanisms"][0]["p20_mechanism_ids"] = ["invented_observer"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="unknown P20 identities"):
        build_vehicle_dynamics_knowledge_graph(payload)

    duplicate_rule = _graph_payload()
    rule = duplicate_rule["mechanisms"][0]["forbidden_inferences"][0]  # type: ignore[index]
    duplicate_rule["mechanisms"][0]["forbidden_inferences"].append(rule)  # type: ignore[index]
    with pytest.raises(ValidationError, match="definition identities must be unique"):
        VehicleDynamicsKnowledgeGraph.model_validate(
            duplicate_rule, context={"skip_content_hash": True}
        )


def test_focus_artifact_requires_exact_scope_for_positive_evidence() -> None:
    with pytest.raises(ValidationError, match="exact lap/window/phase"):
        VehicleDynamicsFocusArtifact(
            artifact_id=f"p35.focus.steady_state_balance:{'3' * 24}",
            mechanism_id="mechanism:center_rotation_deficit",
            inspection_tool_id="inspect_steady_state_balance",
            stage="vehicle_response",
            evidence_state="measured",
            source_artifact_ids=("crew:response",),
            source_channels=("yaw_rate",),
            polarity="support",
            summary="Missing physical scope.",
        )

    with pytest.raises(ValidationError, match="bind its exact inspection tool"):
        VehicleDynamicsFocusArtifact(
            artifact_id=f"p35.focus.tire_demand:{'4' * 24}",
            mechanism_id="mechanism:center_rotation_deficit",
            inspection_tool_id="inspect_steady_state_balance",
            stage="tire_platform_state",
            evidence_state="needs_confirmation",
            source_artifact_ids=("crew:tire",),
            source_channels=("steering_deg",),
            polarity="uncertainty",
            summary="Wrong producer identity.",
            blocker_reasons=("Discriminator incomplete.",),
        )

    valid = _assessment().focus_artifacts[0]
    suffixed = valid.model_dump(mode="json")
    suffixed["artifact_id"] = f"{valid.artifact_id}extra"
    with pytest.raises(ValidationError, match="bind its exact inspection tool"):
        VehicleDynamicsFocusArtifact.model_validate(suffixed)

    duplicated_provenance = valid.model_dump(mode="json")
    duplicated_provenance["source_artifact_ids"] = ["crew:response", "crew:response"]
    with pytest.raises(ValidationError, match="provenance identities must be unique"):
        VehicleDynamicsFocusArtifact.model_validate(duplicated_provenance)

    duplicated_channels = valid.model_dump(mode="json")
    duplicated_channels["source_channels"] = ["yaw_rate", "yaw_rate"]
    with pytest.raises(ValidationError, match="provenance identities must be unique"):
        VehicleDynamicsFocusArtifact.model_validate(duplicated_channels)


def test_assessment_is_canonical_five_stage_noncausal_and_hash_bound() -> None:
    assessment = _assessment()
    assert assessment.p35_assessment_sha256 == performance_mechanism_assessment_hash(
        assessment
    )
    assert tuple(item.stage for item in assessment.chain) == tuple(DynamicsChainStageKind)
    assert assessment.p20_profile_hash is None
    assert assessment.component_causal_claim_count == 0
    assert assessment.setup_authorized is False
    assert assessment.terminal_authority == "p19_only"
    assert assessment.strongest_support_artifact_id
    assert assessment.strongest_contradiction_artifact_id
    assert assessment.next_discriminator_contract_id in assessment.candidates[0].discriminator_contract_ids

    tampered = assessment.model_copy(update={"objective_id": "qualifying_peak"})
    with pytest.raises(ValidationError, match="hash does not match"):
        PerformanceMechanismAssessment.model_validate(tampered.model_dump(mode="json"))


def test_chain_cannot_narrate_missing_input_as_present() -> None:
    with pytest.raises(ValidationError, match="require artifacts and channels"):
        VehicleDynamicsChainStage(
            stage="driver_input",
            evidence_state="measured",
            summary="Driver input was measured despite no evidence.",
        )
    blocked = VehicleDynamicsChainStage(
        stage="driver_input",
        evidence_state="unavailable",
        summary="Driver input is unavailable.",
        blocker_reasons=("Steering channel is missing.",),
    )
    assert blocked.evidence_state is EvidenceState.UNAVAILABLE

    with pytest.raises(ValidationError, match="provenance identities must be unique"):
        VehicleDynamicsChainStage(
            stage="driver_input",
            evidence_state="measured",
            source_artifact_ids=("crew:driver", "crew:driver"),
            source_channels=("brake_01",),
            summary="Duplicated provenance is not canonical evidence.",
        )

    with pytest.raises(ValidationError, match="provenance identities must be unique"):
        VehicleDynamicsChainStage(
            stage="driver_input",
            evidence_state="measured",
            source_artifact_ids=("crew:driver",),
            source_channels=("brake_01", "brake_01"),
            summary="Duplicated channels are not canonical evidence.",
        )


def test_assessment_requires_support_contradiction_and_candidate_owned_discriminator() -> None:
    assessment = _assessment()
    payload = assessment.model_dump(mode="json", exclude={"p35_assessment_sha256"})
    payload["strongest_contradiction_artifact_id"] = None
    with pytest.raises(ValidationError, match="strongest contradiction/uncertainty"):
        build_performance_mechanism_assessment(payload)

    payload = assessment.model_dump(mode="json", exclude={"p35_assessment_sha256"})
    payload["next_discriminator_contract_id"] = "observation:foreign:contract"
    with pytest.raises(ValidationError, match="belong to a current candidate"):
        build_performance_mechanism_assessment(payload)

    payload = assessment.model_dump(mode="json", exclude={"p35_assessment_sha256"})
    payload["focus_artifacts"][1]["mechanism_id"] = "mechanism:foreign"  # type: ignore[index]
    with pytest.raises(ValidationError, match="same-mechanism"):
        build_performance_mechanism_assessment(payload)

    payload = assessment.model_dump(mode="json", exclude={"p35_assessment_sha256"})
    payload["performance_opportunity_ids"] = ["opportunity:center", "opportunity:exit"]
    with pytest.raises(ValidationError, match="at most 1 item"):
        build_performance_mechanism_assessment(payload)

    payload = assessment.model_dump(mode="json", exclude={"p35_assessment_sha256"})
    payload["performance_opportunity_ids"] = []
    with pytest.raises(ValidationError, match="measured P32 time requires exactly one"):
        build_performance_mechanism_assessment(payload)

    payload = assessment.model_dump(mode="json", exclude={"p35_assessment_sha256"})
    payload["candidates"][0]["relevance"] = "blocked"  # type: ignore[index]
    payload["candidates"][0]["blocker_reasons"] = ["Traffic blocks attribution."]  # type: ignore[index]
    with pytest.raises(ValidationError, match="cannot publish support"):
        build_performance_mechanism_assessment(payload)


def test_assessment_rejects_orphan_and_cross_mechanism_focus_artifacts() -> None:
    assessment = _assessment()
    orphan = assessment.focus_artifacts[1].model_copy(
        update={
            "artifact_id": f"p35.focus.steady_state_balance:{'3' * 24}",
            "observation_contract_id": None,
        }
    )
    payload = assessment.model_dump(mode="python", exclude={"p35_assessment_sha256"})
    payload["focus_artifacts"] = (*assessment.focus_artifacts, orphan)
    with pytest.raises(ValidationError, match="owned by a same-mechanism candidate"):
        build_performance_mechanism_assessment(payload)

    swapped = assessment.focus_artifacts[1].model_copy(
        update={
            "artifact_id": f"p35.focus.steady_state_balance:{'4' * 24}",
            "mechanism_id": "mechanism:foreign",
            "polarity": "neutral",
        }
    )
    payload = assessment.model_dump(mode="python", exclude={"p35_assessment_sha256"})
    payload["focus_artifacts"] = (*assessment.focus_artifacts, swapped)
    with pytest.raises(ValidationError, match="owned by a same-mechanism candidate"):
        build_performance_mechanism_assessment(payload)


def test_traffic_blocked_assessment_retains_candidates_without_fake_support() -> None:
    payload = _assessment().model_dump(mode="json", exclude={"p35_assessment_sha256"})
    payload["candidates"][0]["relevance"] = "blocked"  # type: ignore[index]
    payload["candidates"][0]["support_artifact_ids"] = []  # type: ignore[index]
    payload["candidates"][0]["blocker_reasons"] = ["Traffic blocks attribution."]  # type: ignore[index]
    payload["focus_artifacts"] = [payload["focus_artifacts"][1]]  # type: ignore[index]
    payload["strongest_support_artifact_id"] = None
    payload["traffic_blocked"] = True
    payload["blocker_reasons"] = ["Traffic blocks vehicle-dynamics attribution."]
    payload["chain"][3]["evidence_state"] = "blocked_by_context"  # type: ignore[index]
    payload["chain"][3]["blocker_reasons"] = ["Traffic contaminates tire/platform state."]  # type: ignore[index]

    blocked = build_performance_mechanism_assessment(payload)

    assert blocked.measured_time_consequence_available is True
    assert blocked.traffic_blocked is True
    assert blocked.strongest_support_artifact_id is None
    assert blocked.strongest_contradiction_artifact_id
    assert blocked.next_discriminator_contract_id
    assert blocked.candidates[0].relevance == "blocked"
    assert blocked.candidates[0].support_artifact_ids == ()
    assert blocked.component_causal_claim_count == 0
    assert blocked.setup_authorized is False

def test_all_fourteen_inspection_tools_are_typed_and_covered() -> None:
    graph = compile_next_gen_oval_knowledge_graph()
    assert {item.inspection_tool_id for item in graph.mechanisms} == set(
        VehicleDynamicsInspectionToolId
    )
    for contract in graph.observation_contracts:
        direct = (*contract.supports_mechanism_ids, *contract.contradicts_mechanism_ids)
        assert all(
            graph.mechanism(mechanism_id).inspection_tool_id is contract.inspection_tool_id
            for mechanism_id in direct
        )


def test_phase_response_rejects_force_like_and_snapshot_channel_smuggling() -> None:
    metric = PhaseResponseMetric(
        metric_id=f"p354.metric:{'1' * 24}",
        quantity="yaw_rate_response_delta_rad_s",
        value=-0.02,
        units="rad/s",
        semantics="measured_delta",
        source_channels=("YawRate",),
    )
    with pytest.raises(ValidationError, match="research/display-only physics"):
        VehicleResponseObservation(
            observation_id=f"p354.response:{'2' * 24}",
            opportunity_id="p32o:test",
            run_id="run-1",
            source_lap_numbers=(4,),
            reference_lap_numbers=(5,),
            phase="center",
            lap_pct_start=20.0,
            lap_pct_end=30.0,
            onset_pct=20.0,
            response_regime="steady_state",
            driver_demand_state="matched",
            vehicle_response_state="changed",
            line_state="matched",
            context_state="qualified",
            persistence="phase_local",
            metrics=(metric,),
            source_artifact_ids=("p32:chain",),
            source_channels=("YawRate", "front_slip_angle_deg"),
            evidence_state="measured",
        )

    with pytest.raises(ValidationError, match="match the measured quantity"):
        PhaseResponseMetric.model_validate(
            {
                **metric.model_dump(mode="json"),
                "source_channels": ["rf_carcass_temp_m"],
            }
        )
