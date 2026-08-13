from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.analysis.crew_chief_packet import KaizenEvidencePacket
from racelab_engine.analysis.test_director import TestExecution, TestQualityResult


class VehicleConditionEpoch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["known_clear", "unknown", "boundary_observed"]
    identity_sha256: str
    observed_channels: tuple[str, ...] = ()
    incident_baseline: dict[str, float] = Field(default_factory=dict)
    blocker_reasons: tuple[str, ...] = ()


class AppliedControlCertificate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["not_applicable", "stable", "missing", "mutated", "setup_mismatch"]
    control_key: str | None = None
    expected_value: float | None = None
    observed_value: float | None = None
    coverage_fraction: float | None = None
    observed_range: float | None = None
    source_channel: str | None = None
    blocker_reasons: tuple[str, ...] = ()


class StageExperimentContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    vehicle_condition: VehicleConditionEpoch
    applied_control: AppliedControlCertificate


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
    stage_experiment_contexts: dict[Literal["A", "B", "A2"], StageExperimentContext] = Field(default_factory=dict)
    analysis_version: str = "controlled-workflow-aba2-v1"
    execution: TestExecution | None = None
    reproduction_snapshot: dict[str, Any] = Field(default_factory=dict)
    quality: TestQualityResult | None = None
    learning_admitted: bool | None = None


__all__ = [
    "AppliedControlCertificate", "ControlledWorkflow", "StageExperimentContext",
    "VehicleConditionEpoch",
]
