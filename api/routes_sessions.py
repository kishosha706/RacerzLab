from __future__ import annotations

from collections import Counter
import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.schemas import RunListItem
from racelab_engine.models.racelab_session import RaceLabSession
from racelab_engine.services.lap_service import build_lap_list_for_run
from racelab_engine.services.session_service import (
    add_run_to_session,
    archive_session,
    clear_session_intelligence_quarantine,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    remove_run_from_session,
    quarantine_session_intelligence_history,
    update_session,
)
from racelab_engine.storage.repository import RaceLabRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session_picker_payload(session: RaceLabSession, run_items: list[dict]) -> dict:
    """Add truthful, presentation-only run context to a session card."""
    payload = session.as_dict()
    returned_run_ids = [item.get("run_id") for item in run_items]
    if (
        len(returned_run_ids) != len(session.run_ids)
        or any(not isinstance(run_id, str) or not run_id for run_id in returned_run_ids)
        or len(set(returned_run_ids)) != len(returned_run_ids)
        or set(returned_run_ids) != set(session.run_ids)
    ):
        return payload

    def summarize(field: str, multiple_label: str) -> str | None:
        values = list(dict.fromkeys(
            str(item[field]).strip()
            for item in run_items
            if item.get(field) is not None and str(item[field]).strip()
        ))
        if len(values) == 1:
            return values[0]
        if len(values) > 1:
            return multiple_label
        return None

    if not payload.get("track_name"):
        payload["track_name"] = summarize("track_name", "Multiple tracks")
    if not payload.get("car_name"):
        payload["car_name"] = summarize("car_name", "Multiple cars")
    return payload


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


class QuarantineIntelligenceHistoryRequest(BaseModel):
    reason: str


# ── Session CRUD ────────────────────────────────────────────

@router.post("")
def create_session_endpoint(req: CreateSessionRequest) -> dict:
    session = create_session(name=req.name)
    return session.as_dict()


@router.get("")
def list_sessions_endpoint(include_archived: bool = False) -> list[dict]:
    sessions = list_sessions(include_archived=include_archived)
    repository = RaceLabRepository()
    all_run_ids = list(dict.fromkeys(
        run_id
        for session in sessions
        for run_id in session.run_ids
    ))
    try:
        all_run_items = repository.get_run_list_items(all_run_ids)
    except (OSError, RuntimeError, ValueError, sqlite3.Error):
        # Session selection is presentation-only. A damaged run summary must
        # not hide sessions or manufacture context for them.
        all_run_items = []
    returned_run_ids = [
        run_id
        for item in all_run_items
        if isinstance((run_id := item.get("run_id")), str) and run_id
    ]
    run_id_counts = Counter(returned_run_ids)
    run_items_by_id = {
        run_id: item
        for item in all_run_items
        if isinstance((run_id := item.get("run_id")), str) and run_id_counts[run_id] == 1
    }
    return [
        _session_picker_payload(
            session,
            [run_items_by_id[run_id] for run_id in session.run_ids if run_id in run_items_by_id],
        )
        for session in sessions
    ]


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


@router.post("/{session_id}/intelligence-quarantine")
def quarantine_intelligence_history_endpoint(
    session_id: str,
    request: QuarantineIntelligenceHistoryRequest,
) -> dict:
    try:
        quarantine_session_intelligence_history(session_id, request.reason)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"session_id": session_id, "quarantined": True}


@router.delete("/{session_id}/intelligence-quarantine")
def clear_intelligence_history_quarantine_endpoint(session_id: str) -> dict:
    try:
        cleared = clear_session_intelligence_quarantine(session_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"session_id": session_id, "cleared": cleared}


@router.get("/{session_id}/runs", response_model=list[RunListItem])
def list_session_runs_endpoint(session_id: str) -> list[RunListItem]:
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session not found: {session_id}")
    repo = RaceLabRepository()
    return [RunListItem(**item) for item in repo.get_run_list_items(session.run_ids)]


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
