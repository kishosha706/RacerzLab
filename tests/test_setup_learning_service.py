from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    DidItWorkVerdict,
    DriverComparison,
    PaceComparison,
    SetupChange,
    TargetZoneComparison,
    TestDisciplineResult,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.services.setup_learning_service import (
    SetupResponseContext,
    build_setup_response_context,
    get_setup_area_biases,
    get_interaction_response_models,
    get_observed_tech_envelope,
    get_setup_response_graph,
    get_setup_response_models,
    record_interaction_response,
    record_setup_response,
    response_environment_key,
)
from racelab_engine.analysis.advanced_experimentation import (
    ExperimentHistorySummary,
    evaluate_experiment_unlock,
)
from racelab_engine.storage.db import initialize_database


def _context(*, build: str = "2026.08.01") -> SetupResponseContext:
    return SetupResponseContext(
        driver_id="driver-1",
        car_name="Next Gen Camaro",
        car_version="car-v1",
        track_name="Charlotte Oval",
        track_configuration="oval",
        track_version="track-v1",
        sim_build=build,
        weather_bucket="25C-30C/dry/low-wind",
        tire_age_bucket="0-5 laps",
        fuel_bucket="40-50 L",
        run_type="setup-test",
        package_archetype="intermediate-oval",
        objective="race-pace",
        baseline_setup_fingerprint="setup-v1",
        tire_compound="dry",
    )


def _record(
    db_path: Path,
    comparison_id: str,
    verdict: str = "keep_direction",
    *,
    sim_integrity_clear: bool | None = True,
    driver_verdict: str = "consistent",
    controlled_effect_eligible: bool = True,
    include_source_runs: bool = True,
    response_context: SetupResponseContext | None = None,
) -> bool:
    context = response_context or _context()
    return record_setup_response(
        comparison_id=comparison_id,
        car_name="Next Gen Camaro",
        track_name="Charlotte Oval",
        baseline_run_id=f"{comparison_id}-a",
        test_run_id=f"{comparison_id}-b",
        baseline_lap=2,
        test_lap=2,
        setup_changes=[SetupChange(
            setup_key="rf_front_spring_n_per_mm",
            label="RF Spring",
            group="springs",
            baseline_value=300.0,
            test_value=305.0,
            significance="small",
            relative_delta_percent=1.667,
        )],
        discipline=TestDisciplineResult(score=92, label="clean"),
        target_zone=TargetZoneComparison(
            start_pct=55.0,
            end_pct=70.0,
            channel_deltas=[
                ComparedChannelDelta("speed_mph", "Speed", "mph", delta=0.25),
                ComparedChannelDelta("cfs_ride_height_in", "CFS", "in", delta=0.01),
            ],
        ),
        verdict=DidItWorkVerdict(verdict=verdict, confidence_score=0.75, headline="Measured result"),
        pace=PaceComparison(
            cohort_delta_s=-0.2,
            noise_band_s=0.05,
            baseline_eligible_laps=4,
            test_eligible_laps=4,
            is_significant=True,
            direction="faster",
            confidence_score=0.8,
        ),
        driver=DriverComparison(driver_verdict=driver_verdict, repeatability_score=92.0),
        context_problem_count=0,
        response_context=context,
        test_driver_id=context.driver_id,
        sim_integrity_clear=sim_integrity_clear,
        controlled_effect_eligible=controlled_effect_eligible,
        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
        source_channels=["lap_dist_pct", "speed_mph"],
        evidence_event_ids=[f"{comparison_id}:event"],
        source_run_ids=(
            [f"{comparison_id}-a", f"{comparison_id}-b", f"{comparison_id}-a2"]
            if include_source_runs else None
        ),
        baseline_setup_passed_tech=True,
        test_setup_passed_tech=True,
        baseline_setup_for_model={"rf_front_spring_n_per_mm": 300.0, "cross_weight_percent": 50.0},
        test_setup_for_model={"rf_front_spring_n_per_mm": 305.0, "cross_weight_percent": 50.0},
        target_phase="center",
        db_path=db_path,
    )


def test_repeated_controlled_tests_create_directional_learning_bias(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    for index in range(3):
        assert _record(db_path, f"comparison-{index}") is True

    biases = get_setup_area_biases(
        "Next Gen Camaro",
        "Charlotte Oval",
        response_context=_context(),
        db_path=db_path,
    )

    signal = biases[("rf_front_spring_n_per_mm", 1)]
    assert signal["count"] == 3
    assert signal["weighted_outcome"] == 1.0
    assert signal["mean_lap_delta_s"] == -0.2
    assert signal["magnitude_counts"] == {"small": 3}
    assert signal["weighted_outcome_by_magnitude"] == {"small": 1.0}
    assert signal["mean_abs_numeric_delta"] == 5.0

    exact = get_setup_area_biases(
        "Next Gen Camaro", "Charlotte Oval", response_context=_context(),
        target_zone=(55.0, 70.0), target_phase="center", db_path=db_path,
    )
    assert ("rf_front_spring_n_per_mm", 1) in exact
    assert get_setup_area_biases(
        "Next Gen Camaro", "Charlotte Oval", response_context=_context(),
        target_zone=(10.0, 20.0), target_phase="center", db_path=db_path,
    ) == {}
    assert get_setup_area_biases(
        "Next Gen Camaro", "Charlotte Oval", response_context=_context(),
        target_zone=(55.0, 70.0), target_phase="exit", db_path=db_path,
    ) == {}


def test_same_physical_aba_cannot_be_counted_again_under_a_new_comparison_id(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    assert _record(db_path, "original") is True

    # A second packet ID that points to the same physical A/B/A2 triplet must
    # not manufacture an independent experiment.
    assert record_setup_response(
        comparison_id="duplicate-packet",
        car_name="Next Gen Camaro",
        track_name="Charlotte Oval",
        baseline_run_id="original-a",
        test_run_id="original-b",
        baseline_lap=2,
        test_lap=2,
        setup_changes=[SetupChange(
            setup_key="rf_front_spring_n_per_mm",
            label="RF Spring",
            group="springs",
            baseline_value=300.0,
            test_value=305.0,
            significance="small",
        )],
        discipline=TestDisciplineResult(score=92, label="clean"),
        target_zone=TargetZoneComparison(start_pct=55.0, end_pct=70.0),
        verdict=DidItWorkVerdict(verdict="keep_direction", confidence_score=0.75, headline="Duplicate"),
        pace=PaceComparison(
            cohort_delta_s=-0.2,
            noise_band_s=0.05,
            baseline_eligible_laps=4,
            test_eligible_laps=4,
            is_significant=True,
        ),
        driver=DriverComparison(driver_verdict="consistent", repeatability_score=92.0),
        context_problem_count=0,
        response_context=_context(),
        test_driver_id="driver-1",
        sim_integrity_clear=True,
        controlled_effect_eligible=True,
        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
        source_channels=["lap_dist_pct", "speed_mph"],
        evidence_event_ids=["duplicate:event"],
        source_run_ids=["original-a", "original-b", "original-a2"],
        baseline_setup_passed_tech=True,
        test_setup_passed_tech=True,
        baseline_setup_for_model={"rf_front_spring_n_per_mm": 300.0, "cross_weight_percent": 50.0},
        test_setup_for_model={"rf_front_spring_n_per_mm": 305.0, "cross_weight_percent": 50.0},
        db_path=db_path,
    ) is False


def test_existing_setup_response_is_idempotent_and_cannot_be_partially_rewritten(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    assert _record(db_path, "immutable") is True
    assert _record(db_path, "immutable") is True
    assert _record(
        db_path,
        "immutable",
        response_context=replace(_context(), objective="qualifying"),
    ) is False

    graph = get_setup_response_graph(_context(), db_path=db_path)
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["response_context"]["objective"] == "race-pace"


def test_uncontrolled_comparison_is_not_learned(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    recorded = record_setup_response(
        comparison_id="bad-test",
        car_name="Next Gen Camaro",
        track_name="Charlotte Oval",
        baseline_run_id="a",
        test_run_id="b",
        baseline_lap=1,
        test_lap=1,
        setup_changes=[],
        discipline=TestDisciplineResult(score=10, label="invalid"),
        target_zone=TargetZoneComparison(start_pct=55, end_pct=70),
        verdict=DidItWorkVerdict(verdict="inconclusive", confidence_score=0.1, headline="Invalid"),
        pace=PaceComparison(),
        driver=DriverComparison(driver_verdict="changed"),
        context_problem_count=1,
        db_path=db_path,
    )

    assert recorded is False
    assert get_setup_area_biases("Next Gen Camaro", "Charlotte Oval", db_path=db_path) == {}


def test_sim_integrity_must_be_observed_clear_before_learning(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"

    assert _record(db_path, "integrity-unknown", sim_integrity_clear=None) is False
    assert _record(db_path, "integrity-failed", sim_integrity_clear=False) is False
    assert get_setup_response_graph(_context(), db_path=db_path)["edges"] == []


def test_memory_requires_confirmed_driver_and_aba_controlled_effect(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"

    assert _record(db_path, "driver-unknown", driver_verdict="unavailable") is False
    assert _record(db_path, "ordinary-ab", controlled_effect_eligible=False) is False
    assert _record(db_path, "missing-a2-provenance", include_source_runs=False) is False
    assert get_setup_response_graph(_context(), db_path=db_path)["edges"] == []


def test_learning_bias_requires_exact_context_and_build(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    for index in range(3):
        assert _record(db_path, f"context-{index}") is True

    assert get_setup_area_biases(
        "Next Gen Camaro",
        "Charlotte Oval",
        response_context=_context(build="2026.09.01"),
        db_path=db_path,
    ) == {}


def test_response_graph_preserves_traceability_and_contradictions(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    assert _record(db_path, "keep-1", verdict="keep_direction") is True
    assert _record(db_path, "undo-1", verdict="undo") is True

    graph = get_setup_response_graph(_context(), db_path=db_path)

    assert len(graph["edges"]) == 2
    assert graph["edges"][0]["source_runs"] == ["keep-1-a", "keep-1-b", "keep-1-a2"]
    assert graph["edges"][0]["evidence"]["evidence_packet_id"] == "keep-1"
    assert graph["edges"][0]["evidence"]["evidence_state"] == "controlled_test_effect"
    assert graph["edges"][0]["evidence"]["source_channels"] == ["lap_dist_pct", "speed_mph"]
    assert graph["edges"][0]["evidence"]["evidence_event_ids"] == ["keep-1:event"]
    assert graph["edges"][0]["evidence"]["hypothesis"] == "Measured result"
    assert graph["edges"][0]["evidence"]["observed_phase_effects"]["median_lap_delta_s"] == -0.2
    assert "countereffects" in graph["edges"][0]["evidence"]
    summary = graph["control_summaries"]["rf_front_spring_n_per_mm:1"]
    assert summary["contradictory"] is True
    assert summary["keep_count"] == 1
    assert summary["undo_count"] == 1
    assert summary["confidence_capped_for_contradiction"] == 0.5
    assert summary["observed_setup_envelope"] == {
        "minimum": 300.0,
        "maximum": 305.0,
        "scope": "observed_exact_context_only",
    }
    assert get_setup_response_graph(_context(build="new-build"), db_path=db_path)["edges"] == []
    assert get_setup_area_biases(
        "Next Gen Camaro",
        "Charlotte Oval",
        db_path=db_path,
    ) == {}


def test_response_graph_skips_malformed_or_cross_context_memory_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "malformed-learning.sqlite"
    assert _record(db_path, "malformed-memory") is True
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE setup_response_observations SET evidence_json = ?",
            ("{bad",),
        )
    connection.close()
    assert get_setup_response_models(_context(), db_path=db_path) == {}
    assert get_setup_response_graph(_context(), db_path=db_path)["edges"] == []

    other_db_path = tmp_path / "cross-context-learning.sqlite"
    assert _record(other_db_path, "cross-context-memory") is True
    connection = initialize_database(other_db_path)
    with connection:
        connection.execute(
            "UPDATE setup_response_observations SET response_context_json = ?",
            ('{"driver_id":"other"}',),
        )
    connection.close()
    assert get_setup_response_graph(_context(), db_path=other_db_path)["edges"] == []

    interaction_db_path = tmp_path / "malformed-interaction.sqlite"
    unlock = evaluate_experiment_unlock(ExperimentHistorySummary(
        phase_exit_passed={f"P{index}": True for index in range(7)},
        controlled_experiments=40,
        distinct_contexts=4,
        experiments_per_factor={"f0": 8, "f1": 8},
        held_out_validation_score=0.8,
        contradiction_rate=0.1,
        traceable_fraction=1.0,
    ))
    assert record_interaction_response(
        experiment_id="malformed-interaction",
        response_context=_context(),
        factor_deltas={"f0": 1.0, "f1": -1.0},
        outcomes={"lap_delta_s": -0.1},
        uncertainty=0.02,
        setup_passed_tech=True,
        evidence_packet_ids=["packet-1"],
        source_run_ids=["a", "b", "a2"],
        experiment_unlock=unlock,
        controlled_effect_eligible=True,
        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
        driver_matched=True,
        sim_integrity_clear=True,
        db_path=interaction_db_path,
    )
    connection = initialize_database(interaction_db_path)
    with connection:
        connection.execute(
            "UPDATE setup_interaction_observations SET factor_deltas_json = ?",
            ("{bad",),
        )
    connection.close()
    assert get_interaction_response_models(
        _context(), db_path=interaction_db_path,
    ) == {}
    assert get_setup_response_graph(
        _context(), db_path=interaction_db_path,
    )["interaction_models"] == {}


def test_reassigned_response_rows_cannot_cross_driver_or_context_scope(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "reassigned-memory.sqlite"
    foreign = replace(_context(), driver_id="driver-foreign")
    victim = _context()
    for index in range(6):
        assert _record(
            db_path,
            f"foreign-{index}",
            response_context=foreign,
        ) is True
    connection = initialize_database(db_path)
    with connection:
        rows = connection.execute(
            "SELECT observation_id FROM setup_response_observations ORDER BY observation_id"
        ).fetchall()
        pairs = ((300.0, 295.0), (300.0, 295.0), (300.0, 305.0),
                 (300.0, 305.0), (300.0, 310.0), (300.0, 310.0))
        for row, (baseline, test) in zip(rows, pairs):
            connection.execute(
                """
                UPDATE setup_response_observations
                SET baseline_value = ?, test_value = ?, numeric_delta = ?,
                    direction_sign = ?
                WHERE observation_id = ?
                """,
                (
                    str(baseline),
                    str(test),
                    test - baseline,
                    1 if test > baseline else -1,
                    row["observation_id"],
                ),
            )
        connection.execute(
            """
            UPDATE setup_response_observations
            SET response_context_key = ?, environment_context_key = ?
            """,
            (victim.key, response_environment_key(victim)),
        )
    connection.close()

    assert get_setup_area_biases(
        victim.car_name,
        victim.track_name,
        response_context=victim,
        minimum_observations=1,
        db_path=db_path,
    ) == {}
    assert get_setup_response_models(
        victim,
        minimum_observations=1,
        db_path=db_path,
    ) == {}
    assert get_observed_tech_envelope(victim, db_path=db_path) == {}
    assert get_setup_response_graph(victim, db_path=db_path)["edges"] == []


def test_response_context_builder_fails_closed_and_versions_setup() -> None:
    identity = {
        "driver_user_id": 42,
        "car_name": "Next Gen Camaro",
        "car_version": "car-v1",
        "track_name": "Charlotte Oval",
        "track_configuration_name": "oval",
        "track_version": "track-v1",
        "iracing_build_version": "2026.08.01",
        "session_type": "Race",
    }
    rows = [
        {
            "air_temp": 25.0,
            "track_temp": 35.0,
            "wind_vel": 2.0,
            "fuel_level": 45.0,
            "lf_tire_distance_m": 1_000.0,
            "tire_compound": "dry",
        }
    ]
    first = build_setup_response_context(
        compatibility_identity=identity,
        rows=rows,
        baseline_setup={"cross_weight": 50.0},
        package_archetype="intermediate-oval",
        objective="race-pace",
    )
    second = build_setup_response_context(
        compatibility_identity=identity,
        rows=rows,
        baseline_setup={"cross_weight": 50.5},
        package_archetype="intermediate-oval",
        objective="race-pace",
    )
    assert first is not None and second is not None
    assert first.key != second.key
    assert build_setup_response_context(
        compatibility_identity={**identity, "driver_user_id": None},
        rows=rows,
        baseline_setup={"cross_weight": 50.0},
        package_archetype="intermediate-oval",
        objective="race-pace",
    ) is None


def test_response_context_requires_complete_weather() -> None:
    identity = {
        "driver_user_id": 42,
        "car_name": "Next Gen Camaro",
        "car_version": "car-v1",
        "track_name": "Charlotte Oval",
        "track_configuration_name": "oval",
        "track_version": "track-v1",
        "iracing_build_version": "2026.08.01",
        "session_type": "Race",
    }
    rows = [{
        "fuel_level": 45.0,
        "lf_tire_distance_m": 1_000.0,
        "tire_compound": "dry",
    }]

    assert build_setup_response_context(
        compatibility_identity=identity,
        rows=rows,
        baseline_setup={"cross_weight": 50.0},
        package_archetype="intermediate-oval",
        objective="race-pace",
    ) is None


def test_response_context_ignores_run_identity_in_setup_fingerprint() -> None:
    identity = {
        "driver_user_id": 42,
        "car_name": "Next Gen Camaro",
        "car_version": "car-v1",
        "track_name": "Charlotte Oval",
        "track_configuration_name": "oval",
        "track_version": "track-v1",
        "iracing_build_version": "2026.08.01",
        "session_type": "Race",
    }
    rows = [{
        "air_temp": 25.0,
        "track_temp": 35.0,
        "wind_vel": 2.0,
        "fuel_level": 45.0,
        "lf_tire_distance_m": 1_000.0,
        "tire_compound": "dry",
    }]
    left = build_setup_response_context(
        compatibility_identity=identity,
        rows=rows,
        baseline_setup={"run_id": "a", "setup_id": "a:setup", "setup_json": {"cross": 50.0}},
        package_archetype="intermediate-oval",
        objective="race-pace",
    )
    right = build_setup_response_context(
        compatibility_identity=identity,
        rows=rows,
        baseline_setup={"run_id": "b", "setup_id": "b:setup", "setup_json": {"cross": 50.0}},
        package_archetype="intermediate-oval",
        objective="race-pace",
    )

    assert left is not None and right is not None
    assert left.baseline_setup_fingerprint == right.baseline_setup_fingerprint


def test_memory_rejects_different_test_driver(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    assert record_setup_response(
        comparison_id="other-driver",
        car_name="Next Gen Camaro",
        track_name="Charlotte Oval",
        baseline_run_id="a",
        test_run_id="b",
        baseline_lap=2,
        test_lap=2,
        setup_changes=[SetupChange(
            setup_key="rf_front_spring_n_per_mm",
            label="RF Spring",
            group="springs",
            baseline_value=300.0,
            test_value=305.0,
            significance="small",
        )],
        discipline=TestDisciplineResult(score=92, label="clean"),
        target_zone=TargetZoneComparison(start_pct=55.0, end_pct=70.0),
        verdict=DidItWorkVerdict(verdict="keep_direction", confidence_score=0.75, headline="Measured"),
        pace=PaceComparison(
            cohort_delta_s=-0.2,
            noise_band_s=0.05,
            baseline_eligible_laps=4,
            test_eligible_laps=4,
            is_significant=True,
        ),
        driver=DriverComparison(driver_verdict="consistent", repeatability_score=92.0),
        context_problem_count=0,
        response_context=_context(),
        test_driver_id="driver-2",
        sim_integrity_clear=True,
        db_path=db_path,
    ) is False


def _record_model_point(
    db_path: Path,
    *,
    comparison_id: str,
    baseline: float,
    delta: float,
    outcome_s: float,
    tech_passed: bool | None = True,
    baseline_tape: float = 20.0,
    test_tape: float = 20.0,
) -> bool:
    context = replace(_context(), baseline_setup_fingerprint=f"baseline-{baseline}")
    return record_setup_response(
        comparison_id=comparison_id,
        car_name=context.car_name,
        track_name=context.track_name,
        baseline_run_id=f"{comparison_id}-a",
        test_run_id=f"{comparison_id}-b",
        baseline_lap=2,
        test_lap=2,
        setup_changes=[SetupChange(
            setup_key="cross_weight_percent",
            label="Cross Weight",
            group="weight_distribution",
            baseline_value=baseline,
            test_value=baseline + delta,
            significance="small",
        )],
        discipline=TestDisciplineResult(score=95, label="clean"),
        target_zone=TargetZoneComparison(start_pct=40.0, end_pct=60.0),
        verdict=DidItWorkVerdict(
            verdict="keep_direction" if outcome_s < 0 else "undo",
            confidence_score=0.82,
            headline="Controlled response",
        ),
        pace=PaceComparison(
            cohort_delta_s=outcome_s,
            noise_band_s=0.02,
            baseline_eligible_laps=4,
            test_eligible_laps=4,
            is_significant=True,
            direction="faster" if outcome_s < 0 else "slower",
            confidence_score=0.85,
        ),
        driver=DriverComparison(driver_verdict="consistent", repeatability_score=94.0),
        context_problem_count=0,
        response_context=context,
        test_driver_id=context.driver_id,
        sim_integrity_clear=True,
        controlled_effect_eligible=True,
        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
        source_channels=["lap_dist_pct", "speed_mph"],
        evidence_event_ids=[f"{comparison_id}:event"],
        source_run_ids=[f"{comparison_id}-a", f"{comparison_id}-b", f"{comparison_id}-a2"],
        baseline_setup_passed_tech=tech_passed,
        test_setup_passed_tech=tech_passed,
        baseline_setup_for_model={"cross_weight_percent": baseline, "tape_percent": baseline_tape},
        test_setup_for_model={"cross_weight_percent": baseline + delta, "tape_percent": test_tape},
        db_path=db_path,
    )


def test_nonlinear_model_groups_baseline_levels_only_when_surrounding_package_matches(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    points = [
        (50.0, -1.0, 0.25), (50.0, -1.0, 0.24),
        (49.5, 0.5, -0.08), (49.5, 0.5, -0.09),
        (50.0, 1.0, -0.1), (50.0, 1.0, -0.11),
    ]
    for index, (baseline, delta, outcome) in enumerate(points):
        assert _record_model_point(
            db_path,
            comparison_id=f"model-{index}",
            baseline=baseline,
            delta=delta,
            outcome_s=outcome,
        )

    models = get_setup_response_models(_context(), db_path=db_path)
    assert len(models) == 1
    model = next(iter(models.values()))
    assert model["setup_key"] == "cross_weight_percent"
    assert model["observed_absolute_control_range"] == {"minimum": 49.0, "maximum": 51.0}
    assert model["observation_count"] == 6
    assert model["distinct_input_count"] == 3
    assert model["nonlinearity_detected"] is True
    assert model["scope"] == "observed_exact_context_only_no_extrapolation"

    envelope = get_observed_tech_envelope(_context(), db_path=db_path)
    item = next(iter(envelope.values()))
    assert item["setup_key"] == "cross_weight_percent"
    assert item["value_kind"] == "continuous_observed_range"
    assert item["scope"] == "observed_tech_passing_exact_context_not_a_universal_limit"
    assert len(item["source_observation_ids"]) == 6


def test_observed_options_keep_provenance_attached_to_each_exact_value(tmp_path: Path) -> None:
    db_path = tmp_path / "per-value-provenance.sqlite"
    assert _record_model_point(
        db_path,
        comparison_id="lower-edge",
        baseline=50.0,
        delta=0.5,
        outcome_s=-0.02,
    )
    assert _record_model_point(
        db_path,
        comparison_id="upper-edge",
        baseline=50.5,
        delta=0.5,
        outcome_s=-0.03,
    )

    envelope = get_observed_tech_envelope(_context(), db_path=db_path)
    item = next(iter(envelope.values()))
    options = {float(option["value"]): set(option["source_observation_ids"]) for option in item["observed_options"]}

    assert set(options) == {50.0, 50.5, 51.0}
    assert len(options[50.0]) == 1
    assert len(options[51.0]) == 1
    assert options[50.0].isdisjoint(options[51.0])
    assert options[50.5] == options[50.0] | options[51.0]


def test_response_model_requires_both_directions_and_replicated_levels(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    for index, delta in enumerate((0.25, 0.5, 0.75, 1.0, 1.25, 1.5)):
        assert _record_model_point(
            db_path,
            comparison_id=f"one-way-{index}",
            baseline=50.0,
            delta=delta,
            outcome_s=-0.02 * delta,
        )
    assert get_setup_response_models(_context(), db_path=db_path) == {}


def test_memory_rejects_unknown_tech_or_changed_surrounding_package(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    assert not _record_model_point(
        db_path,
        comparison_id="unknown-tech",
        baseline=50.0,
        delta=0.5,
        outcome_s=-0.05,
        tech_passed=None,
    )
    assert not _record_model_point(
        db_path,
        comparison_id="changed-package",
        baseline=50.0,
        delta=0.5,
        outcome_s=-0.05,
        baseline_tape=20.0,
        test_tape=25.0,
    )
    assert get_setup_response_graph(_context(), db_path=db_path)["edges"] == []


def test_qualified_interaction_learning_is_traceable_and_exact_context(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    history = ExperimentHistorySummary(
        phase_exit_passed={f"P{index}": True for index in range(7)},
        controlled_experiments=40,
        distinct_contexts=4,
        experiments_per_factor={"f0": 8, "f1": 8},
        held_out_validation_score=0.8,
        contradiction_rate=0.1,
        traceable_fraction=1.0,
    )
    unlock = evaluate_experiment_unlock(history)
    rows = [(-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0)] * 2
    for index, (left, right) in enumerate(rows):
        assert record_interaction_response(
            experiment_id=f"doe-{index}",
            response_context=_context(),
            factor_deltas={"f0": left, "f1": right},
            outcomes={"lap_time_delta_s": 0.1 * left + 0.2 * right + 0.4 * left * right},
            uncertainty=0.03,
            setup_passed_tech=True,
            evidence_packet_ids=[f"packet-{index}"],
            source_run_ids=[f"run-{index}-a", f"run-{index}-b", f"run-{index}-a2"],
            experiment_unlock=unlock,
            controlled_effect_eligible=True,
            evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
            driver_matched=True,
            sim_integrity_clear=True,
            db_path=db_path,
        )

    model = get_interaction_response_models(_context(), db_path=db_path)
    coefficients = model["outcomes"]["lap_time_delta_s"]["coefficients"]
    assert coefficients["f0*f1"] == pytest.approx(0.4, abs=1e-5)
    assert model["observation_count"] == 8
    assert len(model["evidence_packet_ids"]) == 8

    assert record_interaction_response(
        experiment_id="doe-0",
        response_context=replace(_context(), objective="qualifying"),
        factor_deltas={"f0": 9.0, "f1": 8.0},
        outcomes={"lap_time_delta_s": 99.0},
        uncertainty=0.5,
        setup_passed_tech=True,
        evidence_packet_ids=["replacement-packet"],
        source_run_ids=["replacement-a", "replacement-b", "replacement-a2"],
        experiment_unlock=unlock,
        controlled_effect_eligible=True,
        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
        driver_matched=True,
        sim_integrity_clear=True,
        db_path=db_path,
    ) is False

    unchanged = get_interaction_response_models(_context(), db_path=db_path)
    assert unchanged["outcomes"]["lap_time_delta_s"]["coefficients"]["f0*f1"] == pytest.approx(0.4, abs=1e-5)


def test_interaction_admission_requires_controlled_context_and_two_real_factor_changes(tmp_path: Path) -> None:
    history = ExperimentHistorySummary(
        phase_exit_passed={f"P{index}": True for index in range(7)},
        controlled_experiments=40,
        distinct_contexts=4,
        experiments_per_factor={"f0": 8, "f1": 8},
        held_out_validation_score=0.8,
        contradiction_rate=0.1,
        traceable_fraction=1.0,
    )
    unlock = evaluate_experiment_unlock(history)
    common = dict(
        experiment_id="blocked-doe",
        response_context=_context(),
        outcomes={"lap_time_delta_s": -0.1},
        uncertainty=0.02,
        setup_passed_tech=True,
        evidence_packet_ids=["packet"],
        source_run_ids=["run-a", "run-b", "run-a2"],
        experiment_unlock=unlock,
        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
        driver_matched=True,
        sim_integrity_clear=True,
        db_path=tmp_path / "learning.sqlite",
    )
    assert record_interaction_response(
        **common,
        factor_deltas={"f0": 1.0, "f1": 0.0},
        controlled_effect_eligible=True,
    ) is False
    assert record_interaction_response(
        **common,
        factor_deltas={"f0": 1.0, "f1": -1.0},
        controlled_effect_eligible=False,
    ) is False
