from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.routes_runs import repository
from racelab_engine.analysis.comparison import compare_target_zone, EnhancedComparisonSummary
from racelab_engine.analysis.compare_delta_traces import (
    DeltaTraceResponse,
    compute_delta_traces,
)
from racelab_engine.analysis.compare_math import (
    aggregate_platform_stats, aggregate_driver_stats,
    aggregate_powertrain_stats, aggregate_corner_stats,
    aggregate_tire_comparison, aggregate_shock_comparison,
    compute_whole_car_index,
)
from racelab_engine.analysis.did_it_work import compute_verdict
from racelab_engine.analysis.setup_diff import diff_context, diff_setups
from racelab_engine.analysis.test_discipline import score_test_discipline
from racelab_engine.services.import_service import read_telemetry_rows
from racelab_engine.services.insight_service import build_comparison_insights

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareRequest(BaseModel):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None = None
    test_lap: int | None = None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0


class ComparePreviewResponse(BaseModel):
    baseline_laps: list[int]
    test_laps: list[int]
    suggested_baseline_lap: int | None
    suggested_test_lap: int | None
    setup_changes: list[dict]
    context_changes: list[dict]
    warnings: list[str]


class DeltaTraceRequest(BaseModel):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None = None
    test_lap: int | None = None
    channels: list[str] | None = None
    x_axis: str = "lap_dist_ft"
    start_pct: float = 0.0
    end_pct: float = 100.0
    step_pct: float = 0.1
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0


def _make_comparison_id(baseline: str, test: str, bl_lap: int | None, t_lap: int | None) -> str:
    return f"{baseline[:12]}_vs_{test[:12]}_l{bl_lap or 'x'}_l{t_lap or 'x'}"


@router.post("")
def run_comparison(req: CompareRequest) -> dict:
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = req.baseline_lap or (bl_overview.best_useful_lap.lap_number if bl_overview.best_useful_lap else None)
    t_lap = req.test_lap or (t_overview.best_useful_lap.lap_number if t_overview.best_useful_lap else None)

    is_same = req.baseline_run_id == req.test_run_id and bl_lap == t_lap and bl_lap is not None

    bl_rows = read_telemetry_rows(req.baseline_run_id)
    t_rows = read_telemetry_rows(req.test_run_id)
    bl_rows = [r for r in bl_rows if r.get("lap") == bl_lap] if bl_lap else bl_rows
    t_rows = [r for r in t_rows if r.get("lap") == t_lap] if t_lap else t_rows

    s = req.target_zone_start_pct
    e = req.target_zone_end_pct

    # target zone
    target_zone = compare_target_zone(bl_rows, t_rows, s, e)

    # whole-car comparison sub-systems
    platform = aggregate_platform_stats(bl_rows, t_rows, s, e)
    corners = aggregate_corner_stats(bl_rows, t_rows, s, e)
    driver = aggregate_driver_stats(bl_rows, t_rows, s, e)
    powertrain = aggregate_powertrain_stats(bl_rows, t_rows, s, e)
    tire_comparison = aggregate_tire_comparison(
        bl_rows, t_rows, s, e,
        lap_count=len(bl_overview.laps) if bl_overview.laps else 0,
    )
    shock_comparison = aggregate_shock_comparison(bl_rows, t_rows, s, e)

    # setup diff
    bl_setup = repo.get_setup_snapshot(req.baseline_run_id)
    t_setup = repo.get_setup_snapshot(req.test_run_id)
    setup_changes = diff_setups(bl_setup, t_setup)

    # context diff
    bl_lap_valid = bl_overview.best_useful_lap is not None
    t_lap_valid = t_overview.best_useful_lap is not None
    context_changes = diff_context(bl_overview.session, t_overview.session, bl_lap_valid, t_lap_valid)

    # ── Draft status context ──────────────────────────────────────
    import logging
    _log = logging.getLogger(__name__)
    try:
        from racelab_engine.analysis.draft_detection import classify_draft_status
        bl_draft = classify_draft_status(bl_rows)
        t_draft = classify_draft_status(t_rows)
        if bl_draft.status != t_draft.status:
            from racelab_engine.analysis.comparison import ContextChange
            context_changes.append(ContextChange(
                key="draft_status",
                label="Draft Status",
                warning=f"Baseline: {bl_draft.status.value}, Test: {t_draft.status.value}. "
                        f"Draft difference may affect speed comparison.",
                is_problem=True,
            ))
    except Exception as exc:
        _log.warning("Draft comparison failed: %s", exc)

    # discipline
    context_problems = sum(c.is_problem for c in context_changes)
    discipline = score_test_discipline(setup_changes, context_problems)

    # verdict
    verdict = compute_verdict(target_zone, discipline, is_same_run=is_same)

    # whole car index
    wci = compute_whole_car_index(platform, driver, powertrain, discipline.score, context_problems)

    comparison_id = _make_comparison_id(req.baseline_run_id, req.test_run_id, bl_lap, t_lap)
    # Thread recommendation fields into verdict if available
    bl_recommendations = repo.get_recommendations(req.baseline_run_id) if hasattr(repo, 'get_recommendations') else []
    cause_bucket = bl_recommendations[0].cause_bucket if bl_recommendations else None
    success_metric = bl_recommendations[0].success_metric if bl_recommendations else None
    required_next_data = bl_recommendations[0].required_next_data if bl_recommendations else []
    do_not_change_warnings = bl_recommendations[0].do_not_change_warnings if bl_recommendations else []

    summary = EnhancedComparisonSummary(
        comparison_id=comparison_id,
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        baseline_lap=bl_lap,
        test_lap=t_lap,
        target_zone_start_pct=s,
        target_zone_end_pct=e,
        whole_car_index=wci,
        platform=platform,
        corner_matrix=corners,
        tire_comparison=tire_comparison,
        shock_comparison=shock_comparison,
        driver_comparison=driver,
        powertrain_comparison=powertrain,
        setup_changes=[{"setup_key": c.setup_key, "label": c.label, "group": c.group,
                         "baseline_value": c.baseline_value, "test_value": c.test_value,
                         "delta": c.delta, "significance": c.significance,
                         "related_to_target_issue": c.related_to_target_issue} for c in setup_changes],
        context_changes=[{"key": c.key, "label": c.label, "baseline_value": c.baseline_value,
                          "test_value": c.test_value, "warning": c.warning,
                          "is_problem": c.is_problem} for c in context_changes],
        test_discipline={"score": discipline.score, "label": discipline.label,
                         "positive_factors": discipline.positive_factors,
                         "negative_factors": discipline.negative_factors,
                         "recommendation": discipline.recommendation},
        verdict={"verdict": verdict.verdict, "confidence_score": verdict.confidence_score,
                 "headline": verdict.headline, "evidence": verdict.evidence,
                 "warnings": verdict.warnings, "next_step": verdict.next_step,
                 "success_metric": success_metric,
                 "cause_bucket": cause_bucket,
                 "required_next_data": required_next_data,
                 "do_not_change_warnings": do_not_change_warnings},
        warnings=["Same run/lap comparison — reference only. Import a second .ibt to compare."] if is_same else [],
        confidence_score=verdict.confidence_score,
    )
    return summary.as_dict()


@router.get("/preview")
def compare_preview(baseline_run_id: str, test_run_id: str) -> ComparePreviewResponse:
    repo = repository()
    bl = repo.get_overview(baseline_run_id)
    t = repo.get_overview(test_run_id)
    if bl is None or t is None:
        raise HTTPException(404, "One or both runs not found.")

    bl_setup = repo.get_setup_snapshot(baseline_run_id)
    t_setup = repo.get_setup_snapshot(test_run_id)
    setup_changes = diff_setups(bl_setup, t_setup)
    context_changes = diff_context(bl.session, t.session)

    return ComparePreviewResponse(
        baseline_laps=[lap.lap_number for lap in bl.laps if lap.is_useful],
        test_laps=[lap.lap_number for lap in t.laps if lap.is_useful],
        suggested_baseline_lap=bl.best_useful_lap.lap_number if bl.best_useful_lap else None,
        suggested_test_lap=t.best_useful_lap.lap_number if t.best_useful_lap else None,
        setup_changes=[{"setup_key": c.setup_key, "label": c.label, "group": c.group,
                         "baseline_value": c.baseline_value, "test_value": c.test_value,
                         "delta": c.delta, "significance": c.significance,
                         "related_to_target_issue": c.related_to_target_issue} for c in setup_changes],
        context_changes=[{"key": c.key, "label": c.label, "baseline_value": c.baseline_value,
                          "test_value": c.test_value, "warning": c.warning,
                          "is_problem": c.is_problem} for c in context_changes],
        warnings=[],
    )


@router.post("/delta-traces")
def get_delta_traces(req: DeltaTraceRequest) -> dict:
    """Return per-channel baseline, test, and delta traces on a shared lap-percent grid."""
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = req.baseline_lap or (bl_overview.best_useful_lap.lap_number if bl_overview.best_useful_lap else None)
    t_lap = req.test_lap or (t_overview.best_useful_lap.lap_number if t_overview.best_useful_lap else None)

    if bl_lap is None:
        raise HTTPException(400, "No useful baseline lap available. Import a run with valid laps.")
    if t_lap is None:
        raise HTTPException(400, "No useful test lap available. Import a run with valid laps.")

    # Block same-run comparison
    if req.baseline_run_id == req.test_run_id and bl_lap == t_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    bl_rows = read_telemetry_rows(req.baseline_run_id)
    t_rows = read_telemetry_rows(req.test_run_id)
    bl_rows = [r for r in bl_rows if r.get("lap") == bl_lap]
    t_rows = [r for r in t_rows if r.get("lap") == t_lap]

    if not bl_rows:
        raise HTTPException(400, f"Baseline lap {bl_lap} has no telemetry data.")
    if not t_rows:
        raise HTTPException(400, f"Test lap {t_lap} has no telemetry data.")

    result = compute_delta_traces(
        bl_rows, t_rows,
        channels=req.channels,
        x_axis=req.x_axis,
        start_pct=req.start_pct,
        end_pct=req.end_pct,
        step_pct=req.step_pct,
        target_zone_start_pct=req.target_zone_start_pct,
        target_zone_end_pct=req.target_zone_end_pct,
    )

    return DeltaTraceResponse(
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        baseline_lap=bl_lap,
        test_lap=t_lap,
        x_axis=result.x_axis,
        x_unit=result.x_unit,
        x_values=result.x_values,
        lap_pct_values=result.lap_pct_values,
        target_zone_start_pct=result.target_zone_start_pct,
        target_zone_end_pct=result.target_zone_end_pct,
        channels=result.channels,
        warnings=result.warnings,
        missing_channels=result.missing_channels,
    ).as_dict()


class InsightsRequest(BaseModel):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None = None
    test_lap: int | None = None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0
    channels: list[str] | None = None


@router.post("/insights")
def get_comparison_insights(req: InsightsRequest) -> dict:
    """Run all insight engines and return combined analysis."""
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = req.baseline_lap or (bl_overview.best_useful_lap.lap_number if bl_overview.best_useful_lap else None)
    t_lap = req.test_lap or (t_overview.best_useful_lap.lap_number if t_overview.best_useful_lap else None)

    if bl_lap is None:
        raise HTTPException(400, "No useful baseline lap available.")
    if t_lap is None:
        raise HTTPException(400, "No useful test lap available.")

    # Block same-run
    if req.baseline_run_id == req.test_run_id and bl_lap == t_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    bl_rows = read_telemetry_rows(req.baseline_run_id)
    t_rows = read_telemetry_rows(req.test_run_id)
    bl_rows = [r for r in bl_rows if r.get("lap") == bl_lap]
    t_rows = [r for r in t_rows if r.get("lap") == t_lap]

    if not bl_rows:
        raise HTTPException(400, f"Baseline lap {bl_lap} has no telemetry data.")
    if not t_rows:
        raise HTTPException(400, f"Test lap {t_lap} has no telemetry data.")

    # Gather context for confidence weighting
    bl_setup = repo.get_setup_snapshot(req.baseline_run_id)
    t_setup = repo.get_setup_snapshot(req.test_run_id)
    from racelab_engine.analysis.setup_diff import diff_context, diff_setups
    from racelab_engine.analysis.test_discipline import score_test_discipline
    setup_changes = diff_setups(bl_setup, t_setup)
    context_changes = diff_context(bl_overview.session, t_overview.session)
    context_problems = sum(c.is_problem for c in context_changes)
    discipline = score_test_discipline(setup_changes, context_problems)

    # Get base verdict
    from racelab_engine.analysis.comparison import compare_target_zone
    target_zone = compare_target_zone(bl_rows, t_rows, req.target_zone_start_pct, req.target_zone_end_pct)
    from racelab_engine.analysis.did_it_work import compute_verdict
    verdict = compute_verdict(target_zone, discipline)

    comparison_id = f"{req.baseline_run_id[:12]}_vs_{req.test_run_id[:12]}_l{bl_lap or 'x'}_l{t_lap or 'x'}"

    insights = build_comparison_insights(
        comparison_id=comparison_id,
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        baseline_lap=bl_lap,
        test_lap=t_lap,
        baseline_rows=bl_rows,
        test_rows=t_rows,
        target_zone_start_pct=req.target_zone_start_pct,
        target_zone_end_pct=req.target_zone_end_pct,
        discipline_label=discipline.label,
        discipline_score=discipline.score,
        context_problems=context_problems,
        verdict_str=verdict.verdict,
        base_confidence=verdict.confidence_score,
        channels=req.channels,
    )
    return insights.as_dict()
