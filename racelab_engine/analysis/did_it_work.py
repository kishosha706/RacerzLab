from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    DidItWorkVerdict,
    PaceComparison,
    TargetZoneComparison,
    TestDisciplineResult,
)
from racelab_engine.analysis.constants import (
    SPEED_NOISE_THRESHOLD,
    CFS_WORSEN_THRESHOLD,
    CFS_SIGNIFICANT,
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
    return bool(
        cfs_delta is not None
        and (
            (cfs_delta.delta is not None and cfs_delta.delta < CFS_WORSEN_THRESHOLD)
            or (
                cfs_delta.delta_low_p05 is not None
                and cfs_delta.delta_low_p05 < CFS_SIGNIFICANT
            )
        )
    )


def _format_speed_delta(d: ComparedChannelDelta | None) -> str:
    return f"{d.delta:+.2f} mph" if d is not None and d.delta is not None else "N/A"


def _format_cfs_delta(d: ComparedChannelDelta | None) -> str:
    return f"{d.delta:+.3f} in" if d is not None and d.delta is not None else "N/A"


def _format_cfs_low_delta(d: ComparedChannelDelta | None) -> str | None:
    if d is None or d.delta_low_p05 is None:
        return None
    return f"{d.delta_low_p05:+.3f} in at the low 5th-percentile positions"


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


def _build_verdict_reference(discipline: TestDisciplineResult) -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="inconclusive",
        confidence_score=CONF_LOW,
        headline="No setup control changed; this is a repeatability reference, not a setup test.",
        evidence=[f"Test discipline: {discipline.label} ({discipline.score}/100)."],
        next_step="Use these runs to measure normal variation, or change exactly one setup control for a causal test.",
    )


def _build_verdict_retest_context(
    speed_delta: ComparedChannelDelta | None,
    evidence: list[str],
    next_step: str | None,
) -> DidItWorkVerdict:
    _changed, speed_gained, speed_lost = _speed_flags(speed_delta)
    if speed_gained:
        headline = "Speed improved, but uncontrolled context prevents attributing it to the setup."
    elif speed_lost:
        headline = "Speed dropped, but uncontrolled context prevents attributing it to the setup."
    else:
        headline = "Uncontrolled context prevents a causal setup verdict."
    return DidItWorkVerdict(
        verdict="retest",
        confidence_score=CONF_LOW,
        headline=headline,
        evidence=[f"Observed target-zone speed delta: {_format_speed_delta(speed_delta)}.", *evidence],
        next_step=next_step or (
            "Keep this as an observed result, then repeat the same one-change test "
            "under matched conditions before accepting a setup direction."
        ),
    )


def _build_verdict_missing_supporting_evidence(
    speed_delta: ComparedChannelDelta | None,
    missing_evidence: list[str],
) -> DidItWorkVerdict:
    return DidItWorkVerdict(
        verdict="retest",
        confidence_score=CONF_LOW,
        headline="A speed direction is visible, but supporting evidence is incomplete.",
        evidence=[
            f"Observed target-zone speed delta: {_format_speed_delta(speed_delta)}.",
            f"Missing comparison evidence: {', '.join(missing_evidence)}.",
        ],
        next_step="Repeat with complete platform and driver-input telemetry before accepting a setup direction.",
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
    low_delta = _format_cfs_low_delta(cfs_delta)
    evidence = [
        f"Speed delta: {_format_speed_delta(speed_delta)}",
        f"Average CFS delta: {_format_cfs_delta(cfs_delta)} (lower = riskier)",
    ]
    if low_delta is not None:
        evidence.append(f"Localized CFS change: {low_delta}.")
    return DidItWorkVerdict(
        verdict="retest",
        confidence_score=CONF_LOW,
        headline="Speed improved but splitter risk worsened — confirm tradeoff.",
        evidence=evidence,
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
    pace: PaceComparison | None = None,
    driver_changed: bool = False,
    driver_evidence_available: bool = True,
    context_blocks_attribution: bool = False,
    context_evidence: list[str] | None = None,
    context_retest_instruction: str | None = None,
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
    missing_supporting_evidence: list[str] = []
    if cfs_delta is None or cfs_delta.delta is None:
        missing_supporting_evidence.append("CFS ride-height delta")
    if not driver_evidence_available:
        missing_supporting_evidence.append("matched throttle, brake, and steering traces")
    discipline_ok = discipline.label in RELIABLE_DISCIPLINES

    if discipline.label == "invalid":
        result = _build_verdict_invalid()
    elif context_blocks_attribution:
        result = _build_verdict_retest_context(
            speed_delta,
            list(context_evidence or ["Required comparison context is uncontrolled or unavailable."]),
            context_retest_instruction,
        )
    elif discipline.label == "reference":
        result = _build_verdict_reference(discipline)
    elif not discipline_ok:
        result = _build_verdict_retest_discipline(discipline)
    elif missing_supporting_evidence and (speed_gained or speed_lost):
        result = _build_verdict_missing_supporting_evidence(
            speed_delta,
            missing_supporting_evidence,
        )
    elif driver_changed:
        result = DidItWorkVerdict(
            verdict="retest",
            confidence_score=CONF_LOW,
            headline="Driver inputs changed too much to isolate the setup effect.",
            evidence=["Throttle, brake, or steering traces diverged by track position."],
            next_step="Repeat the same setup test with a more repeatable driving trace.",
        )
    elif pace is not None and pace.direction == "insufficient_data":
        zone_direction = "improved" if speed_gained else "slowed" if speed_lost else "did not change clearly"
        result = DidItWorkVerdict(
            verdict="retest" if speed_gained or speed_lost else "inconclusive",
            confidence_score=min(CONF_LOW, pace.confidence_score),
            headline="A direction is visible, but there are not enough clean laps to prove it." if speed_gained or speed_lost else "Not enough clean laps for a setup verdict.",
            evidence=[
                f"Target-zone speed {zone_direction} ({_format_speed_delta(speed_delta)}).",
                f"Eligible laps: {pace.baseline_eligible_laps} baseline / {pace.test_eligible_laps} test.",
            ],
            next_step="Run at least three eligible laps on both setups under comparable conditions.",
        )
    elif pace is not None and pace.direction == "no_clear_difference":
        result = DidItWorkVerdict(
            verdict="inconclusive",
            confidence_score=max(CONF_NOISE, min(CONF_MEDIUM, pace.confidence_score)),
            headline="Whole-lap pace stayed inside the measured noise band.",
            evidence=[
                f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap delta unavailable.",
                f"Noise band: ±{pace.noise_band_s:.3f} s." if pace.noise_band_s is not None else "Noise band unavailable.",
            ],
            next_step="Repeat the same one-control test before changing direction.",
        )
    elif pace is not None and pace.direction == "faster":
        if speed_gained and not cfs_worse:
            base = _build_verdict_keep_direction(speed_delta, cfs_delta, discipline)
            result = DidItWorkVerdict(
                verdict=base.verdict,
                confidence_score=max(CONF_MEDIUM, min(CONF_HIGH, pace.confidence_score)),
                headline="Repeatable whole-lap pace and target-zone speed improved.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap improved.",
                    *base.evidence,
                ],
                next_step=base.next_step,
            )
        else:
            result = DidItWorkVerdict(
                verdict="retest",
                confidence_score=min(CONF_MEDIUM, pace.confidence_score),
                headline="Whole-lap pace improved, but the target-zone or platform evidence is mixed.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap improved.",
                    f"Target-zone speed delta: {_format_speed_delta(speed_delta)}.",
                    f"CFS delta: {_format_cfs_delta(cfs_delta)}.",
                ],
                next_step="Repeat the same setup before accepting the tradeoff.",
            )
    elif pace is not None and pace.direction == "slower":
        if speed_gained:
            result = DidItWorkVerdict(
                verdict="retest",
                confidence_score=min(CONF_MEDIUM, pace.confidence_score),
                headline="The target zone improved, but repeatable whole-lap pace became slower.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap slowed.",
                    f"Target-zone speed delta: {_format_speed_delta(speed_delta)}.",
                ],
                next_step="Retest before keeping a local gain that costs time elsewhere.",
            )
        else:
            base = _build_verdict_undo(speed_delta)
            result = DidItWorkVerdict(
                verdict="undo",
                confidence_score=max(CONF_MEDIUM, min(CONF_HIGH, pace.confidence_score)),
                headline="Repeatable whole-lap pace became slower.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap slowed.",
                    *base.evidence,
                ],
                next_step=base.next_step,
            )
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
