from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from api.routes_runs import repository
from api.schemas import PlatformEventItem, PlatformEventsReport
from racelab_engine.analysis.platform_events import PLATFORM_EVENT_COLUMNS, detect_platform_events
from racelab_engine.analysis.lap_eligibility import lap_ineligibility_reasons, lap_is_eligible
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.services.import_service import _file_signature, csv_path, default_data_dir, parquet_path, read_telemetry_rows

router = APIRouter(prefix="/api/runs", tags=["events"])


@dataclass
class _PlatformEventsCacheEntry:
    signature: tuple[Any, ...] | None
    payload: list[PlatformEventItem]
    evidence_status: str
    blocker_reasons: list[str]
    last_access: float


_PLATFORM_EVENTS_CACHE: dict[tuple[str, int | None, str | None], _PlatformEventsCacheEntry] = {}
_PLATFORM_EVENTS_CACHE_LOCK = RLock()
_PLATFORM_EVENTS_CACHE_MAX = 64
def _source_signature(run_id: str) -> tuple[Any, ...] | None:
    data_root = default_data_dir()
    parquet = parquet_path(data_root, run_id)
    csv_file = csv_path(data_root, run_id)
    source = parquet if parquet.exists() else csv_file if csv_file.exists() else None
    if source is None:
        return None
    return _file_signature(Path(source))


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
    payload, _status, _blockers = _load_platform_events(run_id, lap=lap, event_type=event_type)
    return payload


def _load_platform_events(
    run_id: str,
    *,
    lap: Optional[int] = None,
    event_type: Optional[str] = None,
) -> tuple[list[PlatformEventItem], str, list[str]]:
    repo = repository()
    if repo.get_session(run_id) is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    laps = repo.get_laps(run_id)
    eligible_lap_numbers = {
        item.lap_number for item in laps
        if item.lap_number is not None and lap_is_eligible(item)
    }
    if lap is not None and lap not in eligible_lap_numbers:
        selected_lap = next((item for item in laps if item.lap_number == lap), None)
        reasons = lap_ineligibility_reasons(selected_lap) if selected_lap is not None else ["Lap not found"]
        return [], "unavailable", [
            f"Lap {lap} is not eligible for platform conclusions: {'; '.join(reasons)}."
        ]

    cache_key = (run_id, lap, event_type)
    signature = (_source_signature(run_id), tuple(sorted(eligible_lap_numbers)))
    with _PLATFORM_EVENTS_CACHE_LOCK:
        entry = _PLATFORM_EVENTS_CACHE.get(cache_key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            return entry.payload, entry.evidence_status, entry.blocker_reasons

    rows = read_telemetry_rows(run_id, lap=lap, columns=PLATFORM_EVENT_COLUMNS)
    if lap is None:
        rows = [
            row for row in rows
            if row.get("lap", row.get("lap_number")) in eligible_lap_numbers
        ]
    if not rows:
        payload: list[PlatformEventItem] = []
        evidence_status = "unavailable"
        blocker_reasons = ["No telemetry rows were available for the selected run and lap."]
    else:
        event_types = [event_type] if event_type else None
        events = detect_platform_events(rows, lap=lap, event_types=event_types)
        payload = [PlatformEventItem(**event.as_dict()) for event in events]
        if lap is not None and any(event.lap != lap for event in payload):
            payload = []
            evidence_status = "unavailable"
            blocker_reasons = [
                "Platform diagnostic evidence did not match the requested lap."
            ]
        else:
            usable_evidence_states = {"measured", "calculated", "estimated_proxy", "observed_correlation"}
            has_finding = any(
                event.diagnostic_state == "finding" and event.display_scope in {"actionable", "watch"}
                and event.evidence_state in usable_evidence_states
                for event in payload
            )
            has_clear_check = any(
                event.diagnostic_state == "clear_check" and event.evidence_state in usable_evidence_states
                for event in payload
            )
            if has_finding:
                evidence_status = "findings"
                blocker_reasons = []
            elif has_clear_check:
                evidence_status = "clear"
                blocker_reasons = []
            else:
                evidence_status = "unavailable"
                blocker_reasons = [
                    "No supported platform risk check had enough telemetry to produce a finding or a clear result."
                ]

    with _PLATFORM_EVENTS_CACHE_LOCK:
        _PLATFORM_EVENTS_CACHE[cache_key] = _PlatformEventsCacheEntry(
            signature=signature,
            payload=payload,
            evidence_status=evidence_status,
            blocker_reasons=blocker_reasons,
            last_access=time.time(),
        )
        _evict_platform_event_cache()
    return payload, evidence_status, blocker_reasons


@router.get("/{run_id}/platform-events-report", response_model=PlatformEventsReport)
def get_platform_events_report(
    run_id: str,
    lap: Optional[int] = None,
    event_type: Optional[str] = None,
) -> PlatformEventsReport:
    payload, evidence_status, blocker_reasons = _load_platform_events(
        run_id,
        lap=lap,
        event_type=event_type,
    )
    return PlatformEventsReport(
        run_id=run_id,
        lap=lap,
        evidence_status=evidence_status,
        events=payload,
        blocker_reasons=blocker_reasons,
    )
