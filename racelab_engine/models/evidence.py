"""Neutral evidence vocabulary shared by models, analysis, API, and UI contracts."""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceState(str, Enum):
    MEASURED = "measured"
    CALCULATED = "calculated"
    ESTIMATED_PROXY = "estimated_proxy"
    OBSERVED_CORRELATION = "observed_correlation"
    CONTROLLED_TEST_EFFECT = "controlled_test_effect"
    UNAVAILABLE = "unavailable"
    BLOCKED_BY_CONTEXT = "blocked_by_context"
    NEEDS_CONFIRMATION = "needs_confirmation"


class EngineeringBlockerSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"
    CRITICAL = "critical"


class EngineeringBlockTarget(str, Enum):
    OBSERVATION = "observation"
    COMPARISON = "comparison"
    PERFORMANCE = "performance"
    MECHANISM = "mechanism"
    COMPONENT = "component"
    SETUP_ATTRIBUTION = "setup_attribution"
    NAVIGATION = "navigation"


class BlockerPhysicalScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    lap_number: int | None = None
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)
    event_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def physical_window_is_complete_and_ordered(self) -> Self:
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("blocker physical windows require both bounds")
        if (
            self.lap_pct_start is not None
            and self.lap_pct_end is not None
            and self.lap_pct_end < self.lap_pct_start
        ):
            raise ValueError("blocker physical window is reversed")
        if len(self.event_ids) != len(set(self.event_ids)):
            raise ValueError("blocker physical event identities must be unique")
        return self


class EngineeringBlocker(BaseModel):
    """Typed limitation; prose explains it but never decides its scope."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    severity: EngineeringBlockerSeverity
    scope: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    blocks: tuple[EngineeringBlockTarget, ...] = ()
    message: str = Field(min_length=1)
    evidence_state: EvidenceState
    source_artifact_ids: tuple[str, ...] = ()
    source_channels: tuple[str, ...] = ()
    physical_scope: BlockerPhysicalScope | None = None
    recovery: str = Field(min_length=1)

    @model_validator(mode="after")
    def typed_scope_is_canonical(self) -> Self:
        if len(self.blocks) != len(set(self.blocks)):
            raise ValueError("engineering blocker targets must be unique")
        if len(self.source_artifact_ids) != len(set(self.source_artifact_ids)):
            raise ValueError("engineering blocker source artifacts must be unique")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("engineering blocker source channels must be unique")
        if self.evidence_state not in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.BLOCKED_BY_CONTEXT,
            EvidenceState.NEEDS_CONFIRMATION,
        }:
            raise ValueError("engineering blockers require a non-authorizing evidence state")
        return self


def engineering_blockers_for(
    blockers: Iterable[EngineeringBlocker],
    *targets: EngineeringBlockTarget,
) -> tuple[EngineeringBlocker, ...]:
    requested = set(targets)
    return tuple(blocker for blocker in blockers if requested.intersection(blocker.blocks))


__all__ = [
    "BlockerPhysicalScope",
    "EngineeringBlocker",
    "EngineeringBlockerSeverity",
    "EngineeringBlockTarget",
    "engineering_blockers_for",
    "EvidenceState",
]
