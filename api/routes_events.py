from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from api.routes_runs import repository
from api.schemas import PlatformEventItem
from racelab_engine.analysis.platform_events import detect_platform_events
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.services.import_service import read_telemetry_rows

router = APIRouter(prefix="/api/runs", tags=["events"])


@router.get("/{run_id}/events")
def get_events(run_id: str, lap: Optional[int] = None, type: Optional[str] = None) -> list[TelemetryEvent]:
    return repository().get_events(run_id, lap=lap, event_type=type)


@router.get("/{run_id}/platform-events", response_model=list[PlatformEventItem])
def get_platform_events(
    run_id: str,
    lap: Optional[int] = None,
    event_type: Optional[str] = None,
) -> list[PlatformEventItem]:
    if repository().get_session(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    rows = read_telemetry_rows(run_id)
    if not rows:
        return []

    event_types = [event_type] if event_type else None
    events = detect_platform_events(rows, lap=lap, event_types=event_types)
    return [PlatformEventItem(**event.as_dict()) for event in events]
