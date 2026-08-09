"""Immutable measurement contracts and explicit experiment-attempt outcomes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExperimentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SessionResourceSnapshot(ExperimentModel):
    remaining_laps: int | None = Field(default=None, ge=0)
    remaining_time_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fuel_laps_available: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tire_sets_available: int | None = Field(default=None, ge=0)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: Literal["simulator_channels", "user_declared", "unknown"] = "unknown"

    @property
    def feasible_laps(self) -> int | None:
        candidates = [
            value
            for value in (
                self.remaining_laps,
                int(self.fuel_laps_available) if self.fuel_laps_available is not None else None,
            )
            if value is not None
        ]
        return min(candidates) if candidates else None


class MeasurementMissionContract(ExperimentModel):
    contract_id: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    purpose: str = Field(min_length=1)
    procedure: tuple[str, ...] = Field(min_length=1)
    required_channels: tuple[str, ...]
    controlled_variables: tuple[str, ...] = Field(min_length=1)
    required_laps: int = Field(ge=1)
    acceptance_thresholds: tuple[str, ...] = Field(min_length=1)
    integrity_stop_rules: tuple[str, ...] = Field(min_length=1)
    source_event_ids: tuple[str, ...] = ()
    cause_ids: tuple[str, ...] = ()
    telemetry_health_identity: str = Field(min_length=1)
    resource_snapshot: SessionResourceSnapshot

    @model_validator(mode="after")
    def contract_collections_are_canonical(self) -> MeasurementMissionContract:
        for values, label in (
            (self.procedure, "procedure"),
            (self.required_channels, "channel"),
            (self.controlled_variables, "controlled variable"),
            (self.acceptance_thresholds, "acceptance threshold"),
            (self.integrity_stop_rules, "stop rule"),
            (self.source_event_ids, "event"),
            (self.cause_ids, "cause"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"mission-contract {label} values must be non-empty and unique")
        return self


class MeasurementAttempt(ExperimentModel):
    attempt_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    eligible_lap_ids: tuple[str, ...] = ()
    outcome: Literal[
        "completed_clean",
        "no_signal",
        "failed_integrity",
        "infeasible",
        "abandoned",
    ]
    observed_channels: tuple[str, ...] = ()
    integrity_blockers: tuple[str, ...] = ()
    outcome_reasons: tuple[str, ...] = Field(min_length=1)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def attempt_outcome_has_required_evidence(self) -> MeasurementAttempt:
        if self.outcome == "completed_clean" and (
            not self.eligible_lap_ids or self.integrity_blockers
        ):
            raise ValueError("clean attempts require eligible laps and no integrity blocker")
        if self.outcome == "failed_integrity" and not self.integrity_blockers:
            raise ValueError("integrity failures require typed blockers")
        if self.outcome in {"infeasible", "abandoned"} and self.eligible_lap_ids:
            raise ValueError("infeasible and abandoned attempts cannot claim eligible evidence")
        return self


__all__ = [
    "MeasurementAttempt",
    "MeasurementMissionContract",
    "SessionResourceSnapshot",
]
