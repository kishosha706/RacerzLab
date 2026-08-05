from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from api.schemas import ChannelCatalogItem, ChannelSummaryItem, DialInRequest, RunListItem, TraceResponse
from racelab_engine.knowledge.setup.dial_in_schema import DialInResponse
from racelab_engine.knowledge.setup.dial_in_service import build_dial_in_response
from racelab_engine.models.session import RunOverview
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import (
    build_channel_catalog,
    build_channel_summary,
    build_telemetry_capability_payload,
    build_trace_payload,
)
from racelab_engine.storage.repository import RaceLabRepository

router = APIRouter(prefix="/api/runs", tags=["runs"])


def repository() -> RaceLabRepository:
    return RaceLabRepository()


def get_run_or_404(run_id: str) -> RunOverview:
    overview = repository().get_overview(run_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return overview


@router.get("", response_model=list[RunListItem])
def list_runs() -> list[RunListItem]:
    return [RunListItem(**item) for item in repository().list_runs()]


@router.get("/{run_id}/overview", response_model=RunOverview)
def get_run_overview(run_id: str) -> RunOverview:
    return get_run_or_404(run_id)


@router.get("/{run_id}/setup", response_model=SetupSnapshot)
def get_setup(run_id: str) -> SetupSnapshot:
    setup = repository().get_setup_snapshot(run_id)
    if setup is None:
        raise HTTPException(status_code=404, detail=f"Setup snapshot not found for run: {run_id}")
    return setup


@router.post("/{run_id}/dial-in", response_model=DialInResponse, response_model_exclude_none=True)
def dial_in(run_id: str, request: DialInRequest) -> DialInResponse:
    get_run_or_404(run_id)
    try:
        return build_dial_in_response(
            run_id,
            request.complaint,
            car_family_override=request.car_family,
            track_family_override=request.track_family,
            baseline_run_id=request.baseline_run_id,
            test_run_id=request.test_run_id,
            package_archetype=request.package_archetype,
            selected_lap=request.selected_lap,
            selected_zone_start_pct=request.selected_zone_start_pct,
            selected_zone_end_pct=request.selected_zone_end_pct,
            selected_phase=request.selected_phase,
            objective=request.objective,
            priority=request.priority,
            limit=request.limit,
            include_debug_evidence=request.include_debug_evidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}/channels", response_model=list[ChannelCatalogItem])
def get_channels(run_id: str, summary: bool = False) -> list[ChannelCatalogItem]:
    if repository().get_session(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    if summary:
        return [ChannelCatalogItem(**item) for item in build_channel_summary(run_id)]
    return [ChannelCatalogItem(**item) for item in build_channel_catalog(run_id)]


@router.get("/{run_id}/channels/summary", response_model=list[ChannelSummaryItem])
def get_channels_summary(run_id: str) -> list[ChannelSummaryItem]:
    if repository().get_session(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return [ChannelSummaryItem(**item) for item in build_channel_summary(run_id)]


@router.get("/{run_id}/telemetry-capabilities", response_model=dict[str, Any])
def get_telemetry_capabilities(run_id: str) -> dict[str, Any]:
    if repository().get_session(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    manifest = build_telemetry_capability_payload(run_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Telemetry capability manifest not found for run: {run_id}")
    return manifest


@router.get("/{run_id}/trace", response_model=TraceResponse)
def get_trace(
    run_id: str,
    lap: Optional[int] = None,
    channels: Optional[str] = None,
    x: Optional[str] = None,
    downsample: str = "1",
    preserve_extrema: bool = False,
    resolution: Optional[str] = None,
    start_ft: Optional[float] = None,
    end_ft: Optional[float] = None,
) -> TraceResponse:
    repo = repository()
    overview = repo.get_overview(run_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    selected_channels = [item.strip() for item in channels.split(",") if item.strip()] if channels else None
    events = repo.get_events(run_id, lap=lap)
    effective_downsample = "1" if (resolution or "").lower() == "raw" else downsample
    effective_preserve = preserve_extrema or (isinstance(effective_downsample, str) and effective_downsample.lower() == "auto")
    payload = build_trace_payload(
        run_id,
        lap=lap,
        channels=selected_channels,
        downsample=effective_downsample,
        x_axis=x,
        preserve_extrema=effective_preserve,
        events=events,
        start_ft=start_ft,
        end_ft=end_ft,
        raw_resolution=(resolution or "").lower() == "raw",
        car_path=overview.session.car_path,
    )
    return TraceResponse(**payload)
