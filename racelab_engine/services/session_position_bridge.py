"""Bridge qualified same-run opportunities into exact-session pace evidence.

The observation engine discovers repeatable windows inside the current run.
This module asks one narrower question: how did those exact physical windows
compare with the immediately preceding run in the caller-pinned session?

The output is descriptive only.  It deliberately carries no setup change,
cause, recommendation, or causal attribution.  Every failure returns an empty
tuple so session intelligence can fall back to its existing honest limits.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import Any

from racelab_engine.analysis.comparison import interpolate_run_to_grid
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.proximity_context import (
    ProximityState,
    classify_proximity_time_gap_window,
)
from racelab_engine.analysis.time_alignment import (
    TimeAlignmentResult,
    analyze_time_alignment,
    nearest_sorted_index,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    ObservationStatus,
    OpportunitySignature,
    RunObservationIntelligence,
)
from racelab_engine.models.session_intelligence import (
    AngularOperatingContextMatch,
    CategoricalOperatingContextMatch,
    ComparabilityDebt,
    NumericOperatingContextMatch,
    OperatingContextAttestation,
    PairedLapOperatingContext,
    PositionAlignedEvidence,
    ProximityOperatingContextMatch,
    RacingLineContextMatch,
    SessionPositionEvidenceResult,
)
from racelab_engine.services.import_service import read_telemetry_rows
from racelab_engine.services.session_intelligence_service import (
    position_evidence_sha256,
)
from racelab_engine.storage.repository import RaceLabRepository

_MINIMUM_ELIGIBLE_LAPS = 3
_MINIMUM_COVERAGE = 0.95
_MINIMUM_LOCAL_CONFIDENCE = 0.8
_MAXIMUM_LINE_MEDIAN_M = 1.5
_MAXIMUM_LINE_P95_M = 3.0

# Keep this projection explicit.  ``read_telemetry_rows`` verifies immutable
# cache ownership before returning a lap, while the narrow projection avoids a
# full universal-archive materialization for every pair.
_ALIGNMENT_COLUMNS = (
    "lap",
    "lap_number",
    "lap_dist_pct_100",
    "session_time",
    "lap_dist_ft",
    "speed_mps",
    "speed_mph",
    "fuel_level",
    "fuel_level_pct",
    "lf_tire_distance_m",
    "rf_tire_distance_m",
    "lr_tire_distance_m",
    "rr_tire_distance_m",
    "player_tire_compound",
    "air_temp",
    "track_temp",
    "wind_vel",
    "wind_dir",
    "car_distance_ahead_m",
    "car_distance_behind_m",
    "throttle_pct",
    "brake_pct",
    "steering_deg",
    "yaw_rate",
    "lat_accel",
    "long_accel",
    "vert_accel",
    "vert_accel_g",
    "lat",
    "lon",
    "alt",
    "on_pit_road",
    "enter_exit_reset_state",
    "lf_shock_defl_in",
    "rf_shock_defl_in",
    "lr_shock_defl_in",
    "rr_shock_defl_in",
    "lf_shock_vel_in_s",
    "rf_shock_vel_in_s",
    "lr_shock_vel_in_s",
    "rr_shock_vel_in_s",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
    "cfs_ride_height_in",
)

_ALIGNMENT_METHOD_CHANNELS: Mapping[str, tuple[str, ...]] = {
    "lap_percentage": ("lap_dist_pct_100", "session_time"),
    "bounded_circular_boundary": ("lap_dist_pct_100", "session_time"),
    "gps_geometry": ("lat", "lon"),
    "track_distance_geometry": ("lap_dist_ft",),
    "yaw_curvature": ("yaw_rate",),
    "road_profile": (
        "vert_accel",
        "lf_shock_defl_in",
        "rf_shock_defl_in",
        "lr_shock_defl_in",
        "rr_shock_defl_in",
        "lf_ride_height_in",
        "rf_ride_height_in",
        "lr_ride_height_in",
        "rr_ride_height_in",
        "cfs_ride_height_in",
    ),
    "repeatable_bump_anchor": (
        "vert_accel",
        "lf_shock_defl_in",
        "rf_shock_defl_in",
        "lr_shock_defl_in",
        "rr_shock_defl_in",
    ),
    "braking_onset_anchor": ("brake_pct",),
    "apex_curvature_anchor": ("steering_deg",),
}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_eligible_laps(overview: Any, run_id: str) -> tuple[LapSummary, ...] | None:
    if (
        overview is None
        or overview.run_id != run_id
        or overview.session.run_id != run_id
        or any(
            str(warning).casefold().startswith("evidence integrity:")
            for warning in overview.warnings
        )
    ):
        return None
    selected = tuple(sorted(eligible_laps(overview.laps), key=lambda lap: lap.lap_number))
    if (
        len(selected) < _MINIMUM_ELIGIBLE_LAPS
        or any(lap.run_id != run_id for lap in selected)
        or len({lap.lap_number for lap in selected}) != len(selected)
    ):
        return None
    return selected


def _session_pair(
    current_run_id: str,
    ordered_session_run_ids: Sequence[str],
) -> tuple[str, str] | None:
    ordered = tuple(ordered_session_run_ids)
    if (
        not current_run_id
        or current_run_id != current_run_id.strip()
        or not ordered
        or any(
            not isinstance(run_id, str)
            or not run_id
            or run_id != run_id.strip()
            for run_id in ordered
        )
        or len(set(ordered)) != len(ordered)
        or current_run_id not in ordered
    ):
        return None
    current_index = ordered.index(current_run_id)
    if current_index == 0:
        return None
    return ordered[current_index - 1], current_run_id


def _observation_signatures(
    current_run_id: str,
    observations: RunObservationIntelligence,
    current_laps: Sequence[LapSummary],
    current_setup_id: str | None,
) -> tuple[OpportunitySignature, ...] | None:
    report = observations.opportunity_signatures
    canonical_lap_numbers = tuple(lap.lap_number for lap in current_laps)
    if (
        observations.run_id != current_run_id
        or observations.setup_id is None
        or observations.setup_id != current_setup_id
        or report.status is not ObservationStatus.READY
        or report.run_id != current_run_id
        or report.setup_id != observations.setup_id
        or report.eligible_lap_numbers != canonical_lap_numbers
        or report.eligible_lap_count != len(canonical_lap_numbers)
        or not report.signatures
    ):
        return None
    signatures = tuple(report.signatures)
    if (
        len({signature.signature_id for signature in signatures}) != len(signatures)
        or any(
            signature.run_id != current_run_id
            or signature.setup_id != current_setup_id
            or signature.eligible_lap_count != len(canonical_lap_numbers)
            for signature in signatures
        )
    ):
        return None
    return signatures


def _lap_rows(
    run_id: str,
    lap_number: int,
    *,
    data_dir: str | Path | None,
) -> list[dict[str, Any]] | None:
    rows = read_telemetry_rows(
        run_id,
        data_dir,
        lap=lap_number,
        columns=list(_ALIGNMENT_COLUMNS),
    )
    if len(rows) < 2:
        return None
    if any(row.get("lap") != lap_number for row in rows):
        return None
    positions = [_finite(row.get("lap_dist_pct_100")) for row in rows]
    times = [_finite(row.get("session_time")) for row in rows]
    if sum(value is not None for value in positions) < 2 or sum(
        value is not None for value in times
    ) < 2:
        return None
    return rows


def _window_rows(
    rows: Sequence[Mapping[str, Any]],
    start_pct: float,
    end_pct: float,
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if (position := _finite(row.get("lap_dist_pct_100"))) is not None
        and start_pct <= position <= end_pct
    ]


def _numeric_values(
    rows: Sequence[Mapping[str, Any]], channel: str
) -> tuple[list[float], float]:
    values = [value for row in rows if (value := _finite(row.get(channel))) is not None]
    return values, len(values) / len(rows) if rows else 0.0


def _numeric_context_match(
    channel: str,
    baseline_rows: Sequence[Mapping[str, Any]],
    test_rows: Sequence[Mapping[str, Any]],
    *,
    tolerance: float,
    maximum_span: float,
) -> NumericOperatingContextMatch | None:
    baseline, baseline_coverage = _numeric_values(baseline_rows, channel)
    test, test_coverage = _numeric_values(test_rows, channel)
    if (
        baseline_coverage < _MINIMUM_COVERAGE
        or test_coverage < _MINIMUM_COVERAGE
        or not baseline
        or not test
    ):
        return None
    try:
        return NumericOperatingContextMatch(
            channel=channel,
            baseline_range=(min(baseline), max(baseline)),
            test_range=(min(test), max(test)),
            baseline_coverage=round(baseline_coverage, 6),
            test_coverage=round(test_coverage, 6),
            tolerance=tolerance,
            maximum_within_lap_span=maximum_span,
        )
    except ValueError:
        return None


def _angular_context_match(
    baseline_rows: Sequence[Mapping[str, Any]],
    test_rows: Sequence[Mapping[str, Any]],
) -> AngularOperatingContextMatch | None:
    baseline, baseline_coverage = _numeric_values(baseline_rows, "wind_dir")
    test, test_coverage = _numeric_values(test_rows, "wind_dir")
    if (
        baseline_coverage < _MINIMUM_COVERAGE
        or test_coverage < _MINIMUM_COVERAGE
        or not baseline
        or not test
    ):
        return None

    def radians(value: float) -> float:
        return math.radians(value) if abs(value) > 2.0 * math.pi else value

    baseline_center = median(radians(value) for value in baseline)
    test_center = median(radians(value) for value in test)
    difference = abs((test_center - baseline_center + math.pi) % (2.0 * math.pi) - math.pi)
    try:
        return AngularOperatingContextMatch(
            baseline_median=baseline_center,
            test_median=test_center,
            absolute_delta_rad=difference,
            maximum_delta_rad=math.radians(20.0),
            baseline_coverage=round(baseline_coverage, 6),
            test_coverage=round(test_coverage, 6),
        )
    except ValueError:
        return None


def _categorical_context_match(
    baseline_rows: Sequence[Mapping[str, Any]],
    test_rows: Sequence[Mapping[str, Any]],
) -> CategoricalOperatingContextMatch | None:
    channel = "player_tire_compound"

    def values(rows: Sequence[Mapping[str, Any]]) -> tuple[list[str], float]:
        selected = [
            str(value).strip()
            for row in rows
            if (value := row.get(channel)) is not None and str(value).strip()
        ]
        return selected, len(selected) / len(rows) if rows else 0.0

    baseline, baseline_coverage = values(baseline_rows)
    test, test_coverage = values(test_rows)
    if (
        baseline_coverage < _MINIMUM_COVERAGE
        or test_coverage < _MINIMUM_COVERAGE
        or len(set(baseline)) != 1
        or len(set(test)) != 1
    ):
        return None
    try:
        return CategoricalOperatingContextMatch(
            baseline_value=baseline[0],
            test_value=test[0],
            baseline_coverage=round(baseline_coverage, 6),
            test_coverage=round(test_coverage, 6),
        )
    except ValueError:
        return None


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _line_context_match(
    result: TimeAlignmentResult,
    baseline_rows: Sequence[Mapping[str, Any]],
    test_rows: Sequence[Mapping[str, Any]],
) -> RacingLineContextMatch | None:
    if not result.grid_pct or len(result.alignment) != len(result.grid_pct):
        return None
    baseline = interpolate_run_to_grid(
        list(baseline_rows), ["lat", "lon"], result.grid_pct
    )
    test = interpolate_run_to_grid(list(test_rows), ["lat", "lon"], result.grid_pct)
    deviations: list[float] = []
    earth_radius_m = 6_371_000.0
    for index, point in enumerate(result.alignment):
        if point.is_gap or point.aligned_test_pct is None:
            continue
        test_index = nearest_sorted_index(result.grid_pct, point.aligned_test_pct)
        baseline_lat = baseline["lat"][index]
        baseline_lon = baseline["lon"][index]
        test_lat = test["lat"][test_index]
        test_lon = test["lon"][test_index]
        if None in (baseline_lat, baseline_lon, test_lat, test_lon):
            continue
        mean_lat = math.radians((baseline_lat + test_lat) / 2.0)  # type: ignore[operator]
        dx = earth_radius_m * math.radians(test_lon - baseline_lon) * math.cos(  # type: ignore[operator]
            mean_lat
        )
        dy = earth_radius_m * math.radians(test_lat - baseline_lat)  # type: ignore[operator]
        deviations.append(math.hypot(dx, dy))
    coverage = len(deviations) / len(result.grid_pct)
    if coverage < _MINIMUM_COVERAGE or not deviations:
        return None
    try:
        return RacingLineContextMatch(
            coverage_fraction=round(coverage, 6),
            median_deviation_m=median(deviations),
            p95_deviation_m=_percentile(deviations, 0.95),
            maximum_median_deviation_m=_MAXIMUM_LINE_MEDIAN_M,
            maximum_p95_deviation_m=_MAXIMUM_LINE_P95_M,
        )
    except ValueError:
        return None


def _proximity_context_match(
    baseline_rows: Sequence[Mapping[str, Any]],
    test_rows: Sequence[Mapping[str, Any]],
) -> ProximityOperatingContextMatch | None:
    baseline = classify_proximity_time_gap_window(baseline_rows)
    test = classify_proximity_time_gap_window(test_rows)
    if (
        baseline.state is not ProximityState.NO_NEARBY_CAR_REPORTED
        or test.state is not ProximityState.NO_NEARBY_CAR_REPORTED
        or baseline.coverage_fraction != 1.0
        or test.coverage_fraction != 1.0
    ):
        return None
    speed_channels = tuple(
        channel
        for channel in ("speed_mps", "speed_mph")
        if _numeric_values(baseline_rows, channel)[1] >= _MINIMUM_COVERAGE
        or _numeric_values(test_rows, channel)[1] >= _MINIMUM_COVERAGE
    )
    if not speed_channels:
        return None
    measured = (
        baseline.min_distance_ahead_m,
        baseline.min_distance_behind_m,
        test.min_distance_ahead_m,
        test.min_distance_behind_m,
        baseline.min_time_gap_ahead_s,
        baseline.min_time_gap_behind_s,
        test.min_time_gap_ahead_s,
        test.min_time_gap_behind_s,
    )
    if any(value is None for value in measured):
        return None
    return ProximityOperatingContextMatch(
        channels=(
            "car_distance_ahead_m",
            "car_distance_behind_m",
            *speed_channels,
        ),
        baseline_state=baseline.state.value,
        test_state=test.state.value,
        baseline_coverage=1.0,
        test_coverage=1.0,
        baseline_min_distance_ahead_m=baseline.min_distance_ahead_m,
        baseline_min_distance_behind_m=baseline.min_distance_behind_m,
        test_min_distance_ahead_m=test.min_distance_ahead_m,
        test_min_distance_behind_m=test.min_distance_behind_m,
        baseline_min_time_gap_ahead_s=baseline.min_time_gap_ahead_s,
        baseline_min_time_gap_behind_s=baseline.min_time_gap_behind_s,
        test_min_time_gap_ahead_s=test.min_time_gap_ahead_s,
        test_min_time_gap_behind_s=test.min_time_gap_behind_s,
        ahead_exclusion_seconds=baseline.ahead_exclusion_seconds or 1.5,
        behind_exclusion_seconds=baseline.behind_exclusion_seconds or 0.5,
    )


def _paired_context_match(
    baseline_lap_id: str,
    test_lap_id: str,
    signature: OpportunitySignature,
    result: TimeAlignmentResult,
    baseline_rows: Sequence[Mapping[str, Any]],
    test_rows: Sequence[Mapping[str, Any]],
) -> PairedLapOperatingContext | None:
    baseline_window = _window_rows(
        baseline_rows, signature.lap_pct_start, signature.lap_pct_end
    )
    test_window = _window_rows(test_rows, signature.lap_pct_start, signature.lap_pct_end)
    if len(baseline_window) < 2 or len(test_window) < 2:
        return None
    volume_fuel_present = any(
        _numeric_values(rows, "fuel_level")[0]
        for rows in (baseline_window, test_window)
    )
    fuel_channel = "fuel_level" if volume_fuel_present else "fuel_level_pct"
    fuel = _numeric_context_match(
        fuel_channel,
        baseline_window,
        test_window,
        tolerance=2.0,
        maximum_span=10.0,
    )
    air_temperature = _numeric_context_match(
        "air_temp", baseline_window, test_window, tolerance=5.0, maximum_span=5.0
    )
    track_temperature = _numeric_context_match(
        "track_temp", baseline_window, test_window, tolerance=5.0, maximum_span=8.0
    )
    wind_speed = _numeric_context_match(
        "wind_vel", baseline_window, test_window, tolerance=2.0, maximum_span=3.0
    )
    wind_direction = _angular_context_match(baseline_window, test_window)
    line = _line_context_match(result, baseline_rows, test_rows)
    proximity = _proximity_context_match(baseline_window, test_window)
    required = (
        fuel,
        air_temperature,
        track_temperature,
        wind_speed,
        wind_direction,
        line,
        proximity,
    )
    if any(item is None for item in required):
        return None
    tire_channels = (
        "lf_tire_distance_m",
        "rf_tire_distance_m",
        "lr_tire_distance_m",
        "rr_tire_distance_m",
    )
    matches = tuple(
        _numeric_context_match(
            channel,
            baseline_window,
            test_window,
            tolerance=1_000.0,
            maximum_span=5_000.0,
        )
        for channel in tire_channels
    )
    if any(match is None for match in matches):
        return None
    tire_distances = tuple(match for match in matches if match is not None)
    tire_compound = _categorical_context_match(baseline_window, test_window)
    if tire_compound is None:
        return None
    assert fuel is not None
    assert air_temperature is not None
    assert track_temperature is not None
    assert wind_speed is not None
    assert wind_direction is not None
    assert line is not None
    assert proximity is not None
    channels = tuple(
        dict.fromkeys(
            (
                fuel.channel,
                air_temperature.channel,
                track_temperature.channel,
                wind_speed.channel,
                wind_direction.channel,
                *(
                    match.channel
                    for match in tire_distances
                ),
                tire_compound.channel,
                *line.channels,
                *proximity.channels,
            )
        )
    )
    return PairedLapOperatingContext(
        baseline_lap_id=baseline_lap_id,
        test_lap_id=test_lap_id,
        fuel=fuel,
        air_temperature=air_temperature,
        track_temperature=track_temperature,
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        tire_distances=tire_distances,
        tire_compound=tire_compound,
        line=line,
        proximity=proximity,
        source_channels=channels,
    )


def _paired_window_delta(result: TimeAlignmentResult) -> float | None:
    coverage = _finite(result.coverage_fraction)
    confidence = _finite(result.local_alignment_confidence)
    if (
        coverage is None
        or coverage < _MINIMUM_COVERAGE
        or confidence is None
        or confidence < _MINIMUM_LOCAL_CONFIDENCE
        or not result.incremental_delta_s
    ):
        return None
    deltas = [_finite(value) for value in result.incremental_delta_s]
    delta_coverage = sum(value is not None for value in deltas) / len(deltas)
    if delta_coverage < _MINIMUM_COVERAGE:
        return None
    finite_deltas = [value for value in deltas if value is not None]
    return sum(finite_deltas) if finite_deltas else None


def _channel_has_value(rows: Sequence[Mapping[str, Any]], channel: str) -> bool:
    return any(_finite(row.get(channel)) is not None for row in rows)


def _result_channels(
    result: TimeAlignmentResult,
    baseline_rows: Sequence[Mapping[str, Any]],
    test_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    channels: set[str] = {"lap_dist_pct_100", "session_time"}
    for basis in result.incremental_basis:
        if basis == "reciprocal_speed_integration":
            channels.add("lap_dist_ft")
            for channel in ("speed_mph", "speed_mps"):
                if _channel_has_value(baseline_rows, channel) and _channel_has_value(
                    test_rows, channel
                ):
                    channels.add(channel)
        elif basis == "aligned_timing_boundaries":
            channels.add("session_time")
    for point in result.alignment:
        for method in point.methods:
            channels.update(_ALIGNMENT_METHOD_CHANNELS.get(method, ()))
    for effect in result.phase_effects:
        if effect.delta_s is not None:
            channels.update(effect.source_channels)
    # Do not publish a channel merely because a method can use it.  At least one
    # of the two exact traces must contain a finite value, and core timing inputs
    # must be present on both sides (already checked by ``_lap_rows``).
    channels = {
        channel
        for channel in channels
        if _channel_has_value(baseline_rows, channel)
        or _channel_has_value(test_rows, channel)
    }
    ordered = [channel for channel in _ALIGNMENT_COLUMNS if channel in channels]
    ordered.extend(sorted(channels - set(ordered)))
    return tuple(ordered)


def _build_signature_evidence(
    signature: OpportunitySignature,
    baseline_run_id: str,
    current_run_id: str,
    paired_laps: Sequence[tuple[LapSummary, LapSummary]],
    *,
    data_dir: str | Path | None,
) -> PositionAlignedEvidence | None:
    deltas: list[float] = []
    confidences: list[float] = []
    context_matches: list[PairedLapOperatingContext] = []
    source_channels: set[str] = set()
    baseline_lap_ids: list[str] = []
    test_lap_ids: list[str] = []
    for baseline_lap, current_lap in paired_laps:
        baseline_rows = _lap_rows(
            baseline_run_id, baseline_lap.lap_number, data_dir=data_dir
        )
        current_rows = _lap_rows(current_run_id, current_lap.lap_number, data_dir=data_dir)
        if baseline_rows is None or current_rows is None:
            return None
        result = analyze_time_alignment(
            baseline_rows,
            current_rows,
            start_pct=signature.lap_pct_start,
            end_pct=signature.lap_pct_end,
        )
        delta = _paired_window_delta(result)
        confidence = _finite(result.local_alignment_confidence)
        channels = _result_channels(result, baseline_rows, current_rows)
        baseline_lap_id = f"{baseline_run_id}:{baseline_lap.lap_number}"
        test_lap_id = f"{current_run_id}:{current_lap.lap_number}"
        context_match = _paired_context_match(
            baseline_lap_id,
            test_lap_id,
            signature,
            result,
            baseline_rows,
            current_rows,
        )
        if (
            delta is None
            or confidence is None
            or not channels
            or context_match is None
        ):
            return None
        deltas.append(delta)
        confidences.append(confidence)
        source_channels.update(channels)
        source_channels.update(context_match.source_channels)
        context_matches.append(context_match)
        baseline_lap_ids.append(baseline_lap_id)
        test_lap_ids.append(test_lap_id)

    if len(deltas) < _MINIMUM_ELIGIBLE_LAPS:
        return None
    center = median(deltas)
    empirical_mad = median(abs(delta - center) for delta in deltas)
    if abs(center) <= max(empirical_mad, 1e-9):
        return None
    ordered_channels = tuple(
        channel for channel in _ALIGNMENT_COLUMNS if channel in source_channels
    )
    context_source_channels = tuple(
        channel
        for channel in _ALIGNMENT_COLUMNS
        if any(channel in match.source_channels for match in context_matches)
    )
    context_attestation = OperatingContextAttestation(
        pairs=tuple(context_matches),
        source_channels=context_source_channels,
    )
    identity_payload = {
        "signature_id": signature.signature_id,
        "baseline_run_id": baseline_run_id,
        "test_run_id": current_run_id,
        "baseline_lap_ids": baseline_lap_ids,
        "test_lap_ids": test_lap_ids,
        "start_pct": signature.lap_pct_start,
        "end_pct": signature.lap_pct_end,
        "phase": signature.phase,
        "delta_s": round(center, 6),
        "empirical_mad_s": round(empirical_mad, 6),
        "alignment_confidence": round(median(confidences), 3),
        "source_channels": ordered_channels,
        "context_match": context_attestation.model_dump(mode="json"),
    }
    evidence_id = "position_" + _sha256(identity_payload)[:24]
    draft = PositionAlignedEvidence(
        evidence_id=evidence_id,
        baseline_run_id=baseline_run_id,
        test_run_id=current_run_id,
        baseline_lap_ids=tuple(baseline_lap_ids),
        test_lap_ids=tuple(test_lap_ids),
        start_pct=signature.lap_pct_start,
        end_pct=signature.lap_pct_end,
        phase=signature.phase,
        delta_s=round(center, 6),
        empirical_noise_s=round(empirical_mad, 6),
        alignment_confidence=round(median(confidences), 3),
        source_channels=ordered_channels,
        provenance_sha256="0" * 64,
        context_match=context_attestation,
    )
    return PositionAlignedEvidence(
        **draft.model_dump(exclude={"provenance_sha256"}),
        provenance_sha256=position_evidence_sha256(draft),
    )


def build_session_position_evidence(
    current_run_id: str,
    ordered_session_run_ids: Sequence[str],
    current_observations: RunObservationIntelligence,
    *,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> tuple[PositionAlignedEvidence, ...]:
    """Build verified observations for current opportunity windows.

    Laps are paired chronologically after selecting the most recent equal-sized
    canonical cohorts.  Every pair and every signature must pass.  This
    all-or-nothing behavior prevents a partially readable cache or stale
    observation cohort from looking like a complete session comparison.
    """

    try:
        pair = _session_pair(current_run_id, ordered_session_run_ids)
        if pair is None:
            return ()
        baseline_run_id, test_run_id = pair
        repository = RaceLabRepository(db_path)
        baseline_overview = repository.get_overview(baseline_run_id)
        current_overview = repository.get_overview(test_run_id)
        baseline_laps = _canonical_eligible_laps(baseline_overview, baseline_run_id)
        current_laps = _canonical_eligible_laps(current_overview, current_run_id)
        if baseline_laps is None or current_laps is None:
            return ()
        current_setup = current_overview.setup_snapshot
        current_setup_id = (
            current_setup.setup_id
            if current_setup is not None and current_setup.run_id == current_run_id
            else None
        )
        signatures = _observation_signatures(
            current_run_id,
            current_observations,
            current_laps,
            current_setup_id,
        )
        if signatures is None:
            return ()
        pair_count = min(len(baseline_laps), len(current_laps))
        if pair_count < _MINIMUM_ELIGIBLE_LAPS:
            return ()
        paired_laps = tuple(
            zip(baseline_laps[-pair_count:], current_laps[-pair_count:])
        )
        evidence = tuple(
            _build_signature_evidence(
                signature,
                baseline_run_id,
                current_run_id,
                paired_laps,
                data_dir=data_dir,
            )
            for signature in signatures
        )
        if any(item is None for item in evidence):
            return ()
        verified = tuple(item for item in evidence if item is not None)
        if (
            len(verified) != len(signatures)
            or len({item.evidence_id for item in verified}) != len(verified)
            or any(item.provenance_sha256 != position_evidence_sha256(item) for item in verified)
        ):
            return ()
        return verified
    except (
        ArithmeticError,
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        TypeError,
        ValueError,
    ):
        # This is an optional evidence bridge on the intelligence read path.
        # Malformed storage, cache identity errors, and unexpected analysis
        # failures must withhold evidence rather than weaken the caller.
        return ()


def build_session_position_evidence_result(
    current_run_id: str,
    ordered_session_run_ids: Sequence[str],
    current_observations: RunObservationIntelligence,
    *,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> SessionPositionEvidenceResult:
    """Return evidence or one actionable typed comparability debt."""

    def debt(
        kind: str,
        reason: str,
        recovery: str,
        *,
        baseline_run_id: str | None = None,
        required_channels: tuple[str, ...] = (),
    ) -> SessionPositionEvidenceResult:
        digest = _sha256({
            "kind": kind,
            "baseline_run_id": baseline_run_id,
            "test_run_id": current_run_id,
            "reason": reason,
        })[:20]
        return SessionPositionEvidenceResult(
            current_run_id=current_run_id,
            comparability_debt=(ComparabilityDebt(
                debt_id=f"comparability:{digest}",
                kind=kind,
                baseline_run_id=baseline_run_id,
                test_run_id=current_run_id,
                reason=reason,
                required_channels=required_channels,
                recovery=recovery,
            ),),
        )

    try:
        pair = _session_pair(current_run_id, ordered_session_run_ids)
        if pair is None:
            return debt(
                "session_pair",
                "The current run has no immediately preceding run in the pinned session.",
                "Record or select a preceding compatible run before comparing position evidence.",
            )
        baseline_run_id, _test_run_id = pair
        repository = RaceLabRepository(db_path)
        baseline_overview = repository.get_overview(baseline_run_id)
        current_overview = repository.get_overview(current_run_id)
        baseline_laps = _canonical_eligible_laps(baseline_overview, baseline_run_id)
        current_laps = _canonical_eligible_laps(current_overview, current_run_id)
        if baseline_laps is None or current_laps is None:
            return debt(
                "eligible_laps",
                "One run lacks a canonical eligible-lap cohort.",
                "Record complete flying laps without pit, reset, incident, caution, or partial-lap contamination.",
                baseline_run_id=baseline_run_id,
            )
        setup = current_overview.setup_snapshot
        setup_id = setup.setup_id if setup is not None and setup.run_id == current_run_id else None
        signatures = _observation_signatures(
            current_run_id,
            current_observations,
            current_laps,
            setup_id,
        )
        if signatures is None:
            return debt(
                "observation_scope",
                "Current opportunity signatures are absent, blocked, or stale for this run/setup scope.",
                "Rebuild same-setup opportunity signatures from the current eligible laps.",
                baseline_run_id=baseline_run_id,
            )
        if min(len(baseline_laps), len(current_laps)) < _MINIMUM_ELIGIBLE_LAPS:
            return debt(
                "insufficient_repetition",
                "Fewer than three eligible laps are available in one comparison run.",
                "Record at least three eligible laps in both unchanged comparison runs.",
                baseline_run_id=baseline_run_id,
            )
        evidence = build_session_position_evidence(
            current_run_id,
            ordered_session_run_ids,
            current_observations,
            db_path=db_path,
            data_dir=data_dir,
        )
        if evidence:
            return SessionPositionEvidenceResult(
                current_run_id=current_run_id,
                evidence=evidence,
            )
        return debt(
            "operating_context",
            (
                "The exact lap pairs did not pass physical-position alignment, fuel, tire, "
                "weather, line, proximity, coverage, or beyond-noise signal gates."
            ),
            "Repeat the marked window with setup, fuel, tire state, weather, line, and nearby-car context matched.",
            baseline_run_id=baseline_run_id,
            required_channels=(
                "fuel_level",
                "air_temp",
                "track_temp",
                "wind_vel",
                "wind_dir",
                "lf_tire_distance_m",
                "rf_tire_distance_m",
                "lr_tire_distance_m",
                "rr_tire_distance_m",
                "player_tire_compound",
                "lat",
                "lon",
                "car_distance_ahead_m",
                "car_distance_behind_m",
                "speed_mps",
            ),
        )
    except (OSError, RuntimeError, sqlite3.Error, TypeError, ValueError):
        return debt(
            "integrity",
            "Position-comparison storage or telemetry integrity could not be verified.",
            "Re-import the exact source telemetry and rebuild its immutable cache identity.",
        )


__all__ = [
    "build_session_position_evidence",
    "build_session_position_evidence_result",
]
