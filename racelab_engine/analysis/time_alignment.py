"""Physical-position lap alignment, phase detection, and lap-level time evidence.

The module deliberately keeps percentage bins as an index only.  Every output
describes the physical-position evidence used, retains honest gaps, and treats
laps (not telemetry rows) as the statistical experiment unit.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from numbers import Real
from statistics import median
from typing import Any, Literal

from racelab_engine.analysis.comparison import build_lap_grid, interpolate_run_to_grid

PhaseName = Literal[
    "straight", "lift", "brake_application", "threshold_braking", "brake_release",
    "turn_in", "entry", "center", "apex_region", "initial_throttle",
    "full_throttle_exit", "following_straight_carry", "transition", "bump_curb",
    "pit", "reset", "unknown",
]

_PHASE_CHANNELS = [
    "session_time", "lap_dist_ft", "speed_mps", "speed_mph", "throttle_pct",
    "brake_pct", "steering_deg", "yaw_rate", "lat_accel", "long_accel",
    "vert_accel", "vert_accel_g", "lat", "lon", "alt", "on_pit_road",
    "enter_exit_reset_state", "lf_shock_defl_in", "rf_shock_defl_in",
    "lr_shock_defl_in", "rr_shock_defl_in", "lf_shock_vel_in_s",
    "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
    "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in",
    "rr_ride_height_in", "cfs_ride_height_in",
]


@dataclass(frozen=True)
class PhaseInterval:
    phase: PhaseName
    start_pct: float
    end_pct: float
    confidence: float
    source_channels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AlignmentPoint:
    lap_pct: float
    aligned_test_pct: float | None
    confidence: float
    uncertainty_pct: float | None
    methods: list[str]
    is_gap: bool = False
    gap_reason: str | None = None


@dataclass(frozen=True)
class DriverEventCorrespondence:
    """A driver-demand or response event observed on the physical lap grid.

    These observations are deliberately separate from ``AlignmentPoint``.
    They retain useful event timing differences without granting brake,
    throttle, steering, or yaw any authority to translate track position.
    """

    event: str
    source_channel: str
    baseline_pct: float
    test_pct: float
    delta_pct: float
    threshold: float
    threshold_unit: str
    calculation_basis: str = "threshold_crossing_on_physical_position_grid"
    is_physical_alignment_authority: bool = False


@dataclass(frozen=True)
class PhaseTimeEffect:
    phase: str
    start_pct: float
    end_pct: float
    delta_s: float | None
    cumulative_delta_s: float | None
    alignment_confidence: float
    evidence_state: str
    source_channels: list[str]
    calculation_basis: str
    interpretation: str


@dataclass(frozen=True)
class NoiseEstimate:
    experiment_unit: str = "eligible_lap"
    baseline_laps: int = 0
    test_laps: int = 0
    paired_lap_differences: int = 0
    median_effect_s: float | None = None
    trimmed_mean_effect_s: float | None = None
    bootstrap_low_s: float | None = None
    bootstrap_high_s: float | None = None
    contradiction_score: float | None = None
    aba_consistency: str = "not_available_without_restored_baseline"
    is_repeatable: bool | None = None
    context_complete: bool = False
    context_blockers: list[str] = field(default_factory=list)
    context_key: dict[str, Any] = field(default_factory=dict)
    phase_estimates: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TimeAlignmentResult:
    grid_pct: list[float]
    phase_by_position: list[str | None]
    phases: list[PhaseInterval]
    alignment: list[AlignmentPoint]
    cumulative_delta_s: list[float | None]
    incremental_delta_s: list[float | None]
    incremental_basis: list[str | None]
    baseline_elapsed_s: list[float | None]
    test_elapsed_s: list[float | None]
    phase_effects: list[PhaseTimeEffect]
    phase_attribution: dict[str, float | None]
    gain_origin_pct: float | None
    gain_origin_phase: str | None
    surrender_pct: float | None
    gain_persistence_pct: float | None
    selected_effect_s: float | None
    time_delta_complete: bool
    theoretical_opportunity_s: float | None
    repeatable_opportunity_s: float | None
    noise: NoiseEstimate
    coverage_fraction: float
    local_alignment_confidence: float
    distance_basis: str
    warnings: list[str]
    source_channels: list[str]
    driver_event_correspondence: list[DriverEventCorrespondence] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _median_window(values: list[float | None], radius: int = 2) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        window = [v for v in values[max(0, index - radius):index + radius + 1] if v is not None]
        result.append(median(window) if window else None)
    return result


def _derivative(values: list[float | None], grid: list[float]) -> list[float | None]:
    result: list[float | None] = [None]
    for index in range(1, len(values)):
        left, right = values[index - 1], values[index]
        step = grid[index] - grid[index - 1]
        result.append((right - left) / step if left is not None and right is not None and step > 0 else None)
    return result


def _truthy(value: float | None) -> bool:
    return value is not None and value > 0.5


def nearest_sorted_index(values: list[float], target: float) -> int:
    """Return the closest index in a non-empty sorted sequence.

    Ties resolve to the lower track position.  Using binary search keeps
    position-grid lookups logarithmic instead of scanning the whole lap.
    """
    right = bisect_left(values, target)
    if right <= 0:
        return 0
    if right >= len(values):
        return len(values) - 1
    left = right - 1
    return left if target - values[left] <= values[right] - target else right


def _categorical_state_grid(
    rows: list[dict[str, Any]],
    channel: str,
    grid: list[float],
) -> list[bool | None]:
    samples: list[tuple[float, bool]] = []
    for row in rows:
        pct = _finite(row.get("lap_dist_pct_100"))
        value = row.get(channel)
        if pct is None or value is None:
            continue
        samples.append((pct, bool(value)))
    if not samples:
        return [None] * len(grid)
    samples.sort(key=lambda sample: sample[0])
    positions = [sample[0] for sample in samples]
    states = [sample[1] for sample in samples]
    result: list[bool | None] = []
    for pct in grid:
        index = nearest_sorted_index(positions, pct)
        result.append(states[index] if abs(positions[index] - pct) <= 2.0 else None)
    return result


def _confirmed_reset_positions(rows: list[dict[str, Any]]) -> list[float]:
    """Require reset action state plus a physical-position discontinuity."""
    confirmed: list[float] = []
    for previous, current in pairwise(rows):
        previous_pct = _finite(previous.get("lap_dist_pct_100"))
        current_pct = _finite(current.get("lap_dist_pct_100"))
        previous_state = _finite(previous.get("enter_exit_reset_state"))
        current_state = _finite(current.get("enter_exit_reset_state"))
        action_state = previous_state == 2.0 or current_state == 2.0
        if (
            action_state
            and previous_pct is not None
            and current_pct is not None
            and current_pct < previous_pct - 5.0
        ):
            confirmed.append(current_pct)
    return confirmed


def detect_engineering_phases(
    rows: list[dict[str, Any]],
    *,
    grid: list[float] | None = None,
    _interpolated_channels: dict[str, list[float | None]] | None = None,
) -> tuple[list[str | None], list[PhaseInterval], dict[str, list[float | None]]]:
    """Classify sustained operating phases on a physical-position grid."""
    position_grid = grid or build_lap_grid(0.0, 100.0, 0.1)
    channels = (
        _interpolated_channels
        if _interpolated_channels is not None
        else interpolate_run_to_grid(rows, _PHASE_CHANNELS, position_grid)
    )
    pit_state = _categorical_state_grid(rows, "on_pit_road", position_grid)
    confirmed_reset_pcts = _confirmed_reset_positions(rows)
    throttle = _median_window(channels["throttle_pct"])
    brake = _median_window(channels["brake_pct"])
    steering = _median_window(channels["steering_deg"])
    yaw = _median_window(channels["yaw_rate"])
    lateral = _median_window(channels["lat_accel"])
    vertical = _median_window(
        [
            g if g is not None else (v / 9.80665 if v is not None else None)
            for g, v in zip(channels["vert_accel_g"], channels["vert_accel"])
        ]
    )
    throttle_rate = _derivative(throttle, position_grid)
    brake_rate = _derivative(brake, position_grid)
    steering_rate = _derivative(steering, position_grid)
    shock_activity: list[float | None] = []
    for index in range(len(position_grid)):
        values = [
            abs(channel[index])
            for name in (
                "lf_shock_vel_in_s", "rf_shock_vel_in_s",
                "lr_shock_vel_in_s", "rr_shock_vel_in_s",
            )
            if (channel := channels[name])[index] is not None
        ]
        shock_activity.append(median(values) if values else None)

    raw: list[str | None] = []
    for index in range(len(position_grid)):
        t = throttle[index]
        b = brake[index]
        st = abs(steering[index]) if steering[index] is not None else None
        yr = abs(yaw[index]) if yaw[index] is not None else None
        lat = abs(lateral[index]) if lateral[index] is not None else None
        cornering = bool((st is not None and st >= 3.0) or (yr is not None and yr >= 0.08) or (lat is not None and lat >= 2.0))
        bump = bool(
            (vertical[index] is not None and abs(vertical[index] - 1.0) >= 0.35)
            or (shock_activity[index] is not None and shock_activity[index] >= 8.0)
        )
        if pit_state[index] is True:
            phase: str | None = "pit"
        elif any(abs(position_grid[index] - pct) <= 0.3 for pct in confirmed_reset_pcts):
            phase = "reset"
        elif bump:
            phase = "bump_curb"
        elif b is not None and b >= 60.0:
            phase = "threshold_braking"
        elif b is not None and b >= 5.0 and (brake_rate[index] or 0.0) > 0.5:
            phase = "brake_application"
        elif b is not None and b >= 3.0 and (brake_rate[index] or 0.0) < -0.5:
            phase = "brake_release"
        elif cornering:
            if t is not None and t >= 98.0:
                phase = "full_throttle_exit"
            elif t is not None and 10.0 <= t < 98.0 and (throttle_rate[index] or 0.0) > 0.5:
                phase = "initial_throttle"
            elif (steering_rate[index] or 0.0) * (steering[index] or 0.0) > 0.5:
                phase = "turn_in"
            else:
                phase = "center"
        elif t is not None and t < 10.0 and (b is None or b < 3.0):
            phase = "lift"
        elif t is not None and t >= 98.0:
            phase = "straight"
        elif t is not None:
            phase = "transition"
        else:
            phase = "unknown"
        raw.append(phase)

    # Re-label the sustained center of each corner and its minimum-speed region.
    speed = _median_window([
        mph / 2.2369362920544 if mph is not None else mps
        for mps, mph in zip(channels["speed_mps"], channels["speed_mph"])
    ])
    phase_values = list(raw)
    corner_indices = [i for i, phase in enumerate(raw) if phase in {"turn_in", "center", "initial_throttle", "full_throttle_exit"}]
    groups: list[list[int]] = []
    for index in corner_indices:
        if not groups or index > groups[-1][-1] + 2:
            groups.append([index])
        else:
            groups[-1].append(index)
    for group in groups:
        available = [i for i in group if speed[i] is not None]
        if not available:
            continue
        apex = min(available, key=lambda i: speed[i] or math.inf)
        for index in group:
            if phase_values[index] in {"initial_throttle", "full_throttle_exit", "turn_in"}:
                continue
            if abs(index - apex) <= 2:
                phase_values[index] = "apex_region"
            elif index < apex:
                phase_values[index] = "entry"
            else:
                phase_values[index] = "center"

    # Suppress isolated classifications: a single bin may not define a phase.
    for index in range(1, len(phase_values) - 1):
        if (
            phase_values[index] not in {"pit", "reset"}
            and phase_values[index - 1] == phase_values[index + 1] != phase_values[index]
        ):
            phase_values[index] = phase_values[index - 1]

    carry_bins = max(1, round(5.0 / (position_grid[1] - position_grid[0]))) if len(position_grid) > 1 else 1
    for index, phase in enumerate(list(phase_values)):
        if phase != "full_throttle_exit":
            continue
        for candidate in range(index + 1, min(len(phase_values), index + carry_bins + 1)):
            if phase_values[candidate] != "straight":
                break
            phase_values[candidate] = "following_straight_carry"

    intervals: list[PhaseInterval] = []
    start = 0
    for index in range(1, len(phase_values) + 1):
        if index < len(phase_values) and phase_values[index] == phase_values[start]:
            continue
        phase = phase_values[start] or "unknown"
        source = [name for name in _PHASE_CHANNELS if any(v is not None for v in channels[name][start:index])]
        confidence = min(1.0, 0.35 + 0.1 * min(6, len(source)))
        intervals.append(PhaseInterval(
            phase=phase,  # type: ignore[arg-type]
            start_pct=position_grid[start],
            end_pct=position_grid[index - 1],
            confidence=round(confidence, 3),
            source_channels=source,
        ))
        start = index
    return phase_values, intervals, channels


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _normalized_difference(left: float | None, right: float | None, scale: float) -> float | None:
    return min(3.0, abs(left - right) / scale) if left is not None and right is not None else None


def _has_signal_variation(values: list[float | None], minimum_range: float) -> bool:
    finite = [value for value in values if value is not None]
    return bool(finite) and max(finite) - min(finite) >= minimum_range


def _has_local_signal_variation(
    values: list[float | None],
    index: int,
    radius: int,
    minimum_range: float,
) -> bool:
    return _has_signal_variation(values[max(0, index - radius):index + radius + 1], minimum_range)


_DRIVER_EVENT_SPECS = (
    ("brake_application", "brake_pct", 5.0, "rising", False, "%"),
    ("brake_release", "brake_pct", 5.0, "falling", False, "%"),
    ("throttle_application", "throttle_pct", 10.0, "rising", False, "%"),
    ("throttle_release", "throttle_pct", 10.0, "falling", False, "%"),
    ("steering_application", "steering_deg", 2.0, "rising", True, "deg"),
    ("yaw_response_onset", "yaw_rate", 0.02, "rising", True, "rad/s"),
)


def _threshold_crossing_positions(
    values: list[float | None],
    grid: list[float],
    *,
    threshold: float,
    direction: str,
    use_absolute_value: bool,
) -> list[float]:
    positions: list[float] = []
    for index in range(1, len(grid)):
        previous = values[index - 1]
        current = values[index]
        if previous is None or current is None:
            continue
        left = abs(previous) if use_absolute_value else previous
        right = abs(current) if use_absolute_value else current
        crossed = (
            left < threshold <= right
            if direction == "rising"
            else left >= threshold > right
        )
        if not crossed or right == left:
            continue
        fraction = (threshold - left) / (right - left)
        pct = grid[index - 1] + fraction * (grid[index] - grid[index - 1])
        if math.isfinite(pct):
            positions.append(round(pct, 6))
    return positions


def build_driver_event_correspondence(
    baseline: dict[str, list[float | None]],
    test: dict[str, list[float | None]],
    grid: list[float],
) -> list[DriverEventCorrespondence]:
    """Retain event-position differences without changing physical alignment.

    Events are paired only when both laps expose the same ordered event count.
    Ambiguous or missing transitions remain absent instead of being forced into
    a correspondence.
    """
    observations: list[DriverEventCorrespondence] = []
    for event, channel, threshold, direction, use_absolute, unit in _DRIVER_EVENT_SPECS:
        baseline_positions = _threshold_crossing_positions(
            baseline.get(channel, [None] * len(grid)),
            grid,
            threshold=threshold,
            direction=direction,
            use_absolute_value=use_absolute,
        )
        test_positions = _threshold_crossing_positions(
            test.get(channel, [None] * len(grid)),
            grid,
            threshold=threshold,
            direction=direction,
            use_absolute_value=use_absolute,
        )
        if not baseline_positions or len(baseline_positions) != len(test_positions):
            continue
        observations.extend(
            DriverEventCorrespondence(
                event=event,
                source_channel=channel,
                baseline_pct=baseline_pct,
                test_pct=test_pct,
                delta_pct=round(test_pct - baseline_pct, 6),
                threshold=threshold,
                threshold_unit=unit,
            )
            for baseline_pct, test_pct in zip(baseline_positions, test_positions)
        )
    return observations


_MAX_CIRCULAR_BOUNDARY_GAP_PCT = 2.0
_BOUNDARY_SPACING_MULTIPLIER = 3.0
_MIN_BOUNDARY_SAMPLES = 8


def _channel_boundary_samples(
    rows: list[dict[str, Any]],
    channel: str,
) -> tuple[list[float], list[float]]:
    grouped: dict[float, list[float]] = {}
    for row in rows:
        pct = _finite(row.get("lap_dist_pct_100"))
        value = _finite(row.get(channel))
        if pct is None or value is None or not 0.0 <= pct <= 100.0:
            continue
        grouped.setdefault(pct, []).append(value)
    positions = sorted(grouped)
    return positions, [median(grouped[position]) for position in positions]


def _admit_bounded_circular_boundary(
    rows: list[dict[str, Any]],
    channels: dict[str, list[float | None]],
    grid: list[float],
) -> set[int]:
    """Fill only a sampling-sized start/finish omission on a full-lap grid.

    The admissible width comes from each channel's observed position spacing and
    is capped at two percent of a lap. Interior gaps are never touched.
    """
    if not grid or min(grid) > 1e-9 or max(grid) < 100.0 - 1e-9:
        return set()
    timing_boundary_indices: set[int] = set()
    for channel, values in channels.items():
        if channel in {"on_pit_road", "enter_exit_reset_state"}:
            continue
        positions, samples = _channel_boundary_samples(rows, channel)
        if len(positions) < _MIN_BOUNDARY_SAMPLES:
            continue
        spacings = [right - left for left, right in pairwise(positions) if right > left]
        if not spacings:
            continue
        observed_spacing = median(spacings)
        allowed_gap = min(
            _MAX_CIRCULAR_BOUNDARY_GAP_PCT,
            _BOUNDARY_SPACING_MULTIPLIER * observed_spacing,
        )
        circular_gap = positions[0] + (100.0 - positions[-1])
        if allowed_gap <= 0.0 or circular_gap <= 0.0 or circular_gap > allowed_gap + 1e-9:
            continue
        if channel in {"session_time", "lap_dist_ft"} and (
            positions[1] - positions[0] > allowed_gap + 1e-9
            or positions[-1] - positions[-2] > allowed_gap + 1e-9
        ):
            continue

        admitted: set[int] = set()
        for index, pct in enumerate(grid):
            if values[index] is not None or positions[0] <= pct <= positions[-1]:
                continue
            if pct < positions[0]:
                if positions[0] - pct > allowed_gap + 1e-9:
                    continue
                if channel == "lap_dist_pct_100":
                    estimate = pct
                elif channel in {"session_time", "lap_dist_ft"}:
                    span = positions[1] - positions[0]
                    estimate = samples[0] + (pct - positions[0]) * (samples[1] - samples[0]) / span
                else:
                    wrapped_pct = pct + 100.0
                    estimate = samples[-1] + (
                        (wrapped_pct - positions[-1]) / circular_gap
                    ) * (samples[0] - samples[-1])
            else:
                if pct - positions[-1] > allowed_gap + 1e-9:
                    continue
                if channel == "lap_dist_pct_100":
                    estimate = pct
                elif channel in {"session_time", "lap_dist_ft"}:
                    span = positions[-1] - positions[-2]
                    estimate = samples[-1] + (pct - positions[-1]) * (
                        samples[-1] - samples[-2]
                    ) / span
                else:
                    estimate = samples[-1] + (
                        (pct - positions[-1]) / circular_gap
                    ) * (samples[0] - samples[-1])
            if math.isfinite(estimate):
                values[index] = estimate
                admitted.add(index)
        if channel == "session_time":
            timing_boundary_indices.update(admitted)
    return timing_boundary_indices


def _context_missing(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, dict):
        return not value or any(_context_missing(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return not value or any(item is None for item in value)
    return False


_CONTEXT_RANGE_LIMITS: dict[str, tuple[float, float]] = {
    # These deliberately broad physical limits reject corrupt context without
    # constraining a plausible tire stint or vehicle fuel capacity.
    "baseline_tire_age_range_m": (0.0, 10_000_000.0),
    "test_tire_age_range_m": (0.0, 10_000_000.0),
    "baseline_fuel_range": (0.0, 1_000.0),
    "test_fuel_range": (0.0, 1_000.0),
}
_WEATHER_RANGE_LIMITS: dict[str, tuple[float, float]] = {
    "air_temp": (-100.0, 100.0),
    "track_temp": (-100.0, 200.0),
    "wind_vel": (0.0, 200.0),
}


def _validated_context_range(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> tuple[float, float] | None:
    """Return one ordered finite numeric context range, or fail closed."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if any(isinstance(item, bool) or not isinstance(item, Real) for item in value):
        return None
    try:
        lower, upper = float(value[0]), float(value[1])
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(lower) or not math.isfinite(upper):
        return None
    if lower > upper or lower < minimum or upper > maximum:
        return None
    return lower, upper


def _validated_weather_ranges(value: Any) -> dict[str, tuple[float, float]] | None:
    if not isinstance(value, dict):
        return None
    ranges: dict[str, tuple[float, float]] = {}
    for channel, (minimum, maximum) in _WEATHER_RANGE_LIMITS.items():
        validated = _validated_context_range(
            value.get(channel),
            minimum=minimum,
            maximum=maximum,
        )
        if validated is None:
            return None
        ranges[channel] = validated
    return ranges


def _noise_context_blockers(context: dict[str, Any]) -> list[str]:
    required = {
        "baseline_driver_identity": "baseline driver identity",
        "test_driver_identity": "test driver identity",
        "car": "car identity",
        "car_version": "car version",
        "track": "track identity",
        "track_configuration": "track configuration",
        "track_version": "track version",
        "baseline_setup_fingerprint": "baseline setup",
        "test_setup_fingerprint": "test setup",
        "baseline_tire_age_range_m": "baseline tire age",
        "test_tire_age_range_m": "test tire age",
        "baseline_fuel_range": "baseline fuel range",
        "test_fuel_range": "test fuel range",
        "baseline_weather_range": "baseline weather range",
        "test_weather_range": "test weather range",
        "run_type": "run type",
        "phase": "phase scope",
        "controlled_setup_change_count": "controlled setup change count",
        "unmapped_setup_changes": "unmapped setup-change status",
    }
    blockers: list[str] = []
    validated_ranges: dict[str, tuple[float, float]] = {}
    validated_weather: dict[str, dict[str, tuple[float, float]]] = {}
    for key, label in required.items():
        if key in _CONTEXT_RANGE_LIMITS:
            minimum, maximum = _CONTEXT_RANGE_LIMITS[key]
            validated = _validated_context_range(
                context.get(key),
                minimum=minimum,
                maximum=maximum,
            )
            if validated is None:
                blockers.append(label)
            else:
                validated_ranges[key] = validated
        elif key in {"baseline_weather_range", "test_weather_range"}:
            weather_ranges = _validated_weather_ranges(context.get(key))
            if weather_ranges is None:
                blockers.append(label)
            else:
                validated_weather[key] = weather_ranges
        elif _context_missing(context.get(key)):
            blockers.append(label)
    if (
        context.get("baseline_driver_identity") is not None
        and context.get("test_driver_identity") is not None
        and str(context.get("baseline_driver_identity")) != str(context.get("test_driver_identity"))
    ):
        blockers.append("same driver")
    controlled_change_count = context.get("controlled_setup_change_count")
    if (
        isinstance(controlled_change_count, bool)
        or not isinstance(controlled_change_count, int)
        or controlled_change_count != 1
    ):
        blockers.append("exactly one mapped setup change")
    if context.get("unmapped_setup_changes") is not False:
        blockers.append("no unmapped setup changes")

    for baseline_key, test_key, tolerance, label in (
        ("baseline_tire_age_range_m", "test_tire_age_range_m", 1_000.0, "matched tire age"),
        ("baseline_fuel_range", "test_fuel_range", 2.0, "matched fuel range"),
    ):
        baseline_range = validated_ranges.get(baseline_key)
        test_range = validated_ranges.get(test_key)
        if baseline_range is None or test_range is None:
            continue
        baseline_center = sum(baseline_range) / 2
        test_center = sum(test_range) / 2
        if abs(test_center - baseline_center) > tolerance:
            blockers.append(label)
    for key, maximum_span, label in (
        ("baseline_tire_age_range_m", 5_000.0, "narrow baseline tire-age range"),
        ("test_tire_age_range_m", 5_000.0, "narrow test tire-age range"),
        ("baseline_fuel_range", 10.0, "narrow baseline fuel range"),
        ("test_fuel_range", 10.0, "narrow test fuel range"),
    ):
        value = validated_ranges.get(key)
        if value is not None and value[1] - value[0] > maximum_span:
            blockers.append(label)
    baseline_weather = validated_weather.get("baseline_weather_range")
    test_weather = validated_weather.get("test_weather_range")
    if baseline_weather is not None and test_weather is not None:
        for channel, tolerance in (("air_temp", 5.0), ("track_temp", 5.0), ("wind_vel", 2.0)):
            baseline_value, test_value = baseline_weather[channel], test_weather[channel]
            baseline_center = sum(baseline_value) / 2
            test_center = sum(test_value) / 2
            if abs(test_center - baseline_center) > tolerance:
                blockers.append(f"matched {channel.replace('_', ' ')}")
            maximum_span = {"air_temp": 5.0, "track_temp": 8.0, "wind_vel": 3.0}[channel]
            if baseline_value[1] - baseline_value[0] > maximum_span:
                blockers.append(f"stable baseline {channel.replace('_', ' ')}")
            if test_value[1] - test_value[0] > maximum_span:
                blockers.append(f"stable test {channel.replace('_', ' ')}")
    return list(dict.fromkeys(blockers))


def build_layered_alignment(
    baseline_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    grid: list[float],
) -> tuple[list[AlignmentPoint], dict[str, list[float | None]], dict[str, list[float | None]]]:
    """Build monotonic local alignment using only physical-position evidence.

    Lap position is the immutable default. Only qualified GPS geometry or a
    repeatable road-profile landmark may move a test candidate away from that
    position. Driver demand and vehicle response remain available in the
    interpolated channel maps, but never participate in this physical score.
    """
    evidence_channels = list(dict.fromkeys([*_PHASE_CHANNELS, "lap_dist_pct_100"]))
    baseline = interpolate_run_to_grid(baseline_rows, evidence_channels, grid)
    test = interpolate_run_to_grid(test_rows, evidence_channels, grid)
    baseline_boundary_indices = _admit_bounded_circular_boundary(baseline_rows, baseline, grid)
    test_boundary_indices = _admit_bounded_circular_boundary(test_rows, test, grid)
    gps_available = all(
        _has_signal_variation(run[name], 1e-7)
        for run in (baseline, test)
        for name in ("lat", "lon")
    )
    road_thresholds = {
        "vert_accel": 0.5,
        "lf_shock_defl_in": 0.02,
        "rf_shock_defl_in": 0.02,
        "lr_shock_defl_in": 0.02,
        "rr_shock_defl_in": 0.02,
    }
    road_available = {
        name: all(_has_signal_variation(run[name], threshold) for run in (baseline, test))
        for name, threshold in road_thresholds.items()
    }
    step = grid[1] - grid[0] if len(grid) > 1 else 0.1
    radius = max(1, round(0.5 / step))
    points: list[AlignmentPoint] = []
    last_index = -1
    reuse_count = 0
    for index, pct in enumerate(grid):
        # Primary timing-boundary alignment is always the candidate center.  Extra
        # layers can refine locally but may never create coverage outside the lap.
        candidates: list[tuple[float, int, list[str]]] = []
        for candidate in range(max(0, index - radius), min(len(grid), index + radius + 1)):
            costs: list[float] = []
            methods = ["lap_percentage"]
            bl_lat, bl_lon = baseline["lat"][index], baseline["lon"][index]
            te_lat, te_lon = test["lat"][candidate], test["lon"][candidate]
            local_gps = all(
                any(_has_local_signal_variation(run[name], position, radius, 1e-8) for name in ("lat", "lon"))
                for run, position in ((baseline, index), (test, candidate))
            )
            if gps_available and local_gps and None not in (bl_lat, bl_lon, te_lat, te_lon):
                costs.append(min(3.0, _haversine_m(bl_lat, bl_lon, te_lat, te_lon) / 3.0))  # type: ignore[arg-type]
                methods.append("gps_geometry")
            track_distance = _normalized_difference(
                baseline["lap_dist_ft"][index],
                test["lap_dist_ft"][candidate],
                50.0,
            )
            if track_distance is not None:
                costs.append(track_distance)
                methods.append("track_distance_geometry")
            road_costs: list[float] = []
            baseline_vertical = baseline["vert_accel"][index]
            test_vertical = test["vert_accel"][candidate]
            repeatable_vertical_landmark = (
                road_available["vert_accel"]
                and baseline_vertical is not None
                and test_vertical is not None
                and abs(baseline_vertical - 9.80665) >= 2.0
                and abs(test_vertical - 9.80665) >= 2.0
                and _has_local_signal_variation(baseline["vert_accel"], index, radius, 1.0)
                and _has_local_signal_variation(test["vert_accel"], candidate, radius, 1.0)
            )
            if repeatable_vertical_landmark:
                vertical_cost = _normalized_difference(baseline_vertical, test_vertical, 3.0)
                if vertical_cost is not None:
                    road_costs.append(vertical_cost)
                road_costs.extend(
                    value
                    for name in (
                        "lf_shock_defl_in",
                        "rf_shock_defl_in",
                        "lr_shock_defl_in",
                        "rr_shock_defl_in",
                    )
                    if road_available[name]
                    and _has_local_signal_variation(
                        baseline[name], index, radius, road_thresholds[name] / 2,
                    )
                    and _has_local_signal_variation(
                        test[name], candidate, radius, road_thresholds[name] / 2,
                    )
                    and (
                        value := _normalized_difference(
                            baseline[name][index], test[name][candidate], 0.15,
                        )
                    ) is not None
                )
            if road_costs:
                costs.append(median(road_costs))
                methods.append("road_profile")
                if repeatable_vertical_landmark:
                    methods.append("repeatable_bump_anchor")
            if candidate != index and not {"gps_geometry", "road_profile"}.intersection(methods):
                continue
            primary_penalty = abs(candidate - index) * step / 0.5
            score = (sum(costs) / len(costs) if costs else 0.0) + 0.35 * primary_penalty
            candidates.append((score, candidate, methods))
        candidates.sort(key=lambda item: item[0])
        score, candidate, methods = next(
            (
                item
                for item in candidates
                if item[1] >= last_index
                and not (item[1] == last_index and reuse_count >= 1)
            ),
            (math.inf, -1, ["lap_percentage"]),
        )
        required = (baseline["session_time"][index], test["session_time"][candidate] if candidate >= 0 else None)
        if candidate < 0 or any(value is None for value in required):
            points.append(AlignmentPoint(pct, None, 0.0, None, methods, True, "No paired timing coverage at this physical position."))
            continue
        if candidate == last_index:
            reuse_count += 1
        else:
            last_index = candidate
            reuse_count = 0
        boundary_admitted = index in baseline_boundary_indices or candidate in test_boundary_indices
        if boundary_admitted:
            methods.append("bounded_circular_boundary")
        layer_count = len(set(methods) - {"lap_percentage", "bounded_circular_boundary"})
        confidence = max(0.2, min(1.0, 0.55 + layer_count * 0.125 - min(score, 3.0) * 0.12))
        if boundary_admitted:
            confidence = min(confidence, 0.7)
        uncertainty = step * (1.0 + max(0.0, score) + 0.5 * reuse_count) / max(confidence, 0.1)
        points.append(AlignmentPoint(
            lap_pct=pct,
            aligned_test_pct=grid[candidate],
            confidence=round(confidence, 3),
            uncertainty_pct=round(uncertainty, 4),
            methods=list(dict.fromkeys(methods)),
        ))
    return points, baseline, test


def _elapsed(values: list[float | None]) -> list[float | None]:
    origin = next((value for value in values if value is not None), None)
    return [value - origin if value is not None and origin is not None else None for value in values]


def _trimmed_mean(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    cut = int(len(ordered) * 0.1) if len(ordered) >= 10 else 0
    kept = ordered[cut:len(ordered) - cut] if cut else ordered
    return sum(kept) / len(kept)


def _bootstrap_interval(values: list[float], repetitions: int = 800) -> tuple[float | None, float | None]:
    """Deterministic lap-level bootstrap (LCG avoids a global RNG side effect)."""
    if len(values) < 3:
        return None, None
    state = 0xC0FFEE
    estimates: list[float] = []
    for _ in range(repetitions):
        sample: list[float] = []
        for _index in range(len(values)):
            state = (1_664_525 * state + 1_013_904_223) & 0xFFFFFFFF
            sample.append(values[state % len(values)])
        estimates.append(median(sample))
    estimates.sort()
    return estimates[int(0.025 * (len(estimates) - 1))], estimates[int(0.975 * (len(estimates) - 1))]


def _robust_sigma(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    center = median(values)
    mad = median(abs(value - center) for value in values)
    return 1.4826 * mad if mad > 0 else (max(values) - min(values)) / 1.349


def extract_phase_times(
    rows: list[dict[str, Any]],
    grid: list[float],
    phase_by_position: list[str | None],
) -> dict[str, float]:
    """Return phase durations for one lap; each lap remains one experiment."""
    times = interpolate_run_to_grid(rows, ["session_time"], grid)["session_time"]
    result: dict[str, float] = {}
    coverage: dict[str, int] = {}
    expected: dict[str, int] = {}
    for index in range(1, len(grid)):
        phase = phase_by_position[index]
        if phase is None:
            continue
        expected[phase] = expected.get(phase, 0) + 1
        left, right = times[index - 1], times[index]
        if left is None or right is None or right <= left:
            continue
        result[phase] = result.get(phase, 0.0) + right - left
        coverage[phase] = coverage.get(phase, 0) + 1
    return {
        phase: round(value, 7)
        for phase, value in result.items()
        if coverage.get(phase, 0) >= math.ceil(0.9 * expected.get(phase, 1))
    }


def estimate_driver_noise(
    baseline_lap_times_s: list[float],
    test_lap_times_s: list[float],
    *,
    baseline_phase_times: list[dict[str, float]] | None = None,
    test_phase_times: list[dict[str, float]] | None = None,
    context_key: dict[str, Any] | None = None,
) -> NoiseEstimate:
    """Estimate repeatability from paired eligible laps; rows are never experiments."""
    baseline = [v for value in baseline_lap_times_s if (v := _finite(value)) is not None]
    test = [v for value in test_lap_times_s if (v := _finite(value)) is not None]
    count = min(len(baseline), len(test))
    effects = [test[index] - baseline[index] for index in range(count)]
    warnings: list[str] = []
    if count < 3:
        warnings.append("Need at least three paired eligible laps for a repeatability interval.")
    if len(baseline) != len(test):
        warnings.append(f"Balanced comparison to the first {count} eligible laps in each run.")
    center = median(effects) if effects else None
    low, high = _bootstrap_interval(effects)
    contradiction = None
    if center is not None and effects:
        if abs(center) <= 1e-9:
            contradiction = sum(abs(value) > 0.05 for value in effects) / len(effects)
        else:
            contradiction = sum(value * center < 0 for value in effects) / len(effects)
    resolved_context = dict(context_key or {})
    context_blockers = _noise_context_blockers(resolved_context)
    context_complete = not context_blockers
    statistical_repeatable = None if low is None or high is None else (low > 0 or high < 0)
    repeatable = statistical_repeatable if context_complete else None
    phase_estimates: dict[str, dict[str, Any]] = {}
    baseline_phase_times = baseline_phase_times or []
    test_phase_times = test_phase_times or []
    phase_names = sorted({phase for lap in [*baseline_phase_times, *test_phase_times] for phase in lap})
    for phase in phase_names:
        baseline_values = [lap[phase] for lap in baseline_phase_times if phase in lap]
        test_values = [lap[phase] for lap in test_phase_times if phase in lap]
        paired_count = min(len(baseline_values), len(test_values))
        paired_effects = [test_values[index] - baseline_values[index] for index in range(paired_count)]
        phase_low, phase_high = _bootstrap_interval(paired_effects)
        empirical_noise = 1.96 * math.sqrt(
            _robust_sigma(baseline_values) ** 2 + _robust_sigma(test_values) ** 2
        )
        phase_center = median(paired_effects) if paired_effects else None
        phase_statistical_repeatable = (
            None
            if phase_low is None or phase_high is None or phase_center is None
            else (phase_low > 0 or phase_high < 0) and abs(phase_center) > max(0.01, empirical_noise)
        )
        phase_repeatable = phase_statistical_repeatable if context_complete else None
        phase_estimates[phase] = {
            "experiment_unit": "eligible_lap",
            "baseline_laps": len(baseline_values),
            "test_laps": len(test_values),
            "paired_lap_differences": paired_count,
            "median_effect_s": round(phase_center, 6) if phase_center is not None else None,
            "empirical_noise_band_s": round(empirical_noise, 6),
            "bootstrap_low_s": round(phase_low, 6) if phase_low is not None else None,
            "bootstrap_high_s": round(phase_high, 6) if phase_high is not None else None,
            "is_repeatable": phase_repeatable,
        }
    if context_blockers:
        warnings.append(
            "Repeatability is blocked until context is complete: "
            + ", ".join(context_blockers)
            + "."
        )
    return NoiseEstimate(
        baseline_laps=len(baseline),
        test_laps=len(test),
        paired_lap_differences=count,
        median_effect_s=round(center, 6) if center is not None else None,
        trimmed_mean_effect_s=round(_trimmed_mean(effects), 6) if effects else None,
        bootstrap_low_s=round(low, 6) if low is not None else None,
        bootstrap_high_s=round(high, 6) if high is not None else None,
        contradiction_score=round(contradiction, 3) if contradiction is not None else None,
        is_repeatable=repeatable,
        context_complete=context_complete,
        context_blockers=context_blockers,
        context_key=resolved_context,
        phase_estimates=phase_estimates,
        warnings=warnings,
    )


def analyze_time_alignment(
    baseline_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    *,
    baseline_lap_times_s: list[float] | None = None,
    test_lap_times_s: list[float] | None = None,
    baseline_lap_rows: list[list[dict[str, Any]]] | None = None,
    test_lap_rows: list[list[dict[str, Any]]] | None = None,
    noise_context_key: dict[str, Any] | None = None,
    start_pct: float = 0.0,
    end_pct: float = 100.0,
    step_pct: float = 0.1,
) -> TimeAlignmentResult:
    grid = build_lap_grid(start_pct, end_pct, step_pct)
    alignment, baseline, test = build_layered_alignment(baseline_rows, test_rows, grid)
    driver_event_correspondence = build_driver_event_correspondence(baseline, test, grid)
    phase_by_position, phases, _phase_channels = detect_engineering_phases(
        baseline_rows,
        grid=grid,
        _interpolated_channels=baseline,
    )
    baseline_elapsed = _elapsed(baseline["session_time"])
    test_time = test["session_time"]
    aligned_test_time: list[float | None] = []
    for point in alignment:
        if point.aligned_test_pct is None:
            aligned_test_time.append(None)
            continue
        index = nearest_sorted_index(grid, point.aligned_test_pct)
        aligned_test_time.append(test_time[index])
    test_elapsed = _elapsed(aligned_test_time)

    baseline_dist = baseline["lap_dist_ft"]
    speed_baseline = [
        mph / 2.2369362920544 if mph is not None else mps
        for mps, mph in zip(baseline["speed_mps"], baseline["speed_mph"])
    ]
    speed_test = [
        mph / 2.2369362920544 if mph is not None else mps
        for mps, mph in zip(test["speed_mps"], test["speed_mph"])
    ]
    use_distance = sum(value is not None for value in baseline_dist) >= 0.9 * len(grid)
    cumulative: list[float | None] = [0.0 if alignment and not alignment[0].is_gap else None]
    incremental: list[float | None] = [0.0 if cumulative[0] is not None else None]
    incremental_basis: list[str | None] = [None]
    running = 0.0
    for index in range(1, len(grid)):
        point = alignment[index]
        previous = alignment[index - 1]
        if point.is_gap or previous.is_gap:
            incremental.append(None)
            incremental_basis.append(None)
            cumulative.append(None)
            continue
        delta: float | None = None
        basis: str | None = None
        if use_distance:
            left, right = baseline_dist[index - 1], baseline_dist[index]
            vb = speed_baseline[index]
            aligned_pct = point.aligned_test_pct
            test_index = nearest_sorted_index(grid, aligned_pct)  # type: ignore[arg-type]
            vt = speed_test[test_index]
            if None not in (left, right, vb, vt) and right > left and vb > 1.0 and vt > 1.0:  # type: ignore[operator]
                distance_m = (right - left) / 3.280839895  # type: ignore[operator]
                delta = distance_m * (1.0 / vt - 1.0 / vb)  # type: ignore[operator]
                basis = "reciprocal_speed_integration"
        if delta is None and None not in (
            baseline_elapsed[index - 1], baseline_elapsed[index], test_elapsed[index - 1], test_elapsed[index],
        ):
            delta = (test_elapsed[index] - test_elapsed[index - 1]) - (baseline_elapsed[index] - baseline_elapsed[index - 1])  # type: ignore[operator]
            basis = "aligned_timing_boundaries"
        if delta is None:
            incremental.append(None)
            incremental_basis.append(None)
            cumulative.append(None)
            continue
        running += delta
        incremental.append(round(delta, 7))
        incremental_basis.append(basis)
        cumulative.append(round(running, 6))

    used_bases = {basis for basis in incremental_basis if basis is not None}
    distance_basis = (
        next(iter(used_bases))
        if len(used_bases) == 1
        else "mixed"
        if used_bases
        else "unavailable"
    )

    effects: list[PhaseTimeEffect] = []
    for interval in phases:
        indices = [i for i, pct in enumerate(grid) if interval.start_pct <= pct <= interval.end_pct]
        values = [incremental[i] for i in indices if incremental[i] is not None]
        confidence_values = [alignment[i].confidence for i in indices if not alignment[i].is_gap]
        interval_bases = {incremental_basis[i] for i in indices if incremental_basis[i] is not None}
        delta = sum(values) if values and len(values) >= max(1, math.ceil(0.8 * len(indices))) else None
        end_value = next((cumulative[i] for i in reversed(indices) if cumulative[i] is not None), None)
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        effects.append(PhaseTimeEffect(
            phase=interval.phase,
            start_pct=interval.start_pct,
            end_pct=interval.end_pct,
            delta_s=round(delta, 6) if delta is not None else None,
            cumulative_delta_s=end_value,
            alignment_confidence=round(confidence, 3),
            evidence_state="calculated" if delta is not None else "unavailable",
            source_channels=list(dict.fromkeys([
                *(["lap_dist_ft", "speed_mps", "speed_mph"] if "reciprocal_speed_integration" in interval_bases else []),
                *(["session_time"] if "aligned_timing_boundaries" in interval_bases else []),
                *interval.source_channels,
            ])),
            calculation_basis=(
                next(iter(interval_bases))
                if len(interval_bases) == 1
                else "mixed"
                if interval_bases
                else "unavailable"
            ),
            interpretation=(
                f"Time change is localized to {interval.phase.replace('_', ' ')}; "
                "evaluate symptoms only against telemetry from this phase."
            ),
        ))

    def _phase_sum(names: set[str]) -> float | None:
        values = [effect.delta_s for effect in effects if effect.phase in names and effect.delta_s is not None]
        return round(sum(values), 6) if values else None

    phase_attribution = {
        "entry_delta_s": _phase_sum({"brake_application", "threshold_braking", "brake_release", "turn_in", "entry"}),
        "center_delta_s": _phase_sum({"center", "apex_region"}),
        "exit_delta_s": _phase_sum({"initial_throttle", "full_throttle_exit"}),
        "following_straight_carry_delta_s": _phase_sum({"following_straight_carry"}),
    }

    baseline_phase_times = [
        extract_phase_times(rows, grid, phase_by_position)
        for rows in (baseline_lap_rows or [])
    ]
    test_phase_times = [
        extract_phase_times(rows, grid, phase_by_position)
        for rows in (test_lap_rows or [])
    ]
    noise = estimate_driver_noise(
        baseline_lap_times_s or [],
        test_lap_times_s or [],
        baseline_phase_times=baseline_phase_times,
        test_phase_times=test_phase_times,
        context_key=noise_context_key,
    )
    noise_threshold = max(0.02, abs(noise.bootstrap_high_s - noise.bootstrap_low_s) / 2) if None not in (noise.bootstrap_low_s, noise.bootstrap_high_s) else 0.05
    meaningful = [(i, value) for i, value in enumerate(cumulative) if value is not None and value < -noise_threshold]
    origin_index = meaningful[0][0] if meaningful else None
    time_delta_complete = bool(alignment) and all(not point.is_gap for point in alignment)
    selected = next((value for value in reversed(cumulative) if value is not None), None) if time_delta_complete else None
    surrender_index: int | None = None
    persistence: float | None = None
    if selected is not None and selected < -noise_threshold:
        best_index, best_gain = min(((i, v) for i, v in enumerate(cumulative) if v is not None), key=lambda item: item[1])
        surrender_index = next((i for i in range(best_index + 1, len(cumulative)) if cumulative[i] is not None and cumulative[i] > best_gain * 0.5), None)
        endpoint = surrender_index if surrender_index is not None else len(grid) - 1
        persistence = max(0.0, grid[endpoint] - grid[best_index])
    repeatable = (
        abs(noise.median_effect_s)
        if noise.is_repeatable
        and noise.median_effect_s is not None
        and noise.median_effect_s < 0
        and selected is not None
        and selected < -noise_threshold
        and start_pct <= 0.0
        and end_pct >= 100.0
        else None
    )
    theoretical = abs(selected) if selected is not None and selected < 0 else None
    coverage = sum(not point.is_gap for point in alignment) / len(alignment) if alignment else 0.0
    confidence_values = [point.confidence for point in alignment if not point.is_gap]
    methods = sorted({method for point in alignment for method in point.methods})
    warnings = list(noise.warnings)
    if coverage < 0.9:
        warnings.append(f"Paired local alignment coverage is {coverage:.0%}; missing positions remain gaps.")
    if methods == ["lap_percentage"]:
        warnings.append("Geometry, curvature, and road-profile layers are unavailable; alignment uses timing boundaries only.")
    return TimeAlignmentResult(
        grid_pct=grid,
        phase_by_position=phase_by_position,
        phases=phases,
        alignment=alignment,
        cumulative_delta_s=cumulative,
        incremental_delta_s=incremental,
        incremental_basis=incremental_basis,
        baseline_elapsed_s=baseline_elapsed,
        test_elapsed_s=test_elapsed,
        phase_effects=effects,
        phase_attribution=phase_attribution,
        gain_origin_pct=grid[origin_index] if origin_index is not None else None,
        gain_origin_phase=phase_by_position[origin_index] if origin_index is not None else None,
        surrender_pct=grid[surrender_index] if surrender_index is not None else None,
        gain_persistence_pct=round(persistence, 3) if persistence is not None else None,
        selected_effect_s=selected,
        time_delta_complete=time_delta_complete,
        theoretical_opportunity_s=round(theoretical, 6) if theoretical is not None else None,
        repeatable_opportunity_s=round(repeatable, 6) if repeatable is not None else None,
        noise=noise,
        coverage_fraction=round(coverage, 3),
        local_alignment_confidence=round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0.0,
        distance_basis=distance_basis,
        warnings=warnings,
        source_channels=methods,
        driver_event_correspondence=driver_event_correspondence,
    )
