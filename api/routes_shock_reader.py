from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.routes_runs import get_run_or_404, repository
from racelab_engine.analysis.shock_reader import build_shock_reader_response
from racelab_engine.analysis.shock_reader_schema import ShockReaderResponse
from racelab_engine.analysis.ride_height_calibration import is_next_gen_car_path

router = APIRouter(prefix="/api/runs", tags=["shock-reader"])


@router.get("/{run_id}/shock-reader", response_model=ShockReaderResponse)
def get_shock_reader(
    run_id: str,
    request: Request,
    lap: int | None = None,
    lap_window: str | None = None,
    phase: str | None = None,
    zone_start_pct: float | None = None,
    zone_end_pct: float | None = None,
) -> ShockReaderResponse:
    allowed_query_fields = {
        "lap", "lap_window", "phase", "zone_start_pct", "zone_end_pct",
    }
    unexpected = sorted(set(request.query_params) - allowed_query_fields)
    if unexpected:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported Shock Reader query fields: {', '.join(unexpected)}",
        )
    overview = get_run_or_404(run_id)
    parsed_window = _parse_lap_window(lap_window)
    if lap is not None and parsed_window is not None:
        raise HTTPException(status_code=400, detail="Use lap or lap_window, not both.")
    setup = repository().get_setup_snapshot(run_id)
    next_gen = is_next_gen_car_path(overview.session.car_path)
    boundary = 1.5 if next_gen else 1.0
    boundary_basis = (
        "Official iRacing Next Gen guidance: the high-speed adjuster begins at approximately 1.5 in/s; "
        "the regime classification must also survive a plus/minus 25% sensitivity check."
        if next_gen
        else "Descriptive 1.0 in/s boundary only; a verified car-specific high-speed transition is unavailable."
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
            expected_sample_rate_hz=float(overview.session.telemetry_rate_hz or 60.0),
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
