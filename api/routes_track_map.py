from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from api.routes_runs import repository
from racelab_engine.services.track_map_service import (
    import_mt2_file,
    import_mt2_folder,
    list_track_maps,
    get_track_map,
    find_best_map_for_run,
    build_track_map_package,
    save_and_import_mt2_upload,
)
router = APIRouter(prefix="/api", tags=["track-maps"])

MAX_MT2_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


class ImportMt2FolderRequest(BaseModel):
    folder_path: str


def _get_track_name(overview) -> str:
    """Safely extract track_name from a RunOverview."""
    session = getattr(overview, "session", None)
    if session is not None:
        name = getattr(session, "track_name", None) or getattr(session, "track_display_name", None)
        if name:
            return name
    return ""


# ── import ────────────────────────────────────────────────────

@router.post("/imports/mt2")
async def import_mt2_endpoint(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".mt2"):
        raise HTTPException(400, "Unsupported file type. Please select an .mt2 track map file.")
    safe_name = file.filename
    content = await file.read()
    if len(content) > MAX_MT2_SIZE_BYTES:
        raise HTTPException(413, f".mt2 file is too large. Maximum size is {MAX_MT2_SIZE_BYTES // (1024*1024)} MB.")
    try:
        entry = save_and_import_mt2_upload(safe_name, content)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(422, f"Failed to parse .mt2: {e}") from e
    return entry


@router.post("/imports/mt2-folder")
async def import_mt2_folder_endpoint(req: ImportMt2FolderRequest) -> dict:
    """Local/dev-only: import all .mt2 files from a local folder."""
    folder = req.folder_path.strip()
    if not folder:
        raise HTTPException(400, "folder_path must not be empty.")
    path = Path(folder).resolve()
    if not path.exists():
        raise HTTPException(400, f"Folder does not exist: {folder}")
    if not path.is_dir():
        raise HTTPException(400, f"Path is not a directory: {folder}")
    # Reject obvious traversal outside expected patterns
    if ".." in folder:
        raise HTTPException(400, "Path traversal not allowed.")
    try:
        entries = import_mt2_folder(path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(422, str(e)) from e
    return {"imported": len(entries), "entries": entries}


# ── query ─────────────────────────────────────────────────────

@router.get("/track-maps")
def list_track_maps_endpoint() -> list[dict]:
    return list_track_maps()


@router.get("/track-maps/{map_id}")
def get_track_map_endpoint(map_id: str) -> dict:
    tm = get_track_map(map_id)
    if tm is None:
        raise HTTPException(404, f"Track map not found: {map_id}")
    return tm.as_dict()


@router.get("/runs/{run_id}/track-map-match")
def run_track_map_match(run_id: str, preferred_map_id: str | None = None) -> dict:
    repo = repository()
    overview = repo.get_overview(run_id)
    if overview is None:
        raise HTTPException(404, f"Run not found: {run_id}")
    track_name = _get_track_name(overview)
    match = find_best_map_for_run(run_id, track_name, preferred_map_id=preferred_map_id)
    if preferred_map_id and match is None:
        raise HTTPException(404, f"Track map not found: {preferred_map_id}")
    return {"run_id": run_id, "track_name": track_name, "match": match}


@router.get("/runs/{run_id}/track-map-package")
def run_track_map_package(
    run_id: str,
    lap: int | None = None,
    target_zone_start_pct: float | None = None,
    target_zone_end_pct: float | None = None,
    preferred_map_id: str | None = None,
) -> dict:
    repo = repository()
    overview = repo.get_overview(run_id)
    if overview is None:
        raise HTTPException(404, f"Run not found: {run_id}")
    track_name = _get_track_name(overview)
    match = find_best_map_for_run(run_id, track_name, preferred_map_id=preferred_map_id)

    # If the user explicitly requested a map ID that doesn't exist, 404
    if preferred_map_id and match is None:
        raise HTTPException(404, f"Track map not found: {preferred_map_id}")

    map_id = match.get("map_id") if match else None
    if not map_id:
        return {
            "run_id": run_id, "lap": lap,
            "map": None, "match": match,
            "overlays": [], "sections": [], "markers": [],
            "target_zone": None,
            "warnings": ["No track map matched for this run."],
        }

    # Get platform events for overlay
    platform_events: list[dict] | None = None
    from contextlib import suppress
    with suppress(Exception):
        from racelab_engine.analysis.platform_events import detect_platform_events
        from racelab_engine.services.import_service import read_telemetry_rows
        rows = read_telemetry_rows(run_id)
        if rows and (all_events := detect_platform_events(rows, lap=lap)):
            platform_events = [e.as_dict() for e in all_events]

    pkg = build_track_map_package(
        map_id, run_id, lap=lap,
        platform_events=platform_events,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
    )
    pkg["match"] = match
    return pkg
