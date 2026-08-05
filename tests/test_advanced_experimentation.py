from __future__ import annotations

import pytest

from racelab_engine.analysis.advanced_experimentation import (
    ExperimentHistorySummary,
    Factor,
    ObjectivePoint,
    ObjectiveProfile,
    SearchObservation,
    contextual_bayesian_parameter_search,
    evaluate_experiment_unlock,
    fractional_factorial_design,
    pareto_frontier,
    response_surface_terms,
    select_next_design_run,
    select_objectives,
)


def _history(*, complete: bool) -> ExperimentHistorySummary:
    return ExperimentHistorySummary(
        phase_exit_passed={f"P{index}": complete for index in range(7)},
        controlled_experiments=40 if complete else 5,
        distinct_contexts=4 if complete else 1,
        experiments_per_factor={f"f{index}": 8 for index in range(5)} if complete else {"cross_weight": 2},
        held_out_validation_score=0.8 if complete else None,
        contradiction_rate=0.1 if complete else None,
        traceable_fraction=1.0 if complete else 0.8,
    )


def test_advanced_experimentation_fails_closed_until_p0_p6_pass() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=False))
    assert unlock.unlocked is False
    assert len(unlock.blockers) >= 6
    with pytest.raises(ValueError, match="locked"):
        fractional_factorial_design(
            [Factor(key="cross", low=49.5, high=50.5), Factor(key="bias", low=51.0, high=52.0)],
            unlock,
        )


def test_fractional_design_and_sequential_selection_are_deterministic() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=True))
    assert unlock.unlocked is True
    factors = [Factor(key=f"f{index}", low=0.0, high=1.0) for index in range(5)]
    design = fractional_factorial_design(factors, unlock)
    assert len(design) == 16
    assert all(run.coded_levels["f4"] in {-1, 1} for run in design)
    assert select_next_design_run(design, set()) == design[0]
    assert select_next_design_run(design, {1}) is not None


def test_fractional_design_rejects_factors_without_controlled_history() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=True))

    with pytest.raises(ValueError, match="lack the required controlled history"):
        fractional_factorial_design(
            [Factor(key="f0", low=0.0, high=1.0), Factor(key="invented", low=0.0, high=1.0)],
            unlock,
        )


def test_response_surface_terms_include_interactions() -> None:
    terms = response_surface_terms({"b": 2.0, "a": 3.0})
    assert terms == {
        "intercept": 1.0,
        "a": 3.0,
        "a^2": 9.0,
        "b": 2.0,
        "b^2": 4.0,
        "a*b": 6.0,
    }


def test_pareto_frontier_keeps_tradeoffs_and_uncertainty() -> None:
    points = [
        ObjectivePoint(experiment_id="fast-risky", objectives={"lap_time": 29.8, "falloff": 0.5}, uncertainty=0.2),
        ObjectivePoint(experiment_id="balanced", objectives={"lap_time": 30.0, "falloff": 0.2}, uncertainty=0.1),
        ObjectivePoint(experiment_id="dominated", objectives={"lap_time": 30.2, "falloff": 0.6}, uncertainty=0.3),
    ]
    frontier = pareto_frontier(points, minimize={"lap_time", "falloff"})
    assert {point.experiment_id for point in frontier} == {"fast-risky", "balanced"}


def test_explicit_objective_profiles_return_different_valid_compromises() -> None:
    points = [
        ObjectivePoint(experiment_id="qualifying", objectives={"lap_time": 29.7, "falloff": 0.7}, uncertainty=0.2),
        ObjectivePoint(experiment_id="long-run", objectives={"lap_time": 30.0, "falloff": 0.15}, uncertainty=0.05),
    ]
    choices = select_objectives(points, [
        ObjectiveProfile(name="qualifying", weights={"lap_time": 1.0, "falloff": 0.05}, uncertainty_weight=0.1),
        ObjectiveProfile(name="long-run", weights={"lap_time": 0.1, "falloff": 1.0}, uncertainty_weight=0.5),
        ObjectiveProfile(name="highest-confidence", weights={"lap_time": 0.01, "falloff": 0.01}, uncertainty_weight=10.0),
    ])

    assert choices["qualifying"].experiment_id == "qualifying"
    assert choices["long-run"].experiment_id == "long-run"
    assert choices["highest-confidence"].experiment_id == "long-run"


def _search_observations(*, context: str = "ctx") -> list[SearchObservation]:
    values = (49.5, 49.75, 50.0, 50.25, 50.5, 50.75, 51.0, 51.25)
    return [
        SearchObservation(
            experiment_id=f"search-{index}",
            context_key=context,
            values={"f0": value, "f1": 2.0},
            objective=(value - 50.4) ** 2 + 0.1,
            measurement_uncertainty=0.03,
            setup_passed_tech=True,
            evidence_packet_ids=(f"packet-{index}",),
            source_run_ids=(f"search-{index}-a", f"search-{index}-b", f"search-{index}-a2"),
        )
        for index, value in enumerate(values)
    ]


def test_contextual_parameter_search_selects_one_control_inside_observed_envelope() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=True))
    result = contextual_bayesian_parameter_search(
        context_key="ctx",
        observations=_search_observations(),
        current_values={"f0": 50.0, "f1": 2.0},
        candidates=[
            {"f0": 50.25, "f1": 2.0},
            {"f0": 50.5, "f1": 2.0},
            {"f0": 50.75, "f1": 2.0},
        ],
        observed_tech_envelope={"f0": (49.5, 51.25), "f1": (1.5, 2.5)},
        legal_values={
            "f0": (49.5, 49.75, 50.0, 50.25, 50.5, 50.75, 51.0, 51.25),
            "f1": (2.0,),
        },
        unlock=unlock,
    )
    assert result.status == "ready"
    assert result.selected is not None
    assert result.selected.changed_factor == "f0"
    assert result.selected.values["f1"] == 2.0
    assert result.selected.predicted_interval_95[0] <= result.selected.predicted_objective
    assert result.selected.predicted_interval_95[1] >= result.selected.predicted_objective
    assert result.scope == "next_controlled_test_only_within_observed_tech_envelope"


def test_parameter_search_fails_closed_for_context_mix_illegal_or_multiple_changes() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=True))
    mixed = _search_observations()
    mixed[-1] = mixed[-1].model_copy(update={"context_key": "other"})
    result = contextual_bayesian_parameter_search(
        context_key="ctx",
        observations=mixed,
        current_values={"f0": 50.0, "f1": 2.0},
        candidates=[{"f0": 50.4, "f1": 2.2}],
        observed_tech_envelope={"f0": (49.5, 51.25), "f1": (1.5, 2.5)},
        legal_values={"f0": (49.5, 50.0, 50.5, 51.0), "f1": (2.0,)},
        unlock=unlock,
    )
    assert result.status == "blocked"
    assert result.selected is None
    assert any("different contexts" in blocker for blocker in result.blockers)


def test_parameter_search_uncertainty_is_lower_near_supported_points() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=True))
    result = contextual_bayesian_parameter_search(
        context_key="ctx",
        observations=_search_observations(),
        current_values={"f0": 50.0, "f1": 2.0},
        candidates=[{"f0": 50.25, "f1": 2.0}, {"f0": 51.2, "f1": 2.0}],
        observed_tech_envelope={"f0": (49.5, 51.25), "f1": (1.5, 2.5)},
        legal_values={
            "f0": (49.5, 49.75, 50.0, 50.25, 50.5, 50.75, 51.0, 51.2, 51.25),
            "f1": (2.0,),
        },
        unlock=unlock,
    )
    assert result.status == "ready"
    by_value = {item.values["f0"]: item for item in result.ranked_candidates}
    assert by_value[50.25].predictive_uncertainty < by_value[51.2].predictive_uncertainty


def test_parameter_search_blocks_underflow_length_scale_and_missing_factor_legal_table() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=True))
    common = dict(
        context_key="ctx",
        observations=_search_observations(),
        current_values={"f0": 50.0, "f1": 2.0},
        candidates=[{"f0": 50.25, "f1": 2.0}],
        observed_tech_envelope={"f0": (49.5, 51.25), "f1": (1.5, 2.5)},
        unlock=unlock,
    )
    tiny = contextual_bayesian_parameter_search(
        **common,
        legal_values={"f0": (50.0, 50.25), "f1": (2.0,)},
        length_scale=1e-300,
    )
    assert tiny.status == "blocked"
    assert any("length scale" in blocker for blocker in tiny.blockers)

    missing = contextual_bayesian_parameter_search(
        **common,
        legal_values={"f0": (50.0, 50.25)},
    )
    assert missing.status == "blocked"
    assert any("every searched factor" in blocker.lower() for blocker in missing.blockers)


def test_parameter_search_rejects_duplicate_or_shared_physical_experiments() -> None:
    unlock = evaluate_experiment_unlock(_history(complete=True))
    observations = _search_observations()
    observations[1] = observations[1].model_copy(update={
        "experiment_id": observations[0].experiment_id,
        "source_run_ids": (
            observations[0].source_run_ids[0],
            "different-b",
            "different-a2",
        ),
    })
    result = contextual_bayesian_parameter_search(
        context_key="ctx",
        observations=observations,
        current_values={"f0": 50.0, "f1": 2.0},
        candidates=[{"f0": 50.25, "f1": 2.0}],
        observed_tech_envelope={"f0": (49.5, 51.25), "f1": (1.5, 2.5)},
        legal_values={
            "f0": (49.5, 49.75, 50.0, 50.25, 50.5, 50.75, 51.0, 51.25),
            "f1": (2.0,),
        },
        unlock=unlock,
    )
    assert result.status == "blocked"
    assert any("unique controlled experiment" in blocker for blocker in result.blockers)
    assert any("disjoint source runs" in blocker for blocker in result.blockers)


def test_advanced_models_reject_nonfinite_and_ambiguous_objectives() -> None:
    with pytest.raises(ValueError):
        Factor(key="bad", low=float("nan"), high=1.0)
    with pytest.raises(ValueError):
        ObjectivePoint(experiment_id="bad", objectives={"lap": float("nan")}, uncertainty=0.1)
    with pytest.raises(ValueError):
        ObjectiveProfile(name="bad", weights={"lap": 1.0, "falloff": -1.0})
    with pytest.raises(ValueError):
        response_surface_terms({"f0": float("inf")})
    point = ObjectivePoint(experiment_id="p", objectives={"lap": 1.0}, uncertainty=0.1)
    with pytest.raises(ValueError, match="unique"):
        select_objectives(
            [point],
            [ObjectiveProfile(name="same", weights={"lap": 1.0}), ObjectiveProfile(name="same", weights={"lap": 1.0})],
        )


def test_pareto_equal_objectives_discards_higher_uncertainty() -> None:
    low = ObjectivePoint(experiment_id="low", objectives={"lap": 30.0}, uncertainty=0.05)
    high = ObjectivePoint(experiment_id="high", objectives={"lap": 30.0}, uncertainty=0.2)
    assert pareto_frontier([low, high], minimize={"lap"}) == (low,)
