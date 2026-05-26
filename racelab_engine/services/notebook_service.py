from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from racelab_engine.models.notebook import (
    FindingStatus,
    NotebookFinding,
    SetupMemorySummary,
    TestPlan,
)
from racelab_engine.storage.db import initialize_database


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _load_json(value: str | None, fallback: Any = None) -> Any:
    return json.loads(value) if value else fallback


def _default_status(verdict: str | None) -> FindingStatus:
    mapping: dict[str, FindingStatus] = {
        "keep_direction": "saved",
        "undo": "rejected",
        "retest": "needs_retest",
        "inconclusive": "needs_retest",
    }
    return mapping.get(verdict or "", "saved")


def find_duplicate(
    comparison_id: str | None,
    baseline_run_id: str | None,
    test_run_id: str | None,
    target_zone_start_pct: float = 55.0,
    target_zone_end_pct: float = 70.0,
    db_path: str | Path | None = None,
) -> NotebookFinding | None:
    """Check if a finding already exists for this comparison + target zone."""
    if not comparison_id:
        return None
    conn = initialize_database(db_path)
    row = conn.execute(
        """
        SELECT * FROM notebook_findings
        WHERE comparison_id = ? AND baseline_run_id = ? AND test_run_id = ?
          AND target_zone_start_pct = ? AND target_zone_end_pct = ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (comparison_id, baseline_run_id, test_run_id, target_zone_start_pct, target_zone_end_pct),
    ).fetchone()
    conn.close()
    return _row_to_finding(dict(row)) if row else None


def save_finding(
    *,
    car_name: str | None = None,
    track_name: str | None = None,
    setup_name: str | None = None,
    baseline_run_id: str | None = None,
    test_run_id: str | None = None,
    comparison_id: str | None = None,
    baseline_lap: int | None = None,
    test_lap: int | None = None,
    target_zone_start_pct: float = 55.0,
    target_zone_end_pct: float = 70.0,
    verdict: str | None = None,
    confidence_score: float = 0.0,
    confidence_tier: str | None = None,
    test_discipline_score: float = 0.0,
    target_zone_classification: str | None = None,
    summary_headline: str | None = None,
    key_takeaways: list[str] | None = None,
    evidence: list[str] | None = None,
    warnings: list[str] | None = None,
    sector_summaries: list[dict[str, Any]] | None = None,
    setup_changes: list[dict[str, Any]] | None = None,
    context_changes: list[dict[str, Any]] | None = None,
    improved_metrics: list[str] | None = None,
    worsened_metrics: list[str] | None = None,
    next_step: str | None = None,
    notes: str = "",
    tags: list[str] | None = None,
    status: FindingStatus | None = None,
    force: bool = False,
    db_path: str | Path | None = None,
) -> NotebookFinding:
    """Save a notebook finding from comparison + insights data.

    If a duplicate finding exists (same comparison_id + runs + target zone),
    returns the existing finding unless force=True.
    """
    # Check for duplicate
    if not force and comparison_id:
        existing = find_duplicate(comparison_id, baseline_run_id, test_run_id,
                                  target_zone_start_pct, target_zone_end_pct, db_path)
        if existing:
            return existing

    finding_id = f"finding_{uuid.uuid4().hex[:12]}"
    now = _utc_now()
    effective_status: FindingStatus = status or _default_status(verdict)

    conn = initialize_database(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO notebook_findings (
              finding_id, created_at, updated_at,
              car_name, track_name, setup_name,
              baseline_run_id, test_run_id, comparison_id,
              baseline_lap, test_lap,
              target_zone_start_pct, target_zone_end_pct,
              verdict, confidence_score, confidence_tier,
              test_discipline_score, target_zone_classification,
              summary_headline,
              key_takeaways_json, evidence_json, warnings_json,
              sector_summaries_json, setup_changes_json, context_changes_json,
              improved_metrics_json, worsened_metrics_json,
              next_step, notes, tags_json, status
            ) VALUES (
              ?, ?, ?,
              ?, ?, ?,
              ?, ?, ?,
              ?, ?,
              ?, ?,
              ?, ?, ?,
              ?, ?,
              ?,
              ?, ?, ?,
              ?, ?, ?,
              ?, ?,
              ?, ?, ?, ?
            )
            """,
            (
                finding_id, now, now,
                car_name, track_name, setup_name,
                baseline_run_id, test_run_id, comparison_id,
                baseline_lap, test_lap,
                target_zone_start_pct, target_zone_end_pct,
                verdict, confidence_score, confidence_tier,
                test_discipline_score, target_zone_classification,
                summary_headline,
                _json(key_takeaways or []),
                _json(evidence or []),
                _json(warnings or []),
                _json(sector_summaries or []),
                _json(setup_changes or []),
                _json(context_changes or []),
                _json(improved_metrics or []),
                _json(worsened_metrics or []),
                next_step, notes, _json(tags or []),
                effective_status,
            ),
        )
    conn.close()

    return NotebookFinding(
        finding_id=finding_id,
        created_at=now,
        updated_at=now,
        car_name=car_name,
        track_name=track_name,
        setup_name=setup_name,
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        comparison_id=comparison_id,
        baseline_lap=baseline_lap,
        test_lap=test_lap,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
        verdict=verdict,
        confidence_score=confidence_score,
        confidence_tier=confidence_tier,
        test_discipline_score=test_discipline_score,
        target_zone_classification=target_zone_classification,
        summary_headline=summary_headline,
        key_takeaways=key_takeaways or [],
        evidence=evidence or [],
        warnings=warnings or [],
        sector_summaries=sector_summaries or [],
        setup_changes=setup_changes or [],
        context_changes=context_changes or [],
        improved_metrics=improved_metrics or [],
        worsened_metrics=worsened_metrics or [],
        next_step=next_step,
        notes=notes,
        tags=tags or [],
        status=effective_status,
    )


def _row_to_finding(row: dict[str, Any]) -> NotebookFinding:
    return NotebookFinding(
        finding_id=row["finding_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        car_name=row["car_name"],
        track_name=row["track_name"],
        setup_name=row["setup_name"],
        baseline_run_id=row["baseline_run_id"],
        test_run_id=row["test_run_id"],
        comparison_id=row["comparison_id"],
        baseline_lap=row["baseline_lap"],
        test_lap=row["test_lap"],
        target_zone_start_pct=row["target_zone_start_pct"] or 55.0,
        target_zone_end_pct=row["target_zone_end_pct"] or 70.0,
        verdict=row["verdict"],
        confidence_score=row["confidence_score"] or 0.0,
        confidence_tier=row["confidence_tier"],
        test_discipline_score=row["test_discipline_score"] or 0.0,
        target_zone_classification=row["target_zone_classification"],
        summary_headline=row["summary_headline"],
        key_takeaways=_load_json(row["key_takeaways_json"], []),
        evidence=_load_json(row["evidence_json"], []),
        warnings=_load_json(row["warnings_json"], []),
        sector_summaries=_load_json(row["sector_summaries_json"], []),
        setup_changes=_load_json(row["setup_changes_json"], []),
        context_changes=_load_json(row["context_changes_json"], []),
        improved_metrics=_load_json(row["improved_metrics_json"], []),
        worsened_metrics=_load_json(row["worsened_metrics_json"], []),
        next_step=row["next_step"],
        notes=row["notes"] or "",
        tags=_load_json(row["tags_json"], []),
        status=row["status"],
    )


def list_findings(
    car_name: str | None = None,
    track_name: str | None = None,
    verdict: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    db_path: str | Path | None = None,
) -> list[NotebookFinding]:
    conn = initialize_database(db_path)
    sql = "SELECT * FROM notebook_findings WHERE 1=1"
    params: list[Any] = []
    if car_name:
        sql += " AND car_name = ?"
        params.append(car_name)
    if track_name:
        sql += " AND track_name = ?"
        params.append(track_name)
    if verdict:
        sql += " AND verdict = ?"
        params.append(verdict)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_finding(dict(r)) for r in rows]


def get_finding(finding_id: str, db_path: str | Path | None = None) -> NotebookFinding | None:
    conn = initialize_database(db_path)
    row = conn.execute("SELECT * FROM notebook_findings WHERE finding_id = ?", (finding_id,)).fetchone()
    conn.close()
    return _row_to_finding(dict(row)) if row else None


def update_finding(
    finding_id: str,
    *,
    notes: str | None = None,
    status: FindingStatus | None = None,
    tags: list[str] | None = None,
    db_path: str | Path | None = None,
) -> NotebookFinding | None:
    conn = initialize_database(db_path)
    now = _utc_now()
    updates: list[str] = ["updated_at = ?"]
    params: list[Any] = [now]
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if tags is not None:
        updates.append("tags_json = ?")
        params.append(_json(tags))
    params.append(finding_id)
    conn.execute(f"UPDATE notebook_findings SET {', '.join(updates)} WHERE finding_id = ?", params)
    conn.commit()
    conn.close()
    return get_finding(finding_id, db_path)


def create_test_plan(
    source_finding_id: str,
    *,
    goal: str | None = None,
    change_to_try: str | None = None,
    do_not_change: list[str] | None = None,
    success_metric: str | None = None,
    target_zone_start_pct: float = 55.0,
    target_zone_end_pct: float = 70.0,
    planned_notes: str = "",
    db_path: str | Path | None = None,
) -> TestPlan | None:
    finding = get_finding(source_finding_id, db_path)
    if not finding:
        return None

    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    now = _utc_now()

    conn = initialize_database(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO test_plans (
              test_plan_id, created_at, updated_at, source_finding_id,
              car_name, track_name, setup_name,
              goal, change_to_try, do_not_change_json,
              success_metric, target_zone_start_pct, target_zone_end_pct,
              planned_notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id, now, now, source_finding_id,
                finding.car_name, finding.track_name, finding.setup_name,
                goal or finding.next_step,
                change_to_try,
                _json(do_not_change or []),
                success_metric or "Speed gain in target zone without CFS worsening.",
                target_zone_start_pct, target_zone_end_pct,
                planned_notes, "planned",
            ),
        )
    conn.close()

    return TestPlan(
        test_plan_id=plan_id,
        created_at=now,
        updated_at=now,
        source_finding_id=source_finding_id,
        car_name=finding.car_name,
        track_name=finding.track_name,
        setup_name=finding.setup_name,
        goal=goal or finding.next_step,
        change_to_try=change_to_try,
        do_not_change=do_not_change or [],
        success_metric=success_metric or "Speed gain in target zone without CFS worsening.",
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
        planned_notes=planned_notes,
        status="planned",
    )


def list_test_plans(
    car_name: str | None = None,
    track_name: str | None = None,
    status: str | None = None,
    db_path: str | Path | None = None,
) -> list[TestPlan]:
    conn = initialize_database(db_path)
    sql = "SELECT * FROM test_plans WHERE 1=1"
    params: list[Any] = []
    if car_name:
        sql += " AND car_name = ?"
        params.append(car_name)
    if track_name:
        sql += " AND track_name = ?"
        params.append(track_name)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results: list[TestPlan] = []
    for r in rows:
        row = dict(r)
        results.append(TestPlan(
            test_plan_id=row["test_plan_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source_finding_id=row["source_finding_id"],
            car_name=row["car_name"],
            track_name=row["track_name"],
            setup_name=row["setup_name"],
            goal=row["goal"],
            change_to_try=row["change_to_try"],
            do_not_change=_load_json(row["do_not_change_json"], []),
            success_metric=row["success_metric"],
            target_zone_start_pct=row["target_zone_start_pct"] or 55.0,
            target_zone_end_pct=row["target_zone_end_pct"] or 70.0,
            planned_notes=row["planned_notes"] or "",
            status=row["status"],
        ))
    return results


def update_test_plan(
    test_plan_id: str,
    *,
    status: str | None = None,
    planned_notes: str | None = None,
    db_path: str | Path | None = None,
) -> TestPlan | None:
    conn = initialize_database(db_path)
    now = _utc_now()
    updates: list[str] = ["updated_at = ?"]
    params: list[Any] = [now]
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if planned_notes is not None:
        updates.append("planned_notes = ?")
        params.append(planned_notes)
    params.append(test_plan_id)
    conn.execute(f"UPDATE test_plans SET {', '.join(updates)} WHERE test_plan_id = ?", params)
    conn.commit()
    conn.close()

    conn = initialize_database(db_path)
    row = conn.execute("SELECT * FROM test_plans WHERE test_plan_id = ?", (test_plan_id,)).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    return TestPlan(
        test_plan_id=r["test_plan_id"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        source_finding_id=r["source_finding_id"],
        car_name=r["car_name"],
        track_name=r["track_name"],
        setup_name=r["setup_name"],
        goal=r["goal"],
        change_to_try=r["change_to_try"],
        do_not_change=_load_json(r["do_not_change_json"], []),
        success_metric=r["success_metric"],
        target_zone_start_pct=r["target_zone_start_pct"] or 55.0,
        target_zone_end_pct=r["target_zone_end_pct"] or 70.0,
        planned_notes=r["planned_notes"] or "",
        status=r["status"],
    )


def build_setup_memory_summary(
    car_name: str | None = None,
    track_name: str | None = None,
    db_path: str | Path | None = None,
) -> SetupMemorySummary:
    conn = initialize_database(db_path)
    sql = "SELECT * FROM notebook_findings WHERE 1=1"
    params: list[Any] = []
    if car_name:
        sql += " AND car_name = ?"
        params.append(car_name)
    if track_name:
        sql += " AND track_name = ?"
        params.append(track_name)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    findings = [_row_to_finding(dict(r)) for r in rows]
    total = len(findings)
    keep = sum(f.verdict == "keep_direction" for f in findings)
    undo = sum(f.verdict == "undo" for f in findings)
    retest = sum(f.verdict == "retest" for f in findings)
    inconclusive = sum(f.verdict == "inconclusive" for f in findings)
    confirmed = sum(f.status == "confirmed" for f in findings)
    rejected = sum(f.status == "rejected" for f in findings)

    # Most common issue from target_zone_classification
    classifications = [f.target_zone_classification for f in findings if f.target_zone_classification]
    most_common = max(set(classifications), key=classifications.count) if classifications else None

    # Best known target zone from keep_direction findings with highest confidence
    keep_findings = [f for f in findings if f.verdict == "keep_direction" and f.confidence_score > 0]
    best_tz = None
    if keep_findings:
        best = max(keep_findings, key=lambda f: f.confidence_score)
        best_tz = f"{best.target_zone_start_pct}–{best.target_zone_end_pct}%"

    latest = findings[0].as_dict() if findings else None

    # Recommended next test from latest needs_retest finding
    needs_retest = [f for f in findings if f.status == "needs_retest"]
    next_test = needs_retest[0].next_step if needs_retest else None

    return SetupMemorySummary(
        car_name=car_name,
        track_name=track_name,
        total_findings=total,
        keep_count=keep,
        undo_count=undo,
        retest_count=retest,
        inconclusive_count=inconclusive,
        confirmed_count=confirmed,
        rejected_count=rejected,
        most_common_issue=most_common,
        best_known_target_zone=best_tz,
        latest_finding=latest,
        recommended_next_test=next_test,
    )
