from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.models.crew_chief import (
    EngineeringEvidenceIndex,
    EngineeringEvidenceIndexEntry,
    EngineeringObjective,
)
from racelab_engine.models.performance_intelligence import (
    ComponentPerformanceInfluence,
    CornerPerformanceChain,
    DriverVehicleSeparation,
    LapTimeOpportunity,
    PerformanceObjectiveEnvelope,
    PerformancePhaseState,
    TrackDemandProfile,
)
from racelab_engine.services.crew_chief_service import (
    _UnavailableP26,
    _evidence_index,
    _is_optional_p26_applicability_failure,
    _select_tool_entries,
    _subgoal,
)
from test_crew_chief_contracts import _identity


class _Repository:
    @staticmethod
    def get_setup_snapshots(_run_ids):
        return {}


def _p32_fixture():
    phase = PerformancePhaseState(
        phase="center",
        start_pct=20.0,
        end_pct=30.0,
        path_delta_m=1.2,
        source_channels=("LapDistPct", "Speed", "Lat"),
        evidence_state="measured",
    )
    separation = DriverVehicleSeparation(
        separation_id="separation-center",
        phase="center",
        driver_demand_changed=False,
        vehicle_response_changed=True,
        line_changed=False,
        context_changed=False,
        time_changed=True,
        result="vehicle_response_changed_with_matched_inputs",
        support=("Complete co-observed driver-demand evidence is matched.",),
        blockers=(),
        contradictions=(),
    )
    chain = CornerPerformanceChain(
        chain_id="corner-chain-one",
        track_region="Turn 1",
        lap_numbers=(4,),
        reference_lap_numbers=(3,),
        approach_state=None,
        braking_state=None,
        entry_state=None,
        center_state=phase,
        exit_state=None,
        carry_state=None,
        local_time_effect_s=0.08,
        downstream_time_effect_s=0.03,
        driver_vehicle_separation=(separation,),
        context=("qualified lap pair",),
        contradictions=("Minimum speed alone is not the center phase.",),
    )
    opportunity = LapTimeOpportunity(
        opportunity_id="opportunity-one",
        track_region="Turn 1",
        context_state="qualified_pair",
        contradictions=("Measured time does not establish component cause.",),
        start_pct=20.0,
        end_pct=30.0,
        phase="center",
        origin_kind="local_generation",
        persistence_distance_pct=4.0,
        following_phase_effect_s=0.03,
        following_phase_start_pct=30.0,
        following_phase_end_pct=36.0,
        repeatability="repeatable",
        noise_basis="same-run signature; empirical noise 0.0100 s",
        source_laps=(4, 3),
        source_channels=("LapDistPct", "Speed"),
        driver_execution_state="matched phase demand",
        vehicle_response_state="response changed with matched demand",
        mechanism_candidates=("corner_rotation",),
        component_candidates=("springs",),
    )
    track_demand = TrackDemandProfile(
        full_throttle_fraction=0.6,
        braking_fraction=0.1,
        cornering_fraction=0.3,
        speed_min_mph=75.0,
        speed_max_mph=185.0,
        disturbance_exposure_fraction=0.04,
        traffic_exposure_fraction=0.0,
        source_channels=("Throttle", "Brake", "Speed"),
        blockers=(),
        tire_state_development="short_run",
    )
    influence = ComponentPerformanceInfluence(
        influence_id="component-link-springs",
        runtime_support_state="response_supported",
        measurable_through=("LFshockDefl", "RFshockDefl"),
        performance_mechanism_ids=("platform_response",),
        component_id="springs",
        expected_state_ids=("platform stability",),
        source_artifact_ids=("opportunity-one",),
        contradictions=("Mechanical relevance is not component cause.",),
        authority="observation_only",
    )
    envelope = PerformanceObjectiveEnvelope(
        objective_id="race_long_run",
        primary_outcomes=("repeatable lap time",),
        protected_outcomes=("tire durability",),
        countereffect_limits=("no downstream loss",),
        measurement_requirements=("phase time", "exit carry"),
        policy_note="P19 alone owns setup policy.",
    )
    return SimpleNamespace(
        basis=SimpleNamespace(source_lap_numbers=(4,), context_blockers=()),
        opportunity_map=SimpleNamespace(opportunities=(opportunity,)),
        corner_chains=(chain,),
        track_demand=track_demand,
        component_influences=(influence,),
        objective_envelope=envelope,
    )


def _bundle():
    return SimpleNamespace(
        report=SimpleNamespace(
            reasoning_snapshot=SimpleNamespace(causes=(), mechanism_episodes=()),
            data_quality=SimpleNamespace(status="ready"),
            lap_context=SimpleNamespace(contexts=()),
        )
    )


def test_all_nine_p32_tools_attach_the_typed_artifact_they_advertise() -> None:
    p32 = _p32_fixture()
    evidence = _evidence_index(
        _bundle(),
        _identity(),
        EngineeringObjective.RACE_LONG_RUN,
        SimpleNamespace(component_states=()),
        p32,
        _Repository(),
    )
    expected = {
        "inspect_lap_time_opportunity": "p32.lap_time_opportunity",
        "inspect_time_loss_origin": "p32.time_loss_origin",
        "inspect_corner_performance_chain": "p32.corner_performance_chain",
        "inspect_exit_carry": "p32.exit_carry",
        "inspect_path_efficiency": "p32.path_efficiency",
        "inspect_driver_vehicle_separation": "p32.driver_vehicle_separation",
        "inspect_track_demand": "p32.track_demand",
        "inspect_component_performance_link": "p32.component_performance_link",
        "inspect_objective_tradeoff": "p32.objective_envelope",
    }
    workspace = SimpleNamespace(
        evidence_index=evidence,
        folded_state=SimpleNamespace(driver_answers=("center",)),
    )

    for tool_id, producer_id in expected.items():
        selected = _select_tool_entries(workspace, tool_id, ())
        assert selected
        assert {item.producer_id for item in selected} == {producer_id}
        assert all(item.typed_artifact is not None for item in selected)
        assert all(
            item.typed_artifact.artifact_type == producer_id.removeprefix("p32.")
            for item in selected
        )

    by_producer = {item.producer_id: item for item in evidence.entries}
    origin = by_producer["p32.time_loss_origin"]
    assert origin.typed_artifact.opportunity.origin_kind.value == "local_generation"
    assert origin.typed_artifact.opportunity.local_delta_s is None
    carry = by_producer["p32.exit_carry"]
    assert (carry.lap_pct_start, carry.lap_pct_end) == (30.0, 36.0)
    assert carry.typed_artifact.opportunity.following_phase_effect_s == pytest.approx(
        0.03
    )
    path = by_producer["p32.path_efficiency"]
    assert path.typed_artifact.phase_state.path_delta_m == pytest.approx(1.2)
    demand = by_producer["p32.track_demand"]
    assert demand.typed_artifact.profile.disturbance_exposure_fraction == pytest.approx(
        0.04
    )
    objective = by_producer["p32.objective_envelope"]
    assert objective.typed_artifact.envelope.objective_id == "race_long_run"
    restored = EngineeringEvidenceIndex.model_validate_json(evidence.model_dump_json())
    assert restored == evidence


def test_p32_typed_artifact_cannot_be_swapped_under_foreign_metadata() -> None:
    evidence = _evidence_index(
        _bundle(),
        _identity(),
        EngineeringObjective.RACE_LONG_RUN,
        SimpleNamespace(component_states=()),
        _p32_fixture(),
        _Repository(),
    )
    origin = next(
        item for item in evidence.entries if item.producer_id == "p32.time_loss_origin"
    )
    carry = next(
        item for item in evidence.entries if item.producer_id == "p32.exit_carry"
    )
    hostile = origin.model_dump(mode="python")
    hostile["typed_artifact"] = carry.typed_artifact.model_dump(mode="python")
    with pytest.raises(ValidationError, match="producer, typed artifact"):
        EngineeringEvidenceIndexEntry.model_validate(hostile)


def test_p32_planner_can_reach_every_performance_tool_without_p19_causes() -> None:
    completed = ["inspect_data_quality", "inspect_lap_context"]
    seen: list[str] = []
    p26 = SimpleNamespace(component_states=(), leading_component_ids=())
    for _ in range(16):
        folded = SimpleNamespace(
            status="open",
            completed_tool_ids=tuple(completed),
            hypotheses=(),
            driver_answers=("center",),
            objective=EngineeringObjective.RACE_LONG_RUN,
            investigation_id="investigation-p321",
        )
        subgoal = _subgoal(_bundle(), folded, p26, _p32_fixture())
        if subgoal is None:
            break
        completed.append(subgoal.selected_tool)
        seen.append(subgoal.selected_tool)

    assert {
        "inspect_lap_time_opportunity",
        "inspect_time_loss_origin",
        "inspect_corner_performance_chain",
        "inspect_exit_carry",
        "inspect_path_efficiency",
        "inspect_driver_vehicle_separation",
        "inspect_track_demand",
        "inspect_component_performance_link",
        "inspect_objective_tradeoff",
    } <= set(seen)


def test_only_reviewed_graph_applicability_failures_are_optional() -> None:
    assert _is_optional_p26_applicability_failure(
        ValueError("Vehicle Systems graph 1 is unavailable for car path road-car.")
    )
    assert _is_optional_p26_applicability_failure(
        ValueError("Vehicle Systems graph 1 requires review for future iRacing build 9.")
    )
    assert not _is_optional_p26_applicability_failure(
        ValueError("Vehicle Systems telemetry ownership does not match run run-1.")
    )
    assert not _is_optional_p26_applicability_failure(
        ValueError("Vehicle Systems compatibility identity failed integrity verification.")
    )


def test_unavailable_p26_blocks_only_the_component_performance_artifact() -> None:
    p32 = _p32_fixture()
    p32.component_influences = ()
    reason = "P26 component attribution is unavailable for this car/build/track."
    p26 = _UnavailableP26(
        setup_id="setup-1",
        setup_snapshot_sha256="6" * 64,
        graph_version="p26.unavailable:999999999999",
        knowledge_graph_sha256="9" * 64,
        reasoning_snapshot_sha256="2" * 64,
        runtime_identity={"run_id": "run-1", "state": "unavailable"},
        unavailable_reason=reason,
    )

    evidence = _evidence_index(
        _bundle(),
        _identity(),
        EngineeringObjective.RACE_LONG_RUN,
        p26,
        p32,
        _Repository(),
    )
    component = next(
        item
        for item in evidence.entries
        if item.producer_id == "p32.component_performance_link"
    )
    assert component.evidence_state.value == "unavailable"
    assert component.blocker_reasons == (reason,)
    assert component.component_ids == ()
    assert component.typed_artifact.artifact_type == "unavailable"
    assert component.typed_artifact.claimed_artifact_type == (
        "component_performance_link"
    )
    workspace = SimpleNamespace(
        evidence_index=evidence,
        folded_state=SimpleNamespace(driver_answers=("center",)),
    )
    p26_state = _select_tool_entries(workspace, "inspect_component_state", ())
    assert {item.producer_id for item in p26_state} == {
        "p26.component_state_unavailable"
    }
    assert p26_state[0].blocker_reasons == (reason,)
    assert any(
        item.producer_id == "p32.lap_time_opportunity"
        and item.evidence_state.value != "unavailable"
        for item in evidence.entries
    )
