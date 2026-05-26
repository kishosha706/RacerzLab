from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import aiofiles  # type: ignore[import-untyped]

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File

from api.schemas import CacheInfo, ImportIbtRequest, ImportIbtResponse
from racelab_engine.services.import_service import ImportService, default_data_dir

router = APIRouter(prefix="/api/imports", tags=["imports"])

IMPORTS_DIR = default_data_dir() / "imports" / "ibt"
os.makedirs(IMPORTS_DIR, exist_ok=True)


def _sanitize_filename(name: str) -> str:
    """Strip directory components and reject path traversal."""
    name = os.path.basename(name)
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Invalid filename.")
    name = re.sub(r'[^\w.\- ]', "_", name)
    return name


@router.post("/ibt")
async def import_ibt_file(request: Request) -> ImportIbtResponse:
    """Import an .ibt telemetry file.

    Primary path: multipart file upload (used by the UI).
    Secondary path: JSON {path: ...} (dev/local-only — not exposed in the UI).
    """
    content_type = request.headers.get("content-type", "").lower()

    if "multipart/form-data" in content_type or "application/octet-stream" in content_type:
        form = await request.form()
        raw_file = form.get("file")
        if raw_file is None or not isinstance(raw_file, UploadFile):
            raise HTTPException(400, "Missing file in upload.")
        file: UploadFile = raw_file
        filename = file.filename
        if filename is None or not filename.lower().endswith(".ibt"):
            raise HTTPException(400, "Unsupported file type. Please select an .ibt telemetry file.")
        safe_name = _sanitize_filename(filename)
        dest = IMPORTS_DIR / safe_name
        content = await file.read()
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        path_or_file = str(dest)
    elif "application/json" in content_type:
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
    else:
        raise HTTPException(400, "Unsupported Content-Type. Use multipart/form-data or application/json.")

    result, cache_result = ImportService().import_ibt_file(path_or_file)
    cache = None
    if cache_result is not None:
        cache = CacheInfo(
            path=str(cache_result.path),
            format=cache_result.format,
            used_fallback=cache_result.used_fallback,
        )
    return ImportIbtResponse(
        run_id=result.overview.run_id if result.overview is not None else None,
        status=result.status,
        cache=cache,
    )
