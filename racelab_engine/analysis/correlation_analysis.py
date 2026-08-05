from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CorrelationPair:
    channel_a: str
    channel_b: str
    label_a: str
    label_b: str
    pearson_r: float | None
    interpretation: str | None = None
    paired_sample_count: int = 0
    paired_coverage: float = 0.0


@dataclass(frozen=True)
class CorrelationResult:
    pairs: list[CorrelationPair] = field(default_factory=list)
    narrative: str | None = None


def _pearson_r(
    xs: list[float | None], ys: list[float | None]
) -> tuple[float | None, int, float]:
    """Return exploratory correlation only when positional coverage is adequate."""
    expected = min(len(xs), len(ys))
    pairs = [
        (x, y)
        for x, y in zip(xs, ys)
        if x is not None and y is not None and math.isfinite(x) and math.isfinite(y)
    ]
    n = len(pairs)
    coverage = n / expected if expected else 0.0
    if n < 20 or coverage < 0.90:
        return None, n, coverage

    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]

    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n

    num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in x_vals))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in y_vals))

    if den_x == 0 or den_y == 0:
        return None, n, coverage

    r = num / (den_x * den_y)
    return max(-1.0, min(1.0, r)), n, coverage


def _interpret_correlation(r: float, label_a: str, label_b: str) -> str:
    abs_r = abs(r)
    direction = "positive" if r > 0 else "negative"
    strength = "strong" if abs_r >= 0.7 else "moderate" if abs_r >= 0.4 else "weak"

    if r > 0:
        return f"{strength.title()} {direction} association: {label_a} and {label_b} move together (r={r:.2f}). This does not establish cause."
    else:
        return f"{strength.title()} {direction} association: {label_a} increases as {label_b} decreases (r={r:.2f}). This does not establish cause."


def correlate_delta_channels(
    delta_channels: dict[str, dict[str, Any]],
) -> CorrelationResult:
    """Correlate speed delta against platform/steering/drag/RPM deltas."""
    pairs_to_check = [
        ("speed_mph", "cfs_ride_height_in", "Speed", "CFS Height"),
        ("speed_mph", "center_rake_fs_in", "Speed", "Center Rake"),
        ("speed_mph", "drag_scrub_suspicion", "Speed", "Drag/Scrub"),
        ("speed_mph", "abs_steering_deg", "Speed", "Steering"),
        ("speed_mph", "rpm", "Speed", "RPM"),
        ("speed_mph", "dynamic_pressure_psf", "Speed", "Dynamic Pressure"),
        ("cfs_ride_height_in", "drag_scrub_suspicion", "CFS Height", "Drag/Scrub"),
        ("cfs_ride_height_in", "center_rake_fs_in", "CFS Height", "Center Rake"),
    ]

    results: list[CorrelationPair] = []
    for ch_a, ch_b, label_a, label_b in pairs_to_check:
        a_data = delta_channels.get(ch_a, {})
        b_data = delta_channels.get(ch_b, {})

        a_deltas = a_data.get("delta_values", [])
        b_deltas = b_data.get("delta_values", [])

        if not a_deltas or not b_deltas:
            continue

        r, paired_count, paired_coverage = _pearson_r(a_deltas, b_deltas)
        if r is None:
            continue

        interpretation = _interpret_correlation(r, label_a, label_b)
        results.append(CorrelationPair(
            channel_a=ch_a,
            channel_b=ch_b,
            label_a=label_a,
            label_b=label_b,
            pearson_r=round(r, 3),
            interpretation=interpretation,
            paired_sample_count=paired_count,
            paired_coverage=paired_coverage,
        ))

    # Build narrative
    narrative: str | None = None
    strong = [p for p in results if p.pearson_r is not None and abs(p.pearson_r) >= 0.5]
    if strong:
        top = strong[0]
        narrative = (
            f"Strongest relationship: {top.interpretation} "
            f"Treat this as exploratory co-variation with {top.label_b.lower()}, not proof of cause."
        )
    else:
        narrative = "No strong correlations detected between speed and platform channels."

    return CorrelationResult(pairs=results, narrative=narrative)
