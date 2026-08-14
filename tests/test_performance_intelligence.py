from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.time_alignment import (
    AlignmentPoint,
    NoiseEstimate,
    PhaseTimeEffect,
    TimeAlignmentResult,
)
from racelab_engine.models.crew_chief import EngineeringObjective
from racelab_engine.models.performance_intelligence import (
    ComponentPerformanceInfluence,
    CornerPerformanceChain,
    DriverVehicleResult,
    LapTimeOpportunityMap,
    PerformanceExplanationEdge,
    PerformanceExplanationChain,
    PerformancePhaseState,
    SpeedStory,
    TimeOriginKind,
)
from racelab_engine.services.performance_intelligence_service import (
    _component_influences,
    _opportunities,
    _separation,
    objective_envelope,
    performance_mechanisms,
    performance_principles,
)


def _effect(
    phase: str,
    start: float,
    end: float,
    delta: float,
) -> PhaseTimeEffect:
    return PhaseTimeEffect(
        phase=phase,
        start_pct=start,
        end_pct=end,
        delta_s=delta,
        cumulative_delta_s=None,
        alignment_confidence=1.0,
        evidence_state="calculated",
        source_channels=["lap_dist_ft", "speed_mph"],
        calculation_basis="reciprocal_speed_integration",
        interpretation="Measured elapsed-time effect.",
    )


def _alignment(effect: PhaseTimeEffect, cumulative: list[float]) -> TimeAlignmentResult:
    grid = [0.0, 50.0, 100.0]
    return TimeAlignmentResult(
        grid_pct=grid,
        phase_by_position=[effect.phase] * 3,
        phases=[],
        alignment=[
            AlignmentPoint(
                lap_pct=value,
                aligned_test_pct=value,
                confidence=1.0,
                uncertainty_pct=0.0,
                methods=["track_distance_geometry"],
            )
            for value in grid
        ],
        cumulative_delta_s=cumulative,
        incremental_delta_s=[0.0, effect.delta_s, 0.0],
        incremental_basis=[None, "reciprocal_speed_integration", None],
        baseline_elapsed_s=[0.0, 1.0, 2.0],
        test_elapsed_s=[0.0, 1.0, 2.0],
        phase_effects=[effect],
        phase_attribution={},
        gain_origin_pct=None,
        gain_origin_phase=None,
        surrender_pct=None,
        gain_persistence_pct=None,
        selected_effect_s=cumulative[-1],
        time_delta_complete=True,
        theoretical_opportunity_s=None,
        repeatable_opportunity_s=None,
        noise=NoiseEstimate(),
        coverage_fraction=1.0,
        local_alignment_confidence=1.0,
        distance_basis="reciprocal_speed_integration",
        warnings=[],
        source_channels=["track_distance_geometry"],
    )


def _state(**updates: object) -> PerformancePhaseState:
    values: dict[str, object] = {
        "phase": "center",
        "start_pct": 20.0,
        "end_pct": 30.0,
        "elapsed_delta_s": 0.08,
        "speed_delta_mph": -1.2,
        "throttle_delta_pct": 0.0,
        "brake_delta_pct": 0.0,
        "steering_delta_deg": 0.0,
        "yaw_rate_delta": 0.8,
        "long_accel_delta": 0.0,
        "path_delta_m": 0.0,
        "driver_demand_source_coverage": 1.0,
        "driver_demand_reference_coverage": 1.0,
        "evidence_state": "measured",
        "source_channels": ("session_time", "speed_mph", "yaw_rate"),
    }
    values.update(updates)
    return PerformancePhaseState(**values)


def test_p32_knowledge_registry_is_versioned_non_authoritative_and_complete() -> None:
    principles = performance_principles()
    mechanisms = performance_mechanisms()
    assert len(principles) == 12
    assert len({item.principle_id for item in principles}) == 12
    assert all(
        item.authority == "knowledge_only" and item.source_ids for item in principles
    )
    assert {item.mechanism_id for item in mechanisms} >= {
        "braking_realization",
        "center_rotation",
        "exit_carry",
        "path_efficiency",
        "traffic_robustness",
    }
    assert all(
        "cause" in " ".join(item.forbidden_claims).casefold() for item in mechanisms
    )


def test_objective_changes_policy_envelope_not_measured_physics() -> None:
    qualifying = objective_envelope(EngineeringObjective.QUALIFYING_PEAK)
    long_run = objective_envelope(EngineeringObjective.RACE_LONG_RUN)
    assert qualifying.primary_outcomes != long_run.primary_outcomes
    assert qualifying.physics_changes is long_run.physics_changes is False
    assert qualifying.setup_authorized is long_run.setup_authorized is False


def test_straight_deficit_carried_from_exit_cannot_become_powertrain_diagnosis() -> (
    None
):
    effect = _effect("straight", 50.0, 100.0, 0.01)
    opportunities = _opportunities(
        "run-1",
        5,
        4,
        _alignment(effect, [0.2, 0.205, 0.21]),
        (),
        SimpleNamespace(report=SimpleNamespace(opportunity_signature=None)),
        SimpleNamespace(leading_component_ids=()),
        False,
    )
    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.origin_kind is TimeOriginKind.CARRIED_IN
    assert opportunity.mechanism_candidates == ("exit_carry",)
    assert "straight_acceleration" not in opportunity.mechanism_candidates
    assert any(
        "not a powertrain diagnosis" in item for item in opportunity.contradictions
    )


def test_traffic_blocks_full_throttle_straight_attribution() -> None:
    effect = _effect("straight", 50.0, 100.0, 0.12)
    opportunity = _opportunities(
        "run-1",
        5,
        4,
        _alignment(effect, [0.0, 0.02, 0.14]),
        (),
        SimpleNamespace(report=SimpleNamespace(opportunity_signature=None)),
        SimpleNamespace(leading_component_ids=()),
        True,
    )[0]
    assert opportunity.context_state == "traffic_contaminated"
    assert any("Traffic exposure blocks" in item for item in opportunity.contradictions)


def test_driver_line_change_blocks_setup_attribution() -> None:
    separation = _separation("run-1", _state(path_delta_m=2.5), traffic=False)
    assert separation.result is DriverVehicleResult.CONTEXT_CONTAMINATED
    assert separation.line_changed is True
    assert any("driver-line" in item for item in separation.blockers)


def test_matched_inputs_with_changed_response_remains_vehicle_candidate_only() -> None:
    separation = _separation("run-1", _state(), traffic=False)
    assert (
        separation.result
        is DriverVehicleResult.VEHICLE_RESPONSE_CHANGED_WITH_MATCHED_INPUTS
    )
    assert separation.authority == "observation_only"


def test_one_pair_cannot_be_published_as_repeatable_opportunity() -> None:
    effect = _effect("center", 0.0, 50.0, 0.12)
    opportunity = _opportunities(
        "run-1",
        5,
        4,
        _alignment(effect, [0.0, 0.12, 0.12]),
        (),
        SimpleNamespace(report=SimpleNamespace(opportunity_signature=None)),
        SimpleNamespace(leading_component_ids=()),
        False,
    )[0]
    assert opportunity.repeatability == "observed_once"


def test_missing_time_data_stays_unavailable() -> None:
    state = PerformancePhaseState(
        phase="center",
        start_pct=20,
        end_pct=30,
        evidence_state="unavailable",
        blockers=("Speed/time/path data are missing.",),
    )
    assert state.elapsed_delta_s is None
    with pytest.raises(ValidationError, match="requires blockers"):
        PerformancePhaseState(
            phase="center",
            start_pct=20,
            end_pct=30,
            evidence_state="unavailable",
        )


def test_theoretical_composite_cannot_be_marked_guaranteed() -> None:
    with pytest.raises(ValidationError):
        LapTimeOpportunityMap(
            run_id="run-1",
            setup_id="setup-1",
            physical_alignment_identity="a" * 64,
            coverage=1.0,
            noise_basis="measured",
            theoretical_composite_s=0.2,
            theoretical_is_guaranteed=True,
        )


def test_explanation_graph_has_no_generic_cause_edge_and_story_rejects_causation() -> (
    None
):
    with pytest.raises(ValidationError):
        PerformanceExplanationEdge(
            source_id="component",
            target_id="time",
            kind="causes",
        )


def test_higher_minimum_speed_cannot_override_slower_complete_corner() -> None:
    center = _state(speed_delta_mph=2.0, elapsed_delta_s=0.08)
    chain = CornerPerformanceChain(
        chain_id="chain-1",
        track_region="Turn 1",
        center_state=center,
        local_time_effect_s=0.08,
        contradictions=("Minimum speed alone is not the complete corner.",),
    )
    assert chain.center_state is not None
    assert chain.center_state.speed_delta_mph > 0
    assert chain.local_time_effect_s > 0


def test_later_braking_cannot_hide_worse_exit_and_carry() -> None:
    chain = CornerPerformanceChain(
        chain_id="chain-2",
        track_region="Turn 2",
        braking_state=_state(
            phase="braking", elapsed_delta_s=-0.02, brake_delta_pct=4.0
        ),
        exit_state=_state(phase="exit", elapsed_delta_s=0.08),
        carry_state=_state(phase="carry", elapsed_delta_s=0.05),
        local_time_effect_s=0.06,
        downstream_time_effect_s=0.05,
        contradictions=("The exit and carry countereffect remains protected.",),
    )
    assert chain.braking_state.elapsed_delta_s < 0
    assert chain.local_time_effect_s > 0
    assert chain.downstream_time_effect_s > 0


def test_higher_top_speed_with_slower_elapsed_time_remains_a_loss() -> None:
    approach = _state(
        phase="approach", speed_delta_mph=5.0, elapsed_delta_s=0.1
    )
    assert approach.speed_delta_mph > 0
    assert approach.elapsed_delta_s > 0


def test_shorter_path_with_lower_speed_is_judged_by_time_and_remains_confounding() -> None:
    state = _state(path_delta_m=-4.0, speed_delta_mph=-2.0, elapsed_delta_s=0.09)
    separation = _separation("run-1", state, traffic=False)
    assert state.path_delta_m < 0
    assert state.elapsed_delta_s > 0
    assert separation.result is DriverVehicleResult.CONTEXT_CONTAMINATED


def test_one_multi_system_time_episode_remains_one_evidence_unit() -> None:
    opportunity = _opportunities(
        "run-1",
        5,
        4,
        _alignment(_effect("center", 0.0, 50.0, 0.12), [0.0, 0.12, 0.12]),
        (),
        SimpleNamespace(report=SimpleNamespace(opportunity_signature=None)),
        SimpleNamespace(leading_component_ids=("anti_roll_bars", "springs")),
        False,
    )
    assert len(opportunity) == 1
    assert set(opportunity[0].component_candidates) == {"anti_roll_bars", "springs"}


def test_cross_start_finish_windows_remain_two_exact_physical_segments() -> None:
    effects = (_effect("exit", 0.0, 5.0, 0.06), _effect("entry", 95.0, 100.0, 0.06))
    alignment = _alignment(effects[0], [0.0, 0.06, 0.12])
    alignment = replace(
        alignment,
        grid_pct=[0.0, 5.0, 95.0, 100.0],
        cumulative_delta_s=[0.0, 0.06, 0.06, 0.12],
        phase_effects=list(effects),
    )
    opportunities = _opportunities(
        "run-1",
        5,
        4,
        alignment,
        (),
        SimpleNamespace(report=SimpleNamespace(opportunity_signature=None)),
        SimpleNamespace(leading_component_ids=()),
        False,
    )
    assert {(item.start_pct, item.end_pct) for item in opportunities} == {
        (0.0, 5.0),
        (95.0, 100.0),
    }


def test_p26_relevance_cannot_become_component_cause_or_setup_authority() -> None:
    influence = ComponentPerformanceInfluence(
        influence_id="influence-1",
        component_id="anti_roll_bars",
        performance_mechanism_ids=("center_rotation",),
        expected_state_ids=("front roll response",),
        measurable_through=("phase elapsed time",),
        runtime_support_state="mechanically_relevant",
        contradictions=("Mechanical relevance is not component cause.",),
        authority="knowledge_only",
    )
    assert influence.setup_authorized is False
    assert influence.runtime_support_state == "mechanically_relevant"


def test_exact_undo_history_outranks_generic_component_relevance() -> None:
    history = SimpleNamespace(exact_context=True, policy_verdict="undo")
    state = SimpleNamespace(
        component_id="anti_roll_bars",
        controlled_history=(history,),
        current_response_state="candidate",
        available_live_channel_ids=(),
        quantity_observability=(),
        supporting_artifact_ids=(),
    )
    p26 = SimpleNamespace(
        component_states=(state,), runtime_graph=SimpleNamespace(nodes=())
    )
    opportunity = SimpleNamespace(
        component_candidates=("anti_roll_bars",),
        mechanism_candidates=("center_rotation",),
        opportunity_id="opportunity-1",
    )
    result = _component_influences(p26, (opportunity,))[0]
    assert result.runtime_support_state == "controlled_response_observed"
    assert result.authority == "controlled_history"
    assert "Undo" in result.contradictions[0]


def test_every_explanation_requires_a_strongest_contradiction() -> None:
    with pytest.raises(ValidationError):
        PerformanceExplanationChain(
            chain_id="explanation-1",
            node_ids=("time",),
            strongest_contradiction="",
            p19_next_move="Measure again.",
        )


def test_speed_story_rejects_optimal_setup_language() -> None:
    with pytest.raises(ValidationError, match="optimization"):
        SpeedStory(
            what_costs_time="Center costs time.",
            where_it_starts="Brake release.",
            what_carries="Exit carry.",
            driver="Inputs match.",
            car="Response remains uncertain.",
            systems="The optimal setup is a stiffer bar.",
            history="No exact history.",
            strongest_contradiction="Line uncertainty.",
            next="Measure again.",
        )
    with pytest.raises(ValidationError, match="causation"):
        SpeedStory(
            what_costs_time="Center costs time.",
            where_it_starts="Brake release.",
            what_carries="Exit carry.",
            driver="Inputs match.",
            car="The loss was caused by the front bar.",
            systems="Front systems are relevant.",
            history="No exact history.",
            strongest_contradiction="Line uncertainty.",
            next="Measure again.",
        )
