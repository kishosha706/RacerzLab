from __future__ import annotations

import hashlib
import sqlite3
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from api.intelligence_adapter import (
    to_public_intelligence_citation,
    to_public_intelligence_navigation,
    to_public_intelligence_report,
    to_public_mind_change_criterion,
)
from api.intelligence_schemas import (
    IntelligenceQueryRequest,
    IntelligenceQueryResponse,
    RunIntelligenceResponse,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import GroundedQueryResult, InternalIntelligenceReport
from racelab_engine.services.engineering_memory_service import (
    record_driver_presentation_preference_for_run,
)
from racelab_engine.services.intelligence_service import answer_grounded_query
from racelab_engine.services.run_intelligence_service import build_run_intelligence


router = APIRouter(prefix="/api/runs", tags=["internal-intelligence"])


def _http_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "not found" in message.casefold():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=409, detail=message)


def _query_action_matches_current_report(
    result: GroundedQueryResult,
    report: InternalIntelligenceReport,
) -> bool:
    try:
        public_report = to_public_intelligence_report(report)
    except ValueError:
        return False
    action = public_report.briefing.action
    canonical_action_values = (
        action.control_key,
        action.current_value,
        action.proposed_value,
        action.instruction,
    )
    return bool(
        result.action_authorized
        and public_report.status == "ready"
        and public_report.decision_status == "ready"
        and public_report.data_quality is not None
        and public_report.data_quality.status == "ready"
        and not public_report.data_quality.issues
        and not public_report.blocker_reasons
        and not public_report.briefing.blocker_reasons
        and action.kind == "controlled_test"
        and action.setup_authorized
        and not action.blocker_reasons
        and all(
            isinstance(value, str) and value and value.strip() == value
            for value in canonical_action_values
        )
        and result.answer == action.instruction
        and tuple(result.action_source_event_ids) == tuple(action.source_event_ids)
        and len(set(result.action_source_event_ids)) == len(result.action_source_event_ids)
    )


@router.get("/{run_id}/intelligence", response_model=RunIntelligenceResponse)
def get_run_intelligence(
    run_id: str,
    session_id: str | None = None,
    refresh: Annotated[str | None, Query(max_length=1024)] = None,
) -> RunIntelligenceResponse:
    del refresh
    try:
        bundle = build_run_intelligence(run_id, session_id=session_id)
        return to_public_intelligence_report(
            bundle.report,
            narrative_entries=bundle.narrative_entries,
            calibration=bundle.calibration,
            driver_profile=bundle.driver_profile,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


_QUERY_HEADLINES = {
    "why_this_call": "Why this call",
    "where_is_loss": "Where the loss appears",
    "what_next": "Best next step",
    "what_evidence": "Evidence behind the call",
    "what_was_ruled_out": "What was ruled out",
    "what_worked_before": "What worked here before",
    "what_changed": "What changed",
    "how_repeatable": "Repeatable opportunity",
    "driver_focus": "Driver repeatability focus",
    "what_anomalies": "Same-setup anomalies",
    "mechanism_evidence": "Typed mechanism evidence",
    "hypothesis_history": "Controlled hypothesis history",
    "recovery_priority": "Evidence recovery priority",
    "how_reliable": "Prediction track record",
    "what_would_change_mind": "What would change the call",
    "data_quality": "Data quality",
    "unsupported": "Question not supported",
}


@router.post(
    "/{run_id}/intelligence/query",
    response_model=IntelligenceQueryResponse,
)
def query_run_intelligence(
    run_id: str,
    request: IntelligenceQueryRequest,
) -> IntelligenceQueryResponse:
    try:
        bundle = build_run_intelligence(run_id, session_id=request.session_id)
    except ValueError as exc:
        raise _http_error(exc) from exc
    selected_scope_laps = tuple(
        dict.fromkeys(
            lap_number
            for lap_number in (
                request.selected_lap,
                request.selected_window_start_lap,
                request.selected_window_end_lap,
            )
            if lap_number is not None
        )
    )
    graph_lap_ids = {
        item.entity_id
        for item in bundle.report.evidence_graph.nodes
        if item.kind.value == "lap"
    }
    missing_scope_laps = tuple(
        lap_number
        for lap_number in selected_scope_laps
        if f"{run_id}:{lap_number}" not in graph_lap_ids
    )
    if missing_scope_laps:
        missing = ", ".join(str(lap_number) for lap_number in missing_scope_laps)
        raise HTTPException(
            status_code=409,
            detail=f"Selected lap scope ({missing}) does not belong to run {run_id}.",
        )
    selected_window = request.selected_window_start_lap is not None
    result = answer_grounded_query(
        request.question,
        bundle.report,
        selected_lap_number=None if selected_window else request.selected_lap,
        selected_window_start_lap=request.selected_window_start_lap,
        selected_window_end_lap=request.selected_window_end_lap,
        selected_window_representative_lap=(
            request.selected_window_representative_lap
        ),
    )
    if request.presentation_mode is not None:
        digest = hashlib.sha256(
            (
                f"{run_id}|{bundle.report.session_id or ''}|"
                f"{bundle.driver_profile.profile_id}|{request.selected_lap or ''}|"
                f"{request.selected_window_start_lap or ''}|"
                f"{request.selected_window_end_lap or ''}|"
                f"{request.selected_window_representative_lap or ''}|"
                f"{request.presentation_mode}|"
                f"{' '.join(request.question.casefold().split())}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        try:
            record_driver_presentation_preference_for_run(
                run_id,
                source_key=f"grounded-query:{digest}",
                preferred_mode=request.presentation_mode,
            )
        except (OSError, ValueError, sqlite3.Error):
            # Presentation memory is non-authoritative. A stale/corrupt profile
            # must never suppress an otherwise valid evidence-grounded answer.
            pass
    scope_run_ids = tuple(bundle.calibration.scope_run_ids)
    scope_run_id_set = set(scope_run_ids)
    citations = [to_public_intelligence_citation(item) for item in result.citations]
    if any(citation.run_id not in scope_run_id_set for citation in citations):
        raise HTTPException(
            status_code=409,
            detail="Query evidence escaped the exact run/session scope and was withheld.",
        )
    scoped_navigation = tuple(
        item for item in result.suggested_navigation if item.run_id in scope_run_id_set
    )
    navigation_withheld = len(scoped_navigation) != len(result.suggested_navigation)
    query_action_matches_report = _query_action_matches_current_report(
        result,
        bundle.report,
    )
    action_binding_withheld = result.action_authorized and not query_action_matches_report
    action_authorized = result.action_authorized and query_action_matches_report
    if action_authorized:
        evidence_state = bundle.report.briefing.action.evidence_state
    elif citations:
        evidence_state = citations[0].evidence_state
    elif result.supported:
        evidence_state = EvidenceState.NEEDS_CONFIRMATION
    else:
        evidence_state = EvidenceState.UNAVAILABLE
    report_criteria = {
        item.criterion_id: item for item in bundle.report.mind_change_criteria
    }
    if any(
        report_criteria.get(item.criterion_id) != item
        for item in result.mind_change_criteria
    ):
        raise HTTPException(
            status_code=409,
            detail="Query mind-change criteria did not match the current report scope.",
        )
    return IntelligenceQueryResponse(
        run_id=run_id,
        session_id=bundle.report.session_id,
        scope_run_ids=list(scope_run_ids),
        selected_lap=request.selected_lap,
        status="ready" if result.supported else "unavailable",
        question=request.question,
        headline=_QUERY_HEADLINES[result.intent],
        answer=(
            "The setup instruction was withheld because it did not match the current "
            "evidence-qualified briefing. Reopen the controlled test from the current report."
            if action_binding_withheld
            else (
                result.answer
                + " A historical handoff outside the open run/session scope was withheld."
                if navigation_withheld
                else result.answer
            )
        ),
        interpreted_lap_number=result.interpreted_lap_number,
        interpreted_window_start_lap=result.interpreted_window_start_lap,
        interpreted_window_end_lap=result.interpreted_window_end_lap,
        interpreted_window_representative_lap=(
            result.interpreted_window_representative_lap
        ),
        interpreted_phase=result.interpreted_phase,
        interpreted_control_key=result.interpreted_control_key,
        clarification_required=result.clarification_required,
        action_authorized=action_authorized,
        action_source_event_ids=(
            list(result.action_source_event_ids) if action_authorized else []
        ),
        evidence_state=evidence_state,
        citations=citations,
        suggested_navigation=[
            to_public_intelligence_navigation(item)
            for item in scoped_navigation
        ],
        mind_change_criteria=[
            to_public_mind_change_criterion(item)
            for item in result.mind_change_criteria
        ],
        blocker_reasons=[
            *result.blocker_reasons,
            *(
                ("Historical navigation outside the exact run/session scope was withheld.",)
                if navigation_withheld
                else ()
            ),
            *(
                (
                    "The query action did not exactly match the current controlled-test "
                    "instruction and source evidence.",
                )
                if action_binding_withheld
                else ()
            ),
        ],
        follow_up_questions=list(bundle.report.suggested_questions),
    )


__all__ = ["router"]
