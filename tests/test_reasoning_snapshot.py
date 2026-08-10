from __future__ import annotations

from api.intelligence_adapter import _graph as adapt_graph
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import (
    CapabilityAssessment,
    CauseHypothesis,
    ControlledCauseOutcome,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    MechanismKind,
    MechanismObservation,
    ObservationCitation,
)
from racelab_engine.services.intelligence_service import (
    assess_data_quality,
    build_evidence_graph,
    build_internal_intelligence_report,
    build_reasoning_snapshot,
    plan_best_next_measurement,
    rank_competing_causes,
)


def _lap(number: int) -> LapSummary:
    return LapSummary(
        lap_id=f"run-1:{number}",
        run_id="run-1",
        lap_number=number,
        lap_type="flying",
        is_complete=True,
        is_useful=True,
        lap_time=30.0,
        sample_count=100,
    )


def _observation() -> MechanismObservation:
    citations = tuple(
        ObservationCitation(
            run_id="run-1",
            lap_number=lap_number,
            setup_id="setup-1",
            lap_pct_start=40.0,
            lap_pct_end=50.0,
            lap_pct_peak=45.0,
            phase="exit",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=("speed_mph", "throttle_pct"),
            telemetry_sample_count=20,
        )
        for lap_number in (4, 5)
    )
    return MechanismObservation(
        observation_id="typed-exit-drive",
        producer_id="test.powertrain",
        artifact_id="typed-exit-drive",
        source_run_ids=("run-1",),
        source_setup_ids=("setup-1",),
        sample_coverage=1.0,
        mechanism=MechanismKind.POWERTRAIN_RESPONSE,
        run_id="run-1",
        setup_id="setup-1",
        lap_number=4,
        phase="exit",
        lap_pct_start=40.0,
        lap_pct_end=50.0,
        lap_pct_peak=45.0,
        summary="Exit drive remains weak at the same physical window.",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        qualified=True,
        source_channels=("speed_mph", "throttle_pct"),
        supporting_evidence=("The signal repeats on two eligible laps.",),
        telemetry_sample_count=40,
        repetition_count=2,
        citations=citations,
    )


def _control_miss() -> ControlledCauseOutcome:
    runs = ("run-1", "run-b", "run-a2")
    return ControlledCauseOutcome(
        workflow_id="workflow-1",
        outcome="inconclusive",
        verdict="undo",
        source_run_id="run-1",
        stage_run_ids=runs,
        eligible_lap_ids=tuple(
            f"{run_id}:{lap_number}" for run_id in runs for lap_number in (1, 2, 3)
        ),
        metric="exit_time_s",
        phase="exit",
        control_key="cross_weight_percent",
        countereffects=("Entry response worsened.",),
        diagnostic_validity="control_response_only",
        control_direction_result="missed",
    )


def test_control_miss_does_not_erase_persistent_mechanism_observation() -> None:
    observation = _observation()
    cause = CauseHypothesis(
        cause_id="exit-drive",
        label="Exit drive",
        hypothesis="Exit-drive response remains a candidate mechanism.",
        supporting_observation_ids=("typed-exit-drive:0", "typed-exit-drive:1"),
        controlled_outcomes=(_control_miss(),),
    )
    graph = build_evidence_graph(
        causes=(cause,),
        observations=(observation,),
        laps=(_lap(4), _lap(5)),
    )
    ranked = rank_competing_causes((cause,), graph)
    plan = plan_best_next_measurement(ranked)
    quality = assess_data_quality(
        laps=(_lap(4), _lap(5)),
        events=(),
        capability=CapabilityAssessment(status="ready"),
    ).model_copy(update={
        "scope_run_ids": ("run-1",),
        "status": "limited",
    })
    snapshot = build_reasoning_snapshot(
        run_id="run-1",
        session_id=None,
        graph=graph,
        ranked_causes=ranked,
        measurement_plan=plan,
        data_quality=quality,
    )

    assert ranked[0].status != "ruled_out"
    assessment = snapshot.controlled_outcomes[0]
    assert assessment.mechanism.state == "unchanged"
    assert assessment.control_response.result == "missed"
    assert assessment.policy.verdict == "undo"
    cause_edges = [edge for edge in snapshot.evidence_graph.edges if edge.source_node_id == "cause:exit-drive"]
    assert len(cause_edges) == 2
    assert all(edge.kind.value == "supported_by" for edge in cause_edges)


def test_report_and_adapter_consume_backend_cause_nodes_without_synthesis() -> None:
    observation = _observation()
    cause = CauseHypothesis(
        cause_id="typed-only",
        label="Typed-only cause",
        hypothesis="This cause came from a P3 observation, not a recommendation.",
        supporting_observation_ids=("typed-exit-drive:0", "typed-exit-drive:1"),
    )
    event = TelemetryEvent(
        event_id="quality-event",
        run_id="run-1",
        lap_number=4,
        event_type="EXIT_SPEED",
        event_subtype="exit",
        lap_pct_start=40.0,
        lap_pct_end=50.0,
        lap_pct_peak=45.0,
        confidence_score=0.8,
        valid_for_tuning=True,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=["speed_mph"],
    )
    laps = (_lap(4), _lap(5))
    graph = build_evidence_graph(
        causes=(cause,), observations=(observation,), events=(event,), laps=laps
    )
    ranked = rank_competing_causes((cause,), graph)
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Typed observation",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=assess_data_quality(
            laps=laps,
            events=(event,),
            capability=CapabilityAssessment(status="ready"),
        ),
    )
    adapted = adapt_graph(report, setup_authorized=False)
    assert sum(node.kind == "cause" for node in adapted.nodes) == 1
    assert {cause.cause_id for cause in report.reasoning_snapshot.causes} == {
        node.entity_id
        for node in report.reasoning_snapshot.evidence_graph.nodes
        if node.kind.value == "cause"
    }
