"""Bounded, stale-identifiable projection of the canonical P19/P20 state."""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any

from racelab_engine.models.engineering_awareness import TrustAxis, TrustBudget, TrustState
from racelab_engine.models.engineering_projection import (
    AwarenessArtifactVersion,
    AwarenessRequestIdentity,
    EngineeringAwarenessProjection,
    ExpectedVsObservedState,
    PrimaryEngineeringState,
    SubsystemAwarenessState,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.services.import_service import read_telemetry_manifest
from racelab_engine.services.run_intelligence_service import (
    RunIntelligenceBundle,
    build_run_intelligence,
)
from racelab_engine.storage.db import default_db_path


_SCHEMA_VERSION = "p20.awareness.v2"
_CACHE_LIMIT = 8
_CACHE: OrderedDict[tuple[object, ...], EngineeringAwarenessProjection] = OrderedDict()
_CACHE_LOCK = RLock()


def _canonical_sha256(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_identity(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _cache_key(
    run_id: str,
    session_id: str | None,
    db_path: str | Path | None,
) -> tuple[object, ...]:
    database = Path(db_path) if db_path is not None else default_db_path()
    manifest = read_telemetry_manifest(run_id)
    return (
        _SCHEMA_VERSION,
        run_id,
        session_id,
        str(database.resolve()),
        _file_identity(database),
        _file_identity(Path(f"{database}-wal")),
        manifest.get("source_file_sha256"),
        manifest.get("telemetry_cache_sha256"),
        manifest.get("schema_fingerprint"),
        manifest.get("manifest_identity"),
    )


def clear_engineering_awareness_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _unique(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _axis(
    state: TrustState,
    basis: str,
    blockers: tuple[str, ...] = (),
    sources: tuple[str, ...] = (),
) -> TrustAxis:
    return TrustAxis(
        state=state,
        basis=basis,
        blockers=_unique(blockers),
        source_artifact_ids=_unique(sources),
    )


def _trust_budget(bundle: RunIntelligenceBundle) -> TrustBudget:
    report = bundle.report
    snapshot = report.reasoning_snapshot
    quality = snapshot.data_quality
    quality_sources = tuple(quality.trusted_event_ids)
    data_state = {
        "ready": TrustState.TRUSTED,
        "limited": TrustState.LIMITED,
        "blocked": TrustState.BLOCKED,
    }[quality.status]
    data_blockers = () if data_state is TrustState.TRUSTED else _unique(
        [*quality.issues, *quality.recovery_steps]
    )

    if snapshot.mechanism_episodes:
        alignment = _axis(
            TrustState.TRUSTED,
            "Producer-owned episodes preserve exact physical windows.",
            sources=tuple(item.episode_id for item in snapshot.mechanism_episodes),
        )
    elif snapshot.mechanism_episode_blocker_reasons:
        alignment = _axis(
            TrustState.LIMITED,
            "No qualified temporal episode is available.",
            snapshot.mechanism_episode_blocker_reasons,
        )
    else:
        alignment = _axis(
            TrustState.UNAVAILABLE,
            "Temporal alignment has no qualified episode artifact.",
            ("No exact temporal mechanism episode was produced for this run.",),
        )

    context = snapshot.lap_context
    if context is None:
        context_axis = _axis(
            TrustState.UNAVAILABLE,
            "Lap engineering context was not produced.",
            ("Fuel, tire, weather, traffic, and channel-update comparability are unavailable.",),
        )
    else:
        context_state = {
            "ready": TrustState.TRUSTED,
            "limited": TrustState.LIMITED,
            "blocked": TrustState.BLOCKED,
        }[context.status]
        context_axis = _axis(
            context_state,
            "Canonical lap engineering context controls comparability.",
            () if context_state is TrustState.TRUSTED else context.blocker_reasons,
        )

    driver = report.driver_focus
    if driver is None:
        driver_axis = _axis(
            TrustState.UNAVAILABLE,
            "Same-setup driver repeatability was not produced.",
            ("Driver repeatability evidence is unavailable for this run.",),
        )
    elif driver.status.value == "blocked":
        driver_axis = _axis(
            TrustState.BLOCKED,
            "Driver repeatability is blocked by its producer contract.",
            driver.blocker_reasons,
        )
    else:
        driver_axis = _axis(
            TrustState.TRUSTED,
            "Same-setup driver repeatability passed its producer contract.",
        )

    active_causes = tuple(cause for cause in snapshot.causes if cause.status != "ruled_out")
    if not active_causes:
        mechanism_axis = _axis(
            TrustState.UNAVAILABLE,
            "No active backend cause is available.",
            ("The P19 snapshot has no active mechanism cause to separate.",),
        )
    elif any(cause.controlled_conflict for cause in active_causes):
        mechanism_axis = _axis(
            TrustState.BLOCKED,
            "Contradictory controlled mechanism outcomes remain unresolved.",
            ("At least one cause has conflicting controlled mechanism evidence.",),
        )
    elif len(active_causes) > 1:
        mechanism_axis = _axis(
            TrustState.LIMITED,
            "Multiple backend causes remain active.",
            ("Competing causes still require a discriminator or controlled evidence.",),
        )
    elif active_causes[0].blocker_reasons or active_causes[0].missing_evidence:
        mechanism_axis = _axis(
            TrustState.LIMITED,
            "The sole active cause still carries explicit evidence debt.",
            _unique(
                [
                    *active_causes[0].blocker_reasons,
                    *active_causes[0].missing_evidence,
                ]
            ),
        )
    else:
        mechanism_axis = _axis(
            TrustState.TRUSTED,
            "The backend snapshot has one active, non-conflicting cause.",
        )

    outcomes = snapshot.controlled_outcomes
    if not outcomes:
        response_axis = _axis(
            TrustState.UNAVAILABLE,
            "No protocol-valid controlled response is attached.",
            ("Complete a canonical A/B/A2 workflow before judging control response.",),
        )
    else:
        invalid = tuple(item for item in outcomes if item.control_response.result == "invalid")
        response_axis = (
            _axis(
                TrustState.BLOCKED,
                "At least one controlled response is invalid.",
                tuple(item.control_response.reason for item in invalid),
            )
            if invalid
            else _axis(
                TrustState.TRUSTED,
                "Controlled response validity comes directly from P19 outcomes.",
                sources=tuple(item.workflow_id for item in outcomes),
            )
        )
    policy_axis = _axis(
        TrustState.UNAVAILABLE,
        "Setup policy is intentionally withheld from this observation-only projection.",
        ("Use the exact P19 controlled workflow for setup-policy decisions.",),
    )

    history_blockers = _unique(
        [
            reason
            for reason in (*report.blocker_reasons, *snapshot.blocker_reasons)
            if any(token in reason.casefold() for token in ("history", "recovery", "unreadable", "incomplete"))
        ]
    )
    history_axis = (
        _axis(
            TrustState.BLOCKED,
            "Historical absence cannot be interpreted while saved intelligence is incomplete.",
            history_blockers,
        )
        if history_blockers
        else _axis(
            TrustState.TRUSTED,
            "No fail-closed historical-completeness blocker is active.",
        )
    )
    return TrustBudget(
        data_health=_axis(
            data_state,
            "Canonical eligible-lap and trusted-event quality gate.",
            data_blockers,
            quality_sources,
        ),
        alignment_quality=alignment,
        context_comparability=context_axis,
        driver_repeatability=driver_axis,
        mechanism_separation=mechanism_axis,
        controlled_response_validity=response_axis,
        policy_countereffect_risk=policy_axis,
        history_completeness=history_axis,
    )


def _subsystem_states(bundle: RunIntelligenceBundle) -> tuple[SubsystemAwarenessState, ...]:
    report = bundle.report.mechanism_observations
    observations = report.observations if report is not None else ()
    by_mechanism: dict[MechanismKind, list[Any]] = defaultdict(list)
    for observation in observations:
        for mechanism in (
            getattr(observation, "mechanism_kinds", ()) or (observation.mechanism,)
        ):
            by_mechanism[mechanism].append(observation)
    states: list[SubsystemAwarenessState] = []
    for mechanism in MechanismKind:
        if mechanism is MechanismKind.UNCLASSIFIED:
            continue
        members = sorted(by_mechanism.get(mechanism, ()), key=lambda item: item.artifact_id)
        qualified = tuple(item for item in members if item.qualified)
        blocked = tuple(item for item in members if not item.qualified)
        if qualified and blocked:
            states.append(
                SubsystemAwarenessState(
                    mechanism=mechanism,
                    status="blocked",
                    summary=(
                        f"{qualified[0].summary} Another {mechanism.value} producer remains blocked."
                    ),
                    phase=qualified[0].phase,
                    lap_number=qualified[0].lap_number,
                    lap_pct_start=qualified[0].lap_pct_start,
                    lap_pct_end=qualified[0].lap_pct_end,
                    evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                    source_artifact_ids=_unique([item.artifact_id for item in members]),
                    source_channels=_unique(
                        [channel for item in members for channel in item.source_channels]
                    ),
                    blocker_reasons=_unique(
                        [reason for item in blocked for reason in item.blocker_reasons]
                    ),
                )
            )
        elif qualified:
            representative = qualified[0]
            states.append(
                SubsystemAwarenessState(
                    mechanism=mechanism,
                    status="ready",
                    summary=representative.summary,
                    phase=representative.phase,
                    lap_number=representative.lap_number,
                    lap_pct_start=representative.lap_pct_start,
                    lap_pct_end=representative.lap_pct_end,
                    evidence_state=representative.evidence_state,
                    source_artifact_ids=_unique([item.artifact_id for item in qualified]),
                    source_channels=_unique(
                        [channel for item in qualified for channel in item.source_channels]
                    ),
                )
            )
        elif blocked:
            states.append(
                SubsystemAwarenessState(
                    mechanism=mechanism,
                    status="blocked",
                    summary=f"{mechanism.value.replace('_', ' ').title()} is blocked.",
                    evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                    source_artifact_ids=_unique([item.artifact_id for item in blocked]),
                    source_channels=_unique(
                        [channel for item in blocked for channel in item.source_channels]
                    ),
                    blocker_reasons=_unique(
                        [reason for item in blocked for reason in item.blocker_reasons]
                    ),
                )
            )
        else:
            states.append(
                SubsystemAwarenessState(
                    mechanism=mechanism,
                    status="unavailable",
                    summary=f"{mechanism.value.replace('_', ' ').title()} is unavailable.",
                    evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                    blocker_reasons=(
                        f"No producer-owned {mechanism.value} observation exists for this exact run.",
                    ),
                )
            )
    return tuple(states)


def _primary_state(bundle: RunIntelligenceBundle) -> PrimaryEngineeringState | None:
    report = bundle.report
    if not report.reasoning_snapshot.causes or report.mechanism_observations is None:
        return None
    cause = report.reasoning_snapshot.causes[0]
    observation_id = cause.cause_id.removeprefix("observation:")
    observation = next(
        (
            item
            for item in report.mechanism_observations.observations
            if item.observation_id == observation_id and item.qualified
        ),
        None,
    )
    if observation is None:
        return None
    assert observation.lap_number is not None
    assert observation.phase is not None
    assert observation.lap_pct_start is not None
    assert observation.lap_pct_end is not None
    assert observation.lap_pct_peak is not None
    return PrimaryEngineeringState(
        state_id=observation.observation_id,
        label=observation.summary,
        mechanism=observation.mechanism,
        lap_number=observation.lap_number,
        phase=observation.phase,
        lap_pct_start=observation.lap_pct_start,
        lap_pct_end=observation.lap_pct_end,
        lap_pct_peak=observation.lap_pct_peak,
        evidence_state=observation.evidence_state,
        source_artifact_ids=(observation.artifact_id,),
        source_channels=observation.source_channels,
    )


def _expected_vs_observed(bundle: RunIntelligenceBundle) -> tuple[ExpectedVsObservedState, ...]:
    return tuple(
        ExpectedVsObservedState(
            workflow_id=item.workflow_id,
            control_key=item.control_response.control_key,
            metric=item.control_response.metric,
            phase=item.control_response.phase,
            mechanism_state=item.mechanism.state,
            control_response=item.control_response.result,
            mechanism_reason=item.mechanism.reason,
            control_response_reason=item.control_response.reason,
        )
        for item in bundle.report.reasoning_snapshot.controlled_outcomes
    )


def _artifact_versions(bundle: RunIntelligenceBundle) -> tuple[AwarenessArtifactVersion, ...]:
    versions: dict[str, str] = {
        "projection_schema": _SCHEMA_VERSION,
        "reasoning_snapshot": "p19.reasoning.v1",
        "mechanism_episode": "p20.episode.v1",
        "mechanism_signature": "p20.signature.v1",
    }
    for frame in bundle.awareness.frames:
        for analyzer in frame.analyzer_versions:
            versions[f"analyzer:{analyzer.analyzer_id}"] = analyzer.version
    return tuple(
        AwarenessArtifactVersion(artifact_key=key, version=value)
        for key, value in sorted(versions.items())
    )


def _build_projection(
    bundle: RunIntelligenceBundle,
    *,
    started: float,
) -> EngineeringAwarenessProjection:
    report = bundle.report
    snapshot = report.reasoning_snapshot
    snapshot_id = _canonical_sha256(snapshot)
    profile_hashes = {frame.vehicle_profile_hash for frame in bundle.awareness.frames if frame.vehicle_profile_hash}
    profile_hash = next(iter(profile_hashes)) if len(profile_hashes) == 1 else None
    revision_payload = {
        "snapshot": snapshot_id,
        "frames": [item.frame_id for item in bundle.awareness.frames],
        "transitions": [item.transition_id for item in bundle.awareness.transitions],
        "episodes": [item.episode_id for item in bundle.awareness.episodes],
        "mutations": [item.mutation_id for item in bundle.awareness.control_mutations],
        "profile": profile_hash,
        "versions": [item.model_dump(mode="json") for item in _artifact_versions(bundle)],
    }
    state_revision = _canonical_sha256(revision_payload)
    request_identity = AwarenessRequestIdentity(
        run_id=report.run_id,
        session_id=report.session_id,
        reasoning_snapshot_id=snapshot_id,
        state_revision=state_revision,
    )
    primary = _primary_state(bundle)
    subsystem_states = _subsystem_states(bundle)
    debt = [
        *report.blocker_reasons,
        *snapshot.blocker_reasons,
        *snapshot.mechanism_episode_blocker_reasons,
        *bundle.awareness.blocker_reasons,
        "State drift is unavailable until comparable numeric clean-stint entries are assembled under unchanged control and stable channel-health context.",
    ]
    if not bundle.awareness.frames:
        debt.append("No exact engineering state frame was produced for this run.")
    if primary is None:
        debt.append("The leading P19 cause does not resolve to a qualified producer-owned mechanism observation.")
    if len(profile_hashes) > 1:
        debt.append("Multiple vehicle-profile hashes appear inside the awareness frame set.")
    projection = EngineeringAwarenessProjection(
        run_id=report.run_id,
        session_id=report.session_id,
        reasoning_snapshot_id=snapshot_id,
        state_revision=state_revision,
        request_identity=request_identity,
        generated_at=datetime.now(timezone.utc),
        cache_state="cold",
        build_duration_ms=max(0.0, (perf_counter() - started) * 1000.0),
        profile_hash=profile_hash,
        trust_budget=_trust_budget(bundle),
        primary_state=primary,
        subsystem_states=subsystem_states,
        episodes=snapshot.mechanism_episodes,
        state_drift_status="unavailable",
        state_drift_blocker_reasons=(
            "No canonical clean-stint state-drift ledger is attached to the P19 snapshot.",
        ),
        expected_vs_observed=_expected_vs_observed(bundle),
        control_mutations=bundle.awareness.control_mutations,
        knowledge_debt=_unique(debt),
        artifact_versions=_artifact_versions(bundle),
    )
    return projection


def project_engineering_awareness(
    bundle: RunIntelligenceBundle,
) -> EngineeringAwarenessProjection:
    """Project P20 from an already-built canonical intelligence bundle."""
    return _build_projection(bundle, started=perf_counter())


def build_engineering_awareness_projection(
    run_id: str,
    *,
    session_id: str | None = None,
    db_path: str | Path | None = None,
    refresh: bool = False,
) -> EngineeringAwarenessProjection:
    """Build one backend-owned public read without materializing raw traces."""
    started = perf_counter()
    key = _cache_key(run_id, session_id, db_path)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None and not refresh:
            _CACHE.move_to_end(key)
            return cached.model_copy(
                update={
                    "cache_state": "warm",
                    "build_duration_ms": max(0.0, (perf_counter() - started) * 1000.0),
                }
            )
    bundle = build_run_intelligence(run_id, session_id=session_id, db_path=db_path)
    projection = _build_projection(bundle, started=started)
    with _CACHE_LOCK:
        stale = [item for item in _CACHE if item[:3] == key[:3] and item != key]
        for item in stale:
            _CACHE.pop(item, None)
        _CACHE[key] = projection
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_LIMIT:
            _CACHE.popitem(last=False)
    return projection


__all__ = [
    "build_engineering_awareness_projection",
    "clear_engineering_awareness_cache",
    "project_engineering_awareness",
]
