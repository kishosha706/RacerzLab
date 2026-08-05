"""Fuel, tire-life, and long-run strategy evidence with adequate-length gates."""

from __future__ import annotations

import math
from statistics import mean, median
from typing import Any, Literal

from pydantic import Field

from racelab_engine.analysis.evidence_contracts import EvidenceEvaluationInput, evaluate_evidence_contract
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.p3_common import (
    bounded_confidence,
    finite,
    lap_number,
    lap_pct,
    percentile,
)
from racelab_engine.analysis.p3_contracts import STINT_STRATEGY_CONTRACT
from racelab_engine.analysis.test_director import MeasurementMission
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary


class StintLapPoint(EngineeringModel):
    lap_number: int
    lap_time_s: float
    fuel_start: float | None = None
    fuel_end: float | None = None
    fuel_burn: float | None = None
    average_tire_temp: float | None = None
    average_tire_distance_m: float | None = None


class TireLifePoint(EngineeringModel):
    lap_number: int
    tire_distance_m: float | None = None
    minimum_remaining_wear_pct: float


class TireLifeCurve(EngineeringModel):
    corner: Literal["LF", "RF", "LR", "RR"]
    points: list[TireLifePoint] = Field(default_factory=list)
    observed_remaining_range_pct: tuple[float, float] | None = None
    wear_loss_percentage_points_per_lap: float | None = None
    wear_loss_percentage_points_per_1000m: float | None = None
    wear_loss_percentage_points_per_1000m_range: tuple[float, float] | None = None
    monotonic_transition_fraction: float | None = None
    replicated_tire_sets: int = 0
    right_censored: bool = True
    trend_established: bool = False
    blocker_reasons: list[str] = Field(default_factory=list)


class PitWindowRecommendation(EngineeringModel):
    status: Literal["available", "blocked"]
    current_completed_lap: int | None = None
    earliest_laps_from_now: int | None = None
    latest_laps_from_now: int | None = None
    earliest_pit_lap: int | None = None
    latest_pit_lap: int | None = None
    limiting_factor: Literal["fuel", "unknown"] = "unknown"
    classification: Literal["fuel_exhaustion_service_bound", "strategy_window"] = (
        "fuel_exhaustion_service_bound"
    )
    strategy_ready: bool = False
    available_tire_sets: int | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    basis: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    blocker_reasons: list[str] = Field(default_factory=list)
    measurement_mission: MeasurementMission | None = None


class PitStrategyContext(EngineeringModel):
    session_type: str | None = None
    race_session: bool = False
    horizon_laps_remaining: int | None = None
    horizon_source: Literal["session_laps_remaining", "session_time_remaining", "unavailable"] = "unavailable"
    horizon_uncertainty_laps: int | None = None
    pits_open: bool | None = None
    pit_rule_state_coverage_pct: float = 0.0
    session_state: int | None = None
    latest_telemetry_lap: int | None = None
    latest_completed_lap: int | None = None
    latest_fuel_level_l: float | None = None
    measured_pit_loss_s: float | None = None
    measured_pit_loss_samples: int = 0
    mandatory_repair_remaining_s: float | None = None
    optional_repair_remaining_s: float | None = None
    strategy_ready: bool = False
    blocker_reasons: list[str] = Field(default_factory=list)
    source_channels: list[str] = Field(default_factory=list)


class StintStrategyReport(EngineeringModel):
    gate: EngineGate
    eligible_lap_count: int
    historical_segment_laps: list[int] = Field(default_factory=list)
    active_segment_laps: list[int] = Field(default_factory=list)
    points: list[StintLapPoint] = Field(default_factory=list)
    median_fuel_burn_per_lap: float | None = None
    estimated_laps_remaining: float | None = None
    fuel_pace_slope_s_per_unit: float | None = None
    stabilization_lap: int | None = None
    degradation_s_per_lap: float | None = None
    tire_set_resets_observed: int = 0
    repair_context_observed: bool | None = None
    tire_life_curves: dict[str, TireLifeCurve] = Field(default_factory=dict)
    pit_window: PitWindowRecommendation | None = None
    pit_strategy_context: PitStrategyContext | None = None
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


def _linear_slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 3:
        return None
    x_mean = mean(item[0] for item in points)
    y_mean = mean(item[1] for item in points)
    denominator = sum((x - x_mean) ** 2 for x, _ in points)
    if denominator <= 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator


def _row_average(rows: list[dict[str, Any]], channels: tuple[str, ...]) -> float | None:
    values = [
        value
        for row in rows
        for channel in channels
        if (value := finite(row.get(channel))) is not None
    ]
    return mean(values) if values else None


def _remaining_wear_pct(value: Any) -> float | None:
    number = finite(value)
    if number is None or number < 0.0:
        return None
    percent = number * 100.0 if number <= 1.5 else number
    return percent if percent <= 100.0 else None


def _corner_remaining_wear(lap_rows: list[dict[str, Any]], corner: str) -> float | None:
    samples: list[float] = []
    for row in lap_rows:
        profile = [
            _remaining_wear_pct(row.get(f"{corner}_wear_{position}"))
            for position in ("inner", "middle", "outer")
        ]
        if all(value is not None for value in profile):
            samples.append(min(float(value) for value in profile if value is not None))
    return median(samples) if len(samples) >= 5 else None


def _sort_lap_rows(lap_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one lap in physical sample order, independent of storage/read order."""
    if lap_rows and all(finite(row.get("session_time")) is not None for row in lap_rows):
        return sorted(lap_rows, key=lambda row: finite(row.get("session_time")) or 0.0)
    return sorted(
        lap_rows,
        key=lambda row: (
            lap_pct(row) is None,
            lap_pct(row) if lap_pct(row) is not None else float("inf"),
        ),
    )


def _ordered_rows_by_lap(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        number = lap_number(row)
        if number is not None:
            grouped.setdefault(number, []).append(row)
    return {number: _sort_lap_rows(lap_rows) for number, lap_rows in grouped.items()}


def _first_channel(row: dict[str, Any], *channels: str) -> Any:
    return next((row.get(channel) for channel in channels if row.get(channel) is not None), None)


def _interpolated_lap_elapsed(lap_rows: list[dict[str, Any]], position_pct: float) -> float | None:
    samples = sorted(
        (
            (float(position), float(time))
            for row in lap_rows
            if (position := lap_pct(row)) is not None
            and (time := finite(row.get("session_time"))) is not None
        ),
        key=lambda item: item[0],
    )
    if len(samples) < 2 or not samples[0][0] <= position_pct <= samples[-1][0]:
        return None
    for (left_position, left_time), (right_position, right_time) in zip(samples, samples[1:]):
        if left_position <= position_pct <= right_position and right_position > left_position:
            fraction = (position_pct - left_position) / (right_position - left_position)
            return left_time + (right_time - left_time) * fraction - samples[0][1]
    return None


def _measured_pit_losses(
    rows: list[dict[str, Any]],
    rows_by_lap: dict[int, list[dict[str, Any]]],
    eligible: list[LapSummary],
) -> list[float]:
    ordered = sorted(
        rows,
        key=lambda row: finite(row.get("session_time")) or -1.0,
    )
    pit_state = [
        bool(_first_channel(row, "on_pit_road", "OnPitRoad"))
        for row in ordered
    ]
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, active in enumerate(pit_state):
        if active and start is None:
            start = index
        elif not active and start is not None:
            spans.append((start, index - 1))
            start = None
    losses: list[float] = []
    for start, end in spans:
        if start == 0 or end + 1 >= len(ordered):
            continue
        span_rows = ordered[start:end + 1]
        serviced = any(
            bool(_first_channel(row, "pitstop_active", "PitstopActive"))
            or bool(_first_channel(row, "player_in_pit_stall", "PlayerCarInPitStall"))
            or (finite(_first_channel(row, "player_pit_service_status", "PlayerCarPitSvStatus")) or 0.0) > 0.0
            for row in span_rows
        )
        if not serviced:
            continue
        entry_time = finite(ordered[start].get("session_time"))
        exit_time = finite(ordered[end + 1].get("session_time"))
        entry_position = lap_pct(ordered[start])
        exit_position = lap_pct(ordered[end + 1])
        if None in (entry_time, exit_time, entry_position, exit_position):
            continue
        pit_duration = float(exit_time) - float(entry_time)
        baselines: list[float] = []
        for lap in eligible:
            lap_rows = rows_by_lap.get(lap.lap_number, [])
            entry_elapsed = _interpolated_lap_elapsed(lap_rows, float(entry_position))
            exit_elapsed = _interpolated_lap_elapsed(lap_rows, float(exit_position))
            if entry_elapsed is None or exit_elapsed is None:
                continue
            expected = (
                exit_elapsed - entry_elapsed
                if float(exit_position) >= float(entry_position)
                else float(lap.lap_time) - entry_elapsed + exit_elapsed
            )
            if expected > 0.0:
                baselines.append(expected)
        if baselines:
            loss = pit_duration - median(baselines)
            if 1.0 <= loss <= 600.0:
                losses.append(loss)
    return losses


def _derive_pit_strategy_context(
    rows: list[dict[str, Any]],
    rows_by_lap: dict[int, list[dict[str, Any]]],
    eligible: list[LapSummary],
    *,
    session_type: str | None,
    active_lap: int | None,
) -> PitStrategyContext:
    ordered = sorted(rows, key=lambda row: finite(row.get("session_time")) or -1.0)
    latest = ordered[-1] if ordered else {}
    race_session = bool(session_type and "race" in session_type.casefold())
    laps_remaining = finite(_first_channel(
        latest, "session_laps_remaining", "SessionLapsRemainEx",
        "session_laps_remaining_legacy", "SessionLapsRemain",
    ))
    if laps_remaining is not None and not 0.0 <= laps_remaining < 32_000.0:
        laps_remaining = None
    time_remaining = finite(_first_channel(latest, "session_time_remaining_s", "SessionTimeRemain"))
    time_total = finite(_first_channel(latest, "session_time_total_s", "SessionTimeTotal"))
    if time_remaining is not None and not 0.0 <= time_remaining < 604_800.0:
        time_remaining = None
    if time_total is not None and not 0.0 < time_total < 604_800.0:
        time_total = None
    horizon = int(math.ceil(laps_remaining)) if laps_remaining is not None else None
    horizon_source: Literal[
        "session_laps_remaining", "session_time_remaining", "unavailable"
    ] = "session_laps_remaining" if horizon is not None else "unavailable"
    horizon_uncertainty = 0 if horizon is not None else None
    eligible_times = [float(lap.lap_time) for lap in eligible if lap.lap_time and lap.lap_time > 0.0]
    if horizon is None and time_remaining is not None and time_total is not None and eligible_times:
        horizon = int(math.ceil(time_remaining / median(eligible_times))) + 1
        horizon_source = "session_time_remaining"
        horizon_uncertainty = 1
    recent = ordered[-min(len(ordered), 300):]
    pit_rule_values = [
        bool(value) for row in recent
        if (value := _first_channel(row, "pits_open", "PitsOpen")) is not None
    ]
    pit_rule_coverage = len(pit_rule_values) / len(recent) * 100.0 if recent else 0.0
    pits_open = pit_rule_values[-1] if pit_rule_coverage >= 90.0 else None
    session_state_value = finite(_first_channel(latest, "session_state", "SessionState"))
    session_state = int(session_state_value) if session_state_value is not None else None
    latest_lap = lap_number(latest)
    completed_value = finite(_first_channel(latest, "lap_completed", "LapCompleted"))
    latest_completed_lap = int(completed_value) if completed_value is not None else None
    latest_fuel = finite(_first_channel(latest, "fuel_level", "FuelLevel"))
    pit_losses = _measured_pit_losses(rows, rows_by_lap, eligible)
    mandatory_repair = finite(_first_channel(
        latest, "pit_repair_remaining_s", "PitRepairLeft",
    ))
    optional_repair = finite(_first_channel(
        latest, "pit_optional_repair_remaining_s", "PitOptRepairLeft",
    ))
    blockers: list[str] = []
    if not race_session:
        blockers.append("The imported session is not identified by the server as a Race session.")
    if horizon is None:
        blockers.append(
            "A finite SessionLapsRemainEx value or finite SessionTimeRemain/SessionTimeTotal race horizon is unavailable."
        )
    if pits_open is not True:
        blockers.append("PitsOpen is closed, missing, or below 90% recent coverage.")
    if session_state != 4:
        blockers.append("SessionState does not show an active racing state at the latest sample.")
    if active_lap is None or latest_completed_lap != active_lap:
        blockers.append(
            "LapCompleted at the latest sample does not match the active complete eligible lap used for burn history."
        )
    if latest_fuel is None or latest_fuel < 0.0:
        blockers.append("FuelLevel is unavailable or implausible at the latest telemetry sample.")
    if bool(_first_channel(latest, "on_pit_road", "OnPitRoad")):
        blockers.append("The latest sample is already on pit road, so a pre-pit strategy window is not applicable.")
    if not pit_losses:
        blockers.append(
            "No complete serviced pit-road traversal has a clean-lap matched-position baseline for measured pit loss."
        )
    sources = [
        "session_time", "lap_dist_pct", "lap_completed", "fuel_level",
        "on_pit_road", "pitstop_active",
        "player_in_pit_stall", "pits_open", "session_state",
    ]
    sources.append(
        "session_laps_remaining" if horizon_source == "session_laps_remaining"
        else "session_time_remaining_s"
    )
    return PitStrategyContext(
        session_type=session_type,
        race_session=race_session,
        horizon_laps_remaining=horizon,
        horizon_source=horizon_source,
        horizon_uncertainty_laps=horizon_uncertainty,
        pits_open=pits_open,
        pit_rule_state_coverage_pct=round(pit_rule_coverage, 3),
        session_state=session_state,
        latest_telemetry_lap=latest_lap,
        latest_completed_lap=latest_completed_lap,
        latest_fuel_level_l=latest_fuel,
        measured_pit_loss_s=median(pit_losses) if pit_losses else None,
        measured_pit_loss_samples=len(pit_losses),
        mandatory_repair_remaining_s=mandatory_repair,
        optional_repair_remaining_s=optional_repair,
        strategy_ready=not blockers,
        blocker_reasons=blockers,
        source_channels=sources,
    )


def _complete_fuel_trace(lap_rows: list[dict[str, Any]]) -> list[float]:
    samples = [
        (position, fuel)
        for row in lap_rows
        if (position := lap_pct(row)) is not None
        and (fuel := finite(row.get("fuel_level"))) is not None
    ]
    if len(samples) < 2 or samples[0][0] > 5.0 or samples[-1][0] < 95.0:
        return []
    return [float(fuel) for _, fuel in samples]


def _continuous_segments(
    rows_by_lap: dict[int, list[dict[str, Any]]],
    eligible: list[LapSummary],
) -> list[list[LapSummary]]:
    segments: list[list[LapSummary]] = []
    current: list[LapSummary] = []
    previous_fuel_end: float | None = None
    previous_corner_distances: tuple[float | None, ...] | None = None
    previous_compound: str | None = None
    previous_set_state: tuple[int | None, ...] | None = None
    for lap in eligible:
        lap_rows = rows_by_lap.get(lap.lap_number, [])
        fuel = _complete_fuel_trace(lap_rows)
        corner_distances = tuple(
            _row_average(lap_rows, (f"{corner}_tire_distance_m",))
            for corner in ("lf", "rf", "lr", "rr")
        )
        compound = next(
            (str(value) for row in lap_rows if (value := row.get("player_tire_compound")) not in (None, "")),
            None,
        )
        set_state = tuple(
            int(value) if value is not None and value >= 0.0 else None
            for channel in (
                "tire_sets_used", "left_tire_sets_used", "right_tire_sets_used",
                "front_tire_sets_used", "rear_tire_sets_used",
            )
            for value in [next(
                (finite(row.get(channel)) for row in lap_rows if finite(row.get(channel)) is not None),
                None,
            )]
        )
        repair = any(
            (finite(row.get("repair_required")) or 0.0) > 0
            or (finite(row.get("repair_time_s")) or 0.0) > 0
            for row in lap_rows
        )
        if repair:
            if current:
                segments.append(current)
                current = []
            previous_fuel_end = None
            previous_corner_distances = None
            previous_compound = None
            previous_set_state = None
            continue
        split = bool(
            current
            and (
                lap.lap_number != current[-1].lap_number + 1
                or (fuel and previous_fuel_end is not None and fuel[0] > previous_fuel_end + 0.1)
                or (
                    any(
                        current_distance is not None and previous_distance is not None
                        and current_distance + 100.0 < previous_distance
                        for current_distance, previous_distance in zip(
                            corner_distances, previous_corner_distances or (),
                        )
                    )
                )
                or (
                    compound is not None and previous_compound is not None
                    and compound != previous_compound
                )
                or any(
                    current_value is not None and previous_value is not None
                    and current_value != previous_value
                    for current_value, previous_value in zip(
                        set_state, previous_set_state or (),
                    )
                )
            )
        )
        if split:
            segments.append(current)
            current = []
        current.append(lap)
        previous_fuel_end = fuel[-1] if fuel else None
        previous_corner_distances = corner_distances
        previous_compound = compound
        previous_set_state = set_state
    if current:
        segments.append(current)
    return segments


def _build_tire_life_curves(
    rows_by_lap: dict[int, list[dict[str, Any]]],
    eligible: list[LapSummary],
    all_segments: list[list[LapSummary]],
) -> dict[str, TireLifeCurve]:
    curves: dict[str, TireLifeCurve] = {}
    selected_compound = next(
        (
            str(value)
            for lap in eligible
            for row in rows_by_lap.get(lap.lap_number, [])
            if (value := row.get("player_tire_compound")) not in (None, "")
        ),
        None,
    )
    for corner in ("lf", "rf", "lr", "rr"):
        points: list[TireLifePoint] = []
        for lap in eligible:
            lap_rows = rows_by_lap.get(lap.lap_number, [])
            remaining = _corner_remaining_wear(lap_rows, corner)
            if remaining is None:
                continue
            distance = _row_average(lap_rows, (f"{corner}_tire_distance_m",))
            points.append(TireLifePoint(
                lap_number=lap.lap_number,
                tire_distance_m=distance,
                minimum_remaining_wear_pct=remaining,
            ))
        lap_slope = _linear_slope([
            (float(point.lap_number), point.minimum_remaining_wear_pct)
            for point in points
        ])
        distance_slope = _linear_slope([
            (float(point.tire_distance_m) / 1000.0, point.minimum_remaining_wear_pct)
            for point in points if point.tire_distance_m is not None
        ])
        transitions = list(zip(points, points[1:]))
        monotonic = (
            sum(
                right.minimum_remaining_wear_pct <= left.minimum_remaining_wear_pct + 0.10
                for left, right in transitions
            ) / len(transitions)
            if transitions else None
        )
        loss_per_lap = -lap_slope if lap_slope is not None and lap_slope < 0.0 else None
        loss_per_distance = (
            -distance_slope if distance_slope is not None and distance_slope < 0.0 else None
        )
        segment_distance_losses = [
            (left.minimum_remaining_wear_pct - right.minimum_remaining_wear_pct)
            / ((float(right.tire_distance_m) - float(left.tire_distance_m)) / 1000.0)
            for left, right in transitions
            if left.tire_distance_m is not None and right.tire_distance_m is not None
            and float(right.tire_distance_m) - float(left.tire_distance_m) > 1.0
        ]
        distance_loss_range = (
            (percentile(segment_distance_losses, 0.10), percentile(segment_distance_losses, 0.90))
            if segment_distance_losses else None
        )
        trend_established = bool(
            len(points) >= 10
            and loss_per_distance is not None and loss_per_distance > 0.0
            and monotonic is not None and monotonic >= 0.80
        )
        replicated_signatures: set[tuple[str, tuple[int | None, ...]]] = set()
        for segment in all_segments:
            segment_rows = [
                row
                for lap in segment
                for row in rows_by_lap.get(lap.lap_number, [])
            ]
            compound = next(
                (
                    str(value) for row in segment_rows
                    if (value := row.get("player_tire_compound")) not in (None, "")
                ),
                None,
            )
            if compound is None or selected_compound is None or compound != selected_compound:
                continue
            set_state = tuple(
                int(value) if value is not None and value >= 0.0 else None
                for channel in (
                    "tire_sets_used", "left_tire_sets_used", "right_tire_sets_used",
                    "front_tire_sets_used", "rear_tire_sets_used",
                )
                for value in [next(
                    (
                        finite(row.get(channel)) for row in segment_rows
                        if finite(row.get(channel)) is not None
                    ),
                    None,
                )]
            )
            if all(value is None for value in set_state):
                continue
            segment_points = [
                TireLifePoint(
                    lap_number=lap.lap_number,
                    tire_distance_m=_row_average(
                        rows_by_lap.get(lap.lap_number, []),
                        (f"{corner}_tire_distance_m",),
                    ),
                    minimum_remaining_wear_pct=remaining,
                )
                for lap in segment
                if (remaining := _corner_remaining_wear(
                    rows_by_lap.get(lap.lap_number, []), corner,
                )) is not None
            ]
            segment_slope = _linear_slope([
                (float(point.tire_distance_m) / 1000.0, point.minimum_remaining_wear_pct)
                for point in segment_points if point.tire_distance_m is not None
            ])
            segment_transitions = list(zip(segment_points, segment_points[1:]))
            segment_monotonic = (
                sum(
                    right.minimum_remaining_wear_pct <= left.minimum_remaining_wear_pct + 0.10
                    for left, right in segment_transitions
                ) / len(segment_transitions)
                if segment_transitions else 0.0
            )
            if (
                len(segment_points) >= 10
                and segment_slope is not None and segment_slope < 0.0
                and segment_monotonic >= 0.80
            ):
                replicated_signatures.add((compound, set_state))
        blockers: list[str] = []
        if len(points) < 10:
            blockers.append("At least 10 continuous eligible laps with complete three-zone wear are required.")
        if len(points) >= 10 and not trend_established:
            blockers.append("Remaining-wear decline is not monotonic and repeatable enough to establish a tire-life trend.")
        values = [point.minimum_remaining_wear_pct for point in points]
        curves[corner.upper()] = TireLifeCurve(
            corner=corner.upper(),  # type: ignore[arg-type]
            points=points,
            observed_remaining_range_pct=(min(values), max(values)) if values else None,
            wear_loss_percentage_points_per_lap=loss_per_lap,
            wear_loss_percentage_points_per_1000m=loss_per_distance,
            wear_loss_percentage_points_per_1000m_range=(
                (float(distance_loss_range[0]), float(distance_loss_range[1]))
                if distance_loss_range is not None
                and None not in distance_loss_range else None
            ),
            monotonic_transition_fraction=monotonic,
            replicated_tire_sets=len(replicated_signatures),
            trend_established=trend_established,
            blocker_reasons=blockers,
        )
    return curves


def _pit_window_from_fuel(
    *,
    burns: list[float],
    last_fuel: float | None,
    current_lap: int | None,
    active_last_rows: list[dict[str, Any]],
    confidence_cap: float,
    strategy_context: PitStrategyContext,
) -> PitWindowRecommendation:
    p10 = percentile(burns, 0.10)
    p90 = percentile(burns, 0.90)
    burn_median = median(burns) if burns else None
    blockers: list[str] = []
    if len(burns) < 3:
        blockers.append("At least three complete eligible within-lap fuel burns are required.")
    if last_fuel is None or last_fuel < 0.0:
        blockers.append("The active eligible lap does not have a valid ending FuelLevel sample.")
    variability = (
        (p90 - p10) / burn_median
        if p10 is not None and p90 is not None and burn_median is not None and burn_median > 0.0
        else None
    )
    if variability is None or variability > 0.15:
        blockers.append("Fuel-burn variability exceeds 15%, so a narrow service window is not trustworthy.")
    tire_set_values = [
        int(value) for row in active_last_rows
        for channel in (
            "tire_sets_available", "left_tire_sets_available", "right_tire_sets_available",
            "front_tire_sets_available", "rear_tire_sets_available",
        )
        if (value := finite(row.get(channel))) is not None and value >= 0.0
    ]
    tire_sets = min(tire_set_values) if tire_set_values else None
    strategy_blockers = list(strategy_context.blocker_reasons)
    mission_blockers = [*blockers, *strategy_blockers]
    mission = MeasurementMission(
        purpose="Collect the server-derived race context required for a production pit-window recommendation.",
        procedure=(
            "Re-import the original .ibt with the current universal archive if any declared strategy channel is missing from an older cache.",
            "Import a Race-session recording that includes the active stint and current SessionLapsRemainEx or timed-session horizon.",
            "Record at least three complete green eligible laps with continuous FuelLevel and PitsOpen telemetry.",
            "Complete one representative legal pit entry, serviced stall visit, and pit exit in the same car/track context.",
            "For tire strategy, repeat a comparable stint on a second recorded tire set with compound and set counters present.",
        ),
        required_laps_or_passes=4,
        controlled_variables=(
            "race session and track configuration",
            "fuel burn mode",
            "pit entry and service procedure",
            "tire compound and set identity",
            "caution/flag state",
        ),
        target_phase="race stint and pit cycle",
        acceptance_thresholds=(
            "At least three complete eligible active-stint fuel burns with no more than 15% variability",
            "At least 90% recent PitsOpen coverage and active SessionState",
            "Finite server-derived race horizon without unlimited-session sentinels",
            "One complete serviced pit traversal with clean-lap matched-position pit-loss baseline",
        ),
        stop_rule="Stop and repeat after a caution, incident, tow, reset, data-integrity fault, or non-representative pit service.",
        blockers=tuple(mission_blockers or ["Production strategy context is incomplete."]),
    )
    if blockers or p90 is None or burn_median is None or last_fuel is None or current_lap is None:
        return PitWindowRecommendation(
            status="blocked",
            current_completed_lap=current_lap,
            available_tire_sets=tire_sets,
            confidence_score=0.0,
            caveats=[
                "No universal tire-wear safety threshold is inferred from telemetry."
            ],
            blocker_reasons=blockers or ["A complete active stint context is unavailable."],
            measurement_mission=mission,
        )
    conservative_laps = max(0, math.floor(last_fuel / p90 - 1.0))
    median_laps = max(conservative_laps, math.floor(last_fuel / burn_median - 1.0))
    if not strategy_context.strategy_ready:
        return PitWindowRecommendation(
            status="available",
            current_completed_lap=current_lap,
            earliest_laps_from_now=conservative_laps,
            latest_laps_from_now=median_laps,
            earliest_pit_lap=current_lap + conservative_laps + 1,
            latest_pit_lap=current_lap + median_laps + 1,
            limiting_factor="fuel",
            available_tire_sets=tire_sets,
            confidence_score=min(0.65, confidence_cap),
            basis=[
                f"Active ending fuel {last_fuel:.3f} L.",
                f"Observed median/P90 burn {burn_median:.3f}/{p90:.3f} L per lap across {len(burns)} active eligible laps.",
                "The conservative edge reserves one observed lap at the high-burn bound.",
            ],
            caveats=[
                "This is a fuel-exhaustion/service bound, not a production race-strategy recommendation.",
                "It is not a guaranteed race-strategy optimum.",
                "A server-derived race horizon, pit-rule state, and measured pit-lane time loss are required to promote this bound to strategy.",
                *strategy_blockers,
                "No universal unsafe-wear threshold is inferred.",
            ],
            blocker_reasons=strategy_blockers,
            measurement_mission=mission,
        )
    horizon = strategy_context.horizon_laps_remaining
    assert horizon is not None
    mandatory_repair = strategy_context.mandatory_repair_remaining_s or 0.0
    if mandatory_repair > 0.0:
        earliest = latest = 0
        action = "Pit at the next legal opportunity because mandatory repair service is active."
    elif horizon <= conservative_laps:
        earliest = latest = None
        action = (
            f"No fuel stop is required over the server-derived {horizon}-lap remaining horizon "
            "under the observed high-burn bound."
        )
    else:
        latest = conservative_laps
        earliest = max(0, latest - 1)
        action = (
            "Pit at the next legal opportunity for fuel."
            if latest == 0
            else f"Schedule the next fuel stop {earliest}-{latest} laps from now; do not exceed the late edge."
        )
    return PitWindowRecommendation(
        status="available",
        current_completed_lap=current_lap,
        earliest_laps_from_now=earliest,
        latest_laps_from_now=latest,
        earliest_pit_lap=current_lap + earliest + 1 if earliest is not None else None,
        latest_pit_lap=current_lap + latest + 1 if latest is not None else None,
        limiting_factor="fuel",
        classification="strategy_window",
        strategy_ready=True,
        available_tire_sets=tire_sets,
        confidence_score=min(0.80, confidence_cap),
        basis=[
            f"Active ending fuel {last_fuel:.3f} L.",
            f"Observed median/P90 burn {burn_median:.3f}/{p90:.3f} L per lap across {len(burns)} eligible laps.",
            "The window reserves one observed lap of fuel and uses the higher-burn bound for its early edge.",
            f"Server-derived remaining race horizon: {horizon} lap(s) from {strategy_context.horizon_source}.",
            f"Measured matched-position pit loss: {strategy_context.measured_pit_loss_s:.3f} s across {strategy_context.measured_pit_loss_samples} stop(s).",
            f"Recent PitsOpen coverage: {strategy_context.pit_rule_state_coverage_pct:.1f}% and pits are currently open.",
        ],
        caveats=[
            "This is a guarded fuel-service recommendation, not a claim of globally optimal race strategy.",
            "Cautions, traffic, fuel saving, weather, or a pit-rule change can invalidate the window.",
            "Tire wear remains observed context; no universal unsafe-wear threshold is inferred.",
        ],
        recommendation=action,
    )


def analyze_stint_strategy(
    rows: list[dict[str, Any]],
    lap_summaries: list[LapSummary] | None,
    *,
    sim_integrity_clear: bool | None,
    sim_integrity_confidence_cap: float = 1.0,
    session_type: str | None = None,
) -> StintStrategyReport:
    all_eligible = sorted(eligible_laps(lap_summaries or []), key=lambda lap: lap.lap_number)
    rows_by_lap = _ordered_rows_by_lap(rows)
    segments = _continuous_segments(rows_by_lap, all_eligible)
    eligible = max(segments, key=len, default=[])
    active_segment = max(segments, key=lambda segment: segment[-1].lap_number, default=[])
    eligible_numbers = {lap.lap_number for lap in eligible}
    scoped = [row for number in eligible_numbers for row in rows_by_lap.get(number, [])]
    usable = frozenset(
        channel for row in scoped for channel, value in row.items()
        if value is not None and (finite(value) is not None or isinstance(value, (bool, str)))
    )
    fuel_trace = bool(eligible) and all(
        _complete_fuel_trace(rows_by_lap.get(lap.lap_number, [])) for lap in eligible
    )
    pit_strategy_context = _derive_pit_strategy_context(
        rows,
        rows_by_lap,
        eligible,
        session_type=session_type,
        active_lap=active_segment[-1].lap_number if active_segment else None,
    )
    tire_curve_channels = {
        *(f"{corner}_tire_distance_m" for corner in ("lf", "rf", "lr", "rr")),
        *(
            f"{corner}_wear_{position}"
            for corner in ("lf", "rf", "lr", "rr")
            for position in ("inner", "middle", "outer")
        ),
    }
    requested_outputs = {
        "fuel_strategy_metrics", "stint_degradation_hypothesis",
        "fuel_exhaustion_service_bound",
    }
    if pit_strategy_context.strategy_ready:
        requested_outputs.add("pit_window_recommendation")
    if tire_curve_channels.issubset(usable):
        requested_outputs.add("tire_life_curve")
    evaluation = evaluate_evidence_contract(
        STINT_STRATEGY_CONTRACT,
        EvidenceEvaluationInput(
            usable_channels=usable,
            condition_results={"eligible_history": len(eligible) >= 3, "fuel_trace_available": fuel_trace},
            blocker_results={
                "sim_integrity_uncertain": False if sim_integrity_clear is True else True if sim_integrity_clear is False else None,
            },
            repetitions=len(eligible),
            requested_outputs=frozenset(requested_outputs),
        ),
    )
    cap = min(evaluation.confidence_cap, bounded_confidence(sim_integrity_confidence_cap))
    gate = EngineGate(
        contract_key=evaluation.contract_key,
        eligible=evaluation.eligible,
        confidence_cap=cap,
        blocker_reasons=[item.message for item in evaluation.blockers],
        needed_measurements=[item.instruction for item in evaluation.needed_measurements],
    )
    if not evaluation.eligible:
        return StintStrategyReport(
            gate=gate,
            eligible_lap_count=len(eligible),
            historical_segment_laps=[lap.lap_number for lap in eligible],
            active_segment_laps=[lap.lap_number for lap in active_segment],
            pit_strategy_context=pit_strategy_context,
            conclusions=[EngineeringConclusion(
                key="stint_strategy_blocked",
                summary="Fuel and stint strategy are blocked until an eligible continuous history is available.",
                evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                confidence_score=0.0,
                blocker_reasons=gate.blocker_reasons,
            )],
        )

    points: list[StintLapPoint] = []
    burns: list[float] = []
    for lap in eligible:
        lap_rows = rows_by_lap.get(lap.lap_number, [])
        fuel = _complete_fuel_trace(lap_rows)
        burn = fuel[0] - fuel[-1] if len(fuel) >= 2 and fuel[0] >= fuel[-1] else None
        if burn is not None and burn > 0:
            burns.append(burn)
        tire_temp = _row_average(lap_rows, tuple(f"{corner}_temp_middle" for corner in ("lf", "rf", "lr", "rr")))
        tire_distance = _row_average(lap_rows, tuple(f"{corner}_tire_distance_m" for corner in ("lf", "rf", "lr", "rr")))
        points.append(StintLapPoint(
            lap_number=lap.lap_number,
            lap_time_s=float(lap.lap_time),
            fuel_start=fuel[0] if fuel else None,
            fuel_end=fuel[-1] if fuel else None,
            fuel_burn=burn,
            average_tire_temp=tire_temp,
            average_tire_distance_m=tire_distance,
        ))
    burn_median = median(burns) if burns else None
    active_last_rows = (
        rows_by_lap.get(active_segment[-1].lap_number, [])
        if active_segment else []
    )
    active_fuel = _complete_fuel_trace(active_last_rows)
    last_fuel = active_fuel[-1] if active_fuel else None
    remaining = last_fuel / burn_median if last_fuel is not None and burn_median and burn_median > 0 else None
    tire_life_curves = _build_tire_life_curves(rows_by_lap, eligible, segments)
    current_lap = active_segment[-1].lap_number if active_segment else None
    active_burns = []
    for lap in active_segment:
        fuel = _complete_fuel_trace(rows_by_lap.get(lap.lap_number, []))
        burn = fuel[0] - fuel[-1] if len(fuel) >= 2 and fuel[0] >= fuel[-1] else None
        if burn is not None and burn > 0.0:
            active_burns.append(burn)
    pit_window = _pit_window_from_fuel(
        burns=active_burns,
        last_fuel=(
            pit_strategy_context.latest_fuel_level_l
            if pit_strategy_context.strategy_ready else last_fuel
        ),
        current_lap=(
            pit_strategy_context.latest_completed_lap
            if pit_strategy_context.strategy_ready else current_lap
        ),
        active_last_rows=active_last_rows,
        confidence_cap=cap,
        strategy_context=pit_strategy_context,
    )
    fuel_pace = _linear_slope([
        ((point.fuel_start + point.fuel_end) / 2.0, point.lap_time_s)
        for point in points if point.fuel_start is not None and point.fuel_end is not None
    ])
    stabilization = None
    temperatures = [point.average_tire_temp for point in points]
    for index in range(3, len(temperatures)):
        window = temperatures[index - 3:index + 1]
        if all(value is not None for value in window) and max(float(value) for value in window) - min(float(value) for value in window) <= 1.0:
            stabilization = points[index - 2].lap_number
            break
    degradation = None
    adequate = len(points) >= 10
    if adequate:
        start_index = next((index for index, point in enumerate(points) if point.lap_number >= (stabilization or points[0].lap_number)), 0)
        degradation = _linear_slope([(float(index), point.lap_time_s) for index, point in enumerate(points[start_index:])])
    all_lap_numbers = sorted(rows_by_lap)
    all_corner_distances = [
        tuple(
            _row_average(rows_by_lap[number], (f"{corner}_tire_distance_m",))
            for corner in ("lf", "rf", "lr", "rr")
        )
        for number in all_lap_numbers
    ]
    all_compounds = [
        next(
            (
                str(value) for row in rows_by_lap[number]
                if (value := row.get("player_tire_compound")) not in (None, "")
            ),
            None,
        )
        for number in all_lap_numbers
    ]
    set_channels = (
        "tire_sets_used", "left_tire_sets_used", "right_tire_sets_used",
        "front_tire_sets_used", "rear_tire_sets_used",
    )
    all_set_states = [
        tuple(
            next(
                (
                    int(value) for row in rows_by_lap[number]
                    if (value := finite(row.get(channel))) is not None and value >= 0.0
                ),
                None,
            )
            for channel in set_channels
        )
        for number in all_lap_numbers
    ]
    resets = sum(
        (
            any(
                left_value is not None and right_value is not None
                and right_value + 100.0 < left_value
                for left_value, right_value in zip(left_distances, right_distances)
            )
            or (
                left_compound is not None and right_compound is not None
                and left_compound != right_compound
            )
            or any(
                left_value is not None and right_value is not None
                and left_value != right_value
                for left_value, right_value in zip(left_state, right_state)
            )
        )
        for left_distances, right_distances, left_compound, right_compound, left_state, right_state
        in zip(
            all_corner_distances, all_corner_distances[1:],
            all_compounds, all_compounds[1:], all_set_states, all_set_states[1:],
        )
    )
    repair_values = [
        value for row in scoped for name in ("repair_required", "repair_time_s")
        if (value := finite(row.get(name))) is not None
    ]
    repair_observed = any(value > 0 for value in repair_values) if repair_values else None
    fuel_sources = ["lap_dist_pct", "fuel_level", "lap_summary.lap_time"]
    fuel_support = [
        f"Median within-lap fuel burn {burn_median:.4f}." if burn_median is not None else "Fuel burn unavailable.",
        f"Estimated range {remaining:.2f} laps at the observed median burn." if remaining is not None else "Fuel range unavailable.",
        f"Observed {resets} tire-distance reset(s); this is tire-set accounting context.",
    ]
    degradation_blockers = [] if adequate else ["At least 10 canonical eligible laps are required for a degradation conclusion."]
    degradation_conclusion = (
        EngineeringConclusion(
            key="stint_degradation_hypothesis",
            summary=f"Observed eligible-stint pace slope is {degradation:.4f} s/lap." if degradation is not None else "Adequate history exists, but no stable degradation slope was established.",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            confidence_score=min(0.75, cap),
            source_channels=fuel_sources,
            supporting_evidence=[
                f"{len(points)} eligible laps; stabilization lap {stabilization or 'not established'}.",
                "The slope is fuel/tire/driver-correlated stint behavior, not tire degradation in isolation.",
            ],
            contradicting_evidence=[
                "Fuel mass, traffic, driver variation, tire state, and repairs can counteract or mimic long-run falloff.",
                "A short-run gain must be confirmed against later tire and thermal behavior.",
            ],
        )
        if adequate else EngineeringConclusion(
            key="stint_degradation_hypothesis",
            summary="Stint degradation is unavailable from this short run.",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            confidence_score=0.0,
            blocker_reasons=degradation_blockers,
        )
    )
    state_channels = {
        "player_tire_compound", "tire_sets_used", "left_tire_sets_used",
        "right_tire_sets_used", "front_tire_sets_used", "rear_tire_sets_used",
    }
    tire_state_context_complete = bool(state_channels & {key for row in scoped for key in row})
    repair_context_complete = bool({"repair_required", "repair_time_s"} & {key for row in scoped for key in row})
    tire_context_cap = 1.0 if tire_state_context_complete and repair_context_complete else 0.55
    established_curves = [curve for curve in tire_life_curves.values() if curve.trend_established]
    replicated_curve_context = bool(
        established_curves and all(curve.replicated_tire_sets >= 2 for curve in established_curves)
    )
    if not replicated_curve_context:
        tire_context_cap = min(tire_context_cap, 0.55)
    tire_life_conclusion = (
        EngineeringConclusion(
            key="tire_life_curve",
            summary=(
                f"Observed remaining-wear curves are established for {', '.join(curve.corner for curve in established_curves)}."
            ),
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            confidence_score=min(0.75, cap, tire_context_cap),
            source_channels=sorted(
                channel for channel in usable
                if "wear_" in channel or channel.endswith("_tire_distance_m")
            ),
            supporting_evidence=[
                (
                    f"{curve.corner}: {curve.wear_loss_percentage_points_per_1000m:.4f} percentage points per 1000 m "
                    f"across {len(curve.points)} eligible laps; the final observation is right-censored."
                )
                for curve in established_curves
                if curve.wear_loss_percentage_points_per_1000m is not None
            ],
            contradicting_evidence=[
                "The curve reports only the observed range and does not extrapolate to a universal failure threshold.",
                "Wear, pace, thermal state, traffic, and driver behavior remain correlated rather than isolated causes.",
                *(
                    [] if replicated_curve_context
                    else ["Fewer than two comparable recorded tire sets establish between-set repeatability."]
                ),
                *(
                    ["Repair and/or tire-compound/set-state context is incomplete; confidence is capped."]
                    if tire_context_cap < 1.0 else []
                ),
            ],
        )
        if established_curves else EngineeringConclusion(
            key="tire_life_curve",
            summary="A repeatable tire-life curve is not established from this stint.",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            confidence_score=0.0,
            blocker_reasons=sorted({
                reason for curve in tire_life_curves.values() for reason in curve.blocker_reasons
            }) or ["Complete three-zone wear history is unavailable."],
        )
    )
    bound_conclusion = (
        EngineeringConclusion(
            key="fuel_exhaustion_service_bound",
            summary=(
                "The observed high-burn fuel bound covers the remaining race horizon."
                if pit_window.strategy_ready and pit_window.latest_laps_from_now is None
                else f"Fuel-exhaustion service bound: {pit_window.earliest_laps_from_now}-{pit_window.latest_laps_from_now} laps from now."
            ),
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=pit_window.confidence_score,
            source_channels=["lap_dist_pct", "fuel_level"],
            supporting_evidence=pit_window.basis,
            contradicting_evidence=pit_window.caveats,
        )
        if pit_window.status == "available" else EngineeringConclusion(
            key="fuel_exhaustion_service_bound",
            summary="A fuel-exhaustion/service bound is not justified by the current stint.",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            confidence_score=0.0,
            blocker_reasons=pit_window.blocker_reasons,
        )
    )
    pit_conclusion = (
        EngineeringConclusion(
            key="pit_window_recommendation",
            summary=(
                "The server-derived race horizon does not require a fuel stop."
                if pit_window.latest_laps_from_now is None
                else "A server-derived production fuel-service recommendation is available."
            ),
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=pit_window.confidence_score,
            source_channels=sorted(set([
                "fuel_level", "lap_dist_pct", *pit_strategy_context.source_channels,
            ])),
            supporting_evidence=pit_window.basis,
            contradicting_evidence=pit_window.caveats,
            recommendation=pit_window.recommendation,
        )
        if pit_window.strategy_ready else EngineeringConclusion(
            key="pit_window_recommendation",
            summary="Production pit-window strategy is blocked; only the fuel service bound is available.",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            confidence_score=0.0,
            blocker_reasons=(
                pit_window.blocker_reasons
                or pit_strategy_context.blocker_reasons
                or ["Server-derived race-strategy context is incomplete."]
            ),
        )
    )
    return StintStrategyReport(
        gate=gate,
        eligible_lap_count=len(eligible),
        historical_segment_laps=[lap.lap_number for lap in eligible],
        active_segment_laps=[lap.lap_number for lap in active_segment],
        points=points,
        median_fuel_burn_per_lap=burn_median,
        estimated_laps_remaining=remaining,
        fuel_pace_slope_s_per_unit=fuel_pace,
        stabilization_lap=stabilization,
        degradation_s_per_lap=degradation,
        tire_set_resets_observed=resets,
        repair_context_observed=repair_observed,
        tire_life_curves=tire_life_curves,
        pit_window=pit_window,
        pit_strategy_context=pit_strategy_context,
        conclusions=[
            EngineeringConclusion(
                key="fuel_strategy_metrics",
                summary="Fuel range and fuel-normalized pace context are calculated from eligible laps.",
                evidence_state=EvidenceState.CALCULATED,
                confidence_score=min(0.85, cap),
                source_channels=fuel_sources,
                supporting_evidence=fuel_support,
                contradicting_evidence=[
                    "Range is conditional on the observed burn rate and is not a guaranteed pit window.",
                    "Cautions, traffic, fuel saving, and repair status can change consumption and pace.",
                ],
            ),
            tire_life_conclusion,
            bound_conclusion,
            pit_conclusion,
            degradation_conclusion,
        ],
    )


__all__ = [
    "PitWindowRecommendation", "StintLapPoint", "StintStrategyReport",
    "TireLifeCurve", "TireLifePoint", "analyze_stint_strategy",
]
