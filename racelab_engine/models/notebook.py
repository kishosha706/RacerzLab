from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

FindingStatus = Literal["saved", "confirmed", "rejected", "needs_retest", "archived"]
TestPlanStatus = Literal["planned", "completed", "cancelled"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class NotebookFinding:
    finding_id: str
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
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
    key_takeaways: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sector_summaries: list[dict[str, Any]] = field(default_factory=list)
    setup_changes: list[dict[str, Any]] = field(default_factory=list)
    context_changes: list[dict[str, Any]] = field(default_factory=list)
    improved_metrics: list[str] = field(default_factory=list)
    worsened_metrics: list[str] = field(default_factory=list)
    next_step: str | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    status: FindingStatus = "saved"

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "car_name": self.car_name,
            "track_name": self.track_name,
            "setup_name": self.setup_name,
            "baseline_run_id": self.baseline_run_id,
            "test_run_id": self.test_run_id,
            "comparison_id": self.comparison_id,
            "baseline_lap": self.baseline_lap,
            "test_lap": self.test_lap,
            "target_zone_start_pct": self.target_zone_start_pct,
            "target_zone_end_pct": self.target_zone_end_pct,
            "verdict": self.verdict,
            "confidence_score": self.confidence_score,
            "confidence_tier": self.confidence_tier,
            "test_discipline_score": self.test_discipline_score,
            "target_zone_classification": self.target_zone_classification,
            "summary_headline": self.summary_headline,
            "key_takeaways": self.key_takeaways,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "sector_summaries": self.sector_summaries,
            "setup_changes": self.setup_changes,
            "context_changes": self.context_changes,
            "improved_metrics": self.improved_metrics,
            "worsened_metrics": self.worsened_metrics,
            "next_step": self.next_step,
            "notes": self.notes,
            "tags": self.tags,
            "status": self.status,
        }


@dataclass(frozen=True)
class TestPlan:
    test_plan_id: str
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    source_finding_id: str | None = None
    car_name: str | None = None
    track_name: str | None = None
    setup_name: str | None = None
    goal: str | None = None
    change_to_try: str | None = None
    do_not_change: list[str] = field(default_factory=list)
    success_metric: str | None = None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0
    planned_notes: str = ""
    status: TestPlanStatus = "planned"

    def as_dict(self) -> dict[str, Any]:
        return {
            "test_plan_id": self.test_plan_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_finding_id": self.source_finding_id,
            "car_name": self.car_name,
            "track_name": self.track_name,
            "setup_name": self.setup_name,
            "goal": self.goal,
            "change_to_try": self.change_to_try,
            "do_not_change": self.do_not_change,
            "success_metric": self.success_metric,
            "target_zone_start_pct": self.target_zone_start_pct,
            "target_zone_end_pct": self.target_zone_end_pct,
            "planned_notes": self.planned_notes,
            "status": self.status,
        }


@dataclass(frozen=True)
class SetupMemorySummary:
    car_name: str | None = None
    track_name: str | None = None
    total_findings: int = 0
    keep_count: int = 0
    undo_count: int = 0
    retest_count: int = 0
    inconclusive_count: int = 0
    confirmed_count: int = 0
    rejected_count: int = 0
    most_common_issue: str | None = None
    best_known_target_zone: str | None = None
    latest_finding: dict[str, Any] | None = None
    recommended_next_test: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "car_name": self.car_name,
            "track_name": self.track_name,
            "total_findings": self.total_findings,
            "keep_count": self.keep_count,
            "undo_count": self.undo_count,
            "retest_count": self.retest_count,
            "inconclusive_count": self.inconclusive_count,
            "confirmed_count": self.confirmed_count,
            "rejected_count": self.rejected_count,
            "most_common_issue": self.most_common_issue,
            "best_known_target_zone": self.best_known_target_zone,
            "latest_finding": self.latest_finding,
            "recommended_next_test": self.recommended_next_test,
        }
