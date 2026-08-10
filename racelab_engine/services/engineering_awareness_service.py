"""Deterministic state-frame, transition, episode, and clean-stint drift builders."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import math
from statistics import median
from typing import Any

from racelab_engine.models.engineering_awareness import (
    AnalyzerVersion,
    ChannelCoverage,
    ChannelRole,
    EngineeringStateFrame,
    EpisodeRepeatability,
    FrameChannelSemantic,
    MechanismEpisode,
    MechanismSignatureDefinition,
    StateDriftEntry,
    StateDriftFinding,
    StateDriftLedger,
    StateEvidenceReference,
    StateTransition,
    SubsystemStateReference,
    TemporalRelationship,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.engineering_context import ControlMutationEvent
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.models.observation_intelligence import (
    MechanismKind,
    MechanismObservation,
    MechanismObservationReport,
    ObservationCitation,
    ObservationStatus,
)
from racelab_engine.services.engineering_context_service import (
    detect_control_mutations,
    engineering_channel_role,
)


MECHANISM_SIGNATURE_DEFINITIONS = (
    MechanismSignatureDefinition(
        signature_key="center_front_response_chain",
        signature_version="p20.signature.v1",
        label="Center front-response evidence chain",
        valid_phases=("center", "apex_region"),
        required_mechanism_kinds=(
            MechanismKind.DRIVER_EXECUTION,
            MechanismKind.CORNER_ROTATION,
            MechanismKind.PLATFORM_RESPONSE,
        ),
        expected_patterns=(
            "Steering demand and yaw response are cited at the same physical center window.",
            "A producer-owned platform response is cited after or with driver input.",
            "Any time consequence is independently measured rather than inferred.",
        ),
        contradiction_patterns=(
            "Driver line or brake release changed materially in the same window.",
            "The yaw response repeats at low speed while platform state remains stable.",
            "Tire, traffic, or integrity context provides a stronger typed explanation.",
        ),
        mind_change_requirements=(
            "Repeat the exact center window on comparable eligible laps.",
            "Observe stable platform state while the yaw response persists.",
        ),
        measurement_requirements=(
            "Capture driver, yaw, platform, tire, traffic, and phase-time evidence together.",
        ),
    ),
    MechanismSignatureDefinition(
        signature_key="brake_release_rotation_chain",
        signature_version="p20.signature.v1",
        label="Brake-release and rotation evidence chain",
        valid_phases=("brake_release", "turn_in", "entry"),
        required_mechanism_kinds=(
            MechanismKind.BRAKING_RESPONSE,
            MechanismKind.CORNER_ROTATION,
        ),
        expected_patterns=(
            "Brake response precedes or co-occurs with the cited rotation response.",
            "Both producers cite the same exact entry scope.",
        ),
        contradiction_patterns=(
            "The rotation response persists with stable brake release.",
            "Driver line, traffic, or integrity context is not comparable.",
        ),
        mind_change_requirements=(
            "Repeat the entry window with matched brake release and driver line.",
        ),
        measurement_requirements=(
            "Capture brake pressure, processed brake, steering, yaw, speed, line, and traffic context.",
        ),
    ),
    MechanismSignatureDefinition(
        signature_key="exit_drive_response_chain",
        signature_version="p20.signature.v1",
        label="Exit drive-response evidence chain",
        valid_phases=("initial_throttle", "full_throttle_exit", "exit"),
        required_mechanism_kinds=(
            MechanismKind.DRIVER_EXECUTION,
            MechanismKind.POWERTRAIN_RESPONSE,
        ),
        expected_patterns=(
            "Throttle commitment precedes or co-occurs with the producer-owned powertrain response.",
            "Exit time consequence remains independently cited.",
        ),
        contradiction_patterns=(
            "Throttle timing or line changed materially.",
            "Traffic, tire, or simulator integrity context is blocked.",
        ),
        mind_change_requirements=(
            "Repeat the exact exit window with matched throttle and line context.",
        ),
        measurement_requirements=(
            "Capture throttle, wheel speed, engine speed, gearing, line, traffic, and phase time.",
        ),
    ),
)


@dataclass(frozen=True)
class EngineeringAwarenessEvidenceBuild:
    frames: tuple[EngineeringStateFrame, ...]
    transitions: tuple[StateTransition, ...]
    episodes: tuple[MechanismEpisode, ...]
    episode_observations: MechanismObservationReport
    control_mutations: tuple[ControlMutationEvent, ...] = ()
    blocker_reasons: tuple[str, ...] = ()


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _hash(prefix: str, *parts: object) -> str:
    encoded = "|".join(str(part) for part in parts).encode()
    return f"{prefix}:" + hashlib.sha256(encoded).hexdigest()[:24]


def _exact_rows(
    rows: Sequence[Mapping[str, Any]],
    citation: ObservationCitation,
) -> list[Mapping[str, Any]]:
    scoped = []
    for row in rows:
        lap = _finite(row.get("lap", row.get("lap_number")))
        pct = _finite(row.get("lap_dist_pct_100"))
        if pct is None:
            raw_pct = _finite(row.get("lap_dist_pct"))
            pct = raw_pct * 100.0 if raw_pct is not None and raw_pct <= 1.0 else raw_pct
        time = _finite(row.get("session_time"))
        if (
            lap == citation.lap_number
            and pct is not None
            and time is not None
            and citation.lap_pct_start <= pct <= citation.lap_pct_end
        ):
            scoped.append(row)
    return sorted(scoped, key=lambda row: _finite(row.get("session_time")) or 0.0)


def _frame_channel(
    channel: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[FrameChannelSemantic, ChannelCoverage]:
    values = [_finite(row.get(channel)) for row in rows]
    finite = [value for value in values if value is not None]
    coverage = len(finite) / len(rows) if rows else 0.0
    if not finite:
        semantic = ChannelUpdateSemantic.MISSING
    elif coverage < 0.9:
        semantic = ChannelUpdateSemantic.UNHEALTHY
    elif len({round(value, 8) for value in finite}) < 2:
        semantic = ChannelUpdateSemantic.CONSTANT
    else:
        semantic = ChannelUpdateSemantic.CONTINUOUS
    role = engineering_channel_role(channel)
    if channel == "lap_dist_pct_100":
        role = ChannelRole.POSITION_LOCATOR
    elif channel == "session_time":
        role = ChannelRole.PHASE_LOCATOR
    return (
        FrameChannelSemantic(channel=channel, role=role, update_semantic=semantic),
        ChannelCoverage(channel=channel, sample_coverage=coverage),
    )


_SUBSYSTEM_FIELD = {
    MechanismKind.DRIVER_EXECUTION: "driver",
    MechanismKind.BRAKING_RESPONSE: "braking",
    MechanismKind.CORNER_ROTATION: "rotation",
    MechanismKind.TIRE_STATE: "tires",
    MechanismKind.DAMPER_RESPONSE: "dampers",
    MechanismKind.PLATFORM_RESPONSE: "platform",
    MechanismKind.RESISTANCE_SCRUB_LIKE: "resistance",
    MechanismKind.POWERTRAIN_RESPONSE: "powertrain",
    MechanismKind.STINT_TREND: "stint",
    MechanismKind.SIM_INTEGRITY: "integrity",
}


def build_engineering_state_frames(
    observations: Sequence[MechanismObservation],
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    setup_id: str,
) -> tuple[tuple[EngineeringStateFrame, ...], tuple[str, ...]]:
    """Bind qualified producer citations to exact immutable telemetry windows."""
    frames: list[EngineeringStateFrame] = []
    blockers: list[str] = []
    for observation in observations:
        if not observation.qualified or observation.run_id != run_id:
            continue
        if observation.setup_id != setup_id:
            blockers.append(
                f"Observation {observation.observation_id} does not match the requested setup identity."
            )
            continue
        for index, citation in enumerate(observation.citations):
            if citation.run_id != run_id or citation.setup_id != setup_id:
                continue
            scoped = _exact_rows(rows, citation)
            channels = tuple(
                dict.fromkeys(
                    ("session_time", "lap_dist_pct_100", *citation.source_channels)
                )
            )
            semantics: list[FrameChannelSemantic] = []
            coverage: list[ChannelCoverage] = []
            for channel in channels:
                channel_semantic, channel_coverage = _frame_channel(channel, scoped)
                semantics.append(channel_semantic)
                coverage.append(channel_coverage)
            missing = [
                item.channel
                for item in semantics
                if item.update_semantic
                in {ChannelUpdateSemantic.MISSING, ChannelUpdateSemantic.UNHEALTHY}
            ]
            if len(scoped) < 3 or missing:
                blockers.append(
                    f"Observation {observation.observation_id} citation {index} cannot form a state frame: "
                    + (
                        "missing/unhealthy " + ", ".join(missing)
                        if missing
                        else "fewer than three samples"
                    )
                    + "."
                )
                continue
            times = [float(row["session_time"]) for row in scoped]
            evidence = StateEvidenceReference(
                evidence_id=_hash("state-evidence", observation.observation_id, index),
                artifact_id=observation.artifact_id,
                run_id=run_id,
                setup_id=setup_id,
                lap_number=citation.lap_number,
                lap_pct_start=citation.lap_pct_start,
                lap_pct_end=citation.lap_pct_end,
                lap_pct_peak=citation.lap_pct_peak,
                evidence_state=citation.evidence_state,
                source_channels=citation.source_channels,
                summary=observation.summary,
            )
            subsystem = SubsystemStateReference(
                artifact_id=observation.artifact_id,
                producer_id=observation.producer_id,
                mechanism=observation.mechanism,
                run_id=run_id,
                setup_id=setup_id,
                lap_number=citation.lap_number,
                lap_pct_start=citation.lap_pct_start,
                lap_pct_end=citation.lap_pct_end,
                lap_pct_peak=citation.lap_pct_peak,
            )
            context_id = (
                f"{setup_id}:{citation.phase}:"
                f"{citation.lap_pct_start:.4f}:{citation.lap_pct_end:.4f}"
            )
            frame_id = _hash(
                "state-frame",
                observation.producer_id,
                observation.artifact_id,
                run_id,
                citation.lap_number,
                citation.lap_pct_start,
                citation.lap_pct_end,
                index,
            )
            field_name = _SUBSYSTEM_FIELD.get(observation.mechanism)
            if field_name is None:
                blockers.append(
                    f"Observation {observation.observation_id} has no typed subsystem state field."
                )
                continue
            frames.append(
                EngineeringStateFrame(
                    frame_id=frame_id,
                    run_id=run_id,
                    lap_number=citation.lap_number,
                    setup_id=setup_id,
                    context_id=context_id,
                    independence_cluster_id=f"{run_id}:{setup_id}:same-stint",
                    lap_pct_start=citation.lap_pct_start,
                    lap_pct_end=citation.lap_pct_end,
                    lap_pct_peak=citation.lap_pct_peak,
                    session_time_start=min(times),
                    session_time_end=max(times),
                    phase=citation.phase,
                    source_artifact_ids=(observation.artifact_id,),
                    source_event_ids=(
                        (citation.event_id,) if citation.event_id else ()
                    ),
                    source_channels=channels,
                    channel_semantics=tuple(semantics),
                    coverage_by_channel=tuple(coverage),
                    analyzer_versions=(
                        AnalyzerVersion(
                            analyzer_id=observation.producer_id,
                            version="producer-artifact-bound-v1",
                        ),
                    ),
                    **{field_name: subsystem},
                    evidence_states=(citation.evidence_state,),
                    supporting_evidence=(evidence,),
                    blocker_reasons=(),
                )
            )
    return tuple(
        sorted(
            frames,
            key=lambda frame: (
                frame.lap_number,
                frame.session_time_start,
                frame.frame_id,
            ),
        )
    ), tuple(dict.fromkeys(blockers))


def build_state_transitions(
    frames: Sequence[EngineeringStateFrame],
) -> tuple[StateTransition, ...]:
    """Build temporal-only edges between backend frames sharing exact context."""
    grouped: dict[tuple[str, str, str], list[EngineeringStateFrame]] = defaultdict(list)
    for frame in frames:
        grouped[(frame.run_id, frame.setup_id, frame.context_id)].append(frame)
    transitions: list[StateTransition] = []
    for group in grouped.values():
        ordered = sorted(
            group,
            key=lambda frame: (
                frame.lap_number,
                frame.session_time_start,
                frame.frame_id,
            ),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if current.lap_number == previous.lap_number:
                relationship = (
                    TemporalRelationship.CO_OCCURS_WITH
                    if current.session_time_start <= previous.session_time_end
                    else TemporalRelationship.PRECEDES
                )
            else:
                relationship = TemporalRelationship.PERSISTS_INTO
            onset = previous.session_time_start
            peak = max(onset, current.session_time_start)
            supporting = tuple(
                dict.fromkeys(
                    (*previous.supporting_evidence, *current.supporting_evidence)
                )
            )
            artifacts = tuple(
                dict.fromkeys(
                    (*previous.source_artifact_ids, *current.source_artifact_ids)
                )
            )
            channels = tuple(
                dict.fromkeys((*previous.source_channels, *current.source_channels))
            )
            transitions.append(
                StateTransition(
                    transition_id=_hash(
                        "state-transition",
                        previous.frame_id,
                        current.frame_id,
                        relationship.value,
                    ),
                    run_id=previous.run_id,
                    setup_id=previous.setup_id,
                    context_id=previous.context_id,
                    from_frame_id=previous.frame_id,
                    to_frame_id=current.frame_id,
                    relationship=relationship,
                    onset_time=onset,
                    peak_time=peak,
                    onset_lap_pct=previous.lap_pct_peak,
                    peak_lap_pct=max(previous.lap_pct_peak, current.lap_pct_peak),
                    observed_lag_ms=max(
                        0.0, (peak - previous.session_time_end) * 1000.0
                    ),
                    source_artifact_ids=artifacts,
                    source_channels=channels,
                    evidence_state=EvidenceState.OBSERVED_CORRELATION,
                    supporting_evidence=supporting,
                )
            )
    return tuple(sorted(transitions, key=lambda item: item.transition_id))


def _mechanisms(frame: EngineeringStateFrame) -> tuple[MechanismKind, ...]:
    return tuple(
        reference.mechanism
        for name in _SUBSYSTEM_FIELD.values()
        if (reference := getattr(frame, name)) is not None
    )


def matching_mechanism_signatures(
    mechanisms: Sequence[MechanismKind],
    phase: str,
) -> tuple[MechanismSignatureDefinition, ...]:
    present = set(mechanisms)
    return tuple(
        definition
        for definition in MECHANISM_SIGNATURE_DEFINITIONS
        if phase in definition.valid_phases
        and set(definition.required_mechanism_kinds) <= present
    )


def build_mechanism_episodes(
    frames: Sequence[EngineeringStateFrame],
    transitions: Sequence[StateTransition],
) -> tuple[MechanismEpisode, ...]:
    by_context: dict[tuple[str, str, str], list[EngineeringStateFrame]] = defaultdict(
        list
    )
    for frame in frames:
        by_context[(frame.run_id, frame.setup_id, frame.context_id)].append(frame)
    episodes: list[MechanismEpisode] = []
    for (run_id, setup_id, context_id), group in by_context.items():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda frame: (
                frame.lap_number,
                frame.session_time_start,
                frame.frame_id,
            ),
        )
        frame_ids = {frame.frame_id for frame in ordered}
        related = tuple(
            transition
            for transition in transitions
            if transition.from_frame_id in frame_ids
            and transition.to_frame_id in frame_ids
        )
        if not related:
            continue
        mechanisms = tuple(
            sorted(
                {mechanism for frame in ordered for mechanism in _mechanisms(frame)},
                key=lambda item: item.value,
            )
        )
        signatures = matching_mechanism_signatures(mechanisms, ordered[0].phase)
        mind_change = tuple(
            dict.fromkeys(
                requirement
                for definition in signatures
                for requirement in definition.mind_change_requirements
            )
        ) or ("Repeat the exact physical window under comparable context.",)
        measurement = tuple(
            dict.fromkeys(
                requirement
                for definition in signatures
                for requirement in definition.measurement_requirements
            )
        ) or ("Capture the same producer-owned channels on additional eligible laps.",)
        lap_scope = tuple(sorted({frame.lap_number for frame in ordered}))
        clusters = tuple(
            dict.fromkeys(frame.independence_cluster_id for frame in ordered)
        )
        artifacts = tuple(
            dict.fromkeys(
                artifact for frame in ordered for artifact in frame.source_artifact_ids
            )
        )
        episodes.append(
            MechanismEpisode(
                episode_id=_hash(
                    "mechanism-episode",
                    run_id,
                    setup_id,
                    context_id,
                    *(frame.frame_id for frame in ordered),
                ),
                run_id=run_id,
                setup_id=setup_id,
                context_id=context_id,
                lap_scope=lap_scope,
                phase=ordered[0].phase,
                lap_pct_start=min(frame.lap_pct_start for frame in ordered),
                lap_pct_end=max(frame.lap_pct_end for frame in ordered),
                lap_pct_peak=float(median(frame.lap_pct_peak for frame in ordered)),
                state_frame_ids=tuple(frame.frame_id for frame in ordered),
                transition_ids=tuple(
                    transition.transition_id for transition in related
                ),
                supporting_mechanism_kinds=mechanisms,
                supporting_artifact_ids=artifacts,
                independence_cluster_ids=clusters,
                repeatability=EpisodeRepeatability(
                    repetition_count=len(ordered),
                    distinct_lap_count=len(lap_scope),
                    independent_cluster_count=len(clusters),
                    basis=(
                        "Same-run same-setup repetitions show temporal repeatability; "
                        "they remain one conservative independence cluster."
                    ),
                ),
                mind_change_requirements=mind_change,
                measurement_requirements=measurement,
                signature_keys=tuple(
                    definition.signature_key for definition in signatures
                ),
            )
        )
    return tuple(sorted(episodes, key=lambda episode: episode.episode_id))


def episode_observation_report(
    episodes: Sequence[MechanismEpisode],
    frames: Sequence[EngineeringStateFrame],
    *,
    run_id: str,
    setup_id: str,
) -> MechanismObservationReport:
    frames_by_id = {frame.frame_id: frame for frame in frames}
    observations: list[MechanismObservation] = []
    for episode in episodes:
        episode_frames = [
            frames_by_id[frame_id] for frame_id in episode.state_frame_ids
        ]
        channels = tuple(
            dict.fromkeys(
                channel for frame in episode_frames for channel in frame.source_channels
            )
        )
        citations = []
        for lap_number in episode.lap_scope:
            frame = next(
                frame for frame in episode_frames if frame.lap_number == lap_number
            )
            citations.append(
                ObservationCitation(
                    run_id=run_id,
                    lap_number=lap_number,
                    setup_id=setup_id,
                    lap_pct_start=episode.lap_pct_start,
                    lap_pct_end=episode.lap_pct_end,
                    lap_pct_peak=episode.lap_pct_peak,
                    phase=episode.phase,
                    evidence_state=EvidenceState.OBSERVED_CORRELATION,
                    source_channels=channels,
                    telemetry_sample_count=max(1, len(frame.supporting_evidence)),
                )
            )
        observations.append(
            MechanismObservation(
                observation_id=episode.episode_id,
                producer_id="p20.mechanism_episode_builder",
                artifact_id=episode.episode_id,
                source_run_ids=(run_id,),
                source_setup_ids=(setup_id,),
                sample_coverage=1.0,
                mechanism=episode.supporting_mechanism_kinds[0],
                run_id=run_id,
                setup_id=setup_id,
                lap_number=episode.lap_scope[0],
                phase=episode.phase,
                lap_pct_start=episode.lap_pct_start,
                lap_pct_end=episode.lap_pct_end,
                lap_pct_peak=episode.lap_pct_peak,
                summary=(
                    "Temporal mechanism episode: "
                    + ", ".join(
                        item.value for item in episode.supporting_mechanism_kinds
                    )
                    + ". Temporal order is observation-only, not causal attribution."
                ),
                evidence_state=EvidenceState.OBSERVED_CORRELATION,
                qualified=True,
                source_channels=channels,
                required_channels=channels,
                supporting_evidence=episode.transition_ids,
                telemetry_sample_count=sum(
                    item.telemetry_sample_count for item in citations
                ),
                repetition_count=len(episode.lap_scope),
                citations=tuple(citations),
            )
        )
    return MechanismObservationReport(
        status=ObservationStatus.READY
        if observations
        else ObservationStatus.NO_FINDING,
        run_id=run_id,
        setup_id=setup_id,
        observations=tuple(observations),
    )


def build_engineering_awareness_evidence(
    observations: MechanismObservationReport,
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    setup_id: str | None,
) -> EngineeringAwarenessEvidenceBuild:
    if setup_id is None:
        empty = MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=None,
            blocker_reasons=(
                "An exact setup identity is required for state awareness.",
            ),
        )
        return EngineeringAwarenessEvidenceBuild(
            (), (), (), empty, (), empty.blocker_reasons
        )
    frames, blockers = build_engineering_state_frames(
        observations.observations, rows, run_id=run_id, setup_id=setup_id
    )
    transitions = build_state_transitions(frames)
    episodes = build_mechanism_episodes(frames, transitions)
    episode_report = episode_observation_report(
        episodes, frames, run_id=run_id, setup_id=setup_id
    )
    if blockers and not episodes:
        episode_report = MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=blockers,
        )
    return EngineeringAwarenessEvidenceBuild(
        frames=frames,
        transitions=transitions,
        episodes=episodes,
        episode_observations=episode_report,
        control_mutations=detect_control_mutations(rows, run_id=run_id),
        blocker_reasons=blockers,
    )


def build_state_drift_ledger(
    entries: Sequence[StateDriftEntry],
    *,
    run_id: str,
    setup_id: str,
    control_state_unchanged: bool,
    channel_health_stable: bool,
    context_comparable: bool,
    empirical_noise_by_metric: Mapping[str, float],
) -> StateDriftLedger:
    """Detect only persistent, above-noise shifts on contiguous clean laps."""
    ordered = tuple(sorted(entries, key=lambda entry: entry.lap_number))
    blockers: list[str] = []
    if any(entry.run_id != run_id or entry.setup_id != setup_id for entry in ordered):
        blockers.append("State-drift entries do not match the exact run and setup.")
    if len(ordered) < 3:
        blockers.append("At least three eligible clean-stint entries are required.")
    if ordered and tuple(entry.lap_number for entry in ordered) != tuple(
        range(ordered[0].lap_number, ordered[-1].lap_number + 1)
    ):
        blockers.append("Eligible state-drift laps are not contiguous.")
    if (
        len(
            {
                (entry.context_id, entry.phase, entry.lap_pct_start, entry.lap_pct_end)
                for entry in ordered
            }
        )
        > 1
    ):
        blockers.append("State-drift entries do not share one exact physical context.")
    if not control_state_unchanged:
        blockers.append(
            "A material in-car control state changed inside the drift scope."
        )
    if not channel_health_stable:
        blockers.append("Channel health is not stable across the drift scope.")
    if not context_comparable:
        blockers.append(
            "Fuel, tire, weather, line, or traffic context is not comparable."
        )
    if blockers:
        return StateDriftLedger(
            ledger_id=_hash("state-drift", run_id, setup_id, "blocked"),
            run_id=run_id,
            setup_id=setup_id,
            status="blocked",
            entries=ordered,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    by_metric: dict[str, list[tuple[StateDriftEntry, Any]]] = defaultdict(list)
    for entry in ordered:
        for metric in entry.metrics:
            by_metric[metric.metric_key].append((entry, metric))
    findings: list[StateDriftFinding] = []
    for metric_key, values in by_metric.items():
        if len(values) != len(ordered):
            continue
        noise = _finite(empirical_noise_by_metric.get(metric_key))
        if noise is None or noise < 0.0:
            continue
        baseline = values[0][1].value
        latest_pair = values[-2:]
        deltas = [pair[1].value - baseline for pair in latest_pair]
        if not all(abs(delta) > noise for delta in deltas):
            continue
        if deltas[0] * deltas[1] <= 0.0:
            continue
        source_entries = tuple(pair[0].entry_id for pair in values)
        source_artifacts = tuple(
            dict.fromkeys(
                artifact
                for _entry, metric in values
                for artifact in metric.source_artifact_ids
            )
        )
        findings.append(
            StateDriftFinding(
                finding_id=_hash(
                    "state-drift-finding",
                    run_id,
                    setup_id,
                    metric_key,
                    *source_entries,
                ),
                metric_key=metric_key,
                from_lap_number=values[0][0].lap_number,
                to_lap_number=values[-1][0].lap_number,
                observed_delta=float(median(deltas)),
                empirical_noise_floor=noise,
                persistence_lap_count=2,
                source_entry_ids=source_entries,
                source_artifact_ids=source_artifacts,
            )
        )
    return StateDriftLedger(
        ledger_id=_hash(
            "state-drift",
            run_id,
            setup_id,
            *(entry.entry_id for entry in ordered),
        ),
        run_id=run_id,
        setup_id=setup_id,
        status="ready" if findings else "no_finding",
        entries=ordered,
        findings=tuple(findings),
    )


__all__ = [
    "EngineeringAwarenessEvidenceBuild",
    "MECHANISM_SIGNATURE_DEFINITIONS",
    "build_engineering_awareness_evidence",
    "build_engineering_state_frames",
    "build_mechanism_episodes",
    "build_state_drift_ledger",
    "build_state_transitions",
    "episode_observation_report",
    "matching_mechanism_signatures",
]
