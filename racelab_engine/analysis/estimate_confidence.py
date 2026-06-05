"""Confidence tracking for physics estimates.

Every advanced vehicle-dynamics estimate returns an EstimateConfidence
so callers can assess reliability, missing inputs, and assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ConfidenceTier = Literal["high", "medium", "low", "very_low", "unavailable"]


@dataclass(frozen=True)
class EstimateConfidence:
    score: float
    tier: ConfidenceTier
    missing_inputs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    validity_reason: str | None = None


def confidence_from_missing(
    required_inputs: list[str],
    provided_inputs: set[str],
    assumptions: list[str] | None = None,
) -> EstimateConfidence:
    """Build an EstimateConfidence based on which required inputs are missing.

    Rules:
    - All present → high (score 0.90)
    - Some missing → low (score 0.40) with missing_inputs listed
    - All missing → unavailable (score 0.0)
    """
    missing = [k for k in required_inputs if k not in provided_inputs]
    assumptions_list = assumptions or []
    return (
        EstimateConfidence(
            score=0.90,
            tier="high",
            assumptions=assumptions_list,
            validity_reason="No required inputs specified.",
        )
        if not required_inputs
        else EstimateConfidence(
            score=0.40,
            tier="low",
            missing_inputs=missing,
            assumptions=assumptions_list,
            validity_reason=f"Missing inputs: {', '.join(missing)}.",
        )
        if missing
        else EstimateConfidence(
            score=0.90,
            tier="high",
            assumptions=assumptions_list,
            validity_reason="All required inputs available.",
        )
    )
