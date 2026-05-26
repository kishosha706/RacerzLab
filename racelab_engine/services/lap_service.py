from __future__ import annotations

from typing import Any

from racelab_engine.models.lap import LapSummary
from racelab_engine.storage.repository import RaceLabRepository


def format_lap_time(seconds: float | None) -> str:
    """Format lap time as M:SS.sss or 0:SS.sss."""
    if seconds is None:
        return "--:--.---"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:06.3f}"


def compute_lap_delta(lap_time: float | None, reference_time: float | None) -> float | None:
    """Return delta in seconds. Positive = slower, Negative = faster."""
    if lap_time is None or reference_time is None:
        return None
    return lap_time - reference_time


def format_delta(delta_seconds: float | None) -> str:
    """Format delta as +0:00.246 or -0:00.118."""
    if delta_seconds is None:
        return ""
    sign = "+" if delta_seconds >= 0 else "-"
    abs_sec = abs(delta_seconds)
    minutes = int(abs_sec // 60)
    secs = abs_sec % 60
    return f"{sign}{minutes}:{secs:06.3f}"


def find_best_lap(laps: list[LapSummary]) -> LapSummary | None:
    """Return the fastest useful lap."""
    useful = [l for l in laps if l.is_useful and l.lap_time is not None]
    if not useful:
        return None
    return min(useful, key=lambda l: l.lap_time or 999999.0)


def useful_laps(laps: list[LapSummary]) -> list[LapSummary]:
    return [l for l in laps if l.is_useful]


def classify_lap_type(lap: LapSummary, all_laps: list[LapSummary]) -> str:
    """Classify a lap as out/timed/in/unknown based on position and coverage."""
    if not all_laps:
        return "unknown"

    # Find first and last useful/timed laps
    timed = [l for l in all_laps if l.is_useful and l.lap_time is not None]
    if not timed:
        return "unknown"

    first_timed = min(timed, key=lambda l: l.lap_number or 0)
    last_timed = max(timed, key=lambda l: l.lap_number or 0)

    lap_num = lap.lap_number or 0

    # Out lap: before first timed lap
    if lap_num < first_timed.lap_number:
        return "out"

    # In lap: after last timed lap
    if lap_num > last_timed.lap_number:
        return "in"

    # Timed lap: useful with lap time
    if lap.is_useful and lap.lap_time is not None:
        return "timed"

    # Partial/incomplete between timed laps
    if lap.pct_span is not None and lap.pct_span < 50.0:
        return "out" if lap_num <= first_timed.lap_number else "in"

    return "unknown"


def build_lap_list_for_run(run_id: str, repo: RaceLabRepository | None = None) -> dict[str, Any]:
    """Build a full lap list response for a run."""
    if repo is None:
        repo = RaceLabRepository()

    overview = repo.get_overview(run_id)
    if overview is None:
        return {
            "run_id": run_id,
            "display_name": run_id[:12],
            "laps": [],
            "best_lap_number": None,
            "best_lap_time_s": None,
            "useful_lap_numbers": [],
            "warnings": ["Run not found."],
        }

    session = overview.session
    laps = overview.laps
    best = find_best_lap(laps)

    lap_list: list[dict[str, Any]] = []
    for lap in laps:
        lap_type = classify_lap_type(lap, laps)
        delta = compute_lap_delta(lap.lap_time, best.lap_time if best else None)
        lap_list.append({
            "lap_id": lap.lap_id,
            "run_id": lap.run_id,
            "lap_number": lap.lap_number,
            "label": f"{lap_type.title() if lap_type in ('out', 'in') else 'Lap'} {lap.lap_number}",
            "lap_type": lap_type,
            "lap_time_s": lap.lap_time,
            "lap_time_display": format_lap_time(lap.lap_time),
            "delta_s": delta,
            "delta_display": format_delta(delta) if delta is not None else ("BEST" if best and lap.lap_id == best.lap_id else ""),
            "is_valid": lap.is_complete,
            "is_useful": lap.is_useful,
            "invalid_reasons": [] if lap.is_useful else ["Short or incomplete lap"],
            "sample_count": lap.sample_count or 0,
            "distance_ft": None,
            "distance_pct_min": lap.pct_min,
            "distance_pct_max": lap.pct_max,
            "start_sample_index": None,
            "end_sample_index": None,
            "start_time_s": lap.start_time,
            "end_time_s": lap.end_time,
            "has_telemetry": (lap.sample_count or 0) > 0,
            "warnings": [],
        })

    return {
        "run_id": run_id,
        "display_name": session.source_file or run_id[:12],
        "track_name": session.track_display_name or session.track_name,
        "car_name": session.car_name,
        "setup_name": session.setup_name,
        "session_name": session.session_type,
        "imported_at": session.import_time.isoformat() if hasattr(session.import_time, "isoformat") else str(session.import_time),
        "laps": lap_list,
        "best_lap_number": best.lap_number if best else None,
        "best_lap_time_s": best.lap_time if best else None,
        "useful_lap_numbers": [l.lap_number for l in useful_laps(laps) if l.lap_number is not None],
        "warnings": overview.warnings,
    }
