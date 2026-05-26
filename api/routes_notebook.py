from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from racelab_engine.models.notebook import FindingStatus
from racelab_engine.services.notebook_service import (
    build_setup_memory_summary,
    create_test_plan,
    find_duplicate,
    get_finding,
    list_findings,
    list_test_plans,
    save_finding,
    update_finding,
    update_test_plan,
)

router = APIRouter(prefix="/api/notebook", tags=["notebook"])


class SaveFindingRequest(BaseModel):
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
    verdict: str | None = None
    confidence_score: float = 0.0
    confidence_tier: str | None = None
    test_discipline_score: float = 0.0
    target_zone_classification: str | None = None
    summary_headline: str | None = None
    key_takeaways: list[str] | None = None
    evidence: list[str] | None = None
    warnings: list[str] | None = None
    sector_summaries: list[dict[str, Any]] | None = None
    setup_changes: list[dict[str, Any]] | None = None
    context_changes: list[dict[str, Any]] | None = None
    improved_metrics: list[str] | None = None
    worsened_metrics: list[str] | None = None
    next_step: str | None = None
    notes: str = ""
    tags: list[str] | None = None
    status: str | None = None
    force: bool = False


class UpdateFindingRequest(BaseModel):
    notes: str | None = None
    status: str | None = None
    tags: list[str] | None = None


class CreateTestPlanRequest(BaseModel):
    goal: str | None = None
    change_to_try: str | None = None
    do_not_change: list[str] | None = None
    success_metric: str | None = None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0
    planned_notes: str = ""


class UpdateTestPlanRequest(BaseModel):
    status: str | None = None
    planned_notes: str | None = None


@router.post("/findings/from-comparison")
def save_finding_endpoint(req: SaveFindingRequest) -> dict:
    # Check for duplicate before saving
    existing = find_duplicate(
        req.comparison_id, req.baseline_run_id, req.test_run_id,
        req.target_zone_start_pct, req.target_zone_end_pct,
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
        verdict=req.verdict,
        confidence_score=req.confidence_score,
        confidence_tier=req.confidence_tier,
        test_discipline_score=req.test_discipline_score,
        target_zone_classification=req.target_zone_classification,
        summary_headline=req.summary_headline,
        key_takeaways=req.key_takeaways,
        evidence=req.evidence,
        warnings=req.warnings,
        sector_summaries=req.sector_summaries,
        setup_changes=req.setup_changes,
        context_changes=req.context_changes,
        improved_metrics=req.improved_metrics,
        worsened_metrics=req.worsened_metrics,
        next_step=req.next_step,
        notes=req.notes,
        tags=req.tags,
        status=cast("FindingStatus | None", req.status),
        force=req.force,
    )
    return finding.as_dict()


@router.get("/findings")
def list_findings_endpoint(
    car_name: str | None = None,
    track_name: str | None = None,
    verdict: str | None = None,
    status: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    findings = list_findings(
        car_name=car_name,
        track_name=track_name,
        verdict=verdict,
        status=status,
        tag=tag,
    )
    return [f.as_dict() for f in findings]


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
        status=cast("FindingStatus | None", req.status),
        tags=req.tags,
    )):
        raise HTTPException(404, f"Finding not found: {finding_id}")
    return finding.as_dict()


@router.post("/findings/{finding_id}/test-plan")
def create_test_plan_endpoint(finding_id: str, req: CreateTestPlanRequest) -> dict:
    if not (plan := create_test_plan(
        finding_id,
        goal=req.goal,
        change_to_try=req.change_to_try,
        do_not_change=req.do_not_change,
        success_metric=req.success_metric,
        target_zone_start_pct=req.target_zone_start_pct,
        target_zone_end_pct=req.target_zone_end_pct,
        planned_notes=req.planned_notes,
    )):
        raise HTTPException(404, f"Finding not found: {finding_id}")
    return plan.as_dict()


@router.get("/test-plans")
def list_test_plans_endpoint(
    car_name: str | None = None,
    track_name: str | None = None,
    status: str | None = None,
) -> list[dict]:
    plans = list_test_plans(car_name=car_name, track_name=track_name, status=status)
    return [p.as_dict() for p in plans]


@router.patch("/test-plans/{test_plan_id}")
def update_test_plan_endpoint(test_plan_id: str, req: UpdateTestPlanRequest) -> dict:
    if not (plan := update_test_plan(
        test_plan_id,
        status=req.status,
        planned_notes=req.planned_notes,
    )):
        raise HTTPException(404, f"Test plan not found: {test_plan_id}")
    return plan.as_dict()


@router.get("/setup-memory")
def setup_memory_endpoint(
    car_name: str | None = None,
    track_name: str | None = None,
) -> dict:
    summary = build_setup_memory_summary(car_name=car_name, track_name=track_name)
    return summary.as_dict()
