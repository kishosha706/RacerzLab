from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from racelab_engine.models.notebook import FindingStatus
from racelab_engine.services.notebook_service import (
    find_duplicate,
    get_finding,
    list_findings,
    save_finding,
    update_finding,
)

router = APIRouter(prefix="/api/notebook", tags=["notebook"])


class _StrictNotebookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SaveFindingRequest(_StrictNotebookRequest):
    """Client-supplied observation data; no setup policy or test authority."""

    car_name: str | None = None
    track_name: str | None = None
    setup_name: str | None = None
    baseline_run_id: str | None = None
    test_run_id: str | None = None
    comparison_id: str | None = None
    baseline_lap: int | None = None
    test_lap: int | None = None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0
    confidence_score: float = 0.0
    confidence_tier: str | None = None
    test_discipline_score: float = 0.0
    target_zone_classification: str | None = None
    summary_headline: str | None = None
    key_takeaways: list[str] | None = None
    evidence: list[str] | None = None
    warnings: list[str] | None = None
    sector_summaries: list[dict[str, Any]] | None = None
    context_changes: list[dict[str, Any]] | None = None
    improved_metrics: list[str] | None = None
    worsened_metrics: list[str] | None = None
    notes: str = ""
    tags: list[str] | None = None
    force: bool = False


class UpdateFindingRequest(_StrictNotebookRequest):
    notes: str | None = None
    status: FindingStatus | None = None
    tags: list[str] | None = None


@router.post("/findings/from-comparison")
def save_finding_endpoint(req: SaveFindingRequest) -> dict:
    existing = find_duplicate(
        req.comparison_id,
        req.baseline_run_id,
        req.test_run_id,
        req.target_zone_start_pct,
        req.target_zone_end_pct,
    )
    if existing and not req.force:
        result = existing.as_dict()
        result["duplicate"] = True
        result["duplicate_finding_id"] = existing.finding_id
        return result

    finding = save_finding(
        car_name=req.car_name,
        track_name=req.track_name,
        setup_name=req.setup_name,
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        comparison_id=req.comparison_id,
        baseline_lap=req.baseline_lap,
        test_lap=req.test_lap,
        target_zone_start_pct=req.target_zone_start_pct,
        target_zone_end_pct=req.target_zone_end_pct,
        confidence_score=req.confidence_score,
        confidence_tier=req.confidence_tier,
        test_discipline_score=req.test_discipline_score,
        target_zone_classification=req.target_zone_classification,
        summary_headline=req.summary_headline,
        key_takeaways=req.key_takeaways,
        evidence=req.evidence,
        warnings=req.warnings,
        sector_summaries=req.sector_summaries,
        context_changes=req.context_changes,
        improved_metrics=req.improved_metrics,
        worsened_metrics=req.worsened_metrics,
        notes=req.notes,
        tags=req.tags,
        force=req.force,
    )
    return finding.as_dict()


@router.get("/findings")
def list_findings_endpoint(
    request: Request,
    car_name: str | None = None,
    track_name: str | None = None,
    status: FindingStatus | None = None,
    tag: str | None = None,
) -> list[dict]:
    allowed_query_fields = {"car_name", "track_name", "status", "tag"}
    unexpected = sorted(set(request.query_params) - allowed_query_fields)
    if unexpected:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported Notebook query fields: {', '.join(unexpected)}",
        )
    findings = list_findings(
        car_name=car_name,
        track_name=track_name,
        status=status,
        tag=tag,
    )
    return [finding.as_dict() for finding in findings]


@router.get("/findings/{finding_id}")
def get_finding_endpoint(finding_id: str) -> dict:
    if not (finding := get_finding(finding_id)):
        raise HTTPException(404, f"Finding not found: {finding_id}")
    return finding.as_dict()


@router.patch("/findings/{finding_id}")
def update_finding_endpoint(finding_id: str, req: UpdateFindingRequest) -> dict:
    if not (finding := update_finding(
        finding_id,
        notes=req.notes,
        status=req.status,
        tags=req.tags,
    )):
        raise HTTPException(404, f"Finding not found: {finding_id}")
    return finding.as_dict()
