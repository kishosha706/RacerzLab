"""Descriptive transient response and sub-tick steering workload analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import math
from statistics import median
from typing import Any

import polars as pl

from racelab_engine.models.engineering_awareness import (
    DerivedMetricContract,
    MetricProvenance,
)
from racelab_engine.models.engineering_context import (
    ControlMutationEvent,
    ControlMutationKind,
    SteeringContextFingerprint,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.models.transient_awareness import (
    ExactAnalysisWindow,
    SteeringWorkloadComparison,
    SteeringWorkloadDescriptor,
    SteeringWorkloadReport,
    TransientResponseDescriptor,
    TransientResponseReport,
)
from racelab_engine.services.engineering_context_service import (
    compare_steering_contexts,
)


_TRANSIENT_FORMULA_VERSION = "p20.transient_response.v1"
_WORKLOAD_FORMULA_VERSION = "p20.steering_workload.v1"

TRANSIENT_RESPONSE_CONTRACT = DerivedMetricContract(
    metric_key="steering_to_yaw_transient_response",
    formula_version=_TRANSIENT_FORMULA_VERSION,
    label="Steering-to-yaw transient response",
    evidence_state=EvidenceState.CALCULATED,
    required_channels=(
        "session_time",
        "lap_dist_pct_100",
        "steering_deg",
        "yaw_rate",
        "lat_accel",
        "speed_mps",
    ),
    preferred_channels=("curvature_1_per_m", "roll_rate", "pitch_rate"),
    allowed_channel_semantics=(ChannelUpdateSemantic.CONTINUOUS,),
    required_vehicle_profile_fields=(),
    valid_phases=(
        "turn_in",
        "entry",
        "center",
        "apex_region",
        "initial_throttle",
        "full_throttle_exit",
    ),
    hard_blockers=(
        "junk_or_ineligible_lap",
        "material_control_mutation",
        "unhealthy_sample_clock",
        "insufficient_window_coverage",
        "no_detectable_steering_or_yaw_response",
    ),
    minimum_sample_coverage=0.9,
    minimum_repetitions=1,
    allowed_outputs=(
        "observed_yaw_response_delay_ms",
        "observed_lateral_response_delay_ms",
        "descriptive_rise_time_ms",
        "peak_yaw_response_gain_proxy",
        "overshoot_proxy_fraction",
        "settling_time_s",
        "steering_yaw_hysteresis_proxy",
    ),
    forbidden_claims=(
        "vehicle_time_constant",
        "understeer_coefficient",
        "stability_derivative",
        "exact_handling_transfer_function",
        "setup_cause",
    ),
    authority_ceiling="observation_only",
    description=(
        "Amplitude-relative onset, rise, peak, settling, and path descriptors for one "
        "exact telemetry window; temporal response is not causal setup attribution."
    ),
    provenance=MetricProvenance(
        producer_id="p20.transient_awareness",
        source_module="racelab_engine.analysis.transient_awareness",
        source_contract_ids=("p19.exact_physical_position",),
        reference_ids=("p20_request.transient_response",),
    ),
)

STEERING_WORKLOAD_CONTRACT = DerivedMetricContract(
    metric_key="steering_control_workload",
    formula_version=_WORKLOAD_FORMULA_VERSION,
    label="Steering control workload",
    evidence_state=EvidenceState.ESTIMATED_PROXY,
    required_channels=(
        "session_time",
        "lap_dist_pct_100",
        "steering_deg",
        "steering_wheel_torque_subtick_nm",
        "speed_mps",
    ),
    preferred_channels=("curvature_1_per_m", "steering_wheel_torque_nm"),
    allowed_channel_semantics=(ChannelUpdateSemantic.CONTINUOUS,),
    required_vehicle_profile_fields=(),
    valid_phases=(
        "straight",
        "following_straight_carry",
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
        "lift",
        "transition",
    ),
    hard_blockers=(
        "junk_or_ineligible_lap",
        "unhealthy_sub_tick_clock",
        "missing_sub_tick_torque",
        "material_control_mutation",
        "ffb_fingerprint_mismatch_for_comparison",
        "steering_conversion_mismatch_for_comparison",
    ),
    minimum_sample_coverage=0.9,
    minimum_repetitions=1,
    allowed_outputs=(
        "torque_rms_nm",
        "torque_p95_nm",
        "peak_abs_torque_nm",
        "near_limiter_duty_fraction",
        "torque_reversal_rate_hz",
        "steering_rate_reversal_rate_hz",
        "high_frequency_variation_proxy_nm2",
        "steering_perturbation_index",
        "torque_angle_hysteresis_proxy_nm_rad",
        "steering_effort_work_proxy",
        "correction_density_per_s",
        "effort_per_achieved_curvature_proxy",
    ),
    forbidden_claims=(
        "driver_fatigue",
        "mental_workload",
        "physical_exhaustion",
        "driver_impairment",
        "tire_aligning_torque",
        "tire_force",
        "rack_work",
        "steering_energy",
    ),
    authority_ceiling="observation_only",
    description=(
        "Sub-tick steering torque and steering-motion workload proxies. Values are "
        "descriptive and comparisons require an exact matching FFB fingerprint."
    ),
    provenance=MetricProvenance(
        producer_id="p20.transient_awareness",
        source_module="racelab_engine.analysis.transient_awareness",
        source_contract_ids=("p19.sub_tick_preservation",),
        reference_ids=("p20_request.driver_control_workload",),
    ),
)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * fraction))
    return ordered[index]


def _scope_rows(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    window: ExactAnalysisWindow,
    columns: Sequence[str],
) -> list[dict[str, Any]]:
    requested = tuple(dict.fromkeys(("run_id", "lap", "lap_number", *columns)))
    if isinstance(data, pl.DataFrame):
        existing = [name for name in requested if name in data.columns]
        scoped = data.select(existing)
        lap_column = "lap" if "lap" in scoped.columns else "lap_number" if "lap_number" in scoped.columns else None
        if lap_column is not None:
            scoped = scoped.filter(
                pl.col(lap_column).cast(pl.Int64, strict=False) == window.lap_number
            )
        if "lap_dist_pct_100" in scoped.columns:
            scoped = scoped.filter(
                pl.col("lap_dist_pct_100").is_between(
                    window.lap_pct_start,
                    window.lap_pct_end,
                    closed="both",
                )
            )
        if "session_time" in scoped.columns:
            scoped = scoped.filter(
                pl.col("session_time").is_between(
                    window.session_time_start,
                    window.session_time_end,
                    closed="both",
                )
            )
        rows = scoped.to_dicts()
    else:
        rows = []
        for source in data:
            number = _finite(source.get("lap", source.get("lap_number")))
            pct = _finite(source.get("lap_dist_pct_100"))
            time = _finite(source.get("session_time"))
            if (
                number != window.lap_number
                or pct is None
                or time is None
                or not window.lap_pct_start <= pct <= window.lap_pct_end
                or not window.session_time_start <= time <= window.session_time_end
            ):
                continue
            rows.append({name: source.get(name) for name in requested if name in source})
    return sorted(rows, key=lambda row: _finite(row.get("session_time")) or 0.0)


def _scope_blockers(
    rows: Sequence[Mapping[str, Any]],
    window: ExactAnalysisWindow,
    *,
    lap_eligible: bool,
    control_mutations: Sequence[ControlMutationEvent],
    expected_sample_rate_hz: float,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not lap_eligible:
        blockers.append("The selected lap is not canonically eligible.")
    if any(
        mutation.run_id == window.run_id
        and mutation.mutation_kind is ControlMutationKind.APPLIED_STATE
        and window.session_time_start < mutation.session_time < window.session_time_end
        for mutation in control_mutations
    ):
        blockers.append("A material applied control mutation occurs inside the analysis window.")
    times = [
        value for row in rows if (value := _finite(row.get("session_time"))) is not None
    ]
    if len(times) < 3 or any(right <= left for left, right in zip(times, times[1:])):
        blockers.append("The analysis window requires a healthy monotonic sample clock.")
    duration = max(0.0, window.session_time_end - window.session_time_start)
    expected = max(1, int(math.floor(duration * expected_sample_rate_hz)) + 1)
    if len(times) / expected < 0.9:
        blockers.append("The analysis window has less than 90% expected sample coverage.")
    if any(str(row.get("run_id")) != window.run_id for row in rows if row.get("run_id") is not None):
        blockers.append("A telemetry sample belongs to a different run.")
    return tuple(dict.fromkeys(blockers))


def _series(rows: Sequence[Mapping[str, Any]], channel: str) -> list[float] | None:
    values = [_finite(row.get(channel)) for row in rows]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values if value is not None]


def _relative_onset(values: Sequence[float]) -> int | None:
    if len(values) < 3:
        return None
    initial = median(values[: max(1, min(3, len(values)))])
    deltas = [abs(value - initial) for value in values]
    amplitude = max(deltas)
    if amplitude <= 1e-12:
        return None
    threshold = amplitude * 0.10
    return next((index for index, value in enumerate(deltas) if value >= threshold), None)


def _rise_time(times: Sequence[float], values: Sequence[float], onset: int) -> float | None:
    baseline = values[onset]
    deltas = [abs(value - baseline) for value in values[onset:]]
    amplitude = max(deltas, default=0.0)
    if amplitude <= 1e-12:
        return None
    index_10 = next((index for index, value in enumerate(deltas) if value >= 0.10 * amplitude), None)
    index_90 = next((index for index, value in enumerate(deltas) if value >= 0.90 * amplitude), None)
    if index_10 is None or index_90 is None or index_90 < index_10:
        return None
    return (times[onset + index_90] - times[onset + index_10]) * 1000.0


def analyze_transient_response(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    control_mutations: Sequence[ControlMutationEvent] = (),
    expected_sample_rate_hz: float = 60.0,
) -> TransientResponseReport:
    columns = (*TRANSIENT_RESPONSE_CONTRACT.required_channels, "run_id")
    rows = _scope_rows(data, window, columns)
    blockers = list(
        _scope_blockers(
            rows,
            window,
            lap_eligible=lap_eligible,
            control_mutations=control_mutations,
            expected_sample_rate_hz=expected_sample_rate_hz,
        )
    )
    if window.phase not in TRANSIENT_RESPONSE_CONTRACT.valid_phases:
        blockers.append("The exact window is not assigned to a valid transient-response phase.")
    times = _series(rows, "session_time")
    steering = _series(rows, "steering_deg")
    yaw = _series(rows, "yaw_rate")
    lateral = _series(rows, "lat_accel")
    speed = _series(rows, "speed_mps")
    for values, label in (
        (steering, "steering angle"),
        (yaw, "yaw rate"),
        (lateral, "lateral acceleration"),
        (speed, "speed"),
    ):
        if values is None:
            blockers.append(f"Continuous {label} coverage is required in the exact window.")
    if blockers or times is None or steering is None or yaw is None or lateral is None:
        return TransientResponseReport(
            status="blocked",
            contract=TRANSIENT_RESPONSE_CONTRACT,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    steering_onset = _relative_onset(steering)
    yaw_onset = _relative_onset(yaw)
    lateral_onset = _relative_onset(lateral)
    if steering_onset is None or yaw_onset is None:
        return TransientResponseReport(
            status="no_finding",
            contract=TRANSIENT_RESPONSE_CONTRACT,
        )
    yaw_delta = max(abs(value - yaw[steering_onset]) for value in yaw[steering_onset:])
    steering_delta = max(
        abs(value - steering[steering_onset]) for value in steering[steering_onset:]
    )
    peak_index = max(
        range(steering_onset, len(yaw)),
        key=lambda index: abs(yaw[index] - yaw[steering_onset]),
    )
    final_yaw = median(yaw[-max(1, min(3, len(yaw))):])
    final_delta = abs(final_yaw - yaw[steering_onset])
    overshoot = max(0.0, (yaw_delta - final_delta) / yaw_delta) if yaw_delta > 0.0 else None
    settle_index: int | None = None
    tolerance = max(yaw_delta * 0.10, 1e-12)
    for index in range(peak_index, len(yaw)):
        if all(abs(value - final_yaw) <= tolerance for value in yaw[index:]):
            settle_index = index
            break
    hysteresis = sum(
        abs((left_yaw + right_yaw) * 0.5 * (right_steer - left_steer))
        for left_yaw, right_yaw, left_steer, right_steer in zip(
            yaw,
            yaw[1:],
            steering,
            steering[1:],
        )
    )
    duration = max(1e-12, window.session_time_end - window.session_time_start)
    expected = max(1, int(math.floor(duration * expected_sample_rate_hz)) + 1)
    identity = (
        f"{window.run_id}|{window.lap_number}|{window.lap_pct_start}|"
        f"{window.lap_pct_end}|{_TRANSIENT_FORMULA_VERSION}"
    )
    descriptor = TransientResponseDescriptor(
        descriptor_id="transient:" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        formula_version=_TRANSIENT_FORMULA_VERSION,
        window=window,
        steering_onset_time_s=times[steering_onset],
        yaw_onset_time_s=times[yaw_onset],
        lateral_accel_onset_time_s=(
            times[lateral_onset] if lateral_onset is not None else None
        ),
        observed_yaw_response_delay_ms=(times[yaw_onset] - times[steering_onset]) * 1000.0,
        observed_lateral_response_delay_ms=(
            (times[lateral_onset] - times[steering_onset]) * 1000.0
            if lateral_onset is not None
            else None
        ),
        descriptive_rise_time_ms=_rise_time(times, yaw, yaw_onset),
        peak_yaw_response_gain_proxy=(
            yaw_delta / steering_delta if steering_delta > 1e-12 else None
        ),
        overshoot_proxy_fraction=overshoot,
        settling_time_s=(
            times[settle_index] - times[steering_onset]
            if settle_index is not None
            else None
        ),
        steering_yaw_hysteresis_proxy=hysteresis,
        sample_count=len(rows),
        sample_coverage=min(1.0, len(rows) / expected),
        source_channels=TRANSIENT_RESPONSE_CONTRACT.required_channels,
    )
    return TransientResponseReport(
        status="ready",
        contract=TRANSIENT_RESPONSE_CONTRACT,
        descriptor=descriptor,
    )


def _flatten_subtick_torque(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[float], list[float], list[float], float] | None:
    times = _series(rows, "session_time")
    steering = _series(rows, "steering_deg")
    if times is None or steering is None or len(times) < 2:
        return None
    torque: list[float] = []
    torque_dt: list[float] = []
    steering_rate: list[float] = []
    sample_rates: list[float] = []
    for index, row in enumerate(rows):
        raw = row.get("steering_wheel_torque_subtick_nm")
        samples = raw if isinstance(raw, (list, tuple)) else ()
        finite_samples = [value for item in samples if (value := _finite(item)) is not None]
        if not finite_samples:
            return None
        if index + 1 < len(times):
            frame_dt = times[index + 1] - times[index]
            angle_dt = steering[index + 1] - steering[index]
        elif index > 0:
            frame_dt = times[index] - times[index - 1]
            angle_dt = steering[index] - steering[index - 1]
        else:
            return None
        if frame_dt <= 0.0:
            return None
        dt = frame_dt / len(finite_samples)
        rate_rad_s = math.radians(angle_dt / frame_dt)
        torque.extend(finite_samples)
        torque_dt.extend([dt] * len(finite_samples))
        steering_rate.extend([rate_rad_s] * len(finite_samples))
        sample_rates.append(len(finite_samples) / frame_dt)
    return torque, torque_dt, steering_rate, float(median(sample_rates))


def _reversal_count(values: Sequence[float]) -> int:
    signs = [1 if value > 0.0 else -1 if value < 0.0 else 0 for value in values]
    nonzero = [sign for sign in signs if sign]
    return sum(left != right for left, right in zip(nonzero, nonzero[1:]))


def analyze_steering_workload(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    ffb_fingerprint: SteeringContextFingerprint,
    control_mutations: Sequence[ControlMutationEvent] = (),
    expected_sample_rate_hz: float = 60.0,
) -> SteeringWorkloadReport:
    columns = (
        *STEERING_WORKLOAD_CONTRACT.required_channels,
        *STEERING_WORKLOAD_CONTRACT.preferred_channels,
        "run_id",
    )
    rows = _scope_rows(data, window, columns)
    blockers = list(
        _scope_blockers(
            rows,
            window,
            lap_eligible=lap_eligible,
            control_mutations=control_mutations,
            expected_sample_rate_hz=expected_sample_rate_hz,
        )
    )
    if window.phase not in STEERING_WORKLOAD_CONTRACT.valid_phases:
        blockers.append("The exact window is not assigned to a valid steering-workload phase.")
    flattened = _flatten_subtick_torque(rows)
    speed = _series(rows, "speed_mps")
    if flattened is None:
        blockers.append("The exact window lacks a healthy preserved sub-tick torque stream.")
    if speed is None:
        blockers.append("Continuous speed context is required for steering workload.")
    if blockers or flattened is None or speed is None:
        return SteeringWorkloadReport(
            status="blocked",
            contract=STEERING_WORKLOAD_CONTRACT,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    torque, sample_dt, steering_rate, torque_rate_hz = flattened
    abs_torque = [abs(value) for value in torque]
    duration = sum(sample_dt)
    if duration <= 0.0:
        return SteeringWorkloadReport(
            status="blocked",
            contract=STEERING_WORKLOAD_CONTRACT,
            blocker_reasons=("The sub-tick torque window has no positive duration.",),
        )
    p95 = _percentile(abs_torque, 0.95)
    torque_mean_square = sum(value * value for value in torque) / len(torque)
    torque_variation = [right - left for left, right in zip(torque, torque[1:])]
    effort = sum(
        abs(value * rate) * dt
        for value, rate, dt in zip(torque, steering_rate, sample_dt)
    )
    angle_deltas = [rate * dt for rate, dt in zip(steering_rate, sample_dt)]
    hysteresis = sum(
        abs(value * delta) for value, delta in zip(torque, angle_deltas)
    )
    curvature = _series(rows, "curvature_1_per_m")
    achieved_curvature = (
        median(abs(value) for value in curvature) if curvature else None
    )
    near_limiter = (
        sum(value >= 0.95 * ffb_fingerprint.max_force_nm for value in abs_torque)
        / len(abs_torque)
        if ffb_fingerprint.max_force_nm is not None
        else None
    )
    steering_reversals = _reversal_count(steering_rate)
    torque_reversals = _reversal_count(torque)
    perturbation = (
        sum(abs(value) for value in torque_variation)
        / max(1, len(torque_variation))
        / max(p95, 1e-12)
    )
    identity = (
        f"{window.run_id}|{window.lap_number}|{window.lap_pct_start}|"
        f"{window.lap_pct_end}|{ffb_fingerprint.fingerprint_sha256}|"
        f"{_WORKLOAD_FORMULA_VERSION}"
    )
    descriptor = SteeringWorkloadDescriptor(
        descriptor_id="workload:" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        formula_version=_WORKLOAD_FORMULA_VERSION,
        window=window,
        ffb_fingerprint_sha256=ffb_fingerprint.fingerprint_sha256,
        torque_sample_rate_hz=torque_rate_hz,
        torque_sample_count=len(torque),
        sample_coverage=min(
            1.0,
            len(rows)
            / max(
                1,
                int(
                    math.floor(
                        (window.session_time_end - window.session_time_start)
                        * expected_sample_rate_hz
                    )
                )
                + 1,
            ),
        ),
        median_speed_mps=float(median(speed)),
        torque_rms_nm=math.sqrt(torque_mean_square),
        torque_p95_nm=p95,
        peak_abs_torque_nm=max(abs_torque),
        near_limiter_duty_fraction=near_limiter,
        torque_reversal_rate_hz=torque_reversals / duration,
        steering_rate_reversal_rate_hz=steering_reversals / duration,
        high_frequency_variation_proxy_nm2=(
            sum(value * value for value in torque_variation)
            / max(1, len(torque_variation))
        ),
        steering_perturbation_index=perturbation,
        torque_angle_hysteresis_proxy_nm_rad=hysteresis,
        steering_effort_work_proxy=effort,
        correction_density_per_s=steering_reversals / duration,
        effort_per_achieved_curvature_proxy=(
            effort / (achieved_curvature * duration)
            if achieved_curvature is not None and achieved_curvature > 1e-12
            else None
        ),
        source_channels=STEERING_WORKLOAD_CONTRACT.required_channels,
    )
    limitations = tuple(ffb_fingerprint.blocker_reasons)
    return SteeringWorkloadReport(
        status="limited" if limitations else "ready",
        contract=STEERING_WORKLOAD_CONTRACT,
        descriptor=descriptor,
        blocker_reasons=limitations,
    )


def compare_steering_workload(
    baseline: SteeringWorkloadDescriptor,
    test: SteeringWorkloadDescriptor,
    *,
    baseline_fingerprint: SteeringContextFingerprint,
    test_fingerprint: SteeringContextFingerprint,
    matched_physical_window: bool,
    matched_speed_band: bool,
    matched_driver_context: bool,
    healthy_sub_tick_clock: bool,
) -> SteeringWorkloadComparison:
    blockers: list[str] = []
    steering_context = compare_steering_contexts(
        baseline_fingerprint,
        test_fingerprint,
    )
    blockers.extend(steering_context.blocker_reasons)
    exact_baseline_scope = (
        baseline.window.phase,
        baseline.window.lap_pct_start,
        baseline.window.lap_pct_end,
    )
    exact_test_scope = (
        test.window.phase,
        test.window.lap_pct_start,
        test.window.lap_pct_end,
    )
    if exact_baseline_scope != exact_test_scope:
        blockers.append("Workload artifacts do not share the same exact physical phase window.")
    if baseline.window.context_id != test.window.context_id:
        blockers.append("Workload artifacts do not share the same backend context identity.")
    if not matched_physical_window:
        blockers.append("Steering workload requires a matched physical-position window.")
    if not matched_speed_band:
        blockers.append("Steering workload requires a matched speed band.")
    if not matched_driver_context:
        blockers.append("Steering workload requires matched driver context.")
    if not healthy_sub_tick_clock:
        blockers.append("Steering workload requires a healthy sub-tick clock.")
    if (
        baseline.ffb_fingerprint_sha256 != baseline_fingerprint.fingerprint_sha256
        or test.ffb_fingerprint_sha256 != test_fingerprint.fingerprint_sha256
    ):
        blockers.append("A workload artifact is not bound to the supplied FFB fingerprint.")
    if blockers:
        return SteeringWorkloadComparison(
            state=(
                "not_comparable"
                if steering_context.state == "not_comparable"
                else "unavailable"
            ),
            baseline_descriptor_id=baseline.descriptor_id,
            test_descriptor_id=test.descriptor_id,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    return SteeringWorkloadComparison(
        state="comparable",
        baseline_descriptor_id=baseline.descriptor_id,
        test_descriptor_id=test.descriptor_id,
        torque_rms_delta_nm=test.torque_rms_nm - baseline.torque_rms_nm,
        effort_work_proxy_delta=(
            test.steering_effort_work_proxy - baseline.steering_effort_work_proxy
        ),
        correction_density_delta_per_s=(
            test.correction_density_per_s - baseline.correction_density_per_s
        ),
    )


__all__ = [
    "STEERING_WORKLOAD_CONTRACT",
    "TRANSIENT_RESPONSE_CONTRACT",
    "analyze_steering_workload",
    "analyze_transient_response",
    "compare_steering_workload",
]
