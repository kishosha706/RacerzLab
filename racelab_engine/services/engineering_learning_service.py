"""Deterministic P33 experience construction and attention-only retrieval.

P33 never ranks current causes, chooses setup values, or emits Keep/Undo/Retest.
It materializes immutable facts from P19/P32 and controlled lifecycle events,
then retrieves a bounded history to refine attention inside Crew safety bands.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Literal, Mapping

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.crew_chief import (
    CrewChiefEvent,
    CrewChiefInvestigation,
    CrewChiefTerminalDecision,
)
from racelab_engine.models.engineering_learning import (
    AttentionOrderItem,
    CarResponseFact,
    CarResponseFingerprint,
    ContextTransferAssessment,
    ContextTransferLevel,
    CrewChiefLearningPrior,
    DeadEndFact,
    DriverFingerprintContribution,
    DriverPerformanceFingerprint,
    EngineeringDeadEndRecord,
    EngineeringExperienceContext,
    EngineeringExperienceRecord,
    EngineeringLearningLedger,
    EngineeringObjectiveValue,
    EngineeringSourceProvenance,
    EvidenceUnitCounts,
    InvestigationOutcomeRecord,
    InvestigationPathFact,
    LearningEvidenceReference,
    LearningStrength,
    MindChangeFact,
    MindChangeRecord,
    P19CauseMemory,
    P19ReasoningMemory,
    PerformanceResponseFact,
    PostRunLearningBrief,
    ProblemFingerprint,
    RecurringProblemMatch,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.performance_intelligence import (
    DriverVehicleResult,
    LapTimeOpportunity,
    PerformanceIntelligenceProjection,
)
from racelab_engine.models.session import RunOverview
from racelab_engine.recording_identity import (
    RECORDING_RUN_ID_PREFIX,
    normalize_source_sha256,
)
from racelab_engine.services.import_service import read_telemetry_manifest
from racelab_engine.services.run_intelligence_service import RunIntelligenceBundle
from racelab_engine.storage.db import default_db_path, initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    EngineeringLearningIntegrityError,
    EngineeringLearningRepository,
)
from racelab_engine.storage.repository import RaceLabRepository

_OBJECTIVES: frozenset[str] = frozenset(
    {
        "qualifying_peak",
        "race_long_run",
        "tire_conservation",
        "driver_confidence",
        "traffic_robustness",
        "superspeedway_stability",
        "fuel_strategy",
    }
)
_TRANSFER_ORDER: dict[ContextTransferLevel, int] = {
    "exact": 0,
    "compatible": 1,
    "weak": 2,
    "blocked": 3,
}
_ATTENTION_TOOLS: dict[str, tuple[str, int]] = {
    "inspect_lap_time_opportunity": ("performance_measurement", 1),
    "inspect_time_loss_origin": ("performance_measurement", 2),
    "inspect_corner_performance_chain": ("performance_measurement", 3),
    "inspect_exit_carry": ("performance_measurement", 4),
    "inspect_path_efficiency": ("performance_measurement", 5),
    "inspect_driver_vehicle_separation": ("performance_measurement", 6),
    "inspect_track_demand": ("performance_measurement", 7),
}
_OPTIONAL_P26_MARKERS = (
    "graph is unavailable",
    "requires review for future",
    "does not cover iracing build",
    "requires an oval track configuration",
    "unavailable for car path",
    "requires review for car version",
)

_CACHE_LOCK = RLock()
_CACHE: dict[tuple[str, ...], CrewChiefLearningPrior] = {}


@dataclass(frozen=True)
class CurrentLearningInputs:
    context: EngineeringExperienceContext
    problem: ProblemFingerprint
    reasoning: P19ReasoningMemory
    source_provenance: tuple[EngineeringSourceProvenance, ...]
    performance_response: PerformanceResponseFact | None
    driver_contributions: tuple[DriverFingerprintContribution, ...]


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _objective(value: object) -> EngineeringObjectiveValue:
    normalized = _enum_text(value).strip()
    return normalized if normalized in _OBJECTIVES else "race_long_run"


def _database_identity(db_path: str | Path | None) -> tuple[str, str, str]:
    path = Path(db_path) if db_path is not None else default_db_path()
    resolved = path.resolve()
    try:
        stat = resolved.stat()
        return str(resolved), str(stat.st_mtime_ns), str(stat.st_size)
    except OSError:
        return str(resolved), "missing", "0"


def clear_learning_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def build_p19_reasoning_memory(report: Any) -> P19ReasoningMemory:
    """Freeze the exact P19 state without copying its narrative authority."""

    snapshot = report.reasoning_snapshot
    return P19ReasoningMemory(
        reasoning_snapshot_sha256=canonical_json_sha256(snapshot),
        causes=tuple(
            P19CauseMemory(
                cause_id=cause.cause_id,
                status=_enum_text(cause.status),
                ordinal_rank=cause.ordinal_rank,
                mechanism_family=(getattr(cause, "mechanism_key", None) or None),
            )
            for cause in snapshot.causes
        ),
        measurement_plan_kind=_enum_text(snapshot.measurement_plan.kind),
        discriminator_ids=tuple(
            criterion.criterion_id for criterion in report.mind_change_criteria
        ),
        authority_level=_enum_text(snapshot.authority.level),
        setup_authorized=snapshot.authority.setup_authorized,
    )


def _manifest_parts(run_id: str) -> tuple[dict[str, Any], str]:
    manifest = read_telemetry_manifest(run_id)
    identity = manifest.get("compatibility_identity")
    if not isinstance(identity, dict) or identity.get("missing_required_fields"):
        raise ValueError("P33 requires a complete telemetry compatibility identity")
    build_hash: str
    try:
        from racelab_engine.services.vehicle_systems_service import (
            vehicle_systems_runtime_identity,
        )

        build_hash = canonical_json_sha256(
            vehicle_systems_runtime_identity(run_id).model_dump(mode="json")
        )
    except ValueError:
        build_hash = canonical_json_sha256(
            {
                "compatibility_identity": identity,
                "compatibility_fingerprint": manifest.get("compatibility_fingerprint"),
                "source_file_sha256": manifest.get("source_file_sha256"),
                "cache_version": manifest.get("cache_version"),
            }
        )
    return identity, build_hash


def _dominant_opportunity(
    projection: PerformanceIntelligenceProjection,
) -> LapTimeOpportunity | None:
    opportunities = tuple(projection.opportunity_map.opportunities)
    if not opportunities:
        return None
    return min(
        opportunities,
        key=lambda item: (
            item.local_delta_s is None or item.local_delta_s == 0,
            -abs(item.local_delta_s or 0.0),
            item.opportunity_id,
        ),
    )


def _traffic_state(
    opportunity: LapTimeOpportunity | None,
    projection: PerformanceIntelligenceProjection,
) -> str:
    if (
        opportunity is not None
        and opportunity.attribution_state == "blocked_by_traffic"
    ):
        return "traffic_contaminated"
    exposure = projection.track_demand.traffic_exposure_fraction
    if exposure is None:
        return "unresolved"
    return "clear" if exposure == 0 else "traffic_exposed"


def _current_artifact(
    *,
    run_id: str,
    session_id: str,
    overview: RunOverview,
    projection: PerformanceIntelligenceProjection,
    opportunity: LapTimeOpportunity | None,
    build_context_sha256: str,
) -> EngineeringSourceProvenance:
    setup = overview.setup_snapshot
    if setup is None:
        raise ValueError("P33 requires an exact setup snapshot")
    setup_hash = canonical_json_sha256(setup)
    if opportunity is not None:
        return EngineeringSourceProvenance.build(
            artifact_id=opportunity.opportunity_id,
            producer_id="p32.lap_time_opportunity",
            run_id=run_id,
            session_id=session_id,
            setup_id=setup.setup_id,
            setup_snapshot_sha256=setup_hash,
            build_context_sha256=build_context_sha256,
            lap_numbers=opportunity.source_laps,
            lap_pct_start=opportunity.start_pct,
            lap_pct_end=opportunity.end_pct,
            phase=opportunity.phase,
            source_channels=opportunity.source_channels,
            evidence_state=(
                EvidenceState.BLOCKED_BY_CONTEXT
                if opportunity.attribution_state.startswith("blocked_by_")
                else EvidenceState.CALCULATED
            ),
            polarity="neutral",
        )
    profile = projection.track_demand
    artifact_id = f"p32-track-demand:{canonical_json_sha256(profile)[:20]}"
    available = any(
        value is not None
        for value in (
            profile.full_throttle_fraction,
            profile.braking_fraction,
            profile.cornering_fraction,
            profile.speed_min_mph,
            profile.speed_max_mph,
            profile.disturbance_exposure_fraction,
            profile.traffic_exposure_fraction,
        )
    )
    return EngineeringSourceProvenance.build(
        artifact_id=artifact_id,
        producer_id="p32.track_demand",
        run_id=run_id,
        session_id=session_id,
        setup_id=setup.setup_id,
        setup_snapshot_sha256=setup_hash,
        build_context_sha256=build_context_sha256,
        lap_numbers=projection.basis.source_lap_numbers,
        lap_pct_start=0.0,
        lap_pct_end=100.0,
        phase="whole_run",
        source_channels=profile.source_channels,
        evidence_state=(
            EvidenceState.CALCULATED if available else EvidenceState.UNAVAILABLE
        ),
        polarity="neutral",
    )


def _driver_contributions(
    *,
    bundle: RunIntelligenceBundle,
    projection: PerformanceIntelligenceProjection,
    opportunity: LapTimeOpportunity | None,
    artifact_id: str,
) -> tuple[DriverFingerprintContribution, ...]:
    laps = (
        opportunity.source_laps
        if opportunity is not None
        else projection.basis.source_lap_numbers
    )
    episode_ids = (opportunity.opportunity_id,) if opportunity is not None else ()
    contributions: list[DriverFingerprintContribution] = []
    focus = bundle.report.driver_focus
    channel_metrics = {
        "brake_pct": "brake_release_timing_consistency",
        "throttle_pct": "throttle_pickup_timing",
        "steering_deg": "steering_workload",
    }
    if focus is not None and _enum_text(focus.status) != "blocked":
        for item in focus.channel_repeatability:
            metric = channel_metrics.get(item.channel)
            if metric is None:
                continue
            contribution_id = (
                "p33driver_"
                + canonical_json_sha256([artifact_id, metric, tuple(laps)])[:24]
            )
            contributions.append(
                DriverFingerprintContribution(
                    contribution_id=contribution_id,
                    metric=metric,
                    tendency="context_dependent_tendency",
                    statement=(
                        f"Same-setup {item.channel.replace('_', ' ')} repeatability "
                        f"was measured across {len(laps)} eligible laps in this exact context."
                    ),
                    physical_episode_ids=episode_ids,
                    source_artifact_ids=(artifact_id,),
                    source_lap_count=len(laps),
                )
            )
    if opportunity is not None:
        separations = tuple(
            separation
            for chain in projection.corner_chains
            if chain.track_region == opportunity.track_region
            for separation in chain.driver_vehicle_separation
            if separation.phase == opportunity.phase
        )
        resolved = tuple(
            item
            for item in separations
            if item.result
            not in {
                DriverVehicleResult.CONTEXT_CONTAMINATED,
                DriverVehicleResult.UNRESOLVED,
            }
        )
        if resolved:
            states = _unique(_enum_text(item.result) for item in resolved)
            contributions.append(
                DriverFingerprintContribution(
                    contribution_id="p33driver_"
                    + canonical_json_sha256([artifact_id, states])[:24],
                    metric="driver_vehicle_separation",
                    tendency="context_dependent_tendency",
                    statement=(
                        "Driver-demand and vehicle-response separation was measured "
                        f"as {', '.join(value.replace('_', ' ') for value in states)} "
                        "in this exact phase."
                    ),
                    physical_episode_ids=episode_ids,
                    source_artifact_ids=(artifact_id,),
                    source_lap_count=len(laps),
                )
            )
    return tuple(contributions)


def _build_current_from_products(
    run_id: str,
    *,
    session_id: str,
    objective: object,
    bundle: RunIntelligenceBundle,
    p32: PerformanceIntelligenceProjection,
    overview: RunOverview,
) -> CurrentLearningInputs:
    if (
        bundle.report.run_id != run_id
        or bundle.report.session_id != session_id
        or p32.run_id != run_id
        or p32.session_id != session_id
        or overview.run_id != run_id
        or overview.setup_snapshot is None
    ):
        raise ValueError("P33 current inputs must share one exact run/session/setup")
    objective_value = _objective(objective)
    if p32.objective_id != objective_value:
        raise ValueError("P33 objective must equal the current P32 objective")
    identity, build_hash = _manifest_parts(run_id)
    opportunity = _dominant_opportunity(p32)
    setup = overview.setup_snapshot
    setup_hash = canonical_json_sha256(setup)
    phase = opportunity.phase if opportunity is not None else "whole_run"
    region = opportunity.track_region if opportunity is not None else "run scope"
    start_pct = opportunity.start_pct if opportunity is not None else 0.0
    end_pct = opportunity.end_pct if opportunity is not None else 100.0
    speed_min = p32.track_demand.speed_min_mph
    speed_max = p32.track_demand.speed_max_mph
    speed_band = (
        f"{speed_min:.0f}-{speed_max:.0f} mph"
        if speed_min is not None and speed_max is not None
        else "unresolved"
    )
    context = EngineeringExperienceContext.build(
        run_id=run_id,
        session_id=session_id,
        driver_id=(
            str(identity.get("driver_user_id"))
            if identity.get("driver_user_id") is not None
            else None
        ),
        car_path=str(
            identity.get("car_path") or overview.session.car_path or "unknown"
        ),
        car_version=str(identity.get("car_version") or "unknown"),
        iracing_build=str(identity.get("iracing_build_version") or "unknown"),
        track=str(
            identity.get("track_name")
            or overview.session.track_id_or_path
            or overview.session.track_name
            or "unknown"
        ),
        track_configuration=str(identity.get("track_configuration_name") or "unknown"),
        package_type=str(
            identity.get("car_configuration_name")
            or identity.get("track_configuration_name")
            or "unknown"
        ),
        setup_family=None,
        setup_snapshot_sha256=setup_hash,
        objective=objective_value,
        physical_scope_sha256=canonical_json_sha256(
            {
                "phase": phase,
                "physical_region": region,
                "start_pct": start_pct,
                "end_pct": end_pct,
            }
        ),
        phase=phase,
        physical_region=region,
        speed_load_band=speed_band,
        fuel_state="unresolved",
        tire_state=p32.track_demand.tire_state_development,
        weather_state=overview.session.weather_summary or "unresolved",
        traffic_state=_traffic_state(opportunity, p32),
        driver_execution_state=(
            opportunity.driver_execution_state
            if opportunity is not None
            else "unresolved"
        ),
    )
    artifact = _current_artifact(
        run_id=run_id,
        session_id=session_id,
        overview=overview,
        projection=p32,
        opportunity=opportunity,
        build_context_sha256=build_hash,
    )
    if opportunity is not None:
        carry = (
            "no_measured_carry"
            if opportunity.following_phase_effect_s is None
            else "following_phase_gain"
            if opportunity.following_phase_effect_s < 0
            else "following_phase_loss"
            if opportunity.following_phase_effect_s > 0
            else "no_measured_carry"
        )
        problem = ProblemFingerprint.build(
            physical_episode_id=opportunity.opportunity_id,
            performance_opportunity_id=opportunity.opportunity_id,
            phase=opportunity.phase,
            physical_region=opportunity.track_region,
            time_origin_class=_enum_text(opportunity.origin_kind),
            carry_behavior=carry,
            driver_demand_state=opportunity.driver_execution_state,
            vehicle_response_state=opportunity.vehicle_response_state,
            p20_mechanism_families=opportunity.mechanism_candidates,
            p26_component_families=opportunity.component_candidates,
            traffic_context_state=context.traffic_state,
            tire_stint_state=context.tire_state,
            objective=objective_value,
            source_artifact_ids=(artifact.artifact_id,),
        )
        measured_delta = (
            opportunity.local_delta_s
            if opportunity.local_delta_s not in {None, 0.0}
            else None
        )
        performance = (
            PerformanceResponseFact(
                performance_opportunity_id=opportunity.opportunity_id,
                observed_delta_s=measured_delta,
                observed_direction=(
                    "gain"
                    if measured_delta is not None and measured_delta < 0
                    else "loss"
                ),
                attribution_state=opportunity.attribution_state,
                time_origin=_enum_text(opportunity.origin_kind),
                phase_effect_s=measured_delta,
                carry_effect_s=opportunity.following_phase_effect_s,
                recovery_surrender=carry,
                source_artifact_ids=(artifact.artifact_id,),
            )
            if measured_delta is not None
            else None
        )
    else:
        problem = ProblemFingerprint.build(
            phase="whole_run",
            physical_region="run scope",
            time_origin_class="unavailable",
            carry_behavior="unavailable",
            driver_demand_state="unresolved",
            vehicle_response_state="unresolved",
            traffic_context_state=context.traffic_state,
            tire_stint_state=context.tire_state,
            objective=objective_value,
            source_artifact_ids=(artifact.artifact_id,),
        )
        performance = None
    return CurrentLearningInputs(
        context=context,
        problem=problem,
        reasoning=build_p19_reasoning_memory(bundle.report),
        source_provenance=(artifact,),
        performance_response=performance,
        driver_contributions=_driver_contributions(
            bundle=bundle,
            projection=p32,
            opportunity=opportunity,
            artifact_id=artifact.artifact_id,
        ),
    )


def build_current_learning_inputs(
    run_id: str,
    *,
    session_id: str,
    scope_run_ids: tuple[str, ...],
    objective: object,
    bundle: RunIntelligenceBundle | None = None,
    p20: object | None = None,
    p26: object | None = None,
    p32: PerformanceIntelligenceProjection | None = None,
    overview: RunOverview | None = None,
    db_path: str | Path | None = None,
) -> CurrentLearningInputs:
    """Build current P33 inputs, reusing already-built products when supplied."""

    if not scope_run_ids or run_id not in scope_run_ids:
        raise ValueError("P33 requires exact selected-scope membership")
    repository = RaceLabRepository(db_path)
    if bundle is None:
        from racelab_engine.services.run_intelligence_service import (
            build_run_intelligence,
        )

        bundle = build_run_intelligence(run_id, session_id=session_id, db_path=db_path)
    overview = overview or repository.get_overview(run_id)
    if overview is None:
        raise ValueError("P33 requires an imported current run")
    if p32 is None:
        from racelab_engine.services.engineering_projection_service import (
            project_engineering_awareness,
        )
        from racelab_engine.services.performance_intelligence_service import (
            build_performance_intelligence,
        )
        from racelab_engine.services.vehicle_systems_service import (
            build_component_awareness,
            vehicle_systems_runtime_identity,
        )

        p20 = p20 or project_engineering_awareness(bundle)
        if p26 is None:
            try:
                p26 = build_component_awareness(
                    bundle.report,
                    setup_snapshot=overview.setup_snapshot,
                    runtime_identity=vehicle_systems_runtime_identity(run_id),
                )
            except ValueError as exc:
                if not any(
                    marker in str(exc).casefold() for marker in _OPTIONAL_P26_MARKERS
                ):
                    raise
                p26 = None
        p32 = build_performance_intelligence(
            run_id,
            session_id=session_id,
            scope_run_ids=scope_run_ids,
            objective=objective,
            bundle=bundle,
            p20=p20,
            p26=p26,
            overview=overview,
            repository=repository,
        )
    return _build_current_from_products(
        run_id,
        session_id=session_id,
        objective=objective,
        bundle=bundle,
        p32=p32,
        overview=overview,
    )


def _transfer_assessment(
    current: EngineeringExperienceContext,
    record: EngineeringExperienceRecord,
) -> ContextTransferAssessment:
    prior = record.context
    dimensions = {
        "driver": (current.driver_id, prior.driver_id),
        "car_path": (current.car_path, prior.car_path),
        "car_version": (current.car_version, prior.car_version),
        "iRacing_build": (current.iracing_build, prior.iracing_build),
        "track": (current.track, prior.track),
        "track_configuration": (
            current.track_configuration,
            prior.track_configuration,
        ),
        "package_type": (current.package_type, prior.package_type),
        "setup_family": (current.setup_family, prior.setup_family),
        "setup_snapshot": (
            current.setup_snapshot_sha256,
            prior.setup_snapshot_sha256,
        ),
        "objective": (current.objective, prior.objective),
        "physical_scope": (
            current.physical_scope_sha256,
            prior.physical_scope_sha256,
        ),
        "phase": (current.phase, prior.phase),
        "physical_region": (current.physical_region, prior.physical_region),
        "speed_load_band": (current.speed_load_band, prior.speed_load_band),
        "fuel_state": (current.fuel_state, prior.fuel_state),
        "tire_state": (current.tire_state, prior.tire_state),
        "weather_state": (current.weather_state, prior.weather_state),
        "traffic_state": (current.traffic_state, prior.traffic_state),
        "driver_execution_state": (
            current.driver_execution_state,
            prior.driver_execution_state,
        ),
    }
    matching = tuple(
        key for key, values in dimensions.items() if values[0] == values[1]
    )
    mismatched = tuple(
        key for key, values in dimensions.items() if values[0] != values[1]
    )
    blockers: list[str] = []
    if current.car_path != prior.car_path:
        blockers.append("The historical car identity does not match the current car.")
    if current.car_version != prior.car_version:
        blockers.append("The historical car version is not current-context compatible.")
    if current.iracing_build != prior.iracing_build:
        blockers.append(
            "The historical iRacing build is not current-context compatible."
        )
    if current.context_sha256 == prior.context_sha256:
        level: ContextTransferLevel = "exact"
        mismatched = ()
    elif blockers:
        level = "blocked"
    elif all(
        getattr(current, key) == getattr(prior, key)
        for key in (
            "car_path",
            "car_version",
            "iracing_build",
            "track",
            "track_configuration",
            "package_type",
            "objective",
            "phase",
            "physical_region",
            "speed_load_band",
        )
    ):
        # A material execution-state change is concept drift for driver
        # memory. It remains a weak historical clue, never a clean compatible
        # tendency in today's context.
        level = (
            "weak"
            if current.driver_execution_state != prior.driver_execution_state
            else "compatible"
        )
    else:
        level = "weak"
    drift = (
        tuple(
            f"Historical {key.replace('_', ' ')} differs from the current context."
            for key in mismatched
            if key
            in {
                "setup_family",
                "setup_snapshot",
                "speed_load_band",
                "fuel_state",
                "tire_state",
                "weather_state",
                "traffic_state",
                "driver_execution_state",
            }
        )
        if level != "exact"
        else ()
    )
    return ContextTransferAssessment(
        experience_id=record.experience_id,
        level=level,
        matching_dimensions=matching,
        mismatched_dimensions=mismatched,
        drift_reasons=drift,
        blocker_reasons=tuple(blockers),
    )


def _recording_independence_keys(
    records: tuple[EngineeringExperienceRecord, ...],
    *,
    db_path: str | Path | None,
) -> dict[str, str]:
    """Cluster historical experiences by physical source recordings.

    Multiple sessions/investigations may reference the same immutable source,
    but they remain one independence unit.  Pre-P35.4 test/legacy rows without
    a stored full hash retain their existing episode/workflow contract; current
    production imports always carry the source identity and therefore collapse
    filename aliases.
    """

    run_ids = _unique(
        provenance.run_id for record in records for provenance in record.source_provenance
    )
    source_by_run = RaceLabRepository(db_path).get_recording_sha256s(run_ids)
    for run_id in run_ids:
        if run_id in source_by_run or not run_id.startswith(RECORDING_RUN_ID_PREFIX):
            continue
        embedded = normalize_source_sha256(run_id.removeprefix(RECORDING_RUN_ID_PREFIX))
        if embedded is not None:
            source_by_run[run_id] = embedded
    keys: dict[str, str] = {}
    for record in records:
        hashes = {
            source_by_run.get(provenance.run_id)
            for provenance in record.source_provenance
        }
        if None in hashes or not hashes:
            continue
        keys[record.experience_id] = "recording-cluster:" + canonical_json_sha256(
            tuple(sorted(str(value) for value in hashes))
        )
    return keys


def _counts(
    records: Iterable[EngineeringExperienceRecord],
    independence_keys: Mapping[str, str] | None = None,
) -> EvidenceUnitCounts:
    values = tuple(records)
    if independence_keys is not None:
        episode_units = {
            independence_keys.get(item.experience_id)
            or item.problem.physical_episode_id
            or item.source_investigation_id
            or item.source_workflow_id
            or item.experience_id
            for item in values
        }
        workflow_units = {
            independence_keys.get(item.experience_id) or item.source_workflow_id
            for item in values
            if item.source_workflow_id is not None
        }
        independent_count = len(episode_units)
        return EvidenceUnitCounts(
            observation_count=len(values),
            independent_episode_count=independent_count,
            independent_workflow_count=len(workflow_units),
            distinct_session_count=min(
                len({item.context.session_id for item in values}), independent_count
            ),
            distinct_context_count=min(
                len({item.context.context_sha256 for item in values}), independent_count
            ),
        )
    return EvidenceUnitCounts(
        observation_count=len(values),
        independent_episode_count=len(
            {
                item.problem.physical_episode_id
                or item.source_investigation_id
                or item.source_workflow_id
                or item.experience_id
                for item in values
            }
        ),
        independent_workflow_count=len(
            {
                item.source_workflow_id
                for item in values
                if item.source_workflow_id is not None
            }
        ),
        distinct_session_count=len({item.context.session_id for item in values}),
        distinct_context_count=len({item.context.context_sha256 for item in values}),
    )


def _strength(
    records: Iterable[EngineeringExperienceRecord],
    *,
    conflicted: bool = False,
    independence_keys: Mapping[str, str] | None = None,
) -> LearningStrength:
    values = tuple(records)
    counts = _counts(values, independence_keys)
    if not values:
        return "insufficient"
    if conflicted:
        return "conflicted"
    if counts.independent_workflow_count >= 2:
        return "controlled_repeated"
    if counts.distinct_context_count >= 2 and counts.independent_episode_count >= 2:
        return "cross_context_supported"
    if counts.distinct_session_count >= 2 and counts.independent_episode_count >= 2:
        return "repeated_multi_session"
    if counts.independent_episode_count >= 2:
        return "repeated_same_context"
    return "single_case"


def _empty_ledger() -> EngineeringLearningLedger:
    return EngineeringLearningLedger(
        investigations_opened=0,
        investigations_resolved=0,
        no_call_outcomes=0,
        driver_focus_outcomes=0,
        measurement_missions=0,
        controlled_tests=0,
        keep_outcomes=0,
        undo_outcomes=0,
        retest_outcomes=0,
        laps_consumed_before_resolution=0,
        questions_asked=0,
        recurring_problem_count=0,
        recurrence_resolved_faster_count=0,
    )


def _ledger(
    records: tuple[EngineeringExperienceRecord, ...],
) -> EngineeringLearningLedger:
    investigations = tuple(
        item.investigation_outcome
        for item in records
        if item.investigation_outcome is not None
    )
    car_responses = tuple(
        item.car_response for item in records if item.car_response is not None
    )
    tool_counts = Counter(
        tool for item in investigations for tool in item.tools_inspected
    )
    resolved = tuple(
        item for item in investigations if item.terminal_decision != "abandoned"
    )
    return EngineeringLearningLedger(
        investigations_opened=len(investigations),
        investigations_resolved=len(resolved),
        no_call_outcomes=sum(item.terminal_decision == "no_call" for item in resolved),
        driver_focus_outcomes=sum(
            item.terminal_decision == "driver_focus" for item in resolved
        ),
        measurement_missions=sum(
            item.terminal_decision == "measurement_only" for item in resolved
        ),
        controlled_tests=sum(
            item.terminal_decision == "controlled_test" for item in resolved
        ),
        keep_outcomes=sum(item.policy_verdict == "keep" for item in car_responses),
        undo_outcomes=sum(item.policy_verdict == "undo" for item in car_responses),
        retest_outcomes=sum(item.policy_verdict == "retest" for item in car_responses),
        average_tool_steps_before_resolution=(
            sum(item.tool_steps_consumed for item in resolved) / len(resolved)
            if resolved
            else None
        ),
        laps_consumed_before_resolution=sum(item.laps_consumed for item in resolved),
        questions_asked=sum(item.driver_questions_consumed for item in investigations),
        repeated_dead_end_tools=tuple(
            sorted(tool for tool, count in tool_counts.items() if count >= 2)
        ),
        successful_discriminators=_unique(
            discriminator
            for item in investigations
            for discriminator in item.successful_discriminator_ids
        ),
        recurring_problem_count=len(
            {
                item.problem.problem_sha256
                for item in records
                if sum(
                    peer.problem.problem_sha256 == item.problem.problem_sha256
                    for peer in records
                )
                >= 2
            }
        ),
        # A confirmed historical match is not a speed comparison.  This remains
        # zero until paired operational baselines prove a faster resolution.
        recurrence_resolved_faster_count=0,
    )


def _new_recurrence(
    current: CurrentLearningInputs,
    *,
    blocker: str,
) -> RecurringProblemMatch:
    return RecurringProblemMatch(
        recurrence_id="p33rec_"
        + canonical_json_sha256([current.problem.problem_sha256, "new"])[:24],
        classification="new_problem",
        problem_sha256s=(current.problem.problem_sha256,),
        statement="No prior recurrence is qualified.",
        strongest_contradiction=blocker,
        counts=_counts(()),
        strength="insufficient",
    )


def _recurrence(
    current: CurrentLearningInputs,
    records: tuple[EngineeringExperienceRecord, ...],
    transfers: dict[str, ContextTransferAssessment],
    independence_keys: Mapping[str, str] | None = None,
) -> RecurringProblemMatch:
    matching = tuple(
        item
        for item in records
        if item.problem.problem_sha256 == current.problem.problem_sha256
        and transfers[item.experience_id].level != "blocked"
    )
    if not matching:
        return _new_recurrence(
            current,
            blocker="No independent prior physical episode matches this fingerprint.",
        )
    counts = _counts(matching, independence_keys)
    independent = max(
        counts.independent_episode_count, counts.independent_workflow_count
    )
    exact = tuple(
        item for item in matching if transfers[item.experience_id].level == "exact"
    )
    has_weak_transfer = any(
        transfers[item.experience_id].level == "weak" for item in matching
    )
    if independent >= 2 and len(exact) == len(matching):
        classification: Literal[
            "new_problem",
            "possible_recurrence",
            "strong_recurrence",
            "exact_context_recurrence",
        ] = "exact_context_recurrence"
    elif independent >= 2 and not has_weak_transfer:
        classification = "strong_recurrence"
    else:
        classification = "possible_recurrence"
    investigations = tuple(
        item for item in matching if item.investigation_outcome is not None
    )
    useful_discriminator = next(
        (
            discriminator
            for item in investigations
            for discriminator in item.investigation_outcome.successful_discriminator_ids
        ),
        None,
    )
    prior_dead_end = next(
        (dead_end.statement for item in matching for dead_end in item.dead_ends),
        None,
    )
    transfer = min(
        (transfers[item.experience_id] for item in matching),
        key=lambda item: (_TRANSFER_ORDER[item.level], item.experience_id),
    )
    return RecurringProblemMatch(
        recurrence_id="p33rec_"
        + canonical_json_sha256(
            [
                current.problem.problem_sha256,
                tuple(item.experience_id for item in matching),
            ]
        )[:24],
        classification=classification,
        problem_sha256s=_unique(
            [
                current.problem.problem_sha256,
                *(item.problem.problem_sha256 for item in matching),
            ]
        ),
        experience_ids=tuple(item.experience_id for item in matching),
        investigation_ids=tuple(
            item.source_investigation_id
            for item in investigations
            if item.source_investigation_id is not None
        ),
        statement=(
            "Independent prior cases share this physical problem fingerprint."
            if independent >= 2
            else "One prior case shares this physical problem fingerprint."
        ),
        useful_discriminator=useful_discriminator,
        prior_dead_end=prior_dead_end,
        strongest_contradiction=(
            "Transfer remains attention-only and does not establish the current cause."
        ),
        transfer=transfer,
        counts=counts,
        strength=_strength(matching, independence_keys=independence_keys),
    )


def _investigation_records(
    records: tuple[EngineeringExperienceRecord, ...],
    transfers: dict[str, ContextTransferAssessment],
    independence_keys: Mapping[str, str] | None = None,
) -> tuple[InvestigationOutcomeRecord, ...]:
    projected: list[InvestigationOutcomeRecord] = []
    for record in records:
        fact = record.investigation_outcome
        transfer = transfers[record.experience_id]
        if fact is None or transfer.level == "blocked":
            continue
        useful = bool(
            fact.successful_discriminator_ids
            or fact.completed_measurement_ids
            or fact.terminal_decision in {"controlled_test", "driver_focus"}
        )
        if not useful:
            continue
        projected.append(
            InvestigationOutcomeRecord(
                outcome_id="p33inv_"
                + canonical_json_sha256([record.experience_id, fact.investigation_id])[
                    :24
                ],
                experience_id=record.experience_id,
                transfer_level=transfer.level,
                outcome=fact,
                counts=_counts((record,), independence_keys),
                useful=useful,
                explanation=(
                    "This prior investigation reached a recorded discriminator or terminal evidence state."
                    if useful
                    else "This prior investigation ended without a qualified discriminator."
                ),
            )
        )
    return tuple(projected)


def _dead_end_records(
    records: tuple[EngineeringExperienceRecord, ...],
    transfers: dict[str, ContextTransferAssessment],
    independence_keys: Mapping[str, str] | None = None,
) -> tuple[EngineeringDeadEndRecord, ...]:
    grouped: dict[
        tuple[str, str | None, str | None, str | None],
        list[tuple[EngineeringExperienceRecord, DeadEndFact]],
    ] = defaultdict(list)
    for record in records:
        if transfers[record.experience_id].level == "blocked":
            continue
        for fact in record.dead_ends:
            grouped[
                (fact.kind, fact.tool_id, fact.component_family, fact.control)
            ].append((record, fact))
    projected: list[EngineeringDeadEndRecord] = []
    for key in sorted(grouped, key=lambda item: tuple(value or "" for value in item)):
        pairs = grouped[key]
        group_records = tuple({item.experience_id: item for item, _ in pairs}.values())
        facts = tuple(fact for _, fact in pairs)
        transfer_level = max(
            (transfers[item.experience_id].level for item in group_records),
            key=lambda level: _TRANSFER_ORDER[level],
        )
        counts = _counts(group_records, independence_keys)
        repeatable = (
            transfer_level in {"exact", "compatible"}
            and max(
                counts.independent_episode_count,
                counts.independent_workflow_count,
            )
            >= 2
        )
        representative = facts[0]
        merged = DeadEndFact(
            dead_end_id="p33dead_"
            + canonical_json_sha256(
                [key, tuple(item.experience_id for item in group_records)]
            )[:24],
            kind=representative.kind,
            tool_id=representative.tool_id,
            component_family=representative.component_family,
            control=representative.control,
            statement=representative.statement,
            source_artifact_ids=_unique(
                artifact for fact in facts for artifact in fact.source_artifact_ids
            ),
            source_workflow_ids=_unique(
                workflow for fact in facts for workflow in fact.source_workflow_ids
            ),
        )
        projected.append(
            EngineeringDeadEndRecord(
                experience_ids=tuple(item.experience_id for item in group_records),
                transfer_level=transfer_level,
                fact=merged,
                counts=counts,
                may_deprioritize_within_band=repeatable,
            )
        )
    return tuple(projected)


def _driver_fingerprints(
    current: CurrentLearningInputs,
    records: tuple[EngineeringExperienceRecord, ...],
    transfers: dict[str, ContextTransferAssessment],
    independence_keys: Mapping[str, str] | None = None,
) -> tuple[DriverPerformanceFingerprint, ...]:
    if current.context.driver_id is None:
        return ()
    grouped: dict[
        str, list[tuple[EngineeringExperienceRecord, DriverFingerprintContribution]]
    ] = defaultdict(list)
    driver_drift_dimensions = {
        "physical_scope",
        "setup_family",
        "setup_snapshot",
        "speed_load_band",
        "fuel_state",
        "tire_state",
        "weather_state",
        "traffic_state",
        "driver_execution_state",
    }
    for record in records:
        transfer = transfers[record.experience_id]
        weak_driver_drift = (
            transfer.level == "weak"
            and "driver_execution_state" in transfer.mismatched_dimensions
            and not transfer.blocker_reasons
            and set(transfer.mismatched_dimensions).issubset(driver_drift_dimensions)
        )
        if record.context.driver_id != current.context.driver_id or (
            transfer.level not in {"exact", "compatible"} and not weak_driver_drift
        ):
            continue
        for contribution in record.driver_contributions:
            grouped[contribution.metric].append((record, contribution))
    fingerprints: list[DriverPerformanceFingerprint] = []
    for metric in sorted(grouped):
        pairs = grouped[metric]
        group_records = tuple(record for record, _ in pairs)
        counts = _counts(group_records, independence_keys)
        if (
            counts.independent_episode_count < 2
            and counts.independent_workflow_count < 2
        ):
            continue
        statements = {item.statement for _, item in pairs}
        tendency_states = {item.tendency for _, item in pairs}
        current_driver_drift = any(
            "driver_execution_state"
            in transfers[record.experience_id].mismatched_dimensions
            for record in group_records
        )
        state: Literal[
            "repeatable_tendency",
            "context_dependent_tendency",
            "insufficient_history",
            "changed_behavior",
        ]
        if current_driver_drift or "changed_behavior" in tendency_states:
            state = "changed_behavior"
        elif tendency_states == {"repeatable_tendency"} and len(statements) == 1:
            state = "repeatable_tendency"
        else:
            state = "context_dependent_tendency"
        aggregate = DriverFingerprintContribution(
            contribution_id="p33driver_"
            + canonical_json_sha256(
                [metric, tuple(record.experience_id for record in group_records)]
            )[:24],
            metric=metric,
            tendency=state,
            statement=(
                "The measured driver behavior changed across qualified historical episodes."
                if state == "changed_behavior"
                else next(iter(statements))
                if state == "repeatable_tendency"
                else "This driver tendency varied across otherwise compatible contexts."
            ),
            physical_episode_ids=_unique(
                episode for _, item in pairs for episode in item.physical_episode_ids
            ),
            source_artifact_ids=_unique(
                artifact for _, item in pairs for artifact in item.source_artifact_ids
            ),
            source_lap_count=sum(item.source_lap_count for _, item in pairs),
        )
        transfer_level = max(
            (transfers[record.experience_id].level for record in group_records),
            key=lambda level: _TRANSFER_ORDER[level],
        )
        fingerprints.append(
            DriverPerformanceFingerprint(
                fingerprint_id="p33driverfp_"
                + canonical_json_sha256(
                    [current.context.driver_id, metric, aggregate.contribution_id]
                )[:24],
                driver_id=current.context.driver_id,
                transfer_level=transfer_level,
                state=state,
                tendencies=(aggregate,),
                counts=counts,
                source_experience_ids=_unique(
                    record.experience_id for record in group_records
                ),
                contradictions=(
                    (
                        "Current driver execution differs from the qualified historical tendency.",
                    )
                    if current_driver_drift
                    else ("The measured tendency changes across compatible contexts.",)
                    if state in {"context_dependent_tendency", "changed_behavior"}
                    else ()
                ),
            )
        )
    return tuple(fingerprints)


def _car_fingerprints(
    records: tuple[EngineeringExperienceRecord, ...],
    transfers: dict[str, ContextTransferAssessment],
    independence_keys: Mapping[str, str] | None = None,
) -> tuple[CarResponseFingerprint, ...]:
    grouped: dict[tuple[str, str, str, str], list[EngineeringExperienceRecord]] = (
        defaultdict(list)
    )
    for record in records:
        response = record.car_response
        if response is None or transfers[record.experience_id].level == "blocked":
            continue
        grouped[
            (
                response.component,
                response.control,
                response.direction,
                response.magnitude_class,
            )
        ].append(record)
    fingerprints: list[CarResponseFingerprint] = []
    for key in sorted(grouped):
        group_records = tuple(grouped[key])
        representative = group_records[0].car_response
        assert representative is not None
        workflows = _unique(
            record.source_workflow_id
            for record in group_records
            if record.source_workflow_id is not None
        )
        if not workflows:
            continue
        transfer_level = max(
            (transfers[record.experience_id].level for record in group_records),
            key=lambda level: _TRANSFER_ORDER[level],
        )
        fingerprints.append(
            CarResponseFingerprint(
                fingerprint_id="p33car_"
                + canonical_json_sha256(
                    [key, tuple(record.experience_id for record in group_records)]
                )[:24],
                transfer_level=transfer_level,
                response=representative,
                counts=_counts(group_records, independence_keys),
                source_experience_ids=tuple(
                    record.experience_id for record in group_records
                ),
                source_workflow_ids=workflows,
                contradictions=tuple(
                    sorted(
                        {
                            "Controlled policy outcomes differed across these historical responses."
                            for record in group_records
                            if record.car_response is not None
                            and record.car_response.policy_verdict
                            != representative.policy_verdict
                        }
                    )
                ),
                statement=(
                    "Controlled history recorded this response class, but current-context transfer is weak."
                    if transfer_level == "weak"
                    else "Controlled history recorded this response class in exact or compatible contexts."
                ),
            )
        )
    return tuple(fingerprints)


def _mind_change_records(
    records: tuple[EngineeringExperienceRecord, ...],
    transfers: dict[str, ContextTransferAssessment],
) -> tuple[MindChangeRecord, ...]:
    return tuple(
        MindChangeRecord(
            experience_id=record.experience_id,
            transfer_level=transfers[record.experience_id].level,
            fact=record.mind_change,
            statement="New recorded evidence changed the stored P19 reasoning state in this prior investigation.",
        )
        for record in records
        if record.mind_change is not None
        and transfers[record.experience_id].level != "blocked"
    )


def _attention_order(
    investigation_records: tuple[InvestigationOutcomeRecord, ...],
    record_by_id: dict[str, EngineeringExperienceRecord],
    independence_keys: Mapping[str, str] | None = None,
) -> tuple[AttentionOrderItem, ...]:
    exact_or_compatible = tuple(
        item
        for item in investigation_records
        if item.transfer_level in {"exact", "compatible"}
    )

    def independent_units(
        values: Iterable[InvestigationOutcomeRecord],
    ) -> tuple[set[str], set[str]]:
        items = tuple(values)
        if independence_keys is not None:
            episode_units = {
                independence_keys.get(item.experience_id)
                or record_by_id[item.experience_id].problem.physical_episode_id
                or item.outcome.investigation_id
                for item in items
            }
            workflow_units = {
                independence_keys.get(item.experience_id)
                or record_by_id[item.experience_id].source_workflow_id
                or next(iter(item.outcome.workflow_ids), item.outcome.investigation_id)
                for item in items
                if item.outcome.workflow_ids
                or record_by_id[item.experience_id].source_workflow_id is not None
            }
            return episode_units, workflow_units
        episode_ids = {
            episode_id
            for item in items
            if (
                episode_id := record_by_id[
                    item.experience_id
                ].problem.physical_episode_id
            )
            is not None
        }
        workflow_ids = {
            workflow_id
            for item in items
            for workflow_id in (
                *item.outcome.workflow_ids,
                *(
                    (record_by_id[item.experience_id].source_workflow_id,)
                    if record_by_id[item.experience_id].source_workflow_id is not None
                    else ()
                ),
            )
        }
        return episode_ids, workflow_ids

    repeated_dead_end_levels: dict[str, set[ContextTransferLevel]] = defaultdict(set)
    dead_end_items: dict[
        tuple[str, ContextTransferLevel],
        dict[str, InvestigationOutcomeRecord],
    ] = defaultdict(dict)
    for item in exact_or_compatible:
        record = record_by_id[item.experience_id]
        for dead_end in record.dead_ends:
            if (
                dead_end.kind == "repeated_no_finding_tool"
                and dead_end.tool_id in _ATTENTION_TOOLS
            ):
                dead_end_items[(dead_end.tool_id, item.transfer_level)][
                    record.experience_id
                ] = item
    for (tool_id, transfer_level), items_by_id in dead_end_items.items():
        episodes, workflows = independent_units(items_by_id.values())
        if max(len(episodes), len(workflows)) >= 2:
            repeated_dead_end_levels[tool_id].add(transfer_level)

    positions: dict[str, list[tuple[int, InvestigationOutcomeRecord]]] = defaultdict(
        list
    )
    for item in exact_or_compatible:
        successful_tools = set(item.outcome.successful_discriminator_ids)
        for index, tool in enumerate(item.outcome.tools_inspected, start=1):
            # A useful investigation does not make every tool in its path
            # useful.  Only an explicitly linked discriminator may earn
            # learned priority.  Repeated no-finding history can remove learned
            # credit, but never removes the tool from Crew's live baseline.
            if (
                tool in _ATTENTION_TOOLS
                and tool in successful_tools
                and not any(
                    _TRANSFER_ORDER[dead_end_level]
                    <= _TRANSFER_ORDER[item.transfer_level]
                    for dead_end_level in repeated_dead_end_levels.get(tool, ())
                )
            ):
                positions[tool].append((index, item))
    qualified = {
        tool: values
        for tool, values in positions.items()
        if len({item.experience_id for _, item in values}) >= 2
        and len({item.outcome.investigation_id for _, item in values}) >= 2
        and max(
            len(independent_units(item for _, item in values)[0]),
            len(independent_units(item for _, item in values)[1]),
        )
        >= 2
    }

    def learned_order(tool_id: str) -> tuple[int, float, int, str]:
        values = qualified[tool_id]
        # Grouped attention uses the most conservative qualified transfer.
        # Exact-only evidence must sort ahead of any group containing merely
        # compatible history; position then captures within-tier efficiency.
        transfer_level = max(
            (item.transfer_level for _, item in values),
            key=lambda level: _TRANSFER_ORDER[level],
        )
        return (
            _TRANSFER_ORDER[transfer_level],
            sum(index for index, _ in values) / len(values),
            _ATTENTION_TOOLS[tool_id][1],
            tool_id,
        )

    learned = sorted(qualified, key=learned_order)
    rank: dict[str, int] = {}
    band_counts: Counter[str] = Counter()
    for tool in learned:
        band = _ATTENTION_TOOLS[tool][0]
        band_counts[band] += 1
        rank[tool] = band_counts[band]
    projected: list[AttentionOrderItem] = []
    for tool in learned:
        values = qualified[tool]
        items = tuple(item for _, item in values)
        experience_ids = _unique(item.experience_id for item in items)
        investigations = {item.outcome.investigation_id for item in items}
        sessions = {
            record_by_id[item.experience_id].context.session_id for item in items
        }
        workflows = {
            workflow for item in items for workflow in independent_units((item,))[1]
        }
        level = max(
            (item.transfer_level for item in items),
            key=lambda value: _TRANSFER_ORDER[value],
        )
        band, baseline = _ATTENTION_TOOLS[tool]
        projected.append(
            AttentionOrderItem(
                tool_id=tool,
                safety_band=band,
                learned_rank_within_band=rank[tool],
                baseline_rank_within_band=baseline,
                reason=(
                    "Prior exact or compatible investigations reached recorded discriminators earlier with this inspection."
                ),
                transfer_level=level,
                source_experience_ids=experience_ids,
                investigation_count=len(investigations),
                session_count=len(sessions),
                independent_workflow_count=len(workflows),
            )
        )
    return tuple(projected)


def _session_memberships(
    session_ids: tuple[str, ...],
    *,
    db_path: str | Path | None,
) -> dict[str, frozenset[str]]:
    if not session_ids:
        return {}
    connection = initialize_database(db_path)
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'racelab_sessions'"
        ).fetchone()
        if table is None:
            return {}
        placeholders = ",".join("?" for _ in session_ids)
        rows = connection.execute(
            "SELECT session_id, run_ids_json FROM racelab_sessions "
            f"WHERE session_id IN ({placeholders})",
            session_ids,
        ).fetchall()
    finally:
        connection.close()
    memberships: dict[str, frozenset[str]] = {}
    for row in rows:
        try:
            run_ids = json.loads(row["run_ids_json"] or "[]")
        except (TypeError, ValueError):
            continue
        if (
            not isinstance(run_ids, list)
            or any(not isinstance(item, str) or not item for item in run_ids)
            or len(run_ids) != len(set(run_ids))
        ):
            continue
        memberships[row["session_id"]] = frozenset(run_ids)
    return memberships


def _evidence_references(
    records: tuple[EngineeringExperienceRecord, ...],
    surfaced_experience_ids: set[str],
    *,
    db_path: str | Path | None,
) -> tuple[LearningEvidenceReference, ...]:
    surfaced = tuple(
        item for item in records if item.experience_id in surfaced_experience_ids
    )
    run_ids = _unique(
        provenance.run_id for item in surfaced for provenance in item.source_provenance
    )
    setups = RaceLabRepository(db_path).get_setup_snapshots(run_ids)
    memberships = _session_memberships(
        _unique(
            provenance.session_id
            for item in surfaced
            for provenance in item.source_provenance
        ),
        db_path=db_path,
    )
    references: list[LearningEvidenceReference] = []
    for record in surfaced:
        for provenance in record.source_provenance:
            setup = setups.get(provenance.run_id)
            blockers: list[str] = []
            if setup is None:
                blockers.append(
                    "The historical source run or setup is no longer available."
                )
            elif (
                setup.setup_id != provenance.setup_id
                or canonical_json_sha256(setup) != provenance.setup_snapshot_sha256
            ):
                blockers.append(
                    "The historical setup identity no longer matches its source."
                )
            if provenance.run_id not in memberships.get(
                provenance.session_id, frozenset()
            ):
                blockers.append(
                    "The historical source session is unavailable or no longer contains this run."
                )
            references.append(
                LearningEvidenceReference.build(
                    experience_id=record.experience_id,
                    provenance=provenance,
                    state="unavailable" if blockers else "available",
                    blocker_reasons=tuple(blockers),
                )
            )
    return tuple(references)


def _post_run_brief(
    *,
    state: Literal["available", "insufficient_history", "blocked"],
    recurrence: RecurringProblemMatch,
    investigations: tuple[InvestigationOutcomeRecord, ...],
    dead_ends: tuple[EngineeringDeadEndRecord, ...],
    mind_changes: tuple[MindChangeRecord, ...],
    attention: tuple[AttentionOrderItem, ...],
    blockers: tuple[str, ...],
) -> PostRunLearningBrief:
    if state != "available":
        return PostRunLearningBrief(state=state, blocker_reasons=blockers)
    return PostRunLearningBrief(
        state="available",
        what_we_learned=(recurrence.statement,),
        what_changed_our_mind=_unique(item.statement for item in mind_changes)[:3],
        what_did_not_work=_unique(item.fact.statement for item in dead_ends)[:3],
        next_attention=_unique(
            f"Review {item.tool_id.replace('_', ' ')} earlier within its existing safety band."
            for item in attention
        )[:3],
    )


def _build_blocked_prior(
    current: CurrentLearningInputs,
    *,
    scope_run_ids: tuple[str, ...],
    p19_reasoning_snapshot_sha256: str,
    p32_projection_sha256: str,
    history_revision: str,
    blocker: str | tuple[str, ...],
) -> CrewChiefLearningPrior:
    blockers = (blocker,) if isinstance(blocker, str) else blocker
    if not blockers:
        raise ValueError("A blocked P33 prior requires exact blocker evidence")
    return CrewChiefLearningPrior.build(
        history_revision=history_revision,
        run_id=current.context.run_id,
        session_id=current.context.session_id,
        objective_id=current.context.objective,
        selected_scope_hash=canonical_json_sha256(scope_run_ids),
        p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
        p32_projection_sha256=p32_projection_sha256,
        current_context_sha256=current.context.context_sha256,
        current_problem_sha256=current.problem.problem_sha256,
        state="blocked",
        recurrence=_new_recurrence(current, blocker=" ".join(blockers)),
        context_transfer_level="blocked",
        strength="insufficient",
        counts=_counts(()),
        ledger=_empty_ledger(),
        post_run_brief=PostRunLearningBrief(state="blocked", blocker_reasons=blockers),
        blocker_reasons=blockers,
    )


def build_crew_chief_learning_prior(
    current: CurrentLearningInputs,
    *,
    scope_run_ids: tuple[str, ...],
    p19_reasoning_snapshot_sha256: str,
    p32_projection_sha256: str,
    repository: EngineeringLearningRepository | None = None,
    db_path: str | Path | None = None,
    max_candidates: int = 128,
) -> CrewChiefLearningPrior:
    """Project bounded history into one deterministic, attention-only prior."""

    if (
        not scope_run_ids
        or current.context.run_id not in scope_run_ids
        or p19_reasoning_snapshot_sha256 != current.reasoning.reasoning_snapshot_sha256
    ):
        raise ValueError("P33 prior inputs must match current P19 and selected scope")
    learning_repository = repository or EngineeringLearningRepository(db_path)
    try:
        state = learning_repository.stream_state()
    except EngineeringLearningIntegrityError as exc:
        return _build_blocked_prior(
            current,
            scope_run_ids=scope_run_ids,
            p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
            p32_projection_sha256=p32_projection_sha256,
            history_revision=canonical_json_sha256(
                {"schema_version": "p33.engineering-learning.v1", "state": "blocked"}
            ),
            blocker=f"Engineering learning history is blocked: {exc}",
        )
    key = (
        *_database_identity(db_path or learning_repository.db_path),
        current.context.context_sha256,
        current.problem.problem_sha256,
        p19_reasoning_snapshot_sha256,
        p32_projection_sha256,
        canonical_json_sha256(scope_run_ids),
        state.history_revision,
        str(max_candidates),
    )
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached
    try:
        query = learning_repository.query_relevant(
            current.context,
            problem=current.problem,
            limit=max_candidates,
        )
    except EngineeringLearningIntegrityError as exc:
        return _build_blocked_prior(
            current,
            scope_run_ids=scope_run_ids,
            p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
            p32_projection_sha256=p32_projection_sha256,
            history_revision=state.history_revision,
            blocker=f"Engineering learning history is blocked: {exc}",
        )
    if query.blockers:
        # A corrupt row selected by the exact relevant-history query is
        # relevant negative evidence, not absence of history. Preserve the
        # repository-authored blocker strings byte-for-byte so P34 can bind
        # and independently reconstruct the corrupt-history control.
        return _build_blocked_prior(
            current,
            scope_run_ids=scope_run_ids,
            p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
            p32_projection_sha256=p32_projection_sha256,
            history_revision=state.history_revision,
            blocker=query.blockers,
        )
    records = query.records
    independence_keys = _recording_independence_keys(
        records,
        db_path=db_path or learning_repository.db_path,
    )
    transfers = {
        record.experience_id: _transfer_assessment(current.context, record)
        for record in records
    }
    transfer_values = tuple(transfers.values())
    recurrence = _recurrence(
        current, records, transfers, independence_keys=independence_keys
    )
    investigations = _investigation_records(
        records, transfers, independence_keys=independence_keys
    )
    dead_ends = _dead_end_records(
        records, transfers, independence_keys=independence_keys
    )
    driver = _driver_fingerprints(
        current, records, transfers, independence_keys=independence_keys
    )
    car = _car_fingerprints(
        records, transfers, independence_keys=independence_keys
    )
    mind_changes = _mind_change_records(records, transfers)
    attention = _attention_order(
        investigations,
        {record.experience_id: record for record in records},
        independence_keys=independence_keys,
    )
    surfaced = (
        {item.experience_id for item in investigations}
        | {experience_id for item in dead_ends for experience_id in item.experience_ids}
        | {
            experience_id
            for item in driver
            for experience_id in item.source_experience_ids
        }
        | {
            experience_id
            for item in car
            for experience_id in item.source_experience_ids
        }
        | {item.experience_id for item in mind_changes}
    )
    references = _evidence_references(
        records, surfaced, db_path=db_path or learning_repository.db_path
    )
    memory_items = (
        len(investigations)
        + len(dead_ends)
        + len(driver)
        + len(car)
        + len(mind_changes)
    )
    blockers = _unique(
        [
            *query.blockers,
            *(
                blocker
                for reference in references
                for blocker in reference.blocker_reasons
            ),
        ]
    )
    if memory_items:
        prior_state: Literal["available", "insufficient_history", "blocked"] = (
            "available"
        )
    else:
        prior_state = "insufficient_history"
        blockers = _unique(
            [*blockers, "No qualified independent engineering history is available."]
        )
        attention = ()
    best_transfer: ContextTransferLevel = (
        min(
            (item.level for item in transfer_values),
            key=lambda level: _TRANSFER_ORDER[level],
        )
        if transfer_values
        else "blocked"
    )
    if best_transfer in {"weak", "blocked"}:
        attention = ()
    counts = _counts(records, independence_keys)
    brief = _post_run_brief(
        state=prior_state,
        recurrence=recurrence,
        investigations=investigations,
        dead_ends=dead_ends,
        mind_changes=mind_changes,
        attention=attention,
        blockers=blockers,
    )
    prior = CrewChiefLearningPrior.build(
        history_revision=query.stream_state.history_revision,
        run_id=current.context.run_id,
        session_id=current.context.session_id,
        objective_id=current.context.objective,
        selected_scope_hash=canonical_json_sha256(scope_run_ids),
        p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
        p32_projection_sha256=p32_projection_sha256,
        current_context_sha256=current.context.context_sha256,
        current_problem_sha256=current.problem.problem_sha256,
        state=prior_state,
        recurrence=recurrence,
        useful_prior_investigations=investigations,
        known_dead_ends=dead_ends,
        driver_tendencies=driver,
        car_response_history=car,
        mind_change_history=mind_changes,
        recommended_attention_order=attention,
        context_transfers=transfer_values,
        evidence_references=references,
        context_transfer_level=best_transfer,
        strength=_strength(records, independence_keys=independence_keys),
        counts=counts,
        ledger=_ledger(records),
        post_run_brief=brief,
        blocker_reasons=blockers,
    )
    with _CACHE_LOCK:
        _CACHE[key] = prior
        if len(_CACHE) > 32:
            _CACHE.pop(next(iter(_CACHE)))
    return prior


def _terminal_kind(
    event: CrewChiefEvent,
    decision: CrewChiefTerminalDecision | None,
) -> Literal[
    "controlled_test",
    "retest",
    "no_call",
    "driver_focus",
    "measurement_only",
    "abandoned",
]:
    if event.event_type == "investigation_abandoned":
        return "abandoned"
    if decision is None:
        raise ValueError("P33 decision events require the exact terminal decision")
    return {
        "controlled_test": "controlled_test",
        "driver_focus": "driver_focus",
        "measurement_mission": "measurement_only",
        "driver_question": "measurement_only",
        "observe_only": "no_call",
        "no_call": "no_call",
    }[decision.kind]


def _cause_transitions(
    opening: P19ReasoningMemory,
    closing: P19ReasoningMemory,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    before = {item.cause_id: item for item in opening.causes}
    after = {item.cause_id: item for item in closing.causes}
    promoted: list[str] = []
    demoted: list[str] = []
    ruled_out: list[str] = []
    status_order = {"likely": 0, "possible": 1, "unresolved": 2, "ruled_out": 3}
    for cause_id in sorted(set(before) & set(after)):
        previous = before[cause_id]
        current = after[cause_id]
        if current.status == "ruled_out" and previous.status != "ruled_out":
            ruled_out.append(cause_id)
        elif (
            current.ordinal_rank < previous.ordinal_rank
            or status_order[current.status] < status_order[previous.status]
        ):
            promoted.append(cause_id)
        elif (
            current.ordinal_rank > previous.ordinal_rank
            or status_order[current.status] > status_order[previous.status]
        ):
            demoted.append(cause_id)
    return tuple(promoted), tuple(demoted), tuple(ruled_out)


def _successful_tool_discriminators(
    *,
    events: tuple[CrewChiefEvent, ...],
    transitioned_cause_ids: tuple[str, ...],
    provenance_by_artifact: dict[str, EngineeringSourceProvenance],
) -> tuple[str, ...]:
    """Credit one exact tool result that survived unchanged authority history."""

    transitioned = set(transitioned_cause_ids)
    qualifying_states = {
        EvidenceState.MEASURED,
        EvidenceState.CALCULATED,
        EvidenceState.CONTROLLED_TEST_EFFECT,
    }
    qualifying: list[CrewChiefEvent] = []
    for index, event in enumerate(events):
        payload = event.payload
        if (
            event.event_type != "tool_result_attached"
            or payload.tool_id is None
            or payload.completed_measurement_ids != (payload.tool_id,)
            or not payload.artifact_ids
            or not set(payload.cause_ids).intersection(transitioned)
            or any(
                later.event_type == "workspace_rebased" for later in events[index + 1 :]
            )
        ):
            continue
        if index == 0:
            continue
        request_event = events[index - 1]
        if (
            request_event.event_type != "tool_invoked"
            or request_event.workspace_revision != event.workspace_revision
            or request_event.payload.tool_id != payload.tool_id
            or request_event.payload.requested_measurement_ids != (payload.tool_id,)
        ):
            continue
        if any(
            artifact_id.startswith("p33ref_")
            or artifact_id not in provenance_by_artifact
            or provenance_by_artifact[artifact_id].evidence_state
            not in qualifying_states
            for artifact_id in payload.artifact_ids
        ):
            continue
        qualifying.append(event)
    if len(qualifying) != 1:
        return ()
    tool_id = qualifying[0].payload.tool_id
    return (tool_id,) if tool_id is not None else ()


def _validate_tool_measurement_order(events: tuple[CrewChiefEvent, ...]) -> None:
    for index, event in enumerate(events):
        payload = event.payload
        if event.event_type == "tool_invoked" and payload.tool_id is not None:
            if index + 1 >= len(events):
                raise ValueError(
                    "P33 tool measurement requests must complete immediately"
                )
            result = events[index + 1]
            if (
                result.event_type != "tool_result_attached"
                or result.workspace_revision != event.workspace_revision
                or result.payload.tool_id != payload.tool_id
                or result.payload.completed_measurement_ids != (payload.tool_id,)
            ):
                raise ValueError(
                    "P33 tool measurement requests must complete immediately"
                )
        elif event.event_type == "tool_result_attached" and payload.tool_id is not None:
            if index == 0:
                raise ValueError(
                    "P33 tool result has no exact preceding measurement request"
                )
            request = events[index - 1]
            if (
                request.event_type != "tool_invoked"
                or request.workspace_revision != event.workspace_revision
                or request.payload.tool_id != payload.tool_id
                or request.payload.requested_measurement_ids != (payload.tool_id,)
            ):
                raise ValueError(
                    "P33 tool result has no exact preceding measurement request"
                )


def build_investigation_experience(
    *,
    investigation: CrewChiefInvestigation,
    events: tuple[CrewChiefEvent, ...],
    current: CurrentLearningInputs,
    terminal_decision: CrewChiefTerminalDecision | None,
    p32_projection_sha256: str,
) -> EngineeringExperienceRecord:
    """Freeze one resolved Crew investigation from its immutable event stream."""

    if not events or any(
        event.investigation_id != investigation.investigation_id
        or event.sequence != index
        for index, event in enumerate(events, start=1)
    ):
        raise ValueError(
            "P33 investigation experience requires one complete event stream"
        )
    terminal_event = events[-1]
    if terminal_event.event_type not in {"decision_emitted", "investigation_abandoned"}:
        raise ValueError("P33 investigation experience requires a terminal event")
    _validate_tool_measurement_order(events)
    if terminal_event.event_type == "decision_emitted" and (
        terminal_decision is None
        or terminal_event.payload.decision_kind != terminal_decision.kind
        or terminal_event.payload.workflow_ids
        != (
            (terminal_decision.workflow_id,)
            if terminal_decision is not None
            and terminal_decision.workflow_id is not None
            else ()
        )
    ):
        raise ValueError("P33 terminal event and decision identities do not match")
    if investigation.opening_problem != current.problem:
        raise ValueError(
            "P33 terminal memory requires the exact immutable opening problem; rebase first"
        )
    opening_identity = investigation.workspace_identity
    if (
        current.context.run_id != opening_identity.run_id
        or current.context.session_id != opening_identity.session_id
        or current.context.setup_snapshot_sha256
        != opening_identity.setup_snapshot_sha256
    ):
        raise ValueError(
            "P33 terminal memory requires the immutable opening run/session/setup provenance"
        )
    opening_run_sources = tuple(
        item
        for item in current.source_provenance
        if item.run_id == opening_identity.run_id
    )
    if not opening_run_sources or any(
        item.session_id != opening_identity.session_id
        or item.setup_id != opening_identity.setup_id
        or item.setup_snapshot_sha256 != opening_identity.setup_snapshot_sha256
        or item.build_context_sha256 != opening_identity.vehicle_runtime_identity_hash
        for item in opening_run_sources
    ):
        raise ValueError(
            "P33 terminal memory requires the immutable opening setup/build identity"
        )
    provenance_by_artifact = {
        item.artifact_id: item for item in current.source_provenance
    }
    cited_event_artifact_ids = _unique(
        artifact
        for event in events
        for artifact in event.payload.artifact_ids
        if not artifact.startswith("p33ref_")
    )
    event_artifact_ids = tuple(
        artifact
        for artifact in cited_event_artifact_ids
        if artifact in provenance_by_artifact
    )
    source_artifact_ids = _unique(
        [*current.problem.source_artifact_ids, *event_artifact_ids]
    )
    tools = tuple(
        event.payload.tool_id
        for event in events
        if event.event_type == "tool_result_attached"
        and event.payload.tool_id is not None
    )
    requested_measurement_ids = _unique(
        measurement_id
        for event in events
        for measurement_id in event.payload.requested_measurement_ids
    )
    completed_measurement_ids = _unique(
        measurement_id
        for event in events
        for measurement_id in event.payload.completed_measurement_ids
    )
    question_ids = tuple(
        event.payload.question_id
        for event in events
        if event.event_type == "driver_question_asked"
        and event.payload.question_id is not None
    )
    answers = tuple(
        event.payload.answer
        for event in events
        if event.event_type == "driver_answer_recorded"
        and event.payload.answer is not None
    )
    closing = current.reasoning
    opening = investigation.opening_reasoning
    promoted, demoted, ruled_out = _cause_transitions(opening, closing)
    closing_by_id = {item.cause_id: item for item in closing.causes}
    opening_ids = tuple(item.cause_id for item in opening.causes)
    successful_discriminators = _successful_tool_discriminators(
        events=events,
        transitioned_cause_ids=(*promoted, *demoted, *ruled_out),
        provenance_by_artifact=provenance_by_artifact,
    )
    reasoning_changed = (
        opening.reasoning_snapshot_sha256 != closing.reasoning_snapshot_sha256
    )
    mind_change_has_exact_provenance = bool(cited_event_artifact_ids) and (
        len(event_artifact_ids) == len(cited_event_artifact_ids)
    )
    terminal_kind = _terminal_kind(terminal_event, terminal_decision)
    elapsed = max(
        0.0,
        (terminal_event.created_at - investigation.opened_at).total_seconds(),
    )
    investigation_fact = InvestigationPathFact(
        investigation_id=investigation.investigation_id,
        started_at=investigation.opened_at,
        completed_at=terminal_event.created_at,
        initial_cause_ids=opening_ids,
        tools_inspected=tools,
        driver_question_ids=question_ids,
        driver_answers=answers,
        requested_measurement_ids=requested_measurement_ids,
        completed_measurement_ids=completed_measurement_ids,
        strongest_contradiction=(
            "Mind-change history was withheld because exact new-artifact provenance was unavailable."
            if reasoning_changed and not mind_change_has_exact_provenance
            else "The recorded investigation retained a contradiction to its opening state."
            if ruled_out or demoted
            else "No contradiction independently established the current cause."
        ),
        eliminated_cause_ids=tuple(
            cause_id
            for cause_id, cause in closing_by_id.items()
            if cause.status == "ruled_out"
        ),
        unresolved_cause_ids=tuple(
            cause_id
            for cause_id, cause in closing_by_id.items()
            if cause.status != "ruled_out"
        ),
        terminal_decision=terminal_kind,
        workflow_ids=terminal_event.payload.workflow_ids,
        elapsed_seconds=elapsed,
        laps_consumed=len(
            {
                lap
                for provenance in current.source_provenance
                for lap in provenance.lap_numbers
            }
        ),
        tool_steps_consumed=len(tools),
        driver_questions_consumed=len(question_ids),
        successful_discriminator_ids=successful_discriminators,
        source_artifact_ids=source_artifact_ids,
        historical_retrieval_used=any(
            artifact.startswith("p33ref_")
            for event in events
            for artifact in event.payload.artifact_ids
        ),
        # Retrieval is not confirmation.  A future typed discriminator may set
        # this only after it explicitly compares the historical match.
        historical_match_confirmed=None,
    )
    mind_change: MindChangeFact | None = None
    if reasoning_changed and mind_change_has_exact_provenance:
        states = tuple(
            _enum_text(provenance_by_artifact[artifact].evidence_state)
            for artifact in event_artifact_ids
        )
        mind_change = MindChangeFact(
            mind_change_id="p33mind_"
            + canonical_json_sha256(
                [
                    investigation.investigation_id,
                    opening.reasoning_snapshot_sha256,
                    closing.reasoning_snapshot_sha256,
                    event_artifact_ids,
                ]
            )[:24],
            before_reasoning=opening,
            after_reasoning=closing,
            new_artifact_ids=event_artifact_ids,
            new_evidence_states=states,
            causes_promoted=promoted,
            causes_demoted=demoted,
            causes_ruled_out=ruled_out,
            measurement_discriminator_id=(
                successful_discriminators[0] if successful_discriminators else None
            ),
            evidence_discriminated=bool(successful_discriminators),
            driver_question_involved=bool(question_ids),
            controlled_evidence_involved=(terminal_kind == "controlled_test"),
            context_gate_involved=any(
                item.evidence_state == EvidenceState.BLOCKED_BY_CONTEXT
                for item in current.source_provenance
            ),
        )
    dead_ends: list[DeadEndFact] = []
    no_finding_tools = _unique(
        event.payload.tool_id
        for event in events
        if event.event_type == "tool_result_attached"
        and event.payload.tool_id is not None
        and not event.payload.artifact_ids
    )
    for tool_id in no_finding_tools:
        dead_ends.append(
            DeadEndFact(
                dead_end_id="p33dead_"
                + canonical_json_sha256(
                    [investigation.investigation_id, "no_finding", tool_id]
                )[:24],
                kind="repeated_no_finding_tool",
                tool_id=tool_id,
                statement=(
                    "This inspection produced no canonical finding in the recorded investigation."
                ),
            )
        )
    if terminal_kind in {"abandoned", "no_call"}:
        dead_ends.append(
            DeadEndFact(
                dead_end_id="p33dead_"
                + canonical_json_sha256(
                    [investigation.investigation_id, terminal_kind]
                )[:24],
                kind=(
                    "failed_investigation"
                    if terminal_kind == "abandoned"
                    else "non_discriminating_measurement"
                ),
                statement=(
                    "The investigation ended without a qualified discriminator."
                ),
                source_artifact_ids=source_artifact_ids,
                source_workflow_ids=terminal_event.payload.workflow_ids,
            )
        )
    source_response_ids = _unique(
        response_id
        for response_id in (
            current.performance_response.source_response_record_id
            if current.performance_response is not None
            else None,
        )
        if response_id is not None
    )
    return EngineeringExperienceRecord.build(
        source_kind="resolved_investigation",
        source_investigation_id=investigation.investigation_id,
        created_at=terminal_event.created_at,
        context=current.context,
        problem=investigation.opening_problem,
        source_p19_reasoning_snapshot_sha256=closing.reasoning_snapshot_sha256,
        source_p32_projection_sha256=(
            p32_projection_sha256 if current.performance_response is not None else None
        ),
        opening_reasoning=opening,
        closing_reasoning=closing,
        driver_contributions=current.driver_contributions,
        performance_response=current.performance_response,
        investigation_outcome=investigation_fact,
        mind_change=mind_change,
        dead_ends=tuple(dead_ends),
        source_event_ids=tuple(event.event_id for event in events),
        source_response_record_ids=source_response_ids,
        source_artifact_ids=source_artifact_ids,
        source_provenance=current.source_provenance,
    )


def _workflow_outcome_axes(
    controlled_outcome: object,
) -> tuple[
    Literal["supported", "weakened", "unchanged", "inconclusive", "invalid"],
    Literal["matched", "missed", "inconclusive", "unavailable", "invalid"],
    Literal["keep", "undo", "retest", "invalid"],
    tuple[str, ...],
    float | None,
    float | None,
    str,
]:
    mechanism = getattr(controlled_outcome, "mechanism", None)
    response = getattr(controlled_outcome, "control_response", None)
    policy = getattr(controlled_outcome, "policy", None)
    mechanism_value = _enum_text(
        getattr(
            mechanism, "state", getattr(controlled_outcome, "outcome", "inconclusive")
        )
    )
    mechanism_state = {
        "supported": "supported",
        "contradicted": "weakened",
        "weakened": "weakened",
        "unchanged": "unchanged",
        "invalid": "invalid",
    }.get(mechanism_value, "inconclusive")
    response_state = _enum_text(
        getattr(
            response,
            "result",
            getattr(controlled_outcome, "control_direction_result", "unavailable"),
        )
    )
    if response_state not in {
        "matched",
        "missed",
        "inconclusive",
        "unavailable",
        "invalid",
    }:
        response_state = "unavailable"
    verdict = _enum_text(
        getattr(policy, "verdict", getattr(controlled_outcome, "verdict", "invalid"))
    )
    if verdict not in {"keep", "undo", "retest", "invalid"}:
        verdict = "invalid"
    countereffects = tuple(
        getattr(
            policy, "countereffects", getattr(controlled_outcome, "countereffects", ())
        )
    )
    effect = getattr(controlled_outcome, "actual_effect_s", None)
    carry = getattr(controlled_outcome, "downstream_carry_effect_s", None)
    phase = str(
        getattr(
            response,
            "phase",
            getattr(controlled_outcome, "phase", "unavailable"),
        )
    )
    return (
        mechanism_state,  # type: ignore[return-value]
        response_state,  # type: ignore[return-value]
        verdict,  # type: ignore[return-value]
        countereffects,
        effect,
        carry,
        phase,
    )


def _workflow_context_and_provenance(
    workflow: ControlledWorkflow,
    repository: RaceLabRepository,
) -> tuple[
    EngineeringExperienceContext,
    ProblemFingerprint,
    tuple[EngineeringSourceProvenance, ...],
]:
    stages = workflow.reproduction_snapshot.get("stages")
    if not isinstance(stages, dict) or set(stages) != {"A", "B", "A2"}:
        raise ValueError(
            "P33 workflow memory requires immutable A/B/A2 reproduction stages"
        )
    run_ids = tuple(
        str(stages[stage].get("run_id") or "") for stage in ("A", "B", "A2")
    )
    if (
        any(not run_id for run_id in run_ids)
        or tuple(workflow.stage_run_ids.get(stage) for stage in ("A", "B", "A2"))
        != run_ids
    ):
        raise ValueError(
            "P33 workflow stage identities do not match reproduction history"
        )
    setups = repository.get_setup_snapshots(run_ids)
    if set(setups) != set(run_ids):
        raise ValueError("P33 workflow memory requires all exact stage setup snapshots")
    binding = workflow.reproduction_snapshot.get("p19_authority_binding")
    if not isinstance(binding, dict):
        raise ValueError(
            "P33 workflow memory requires its immutable P19 authority binding"
        )
    session_id = str(binding.get("session_id") or "")
    if not session_id:
        raise ValueError("P33 workflow authority binding requires its source session")
    packet = workflow.packet
    card = packet.primary_test
    if card is None:
        raise ValueError("P33 scored workflow requires its one-control test card")
    b_stage = stages["B"]
    identity = b_stage.get("compatibility_identity")
    if not isinstance(identity, dict) or not identity:
        raise ValueError("P33 workflow memory requires complete compatibility identity")
    compatibility_hashes = {
        canonical_json_sha256(stages[stage].get("compatibility_identity"))
        for stage in ("A", "B", "A2")
    }
    if len(compatibility_hashes) != 1:
        raise ValueError("P33 workflow memory requires canonical A/B/A2 compatibility")
    setup_b = setups[run_ids[1]]
    setup_hash = canonical_json_sha256(setup_b)
    objective = _objective(
        (workflow.reproduction_snapshot.get("decision_context") or {}).get("objective")
    )
    start_pct = packet.opportunity.start_pct
    end_pct = packet.opportunity.end_pct
    phase = packet.opportunity.phase
    physical_region = packet.canonical_symptom
    driver_state = (
        "matched_inputs"
        if workflow.execution is not None
        and workflow.execution.driver_match_score >= 0.8
        else "unresolved"
    )
    context = EngineeringExperienceContext.build(
        run_id=run_ids[1],
        session_id=session_id,
        driver_id=(
            str(identity.get("driver_user_id"))
            if identity.get("driver_user_id") is not None
            else None
        ),
        car_path=str(identity.get("car_path") or "unknown"),
        car_version=str(identity.get("car_version") or "unknown"),
        iracing_build=str(identity.get("iracing_build_version") or "unknown"),
        track=str(identity.get("track_name") or "unknown"),
        track_configuration=str(identity.get("track_configuration_name") or "unknown"),
        package_type=str(
            identity.get("car_configuration_name")
            or identity.get("track_configuration_name")
            or "unknown"
        ),
        setup_family=None,
        setup_snapshot_sha256=setup_hash,
        objective=objective,
        physical_scope_sha256=canonical_json_sha256(
            {
                "phase": phase,
                "physical_region": physical_region,
                "start_pct": start_pct,
                "end_pct": end_pct,
            }
        ),
        phase=phase,
        physical_region=physical_region,
        speed_load_band="unresolved",
        fuel_state="unresolved",
        tire_state="unresolved",
        weather_state="unresolved",
        traffic_state="unresolved",
        driver_execution_state=driver_state,
    )
    provenance: list[EngineeringSourceProvenance] = []
    artifact_ids: list[str] = []
    for stage, run_id in zip(("A", "B", "A2"), run_ids, strict=True):
        snapshot = stages[stage]
        setup = setups[run_id]
        expected_setup = snapshot.get("setup_fingerprint")
        if expected_setup and expected_setup != canonical_json_sha256(setup):
            raise ValueError("P33 workflow stage setup fingerprint is corrupt")
        artifact_id = f"p33workflow:{workflow.workflow_id}:{stage}"
        artifact_ids.append(artifact_id)
        manifest_identity, build_hash = _manifest_parts(run_id)
        if canonical_json_sha256(manifest_identity) != canonical_json_sha256(
            snapshot.get("compatibility_identity")
        ):
            raise ValueError(
                "P33 workflow build provenance does not match its reproduction stage"
            )
        provenance.append(
            EngineeringSourceProvenance.build(
                artifact_id=artifact_id,
                producer_id="p33.controlled_workflow",
                run_id=run_id,
                session_id=session_id,
                setup_id=setup.setup_id,
                setup_snapshot_sha256=canonical_json_sha256(setup),
                build_context_sha256=build_hash,
                lap_numbers=tuple(snapshot.get("eligible_lap_numbers") or ()),
                lap_pct_start=start_pct,
                lap_pct_end=end_pct,
                phase=phase,
                source_channels=packet.opportunity.source_channels,
                evidence_state=(
                    EvidenceState.CONTROLLED_TEST_EFFECT
                    if workflow.quality is not None
                    and workflow.quality.protocol_valid
                    and workflow.quality.verdict != "invalid"
                    else EvidenceState.UNAVAILABLE
                ),
                polarity="neutral",
            )
        )
    execution = workflow.execution
    carry = (
        "unavailable"
        if execution is None or execution.downstream_carry_effect_s is None
        else "following_phase_gain"
        if execution.downstream_carry_effect_s < 0
        else "following_phase_loss"
        if execution.downstream_carry_effect_s > 0
        else "no_measured_carry"
    )
    problem = ProblemFingerprint.build(
        physical_episode_id=f"p33workflow:{workflow.workflow_id}",
        phase=phase,
        physical_region=physical_region,
        time_origin_class=(
            execution.time_origin_phase
            if execution is not None and execution.time_origin_phase is not None
            else "unavailable"
        ),
        carry_behavior=carry,
        driver_demand_state=driver_state,
        vehicle_response_state="controlled_response_recorded",
        p20_mechanism_families=(
            (packet.primary_cause_bucket,) if packet.primary_cause_bucket else ()
        ),
        p26_component_families=(),
        traffic_context_state="unresolved",
        tire_stint_state="unresolved",
        objective=objective,
        source_artifact_ids=tuple(artifact_ids),
    )
    return context, problem, tuple(provenance)


def build_controlled_workflow_experience(
    workflow: ControlledWorkflow,
    *,
    controlled_outcome: object,
    closing_reasoning: P19ReasoningMemory,
    p19_reasoning_snapshot_sha256: str,
    repository: RaceLabRepository,
) -> EngineeringExperienceRecord:
    """Freeze one fully scored workflow without reading telemetry samples."""

    if (
        workflow.status != "scored"
        or workflow.quality is None
        or workflow.execution is None
        or closing_reasoning.reasoning_snapshot_sha256 != p19_reasoning_snapshot_sha256
    ):
        raise ValueError("P33 workflow experience requires one final P19-bound score")
    expected_stage_run_ids = tuple(
        workflow.stage_run_ids.get(stage) for stage in ("A", "B", "A2")
    )
    if (
        getattr(controlled_outcome, "workflow_id", None) != workflow.workflow_id
        or getattr(controlled_outcome, "source_run_id", None) != workflow.source_run_id
        or tuple(getattr(controlled_outcome, "stage_run_ids", ()))
        != expected_stage_run_ids
    ):
        raise ValueError(
            "P33 controlled outcome must bind the exact workflow/source/A-B-A2 identity"
        )
    context, problem, provenance = _workflow_context_and_provenance(
        workflow, repository
    )
    controlled_response_receipt = workflow.controlled_response_receipt
    if controlled_response_receipt is not None:
        provenance_by_run = {item.run_id: item for item in provenance}
        response_provenance: list[EngineeringSourceProvenance] = []
        for stage in controlled_response_receipt.stages:
            base = provenance_by_run.get(stage.run_id)
            if base is None:
                raise ValueError(
                    "P33 controlled response stage lacks exact run/setup/build provenance"
                )
            for artifact_id in stage.response_artifact_ids:
                response_provenance.append(
                    EngineeringSourceProvenance.build(
                        artifact_id=artifact_id,
                        producer_id="p3543.controlled_response",
                        run_id=base.run_id,
                        session_id=base.session_id,
                        setup_id=base.setup_id,
                        setup_snapshot_sha256=base.setup_snapshot_sha256,
                        build_context_sha256=base.build_context_sha256,
                        lap_numbers=stage.eligible_lap_numbers,
                        lap_pct_start=stage.lap_pct_start,
                        lap_pct_end=stage.lap_pct_end,
                        phase=stage.phase,
                        source_channels=stage.source_channels,
                        evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
                        polarity="neutral",
                    )
                )
        provenance = (*provenance, *response_provenance)
    (
        mechanism,
        control_response,
        verdict,
        countereffects,
        effect,
        carry,
        outcome_phase,
    ) = _workflow_outcome_axes(controlled_outcome)
    if verdict != workflow.quality.verdict:
        raise ValueError("P33 controlled outcome does not match the scored workflow")
    if verdict == "invalid":
        effect = None
        carry = None
    if verdict == "undo" and not countereffects:
        countereffects = (
            "A recorded countereffect made the total controlled response unacceptable.",
        )
    execution = workflow.execution
    card = workflow.packet.primary_test
    assert card is not None
    artifact_ids = tuple(item.artifact_id for item in provenance)
    recovery = (
        "unavailable"
        if carry is None
        else "following_phase_gain"
        if carry < 0
        else "following_phase_loss"
        if carry > 0
        else "no_measured_carry"
    )
    expected_response = (
        "Expected A/B/A2 response relations: "
        + ", ".join(controlled_response_receipt.expected_response_relation_ids)
        + "."
        if controlled_response_receipt is not None
        else "The workflow preserved its predeclared controlled response metric."
    )
    observed_response = (
        "Observed A/B/A2 response deltas: "
        + "; ".join(
            f"{item.relation} {item.label} {item.observed_b_delta:+.6g} {item.units}"
            for item in controlled_response_receipt.observed_metric_deltas[:6]
        )
        + "."
        if controlled_response_receipt is not None
        and controlled_response_receipt.observed_metric_deltas
        else f"The recorded control response was {control_response.replace('_', ' ')}."
    )
    response_speed_band = None
    if controlled_response_receipt is not None and all(
        stage.speed_min_mps is not None and stage.speed_max_mps is not None
        for stage in controlled_response_receipt.stages
    ):
        lower = max(
            stage.speed_min_mps  # type: ignore[arg-type]
            for stage in controlled_response_receipt.stages
        )
        upper = min(
            stage.speed_max_mps  # type: ignore[arg-type]
            for stage in controlled_response_receipt.stages
        )
        if lower <= upper:
            response_speed_band = (lower, upper)
    response = CarResponseFact(
        response_id="p33response_"
        + canonical_json_sha256(
            [workflow.workflow_id, mechanism, control_response, verdict]
        )[:24],
        component=workflow.packet.primary_cause_bucket or "unresolved_component",
        control=card.control_key,
        direction="increase" if card.direction_sign > 0 else "decrease",
        magnitude_class="adjacent",
        expected_vehicle_response=expected_response,
        observed_vehicle_response=observed_response,
        p32_time_origin=execution.time_origin_phase or outcome_phase,
        phase_time_effect_s=effect,
        carry_effect_s=carry,
        recovery_surrender=recovery,
        countereffects=countereffects,
        p19_mechanism_assessment=mechanism,
        control_response_assessment=control_response,
        policy_verdict=verdict,
        source_workflow_id=workflow.workflow_id,
        source_response_record_id=(
            controlled_response_receipt.receipt_id
            if controlled_response_receipt is not None
            else None
        ),
        response_expectation_contract_ids=(
            controlled_response_receipt.expected_response_contract_ids
            if controlled_response_receipt is not None
            else ()
        ),
        response_metric_delta_ids=(
            tuple(
                item.metric_id
                for item in controlled_response_receipt.observed_metric_deltas
            )
            if controlled_response_receipt is not None
            else ()
        ),
        stage_response_artifact_ids=(
            tuple(
                (stage.stage, stage.response_artifact_ids)
                for stage in controlled_response_receipt.stages
            )
            if controlled_response_receipt is not None
            else ()
        ),
        response_phase=(
            controlled_response_receipt.stages[0].phase
            if controlled_response_receipt is not None
            else None
        ),
        response_speed_band_mps=response_speed_band,
        source_artifact_ids=artifact_ids,
    )
    driver_contributions = (
        DriverFingerprintContribution(
            contribution_id="p33driver_"
            + canonical_json_sha256([workflow.workflow_id, "controlled-execution"])[
                :24
            ],
            metric="controlled_test_execution_consistency",
            tendency="context_dependent_tendency",
            statement="Controlled A/B/A2 execution comparability was recorded for this workflow.",
            physical_episode_ids=(problem.physical_episode_id,),
            source_artifact_ids=artifact_ids,
            source_lap_count=sum(len(item.lap_numbers) for item in provenance),
        ),
    )
    dead_ends: tuple[DeadEndFact, ...] = ()
    if verdict == "undo":
        dead_ends = (
            DeadEndFact(
                dead_end_id="p33dead_"
                + canonical_json_sha256([workflow.workflow_id, "undo"])[:24],
                kind="repeated_undo_policy",
                component_family=workflow.packet.primary_cause_bucket,
                control=card.control_key,
                statement="This controlled workflow recorded an Undo policy outcome.",
                source_artifact_ids=artifact_ids,
                source_workflow_ids=(workflow.workflow_id,),
            ),
        )
    return EngineeringExperienceRecord.build(
        source_kind="controlled_workflow",
        source_workflow_id=workflow.workflow_id,
        created_at=workflow.updated_at,
        context=context,
        problem=problem,
        source_p19_reasoning_snapshot_sha256=p19_reasoning_snapshot_sha256,
        closing_reasoning=closing_reasoning,
        driver_contributions=driver_contributions,
        car_response=response,
        dead_ends=dead_ends,
        source_response_record_ids=(
            (controlled_response_receipt.receipt_id,)
            if controlled_response_receipt is not None
            else ()
        ),
        source_artifact_ids=artifact_ids,
        source_provenance=provenance,
    )


__all__ = [
    "CurrentLearningInputs",
    "build_controlled_workflow_experience",
    "build_crew_chief_learning_prior",
    "build_current_learning_inputs",
    "build_investigation_experience",
    "build_p19_reasoning_memory",
    "clear_learning_cache",
]
