from __future__ import annotations

from types import SimpleNamespace

import pytest

import api.routes_intelligence as routes
from api.intelligence_schemas import IntelligenceQueryRequest
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    EngineeringEvidenceIndexEntry,
    EngineeringObjective,
)
from racelab_engine.models.engineering_case import EngineeringMission
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.engineering_case_query_service import (
    answer_engineering_case_question,
)
from tests.test_internal_intelligence_service import _authorized_report


CASE_ID = "p3543case_" + "a" * 24
CASE_SHA256 = "b" * 64


def _authorized_workspace(report, setup: SetupSnapshot):
    action = report.briefing.action
    citations_by_event_id = {
        node.citation.event_id: node.citation
        for node in report.evidence_graph.nodes
        if node.citation is not None and node.citation.event_id is not None
    }
    citations = tuple(
        citations_by_event_id[event_id] for event_id in action.source_event_ids
    )
    setup_sha256 = canonical_json_sha256(setup)
    build_sha256 = "c" * 64
    identity = SimpleNamespace(
        run_id=report.run_id,
        session_id=report.session_id,
        setup_id=setup.setup_id,
        setup_snapshot_sha256=setup_sha256,
        vehicle_runtime_identity_hash=build_sha256,
    )
    entries = tuple(
        EngineeringEvidenceIndexEntry(
            artifact_id=citation.event_id,
            producer_id="p19.reasoning_snapshot",
            run_id=report.run_id,
            session_id=report.session_id,
            setup_id=setup.setup_id,
            workspace_run_id=report.run_id,
            workspace_session_id=report.session_id,
            workspace_setup_id=setup.setup_id,
            source_run_id=report.run_id,
            source_session_id=report.session_id,
            source_setup_id=setup.setup_id,
            source_setup_sha256=setup_sha256,
            source_build_context_sha256=build_sha256,
            source_provenance_available=True,
            lap_numbers=(citation.lap_number,),
            lap_pct_start=citation.lap_pct_start,
            lap_pct_end=citation.lap_pct_end,
            phase=citation.phase,
            objective=EngineeringObjective.RACE_LONG_RUN,
            source_channels=citation.channels,
            evidence_state=citation.evidence_state,
            polarity="support",
            authority_ceiling="measurement_only",
        )
        for citation in citations
    )
    terminal = SimpleNamespace(
        kind="controlled_test",
        title=action.title,
        instruction=action.instruction,
        authority="p19_projection_only",
        source_event_ids=tuple(action.source_event_ids),
        blocker_reasons=(),
    )
    mission = EngineeringMission(
        what=action.title,
        where="exit · 20.0–30.0%",
        why_it_matters="This is the current exact-scope P19 terminal decision.",
        uncertain="No stronger causal claim is authorized.",
        next=action.instruction,
        done_when="The controlled A/B/A2 contract is complete.",
        source_authority="p19_exact_mirror",
        terminal_move_sha256=canonical_json_sha256(terminal),
        source_artifact_ids=tuple(action.source_event_ids),
        setup_authorized=True,
    )
    workspace = SimpleNamespace(
        identity=identity,
        evidence_index=SimpleNamespace(entries=entries),
        engineering_case=SimpleNamespace(
            case_sha256=CASE_SHA256,
            mission=mission,
        ),
        terminal_decision=terminal,
    )
    return workspace, citations


def test_exact_case_action_reuses_complete_p19_citations() -> None:
    report = _authorized_report()
    setup = SetupSnapshot(
        setup_id=f"{report.run_id}:setup",
        run_id=report.run_id,
        setup_name="Exact case citation fixture",
        cross_weight_percent=50.0,
    )
    workspace, citations = _authorized_workspace(report, setup)

    answer = answer_engineering_case_question(
        "What is the exact current next move?",
        workspace,
        available_citations=citations,
    )

    assert answer is not None
    assert answer.action_authorized is True
    assert answer.answer == workspace.terminal_decision.instruction
    assert answer.action_source_event_ids == workspace.terminal_decision.source_event_ids
    assert answer.citations == citations
    assert answer.blocker_reasons == ()


@pytest.mark.parametrize("citation_mutation", ["missing", "wrong_run", "duplicate"])
def test_exact_case_action_is_withheld_when_citations_do_not_resolve(
    citation_mutation: str,
) -> None:
    report = _authorized_report()
    setup = SetupSnapshot(
        setup_id=f"{report.run_id}:setup",
        run_id=report.run_id,
        setup_name="Exact case citation fixture",
        cross_weight_percent=50.0,
    )
    workspace, citations = _authorized_workspace(report, setup)
    if citation_mutation == "missing":
        available = ()
    elif citation_mutation == "wrong_run":
        available = (
            citations[0].model_copy(update={"run_id": "foreign-run"}),
            *citations[1:],
        )
    else:
        available = (*citations, citations[0])

    answer = answer_engineering_case_question(
        "What is the exact current next move?",
        workspace,
        available_citations=tuple(available),
    )

    assert answer is not None
    assert answer.action_authorized is False
    assert answer.action_source_event_ids == ()
    assert answer.citations == ()
    assert workspace.terminal_decision.instruction not in answer.answer
    assert "withheld" in answer.answer
    assert answer.blocker_reasons == (
        "Smart Engineer could not resolve every P19 mission source event to one "
        "exact qualified citation.",
    )


def test_exact_case_api_publishes_the_resolved_source_event_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _authorized_report()
    assert report.session_id is not None
    setup = SetupSnapshot(
        setup_id=f"{report.run_id}:setup",
        run_id=report.run_id,
        setup_name="Exact case citation fixture",
        cross_weight_percent=50.0,
    )
    workspace, citations = _authorized_workspace(report, setup)
    bundle = SimpleNamespace(
        report=report,
        calibration=SimpleNamespace(scope_run_ids=(report.run_id,)),
    )
    revision = SimpleNamespace(
        case_id=CASE_ID,
        case_sha256=CASE_SHA256,
        case=SimpleNamespace(objective_id="race_long_run"),
    )
    monkeypatch.setattr(
        routes,
        "build_run_intelligence",
        lambda run_id, session_id=None: bundle,
    )
    monkeypatch.setattr(
        routes.RaceLabRepository,
        "get_overview",
        lambda self, run_id: SimpleNamespace(setup_snapshot=setup),
    )
    monkeypatch.setattr(
        routes.EngineeringCaseRepository,
        "current_for_scope",
        lambda self, run_id, session_id: revision,
    )
    monkeypatch.setattr(
        routes,
        "build_crew_chief_workspace",
        lambda *args, **kwargs: workspace,
    )

    response = routes.query_run_intelligence(
        report.run_id,
        IntelligenceQueryRequest(
            question="What is the exact current next move?",
            session_id=report.session_id,
            case_id=CASE_ID,
            case_sha256=CASE_SHA256,
        ),
    )
    foreign_lap_response = routes.query_run_intelligence(
        report.run_id,
        IntelligenceQueryRequest(
            question="What is the exact current next move?",
            session_id=report.session_id,
            case_id=CASE_ID,
            case_sha256=CASE_SHA256,
            selected_lap=max(
                citation.lap_number for citation in citations
                if citation.lap_number is not None
            )
            + 1,
        ),
    )

    assert response.action_authorized is True
    assert response.action_source_event_ids == list(
        workspace.terminal_decision.source_event_ids
    )
    assert [citation.event_id for citation in response.citations] == [
        citation.event_id for citation in citations
    ]
    assert all(citation.valid_for_tuning for citation in response.citations)
    assert foreign_lap_response.action_authorized is False
    assert foreign_lap_response.action_source_event_ids == []
    assert foreign_lap_response.citations == []
    assert workspace.terminal_decision.instruction not in foreign_lap_response.answer


def test_exact_case_api_withholds_action_when_graph_citation_is_not_qualified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _authorized_report()
    assert report.session_id is not None
    setup = SetupSnapshot(
        setup_id=f"{report.run_id}:setup",
        run_id=report.run_id,
        setup_name="Exact case citation fixture",
        cross_weight_percent=50.0,
    )
    workspace, _ = _authorized_workspace(report, setup)
    source_event_ids = set(workspace.terminal_decision.source_event_ids)
    withheld_graph = report.evidence_graph.model_copy(
        update={
            "nodes": tuple(
                node.model_copy(
                    update={
                        "qualified": False,
                        "blocker_reasons": ("Late citation qualification failure.",),
                    }
                )
                if node.citation is not None
                and node.citation.event_id in source_event_ids
                else node
                for node in report.evidence_graph.nodes
            )
        }
    )
    withheld_report = report.model_copy(update={"evidence_graph": withheld_graph})
    bundle = SimpleNamespace(
        report=withheld_report,
        calibration=SimpleNamespace(scope_run_ids=(report.run_id,)),
    )
    revision = SimpleNamespace(
        case_id=CASE_ID,
        case_sha256=CASE_SHA256,
        case=SimpleNamespace(objective_id="race_long_run"),
    )
    monkeypatch.setattr(
        routes,
        "build_run_intelligence",
        lambda run_id, session_id=None: bundle,
    )
    monkeypatch.setattr(
        routes.RaceLabRepository,
        "get_overview",
        lambda self, run_id: SimpleNamespace(setup_snapshot=setup),
    )
    monkeypatch.setattr(
        routes.EngineeringCaseRepository,
        "current_for_scope",
        lambda self, run_id, session_id: revision,
    )
    monkeypatch.setattr(
        routes,
        "build_crew_chief_workspace",
        lambda *args, **kwargs: workspace,
    )

    response = routes.query_run_intelligence(
        report.run_id,
        IntelligenceQueryRequest(
            question="What is the exact current next move?",
            session_id=report.session_id,
            case_id=CASE_ID,
            case_sha256=CASE_SHA256,
        ),
    )

    assert response.action_authorized is False
    assert response.action_source_event_ids == []
    assert response.citations == []
    assert workspace.terminal_decision.instruction not in response.answer
    assert "withheld" in response.answer
    assert response.blocker_reasons == [
        "Smart Engineer could not resolve every P19 mission source event to one "
        "exact qualified citation."
    ]


def test_exact_case_api_rejects_revision_that_changes_during_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _authorized_report()
    assert report.session_id is not None
    setup = SetupSnapshot(
        setup_id=f"{report.run_id}:setup",
        run_id=report.run_id,
        setup_name="Exact case citation fixture",
        cross_weight_percent=50.0,
    )
    workspace, citations = _authorized_workspace(report, setup)
    bundle = SimpleNamespace(
        report=report,
        calibration=SimpleNamespace(scope_run_ids=(report.run_id,)),
    )
    current = SimpleNamespace(
        case_id=CASE_ID,
        case_sha256=CASE_SHA256,
        case=SimpleNamespace(objective_id="race_long_run"),
    )
    advanced = SimpleNamespace(
        case_id=CASE_ID,
        case_sha256="d" * 64,
        case=SimpleNamespace(objective_id="race_long_run"),
    )
    repository_reads = 0

    def read_current(*_args, **_kwargs):
        nonlocal repository_reads
        repository_reads += 1
        return current if repository_reads == 1 else advanced

    monkeypatch.setattr(routes, "build_run_intelligence", lambda *_args, **_kwargs: bundle)
    monkeypatch.setattr(
        routes.RaceLabRepository,
        "get_overview",
        lambda self, run_id: SimpleNamespace(setup_snapshot=setup),
    )
    monkeypatch.setattr(
        routes.EngineeringCaseRepository,
        "current_for_scope",
        read_current,
    )
    monkeypatch.setattr(routes, "build_crew_chief_workspace", lambda *_args, **_kwargs: workspace)

    with pytest.raises(routes.HTTPException, match="changed while Smart Engineer was answering") as exc:
        routes.query_run_intelligence(
            report.run_id,
            IntelligenceQueryRequest(
                question="What is the exact current next move?",
                session_id=report.session_id,
                case_id=CASE_ID,
                case_sha256=CASE_SHA256,
            ),
        )

    assert exc.value.status_code == 409
    assert repository_reads == 2
    assert workspace.terminal_decision.instruction not in str(exc.value.detail)
    assert citations
