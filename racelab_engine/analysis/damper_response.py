"""Damper/suspension response metrics based on measured shaft motion only."""

from __future__ import annotations

import math
from statistics import mean, median
from typing import Any, Literal

from pydantic import Field

from racelab_engine.analysis.p3_common import finite, lap_number, lap_pct, percentile, qualify_phase_engine, rms, values
from racelab_engine.analysis.p3_contracts import DAMPER_RESPONSE_CONTRACT
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary


DAMPER_PHASES = {
    "bump_curb", "brake_application", "threshold_braking", "brake_release", "entry",
    "center", "apex_region", "initial_throttle", "full_throttle_exit", "straight", "transition",
}
_CORNERS = ("lf", "rf", "lr", "rr")
_BINS = (-math.inf, -10.0, -5.0, -1.0, 0.0, 1.0, 5.0, 10.0, math.inf)
_BIN_LABELS = ("<-10", "-10:-5", "-5:-1", "-1:0", "0:1", "1:5", "5:10", ">10")


class DamperSpectralEvidence(EngineeringModel):
    source_lap_ids: list[int] = Field(default_factory=list)
    qualified_window_count: int = 0
    effective_sample_rates_hz: list[float] = Field(default_factory=list)
    continuous_window_durations_s: list[float] = Field(default_factory=list)
    half_window_peak_hz: list[float] = Field(default_factory=list)
    frequency_resolution_hz: list[float] = Field(default_factory=list)
    agreement_tolerance_hz: float | None = None
    agreeing_peak_count: int = 0
    repeated: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)


class DamperCornerMetrics(EngineeringModel):
    corner: Literal["LF", "RF", "LR", "RR"]
    sample_count: int
    velocity_histogram_pct: dict[str, float] = Field(default_factory=dict)
    recorded_negative_pct: float
    recorded_positive_pct: float
    low_speed_regime_pct: float
    high_speed_regime_pct: float
    velocity_rms_in_s: float | None = None
    velocity_peak_in_s: float | None = None
    displacement_rms_in: float | None = None
    displacement_peak_to_peak_in: float | None = None
    zero_crossings: int
    median_settle_time_s: float | None = None
    oscillation_count: int
    dominant_frequency_hz: float | None = None
    dominant_psd_proxy: float | None = None
    spectral_evidence: DamperSpectralEvidence | None = None


class TrackResponseFingerprint(EngineeringModel):
    observed_bump_positions_pct: list[float] = Field(default_factory=list)
    bump_positions_pct: list[float] = Field(default_factory=list)
    repeatability_fraction: float | None = None
    cross_corner_coherence: dict[str, float] = Field(default_factory=dict)


class DamperResponseReport(EngineeringModel):
    selected_lap: int
    phases: list[str] = Field(default_factory=list)
    gate: EngineGate
    corners: list[DamperCornerMetrics] = Field(default_factory=list)
    fingerprint: TrackResponseFingerprint | None = None
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


def _histogram(items: list[float]) -> dict[str, float]:
    counts = [0] * len(_BIN_LABELS)
    for item in items:
        for index, (left, right) in enumerate(zip(_BINS, _BINS[1:])):
            if left <= item < right or (index == len(counts) - 1 and item == right):
                counts[index] += 1
                break
    return {
        label: round(count / len(items) * 100.0, 4) if items else 0.0
        for label, count in zip(_BIN_LABELS, counts)
    }


def _zero_crossings(items: list[float], threshold: float = 0.2) -> int:
    signs = [1 if item > threshold else -1 if item < -threshold else 0 for item in items]
    nonzero = [item for item in signs if item]
    return sum(left != right for left, right in zip(nonzero, nonzero[1:]))


def _settle_and_oscillation(items: list[float], times: list[float]) -> tuple[float | None, int]:
    if len(items) < 4 or len(items) != len(times):
        return None, 0
    peak_threshold = percentile([abs(item) for item in items], 0.9) or math.inf
    settle: list[float] = []
    oscillations = 0
    for index, item in enumerate(items[:-3]):
        if abs(item) < peak_threshold:
            continue
        for candidate in range(index + 1, len(items) - 2):
            if all(abs(value) <= 1.0 for value in items[candidate:candidate + 3]):
                settle.append(times[candidate] - times[index])
                oscillations += _zero_crossings(items[index:candidate + 1])
                break
    return (median(settle) if settle else None), oscillations


def _spectral_peak(items: list[float], rate: float) -> tuple[float, float] | None:
    """Return a Hann-windowed descriptive peak for one continuous window."""
    if len(items) < 32 or rate <= 0.0:
        return None
    centered = [item - mean(items) for item in items]
    # Repeated rail values are normally a clipped sensor, not a trustworthy mode.
    rail_count = max(centered.count(min(centered)), centered.count(max(centered)))
    if len(set(round(item, 8) for item in centered)) <= 3 or rail_count / len(centered) > 0.1:
        return None
    windowed = [
        value * (0.5 - 0.5 * math.cos(2.0 * math.pi * index / (len(centered) - 1)))
        for index, value in enumerate(centered)
    ]
    powers: list[tuple[int, float]] = []
    for frequency_bin in range(1, len(windowed) // 2 + 1):
        real = sum(
            value * math.cos(2.0 * math.pi * frequency_bin * index / len(windowed))
            for index, value in enumerate(windowed)
        )
        imag = -sum(
            value * math.sin(2.0 * math.pi * frequency_bin * index / len(windowed))
            for index, value in enumerate(windowed)
        )
        powers.append((frequency_bin, (real * real + imag * imag) / len(windowed)))
    if not powers:
        return None
    frequency_bin, power = max(powers, key=lambda item: item[1])
    return frequency_bin * rate / len(windowed), power


def _dominant_psd(
    items: list[float],
    times: list[float],
    *,
    evidence: dict[str, Any] | None = None,
) -> tuple[float | None, float | None]:
    """Find a repeated peak without bridging gaps or irregular sample clocks.

    PSD is intentionally withheld unless two independent continuous sub-windows
    agree.  This makes the value a repeatability indicator rather than a result
    manufactured by concatenating unrelated phases.
    """
    detail = evidence if evidence is not None else {}
    detail.update({
        "qualified_window_count": 0,
        "effective_sample_rates_hz": [],
        "continuous_window_durations_s": [],
        "half_window_peak_hz": [],
        "frequency_resolution_hz": [],
        "agreement_tolerance_hz": None,
        "agreeing_peak_count": 0,
        "repeated": False,
        "rejection_reasons": [],
    })
    if len(items) < 64 or len(items) != len(times):
        detail["rejection_reasons"].append("At least 64 paired samples are required.")
        return None, None
    positive_deltas = [right - left for left, right in zip(times, times[1:]) if right > left]
    if not positive_deltas:
        detail["rejection_reasons"].append("No positive sample-clock deltas are available.")
        return None, None
    nominal_dt = median(positive_deltas)
    if nominal_dt <= 0.0:
        detail["rejection_reasons"].append("The sample clock is invalid.")
        return None, None

    windows: list[tuple[list[float], list[float]]] = []
    window_items = [items[0]]
    window_times = [times[0]]
    for item, timestamp, previous in zip(items[1:], times[1:], times):
        delta = timestamp - previous
        if delta <= 0.0 or delta > nominal_dt * 1.5:
            windows.append((window_items, window_times))
            window_items, window_times = [item], [timestamp]
        else:
            window_items.append(item)
            window_times.append(timestamp)
    windows.append((window_items, window_times))

    peaks: list[tuple[float, float]] = []
    for window_values, window_clock in windows:
        if len(window_values) < 64:
            detail["rejection_reasons"].append("A gap-separated window had fewer than 64 samples.")
            continue
        deltas = [right - left for left, right in zip(window_clock, window_clock[1:])]
        local_dt = median(deltas)
        if local_dt <= 0.0 or (window_clock[-1] - window_clock[0]) < 0.75:
            detail["rejection_reasons"].append("A continuous window was shorter than 0.75 seconds.")
            continue
        jitter = max(abs(delta - local_dt) / local_dt for delta in deltas)
        if jitter > 0.1:
            detail["rejection_reasons"].append("A continuous window exceeded 10% sample-clock jitter.")
            continue
        rate = 1.0 / local_dt
        detail["qualified_window_count"] += 1
        detail["effective_sample_rates_hz"].append(round(rate, 6))
        detail["continuous_window_durations_s"].append(round(window_clock[-1] - window_clock[0], 6))
        # Two halves provide an independent repetition check within the same
        # continuous phase window. Additional windows add further repetitions.
        midpoint = len(window_values) // 2
        for half in (window_values[:midpoint], window_values[midpoint:]):
            peak = _spectral_peak(half, rate)
            if peak is not None:
                peaks.append(peak)
                detail["half_window_peak_hz"].append(round(peak[0], 6))
                detail["frequency_resolution_hz"].append(round(rate / len(half), 6))
            else:
                detail["rejection_reasons"].append("A half-window was clipped, quantized, or spectrally invalid.")
    if len(peaks) < 2:
        detail["rejection_reasons"].append("Two independent spectral peaks were not available.")
        return None, None
    frequencies = [peak[0] for peak in peaks]
    center = median(frequencies)
    tolerance = max(0.5, center * 0.15)
    detail["agreement_tolerance_hz"] = round(tolerance, 6)
    agreeing = [peak for peak in peaks if abs(peak[0] - center) <= tolerance]
    detail["agreeing_peak_count"] = len(agreeing)
    if len(agreeing) < 2 or len(agreeing) / len(peaks) < 0.6:
        detail["rejection_reasons"].append("Fewer than 60% of half-window peaks agreed.")
        return None, None
    detail["repeated"] = True
    return median([peak[0] for peak in agreeing]), median([peak[1] for peak in agreeing])


def _correlation(left: list[float], right: list[float]) -> float | None:
    count = min(len(left), len(right))
    if count < 3:
        return None
    x, y = left[:count], right[:count]
    mx, my = mean(x), mean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denominator = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return numerator / denominator if denominator > 0 else None


def _fingerprint(
    all_rows: list[dict[str, Any]],
    eligible_numbers: set[int],
) -> TrackResponseFingerprint:
    per_lap_positions: list[set[float]] = []
    for number in eligible_numbers:
        lap_rows = [row for row in all_rows if lap_number(row) == number]
        activity = []
        for row in lap_rows:
            motions = [abs(value) for corner in _CORNERS if (value := finite(row.get(f"{corner}_shock_vel_in_s"))) is not None]
            pct = lap_pct(row)
            if motions and pct is not None:
                activity.append((pct, max(motions)))
        threshold = percentile([item[1] for item in activity], 0.95)
        per_lap_positions.append({round(pct * 2.0) / 2.0 for pct, value in activity if threshold is not None and value >= threshold})
    counts: dict[float, int] = {}
    for positions in per_lap_positions:
        for position in positions:
            counts[position] = counts.get(position, 0) + 1
    union = set().union(*per_lap_positions) if per_lap_positions else set()
    if len(per_lap_positions) < 2:
        repeated: list[float] = []
        repeatability = None
    else:
        required = math.ceil(len(per_lap_positions) * 0.6)
        repeated = sorted(position for position, count in counts.items() if count >= required)
        repeatability = len(repeated) / len(union) if union else None
    coherence: dict[str, float] = {}
    for left, right in (("lf", "rf"), ("lr", "rr"), ("lf", "lr"), ("rf", "rr")):
        coefficient = _correlation(
            values(all_rows, f"{left}_shock_vel_in_s"),
            values(all_rows, f"{right}_shock_vel_in_s"),
        )
        if coefficient is not None:
            coherence[f"{left.upper()}-{right.upper()}"] = round(coefficient, 5)
    return TrackResponseFingerprint(
        observed_bump_positions_pct=sorted(union),
        bump_positions_pct=repeated,
        repeatability_fraction=repeatability,
        cross_corner_coherence=coherence,
    )


def analyze_damper_response(
    rows: list[dict[str, Any]],
    lap_summaries: list[LapSummary] | None,
    *,
    selected_lap: int,
    sim_integrity_clear: bool | None,
    setup_snapshot_captured: bool,
    sim_integrity_confidence_cap: float = 1.0,
) -> DamperResponseReport:
    scoped, phases, evaluation, gate = qualify_phase_engine(
        DAMPER_RESPONSE_CONTRACT,
        rows,
        lap_summaries,
        selected_lap=selected_lap,
        target_phases=DAMPER_PHASES,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
        requested_outputs=frozenset({"damper_response_metrics", "damper_regime_test"}),
    )
    eligible_numbers = {lap.lap_number for lap in eligible_laps(lap_summaries or [])}
    if not evaluation.eligible:
        return DamperResponseReport(
            selected_lap=selected_lap,
            phases=sorted(phases & DAMPER_PHASES),
            gate=gate,
            conclusions=[EngineeringConclusion(
                key="damper_response_blocked",
                summary="Damper response cannot be qualified for this window.",
                evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                confidence_score=0.0,
                blocker_reasons=gate.blocker_reasons,
            )],
        )
    corner_metrics: list[DamperCornerMetrics] = []
    conclusions: list[EngineeringConclusion] = []
    for corner in _CORNERS:
        paired = [
            (velocity, time)
            for row in scoped
            if (velocity := finite(row.get(f"{corner}_shock_vel_in_s"))) is not None
            and (time := finite(row.get("session_time"))) is not None
        ]
        velocities = [item[0] for item in paired]
        times = [item[1] for item in paired]
        deflections = values(scoped, f"{corner}_shock_defl_in")
        settle, oscillations = _settle_and_oscillation(velocities, times)
        spectral_detail: dict[str, Any] = {}
        frequency, psd = _dominant_psd(velocities, times, evidence=spectral_detail)
        spectral_detail["source_lap_ids"] = [selected_lap]
        high = sum(abs(item) > 1.0 for item in velocities) / len(velocities) * 100.0
        low = 100.0 - high
        negative = sum(item < 0 for item in velocities) / len(velocities) * 100.0
        positive = sum(item > 0 for item in velocities) / len(velocities) * 100.0
        metrics = DamperCornerMetrics(
            corner=corner.upper(),  # type: ignore[arg-type]
            sample_count=len(velocities),
            velocity_histogram_pct=_histogram(velocities),
            recorded_negative_pct=negative,
            recorded_positive_pct=positive,
            low_speed_regime_pct=low,
            high_speed_regime_pct=high,
            velocity_rms_in_s=rms(velocities),
            velocity_peak_in_s=max((abs(item) for item in velocities), default=None),
            displacement_rms_in=rms(deflections),
            displacement_peak_to_peak_in=(max(deflections) - min(deflections)) if deflections else None,
            zero_crossings=_zero_crossings(velocities),
            median_settle_time_s=settle,
            oscillation_count=oscillations,
            dominant_frequency_hz=frequency,
            dominant_psd_proxy=psd,
            spectral_evidence=DamperSpectralEvidence(**spectral_detail),
        )
        corner_metrics.append(metrics)
        regime_occupied = min(metrics.low_speed_regime_pct, metrics.high_speed_regime_pct) >= 10.0
        per_lap_high_occupancy: list[float] = []
        for number in sorted(eligible_numbers):
            lap_velocities = values(
                [row for row in rows if lap_number(row) == number],
                f"{corner}_shock_vel_in_s",
            )
            if len(lap_velocities) >= 32:
                per_lap_high_occupancy.append(
                    sum(abs(item) > 1.0 for item in lap_velocities) / len(lap_velocities) * 100.0
                )
        repeated = (
            len(per_lap_high_occupancy) >= 2
            and max(per_lap_high_occupancy) - min(per_lap_high_occupancy) <= 15.0
        )
        recommendation = None
        blockers = []
        if not regime_occupied:
            blockers.append("The relevant shaft-velocity regime occupies less than 10% of this phase window.")
        if not repeated:
            blockers.append(
                "The corner's shaft-velocity regime occupancy did not repeat within 15 percentage points on two eligible laps."
            )
        if not setup_snapshot_captured:
            blockers.append("A current corner-specific damper setting is not present in the setup snapshot.")
        blockers.append(
            "Damper clicks are not one of RacerZLab's supported driver-changeable controls, so this engine provides evidence but no click recommendation."
        )
        conclusions.append(EngineeringConclusion(
            key=f"{corner}_damper_response",
            summary=(
                f"{corner.upper()} shaft motion used {metrics.low_speed_regime_pct:.1f}% low-speed and "
                f"{metrics.high_speed_regime_pct:.1f}% high-speed regime occupancy."
            ),
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=min(0.85 if regime_occupied else 0.55, gate.confidence_cap),
            source_channels=["lap_dist_pct", "session_time", f"{corner}_shock_vel_in_s", f"{corner}_shock_defl_in"],
            supporting_evidence=[
                f"RMS shaft speed {metrics.velocity_rms_in_s:.3f} in/s." if metrics.velocity_rms_in_s is not None else "RMS unavailable.",
                f"Zero crossings {metrics.zero_crossings}; oscillation count {metrics.oscillation_count}.",
                (
                    f"High-speed regime occupancy repeated across {len(per_lap_high_occupancy)} eligible laps."
                    if repeated else "Regime repetition is not established."
                ),
                f"Dominant spectral component {metrics.dominant_frequency_hz:.2f} Hz." if metrics.dominant_frequency_hz is not None else "Spectral window too short.",
            ],
            contradicting_evidence=[
                "Shaft velocity and displacement do not measure damper force.",
                *blockers,
            ],
            recommendation=recommendation,
        ))
    fingerprint = _fingerprint(
        [row for row in rows if lap_number(row) in eligible_numbers],
        eligible_numbers,
    )
    return DamperResponseReport(
        selected_lap=selected_lap,
        phases=sorted(phases & DAMPER_PHASES),
        gate=gate,
        corners=corner_metrics,
        fingerprint=fingerprint,
        conclusions=conclusions,
    )


__all__ = [
    "DamperCornerMetrics", "DamperResponseReport", "DamperSpectralEvidence", "TrackResponseFingerprint",
    "analyze_damper_response",
]
