"""Bounded public projection of backend-owned P19/P20 engineering awareness."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.engineering_awareness import (
    MechanismEpisode,
    StateDriftFinding,
    TrustBudget,
)
from racelab_engine.models.engineering_context import ControlMutationEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind


class ProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AwarenessRequestIdentity(ProjectionModel):
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    reasoning_snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class PrimaryEngineeringState(ProjectionModel):
    state_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    mechanism: MechanismKind
    lap_number: int = Field(ge=0)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0)
    lap_pct_end: float = Field(ge=0.0, le=100.0)
    lap_pct_peak: float = Field(ge=0.0, le=100.0)
    evidence_state: EvidenceState
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_channels: tuple[str, ...] = Field(min_length=1)
    authority: Literal["observation_only"] = "observation_only"


class SubsystemAwarenessState(ProjectionModel):
    mechanism: MechanismKind
    status: Literal["ready", "blocked", "no_finding", "unavailable"]
    summary: str = Field(min_length=1)
    phase: str | None = None
    lap_number: int | None = Field(default=None, ge=0)
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)
    evidence_state: EvidenceState
    source_artifact_ids: tuple[str, ...] = ()
    source_channels: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def state_preserves_blockers(self) -> SubsystemAwarenessState:
        if self.status == "ready" and self.blocker_reasons:
            raise ValueError("ready subsystem state cannot hide blockers")
        if self.status in {"blocked", "unavailable"} and not self.blocker_reasons:
            raise ValueError("blocked/unavailable subsystem state requires blockers")
        return self


class SetupLeverageState(ProjectionModel):
    control_key: str = Field(min_length=1)
    states: tuple[
        Literal[
            "relevant",
            "needs_measurement",
            "prior_keep",
            "prior_undo",
            "blocked",
            "authorized",
            "active_test",
        ],
        ...,
    ] = Field(min_length=1)
    basis: tuple[str, ...] = Field(min_length=1)
    workflow_ids: tuple[str, ...] = ()
    source_event_ids: tuple[str, ...] = ()
    authority_source: Literal["p19_reasoning_snapshot"] = "p19_reasoning_snapshot"


class ExpectedVsObservedState(ProjectionModel):
    workflow_id: str = Field(min_length=1)
    control_key: str | None = None
    metric: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    mechanism_state: Literal[
        "supported", "weakened", "unchanged", "inconclusive", "invalid"
    ]
    control_response: Literal[
        "matched", "missed", "inconclusive", "unavailable", "invalid"
    ]
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    countereffects: tuple[str, ...] = ()
    mechanism_reason: str = Field(min_length=1)
    control_response_reason: str = Field(min_length=1)
    policy_reason: str = Field(min_length=1)


class AwarenessMissionState(ProjectionModel):
    kind: Literal[
        "controlled_test",
        "measurement_mission",
        "discriminator",
        "stop_testing",
        "blocked",
    ]
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    setup_authorized: bool
    contract_id: str | None = None
    blocker_reasons: tuple[str, ...] = ()


class AwarenessArtifactVersion(ProjectionModel):
    artifact_key: str = Field(min_length=1)
    version: str = Field(min_length=1)


class EngineeringAwarenessProjection(ProjectionModel):
    schema_version: Literal["p20.awareness.v1"] = "p20.awareness.v1"
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    reasoning_snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_identity: AwarenessRequestIdentity
    generated_at: datetime
    cache_state: Literal["cold", "warm"]
    build_duration_ms: float = Field(ge=0.0, allow_inf_nan=False)
    profile_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    authority_state: Literal["observation", "measurement", "controlled_setup", "blocked"]
    setup_authorized: bool
    trust_budget: TrustBudget
    primary_state: PrimaryEngineeringState | None = None
    subsystem_states: tuple[SubsystemAwarenessState, ...] = Field(min_length=10, max_length=10)
    episodes: tuple[MechanismEpisode, ...] = ()
    state_drift_status: Literal["ready", "no_finding", "blocked", "unavailable"]
    state_drift_findings: tuple[StateDriftFinding, ...] = ()
    state_drift_blocker_reasons: tuple[str, ...] = ()
    setup_leverage_states: tuple[SetupLeverageState, ...] = ()
    expected_vs_observed: tuple[ExpectedVsObservedState, ...] = ()
    control_mutations: tuple[ControlMutationEvent, ...] = ()
    knowledge_debt: tuple[str, ...] = ()
    current_mission: AwarenessMissionState
    artifact_versions: tuple[AwarenessArtifactVersion, ...] = Field(min_length=1)
    raw_trace_included: Literal[False] = False

    @model_validator(mode="after")
    def projection_cannot_reinterpret_backend_authority(
        self,
    ) -> EngineeringAwarenessProjection:
        if self.request_identity.run_id != self.run_id:
            raise ValueError("awareness request identity must match the exact run")
        if self.request_identity.session_id != self.session_id:
            raise ValueError("awareness request identity must match the exact session scope")
        if (
            self.request_identity.reasoning_snapshot_id != self.reasoning_snapshot_id
            or self.request_identity.state_revision != self.state_revision
        ):
            raise ValueError("awareness request identity must bind snapshot and revision")
        if self.setup_authorized != (self.authority_state == "controlled_setup"):
            raise ValueError("awareness cannot manufacture setup authority")
        if self.state_drift_status == "ready" and (
            not self.state_drift_findings or self.state_drift_blocker_reasons
        ):
            raise ValueError("ready state drift requires findings and no blockers")
        if self.state_drift_status in {"blocked", "unavailable"} and (
            self.state_drift_findings or not self.state_drift_blocker_reasons
        ):
            raise ValueError("blocked/unavailable state drift requires blockers only")
        if self.state_drift_status == "no_finding" and (
            self.state_drift_findings or self.state_drift_blocker_reasons
        ):
            raise ValueError("no-finding state drift cannot carry findings or blockers")
        mechanisms = [state.mechanism for state in self.subsystem_states]
        expected = {item for item in MechanismKind if item is not MechanismKind.UNCLASSIFIED}
        if set(mechanisms) != expected or len(mechanisms) != len(set(mechanisms)):
            raise ValueError("awareness projection requires every mechanism family exactly once")
        return self


__all__ = [
    "AwarenessArtifactVersion",
    "AwarenessMissionState",
    "AwarenessRequestIdentity",
    "EngineeringAwarenessProjection",
    "ExpectedVsObservedState",
    "PrimaryEngineeringState",
    "SetupLeverageState",
    "SubsystemAwarenessState",
]
