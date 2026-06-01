from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.routes_runs import repository
from api.schemas import PlatformEventItem
from racelab_engine.analysis.platform_events import detect_platform_events
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.services.import_service import csv_path, default_data_dir, parquet_path, read_telemetry_rows

router = APIRouter(prefix="/api/runs", tags=["events"])


@dataclass
class _PlatformEventsCacheEntry:
    signature: tuple[str, int, int] | None
    payload: list[PlatformEventItem]
    last_access: float


_PLATFORM_EVENTS_CACHE: dict[tuple[str, int | None, str | None], _PlatformEventsCacheEntry] = {}
_PLATFORM_EVENTS_CACHE_LOCK = RLock()
_PLATFORM_EVENTS_CACHE_MAX = 64


def _source_signature(run_id: str) -> tuple[str, int, int] | None:
    data_root = default_data_dir()
    parquet = parquet_path(data_root, run_id)
    csv_file = csv_path(data_root, run_id)
    source = parquet if parquet.exists() else csv_file if csv_file.exists() else None
    if source is None:
        return None
    stat = source.stat()
    return str(Path(source).resolve()), stat.st_mtime_ns, stat.st_size


def _evict_platform_event_cache() -> None:
    if len(_PLATFORM_EVENTS_CACHE) <= _PLATFORM_EVENTS_CACHE_MAX:
        return
    oldest_key = min(_PLATFORM_EVENTS_CACHE.items(), key=lambda item: item[1].last_access)[0]
    _PLATFORM_EVENTS_CACHE.pop(oldest_key, None)


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

    cache_key = (run_id, lap, event_type)
    signature = _source_signature(run_id)
    with _PLATFORM_EVENTS_CACHE_LOCK:
        entry = _PLATFORM_EVENTS_CACHE.get(cache_key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            return entry.payload

    rows = read_telemetry_rows(run_id, lap=lap)
    if not rows:
        return []

    event_types = [event_type] if event_type else None
    events = detect_platform_events(rows, lap=lap, event_types=event_types)
    payload = [PlatformEventItem(**event.as_dict()) for event in events]
    with _PLATFORM_EVENTS_CACHE_LOCK:
        _PLATFORM_EVENTS_CACHE[cache_key] = _PlatformEventsCacheEntry(
            signature=signature,
            payload=payload,
            last_access=time.time(),
        )
        _evict_platform_event_cache()
    return payload
