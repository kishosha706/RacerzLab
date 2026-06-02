from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile

from api.routes_runs import repository
from racelab_engine.analysis.platform_events import PLATFORM_EVENT_COLUMNS
from racelab_engine.services.track_map_service import (
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
        if name := getattr(session, "track_name", None) or getattr(session, "track_display_name", None):
            return name
    return ""


# ── import ────────────────────────────────────────────────────

@router.post("/imports/mt2")
async def import_mt2_endpoint(request: Request) -> dict:
    """Import an .mt2 track map file.

    Primary path: multipart file upload (used by the browser UI).
    Secondary path: JSON {path: ...} (used by Tauri native picker).
    """
    content_type = request.headers.get("content-type", "").lower()

    if "multipart/form-data" in content_type:
        # Multipart upload path
        form = await request.form()
        raw_file = form.get("file")
        if raw_file is None or not isinstance(raw_file, StarletteUploadFile):
            raise HTTPException(400, "Missing file in upload.")
        file: UploadFile | StarletteUploadFile = raw_file
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

    if "application/json" in content_type:
        # JSON path import (Tauri native picker)
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes) if body_bytes else {}
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "Malformed JSON body.") from exc
        if not isinstance(body, dict):
            raise HTTPException(400, "JSON body must be an object.")
        path_or_file = body.get("path")
        if not path_or_file:
            raise HTTPException(400, "Missing 'path' in JSON body.")
        resolved = os.path.abspath(os.path.normpath(path_or_file))
        if not os.path.exists(resolved):
            raise HTTPException(400, f"Path does not exist: {resolved}")
        if os.path.isdir(resolved):
            raise HTTPException(400, "Path is a directory, not a file.")
        if not resolved.lower().endswith(".mt2"):
            raise HTTPException(400, "Path must point to an .mt2 file.")
        if ".." in path_or_file or path_or_file.startswith("~"):
            raise HTTPException(400, "Path traversal is not allowed.")
        try:
            from racelab_engine.services.track_map_service import import_mt2_file
            entry = import_mt2_file(Path(resolved))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            raise HTTPException(422, f"Failed to parse .mt2: {e}") from e
        return entry

    raise HTTPException(400, "Unsupported Content-Type. Use multipart/form-data or application/json.")


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
        rows = read_telemetry_rows(run_id, lap=lap, columns=PLATFORM_EVENT_COLUMNS)
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
