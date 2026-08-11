from __future__ import annotations

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    ComparisonObservation,
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


def _build_verdict_invalid() -> ComparisonObservation:
    return ComparisonObservation(
        observation_state="inconclusive",
        confidence_score=CONF_INVALID,
        headline="Comparison conditions do not support setup attribution.",
        evidence=["Too many uncontrolled variables."],
    )


def _build_verdict_retest_discipline(discipline: TestDisciplineResult) -> ComparisonObservation:
    return ComparisonObservation(
        observation_state="needs_confirmation",
        confidence_score=CONF_RETEST_DISCIPLINE,
        headline="Multiple changes prevent an isolated comparison observation.",
        evidence=[f"Test discipline: {discipline.label} ({discipline.score}/100)."],
    )


def _build_verdict_reference(discipline: TestDisciplineResult) -> ComparisonObservation:
    return ComparisonObservation(
        observation_state="inconclusive",
        confidence_score=CONF_LOW,
        headline="No setup control changed; this is a repeatability reference, not a setup test.",
        evidence=[f"Test discipline: {discipline.label} ({discipline.score}/100)."],
    )


def _build_verdict_retest_context(
    speed_delta: ComparedChannelDelta | None,
    evidence: list[str],
) -> ComparisonObservation:
    _changed, speed_gained, speed_lost = _speed_flags(speed_delta)
    if speed_gained:
        headline = "Speed improved, but uncontrolled context prevents attributing it to the setup."
    elif speed_lost:
        headline = "Speed dropped, but uncontrolled context prevents attributing it to the setup."
    else:
        headline = "Uncontrolled context prevents a causal setup observation."
    return ComparisonObservation(
        observation_state="needs_confirmation",
        confidence_score=CONF_LOW,
        headline=headline,
        evidence=[f"Observed target-zone speed delta: {_format_speed_delta(speed_delta)}.", *evidence],
    )


def _build_verdict_missing_supporting_evidence(
    speed_delta: ComparedChannelDelta | None,
    missing_evidence: list[str],
) -> ComparisonObservation:
    return ComparisonObservation(
        observation_state="needs_confirmation",
        confidence_score=CONF_LOW,
        headline="A speed direction is visible, but supporting evidence is incomplete.",
        evidence=[
            f"Observed target-zone speed delta: {_format_speed_delta(speed_delta)}.",
            f"Missing comparison evidence: {', '.join(missing_evidence)}.",
        ],
    )


def _build_verdict_observed_improvement(
    speed_delta: ComparedChannelDelta | None,
    cfs_delta: ComparedChannelDelta | None,
    discipline: TestDisciplineResult,
) -> ComparisonObservation:
    evidence: list[str] = [f"Speed delta: {_format_speed_delta(speed_delta)}"]
    if cfs_delta and cfs_delta.delta is not None:
        evidence.append(f"CFS delta: {_format_cfs_delta(cfs_delta)}")
    return ComparisonObservation(
        observation_state="observed_improvement",
        confidence_score=CONF_HIGH if discipline.label == "clean" else CONF_KEEP_MIXED,
        headline="Target-zone speed improved while splitter risk did not worsen.",
        evidence=evidence,
    )


def _build_verdict_retest_tradeoff(
    speed_delta: ComparedChannelDelta | None,
    cfs_delta: ComparedChannelDelta | None,
) -> ComparisonObservation:
    low_delta = _format_cfs_low_delta(cfs_delta)
    evidence = [
        f"Speed delta: {_format_speed_delta(speed_delta)}",
        f"Average CFS delta: {_format_cfs_delta(cfs_delta)} (lower = riskier)",
    ]
    if low_delta is not None:
        evidence.append(f"Localized CFS change: {low_delta}.")
    return ComparisonObservation(
        observation_state="needs_confirmation",
        confidence_score=CONF_LOW,
        headline="Speed improved while splitter risk worsened; the comparison shows a tradeoff.",
        evidence=evidence,
    )


def _build_verdict_observed_regression(
    speed_delta: ComparedChannelDelta | None,
) -> ComparisonObservation:
    return ComparisonObservation(
        observation_state="observed_regression",
        confidence_score=CONF_MEDIUM,
        headline="Target-zone speed dropped in the compared run.",
        evidence=[f"Speed delta: {_format_speed_delta(speed_delta)}"],
    )


def _build_verdict_inconclusive(speed_delta: ComparedChannelDelta | None) -> ComparisonObservation:
    has_data = speed_delta is not None and speed_delta.delta is not None
    evidence = "Speed delta is within noise range." if has_data else "Speed telemetry was unavailable in the target zone."
    
    return ComparisonObservation(
        observation_state="inconclusive",
        confidence_score=CONF_NOISE,
        headline="No clear speed difference detected.",
        evidence=[evidence],
    )


def compute_observation(
    target_zone: TargetZoneComparison,
    discipline: TestDisciplineResult,
    is_same_run: bool = False,
    pace: PaceComparison | None = None,
    driver_changed: bool = False,
    driver_evidence_available: bool = True,
    context_blocks_attribution: bool = False,
    context_evidence: list[str] | None = None,
) -> ComparisonObservation:
    speed_delta = _speed_delta_info(target_zone)
    if is_same_run:
        return ComparisonObservation(
            observation_state="inconclusive",
            confidence_score=1.0,
            headline="Baseline Reference: You are comparing a run to itself.",
            evidence=["Telemetry is identical."],
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
        result = ComparisonObservation(
            observation_state="needs_confirmation",
            confidence_score=CONF_LOW,
            headline="Driver inputs changed too much to isolate the setup effect.",
            evidence=["Throttle, brake, or steering traces diverged by track position."],
        )
    elif pace is not None and pace.direction == "insufficient_data":
        zone_direction = "improved" if speed_gained else "slowed" if speed_lost else "did not change clearly"
        result = ComparisonObservation(
            observation_state="needs_confirmation" if speed_gained or speed_lost else "inconclusive",
            confidence_score=min(CONF_LOW, pace.confidence_score),
            headline="A direction is visible, but there are not enough clean laps to prove it." if speed_gained or speed_lost else "Not enough clean laps for a setup observation.",
            evidence=[
                f"Target-zone speed {zone_direction} ({_format_speed_delta(speed_delta)}).",
                f"Eligible laps: {pace.baseline_eligible_laps} baseline / {pace.test_eligible_laps} test.",
            ],
        )
    elif pace is not None and pace.direction == "no_clear_difference":
        result = ComparisonObservation(
            observation_state="inconclusive",
            confidence_score=max(CONF_NOISE, min(CONF_MEDIUM, pace.confidence_score)),
            headline="Whole-lap pace stayed inside the measured noise band.",
            evidence=[
                f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap delta unavailable.",
                f"Noise band: ±{pace.noise_band_s:.3f} s." if pace.noise_band_s is not None else "Noise band unavailable.",
            ],
        )
    elif pace is not None and pace.direction == "faster":
        if speed_gained and not cfs_worse:
            base = _build_verdict_observed_improvement(speed_delta, cfs_delta, discipline)
            result = ComparisonObservation(
                observation_state=base.observation_state,
                confidence_score=max(CONF_MEDIUM, min(CONF_HIGH, pace.confidence_score)),
                headline="Repeatable whole-lap pace and target-zone speed improved.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap improved.",
                    *base.evidence,
                ],
            )
        else:
            result = ComparisonObservation(
                observation_state="needs_confirmation",
                confidence_score=min(CONF_MEDIUM, pace.confidence_score),
                headline="Whole-lap pace improved, but the target-zone or platform evidence is mixed.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap improved.",
                    f"Target-zone speed delta: {_format_speed_delta(speed_delta)}.",
                    f"CFS delta: {_format_cfs_delta(cfs_delta)}.",
                ],
            )
    elif pace is not None and pace.direction == "slower":
        if speed_gained:
            result = ComparisonObservation(
                observation_state="needs_confirmation",
                confidence_score=min(CONF_MEDIUM, pace.confidence_score),
                headline="The target zone improved, but repeatable whole-lap pace became slower.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap slowed.",
                    f"Target-zone speed delta: {_format_speed_delta(speed_delta)}.",
                ],
            )
        else:
            base = _build_verdict_observed_regression(speed_delta)
            result = ComparisonObservation(
                observation_state="observed_regression",
                confidence_score=max(CONF_MEDIUM, min(CONF_HIGH, pace.confidence_score)),
                headline="Repeatable whole-lap pace became slower.",
                evidence=[
                    f"Median lap delta: {pace.cohort_delta_s:+.3f} s." if pace.cohort_delta_s is not None else "Median lap slowed.",
                    *base.evidence,
                ],
            )
    elif speed_gained and not cfs_worse:
        result = _build_verdict_observed_improvement(speed_delta, cfs_delta, discipline)
    elif speed_gained and cfs_worse:
        result = _build_verdict_retest_tradeoff(speed_delta, cfs_delta)
    elif speed_lost:
        result = _build_verdict_observed_regression(speed_delta)
    else:
        result = _build_verdict_inconclusive(speed_delta)

    warnings = list(result.warnings)
    if discipline.label in ("mixed", "weak"):
        msg = "Low test discipline — result may not be reproducible."
        warnings.append(msg)
    for factor in discipline.negative_factors:
        if factor not in warnings:
            warnings.append(factor)

    return ComparisonObservation(
        observation_state=result.observation_state,
        confidence_score=result.confidence_score,
        headline=result.headline,
        evidence=result.evidence,
        warnings=warnings,
    )
