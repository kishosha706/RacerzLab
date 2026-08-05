from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.analysis.crew_chief_packet import KaizenEvidencePacket
from racelab_engine.analysis.test_director import TestExecution, TestQualityResult


class ControlledWorkflow(BaseModel):
    """Persisted, server-verifiable A/B/A2 test state."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    created_at: datetime
    updated_at: datetime
    status: Literal["planned", "a_recorded", "b_recorded", "a2_recorded", "scored", "cancelled"]
    source_run_id: str
    complaint: str
    packet: KaizenEvidencePacket
    stage_run_ids: dict[Literal["A", "B", "A2"], str] = Field(default_factory=dict)
    stage_eligible_lap_numbers: dict[Literal["A", "B", "A2"], tuple[int, ...]] = Field(default_factory=dict)
    analysis_version: str = "controlled-workflow-aba2-v2"
    execution: TestExecution | None = None
    reproduction_snapshot: dict[str, Any] = Field(default_factory=dict)
    quality: TestQualityResult | None = None
    learning_admitted: bool | None = None


__all__ = ["ControlledWorkflow"]
