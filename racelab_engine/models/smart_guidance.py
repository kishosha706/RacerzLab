"""Deterministic, navigation-only guidance layered over engineering evidence.

These contracts may prioritize where the driver should look or what should be
measured next.  They never create setup authority; that remains owned by the
controlled-test card in the intelligence report.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Workspace = Literal["overview", "laps", "platform", "setup", "engineer", "dial_in"]
MeasurementPriority = Literal[
    "integrity",
    "data_qualification",
    "affected_channel_health",
    "repetition",
    "discrimination",
    "background_health",
]
MeasurementCandidateRejection = Literal[
    "duplicate_candidate_id",
    "unknown_blocker_reference",
    "unauthorized_blocker_claim",
    "unknown_cause_reference",
    "unauthorized_cause_claim",
    "unknown_event_reference",
    "cross_run_event_reference",
    "unavailable_required_channel",
    "affected_channel_health",
    "no_current_planning_value",
]
MEASUREMENT_PRIORITY_ORDER: tuple[MeasurementPriority, ...] = (
    "integrity",
    "data_qualification",
    "affected_channel_health",
    "repetition",
    "discrimination",
    "background_health",
)


def measurement_priority_rank(priority: MeasurementPriority) -> int:
    return MEASUREMENT_PRIORITY_ORDER.index(priority)


class GuidanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class MeasurementDebtItem(GuidanceModel):
    debt_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    recovery_kind: Literal[
        "select_eligible_lap",
        "retry_resource",
        "inspect_missing_channel",
        "repeat_measurement",
        "resume_workflow",
    ]
    workspace: Workspace
    priority: MeasurementPriority = "discrimination"
    blocks_current_move: bool = False
    required_channels: tuple[str, ...] = ()
    resolves_cause_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identities_are_canonical(self) -> MeasurementDebtItem:
        for values, label in (
            (self.required_channels, "channel"),
            (self.resolves_cause_ids, "cause"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"measurement-debt {label} identities must be unique")
        return self


class MeasurementBlocker(GuidanceModel):
    """Planner-owned prerequisite that a candidate may truthfully resolve."""

    blocker_id: str = Field(min_length=1)
    priority: MeasurementPriority
    reason: str = Field(min_length=1)
    affected_channels: tuple[str, ...] = ()
    resolving_candidate_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def blocker_channels_are_canonical(self) -> MeasurementBlocker:
        for values, label in (
            (self.affected_channels, "channel"),
            (self.resolving_candidate_ids, "resolving candidate"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"measurement blocker {label} identities must be unique")
        return self


class MeasurementDebt(GuidanceModel):
    status: Literal["clear", "open", "blocked"]
    summary: str = Field(min_length=1)
    items: tuple[MeasurementDebtItem, ...] = ()

    @model_validator(mode="after")
    def status_matches_items(self) -> MeasurementDebt:
        if self.status == "clear" and self.items:
            raise ValueError("clear measurement debt cannot contain open items")
        if self.status != "clear" and not self.items:
            raise ValueError("open measurement debt requires a recovery item")
        if len({item.debt_id for item in self.items}) != len(self.items):
            raise ValueError("measurement-debt identities must be unique")
        return self


class MeasurementCandidate(GuidanceModel):
    candidate_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    procedure: tuple[str, ...] = Field(min_length=1)
    required_channels: tuple[str, ...] = ()
    available_channels: tuple[str, ...] = ()
    resolves_blocker_ids: tuple[str, ...] = ()
    distinguishes_cause_ids: tuple[str, ...] = ()
    required_laps: int = Field(ge=1)
    target_phase: str = Field(min_length=1)
    acceptance_thresholds: tuple[str, ...] = Field(min_length=1)
    stop_rule: str = Field(min_length=1)
    controlled_variables: tuple[str, ...] = Field(min_length=1)
    source_event_ids: tuple[str, ...] = ()
    authority: Literal["measurement_only"] = "measurement_only"

    @model_validator(mode="after")
    def measurement_contract_is_canonical(self) -> MeasurementCandidate:
        for values, label in (
            (self.required_channels, "required channel"),
            (self.available_channels, "available channel"),
            (self.resolves_blocker_ids, "blocker"),
            (self.distinguishes_cause_ids, "cause"),
            (self.source_event_ids, "event"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"measurement {label} identities must be unique")
        return self

    @property
    def feasible(self) -> bool:
        return set(self.required_channels).issubset(self.available_channels)


class MeasurementCandidateEvaluation(GuidanceModel):
    """Inspectable deterministic evaluation; it carries no probability claim."""

    candidate_id: str = Field(min_length=1)
    admissible: bool
    priority: MeasurementPriority
    resolved_blocker_ids: tuple[str, ...] = ()
    distinguished_cause_ids: tuple[str, ...] = ()
    resolved_source_event_ids: tuple[str, ...] = ()
    required_new_laps: int = Field(ge=1)
    rejection_reasons: tuple[MeasurementCandidateRejection, ...] = ()
    priority_rank: int = Field(ge=0)
    blocker_coverage: int = Field(ge=0)
    cause_coverage: int = Field(ge=0)

    @model_validator(mode="after")
    def admissibility_matches_rejections(self) -> MeasurementCandidateEvaluation:
        if self.admissible == bool(self.rejection_reasons):
            raise ValueError("candidate admissibility must match its rejection reasons")
        if self.priority_rank != measurement_priority_rank(self.priority):
            raise ValueError("candidate priority rank must match the declared priority")
        if self.blocker_coverage != len(self.resolved_blocker_ids):
            raise ValueError("candidate blocker coverage must match resolved blockers")
        if self.cause_coverage != len(self.distinguished_cause_ids):
            raise ValueError("candidate cause coverage must match resolved causes")
        for values, label in (
            (self.resolved_blocker_ids, "blocker"),
            (self.distinguished_cause_ids, "cause"),
            (self.resolved_source_event_ids, "event"),
            (self.rejection_reasons, "rejection"),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"candidate evaluation {label} identities must be unique")
        return self


class MeasurementSelectionAudit(GuidanceModel):
    """Stable planner trace suitable for hostile-contract tests and diagnostics."""

    selected_candidate_id: str | None = Field(default=None, min_length=1)
    evaluations: tuple[MeasurementCandidateEvaluation, ...]
    known_blocker_ids: tuple[str, ...] = ()
    known_cause_ids: tuple[str, ...] = ()
    known_event_ids: tuple[str, ...] = ()
    duplicate_candidate_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def selection_is_admissible_and_unique(self) -> MeasurementSelectionAudit:
        evaluation_ids = [item.candidate_id for item in self.evaluations]
        if self.selected_candidate_id is not None:
            selected = [
                item
                for item in self.evaluations
                if item.candidate_id == self.selected_candidate_id and item.admissible
            ]
            if len(selected) != 1 or self.duplicate_candidate_ids:
                raise ValueError("measurement selection must identify one admissible candidate")
        if len(set(self.duplicate_candidate_ids)) != len(self.duplicate_candidate_ids):
            raise ValueError("duplicate candidate audit identities must be unique")
        if self.duplicate_candidate_ids and self.selected_candidate_id is not None:
            raise ValueError("duplicate candidate identities fail selection closed")
        if not self.duplicate_candidate_ids and len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("candidate evaluation identities must be unique")
        return self


class PreflightCheck(GuidanceModel):
    check_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    state: Literal["verified", "required", "blocked"]
    detail: str = Field(min_length=1)


class ControlledTestPreflight(GuidanceModel):
    workflow_id: str = Field(min_length=1)
    stage: Literal["A", "B", "A2", "complete"]
    status: Literal["ready", "blocked", "complete"]
    title: str = Field(min_length=1)
    checks: tuple[PreflightCheck, ...]
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def stage_status_is_honest(self) -> ControlledTestPreflight:
        states = {check.state for check in self.checks}
        if self.status == "ready" and ("blocked" in states or self.blocker_reasons):
            raise ValueError("ready preflight cannot contain blockers")
        if self.status == "blocked" and not ("blocked" in states or self.blocker_reasons):
            raise ValueError("blocked preflight requires a blocker")
        if self.status == "complete" and self.stage != "complete":
            raise ValueError("complete preflight requires the complete stage")
        return self


class NextTrustworthyMove(GuidanceModel):
    move_id: str = Field(min_length=1)
    kind: Literal[
        "recover",
        "qualify",
        "diagnose",
        "measure",
        "controlled_test",
        "compare",
        "decide",
    ]
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    workspace: Workspace
    authority: Literal["navigation_only", "setup_authorized"] = "navigation_only"
    run_id: str = Field(min_length=1)
    workflow_id: str | None = Field(default=None, min_length=1)
    workflow_updated_at: datetime | None = None
    control_key: str | None = Field(default=None, min_length=1)
    lap_number: int | None = Field(default=None, ge=1)
    window_start_lap: int | None = Field(default=None, ge=1)
    window_end_lap: int | None = Field(default=None, ge=1)
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)
    source_event_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def authority_and_scope_are_consistent(self) -> NextTrustworthyMove:
        if (self.workflow_id is None) != (self.workflow_updated_at is None):
            raise ValueError("workflow identity and revision must be supplied together")
        if self.authority == "setup_authorized":
            if (
                self.kind != "controlled_test"
                or not self.source_event_ids
                or self.blocker_reasons
                or self.workflow_id is None
                or self.workflow_updated_at is None
                or self.control_key is None
            ):
                raise ValueError(
                    "setup authority requires one exact workflow-bound, control-bound, "
                    "unblocked evidence-linked test"
                )
        elif self.control_key is not None:
            raise ValueError("navigation-only moves cannot publish a setup control")
        if (self.window_start_lap is None) != (self.window_end_lap is None):
            raise ValueError("lap-window bounds must be supplied together")
        if (
            self.window_start_lap is not None
            and self.window_end_lap is not None
            and self.window_start_lap > self.window_end_lap
        ):
            raise ValueError("lap-window bounds must be ordered")
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("physical-position bounds must be supplied together")
        if (
            self.lap_pct_start is not None
            and self.lap_pct_end is not None
            and self.lap_pct_start >= self.lap_pct_end
        ):
            raise ValueError("physical-position bounds must be ordered and non-zero")
        if any(not value for value in self.source_event_ids) or len(
            set(self.source_event_ids)
        ) != len(self.source_event_ids):
            raise ValueError("next-move source event identities must be unique")
        return self


class AttentionItem(GuidanceModel):
    attention_id: str = Field(min_length=1)
    state: Literal["new", "changed", "resolved"]
    label: str = Field(min_length=1)
    workspace: Workspace
    run_id: str = Field(min_length=1)
    fingerprint: str = Field(min_length=16)


class SmartGuidance(GuidanceModel):
    mission_stage: Literal[
        "qualify", "diagnose", "measure", "test", "compare", "decide", "certified"
    ]
    next_trustworthy_move: NextTrustworthyMove
    measurement_debt: MeasurementDebt
    test_preflight: ControlledTestPreflight | None = None
    attention_items: tuple[AttentionItem, ...] = ()
    contextual_questions: tuple[str, ...] = ()


__all__ = [
    "AttentionItem",
    "ControlledTestPreflight",
    "GuidanceModel",
    "MeasurementDebt",
    "MeasurementDebtItem",
    "MeasurementCandidate",
    "MeasurementBlocker",
    "MeasurementCandidateEvaluation",
    "MeasurementCandidateRejection",
    "MEASUREMENT_PRIORITY_ORDER",
    "MeasurementPriority",
    "MeasurementSelectionAudit",
    "measurement_priority_rank",
    "NextTrustworthyMove",
    "PreflightCheck",
    "SmartGuidance",
    "Workspace",
]
