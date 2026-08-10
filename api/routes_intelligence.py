from __future__ import annotations

import hashlib
import sqlite3
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from api.intelligence_adapter import (
    to_public_intelligence_citation,
    to_public_intelligence_navigation,
    to_public_intelligence_report,
    to_public_mind_change_criterion,
)
from api.intelligence_schemas import (
    IntelligenceCitationResponse,
    IntelligenceQueryRequest,
    IntelligenceQueryResponse,
    MeasurementAttemptRequest,
    MeasurementAttemptResponse,
    RunIntelligenceResponse,
)
from racelab_engine.analysis.lap_eligibility import lap_is_eligible
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.experiment import MeasurementAttempt
from racelab_engine.models.intelligence import (
    EvidenceCitation,
    GroundedQueryResult,
    InternalIntelligenceReport,
)
from racelab_engine.services.engineering_memory_service import (
    record_driver_presentation_preference_for_run,
)
from racelab_engine.services.experiment_service import (
    record_durable_measurement_attempt,
)
from racelab_engine.services.intelligence_service import answer_grounded_query
from racelab_engine.services.run_intelligence_service import build_run_intelligence
from racelab_engine.services.track_map_service import (
    build_track_regions,
    find_best_map_for_run,
    get_track_map,
    locate_track_region,
)
from racelab_engine.services.vehicle_systems_service import (
    build_component_awareness,
    inspect_component,
    trace_control_mechanism,
)
from racelab_engine.storage.repository import RaceLabRepository

router = APIRouter(prefix="/api/runs", tags=["internal-intelligence"])


class _TrackRegionContext:
    """Cache one canonical region model for AI scoping and citation display."""

    def __init__(self) -> None:
        self._repository = RaceLabRepository()
        self._regions_by_run: dict[str, list[dict[str, object]]] = {}

    def regions(self, run_id: str) -> list[dict[str, object]]:
        if run_id in self._regions_by_run:
            return self._regions_by_run[run_id]
        regions: list[dict[str, object]] = []
        try:
            overview = self._repository.get_overview(run_id)
            session = getattr(overview, "session", None) if overview is not None else None
            track_name = (
                getattr(session, "track_name", None)
                or getattr(session, "track_display_name", None)
                or ""
            )
            match = find_best_map_for_run(run_id, track_name)
            track_map = get_track_map(match["map_id"]) if match and match.get("map_id") else None
            if track_map is not None:
                regions = build_track_regions(track_map, match)
        except (OSError, TypeError, ValueError, KeyError, sqlite3.Error):
            regions = []
        self._regions_by_run[run_id] = regions
        return regions

    def locate(self, run_id: str, lap_pct: float) -> dict[str, object] | None:
        return locate_track_region(self.regions(run_id), lap_pct)

    def catalog(self, run_id: str) -> dict[str, str]:
        catalog: dict[str, str] = {}
        for region in self.regions(run_id):
            region_id = str(region.get("region_id") or "")
            label = str(region.get("label") or "")
            if region_id.startswith("turn_"):
                catalog[region_id] = label
            elif region_id.startswith("straight:"):
                catalog[region_id.split(":", 1)[1]] = label
            elif label.casefold().replace(" ", "") == "frontstretch":
                catalog["front_stretch"] = "Front Stretch"
            elif label.casefold().replace(" ", "") == "backstretch":
                catalog["backstretch"] = "Backstretch"
        return catalog


def _citation_track_locations(
    citations: tuple[EvidenceCitation, ...],
    *,
    context: _TrackRegionContext | None = None,
) -> dict[str, dict[str, object]]:
    """Resolve citation positions through the same canonical map regions the UI receives."""
    region_context = context or _TrackRegionContext()
    result: dict[str, dict[str, object]] = {}
    for citation in citations:
        lap_pct = (
            citation.lap_pct_peak
            if citation.lap_pct_peak is not None
            else citation.lap_pct_start
        )
        if lap_pct is None:
            continue
        location = region_context.locate(citation.run_id, lap_pct)
        if location is not None:
            result[citation.citation_id] = location
    return result


def _region_aware_query_answer(
    result: GroundedQueryResult,
    citations: list[IntelligenceCitationResponse],
) -> str:
    answer = result.answer
    if (
        result.intent == "where_is_loss"
        and answer.startswith("The earliest qualified track location is near")
        and citations
        and citations[0].track_region_label is not None
        and citations[0].lap_pct is not None
    ):
        return (
            f"The earliest qualified track location is {citations[0].track_region_label} "
            f"near {citations[0].lap_pct:g}% of lap {citations[0].lap_number}; "
            "open the cited event for the recorded trace."
        )
    return answer


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


@router.get("/{run_id}/vehicle-systems")
def get_run_vehicle_systems(run_id: str, session_id: str | None = None) -> dict[str, object]:
    """Return component cognition as a read-only projection of P19/P20 truth."""
    try:
        bundle = build_run_intelligence(run_id, session_id=session_id)
        overview = RaceLabRepository().get_overview(run_id)
        projection = build_component_awareness(
            bundle.report,
            setup_snapshot=overview.setup_snapshot if overview is not None else None,
            car_path=overview.session.car_path if overview is not None else None,
        )
        return projection.model_dump(mode="json")
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/{run_id}/vehicle-systems/components/{component_id}")
def get_run_vehicle_component(
    run_id: str,
    component_id: str,
    session_id: str | None = None,
) -> dict[str, object]:
    """Inspect one sourced component, its interactions, and exact-run state."""
    try:
        bundle = build_run_intelligence(run_id, session_id=session_id)
        overview = RaceLabRepository().get_overview(run_id)
        projection = build_component_awareness(
            bundle.report,
            setup_snapshot=overview.setup_snapshot if overview is not None else None,
            car_path=overview.session.car_path if overview is not None else None,
        )
        return {
            key: value.model_dump(mode="json")
            if hasattr(value, "model_dump")
            else [item.model_dump(mode="json") for item in value]
            if isinstance(value, tuple) and value and hasattr(value[0], "model_dump")
            else value
            for key, value in inspect_component(component_id, projection).items()
        }
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/{run_id}/vehicle-systems/controls/{control_key}/trace")
def get_vehicle_control_trace(run_id: str, control_key: str) -> dict[str, object]:
    """Trace only source-declared expectation edges; never infer a runtime cause."""
    try:
        if RaceLabRepository().get_overview(run_id) is None:
            raise ValueError(f"Run not found: {run_id}")
        edges = trace_control_mechanism(control_key)
        return {
            "run_id": run_id,
            "control_key": control_key,
            "authority": "engineering_expectation_only",
            "setup_authorized": False,
            "edges": [edge.model_dump(mode="json") for edge in edges],
        }
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/intelligence/measurement-attempt",
    response_model=MeasurementAttemptResponse,
)
def record_measurement_attempt(
    run_id: str,
    request: MeasurementAttemptRequest,
) -> MeasurementAttemptResponse:
    """Append a cleanly scoped mission outcome without granting setup authority."""
    try:
        bundle = build_run_intelligence(run_id, session_id=request.session_id)
    except ValueError as exc:
        raise _http_error(exc) from exc
    plan = bundle.report.best_measurement
    contract = plan.mission_contract
    if contract is None:
        raise HTTPException(
            status_code=409,
            detail="The current report has no immutable measurement contract to record.",
        )
    if (
        contract.contract_id != request.contract_id
        or contract.contract_sha256 != request.contract_sha256
    ):
        raise HTTPException(
            status_code=409,
            detail="The supplied attempt does not match the current immutable measurement contract.",
        )
    if plan.kind == "stop_testing":
        raise HTTPException(
            status_code=409,
            detail="This exact mission is already stopped; redesign it before recording another attempt.",
        )
    attempt_run_id = request.attempt_run_id or run_id
    overview = RaceLabRepository().get_overview(attempt_run_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {attempt_run_id}")
    eligible_ids = {
        f"{attempt_run_id}:{lap.lap_number}"
        for lap in overview.laps
        if lap_is_eligible(lap)
    }
    supplied_laps = tuple(request.eligible_lap_ids)
    if not set(supplied_laps).issubset(eligible_ids):
        raise HTTPException(
            status_code=409,
            detail="Measurement attempts may cite only canonical eligible laps from the declared attempt run.",
        )
    if request.outcome in {"completed_clean", "no_signal"} and len(supplied_laps) < contract.required_laps:
        raise HTTPException(
            status_code=409,
            detail=(
                "A clean or no-signal measurement outcome requires the contract's full "
                "eligible-lap cohort."
            ),
        )
    try:
        attempt = MeasurementAttempt(
            attempt_id=f"measurement-attempt:{uuid.uuid4().hex}",
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            run_id=attempt_run_id,
            eligible_lap_ids=supplied_laps,
            outcome=request.outcome,
            observed_channels=tuple(request.observed_channels),
            integrity_blockers=tuple(request.integrity_blockers),
            outcome_reasons=tuple(request.outcome_reasons),
        )
        record_durable_measurement_attempt(
            contract,
            attempt,
            repository=RaceLabRepository(),
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
    return MeasurementAttemptResponse(
        attempt_id=attempt.attempt_id,
        contract_id=attempt.contract_id,
        contract_sha256=attempt.contract_sha256,
        outcome=attempt.outcome,
    )


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
    "component_awareness": "Vehicle system awareness",
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
    overview = RaceLabRepository().get_overview(run_id)
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
    track_region_context = _TrackRegionContext()
    result = answer_grounded_query(
        request.question,
        bundle.report,
        selected_lap_number=None if selected_window else request.selected_lap,
        selected_window_start_lap=request.selected_window_start_lap,
        selected_window_end_lap=request.selected_window_end_lap,
        selected_window_representative_lap=(
            request.selected_window_representative_lap
        ),
        track_region_resolver=track_region_context.locate,
        track_region_catalog=lambda: track_region_context.catalog(run_id),
        vehicle_car_path=overview.session.car_path if overview is not None else None,
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
    if any(item.run_id not in scope_run_id_set for item in result.citations):
        raise HTTPException(
            status_code=409,
            detail="Query evidence escaped the exact run/session scope and was withheld.",
        )
    track_locations = _citation_track_locations(result.citations, context=track_region_context)
    citations = []
    for item in result.citations:
        citation = to_public_intelligence_citation(item)
        location = track_locations.get(item.citation_id)
        if location is not None:
            citation = IntelligenceCitationResponse.model_validate(
                {
                    **citation.model_dump(),
                    "track_region_id": location["region_id"],
                    "track_region_label": location["display_label"],
                    "track_region_phase": location["phase"],
                    "track_region_confidence": location["confidence"],
                }
            )
        citations.append(citation)
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
    answer = _region_aware_query_answer(result, citations)
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
                answer
                + " A historical handoff outside the open run/session scope was withheld."
                if navigation_withheld
                else answer
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
        interpreted_track_region_id=getattr(result, "interpreted_track_region_id", None),
        interpreted_track_region_label=getattr(result, "interpreted_track_region_label", None),
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
