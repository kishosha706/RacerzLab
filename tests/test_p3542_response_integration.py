from __future__ import annotations

from racelab_engine.models.performance_intelligence import LapTimeOpportunity
from racelab_engine.models.vehicle_dynamics_knowledge import (
    PerformanceMechanismCandidate,
    build_vehicle_response_observation,
    build_phase_response_metric,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.services.surface_disturbance_response_service import (
    build_surface_disturbance_settling_report,
)
from racelab_engine.services.vehicle_dynamics_service import (
    _dynamic_operational_evidence,
    _mechanism_separation_rows,
    _stint_operational_evidence,
    _surface_operational_evidence,
)
from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
    compile_next_gen_oval_knowledge_graph,
)
from test_dynamic_response import _analyze as analyze_dynamic
from test_dynamic_response import _rows as dynamic_rows
from test_stint_response_migration import _laps as stint_laps
from test_stint_response_migration import _report as analyze_stint
from test_stint_response_migration import _rows as stint_rows
from test_surface_disturbance_response import _input as disturbance_input


def _opportunity(*, phase: str = "transition") -> LapTimeOpportunity:
    return LapTimeOpportunity(
        opportunity_id="p32-opportunity-response-integration",
        start_pct=0.0,
        end_pct=100.0,
        track_region="turn 1",
        phase=phase,
        local_delta_s=0.1,
        cumulative_delta_at_entry_s=0.0,
        cumulative_delta_at_exit_s=0.1,
        origin_kind="local_generation",
        repeatability="repeatable",
        noise_basis="same-run empirical noise",
        source_laps=(1, 2),
        source_channels=("session_tick", "lap_dist_pct_100"),
        driver_execution_state="matched",
        vehicle_response_state="changed",
        context_state="qualified_pair",
        mechanism_candidates=("braking_realization",),
        contradictions=("No component cause is established.",),
    )


def _response_observation():
    metric = build_phase_response_metric(
        {
            "quantity": "elapsed_time_delta_s",
            "value": 0.1,
            "units": "s",
            "semantics": "calculated_delta",
            "source_channels": ("session_time",),
        }
    )
    return build_vehicle_response_observation(
        {
            "opportunity_id": "p32-opportunity-response-integration",
            "run_id": "run-response",
            "source_lap_numbers": (1,),
            "reference_lap_numbers": (2,),
            "phase": "transition",
            "lap_pct_start": 0.0,
            "lap_pct_end": 100.0,
            "onset_pct": 0.0,
            "response_regime": "transient",
            "driver_demand_state": "matched",
            "vehicle_response_state": "changed",
            "line_state": "matched",
            "context_state": "qualified",
            "persistence": "phase_local",
            "metrics": (metric,),
            "source_artifact_ids": ("p32-opportunity-response-integration",),
            "source_channels": ("session_time",),
            "evidence_state": EvidenceState.MEASURED,
        }
    )


def test_dynamic_paths_project_native_lag_gain_settling_and_repeatability() -> None:
    report = analyze_dynamic(dynamic_rows())
    evidence = (
        *_dynamic_operational_evidence(report, _opportunity(phase="brake")),
        *_dynamic_operational_evidence(
            report, _opportunity(phase="initial_throttle")
        ),
        *_dynamic_operational_evidence(report, _opportunity(phase="center")),
    )

    by_relation = {item.relation: item for item in evidence}
    assert set(by_relation) == {
            "brake_to_pressure",
            "brake_to_deceleration",
            "brake_to_yaw",
            "brake_release_to_yaw",
            "throttle_to_acceleration",
            "throttle_to_yaw",
            "steering_wheel_to_yaw",
    }
    pressure = by_relation["brake_to_pressure"]
    assert pressure.repetition_count == 2
    assert {item.corner for item in pressure.metrics if item.corner} == {
        "lf",
        "rf",
        "lr",
        "rr",
    }
    assert {item.label for item in by_relation["brake_release_to_yaw"].metrics} >= {
        "response lag",
        "peak gain",
        "settling",
        "corrections",
        "repeatability strength",
    }
    assert all(item.authority == "observation_only" for item in evidence)
    assert all(item.setup_authorized is False for item in evidence)


def test_incomplete_brake_pressure_path_cannot_become_four_corner_evidence() -> None:
    evidence = _dynamic_operational_evidence(
        analyze_dynamic(dynamic_rows(omit="lf_brake_line_pressure_bar")),
        _opportunity(phase="brake"),
    )

    assert "brake_to_pressure" not in {item.relation for item in evidence}
    center = _dynamic_operational_evidence(
        analyze_dynamic(dynamic_rows()), _opportunity(phase="center")
    )
    assert {item.relation for item in center} == {"steering_wheel_to_yaw"}


def test_surface_response_requires_repeated_exact_physical_event() -> None:
    ready = build_surface_disturbance_settling_report(
        (disturbance_input(30), disturbance_input(31))
    )
    unavailable = build_surface_disturbance_settling_report((disturbance_input(30),))

    projected = _surface_operational_evidence(ready, _opportunity())
    assert len(projected) == 1
    assert projected[0].relation == "disturbance_to_chassis"
    assert projected[0].repetition_count == 2
    assert {item.corner for item in projected[0].metrics} == {"lf", "rf", "lr", "rr"}
    assert _surface_operational_evidence(unavailable, _opportunity()) == ()


def test_stint_migration_requires_ten_clean_noise_cleared_laps() -> None:
    ready = analyze_stint(stint_rows(10), stint_laps(10))
    short = analyze_stint(stint_rows(9), stint_laps(9))
    opportunity = LapTimeOpportunity(
        **{
            **_opportunity(phase="initial_throttle").model_dump(mode="python"),
            "start_pct": 20.0,
            "end_pct": 30.0,
        }
    )

    projected = _stint_operational_evidence(ready, opportunity)
    assert len(projected) == 1
    assert projected[0].relation == "stint_migration"
    assert projected[0].repetition_count == 10
    assert {item.lap_number for item in projected[0].metrics} == set(range(1, 11))
    assert _stint_operational_evidence(short, opportunity) == ()
    assert _stint_operational_evidence(
        ready, opportunity, expected_setup_id="foreign-setup"
    ) == ()


def test_mechanism_rows_reference_response_evidence_without_promoting_support() -> None:
    report = build_surface_disturbance_settling_report(
        (disturbance_input(30), disturbance_input(31))
    )
    evidence = _surface_operational_evidence(report, _opportunity())
    mechanism = next(
        item
        for item in compile_next_gen_oval_knowledge_graph().mechanisms
        if item.definition_id == "mechanism:disturbance_compliance_issue"
    )
    candidate = PerformanceMechanismCandidate(
        mechanism_id=mechanism.definition_id,
        p32_performance_mechanism_ids=("platform_roll_migration",),
        support_artifact_ids=("p35.focus.support:test",),
        contradiction_artifact_ids=("p35.focus.uncertainty:test",),
        discriminator_contract_ids=(mechanism.support_contract_ids[0],),
        component_family_ids=mechanism.p26_component_family_ids,
        relevance="candidate",
    )

    row = _mechanism_separation_rows(
        (mechanism,),
        (candidate,),
        (_response_observation(),),
        evidence,
    )[0]

    assert row.response_evidence_ids == (evidence[0].evidence_id,)
    assert row.support_artifact_ids == candidate.support_artifact_ids
    assert evidence[0].evidence_id not in row.support_artifact_ids
    assert row.authority == "candidate_only"
    assert row.setup_authorized is False
