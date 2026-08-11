"""Phase-aware braking efficiency and dynamic balance analysis.

All efficiency results are response proxies.  This module never calculates or
labels a friction coefficient or exact brake force.
"""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from pydantic import Field

from racelab_engine.analysis.p3_common import derivative, finite, lap_pct, qualify_phase_engine
from racelab_engine.analysis.p3_contracts import BRAKING_EFFICIENCY_CONTRACT
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary


BRAKING_PHASES = {"brake_application", "threshold_braking", "brake_release", "entry"}
PRESSURE_CHANNELS = (
    "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
    "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
)
WHEEL_CHANNELS = ("lf_speed", "rf_speed", "lr_speed", "rr_speed")


class BrakingPhaseMetrics(EngineeringModel):
    sample_count: int
    pressure_buildup_bar_s: float | None = None
    pressure_release_bar_s: float | None = None
    effective_front_ratio: float | None = None
    front_left_right_balance: float | None = None
    rear_left_right_balance: float | None = None
    incipient_lock_lap_pct: float | None = None
    incipient_lock_corner: str | None = None
    abs_active_duration_s: float | None = None
    matched_deceleration_efficiency_proxy: float | None = None
    efficiency_proxy_unit: str = "m/s^2 per bar"


class BrakingEfficiencyReport(EngineeringModel):
    selected_lap: int
    phases: list[str] = Field(default_factory=list)
    gate: EngineGate
    metrics: BrakingPhaseMetrics | None = None
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


def _mean_or_none(items: list[float]) -> float | None:
    return mean(items) if items else None


def _pressure_totals(rows: list[dict[str, Any]]) -> list[tuple[float, float, float]]:
    totals: list[tuple[float, float, float]] = []
    for row in rows:
        pressures = [finite(row.get(channel)) for channel in PRESSURE_CHANNELS]
        if any(value is None for value in pressures):
            continue
        lf, rf, lr, rr = (float(value) for value in pressures if value is not None)
        total = lf + rf + lr + rr
        if total > 0:
            totals.append((lf + rf, lr + rr, total))
    return totals


def _lock_timing(rows: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    for row in rows:
        explicit = [finite(row.get(f"{corner}_slip_ratio")) for corner in ("lf", "rf", "lr", "rr")]
        if all(value is not None for value in explicit):
            candidates = [(corner.upper(), float(value)) for corner, value in zip(("lf", "rf", "lr", "rr"), explicit) if value is not None]
            corner, value = min(candidates, key=lambda item: item[1])
            if value <= -0.08:
                return lap_pct(row), corner
        wheels = [finite(row.get(channel)) for channel in WHEEL_CHANNELS]
        if any(value is None for value in wheels):
            continue
        reference = max(float(value) for value in wheels if value is not None)
        if reference <= 1.0:
            continue
        corner, slowest = min(
            zip(("LF", "RF", "LR", "RR"), (float(value) for value in wheels if value is not None)),
            key=lambda item: item[1],
        )
        if (slowest - reference) / reference <= -0.08:
            return lap_pct(row), corner
    return None, None


def _abs_duration(rows: list[dict[str, Any]]) -> float | None:
    if not any("brake_abs_active" in row or "brake_abs_cut_01" in row for row in rows):
        return None
    duration = 0.0
    observed_interval = False
    for left, right in zip(rows, rows[1:]):
        t0, t1 = finite(left.get("session_time")), finite(right.get("session_time"))
        if t0 is None or t1 is None or t1 <= t0:
            continue
        active = bool(left.get("brake_abs_active")) or (finite(left.get("brake_abs_cut_01")) or 0.0) > 0
        observed_interval = True
        if active:
            duration += t1 - t0
    return duration if observed_interval else None


def analyze_braking_efficiency(
    rows: list[dict[str, Any]],
    lap_summaries: list[LapSummary] | None,
    *,
    selected_lap: int,
    sim_integrity_clear: bool | None,
    sim_integrity_confidence_cap: float = 1.0,
) -> BrakingEfficiencyReport:
    scoped, phases, evaluation, gate = qualify_phase_engine(
        BRAKING_EFFICIENCY_CONTRACT,
        rows,
        lap_summaries,
        selected_lap=selected_lap,
        target_phases=BRAKING_PHASES,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
        requested_outputs=frozenset({"braking_phase_metrics", "braking_cause_hypothesis"}),
    )
    if not evaluation.eligible:
        return BrakingEfficiencyReport(
            selected_lap=selected_lap,
            phases=sorted(phases & BRAKING_PHASES),
            gate=gate,
            conclusions=[EngineeringConclusion(
                key="braking_analysis_blocked",
                summary="Braking observations are retained, but this window cannot support an engineering conclusion.",
                evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                confidence_score=0.0,
                blocker_reasons=gate.blocker_reasons,
            )],
        )

    totals = _pressure_totals(scoped)
    total_pressure = [total for _front, _rear, total in totals]
    times = [finite(row.get("session_time")) for row in scoped]
    pressure_rows = [
        (time, sum(float(value) for channel in PRESSURE_CHANNELS if (value := finite(row.get(channel))) is not None))
        for row, time in zip(scoped, times)
        if time is not None and all(finite(row.get(channel)) is not None for channel in PRESSURE_CHANNELS)
    ]
    pressure_rates = derivative(
        [item[1] for item in pressure_rows],
        [float(item[0]) for item in pressure_rows],
    )
    buildup = _mean_or_none([value for value in pressure_rates if value > 0])
    release = _mean_or_none([value for value in pressure_rates if value < 0])
    front_ratios = [front / total for front, _rear, total in totals]
    front_lr = []
    rear_lr = []
    for row in scoped:
        lf, rf, lr, rr = (finite(row.get(channel)) for channel in PRESSURE_CHANNELS)
        if lf is not None and rf is not None and lf + rf > 0:
            front_lr.append((lf - rf) / (lf + rf))
        if lr is not None and rr is not None and lr + rr > 0:
            rear_lr.append((lr - rr) / (lr + rr))
    decel = [-value for row in scoped if (value := finite(row.get("long_accel"))) is not None and value < 0]
    avg_pressure = _mean_or_none(total_pressure)
    efficiency = (_mean_or_none(decel) / avg_pressure) if decel and avg_pressure and avg_pressure > 0 else None
    lock_pct, lock_corner = _lock_timing(scoped)
    metrics = BrakingPhaseMetrics(
        sample_count=len(scoped),
        pressure_buildup_bar_s=buildup,
        pressure_release_bar_s=release,
        effective_front_ratio=_mean_or_none(front_ratios),
        front_left_right_balance=_mean_or_none(front_lr),
        rear_left_right_balance=_mean_or_none(rear_lr),
        incipient_lock_lap_pct=lock_pct,
        incipient_lock_corner=lock_corner,
        abs_active_duration_s=_abs_duration(scoped),
        matched_deceleration_efficiency_proxy=efficiency,
    )
    source_channels = sorted(BRAKING_EFFICIENCY_CONTRACT.required_channels)
    metric_support = [
        f"{len(scoped)} phase-scoped samples were analyzed by lap position.",
        f"Effective front line-pressure share was {metrics.effective_front_ratio:.3f}."
        if metrics.effective_front_ratio is not None else "Front pressure share was unavailable.",
        "Deceleration efficiency is reported only as m/s^2 per bar, not a friction coefficient.",
    ]
    contradictions = []
    if metrics.abs_active_duration_s:
        contradictions.append("ABS intervention can mask the underlying mechanical balance.")
    if lock_corner is None:
        contradictions.append("No repeatable incipient-lock signature was observed in this window.")
    conclusions = [EngineeringConclusion(
        key="braking_phase_metrics",
        summary="Phase-scoped brake response and dynamic line-pressure balance were calculated.",
        evidence_state=EvidenceState.CALCULATED,
        confidence_score=min(0.9, gate.confidence_cap),
        source_channels=source_channels,
        supporting_evidence=metric_support,
        contradicting_evidence=contradictions,
    )]

    ratio_variation = pstdev(front_ratios) if len(front_ratios) >= 2 else None
    pedal = [finite(row.get("brake_pct")) for row in scoped]
    pedal_times = [finite(row.get("session_time")) for row in scoped]
    pedal_pairs = [(float(t), float(p)) for t, p in zip(pedal_times, pedal) if t is not None and p is not None]
    pedal_rates = derivative([item[1] for item in pedal_pairs], [item[0] for item in pedal_pairs])
    pedal_variation = pstdev(pedal_rates) if len(pedal_rates) >= 2 else None
    bias_support = bool(
        metrics.effective_front_ratio is not None
        and ratio_variation is not None
        and ratio_variation <= 0.03
        and (lock_corner is not None or (metrics.abs_active_duration_s or 0.0) > 0)
    )
    technique_support = bool(pedal_variation is not None and pedal_variation >= 80.0)
    if bias_support and not technique_support:
        cause = "The persistent axle-pressure/lock pattern is more consistent with a brake-balance test than pedal technique alone."
    elif technique_support and not bias_support:
        cause = "Pedal application varied strongly; driver technique can explain the braking response before setup bias is blamed."
    else:
        cause = "Setup-bias and pedal-technique evidence are mixed or incomplete; no brake-bias change is justified yet."
    conclusions.append(EngineeringConclusion(
        key="braking_cause_hypothesis",
        summary=cause,
        evidence_state=EvidenceState.ESTIMATED_PROXY,
        confidence_score=min(0.7 if (bias_support ^ technique_support) else 0.45, gate.confidence_cap),
        source_channels=source_channels,
        supporting_evidence=[
            f"Front pressure-share variation: {ratio_variation:.3f}." if ratio_variation is not None else "Pressure-share repeatability unavailable.",
            f"Pedal-rate variation: {pedal_variation:.1f} %/s." if pedal_variation is not None else "Pedal-rate repeatability unavailable.",
        ],
        contradicting_evidence=[
            "A line-pressure ratio is not the same thing as measured tire-road friction.",
            "ABS or tire state may alter the observed lock sequence.",
            "This P3 observation cannot authorize a brake-bias change; setup policy belongs to the controlled P19 workflow.",
        ],
    ))
    return BrakingEfficiencyReport(
        selected_lap=selected_lap,
        phases=sorted(phases & BRAKING_PHASES),
        gate=gate,
        metrics=metrics,
        conclusions=conclusions,
    )


__all__ = ["BrakingEfficiencyReport", "BrakingPhaseMetrics", "analyze_braking_efficiency"]
