from __future__ import annotations

import logging
import os
import re
import time
import uuid
from pathlib import Path

import aiofiles  # type: ignore[import-untyped]

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.schemas import CacheInfo, ImportIbtRequest, ImportIbtResponse, TrackMapResolution
from racelab_engine.services.import_service import ImportService, default_data_dir

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/imports", tags=["imports"])

IMPORTS_DIR = default_data_dir() / "imports" / "ibt"
os.makedirs(IMPORTS_DIR, exist_ok=True)


def _get_request_id(request: Request) -> str:
    """Get or generate a correlation ID for this request."""
    req_id = request.headers.get("x-racerzlab-request-id", "")
    if not req_id:
        req_id = f"be_{uuid.uuid4().hex[:12]}"
    return req_id


def _sanitize_filename(name: str) -> str:
    """Strip directory components and reject path traversal."""
    name = os.path.basename(name)
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Invalid filename.")
    name = re.sub(r'[^\w.\- ]', "_", name)
    return name


class ScanTelemetryFolderRequest(BaseModel):
    folder_path: str


class TelemetryFileEntry(BaseModel):
    name: str
    path: str
    size_bytes: int
    modified_at: str


@router.post("/scan-telemetry-folder")
def scan_telemetry_folder(req: ScanTelemetryFolderRequest) -> dict:
    """Scan a local folder for .ibt telemetry files. Returns newest-first sorted list."""
    folder = req.folder_path.strip()
    if not folder:
        raise HTTPException(400, "folder_path must not be empty.")
    if ".." in folder:
        raise HTTPException(400, "Path traversal not allowed.")
    path = Path(folder).resolve()
    if not path.exists():
        raise HTTPException(400, f"Folder does not exist: {folder}")
    if not path.is_dir():
        raise HTTPException(400, f"Path is not a directory: {folder}")

    from datetime import datetime, timezone
    files: list[dict] = []
    for f in path.iterdir():
        if f.suffix.lower() != ".ibt":
            continue
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        files.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "modified_at": mtime.isoformat(),
        })
    files.sort(key=lambda x: x["modified_at"], reverse=True)
    return {"files": files, "folder": folder, "count": len(files)}


@router.post("/ibt")
async def import_ibt_file(request: Request) -> ImportIbtResponse:
    """Import an .ibt telemetry file.

    Primary path: multipart file upload (used by the UI).
    Secondary path: JSON {path: ...} (dev/local-only — not exposed in the UI).
    """
    req_id = _get_request_id(request)
    content_type = request.headers.get("content-type", "").lower()
    import_mode = "unknown"

    if "multipart/form-data" in content_type or "application/octet-stream" in content_type:
        import_mode = "multipart"
        _log.info("[%s] Import mode=%s content_type=%s", req_id, import_mode, content_type)
        form = await request.form()
        raw_file = form.get("file")
        if raw_file is None or not isinstance(raw_file, UploadFile):
            raise HTTPException(400, "Missing file in upload.")
        file: UploadFile = raw_file
        filename = file.filename
        if filename is None or not filename.lower().endswith(".ibt"):
            raise HTTPException(400, "Unsupported file type. Please select an .ibt telemetry file.")
        _log.info("[%s] Multipart file accepted: %s", req_id, filename)
        safe_name = _sanitize_filename(filename)
        dest = IMPORTS_DIR / safe_name
        content = await file.read()
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        path_or_file = str(dest)
    elif "application/json" in content_type:
        import_mode = "json_path"
        _log.info("[%s] Import mode=%s", req_id, import_mode)
        # DEV/LOCAL-ONLY: JSON path import is not exposed in the UI.
        # It exists for test fixtures and local debugging.
        body = await request.json()
        path_or_file = body.get("path")
        if not path_or_file:
            raise HTTPException(400, "Missing 'path' in JSON body.")
        resolved = os.path.abspath(os.path.normpath(path_or_file))
        # Safety checks
        if not os.path.exists(resolved):
            raise HTTPException(400, f"Path does not exist: {resolved}")
        if os.path.isdir(resolved):
            raise HTTPException(400, "Path is a directory, not a file.")
        if not resolved.lower().endswith(".ibt"):
            raise HTTPException(400, "Path must point to an .ibt file.")
        # Reject path traversal outside the intended scope
        if ".." in path_or_file or path_or_file.startswith("~"):
            raise HTTPException(400, "Path traversal is not allowed.")
        path_or_file = resolved
        _log.info("[%s] JSON path accepted: %s", req_id, path_or_file)
    else:
        _log.warning("[%s] Unsupported Content-Type received: '%s'", req_id, content_type)
        raise HTTPException(400, "Unsupported Content-Type. Use multipart/form-data or application/json.")

    # ── Import with timing (offloaded to threadpool) ─────────────
    _log.info("[%s] Starting import_service.import_ibt_file (dispatched to threadpool)", req_id)
    _log.info("[%s] Decoder stage: file_path=%s size=%s", req_id, path_or_file,
              os.path.getsize(path_or_file) if os.path.exists(path_or_file) else "N/A")
    t0 = time.time()
    import_service = ImportService()
    try:
        result, cache_result = await run_in_threadpool(import_service.import_ibt_file, path_or_file)
    except Exception as exc:
        _log.error("[%s] Import_service raised unhandled exception: %s", req_id, exc)
        raise HTTPException(500, detail=f"Internal import error: {exc}")
    elapsed = time.time() - t0
    run_id = result.overview.run_id if result.overview else None
    _log.info("[%s] Import_service finished in %.1f s: run_id=%s", req_id, elapsed, run_id)

    cache = None
    if cache_result is not None:
        cache = CacheInfo(
            path=str(cache_result.path),
            format=cache_result.format,
            used_fallback=cache_result.used_fallback,
        )

    # ── Auto-resolve track map (also offloaded — reads disk index) ──
    track_map_resolution: TrackMapResolution | None = None
    if result.overview is not None:
        try:
            from racelab_engine.services.track_map_service import find_best_map_for_run
            track_name = (
                result.overview.session.track_display_name
                or result.overview.session.track_name
                or ""
            )
            match = await run_in_threadpool(find_best_map_for_run, result.overview.run_id, track_name)
            if match:
                conf = match.get("match_confidence", "unknown")
                track_map_resolution = TrackMapResolution(
                    status="matched",
                    map_id=match.get("map_id"),
                    map_name=match.get("display_name"),
                    confidence=conf,
                    message=f"Matched {match.get('display_name', 'track map')} from local map index.",
                )
                _log.info("[%s] Track map matched: %s (confidence=%s)", req_id, match.get("display_name"), conf)
            else:
                track_map_resolution = TrackMapResolution(
                    status="missing",
                    message="No matching track map found in local index. Import a .mt2 file or choose a map manually.",
                )
                _log.info("[%s] Track map not found for track: %s", req_id, track_name)
        except Exception as exc:
            _log.warning("[%s] Track map resolution failed: %s", req_id, exc)
            track_map_resolution = TrackMapResolution(
                status="missing",
                message="Track map resolution unavailable.",
            )

    _log.info("[%s] Returning response: run_id=%s track_map=%s", req_id, run_id, track_map_resolution.status if track_map_resolution else "None")
    return ImportIbtResponse(
        run_id=run_id,
        status=result.status,
        cache=cache,
        track_map=track_map_resolution,
        analysis_status="ready",
    )
