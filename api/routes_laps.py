from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.routes_runs import repository
from racelab_engine.analysis.lap_windows import compute_lap_windows_response
from racelab_engine.analysis.lap_eligibility import lap_ineligibility_reasons, lap_is_eligible
from racelab_engine.analysis.stint_intelligence import build_stint_response, compare_stints
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import (
    LapCompareSelection,
    LapWindowsResponse,
    StintCompareRequest,
    StintCompareResult,
    StintResponse,
)

router = APIRouter(prefix="/api/runs", tags=["laps"])
stints_router = APIRouter(prefix="/api/stints", tags=["stints"])


@router.get("/{run_id}/laps")
def get_laps(run_id: str) -> list[LapSummary]:
    return repository().get_laps(run_id)


@router.get("/{run_id}/lap-windows", response_model=LapWindowsResponse)
def get_lap_windows(run_id: str) -> LapWindowsResponse:
    if not (laps := repository().get_laps(run_id)):
        raise HTTPException(404, f"No laps found for run {run_id}")
    return compute_lap_windows_response(laps)


@router.get("/{run_id}/stints", response_model=StintResponse)
def get_stints(run_id: str) -> StintResponse:
    repo = repository()
    if not (laps := repo.get_laps(run_id)):
        raise HTTPException(404, f"No laps found for run {run_id}")
    return build_stint_response(laps, repo.get_session(run_id))


@stints_router.post("/compare", response_model=StintCompareResult)
def compare_stint_summaries(req: StintCompareRequest) -> StintCompareResult:
    repo = repository()
    baseline_laps = repo.get_laps(req.baseline_run_id)
    test_laps = repo.get_laps(req.test_run_id)
    if not baseline_laps:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if not test_laps:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    baseline_response = build_stint_response(baseline_laps, repo.get_session(req.baseline_run_id))
    test_response = build_stint_response(test_laps, repo.get_session(req.test_run_id))
    baseline_candidates = {
        stint.stint_id: stint
        for stint in [
            *baseline_response.stint_rows,
            *baseline_response.best_window_cards,
            *baseline_response.stints,
            *baseline_response.all_windows,
        ]
    }
    test_candidates = {
        stint.stint_id: stint
        for stint in [
            *test_response.stint_rows,
            *test_response.best_window_cards,
            *test_response.stints,
            *test_response.all_windows,
        ]
    }
    baseline = baseline_candidates.get(req.baseline_stint_id)
    test = test_candidates.get(req.test_stint_id)
    if baseline is None:
        raise HTTPException(404, f"Baseline stint not found: {req.baseline_stint_id}")
    if test is None:
        raise HTTPException(404, f"Test stint not found: {req.test_stint_id}")
    return compare_stints(baseline, test)


@router.post("/laps/compare-selection")
def validate_compare_selection(req: LapCompareSelection) -> LapCompareSelection:
    repo = repository()
    bl_laps = repo.get_laps(req.baseline_run_id)
    t_laps = repo.get_laps(req.test_run_id)
    if not bl_laps:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if not t_laps:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = next((lap for lap in bl_laps if lap.lap_number == req.baseline_lap), None)
    t_lap = next((lap for lap in t_laps if lap.lap_number == req.test_lap), None)
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

    if not lap_is_eligible(bl_lap):
        detail = "; ".join(lap_ineligibility_reasons(bl_lap))
        warnings.append(f"Baseline lap {req.baseline_lap} is not eligible: {detail}.")
        can_compare = False
    if not lap_is_eligible(t_lap):
        detail = "; ".join(lap_ineligibility_reasons(t_lap))
        warnings.append(f"Test lap {req.test_lap} is not eligible: {detail}.")
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
