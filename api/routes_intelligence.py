from __future__ import annotations

import hashlib
import math
import sqlite3
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from api.intelligence_identity import intelligence_snapshot_identity
from api.intelligence_adapter import (
    to_public_intelligence_citation,
    to_public_intelligence_navigation,
    to_public_intelligence_report,
    to_public_mind_change_criterion,
    to_public_next_trustworthy_move,
)
from api.intelligence_schemas import (
    IntelligenceCitationResponse,
    IntelligenceQueryRequest,
    IntelligenceQueryResponse,
    IntelligenceShellProjectionResponse,
    MeasurementAttemptRequest,
    MeasurementAttemptResponse,
    RunIntelligenceResponse,
)
from racelab_engine.analysis.lap_eligibility import lap_is_eligible
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.experiment import MeasurementAttempt
from racelab_engine.models.crew_chief import EngineeringObjective
from racelab_engine.models.intelligence import (
    EvidenceCitation,
    GroundedQueryResult,
    InternalIntelligenceReport,
)
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.models.vehicle_systems import (
    ComponentInspectionResponse,
    ControlMechanismTraceResponse,
    VehicleSystemsProjection,
)
from racelab_engine.services.import_service import (
    build_telemetry_capability_payload,
    read_telemetry_rows,
)
from racelab_engine.services.engineering_memory_service import (
    record_driver_presentation_preference_for_run,
)
from racelab_engine.services.experiment_service import (
    record_durable_measurement_attempt,
)
from racelab_engine.services.intelligence_service import answer_grounded_query
from racelab_engine.services.crew_chief_service import build_crew_chief_workspace
from racelab_engine.services.engineering_case_query_service import (
    answer_engineering_case_question,
)
from racelab_engine.services.lap_engineering_context_service import (
    mission_lap_context_is_clear,
)
from racelab_engine.services.run_intelligence_service import (
    build_run_intelligence,
    peek_cached_run_intelligence,
)
from racelab_engine.services.session_intelligence_service import setup_policy_fingerprint
from racelab_engine.services.session_service import get_session as get_racelab_session
from racelab_engine.services.track_map_service import (
    build_track_regions,
    find_best_map_for_run,
    get_track_map,
    locate_track_region,
)
from racelab_engine.services.vehicle_systems_service import (
    build_component_awareness,
    compile_vehicle_systems_graph,
    inspect_component,
    trace_control_mechanism,
    vehicle_systems_runtime_identity,
)
from racelab_engine.storage.repository import RaceLabRepository
from racelab_engine.storage.engineering_case_repository import (
    EngineeringCaseIntegrityError,
    EngineeringCaseRepository,
)

router = APIRouter(prefix="/api/runs", tags=["internal-intelligence"])


def _usable_measurement_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _verify_position_aligned_measurement_cohort(
    run_id: str,
    lap_ids: tuple[str, ...],
    required_channels: tuple[str, ...],
) -> None:
    columns = list(dict.fromkeys((
        "lap",
        "lap_dist_pct_100",
        "lap_dist_pct",
        *required_channels,
    )))
    for lap_id in lap_ids:
        try:
            lap_number = int(lap_id.rsplit(":", 1)[1])
            rows = read_telemetry_rows(run_id, lap=lap_number, columns=columns)
        except (IndexError, OSError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail="The declared mission cohort could not be read at exact lap scope.",
            ) from exc
        if not rows:
            raise HTTPException(
                status_code=409,
                detail="Every mission-accepted lap requires a readable telemetry trace.",
            )
        positions: list[float] = []
        for row in rows:
            value = row.get("lap_dist_pct_100")
            if value is None and row.get("lap_dist_pct") is not None:
                try:
                    value = float(row["lap_dist_pct"]) * 100.0
                except (TypeError, ValueError):
                    value = None
            try:
                position = float(value) if value is not None else None
            except (TypeError, ValueError):
                position = None
            if position is not None and math.isfinite(position):
                positions.append(position)
        unique_positions = sorted({round(value, 3) for value in positions})
        position_gaps = (
            [unique_positions[0]]
            + [
                right - left
                for left, right in zip(unique_positions, unique_positions[1:])
            ]
            + [100.0 - unique_positions[-1]]
            if unique_positions
            else [100.0]
        )
        if (
            len(positions) != len(rows)
            or any(value < 0.0 or value > 100.0 for value in positions)
            or len(unique_positions) < 10
            or max(position_gaps) > 5.0
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Every mission-accepted lap requires complete finite "
                    "physical-position coverage across the lap."
                ),
            )
        for channel in required_channels:
            usable_count = sum(
                _usable_measurement_value(row.get(channel)) for row in rows
            )
            if usable_count != len(rows):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Every mission-accepted lap requires complete usable "
                        f"coverage for required channel {channel}."
                    ),
                )


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


def _canonical_public_track_region_id(location: dict[str, object]) -> str | None:
    region_id = location.get("region_id")
    if not isinstance(region_id, str) or not region_id:
        return None
    if region_id.startswith("straight:"):
        return region_id.split(":", 1)[1]
    return region_id


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
    *,
    setup_snapshot: SetupSnapshot | None = None,
) -> bool:
    try:
        public_report = to_public_intelligence_report(
            report,
            setup_snapshot=setup_snapshot,
        )
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


@router.get(
    "/{run_id}/intelligence-shell",
    response_model=IntelligenceShellProjectionResponse,
)
def get_run_intelligence_shell(
    run_id: str,
    session_id: str | None = None,
) -> IntelligenceShellProjectionResponse:
    """Return a compact current cached move without starting cold intelligence."""

    try:
        bundle = peek_cached_run_intelligence(run_id, session_id=session_id)
        if bundle is None:
            return IntelligenceShellProjectionResponse(
                schema_version="p19.intelligence-shell.v1",
                run_id=run_id,
                session_id=session_id,
                status="not_built",
                recovery=(
                    "Open Smart Engineer when you want to assemble the full exact-scope "
                    "briefing. Run open remains fast and does not precompute it."
                ),
            )
        report = bundle.report
        if report.run_id != run_id or report.session_id != session_id:
            raise ValueError("cached intelligence does not match the requested scope")
        overview = RaceLabRepository().get_overview(run_id)
        setup_snapshot = overview.setup_snapshot if overview is not None else None
        identity = intelligence_snapshot_identity(
            report.reasoning_snapshot,
            run_id=run_id,
            setup_snapshot=setup_snapshot,
        )
        move = to_public_next_trustworthy_move(report)
        navigation_move = (
            move if move is not None and move.authority == "navigation_only" else None
        )
        return IntelligenceShellProjectionResponse(
            schema_version="p19.intelligence-shell.v1",
            run_id=run_id,
            session_id=session_id,
            status="ready",
            reasoning_snapshot_sha256=identity.reasoning_snapshot_sha256,
            setup_id=identity.setup_id,
            setup_snapshot_sha256=identity.setup_snapshot_sha256,
            next_trustworthy_move=navigation_move,
            recovery=(
                "Open the projected supporting view. Setup authority remains in the "
                "exact controlled-test ribbon."
                if navigation_move is not None
                else "No navigation-only move is available for this exact scope."
            ),
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/{run_id}/intelligence", response_model=RunIntelligenceResponse)
def get_run_intelligence(
    run_id: str,
    session_id: str | None = None,
    refresh: Annotated[str | None, Query(max_length=1024)] = None,
) -> RunIntelligenceResponse:
    del refresh  # Compatibility-only; never participates in semantic identity.
    try:
        bundle = build_run_intelligence(run_id, session_id=session_id)
        try:
            vehicle_systems = _vehicle_systems_projection(bundle.report)
        except ValueError:
            # P26 is a read-only supplement. Its exact-build fail-closed state
            # must not erase the canonical P19 report or create authority.
            vehicle_systems = None
        overview = RaceLabRepository().get_overview(run_id)
        return to_public_intelligence_report(
            bundle.report,
            narrative_entries=bundle.narrative_entries,
            calibration=bundle.calibration,
            driver_profile=bundle.driver_profile,
            vehicle_systems=vehicle_systems,
            setup_snapshot=(overview.setup_snapshot if overview is not None else None),
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


def _vehicle_systems_projection(
    report: InternalIntelligenceReport,
) -> VehicleSystemsProjection:
    overview = RaceLabRepository().get_overview(report.run_id)
    return build_component_awareness(
        report,
        setup_snapshot=overview.setup_snapshot if overview is not None else None,
        runtime_identity=vehicle_systems_runtime_identity(report.run_id),
    )


@router.get("/{run_id}/vehicle-systems", response_model=VehicleSystemsProjection)
def get_run_vehicle_systems(
    run_id: str,
    session_id: str | None = None,
    refresh: Annotated[str | None, Query(max_length=1024)] = None,
) -> VehicleSystemsProjection:
    """Return component cognition as a read-only projection of P19/P20 truth."""
    del refresh
    try:
        bundle = build_run_intelligence(run_id, session_id=session_id)
        return _vehicle_systems_projection(bundle.report)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/{run_id}/vehicle-systems/components/{component_id}", response_model=ComponentInspectionResponse)
def get_run_vehicle_component(
    run_id: str,
    component_id: str,
    session_id: str | None = None,
    refresh: Annotated[str | None, Query(max_length=1024)] = None,
) -> ComponentInspectionResponse:
    """Inspect one sourced component, its interactions, and exact-run state."""
    del refresh
    try:
        bundle = build_run_intelligence(run_id, session_id=session_id)
        return inspect_component(component_id, _vehicle_systems_projection(bundle.report))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/{run_id}/vehicle-systems/controls/{control_key}/trace", response_model=ControlMechanismTraceResponse)
def get_vehicle_control_trace(run_id: str, control_key: str) -> ControlMechanismTraceResponse:
    """Trace only source-declared expectation edges; never infer a runtime cause."""
    try:
        if RaceLabRepository().get_overview(run_id) is None:
            raise ValueError(f"Run not found: {run_id}")
        runtime_identity = vehicle_systems_runtime_identity(run_id)
        graph = compile_vehicle_systems_graph()
        edges = trace_control_mechanism(control_key)
        trace_node_ids = {
            node_id
            for edge in edges
            for node_id in (edge.source_node_id, edge.target_node_id)
        }
        return ControlMechanismTraceResponse(
            run_id=run_id,
            control_key=control_key,
            graph_version=graph.graph_version,
            graph_content_sha256=graph.content_sha256,
            runtime_identity=runtime_identity,
            nodes=tuple(node for node in graph.nodes if node.node_id in trace_node_ids),
            edges=edges,
        )
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
    """Verify one acquisition cohort while keeping its outcome client-attested."""
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
    if contract.session_id is None:
        if attempt_run_id != contract.run_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A run-scoped measurement contract cannot accept an attempt from "
                    "another run. Rebuild the mission in an explicit session scope."
                ),
            )
    else:
        mission_session = get_racelab_session(contract.session_id)
        current_session_run_ids = (
            tuple(sorted(set(mission_session.run_ids)))
            if mission_session is not None
            else ()
        )
        if (
            current_session_run_ids != contract.session_run_ids
            or attempt_run_id not in contract.session_run_ids
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "The attempt run is outside the immutable mission session scope, "
                    "or that session's run membership changed."
                ),
            )
    overview = RaceLabRepository().get_overview(attempt_run_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {attempt_run_id}")
    attempt_setup = overview.setup_snapshot
    try:
        attempt_setup_sha256 = setup_policy_fingerprint(attempt_setup)
    except (TypeError, ValueError):
        attempt_setup_sha256 = None
    if (
        attempt_setup is None
        or attempt_setup_sha256 is None
        or attempt_setup_sha256 != contract.setup_sha256
    ):
        raise HTTPException(
            status_code=409,
            detail="The attempt run does not preserve the mission's exact material setup.",
        )
    try:
        capability = build_telemetry_capability_payload(
            attempt_run_id,
            expected_source_file_sha256=overview.session.file_hash,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="The attempt run telemetry ownership could not be verified.",
        ) from exc
    if capability.get("compatibility_fingerprint") != contract.compatibility_fingerprint:
        raise HTTPException(
            status_code=409,
            detail="The attempt run car, track, build, or schema identity changed.",
        )
    available_channels: set[str] = set()
    channel_entries = capability.get("channels", ())
    if not isinstance(channel_entries, list):
        raise HTTPException(
            status_code=409,
            detail="The attempt run channel manifest is malformed.",
        )
    for entry in channel_entries:
        if not isinstance(entry, dict):
            continue
        try:
            valid_record_count = int(entry.get("valid_record_count") or 0)
        except (TypeError, ValueError):
            continue
        if (
            entry.get("archive_status") != "cached"
            or entry.get("health_status") != "healthy"
            or valid_record_count < 1
        ):
            continue
        available_channels.update(
            channel_id
            for channel_id in (entry.get("name"), entry.get("canonical_name"))
            if isinstance(channel_id, str) and channel_id
        )
    declared_observed_channels = set(request.observed_channels)
    unavailable_declared_channels = declared_observed_channels - available_channels
    if unavailable_declared_channels:
        raise HTTPException(
            status_code=409,
            detail=(
                "The attempt declares channels that are not usable in its verified archive: "
                + ", ".join(sorted(unavailable_declared_channels))
                + "."
            ),
        )
    if request.outcome in {"completed_clean", "no_signal"}:
        missing_required_channels = set(contract.required_channels) - available_channels
        undeclared_required_channels = (
            set(contract.required_channels) - declared_observed_channels
        )
        if missing_required_channels or undeclared_required_channels:
            missing = sorted(missing_required_channels | undeclared_required_channels)
            raise HTTPException(
                status_code=409,
                detail=(
                    "A clean or no-signal outcome requires every producer-owned mission "
                    "channel to be verified and declared: "
                    + ", ".join(missing)
                    + "."
                ),
            )
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
    if request.outcome in {"completed_clean", "no_signal"}:
        try:
            attempt_bundle = (
                bundle
                if attempt_run_id == run_id
                else build_run_intelligence(
                    attempt_run_id,
                    session_id=request.session_id,
                )
            )
            attempt_report = attempt_bundle.report
            report_eligible_ids = set(
                attempt_report.data_quality.eligible_lap_ids
            )
            context_by_lap = {
                context.lap_number: context
                for context in attempt_report.lap_context.contexts
            }
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The declared mission cohort could not be verified against "
                    "its exact P19 lap and context report."
                ),
            ) from exc
        context_cleared_ids = {
            lap_id
            for lap_id in report_eligible_ids
            if (
                (context := context_by_lap.get(int(lap_id.rsplit(":", 1)[1])))
                is not None
                and mission_lap_context_is_clear(context)
            )
        }
        if not set(supplied_laps).issubset(context_cleared_ids):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Mission completion requires every supplied lap to remain "
                    "eligible and context-cleared in its exact P19 report."
                ),
            )
        _verify_position_aligned_measurement_cohort(
            attempt_run_id,
            supplied_laps,
            tuple(contract.required_channels),
        )
    try:
        attempt = MeasurementAttempt(
            attempt_id=f"measurement-attempt:{uuid.uuid4().hex}",
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            run_id=attempt_run_id,
            setup_id=attempt_setup.setup_id,
            setup_sha256=attempt_setup_sha256,
            compatibility_fingerprint=contract.compatibility_fingerprint,
            outcome_authority="client_attested",
            collection_authority="server_verified",
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
        outcome_authority="client_attested",
        collection_authority="server_verified",
        counts_toward_mission_completion=attempt.counts_toward_mission_completion,
        counts_toward_stop_testing=False,
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
    try:
        persisted_case = EngineeringCaseRepository().current_for_scope(
            run_id, request.session_id
        )
        if persisted_case is None:
            raise ValueError(
                "Open the current Engineering Case before asking Smart Engineer."
            )
        if (
            persisted_case.case_id != request.case_id
            or persisted_case.case_sha256 != request.case_sha256
        ):
            raise ValueError(
                "Smart Engineer question is stale for the current Engineering Case revision."
            )
        workspace = build_crew_chief_workspace(
            run_id,
            session_id=request.session_id,
            objective=EngineeringObjective(persisted_case.case.objective_id),
        )
        if workspace.engineering_case.case_sha256 != request.case_sha256:
            raise ValueError(
                "Engineering Case changed while Smart Engineer was binding evidence."
            )
    except (EngineeringCaseIntegrityError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    case_answer = answer_engineering_case_question(request.question, workspace)
    if case_answer is not None:
        snapshot_identity = intelligence_snapshot_identity(
            bundle.report.reasoning_snapshot,
            run_id=run_id,
            setup_snapshot=(overview.setup_snapshot if overview is not None else None),
        )
        action_authorized = (
            case_answer.action_authorized
            and workspace.engineering_case.mission.setup_authorized
            and workspace.terminal_decision.authority == "p19_projection_only"
        )
        return IntelligenceQueryResponse(
            schema_version="p3544.engineering-case-query.v1",
            run_id=run_id,
            session_id=request.session_id,
            case_id=request.case_id,
            case_sha256=request.case_sha256,
            reasoning_snapshot_sha256=snapshot_identity.reasoning_snapshot_sha256,
            setup_id=snapshot_identity.setup_id,
            setup_snapshot_sha256=snapshot_identity.setup_snapshot_sha256,
            scope_run_ids=list(bundle.calibration.scope_run_ids),
            selected_lap=request.selected_lap,
            status="ready",
            question=request.question,
            headline=case_answer.headline,
            answer=case_answer.answer,
            interpreted_lap_number=request.selected_lap,
            interpreted_window_start_lap=request.selected_window_start_lap,
            interpreted_window_end_lap=request.selected_window_end_lap,
            interpreted_window_representative_lap=(
                request.selected_window_representative_lap
            ),
            action_authorized=action_authorized,
            action_source_event_ids=(
                list(workspace.terminal_decision.source_event_ids)
                if action_authorized
                else []
            ),
            source_artifact_ids=list(case_answer.source_artifact_ids),
            authority_ceiling=case_answer.authority_ceiling,
            evidence_state=(
                EvidenceState.CONTROLLED_TEST_EFFECT
                if action_authorized
                else EvidenceState.CALCULATED
                if case_answer.source_artifact_ids
                else EvidenceState.NEEDS_CONFIRMATION
            ),
            blocker_reasons=list(case_answer.blocker_reasons),
            follow_up_questions=list(bundle.report.suggested_questions),
        )
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
    try:
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
            vehicle_setup_snapshot=(
                overview.setup_snapshot if overview is not None else None
            ),
            vehicle_runtime_identity_factory=(
                (lambda: vehicle_systems_runtime_identity(run_id))
                if overview is not None
                else None
            ),
            vehicle_history_scope_run_ids=tuple(bundle.calibration.scope_run_ids),
            presentation_mode=request.presentation_mode or "learning",
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
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
            ).encode()
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
                    "track_region_id": _canonical_public_track_region_id(location),
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
        setup_snapshot=(overview.setup_snapshot if overview is not None else None),
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
    snapshot_identity = intelligence_snapshot_identity(
        bundle.report.reasoning_snapshot,
        run_id=run_id,
        setup_snapshot=(overview.setup_snapshot if overview is not None else None),
    )
    return IntelligenceQueryResponse(
        schema_version="p3544.engineering-case-query.v1",
        run_id=run_id,
        session_id=request.session_id,
        case_id=request.case_id,
        case_sha256=request.case_sha256,
        reasoning_snapshot_sha256=snapshot_identity.reasoning_snapshot_sha256,
        setup_id=snapshot_identity.setup_id,
        setup_snapshot_sha256=snapshot_identity.setup_snapshot_sha256,
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
        interpreted_component_id=result.interpreted_component_id,
        interpreted_track_region_id=getattr(result, "interpreted_track_region_id", None),
        interpreted_track_region_label=getattr(result, "interpreted_track_region_label", None),
        clarification_required=result.clarification_required,
        action_authorized=action_authorized,
        action_source_event_ids=(
            list(result.action_source_event_ids) if action_authorized else []
        ),
        source_artifact_ids=list(
            dict.fromkeys(
                item.event_id or item.citation_id for item in result.citations
            )
        ),
        authority_ceiling=(
            "p19_exact_mirror" if action_authorized else "evidence_only"
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
                    (
                        "The query action did not exactly match the current controlled-test "
                        "instruction and source evidence."
                    ),
                )
                if action_binding_withheld
                else ()
            ),
        ],
        follow_up_questions=list(bundle.report.suggested_questions),
    )


__all__ = ["router"]
