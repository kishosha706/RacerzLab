from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS
from racelab_engine.models.vehicle_systems import (
    ComponentAwarenessState,
    ComponentObservabilityState,
    ComponentRelevance,
    VehicleSystemsEdgeKind,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.services.vehicle_systems_service import (
    build_component_awareness,
    compile_vehicle_systems_graph,
    trace_control_mechanism,
)


def _cause(*, outcome: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        hypothesis="Cross weight may influence center rotation.",
        controlled_outcomes=(outcome,) if outcome is not None else (),
        supporting_evidence=(),
        contradicting_evidence=(),
        status="possible",
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


def test_generic_language_cannot_activate_component_relevance_by_word_overlap() -> None:
    unrelated = SimpleNamespace(
        hypothesis="Traffic and weather context remain unresolved.",
        controlled_outcomes=(),
        supporting_evidence=(),
        contradicting_evidence=(),
        status="possible",
    )
    projection = build_component_awareness(_report(causes=(unrelated,)))

    assert all(item.relevance is ComponentRelevance.IRRELEVANT for item in projection.component_states)


def test_next_gen_runtime_projection_rejects_an_unscoped_legacy_car() -> None:
    with pytest.raises(ValueError, match="unavailable for car path"):
        build_component_awareness(
            _report(),
            car_path="stockcars camaro zl1 2018 legacy",
        )


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
