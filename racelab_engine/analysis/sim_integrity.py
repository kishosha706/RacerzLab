"""Simulator and telemetry integrity certificate for controlled comparisons."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from racelab_engine.analysis.evidence_contracts import (
    EvidenceEvaluationInput,
    evaluate_evidence_contract,
)
from racelab_engine.analysis.p3_common import finite, percentile, values
from racelab_engine.analysis.p3_contracts import SIM_INTEGRITY_CONTRACT
from racelab_engine.analysis.qualified_clock import (
    QualifiedTelemetryClock,
    build_qualified_telemetry_clock,
)
from racelab_engine.models.engineering import EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState

IntegrityStatus = Literal["pass", "warning", "fail", "unknown"]


class IntegrityCheck(EngineeringModel):
    key: str
    status: IntegrityStatus
    observed: float | int | str | None = None
    raw_observed: float | int | str | None = None
    normalization_provenance: str | None = None
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
    observed_session_time_coverage_pct: float | None = None
    session_time_duplicate_count: int | None = None
    session_time_reverse_count: int | None = None
    qualified_clock: QualifiedTelemetryClock
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


def _ratio_scale(value: float | None) -> tuple[float | None, str]:
    """Normalize a ratio without guessing across the ambiguous 1..2 range.

    ChanQuality is documented in both ratio and percent representations in real
    captures.  Ratio-valued captures also exhibit small floating-point jitter
    above unity.  Only that measured jitter band is tolerated; other values
    between the two representations remain invalid rather than being silently
    interpreted as percent.
    """
    if value is None:
        return None, "missing"
    if 0.0 <= value <= 1.0:
        return value, "ratio_0_to_1"
    if value <= 1.01:
        return 1.0, "ratio_unity_jitter_clamped_1pct"
    if 2.0 <= value <= 100.0:
        return value / 100.0, "percent_0_to_100"
    return None, "invalid_or_ambiguous"


def build_sim_integrity_certificate(
    rows: list[dict[str, Any]],
    *,
    expected_sample_rate_hz: float | None,
) -> SimIntegrityCertificate:
    clock = build_qualified_telemetry_clock(
        rows,
        expected_sample_rate_hz=expected_sample_rate_hz,
    )
    tick_name = next(
        (name for name in clock.source_channels if name in {"session_tick", "SessionTick"}),
        None,
    )
    time_name = next(
        (name for name in clock.source_channels if name in {"session_time", "SessionTime"}),
        None,
    )
    tick_names = {tick_name} if tick_name else set()
    time_names = {time_name} if time_name else set()
    discontinuities = (
        clock.tick_discontinuity_count if tick_name is not None else None
    )
    dropped = clock.dropped_tick_count if tick_name is not None else None
    non_monotonic = (
        clock.session_time_duplicate_count + clock.session_time_reverse_count
        if time_name is not None else None
    )
    observed_rate = clock.observed_sample_rate_hz
    declared_rate = finite(expected_sample_rate_hz)
    clock_skew_p95 = clock.qualified_session_time_residual_p95_s
    rate_credible = (
        clock.primary_clock == "session_tick"
        and observed_rate is not None
        and declared_rate is not None
        and declared_rate > 0
        and abs(observed_rate - declared_rate) / declared_rate <= 0.05
    )
    core_available = clock.primary_clock != "unavailable" and clock.sample_count >= 2
    core_coverage_pct = clock.canonical_clock_coverage_pct
    core_complete = bool(rows) and core_coverage_pct == 100.0

    checks: list[IntegrityCheck] = []
    checks.append(IntegrityCheck(
        key="clock_coverage",
        status="pass" if core_complete else "fail" if rows else "unknown",
        observed=core_coverage_pct,
        threshold="100% of samples have a canonical qualified-clock projection",
        explanation="Qualified ticks may supply canonical time while observed SessionTime remains corroborating evidence.",
        source_channels=sorted(tick_names | time_names),
    ))
    checks.append(IntegrityCheck(
        key="sample_continuity",
        status=(
            "pass" if discontinuities == 0
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
        status=(
            "pass" if non_monotonic == 0
            else "warning" if non_monotonic is not None and clock.primary_clock == "session_tick"
            else "fail" if non_monotonic is not None
            else "unknown"
        ),
        observed=non_monotonic,
        threshold="0 non-monotonic transitions",
        explanation=(
            "Observed SessionTime anomalies are retained as residual evidence. "
            "They do not replace or invalidate a qualified contiguous tick clock by themselves."
        ),
        source_channels=[time_name] if time_name else [],
    ))
    checks.append(IntegrityCheck(
        key="sample_rate",
        status="pass" if rate_credible else "fail" if observed_rate is not None and declared_rate else "unknown",
        observed=observed_rate,
        threshold="within 5% of declared rate",
        explanation="Observed SessionTime cadence must corroborate the declared rate used by contiguous SessionTick.",
        source_channels=[name for name in (tick_name, time_name) if name],
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
    checks.append(IntegrityCheck(
        key="observed_session_time_coverage",
        status=(
            "pass" if clock.session_time_coverage_pct == 100.0
            else "warning" if clock.session_time_coverage_pct is not None and time_name is not None
            else "unknown"
        ),
        observed=clock.session_time_coverage_pct,
        threshold="100% preferred for simulator-clock corroboration",
        explanation=(
            "Missing observed timestamps limit corroboration but do not remove a complete qualified tick clock."
        ),
        source_channels=[time_name] if time_name else [],
    ))
    checks.append(IntegrityCheck(
        key="clock_epoch_scope",
        status=(
            "pass" if clock.epoch_count == 1
            else "fail" if clock.epoch_count > 1
            else "unknown"
        ),
        observed=clock.epoch_count,
        threshold="one reset epoch per analysis window",
        explanation="A timing-sensitive analysis window cannot cross a telemetry-clock reset boundary.",
        source_channels=[name for name in (tick_name, time_name) if name],
    ))
    checks.append(IntegrityCheck(
        key="simulator_lap_time_corroboration",
        status=(
            "pass" if clock.lap_time_channel_corroboration == "agrees"
            else "fail" if clock.lap_time_channel_corroboration == "disagrees"
            else "unknown"
        ),
        observed=clock.simulator_lap_time_residual_s,
        threshold=(
            f"absolute residual <= {clock.simulator_lap_time_tolerance_s:.6f} s"
            if clock.simulator_lap_time_tolerance_s is not None
            else "corroboration optional; it never creates timing authority"
        ),
        explanation=(
            "Simulator lap time can corroborate the qualified clock; material disagreement blocks timing attribution."
        ),
        source_channels=[
            name for name in (clock.simulator_lap_time_source, tick_name, time_name) if name
        ],
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
    raw_quality_p05 = percentile(quality, 0.05)
    quality_p05, quality_normalization = _ratio_scale(raw_quality_p05)
    quality_invalid = raw_quality_p05 is not None and quality_p05 is None
    checks.append(IntegrityCheck(
        key="communication_quality",
        status="fail" if quality_invalid or (quality_p05 is not None and quality_p05 < 0.7) else "warning" if quality_p05 is not None and quality_p05 < 0.9 else "pass" if quality_p05 is not None else "unknown",
        observed=quality_p05,
        raw_observed=raw_quality_p05,
        normalization_provenance=quality_normalization,
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
    # This contract can only consume the declared integrity channel families.
    # Scanning every value in a wide telemetry row made the certificate cost
    # proportional to unrelated car channels and repeated that work per lap.
    usable_channels: set[str] = set()
    for canonical, aliases in alias_sets.items():
        present_alias = next(
            (
                alias
                for alias in aliases
                if any(finite(row.get(alias)) is not None for row in rows)
            ),
            None,
        )
        if present_alias is not None:
            usable_channels.add(present_alias)
            usable_channels.add(canonical)
    evaluation = evaluate_evidence_contract(
        SIM_INTEGRITY_CONTRACT,
        EvidenceEvaluationInput(
            usable_channels=frozenset(usable_channels),
            condition_results={
                "continuous_clock_window": (
                    core_available
                    and core_complete
                    and clock.clock_state == "qualified"
                    and clock.epoch_count == 1
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
        observed_session_time_coverage_pct=clock.session_time_coverage_pct,
        session_time_duplicate_count=(
            clock.session_time_duplicate_count if time_name is not None else None
        ),
        session_time_reverse_count=(
            clock.session_time_reverse_count if time_name is not None else None
        ),
        qualified_clock=clock,
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
