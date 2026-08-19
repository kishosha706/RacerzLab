from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.analysis.crew_chief_packet import KaizenEvidencePacket
from racelab_engine.analysis.test_director import (
    TestExecution,
    TestQualityResult,
    score_test_execution,
)
from racelab_engine.models.engineering_case import ControlledResponseReceipt


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
    p32_opportunity_id: str | None = None
    p32_projection_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    engineering_knowledge_projection_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    stage_run_ids: dict[Literal["A", "B", "A2"], str] = Field(default_factory=dict)
    stage_eligible_lap_numbers: dict[Literal["A", "B", "A2"], tuple[int, ...]] = Field(default_factory=dict)
    stage_experiment_contexts: dict[Literal["A", "B", "A2"], StageExperimentContext] = Field(default_factory=dict)
    analysis_version: str = "controlled-workflow-aba2-v1"
    execution: TestExecution | None = None
    reproduction_snapshot: dict[str, Any] = Field(default_factory=dict)
    quality: TestQualityResult | None = None
    controlled_response_receipt: ControlledResponseReceipt | None = None
    learning_admitted: bool | None = None
    learning_capture_state: Literal["not_applicable", "captured", "blocked"] = (
        "not_applicable"
    )
    learning_capture_experience_id: str | None = Field(
        default=None, pattern=r"^p33x_[0-9a-f]{24}$"
    )
    learning_capture_experience_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    learning_capture_blocker_reason: str | None = Field(
        default=None, min_length=1, max_length=240
    )

    @model_validator(mode="after")
    def invalid_or_incomplete_tests_withhold_performance_memory(
        self,
    ) -> ControlledWorkflow:
        performance_identity = (
            self.p32_opportunity_id,
            self.p32_projection_sha256,
            self.engineering_knowledge_projection_sha256,
        )
        if any(value is None for value in performance_identity) != all(
            value is None for value in performance_identity
        ):
            raise ValueError("canonical P32 workflow identity must be complete")
        p352_binding = self.reproduction_snapshot.get(
            "p352_performance_opportunity_binding"
        )
        if all(value is not None for value in performance_identity) and (
            p352_binding is None
        ):
            raise ValueError("canonical P32 workflow identity requires its receipt")
        if p352_binding is not None and (
            not isinstance(p352_binding, dict)
            or p352_binding.get("p32_opportunity_id") != self.p32_opportunity_id
            or p352_binding.get("p32_projection_sha256")
            != self.p32_projection_sha256
            or p352_binding.get("engineering_knowledge_projection_sha256")
            != self.engineering_knowledge_projection_sha256
        ):
            raise ValueError("canonical P32 workflow receipt and identity disagree")
        execution = self.execution
        quality = self.quality
        stages = ("A", "B", "A2")
        stage_run_ids = tuple(self.stage_run_ids.get(stage) for stage in stages)
        stage_laps = tuple(self.stage_eligible_lap_numbers.get(stage, ()) for stage in stages)
        complete_scope = (
            self.status == "scored"
            and execution is not None
            and quality is not None
            and quality.protocol_valid
            and quality.verdict != "invalid"
            and score_test_execution(execution) == quality
            and all(stage_run_ids)
            and len(set(stage_run_ids)) == 3
            and all(
                len(laps) >= 3
                and len(laps) == len(set(laps))
                for laps in stage_laps
            )
        )
        if self.controlled_response_receipt is not None and (
            self.status != "scored"
            or self.controlled_response_receipt.workflow_id != self.workflow_id
            or tuple(
                item.run_id for item in self.controlled_response_receipt.stages
            )
            != tuple(self.stage_run_ids.get(stage) for stage in stages)
        ):
            raise ValueError(
                "controlled response receipt must bind the exact scored A/B/A2 workflow"
            )
        if self.status == "scored" and self.controlled_response_receipt is None:
            # Persisted pre-P35.4.3 workflows remain readable. New scoring paths
            # always attach a receipt before persistence.
            pass
        if execution is not None and not complete_scope and any(
            value is not None
            for value in (
                execution.time_origin_phase,
                execution.time_origin_pct,
                execution.downstream_carry_effect_s,
            )
        ):
            self.execution = execution.model_copy(
                update={
                    "time_origin_phase": None,
                    "time_origin_pct": None,
                    "downstream_carry_effect_s": None,
                }
            )
        has_experience_identity = (
            self.learning_capture_experience_id is not None
            and self.learning_capture_experience_sha256 is not None
        )
        if (
            (self.learning_capture_experience_id is None)
            != (self.learning_capture_experience_sha256 is None)
        ):
            raise ValueError(
                "P33 learning-capture experience identity must be complete"
            )
        if self.learning_capture_state == "not_applicable" and (
            has_experience_identity or self.learning_capture_blocker_reason is not None
        ):
            raise ValueError(
                "non-attempted P33 learning capture cannot claim an experience or blocker"
            )
        if self.learning_capture_state == "captured" and (
            not has_experience_identity
            or self.learning_capture_blocker_reason is not None
        ):
            raise ValueError(
                "captured P33 learning requires its exact experience and no blocker"
            )
        if self.learning_capture_state == "blocked" and (
            not has_experience_identity
            or self.learning_capture_blocker_reason is None
        ):
            raise ValueError(
                "blocked P33 learning requires its attempted experience and safe blocker"
            )
        if (
            self.status != "scored"
            and self.learning_capture_state != "not_applicable"
        ):
            raise ValueError(
                "P33 workflow learning capture is exclusive to final scored truth"
            )
        return self


__all__ = [
    "AppliedControlCertificate", "ControlledWorkflow", "StageExperimentContext",
    "VehicleConditionEpoch",
]
