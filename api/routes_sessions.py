from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.schemas import RunListItem
from racelab_engine.services.lap_service import build_lap_list_for_run
from racelab_engine.services.session_service import (
    add_run_to_session,
    archive_session,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    remove_run_from_session,
    set_last_opened,
    update_session,
)
from racelab_engine.storage.repository import RaceLabRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    name: str | None = None


class UpdateSessionRequest(BaseModel):
    name: str | None = None
    track_name: str | None = None
    car_name: str | None = None
    last_opened_run_id: str | None = None
    last_selected_lap: int | None = None
    last_workspace: str | None = None
    status: str | None = None


class AddRunRequest(BaseModel):
    run_id: str


# ── Session CRUD ────────────────────────────────────────────

@router.post("")
def create_session_endpoint(req: CreateSessionRequest) -> dict:
    session = create_session(name=req.name)
    return session.as_dict()


@router.get("")
def list_sessions_endpoint(include_archived: bool = False) -> list[dict]:
    sessions = list_sessions(include_archived=include_archived)
    return [s.as_dict() for s in sessions]


@router.get("/{session_id}")
def get_session_endpoint(session_id: str) -> dict:
    if not (session := get_session(session_id)):
        raise HTTPException(404, f"Session not found: {session_id}")
    return session.as_dict()


@router.patch("/{session_id}")
def update_session_endpoint(session_id: str, req: UpdateSessionRequest) -> dict:
    if not (session := update_session(
        session_id,
        name=req.name,
        track_name=req.track_name,
        car_name=req.car_name,
        last_opened_run_id=req.last_opened_run_id,
        last_selected_lap=req.last_selected_lap,
        last_workspace=req.last_workspace,
        status=req.status,
    )):
        raise HTTPException(404, f"Session not found: {session_id}")
    return session.as_dict()


@router.delete("/{session_id}")
def delete_session_endpoint(session_id: str) -> dict:
    """Delete a RaceLab session. Does NOT delete imported telemetry files."""
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(404, f"Session not found: {session_id}")
    return {"deleted": True, "session_id": session_id}


@router.post("/{session_id}/archive")
def archive_session_endpoint(session_id: str) -> dict:
    if not (session := archive_session(session_id)):
        raise HTTPException(404, f"Session not found: {session_id}")
    return session.as_dict()


# ── Run management ──────────────────────────────────────────

@router.post("/{session_id}/runs")
def add_run_endpoint(session_id: str, req: AddRunRequest) -> dict:
    if not (session := add_run_to_session(session_id, req.run_id)):
        raise HTTPException(404, f"Session not found: {session_id}")
    return session.as_dict()


@router.get("/{session_id}/runs", response_model=list[RunListItem])
def list_session_runs_endpoint(session_id: str) -> list[RunListItem]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session not found: {session_id}")
    repo = RaceLabRepository()
    items = [repo.get_run_list_item(run_id) for run_id in session.run_ids]
    return [RunListItem(**item) for item in items if item is not None]


@router.delete("/{session_id}/runs/{run_id}")
def remove_run_endpoint(session_id: str, run_id: str) -> dict:
    if not (session := remove_run_from_session(session_id, run_id)):
        raise HTTPException(404, f"Session not found: {session_id}")
    return session.as_dict()


# ── Lap list ────────────────────────────────────────────────

@router.get("/{session_id}/runs/{run_id}/laps")
def get_run_laps_endpoint(session_id: str, run_id: str) -> dict:
    """Get full lap list for a run within a session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session not found: {session_id}")
    repo = RaceLabRepository()
    return build_lap_list_for_run(run_id, repo)


# ── Standalone lap list (no session required) ───────────────

@router.get("/runs/{run_id}/laps")
def get_run_laps_standalone_endpoint(run_id: str) -> dict:
    """Get full lap list for a run without requiring a session."""
    repo = RaceLabRepository()
    return build_lap_list_for_run(run_id, repo)
