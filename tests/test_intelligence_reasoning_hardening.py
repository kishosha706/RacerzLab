from __future__ import annotations

import pytest

from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import (
    CapabilityAssessment,
    CauseHypothesis,
    ControlledCauseOutcome,
)
from racelab_engine.models.observation_intelligence import (
    ObservationCitation,
    ObservationStatus,
    OpportunitySignature,
    OpportunitySignatureReport,
)
from racelab_engine.models.session_intelligence import (
    HypothesisCountereffects,
    HypothesisLifecycle,
    HypothesisLifecycleEntry,
    HypothesisProtocol,
    HypothesisTargetEffect,
    SessionEvidenceCitation,
)
from racelab_engine.services.intelligence_service import (
    answer_grounded_query,
    assess_data_quality,
    build_evidence_graph,
    build_internal_intelligence_report,
    plan_best_next_measurement,
    rank_competing_causes,
    summarize_response_memory,
)
from racelab_engine.services.run_intelligence_service import _hypotheses
from tests.test_internal_intelligence_service import (
    _authorized_report,
    _context,
    _event,
    _lap,
    _memory_edge,
    _report,
    _workflow,
)


def _controlled_outcome(
    workflow_id: str,
    outcome: str,
    *,
    source_run_id: str = "run-1",
) -> ControlledCauseOutcome:
    verdict = {
        "supported": "keep",
        "contradicted": "undo",
        "inconclusive": "retest",
        "invalid": "invalid",
    }[outcome]
    stage_run_ids = (source_run_id, f"{workflow_id}-b", f"{workflow_id}-a2")
    eligible_lap_ids = tuple(
        f"{run_id}:{lap_number}"
        for run_id in stage_run_ids
        for lap_number in (4, 5, 6)
    )
    return ControlledCauseOutcome(
        workflow_id=workflow_id,
        outcome=outcome,
        verdict=verdict,
        source_run_id=source_run_id,
        stage_run_ids=stage_run_ids if outcome != "invalid" else (),
        eligible_lap_ids=eligible_lap_ids if outcome != "invalid" else (),
        metric="target_phase_time_s",
        phase="exit",
        control_key="cross_weight_percent",
        countereffects=("Entry rotation stays inside its noise threshold.",),
        blocker_reasons=(
            ("The saved protocol is invalid.",) if outcome == "invalid" else ()
        ),
        diagnostic_validity="mechanism_diagnostic",
        control_direction_result=(
            "matched" if outcome == "supported" else
            "missed" if outcome == "contradicted" else
            "inconclusive" if outcome == "inconclusive" else
            "invalid"
        ),
    )


def _controlled_report(*outcomes: ControlledCauseOutcome):
    base = _report()
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="controlled-platform",
                label="Controlled platform result",
                hypothesis="The exact platform mechanism changes exit time.",
                mechanism_key="platform_balance",
                related_control_keys=("cross_weight_percent",),
                controlled_outcomes=outcomes,
            )
        ],
        base.evidence_graph,
    )
    return build_internal_intelligence_report(
        run_id=base.run_id,
        session_id=base.session_id,
        issue="Controlled cause result",
        graph=base.evidence_graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=base.data_quality,
    )


def _lifecycle_entry(
    *,
    outcome: str,
    verdict: str,
    direction_result: str,
    source_run_id: str = "run-1",
    control_key: str = "cross_weight_percent",
) -> HypothesisLifecycleEntry:
    valid = outcome != "invalid"
    actual_direction = {
        "matched": "decrease",
        "missed": "increase",
        "inconclusive": "inconclusive",
        "unavailable": "unavailable",
    }[direction_result]
    stage_run_ids = (source_run_id, "run-b", "run-a2")
    eligible_lap_ids = tuple(
        f"{run_id}:{lap_number}"
        for run_id in stage_run_ids
        for lap_number in (4, 5, 6)
    )
    return HypothesisLifecycleEntry(
        workflow_id="workflow-1",
        hypothesis_fingerprint="a" * 64,
        lifecycle_state=outcome,
        outcome_classification=outcome,
        hypothesis="Test the exact platform response.",
        expected_mechanism="platform_balance",
        control_key=control_key,
        direction_sign=1,
        target_effect=HypothesisTargetEffect(
            metric="target_phase_time_s",
            phase="exit",
            expected_direction="decrease",
            expected_range_s=(-0.25, -0.05),
            actual_effect_s=(-0.12 if valid else None),
            actual_direction=actual_direction,
            direction_result=direction_result,
            range_result=("inside" if direction_result == "matched" else "outside")
            if valid
            else "unavailable",
        ),
        countereffects=HypothesisCountereffects(
            criteria=("Entry rotation must not worsen.",),
            passed=True if valid else None,
        ),
        protocol=HypothesisProtocol(
            source_run_id=source_run_id,
            a_run_id=stage_run_ids[0] if valid else None,
            b_run_id=stage_run_ids[1] if valid else None,
            a2_run_id=stage_run_ids[2] if valid else None,
            eligible_lap_ids=eligible_lap_ids if valid else (),
            protocol_valid=valid,
            evidence_score=90.0 if valid else 0.0,
            verdict=verdict,
            blocker_reasons=() if valid else ("The stored protocol failed validation.",),
        ),
    )


def _lifecycle(entry: HypothesisLifecycleEntry) -> HypothesisLifecycle:
    stage_run_ids = tuple(
        run_id
        for run_id in (
            entry.protocol.a_run_id,
            entry.protocol.b_run_id,
            entry.protocol.a2_run_id,
        )
        if run_id is not None
    )
    return HypothesisLifecycle(
        session_id="session-1",
        session_scope_sha256="b" * 64,
        status="limited" if entry.outcome_classification == "invalid" else "ready",
        ordered_run_ids=stage_run_ids or (entry.protocol.source_run_id,),
        entries=(entry,),
    )


def test_event_count_cannot_replace_independent_eligible_lap_units() -> None:
    events = [
        _event("same-lap-1", lap_number=4),
        _event("same-lap-2", lap_number=4),
        _event("same-lap-3", lap_number=4),
        _event("second-lap", lap_number=5),
    ]
    graph = build_evidence_graph(events=events, laps=[_lap(4), _lap(5)])

    same_lap_support = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="support",
                label="Support",
                hypothesis="Same-lap events are one evidence unit.",
                supporting_event_ids=("same-lap-1", "same-lap-2", "same-lap-3"),
            )
        ],
        graph,
    )[0]
    repeated_support = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="support",
                label="Support",
                hypothesis="Two laps are independent evidence units.",
                supporting_event_ids=("same-lap-1", "second-lap"),
            )
        ],
        graph,
    )[0]
    same_lap_against = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="against",
                label="Against",
                hypothesis="Same-lap contradictions are one evidence unit.",
                contradicting_event_ids=("same-lap-1", "same-lap-2", "same-lap-3"),
            )
        ],
        graph,
    )[0]
    repeated_against = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="against",
                label="Against",
                hypothesis="Two laps can rule out the cause.",
                contradicting_event_ids=("same-lap-1", "second-lap"),
            )
        ],
        graph,
    )[0]

    assert (same_lap_support.status, same_lap_support.supporting_evidence_unit_count) == (
        "possible",
        1,
    )
    assert (repeated_support.status, repeated_support.supporting_evidence_unit_count) == (
        "possible",
        1,
    )
    assert (same_lap_against.status, same_lap_against.contradicting_evidence_unit_count) == (
        "unresolved",
        1,
    )
    assert (repeated_against.status, repeated_against.contradicting_evidence_unit_count) == (
        "unresolved",
        1,
    )


def test_phase_boundary_jitter_cannot_split_one_physical_event_into_causal_votes() -> None:
    entry = _event("phase-entry", lap_number=4).model_copy(
        update={
            "event_subtype": "entry",
            "lap_pct_start": 42.0,
            "lap_pct_end": 45.0,
        }
    )
    center = _event("phase-center", lap_number=5).model_copy(
        update={
            "event_subtype": "center",
            "lap_pct_start": 42.1,
            "lap_pct_end": 45.1,
        }
    )
    graph = build_evidence_graph(
        events=(entry, center),
        laps=(_lap(4), _lap(5)),
    )

    ranked = rank_competing_causes(
        (
            CauseHypothesis(
                cause_id="same-physical-event",
                label="Same physical event",
                hypothesis="The phase label moved while the telemetry window stayed aligned.",
                supporting_event_ids=("phase-entry", "phase-center"),
            ),
        ),
        graph,
    )[0]

    assert ranked.status == "possible"
    assert ranked.supporting_evidence_unit_count == 1
    assert len(ranked.supporting_clusters) == 1
    assert ranked.supporting_clusters[0].lap_numbers == (4, 5)
    assert ranked.supporting_clusters[0].phase is None


def test_controlled_contradiction_is_direct_and_conflict_stays_unresolved() -> None:
    graph = build_evidence_graph(events=[], laps=[])
    contradicted = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="exact",
                label="Exact",
                hypothesis="The exact controlled candidate failed.",
                controlled_outcomes=(_controlled_outcome("undo", "contradicted"),),
                required_evidence=("More observational laps were requested.",),
                blocker_reasons=("The observational recommendation is provisional.",),
            )
        ],
        graph,
    )[0]
    conflict = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="conflict",
                label="Conflict",
                hypothesis="Exact controlled results conflict.",
                controlled_outcomes=(
                    _controlled_outcome("keep", "supported"),
                    _controlled_outcome("undo", "contradicted"),
                ),
            )
        ],
        graph,
    )[0]

    assert contradicted.status == "ruled_out"
    assert conflict.status == "unresolved"
    assert conflict.controlled_conflict is True


def test_controlled_support_outranks_no_evidence_without_hiding_contradiction() -> None:
    graph = build_evidence_graph(
        events=[_event("observational-against")],
        laps=[_lap(4)],
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="controlled",
                label="Controlled",
                hypothesis="The exact controlled result supports this cause.",
                controlled_outcomes=(_controlled_outcome("keep", "supported"),),
                contradicting_event_ids=("observational-against",),
                required_evidence=("An old observational request remains open.",),
            ),
            CauseHypothesis(
                cause_id="none",
                label="No evidence",
                hypothesis="No evidence supports this alternative.",
            ),
        ],
        graph,
    )

    assert ranked[0].cause_id == "controlled"
    assert ranked[0].status == "possible"
    assert ranked[0].controlled_outcomes[0].outcome == "supported"
    assert ranked[0].contradicting_evidence_unit_count == 1

    supported_only = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="controlled",
                label="Controlled",
                hypothesis="The completed workflow supersedes pre-test data requests.",
                controlled_outcomes=(_controlled_outcome("keep-2", "supported"),),
                required_evidence=("An old observational request remains open.",),
                blocker_reasons=("The pre-test recommendation was provisional.",),
            )
        ],
        build_evidence_graph(events=[], laps=[]),
    )[0]
    assert supported_only.status == "likely"


@pytest.mark.parametrize(
    ("outcome", "verdict", "direction_result", "expected"),
    [
        ("supported", "keep", "matched", "inconclusive"),
        ("contradicted", "undo", "missed", "inconclusive"),
        ("contradicted", "keep", "missed", "inconclusive"),
        ("inconclusive", "retest", "inconclusive", "inconclusive"),
        ("invalid", "invalid", "unavailable", "invalid"),
    ],
)
def test_lifecycle_outcomes_map_only_from_exact_protocol_contracts(
    outcome: str,
    verdict: str,
    direction_result: str,
    expected: str,
) -> None:
    workflow = _workflow()
    entry = _lifecycle_entry(
        outcome=outcome,
        verdict=verdict,
        direction_result=direction_result,
    )
    hypotheses = _hypotheses(
        workflow,
        lifecycle=_lifecycle(entry),
        workflows=(workflow,),
        current_run_id="run-1",
    )

    controlled = tuple(
        controlled_outcome
        for hypothesis in hypotheses
        for controlled_outcome in hypothesis.controlled_outcomes
    )
    assert len(controlled) == 1
    assert controlled[0].outcome == expected
    assert controlled[0].control_direction_result == (
        "invalid" if expected == "invalid" else direction_result
    )
    assert controlled[0].diagnostic_validity == "control_response_only"
    assert bool(controlled[0].blocker_reasons) is (expected == "invalid")


def test_lifecycle_never_transfers_across_source_run_or_unrelated_control() -> None:
    workflow = _workflow()
    foreign = _lifecycle_entry(
        outcome="supported",
        verdict="keep",
        direction_result="matched",
        source_run_id="other-run",
    )
    skipped = _hypotheses(
        workflow,
        lifecycle=_lifecycle(foreign),
        workflows=(workflow,),
        current_run_id="run-1",
    )
    assert skipped[0].controlled_outcomes == ()

    unrelated_control_workflow = workflow.model_copy(
        update={
            "workflow_id": "workflow-other-control",
            "packet": workflow.packet.model_copy(
                update={
                    "primary_test": workflow.packet.primary_test.model_copy(
                        update={"control_key": "rf_front_spring_n_per_mm"}
                    )
                }
            ),
        }
    )
    unrelated_control = _lifecycle_entry(
        outcome="supported",
        verdict="keep",
        direction_result="matched",
        control_key="rf_front_spring_n_per_mm",
    ).model_copy(update={"workflow_id": "workflow-other-control"})
    separated = _hypotheses(
        workflow,
        lifecycle=_lifecycle(unrelated_control),
        workflows=(workflow, unrelated_control_workflow),
        current_run_id="run-1",
    )
    assert len(separated) == 2
    assert separated[0].controlled_outcomes == ()
    assert separated[1].controlled_outcomes[0].control_key == (
        "rf_front_spring_n_per_mm"
    )


def test_duplicate_lifecycle_workflow_identity_becomes_one_invalid_blocker() -> None:
    workflow = _workflow()
    entry = _lifecycle_entry(
        outcome="supported",
        verdict="keep",
        direction_result="matched",
    )
    duplicated = _lifecycle(entry).model_copy(update={"entries": (entry, entry)})
    hypotheses = _hypotheses(
        workflow,
        lifecycle=duplicated,
        workflows=(workflow,),
        current_run_id="run-1",
    )

    controlled = next(
        controlled_outcome
        for hypothesis in hypotheses
        for controlled_outcome in hypothesis.controlled_outcomes
    )
    assert controlled.outcome == "invalid"
    assert "more than once" in controlled.blocker_reasons[0]
    assert controlled.actual_effect_s is None
    assert controlled.time_origin_phase is None
    assert controlled.time_origin_pct is None
    assert controlled.downstream_carry_effect_s is None


def test_countereffect_only_undo_supports_cause_but_blocks_exact_policy() -> None:
    workflow = _workflow()
    base = _lifecycle_entry(
        outcome="supported",
        verdict="undo",
        direction_result="matched",
    )
    entry = base.model_copy(
        update={
            "lifecycle_state": "do_not_repeat",
            "do_not_repeat": True,
            "do_not_repeat_reason": "The target improved, but a countereffect required Undo.",
            "countereffects": base.countereffects.model_copy(update={"passed": False}),
        }
    )
    lifecycle = HypothesisLifecycle(
        session_id="session-1",
        session_scope_sha256="b" * 64,
        status="ready",
        ordered_run_ids=("run-1", "run-b", "run-a2"),
        entries=(entry,),
        do_not_repeat_hypothesis_fingerprints=(entry.hypothesis_fingerprint,),
    )
    hypotheses = _hypotheses(
        workflow,
        lifecycle=lifecycle,
        workflows=(workflow,),
        current_run_id="run-1",
    )
    ranked = rank_competing_causes(hypotheses, _report().evidence_graph)

    assert hypotheses[0].controlled_outcomes[0].verdict == "undo"
    assert hypotheses[0].controlled_outcomes[0].outcome == "inconclusive"
    assert hypotheses[0].controlled_outcomes[0].control_direction_result == "matched"
    assert ranked[0].status != "ruled_out"
    assert entry.lifecycle_state == "do_not_repeat"


def test_materially_different_lifecycle_policy_cannot_rule_out_current_cause() -> None:
    current = _workflow()
    old_card = current.packet.primary_test.model_copy(
        update={
            "target_phase": "entry",
            "direction_sign": -1,
            "hypothesis": "Test the old opposite-direction entry policy.",
        }
    )
    old_workflow = current.model_copy(
        update={
            "workflow_id": "old-workflow",
            "packet": current.packet.model_copy(update={"primary_test": old_card}),
        }
    )
    base = _lifecycle_entry(
        outcome="contradicted",
        verdict="undo",
        direction_result="missed",
    )
    old_entry = base.model_copy(
        update={
            "workflow_id": "old-workflow",
            "direction_sign": -1,
            "target_effect": base.target_effect.model_copy(update={"phase": "entry"}),
        }
    )
    lifecycle = HypothesisLifecycle(
        session_id="session-1",
        session_scope_sha256="b" * 64,
        status="ready",
        ordered_run_ids=("run-1", "run-b", "run-a2"),
        entries=(old_entry,),
    )

    hypotheses = _hypotheses(
        current,
        lifecycle=lifecycle,
        workflows=(current, old_workflow),
        current_run_id="run-1",
    )
    current_cause = next(item for item in hypotheses if item.cause_id.startswith("workflow:"))
    historical_cause = next(item for item in hypotheses if item.cause_id.startswith("lifecycle:"))
    ranked = {item.cause_id: item for item in rank_competing_causes(
        hypotheses,
        _report().evidence_graph,
    )}

    assert current_cause.controlled_outcomes == ()
    assert ranked[current_cause.cause_id].status != "ruled_out"
    assert historical_cause.controlled_outcomes[0].phase == "entry"
    assert historical_cause.controlled_outcomes[0].outcome == "inconclusive"
    assert historical_cause.controlled_outcomes[0].control_direction_result == "missed"


def test_workflow_candidate_is_single_and_exactly_control_scoped() -> None:
    workflow = _workflow()
    hypotheses = _hypotheses(workflow)

    assert len(hypotheses) == 1
    assert hypotheses[0].cause_id.startswith("workflow:")
    assert hypotheses[0].related_control_keys == (
        workflow.packet.primary_test.control_key,
    )
    assert hypotheses[0].supporting_event_ids == (
        *workflow.packet.primary_test.evidence_event_ids,
    )


def test_controlled_outcome_queries_are_visible_but_navigation_only() -> None:
    supported = _controlled_report(_controlled_outcome("keep", "supported"))
    assert supported.competing_causes[0].state == "leading"

    why = answer_grounded_query("Why this call?", supported)
    evidence = answer_grounded_query("What evidence supports this?", supported)
    for result in (why, evidence):
        assert result.citations
        assert {citation.workspace for citation in result.citations} == {"dial_in"}
        assert all(not citation.valid_for_tuning for citation in result.citations)
        assert result.action_authorized is False

    contradicted = _controlled_report(
        _controlled_outcome("undo", "contradicted")
    )
    ruled_out = answer_grounded_query("What was ruled out?", contradicted)
    assert "Ruled out" in ruled_out.answer
    assert ruled_out.citations
    assert ruled_out.citations[0].workspace == "dial_in"
    assert ruled_out.citations[0].valid_for_tuning is False


def test_scoped_ruled_out_query_requires_two_contradiction_laps_inside_scope() -> None:
    laps = [_lap(4), _lap(5)]
    events = [
        _event("contradiction-lap-4", lap_number=4),
        _event("contradiction-lap-5", lap_number=5),
    ]
    graph = build_evidence_graph(events=events, laps=laps)
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="two-lap-contradiction",
                label="Two-lap contradiction",
                hypothesis="The candidate does not reproduce.",
                contradicting_event_ids=tuple(event.event_id for event in events),
            )
        ],
        graph,
    )
    quality = assess_data_quality(
        laps=laps,
        events=events,
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Contradictory evidence",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert report.competing_causes[0].state == "unresolved"

    single_lap = answer_grounded_query(
        "What was ruled out?",
        report,
        selected_lap_number=4,
    )
    partial_window = answer_grounded_query(
        "What was ruled out?",
        report,
        selected_window_start_lap=4,
        selected_window_end_lap=4,
        selected_window_representative_lap=4,
    )
    exact_two_lap_window = answer_grounded_query(
        "What was ruled out?",
        report,
        selected_window_start_lap=4,
        selected_window_end_lap=5,
        selected_window_representative_lap=4,
    )

    for partial in (single_lap, partial_window, exact_two_lap_window):
        assert "No cause has enough" in partial.answer
        assert partial.citations == ()
        assert partial.blocker_reasons
        assert "mechanism-diagnostic" in partial.blocker_reasons[0]


def test_mind_change_contracts_separate_causal_tests_from_collection_only_work() -> None:
    controlled = _authorized_report()
    controlled_criterion = controlled.mind_change_criteria[0]
    assert controlled_criterion.evidence_kind == "controlled_test"
    assert controlled_criterion.requires_aba2 is True
    assert controlled_criterion.minimum_independent_evidence_units == 9
    joined_acceptance = " ".join(controlled_criterion.acceptance_conditions)
    assert "planned target" in joined_acceptance
    assert "0.8" in joined_acceptance
    assert "three qualified within-baseline" in joined_acceptance
    assert "consistency flag is true" in joined_acceptance
    assert "at least 80" in joined_acceptance
    assert "countereffect" not in " ".join(
        controlled_criterion.falsification_conditions
    ).casefold()
    assert "does not by itself falsify" in " ".join(
        controlled_criterion.countereffects
    )
    controlled_answer = answer_grounded_query(
        "What would change your mind?",
        controlled,
    )
    assert "inconclusive or invalid -> unresolved" in controlled_answer.answer

    collection = _report()
    collection_criterion = collection.mind_change_criteria[0]
    assert collection_criterion.evidence_kind == "discriminator"
    assert collection_criterion.next_state_if_accepted == (
        collection_criterion.current_state
    )
    assert collection_criterion.next_state_if_falsified == "unresolved"
    collection_answer = answer_grounded_query(
        "What would change your mind?",
        collection,
    )
    assert "declared no causal opposite" in collection_answer.answer
    assert "cannot rule the cause out" in collection_answer.answer


def test_selected_window_and_single_lap_scopes_never_override_each_other() -> None:
    report = _report()
    incomplete_selected_window = answer_grounded_query(
        "Where is the loss?",
        report,
        selected_window_start_lap=4,
        selected_window_end_lap=5,
    )
    assert incomplete_selected_window.supported is False
    assert incomplete_selected_window.clarification_required is True
    assert "representative lap" in incomplete_selected_window.answer
    assert incomplete_selected_window.interpreted_window_start_lap is None
    assert incomplete_selected_window.interpreted_window_end_lap is None
    assert incomplete_selected_window.interpreted_window_representative_lap is None

    text_only_window = answer_grounded_query(
        "Where is the loss on laps 4-5?",
        report,
    )
    assert text_only_window.supported is False
    assert text_only_window.clarification_required is True
    assert "representative lap" in text_only_window.answer
    assert text_only_window.interpreted_window_start_lap is None
    assert text_only_window.interpreted_window_end_lap is None
    assert text_only_window.interpreted_window_representative_lap is None

    single_vs_window = answer_grounded_query(
        "Where is the loss on laps 4-5?",
        report,
        selected_lap_number=4,
    )
    assert single_vs_window.supported is False
    assert single_vs_window.clarification_required is True
    assert single_vs_window.interpreted_lap_number == 4
    assert single_vs_window.interpreted_window_start_lap is None

    mismatched_window = answer_grounded_query(
        "Where is the loss on laps 4-6?",
        report,
        selected_window_start_lap=4,
        selected_window_end_lap=5,
        selected_window_representative_lap=4,
    )
    assert mismatched_window.supported is False
    assert mismatched_window.interpreted_lap_number is None
    assert mismatched_window.interpreted_window_start_lap == 4
    assert mismatched_window.interpreted_window_end_lap == 5
    assert mismatched_window.interpreted_window_representative_lap == 4

    exact_window = answer_grounded_query(
        "Where is the loss on laps 4-5?",
        report,
        selected_window_start_lap=4,
        selected_window_end_lap=5,
        selected_window_representative_lap=4,
    )
    assert exact_window.supported is True
    assert exact_window.interpreted_window_start_lap == 4
    assert exact_window.interpreted_window_end_lap == 5
    assert exact_window.interpreted_window_representative_lap == 4
    assert all(4 <= citation.lap_number <= 5 for citation in exact_window.citations)


@pytest.mark.parametrize(
    "question",
    (
        "What should I do next on lap 4 and lap 5?",
        "What should I do next on laps 4 and 5?",
        "What should I do next on laps 4, 5?",
        "What should I do next on lap 4 versus 5?",
        "Where is the loss on laps 4-5 versus laps 6-7?",
        "Where is the loss on laps 4-5 versus 6-7?",
        "What should I do next on lap 4 and laps 5–6?",
        "What should I do next on lap 4 and 5–6?",
        "Where is the loss on laps 4—5 and laps 6-7?",
    ),
)
def test_multiple_explicit_lap_scopes_fail_closed_without_partial_scope(
    question: str,
) -> None:
    result = answer_grounded_query(question, _authorized_report())

    assert result.supported is False
    assert result.clarification_required is True
    assert "more than one lap scope" in result.answer
    assert result.action_authorized is False
    assert result.action_source_event_ids == ()
    assert result.citations == ()
    assert result.suggested_navigation == ()
    assert result.interpreted_lap_number is None
    assert result.interpreted_window_start_lap is None
    assert result.interpreted_window_end_lap is None
    assert result.interpreted_window_representative_lap is None


def test_one_exact_explicit_lap_or_unicode_window_scope_is_preserved() -> None:
    report = _authorized_report()
    exact_lap = answer_grounded_query(
        "What should I do next on lap 4?",
        report,
    )
    exact_window = answer_grounded_query(
        "Where is the loss on laps 4–5?",
        report,
        selected_window_start_lap=4,
        selected_window_end_lap=5,
        selected_window_representative_lap=4,
    )

    assert exact_lap.supported is True
    assert exact_lap.action_authorized is True
    assert exact_lap.interpreted_lap_number == 4
    assert exact_window.supported is True
    assert exact_window.interpreted_window_start_lap == 4
    assert exact_window.interpreted_window_end_lap == 5
    assert exact_window.interpreted_window_representative_lap == 4


def test_selected_lap_scope_withholds_out_of_scope_aggregate_details() -> None:
    observation_citations = tuple(
        ObservationCitation(
            run_id="run-1",
            lap_number=lap_number,
            setup_id="setup-a",
            lap_pct_start=10.0,
            lap_pct_end=20.0,
            lap_pct_peak=15.0,
            phase="exit",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=("speed_mph", "session_time"),
            telemetry_sample_count=20,
        )
        for lap_number in (5, 6)
    )
    signature = OpportunitySignature(
        signature_id="outside-selected-lap",
        run_id="run-1",
        setup_id="setup-a",
        phase="exit",
        lap_pct_start=10.0,
        lap_pct_end=20.0,
        lap_pct_peak=15.0,
        eligible_lap_count=3,
        repetition_count=2,
        telemetry_sample_count=40,
        aligned_bin_count=4,
        median_opportunity_s=0.2,
        empirical_noise_s=0.05,
        source_channels=("speed_mph", "session_time"),
        citations=observation_citations,
    )
    opportunity = OpportunitySignatureReport(
        status=ObservationStatus.READY,
        run_id="run-1",
        setup_id="setup-a",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=("speed_mph", "session_time"),
        eligible_lap_numbers=(4, 5, 6),
        eligible_lap_count=3,
        telemetry_sample_count=60,
        signatures=(signature,),
    )
    report = _report().model_copy(update={"opportunity_signature": opportunity})

    for scoped in (
        answer_grounded_query(
            "How repeatable is the strongest opportunity?",
            report,
            selected_lap_number=4,
        ),
        answer_grounded_query(
            "How repeatable is the strongest opportunity?",
            report,
            selected_window_start_lap=4,
            selected_window_end_lap=4,
            selected_window_representative_lap=4,
        ),
    ):
        assert scoped.citations == ()
        assert "0.200" not in scoped.answer
        assert "2 of 3" not in scoped.answer
        assert scoped.blocker_reasons


def test_selected_lap_scope_never_partially_proves_cross_run_lifecycle_outcome() -> None:
    entry = _lifecycle_entry(
        outcome="contradicted",
        verdict="undo",
        direction_result="missed",
    ).model_copy(
        update={
            "lifecycle_state": "do_not_repeat",
            "do_not_repeat": True,
            "do_not_repeat_reason": "The exact controlled test produced Undo.",
            "citations": (
                SessionEvidenceCitation(
                    kind="lap",
                    reference_id="run-1:4",
                    run_id="run-1",
                    lap_number=4,
                ),
                SessionEvidenceCitation(
                    kind="lap",
                    reference_id="run-b:4",
                    run_id="run-b",
                    lap_number=4,
                ),
                SessionEvidenceCitation(
                    kind="lap",
                    reference_id="run-a2:4",
                    run_id="run-a2",
                    lap_number=4,
                ),
            ),
        }
    )
    lifecycle = HypothesisLifecycle(
        session_id="session-1",
        session_scope_sha256="b" * 64,
        status="ready",
        ordered_run_ids=("run-1", "run-b", "run-a2"),
        entries=(entry,),
        do_not_repeat_hypothesis_fingerprints=(entry.hypothesis_fingerprint,),
    )
    report = _report().model_copy(update={"hypothesis_lifecycle": lifecycle})

    for scoped in (
        answer_grounded_query(
            "Which hypotheses should I avoid repeating?",
            report,
            selected_lap_number=4,
        ),
        answer_grounded_query(
            "Which hypotheses should I avoid repeating?",
            report,
            selected_window_start_lap=4,
            selected_window_end_lap=4,
            selected_window_representative_lap=4,
        ),
    ):
        assert scoped.citations == ()
        assert "valid controlled test produced" not in scoped.answer
        assert scoped.blocker_reasons


def test_history_control_filter_and_phase_filter_fail_closed() -> None:
    context = _context()
    memory = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [_memory_edge("history-control", delta=0.1, effect=-0.05)],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    report = _report().model_copy(
        update={
            "response_context_key": context.key,
            "context_matches": (memory,),
        }
    )

    exact = answer_grounded_query(
        "What worked here before for Cross Weight?",
        report,
    )
    wrong_control = answer_grounded_query(
        "What worked here before for RF Spring?",
        report,
    )
    wrong_phase = answer_grounded_query("Where is the loss in entry?", report)
    selected_history = answer_grounded_query(
        "What worked here before in the exit?",
        report,
        selected_lap_number=4,
    )
    selected_window_history = answer_grounded_query(
        "What worked here before?",
        report,
        selected_window_start_lap=4,
        selected_window_end_lap=4,
        selected_window_representative_lap=4,
    )

    assert "cross_weight_percent" in exact.answer
    assert "No qualified" in wrong_control.answer
    assert wrong_control.interpreted_control_key == "rf_front_spring_n_per_mm"
    assert wrong_phase.citations == ()
    for scoped_history in (selected_history, selected_window_history):
        assert scoped_history.citations == ()
        assert scoped_history.suggested_navigation == ()
        assert "qualified exact-context controlled observations exist" not in (
            scoped_history.answer
        )
        assert scoped_history.blocker_reasons
