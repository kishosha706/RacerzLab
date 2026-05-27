from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    DidItWorkVerdict,
    TargetZoneComparison,
    TestDisciplineResult,
)
from racelab_engine.analysis.constants import (
    SPEED_NOISE_THRESHOLD,
    CFS_WORSEN_THRESHOLD,
    CONF_HIGH,
    CONF_MEDIUM,
    CONF_LOW,
    CONF_NOISE,
    CONF_KEEP_MIXED,
    CONF_RETEST_DISCIPLINE,
    CONF_INVALID,
    RELIABLE_DISCIPLINES,
)


def _speed_delta_info(target_zone: TargetZoneComparison) -> ComparedChannelDelta | None:
    return next((d for d in target_zone.channel_deltas if d.channel == "speed_mph"), None)


def _cfs_delta_info(target_zone: TargetZoneComparison) -> ComparedChannelDelta | None:
    return next((d for d in target_zone.channel_deltas if d.channel == "cfs_ride_height_in"), None)


def _speed_flags(speed_delta: ComparedChannelDelta | None) -> tuple[bool, bool, bool]:
    if speed_delta is None or speed_delta.delta is None:
        return False, False, False
    changed = abs(speed_delta.delta) > SPEED_NOISE_THRESHOLD
    gained = changed and speed_delta.delta > 0
    lost = changed and speed_delta.delta < 0
    return changed, gained, lost


def _cfs_worsened(cfs_delta: ComparedChannelDelta | None) -> bool:
    return cfs_delta is not None and cfs_delta.delta is not None and cfs_delta.delta < CFS_WORSEN_THRESHOLD


def _format_speed_delta(d: ComparedChannelDelta | None) -> str:
    return f"{d.delta:+.2f} mph" if d is not None and d.delta is not None else "N/A"


def _format_cfs_delta(d: ComparedChannelDelta | None) -> str:
    return f"{d.delta:+.3f} in" if d is not None and d.delta is not None else "N/A"


def _build_verdict_invalid() -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="inconclusive",
        confidence_score=CONF_INVALID,
        headline="Comparison is not reliable for setup conclusions.",
        evidence=["Too many uncontrolled variables."],
        next_step="Repeat the test with one controlled variable.",
    )


def _build_verdict_retest_discipline(discipline: TestDisciplineResult) -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="retest",
        confidence_score=CONF_RETEST_DISCIPLINE,
        headline="Retest with fewer changes before concluding.",
        evidence=[f"Test discipline: {discipline.label} ({discipline.score}/100)."],
        next_step="Run another test changing only one setup area.",
    )


def _build_verdict_keep_direction(
    speed_delta: ComparedChannelDelta | None,
    cfs_delta: ComparedChannelDelta | None,
    discipline: TestDisciplineResult,
) -> DidItWorkVerdict:
    evidence: list[str] = [f"Speed delta: {_format_speed_delta(speed_delta)}"]
    if cfs_delta and cfs_delta.delta is not None:
        evidence.append(f"CFS delta: {_format_cfs_delta(cfs_delta)}")
    return DidItWorkVerdict(
        verdict="keep_direction",
        confidence_score=CONF_HIGH if discipline.label == "clean" else CONF_KEEP_MIXED,
        headline="Target-zone speed improved while splitter risk did not worsen.",
        evidence=evidence,
        next_step="Keep this direction and confirm with another clean run.",
    )


def _build_verdict_retest_tradeoff(
    speed_delta: ComparedChannelDelta | None,
    cfs_delta: ComparedChannelDelta | None,
) -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="retest",
        confidence_score=CONF_LOW,
        headline="Speed improved but splitter risk worsened — confirm tradeoff.",
        evidence=[
            f"Speed delta: {_format_speed_delta(speed_delta)}",
            f"CFS delta: {_format_cfs_delta(cfs_delta)} (lower = riskier)",
        ],
        next_step="Try a smaller change or target the platform area specifically.",
    )


def _build_verdict_undo(speed_delta: ComparedChannelDelta | None) -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="undo",
        confidence_score=CONF_MEDIUM,
        headline="Target-zone speed dropped. Consider undoing or adjusting.",
        evidence=[f"Speed delta: {_format_speed_delta(speed_delta)}"],
        next_step="Undo the change or try a smaller adjustment in the same area.",
    )


def _build_verdict_inconclusive(speed_delta: ComparedChannelDelta | None) -> DidItWorkVerdict:
    has_data = speed_delta is not None and speed_delta.delta is not None
    evidence = "Speed delta is within noise range." if has_data else "Speed telemetry was unavailable in the target zone."
    
    return DidItWorkVerdict(
        verdict="inconclusive",
        confidence_score=CONF_NOISE,
        headline="No clear speed difference detected.",
        evidence=[evidence],
        next_step="Run another test with a larger or different change.",
    )


def compute_verdict(
    target_zone: TargetZoneComparison,
    discipline: TestDisciplineResult,
    is_same_run: bool = False,
) -> DidItWorkVerdict:
    speed_delta = _speed_delta_info(target_zone)
    if is_same_run:
        return DidItWorkVerdict(
            verdict="inconclusive",
            confidence_score=1.0,
            headline="Baseline Reference: You are comparing a run to itself.",
            evidence=["Telemetry is identical."],
            next_step="Import a second run with a setup change to see a delta verdict.",
        )

    cfs_delta = _cfs_delta_info(target_zone)
    _changed, speed_gained, speed_lost = _speed_flags(speed_delta)
    cfs_worse = _cfs_worsened(cfs_delta)
    discipline_ok = discipline.label in RELIABLE_DISCIPLINES

    if discipline.label == "invalid":
        result = _build_verdict_invalid()
    elif not discipline_ok:
        result = _build_verdict_retest_discipline(discipline)
    elif speed_gained and not cfs_worse:
        result = _build_verdict_keep_direction(speed_delta, cfs_delta, discipline)
    elif speed_gained and cfs_worse:
        result = _build_verdict_retest_tradeoff(speed_delta, cfs_delta)
    elif speed_lost:
        result = _build_verdict_undo(speed_delta)
    else:
        result = _build_verdict_inconclusive(speed_delta)

    warnings = list(result.warnings)
    if discipline.label in ("mixed", "weak"):
        msg = "Low test discipline — result may not be reproducible."
        if msg not in discipline.negative_factors:
            warnings.append(msg)
    for factor in discipline.negative_factors:
        if factor not in warnings:
            warnings.append(factor)

    return DidItWorkVerdict(
        verdict=result.verdict,
        confidence_score=result.confidence_score,
        headline=result.headline,
        evidence=result.evidence,
        warnings=warnings,
        next_step=result.next_step,
    )
