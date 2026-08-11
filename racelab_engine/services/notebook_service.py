from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from racelab_engine.models.notebook import FindingStatus, NotebookFinding
from racelab_engine.storage.db import initialize_database


_FINDING_COLUMNS = """
finding_id, created_at, updated_at,
car_name, track_name, setup_name,
baseline_run_id, test_run_id, comparison_id,
baseline_lap, test_lap,
target_zone_start_pct, target_zone_end_pct,
confidence_score, confidence_tier,
test_discipline_score, target_zone_classification,
summary_headline,
key_takeaways_json, evidence_json, warnings_json,
sector_summaries_json, context_changes_json,
improved_metrics_json, worsened_metrics_json,
notes, tags_json, status
""".strip()

_FINDING_STATUSES: frozenset[str] = frozenset({"saved", "archived"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _load_json(value: str | None, fallback: Any = None) -> Any:
    return json.loads(value) if value else fallback


def _validate_status(status: str) -> FindingStatus:
    if status not in _FINDING_STATUSES:
        raise ValueError("Notebook status is limited to saved or archived")
    return cast(FindingStatus, status)


def find_duplicate(
    comparison_id: str | None,
    baseline_run_id: str | None,
    test_run_id: str | None,
    target_zone_start_pct: float = 55.0,
    target_zone_end_pct: float = 70.0,
    db_path: str | Path | None = None,
) -> NotebookFinding | None:
    """Check for an existing observation with the same source and target zone."""
    if not comparison_id:
        return None
    conn = initialize_database(db_path)
    row = conn.execute(
        f"""
        SELECT {_FINDING_COLUMNS} FROM notebook_findings
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
    confidence_score: float = 0.0,
    confidence_tier: str | None = None,
    test_discipline_score: float = 0.0,
    target_zone_classification: str | None = None,
    summary_headline: str | None = None,
    key_takeaways: list[str] | None = None,
    evidence: list[str] | None = None,
    warnings: list[str] | None = None,
    sector_summaries: list[dict[str, Any]] | None = None,
    context_changes: list[dict[str, Any]] | None = None,
    improved_metrics: list[str] | None = None,
    worsened_metrics: list[str] | None = None,
    notes: str = "",
    tags: list[str] | None = None,
    force: bool = False,
    db_path: str | Path | None = None,
) -> NotebookFinding:
    """Persist an observational finding without policy or test-plan authority."""
    if not force and comparison_id and (existing := find_duplicate(
        comparison_id,
        baseline_run_id,
        test_run_id,
        target_zone_start_pct,
        target_zone_end_pct,
        db_path,
    )):
        return existing

    finding_id = f"finding_{uuid.uuid4().hex[:12]}"
    now = _utc_now()
    status: FindingStatus = "saved"
    finding = NotebookFinding(
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
        confidence_score=confidence_score,
        confidence_tier=confidence_tier,
        test_discipline_score=test_discipline_score,
        target_zone_classification=target_zone_classification,
        summary_headline=summary_headline,
        key_takeaways=key_takeaways or [],
        evidence=evidence or [],
        warnings=warnings or [],
        sector_summaries=sector_summaries or [],
        context_changes=context_changes or [],
        improved_metrics=improved_metrics or [],
        worsened_metrics=worsened_metrics or [],
        notes=notes,
        tags=tags or [],
        status=status,
    )

    conn = initialize_database(db_path)
    with conn:
        conn.execute(
            f"""
            INSERT INTO notebook_findings ({_FINDING_COLUMNS})
            VALUES ({", ".join("?" for _ in range(28))})
            """,
            (
                finding.finding_id,
                finding.created_at,
                finding.updated_at,
                finding.car_name,
                finding.track_name,
                finding.setup_name,
                finding.baseline_run_id,
                finding.test_run_id,
                finding.comparison_id,
                finding.baseline_lap,
                finding.test_lap,
                finding.target_zone_start_pct,
                finding.target_zone_end_pct,
                finding.confidence_score,
                finding.confidence_tier,
                finding.test_discipline_score,
                finding.target_zone_classification,
                finding.summary_headline,
                _json(finding.key_takeaways),
                _json(finding.evidence),
                _json(finding.warnings),
                _json(finding.sector_summaries),
                _json(finding.context_changes),
                _json(finding.improved_metrics),
                _json(finding.worsened_metrics),
                finding.notes,
                _json(finding.tags),
                finding.status,
            ),
        )
    conn.close()
    return finding


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
        target_zone_start_pct=(
            55.0 if row["target_zone_start_pct"] is None else row["target_zone_start_pct"]
        ),
        target_zone_end_pct=(
            70.0 if row["target_zone_end_pct"] is None else row["target_zone_end_pct"]
        ),
        confidence_score=row["confidence_score"] or 0.0,
        confidence_tier=row["confidence_tier"],
        test_discipline_score=row["test_discipline_score"] or 0.0,
        target_zone_classification=row["target_zone_classification"],
        summary_headline=row["summary_headline"],
        key_takeaways=_load_json(row["key_takeaways_json"], []),
        evidence=_load_json(row["evidence_json"], []),
        warnings=_load_json(row["warnings_json"], []),
        sector_summaries=_load_json(row["sector_summaries_json"], []),
        context_changes=_load_json(row["context_changes_json"], []),
        improved_metrics=_load_json(row["improved_metrics_json"], []),
        worsened_metrics=_load_json(row["worsened_metrics_json"], []),
        notes=row["notes"] or "",
        tags=_load_json(row["tags_json"], []),
        status=_validate_status(row["status"] or "saved"),
    )


def list_findings(
    car_name: str | None = None,
    track_name: str | None = None,
    status: FindingStatus | None = None,
    tag: str | None = None,
    db_path: str | Path | None = None,
) -> list[NotebookFinding]:
    if status is not None:
        _validate_status(status)
    conn = initialize_database(db_path)
    sql = f"SELECT {_FINDING_COLUMNS} FROM notebook_findings WHERE 1=1"
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
    findings = [_row_to_finding(dict(row)) for row in rows]
    return [finding for finding in findings if tag in finding.tags] if tag else findings


def get_finding(finding_id: str, db_path: str | Path | None = None) -> NotebookFinding | None:
    conn = initialize_database(db_path)
    row = conn.execute(
        f"SELECT {_FINDING_COLUMNS} FROM notebook_findings WHERE finding_id = ?",
        (finding_id,),
    ).fetchone()
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
    if status is not None:
        _validate_status(status)
    conn = initialize_database(db_path)
    updates: list[str] = ["updated_at = ?"]
    params: list[Any] = [_utc_now()]
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
    with conn:
        conn.execute(
            f"UPDATE notebook_findings SET {', '.join(updates)} WHERE finding_id = ?",
            params,
        )
    conn.close()
    return get_finding(finding_id, db_path)
