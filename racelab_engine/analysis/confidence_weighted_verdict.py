from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ConfidenceTier = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ConfidenceWeightedVerdict:
    verdict: str  # keep_direction | undo | retest | inconclusive
    base_confidence: float
    adjusted_confidence: float
    tier: ConfidenceTier
    penalties: list[str] = field(default_factory=list)
    boosts: list[str] = field(default_factory=list)
    recommendation: str | None = None


def _compute_tier(confidence: float) -> ConfidenceTier:
    if confidence >= 0.7:
        return "high"
    elif confidence >= 0.4:
        return "medium"
    else:
        return "low"


def apply_confidence_weights(
    verdict: str,
    base_confidence: float,
    *,
    discipline_label: str,
    context_problems: int,
    has_transients: bool = False,
    has_shock_noise: bool = False,
    setup_groups_changed: int = 0,
    missing_motion_ratios: bool = False,
    is_same_run: bool = False,
) -> ConfidenceWeightedVerdict:
    """Adjust verdict confidence based on test quality factors."""
    if is_same_run:
        return ConfidenceWeightedVerdict(
            verdict="inconclusive",
            base_confidence=base_confidence,
            adjusted_confidence=0.0,
            tier="low",
            penalties=["Same run compared — no delta to measure."],
            recommendation="Import a second run with a controlled change.",
        )

    confidence = base_confidence
    penalties: list[str] = []
    boosts: list[str] = []

    # Discipline penalties
    if discipline_label == "weak":
        penalties.append("Low test discipline: too many variables changed.")
        confidence -= 0.25
    elif discipline_label == "mixed":
        penalties.append("Mixed test discipline: multiple setup groups changed.")
        confidence -= 0.15
    elif discipline_label == "invalid":
        penalties.append("Invalid test: uncontrolled conditions.")
        confidence -= 0.4

    # Context penalties
    if context_problems > 0:
        penalties.append(f"{context_problems} context problem(s) (weather, draft, run length).")
        confidence -= 0.1 * context_problems

    # Transient penalty
    if has_transients:
        penalties.append("High-G transients detected — aero proxy confidence reduced.")
        confidence -= 0.15

    # Shock noise penalty
    if has_shock_noise:
        penalties.append("High shock activity — platform is noisy.")
        confidence -= 0.1

    # Setup scope penalty
    if setup_groups_changed >= 3:
        penalties.append(f"{setup_groups_changed} setup groups changed — attribution unclear.")
        confidence -= 0.1
    elif setup_groups_changed == 1:
        boosts.append("Single setup group changed — clean test.")
        confidence += 0.05

    # Motion ratio penalty
    if missing_motion_ratios:
        penalties.append("Missing motion ratios — aero proxy estimates are less reliable.")
        confidence -= 0.05

    # Discipline boost
    if discipline_label == "clean":
        boosts.append("Clean test discipline.")
        confidence += 0.1

    # Clamp
    confidence = max(0.0, min(1.0, confidence))
    tier = _compute_tier(confidence)

    # Recommendation
    if tier == "high":
        recommendation = f"High confidence ({confidence:.0%}). {verdict.replace('_', ' ').title()}."
    elif tier == "medium":
        recommendation = f"Medium confidence ({confidence:.0%}). Review evidence before acting."
    else:
        recommendation = f"Low confidence ({confidence:.0%}). Gather more data before concluding."

    return ConfidenceWeightedVerdict(
        verdict=verdict,
        base_confidence=base_confidence,
        adjusted_confidence=round(confidence, 2),
        tier=tier,
        penalties=penalties,
        boosts=boosts,
        recommendation=recommendation,
    )
