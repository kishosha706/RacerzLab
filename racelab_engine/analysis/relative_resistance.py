"""Controlled A/B/A resistance-like and scrub diagnosis using relative proxies only."""

from __future__ import annotations

from statistics import mean, median
from typing import Any, Literal

from pydantic import Field

from racelab_engine.analysis.evidence_contracts import (
    EvidenceEvaluationInput,
    RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT,
    evaluate_evidence_contract,
)
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.p3_common import bounded_confidence, finite, lap_number, lap_pct
from racelab_engine.analysis.proximity_context import ProximityContext, classify_proximity_time_gap_window
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary


class ResistanceWindow(EngineeringModel):
    label: Literal["A1", "B", "A2"]
    sample_count: int
    median_speed_mph: float | None = None
    median_rpm: float | None = None
    dominant_gear: int | None = None
    median_speed_loss_mph_s: float | None = None
    speed_loss_range_mph_s: tuple[float, float] | None = None
    proximity: ProximityContext


class GradeMatchEvidence(EngineeringModel):
    available: bool = False
    matched: bool | None = None
    declared_source_healthy: bool = False
    map_identity_matched: bool = False
    paired_interval_count: int = 0
    coverage_fraction: float = 0.0
    median_grade_pct_by_window: dict[str, float] = Field(default_factory=dict)
    p90_grade_spread_percentage_points: float | None = None
    max_grade_spread_percentage_points: float | None = None
    p90_relative_altitude_spread_m: float | None = None
    explanation: str
    source_channels: list[str] = Field(default_factory=list)


class RelativeResistanceReport(EngineeringModel):
    gate: EngineGate
    windows: list[ResistanceWindow] = Field(default_factory=list)
    aba_confirmed: bool = False
    practical_minimum_mph_s: float | None = None
    relative_speed_loss_delta_mph_s: float | None = None
    relative_speed_loss_range_mph_s: tuple[float, float] | None = None
    grade_match: GradeMatchEvidence | None = None
    cause_scores: dict[str, float] = Field(default_factory=dict)
    unavailable_cause_buckets: list[str] = Field(default_factory=list)
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


def _percentile(items: list[float], fraction: float) -> float | None:
    if not items:
        return None
    ordered = sorted(items)
    index = int(round((len(ordered) - 1) * fraction))
    return ordered[index]


def _coastdown_rows(rows: list[dict[str, Any]], selected_lap: int) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        speed = finite(row.get("speed_mph"))
        throttle = finite(row.get("throttle_pct"))
        brake = finite(row.get("brake_pct"))
        steering = finite(row.get("abs_steering_deg"))
        loss = finite(row.get("speed_rate_mph_s"))
        if (
            lap_number(row) == selected_lap
            and None not in (speed, throttle, brake, steering, loss)
            and speed >= 80.0
            and throttle <= 2.0
            and brake <= 1.0
            and abs(steering) <= 2.0
            and loss < 0.0
        ):
            result.append(row)
    return result


def _median(rows: list[dict[str, Any]], channel: str) -> float | None:
    items = [value for row in rows if (value := finite(row.get(channel))) is not None]
    return median(items) if items else None


def _window(label: Literal["A1", "B", "A2"], rows: list[dict[str, Any]]) -> ResistanceWindow:
    losses = [-float(value) for row in rows if (value := finite(row.get("speed_rate_mph_s"))) is not None]
    gears = [int(value) for row in rows if (value := finite(row.get("gear"))) is not None and value > 0]
    return ResistanceWindow(
        label=label,
        sample_count=len(rows),
        median_speed_mph=_median(rows, "speed_mph"),
        median_rpm=_median(rows, "rpm"),
        dominant_gear=max(set(gears), key=gears.count) if gears else None,
        median_speed_loss_mph_s=median(losses) if losses else None,
        speed_loss_range_mph_s=(float(_percentile(losses, 0.25)), float(_percentile(losses, 0.75))) if losses else None,
        proximity=classify_proximity_time_gap_window(rows),
    )


def _interpolate_rows_at_common_positions(
    row_sets: tuple[list[dict[str, Any]], ...],
    *,
    step_pct: float = 0.25,
) -> tuple[tuple[list[dict[str, Any]], ...], float, bool]:
    positioned = [
        sorted(
            [(pct, row) for row in rows if (pct := lap_pct(row)) is not None],
            key=lambda item: item[0],
        )
        for rows in row_sets
    ]
    if not all(positioned):
        return tuple([] for _ in row_sets), -1.0, False
    start = max(items[0][0] for items in positioned)
    end = min(items[-1][0] for items in positioned)
    span = end - start
    maximum_gap = max(
        max((right[0] - left[0] for left, right in zip(items, items[1:])), default=0.0)
        for items in positioned
    )
    if span < 5.0 or maximum_gap > 2.0:
        return tuple([] for _ in row_sets), span, False
    grid = [start + index * step_pct for index in range(int(span / step_pct) + 1)]
    aligned: list[list[dict[str, Any]]] = []
    for items in positioned:
        cursor = 0
        output: list[dict[str, Any]] = []
        for target in grid:
            while cursor + 1 < len(items) and items[cursor + 1][0] < target:
                cursor += 1
            left_pct, left = items[cursor]
            right_pct, right = items[min(cursor + 1, len(items) - 1)]
            fraction = 0.0 if right_pct <= left_pct else (target - left_pct) / (right_pct - left_pct)
            channels = set(left) | set(right)
            interpolated: dict[str, Any] = {"lap_dist_pct": target / 100.0}
            for channel in channels:
                left_value = finite(left.get(channel))
                right_value = finite(right.get(channel))
                if left_value is not None and right_value is not None:
                    interpolated[channel] = left_value + (right_value - left_value) * fraction
            output.append(interpolated)
        aligned.append(output)
    return tuple(aligned), span, True


def _matched_context(row_sets: tuple[list[dict[str, Any]], ...]) -> bool:
    tolerances = {
        "air_density": (0.04, 0.03),
        "air_temp": (3.0, 0.0),
        "track_temp": (5.0, 0.0),
        "wind_vel": (2.0, 0.15),
        "fuel_level": (1.0, 0.05),
        "lf_tire_distance_m": (500.0, 0.10),
        "rf_tire_distance_m": (500.0, 0.10),
        "lr_tire_distance_m": (500.0, 0.10),
        "rr_tire_distance_m": (500.0, 0.10),
    }
    for channel, (absolute, relative) in tolerances.items():
        values = [_median(rows, channel) for rows in row_sets]
        if any(value is None for value in values):
            return False
        spread = max(float(value) for value in values) - min(float(value) for value in values)
        center = abs(mean(float(value) for value in values))
        if spread > max(absolute, relative * max(1.0, center)):
            return False
    directions = [_median(rows, "wind_dir") for rows in row_sets]
    if any(value is None for value in directions):
        return False
    if all(value is not None for value in directions):
        numeric_directions = [float(value) for value in directions]
        if max(abs(value) for value in numeric_directions) <= 2.0 * 3.141592653589793 + 0.01:
            numeric_directions = [value * 180.0 / 3.141592653589793 for value in numeric_directions]
        pair_differences = [
            min(abs(float(left) - float(right)) % 360.0, 360.0 - (abs(float(left) - float(right)) % 360.0))
            for index, left in enumerate(numeric_directions)
            for right in numeric_directions[index + 1:]
        ]
        if pair_differences and max(pair_differences) > 20.0:
            return False
    return True


def _measured_grade_match(
    row_sets: tuple[list[dict[str, Any]], ...],
    *,
    declared_source_healthy: bool,
    map_identity_matched: bool,
    stride: int = 4,
) -> GradeMatchEvidence:
    if not declared_source_healthy or not map_identity_matched:
        missing = []
        if not declared_source_healthy:
            missing.append("healthy file-declared Alt/LapDist channels with meter units")
        if not map_identity_matched:
            missing.append("matching track/map identity")
        return GradeMatchEvidence(
            declared_source_healthy=declared_source_healthy,
            map_identity_matched=map_identity_matched,
            explanation="Measured grade context is unavailable without " + " and ".join(missing) + ".",
        )
    if not row_sets or min((len(rows) for rows in row_sets), default=0) <= stride:
        return GradeMatchEvidence(
            declared_source_healthy=declared_source_healthy,
            map_identity_matched=map_identity_matched,
            explanation="Measured grade context is unavailable because the common-position window is too short.",
        )
    count = min(len(rows) for rows in row_sets)
    grade_by_window: list[list[float]] = [[] for _ in row_sets]
    grade_spreads: list[float] = []
    for index in range(count - stride):
        interval_grades: list[float] = []
        for rows in row_sets:
            start_distance = finite(rows[index].get("lap_dist_m"))
            end_distance = finite(rows[index + stride].get("lap_dist_m"))
            start_altitude = finite(rows[index].get("alt"))
            end_altitude = finite(rows[index + stride].get("alt"))
            if None in (start_distance, end_distance, start_altitude, end_altitude):
                interval_grades = []
                break
            distance = float(end_distance) - float(start_distance)
            if distance <= 1.0:
                interval_grades = []
                break
            grade_pct = (float(end_altitude) - float(start_altitude)) / distance * 100.0
            if abs(grade_pct) > 30.0:
                interval_grades = []
                break
            interval_grades.append(grade_pct)
        if len(interval_grades) == len(row_sets):
            grade_spreads.append(max(interval_grades) - min(interval_grades))
            for window_grades, grade_pct in zip(grade_by_window, interval_grades):
                window_grades.append(grade_pct)

    altitude_offsets: list[float | None] = []
    for rows in row_sets:
        altitude_offsets.append(next(
            (value for row in rows if (value := finite(row.get("alt"))) is not None),
            None,
        ))
    altitude_spreads: list[float] = []
    if all(value is not None for value in altitude_offsets):
        for index in range(count):
            relative_altitudes = [
                float(altitude) - float(offset)
                for rows, offset in zip(row_sets, altitude_offsets)
                if (altitude := finite(rows[index].get("alt"))) is not None
                and offset is not None
            ]
            if len(relative_altitudes) == len(row_sets):
                altitude_spreads.append(max(relative_altitudes) - min(relative_altitudes))

    expected_intervals = max(1, count - stride)
    coverage = len(grade_spreads) / expected_intervals
    grade_p90 = _percentile(grade_spreads, 0.90)
    grade_max = max(grade_spreads) if grade_spreads else None
    altitude_p90 = _percentile(altitude_spreads, 0.90)
    altitude_ranges = []
    for rows in row_sets:
        values = [float(value) for row in rows if (value := finite(row.get("alt"))) is not None]
        altitude_ranges.append(max(values) - min(values) if values else None)
    available = bool(
        coverage >= 0.90
        and len(altitude_spreads) / count >= 0.90
        and all(grade_by_window)
        and all(value is not None and value >= 0.05 for value in altitude_ranges)
    )
    matched = (
        bool(
            grade_p90 is not None and grade_p90 <= 0.75
            and grade_max is not None and grade_max <= 2.0
            and altitude_p90 is not None and altitude_p90 <= 0.75
        )
        if available else None
    )
    labels = ("A1", "B", "A2")
    medians = {
        label: round(median(items), 4)
        for label, items in zip(labels, grade_by_window)
        if items
    }
    if not available:
        explanation = (
            "Measured Alt/LapDist coverage is incomplete; grade is withheld as a specific cause."
        )
    elif matched:
        explanation = (
            "Measured altitude-versus-distance grade shape agrees across A1/B/A2 at common track positions."
        )
    else:
        explanation = (
            "Measured grade shape does not agree across A1/B/A2; grade-specific attribution is withheld."
        )
    return GradeMatchEvidence(
        available=available,
        matched=matched,
        declared_source_healthy=declared_source_healthy,
        map_identity_matched=map_identity_matched,
        paired_interval_count=len(grade_spreads),
        coverage_fraction=round(coverage, 4),
        median_grade_pct_by_window=medians,
        p90_grade_spread_percentage_points=grade_p90,
        max_grade_spread_percentage_points=grade_max,
        p90_relative_altitude_spread_m=altitude_p90,
        explanation=explanation,
        source_channels=["lap_dist_pct", "lap_dist_m", "alt"] if available else [],
    )


def analyze_relative_resistance_aba(
    a1_rows: list[dict[str, Any]],
    b_rows: list[dict[str, Any]],
    a2_rows: list[dict[str, Any]],
    *,
    lap_summaries: tuple[list[LapSummary], list[LapSummary], list[LapSummary]],
    selected_laps: tuple[int, int, int],
    sim_integrity_clear: tuple[bool | None, bool | None, bool | None],
    sim_integrity_confidence_caps: tuple[float, float, float] = (1.0, 1.0, 1.0),
    isolated_single_change: bool,
    grade_source_declared_healthy: bool = False,
    grade_map_identity_matched: bool = False,
) -> RelativeResistanceReport:
    raw_sets = (a1_rows, b_rows, a2_rows)
    raw_coast_sets = tuple(_coastdown_rows(rows, lap) for rows, lap in zip(raw_sets, selected_laps))
    coast_sets, overlap, matched_coverage = _interpolate_rows_at_common_positions(raw_coast_sets)
    windows = [
        _window(label, rows)
        for label, rows in zip(("A1", "B", "A2"), coast_sets)
    ]
    selected_eligible = all(
        selected in {lap.lap_number for lap in eligible_laps(summaries)}
        for summaries, selected in zip(lap_summaries, selected_laps)
    )
    speeds = [window.median_speed_mph for window in windows]
    rpms = [window.median_rpm for window in windows]
    gears = [window.dominant_gear for window in windows]
    paired_operating = []
    grid_count = min((len(rows) for rows in coast_sets), default=0)
    for index in range(grid_count):
        point_speeds = [finite(rows[index].get("speed_mph")) for rows in coast_sets]
        point_rpms = [finite(rows[index].get("rpm")) for rows in coast_sets]
        point_gears = [finite(rows[index].get("gear")) for rows in coast_sets]
        if all(value is not None for value in (*point_speeds, *point_rpms, *point_gears)):
            paired_operating.append((
                max(float(value) for value in point_speeds) - min(float(value) for value in point_speeds),
                max(float(value) for value in point_rpms) - min(float(value) for value in point_rpms),
                len({int(float(value)) for value in point_gears}) == 1,
            ))
    speed_spreads = [item[0] for item in paired_operating]
    rpm_spreads = [item[1] for item in paired_operating]
    matched_operating = (
        all(value is not None for value in (*speeds, *rpms, *gears))
        and grid_count > 0
        and len(paired_operating) / grid_count >= 0.95
        and speed_spreads
        and mean(speed_spreads) <= 1.5
        and (_percentile(speed_spreads, 0.9) or 0.0) <= 3.0
        and max(speed_spreads) <= 5.0
        and rpm_spreads
        and mean(rpm_spreads) <= 150.0
        and (_percentile(rpm_spreads, 0.9) or 0.0) <= 300.0
        and max(rpm_spreads) <= 500.0
        and all(item[2] for item in paired_operating)
    )
    matched_context = _matched_context(coast_sets)
    grade_match = _measured_grade_match(
        coast_sets,
        declared_source_healthy=grade_source_declared_healthy,
        map_identity_matched=grade_map_identity_matched,
    )
    proximity_blocked = any(window.proximity.blocks_relative_resistance for window in windows)
    integrity_failure = any(value is not True for value in sim_integrity_clear)
    usable_by_window = [
        {channel for row in rows for channel, value in row.items() if finite(value) is not None}
        for rows in coast_sets
    ]
    usable = frozenset(set.intersection(*usable_by_window)) if usable_by_window else frozenset()
    discriminator_channels = frozenset({
        "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
        "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
        "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
    })
    discriminator_sources_available = discriminator_channels.issubset(usable)
    requested_outputs = {"relative_speed_loss_delta", "relative_resistance_direction"}
    if discriminator_sources_available:
        requested_outputs.add("resistance_cause_hypothesis")
    if grade_match.available:
        requested_outputs.add("measured_grade_context")
    evaluation = evaluate_evidence_contract(
        RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT,
        EvidenceEvaluationInput(
            usable_channels=usable,
            condition_results={
                "complete_flying_lap_coverage": selected_eligible,
                "matched_track_position": matched_coverage and overlap >= 5.0,
                "matched_operating_point": matched_operating,
                "matched_fuel_tire_weather_context": matched_context,
                "matched_measured_grade_context": grade_match.matched,
            },
            blocker_results={
                "junk_lap_context": not selected_eligible,
                "sample_or_sim_integrity_failure": integrity_failure,
                "unisolated_setup_change": not isolated_single_change,
                "nearby_car_context_uncertain": proximity_blocked,
            },
            repetitions=3,
            requested_outputs=frozenset(requested_outputs),
        ),
    )
    cap = min(
        evaluation.confidence_cap,
        *(bounded_confidence(value) for value in sim_integrity_confidence_caps),
    )
    gate = EngineGate(
        contract_key=evaluation.contract_key,
        eligible=evaluation.eligible,
        confidence_cap=cap,
        blocker_reasons=[item.message for item in evaluation.blockers],
        needed_measurements=[item.instruction for item in evaluation.needed_measurements],
    )
    if not evaluation.eligible:
        return RelativeResistanceReport(
            gate=gate,
            windows=windows,
            grade_match=grade_match,
            conclusions=[EngineeringConclusion(
                key="relative_resistance_blocked",
                summary="A/B/A resistance comparison is blocked by unmatched or uncertain context.",
                evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                confidence_score=0.0,
                blocker_reasons=gate.blocker_reasons,
            )],
        )
    a1, b, a2 = (window.median_speed_loss_mph_s for window in windows)
    assert a1 is not None and b is not None and a2 is not None
    baseline = mean((a1, a2))
    delta = b - baseline
    aba_tolerance = max(0.05, baseline * 0.15)
    a_distribution_widths = [
        bounds[1] - bounds[0]
        for window in (windows[0], windows[2])
        if (bounds := window.speed_loss_range_mph_s) is not None
    ]
    practical_minimum = max(
        0.02,
        abs(a1 - a2) * 1.5,
        median(a_distribution_widths) if a_distribution_widths else 0.0,
    )
    confirmed = bool(
        abs(a1 - a2) <= aba_tolerance
        and abs(delta) >= practical_minimum
        and (
            b >= max(a1, a2) + practical_minimum
            or b <= min(a1, a2) - practical_minimum
        )
    )
    lower = b - max(a1, a2)
    upper = b - min(a1, a2)
    steering = mean(abs(_median(rows, "abs_steering_deg") or 0.0) for rows in coast_sets)
    slip_channels = tuple(f"{corner}_slip_ratio" for corner in ("lf", "rf", "lr", "rr"))
    slip_values = [_median(rows, channel) for rows in coast_sets for channel in slip_channels]
    pressure_channels = (
        "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar", "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
    )
    brake_pressure_values = [_median(rows, channel) for rows in coast_sets for channel in pressure_channels]
    slip = mean(abs(float(value)) for value in slip_values) if all(value is not None for value in slip_values) else None
    brake_pressure = (
        mean(abs(float(value)) for value in brake_pressure_values)
        if all(value is not None for value in brake_pressure_values) else None
    )
    discriminators_complete = slip is not None and brake_pressure is not None
    unavailable_buckets = []
    cause_scores = {
        "steering_input": round(min(1.0, steering / 2.0), 3),
        "powertrain_context": 0.1,
        "wind_context": 0.1,
        "proximity_context": 0.0,
        "unknown_residual": 0.85 if not discriminators_complete else 0.35 if not confirmed else 0.15,
    }
    if slip is None:
        unavailable_buckets.extend(["tire_scrub_or_wheel_mismatch", "platform_or_aero_related_proxy"])
    else:
        cause_scores["tire_scrub_or_wheel_mismatch"] = round(min(1.0, slip * 10.0), 3)
    if brake_pressure is None:
        unavailable_buckets.extend(["brake_drag_suspicion", "platform_or_aero_related_proxy"])
    else:
        cause_scores["brake_drag_suspicion"] = round(min(1.0, brake_pressure / 5.0), 3)
    if discriminators_complete:
        cause_scores["platform_or_aero_related_proxy"] = round(
            0.65 if confirmed and steering < 0.5 and slip < 0.02 and brake_pressure < 1.0 else 0.2,
            3,
        )
    if grade_match.available and grade_match.matched:
        cause_scores["measured_grade_context"] = 0.0
    else:
        unavailable_buckets.append("measured_grade_context")
    if not confirmed:
        unavailable_buckets.extend(cause_scores.keys() - {"unknown_residual"})
        cause_scores = {"unknown_residual": 1.0}
    delta_sources = ["lap_dist_pct", "speed_mph", "speed_rate_mph_s"]
    context_source_candidates = {
        "air_density", "air_temp", "track_temp", "wind_vel", "wind_dir", "fuel_level",
        "lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m",
        "car_distance_ahead_m", "car_distance_behind_m",
        "lap_dist_m", "alt",
    }
    cause_sources = sorted(
        set(RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT.required_channels)
        | (discriminator_channels & usable)
        | (context_source_candidates & usable)
    )
    support = [
        f"A1/B/A2 median speed-loss proxies: {a1:.4f}/{b:.4f}/{a2:.4f} mph/s.",
        f"B minus A-envelope residual range: {lower:.4f} to {upper:.4f} mph/s.",
        f"A/B/A return confirmation: {'passed' if confirmed else 'not established'}.",
        f"Predeclared/noise-aware practical minimum: {practical_minimum:.4f} mph/s.",
        grade_match.explanation,
    ]
    contradictions = [
        "This is a relative road-load acceleration proxy, not exact aerodynamic drag, CdA, or horsepower loss.",
        "Platform, tire scrub, wheel-speed mismatch, brake drag, powertrain, grade, wind, and unknown residual remain competing causes.",
        *(["Slip and/or brake-line-pressure discriminators are unavailable; platform/aero ranking is withheld."] if not discriminators_complete else []),
        *[window.proximity.explanation for window in windows],
        *(
            ["Grade is not ranked because measured altitude/distance matching is unavailable or failed."]
            if grade_match.matched is not True else []
        ),
    ]
    grade_conclusion = (
        EngineeringConclusion(
            key="measured_grade_context",
            summary=(
                "Measured grade shape is matched; grade is controlled context, not a ranked explanation for the A/B/A difference."
                if grade_match.matched
                else "Measured grade shape failed to match; grade-specific attribution is withheld."
            ),
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=min(0.75 if grade_match.matched else 0.4, cap),
            source_channels=grade_match.source_channels,
            supporting_evidence=[grade_match.explanation],
            contradicting_evidence=[
                "Grade is calculated from measured altitude change over measured lap distance; it is not surveyed track elevation."
            ],
        )
        if grade_match.available else EngineeringConclusion(
            key="measured_grade_context",
            summary="Measured grade matching is unavailable, so grade is not ranked as a cause.",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            confidence_score=0.0,
            blocker_reasons=[grade_match.explanation],
        )
    )
    return RelativeResistanceReport(
        gate=gate,
        windows=windows,
        aba_confirmed=confirmed,
        practical_minimum_mph_s=practical_minimum,
        relative_speed_loss_delta_mph_s=delta,
        relative_speed_loss_range_mph_s=(lower, upper),
        grade_match=grade_match,
        cause_scores=cause_scores,
        unavailable_cause_buckets=sorted(set(unavailable_buckets)),
        conclusions=[
            EngineeringConclusion(
                key="relative_speed_loss_delta",
                summary=f"B changed the matched speed-loss proxy by {delta:+.4f} mph/s versus the A return average.",
                evidence_state=EvidenceState.CALCULATED,
                confidence_score=min(0.85 if confirmed else 0.55, cap),
                source_channels=delta_sources,
                supporting_evidence=support,
                contradicting_evidence=contradictions,
            ),
            EngineeringConclusion(
                key="resistance_cause_hypothesis",
                summary="Cause buckets are proxy-ranked and require one-change confirmation.",
                evidence_state=EvidenceState.ESTIMATED_PROXY,
                confidence_score=min(0.65 if confirmed else 0.4, cap),
                source_channels=cause_sources,
                supporting_evidence=support,
                contradicting_evidence=contradictions,
            ),
            grade_conclusion,
        ],
    )


__all__ = [
    "GradeMatchEvidence", "RelativeResistanceReport", "ResistanceWindow",
    "analyze_relative_resistance_aba",
]
