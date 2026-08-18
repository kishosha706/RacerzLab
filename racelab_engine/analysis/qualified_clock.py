"""One qualified telemetry-clock contract for timing-sensitive analysis.

``SessionTick`` is the base-record clock.  When every base record has an
integer tick, in-epoch ticks are contiguous, and the decoder supplies a valid
declared telemetry rate, canonical time is derived from ticks.  The simulator's
``SessionTime`` remains intact as corroborating evidence; duplicate or reversed
timestamps are counted and their residuals are retained, never silently fixed.

Count-as-time array channels are deliberately outside this projection.  Their
ordered sub-samples keep their declared effective rate and are never flattened
into extra base records by this clock.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Literal, Sequence

import polars as pl
from pydantic import Field, PrivateAttr, model_validator

from racelab_engine.models.engineering import EngineeringModel

ClockPrimary = Literal["session_tick", "session_time", "unavailable"]
ClockState = Literal["qualified", "degraded", "blocked", "unavailable"]

_CLOCK_DISAGREEMENT_LIMIT_S = 0.010
_SIM_LAP_TIME_MIN_TOLERANCE_S = 0.100
_SIM_LAP_TIME_SAMPLE_TOLERANCE = 3.0
_SUBTICK_SEMANTICS = (
    "Base-record clock only. Count-as-time array elements retain source order "
    "and their separately declared effective sample rate."
)


class QualifiedTelemetryClock(EngineeringModel):
    """Serializable clock qualification plus private per-sample projections."""

    primary_clock: ClockPrimary
    clock_state: ClockState
    tick_rate_hz: float | None = None
    sample_count: int = Field(ge=0)
    epoch_count: int = Field(ge=0)
    reset_epoch_count: int = Field(ge=0)
    canonical_clock_coverage_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    session_tick_coverage_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    session_time_coverage_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    canonical_start_time_s: float | None = None
    canonical_end_time_s: float | None = None
    canonical_duration_s: float | None = None
    observed_session_time_start_s: float | None = None
    observed_session_time_end_s: float | None = None
    observed_sample_rate_hz: float | None = None
    invalid_tick_sample_count: int = Field(default=0, ge=0)
    invalid_session_time_sample_count: int = Field(default=0, ge=0)
    duplicate_tick_transition_count: int = Field(default=0, ge=0)
    reversed_tick_transition_count: int = Field(default=0, ge=0)
    dropped_tick_count: int = Field(default=0, ge=0)
    tick_discontinuity_count: int = Field(default=0, ge=0)
    session_time_duplicate_count: int = Field(default=0, ge=0)
    session_time_reverse_count: int = Field(default=0, ge=0)
    timestamp_gap_count: int = Field(default=0, ge=0)
    largest_timestamp_step_s: float | None = None
    session_time_residual_p95_s: float | None = None
    qualified_session_time_residual_p95_s: float | None = None
    session_time_residual_max_abs_s: float | None = None
    session_time_phase_adjustment_count: int = Field(default=0, ge=0)
    material_clock_disagreement_count: int = Field(default=0, ge=0)
    simulator_lap_time_s: float | None = None
    simulator_lap_time_source: str | None = None
    simulator_lap_time_residual_s: float | None = None
    simulator_lap_time_tolerance_s: float | None = None
    lap_time_channel_corroboration: str = "unavailable"
    lap_delta_validity_corroboration: bool | None = None
    source_channels: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    sub_tick_semantics: str = _SUBTICK_SEMANTICS

    _canonical_time_by_sample_s: tuple[float | None, ...] = PrivateAttr(default=())
    _canonical_elapsed_by_sample_s: tuple[float | None, ...] = PrivateAttr(default=())
    _observed_session_time_by_sample_s: tuple[float | None, ...] = PrivateAttr(default=())
    _session_time_residual_by_sample_s: tuple[float | None, ...] = PrivateAttr(default=())
    _epoch_index_by_sample: tuple[int, ...] = PrivateAttr(default=())

    @model_validator(mode="after")
    def require_structural_clock_truth(self) -> QualifiedTelemetryClock:
        if self.primary_clock == "session_tick" and self.tick_rate_hz is None:
            raise ValueError("tick-primary clocks require a declared tick rate")
        if self.clock_state == "qualified" and self.primary_clock != "session_tick":
            raise ValueError("only a qualified tick clock can be authoritative")
        if self.clock_state == "blocked" and not self.blockers:
            raise ValueError("blocked clocks require structural blockers")
        if self.clock_state == "unavailable" and self.primary_clock != "unavailable":
            raise ValueError("unavailable clock state requires unavailable primary clock")
        return self

    @property
    def canonical_time_by_sample_s(self) -> tuple[float | None, ...]:
        return self._canonical_time_by_sample_s

    @property
    def canonical_elapsed_time_s(self) -> tuple[float | None, ...]:
        return self._canonical_elapsed_by_sample_s

    @property
    def session_time_observed_s(self) -> tuple[float | None, ...]:
        return self._observed_session_time_by_sample_s

    @property
    def session_time_residual_s(self) -> tuple[float | None, ...]:
        return self._session_time_residual_by_sample_s

    @property
    def epoch_index_by_sample(self) -> tuple[int, ...]:
        return self._epoch_index_by_sample


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _truth(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on"}:
            return True
        if normalized in {"false", "no", "off"}:
            return False
    number = _finite(value)
    return bool(number) if number is not None else None


def _table_length(table: Any) -> int:
    if isinstance(table, pl.DataFrame):
        return table.height
    if isinstance(table, Sequence) and not isinstance(table, (str, bytes, bytearray)):
        return len(table)
    return 0


def _series(table: Any, names: Sequence[str], count: int) -> tuple[str | None, list[Any]]:
    candidates: list[tuple[int, int, str, list[Any]]] = []
    for order, name in enumerate(names):
        if isinstance(table, pl.DataFrame):
            if name not in table.columns:
                continue
            items = table.get_column(name).to_list()
        elif isinstance(table, Sequence) and not isinstance(table, (str, bytes, bytearray)):
            if not any(isinstance(row, dict) and name in row for row in table):
                continue
            items = [row.get(name) if isinstance(row, dict) else None for row in table]
        else:
            continue
        if len(items) < count:
            items.extend([None] * (count - len(items)))
        elif len(items) > count:
            items = items[:count]
        coverage = sum(value is not None for value in items)
        candidates.append((coverage, -order, name, items))
    if not candidates:
        return None, [None] * count
    _coverage, _order, selected_name, selected = max(candidates, key=lambda item: (item[0], item[1]))
    return selected_name, selected


def _percentile(items: list[float], fraction: float) -> float | None:
    if not items:
        return None
    ordered = sorted(items)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _lap_corroboration(
    table: Any,
    *,
    count: int,
    canonical_duration_s: float | None,
    tick_rate_hz: float | None,
) -> tuple[dict[str, Any], list[str]]:
    """Read simulator lap timing only when the input contains one full lap."""

    lap_name, lap_raw = _series(table, ("lap", "lap_number", "Lap"), count)
    lap_numbers = {
        int(value)
        for raw in lap_raw
        if (value := _finite(raw)) is not None and math.isclose(value, round(value), abs_tol=1e-9)
    }
    pct_name, pct_raw = _series(table, ("lap_dist_pct", "LapDistPct"), count)
    pcts = []
    for raw in pct_raw:
        value = _finite(raw)
        if value is not None:
            pcts.append(value * 100.0 if 0.0 <= value <= 1.5 else value)
    is_one_full_lap = (
        len(lap_numbers) == 1
        and pcts
        and min(pcts) <= 0.5
        and max(pcts) >= 99.5
    )

    timing_name, timing_raw = _series(
        table,
        ("lap_current_time_s", "LapCurrentLapTime"),
        count,
    )
    # LapCurrentLapTime can retain the previous lap briefly after ``Lap``
    # increments.  Only the value co-observed at the completed end of this
    # physical lap is eligible to corroborate its duration.
    finish_timing_values = [
        value
        for index, raw in enumerate(timing_raw)
        if index < len(pct_raw)
        and (value := _finite(raw)) is not None
        and value >= 0.0
        and (pct := _finite(pct_raw[index])) is not None
        and (pct * 100.0 if 0.0 <= pct <= 1.5 else pct) >= 99.5
    ]
    start_timing_values = [
        value
        for index, raw in enumerate(timing_raw)
        if index < len(pct_raw)
        and (value := _finite(raw)) is not None
        and value >= 0.0
        and (pct := _finite(pct_raw[index])) is not None
        and (pct * 100.0 if 0.0 <= pct <= 1.5 else pct) <= 0.5
    ]
    ordered_timing_values = [
        value for raw in timing_raw
        if (value := _finite(raw)) is not None and value >= 0.0
    ]
    timer_reset_observed = any(
        current < previous
        for previous, current in zip(ordered_timing_values, ordered_timing_values[1:])
    )
    simulator_lap_time = (
        finish_timing_values[-1]
        if finish_timing_values and timer_reset_observed and is_one_full_lap
        else finish_timing_values[-1] - min(start_timing_values)
        if finish_timing_values
        and start_timing_values
        and finish_timing_values[-1] >= min(start_timing_values)
        and is_one_full_lap
        else None
    )

    validity_sources: list[str] = []
    validity_values: list[bool] = []
    for canonical, raw in (
        ("lap_delta_to_session_best_valid", "LapDeltaToSessionBestLap_OK"),
        ("lap_delta_to_session_optimal_valid", "LapDeltaToSessionOptimalLap_OK"),
        ("lap_delta_to_best_valid", "LapDeltaToBestLap_OK"),
        ("lap_delta_to_optimal_valid", "LapDeltaToOptimalLap_OK"),
    ):
        name, raw_values = _series(table, (canonical, raw), count)
        observed = [value for item in raw_values if (value := _truth(item)) is not None]
        if name is not None and observed:
            validity_sources.append(name)
            validity_values.extend(observed)
    validity = any(validity_values) if validity_values else None

    tolerance = (
        max(_SIM_LAP_TIME_MIN_TOLERANCE_S, _SIM_LAP_TIME_SAMPLE_TOLERANCE / tick_rate_hz)
        if tick_rate_hz and tick_rate_hz > 0
        else _SIM_LAP_TIME_MIN_TOLERANCE_S
    )
    residual = (
        simulator_lap_time - canonical_duration_s
        if simulator_lap_time is not None and canonical_duration_s is not None
        else None
    )
    blockers: list[str] = []
    if residual is None:
        status = "unavailable"
    elif abs(residual) <= tolerance:
        status = "agrees"
    else:
        status = "disagrees"
        blockers.append("simulator_lap_time_disagreement")
    if status == "unavailable" and validity is False:
        status = "delta_validity_not_corroborated"

    sources = [name for name in (lap_name, pct_name, timing_name, *validity_sources) if name]
    return {
        "simulator_lap_time_s": simulator_lap_time,
        "simulator_lap_time_source": timing_name if simulator_lap_time is not None else None,
        "simulator_lap_time_residual_s": residual,
        "simulator_lap_time_tolerance_s": tolerance if residual is not None else None,
        "lap_time_channel_corroboration": status,
        "lap_delta_validity_corroboration": validity,
        "source_channels": sources,
    }, blockers


def build_qualified_telemetry_clock(
    table: Any,
    *,
    expected_sample_rate_hz: float | None,
) -> QualifiedTelemetryClock:
    """Qualify and project one canonical base-record telemetry clock."""

    count = _table_length(table)
    tick_name, raw_ticks = _series(table, ("session_tick", "SessionTick"), count)
    time_name, raw_times = _series(table, ("session_time", "SessionTime"), count)
    ticks = [_finite(value) for value in raw_ticks]
    observed_times = [_finite(value) for value in raw_times]
    rate = _finite(expected_sample_rate_hz)
    rate = rate if rate is not None and rate > 0.0 else None

    valid_tick_count = sum(value is not None for value in ticks)
    valid_time_count = sum(value is not None for value in observed_times)
    integer_tick_count = sum(
        value is not None and math.isclose(value, round(value), abs_tol=1e-9)
        for value in ticks
    )
    invalid_tick_samples = count - integer_tick_count if tick_name is not None else 0
    invalid_time_samples = count - valid_time_count if time_name is not None else 0

    reset_boundaries: set[int] = set()
    duplicate_ticks = 0
    reversed_ticks = 0
    dropped_ticks = 0
    tick_gap_transitions = 0
    duplicate_times = 0
    reversed_times = 0
    positive_time_deltas: list[float] = []
    time_deltas: list[float] = []

    for index in range(1, count):
        previous_tick = ticks[index - 1]
        current_tick = ticks[index]
        previous_time = observed_times[index - 1]
        current_time = observed_times[index]
        time_delta = (
            current_time - previous_time
            if previous_time is not None and current_time is not None
            else None
        )
        tick_delta = (
            current_tick - previous_tick
            if previous_tick is not None and current_tick is not None
            else None
        )
        is_reset = bool(
            tick_delta is not None
            and tick_delta < 0.0
            and (
                (time_delta is not None and time_delta < 0.0)
                or (current_tick is not None and current_tick <= 1.0 < previous_tick)
            )
        )
        if is_reset:
            reset_boundaries.add(index)
        elif tick_delta is not None:
            if math.isclose(tick_delta, 0.0, abs_tol=1e-9):
                duplicate_ticks += 1
            elif tick_delta < 0.0:
                reversed_ticks += 1
            elif not math.isclose(tick_delta, 1.0, abs_tol=1e-9):
                tick_gap_transitions += 1
                dropped_ticks += max(0, int(round(tick_delta)) - 1)

        if time_delta is not None:
            time_deltas.append(time_delta)
            if math.isclose(time_delta, 0.0, abs_tol=1e-9):
                duplicate_times += 1
            elif time_delta < 0.0:
                if not is_reset:
                    reversed_times += 1
            else:
                positive_time_deltas.append(time_delta)

    missing_or_noninteger_ticks = invalid_tick_samples if tick_name is not None else 0
    tick_discontinuities = (
        missing_or_noninteger_ticks
        + duplicate_ticks
        + reversed_ticks
        + tick_gap_transitions
    )
    tick_order_qualified = bool(
        count
        and tick_name is not None
        and valid_tick_count == count
        and integer_tick_count == count
        and tick_discontinuities == 0
    )
    ticks_qualified = tick_order_qualified and rate is not None

    epoch_indexes: list[int] = []
    epoch_index = 0
    for index in range(count):
        if index in reset_boundaries:
            epoch_index += 1
        epoch_indexes.append(epoch_index)
    epoch_count = epoch_index + 1 if count else 0

    canonical_times: list[float | None] = [None] * count
    canonical_elapsed: list[float | None] = [None] * count
    if ticks_qualified and rate is not None:
        elapsed_offset = 0.0
        for epoch in range(epoch_count):
            indexes = [index for index, value in enumerate(epoch_indexes) if value == epoch]
            if not indexes:
                continue
            first = indexes[0]
            first_tick = ticks[first]
            assert first_tick is not None
            observed_anchor = observed_times[first]
            if observed_anchor is None:
                observed_anchor = (
                    canonical_times[first - 1] + 1.0 / rate
                    if first > 0 and canonical_times[first - 1] is not None
                    else elapsed_offset
                )
            for index in indexes:
                tick = ticks[index]
                assert tick is not None
                epoch_elapsed = (tick - first_tick) / rate
                canonical_times[index] = observed_anchor + epoch_elapsed
                canonical_elapsed[index] = elapsed_offset + epoch_elapsed
            last_elapsed = canonical_elapsed[indexes[-1]]
            elapsed_offset = (last_elapsed if last_elapsed is not None else elapsed_offset) + 1.0 / rate
        primary: ClockPrimary = "session_tick"
    elif valid_time_count:
        canonical_times = list(observed_times)
        first_observed = next((value for value in observed_times if value is not None), None)
        canonical_elapsed = [
            value - first_observed if value is not None and first_observed is not None else None
            for value in observed_times
        ]
        primary = "session_time"
    else:
        primary = "unavailable"

    residuals: list[float | None] = []
    assessed_residuals: list[float] = []
    qualified_residuals: list[float] = []
    all_abs_residuals: list[float] = []
    phase_offset = 0.0
    phase_adjustment_count = 0
    for index, (observed, canonical) in enumerate(zip(observed_times, canonical_times)):
        residual = observed - canonical if observed is not None and canonical is not None else None
        residuals.append(residual)
        if residual is None:
            continue
        all_abs_residuals.append(abs(residual))
        if index in reset_boundaries:
            phase_offset = 0.0
        if ticks_qualified and rate is not None and index > 0 and index not in reset_boundaries:
            previous_observed = observed_times[index - 1]
            previous_tick = ticks[index - 1]
            current_tick = ticks[index]
            if (
                previous_observed is not None
                and previous_tick is not None
                and current_tick is not None
            ):
                transition_error = (
                    observed - previous_observed - (current_tick - previous_tick) / rate
                )
                one_tick = 1.0 / rate
                if 0.75 * one_tick <= abs(transition_error) <= 1.5 * one_tick:
                    # iRacing can quantize/rephase SessionTime by one base
                    # record while SessionTick stays contiguous.  Preserve the
                    # raw residual above, but remove that discrete phase step
                    # when testing sustained clock-rate agreement.
                    phase_offset += transition_error
                    phase_adjustment_count += 1
        qualified_residual = residual - phase_offset
        if index == 0 or index in reset_boundaries:
            assessed_residuals.append(abs(residual))
            qualified_residuals.append(abs(qualified_residual))
            continue
        previous = observed_times[index - 1]
        if previous is not None and observed > previous:
            assessed_residuals.append(abs(residual))
            qualified_residuals.append(abs(qualified_residual))

    residual_p95 = _percentile(assessed_residuals, 0.95) if ticks_qualified else None
    qualified_residual_p95 = (
        _percentile(qualified_residuals, 0.95) if ticks_qualified else None
    )
    residual_max = max(all_abs_residuals) if ticks_qualified and all_abs_residuals else None
    material_disagreements = sum(
        value > _CLOCK_DISAGREEMENT_LIMIT_S for value in qualified_residuals
    ) if ticks_qualified else 0

    expected_dt = 1.0 / rate if rate is not None else None
    timestamp_gaps = (
        sum(delta > expected_dt * 1.5 for delta in time_deltas if delta > 0.0)
        if expected_dt is not None
        else 0
    )
    observed_rate = 1.0 / median(positive_time_deltas) if positive_time_deltas else None

    blockers: list[str] = []
    if tick_name is not None and tick_discontinuities:
        blockers.append("tick_discontinuity")
    # Contiguous integer ticks still establish sample order when an older call
    # site cannot supply the decoder's declared rate.  In that degraded mode a
    # duplicate observed timestamp is retained but does not invalidate the lap;
    # a reversal still blocks because exact elapsed time is unresolved.
    if primary == "session_time" and (
        reversed_times or (duplicate_times and not tick_order_qualified)
    ):
        blockers.append("observed_session_time_not_monotonic")
    if primary == "unavailable" or sum(value is not None for value in canonical_times) != count:
        blockers.append("canonical_clock_incomplete")
    if (
        qualified_residual_p95 is not None
        and qualified_residual_p95 > _CLOCK_DISAGREEMENT_LIMIT_S
    ):
        blockers.append("material_session_clock_disagreement")

    finite_canonical = [value for value in canonical_times if value is not None]
    finite_elapsed = [value for value in canonical_elapsed if value is not None]
    canonical_duration = (
        max(finite_elapsed) - min(finite_elapsed) if len(finite_elapsed) >= 2 else None
    )
    corroboration, corroboration_blockers = _lap_corroboration(
        table,
        count=count,
        canonical_duration_s=canonical_duration,
        tick_rate_hz=rate,
    )
    blockers.extend(corroboration_blockers)
    blockers = list(dict.fromkeys(blockers))

    if primary == "unavailable":
        state: ClockState = "unavailable"
    elif blockers:
        state = "blocked"
    elif primary == "session_tick":
        state = "qualified"
    else:
        state = "degraded"

    sources = [name for name in (tick_name, time_name, *corroboration["source_channels"]) if name]
    clock = QualifiedTelemetryClock(
        primary_clock=primary,
        clock_state=state,
        tick_rate_hz=rate if primary == "session_tick" else None,
        sample_count=count,
        epoch_count=epoch_count,
        reset_epoch_count=len(reset_boundaries),
        canonical_clock_coverage_pct=(
            sum(value is not None for value in canonical_times) / count * 100.0 if count else None
        ),
        session_tick_coverage_pct=valid_tick_count / count * 100.0 if count else None,
        session_time_coverage_pct=valid_time_count / count * 100.0 if count else None,
        canonical_start_time_s=finite_canonical[0] if finite_canonical else None,
        canonical_end_time_s=finite_canonical[-1] if finite_canonical else None,
        canonical_duration_s=canonical_duration,
        observed_session_time_start_s=observed_times[0] if observed_times else None,
        observed_session_time_end_s=observed_times[-1] if observed_times else None,
        observed_sample_rate_hz=observed_rate,
        invalid_tick_sample_count=invalid_tick_samples,
        invalid_session_time_sample_count=invalid_time_samples,
        duplicate_tick_transition_count=duplicate_ticks,
        reversed_tick_transition_count=reversed_ticks,
        dropped_tick_count=dropped_ticks,
        tick_discontinuity_count=tick_discontinuities,
        session_time_duplicate_count=duplicate_times,
        session_time_reverse_count=reversed_times,
        timestamp_gap_count=timestamp_gaps,
        largest_timestamp_step_s=max(time_deltas) if time_deltas else None,
        session_time_residual_p95_s=residual_p95,
        qualified_session_time_residual_p95_s=qualified_residual_p95,
        session_time_residual_max_abs_s=residual_max,
        session_time_phase_adjustment_count=phase_adjustment_count,
        material_clock_disagreement_count=material_disagreements,
        simulator_lap_time_s=corroboration["simulator_lap_time_s"],
        simulator_lap_time_source=corroboration["simulator_lap_time_source"],
        simulator_lap_time_residual_s=corroboration["simulator_lap_time_residual_s"],
        simulator_lap_time_tolerance_s=corroboration["simulator_lap_time_tolerance_s"],
        lap_time_channel_corroboration=corroboration["lap_time_channel_corroboration"],
        lap_delta_validity_corroboration=corroboration["lap_delta_validity_corroboration"],
        source_channels=list(dict.fromkeys(sources)),
        blockers=blockers,
    )
    clock._canonical_time_by_sample_s = tuple(canonical_times)
    clock._canonical_elapsed_by_sample_s = tuple(canonical_elapsed)
    clock._observed_session_time_by_sample_s = tuple(observed_times)
    clock._session_time_residual_by_sample_s = tuple(residuals)
    clock._epoch_index_by_sample = tuple(epoch_indexes)
    return clock


__all__ = ["QualifiedTelemetryClock", "build_qualified_telemetry_clock"]
