"""Immutable measurement contracts and explicit experiment-attempt outcomes."""

from __future__ import annotations

import hashlib
import json
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
    schema_version: Literal["p19.measurement-mission.v2"] = (
        "p19.measurement-mission.v2"
    )
    contract_id: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    session_run_ids: tuple[str, ...] = Field(min_length=1)
    source_setup_id: str = Field(min_length=1)
    setup_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    purpose: str = Field(min_length=1)
    procedure: tuple[str, ...] = Field(min_length=1)
    required_channels: tuple[str, ...] = Field(min_length=1)
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
            (self.session_run_ids, "session run"),
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
        if self.run_id not in self.session_run_ids:
            raise ValueError("mission-contract source run must belong to its frozen run scope")
        if self.session_id is None and self.session_run_ids != (self.run_id,):
            raise ValueError("run-scoped mission contracts may freeze only their source run")
        payload = self.model_dump(
            mode="json",
            exclude={"contract_id", "contract_sha256", "created_at"},
        )
        payload["resource_snapshot"].pop("captured_at", None)
        expected_sha256 = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if self.contract_sha256 != expected_sha256:
            raise ValueError("mission-contract hash must bind every immutable field")
        if self.contract_id != f"mission:{expected_sha256[:20]}":
            raise ValueError("mission-contract identity must derive from its content hash")
        return self


class MeasurementAttempt(ExperimentModel):
    schema_version: Literal["p19.measurement-attempt.v2"] = (
        "p19.measurement-attempt.v2"
    )
    attempt_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    setup_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome_authority: Literal["server_derived", "client_attested"] = "client_attested"
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

    @property
    def counts_toward_stop_testing(self) -> bool:
        """Only a server-derived low-information assessment may alter P19 policy."""
        return (
            self.outcome_authority == "server_derived"
            and self.outcome in {"no_signal", "failed_integrity"}
        )

    @model_validator(mode="after")
    def attempt_outcome_has_required_evidence(self) -> MeasurementAttempt:
        for values, label in (
            (self.eligible_lap_ids, "eligible lap"),
            (self.observed_channels, "observed channel"),
            (self.integrity_blockers, "integrity blocker"),
            (self.outcome_reasons, "outcome reason"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(
                    f"measurement-attempt {label} values must be non-empty and unique"
                )
        if any(
            lap_id.rsplit(":", 1)[0] != self.run_id
            for lap_id in self.eligible_lap_ids
        ):
            raise ValueError("measurement-attempt eligible laps must belong to its exact run")
        if self.outcome in {"completed_clean", "no_signal"} and (
            not self.eligible_lap_ids or self.integrity_blockers
        ):
            raise ValueError(
                "clean and no-signal attempts require eligible laps and no integrity blocker"
            )
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
