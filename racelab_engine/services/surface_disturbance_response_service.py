"""Aggregate independent physical-lap disturbance response episodes."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from statistics import median
from typing import Any

import polars as pl

from racelab_engine.analysis.surface_disturbance_response import (
    FORMULA_VERSION,
    SURFACE_DISTURBANCE_SETTLING_CONTRACT,
    analyze_surface_disturbance_episode,
)
from racelab_engine.models.evidence import (
    BlockerPhysicalScope,
    EngineeringBlocker,
    EngineeringBlockerSeverity,
    EngineeringBlockTarget,
    EvidenceState,
)
from racelab_engine.models.surface_disturbance_response import (
    EmpiricalNoiseFloor,
    PhysicalLapScope,
    SurfaceDisturbanceEpisodeSignature,
    SurfaceDisturbanceSettlingReport,
    SurfaceDisturbanceSettlingSignature,
)


@dataclass(frozen=True)
class SurfaceDisturbanceTelemetryInput:
    data: pl.DataFrame | Sequence[Mapping[str, Any]]
    scope: PhysicalLapScope
    expected_sample_rate_hz: float | None


def _scope_ref(scope: PhysicalLapScope | None) -> BlockerPhysicalScope | None:
    if scope is None:
        return None
    return BlockerPhysicalScope(
        run_id=scope.run_id,
        lap_number=scope.lap_number,
        lap_pct_start=scope.lap_pct_start,
        lap_pct_end=scope.lap_pct_end,
    )


def _blocker(
    *,
    code: str,
    message: str,
    recovery: str,
    scope: PhysicalLapScope | None,
    artifacts: tuple[str, ...] = (),
    severity: EngineeringBlockerSeverity = EngineeringBlockerSeverity.BLOCKER,
    evidence_state: EvidenceState = EvidenceState.UNAVAILABLE,
    blocks: tuple[EngineeringBlockTarget, ...] = (
        EngineeringBlockTarget.OBSERVATION,
        EngineeringBlockTarget.MECHANISM,
        EngineeringBlockTarget.SETUP_ATTRIBUTION,
    ),
) -> EngineeringBlocker:
    source_artifacts = artifacts or (
        (scope.source_artifact_id,) if scope is not None else ()
    )
    return EngineeringBlocker(
        code=code,
        severity=severity,
        scope="surface_disturbance_settling",
        blocks=blocks,
        message=message,
        evidence_state=evidence_state,
        source_artifact_ids=tuple(dict.fromkeys(source_artifacts)),
        physical_scope=_scope_ref(scope),
        recovery=recovery,
    )


def _dedupe(blockers: Sequence[EngineeringBlocker]) -> tuple[EngineeringBlocker, ...]:
    exact: list[EngineeringBlocker] = []
    seen: set[str] = set()
    for blocker in blockers:
        identity = blocker.model_dump_json()
        if identity not in seen:
            seen.add(identity)
            exact.append(blocker)
    return tuple(exact)


def _unavailable(
    blockers: Sequence[EngineeringBlocker],
) -> SurfaceDisturbanceSettlingReport:
    exact = _dedupe(blockers)
    return SurfaceDisturbanceSettlingReport(
        status="unavailable",
        contract=SURFACE_DISTURBANCE_SETTLING_CONTRACT,
        blockers=exact,
        required_measurements=tuple(dict.fromkeys(item.recovery for item in exact)),
    )


def _aggregate_noise(
    episodes: Sequence[SurfaceDisturbanceEpisodeSignature],
) -> tuple[EmpiricalNoiseFloor, ...]:
    by_channel: dict[str, list[EmpiricalNoiseFloor]] = defaultdict(list)
    for episode in episodes:
        for floor in episode.noise_floor_by_channel:
            by_channel[floor.channel].append(floor)
    return tuple(
        EmpiricalNoiseFloor(
            channel=channel,
            unit=values[0].unit,
            baseline_sample_count=sum(item.baseline_sample_count for item in values),
            baseline_center=float(median(item.baseline_center for item in values)),
            robust_noise_floor=float(
                median(item.robust_noise_floor for item in values)
            ),
            observed_baseline_excursion=float(
                median(item.observed_baseline_excursion for item in values)
            ),
            onset_excursion_threshold=float(
                median(item.onset_excursion_threshold for item in values)
            ),
        )
        for channel, values in sorted(by_channel.items())
    )


def build_surface_disturbance_settling_report(
    inputs: Sequence[SurfaceDisturbanceTelemetryInput],
) -> SurfaceDisturbanceSettlingReport:
    """Build one repeated response signature without setup or cause authority."""

    if not inputs:
        return _unavailable(
            [
                _blocker(
                    code="INSUFFICIENT_INDEPENDENT_EPISODES",
                    message="No physical-lap disturbance episodes were supplied.",
                    recovery="Capture at least two distinct eligible laps through the same physical window.",
                    scope=None,
                )
            ]
        )

    first = inputs[0].scope
    physical_context = {
        (
            item.scope.track_identity,
            item.scope.build_identity,
            item.scope.setup_id,
            item.scope.context_id,
            item.scope.phase,
            item.scope.lap_pct_start,
            item.scope.lap_pct_end,
        )
        for item in inputs
    }
    if len(physical_context) != 1:
        return _unavailable(
            [
                _blocker(
                    code="PHYSICAL_EPISODE_SCOPE_MISMATCH",
                    message=(
                        "Disturbance repetitions do not share one exact track/build/setup/"
                        "context/phase/position scope."
                    ),
                    recovery="Repeat the event in the same exact physical and vehicle context.",
                    scope=first,
                    artifacts=tuple(item.scope.source_artifact_id for item in inputs),
                )
            ]
        )

    blockers: list[EngineeringBlocker] = []
    candidate_episodes: list[SurfaceDisturbanceEpisodeSignature] = []
    for item in inputs:
        result = analyze_surface_disturbance_episode(
            item.data,
            scope=item.scope,
            expected_sample_rate_hz=item.expected_sample_rate_hz,
        )
        blockers.extend(result.blockers)
        if result.episode is not None:
            candidate_episodes.append(result.episode)

    source_unit_counts = Counter(
        item.independence_unit_id for item in candidate_episodes
    )
    duplicate_source_units = {
        unit for unit, count in source_unit_counts.items() if count > 1
    }
    content_unit_counts = Counter(
        item.telemetry_content_unit_id for item in candidate_episodes
    )
    duplicate_content_units = {
        unit for unit, count in content_unit_counts.items() if count > 1
    }
    if duplicate_source_units:
        duplicate_artifacts = tuple(
            item.scope.source_artifact_id
            for item in candidate_episodes
            if item.independence_unit_id in duplicate_source_units
        )
        blockers.append(
            _blocker(
                code="DUPLICATE_SOURCE_FILE_EPISODE",
                message=(
                    "The same verified source-file SHA-256/lap was supplied more than "
                    "once and cannot increase repetition."
                ),
                recovery="Supply distinct physical laps; renamed or re-imported aliases do not count.",
                scope=first,
                artifacts=duplicate_artifacts,
                severity=EngineeringBlockerSeverity.WARNING,
                evidence_state=EvidenceState.NEEDS_CONFIRMATION,
                blocks=(
                    EngineeringBlockTarget.COMPARISON,
                    EngineeringBlockTarget.MECHANISM,
                    EngineeringBlockTarget.SETUP_ATTRIBUTION,
                ),
            )
        )
    if duplicate_content_units:
        duplicate_artifacts = tuple(
            item.scope.source_artifact_id
            for item in candidate_episodes
            if item.telemetry_content_unit_id in duplicate_content_units
        )
        blockers.append(
            _blocker(
                code="DUPLICATE_TELEMETRY_CONTENT_EPISODE",
                message=(
                    "Identical ordered telemetry content was supplied for the same lap "
                    "under multiple recording labels and cannot increase repetition."
                ),
                recovery="Supply a distinct physical lap from a verified source recording.",
                scope=first,
                artifacts=duplicate_artifacts,
                severity=EngineeringBlockerSeverity.WARNING,
                evidence_state=EvidenceState.NEEDS_CONFIRMATION,
                blocks=(
                    EngineeringBlockTarget.COMPARISON,
                    EngineeringBlockTarget.MECHANISM,
                    EngineeringBlockTarget.SETUP_ATTRIBUTION,
                ),
            )
        )
    episodes = [
        item
        for item in candidate_episodes
        if item.independence_unit_id not in duplicate_source_units
        and item.telemetry_content_unit_id not in duplicate_content_units
    ]

    episodes.sort(
        key=lambda item: (
            item.scope.source_file_sha256,
            item.telemetry_content_sha256,
            item.scope.lap_number,
            item.episode_id,
        )
    )
    if len(episodes) < SURFACE_DISTURBANCE_SETTLING_CONTRACT.minimum_repetitions:
        blockers.append(
            _blocker(
                code="INSUFFICIENT_INDEPENDENT_EPISODES",
                message=(
                    f"Only {len(episodes)} independent qualified response episode(s) "
                    "remain; two are required."
                ),
                recovery="Capture at least two distinct eligible physical laps with complete clock/yaw/shock response.",
                scope=first,
                artifacts=tuple(item.scope.source_artifact_id for item in inputs),
            )
        )
        return _unavailable(blockers)

    onsets = [item.disturbance_onset_lap_pct for item in episodes]
    onset_span = max(onsets) - min(onsets)
    # Three observed position samples is an instrument-resolution allowance, not
    # a nominal track or vehicle constant.
    repetition_tolerance = 3.0 * max(
        item.physical_sample_resolution_pct for item in episodes
    )
    if onset_span > repetition_tolerance:
        blockers.append(
            _blocker(
                code="DISTURBANCE_POSITION_NOT_REPEATED",
                message=(
                    f"Observed onsets span {onset_span:.6g}% lap distance, beyond the "
                    f"{repetition_tolerance:.6g}% resolution-derived tolerance."
                ),
                recovery="Repeat the pass until the disturbance response recurs at one physical location.",
                scope=first,
                artifacts=tuple(item.scope.source_artifact_id for item in inputs),
            )
        )
        return _unavailable(blockers)

    speeds = [item.median_speed_mps for item in episodes]
    all_speed_min = min(item.speed_min_mps for item in episodes)
    all_speed_max = max(item.speed_max_mps for item in episodes)
    source_artifacts = tuple(
        dict.fromkeys(item.scope.source_artifact_id for item in episodes)
    )
    source_file_sha256s = tuple(
        dict.fromkeys(item.scope.source_file_sha256 for item in episodes)
    )
    telemetry_content_sha256s = tuple(
        dict.fromkeys(item.telemetry_content_sha256 for item in episodes)
    )
    independence_units = tuple(item.independence_unit_id for item in episodes)
    clock_channels = tuple(
        dict.fromkeys(
            channel
            for episode in episodes
            for channel in episode.clock_source_channels
        )
    )
    identity = "|".join(
        (
            FORMULA_VERSION,
            first.track_identity,
            first.build_identity,
            first.setup_id,
            first.context_id,
            first.phase,
            f"{first.lap_pct_start:.12g}",
            f"{first.lap_pct_end:.12g}",
            *[item.episode_id for item in episodes],
        )
    )
    signature = SurfaceDisturbanceSettlingSignature(
        signature_id="surface-settling:"
        + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
        formula_version=FORMULA_VERSION,
        track_identity=first.track_identity,
        build_identity=first.build_identity,
        setup_id=first.setup_id,
        context_id=first.context_id,
        phase=first.phase,
        lap_pct_start=first.lap_pct_start,
        lap_pct_end=first.lap_pct_end,
        episodes=tuple(episodes),
        repetition_count=len(episodes),
        disturbance_onset_median_lap_pct=float(median(onsets)),
        disturbance_onset_span_pct=onset_span,
        physical_repetition_tolerance_pct=repetition_tolerance,
        median_speed_mps=float(median(speeds)),
        speed_min_mps=all_speed_min,
        speed_max_mps=all_speed_max,
        aggregate_noise_floor_by_channel=_aggregate_noise(episodes),
        source_artifact_ids=source_artifacts,
        source_file_sha256s=source_file_sha256s,
        telemetry_content_sha256s=telemetry_content_sha256s,
        independence_unit_ids=independence_units,
        source_channels=episodes[0].source_channels,
        clock_source_channels=clock_channels,
    )
    exact_blockers = _dedupe(blockers)
    return SurfaceDisturbanceSettlingReport(
        status="limited" if exact_blockers else "ready",
        contract=SURFACE_DISTURBANCE_SETTLING_CONTRACT,
        signature=signature,
        blockers=exact_blockers,
        required_measurements=tuple(
            dict.fromkeys(item.recovery for item in exact_blockers)
        ),
    )


__all__ = [
    "SurfaceDisturbanceTelemetryInput",
    "build_surface_disturbance_settling_report",
]
