from __future__ import annotations

from dataclasses import replace
from pathlib import Path
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
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.performance_intelligence import (
    DriverVehicleResult,
    LapTimeOpportunity,
    PerformancePhaseState,
    SpeedStory,
    TimeOriginKind,
)
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import performance_intelligence_service as service
from racelab_engine.services.import_service import (
    TelemetryArtifactIdentityError,
    read_telemetry_rows,
)
from racelab_engine.storage.db import default_db_path


def _effect(phase: str, start: float, end: float, delta: float) -> PhaseTimeEffect:
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


def _alignment(
    effects: list[PhaseTimeEffect],
    grid: list[float],
    cumulative: list[float | None],
) -> TimeAlignmentResult:
    return TimeAlignmentResult(
        grid_pct=grid,
        phase_by_position=[effects[0].phase] * len(grid),
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
        incremental_delta_s=[0.0] * len(grid),
        incremental_basis=[None] * len(grid),
        baseline_elapsed_s=[float(index) for index in range(len(grid))],
        test_elapsed_s=[float(index) for index in range(len(grid))],
        phase_effects=effects,
        phase_attribution={},
        gain_origin_pct=None,
        gain_origin_phase=None,
        surrender_pct=None,
        gain_persistence_pct=None,
        selected_effect_s=next(
            (value for value in reversed(cumulative) if value is not None), None
        ),
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


def _bundle(signatures: tuple[object, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        report=SimpleNamespace(
            opportunity_signature=SimpleNamespace(signatures=signatures)
        )
    )


def _rows(
    points: list[float], *, traffic: bool | None = False
) -> list[dict[str, float | None]]:
    return [
        {
            "lap_dist_pct_100": point,
            "speed_mps": 60.0,
            "car_distance_ahead_m": None
            if traffic is None
            else 10.0
            if traffic
            else 100.0,
            "car_distance_behind_m": None
            if traffic is None
            else 10.0
            if traffic
            else 100.0,
        }
        for point in points
    ]


def test_gain_and_loss_sorting_preserves_elapsed_time_sign() -> None:
    gain = _effect("entry", 0.0, 40.0, -0.10)
    loss = _effect("center", 40.0, 100.0, 0.06)
    opportunities = service._opportunities(
        "run",
        2,
        1,
        _alignment([gain, loss], [0.0, 40.0, 100.0], [0.0, -0.10, -0.04]),
        (),
        _bundle(),
        None,
        False,
    )
    assert opportunities[0].local_delta_s == pytest.approx(0.06)
    assert any(item.local_delta_s == pytest.approx(-0.10) for item in opportunities)
    assert service._origin(gain, 0.0, -0.10, 0.02) is TimeOriginKind.LOCAL_GENERATION


def test_traffic_is_window_local_and_blocks_component_candidates() -> None:
    first = _effect("center", 0.0, 50.0, 0.08)
    second = _effect("entry", 50.0, 100.0, 0.07)
    source = _rows([0.0, 25.0], traffic=True) + _rows([75.0, 100.0])
    reference = _rows([0.0, 25.0, 75.0, 100.0])
    opportunities = service._opportunities(
        "run",
        2,
        1,
        _alignment([first, second], [0.0, 50.0, 100.0], [0.0, 0.08, 0.15]),
        (),
        _bundle(),
        SimpleNamespace(leading_component_ids=()),
        True,
        source_rows=source,
        reference_rows=reference,
        source_traffic_fraction=0.5,
        reference_traffic_fraction=0.0,
    )
    contaminated = next(item for item in opportunities if item.phase == "center")
    clean = next(item for item in opportunities if item.phase == "entry")
    assert contaminated.attribution_state == "blocked_by_traffic"
    assert contaminated.component_candidates == ()
    assert clean.attribution_state == "candidate_only"
    assert clean.component_candidates


def test_traffic_uses_canonical_time_gap_gate_and_partial_coverage_fails_closed() -> (
    None
):
    within_time_gap = [
        {
            "speed_mps": 67.0,
            "car_distance_ahead_m": 80.0,
            "car_distance_behind_m": 500.0,
        }
    ]
    assert service._traffic_exposure(within_time_gap) == 1.0
    assert (
        service._traffic_exposure(
            [
                {
                    "speed_mps": 67.0,
                    "car_distance_ahead_m": None,
                    "car_distance_behind_m": 500.0,
                }
            ]
        )
        is None
    )


def test_any_measured_traffic_exposure_blocks_the_exact_window() -> None:
    effect = _effect("center", 0.0, 100.0, 0.08)
    source = [
        {
            "lap_dist_pct_100": float(index),
            "speed_mps": 60.0,
            "car_distance_ahead_m": 10.0 if index == 50 else 500.0,
            "car_distance_behind_m": 500.0,
        }
        for index in range(101)
    ]
    reference = [
        {
            "lap_dist_pct_100": float(index),
            "speed_mps": 60.0,
            "car_distance_ahead_m": 500.0,
            "car_distance_behind_m": 500.0,
        }
        for index in range(101)
    ]
    opportunity = service._opportunities(
        "run",
        2,
        1,
        _alignment([effect], [0.0, 100.0], [0.0, 0.08]),
        (),
        _bundle(),
        SimpleNamespace(leading_component_ids=()),
        True,
        source_rows=source,
        reference_rows=reference,
    )[0]
    assert opportunity.source_traffic_exposure_fraction == pytest.approx(1 / 101)
    assert opportunity.attribution_state == "blocked_by_traffic"
    assert opportunity.component_candidates == ()


def test_source_traffic_window_uses_the_actual_local_alignment() -> None:
    effect = _effect("center", 20.0, 30.0, 0.08)
    alignment = _alignment(
        [effect], [0.0, 20.0, 30.0], [0.0, 0.0, 0.08]
    )
    alignment = replace(
        alignment,
        alignment=[
            AlignmentPoint(
                lap_pct=baseline_pct,
                aligned_test_pct=source_pct,
                confidence=1.0,
                uncertainty_pct=0.0,
                methods=["track_distance_geometry"],
            )
            for baseline_pct, source_pct in (
                (0.0, 0.0),
                (20.0, 20.5),
                (30.0, 30.5),
            )
        ],
    )
    source = [
        {
            "lap_dist_pct_100": pct,
            "speed_mps": 60.0,
            "car_distance_ahead_m": ahead,
            "car_distance_behind_m": 500.0,
        }
        for pct, ahead in ((20.5, 500.0), (30.5, 10.0))
    ]
    reference = [
        {
            "lap_dist_pct_100": pct,
            "speed_mps": 60.0,
            "car_distance_ahead_m": 500.0,
            "car_distance_behind_m": 500.0,
        }
        for pct in (20.0, 30.0)
    ]
    opportunity = service._opportunities(
        "run",
        2,
        1,
        alignment,
        (),
        _bundle(),
        SimpleNamespace(leading_component_ids=()),
        False,
        source_rows=source,
        reference_rows=reference,
    )[0]
    assert opportunity.source_traffic_exposure_fraction == 0.5
    assert opportunity.attribution_state == "blocked_by_traffic"


def test_missing_driver_demand_cannot_be_treated_as_matched() -> None:
    state = PerformancePhaseState(
        phase="center",
        start_pct=20,
        end_pct=30,
        elapsed_delta_s=0.08,
        speed_delta_mph=-2.0,
        yaw_rate_delta=1.0,
        evidence_state="measured",
    )
    separation = service._separation("run", state, traffic=False)
    assert separation.result is DriverVehicleResult.UNRESOLVED
    assert separation.driver_demand_changed is None
    assert any("co-observed" in blocker for blocker in separation.blockers)


def test_context_blocked_opportunity_cannot_publish_component_candidates() -> None:
    with pytest.raises(ValidationError, match="context-blocked opportunities"):
        service.LapTimeOpportunity(
            opportunity_id="blocked-opportunity",
            start_pct=20.0,
            end_pct=30.0,
            track_region="Turn 1",
            phase="center",
            local_delta_s=0.08,
            cumulative_delta_at_entry_s=0.0,
            cumulative_delta_at_exit_s=0.08,
            origin_kind="local_generation",
            repeatability="blocked",
            noise_basis="context unavailable",
            source_laps=(2, 1),
            source_channels=("speed_mph",),
            driver_execution_state="unresolved",
            vehicle_response_state="unresolved",
            context_state="nearby_context_unavailable",
            attribution_state="blocked_by_context",
            mechanism_candidates=("center_rotation",),
            component_candidates=("springs",),
            contradictions=("Nearby-car context is unavailable.",),
        )


def test_sparse_driver_demand_cannot_be_interpolated_into_matched_inputs() -> None:
    effect = _effect("center", 0.0, 100.0, 0.08)
    alignment = _alignment([effect], [0.0, 50.0, 100.0], [0.0, 0.04, 0.08])

    def rows(yaw_rate: float) -> list[dict[str, float]]:
        result: list[dict[str, float]] = []
        for index in range(101):
            row = {
                "lap_dist_pct_100": float(index),
                "speed_mph": 150.0,
                "yaw_rate": yaw_rate,
                "long_accel": 0.0,
                "lat": 33.0 + index * 0.000001,
                "lon": -84.0,
            }
            if index in {0, 100}:
                row.update(throttle_pct=100.0, brake_pct=0.0, steering_deg=5.0)
            result.append(row)
        return result

    reference_rows = rows(0.0)
    source_rows = rows(1.0)
    reference, source = service._aligned_channels(
        reference_rows, source_rows, alignment
    )
    state = service._phase_state(
        "center",
        [effect],
        alignment,
        reference,
        source,
        reference_rows,
        source_rows,
    )
    assert state is not None
    assert state.throttle_delta_pct == 0.0
    assert state.driver_demand_source_coverage == pytest.approx(2 / 101)
    separation = service._separation("run", state, traffic=False)
    assert separation.result is DriverVehicleResult.UNRESOLVED
    assert separation.driver_demand_changed is None


def test_equal_length_offset_lines_are_detected_at_matched_position() -> None:
    reference = {
        "lat": [33.0, 33.0001],
        "lon": [-84.0, -84.0],
    }
    source = {
        "lat": [33.0, 33.0001],
        "lon": [-83.99998, -83.99998],
    }
    separation = service._line_separation_m(reference, source, [0, 1])
    assert separation is not None and separation > 1.0


def test_vertical_gravity_baseline_is_not_disturbance_and_shifts_are_not_limiters() -> (
    None
):
    rows = [
        {
            "vert_accel_g": value,
            "gear": gear,
            "rpm": rpm,
            "lap_dist_pct_100": float(index * 10),
        }
        for index, (value, gear, rpm) in enumerate(
            ((0.99, 3, 5000), (1.01, 4, 4100), (1.00, 4, 4500))
        )
    ]
    demand = service._track_demand(rows, None, (), eligible_lap_count=1)
    assert demand.disturbance_exposure_fraction == 0.0
    assert demand.shift_zones
    assert demand.limiter_zones == demand.shift_limiter_zones == ()
    assert demand.tire_state_development == "short_run"
    long_overview = service._track_demand(rows, None, (), eligible_lap_count=10)
    assert long_overview.tire_state_development == "short_run"
    assert any("one inspected lap" in item for item in long_overview.blockers)


def test_persisted_atlanta_track_demand_does_not_call_banked_load_disturbance() -> (
    None
):
    if not default_db_path().exists():
        pytest.skip("persisted Atlanta fixture database is unavailable")
    run_id = "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb"
    rows = read_telemetry_rows(run_id, lap=24, columns=list(service._COLUMNS))
    if len(rows) < 1_000:
        pytest.skip("persisted Atlanta lap 24 telemetry fixture is unavailable")
    demand = service._track_demand(rows, None, (), eligible_lap_count=10)
    assert demand.disturbance_exposure_fraction is not None
    assert demand.disturbance_exposure_fraction < 0.25
    assert demand.traffic_exposure_fraction is not None
    assert demand.traffic_exposure_fraction > 0.90
    assert demand.limiter_zones == demand.shift_limiter_zones == ()
    assert any("Limiter zones are unavailable" in item for item in demand.blockers)


def test_repeatability_requires_exact_phase_and_physical_scope() -> None:
    effect = _effect("center", 20.0, 30.0, 0.08)
    wrong_phase = SimpleNamespace(
        phase="entry",
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        signature_id="wrong-phase",
        empirical_noise_s=0.01,
    )
    wrong_scope = SimpleNamespace(
        phase="center",
        lap_pct_start=19.0,
        lap_pct_end=30.0,
        signature_id="wrong-scope",
        empirical_noise_s=0.01,
    )
    opportunity = service._opportunities(
        "run",
        2,
        1,
        _alignment([effect], [0.0, 20.0, 30.0], [0.0, 0.0, 0.08]),
        (),
        _bundle((wrong_phase, wrong_scope)),
        None,
        False,
    )[0]
    assert opportunity.repeatability == "observed_once"


def test_carry_stops_at_first_recovery_and_does_not_reconnect_later_loss() -> None:
    effect = _effect("exit", 0.0, 20.0, 0.08)
    alignment = _alignment(
        [effect],
        [0.0, 20.0, 40.0, 60.0, 100.0],
        [0.0, 0.08, 0.09, 0.0, 0.10],
    )
    assert (
        service._contiguous_persistence_distance(
            alignment, end_index=1, end_pct=20.0, threshold=0.02
        )
        == 20.0
    )


def test_carry_recovery_is_relative_to_this_opportunity_not_prior_deficit() -> None:
    effect = _effect("exit", 20.0, 40.0, 0.08)
    alignment = _alignment(
        [effect],
        [0.0, 20.0, 40.0, 60.0, 80.0, 100.0],
        [0.20, 0.20, 0.28, 0.20, 0.20, 0.20],
    )
    opportunity = service._opportunities(
        "run", 2, 1, alignment, (), _bundle(), None, False
    )[0]
    assert opportunity.origin_kind is TimeOriginKind.AMPLIFIED
    assert opportunity.persistence_distance_pct == pytest.approx(0.0)


def test_following_straight_must_be_adjacent_and_wraps_start_finish() -> None:
    exit_effect = _effect("full_throttle_exit", 90.0, 100.0, -0.08)
    wrap = _effect("following_straight_carry", 0.0, 0.4, -0.06)
    later = _effect("straight", 20.0, 30.0, -0.05)
    assert service._adjacent_following_effect(exit_effect, [later, wrap, exit_effect]) is wrap
    non_adjacent_exit = replace(exit_effect, start_pct=40.0, end_pct=50.0)
    assert (
        service._adjacent_following_effect(non_adjacent_exit, [non_adjacent_exit, later])
        is None
    )
    opportunities = service._opportunities(
        "run",
        2,
        1,
        _alignment(
            [wrap, exit_effect],
            [0.0, 0.4, 99.6, 100.0],
            [-0.06, -0.06, -0.08, -0.08],
        ),
        (),
        _bundle(),
        None,
        False,
    )
    wrapped_exit = next(
        item for item in opportunities if item.phase == "full_throttle_exit"
    )
    assert wrapped_exit.following_phase_effect_s == pytest.approx(-0.06)
    assert wrapped_exit.persistence_distance_pct == pytest.approx(0.4)


def test_intervening_phase_prevents_following_straight_join() -> None:
    exit_effect = _effect("full_throttle_exit", 40.0, 50.0, -0.08)
    transition = _effect("transition", 50.0, 50.2, 0.01)
    straight = _effect("following_straight_carry", 50.2, 60.0, -0.06)
    assert (
        service._adjacent_following_effect(
            exit_effect, [exit_effect, transition, straight]
        )
        is None
    )


def test_repeatability_binds_run_setup_and_elapsed_time_direction() -> None:
    effect = _effect("center", 20.0, 30.0, -0.08)
    foreign_loss = SimpleNamespace(
        phase="center",
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        signature_id="foreign-loss",
        empirical_noise_s=0.01,
        median_opportunity_s=0.08,
        run_id="other-run",
        setup_id="other-setup",
    )
    same_scope_opposite_direction = SimpleNamespace(
        **{
            **vars(foreign_loss),
            "signature_id": "same-scope-loss",
            "run_id": "run",
            "setup_id": "setup",
        }
    )
    opportunity = service._opportunities(
        "run",
        2,
        1,
        _alignment([effect], [0.0, 20.0, 30.0], [0.0, 0.0, -0.08]),
        (),
        _bundle((foreign_loss, same_scope_opposite_direction)),
        None,
        False,
        current_setup_id="setup",
    )[0]
    assert opportunity.repeatability == "observed_once"


def test_manifest_compatibility_mirrors_canonical_full_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {key: f"same-{key}" for key in service._COMPATIBILITY_FIELDS}
    base["track_configuration_name"] = "oval"
    base["car_configuration_id"] = "package"
    identities = {"a": base, "b": {**base, "session_type": "Race"}}
    monkeypatch.setattr(
        service,
        "read_telemetry_manifest",
        lambda run_id: {"compatibility_identity": identities[run_id]},
    )
    compatible, reasons = service._compatibility_assessment("a", "b")
    assert compatible is False
    assert "mismatched session type" in reasons


def test_manifest_compatibility_read_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "read_telemetry_manifest",
        lambda _run_id: (_ for _ in ()).throw(OSError("manifest unavailable")),
    )
    compatible, reasons = service._compatibility_assessment("a", "b")
    assert compatible is False
    assert "manifest compatibility identity is unavailable" in reasons[0]


def _story(**updates: object) -> SpeedStory:
    values: dict[str, object] = {
        "what_costs_time": "Observed 0.100 s slower through this region.",
        "where_it_starts": "Observed at 20.0%.",
        "what_carries": "No carry established.",
        "driver": "Driver attribution blocked.",
        "car": "Car attribution blocked.",
        "systems": "Component attribution withheld.",
        "history": "No exact history.",
        "strongest_contradiction": "Traffic exposure covered the comparison window.",
        "next": "Acquire a clean pass.",
        "observed_difference_s": 0.1,
        "observed_direction": "loss",
        "attribution_state": "blocked_by_traffic",
        "attribution": "Attribution blocked by traffic context.",
    }
    values.update(updates)
    return SpeedStory(**values)


def _overview(run_id: str, lap_times: tuple[float, ...]) -> RunOverview:
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            car_path="car/nextgen",
            track_id_or_path="track/atlanta",
            session_type="Practice",
        ),
        laps=[
            LapSummary(
                lap_id=f"{run_id}-{index}",
                run_id=run_id,
                lap_number=index,
                is_complete=True,
                is_useful=True,
                lap_time=lap_time,
                pct_min=0.0,
                pct_max=100.0,
                pct_span=100.0,
                sample_count=3,
            )
            for index, lap_time in enumerate(lap_times, start=1)
        ],
        setup_snapshot=SetupSnapshot(setup_id=f"setup-{run_id}", run_id=run_id),
    )


def _public_bundle() -> SimpleNamespace:
    return SimpleNamespace(
        report=SimpleNamespace(
            reasoning_snapshot={"snapshot": "p19"},
            opportunity_signature=None,
            briefing=SimpleNamespace(
                action=SimpleNamespace(
                    instruction="Acquire a clean comparable pass.", title="Measure again"
                )
            ),
        )
    )


def _public_rows(lap: int, *, traffic: bool, speed: float) -> list[dict[str, object]]:
    speed_mps = speed / 2.2369362920544
    return [
        {
            "lap": lap,
            "lap_number": lap,
            "lap_dist_pct_100": pct,
            "lap_dist_ft": distance_ft,
            "session_time": distance_ft / 3.280839895 / speed_mps,
            "speed_mph": speed,
            "speed_mps": speed_mps,
            "car_distance_ahead_m": 10.0 if traffic else 500.0,
            "car_distance_behind_m": 10.0 if traffic else 500.0,
            "lat": 33.0 + pct * 0.000001,
            "lon": -84.0,
            # Corner response is co-observed, but throttle/brake/steering are
            # deliberately absent to prove that demand matching fails closed.
            "yaw_rate": 0.1,
            "lat_accel": 2.5,
            "long_accel": 0.0,
            "vert_accel_g": 1.0,
            "gear": 4,
            "rpm": 5000.0,
        }
        for index in range(101)
        for pct in (float(index),)
        for distance_ft in (pct * 100.0,)
    ]


def _build_public_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    effect_s: float,
    traffic: bool,
):
    run_id = f"run-{'traffic' if traffic else 'clean'}-{'loss' if effect_s > 0 else 'gain'}"
    overview = _overview(run_id, (50.0, 50.2))
    rows_by_lap = {
        1: _public_rows(1, traffic=False, speed=150.0),
        2: _public_rows(2, traffic=traffic, speed=149.0 if effect_s > 0 else 151.0),
    }
    monkeypatch.setattr(
        service,
        "read_telemetry_rows",
        lambda _run_id, *, lap, columns: rows_by_lap[lap],
    )
    repository = SimpleNamespace(
        db_path=tmp_path / f"{run_id}.sqlite3",
        get_overview=lambda candidate: overview if candidate == run_id else None,
        list_segments=lambda *_args: [],
    )
    service._PROJECTION_CACHE.clear()
    return service.build_performance_intelligence(
        run_id,
        session_id="session",
        scope_run_ids=(run_id,),
        objective=EngineeringObjective.QUALIFYING_PEAK,
        bundle=_public_bundle(),
        p20=SimpleNamespace(state_revision="a" * 64),
        p26=None,
        overview=overview,
        repository=repository,
    )


def _build_public_projection_with_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    run_id: str,
    reader: object,
):
    overview = _overview(run_id, (50.0, 50.2))
    monkeypatch.setattr(service, "read_telemetry_rows", reader)
    repository = SimpleNamespace(
        db_path=tmp_path / f"{run_id}.sqlite3",
        get_overview=lambda candidate: overview if candidate == run_id else None,
        list_segments=lambda *_args: [],
    )
    service._PROJECTION_CACHE.clear()
    return service.build_performance_intelligence(
        run_id,
        session_id="session",
        scope_run_ids=(run_id,),
        objective=EngineeringObjective.QUALIFYING_PEAK,
        bundle=_public_bundle(),
        p20=SimpleNamespace(state_revision="a" * 64),
        p26=None,
        overview=overview,
        repository=repository,
    )


def test_public_builder_keeps_traffic_difference_but_blocks_attribution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projection = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=True
    )
    story = projection.speed_story
    assert story.observed_difference_s is not None
    assert story.observed_difference_s > 0
    assert story.observed_direction == "loss"
    assert story.attribution_state == "blocked_by_traffic"
    assert "Observed" in story.what_costs_time and "slower" in story.what_costs_time
    assert "costs" not in story.what_costs_time
    assert "blocked" in story.driver.casefold()
    assert "blocked" in story.car.casefold()
    assert "withheld" in story.systems.casefold()
    assert "traffic" in story.strongest_contradiction.casefold()
    leading = projection.opportunity_map.opportunities[0]
    assert leading.component_candidates == ()
    assert projection.component_context_state == "unavailable"
    assert projection.component_influences == projection.response_records == ()
    assert len(projection.p26_knowledge_graph_sha256) == 64


def test_public_builder_publishes_negative_elapsed_time_as_gain_and_unresolved_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projection = _build_public_projection(
        monkeypatch, tmp_path, effect_s=-0.10, traffic=False
    )
    story = projection.speed_story
    assert story.observed_difference_s is not None
    assert story.observed_difference_s < 0
    assert story.observed_direction == "gain"
    assert "gains" in story.what_costs_time
    assert "costs" not in story.what_costs_time
    assert "unresolved" in story.driver.casefold()
    separations = projection.corner_chains[0].driver_vehicle_separation
    assert separations[0].result is DriverVehicleResult.UNRESOLVED
    assert separations[0].driver_demand_changed is None


def test_public_builder_rejects_mismatched_prior_manifest_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    current = _overview("current", (50.0,))
    prior = _overview("prior", (49.9,))
    base = {key: f"same-{key}" for key in service._COMPATIBILITY_FIELDS}
    base.update(
        {"car_configuration_id": "package", "track_configuration_name": "oval"}
    )
    identities = {"prior": base, "current": {**base, "car_version": "changed"}}
    monkeypatch.setattr(
        service,
        "read_telemetry_manifest",
        lambda run_id: {"compatibility_identity": identities[run_id]},
    )
    monkeypatch.setattr(
        service,
        "read_telemetry_rows",
        lambda _run_id, *, lap, columns: _public_rows(lap, traffic=False, speed=150),
    )
    repository = SimpleNamespace(
        db_path=tmp_path / "compat.sqlite3",
        get_overview=lambda run_id: {"current": current, "prior": prior}.get(run_id),
        list_segments=lambda *_args: [],
    )
    service._PROJECTION_CACHE.clear()
    projection = service.build_performance_intelligence(
        "current",
        session_id="session",
        scope_run_ids=("prior", "current"),
        objective=EngineeringObjective.QUALIFYING_PEAK,
        bundle=_public_bundle(),
        p20=SimpleNamespace(state_revision="a" * 64),
        p26=None,
        overview=current,
        repository=repository,
    )
    assert projection.basis.comparison_compatibility == "unavailable"
    assert projection.opportunity_map.reference_run_id is None
    assert any("mismatched car version" in item for item in projection.blockers)
    assert projection.speed_story.observed_direction == "unavailable"


def test_public_builder_degrades_ordinary_telemetry_read_failure_to_debt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    projection = _build_public_projection_with_reader(
        monkeypatch,
        tmp_path,
        run_id="read-unavailable",
        reader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("cache file unavailable")
        ),
    )
    assert projection.speed_story.observed_direction == "unavailable"
    assert projection.opportunity_map.opportunities == ()
    assert any("cache file unavailable" in item for item in projection.blockers)


def test_malformed_lap_identity_becomes_typed_read_debt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "read_telemetry_rows",
        lambda *_args, **_kwargs: [{"lap": None}, {"lap": None}],
    )
    rows, blocker = service._rows("run", 2)
    assert rows == []
    assert blocker is not None and "TypeError" in blocker


def test_public_builder_preserves_hard_telemetry_identity_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(TelemetryArtifactIdentityError, match="owner mismatch"):
        _build_public_projection_with_reader(
            monkeypatch,
            tmp_path,
            run_id="identity-breach",
            reader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                TelemetryArtifactIdentityError("owner mismatch")
            ),
        )


def test_public_builder_degrades_alignment_domain_failure_to_debt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        service,
        "analyze_time_alignment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("malformed timing domain")
        ),
    )
    projection = _build_public_projection_with_reader(
        monkeypatch,
        tmp_path,
        run_id="alignment-domain-error",
        reader=lambda _run_id, *, lap, columns: _public_rows(
            lap, traffic=False, speed=150.0
        ),
    )
    assert projection.speed_story.observed_direction == "unavailable"
    assert any("malformed timing domain" in item for item in projection.blockers)


def test_speed_story_typed_traffic_gate_blocks_cost_and_requires_traffic_first() -> None:
    assert _story().attribution_state == "blocked_by_traffic"
    assert _story(
        attribution_state="candidate_only",
        attribution="Attribution remains candidate-only.",
        systems="Dampers remain mechanically relevant; none is established as cause.",
        strongest_contradiction="Measured time does not establish component cause.",
    )
    with pytest.raises(ValidationError, match="attributable costs"):
        _story(what_costs_time="Turn 1 costs 0.100 s.")
    with pytest.raises(ValidationError, match="strongest contradiction"):
        _story(strongest_contradiction="Shock activity differed.")


@pytest.mark.parametrize(
    "claim",
    (
        "Shocks caused the loss.",
        "The loss was due to shocks.",
        "The loss happened because of shocks.",
        "This proves shocks created the loss.",
        "The shocks produced the loss.",
        "Shock response generated this deficit.",
        "Damper activity resulted in the loss.",
    ),
)
def test_speed_story_rejects_affirmative_causal_variants(claim: str) -> None:
    with pytest.raises(ValidationError, match="causation"):
        _story(systems=claim)


def test_traffic_blocked_opportunity_rejects_component_candidates() -> None:
    with pytest.raises(ValidationError, match="component candidates"):
        LapTimeOpportunity(
            opportunity_id="opportunity",
            start_pct=20.0,
            end_pct=30.0,
            track_region="Turn 1",
            phase="center",
            local_delta_s=0.08,
            cumulative_delta_at_entry_s=0.0,
            cumulative_delta_at_exit_s=0.08,
            origin_kind=TimeOriginKind.LOCAL_GENERATION,
            repeatability="observed_once",
            noise_basis="measured pair",
            driver_execution_state="blocked",
            vehicle_response_state="blocked",
            context_state="traffic_contaminated",
            attribution_state="blocked_by_traffic",
            component_candidates=("dampers",),
            contradictions=("Traffic exposure blocks attribution.",),
        )
