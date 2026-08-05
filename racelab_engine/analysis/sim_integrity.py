"""Simulator and telemetry integrity certificate for controlled comparisons."""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Literal

from pydantic import Field

from racelab_engine.analysis.evidence_contracts import EvidenceEvaluationInput, evaluate_evidence_contract
from racelab_engine.analysis.p3_common import finite, percentile, values
from racelab_engine.analysis.p3_contracts import SIM_INTEGRITY_CONTRACT
from racelab_engine.models.engineering import EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState


IntegrityStatus = Literal["pass", "warning", "fail", "unknown"]


class IntegrityCheck(EngineeringModel):
    key: str
    status: IntegrityStatus
    observed: float | int | str | None = None
    threshold: str
    explanation: str
    source_channels: list[str] = Field(default_factory=list)


class SimIntegrityCertificate(EngineeringModel):
    status: IntegrityStatus
    is_clear_for_analysis: bool | None
    confidence_cap: float
    checks: list[IntegrityCheck] = Field(default_factory=list)
    dropped_tick_count: int | None = None
    tick_discontinuity_count: int | None = None
    non_monotonic_clock_count: int | None = None
    clock_skew_p95_s: float | None = None
    observed_sample_rate_hz: float | None = None
    core_clock_coverage_pct: float | None = None
    conclusion: EngineeringConclusion


def _channel(rows: list[dict[str, Any]], *names: str) -> tuple[str | None, list[float]]:
    for name in names:
        items = values(rows, name)
        if items:
            return name, items
    return None, []


def _percent_scale(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100.0 if 0.0 <= value <= 1.5 else value


def _ratio_scale(value: float | None) -> float | None:
    """Normalize a telemetry ratio that may be declared as either 0..1 or 0..100."""
    if value is None:
        return None
    if 0.0 <= value <= 1.0:
        return value
    if value <= 100.0:
        return value / 100.0
    return -1.0


def _first_finite(row: dict[str, Any], *names: str) -> tuple[str | None, float | None]:
    for name in names:
        value = finite(row.get(name))
        if value is not None:
            return name, value
    return None, None


def build_sim_integrity_certificate(
    rows: list[dict[str, Any]],
    *,
    expected_sample_rate_hz: float | None,
) -> SimIntegrityCertificate:
    paired_clock: list[tuple[float, float]] = []
    tick_names: set[str] = set()
    time_names: set[str] = set()
    for row in rows:
        row_tick_name, tick = _first_finite(row, "session_tick", "SessionTick")
        row_time_name, time = _first_finite(row, "session_time", "SessionTime")
        if row_tick_name:
            tick_names.add(row_tick_name)
        if row_time_name:
            time_names.add(row_time_name)
        if tick is not None and time is not None:
            paired_clock.append((tick, time))
    tick_name = sorted(tick_names)[0] if tick_names else None
    time_name = sorted(time_names)[0] if time_names else None
    ticks = [item[0] for item in paired_clock]
    times = [item[1] for item in paired_clock]
    tick_deltas = [right - left for left, right in zip(ticks, ticks[1:])]
    time_deltas = [right - left for left, right in zip(times, times[1:])]
    integer_ticks = all(math.isclose(tick, round(tick), abs_tol=1e-9) for tick in ticks)
    discontinuities = (
        sum(not math.isclose(delta, 1.0, abs_tol=1e-9) for delta in tick_deltas)
        if tick_deltas and integer_ticks else None
    )
    dropped = (
        sum(max(0, round(delta) - 1) for delta in tick_deltas)
        if tick_deltas and integer_ticks else None
    )
    non_monotonic = sum(delta <= 0 for delta in time_deltas) if time_deltas else None
    positive_time_deltas = [delta for delta in time_deltas if delta > 0]
    observed_rate = 1.0 / median(positive_time_deltas) if positive_time_deltas else None
    clock_skews = []
    declared_rate = finite(expected_sample_rate_hz)
    if declared_rate is not None and declared_rate > 0:
        clock_skews = [
            abs(time_delta - (tick_delta / declared_rate))
            for tick_delta, time_delta in zip(tick_deltas, time_deltas)
            if tick_delta > 0 and time_delta > 0
        ]
    clock_skew_p95 = percentile(clock_skews, 0.95)
    rate_credible = (
        observed_rate is not None
        and declared_rate is not None
        and declared_rate > 0
        and abs(observed_rate - declared_rate) / declared_rate <= 0.05
    )
    core_available = len(paired_clock) >= 2
    core_coverage_pct = len(paired_clock) / len(rows) * 100.0 if rows else None
    core_complete = bool(rows) and len(paired_clock) == len(rows)

    checks: list[IntegrityCheck] = []
    checks.append(IntegrityCheck(
        key="clock_coverage",
        status="pass" if core_complete else "fail" if rows else "unknown",
        observed=core_coverage_pct,
        threshold="100% of samples contain a paired SessionTick and SessionTime",
        explanation="Missing either clock value prevents trustworthy sample pairing and timing attribution.",
        source_channels=sorted(tick_names | time_names),
    ))
    checks.append(IntegrityCheck(
        key="sample_continuity",
        status=(
            "fail" if ticks and not integer_ticks
            else "pass" if discontinuities == 0
            else "fail" if discontinuities is not None
            else "unknown"
        ),
        observed=discontinuities,
        threshold="0 discontinuities",
        explanation="SessionTick must be integer-valued and advance by exactly one sample.",
        source_channels=[tick_name] if tick_name else [],
    ))
    checks.append(IntegrityCheck(
        key="clock_monotonicity",
        status=("pass" if non_monotonic == 0 else "fail" if non_monotonic is not None else "unknown"),
        observed=non_monotonic,
        threshold="0 non-monotonic transitions",
        explanation="SessionTime must increase monotonically.",
        source_channels=[time_name] if time_name else [],
    ))
    checks.append(IntegrityCheck(
        key="sample_rate",
        status="pass" if rate_credible else "fail" if observed_rate is not None and declared_rate else "unknown",
        observed=observed_rate,
        threshold="within 5% of declared rate",
        explanation="Unexpected sample rate can distort derivatives and input timing.",
        source_channels=[time_name] if time_name else [],
    ))
    checks.append(IntegrityCheck(
        key="clock_skew",
        status=(
            "fail" if clock_skew_p95 is not None and clock_skew_p95 > 0.010
            else "warning" if clock_skew_p95 is not None and clock_skew_p95 > 0.002
            else "pass" if clock_skew_p95 is not None else "unknown"
        ),
        observed=clock_skew_p95,
        threshold="95th percentile <= 0.002 s; >0.010 s blocks attribution",
        explanation="SessionTime progression should agree with SessionTick at the declared sample rate.",
        source_channels=[name for name in (tick_name, time_name) if name],
    ))

    fps_name, fps = _channel(rows, "frame_rate", "FrameRate", "fps")
    fps_p05 = percentile(fps, 0.05)
    invalid_fps = any(item <= 0.0 for item in fps)
    checks.append(IntegrityCheck(
        key="frame_rate",
        status="fail" if invalid_fps or (fps_p05 is not None and fps_p05 < 45) else "warning" if fps_p05 is not None and fps_p05 < 60 else "pass" if fps_p05 is not None else "unknown",
        observed=fps_p05,
        threshold="values must be positive; 5th percentile >= 60 FPS; <45 blocks attribution",
        explanation="Low frame rate may change driver inputs and timing.",
        source_channels=[fps_name] if fps_name else [],
    ))
    for key, aliases, fail_threshold, warning_threshold in (
        ("cpu", ("cpu_usage_foreground", "CpuUsageFG"), 98.0, 90.0),
        ("gpu", ("gpu_usage", "GpuUsage"), 99.0, 95.0),
    ):
        name, items = _channel(rows, *aliases)
        p95 = _percent_scale(percentile(items, 0.95))
        invalid_usage = any(item < 0.0 or item > 100.0 for item in items)
        checks.append(IntegrityCheck(
            key=f"{key}_headroom",
            status="fail" if invalid_usage or (p95 is not None and p95 >= fail_threshold) else "warning" if p95 is not None and p95 >= warning_threshold else "pass" if p95 is not None else "unknown",
            observed=p95,
            threshold=f"values must resolve to 0-100%; 95th percentile < {warning_threshold}%",
            explanation=f"Saturated {key.upper()} usage can disturb simulation or input timing.",
            source_channels=[name] if name else [],
        ))
    fault_name, faults = _channel(rows, "memory_page_faults_per_s", "MemPageFaultSec")
    fault_p95 = percentile(faults, 0.95)
    invalid_faults = any(item < 0.0 for item in faults)
    checks.append(IntegrityCheck(
        key="memory_faults",
        status="fail" if invalid_faults else "warning" if fault_p95 is not None and fault_p95 > 500 else "pass" if fault_p95 is not None else "unknown",
        observed=fault_p95,
        threshold="values must be non-negative; 95th percentile <= 500 faults/s",
        explanation="Memory-fault spikes can coincide with timing instability; this is context, not proof of a physics error.",
        source_channels=[fault_name] if fault_name else [],
    ))
    latency_name, latency = _channel(rows, "channel_latency_s", "ChanLatency", "channel_average_latency_s", "ChanAvgLatency")
    latency_p95 = percentile(latency, 0.95)
    invalid_latency = any(item < 0.0 for item in latency)
    checks.append(IntegrityCheck(
        key="communication_latency",
        status="fail" if invalid_latency or (latency_p95 is not None and latency_p95 > 0.25) else "warning" if latency_p95 is not None and latency_p95 > 0.1 else "pass" if latency_p95 is not None else "unknown",
        observed=latency_p95,
        threshold="values must be non-negative; 95th percentile <= 0.10 s; >0.25 s blocks attribution",
        explanation="High communication latency can shift observed input timing.",
        source_channels=[latency_name] if latency_name else [],
    ))
    quality_name, quality = _channel(rows, "channel_quality", "ChanQuality")
    quality_p05 = _ratio_scale(percentile(quality, 0.05))
    checks.append(IntegrityCheck(
        key="communication_quality",
        status="fail" if quality_p05 is not None and quality_p05 < 0.7 else "warning" if quality_p05 is not None and quality_p05 < 0.9 else "pass" if quality_p05 is not None else "unknown",
        observed=quality_p05,
        threshold="values must normalize to 0-1; 5th percentile >= 0.90",
        explanation="Channel quality is normalized from ratio or percent units and supports timing confidence.",
        source_channels=[quality_name] if quality_name else [],
    ))

    severe = any(check.status == "fail" for check in checks)
    warnings = [check for check in checks if check.status == "warning"]
    system_keys = {
        "frame_rate", "cpu_headroom", "gpu_headroom", "memory_faults",
        "communication_latency", "communication_quality",
    }
    unknown_system = [
        check for check in checks if check.key in system_keys and check.status == "unknown"
    ]
    usable_channels = {
        channel for row in rows for channel, value in row.items() if finite(value) is not None
    }
    alias_sets = {
        "session_tick": ("session_tick", "SessionTick"),
        "session_time": ("session_time", "SessionTime"),
        "frame_rate": ("frame_rate", "FrameRate", "fps"),
        "cpu_usage_foreground": ("cpu_usage_foreground", "CpuUsageFG"),
        "cpu_usage_background": ("cpu_usage_background", "CpuUsageBG"),
        "gpu_usage": ("gpu_usage", "GpuUsage"),
        "memory_page_faults_per_s": ("memory_page_faults_per_s", "MemPageFaultSec"),
        "memory_soft_page_faults_per_s": ("memory_soft_page_faults_per_s", "MemSoftPageFaultSec"),
        "channel_latency_s": ("channel_latency_s", "ChanLatency"),
        "channel_average_latency_s": ("channel_average_latency_s", "ChanAvgLatency"),
        "channel_quality": ("channel_quality", "ChanQuality"),
    }
    for canonical, aliases in alias_sets.items():
        if any(alias in usable_channels for alias in aliases):
            usable_channels.add(canonical)
    evaluation = evaluate_evidence_contract(
        SIM_INTEGRITY_CONTRACT,
        EvidenceEvaluationInput(
            usable_channels=frozenset(usable_channels),
            condition_results={
                "continuous_clock_window": (
                    core_available and core_complete and integer_ticks
                    and discontinuities == 0 and non_monotonic == 0
                ),
                "credible_sample_rate": rate_credible,
            },
            blocker_results={"integrity_failure": severe},
            repetitions=1,
            requested_outputs=frozenset({"sim_integrity_certificate"}),
        ),
    )
    if not core_available:
        status: IntegrityStatus = "unknown"
        clear: bool | None = None
        cap = 0.35
    elif severe or not evaluation.eligible:
        status = "fail"
        clear = False
        cap = 0.35
    elif warnings or unknown_system:
        status = "warning"
        clear = True
        cap = min(0.65, evaluation.confidence_cap)
    else:
        status = "pass"
        clear = True
        cap = min(0.95, evaluation.confidence_cap)
    blockers = [item.message for item in evaluation.blockers]
    support = [
        f"{check.key}: {check.status} ({check.observed})."
        for check in checks if check.status in {"pass", "warning"}
    ]
    contradictions = [
        f"{check.key}: {check.status} ({check.observed})."
        for check in checks if check.status in {"fail", "unknown"}
    ]
    conclusion = EngineeringConclusion(
        key="sim_integrity_certificate",
        summary=f"Simulator/data integrity certificate: {status}.",
        evidence_state=EvidenceState.CALCULATED if clear is not None else EvidenceState.UNAVAILABLE,
        confidence_score=cap,
        source_channels=[name for name in (tick_name, time_name, fps_name, fault_name, latency_name, quality_name) if name],
        supporting_evidence=support,
        contradicting_evidence=contradictions,
        blocker_reasons=blockers if clear is None else [],
    )
    return SimIntegrityCertificate(
        status=status,
        is_clear_for_analysis=clear,
        confidence_cap=cap,
        checks=checks,
        dropped_tick_count=dropped,
        tick_discontinuity_count=discontinuities,
        non_monotonic_clock_count=non_monotonic,
        clock_skew_p95_s=clock_skew_p95,
        observed_sample_rate_hz=observed_rate,
        core_clock_coverage_pct=core_coverage_pct,
        conclusion=conclusion,
    )


def comparison_integrity_gate(
    baseline: SimIntegrityCertificate,
    test: SimIntegrityCertificate,
) -> tuple[bool | None, float, list[str]]:
    if baseline.is_clear_for_analysis is False or test.is_clear_for_analysis is False:
        return False, min(baseline.confidence_cap, test.confidence_cap), [
            "Simulator/data integrity failed in at least one comparison run; causal attribution is blocked."
        ]
    if baseline.is_clear_for_analysis is None or test.is_clear_for_analysis is None:
        return None, min(baseline.confidence_cap, test.confidence_cap), [
            "Simulator/data integrity is unknown in at least one comparison run."
        ]
    warnings = []
    if baseline.status == "warning" or test.status == "warning":
        warnings.append("Simulator/data integrity warnings cap controlled-comparison confidence.")
    return True, min(baseline.confidence_cap, test.confidence_cap), warnings


__all__ = [
    "IntegrityCheck", "SimIntegrityCertificate", "build_sim_integrity_certificate",
    "comparison_integrity_gate",
]
