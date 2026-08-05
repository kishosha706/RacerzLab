from __future__ import annotations

from fastapi import APIRouter

from racelab_engine.analysis.analysis_surface_contracts import (
    AnalysisSurfaceContract,
    analysis_surface_contracts,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/surface-contracts", response_model=list[AnalysisSurfaceContract])
def get_analysis_surface_contracts() -> list[AnalysisSurfaceContract]:
    return list(analysis_surface_contracts())
