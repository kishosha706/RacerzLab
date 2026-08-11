from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.models.evidence import EvidenceState


ShockSetting = Literal[
    "ls_compression",
    "hs_compression",
    "hs_compression_slope",
    "ls_rebound",
    "hs_rebound",
    "hs_rebound_slope",
    "compression_slope",
    "rebound_slope",
]
ObservedShockSetting = Literal[
    "ls_compression",
    "hs_compression",
    "hs_compression_slope",
    "ls_rebound",
    "hs_rebound",
    "hs_rebound_slope",
]
Pattern = Literal[
    "balanced",
    "low_speed_bump_heavy",
    "low_speed_rebound_heavy",
    "high_speed_bump_heavy",
    "high_speed_rebound_heavy",
    "excessive_high_speed_shoulders",
    "impact_contact_driven",
    "oscillation_recovery_issue",
    "insufficient_evidence",
]
Confidence = Literal["low", "medium", "high"]


class ShockCornerRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corner: Literal["LF", "RF", "LR", "RR"]
    sample_count: int
    rebound_hi_pct: float
    rebound_lo_pct: float
    bump_lo_pct: float
    bump_hi_pct: float
    avg_rebound_in_s: float | None = None
    avg_bump_in_s: float | None = None
    center_pct: float
    rms_in_s: float | None = None
    activity_index: float | None = None
    deflection_delta_range_in: float | None = None
    pattern: Pattern
    confidence: Confidence
    source_lap_numbers: list[int] = Field(default_factory=list)
    repeatability_lap_count: int = Field(default=0, ge=0)
    high_speed_compression_repeatable: bool = False
    high_speed_rebound_repeatable: bool = False
    compression_boundary_stable: bool = False
    rebound_boundary_stable: bool = False
    boundary_sensitivity_patterns: list[str] = Field(default_factory=list)
    setup_values: dict[ObservedShockSetting, int | None] = Field(default_factory=dict)


class ShockReaderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    lap_window: str | None = None
    phase: str | None = None
    zone_start_pct: float | None = None
    zone_end_pct: float | None = None
    boundary_in_s: float
    boundary_basis: str
    bin_width_in_s: float
    setup_snapshot_available: bool
    corners: list[ShockCornerRead]
    setup_authority: Literal["withheld"] = "withheld"
    warnings: list[str]
    evidence_state: EvidenceState = EvidenceState.NEEDS_CONFIRMATION
    source_channels: list[str] = Field(default_factory=list)
    blocker_reasons: list[str] = Field(default_factory=list)
