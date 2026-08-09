from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas import DialInObjective, DialInPriority
from racelab_engine.analysis.advanced_experimentation import (
    DesignRun,
    ExperimentHistorySummary,
    ExperimentUnlock,
    Factor,
    evaluate_experiment_unlock,
    fractional_factorial_design,
)
from racelab_engine.analysis.crew_chief_packet import (
    KaizenEvidencePacket,
)
from racelab_engine.analysis.active_reset_lab import ActiveResetLabResult, analyze_active_reset_lab
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.services.controlled_workflow_service import (
    attach_stage,
    build_server_kaizen_packet,
    cancel_workflow,
    create_workflow,
    project_kaizen_packet_for_publication,
    project_workflow_for_publication,
    score_workflow,
)
from racelab_engine.services.report_service import ReportService
from racelab_engine.storage.repository import RaceLabRepository
from racelab_engine.services.import_service import read_telemetry_rows

router = APIRouter(prefix="/api/engineering", tags=["engineering"])


def _reject_client_asserted_evidence() -> None:
    raise HTTPException(
        status_code=409,
        detail=(
            "Controlled engineering decisions require server-derived run, lap, setup, event, "
            "driver, context, and simulator-integrity evidence. Client-asserted evidence is not accepted."
        ),
    )


class ServerEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
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
    def validate_lap_selection_scope(self) -> ServerEvidenceRequest:
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


class WorkflowScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)


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


class ExperimentDesignRequest(BaseModel):
    history: ExperimentHistorySummary
    factors: list[Factor]


@router.post("/test-director/plan", response_model=KaizenEvidencePacket)
def plan_controlled_test(request: ServerEvidenceRequest) -> KaizenEvidencePacket:
    try:
        repository = RaceLabRepository()
        packet = build_server_kaizen_packet(
            request.run_id,
            request.complaint,
            selected_lap=request.selected_lap,
            selected_zone_start_pct=request.selected_zone_start_pct,
            selected_zone_end_pct=request.selected_zone_end_pct,
            selected_zone_label=request.selected_zone_label,
            selected_phase=request.selected_phase,
            objective=request.objective,
            priority=request.priority,
            repository=repository,
        )
        return project_kaizen_packet_for_publication(
            request.run_id,
            request.complaint,
            packet,
            repository=repository,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 409, detail=str(exc)) from exc


@router.post("/test-director/score", response_model=ControlledWorkflow)
def score_controlled_test(request: WorkflowScoreRequest) -> ControlledWorkflow:
    try:
        return score_workflow(request.workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/crew-chief/packet", response_model=KaizenEvidencePacket)
def kaizen_packet(request: ServerEvidenceRequest) -> KaizenEvidencePacket:
    return plan_controlled_test(request)


@router.post("/workflows", response_model=ControlledWorkflow)
def start_workflow(request: ServerEvidenceRequest) -> ControlledWorkflow:
    try:
        return create_workflow(
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/workflows", response_model=list[ControlledWorkflow])
def list_workflows(active_only: bool = True) -> list[ControlledWorkflow]:
    repository = RaceLabRepository()
    return [
        project_workflow_for_publication(workflow, repository=repository)
        for workflow in repository.list_controlled_workflows(active_only=active_only)
    ]


@router.get("/workflows/{workflow_id}", response_model=ControlledWorkflow)
def get_workflow(workflow_id: str) -> ControlledWorkflow:
    repository = RaceLabRepository()
    workflow = repository.get_controlled_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return project_workflow_for_publication(workflow, repository=repository)


@router.post("/workflows/{workflow_id}/cancel", response_model=ControlledWorkflow)
def cancel_controlled_workflow(workflow_id: str) -> ControlledWorkflow:
    try:
        cancelled = cancel_workflow(workflow_id)
        return project_workflow_for_publication(cancelled)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 409
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/workflows/{workflow_id}/report", response_model=WorkflowReportResponse)
def get_workflow_report(workflow_id: str) -> WorkflowReportResponse:
    try:
        markdown = ReportService().generate_workflow_markdown(workflow_id)
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
        return attach_stage(workflow_id, stage, request.run_id)
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


@router.post("/experimentation/unlock", response_model=ExperimentUnlock)
def experimentation_unlock(history: ExperimentHistorySummary) -> ExperimentUnlock:
    _reject_client_asserted_evidence()
    return evaluate_experiment_unlock(history)


@router.post("/experimentation/design", response_model=list[DesignRun])
def experimentation_design(request: ExperimentDesignRequest) -> list[DesignRun]:
    _reject_client_asserted_evidence()
    unlock = evaluate_experiment_unlock(request.history)
    if not unlock.unlocked:
        raise HTTPException(status_code=409, detail={"blockers": list(unlock.blockers)})
    return list(fractional_factorial_design(request.factors, unlock))
