from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.routes_runs import repository
from racelab_engine.analysis.comparison import compare_target_zone, ContextChange, EnhancedComparisonSummary
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
from racelab_engine.analysis.setup_diff import (
    diff_context,
    diff_setups,
    setup_control_coverage,
    setup_controls_comparable,
)
from racelab_engine.analysis.test_discipline import score_test_discipline
from racelab_engine.analysis.lap_eligibility import eligible_laps, find_lap, lap_ineligibility_reasons, lap_is_eligible
from racelab_engine.analysis.pace_comparison import build_pace_comparison
from racelab_engine.services.import_service import read_telemetry_rows
from racelab_engine.services.insight_service import build_comparison_insights
from racelab_engine.services.setup_learning_service import record_setup_response

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
    identity = f"{baseline}|{test}|{bl_lap}|{t_lap}".encode("utf-8")
    return f"cmp_{hashlib.sha256(identity).hexdigest()[:20]}"


def _load_compare_rows(run_id: str, lap: int | None) -> list[dict]:
    return read_telemetry_rows(run_id, lap=lap)


def _resolve_eligible_lap(overview, requested_lap: int | None, role: str) -> int:
    if requested_lap is None:
        if overview.best_useful_lap and lap_is_eligible(overview.best_useful_lap):
            return overview.best_useful_lap.lap_number
        raise HTTPException(400, f"No eligible {role} lap is available.")
    lap = find_lap(overview.laps, requested_lap)
    if lap is None:
        raise HTTPException(404, f"{role.title()} lap {requested_lap} was not found.")
    if not lap_is_eligible(lap):
        reasons = "; ".join(lap_ineligibility_reasons(lap)) or "failed the evidence gate"
        raise HTTPException(400, f"{role.title()} lap {requested_lap} is not eligible: {reasons}.")
    return requested_lap


def _first_finite(rows: list[dict], key: str) -> float | None:
    for row in rows:
        value = row.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and number not in (float("inf"), float("-inf")):
            return number
    return None


def _telemetry_context_changes(baseline_rows: list[dict], test_rows: list[dict]) -> list[ContextChange]:
    changes: list[ContextChange] = []
    baseline_fuel = _first_finite(baseline_rows, "fuel_level")
    test_fuel = _first_finite(test_rows, "fuel_level")
    if baseline_fuel is not None and test_fuel is not None and abs(test_fuel - baseline_fuel) > 2.0:
        changes.append(ContextChange(
            key="fuel_level",
            label="Fuel Level",
            baseline_value=baseline_fuel,
            test_value=test_fuel,
            warning="Starting fuel differed by more than 2 L; pace attribution is confounded.",
            is_problem=True,
        ))
    return changes


def _validate_zone(start_pct: float, end_pct: float, *, label: str = "Target zone") -> None:
    if not 0.0 <= start_pct < end_pct <= 100.0:
        raise HTTPException(400, f"{label} must satisfy 0 <= start < end <= 100.")


@router.post("")
def run_comparison(req: CompareRequest) -> dict:
    _validate_zone(req.target_zone_start_pct, req.target_zone_end_pct)
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = _resolve_eligible_lap(bl_overview, req.baseline_lap, "baseline")
    t_lap = _resolve_eligible_lap(t_overview, req.test_lap, "test")

    is_same = req.baseline_run_id == req.test_run_id and bl_lap == t_lap and bl_lap is not None

    bl_rows = _load_compare_rows(req.baseline_run_id, bl_lap)
    t_rows = _load_compare_rows(req.test_run_id, t_lap)
    if not bl_rows:
        raise HTTPException(400, f"Baseline lap {bl_lap} has no telemetry data.")
    if not t_rows:
        raise HTTPException(400, f"Test lap {t_lap} has no telemetry data.")

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
        lap_count=min(len(eligible_laps(bl_overview.laps)), len(eligible_laps(t_overview.laps))),
    )
    shock_comparison = aggregate_shock_comparison(bl_rows, t_rows, s, e)

    # setup diff
    bl_setup = repo.get_setup_snapshot(req.baseline_run_id)
    t_setup = repo.get_setup_snapshot(req.test_run_id)
    setup_changes = diff_setups(bl_setup, t_setup)

    # context diff
    bl_lap_summary = find_lap(bl_overview.laps, bl_lap)
    t_lap_summary = find_lap(t_overview.laps, t_lap)
    bl_lap_valid = bl_lap_summary is not None and lap_is_eligible(bl_lap_summary)
    t_lap_valid = t_lap_summary is not None and lap_is_eligible(t_lap_summary)
    context_changes = diff_context(bl_overview.session, t_overview.session, bl_lap_valid, t_lap_valid)
    context_changes.extend(_telemetry_context_changes(bl_rows, t_rows))

    # ── Context status ──────────────────────────────────────
    # discipline
    context_problems = sum(c.is_problem for c in context_changes)
    setup_data_available = setup_controls_comparable(bl_setup, t_setup)
    discipline = score_test_discipline(
        setup_changes,
        context_problems,
        setup_data_available=setup_data_available,
    )

    # verdict
    pace = build_pace_comparison(bl_overview.laps, t_overview.laps, bl_lap, t_lap)
    verdict = compute_verdict(
        target_zone,
        discipline,
        is_same_run=is_same,
        pace=pace,
        driver_changed=driver.driver_verdict == "changed",
    )

    # whole car index
    target_speed_delta = next(
        (delta.delta for delta in target_zone.channel_deltas if delta.channel == "speed_mph"),
        None,
    )
    wci = compute_whole_car_index(
        platform,
        driver,
        powertrain,
        discipline.score,
        context_problems,
        speed_delta_mph=target_speed_delta,
    )

    comparison_id = _make_comparison_id(req.baseline_run_id, req.test_run_id, bl_lap, t_lap)
    learning_warnings: list[str] = []
    try:
        record_setup_response(
            comparison_id=comparison_id,
            car_name=t_overview.session.car_name,
            track_name=t_overview.session.track_display_name or t_overview.session.track_name,
            baseline_run_id=req.baseline_run_id,
            test_run_id=req.test_run_id,
            baseline_lap=bl_lap,
            test_lap=t_lap,
            setup_changes=setup_changes,
            discipline=discipline,
            target_zone=target_zone,
            verdict=verdict,
            pace=pace,
            driver=driver,
            context_problem_count=context_problems,
            is_same_run=is_same,
        )
    except Exception:
        learning_warnings.append("Internal setup memory could not record this comparison.")
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
        target_zone=target_zone,
        whole_car_index=wci,
        pace_comparison=pace,
        platform=platform,
        corner_matrix=corners,
        tire_comparison=tire_comparison,
        shock_comparison=shock_comparison,
        driver_comparison=driver,
        powertrain_comparison=powertrain,
        setup_changes=[{"setup_key": c.setup_key, "label": c.label, "group": c.group,
                         "baseline_value": c.baseline_value, "test_value": c.test_value,
                         "unit": c.unit, "delta": c.delta, "significance": c.significance,
                         "magnitude_basis": c.magnitude_basis,
                         "relative_delta_percent": c.relative_delta_percent,
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
        warnings=(
            (["Same run/lap comparison — reference only. Import a second .ibt to compare."] if is_same else [])
            + list(pace.confidence_notes)
            + learning_warnings
        ),
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
    baseline_coverage = setup_control_coverage(bl_setup)
    test_coverage = setup_control_coverage(t_setup)
    warnings: list[str] = []
    if baseline_coverage[0] < baseline_coverage[1]:
        warnings.append(f"Baseline setup coverage is {baseline_coverage[0]}/{baseline_coverage[1]} controls.")
    if test_coverage[0] < test_coverage[1]:
        warnings.append(f"Test setup coverage is {test_coverage[0]}/{test_coverage[1]} controls.")

    return ComparePreviewResponse(
        baseline_laps=[lap.lap_number for lap in eligible_laps(bl.laps)],
        test_laps=[lap.lap_number for lap in eligible_laps(t.laps)],
        suggested_baseline_lap=bl.best_useful_lap.lap_number if bl.best_useful_lap else None,
        suggested_test_lap=t.best_useful_lap.lap_number if t.best_useful_lap else None,
        setup_changes=[{"setup_key": c.setup_key, "label": c.label, "group": c.group,
                         "baseline_value": c.baseline_value, "test_value": c.test_value,
                         "unit": c.unit, "delta": c.delta, "significance": c.significance,
                         "magnitude_basis": c.magnitude_basis,
                         "relative_delta_percent": c.relative_delta_percent,
                         "related_to_target_issue": c.related_to_target_issue} for c in setup_changes],
        context_changes=[{"key": c.key, "label": c.label, "baseline_value": c.baseline_value,
                          "test_value": c.test_value, "warning": c.warning,
                          "is_problem": c.is_problem} for c in context_changes],
        warnings=warnings,
    )


@router.post("/delta-traces")
def get_delta_traces(req: DeltaTraceRequest) -> dict:
    """Return per-channel baseline, test, and delta traces on a shared lap-percent grid."""
    _validate_zone(req.start_pct, req.end_pct, label="Trace range")
    _validate_zone(req.target_zone_start_pct, req.target_zone_end_pct)
    if not 0.01 <= req.step_pct <= 10.0:
        raise HTTPException(400, "Trace step must be between 0.01 and 10 percentage points.")
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = _resolve_eligible_lap(bl_overview, req.baseline_lap, "baseline")
    t_lap = _resolve_eligible_lap(t_overview, req.test_lap, "test")

    # Block same-run comparison
    if req.baseline_run_id == req.test_run_id and bl_lap == t_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    bl_rows = _load_compare_rows(req.baseline_run_id, bl_lap)
    t_rows = _load_compare_rows(req.test_run_id, t_lap)

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
    _validate_zone(req.target_zone_start_pct, req.target_zone_end_pct)
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")

    bl_lap = _resolve_eligible_lap(bl_overview, req.baseline_lap, "baseline")
    t_lap = _resolve_eligible_lap(t_overview, req.test_lap, "test")

    # Block same-run
    if req.baseline_run_id == req.test_run_id and bl_lap == t_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    bl_rows = _load_compare_rows(req.baseline_run_id, bl_lap)
    t_rows = _load_compare_rows(req.test_run_id, t_lap)

    if not bl_rows:
        raise HTTPException(400, f"Baseline lap {bl_lap} has no telemetry data.")
    if not t_rows:
        raise HTTPException(400, f"Test lap {t_lap} has no telemetry data.")

    # Gather context for confidence weighting
    bl_setup = repo.get_setup_snapshot(req.baseline_run_id)
    t_setup = repo.get_setup_snapshot(req.test_run_id)
    from racelab_engine.analysis.test_discipline import score_test_discipline
    setup_changes = diff_setups(bl_setup, t_setup)
    context_changes = diff_context(bl_overview.session, t_overview.session)
    context_changes.extend(_telemetry_context_changes(bl_rows, t_rows))
    context_problems = sum(c.is_problem for c in context_changes)
    discipline = score_test_discipline(
        setup_changes,
        context_problems,
        setup_data_available=setup_controls_comparable(bl_setup, t_setup),
    )

    # Get base verdict
    from racelab_engine.analysis.comparison import compare_target_zone
    target_zone = compare_target_zone(bl_rows, t_rows, req.target_zone_start_pct, req.target_zone_end_pct)
    from racelab_engine.analysis.did_it_work import compute_verdict
    pace = build_pace_comparison(bl_overview.laps, t_overview.laps, bl_lap, t_lap)
    driver = aggregate_driver_stats(bl_rows, t_rows, req.target_zone_start_pct, req.target_zone_end_pct)
    verdict = compute_verdict(
        target_zone,
        discipline,
        pace=pace,
        driver_changed=driver.driver_verdict == "changed",
    )

    comparison_id = _make_comparison_id(req.baseline_run_id, req.test_run_id, bl_lap, t_lap)

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

