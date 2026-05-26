from __future__ import annotations

from fastapi import APIRouter

from api.schemas import ReportResponse
from racelab_engine.services.report_service import ReportService

router = APIRouter(prefix="/api/runs", tags=["reports"])


@router.get("/{run_id}/report")
def get_report(run_id: str) -> ReportResponse:
    markdown = ReportService().generate_markdown(run_id)
    if markdown is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return ReportResponse(run_id=run_id, markdown=markdown)
