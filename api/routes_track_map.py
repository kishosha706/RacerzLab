from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile

from api.routes_events import get_platform_events
from api.routes_runs import repository
from racelab_engine.services.track_map_service import (
    build_track_map_package,
    find_best_map_for_run,
    get_track_map,
    import_mt2_folder,
    list_track_maps,
    save_and_import_mt2_upload,
    validate_target_zone,
)

router = APIRouter(prefix="/api", tags=["track-maps"])

MAX_MT2_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


class ImportMt2FolderRequest(BaseModel):
    folder_path: str


def _get_track_name(overview) -> str:
    """Safely extract track_name from a RunOverview."""
    session = getattr(overview, "session", None)
    if session is not None and (
        name := getattr(session, "track_name", None)
        or getattr(session, "track_display_name", None)
    ):
        return name
    return ""


def _public_track_map_summary(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "map_id": entry.get("map_id"),
        "track_key": entry.get("track_key"),
        "layout_key": entry.get("layout_key"),
        "display_name": entry.get("display_name"),
        "points_count": entry.get("points_count"),
        "markers_count": entry.get("markers_count"),
        "sections_count": entry.get("sections_count"),
        "distance_ft": entry.get("distance_ft"),
        "warnings": entry.get("warnings", []),
        "status": entry.get("status"),
        "supported": entry.get("supported"),
        "partial": entry.get("partial"),
        "match_confidence": entry.get("match_confidence"),
        "match_score": entry.get("match_score"),
        "import_status": entry.get("import_status"),
    }


def _public_track_map_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_name": metadata.get("track_name"),
        "display_name": metadata.get("display_name"),
        "closed": metadata.get("closed"),
        "clockwise_flag": metadata.get("clockwise_flag"),
        "x_over": metadata.get("x_over"),
        "z_rotation_rad": metadata.get("z_rotation_rad"),
        "distance_m": metadata.get("distance_m"),
        "distance_ft": metadata.get("distance_ft"),
        "distance_miles": metadata.get("distance_miles"),
        "origin": metadata.get("origin"),
        "has_boundaries": metadata.get("has_boundaries"),
        "has_sections": metadata.get("has_sections"),
        "has_markers": metadata.get("has_markers"),
        "warnings": metadata.get("warnings", []),
    }


def _public_track_map_payload(
    track_map: dict[str, Any] | None,
    *,
    render_projection: bool = False,
) -> dict[str, Any] | None:
    if track_map is None:
        return None
    points = track_map.get("points", [])
    if render_projection:
        # The renderer needs geometry identity, position, distance, and kind.
        # Curvature/radius/section analysis remains server-side and would more
        # than double this frequently loaded package payload.
        points = [
            {
                key: point.get(key)
                for key in ("index", "x", "y", "x_m", "y_m", "distance_ft", "lap_pct", "kind")
            }
            for point in points
            if point.get("kind") in {"centerline", "unknown"}
        ]
    return {
        "map_id": track_map.get("map_id"),
        "metadata": _public_track_map_metadata(track_map.get("metadata", {})),
        "bounds": track_map.get("bounds"),
        "points": points,
        "markers": track_map.get("markers", []),
        "sections": track_map.get("sections", []),
        "status": track_map.get("status"),
        "supported": track_map.get("supported"),
        "partial": track_map.get("partial"),
        "warnings": track_map.get("warnings", []),
    }


def _public_track_map_package(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": package.get("run_id"),
        "lap": package.get("lap"),
        "map": _public_track_map_payload(package.get("map"), render_projection=True),
        "match": _public_track_map_summary(package.get("match")),
        "overlays": package.get("overlays", []),
        "sections": package.get("sections", []),
        "markers": package.get("markers", []),
        "turns": package.get("turns", []),
        "target_zone": package.get("target_zone"),
        "warnings": package.get("warnings", []),
    }


# ── import ────────────────────────────────────────────────────

@router.post("/imports/mt2")
async def import_mt2_endpoint(request: Request) -> dict:
    """Import a track map file.

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
            raise HTTPException(400, "Unsupported file type. Please select a track map file.")
        safe_name = file.filename
        content = await file.read()
        if len(content) > MAX_MT2_SIZE_BYTES:
            raise HTTPException(413, f"Track map file is too large. Maximum size is {MAX_MT2_SIZE_BYTES // (1024*1024)} MB.")
        try:
            entry = save_and_import_mt2_upload(safe_name, content)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            raise HTTPException(422, f"Failed to parse track map file: {e}") from e
        summary = _public_track_map_summary(entry)
        if summary is None:
            raise HTTPException(422, "Imported track map payload was empty.")
        return summary

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
            raise HTTPException(400, "Path must point to a track map file.")
        if ".." in path_or_file or path_or_file.startswith("~"):
            raise HTTPException(400, "Path traversal is not allowed.")
        try:
            from racelab_engine.services.track_map_service import import_mt2_file
            entry = import_mt2_file(Path(resolved))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:
            raise HTTPException(422, f"Failed to parse track map file: {e}") from e
        summary = _public_track_map_summary(entry)
        if summary is None:
            raise HTTPException(422, "Imported track map payload was empty.")
        return summary

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
    public_entries = [summary for entry in entries if (summary := _public_track_map_summary(entry)) is not None]
    return {"imported": len(entries), "entries": public_entries}


# ── query ─────────────────────────────────────────────────────

@router.get("/track-maps")
def list_track_maps_endpoint() -> list[dict]:
    return [summary for entry in list_track_maps() if (summary := _public_track_map_summary(entry)) is not None]


@router.get("/track-maps/{map_id}")
def get_track_map_endpoint(map_id: str) -> JSONResponse:
    tm = get_track_map(map_id)
    if tm is None:
        raise HTTPException(404, f"Track map not found: {map_id}")
    payload = _public_track_map_payload(tm.as_dict())
    if payload is None:
        raise HTTPException(500, f"Track map payload unavailable: {map_id}")
    return JSONResponse(content=payload)


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
    return {"run_id": run_id, "track_name": track_name, "match": _public_track_map_summary(match)}


@router.get("/runs/{run_id}/track-map-package")
def run_track_map_package(
    run_id: str,
    lap: int | None = None,
    target_zone_start_pct: float | None = None,
    target_zone_end_pct: float | None = None,
    preferred_map_id: str | None = None,
) -> JSONResponse:
    try:
        validate_target_zone(target_zone_start_pct, target_zone_end_pct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        return JSONResponse(content=_public_track_map_package({
            "run_id": run_id, "lap": lap,
            "map": None, "match": match,
            "overlays": [], "sections": [], "markers": [], "turns": [],
            "target_zone": None,
            "warnings": ["No track map matched for this run."],
        }))

    # Get platform events for overlay
    platform_events: list[dict] | None = None
    overlay_warnings: list[str] = []
    try:
        if all_events := get_platform_events(run_id, lap=lap):
            platform_events = [event.model_dump(mode="json") for event in all_events]
    except Exception:  # noqa: BLE001 - an overlay failure must not hide map geometry
        overlay_warnings.append(
            "Platform-event overlay unavailable; map geometry remains available."
        )

    pkg = build_track_map_package(
        map_id, run_id, lap=lap,
        platform_events=platform_events,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
    )
    pkg["match"] = match
    pkg["warnings"] = [*pkg.get("warnings", []), *overlay_warnings]
    return JSONResponse(content=_public_track_map_package(pkg))
