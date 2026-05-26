from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field


class AnalyzerStatus(BaseModel):
    status: str = "unavailable"
    missing_channels: list[str] = Field(default_factory=list)
    confidence_penalty: float = 0.0
    notes: list[str] = Field(default_factory=list)


def apply_confidence_penalty(base_score: float, missing_channels: list[str] | None = None) -> float:
    penalty = min(0.6, 0.1 * len(missing_channels or []))
    return max(0.0, min(1.0, base_score - penalty))
