from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    DidItWorkVerdict,
    TargetZoneComparison,
    TestDisciplineResult,
)


def _speed_delta_info(target_zone: TargetZoneComparison) -> ComparedChannelDelta | None:
    return next((d for d in target_zone.channel_deltas if d.channel == "speed_mph"), None)


def _cfs_delta_info(target_zone: TargetZoneComparison) -> ComparedChannelDelta | None:
    return next((d for d in target_zone.channel_deltas if d.channel == "cfs_ride_height_in"), None)


def _is_same_run(speed_delta: ComparedChannelDelta | None) -> bool:
    return (
        speed_delta is not None
        and speed_delta.baseline_avg is not None
        and speed_delta.test_avg is not None
        and abs(speed_delta.delta or 0) < 1e-7
    )


def _speed_flags(speed_delta: ComparedChannelDelta | None) -> tuple[bool, bool, bool]:
    if speed_delta is None or speed_delta.delta is None:
        return False, False, False
    changed = abs(speed_delta.delta) > 0.05
    gained = changed and speed_delta.delta > 0
    lost = changed and speed_delta.delta < 0
    return changed, gained, lost


def _cfs_worsened(cfs_delta: ComparedChannelDelta | None) -> bool:
    return cfs_delta is not None and cfs_delta.delta is not None and cfs_delta.delta < -0.001


def _format_delta(d: ComparedChannelDelta | None, unit: str = "") -> str:
    return f"{d.delta:+.2f} {unit}" if d is not None and d.delta is not None else "N/A"


def _build_verdict_invalid() -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="inconclusive",
        confidence_score=0.1,
        headline="Comparison is not reliable for setup conclusions.",
        evidence=["Too many uncontrolled variables."],
        next_step="Repeat the test with one controlled variable.",
    )


def _build_verdict_retest_discipline(discipline: TestDisciplineResult) -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="retest",
        confidence_score=0.3,
        headline="Retest with fewer changes before concluding.",
        evidence=[f"Test discipline: {discipline.label} ({discipline.score}/100)."],
        next_step="Run another test changing only one setup area.",
    )


def _build_verdict_keep_direction(
    speed_delta: ComparedChannelDelta | None,
    cfs_delta: ComparedChannelDelta | None,
    discipline: TestDisciplineResult,
) -> DidItWorkVerdict:
    evidence: list[str] = [f"Speed delta: {_format_delta(speed_delta)}"]
    if cfs_delta and cfs_delta.delta is not None:
        evidence.append(f"CFS delta: {cfs_delta.delta:+.3f} in")
    return DidItWorkVerdict(
        verdict="keep_direction",
        confidence_score=0.75 if discipline.label == "clean" else 0.55,
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
        confidence_score=0.45,
        headline="Speed improved but splitter risk worsened — confirm tradeoff.",
        evidence=[
            f"Speed delta: {_format_delta(speed_delta)}",
            f"CFS delta: {cfs_delta.delta:+.3f} in (lower = riskier)" if cfs_delta and cfs_delta.delta is not None else "CFS worsened.",
        ],
        next_step="Try a smaller change or target the platform area specifically.",
    )


def _build_verdict_undo(speed_delta: ComparedChannelDelta | None) -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="undo",
        confidence_score=0.6,
        headline="Target-zone speed dropped. Consider undoing or adjusting.",
        evidence=[f"Speed delta: {_format_delta(speed_delta)}"],
        next_step="Undo the change or try a smaller adjustment in the same area.",
    )


def _build_verdict_inconclusive() -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="inconclusive",
        confidence_score=0.25,
        headline="No clear speed difference detected.",
        evidence=["Speed delta is within noise range."],
        next_step="Run another test with a larger or different change.",
    )


def compute_verdict(
    target_zone: TargetZoneComparison,
    discipline: TestDisciplineResult,
) -> DidItWorkVerdict:
    speed_delta = _speed_delta_info(target_zone)
    if _is_same_run(speed_delta):
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
    discipline_ok = discipline.label in ("clean", "mostly_clean")

    if not discipline_ok:
        result = _build_verdict_retest_discipline(discipline) if discipline.label != "invalid" else _build_verdict_invalid()
    elif speed_gained and not cfs_worse:
        result = _build_verdict_keep_direction(speed_delta, cfs_delta, discipline)
    elif speed_gained and cfs_worse:
        result = _build_verdict_retest_tradeoff(speed_delta, cfs_delta)
    elif speed_lost:
        result = _build_verdict_undo(speed_delta)
    else:
        result = _build_verdict_inconclusive()

    warnings = list(result.warnings)
    if discipline.label in ("mixed", "weak"):
        warnings.append("Low test discipline — result may not be reproducible.")
    warnings.extend(discipline.negative_factors)

    return DidItWorkVerdict(
        verdict=result.verdict,
        confidence_score=result.confidence_score,
        headline=result.headline,
        evidence=result.evidence,
        warnings=warnings,
        next_step=result.next_step,
    )
