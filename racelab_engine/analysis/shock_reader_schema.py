from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CornerScope = Literal["LF", "RF", "LR", "RR", "front", "rear", "all"]
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
SemanticDirection = Literal["add", "subtract", "move_more_linear", "move_more_digressive", "leave_alone"]
RecommendationClassification = Literal["fine_tune", "balance_swing", "package_swing", "leave_alone"]
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
SettingDirection = Literal["add", "subtract", "hold", "blocked", "needs_more_evidence"]
SettingMagnitude = Literal["hold", "small", "medium", "big"]
SettingConfidence = Literal["high", "medium", "low", "needs_more_evidence"]


class ShockSettingRecommendation(BaseModel):
    corner: Literal["LF", "RF", "LR", "RR"]
    setting: Literal[
        "ls_compression",
        "hs_compression",
        "hs_compression_slope",
        "ls_rebound",
        "hs_rebound",
        "hs_rebound_slope",
    ]
    display_label: Literal["LS Comp", "HS Comp", "HS-S Comp", "LS Reb", "HS Reb", "HS-S Reb"]
    current_value: int | None = None
    delta: int | None = Field(default=None, ge=-5, le=5)
    suggested_value: int | None = None
    direction: SettingDirection
    magnitude: SettingMagnitude
    confidence: SettingConfidence
    reason_short: str
    goal: str
    tradeoff: str
    watch_for: list[str]
    blocked_reason: str | None = None


class ShockCornerRead(BaseModel):
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
    setup_values: dict[str, int | None] = Field(default_factory=dict)
    setting_recommendations: list[ShockSettingRecommendation] = Field(default_factory=list)


class ShockRecommendation(BaseModel):
    id: str
    corner_scope: CornerScope
    setting: ShockSetting
    display_setting: str
    semantic_direction: SemanticDirection
    numeric_step: int | None = Field(default=None, ge=-5, le=5)
    current_value: int | None = None
    suggested_value: int | None = None
    blocked_by_limit: bool = False
    classification: RecommendationClassification
    goal: str
    tradeoff: str
    next_test: str
    watch_for: list[str]
    confidence: Confidence
    evidence_summary: str
    hidden_debug: dict[str, Any] | None = None


class ShockReaderResponse(BaseModel):
    run_id: str
    lap_window: str | None = None
    phase: str | None = None
    boundary_in_s: float
    bin_width_in_s: float
    setup_snapshot_available: bool
    corners: list[ShockCornerRead]
    recommendations: list[ShockRecommendation]
    warnings: list[str]
