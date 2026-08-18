"""Continuous-clock brake and throttle response producers.

The analyzer consumes an already verified P3/P20 telemetry projection.  It
does not read artifacts, compare sample indexes across laps, infer handling
causes, or authorize setup work.  Input episodes are found with an
episode-relative excursion/noise rule; temporal results require the canonical
qualified tick clock and repeatability is counted only across distinct
canonical eligible laps.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from statistics import median
from typing import Any

import polars as pl

from racelab_engine.analysis.qualified_clock import (
    QualifiedTelemetryClock,
    build_qualified_telemetry_clock,
)
from racelab_engine.models.dynamic_response import (
    DynamicResponseEpisode,
    DynamicResponsePathContract,
    DynamicResponsePathResult,
    DynamicResponseRepeatability,
    DynamicResponseReport,
    DynamicResponseSignature,
    QualifiedClockBinding,
    ResponsePhysicalScope,
    ResponseSpeedBand,
)
from racelab_engine.models.evidence import EvidenceState


_FORMULA_VERSION = "p20.dynamic_response.v1"
_INPUT_ONSET_FRACTION = 0.10
_RESPONSE_ONSET_FRACTION = 0.10
_STEADY_TOLERANCE_FRACTION = 0.10
_NUMERIC_EPSILON = 1e-12

_PRESSURE_CHANNELS = (
    "lf_brake_line_pressure_bar",
    "rf_brake_line_pressure_bar",
    "lr_brake_line_pressure_bar",
    "rr_brake_line_pressure_bar",
)
_CLOCK_POSITION_CONTEXT = (
    "session_tick",
    "lap_dist_pct_100",
    "speed_mps",
)


def _path(
    *,
    event: str,
    input_channel: str,
    transition: str,
    response_channel: str,
    response_unit: str,
    response_polarity: str,
) -> DynamicResponsePathContract:
    return DynamicResponsePathContract(
        contract_id=(
            f"p20.dynamic_response.{event}.{response_channel}.{_FORMULA_VERSION}"
        ),
        formula_version=_FORMULA_VERSION,
        input_channel=input_channel,
        input_unit="%",
        input_transition=transition,
        response_channel=response_channel,
        response_unit=response_unit,
        response_polarity=response_polarity,
        gain_unit=f"{response_unit}/%",
        required_channels=(
            input_channel,
            response_channel,
            *_CLOCK_POSITION_CONTEXT,
        ),
        preferred_channels=("session_time", "engineering_phase"),
    )


BRAKE_APPLICATION_RESPONSE_CONTRACTS = tuple(
    [
        _path(
            event="brake_application",
            input_channel="brake_pct",
            transition="rising",
            response_channel=channel,
            response_unit="bar",
            response_polarity="positive",
        )
        for channel in _PRESSURE_CHANNELS
    ]
    + [
        _path(
            event="brake_application",
            input_channel="brake_pct",
            transition="rising",
            response_channel="long_accel",
            response_unit="m/s^2",
            response_polarity="negative",
        ),
        _path(
            event="brake_application",
            input_channel="brake_pct",
            transition="rising",
            response_channel="yaw_rate",
            response_unit="rad/s",
            response_polarity="either",
        ),
    ]
)

BRAKE_RELEASE_RESPONSE_CONTRACTS = tuple(
    [
        _path(
            event="brake_release",
            input_channel="brake_pct",
            transition="falling",
            response_channel=channel,
            response_unit="bar",
            response_polarity="negative",
        )
        for channel in _PRESSURE_CHANNELS
    ]
    + [
        _path(
            event="brake_release",
            input_channel="brake_pct",
            transition="falling",
            response_channel="yaw_rate",
            response_unit="rad/s",
            response_polarity="either",
        ),
    ]
)

THROTTLE_APPLICATION_RESPONSE_CONTRACTS = (
    _path(
        event="throttle_application",
        input_channel="throttle_pct",
        transition="rising",
        response_channel="long_accel",
        response_unit="m/s^2",
        response_polarity="positive",
    ),
    _path(
        event="throttle_application",
        input_channel="throttle_pct",
        transition="rising",
        response_channel="yaw_rate",
        response_unit="rad/s",
        response_polarity="either",
    ),
)

BRAKE_THROTTLE_RESPONSE_CONTRACTS = (
    *BRAKE_APPLICATION_RESPONSE_CONTRACTS,
    *BRAKE_RELEASE_RESPONSE_CONTRACTS,
    *THROTTLE_APPLICATION_RESPONSE_CONTRACTS,
)


@dataclass(frozen=True)
class _PreparedLap:
    lap_number: int
    rows: tuple[dict[str, Any], ...]
    times: tuple[float, ...]
    positions: tuple[float, ...]
    clock: QualifiedTelemetryClock
    binding: QualifiedClockBinding


@dataclass(frozen=True)
class _InputEvent:
    lap_number: int
    phase: str
    transition: str
    start_index: int
    end_index: int
    input_baseline: float
    input_excursion: float


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _lap_number(row: Mapping[str, Any]) -> int | None:
    value = _finite(row.get("lap", row.get("lap_number")))
    if value is None or not math.isclose(value, round(value), abs_tol=1e-9):
        return None
    return int(round(value))


def _lap_position(row: Mapping[str, Any]) -> float | None:
    value = _finite(row.get("lap_dist_pct_100"))
    if value is not None:
        return value if 0.0 <= value <= 100.0 else None
    value = _finite(row.get("lap_dist_pct", row.get("LapDistPct")))
    if value is None:
        return None
    value = value * 100.0 if 0.0 <= value <= 1.5 else value
    return value if 0.0 <= value <= 100.0 else None


def _channel_value(row: Mapping[str, Any], channel: str) -> float | None:
    value = _finite(row.get(channel))
    if value is not None:
        return value
    aliases = {
        "session_tick": ("SessionTick",),
        "session_time": ("SessionTime",),
        "speed_mps": ("Speed",),
    }
    for alias in aliases.get(channel, ()):
        value = _finite(row.get(alias))
        if value is not None:
            return value
    return None


def _source_name(rows: Sequence[Mapping[str, Any]], channel: str) -> str:
    candidates = {
        "session_tick": ("session_tick", "SessionTick"),
        "session_time": ("session_time", "SessionTime"),
        "lap_dist_pct_100": ("lap_dist_pct_100", "lap_dist_pct", "LapDistPct"),
        "speed_mps": ("speed_mps", "Speed"),
    }.get(channel, (channel,))
    return next(
        (
            name
            for name in candidates
            if any(name in row and _finite(row.get(name)) is not None for row in rows)
        ),
        channel,
    )


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _mad(values: Sequence[float], center: float | None = None) -> float:
    if not values:
        return 0.0
    resolved_center = median(values) if center is None else center
    return float(median(abs(value - resolved_center) for value in values))


def _median_or_none(values: Sequence[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None]
    return float(median(finite)) if finite else None


def _content_id(prefix: str, payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:24]}"


def _clock_binding(
    clock: QualifiedTelemetryClock,
    *,
    run_id: str,
    lap_number: int,
) -> QualifiedClockBinding:
    identity = {
        "run_id": run_id,
        "lap_number": lap_number,
        "clock": clock.model_dump(mode="json"),
        "canonical_elapsed_time_s": clock.canonical_elapsed_time_s,
        "epoch_index_by_sample": clock.epoch_index_by_sample,
    }
    blockers = list(clock.blockers)
    if clock.clock_state != "qualified" or clock.primary_clock != "session_tick":
        blockers.append("qualified_tick_clock_required_for_dynamic_response")
    return QualifiedClockBinding(
        clock_id=_content_id("telemetry-clock", identity),
        run_id=run_id,
        lap_number=lap_number,
        primary_clock=clock.primary_clock,
        clock_state=clock.clock_state,
        tick_rate_hz=clock.tick_rate_hz,
        canonical_clock_coverage_pct=clock.canonical_clock_coverage_pct,
        source_channels=tuple(dict.fromkeys(clock.source_channels)),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _rows_from_table(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(data, pl.DataFrame):
        return data.to_dicts()
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        return [dict(row) for row in data if isinstance(row, Mapping)]
    return []


def _prepare_laps(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    eligible_lap_numbers: tuple[int, ...],
    expected_sample_rate_hz: float | None,
) -> tuple[tuple[_PreparedLap, ...], tuple[QualifiedClockBinding, ...], tuple[str, ...]]:
    grouped: dict[int, list[dict[str, Any]]] = {
        lap_number: [] for lap_number in eligible_lap_numbers
    }
    for source in rows:
        number = _lap_number(source)
        if number in grouped:
            grouped[number].append(dict(source))

    prepared: list[_PreparedLap] = []
    bindings: list[QualifiedClockBinding] = []
    blockers: list[str] = []
    for lap_number in eligible_lap_numbers:
        lap_rows = grouped.get(lap_number, [])
        if not lap_rows:
            blockers.append(f"eligible_lap_missing_telemetry:{lap_number}")
            continue
        clock = build_qualified_telemetry_clock(
            lap_rows,
            expected_sample_rate_hz=expected_sample_rate_hz,
        )
        binding = _clock_binding(clock, run_id=run_id, lap_number=lap_number)
        bindings.append(binding)
        canonical = clock.canonical_time_by_sample_s
        positions = tuple(_lap_position(row) for row in lap_rows)
        if binding.blockers:
            blockers.extend(
                f"lap_{lap_number}_clock:{reason}" for reason in binding.blockers
            )
            continue
        if (
            len(canonical) != len(lap_rows)
            or any(value is None or not math.isfinite(value) for value in canonical)
        ):
            blockers.append(f"lap_{lap_number}_clock:canonical_clock_incomplete")
            continue
        if any(value is None for value in positions):
            blockers.append(f"lap_{lap_number}:physical_position_incomplete")
            continue
        prepared.append(
            _PreparedLap(
                lap_number=lap_number,
                rows=tuple(lap_rows),
                times=tuple(float(value) for value in canonical if value is not None),
                positions=tuple(float(value) for value in positions if value is not None),
                clock=clock,
                binding=binding,
            )
        )
    return tuple(prepared), tuple(bindings), tuple(dict.fromkeys(blockers))


def _phase_for_event(
    lap: _PreparedLap,
    index: int,
    *,
    input_channel: str,
    transition: str,
) -> str:
    explicit = str(lap.rows[index].get("engineering_phase") or "").strip()
    if explicit:
        return explicit
    if input_channel == "brake_pct":
        return "brake_application" if transition == "rising" else "brake_release"
    return "initial_throttle"


def _detect_rising_events(
    lap: _PreparedLap,
    *,
    input_channel: str,
) -> tuple[_InputEvent, ...]:
    values = [_channel_value(row, input_channel) for row in lap.rows]
    if len(values) < 8 or any(value is None for value in values):
        return ()
    finite_values = [float(value) for value in values if value is not None]
    low = _quantile(finite_values, 0.05)
    high = _quantile(finite_values, 0.95)
    observed_range = high - low
    if observed_range <= _NUMERIC_EPSILON:
        return ()
    onset_level = low + _INPUT_ONSET_FRACTION * observed_range
    activation_level = low + 0.50 * observed_range
    events: list[_InputEvent] = []
    index = 1
    while index < len(finite_values):
        if not (
            finite_values[index - 1] <= onset_level < finite_values[index]
        ):
            index += 1
            continue
        return_index = next(
            (
                candidate
                for candidate in range(index + 1, len(finite_values))
                if finite_values[candidate] <= onset_level
            ),
            len(finite_values) - 1,
        )
        peak_index = max(
            range(index, return_index + 1),
            key=lambda candidate: finite_values[candidate],
        )
        peak = finite_values[peak_index]
        if peak < activation_level:
            index = max(index + 1, return_index)
            continue
        release_level = peak - _INPUT_ONSET_FRACTION * (peak - low)
        release_index = next(
            (
                candidate
                for candidate in range(peak_index + 1, return_index + 1)
                if finite_values[candidate] <= release_level
            ),
            return_index,
        )
        if release_index - index >= 2:
            events.append(
                _InputEvent(
                    lap_number=lap.lap_number,
                    phase=_phase_for_event(
                        lap,
                        index,
                        input_channel=input_channel,
                        transition="rising",
                    ),
                    transition="rising",
                    start_index=index,
                    end_index=release_index,
                    input_baseline=low,
                    input_excursion=peak - low,
                )
            )
        index = max(index + 1, return_index)
    return tuple(events)


def _release_events(
    lap: _PreparedLap,
    rising_events: Sequence[_InputEvent],
    *,
    input_channel: str,
) -> tuple[_InputEvent, ...]:
    values = [_channel_value(row, input_channel) for row in lap.rows]
    if any(value is None for value in values):
        return ()
    finite_values = [float(value) for value in values if value is not None]
    releases: list[_InputEvent] = []
    for application in rising_events:
        start = application.end_index
        peak = max(finite_values[application.start_index : start + 1])
        baseline = peak - application.input_excursion
        complete_level = baseline + _INPUT_ONSET_FRACTION * application.input_excursion
        transition_complete = next(
            (
                candidate
                for candidate in range(start + 1, len(finite_values))
                if finite_values[candidate] <= complete_level
            ),
            None,
        )
        if transition_complete is None or transition_complete - start < 2:
            continue
        # Keep an episode-relative post-release observation window.  This lets
        # pressure/yaw settling be measured without imposing a universal fixed
        # handling-time threshold.
        transition_samples = transition_complete - start
        end = min(
            len(finite_values) - 1,
            transition_complete + max(3, transition_samples),
        )
        releases.append(
            _InputEvent(
                lap_number=lap.lap_number,
                phase=_phase_for_event(
                    lap,
                    start,
                    input_channel=input_channel,
                    transition="falling",
                ),
                transition="falling",
                start_index=start,
                end_index=end,
                input_baseline=peak,
                input_excursion=finite_values[transition_complete] - peak,
            )
        )
    return tuple(releases)


def _oriented_delta(delta: float, polarity: str) -> float:
    if polarity == "positive":
        return delta
    if polarity == "negative":
        return -delta
    return abs(delta)


def _correction_count(
    response_deltas: Sequence[float],
    *,
    baseline_noise: float,
) -> int:
    if len(response_deltas) < 4:
        return 0
    smoothed = [
        float(median(response_deltas[max(0, index - 1) : index + 2]))
        for index in range(len(response_deltas))
    ]
    differences = [right - left for left, right in zip(smoothed, smoothed[1:])]
    event_scale = max((abs(value) for value in differences), default=0.0)
    meaningful = max(3.0 * baseline_noise, event_scale * 0.01, _NUMERIC_EPSILON)
    signs = [
        1 if value > meaningful else -1 if value < -meaningful else 0
        for value in differences
    ]
    nonzero = [sign for sign in signs if sign]
    return sum(left != right for left, right in zip(nonzero, nonzero[1:]))


def _measure_episode(
    lap: _PreparedLap,
    event: _InputEvent,
    contract: DynamicResponsePathContract,
) -> tuple[DynamicResponseEpisode | None, str | None]:
    start = event.start_index
    end = event.end_index
    if end - start < 2:
        return None, "input_episode_has_fewer_than_three_samples"
    rate = lap.binding.tick_rate_hz
    if rate is None:
        return None, "qualified_tick_rate_unavailable"
    baseline_count = max(3, int(round(rate * 0.20)))
    baseline_start = max(0, start - baseline_count)
    baseline_indexes = list(range(baseline_start, start))
    if len(baseline_indexes) < 3:
        return None, "pre_event_baseline_has_fewer_than_three_samples"

    input_values = [
        _channel_value(lap.rows[index], contract.input_channel)
        for index in range(baseline_start, end + 1)
    ]
    response_values = [
        _channel_value(lap.rows[index], contract.response_channel)
        for index in range(baseline_start, end + 1)
    ]
    speeds = [
        _channel_value(lap.rows[index], "speed_mps")
        for index in range(start, end + 1)
    ]
    if any(value is None for value in input_values):
        return None, f"nonfinite_episode_channel:{contract.input_channel}"
    if any(value is None for value in response_values):
        return None, f"nonfinite_episode_channel:{contract.response_channel}"
    if any(value is None or value < 0.0 for value in speeds):
        return None, "nonfinite_episode_channel:speed_mps"

    input_series = [float(value) for value in input_values if value is not None]
    response_series = [float(value) for value in response_values if value is not None]
    speed_series = [float(value) for value in speeds if value is not None]
    local_start = start - baseline_start
    local_end = end - baseline_start
    response_baseline_values = response_series[:local_start]
    input_baseline_values = input_series[:local_start]
    response_baseline = float(median(response_baseline_values))
    input_baseline = float(median(input_baseline_values))
    response_noise = _mad(response_baseline_values, response_baseline)
    input_noise = _mad(input_baseline_values, input_baseline)
    response_deltas = [
        value - response_baseline
        for value in response_series[local_start : local_end + 1]
    ]
    input_deltas = [
        value - input_baseline
        for value in input_series[local_start : local_end + 1]
    ]
    oriented = [
        _oriented_delta(value, contract.response_polarity)
        for value in response_deltas
    ]
    amplitude = max(oriented, default=0.0)
    response_threshold = max(
        amplitude * _RESPONSE_ONSET_FRACTION,
        response_noise * 3.0,
        _NUMERIC_EPSILON,
    )
    if amplitude < response_threshold:
        return None, f"no_detectable_response:{contract.response_channel}"
    onset_offset = next(
        (
            index
            for index, value in enumerate(oriented)
            if value >= response_threshold
            and (
                index + 1 == len(oriented)
                or oriented[index + 1] >= response_threshold * 0.5
            )
        ),
        None,
    )
    if onset_offset is None:
        return None, f"response_onset_unresolved:{contract.response_channel}"
    response_index = start + onset_offset
    peak_offset = max(range(len(oriented)), key=oriented.__getitem__)

    minimum_input_delta = max(
        abs(event.input_excursion) * 0.05,
        input_noise * 3.0,
        _NUMERIC_EPSILON,
    )

    def gain_at(offset: int) -> float | None:
        input_delta = input_deltas[offset]
        if abs(input_delta) < minimum_input_delta:
            return None
        return response_deltas[offset] / input_delta

    initial_candidates = [
        gain_at(index)
        for index in range(onset_offset, min(len(oriented), onset_offset + 3))
    ]
    initial_gain = _median_or_none(initial_candidates)
    peak_gain = gain_at(peak_offset)

    tail_count = max(3, len(oriented) // 5)
    tail_start = max(onset_offset, len(oriented) - tail_count)
    tail_response = response_deltas[tail_start:]
    tail_input = input_deltas[tail_start:]
    steady_response = float(median(tail_response))
    steady_input = float(median(tail_input))
    input_tail_tolerance = max(
        abs(steady_input) * _STEADY_TOLERANCE_FRACTION,
        input_noise * 3.0,
        _NUMERIC_EPSILON,
    )
    input_is_steady = all(
        abs(value - steady_input) <= input_tail_tolerance for value in tail_input
    )
    response_tail_noise = _mad(tail_response, steady_response)
    settle_tolerance = max(
        amplitude * _STEADY_TOLERANCE_FRACTION,
        response_tail_noise * 3.0,
        _NUMERIC_EPSILON,
    )
    settle_offset = next(
        (
            index
            for index in range(onset_offset, len(response_deltas))
            if input_is_steady
            and all(
                abs(value - steady_response) <= settle_tolerance
                for value in response_deltas[index:]
            )
        ),
        None,
    )
    steady_gain = (
        steady_response / steady_input
        if settle_offset is not None and abs(steady_input) >= minimum_input_delta
        else None
    )
    peak_oriented = oriented[peak_offset]
    steady_oriented = _oriented_delta(steady_response, contract.response_polarity)
    overshoot = (
        max(0.0, (peak_oriented - steady_oriented) / steady_oriented)
        if settle_offset is not None and steady_oriented > _NUMERIC_EPSILON
        else None
    )
    input_time = lap.times[start]
    response_time = lap.times[response_index]
    source_channels = tuple(dict.fromkeys(
        (
            *(
                _source_name(lap.rows, channel)
                for channel in contract.required_channels
            ),
            *lap.binding.source_channels,
        )
    ))
    payload = {
        "contract_id": contract.contract_id,
        "run_id": lap.binding.run_id,
        "setup_id": "pending",
        "lap_number": lap.lap_number,
        "phase": event.phase,
        "start": start,
        "end": end,
        "input_onset_time_s": input_time,
        "response_onset_time_s": response_time,
        "clock_id": lap.binding.clock_id,
    }
    # setup_id is rebound by the public builder before validation; excluding it
    # from this helper keeps event measurement independent of setup policy.
    episode_id = _content_id("response-episode", payload)
    return (
        DynamicResponseEpisode(
            episode_id=episode_id,
            contract_id=contract.contract_id,
            run_id=lap.binding.run_id,
            setup_id="pending",
            lap_number=lap.lap_number,
            phase=event.phase,
            physical_scope=ResponsePhysicalScope(
                lap_pct_start=min(lap.positions[start : end + 1]),
                lap_pct_end=max(lap.positions[start : end + 1]),
                input_onset_lap_pct=lap.positions[start],
                response_onset_lap_pct=lap.positions[response_index],
            ),
            input_onset_time_s=input_time,
            response_onset_time_s=response_time,
            observed_lag_s=response_time - input_time,
            input_delta=input_deltas[peak_offset],
            response_delta=response_deltas[peak_offset],
            initial_gain=initial_gain,
            peak_gain=peak_gain,
            steady_gain=steady_gain,
            gain_unit=contract.gain_unit,
            overshoot_fraction=overshoot,
            settling_duration_s=(
                lap.times[start + settle_offset] - response_time
                if settle_offset is not None
                else None
            ),
            correction_count=_correction_count(
                response_deltas[onset_offset:],
                baseline_noise=response_noise,
            ),
            speed_band=ResponseSpeedBand(
                minimum_mps=min(speed_series),
                median_mps=float(median(speed_series)),
                maximum_mps=max(speed_series),
            ),
            sample_count=end - start + 1,
            source_channels=source_channels,
            canonical_clock_id=lap.binding.clock_id,
        ),
        None,
    )


def _rebind_episode_setup(
    episode: DynamicResponseEpisode,
    *,
    setup_id: str,
) -> DynamicResponseEpisode:
    payload = episode.model_dump(mode="json")
    payload["setup_id"] = setup_id
    identity = dict(payload)
    identity.pop("episode_id", None)
    payload["episode_id"] = _content_id("response-episode", identity)
    return DynamicResponseEpisode.model_validate(payload)


def _physical_clusters(
    episodes: Sequence[DynamicResponseEpisode],
) -> tuple[tuple[DynamicResponseEpisode, ...], ...]:
    """Match repeated episodes by physical position, never by sample index."""

    clusters: list[list[DynamicResponseEpisode]] = []
    phases = tuple(dict.fromkeys(episode.phase for episode in episodes))
    for phase in phases:
        scoped = [episode for episode in episodes if episode.phase == phase]
        by_lap: dict[int, list[DynamicResponseEpisode]] = {}
        for episode in scoped:
            by_lap.setdefault(episode.lap_number, []).append(episode)
        for lap_number in sorted(by_lap):
            current = sorted(
                by_lap[lap_number],
                key=lambda item: item.physical_scope.input_onset_lap_pct,
            )
            available = [
                index
                for index, cluster in enumerate(clusters)
                if cluster[0].phase == phase
                and all(item.lap_number != lap_number for item in cluster)
            ]
            assignments: list[tuple[float, int, int]] = []
            for episode_index, episode in enumerate(current):
                for cluster_index in available:
                    if not all(
                        _episodes_share_physical_event(episode, member)
                        for member in clusters[cluster_index]
                    ):
                        continue
                    center = float(median(
                        item.physical_scope.input_onset_lap_pct
                        for item in clusters[cluster_index]
                    ))
                    assignments.append((
                        abs(episode.physical_scope.input_onset_lap_pct - center),
                        episode_index,
                        cluster_index,
                    ))
            used_episodes: set[int] = set()
            used_clusters: set[int] = set()
            for _distance, episode_index, cluster_index in sorted(assignments):
                if episode_index in used_episodes or cluster_index in used_clusters:
                    continue
                clusters[cluster_index].append(current[episode_index])
                used_episodes.add(episode_index)
                used_clusters.add(cluster_index)
            for episode_index, episode in enumerate(current):
                if episode_index not in used_episodes:
                    clusters.append([episode])
    return tuple(
        tuple(sorted(cluster, key=lambda item: item.lap_number))
        for cluster in clusters
    )


def _episode_position_resolution(episode: DynamicResponseEpisode) -> float:
    """Estimate one physical sample bin from this exact episode's own scope."""

    return (
        episode.physical_scope.lap_pct_end
        - episode.physical_scope.lap_pct_start
    ) / max(1, episode.sample_count - 1)


def _episodes_share_physical_event(
    left: DynamicResponseEpisode,
    right: DynamicResponseEpisode,
) -> bool:
    """Fail closed unless two onsets resolve to one physical track event.

    One observed position bin from each episode defines the full matching
    tolerance.  There is no track-wide nominal percentage allowance, and every
    member must match every other member so a chain of small shifts cannot
    bridge two distant events.
    """

    if left.phase != right.phase or left.lap_number == right.lap_number:
        return False
    tolerance_pct = (
        _episode_position_resolution(left)
        + _episode_position_resolution(right)
    )
    onset_distance_pct = abs(
        left.physical_scope.input_onset_lap_pct
        - right.physical_scope.input_onset_lap_pct
    )
    scope_gap_pct = max(
        0.0,
        max(
            left.physical_scope.lap_pct_start,
            right.physical_scope.lap_pct_start,
        )
        - min(
            left.physical_scope.lap_pct_end,
            right.physical_scope.lap_pct_end,
        ),
    )
    return (
        onset_distance_pct <= tolerance_pct + _NUMERIC_EPSILON
        and scope_gap_pct <= tolerance_pct + _NUMERIC_EPSILON
    )


def _repeatability(
    episodes: Sequence[DynamicResponseEpisode],
) -> DynamicResponseRepeatability:
    onset_positions = [
        episode.physical_scope.input_onset_lap_pct for episode in episodes
    ]
    lags = [episode.observed_lag_s for episode in episodes]
    gains = [
        episode.peak_gain
        for episode in episodes
        if episode.peak_gain is not None
    ]
    onset_mad = _mad(onset_positions)
    lag_mad = _mad(lags)
    scope_scale = max(
        float(median(
            max(
                episode.physical_scope.lap_pct_end
                - episode.physical_scope.lap_pct_start,
                _NUMERIC_EPSILON,
            )
            for episode in episodes
        )),
        _NUMERIC_EPSILON,
    )
    lag_scale = max(float(median(abs(value) for value in lags)), 1e-6)
    components = [onset_mad / scope_scale, lag_mad / lag_scale]
    gain_relative_mad: float | None = None
    if len(gains) >= 2:
        gain_center = float(median(gains))
        gain_relative_mad = _mad(gains, gain_center) / max(
            abs(gain_center),
            _NUMERIC_EPSILON,
        )
        components.append(gain_relative_mad)
    score = 1.0 / (1.0 + float(sum(components) / len(components)))
    lap_numbers = tuple(episode.lap_number for episode in episodes)
    return DynamicResponseRepeatability(
        score=max(0.0, min(1.0, score)),
        independent_lap_count=len(lap_numbers),
        independent_lap_numbers=lap_numbers,
        input_onset_position_mad_pct=onset_mad,
        observed_lag_mad_s=lag_mad,
        peak_gain_relative_mad=gain_relative_mad,
    )


def _signature(
    contract: DynamicResponsePathContract,
    episodes: Sequence[DynamicResponseEpisode],
) -> DynamicResponseSignature:
    repeatability = _repeatability(episodes)
    median_lag = float(median(episode.observed_lag_s for episode in episodes))
    median_position = float(median(
        episode.physical_scope.input_onset_lap_pct for episode in episodes
    ))
    representative = min(
        episodes,
        key=lambda episode: (
            abs(episode.observed_lag_s - median_lag)
            + abs(episode.physical_scope.input_onset_lap_pct - median_position),
            episode.lap_number,
        ),
    )
    scope = ResponsePhysicalScope(
        lap_pct_start=min(
            episode.physical_scope.lap_pct_start for episode in episodes
        ),
        lap_pct_end=max(
            episode.physical_scope.lap_pct_end for episode in episodes
        ),
        input_onset_lap_pct=median_position,
        response_onset_lap_pct=float(median(
            episode.physical_scope.response_onset_lap_pct for episode in episodes
        )),
    )
    speed_medians = [episode.speed_band.median_mps for episode in episodes]
    source_channels = tuple(dict.fromkeys(
        channel for episode in episodes for channel in episode.source_channels
    ))
    clock_ids = tuple(dict.fromkeys(
        episode.canonical_clock_id for episode in episodes
    ))
    payload = {
        "contract": contract.model_dump(mode="json"),
        "run_id": representative.run_id,
        "setup_id": representative.setup_id,
        "phase": representative.phase,
        "episode_ids": [episode.episode_id for episode in episodes],
        "clock_ids": clock_ids,
    }
    return DynamicResponseSignature(
        signature_id=_content_id("dynamic-response", payload),
        contract=contract,
        run_id=representative.run_id,
        setup_id=representative.setup_id,
        phase=representative.phase,
        physical_scope=scope,
        representative_input_onset_time_s=representative.input_onset_time_s,
        representative_response_onset_time_s=representative.response_onset_time_s,
        median_observed_lag_s=median_lag,
        median_initial_gain=_median_or_none(
            [episode.initial_gain for episode in episodes]
        ),
        median_peak_gain=_median_or_none(
            [episode.peak_gain for episode in episodes]
        ),
        median_steady_gain=_median_or_none(
            [episode.steady_gain for episode in episodes]
        ),
        gain_unit=contract.gain_unit,
        median_overshoot_fraction=_median_or_none(
            [episode.overshoot_fraction for episode in episodes]
        ),
        median_settling_duration_s=_median_or_none(
            [episode.settling_duration_s for episode in episodes]
        ),
        median_correction_count=float(median(
            episode.correction_count for episode in episodes
        )),
        speed_band=ResponseSpeedBand(
            minimum_mps=min(episode.speed_band.minimum_mps for episode in episodes),
            median_mps=float(median(speed_medians)),
            maximum_mps=max(episode.speed_band.maximum_mps for episode in episodes),
        ),
        repeatability=repeatability,
        episodes=tuple(episodes),
        source_channels=source_channels,
        canonical_clock_ids=clock_ids,
    )


def _path_result(
    contract: DynamicResponsePathContract,
    prepared_laps: Sequence[_PreparedLap],
    *,
    setup_id: str,
) -> DynamicResponsePathResult:
    missing = [
        channel
        for channel in contract.required_channels
        if channel not in {"session_tick", "lap_dist_pct_100"}
        and not any(
            _channel_value(row, channel) is not None
            for lap in prepared_laps
            for row in lap.rows
        )
    ]
    if missing:
        return DynamicResponsePathResult(
            contract=contract,
            status="blocked",
            detected_episode_count=0,
            independent_lap_count=0,
            blocker_reasons=tuple(
                f"missing_required_channel:{channel}" for channel in missing
            ),
        )

    episodes: list[DynamicResponseEpisode] = []
    measurement_blockers: list[str] = []
    detected_input_episodes = 0
    for lap in prepared_laps:
        rising = _detect_rising_events(
            lap,
            input_channel=contract.input_channel,
        )
        events = (
            rising
            if contract.input_transition == "rising"
            else _release_events(
                lap,
                rising,
                input_channel=contract.input_channel,
            )
        )
        detected_input_episodes += len(events)
        for event in events:
            episode, blocker = _measure_episode(lap, event, contract)
            if episode is not None:
                episodes.append(_rebind_episode_setup(episode, setup_id=setup_id))
            elif blocker is not None:
                measurement_blockers.append(f"lap_{lap.lap_number}:{blocker}")

    if not episodes:
        if detected_input_episodes == 0:
            return DynamicResponsePathResult(
                contract=contract,
                status="no_finding",
                detected_episode_count=0,
                independent_lap_count=0,
            )
        return DynamicResponsePathResult(
            contract=contract,
            status="blocked",
            detected_episode_count=detected_input_episodes,
            independent_lap_count=0,
            blocker_reasons=tuple(dict.fromkeys(
                measurement_blockers
                or ("response_episode_measurement_unavailable",)
            )),
        )

    clusters = _physical_clusters(episodes)
    signatures = tuple(
        _signature(contract, cluster)
        for cluster in clusters
        if len(cluster) >= contract.minimum_independent_laps
    )
    independent_laps = len({episode.lap_number for episode in episodes})
    if not signatures:
        blockers = [
            (
                "insufficient_physically_corresponding_episodes:requires_"
                f"{contract.minimum_independent_laps}_distinct_eligible_laps_"
                "at_one_empirically_resolved_track_event"
            )
        ]
        blockers.extend(measurement_blockers)
        return DynamicResponsePathResult(
            contract=contract,
            status="blocked",
            detected_episode_count=len(episodes),
            independent_lap_count=independent_laps,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    blockers = tuple(dict.fromkeys(measurement_blockers))
    return DynamicResponsePathResult(
        contract=contract,
        status="partial" if blockers else "ready",
        detected_episode_count=len(episodes),
        independent_lap_count=independent_laps,
        signatures=signatures,
        blocker_reasons=blockers,
    )


def _blocked_paths(
    blockers: Sequence[str],
) -> tuple[DynamicResponsePathResult, ...]:
    reasons = tuple(dict.fromkeys(blockers))
    return tuple(
        DynamicResponsePathResult(
            contract=contract,
            status="blocked",
            detected_episode_count=0,
            independent_lap_count=0,
            blocker_reasons=reasons,
        )
        for contract in BRAKE_THROTTLE_RESPONSE_CONTRACTS
    )


def _report(
    *,
    status: str,
    run_id: str,
    setup_id: str | None,
    eligible_lap_numbers: tuple[int, ...],
    analyzed_lap_numbers: tuple[int, ...],
    clock_bindings: tuple[QualifiedClockBinding, ...],
    paths: tuple[DynamicResponsePathResult, ...],
    blockers: tuple[str, ...],
) -> DynamicResponseReport:
    payload = {
        "status": status,
        "run_id": run_id,
        "setup_id": setup_id,
        "eligible_lap_numbers": eligible_lap_numbers,
        "analyzed_lap_numbers": analyzed_lap_numbers,
        "clock_bindings": [binding.model_dump(mode="json") for binding in clock_bindings],
        "paths": [path.model_dump(mode="json") for path in paths],
        "blockers": blockers,
    }
    return DynamicResponseReport(
        report_id=_content_id("dynamic-response-report", payload),
        status=status,
        run_id=run_id,
        setup_id=setup_id,
        eligible_lap_numbers=eligible_lap_numbers,
        analyzed_lap_numbers=analyzed_lap_numbers,
        clock_bindings=clock_bindings,
        paths=paths,
        blocker_reasons=blockers,
        evidence_state=(
            EvidenceState.BLOCKED_BY_CONTEXT
            if status == "blocked"
            else EvidenceState.CALCULATED
        ),
    )


def analyze_brake_throttle_dynamic_response(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    setup_id: str | None,
    eligible_lap_numbers: Sequence[int],
    expected_sample_rate_hz: float | None,
) -> DynamicResponseReport:
    """Produce qualified brake/throttle response signatures from one P20 read."""

    rows = _rows_from_table(data)
    eligible = tuple(dict.fromkeys(int(value) for value in eligible_lap_numbers))
    global_blockers: list[str] = []
    if not run_id.strip():
        run_id = "invalid-run"
        global_blockers.append("nonempty_run_identity_required")
    if setup_id is None or not setup_id.strip():
        global_blockers.append("recorded_setup_identity_required")
    if len(eligible) < 2:
        global_blockers.append("at_least_two_distinct_canonical_eligible_laps_required")
    if not rows:
        global_blockers.append("verified_telemetry_projection_is_empty")
    if any(
        row.get("run_id") is not None and str(row.get("run_id")) != run_id
        for row in rows
    ):
        global_blockers.append("telemetry_row_belongs_to_foreign_run")
    if global_blockers:
        paths = _blocked_paths(global_blockers)
        return _report(
            status="blocked",
            run_id=run_id,
            setup_id=setup_id,
            eligible_lap_numbers=eligible,
            analyzed_lap_numbers=(),
            clock_bindings=(),
            paths=paths,
            blockers=tuple(dict.fromkeys(global_blockers)),
        )

    prepared, bindings, clock_blockers = _prepare_laps(
        rows,
        run_id=run_id,
        eligible_lap_numbers=eligible,
        expected_sample_rate_hz=expected_sample_rate_hz,
    )
    if clock_blockers:
        paths = _blocked_paths(clock_blockers)
        return _report(
            status="blocked",
            run_id=run_id,
            setup_id=setup_id,
            eligible_lap_numbers=eligible,
            analyzed_lap_numbers=tuple(lap.lap_number for lap in prepared),
            clock_bindings=bindings,
            paths=paths,
            blockers=clock_blockers,
        )
    assert setup_id is not None
    paths = tuple(
        _path_result(contract, prepared, setup_id=setup_id)
        for contract in BRAKE_THROTTLE_RESPONSE_CONTRACTS
    )
    ready = [path for path in paths if path.status == "ready"]
    evidence = [path for path in paths if path.status in {"ready", "partial"}]
    blocked = [path for path in paths if path.status in {"partial", "blocked"}]
    blockers = tuple(dict.fromkeys(
        reason for path in blocked for reason in path.blocker_reasons
    ))
    if len(ready) == len(paths):
        status = "ready"
    elif evidence:
        status = "partial"
    elif blocked:
        status = "blocked"
    else:
        status = "no_finding"
    return _report(
        status=status,
        run_id=run_id,
        setup_id=setup_id,
        eligible_lap_numbers=eligible,
        analyzed_lap_numbers=tuple(lap.lap_number for lap in prepared),
        clock_bindings=bindings,
        paths=paths,
        blockers=blockers,
    )


__all__ = [
    "BRAKE_APPLICATION_RESPONSE_CONTRACTS",
    "BRAKE_RELEASE_RESPONSE_CONTRACTS",
    "BRAKE_THROTTLE_RESPONSE_CONTRACTS",
    "THROTTLE_APPLICATION_RESPONSE_CONTRACTS",
    "analyze_brake_throttle_dynamic_response",
]
