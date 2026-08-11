from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS
from racelab_engine.io.telemetry_manifest import (
    MANIFEST_SCHEMA_VERSION,
    UNIVERSAL_ARCHIVE_VERSION,
    compatibility_fingerprint,
)
from racelab_engine.knowledge.setup import load_setup_knowledge
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.models.vehicle_systems import (
    ComponentAwarenessState,
    ComponentObservabilityState,
    ComponentRelevance,
    VehicleSystemsEdgeKind,
    VehicleSystemsGraph,
    VehicleSystemsRuntimeIdentity,
)
from racelab_engine.services import vehicle_systems_service
from racelab_engine.services.vehicle_systems_service import (
    build_component_awareness,
    compile_vehicle_systems_graph,
    inspect_component,
    trace_control_mechanism,
    vehicle_systems_runtime_identity,
)
from racelab_engine.storage.repository import RaceLabRepository

RUN_ID = "run-p26"
SETUP_ID = "setup-p26"
SOURCE_SHA256 = "1" * 64
CACHE_SHA256 = "2" * 64
SCHEMA_SHA256 = "3" * 64
REAL_NEXT_GEN_RUN_ID = "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb"


EXPECTED_NEXT_GEN_AREA_BINDINGS = {
    "tire_pressure": ("tires", "pressure_support"),
    "pressure_split": ("tires", "pressure_support"),
    "pressure_gain": ("tires", "thermal_state"),
    "tire_temp_spread": ("tires", "thermal_state"),
    "tire_wear": ("tires", "thermal_state"),
    "camber": ("alignment", "camber_attitude"),
    "caster": ("alignment", "caster_split"),
    "toe": ("alignment", "toe_response"),
    "front_toe_response": ("alignment", "toe_response"),
    "rear_toe_stability": ("alignment", "toe_response"),
    "spring_rate": ("springs", "spring_rate"),
    "spring_perch": ("springs", "vertical_support"),
    "front_spring_support": ("springs", "vertical_support"),
    "rear_spring_support": ("springs", "vertical_support"),
    "spring_split": ("springs", "spring_rate"),
    "shock_collar": ("springs", "vertical_support"),
    "ls_compression": ("dampers", "compression_resistance"),
    "hs_compression": ("dampers", "compression_resistance"),
    "hs_comp_slope": ("dampers", "high_speed_slope"),
    "ls_rebound": ("dampers", "rebound_resistance"),
    "hs_rebound": ("dampers", "rebound_resistance"),
    "hs_reb_slope": ("dampers", "high_speed_slope"),
    "shock_histogram": ("dampers", "compression_resistance"),
    "shock_velocity_rms": ("dampers", "high_speed_slope"),
    "shock_deflection_delta": ("dampers", "rebound_resistance"),
    "front_arb_diameter": ("anti_roll_bars", "roll_coupling"),
    "front_arb_arm": ("anti_roll_bars", "arm_position"),
    "front_arb_preload": ("anti_roll_bars", "bar_preload"),
    "front_arb_attach": ("anti_roll_bars", "roll_coupling"),
    "rear_arb_diameter": ("anti_roll_bars", "roll_coupling"),
    "rear_arb_arm": ("anti_roll_bars", "arm_position"),
    "rear_arb_preload": ("anti_roll_bars", "bar_preload"),
    "rear_arb_attach": ("anti_roll_bars", "roll_coupling"),
    "cross_weight": ("weight_distribution", "static_diagonal_relationship"),
    "nose_weight": ("weight_distribution", "nose_weight"),
    "corner_weight": ("weight_distribution", "static_diagonal_relationship"),
    "ballast": ("weight_distribution", "nose_weight"),
    "ride_height": ("platform", "clearance"),
    "front_ride_height_platform": ("platform", "front_platform_height"),
    "rear_ride_height_platform": ("platform", "rear_platform_height"),
    "diffuser_platform": ("platform", "rake_relationship"),
    "cfs/front_splitter/rub_block_reference": ("platform", "clearance"),
    "platform_contact": ("platform", "clearance"),
    "front_platform_contact": ("platform", "front_platform_height"),
    "brake_bias": ("brakes", "front_rear_pressure_distribution"),
    "front_master_cylinder": ("brakes", "line_pressure_response"),
    "rear_master_cylinder": ("brakes", "line_pressure_response"),
    "diff_preload": ("differential", "preload"),
    "final_drive": ("final_drive", "final_drive_ratio"),
    "gear_ratio": ("final_drive", "gear_headroom"),
}


def _runtime_identity(
    run_id: str = RUN_ID,
    *,
    channels: tuple[str, ...] = ("session_time",),
) -> VehicleSystemsRuntimeIdentity:
    return VehicleSystemsRuntimeIdentity(
        run_id=run_id,
        car_path="stockcars chevycamarozl12022",
        car_version="2026.06.08.02",
        iracing_build_version="2026.06.24.02",
        track_configuration_name="Oval",
        source_file_sha256=SOURCE_SHA256,
        telemetry_cache_sha256=CACHE_SHA256,
        schema_fingerprint=SCHEMA_SHA256,
        compatibility_fingerprint="4" * 64,
        available_telemetry_channels=channels,
    )


def _controlled_outcome(
    *,
    run_id: str = RUN_ID,
    workflow_id: str = "workflow-crossweight",
    control_key: str = "cross_weight_percent",
    outcome: str = "inconclusive",
    verdict: str = "retest",
    control_direction_result: str | None = "matched",
    blocker_reasons: tuple[str, ...] = (),
    countereffects: tuple[str, ...] = (),
) -> SimpleNamespace:
    usable = outcome != "invalid" and verdict != "invalid"
    return SimpleNamespace(
        workflow_id=workflow_id,
        source_run_id=run_id,
        stage_run_ids=(f"{run_id}:A", f"{run_id}:B", f"{run_id}:A2") if usable else (),
        eligible_lap_ids=tuple(f"{run_id}:{lap}" for lap in range(1, 10)) if usable else (),
        metric="center_yaw_response",
        phase="center",
        control_key=control_key,
        outcome=outcome,
        control_direction_result=control_direction_result,
        verdict=verdict,
        countereffects=countereffects,
        blocker_reasons=blocker_reasons,
        diagnostic_validity="control_response_only",
    )


def _cause(
    *,
    cause_id: str = "cause:crossweight",
    outcome: object | None = None,
    hypothesis: str = "Cross weight may influence center rotation.",
    mechanism_key: str = "cross_weight",
    related_control_keys: tuple[str, ...] = ("cross_weight_percent",),
    status: str = "possible",
    ordinal_rank: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        cause_id=cause_id,
        hypothesis=hypothesis,
        mechanism_key=mechanism_key,
        related_control_keys=related_control_keys,
        controlled_outcomes=(outcome,) if outcome is not None else (),
        supporting_evidence=(),
        contradicting_evidence=(),
        status=status,
        ordinal_rank=ordinal_rank,
        discriminator=None,
    )


def _observation(
    artifact_id: str,
    *,
    run_id: str = RUN_ID,
    setup_id: str = SETUP_ID,
    mechanism: MechanismKind = MechanismKind.PLATFORM_RESPONSE,
    lap_number: int = 4,
    phase: str = "center",
    lap_pct_start: float = 20.0,
    lap_pct_end: float = 30.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        qualified=True,
        observation_id=f"observation:{artifact_id}",
        artifact_id=artifact_id,
        run_id=run_id,
        setup_id=setup_id,
        mechanism=mechanism,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        lap_number=lap_number,
        phase=phase,
        lap_pct_start=lap_pct_start,
        lap_pct_end=lap_pct_end,
        summary=f"Qualified {artifact_id}",
    )


def _report(
    *,
    run_id: str = RUN_ID,
    authority_control: str | None = None,
    causes: tuple[object, ...] = (),
    observations: tuple[object, ...] = (),
    observation_report_run_id: str | None = None,
    observation_setup_id: str = SETUP_ID,
) -> SimpleNamespace:
    observation_report = (
        SimpleNamespace(
            run_id=observation_report_run_id or run_id,
            setup_id=observation_setup_id,
            observations=observations,
        )
        if observations
        else None
    )
    return SimpleNamespace(
        run_id=run_id,
        session_id=None,
        mechanism_observations=observation_report,
        reasoning_snapshot=SimpleNamespace(
            authority=SimpleNamespace(
                setup_authorized=authority_control is not None,
                control_key=authority_control,
            ),
            causes=causes,
        ),
        best_measurement=SimpleNamespace(
            setup_authorized=authority_control is not None,
            instruction="Measure the exact center window before changing setup.",
        ),
    )


def _project(
    report: SimpleNamespace,
    *,
    runtime_identity: VehicleSystemsRuntimeIdentity | None = None,
    setup_snapshot: object | None = None,
):
    return build_component_awareness(
        report,
        runtime_identity=runtime_identity or _runtime_identity(report.run_id),
        setup_snapshot=setup_snapshot,
    )


def _capability_payload(
    *,
    run_id: str = RUN_ID,
    identity_updates: dict[str, object] | None = None,
    channels: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    identity: dict[str, object] = {
        "car_path": "stockcars chevycamarozl12022",
        "car_version": "2026.06.08.02",
        "iracing_build_version": "2026.06.24.02",
        "track_configuration_name": "Oval",
        "missing_required_fields": [],
    }
    identity.update(identity_updates or {})
    return {
        "run_id": run_id,
        "source_file_sha256": SOURCE_SHA256,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "universal_archive_version": UNIVERSAL_ARCHIVE_VERSION,
        "manifest_identity": {
            "status": "verified",
            "run_id": run_id,
            "source_file_sha256": SOURCE_SHA256,
            "telemetry_cache_sha256": CACHE_SHA256,
        },
        "cache_compatibility": {"status": "current"},
        "compatibility_identity": identity,
        "schema_fingerprint": SCHEMA_SHA256,
        "compatibility_fingerprint": compatibility_fingerprint(SCHEMA_SHA256, identity),
        "channels": channels
        or [
            {
                "name": "SessionTime",
                "canonical_name": "session_time",
                "archive_status": "cached",
                "valid_record_count": 100,
                "health_status": "healthy",
            }
        ],
    }


def _manifest_channel(
    canonical_name: str,
    *,
    health_status: str = "healthy",
) -> dict[str, object]:
    return {
        "name": canonical_name,
        "canonical_name": canonical_name,
        "archive_status": "cached",
        "valid_record_count": 100,
        "health_status": health_status,
    }


def _install_runtime_artifact(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    *,
    repository_run_id: str = RUN_ID,
    repository_source_sha256: str = SOURCE_SHA256,
) -> None:
    session = SimpleNamespace(
        run_id=repository_run_id,
        file_hash=repository_source_sha256,
    )
    repository = SimpleNamespace(get_session=lambda candidate: session)

    def capability_payload(
        candidate: str,
        *,
        expected_source_file_sha256: str,
    ) -> dict[str, object]:
        assert candidate == RUN_ID
        assert expected_source_file_sha256 == repository_source_sha256
        return deepcopy(payload)

    monkeypatch.setattr(vehicle_systems_service, "RaceLabRepository", lambda: repository)
    monkeypatch.setattr(
        vehicle_systems_service,
        "build_telemetry_capability_payload",
        capability_payload,
    )


def test_graph_compiles_every_supported_control_into_typed_next_gen_components() -> None:
    graph = compile_vehicle_systems_graph()

    assert graph.schema_version == "p26.vehicle-systems.v3"
    assert len(graph.components) == 12
    assert graph.setup_authorized is False
    assert {item.evidence_authority_ceiling for item in graph.components} == {"hypothesis_only"}
    assert all(item.observability.unavailable_quantities for item in graph.components)
    control_ids = {node.node_id for node in graph.nodes if node.kind.value == "control"}
    assert {f"control:{key}" for key in SETUP_CONTROL_SPECS} <= control_ids
    assert all(edge.kind.value != "causes" for edge in graph.edges)
    assert any(item.interaction_type == "garage_autocompensated" for item in graph.interactions)
    assert not any("legacy" in item.applicability.car_family for item in graph.components)
    assert compile_vehicle_systems_graph() is graph
    assert graph.graph_version.endswith(graph.content_sha256[:12])


def test_graph_preserves_all_50_areas_and_explicit_effect_property_bindings() -> None:
    graph = compile_vehicle_systems_graph()
    knowledge = load_setup_knowledge()
    next_gen_areas = {
        area.setup_area.casefold()
        for area in knowledge.setup_areas
        if "next_gen" not in area.disabled_for
        and ("all" in area.applies_to or "next_gen" in area.applies_to)
    }
    assert len(EXPECTED_NEXT_GEN_AREA_BINDINGS) == 50
    assert next_gen_areas == set(EXPECTED_NEXT_GEN_AREA_BINDINGS)

    nodes = {node.node_id: node for node in graph.nodes}
    area_nodes = {
        node.node_id.removeprefix("area:"): node
        for node in graph.nodes
        if node.kind.value == "engineering_area"
    }
    assert set(area_nodes) == next_gen_areas
    for area_id, (component_id, _property_id) in EXPECTED_NEXT_GEN_AREA_BINDINGS.items():
        assert area_nodes[area_id].component_id == component_id
        assert any(
            edge.kind is VehicleSystemsEdgeKind.COMPONENT_HAS_ENGINEERING_AREA
            and edge.source_node_id == f"component:{component_id}"
            and edge.target_node_id == f"area:{area_id}"
            for edge in graph.edges
        )

    next_gen_effects = (
        effect
        for effect in knowledge.setup_effects
        if "next_gen" not in effect.disabled_for
        and ("all" in effect.applies_to or "next_gen" in effect.applies_to)
    )
    for effect in next_gen_effects:
        area_id = effect.setup_area.casefold()
        component_id, property_id = EXPECTED_NEXT_GEN_AREA_BINDINGS[area_id]
        control_id = f"control:effect:{effect.effect_id}"
        assert control_id in nodes
        assert any(
            edge.kind is VehicleSystemsEdgeKind.ENGINEERING_AREA_HAS_CONTROL
            and edge.source_node_id == f"area:{area_id}"
            and edge.target_node_id == control_id
            for edge in graph.edges
        )
        property_edges = [
            edge
            for edge in graph.edges
            if edge.kind is VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY
            and edge.source_node_id == control_id
        ]
        assert len(property_edges) == 1
        assert property_edges[0].target_node_id == f"property:{component_id}:{property_id}"

    directions = {
        edge.source_node_id: edge.direction
        for edge in graph.edges
        if edge.kind is VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY
    }
    assert directions["control:effect:add_crossweight_small"] == "increase"
    assert directions["control:effect:reduce_crossweight_small"] == "decrease"
    assert directions["control:effect:adjust_front_arb_preload_small"] is None


def test_shock_collar_is_spring_support_not_damper_compression_resistance() -> None:
    snapshot = SetupSnapshot(
        setup_id=SETUP_ID,
        run_id=RUN_ID,
        extracted_values={
            corner: {"shock_collar_offset_mm": 12.0 + index}
            for index, corner in enumerate(("lf", "rf", "lr", "rr"))
        },
    )
    projection = _project(_report(), setup_snapshot=snapshot)
    states = {state.component_id: state for state in projection.component_states}

    assert "LF shock collar: 12.0 mm" in states["springs"].current_settings
    assert not any(
        "shock collar" in setting.casefold()
        for setting in states["dampers"].current_settings
    )


def test_graph_source_registry_and_content_hash_cover_the_exact_graph() -> None:
    graph = compile_vehicle_systems_graph()
    graph_items = (*graph.components, *graph.interactions, *graph.nodes, *graph.edges)
    used_sources = {
        source_id for item in graph_items for source_id in item.source_ids
    }
    assert set(graph.source_ids) == used_sources

    content_payload = {
        "components": [item.model_dump(mode="json") for item in graph.components],
        "interactions": [item.model_dump(mode="json") for item in graph.interactions],
        "nodes": [item.model_dump(mode="json") for item in graph.nodes],
        "edges": [item.model_dump(mode="json") for item in graph.edges],
        "source_ids": graph.source_ids,
    }
    expected_hash = hashlib.sha256(
        json.dumps(content_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert graph.content_sha256 == expected_hash
    assert graph.graph_version.endswith(expected_hash[:12])

    incomplete = graph.model_dump(mode="json")
    incomplete["source_ids"] = incomplete["source_ids"][:-1]
    with pytest.raises(ValidationError, match="source registry"):
        VehicleSystemsGraph.model_validate(incomplete)


def test_control_trace_stays_in_source_declared_expectation_edges() -> None:
    trace = trace_control_mechanism("cross_weight_percent")

    assert trace
    assert any(edge.source_node_id == "control:cross_weight_percent" for edge in trace)
    assert any(
        edge.target_node_id
        == "property:weight_distribution:static_diagonal_relationship"
        for edge in trace
    )
    assert all(edge.authority == "engineering_expectation_only" for edge in trace)
    assert {edge.kind for edge in trace} <= {
        VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY,
        VehicleSystemsEdgeKind.CONTROL_REQUIRES_INVARIANT,
        VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE,
        VehicleSystemsEdgeKind.STATE_MAY_PRESENT_AS_SYMPTOM,
        VehicleSystemsEdgeKind.STATE_OBSERVABLE_BY,
    }


def test_component_projection_mirrors_only_the_exact_p19_authorized_control() -> None:
    projection = _project(_report(authority_control="cross_weight_percent"))
    authorized = [item for item in projection.component_states if item.setup_authorized]

    assert projection.schema_version == "p26.component-awareness.v4"
    assert projection.runtime_graph.schema_version == "p26.runtime-graph.v3"
    assert projection.setup_authorized is True
    assert len(authorized) == 1
    assert authorized[0].component_id == "weight_distribution"
    assert authorized[0].authorized_control_key == "cross_weight_percent"
    assert authorized[0].authority_state == "p19_authorized"
    assert authorized[0].current_testability == "p19_authorized"


def test_whole_car_observation_makes_coupled_components_candidates_not_proven_causes() -> None:
    observation = _observation("artifact:platform")
    projection = _project(_report(observations=(observation,)))
    coupled = [
        item
        for item in projection.component_states
        if item.component_id in {"springs", "dampers", "anti_roll_bars", "platform"}
    ]

    assert {item.relevance for item in coupled} == {ComponentRelevance.CANDIDATE}
    assert all(
        ComponentObservabilityState.MECHANISM_SUPPORTED not in item.observability_states
        for item in coupled
    )
    assert projection.leading_system == "Platform / suspension component family"
    assert projection.runtime_graph.nodes
    assert all(node.component_id is None for node in projection.runtime_graph.nodes)
    assert {edge.kind for edge in projection.runtime_graph.edges} == {
        VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE
    }
    assert projection.runtime_graph.reasoning_snapshot_sha256 == projection.reasoning_snapshot_sha256
    requirements = {
        definition.component_id: definition.measurement_requirements[0]
        for definition in compile_vehicle_systems_graph().components
    }
    assert all(
        item.next_discriminator == requirements[item.component_id]
        and item.next_discriminator
        != "Measure the exact center window before changing setup."
        for item in coupled
    )


def test_foreign_p20_observation_is_rejected_instead_of_relabelled() -> None:
    foreign = _observation("artifact:foreign", run_id="foreign-run")
    report = _report(observations=(foreign,))

    with pytest.raises(ValueError, match="foreign P20 observation"):
        _project(report)


def test_multiple_p20_observation_scopes_survive_component_projection() -> None:
    first = _observation(
        "artifact:lap-4",
        lap_number=4,
        lap_pct_start=20.0,
        lap_pct_end=25.0,
    )
    second = _observation(
        "artifact:lap-8",
        lap_number=8,
        lap_pct_start=40.0,
        lap_pct_end=47.5,
    )
    projection = _project(_report(observations=(first, second)))
    platform = next(
        item for item in projection.component_states if item.component_id == "platform"
    )

    assert platform.supporting_artifact_ids == ("artifact:lap-4", "artifact:lap-8")
    assert [scope.model_dump() for scope in platform.observation_scopes] == [
        {
            "artifact_id": "artifact:lap-4",
            "observation_id": "observation:artifact:lap-4",
            "lap_number": 4,
            "phase": "center",
            "lap_pct_start": 20.0,
            "lap_pct_end": 25.0,
        },
        {
            "artifact_id": "artifact:lap-8",
            "observation_id": "observation:artifact:lap-8",
            "lap_number": 8,
            "phase": "center",
            "lap_pct_start": 40.0,
            "lap_pct_end": 47.5,
        },
    ]


def test_driver_execution_evidence_does_not_activate_steering_component() -> None:
    observation = _observation(
        "artifact:driver-execution",
        mechanism=MechanismKind.DRIVER_EXECUTION,
    )
    cause = _cause(
        cause_id="cause:driver-execution",
        mechanism_key="driver_execution",
        related_control_keys=(),
        status="likely",
    )
    projection = _project(_report(causes=(cause,), observations=(observation,)))
    steering = next(
        item for item in projection.component_states if item.component_id == "steering"
    )

    assert steering.relevance is ComponentRelevance.IRRELEVANT
    assert steering.supporting_artifact_ids == ()
    assert steering.supporting_cause_ids == ()
    assert all(
        state.relevance is ComponentRelevance.IRRELEVANT
        for state in projection.component_states
    )


def test_live_observability_requires_one_complete_current_manifest_channel_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete_group = (
        "lf_shock_defl_in",
        "rf_shock_defl_in",
        "lr_shock_defl_in",
        "rr_shock_defl_in",
    )
    complete_payload = _capability_payload(
        channels=[
            _manifest_channel("session_time"),
            *(_manifest_channel(channel) for channel in complete_group),
        ]
    )
    _install_runtime_artifact(monkeypatch, complete_payload)
    complete_identity = vehicle_systems_runtime_identity(RUN_ID)
    complete = _project(
        _report(),
        runtime_identity=complete_identity,
    )

    partial_payload = _capability_payload(
        channels=[
            _manifest_channel("session_time"),
            *(_manifest_channel(channel) for channel in complete_group[:-1]),
            _manifest_channel(complete_group[-1], health_status="blocked"),
        ]
    )
    _install_runtime_artifact(monkeypatch, partial_payload)
    partial_identity = vehicle_systems_runtime_identity(RUN_ID)
    partial = _project(
        _report(),
        runtime_identity=partial_identity,
    )
    complete_springs = next(
        item for item in complete.component_states if item.component_id == "springs"
    )
    partial_springs = next(
        item for item in partial.component_states if item.component_id == "springs"
    )

    assert ComponentObservabilityState.LIVE_RESPONSE_OBSERVABLE in complete_springs.observability_states
    assert complete_springs.available_live_channel_ids == complete_group
    assert complete_springs.live_response_blocker_reasons == ()
    assert complete_springs.current_response_state == "not_observed"
    assert ComponentObservabilityState.LIVE_RESPONSE_OBSERVABLE not in partial_springs.observability_states
    assert partial_springs.available_live_channel_ids == ()
    assert partial_springs.live_response_blocker_reasons
    assert partial_springs.current_response_state == "unavailable"


def test_per_control_undo_leaves_unrelated_component_control_testable() -> None:
    outcome = _controlled_outcome(
        workflow_id="workflow-crossweight-undo",
        verdict="undo",
        countereffects=("Exit instability increased.",),
    )
    projection = _project(
        _report(
            authority_control="nose_weight_percent",
            causes=(_cause(outcome=outcome),),
        )
    )
    state = next(
        item
        for item in projection.component_states
        if item.component_id == "weight_distribution"
    )

    assert state.relevance is ComponentRelevance.TESTED
    assert state.blocked_control_keys == ("cross_weight_percent",)
    assert state.testable_control_keys == ("nose_weight_percent",)
    assert state.authorized_control_key == "nose_weight_percent"
    assert state.current_testability == "p19_authorized"
    assert state.setup_authorized is True
    assert any(
        edge.kind is VehicleSystemsEdgeKind.POLICY_REJECTED_DUE_TO_COUNTEREFFECT
        for edge in projection.runtime_graph.edges
    )


def test_p26_cannot_veto_p19_same_control_authority_for_a_changed_policy() -> None:
    prior_undo = _controlled_outcome(
        workflow_id="workflow-old-window-undo",
        verdict="undo",
        countereffects=("Old-window exit instability increased.",),
    )
    projection = _project(
        _report(
            authority_control="cross_weight_percent",
            causes=(_cause(outcome=prior_undo),),
        )
    )
    state = next(
        item
        for item in projection.component_states
        if item.component_id == "weight_distribution"
    )

    assert state.controlled_history[0].policy_verdict == "undo"
    assert state.blocked_control_keys == ()
    assert "cross_weight_percent" in state.testable_control_keys
    assert state.authorized_control_key == "cross_weight_percent"
    assert state.current_testability == "p19_authorized"
    assert state.setup_authorized is True


def test_invalid_history_is_not_exact_context_and_creates_no_runtime_response_edge() -> None:
    outcome = _controlled_outcome(
        workflow_id="workflow-invalid",
        outcome="invalid",
        verdict="invalid",
        control_direction_result=None,
        blocker_reasons=("The A2 stage contains partial laps.",),
    )
    projection = _project(_report(causes=(_cause(outcome=outcome),)))
    state = next(
        item
        for item in projection.component_states
        if item.component_id == "weight_distribution"
    )
    history = state.controlled_history[0]

    assert history.exact_context is False
    assert history.blocker_reasons == ("The A2 stage contains partial laps.",)
    assert history.stage_run_ids == ()
    assert history.eligible_lap_ids == ()
    assert state.blocked_control_keys == ()
    assert ComponentObservabilityState.CONTROLLED_RESPONSE_KNOWN not in state.observability_states
    assert ComponentObservabilityState.EXACT_CONTEXT_POLICY_KNOWN not in state.observability_states
    assert not any(
        "workflow-invalid" in source_id
        for edge in projection.runtime_graph.edges
        for source_id in edge.source_ids
    )


def test_generic_language_cannot_activate_component_relevance_by_word_overlap() -> None:
    unrelated = _cause(
        cause_id="cause:unrelated",
        hypothesis="Traffic and weather context remain unresolved.",
        mechanism_key="unresolved",
        related_control_keys=(),
    )
    projection = _project(_report(causes=(unrelated,)))

    assert all(
        item.relevance is ComponentRelevance.IRRELEVANT
        for item in projection.component_states
    )


def test_typed_component_identity_is_stable_when_redacted_prose_changes() -> None:
    first = _project(
        _report(causes=(_cause(hypothesis="Redacted public explanation A.", status="likely"),))
    )
    second = _project(
        _report(causes=(_cause(hypothesis="Completely unrelated wording B.", status="likely"),))
    )

    first_state = next(
        item for item in first.component_states if item.component_id == "weight_distribution"
    )
    second_state = next(
        item for item in second.component_states if item.component_id == "weight_distribution"
    )
    assert first_state.relevance is ComponentRelevance.SUPPORTED
    assert second_state.relevance is ComponentRelevance.SUPPORTED


def test_broad_mechanism_cannot_manufacture_one_supported_component() -> None:
    projection = _project(
        _report(
            causes=(
                _cause(
                    mechanism_key="platform",
                    related_control_keys=(),
                    status="likely",
                ),
            )
        )
    )
    family = [
        item
        for item in projection.component_states
        if item.component_id in {"platform", "springs", "dampers", "anti_roll_bars"}
    ]
    assert {item.relevance for item in family} == {ComponentRelevance.CANDIDATE}


def test_runtime_identity_uses_only_verified_production_artifact_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _capability_payload()
    _install_runtime_artifact(monkeypatch, payload)
    identity = vehicle_systems_runtime_identity(RUN_ID)

    assert identity.run_id == RUN_ID
    assert identity.source == "verified_telemetry_artifact"
    assert identity.source_file_sha256 == SOURCE_SHA256
    assert identity.telemetry_cache_sha256 == CACHE_SHA256
    assert identity.available_telemetry_channels == ("SessionTime", "session_time")


def test_runtime_identity_rejects_wrong_build_track_run_cache_and_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases: list[tuple[dict[str, object], str, str, str]] = []

    for identity_updates, message in (
        ({"car_path": "stockcars camaro zl1 2018 legacy"}, "unavailable for car path"),
        ({"iracing_build_version": "2025.12.31.99"}, "does not cover"),
        ({"iracing_build_version": "2026.06.24.03"}, "requires review"),
        ({"track_configuration_name": "Road Course"}, "oval track"),
    ):
        cases.append((_capability_payload(identity_updates=identity_updates), RUN_ID, SOURCE_SHA256, message))

    wrong_payload_run = _capability_payload()
    wrong_payload_run["run_id"] = "foreign-run"
    cases.append((wrong_payload_run, RUN_ID, SOURCE_SHA256, "telemetry ownership"))

    wrong_manifest_run = _capability_payload()
    wrong_manifest_run["manifest_identity"]["run_id"] = "foreign-run"  # type: ignore[index]
    cases.append((wrong_manifest_run, RUN_ID, SOURCE_SHA256, "telemetry cache does not belong"))

    wrong_manifest_source = _capability_payload()
    wrong_manifest_source["manifest_identity"]["source_file_sha256"] = "5" * 64  # type: ignore[index]
    cases.append((wrong_manifest_source, RUN_ID, SOURCE_SHA256, "manifest source does not belong"))

    wrong_payload_source = _capability_payload()
    wrong_payload_source["source_file_sha256"] = "5" * 64
    cases.append((wrong_payload_source, RUN_ID, SOURCE_SHA256, "source-file ownership changed"))

    bad_cache = _capability_payload()
    bad_cache["manifest_identity"]["telemetry_cache_sha256"] = "not-a-hash"  # type: ignore[index]
    cases.append((bad_cache, RUN_ID, SOURCE_SHA256, "current verified telemetry archive"))

    cases.append((_capability_payload(), "foreign-run", SOURCE_SHA256, "stored source ownership"))

    for candidate_payload, repository_run, repository_source, message in cases:
        _install_runtime_artifact(
            monkeypatch,
            candidate_payload,
            repository_run_id=repository_run,
            repository_source_sha256=repository_source,
        )
        with pytest.raises(ValueError, match=message):
            vehicle_systems_runtime_identity(RUN_ID)


def test_component_inspection_is_a_typed_non_authoritative_contract() -> None:
    projection = _project(_report())
    inspection = inspect_component("springs", projection)

    assert inspection.run_id == RUN_ID
    assert inspection.component_id == "springs"
    assert inspection.definition.component_id == "springs"
    assert inspection.state.component_id == "springs"
    assert inspection.authority == "p19_projection_only"
    assert inspection.runtime_identity == projection.runtime_identity
    assert inspection.reasoning_snapshot_sha256 == projection.reasoning_snapshot_sha256


def test_vehicle_systems_routes_publish_typed_openapi_contracts() -> None:
    from api.main import app

    paths = app.openapi()["paths"]
    expected = {
        "/api/runs/{run_id}/vehicle-systems": "VehicleSystemsProjection",
        "/api/runs/{run_id}/vehicle-systems/components/{component_id}": "ComponentInspectionResponse",
        "/api/runs/{run_id}/vehicle-systems/controls/{control_key}/trace": "ControlMechanismTraceResponse",
    }
    for path, schema_name in expected.items():
        schema = paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema == {"$ref": f"#/components/schemas/{schema_name}"}


def test_component_state_rejects_manufactured_authority_and_mixed_unavailable() -> None:
    base = {
        "component_id": "springs",
        "run_id": RUN_ID,
        "current_response_state": "unavailable",
        "relevance": "candidate",
        "current_testability": "measurement_only",
        "authority_state": "knowledge_only",
        "live_response_blocker_reasons": ("No complete manifest channel group exists.",),
        "next_discriminator": "Capture the missing response channels.",
    }
    with pytest.raises(ValidationError, match="only mirror P19 setup authority"):
        ComponentAwarenessState(
            **base,
            observability_states=(ComponentObservabilityState.DEFINITION_KNOWN,),
            setup_authorized=True,
        )
    with pytest.raises(ValidationError, match="unavailable observability"):
        ComponentAwarenessState(
            **base,
            observability_states=(
                ComponentObservabilityState.DEFINITION_KNOWN,
                ComponentObservabilityState.UNAVAILABLE,
            ),
        )


def test_experiment_factors_are_non_authoritative_single_property_contracts() -> None:
    projection = _project(_report())

    assert projection.experiment_factors
    assert all(not factor.setup_authorized for factor in projection.experiment_factors)
    assert all(factor.authority == "experiment_definition_only" for factor in projection.experiment_factors)
    front_height = next(
        item
        for item in projection.experiment_factors
        if item.factor_id == "factor:front_platform_height"
    )
    assert front_height.primary_controls == ("lf_ride_height_mm",)
    assert front_height.coordinated_controls == ("rf_ride_height_mm",)
    spring = next(
        item
        for item in projection.experiment_factors
        if item.factor_id == "factor:rf_spring_rate"
    )
    assert spring.automatic_sim_compensations
    assert spring.required_manual_compensations


def test_real_next_gen_ibt_manifest_and_setup_snapshot_project_exactly() -> None:
    overview = RaceLabRepository().get_overview(REAL_NEXT_GEN_RUN_ID)
    if overview is None or overview.setup_snapshot is None:
        pytest.skip("The imported real Next Gen Atlanta fixture is unavailable.")
    try:
        runtime_identity = vehicle_systems_runtime_identity(REAL_NEXT_GEN_RUN_ID)
    except ValueError as exc:
        pytest.skip(f"The real Next Gen telemetry artifact is unavailable: {exc}")

    projection = _project(
        _report(run_id=REAL_NEXT_GEN_RUN_ID),
        runtime_identity=runtime_identity,
        setup_snapshot=overview.setup_snapshot,
    )
    states = {state.component_id: state for state in projection.component_states}

    assert runtime_identity.car_path == "stockcars chevycamarozl12022"
    assert runtime_identity.car_version == "2026.06.08.02"
    assert runtime_identity.iracing_build_version == "2026.06.24.02"
    assert runtime_identity.track_configuration_name == "Oval"
    assert projection.schema_version == "p26.component-awareness.v4"
    assert projection.runtime_graph.schema_version == "p26.runtime-graph.v3"
    assert projection.setup_id == overview.setup_snapshot.setup_id
    assert projection.setup_snapshot_sha256 is not None
    assert len(projection.setup_snapshot_sha256) == 64
    assert len(states["tires"].current_settings) == 4
    assert "RF cold pressure: 324.0 kPa" in states["tires"].current_settings
    assert len(states["alignment"].current_settings) == 10
    assert "RF camber: -4.5 deg" in states["alignment"].current_settings
    assert len(states["springs"].current_settings) == 8
    assert len(states["dampers"].current_settings) == 24
    assert len(states["anti_roll_bars"].current_settings) == 8
    assert "Front ARB arm: P5" in states["anti_roll_bars"].current_settings
    assert "Front master cylinder: 23.7 mm" in states["brakes"].current_settings
    assert states["differential"].current_settings == (
        "Differential preload: 0.0 Nm",
    )
