from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from racelab_engine.analysis.constants import (
    SPEED_NOISE_THRESHOLD,
    CFS_WORSEN_THRESHOLD,
    STEERING_CHANGE_THRESHOLD,
    DRAG_CHANGE_THRESHOLD,
    RPM_CHANGE_THRESHOLD,
    RELIABLE_DISCIPLINES,
)

GainClass = Literal[
    "stable_gain",
    "risky_gain",
    "platform_sensitive_gain",
    "driver_input_gain",
    "drag_reduction",
    "mechanical_balance_improvement",
    "inconclusive",
]


@dataclass(frozen=True)
class TargetZoneClassification:
    gain_class: GainClass
    label: str
    confidence: float  # 0-1
    reasoning: list[str] = field(default_factory=list)


def classify_target_zone(
    avg_speed_delta: float | None,
    min_cfs_delta: float | None,
    avg_steering_delta: float | None,
    avg_drag_delta: float | None,
    avg_rpm_delta: float | None,
    discipline_label: str,
) -> TargetZoneClassification:
    """Classify what kind of gain/loss occurred in the target zone."""
    if avg_speed_delta is None:
        return TargetZoneClassification(
            gain_class="inconclusive",
            label="No speed data",
            confidence=0.0,
            reasoning=["Speed delta unavailable in target zone."],
        )

    reasoning: list[str] = []
    speed = avg_speed_delta
    gained = speed > SPEED_NOISE_THRESHOLD
    lost = speed < -SPEED_NOISE_THRESHOLD

    if not gained and not lost:
        return TargetZoneClassification(
            gain_class="inconclusive",
            label="No meaningful change",
            confidence=0.3,
            reasoning=[f"Speed delta {speed:+.2f} mph is within noise range."],
        )

    required_context = {
        "CFS ride height": min_cfs_delta,
        "steering": avg_steering_delta,
        "drag/scrub suspicion": avg_drag_delta,
    }
    missing_context = [label for label, value in required_context.items() if value is None]
    if missing_context:
        return TargetZoneClassification(
            gain_class="inconclusive",
            label="Observed speed change; supporting evidence unavailable",
            confidence=0.2,
            reasoning=[
                f"Speed changed by {speed:+.2f} mph.",
                f"Missing comparison evidence: {', '.join(missing_context)}.",
            ],
        )

    # Gather signals
    steering_higher = avg_steering_delta is not None and avg_steering_delta > STEERING_CHANGE_THRESHOLD
    steering_lower = avg_steering_delta is not None and avg_steering_delta < -STEERING_CHANGE_THRESHOLD
    drag_higher = avg_drag_delta is not None and avg_drag_delta > DRAG_CHANGE_THRESHOLD
    drag_lower = avg_drag_delta is not None and avg_drag_delta < -DRAG_CHANGE_THRESHOLD
    rpm_higher = avg_rpm_delta is not None and avg_rpm_delta > RPM_CHANGE_THRESHOLD
    rpm_lower = avg_rpm_delta is not None and avg_rpm_delta < -RPM_CHANGE_THRESHOLD

    cfs_ok = min_cfs_delta >= CFS_WORSEN_THRESHOLD
    cfs_worse = min_cfs_delta is not None and min_cfs_delta < CFS_WORSEN_THRESHOLD

    if gained:
        discipline_ok = discipline_label in RELIABLE_DISCIPLINES
        # Speed improved — classify why
        if cfs_ok and not drag_higher and not steering_higher:
            gain_class: GainClass = "stable_gain"
            label = "Stable gain"
            confidence = 0.75 if discipline_ok else 0.55
            reasoning.append(f"Speed +{speed:.2f} mph with stable platform and no drag increase.")
        elif cfs_worse and not drag_higher:
            gain_class = "risky_gain"
            label = "Risky gain"
            confidence = 0.5
            reasoning.append(f"Speed +{speed:.2f} mph but CFS worsened by {min_cfs_delta:.3f} in.")
        elif steering_lower:
            gain_class = "driver_input_gain"
            label = "Driver-input gain"
            confidence = 0.55
            reasoning.append(f"Speed +{speed:.2f} mph with reduced steering ({avg_steering_delta:.2f}°).")
        elif drag_lower:
            gain_class = "drag_reduction"
            label = "Lower drag/scrub suspicion"
            confidence = 0.6
            reasoning.append(f"Speed +{speed:.2f} mph with drag/scrub delta {avg_drag_delta:.3f}.")
        elif rpm_higher:
            gain_class = "mechanical_balance_improvement"
            label = "Speed gain with higher RPM"
            confidence = 0.5
            reasoning.append(f"Speed +{speed:.2f} mph with RPM +{avg_rpm_delta:.0f}.")
        else:
            gain_class = "platform_sensitive_gain"
            label = "Platform-sensitive gain"
            confidence = 0.45
            reasoning.append(f"Speed +{speed:.2f} mph but platform context is mixed.")
    else:
        # Speed lost
        if cfs_worse:
            gain_class = "risky_gain"
            label = "Platform-related loss"
            confidence = 0.6
            reasoning.append(f"Speed {speed:.2f} mph with CFS worsening {min_cfs_delta:.3f} in.")
        elif drag_higher:
            gain_class = "drag_reduction"
            label = "Higher drag/scrub suspicion"
            confidence = 0.55
            reasoning.append(f"Speed {speed:.2f} mph with drag/scrub increase {avg_drag_delta:.3f}.")
        elif steering_higher:
            gain_class = "driver_input_gain"
            label = "Driver-related loss"
            confidence = 0.5
            reasoning.append(f"Speed {speed:.2f} mph with more steering ({avg_steering_delta:.2f}°).")
        else:
            # Speed lost, and no clear platform/drag/driver signal
            if rpm_higher and avg_rpm_delta is not None:
                gain_class = "inconclusive"
                label = "Speed loss with higher RPM"
                confidence = 0.4
                reasoning.append(f"Speed {speed:+.2f} mph lost, but RPM increased (+{avg_rpm_delta:.0f}).")
            elif rpm_lower and avg_rpm_delta is not None:
                gain_class = "inconclusive"
                label = "Speed loss with lower RPM"
                confidence = 0.3
                reasoning.append(f"Speed {speed:+.2f} mph lost, and RPM also decreased ({avg_rpm_delta:+.0f}).")
            else:
                gain_class = "inconclusive"
                label = "Unexplained loss"
                confidence = 0.35
                reasoning.append(f"Speed {speed:+.2f} mph without clear platform/drag/driver signal.")

    return TargetZoneClassification(
        gain_class=gain_class,
        label=label,
        confidence=confidence,
        reasoning=reasoning,
    )
