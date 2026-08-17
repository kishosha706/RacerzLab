from __future__ import annotations

from types import SimpleNamespace

import pytest

from racelab_engine.services import crew_chief_service
from racelab_engine.models.crew_chief import (
    CrewChiefEventPayload,
    CrewChiefSelectionReceipt,
    DriverDiagnosticQuestion,
    EngineeringObjective,
    InvestigationProgress,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.services.crew_chief_service import (
    _critique,
    _event,
    _interpret_driver_answer,
    _select_tool_entries,
    _subgoal,
    advance_until_boundary,
    fold_investigation,
)
from racelab_engine.storage.crew_chief_repository import CrewChiefRepository

from test_crew_chief_contracts import (
    _identity,
    _investigation,
    _planner_fixture,
    _seed_run,
)


def _cause(cause_id: str, artifact_id: str):
    citation = SimpleNamespace(event_id=artifact_id, citation_id=artifact_id)
    return SimpleNamespace(
        cause_id=cause_id,
        status="possible",
        supporting_evidence=(citation,),
        contradicting_evidence=(),
    )


def test_no_finding_never_marks_requested_causes_as_inspected() -> None:
    request_id = "ccir_" + "a" * 24
    receipt = CrewChiefSelectionReceipt.build(
        selection_policy_id="p353.test.v1",
        candidate_count=0,
        selected_count=0,
        omitted_count=0,
        selected_artifact_ids=(),
        selection_reasons=(),
        required_artifact_ids=(),
        required_artifacts_present=True,
    )
    invocation = _event(
        "investigation-1",
        1,
        "8" * 64,
        "tool_invoked",
        CrewChiefEventPayload(
            message="Inspection requested.",
            tool_id="inspect_p19_causes",
            inspection_request_id=request_id,
            cause_ids=("cause-1", "cause-2"),
            requested_measurement_ids=("inspect_p19_causes",),
        ),
    )
    result = _event(
        "investigation-1",
        2,
        "8" * 64,
        "tool_result_attached",
        CrewChiefEventPayload(
            message="No exact evidence found.",
            tool_id="inspect_p19_causes",
            inspection_request_id=request_id,
            tool_execution_duration_ms=1.0,
            finding_kind="no_signal",
            completed_measurement_ids=("inspect_p19_causes",),
            ambiguity_before=2,
            ambiguity_after=2,
            selection_receipt=receipt,
        ),
    )

    folded = fold_investigation(
        _investigation(),
        (invocation, result),
        (_cause("cause-1", "artifact-1"), _cause("cause-2", "artifact-2")),
    )

    assert {item.progress for item in folded.hypotheses} == {
        InvestigationProgress.INSPECTION_REQUESTED
    }


def test_typed_tool_result_requires_measured_execution_duration() -> None:
    request_id = "ccir_" + "d" * 24
    receipt = CrewChiefSelectionReceipt.build(
        selection_policy_id="p353.test.v1",
        candidate_count=0,
        selected_count=0,
        omitted_count=0,
        selected_artifact_ids=(),
        selection_reasons=(),
        required_artifact_ids=(),
        required_artifacts_present=True,
    )

    with pytest.raises(ValueError, match="typed tool results require"):
        _event(
            "investigation-1",
            2,
            "8" * 64,
            "tool_result_attached",
            CrewChiefEventPayload(
                message="No exact evidence found.",
                tool_id="inspect_p19_causes",
                inspection_request_id=request_id,
                finding_kind="no_signal",
                completed_measurement_ids=("inspect_p19_causes",),
                ambiguity_before=2,
                ambiguity_after=2,
                selection_receipt=receipt,
            ),
        )


def test_one_exact_artifact_updates_only_the_cause_it_links() -> None:
    request_id = "ccir_" + "b" * 24
    receipt = CrewChiefSelectionReceipt.build(
        selection_policy_id="p353.test.v1",
        candidate_count=1,
        selected_count=1,
        omitted_count=0,
        selected_artifact_ids=("artifact-1",),
        selection_reasons=("artifact-1: exact support",),
        required_artifact_ids=(),
        required_artifacts_present=True,
    )
    invocation = _event(
        "investigation-1",
        1,
        "8" * 64,
        "tool_invoked",
        CrewChiefEventPayload(
            message="Inspection requested.",
            tool_id="inspect_p19_causes",
            inspection_request_id=request_id,
            cause_ids=("cause-1", "cause-2"),
            requested_measurement_ids=("inspect_p19_causes",),
        ),
    )
    result = _event(
        "investigation-1",
        2,
        "8" * 64,
        "tool_result_attached",
        CrewChiefEventPayload(
            message="Exact support found.",
            tool_id="inspect_p19_causes",
            inspection_request_id=request_id,
            tool_execution_duration_ms=1.0,
            finding_kind="support",
            cause_ids=("cause-1",),
            artifact_ids=("artifact-1",),
            strongest_support_artifact_ids=("artifact-1",),
            completed_measurement_ids=("inspect_p19_causes",),
            ambiguity_before=2,
            ambiguity_after=1,
            selection_receipt=receipt,
        ),
    )
    inspected = _event(
        "investigation-1",
        3,
        "8" * 64,
        "hypothesis_inspected",
        CrewChiefEventPayload(
            message="Cause one received exact support.",
            inspection_request_id=request_id,
            finding_kind="support",
            cause_ids=("cause-1",),
            artifact_ids=("artifact-1",),
        ),
    )

    folded = fold_investigation(
        _investigation(),
        (invocation, result, inspected),
        (_cause("cause-1", "artifact-1"), _cause("cause-2", "artifact-2")),
    )
    progress = {item.cause_id: item.progress for item in folded.hypotheses}
    assert progress == {
        "cause-1": InvestigationProgress.SUPPORT_FOUND,
        "cause-2": InvestigationProgress.INSPECTION_REQUESTED,
    }


def test_every_driver_answer_has_typed_scope_or_explicit_context_only() -> None:
    answers = (
        "builds through run",
        "traffic only",
        "also clean air",
        "load transition only",
        "before throttle",
        "after full throttle",
        "after exit carry",
        "during load transition",
        "after chassis settles",
        "both",
        "not repeatable",
    )
    interpretations = tuple(_interpret_driver_answer(answer) for answer in answers)
    assert interpretations[-1].context_record_only
    assert all(not item.context_record_only for item in interpretations[:-1])
    assert _interpret_driver_answer("builds through run").stint_scope == "migration"
    assert _interpret_driver_answer("traffic only").traffic_scope == "disturbed_air"
    assert _interpret_driver_answer("after full throttle").power_state_scope == "power_on"
    assert _interpret_driver_answer("after chassis settles").response_regime_scope == (
        "steady_state",
    )


def _critic_bundle(*, blocked: bool = False):
    contradiction = SimpleNamespace(
        summary="RF tire-state migration remains unresolved.",
        event_id="contradiction-1",
        citation_id="contradiction-1",
    )
    cause = SimpleNamespace(contradicting_evidence=(contradiction,))
    action = SimpleNamespace(
        setup_authorized=False,
        kind="no_call",
        control_key=None,
        current_value=None,
        proposed_value=None,
    )
    return SimpleNamespace(
        report=SimpleNamespace(
            session_id="session-1",
            briefing=SimpleNamespace(action=action),
            reasoning_snapshot=SimpleNamespace(causes=(cause,)),
            data_quality=SimpleNamespace(status="blocked" if blocked else "ready"),
        )
    )


def test_critic_reaches_all_four_declared_outcomes_without_creating_action() -> None:
    identity = _identity()
    passed = _critique(_critic_bundle(), identity)
    blocked = _critique(_critic_bundle(blocked=True), identity)
    question = DriverDiagnosticQuestion(
        question_id="question-1",
        workspace_revision=identity.workspace_revision,
        question="Before throttle or after full throttle?",
        answer_options=("before throttle", "after full throttle"),
        reason="Telemetry cannot distinguish the power-state boundary.",
    )
    ask_driver = _critique(_critic_bundle(), identity, question=question)
    folded = SimpleNamespace(
        status="open",
        completed_tool_ids=("inspect_data_quality", "inspect_lap_context"),
    )
    reinvestigate = _critique(_critic_bundle(), identity, folded=folded)

    assert passed.outcome == "pass"
    assert blocked.outcome == "blocked"
    assert ask_driver.outcome == "ask_driver"
    assert reinvestigate.outcome == "reinvestigate"
    assert all(
        item.forbidden_decision_kinds in {(), ("controlled_test",)}
        for item in (passed, blocked, ask_driver, reinvestigate)
    )


def test_p19_authority_identity_is_unchanged_by_p353_cognitive_models() -> None:
    identity = _identity()
    before = identity.authority_revision
    _interpret_driver_answer("after full throttle")
    assert identity.authority_revision == before
    assert identity.objective_id == EngineeringObjective.RACE_LONG_RUN
    assert EvidenceState.CONTROLLED_TEST_EFFECT.value == "controlled_test_effect"


def test_typed_driver_scope_materially_reorders_the_next_physical_inspection() -> None:
    bundle, folded, p26 = _planner_fixture()
    folded.completed_tool_ids = (
        *folded.completed_tool_ids,
        "inspect_lap_time_opportunity",
    )
    original_causes = bundle.report.reasoning_snapshot.causes

    folded.driver_answers = ("after full throttle",)
    folded.driver_answer_interpretations = (
        _interpret_driver_answer("after full throttle"),
    )
    power_subgoal = _subgoal(bundle, folded, p26, SimpleNamespace())

    folded.driver_answers = ("braking/entry",)
    folded.driver_answer_interpretations = (
        _interpret_driver_answer("braking/entry"),
    )
    brake_subgoal = _subgoal(bundle, folded, p26, SimpleNamespace())

    assert power_subgoal is not None
    assert power_subgoal.selected_tool == "inspect_exit_carry"
    assert power_subgoal.driver_answer_interpretation.time_origin_scope == (
        "following_straight"
    )
    assert brake_subgoal is not None
    assert brake_subgoal.selected_tool == "inspect_driver_vehicle_separation"
    assert brake_subgoal.driver_answer_interpretation.power_state_scope == (
        "brake_applied"
    )
    assert bundle.report.reasoning_snapshot.causes == original_causes


def test_strongest_contradiction_cannot_be_omitted_by_artifact_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = tuple(
        SimpleNamespace(
            artifact_id=f"artifact-{index:02d}",
            polarity="support",
            evidence_state=EvidenceState.MEASURED,
            producer_id="p19.reasoning_snapshot",
            typed_artifact=None,
        )
        for index in range(20)
    )
    contradiction = entries[-1]
    contradiction.polarity = "contradiction"
    workspace = SimpleNamespace(
        current_subgoal=None,
        vehicle_dynamics=SimpleNamespace(
            strongest_contradiction_artifact_id=contradiction.artifact_id,
        ),
        p19_contradiction_artifact_ids=(contradiction.artifact_id,),
    )
    monkeypatch.setattr(
        crew_chief_service,
        "_candidate_tool_entries",
        lambda *_args, **_kwargs: entries,
    )

    selected = _select_tool_entries(workspace, "inspect_p19_causes", ())

    assert len(selected) == 16
    assert contradiction in selected


def test_bounded_advance_counts_one_driver_action_and_stops_at_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity()
    initial = SimpleNamespace(
        identity=identity,
        folded_state=SimpleNamespace(
            status="open",
            completed_tool_ids=(),
            driver_answers=(),
        ),
        pending_driver_question=None,
        critique=SimpleNamespace(outcome="pass"),
        current_subgoal=SimpleNamespace(selected_tool="inspect_data_quality"),
    )
    boundary = SimpleNamespace(
        identity=identity,
        folded_state=SimpleNamespace(
            status="open",
            completed_tool_ids=("inspect_data_quality",),
            driver_answers=(),
        ),
        pending_driver_question=SimpleNamespace(question_id="question-1"),
        critique=SimpleNamespace(outcome="ask_driver"),
        current_subgoal=None,
    )
    calls: list[bool] = []
    action_count: list[str] = []

    class ActionRepository:
        def __init__(self, _db_path=None) -> None:
            pass

        def record_continue_action(self, investigation_id: str) -> int:
            action_count.append(investigation_id)
            return len(action_count)

    monkeypatch.setattr(
        crew_chief_service,
        "build_crew_chief_workspace",
        lambda *_args, **_kwargs: initial,
    )
    monkeypatch.setattr(crew_chief_service, "CrewChiefRepository", ActionRepository)

    def one_step(*_args, **kwargs):
        calls.append(kwargs["_record_continue_action"])
        return boundary

    monkeypatch.setattr(crew_chief_service, "continue_investigation", one_step)

    result = advance_until_boundary(
        identity.run_id,
        "investigation-1",
        session_id=identity.session_id,
        expected_workspace_revision=identity.workspace_revision,
    )

    assert result is boundary
    assert action_count == ["investigation-1"]
    assert calls == [False]


def test_continue_action_counter_survives_restart_without_touching_event_head(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "p353-actions.sqlite")
    _seed_run(db_path)
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(_investigation())

    assert repository.record_continue_action("investigation-1") == 1
    assert repository.record_continue_action("investigation-1") == 2

    restarted = CrewChiefRepository(db_path)
    assert restarted.continue_action_count("investigation-1") == 2
    assert restarted.list_events("investigation-1") == ()


def test_legacy_untyped_inspection_marker_is_readable_but_cognitively_inert() -> None:
    marker = _event(
        "investigation-1",
        1,
        "8" * 64,
        "hypothesis_inspected",
        CrewChiefEventPayload(
            message="Historical P34 marker.",
            cause_ids=("cause-1",),
            artifact_ids=("artifact-1",),
        ),
    )

    folded = fold_investigation(
        _investigation(),
        (marker,),
        (_cause("cause-1", "artifact-1"),),
    )

    assert folded.hypotheses[0].progress == InvestigationProgress.NOT_INSPECTED
