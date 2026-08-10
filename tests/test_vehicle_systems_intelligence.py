from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS
from racelab_engine.io.telemetry_manifest import compatibility_fingerprint
from racelab_engine.models.vehicle_systems import (
    ComponentAwarenessState,
    ComponentObservabilityState,
    ComponentRelevance,
    VehicleSystemsEdgeKind,
    VehicleSystemsRuntimeIdentity,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.services.vehicle_systems_service import (
    build_component_awareness,
    compile_vehicle_systems_graph,
    inspect_component,
    trace_control_mechanism,
    vehicle_systems_runtime_identity,
)


def _cause(
    *,
    outcome: object | None = None,
    hypothesis: str = "Cross weight may influence center rotation.",
    mechanism_key: str = "cross_weight",
    related_control_keys: tuple[str, ...] = ("cross_weight_percent",),
    status: str = "possible",
) -> SimpleNamespace:
    return SimpleNamespace(
        cause_id="cause:crossweight",
        hypothesis=hypothesis,
        mechanism_key=mechanism_key,
        related_control_keys=related_control_keys,
        controlled_outcomes=(outcome,) if outcome is not None else (),
        supporting_evidence=(),
        contradicting_evidence=(),
        status=status,
    )


def _report(*, authority_control: str | None = None, causes: tuple[object, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-p26",
        mechanism_observations=None,
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


def test_graph_compiles_every_supported_control_into_typed_next_gen_components() -> None:
    graph = compile_vehicle_systems_graph()

    assert graph.schema_version == "p26.vehicle-systems.v1"
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
    assert any(
        edge.interaction_type == "garage_autocompensated"
        for edge in graph.edges
    )


def test_control_trace_stays_in_source_declared_expectation_edges() -> None:
    trace = trace_control_mechanism("cross_weight_percent")

    assert trace
    assert any(edge.source_node_id == "control:cross_weight_percent" for edge in trace)
    assert any(edge.target_node_id == "property:weight_distribution:static_diagonal_relationship" for edge in trace)
    assert all(edge.authority == "engineering_expectation_only" for edge in trace)
    assert {edge.kind for edge in trace} <= {
        VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY,
        VehicleSystemsEdgeKind.CONTROL_REQUIRES_INVARIANT,
        VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE,
        VehicleSystemsEdgeKind.STATE_MAY_PRESENT_AS_SYMPTOM,
        VehicleSystemsEdgeKind.STATE_OBSERVABLE_BY,
    }


def test_component_projection_mirrors_only_the_exact_p19_authorized_control() -> None:
    projection = build_component_awareness(_report(authority_control="cross_weight_percent"))
    authorized = [item for item in projection.component_states if item.setup_authorized]

    assert projection.setup_authorized is True
    assert len(authorized) == 1
    assert authorized[0].component_id == "weight_distribution"
    assert authorized[0].authority_state == "p19_authorized"
    assert authorized[0].current_testability == "p19_authorized"


def test_whole_car_observation_makes_coupled_components_candidates_not_proven_causes() -> None:
    observation = SimpleNamespace(
        qualified=True,
        mechanism=MechanismKind.PLATFORM_RESPONSE,
        artifact_id="artifact:platform",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        lap_number=4,
        phase="center",
        lap_pct_start=20.0,
        lap_pct_end=30.0,
    )
    report = _report()
    report.mechanism_observations = SimpleNamespace(observations=(observation,))

    projection = build_component_awareness(report)
    coupled = [
        item for item in projection.component_states
        if item.component_id in {"springs", "dampers", "anti_roll_bars", "platform"}
    ]
    assert {item.relevance for item in coupled} == {ComponentRelevance.CANDIDATE}
    assert all(ComponentObservabilityState.MECHANISM_SUPPORTED not in item.observability_states for item in coupled)
    assert projection.leading_system == "Platform / suspension component family"
    assert projection.runtime_graph.nodes
    assert all(node.component_id is None for node in projection.runtime_graph.nodes)
    assert {
        edge.kind for edge in projection.runtime_graph.edges
    } == {VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE}
    assert projection.runtime_graph.reasoning_snapshot_sha256 == projection.reasoning_snapshot_sha256


def test_exact_context_undo_blocks_generic_component_prior() -> None:
    outcome = SimpleNamespace(
        workflow_id="workflow-undo",
        control_key="cross_weight_percent",
        outcome="inconclusive",
        control_direction_result="matched",
        verdict="undo",
        countereffects=("Exit instability increased.",),
    )
    projection = build_component_awareness(_report(causes=(_cause(outcome=outcome),)))
    state = next(item for item in projection.component_states if item.component_id == "weight_distribution")

    assert state.relevance is ComponentRelevance.BLOCKED
    assert state.current_testability == "policy_blocked"
    assert state.controlled_history[0].policy_verdict == "undo"
    assert state.setup_authorized is False
    assert "generic component knowledge cannot reopen it" in state.blocker_reasons[0]
    assert any(
        edge.kind is VehicleSystemsEdgeKind.POLICY_REJECTED_DUE_TO_COUNTEREFFECT
        for edge in projection.runtime_graph.edges
    )


def test_generic_language_cannot_activate_component_relevance_by_word_overlap() -> None:
    unrelated = SimpleNamespace(
        cause_id="cause:unrelated",
        hypothesis="Traffic and weather context remain unresolved.",
        mechanism_key="unresolved",
        related_control_keys=(),
        controlled_outcomes=(),
        supporting_evidence=(),
        contradicting_evidence=(),
        status="possible",
    )
    projection = build_component_awareness(_report(causes=(unrelated,)))

    assert all(item.relevance is ComponentRelevance.IRRELEVANT for item in projection.component_states)


def test_typed_component_identity_is_stable_when_redacted_prose_changes() -> None:
    first = build_component_awareness(_report(causes=(_cause(
        hypothesis="Redacted public explanation A.", status="likely",
    ),)))
    second = build_component_awareness(_report(causes=(_cause(
        hypothesis="Completely unrelated wording B.", status="likely",
    ),)))

    first_state = next(item for item in first.component_states if item.component_id == "weight_distribution")
    second_state = next(item for item in second.component_states if item.component_id == "weight_distribution")
    assert first_state.relevance is ComponentRelevance.SUPPORTED
    assert second_state.relevance is ComponentRelevance.SUPPORTED


def test_broad_mechanism_cannot_manufacture_one_supported_component() -> None:
    projection = build_component_awareness(_report(causes=(_cause(
        mechanism_key="platform",
        related_control_keys=(),
        status="likely",
    ),)))
    family = [
        item for item in projection.component_states
        if item.component_id in {"platform", "springs", "dampers", "anti_roll_bars"}
    ]
    assert {item.relevance for item in family} == {ComponentRelevance.CANDIDATE}


def test_next_gen_runtime_projection_rejects_an_unscoped_legacy_car() -> None:
    with pytest.raises(ValueError, match="unavailable for car path"):
        build_component_awareness(
            _report(),
            car_path="stockcars camaro zl1 2018 legacy",
        )


def test_runtime_identity_fails_closed_on_car_build_and_track_scope() -> None:
    base_identity = {
        "car_path": "stockcars chevycamarozl12022",
        "car_version": "2026.06.08.02",
        "iracing_build_version": "2026.06.24.02",
        "track_configuration_name": "Oval",
        "missing_required_fields": [],
    }
    manifest = {
        "compatibility_identity": base_identity,
        "schema_fingerprint": "a" * 64,
    }
    manifest["compatibility_fingerprint"] = compatibility_fingerprint(
        manifest["schema_fingerprint"], base_identity
    )
    identity = vehicle_systems_runtime_identity("run-p26", manifest=manifest)
    assert isinstance(identity, VehicleSystemsRuntimeIdentity)
    assert identity.source == "verified_telemetry_manifest"

    for replacement, message in (
        ({"car_path": "stockcars camaro zl1 2018 legacy"}, "car path"),
        ({"iracing_build_version": "2025.12.01.01"}, "does not cover"),
        ({"iracing_build_version": "2026.07.01.01"}, "requires review"),
        ({"track_configuration_name": "Road Course"}, "oval track"),
    ):
        bad_identity = {**base_identity, **replacement}
        bad = {
            **manifest,
            "compatibility_identity": bad_identity,
            "compatibility_fingerprint": compatibility_fingerprint(
                manifest["schema_fingerprint"], bad_identity
            ),
        }
        with pytest.raises(ValueError, match=message):
            vehicle_systems_runtime_identity("run-p26", manifest=bad)


def test_component_inspection_is_a_typed_non_authoritative_contract() -> None:
    projection = build_component_awareness(_report())
    inspection = inspect_component("springs", projection)

    assert inspection.definition.component_id == "springs"
    assert inspection.state is not None
    assert inspection.authority == "p19_projection_only"


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
    base = dict(
        component_id="springs",
        run_id="run-p26",
        current_response_state="unavailable",
        relevance="candidate",
        current_testability="measurement_only",
        authority_state="knowledge_only",
    )
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
    projection = build_component_awareness(_report())

    assert projection.experiment_factors
    assert all(not factor.setup_authorized for factor in projection.experiment_factors)
    assert all(factor.authority == "experiment_definition_only" for factor in projection.experiment_factors)
    front_height = next(item for item in projection.experiment_factors if item.factor_id == "factor:front_platform_height")
    assert front_height.primary_controls == ("lf_ride_height_mm",)
    assert front_height.coordinated_controls == ("rf_ride_height_mm",)
    spring = next(item for item in projection.experiment_factors if item.factor_id == "factor:rf_spring_rate")
    assert spring.automatic_sim_compensations
    assert spring.required_manual_compensations
