"""Pure, clock-qualified surface-disturbance response analysis.

The detector finds a response event from vertical acceleration, then measures
four-corner shaft/travel, platform-proxy, and yaw response on the canonical
clock.  It never treats the inferred event as a measured road input and never
emits a damper or setup direction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from statistics import median
from typing import Any

import polars as pl

from racelab_engine.analysis.qualified_clock import build_qualified_telemetry_clock
from racelab_engine.models.engineering_awareness import (
    DerivedMetricContract,
    MetricProvenance,
)
from racelab_engine.models.evidence import (
    BlockerPhysicalScope,
    EngineeringBlocker,
    EngineeringBlockerSeverity,
    EngineeringBlockTarget,
    EvidenceState,
)
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.models.surface_disturbance_response import (
    CornerSettlingResponse,
    EmpiricalNoiseFloor,
    PhysicalLapScope,
    PlatformYawSettlingResponse,
    SurfaceDisturbanceEpisodeResult,
    SurfaceDisturbanceEpisodeSignature,
)


FORMULA_VERSION = "p35.4.surface-disturbance-settling.v1"
PRODUCER_ID = "p35.4.surface_disturbance_response"
_CORNERS = ("lf", "rf", "lr", "rr")
_MIN_SCOPE_SAMPLES = 16
_MIN_SAMPLE_COVERAGE = 0.90
_NUMERIC_EPSILON = 1e-12
_PRESENTATION_IDENTITY_KEYS = frozenset(
    {
        "run_id",
        "recording_id",
        "source_artifact_id",
        "source_file",
        "source_path",
    }
)
_VALID_PHASES = (
    "straight",
    "following_straight_carry",
    "lift",
    "brake_application",
    "threshold_braking",
    "brake_release",
    "turn_in",
    "entry",
    "center",
    "apex_region",
    "initial_throttle",
    "full_throttle_exit",
    "bump_curb",
    "transition",
)
_RESPONSE_CHANNELS = (
    "vert_accel",
    "yaw_rate",
    *(f"{corner}_shock_vel_in_s" for corner in _CORNERS),
    *(f"{corner}_shock_defl_in" for corner in _CORNERS),
)
_REQUIRED_CHANNELS = (
    "lap",
    "lap_dist_pct_100",
    "speed_mps",
    *_RESPONSE_CHANNELS,
)
_UNITS = {
    "vert_accel": "m/s^2",
    "yaw_rate": "rad/s",
    **{f"{corner}_shock_vel_in_s": "in/s" for corner in _CORNERS},
    **{f"{corner}_shock_defl_in": "in" for corner in _CORNERS},
}


SURFACE_DISTURBANCE_SETTLING_CONTRACT = DerivedMetricContract(
    metric_key="surface_disturbance_settling_response",
    formula_version=FORMULA_VERSION,
    label="Surface-disturbance shock/platform/yaw settling response",
    evidence_state=EvidenceState.OBSERVED_CORRELATION,
    required_channels=_REQUIRED_CHANNELS,
    preferred_channels=("brake_pct", "throttle_pct", "steering_deg"),
    allowed_channel_semantics=(ChannelUpdateSemantic.CONTINUOUS,),
    valid_phases=_VALID_PHASES,
    hard_blockers=(
        "ineligible_or_incomplete_physical_lap",
        "unqualified_canonical_clock",
        "missing_or_incomplete_yaw_or_four_corner_shocks",
        "insufficient_independent_physical_episodes",
        "unrepeated_physical_location",
    ),
    minimum_sample_coverage=_MIN_SAMPLE_COVERAGE,
    minimum_repetitions=2,
    allowed_outputs=(
        "disturbance_response_onset",
        "four_corner_velocity_and_travel_response",
        "observed_response_lag",
        "peak_and_overshoot",
        "settling_duration_or_right_censor",
        "correction_and_oscillation_count",
        "empirical_noise_floor",
        "speed_phase_and_context",
        "exact_provenance",
    ),
    forbidden_claims=(
        "measured_track_surface_input",
        "damper_force",
        "spring_force",
        "wheel_load",
        "damper_regime",
        "component_cause",
        "setup_direction",
        "setup_target",
    ),
    description=(
        "Repeated, physical-position-bound vehicle response to a disturbance-like "
        "vertical event. Track input is not directly measured; all outputs remain "
        "observation-only and use no nominal vehicle constants."
    ),
    provenance=MetricProvenance(
        producer_id=PRODUCER_ID,
        source_module="racelab_engine.analysis.surface_disturbance_response",
        source_contract_ids=(
            "p19.lap_eligibility",
            "p19.exact_physical_position",
            "qualified_telemetry_clock",
        ),
        reference_ids=("p35.4.continuous_clock_response_request",),
    ),
)


class _Profile:
    def __init__(
        self,
        *,
        center: float,
        noise: float,
        baseline_excursion: float,
        threshold: float,
        baseline_count: int,
    ) -> None:
        self.center = center
        self.noise = noise
        self.baseline_excursion = baseline_excursion
        self.threshold = threshold
        self.baseline_count = baseline_count


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _rows(data: pl.DataFrame | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(data, pl.DataFrame):
        return data.to_dicts()
    return [dict(row) for row in data]


def _canonical_content(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"__nonfinite_float__": "nan"}
        if math.isinf(value):
            return {"__nonfinite_float__": "inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_content(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _PRESENTATION_IDENTITY_KEYS
        }
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_canonical_content(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes_hex__": bytes(value).hex()}
    return {"__typed_text__": f"{type(value).__qualname__}:{value}"}


def ordered_telemetry_content_sha256(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
) -> str:
    """Derive a projection hash from exact ordered telemetry content.

    Presentation aliases such as ``run_id`` and source paths are excluded so a
    renamed or re-imported copy cannot manufacture a new physical source. Row
    order, channel identity, values, nulls, arrays, ticks, and timestamps remain
    in the digest. This is not the original source-file SHA-256; that independent
    physical-recording identity is required separately on ``PhysicalLapScope``.
    """

    payload = _canonical_content(_rows(data))
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lap_number(row: Mapping[str, Any]) -> int | None:
    value = _finite(row.get("lap", row.get("lap_number")))
    if value is None or not math.isclose(value, round(value), abs_tol=1e-9):
        return None
    return int(round(value))


def _lap_pct(row: Mapping[str, Any]) -> float | None:
    value = _finite(row.get("lap_dist_pct_100"))
    if value is None:
        value = _finite(row.get("lap_dist_pct"))
        if value is not None and 0.0 <= value <= 1.5:
            value *= 100.0
    return value if value is not None and 0.0 <= value <= 100.0 else None


def _scope_ref(scope: PhysicalLapScope) -> BlockerPhysicalScope:
    return BlockerPhysicalScope(
        run_id=scope.run_id,
        lap_number=scope.lap_number,
        lap_pct_start=scope.lap_pct_start,
        lap_pct_end=scope.lap_pct_end,
    )


def _blocker(
    scope: PhysicalLapScope,
    *,
    code: str,
    message: str,
    recovery: str,
    channels: tuple[str, ...] = (),
    blocks: tuple[EngineeringBlockTarget, ...] = (
        EngineeringBlockTarget.OBSERVATION,
        EngineeringBlockTarget.MECHANISM,
        EngineeringBlockTarget.SETUP_ATTRIBUTION,
    ),
    evidence_state: EvidenceState = EvidenceState.UNAVAILABLE,
    severity: EngineeringBlockerSeverity = EngineeringBlockerSeverity.BLOCKER,
) -> EngineeringBlocker:
    return EngineeringBlocker(
        code=code,
        severity=severity,
        scope="surface_disturbance_settling",
        blocks=blocks,
        message=message,
        evidence_state=evidence_state,
        source_artifact_ids=(scope.source_artifact_id,),
        source_channels=channels,
        physical_scope=_scope_ref(scope),
        recovery=recovery,
    )


def _dedupe_blockers(
    blockers: Sequence[EngineeringBlocker],
) -> tuple[EngineeringBlocker, ...]:
    unique: list[EngineeringBlocker] = []
    seen: set[str] = set()
    for blocker in blockers:
        identity = blocker.model_dump_json()
        if identity not in seen:
            seen.add(identity)
            unique.append(blocker)
    return tuple(unique)


def _unavailable(
    blockers: Sequence[EngineeringBlocker],
) -> SurfaceDisturbanceEpisodeResult:
    exact = _dedupe_blockers(blockers)
    return SurfaceDisturbanceEpisodeResult(
        status="unavailable",
        blockers=exact,
        required_measurements=tuple(dict.fromkeys(item.recovery for item in exact)),
    )


def _profile(values: Sequence[float], baseline_count: int) -> _Profile:
    baseline = list(values[:baseline_count])
    center = float(median(baseline))
    deviations = [abs(value - center) for value in baseline]
    median_deviation = float(median(deviations))
    robust_noise = 1.4826 * median_deviation
    baseline_excursion = max(deviations, default=0.0)
    numeric_floor = _NUMERIC_EPSILON * max(1.0, abs(center))
    threshold = max(
        baseline_excursion + 3.0 * robust_noise,
        numeric_floor,
    )
    return _Profile(
        center=center,
        noise=robust_noise,
        baseline_excursion=baseline_excursion,
        threshold=threshold,
        baseline_count=baseline_count,
    )


def _onset(
    values: Sequence[float],
    profile: _Profile,
    *,
    start: int,
) -> int | None:
    for index in range(max(start, profile.baseline_count), len(values) - 1):
        if all(
            abs(values[candidate] - profile.center) > profile.threshold
            for candidate in (index, index + 1)
        ):
            return index
    return None


def _settling(
    values: Sequence[float],
    profile: _Profile,
    *,
    onset: int,
    times: Sequence[float],
    hold_count: int,
) -> tuple[float, float, int, float | None]:
    deltas = [value - profile.center for value in values]
    peak_index = max(range(onset, len(values)), key=lambda index: abs(deltas[index]))
    peak = abs(deltas[peak_index])
    tail_count = min(hold_count, len(values))
    tail = abs(float(median(deltas[-tail_count:])))
    overshoot = max(0.0, min(1.0, (peak - tail) / peak)) if peak > 0.0 else 0.0
    settle_index = next(
        (
            index
            for index in range(peak_index, len(values) - hold_count + 1)
            if all(
                abs(deltas[candidate]) <= profile.threshold
                for candidate in range(index, index + hold_count)
            )
        ),
        None,
    )
    stop = settle_index if settle_index is not None else len(values) - 1
    signs = [
        1 if deltas[index] > profile.threshold else -1
        if deltas[index] < -profile.threshold
        else 0
        for index in range(onset, stop + 1)
    ]
    nonzero = [sign for sign in signs if sign]
    oscillations = sum(left != right for left, right in zip(nonzero, nonzero[1:]))
    duration = times[settle_index] - times[onset] if settle_index is not None else None
    return peak, overshoot, oscillations, duration


def _platform_settling(
    travel: Mapping[str, Sequence[float]],
    profiles: Mapping[str, _Profile],
    *,
    onset: int,
    times: Sequence[float],
    hold_count: int,
) -> float | None:
    settle_index = next(
        (
            index
            for index in range(onset, len(times) - hold_count + 1)
            if all(
                abs(travel[corner][candidate] - profiles[corner].center)
                <= profiles[corner].threshold
                for corner in _CORNERS
                for candidate in range(index, index + hold_count)
            )
        ),
        None,
    )
    return times[settle_index] - times[onset] if settle_index is not None else None


def _noise_floor(
    channel: str,
    profile: _Profile,
) -> EmpiricalNoiseFloor:
    return EmpiricalNoiseFloor(
        channel=channel,
        unit=_UNITS[channel],
        baseline_sample_count=profile.baseline_count,
        baseline_center=profile.center,
        robust_noise_floor=profile.noise,
        observed_baseline_excursion=profile.baseline_excursion,
        onset_excursion_threshold=profile.threshold,
    )


def analyze_surface_disturbance_episode(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    scope: PhysicalLapScope,
    expected_sample_rate_hz: float | None,
) -> SurfaceDisturbanceEpisodeResult:
    """Measure one physical-lap disturbance response on canonical time."""

    rows = _rows(data)
    telemetry_content_sha256 = ordered_telemetry_content_sha256(rows)
    clock = build_qualified_telemetry_clock(
        rows,
        expected_sample_rate_hz=expected_sample_rate_hz,
    )
    blockers: list[EngineeringBlocker] = []
    if not scope.lap_is_complete or not scope.lap_is_eligible:
        blockers.append(
            _blocker(
                scope,
                code="INELIGIBLE_PHYSICAL_LAP",
                message="The selected physical lap is incomplete or canonically ineligible.",
                recovery="Select a complete canonically eligible flying lap.",
            )
        )
    observation_context_blockers = tuple(
        item
        for item in scope.context_blockers
        if EngineeringBlockTarget.OBSERVATION in item.blocks
    )
    blockers.extend(observation_context_blockers)
    if (
        clock.clock_state != "qualified"
        or clock.primary_clock != "session_tick"
        or clock.tick_rate_hz is None
        or clock.blockers
    ):
        blockers.append(
            _blocker(
                scope,
                code="QUALIFIED_CLOCK_UNAVAILABLE",
                message="The supplied telemetry clock is not a blocker-free qualified tick clock.",
                recovery="Repair tick continuity/rate truth before measuring settling response.",
                channels=tuple(clock.source_channels),
            )
        )
    if blockers:
        return _unavailable(blockers)

    assert clock.tick_rate_hz is not None
    canonical_times = clock.canonical_time_by_sample_s
    epochs = clock.epoch_index_by_sample
    if (
        clock.sample_count != len(rows)
        or len(canonical_times) != len(rows)
        or len(epochs) != len(rows)
    ):
        return _unavailable(
            [
                _blocker(
                    scope,
                    code="CLOCK_DATA_SCOPE_MISMATCH",
                    message="Clock sample projection does not match the supplied telemetry table.",
                    recovery="Build the canonical clock from the exact same ordered telemetry table.",
                    channels=tuple(clock.source_channels),
                )
            ]
        )

    indexed = [
        (index, row, pct)
        for index, row in enumerate(rows)
        if _lap_number(row) == scope.lap_number
        and (pct := _lap_pct(row)) is not None
        and scope.lap_pct_start <= pct <= scope.lap_pct_end
    ]
    if any(
        row.get("run_id") is not None and str(row.get("run_id")) != scope.run_id
        for _index, row, _pct in indexed
    ):
        blockers.append(
            _blocker(
                scope,
                code="FOREIGN_RUN_SAMPLE",
                message="The physical scope contains a telemetry row from another run.",
                recovery="Supply only telemetry owned by the scoped run.",
            )
        )
    if len(indexed) < _MIN_SCOPE_SAMPLES:
        blockers.append(
            _blocker(
                scope,
                code="INSUFFICIENT_SCOPE_SAMPLES",
                message=(
                    f"The physical window contains {len(indexed)} samples; "
                    f"at least {_MIN_SCOPE_SAMPLES} are required."
                ),
                recovery="Capture a wider pre-event and recovery window on the same physical lap.",
            )
        )
    missing_channels = [
        channel
        for channel in ("speed_mps", *_RESPONSE_CHANNELS)
        if any(_finite(row.get(channel)) is None for _index, row, _pct in indexed)
    ]
    if missing_channels:
        blockers.append(
            _blocker(
                scope,
                code="REQUIRED_RESPONSE_CHANNEL_UNAVAILABLE",
                message=(
                    "Continuous speed, yaw, vertical acceleration, and all four shock "
                    "velocity/travel channels must be co-observed."
                ),
                recovery="Record complete continuous yaw and four-corner shock velocity/travel telemetry.",
                channels=tuple(missing_channels),
            )
        )
    scoped_times = [canonical_times[index] for index, _row, _pct in indexed]
    if any(value is None for value in scoped_times):
        blockers.append(
            _blocker(
                scope,
                code="CANONICAL_CLOCK_GAP",
                message="Canonical time is missing inside the physical response window.",
                recovery="Repair the qualified base-record clock and recapture the event.",
                channels=tuple(clock.source_channels),
            )
        )
    times = [float(value) for value in scoped_times if value is not None]
    if len(times) >= 2 and any(right <= left for left, right in zip(times, times[1:])):
        blockers.append(
            _blocker(
                scope,
                code="CANONICAL_CLOCK_NOT_MONOTONIC",
                message="Canonical time is not strictly increasing inside the physical scope.",
                recovery="Use a single qualified tick-clock epoch for the event.",
                channels=tuple(clock.source_channels),
            )
        )
    scoped_epochs = {epochs[index] for index, _row, _pct in indexed}
    if len(scoped_epochs) > 1:
        blockers.append(
            _blocker(
                scope,
                code="CLOCK_RESET_INSIDE_SCOPE",
                message="The physical response window crosses a telemetry clock reset epoch.",
                recovery="Use an eligible lap window contained in one qualified clock epoch.",
                channels=tuple(clock.source_channels),
            )
        )
    pcts = [pct for _index, _row, pct in indexed]
    if any(right < left for left, right in zip(pcts, pcts[1:])):
        blockers.append(
            _blocker(
                scope,
                code="PHYSICAL_POSITION_NOT_MONOTONIC",
                message="Lap position reverses inside the physical response window.",
                recovery="Use one ordered physical lap segment without reset fragments.",
                channels=("lap_dist_pct_100",),
            )
        )
    if times:
        expected = max(1, int(round((times[-1] - times[0]) * clock.tick_rate_hz)) + 1)
        sample_coverage = min(1.0, len(indexed) / expected)
    else:
        sample_coverage = 0.0
    if sample_coverage < _MIN_SAMPLE_COVERAGE:
        blockers.append(
            _blocker(
                scope,
                code="INSUFFICIENT_CLOCK_COVERAGE",
                message=(
                    f"The physical response window has {sample_coverage:.1%} canonical "
                    "sample coverage."
                ),
                recovery="Capture at least 90% continuous base-record coverage through recovery.",
                channels=tuple(clock.source_channels),
            )
        )
    declared_phases = {
        str(row.get("engineering_phase"))
        for _index, row, _pct in indexed
        if row.get("engineering_phase")
    }
    if declared_phases and scope.phase not in declared_phases:
        blockers.append(
            _blocker(
                scope,
                code="PHASE_SCOPE_MISMATCH",
                message="Telemetry phase labels do not include the requested physical phase.",
                recovery="Bind the response window to its producer-owned physical phase.",
            )
        )
    positive_pct_steps = [
        right - left for left, right in zip(pcts, pcts[1:]) if right > left
    ]
    if not positive_pct_steps:
        blockers.append(
            _blocker(
                scope,
                code="PHYSICAL_POSITION_RESOLUTION_UNAVAILABLE",
                message="The scope has no positive physical-position progression.",
                recovery="Record a moving lap segment with qualified lap position.",
                channels=("lap_dist_pct_100",),
            )
        )
    if blockers:
        return _unavailable(blockers)

    values = {
        channel: [float(_finite(row[channel])) for _index, row, _pct in indexed]
        for channel in ("speed_mps", *_RESPONSE_CHANNELS)
    }
    baseline_count = max(5, len(indexed) // 5)
    if len(indexed) - baseline_count < 8:
        return _unavailable(
            [
                _blocker(
                    scope,
                    code="RECOVERY_WINDOW_TOO_SHORT",
                    message="The scope does not preserve enough samples after its empirical baseline.",
                    recovery="Capture more post-event samples so response and settling can be observed.",
                )
            ]
        )
    profiles = {
        channel: _profile(values[channel], baseline_count)
        for channel in _RESPONSE_CHANNELS
    }
    disturbance_onset = _onset(
        values["vert_accel"],
        profiles["vert_accel"],
        start=baseline_count,
    )
    if disturbance_onset is None:
        return _unavailable(
            [
                _blocker(
                    scope,
                    code="DISTURBANCE_RESPONSE_NOT_OBSERVED",
                    message="Vertical response did not clear its own pre-event noise floor.",
                    recovery="Capture repeated passes with pre-event baseline and visible vertical response.",
                    channels=("vert_accel",),
                )
            ]
        )

    response_onsets: dict[str, int] = {}
    for channel in (
        "yaw_rate",
        *(f"{corner}_shock_vel_in_s" for corner in _CORNERS),
        *(f"{corner}_shock_defl_in" for corner in _CORNERS),
    ):
        onset = _onset(values[channel], profiles[channel], start=disturbance_onset)
        if onset is None:
            blockers.append(
                _blocker(
                    scope,
                    code="RESPONSE_ONSET_UNAVAILABLE",
                    message=f"{channel} did not clear its empirical pre-event noise floor.",
                    recovery="Repeat the event with complete pre-event baseline and recovery coverage.",
                    channels=(channel,),
                )
            )
        else:
            response_onsets[channel] = onset
    if blockers:
        return _unavailable(blockers)

    travel = {
        corner: values[f"{corner}_shock_defl_in"] for corner in _CORNERS
    }
    travel_profiles = {
        corner: profiles[f"{corner}_shock_defl_in"] for corner in _CORNERS
    }
    travel_deltas = {
        corner: [value - travel_profiles[corner].center for value in travel[corner]]
        for corner in _CORNERS
    }
    platform_motion = [
        math.sqrt(
            sum(travel_deltas[corner][index] ** 2 for corner in _CORNERS)
            / len(_CORNERS)
        )
        for index in range(len(indexed))
    ]
    platform_profile = _profile(platform_motion, baseline_count)
    platform_onset = _onset(
        platform_motion,
        platform_profile,
        start=disturbance_onset,
    )
    if platform_onset is None:
        return _unavailable(
            [
                _blocker(
                    scope,
                    code="PLATFORM_RESPONSE_ONSET_UNAVAILABLE",
                    message="Four-corner shock travel did not produce a platform-motion response.",
                    recovery="Repeat the event with complete four-corner shock travel coverage.",
                    channels=tuple(f"{corner}_shock_defl_in" for corner in _CORNERS),
                )
            ]
        )

    hold_count = max(3, baseline_count // 2)
    corner_responses: list[CornerSettlingResponse] = []
    right_censored = False
    for corner in _CORNERS:
        velocity_channel = f"{corner}_shock_vel_in_s"
        travel_channel = f"{corner}_shock_defl_in"
        velocity_onset = response_onsets[velocity_channel]
        travel_onset = response_onsets[travel_channel]
        velocity_peak, velocity_overshoot, velocity_oscillations, velocity_settle = (
            _settling(
                values[velocity_channel],
                profiles[velocity_channel],
                onset=velocity_onset,
                times=times,
                hold_count=hold_count,
            )
        )
        travel_peak, travel_overshoot, travel_oscillations, travel_settle = _settling(
            values[travel_channel],
            profiles[travel_channel],
            onset=travel_onset,
            times=times,
            hold_count=hold_count,
        )
        censored = velocity_settle is None or travel_settle is None
        right_censored = right_censored or censored
        corner_responses.append(
            CornerSettlingResponse(
                corner=corner,
                shock_velocity_onset_canonical_time_s=times[velocity_onset],
                shock_travel_onset_canonical_time_s=times[travel_onset],
                observed_velocity_lag_s=times[velocity_onset]
                - times[disturbance_onset],
                observed_travel_lag_s=times[travel_onset]
                - times[disturbance_onset],
                peak_abs_shock_velocity_in_s=velocity_peak,
                peak_abs_shock_travel_delta_in=travel_peak,
                shock_velocity_overshoot_fraction=velocity_overshoot,
                shock_travel_overshoot_fraction=travel_overshoot,
                velocity_settling_duration_s=velocity_settle,
                travel_settling_duration_s=travel_settle,
                velocity_oscillation_count=velocity_oscillations,
                travel_oscillation_count=travel_oscillations,
                settling_right_censored=censored,
                source_channels=(velocity_channel, travel_channel),
            )
        )

    yaw_onset = response_onsets["yaw_rate"]
    yaw_peak, yaw_overshoot, yaw_corrections, yaw_settle = _settling(
        values["yaw_rate"],
        profiles["yaw_rate"],
        onset=yaw_onset,
        times=times,
        hold_count=hold_count,
    )
    platform_peak, platform_overshoot, _unused, _unused_settle = _settling(
        platform_motion,
        platform_profile,
        onset=platform_onset,
        times=times,
        hold_count=hold_count,
    )
    platform_settle = _platform_settling(
        travel,
        travel_profiles,
        onset=platform_onset,
        times=times,
        hold_count=hold_count,
    )
    platform_oscillations = max(
        item.travel_oscillation_count for item in corner_responses
    )
    front_heave = [
        (travel_deltas["lf"][index] + travel_deltas["rf"][index]) / 2.0
        for index in range(len(indexed))
    ]
    rear_heave = [
        (travel_deltas["lr"][index] + travel_deltas["rr"][index]) / 2.0
        for index in range(len(indexed))
    ]
    pitch = [front - rear for front, rear in zip(front_heave, rear_heave)]
    front_roll = [
        travel_deltas["lf"][index] - travel_deltas["rf"][index]
        for index in range(len(indexed))
    ]
    rear_roll = [
        travel_deltas["lr"][index] - travel_deltas["rr"][index]
        for index in range(len(indexed))
    ]
    platform_yaw_censored = platform_settle is None or yaw_settle is None
    right_censored = right_censored or platform_yaw_censored
    platform_yaw = PlatformYawSettlingResponse(
        platform_response_onset_canonical_time_s=times[platform_onset],
        yaw_response_onset_canonical_time_s=times[yaw_onset],
        observed_platform_lag_s=times[platform_onset] - times[disturbance_onset],
        observed_yaw_lag_s=times[yaw_onset] - times[disturbance_onset],
        peak_platform_motion_proxy_in=platform_peak,
        peak_front_heave_proxy_in=max(abs(value) for value in front_heave),
        peak_rear_heave_proxy_in=max(abs(value) for value in rear_heave),
        peak_pitch_proxy_in=max(abs(value) for value in pitch),
        peak_front_roll_proxy_in=max(abs(value) for value in front_roll),
        peak_rear_roll_proxy_in=max(abs(value) for value in rear_roll),
        peak_abs_yaw_rate_delta_rad_s=yaw_peak,
        platform_overshoot_fraction=platform_overshoot,
        yaw_overshoot_fraction=yaw_overshoot,
        platform_settling_duration_s=platform_settle,
        yaw_settling_duration_s=yaw_settle,
        platform_oscillation_count=platform_oscillations,
        yaw_correction_count=yaw_corrections,
        settling_right_censored=platform_yaw_censored,
        source_channels=(
            "yaw_rate",
            *(f"{corner}_shock_defl_in" for corner in _CORNERS),
        ),
    )

    disturbance_profile = profiles["vert_accel"]
    disturbance_peak = max(
        abs(value - disturbance_profile.center)
        for value in values["vert_accel"][disturbance_onset:]
    )
    speed = values["speed_mps"]
    resolution = float(median(positive_pct_steps))
    identity = "|".join(
        (
            FORMULA_VERSION,
            scope.source_file_sha256,
            telemetry_content_sha256,
            str(scope.lap_number),
            scope.context_id,
            f"{scope.lap_pct_start:.12g}",
            f"{scope.lap_pct_end:.12g}",
            f"{pcts[disturbance_onset]:.12g}",
        )
    )
    episode = SurfaceDisturbanceEpisodeSignature(
        episode_id="surface-response:"
        + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
        formula_version=FORMULA_VERSION,
        telemetry_content_sha256=telemetry_content_sha256,
        scope=scope,
        disturbance_onset_canonical_time_s=times[disturbance_onset],
        disturbance_onset_lap_pct=pcts[disturbance_onset],
        peak_vertical_acceleration_delta_mps2=disturbance_peak,
        corner_responses=tuple(corner_responses),
        platform_yaw_response=platform_yaw,
        median_speed_mps=float(median(speed)),
        speed_min_mps=min(speed),
        speed_max_mps=max(speed),
        physical_sample_resolution_pct=resolution,
        sample_count=len(indexed),
        sample_coverage=sample_coverage,
        noise_floor_by_channel=tuple(
            _noise_floor(channel, profiles[channel]) for channel in _RESPONSE_CHANNELS
        ),
        source_channels=_REQUIRED_CHANNELS,
        clock_source_channels=tuple(dict.fromkeys(clock.source_channels)),
    )

    limited_blockers: list[EngineeringBlocker] = list(scope.context_blockers)
    if right_censored:
        limited_blockers.append(
            _blocker(
                scope,
                code="SETTLING_RIGHT_CENSORED",
                message="At least one response remained outside its empirical baseline at scope end.",
                recovery="Capture a longer post-disturbance physical window through full recovery.",
                blocks=(
                    EngineeringBlockTarget.MECHANISM,
                    EngineeringBlockTarget.SETUP_ATTRIBUTION,
                ),
                evidence_state=EvidenceState.NEEDS_CONFIRMATION,
                severity=EngineeringBlockerSeverity.WARNING,
                channels=_RESPONSE_CHANNELS,
            )
        )
    exact_limited = _dedupe_blockers(limited_blockers)
    return SurfaceDisturbanceEpisodeResult(
        status="limited" if exact_limited else "qualified",
        episode=episode,
        blockers=exact_limited,
        required_measurements=tuple(
            dict.fromkeys(item.recovery for item in exact_limited)
        ),
    )


__all__ = [
    "FORMULA_VERSION",
    "PRODUCER_ID",
    "SURFACE_DISTURBANCE_SETTLING_CONTRACT",
    "analyze_surface_disturbance_episode",
    "ordered_telemetry_content_sha256",
]
