from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

FindingStatus = Literal["saved", "archived"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class NotebookFinding:
    """A read-only observational record with user-managed notes and tags.

    Notebook records deliberately carry no setup-policy verdict, setup change,
    or next-test authority.  P19 controlled workflows own those decisions.
    """

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
    confidence_score: float = 0.0
    confidence_tier: str | None = None
    test_discipline_score: float = 0.0
    target_zone_classification: str | None = None
    summary_headline: str | None = None
    key_takeaways: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sector_summaries: list[dict[str, Any]] = field(default_factory=list)
    context_changes: list[dict[str, Any]] = field(default_factory=list)
    improved_metrics: list[str] = field(default_factory=list)
    worsened_metrics: list[str] = field(default_factory=list)
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
            "confidence_score": self.confidence_score,
            "confidence_tier": self.confidence_tier,
            "test_discipline_score": self.test_discipline_score,
            "target_zone_classification": self.target_zone_classification,
            "summary_headline": self.summary_headline,
            "key_takeaways": self.key_takeaways,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "sector_summaries": self.sector_summaries,
            "context_changes": self.context_changes,
            "improved_metrics": self.improved_metrics,
            "worsened_metrics": self.worsened_metrics,
            "notes": self.notes,
            "tags": self.tags,
            "status": self.status,
        }
