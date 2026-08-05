from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.routes_runs import get_run_or_404, repository
from racelab_engine.analysis.shock_reader import build_shock_reader_response
from racelab_engine.analysis.shock_reader_schema import ShockReaderResponse
from racelab_engine.analysis.ride_height_calibration import is_next_gen_car_path

router = APIRouter(prefix="/api/runs", tags=["shock-reader"])


@router.get("/{run_id}/shock-reader", response_model=ShockReaderResponse)
def get_shock_reader(
    run_id: str,
    lap: int | None = None,
    lap_window: str | None = None,
    phase: str | None = None,
    zone_start_pct: float | None = None,
    zone_end_pct: float | None = None,
    include_debug: bool = False,
) -> ShockReaderResponse:
    overview = get_run_or_404(run_id)
    parsed_window = _parse_lap_window(lap_window)
    if lap is not None and parsed_window is not None:
        raise HTTPException(status_code=400, detail="Use lap or lap_window, not both.")
    setup = repository().get_setup_snapshot(run_id)
    next_gen = is_next_gen_car_path(overview.session.car_path)
    boundary = 1.5 if next_gen else 1.0
    boundary_basis = (
        "Official iRacing Next Gen guidance: the high-speed adjuster begins at approximately 1.5 in/s; "
        "the conclusion must also survive a plus/minus 25% sensitivity check."
        if next_gen
        else "Descriptive 1.0 in/s boundary only; a verified car-specific high-speed transition is unavailable, so slope actions are withheld."
    )
    try:
        return build_shock_reader_response(
            run_id,
            lap=lap,
            lap_window=parsed_window,
            phase=phase,
            zone_start_pct=zone_start_pct,
            zone_end_pct=zone_end_pct,
            boundary_in_s=boundary,
            boundary_basis=boundary_basis,
            slope_boundary_verified=next_gen,
            expected_sample_rate_hz=float(overview.session.telemetry_rate_hz or 60.0),
            include_debug=include_debug,
            setup_snapshot=setup,
            lap_summaries=overview.laps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_lap_window(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    normalized = value.strip().replace(":", "-").replace(",", "-")
    parts = [part.strip() for part in normalized.split("-") if part.strip()]
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="lap_window must look like 3-8.")
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="lap_window must contain whole lap numbers.") from exc
    if start <= 0 or end < start:
        raise HTTPException(status_code=400, detail="lap_window must be a positive ascending range.")
    return start, end
