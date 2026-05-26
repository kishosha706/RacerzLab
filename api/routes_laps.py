from __future__ import annotations

from fastapi import APIRouter

from api.routes_runs import repository
from racelab_engine.models.lap import LapSummary

router = APIRouter(prefix="/api/runs", tags=["laps"])


@router.get("/{run_id}/laps")
def get_laps(run_id: str) -> list[LapSummary]:
    return repository().get_laps(run_id)
