from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.routes_runs import repository
from racelab_engine.analysis.lap_windows import compute_lap_windows_response
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import LapCompareSelection, LapWindowsResponse

router = APIRouter(prefix="/api/runs", tags=["laps"])


@router.get("/{run_id}/laps")
def get_laps(run_id: str) -> list[LapSummary]:
    return repository().get_laps(run_id)


@router.get("/{run_id}/lap-windows", response_model=LapWindowsResponse)
def get_lap_windows(run_id: str) -> LapWindowsResponse:
    if not (laps := repository().get_laps(run_id)):
        raise HTTPException(404, f"No laps found for run {run_id}")
    return compute_lap_windows_response(laps)


@router.post("/laps/compare-selection")
def validate_compare_selection(req: LapCompareSelection) -> LapCompareSelection:
    repo = repository()
    bl_laps = repo.get_laps(req.baseline_run_id)
    t_laps = repo.get_laps(req.test_run_id)
    if not bl_laps:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if not t_laps:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = next((l for l in bl_laps if l.lap_number == req.baseline_lap), None)
    t_lap = next((l for l in t_laps if l.lap_number == req.test_lap), None)
    if bl_lap is None:
        raise HTTPException(404, f"Baseline lap {req.baseline_lap} not found")
    if t_lap is None:
        raise HTTPException(404, f"Test lap {req.test_lap} not found")

    warnings: list[str] = []
    can_compare = True
    if req.baseline_run_id == req.test_run_id and req.baseline_lap == req.test_lap:
        warnings.append("Same run and lap selected - reference mode only.")
        can_compare = False

    bl_session = repo.get_session(req.baseline_run_id)
    t_session = repo.get_session(req.test_run_id)
    if bl_session and t_session:
        if bl_session.car_name != t_session.car_name:
            warnings.append(f"Different cars: {bl_session.car_name} vs {t_session.car_name}")
            can_compare = False
        if bl_session.track_name != t_session.track_name:
            warnings.append(f"Different tracks: {bl_session.track_name} vs {t_session.track_name}")
            can_compare = False

    if not bl_lap.is_useful:
        warnings.append(f"Baseline lap {req.baseline_lap} is not useful.")
        can_compare = False
    if not t_lap.is_useful:
        warnings.append(f"Test lap {req.test_lap} is not useful.")
        can_compare = False

    return LapCompareSelection(
        baseline_run_id=req.baseline_run_id,
        baseline_lap=req.baseline_lap,
        test_run_id=req.test_run_id,
        test_lap=req.test_lap,
        comparison_warnings=warnings,
        can_compare_cleanly=can_compare,
        reason="Ready for comparison." if can_compare else "Resolve warnings before comparing.",
    )
