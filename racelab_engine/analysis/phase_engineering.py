"""Phase-aware driver, corner-rotation, and aero-platform engineering systems."""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Iterable

from racelab_engine.analysis.comparison import interpolate_run_to_grid
from racelab_engine.analysis.evidence_contracts import (
    AnalysisEvidenceContract,
    EvidenceEvaluationInput,
    evaluate_evidence_contract,
)
from racelab_engine.analysis.p3_common import bounded_confidence
from racelab_engine.analysis.phase_engineering_contracts import (
    AERO_PLATFORM_WINDOW_CONTRACT,
    CORNER_ROTATION_CONTRACT,
    DRIVER_LINE_CONTRACT,
)
from racelab_engine.analysis.time_alignment import TimeAlignmentResult, nearest_sorted_index
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.phase_engineering import (
    AeroPlatformReport,
    CornerRotationReport,
    DriverLineReport,
    EngineeringSystemsResponse,
    PhaseMetric,
    PlatformSpeedBand,
)


_DRIVER_CHANNELS = [
    "lap_dist_pct_100", "session_time", "lap_dist_ft", "speed_mps", "speed_mph", "throttle_pct",
    "brake_pct", "steering_deg", "yaw_rate", "lat_accel", "lat", "lon",
    "curvature_1_per_m",
]
_PLATFORM_CHANNELS = [
    "session_time", "speed_mph", "speed_mps", "cfs_ride_height_in",
    "front_avg_rh_in", "rear_avg_rh_in", "center_rake_fs_in", "side_rake_in",
    "dynamic_pressure_psf", "cfs_risk_score", "lf_ride_height_in",
    "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in",
    "throttle_pct", "brake_pct", "long_accel",
]
_MIN_PHASE_BINS = 5


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _values(values: Iterable[float | None]) -> list[float]:
    return [value for item in values if (value := _finite(item)) is not None]


def _percentile(values: Iterable[float | None], fraction: float) -> float | None:
    ordered = sorted(_values(values))
    if not ordered:
        return None
    position = fraction * (len(ordered) - 1)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _mean(values: Iterable[float | None]) -> float | None:
    clean = _values(values)
    return sum(clean) / len(clean) if clean else None


def _coverage(values: Iterable[float | None]) -> float:
    items = list(values)
    return len(_values(items)) / len(items) if items else 0.0


def _smooth(values: list[float | None], radius: int = 2) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        window = _values(values[max(0, index - radius):index + radius + 1])
        result.append(median(window) if window else None)
    return result


def _wrapped_angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def _gps_points_m(
    lat: list[float | None],
    lon: list[float | None],
) -> list[tuple[float, float] | None]:
    if _coverage(lat) < 0.9 or _coverage(lon) < 0.9:
        return [None] * max(len(lat), len(lon))
    lat0 = median(_values(lat))
    lon0 = median(_values(lon))
    earth = 6_371_000.0
    return [
        (
            earth * math.radians(value_lon - lon0) * math.cos(math.radians(lat0)),
            earth * math.radians(value_lat - lat0),
        )
        if value_lat is not None and value_lon is not None else None
        for value_lat, value_lon in zip(lat, lon)
    ]


def _gps_geometry_healthy(rows: list[dict[str, Any]]) -> bool:
    lat = [_finite(row.get("lat")) for row in rows]
    lon = [_finite(row.get("lon")) for row in rows]
    points = [point for point in _gps_points_m(lat, lon) if point is not None]
    if len(points) < max(10, math.ceil(0.9 * len(rows))):
        return False
    extent = math.hypot(
        max(point[0] for point in points) - min(point[0] for point in points),
        max(point[1] for point in points) - min(point[1] for point in points),
    )
    path_length = sum(
        math.hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(points, points[1:])
    )
    return extent >= 20.0 and path_length >= 50.0


def _gps_curvature(channels: dict[str, list[float | None]]) -> list[float | None]:
    lat = channels.get("lat") or []
    lon = channels.get("lon") or []
    if _coverage(lat) < 0.9 or _coverage(lon) < 0.9:
        return [None] * max(len(lat), len(lon))
    points = _gps_points_m(lat, lon)
    headings: list[float | None] = [None]
    for previous, current in zip(points, points[1:]):
        if previous is None or current is None:
            headings.append(None)
            continue
        dx, dy = current[0] - previous[0], current[1] - previous[1]
        headings.append(math.atan2(dy, dx) if math.hypot(dx, dy) >= 0.25 else None)
    curvature: list[float | None] = [None]
    for index in range(1, len(points)):
        previous, current = points[index - 1], points[index]
        left_heading, right_heading = headings[index - 1], headings[index]
        if None in (previous, current, left_heading, right_heading):
            curvature.append(None)
            continue
        distance = math.hypot(current[0] - previous[0], current[1] - previous[1])  # type: ignore[index]
        curvature.append(_wrapped_angle(right_heading - left_heading) / distance if distance >= 0.25 else None)  # type: ignore[operator]
    return _smooth(curvature)


def _geometric_curvature(
    grid: list[float],
    channels: dict[str, list[float | None]],
    *,
    gps_geometry_healthy: bool,
) -> tuple[list[float | None], str]:
    direct = _smooth(channels.get("curvature_1_per_m") or [None] * len(grid))
    gps = _gps_curvature(channels) if gps_geometry_healthy else [None] * len(grid)
    direct_coverage = _coverage(direct)
    gps_coverage = _coverage(gps)
    direct_abs_p95 = _percentile([abs(value) if value is not None else None for value in direct], 0.95)
    gps_abs_median = _percentile([abs(value) if value is not None else None for value in gps], 0.5)
    gps_abs_p95 = _percentile([abs(value) if value is not None else None for value in gps], 0.95)
    direct_healthy = (
        direct_coverage >= 0.9
        and direct_abs_p95 is not None
        and 1e-6 < direct_abs_p95 <= 1.0
    )
    if direct_healthy and gps_coverage >= 0.9 and gps_abs_median is not None and gps_abs_p95 is not None:
        direct_abs_median = _percentile([abs(value) if value is not None else None for value in direct], 0.5)
        direct_healthy = bool(
            direct_abs_median is not None
            and direct_abs_p95 >= max(1e-6, gps_abs_median * 0.1)
            and direct_abs_median <= max(0.01, gps_abs_p95 * 10.0)
        )
    if direct_healthy:
        return direct, "direct_curvature"
    if gps_coverage >= 0.9:
        basis = "gps_fallback_direct_unhealthy" if direct_coverage >= 0.9 else "gps_derived"
        return gps, basis
    return [None] * len(grid), "unavailable"


def _aligned_test_grid(
    raw_test: dict[str, list[float | None]],
    alignment: TimeAlignmentResult,
) -> dict[str, list[float | None]]:
    grid = alignment.grid_pct
    result: dict[str, list[float | None]] = {}
    for channel, values in raw_test.items():
        aligned: list[float | None] = []
        for point in alignment.alignment:
            if point.is_gap or point.aligned_test_pct is None:
                aligned.append(None)
                continue
            index = nearest_sorted_index(grid, point.aligned_test_pct)
            aligned.append(values[index])
        result[channel] = aligned
    return result


def _paired_mae(left: list[float | None], right: list[float | None]) -> float | None:
    paired = [abs(test - baseline) for baseline, test in zip(left, right) if baseline is not None and test is not None]
    return sum(paired) / len(paired) if paired and len(paired) >= math.ceil(0.9 * max(len(left), len(right))) else None


def _line_deviations_m(
    baseline: dict[str, list[float | None]],
    test: dict[str, list[float | None]],
) -> list[float | None]:
    result: list[float | None] = []
    earth = 6_371_000.0
    for bl_lat, bl_lon, te_lat, te_lon in zip(baseline["lat"], baseline["lon"], test["lat"], test["lon"]):
        if None in (bl_lat, bl_lon, te_lat, te_lon):
            result.append(None)
            continue
        mean_lat = math.radians((bl_lat + te_lat) / 2)  # type: ignore[operator]
        dx = earth * math.radians(te_lon - bl_lon) * math.cos(mean_lat)  # type: ignore[operator]
        dy = earth * math.radians(te_lat - bl_lat)  # type: ignore[operator]
        result.append(math.hypot(dx, dy))
    return result


def _correction_count(values: list[float | None]) -> int:
    count = 0
    group: list[float] = []
    for value in [*values, None]:
        if value is not None:
            group.append(value)
            continue
        if len(group) >= 3:
            smoothed = _smooth(group, 2)
            last_sign = 0
            for left, right in zip(smoothed, smoothed[1:]):
                if left is None or right is None or abs(right - left) < 0.5:
                    continue
                sign = 1 if right - left > 0 else -1
                if last_sign and sign != last_sign:
                    count += 1
                last_sign = sign
        group = []
    return count


def _coasting_distance_ft(
    throttle: list[float | None],
    brake: list[float | None],
    distance: list[float | None],
) -> float | None:
    if len(_values(distance)) < 2:
        return None
    total = 0.0
    for index in range(1, len(distance)):
        left, right = distance[index - 1], distance[index]
        if None in (left, right) or right <= left:  # type: ignore[operator]
            continue
        if (
            throttle[index] is not None
            and brake[index] is not None
            and throttle[index] < 10.0
            and brake[index] < 3.0
        ):
            total += right - left  # type: ignore[operator]
    return total


def _brake_release_span_pct(brake: list[float | None], positions: list[float]) -> float | None:
    spans: list[float] = []
    start = 0
    while start < len(brake):
        while start < len(brake) and brake[start] is None:
            start += 1
        end = start
        while end < len(brake) and brake[end] is not None:
            end += 1
        clean = [(index, brake[index]) for index in range(start, end) if brake[index] is not None]
        if clean:
            peak_index, peak = max(clean, key=lambda item: item[1])
            if peak is not None and peak >= 10.0:
                release = next((index for index in range(peak_index + 1, end) if brake[index] is not None and brake[index] < 3.0), None)
                if release is not None:
                    spans.append(positions[release] - positions[peak_index])
        start = max(end, start + 1)
    return median(spans) if spans else None


def _masked(values: list[float | None], indices: list[int]) -> list[float | None]:
    selected = set(indices)
    return [value if index in selected else None for index, value in enumerate(values)]


def _gate(
    contract: AnalysisEvidenceContract,
    usable_channels: set[str],
    *,
    eligible_laps: bool,
    alignment: TimeAlignmentResult,
    repetitions: int,
    setup_change_isolated: bool,
    sim_integrity_clear: bool | None,
    sim_integrity_confidence_cap: float,
) -> EngineGate:
    phase_bins = sum(
        1 for phase in alignment.phases
        if (phase.end_pct - phase.start_pct) >= 0.4 and phase.phase not in {"unknown", "pit", "reset"}
    )
    evaluation = evaluate_evidence_contract(
        contract,
        EvidenceEvaluationInput(
            usable_channels=frozenset(usable_channels),
            condition_results={
                "eligible_laps": eligible_laps,
                "physical_alignment": (
                    alignment.time_delta_complete
                    and alignment.coverage_fraction >= 0.9
                    and alignment.local_alignment_confidence >= 0.55
                ),
                "phase_coverage": phase_bins > 0,
            },
            blocker_results={
                "junk_lap_context": not eligible_laps,
                "sample_integrity_failure": (
                    not alignment.time_delta_complete or sim_integrity_clear is not True
                ),
                "unisolated_setup_change": not setup_change_isolated,
            },
            repetitions=repetitions,
        ),
    )
    return EngineGate(
        contract_key=evaluation.contract_key,
        eligible=evaluation.eligible,
        confidence_cap=min(
            evaluation.confidence_cap,
            bounded_confidence(sim_integrity_confidence_cap),
        ),
        blocker_reasons=[blocker.message for blocker in evaluation.blockers],
        needed_measurements=[measurement.instruction for measurement in evaluation.needed_measurements],
    )


def _blocked_conclusion(key: str, gate: EngineGate) -> EngineeringConclusion:
    return EngineeringConclusion(
        key=key,
        summary="Analysis blocked by its evidence contract.",
        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        confidence_score=0.0,
        blocker_reasons=gate.blocker_reasons or ["Required evidence is unavailable."],
    )


def _phase_indices(phases: list[str | None]) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for index, phase in enumerate(phases):
        if phase not in {None, "unknown", "pit", "reset"}:
            result.setdefault(phase, []).append(index)
    return result


def _driver_report(
    baseline: dict[str, list[float | None]],
    test: dict[str, list[float | None]],
    curvature_baseline: list[float | None],
    curvature_test: list[float | None],
    alignment: TimeAlignmentResult,
    gate: EngineGate,
    curvature_source_channels: list[str],
) -> DriverLineReport:
    if not gate.eligible:
        return DriverLineReport(gate=gate, conclusions=[_blocked_conclusion("driver_execution_similarity", gate)])
    grid = alignment.grid_pct
    line = _line_deviations_m(baseline, test)
    throttle_mae = _paired_mae(baseline["throttle_pct"], test["throttle_pct"])
    brake_mae = _paired_mae(baseline["brake_pct"], test["brake_pct"])
    steering_mae = _paired_mae(baseline["steering_deg"], test["steering_deg"])
    line_median = _percentile(line, 0.5)
    line_p95 = _percentile(line, 0.95)
    similarity_available = all(
        metric is not None
        for metric in (line_median, throttle_mae, brake_mae, steering_mae)
    )
    changed = (
        any((
            line_median > 1.5,
            throttle_mae > 4.0,
            brake_mae > 3.0,
            steering_mae > 1.5,
        ))
        if similarity_available
        else None
    )
    metrics: list[PhaseMetric] = []
    for phase, indices in _phase_indices(alignment.phase_by_position).items():
        if len(indices) < _MIN_PHASE_BINS:
            continue
        paired = [
            index
            for index in indices
            if all(
                values[index] is not None
                for values in (
                    baseline["speed_mps"], test["speed_mps"],
                    baseline["throttle_pct"], test["throttle_pct"],
                    baseline["brake_pct"], test["brake_pct"],
                    baseline["steering_deg"], test["steering_deg"],
                    curvature_baseline, curvature_test,
                )
            )
        ]
        coverage = len(paired) / len(indices)
        if coverage < 0.9:
            continue
        def _demand(steering: list[float | None], curvature: list[float | None]) -> float | None:
            values = [
                abs(steering[index]) * 0.001 / abs(curvature[index])
                for index in indices
                if steering[index] is not None and curvature[index] is not None and abs(curvature[index]) >= 0.0005
            ]
            return median(values) if values else None
        def _min_speed_position(speed: list[float | None]) -> float | None:
            valid = [(index, speed[index]) for index in indices if speed[index] is not None]
            return grid[min(valid, key=lambda item: item[1])[0]] if valid else None
        metrics.append(PhaseMetric(
            phase=phase,
            coverage_fraction=round(coverage, 3),
            sample_bins=len(indices),
            metrics={
                "baseline_steering_demand_deg_per_0_001_curvature": _demand(baseline["steering_deg"], curvature_baseline),
                "test_steering_demand_deg_per_0_001_curvature": _demand(test["steering_deg"], curvature_test),
                "baseline_correction_count": _correction_count(_masked(baseline["steering_deg"], indices)),
                "test_correction_count": _correction_count(_masked(test["steering_deg"], indices)),
                "baseline_throttle_commitment_fraction": _mean([
                    None if baseline["throttle_pct"][index] is None
                    else 1.0 if baseline["throttle_pct"][index] >= 98.0 else 0.0
                    for index in indices
                ]),
                "test_throttle_commitment_fraction": _mean([
                    None if test["throttle_pct"][index] is None
                    else 1.0 if test["throttle_pct"][index] >= 98.0 else 0.0
                    for index in indices
                ]),
                "baseline_brake_release_span_pct": _brake_release_span_pct(_masked(baseline["brake_pct"], indices), grid),
                "test_brake_release_span_pct": _brake_release_span_pct(_masked(test["brake_pct"], indices), grid),
                "baseline_coasting_distance_ft": _coasting_distance_ft(
                    _masked(baseline["throttle_pct"], indices),
                    _masked(baseline["brake_pct"], indices),
                    _masked(baseline["lap_dist_ft"], indices),
                ),
                "test_coasting_distance_ft": _coasting_distance_ft(
                    _masked(test["throttle_pct"], indices),
                    _masked(test["brake_pct"], indices),
                    _masked(test["lap_dist_ft"], indices),
                ),
                "baseline_min_speed_position_pct": _min_speed_position(baseline["speed_mps"]),
                "test_min_speed_position_pct": _min_speed_position(test["speed_mps"]),
            },
        ))
    support = [
        f"Throttle MAE {throttle_mae:.2f}% at matched positions." if throttle_mae is not None else "Throttle comparison unavailable.",
        f"Brake MAE {brake_mae:.2f}% at matched positions." if brake_mae is not None else "Brake comparison unavailable.",
        f"Steering MAE {steering_mae:.2f} deg at matched positions." if steering_mae is not None else "Steering comparison unavailable.",
    ]
    if line_median is not None:
        support.append(f"Median GPS line deviation was {line_median:.2f} m.")
    contradictions = (
        ["Paired driver similarity coverage was below 90%; missing values are not treated as matched execution."]
        if changed is None
        else ["Driver execution changed beyond at least one controlled-comparison threshold."]
        if changed
        else []
    )
    similarity_summary = (
        "Driver execution similarity is unavailable; setup attribution is blocked."
        if changed is None
        else "Driver execution changed materially; setup attribution is blocked."
        if changed
        else "Driver execution stayed inside comparison thresholds."
    )
    similarity_state = EvidenceState.BLOCKED_BY_CONTEXT if changed is None else EvidenceState.OBSERVED_CORRELATION
    conclusions = [
        EngineeringConclusion(
            key="driver_phase_metrics",
            summary=f"Calculated sustained driver metrics across {len(metrics)} engineering phases.",
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=min(gate.confidence_cap, alignment.local_alignment_confidence),
            source_channels=list(dict.fromkeys([
                "lap_dist_pct_100", "session_time", "speed_mps", "throttle_pct",
                "brake_pct", "steering_deg", "geometric_curvature_1_per_m",
                *curvature_source_channels, "lat", "lon",
            ])),
            supporting_evidence=support,
            contradicting_evidence=contradictions,
        ),
        EngineeringConclusion(
            key="driver_execution_similarity",
            summary=similarity_summary,
            evidence_state=similarity_state,
            confidence_score=(
                0.0 if changed is None
                else min(gate.confidence_cap, alignment.local_alignment_confidence)
            ),
            source_channels=(
                [] if changed is None
                else ["lap_dist_pct_100", "throttle_pct", "brake_pct", "steering_deg", "lat", "lon"]
            ),
            supporting_evidence=[] if changed is None else support,
            contradicting_evidence=contradictions,
            blocker_reasons=(
                ["Required paired driver-input or racing-line coverage is below 90%."]
                if changed is None else []
            ),
            recommendation=(
                "Repeat with continuous paired driver channels and racing line."
                if changed is None
                else "Repeat the same setup state with closer driver inputs and racing line."
                if changed
                else None
            ),
        ),
    ]
    return DriverLineReport(
        gate=gate,
        phase_metrics=metrics,
        line_deviation_median_m=line_median,
        line_deviation_p95_m=line_p95,
        throttle_mae_pct=throttle_mae,
        brake_mae_pct=brake_mae,
        steering_mae_deg=steering_mae,
        driver_execution_changed=changed,
        setup_attribution_allowed=changed is False,
        conclusions=conclusions,
    )


def _rotation_report(
    baseline: dict[str, list[float | None]],
    test: dict[str, list[float | None]],
    curvature_baseline: list[float | None],
    curvature_test: list[float | None],
    alignment: TimeAlignmentResult,
    gate: EngineGate,
    curvature_source_channels: list[str],
) -> CornerRotationReport:
    if not gate.eligible:
        return CornerRotationReport(gate=gate, conclusions=[_blocked_conclusion("rotation_phase_metrics", gate)])
    phase_metrics: list[PhaseMetric] = []
    signed_deltas: list[float] = []
    for phase, indices in _phase_indices(alignment.phase_by_position).items():
        if len(indices) < _MIN_PHASE_BINS:
            continue
        def _metrics(run: dict[str, list[float | None]], curvature: list[float | None]) -> dict[str, float | int | None]:
            expected = [
                run["speed_mps"][index] * curvature[index]
                if run["speed_mps"][index] is not None and curvature[index] is not None else None
                for index in indices
            ]
            yaw_error = [
                expected_value - run["yaw_rate"][index]
                if expected_value is not None and run["yaw_rate"][index] is not None else None
                for index, expected_value in zip(indices, expected)
            ]
            sideslip_rate_proxy = [
                run["lat_accel"][index] / max(run["speed_mps"][index], 1.0) - run["yaw_rate"][index]
                if None not in (run["lat_accel"][index], run["speed_mps"][index], run["yaw_rate"][index]) else None
                for index in indices
            ]
            steering_efficiency = [
                abs(curvature[index]) / math.radians(abs(run["steering_deg"][index]))
                if curvature[index] is not None and run["steering_deg"][index] is not None and abs(run["steering_deg"][index]) >= 1.0 else None
                for index in indices
            ]
            response_ratio = [
                run["yaw_rate"][index] / expected_value
                if expected_value is not None and abs(expected_value) >= 0.02 and run["yaw_rate"][index] is not None else None
                for index, expected_value in zip(indices, expected)
            ]
            return {
                "expected_yaw_rate_median_rad_s": _percentile(expected, 0.5),
                "sustained_yaw_error_median_rad_s": _percentile(yaw_error, 0.5),
                "sustained_yaw_error_p90_abs_rad_s": _percentile([abs(value) if value is not None else None for value in yaw_error], 0.9),
                "sideslip_rate_proxy_median_rad_s": _percentile(sideslip_rate_proxy, 0.5),
                "steering_efficiency_median_curvature_per_rad": _percentile(steering_efficiency, 0.5),
                "rotation_response_ratio_median": _percentile(response_ratio, 0.5),
                "correction_count": _correction_count(_masked(run["steering_deg"], indices)),
            }
        baseline_metrics = _metrics(baseline, curvature_baseline)
        test_metrics = _metrics(test, curvature_test)
        baseline_error = baseline_metrics["sustained_yaw_error_median_rad_s"]
        test_error = test_metrics["sustained_yaw_error_median_rad_s"]
        if isinstance(baseline_error, float) and isinstance(test_error, float):
            signed_deltas.append(test_error - baseline_error)
        paired_count = sum(
            all(
                values[index] is not None
                for values in (
                    curvature_baseline, curvature_test,
                    baseline["speed_mps"], test["speed_mps"],
                    baseline["yaw_rate"], test["yaw_rate"],
                    baseline["steering_deg"], test["steering_deg"],
                    baseline["lat_accel"], test["lat_accel"],
                )
            )
            for index in indices
        )
        coverage = paired_count / len(indices)
        if coverage < 0.9:
            continue
        phase_metrics.append(PhaseMetric(
            phase=phase,
            coverage_fraction=round(coverage, 3),
            sample_bins=len(indices),
            metrics={
                **{f"baseline_{key}": value for key, value in baseline_metrics.items()},
                **{f"test_{key}": value for key, value in test_metrics.items()},
            },
        ))
    support = [f"{len(phase_metrics)} sustained phases met at least 90% paired rotation coverage."]
    contradictions = []
    if signed_deltas and min(signed_deltas) < 0 < max(signed_deltas):
        contradictions.append("Yaw-error direction changed across phases; no single whole-corner balance label is justified.")
    conclusions = [
        EngineeringConclusion(
            key="rotation_phase_metrics",
            summary="Expected yaw and rotation response are calculated by sustained engineering phase.",
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=min(gate.confidence_cap, alignment.local_alignment_confidence),
            source_channels=[
                "lap_dist_pct_100", "speed_mps", "yaw_rate", "steering_deg",
                "lat_accel", "geometric_curvature_1_per_m", *curvature_source_channels,
            ],
            supporting_evidence=support,
            contradicting_evidence=contradictions,
        ),
        EngineeringConclusion(
            key="balance_signature_proxy",
            summary="Rotation and sideslip-rate behavior is a phase-local proxy, not a measured understeer gradient or sideslip angle.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            confidence_score=min(0.75, gate.confidence_cap, alignment.local_alignment_confidence),
            source_channels=[
                "speed_mps", "yaw_rate", "steering_deg", "lat_accel",
                "geometric_curvature_1_per_m", *curvature_source_channels,
            ],
            supporting_evidence=support,
            contradicting_evidence=contradictions,
        ),
    ]
    return CornerRotationReport(gate=gate, phase_metrics=phase_metrics, conclusions=conclusions)


def _speed_bands(run: dict[str, list[float | None]]) -> list[PlatformSpeedBand]:
    specifications = (("under_100", 0.0, 100.0), ("100_to_150", 100.0, 150.0), ("150_plus", 150.0, None))
    result: list[PlatformSpeedBand] = []
    for label, minimum, maximum in specifications:
        indices = [
            index for index, speed in enumerate(run["speed_mph"])
            if speed is not None and speed >= minimum and (maximum is None or speed < maximum)
        ]
        if len(indices) < _MIN_PHASE_BINS:
            continue
        cfs = [run["cfs_ride_height_in"][index] for index in indices]
        result.append(PlatformSpeedBand(
            label=label,
            min_speed_mph=minimum,
            max_speed_mph=maximum,
            sample_bins=len(indices),
            metrics={
                "cfs_p05_in": _percentile(cfs, 0.05),
                "cfs_median_in": _percentile(cfs, 0.5),
                "cfs_p95_in": _percentile(cfs, 0.95),
                "front_median_in": _percentile([run["front_avg_rh_in"][index] for index in indices], 0.5),
                "rear_median_in": _percentile([run["rear_avg_rh_in"][index] for index in indices], 0.5),
                "rake_median_in": _percentile([run["center_rake_fs_in"][index] for index in indices], 0.5),
                "near_contact_proxy_duty": _mean([
                    None if run["cfs_ride_height_in"][index] is None
                    else 1.0 if run["cfs_ride_height_in"][index] <= 0.10 else 0.0
                    for index in indices
                ]),
            },
        ))
    return result


def _linear_slope(x: list[float | None], y: list[float | None]) -> float | None:
    paired = [(left, right) for left, right in zip(x, y) if left is not None and right is not None]
    if len(paired) < 10:
        return None
    mean_x = sum(item[0] for item in paired) / len(paired)
    mean_y = sum(item[1] for item in paired) / len(paired)
    denominator = sum((item[0] - mean_x) ** 2 for item in paired)
    return sum((item[0] - mean_x) * (item[1] - mean_y) for item in paired) / denominator if denominator > 1e-9 else None


def _rake_hysteresis_proxy(run: dict[str, list[float | None]]) -> float | None:
    """Return accel/decel rake separation compared inside matched pressure bands."""
    pressure = run["dynamic_pressure_psf"]
    rake = run["center_rake_fs_in"]
    speed = run["speed_mph"]
    direction: list[int | None] = [None]
    for left, right in zip(speed, speed[1:]):
        if left is None or right is None:
            direction.append(None)
        elif right - left > 0.05:
            direction.append(1)
        elif right - left < -0.05:
            direction.append(-1)
        else:
            direction.append(0)
    paired = [
        (q, height, state)
        for q, height, state in zip(pressure, rake, direction)
        if q is not None and height is not None and state in {-1, 1}
    ]
    if len(paired) < 30:
        return None
    lower = _percentile([item[0] for item in paired], 0.05)
    upper = _percentile([item[0] for item in paired], 0.95)
    if lower is None or upper is None or upper - lower <= 1e-6:
        return None
    differences: list[float] = []
    band_width = (upper - lower) / 5.0
    for band in range(5):
        band_lower = lower + band * band_width
        band_upper = lower + (band + 1) * band_width
        members = [
            item for item in paired
            if item[0] >= band_lower and (item[0] <= band_upper if band == 4 else item[0] < band_upper)
        ]
        accelerating = [item[1] for item in members if item[2] == 1]
        decelerating = [item[1] for item in members if item[2] == -1]
        if len(accelerating) >= 3 and len(decelerating) >= 3:
            differences.append(median(accelerating) - median(decelerating))
    return median(differences) if differences else None


def _settling_time_s(run: dict[str, list[float | None]], phases: list[str | None]) -> float | None:
    steady_values = [
        run["cfs_ride_height_in"][index]
        for index, phase in enumerate(phases)
        if phase in {"straight", "following_straight_carry"}
    ]
    target = _percentile(steady_values, 0.5)
    if target is None:
        return None
    tolerance = max(0.02, (_percentile(steady_values, 0.9) or target) - (_percentile(steady_values, 0.1) or target))
    transient_phases = {"brake_application", "threshold_braking", "brake_release", "transition", "bump_curb"}
    times: list[float] = []
    for index in range(1, len(phases) - 3):
        if phases[index - 1] not in transient_phases or phases[index] not in {"straight", "following_straight_carry"}:
            continue
        start_time = run["session_time"][index]
        if start_time is None:
            continue
        for candidate in range(index, len(phases) - 2):
            window = run["cfs_ride_height_in"][candidate:candidate + 3]
            if len(window) == 3 and all(value is not None and abs(value - target) <= tolerance for value in window):
                end_time = run["session_time"][candidate]
                if end_time is not None and end_time >= start_time:
                    times.append(end_time - start_time)
                break
    return median(times) if times else None


def _platform_summary(run: dict[str, list[float | None]], phases: list[str | None]) -> dict[str, float | None]:
    steady = [index for index, phase in enumerate(phases) if phase in {"straight", "following_straight_carry"}]
    transient = [index for index, phase in enumerate(phases) if phase in {"brake_application", "threshold_braking", "brake_release", "transition", "bump_curb"}]
    return {
        "cfs_p05_in": _percentile(run["cfs_ride_height_in"], 0.05),
        "cfs_median_in": _percentile(run["cfs_ride_height_in"], 0.5),
        "near_contact_proxy_duty": _mean([
            None if value is None else 1.0 if value <= 0.10 else 0.0
            for value in run["cfs_ride_height_in"]
        ]),
        "front_response_in_per_psf": _linear_slope(run["dynamic_pressure_psf"], run["front_avg_rh_in"]),
        "rear_response_in_per_psf": _linear_slope(run["dynamic_pressure_psf"], run["rear_avg_rh_in"]),
        "rake_hysteresis_proxy_in": _rake_hysteresis_proxy(run),
        "steady_cfs_median_in": _percentile([run["cfs_ride_height_in"][index] for index in steady], 0.5),
        "transient_cfs_p05_in": _percentile([run["cfs_ride_height_in"][index] for index in transient], 0.05),
        "settling_time_median_s": _settling_time_s(run, phases),
        "left_right_asymmetry_median_in": _percentile([abs(value) if value is not None else None for value in run["side_rake_in"]], 0.5),
    }


def _lap_platform_consistency(laps: list[list[dict[str, Any]]], grid: list[float]) -> dict[str, Any]:
    p05_values: list[float] = []
    rake_values: list[float] = []
    for rows in laps:
        data = interpolate_run_to_grid(rows, ["cfs_ride_height_in", "center_rake_fs_in"], grid)
        p05 = _percentile(data["cfs_ride_height_in"], 0.05)
        rake = _percentile(data["center_rake_fs_in"], 0.5)
        if p05 is not None:
            p05_values.append(p05)
        if rake is not None:
            rake_values.append(rake)
    return {
        "eligible_laps": len(laps),
        "cfs_p05_lap_median_in": _percentile(p05_values, 0.5),
        "cfs_p05_lap_range_in": max(p05_values) - min(p05_values) if len(p05_values) >= 2 else None,
        "rake_lap_range_in": max(rake_values) - min(rake_values) if len(rake_values) >= 2 else None,
        "evidence_state": "calculated" if len(p05_values) >= 3 else "needs_confirmation",
    }


def _platform_report(
    baseline: dict[str, list[float | None]],
    test: dict[str, list[float | None]],
    alignment: TimeAlignmentResult,
    gate: EngineGate,
    baseline_laps: list[list[dict[str, Any]]],
    test_laps: list[list[dict[str, Any]]],
) -> AeroPlatformReport:
    if not gate.eligible:
        return AeroPlatformReport(gate=gate, conclusions=[_blocked_conclusion("platform_operating_metrics", gate)])
    baseline_summary = _platform_summary(baseline, alignment.phase_by_position)
    test_summary = _platform_summary(test, alignment.phase_by_position)
    comparison = {
        f"{key}_delta": (
            test_summary[key] - value
            if value is not None and test_summary.get(key) is not None else None
        )
        for key, value in baseline_summary.items()
    }
    comparison.update({
        "selected_time_effect_s": alignment.selected_effect_s,
        "time_delta_complete": alignment.time_delta_complete,
        "tech_risk_is_proxy": True,
        "near_contact_threshold_in": 0.10,
    })
    faster = alignment.selected_effect_s is not None and alignment.selected_effect_s < 0
    duty_delta = comparison.get("near_contact_proxy_duty_delta")
    clearance_delta = comparison.get("cfs_p05_in_delta")
    platform_risk_worse = (
        (isinstance(duty_delta, float) and duty_delta > 0.01)
        or (isinstance(clearance_delta, float) and clearance_delta < -0.01)
    )
    risk_proxy_delta = None
    if isinstance(duty_delta, float) or isinstance(clearance_delta, float):
        duty_component = duty_delta if isinstance(duty_delta, float) else 0.0
        clearance_component = max(0.0, -clearance_delta * 10.0) if isinstance(clearance_delta, float) else 0.0
        risk_proxy_delta = duty_component + clearance_component
    comparison["tech_risk_proxy_delta"] = risk_proxy_delta
    time_effect = alignment.selected_effect_s
    comparison["time_platform_tradeoff"] = (
        "time_effect_unavailable" if time_effect is None
        else "faster_higher_platform_risk_proxy" if faster and platform_risk_worse
        else "faster_stable_or_lower_platform_risk_proxy" if faster
        else "slower_higher_platform_risk_proxy" if time_effect > 0 and platform_risk_worse
        else "slower_stable_or_lower_platform_risk_proxy" if time_effect > 0
        else "equal_time_higher_platform_risk_proxy" if platform_risk_worse
        else "equal_time_stable_or_lower_platform_risk_proxy"
    )
    support = [
        f"Baseline/test platform distributions use {len(alignment.grid_pct)} matched position bins.",
        "Near-contact duty is a ride-height threshold proxy, not measured track contact or tech legality.",
    ]
    contradictions = []
    if faster and platform_risk_worse:
        contradictions.append(
            "The test was faster in the selected trace while the clearance distribution or "
            "near-contact proxy duty indicated higher platform risk."
        )
    platform_sources = [
        "lap_dist_pct_100", "session_time", "speed_mph", "cfs_ride_height_in",
        "front_avg_rh_in", "rear_avg_rh_in", "center_rake_fs_in", "side_rake_in",
    ]
    if any(
        summary.get(key) is not None
        for summary in (baseline_summary, test_summary)
        for key in ("front_response_in_per_psf", "rear_response_in_per_psf", "rake_hysteresis_proxy_in")
    ):
        platform_sources.append("dynamic_pressure_psf")
    conclusions = [
        EngineeringConclusion(
            key="platform_operating_metrics",
            summary="Speed-conditioned platform distributions and transient/steady response were calculated at matched positions.",
            evidence_state=EvidenceState.CALCULATED,
            confidence_score=min(gate.confidence_cap, alignment.local_alignment_confidence),
            source_channels=platform_sources,
            supporting_evidence=support,
            contradicting_evidence=contradictions,
        ),
        EngineeringConclusion(
            key="platform_risk_proxy",
            summary="Observed time is weighed against platform and tech-risk proxies; no aerodynamic load or legality is measured.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            confidence_score=min(0.75, gate.confidence_cap, alignment.local_alignment_confidence),
            source_channels=["speed_mph", "cfs_ride_height_in", "center_rake_fs_in", "side_rake_in"],
            supporting_evidence=support,
            contradicting_evidence=contradictions,
        ),
    ]
    return AeroPlatformReport(
        gate=gate,
        setup_attribution_allowed=True,
        baseline_speed_bands=_speed_bands(baseline),
        test_speed_bands=_speed_bands(test),
        comparison_metrics={"baseline": baseline_summary, "test": test_summary, "delta": comparison},
        lap_consistency={
            "baseline": _lap_platform_consistency(baseline_laps, alignment.grid_pct),
            "test": _lap_platform_consistency(test_laps, alignment.grid_pct),
        },
        conclusions=conclusions,
    )


def analyze_phase_engineering_systems(
    baseline_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    alignment: TimeAlignmentResult,
    *,
    baseline_run_id: str,
    test_run_id: str,
    baseline_lap: int,
    test_lap: int,
    eligible_laps: bool,
    repetitions: int,
    setup_change_isolated: bool,
    sim_integrity_clear: bool | None,
    sim_integrity_confidence_cap: float,
    baseline_sim_integrity_status: str,
    test_sim_integrity_status: str,
    sim_integrity_warnings: list[str] | None = None,
    baseline_platform_laps: list[list[dict[str, Any]]] | None = None,
    test_platform_laps: list[list[dict[str, Any]]] | None = None,
) -> EngineeringSystemsResponse:
    grid = alignment.grid_pct
    channels = list(dict.fromkeys([*_DRIVER_CHANNELS, *_PLATFORM_CHANNELS]))
    baseline = interpolate_run_to_grid(baseline_rows, channels, grid)
    test_raw = interpolate_run_to_grid(test_rows, channels, grid)
    test = _aligned_test_grid(test_raw, alignment)
    baseline_gps_geometry_healthy = _gps_geometry_healthy(baseline_rows)
    test_gps_geometry_healthy = _gps_geometry_healthy(test_rows)
    curvature_baseline, baseline_curvature_basis = _geometric_curvature(
        grid,
        baseline,
        gps_geometry_healthy=baseline_gps_geometry_healthy,
    )
    curvature_test_raw, test_curvature_basis = _geometric_curvature(
        grid,
        test_raw,
        gps_geometry_healthy=test_gps_geometry_healthy,
    )
    curvature_test = _aligned_test_grid({"curvature": curvature_test_raw}, alignment)["curvature"]
    baseline["geometric_curvature_1_per_m"] = curvature_baseline
    test["geometric_curvature_1_per_m"] = curvature_test

    def _usable(data: dict[str, list[float | None]], names: Iterable[str]) -> set[str]:
        return {name for name in names if name in data and _coverage(data[name]) >= 0.9}

    common_usable = _usable(baseline, baseline) & _usable(test, test)
    if not (baseline_gps_geometry_healthy and test_gps_geometry_healthy):
        # Flatlined coordinates can have perfect numeric coverage while carrying
        # no racing-line information. Do not let presence masquerade as geometry.
        common_usable.difference_update({"lat", "lon"})
    paired_repetitions = 1
    platform_repetitions = max(
        1,
        min(len(baseline_platform_laps or []), len(test_platform_laps or [])),
    )
    driver_gate = _gate(
        DRIVER_LINE_CONTRACT,
        common_usable,
        eligible_laps=eligible_laps,
        alignment=alignment,
        repetitions=paired_repetitions,
        setup_change_isolated=setup_change_isolated,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
    )
    rotation_gate = _gate(
        CORNER_ROTATION_CONTRACT,
        common_usable,
        eligible_laps=eligible_laps,
        alignment=alignment,
        repetitions=paired_repetitions,
        setup_change_isolated=setup_change_isolated,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
    )
    platform_gate = _gate(
        AERO_PLATFORM_WINDOW_CONTRACT,
        common_usable,
        eligible_laps=eligible_laps,
        alignment=alignment,
        repetitions=platform_repetitions,
        setup_change_isolated=setup_change_isolated,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
    )
    _ = repetitions  # Legacy caller input cannot inflate evidence from the one selected pair.
    curvature_bases = {baseline_curvature_basis, test_curvature_basis}
    curvature_source_channels = (
        ["curvature_1_per_m"]
        if curvature_bases == {"direct_curvature"}
        else ["lat", "lon"]
        if curvature_bases <= {"gps_derived", "gps_fallback_direct_unhealthy"}
        else ["curvature_1_per_m", "lat", "lon"]
    )
    driver = _driver_report(
        baseline,
        test,
        curvature_baseline,
        curvature_test,
        alignment,
        driver_gate,
        curvature_source_channels,
    )
    rotation = _rotation_report(
        baseline,
        test,
        curvature_baseline,
        curvature_test,
        alignment,
        rotation_gate,
        curvature_source_channels,
    )
    if not driver.setup_attribution_allowed:
        driver_reason = (
            "Driver execution changed materially, so setup attribution is blocked."
            if driver.driver_execution_changed is True
            else "Paired driver execution similarity is unavailable, so setup attribution is blocked."
        )
        rotation = rotation.model_copy(update={
            "conclusions": [
                conclusion.model_copy(update={
                    "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                    "confidence_score": 0.0,
                    "source_channels": [],
                    "supporting_evidence": [],
                    "blocker_reasons": [driver_reason],
                    "recommendation": "Repeat with matched inputs and line before attributing rotation change to setup.",
                })
                for conclusion in rotation.conclusions
            ],
        })
    platform = _platform_report(
        baseline,
        test,
        alignment,
        platform_gate,
        baseline_platform_laps or [],
        test_platform_laps or [],
    )
    if not driver.setup_attribution_allowed:
        platform = platform.model_copy(update={"setup_attribution_allowed": False})
    warnings = [*alignment.warnings, *(sim_integrity_warnings or [])]
    if not (baseline_gps_geometry_healthy and test_gps_geometry_healthy):
        warnings.append(
            "GPS geometry is flatlined or lacks plausible lap extent; racing-line similarity "
            "and setup attribution are unavailable."
        )
    if "gps_fallback_direct_unhealthy" in curvature_bases:
        warnings.append(
            "Direct curvature failed its geometry health cross-check; GPS-derived curvature "
            "was used for expected-yaw calculations."
        )
    if not driver.setup_attribution_allowed:
        warnings.append(
            "Driver execution changed or could not be paired completely; rotation and platform "
            "observations must not be credited solely to setup."
        )
    return EngineeringSystemsResponse(
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        baseline_lap=baseline_lap,
        test_lap=test_lap,
        alignment_coverage_fraction=alignment.coverage_fraction,
        local_alignment_confidence=alignment.local_alignment_confidence,
        baseline_curvature_basis=baseline_curvature_basis,
        test_curvature_basis=test_curvature_basis,
        baseline_gps_geometry_healthy=baseline_gps_geometry_healthy,
        test_gps_geometry_healthy=test_gps_geometry_healthy,
        baseline_sim_integrity_status=baseline_sim_integrity_status,
        test_sim_integrity_status=test_sim_integrity_status,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
        driver_line=driver,
        corner_rotation=rotation,
        aero_platform=platform,
        warnings=warnings,
    )


__all__ = ["analyze_phase_engineering_systems"]
