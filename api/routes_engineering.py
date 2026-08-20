from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.intelligence_adapter import to_public_intelligence_report
from api.schemas import DialInObjective, DialInPriority
from racelab_engine.analysis.active_reset_lab import ActiveResetLabResult, analyze_active_reset_lab
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.crew_chief import EngineeringObjective
from racelab_engine.services.crew_chief_service import build_crew_chief_workspace
from racelab_engine.services.controlled_workflow_service import (
    P19_WORKFLOW_AUTHORITY_BINDING_SCHEMA,
    attach_stage,
    cancel_workflow,
    create_workflow,
    persist_workflow_candidate,
    project_workflow_for_publication,
    record_scored_workflow_side_effects,
    score_workflow,
    validate_p19_workflow_origin,
    withhold_workflow_authority,
    workflow_authority_action_identity,
    workflow_scope_run_ids,
)
from racelab_engine.services.engineering_learning_service import (
    build_controlled_workflow_experience,
    build_p19_reasoning_memory,
    clear_learning_cache,
)
from racelab_engine.services.engineering_knowledge_service import (
    build_canonical_performance_opportunity_binding,
)
from racelab_engine.services.run_intelligence_service import (
    RunIntelligenceBundle,
    build_run_intelligence,
)
from racelab_engine.services.report_service import ReportService
from racelab_engine.services.session_service import get_session
from racelab_engine.storage.repository import RaceLabRepository
from racelab_engine.services.import_service import read_telemetry_manifest, read_telemetry_rows

router = APIRouter(prefix="/api/engineering", tags=["engineering"])


_P19_BINDING_SCHEMA = P19_WORKFLOW_AUTHORITY_BINDING_SCHEMA
_P19_AUTHORITY_BLOCKER = (
    "The controlled workflow is not bound to the current exact-session P19 reasoning "
    "snapshot. No setup target, Keep/Undo verdict, or stop-testing policy is available."
)

_CREW_OBJECTIVE_BY_DIAL_IN: dict[DialInObjective, EngineeringObjective] = {
    "race-pace": EngineeringObjective.RACE_LONG_RUN,
    "long-run": EngineeringObjective.RACE_LONG_RUN,
    "qualifying": EngineeringObjective.QUALIFYING_PEAK,
    "tire-conservation": EngineeringObjective.TIRE_CONSERVATION,
    "driver-confidence": EngineeringObjective.DRIVER_CONFIDENCE,
}


class WorkflowStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1, max_length=160)
    complaint: str = Field(min_length=1)
    selected_lap: int | None = Field(default=None, ge=1)
    lap_scope: Literal["run", "single_lap", "lap_window", "track_zone"] | None = None
    window_start_lap: int | None = Field(default=None, ge=1)
    window_end_lap: int | None = Field(default=None, ge=1)
    representative_lap: int | None = Field(default=None, ge=1)
    selected_zone_start_pct: float | None = Field(default=None, ge=0.0, lt=100.0)
    selected_zone_end_pct: float | None = Field(default=None, gt=0.0, le=100.0)
    selected_zone_label: str | None = Field(default=None, max_length=120)
    selected_phase: str | None = Field(default=None, max_length=64)
    objective: DialInObjective = "race-pace"
    priority: DialInPriority = "overall-pace"

    @model_validator(mode="after")
    def validate_lap_selection_scope(self) -> WorkflowStartRequest:
        if self.lap_scope is None:
            self.lap_scope = "single_lap" if self.selected_lap is not None else "run"
        if self.lap_scope == "lap_window":
            if None in (
                self.window_start_lap,
                self.window_end_lap,
                self.representative_lap,
                self.selected_lap,
            ):
                raise ValueError(
                    "Lap-window workflows require start, end, representative, and selected lap identities."
                )
            assert self.window_start_lap is not None
            assert self.window_end_lap is not None
            assert self.representative_lap is not None
            if not self.window_start_lap <= self.representative_lap <= self.window_end_lap:
                raise ValueError("The representative lap must fall inside the selected lap window.")
            if self.selected_lap != self.representative_lap:
                raise ValueError("The planner selected lap must equal the window representative lap.")
        elif any(
            value is not None
            for value in (
                self.window_start_lap,
                self.window_end_lap,
                self.representative_lap,
            )
        ):
            raise ValueError("Lap-window identities require lap_scope='lap_window'.")
        if self.lap_scope == "single_lap" and self.selected_lap is None:
            raise ValueError("Single-lap workflow scope requires selected_lap.")
        selected_zone = (self.selected_zone_start_pct, self.selected_zone_end_pct)
        if (selected_zone[0] is None) != (selected_zone[1] is None):
            raise ValueError("A selected track zone requires both start and end positions.")
        if (
            selected_zone[0] is not None
            and selected_zone[1] is not None
            and selected_zone[0] >= selected_zone[1]
        ):
            raise ValueError("A selected track zone must have a non-zero ordered window.")
        if self.lap_scope == "track_zone" and selected_zone[0] is None:
            raise ValueError("Track-zone workflow scope requires an exact physical window.")
        return self


class WorkflowStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)


class WorkflowReportResponse(BaseModel):
    workflow_id: str
    markdown: str


class ActiveResetLabRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    target_start_pct: float = Field(ge=0.0, lt=100.0)
    target_end_pct: float = Field(gt=0.0, le=100.0)


class ControlledWorkflowCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    stage_run_ids: dict[str, str]
    updated_at: datetime
    revision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _card_action_identity(workflow: ControlledWorkflow) -> dict[str, object]:
    return workflow_authority_action_identity(workflow)


def _derive_p19_report(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
    session_id: str,
    candidate: bool = False,
) -> tuple[RunIntelligenceBundle, object]:
    bundle = build_run_intelligence(
        workflow.source_run_id,
        session_id=session_id,
        db_path=repository.db_path,
        workflow_candidate=workflow if candidate else None,
    )
    overview = repository.get_overview(workflow.source_run_id)
    if overview is None:
        raise ValueError(f"Run not found: {workflow.source_run_id}")
    public = to_public_intelligence_report(
        bundle.report,
        setup_snapshot=overview.setup_snapshot,
    )
    return bundle, public


def _require_matching_p19_action(
    workflow: ControlledWorkflow,
    bundle: RunIntelligenceBundle,
    public: object,
) -> None:
    expected = _card_action_identity(workflow)
    action = public.briefing.action
    authority = bundle.report.reasoning_snapshot.authority
    observed = {
        "setup_effect_id": action.setup_effect_id,
        "experiment_factor_id": action.experiment_factor_id,
        "direction_sign": action.direction_sign,
        "control_key": action.control_key,
        "current_value": action.current_value,
        "proposed_value": action.proposed_value,
        "instruction": action.instruction,
        "source_event_ids": list(action.source_event_ids),
    }
    if (
        public.schema_version != "p19.run-intelligence.v1"
        or public.run_id != workflow.source_run_id
        or public.status != "ready"
        or public.decision_status != "ready"
        or public.setup_id is None
        or public.setup_snapshot_sha256 is None
        or action.kind != "controlled_test"
        or action.setup_authorized is not True
        or action.blocker_reasons
        or not authority.setup_authorized
        or authority.level != "controlled_setup"
        or authority.control_key != action.control_key
        or tuple(authority.source_event_ids) != tuple(action.source_event_ids)
        or observed != expected
    ):
        raise ValueError(
            "The current exact-session P19 report did not authorize this workflow target."
        )


def _binding_for_authorized_candidate(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
    session_id: str,
    bundle: RunIntelligenceBundle,
    public: object,
) -> dict[str, object]:
    session = get_session(session_id, db_path=repository.db_path)
    overview = repository.get_overview(workflow.source_run_id)
    if session is None or overview is None or workflow.source_run_id not in session.run_ids:
        raise ValueError("The workflow run is not owned by the exact requested session.")
    if len(session.run_ids) != len(set(session.run_ids)):
        raise ValueError("The requested session has ambiguous run membership.")
    manifest = read_telemetry_manifest(workflow.source_run_id)
    compatibility_fingerprint = str(manifest.get("compatibility_fingerprint") or "")
    if re.fullmatch(r"[0-9a-f]{64}", compatibility_fingerprint) is None:
        raise ValueError("The workflow source build identity is unavailable.")
    setup = overview.setup_snapshot
    if setup is None or setup.setup_id != public.setup_id:
        raise ValueError("The workflow source setup identity is unavailable or changed.")
    result = {
        "schema_version": _P19_BINDING_SCHEMA,
        "workflow_id": workflow.workflow_id,
        "run_id": workflow.source_run_id,
        "session_id": session_id,
        "session_run_ids": list(session.run_ids),
        "setup_id": public.setup_id,
        "setup_snapshot_sha256": public.setup_snapshot_sha256,
        "source_file_sha256": overview.session.file_hash,
        "compatibility_fingerprint": compatibility_fingerprint,
        "compatibility_identity_sha256": canonical_json_sha256(
            manifest.get("compatibility_identity") or {}
        ),
        "plan_binding_sha256": workflow.reproduction_snapshot.get(
            "plan_binding_sha256"
        ),
        "authority_action_sha256": canonical_json_sha256(
            _card_action_identity(workflow)
        ),
        "eligible_lap_ids": list(bundle.report.data_quality.eligible_lap_ids),
        "source_event_ids": list(
            bundle.report.reasoning_snapshot.authority.source_event_ids
        ),
        "reasoning_snapshot_sha256": public.reasoning_snapshot_sha256,
        "bound_at": datetime.now(UTC).isoformat(),
    }
    performance_binding = workflow.reproduction_snapshot.get(
        "p352_performance_opportunity_binding"
    )
    if isinstance(performance_binding, dict):
        result["p352_performance_opportunity_binding_sha256"] = (
            performance_binding.get("binding_sha256")
        )
    return result


def _validate_origin_binding(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
) -> dict[str, object]:
    try:
        return validate_p19_workflow_origin(workflow, repository=repository)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ValueError(_P19_AUTHORITY_BLOCKER) from exc


def _require_current_p19_authority(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
) -> tuple[RunIntelligenceBundle, object]:
    binding = _validate_origin_binding(workflow, repository=repository)
    bundle, public = _derive_p19_report(
        workflow,
        repository=repository,
        session_id=str(binding["session_id"]),
    )
    _require_matching_p19_action(workflow, bundle, public)
    if (
        binding.get("eligible_lap_ids")
        != list(bundle.report.data_quality.eligible_lap_ids)
        or binding.get("source_event_ids")
        != list(bundle.report.reasoning_snapshot.authority.source_event_ids)
    ):
        raise ValueError(_P19_AUTHORITY_BLOCKER)
    return bundle, public


def _require_scored_p19_outcome(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
    transient_candidate: bool = False,
) -> tuple[RunIntelligenceBundle, object]:
    binding = _validate_origin_binding(workflow, repository=repository)
    if workflow.status != "scored" or workflow.quality is None:
        raise ValueError("The workflow has no complete controlled outcome.")
    bundle, public = _derive_p19_report(
        workflow,
        repository=repository,
        session_id=str(binding["session_id"]),
        candidate=transient_candidate,
    )
    outcomes = [
        outcome
        for outcome in bundle.report.reasoning_snapshot.controlled_outcomes
        if outcome.workflow_id == workflow.workflow_id
    ]
    if (
        len(outcomes) != 1
        or outcomes[0].policy.verdict != workflow.quality.verdict
        or outcomes[0].control_response.control_key
        != workflow.packet.primary_test.control_key
    ):
        raise ValueError(
            "The current exact-session P19 snapshot did not validate this workflow verdict."
        )
    return bundle, public


def _project_p19_bound_workflow(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
) -> ControlledWorkflow:
    try:
        if workflow.status == "scored":
            _require_scored_p19_outcome(workflow, repository=repository)
        elif workflow.status == "cancelled":
            raise ValueError(_P19_AUTHORITY_BLOCKER)
        else:
            _require_current_p19_authority(workflow, repository=repository)
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return withhold_workflow_authority(workflow, _P19_AUTHORITY_BLOCKER)
    return project_workflow_for_publication(workflow, repository=repository)


def build_authorized_workflow_candidate(
    request: WorkflowStartRequest,
    *,
    repository: RaceLabRepository,
) -> ControlledWorkflow:
    """Build and bind one candidate without persisting it."""

    candidate = create_workflow(
        request.run_id,
        request.complaint,
        selected_lap=request.selected_lap,
        lap_scope=request.lap_scope,
        window_start_lap=request.window_start_lap,
        window_end_lap=request.window_end_lap,
        representative_lap=request.representative_lap,
        selected_zone_start_pct=request.selected_zone_start_pct,
        selected_zone_end_pct=request.selected_zone_end_pct,
        selected_zone_label=request.selected_zone_label,
        selected_phase=request.selected_phase,
        objective=request.objective,
        priority=request.priority,
        repository=repository,
        persist=False,
    )
    bundle, public = _derive_p19_report(
        candidate,
        repository=repository,
        session_id=request.session_id,
        candidate=True,
    )
    _require_matching_p19_action(candidate, bundle, public)
    workspace = build_crew_chief_workspace(
        request.run_id,
        session_id=request.session_id,
        objective=_CREW_OBJECTIVE_BY_DIAL_IN[request.objective],
        db_path=repository.db_path,
    )
    performance_binding = build_canonical_performance_opportunity_binding(
        p32=workspace.performance_intelligence,
        knowledge=workspace.engineering_knowledge,
        workflow_opportunity=candidate.packet.opportunity,
    )
    snapshot = dict(candidate.reproduction_snapshot)
    snapshot["p352_performance_opportunity_binding"] = (
        performance_binding.model_dump(mode="json")
    )
    candidate = candidate.model_copy(
        update={
            "reproduction_snapshot": snapshot,
            "p32_opportunity_id": performance_binding.p32_opportunity_id,
            "p32_projection_sha256": performance_binding.p32_projection_sha256,
            "engineering_knowledge_projection_sha256": (
                performance_binding.engineering_knowledge_projection_sha256
            ),
        }
    )
    snapshot = dict(candidate.reproduction_snapshot)
    snapshot["p19_authority_binding"] = _binding_for_authorized_candidate(
        candidate,
        repository=repository,
        session_id=request.session_id,
        bundle=bundle,
        public=public,
    )
    return candidate.model_copy(update={"reproduction_snapshot": snapshot})


@router.post("/workflows", response_model=ControlledWorkflow)
def start_workflow(request: WorkflowStartRequest) -> ControlledWorkflow:
    try:
        repository = RaceLabRepository()
        candidate = build_authorized_workflow_candidate(
            request, repository=repository
        )
        persisted = persist_workflow_candidate(candidate, repository=repository)
        return project_workflow_for_publication(persisted, repository=repository)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).casefold() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/workflows", response_model=list[ControlledWorkflow])
def list_workflows(
    session_id: str,
    run_id: str,
    active_only: bool = False,
) -> list[ControlledWorkflow]:
    repository = RaceLabRepository()
    session = get_session(session_id)
    if session is None or run_id not in session.run_ids:
        raise HTTPException(
            status_code=422,
            detail="Controlled-workflow catalog requires exact current session/run membership.",
        )
    workflows, blockers = repository.list_controlled_workflow_catalog_for_run_scope(
        tuple(session.run_ids)
    )
    if blockers:
        raise HTTPException(status_code=409, detail=" ".join(blockers))
    if active_only:
        workflows = [
            workflow for workflow in workflows
            if workflow.status not in {"scored", "cancelled"}
        ]
    return [
        _project_p19_bound_workflow(workflow, repository=repository)
        for workflow in workflows
    ]


@router.get("/workflows/catalog", response_model=list[ControlledWorkflowCatalogItem])
def list_workflow_catalog(
    session_id: str,
    run_id: str,
) -> list[ControlledWorkflowCatalogItem]:
    """Return bounded identity metadata without rebuilding P19 intelligence."""

    repository = RaceLabRepository()
    session = get_session(session_id)
    if session is None or run_id not in session.run_ids:
        raise HTTPException(
            status_code=422,
            detail="Controlled-workflow catalog requires exact current session/run membership.",
        )
    workflows, blockers = repository.list_controlled_workflow_catalog_for_run_scope(
        tuple(session.run_ids),
        scored_run_ids=(run_id,),
    )
    if blockers:
        raise HTTPException(status_code=409, detail=" ".join(blockers))
    return [
        ControlledWorkflowCatalogItem(
            workflow_id=workflow.workflow_id,
            status=workflow.status,
            source_run_id=workflow.source_run_id,
            stage_run_ids=workflow.stage_run_ids,
            updated_at=workflow.updated_at,
            revision_sha256=canonical_json_sha256(workflow),
        )
        for workflow in workflows
    ]


@router.get("/workflows/{workflow_id}", response_model=ControlledWorkflow)
def get_workflow(workflow_id: str) -> ControlledWorkflow:
    repository = RaceLabRepository()
    workflow = repository.get_controlled_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return _project_p19_bound_workflow(workflow, repository=repository)


@router.post("/workflows/{workflow_id}/cancel", response_model=ControlledWorkflow)
def cancel_controlled_workflow(workflow_id: str) -> ControlledWorkflow:
    try:
        repository = RaceLabRepository()
        cancelled = cancel_workflow(workflow_id, repository=repository)
        return withhold_workflow_authority(cancelled, _P19_AUTHORITY_BLOCKER)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/workflows/{workflow_id}/report", response_model=WorkflowReportResponse)
def get_workflow_report(workflow_id: str) -> WorkflowReportResponse:
    try:
        repository = RaceLabRepository()
        workflow = repository.get_controlled_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        if workflow.status == "scored":
            _require_scored_p19_outcome(workflow, repository=repository)
        else:
            _require_current_p19_authority(workflow, repository=repository)
        markdown = ReportService(repository.db_path).generate_workflow_markdown(workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if markdown is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return WorkflowReportResponse(workflow_id=workflow_id, markdown=markdown)


@router.post("/workflows/{workflow_id}/stages/{stage}", response_model=ControlledWorkflow)
def record_workflow_stage(
    workflow_id: str,
    stage: Literal["A", "B", "A2"],
    request: WorkflowStageRequest,
) -> ControlledWorkflow:
    try:
        repository = RaceLabRepository()
        workflow = repository.get_controlled_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        _require_current_p19_authority(workflow, repository=repository)
        updated = attach_stage(
            workflow_id,
            stage,
            request.run_id,
            repository=repository,
        )
        _require_current_p19_authority(updated, repository=repository)
        return project_workflow_for_publication(updated, repository=repository)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/active-reset-lab", response_model=ActiveResetLabResult)
def active_reset_lab(request: ActiveResetLabRequest) -> ActiveResetLabResult:
    if RaceLabRepository().get_overview(request.run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {request.run_id}")
    rows = read_telemetry_rows(request.run_id, columns=[
        "lap_dist_pct", "lap_dist_pct_100", "session_time", "SessionTime",
        "enter_exit_reset_state", "EnterExitReset", "reset_event",
        "active_reset_event", "reset_discontinuity", "on_pit_road", "OnPitRoad",
        "speed_mps", "car_distance_ahead_m", "car_distance_behind_m",
        "incident", "wreck", "slowdown", "invalid_speed",
        "is_on_track", "IsOnTrack", "player_incident_count",
        "player_driver_incident_count", "player_team_incident_count",
        "player_in_pit_stall", "player_tow_service_time_s", "repair_required",
        "pitstop_active", "pit_repair_remaining_s", "pit_optional_repair_remaining_s",
        "session_flags", "SessionFlags", "under_caution", "pace_mode_active", "pace_mode",
        "is_on_track", "IsOnTrack", "player_track_surface", "PlayerTrackSurface",
        "player_incident_count", "player_driver_incident_count", "player_team_incident_count",
        "PlayerCarMyIncidentCount", "PlayerCarDriverIncidentCount", "PlayerCarTeamIncidentCount",
        "under_caution", "pace_mode_active", "session_flags", "SessionFlags", "pace_mode", "PaceMode",
    ])
    try:
        return analyze_active_reset_lab(
            rows,
            target_start_pct=request.target_start_pct,
            target_end_pct=request.target_end_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workflows/{workflow_id}/score", response_model=ControlledWorkflow)
def score_controlled_workflow(workflow_id: str) -> ControlledWorkflow:
    try:
        repository = RaceLabRepository()
        workflow = repository.get_controlled_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        _require_current_p19_authority(workflow, repository=repository)
        scored = score_workflow(
            workflow_id,
            repository=repository,
            persist=False,
        )
        bundle, public = _require_scored_p19_outcome(
            scored,
            repository=repository,
            transient_candidate=True,
        )
        controlled_outcome = next(
            outcome
            for outcome in bundle.report.reasoning_snapshot.controlled_outcomes
            if outcome.workflow_id == scored.workflow_id
        )
        snapshot = dict(scored.reproduction_snapshot)
        snapshot["p19_outcome_binding"] = {
            "schema_version": _P19_BINDING_SCHEMA,
            "workflow_id": scored.workflow_id,
            "reasoning_snapshot_sha256": public.reasoning_snapshot_sha256,
            "policy_verdict": scored.quality.verdict if scored.quality else None,
            "controlled_outcome_sha256": canonical_json_sha256(controlled_outcome),
            "bound_at": datetime.now(UTC).isoformat(),
        }
        scored = scored.model_copy(update={"reproduction_snapshot": snapshot})
        closing_reasoning = build_p19_reasoning_memory(bundle.report)
        experience = build_controlled_workflow_experience(
            scored,
            controlled_outcome=controlled_outcome,
            closing_reasoning=closing_reasoning,
            p19_reasoning_snapshot_sha256=public.reasoning_snapshot_sha256,
            repository=repository,
        )
        scored = repository.save_scored_workflow_with_experience_if_scope_exclusive(
            scored,
            workflow_scope_run_ids(scored, repository=repository),
            experience,
        )
        clear_learning_cache()
        record_scored_workflow_side_effects(scored, repository=repository)
        return project_workflow_for_publication(scored, repository=repository)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
