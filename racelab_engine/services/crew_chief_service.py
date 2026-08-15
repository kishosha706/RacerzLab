"""Deterministic P27-P33 Crew Chief executive.

This layer schedules inspection and presents one atomic workspace.  It never
recomputes P19 setup or policy authority and never analyzes raw telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterable, Literal

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    CrewChiefComponentPerformanceLinkArtifact,
    CrewChiefCornerPerformanceChainArtifact,
    CrewChiefCritique,
    CrewChiefDriverVehicleSeparationArtifact,
    CrewChiefEvent,
    CrewChiefEventPayload,
    CrewChiefExitCarryArtifact,
    CrewChiefInvestigation,
    CrewChiefLapTimeOpportunityArtifact,
    CrewChiefObjectiveEnvelopeArtifact,
    CrewChiefPathEfficiencyArtifact,
    CrewChiefPerformanceArtifact,
    CrewChiefTerminalDecision,
    CrewChiefTimeLossOriginArtifact,
    CrewChiefToolDefinition,
    CrewChiefToolResult,
    CrewChiefTrackDemandArtifact,
    CrewChiefUnavailablePerformanceArtifact,
    CrewChiefWorkspace,
    CrewChiefWorkspaceIdentity,
    DriverDiagnosticQuestion,
    DriverKnowledgeRecord,
    EngineeringEvidenceIndex,
    EngineeringEvidenceIndexEntry,
    EngineeringObjective,
    FoldedInvestigationState,
    HypothesisInspectionState,
    InvestigationProgress,
    InvestigationSubgoal,
    RunSentinelLap,
    RunSentinelState,
    SuccessContract,
    SuccessMetric,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.experiment import MeasurementAttempt
from racelab_engine.models.engineering_learning import (
    CrewChiefLearningPrior,
    EngineeringSourceProvenance,
    PostRunLearningBrief,
)
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.services.engineering_projection_service import (
    project_engineering_awareness,
)
from racelab_engine.services.engineering_learning_service import (
    CurrentLearningInputs,
    build_crew_chief_learning_prior,
    build_current_learning_inputs,
    build_investigation_experience,
    clear_learning_cache,
)
from racelab_engine.services.performance_intelligence_service import (
    build_performance_intelligence,
)
from racelab_engine.services.run_intelligence_service import (
    RunIntelligenceBundle,
    build_run_intelligence,
)
from racelab_engine.services.import_service import read_telemetry_manifest
from racelab_engine.services.lap_engineering_context_service import (
    mission_lap_context_is_clear,
)
from racelab_engine.services.session_service import get_session
from racelab_engine.services.vehicle_systems_service import (
    build_component_awareness,
    vehicle_systems_runtime_identity,
)
from racelab_engine.storage.crew_chief_repository import (
    CrewChiefRepository,
    crew_chief_event_hash,
)
from racelab_engine.storage.db import default_db_path
from racelab_engine.storage.repository import RaceLabRepository


_CACHE_LOCK = RLock()
_CACHE: dict[tuple[str, str], CrewChiefWorkspace] = {}


@dataclass(frozen=True)
class _UnavailableP26:
    """Private fail-closed P26 view for unsupported graph applicability only.

    P32 still owns measured time/origin/carry when the reviewed component graph
    does not cover a car/build/track.  This sentinel carries exact setup and
    identity hashes, but intentionally exposes no component state or authority.
    """

    setup_id: str
    setup_snapshot_sha256: str
    graph_version: str
    knowledge_graph_sha256: str
    reasoning_snapshot_sha256: str
    runtime_identity: dict[str, str]
    unavailable_reason: str
    component_states: tuple[object, ...] = ()
    leading_component_ids: tuple[str, ...] = ()
    experiment_factors: tuple[object, ...] = ()
    setup_authorized: bool = False

    @property
    def strongest_contradiction(self) -> str:
        return self.unavailable_reason

    @property
    def knowledge_debt(self) -> tuple[str, ...]:
        return (self.unavailable_reason,)


_OPTIONAL_P26_FAILURE_MARKERS = (
    "is unavailable for car path",
    "requires review for car version",
    "requires review for future iracing build",
    "does not cover iracing build",
    "requires an oval track configuration",
)
_TOOLS = (
    CrewChiefToolDefinition(
        tool_id="inspect_data_quality",
        allowed_scope="run",
        input_schema="P19 canonical data-quality contract",
        output_artifact_type="integrity blockers",
        authority_ceiling="context_only",
        required_sources=("p19", "telemetry_health"),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_lap_context",
        allowed_scope="run",
        input_schema="eligible-lap engineering context",
        output_artifact_type="context blockers",
        authority_ceiling="context_only",
        required_sources=("p19", "lap_context"),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_driver_execution",
        allowed_scope="run",
        input_schema="P19 driver-focus and execution evidence",
        output_artifact_type="driver/context distinction",
        authority_ceiling="context_only",
        required_sources=("p19",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_p19_causes",
        allowed_scope="session",
        input_schema="canonical P19 reasoning snapshot",
        output_artifact_type="ranked cause evidence",
        authority_ceiling="measurement_only",
        required_sources=("p19",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_mechanism_episodes",
        allowed_scope="run",
        input_schema="P20 mechanism episodes",
        output_artifact_type="physical episode evidence",
        authority_ceiling="observation_only",
        required_sources=("p20",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_component_state",
        allowed_scope="component",
        input_schema="P26 component projection",
        output_artifact_type="component awareness",
        authority_ceiling="observation_only",
        required_sources=("p26",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_controlled_history",
        allowed_scope="workflow",
        input_schema="exact-context A/B/A2 history",
        output_artifact_type="component response record",
        authority_ceiling="observation_only",
        required_sources=("p19", "p26"),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_measurement_debt",
        allowed_scope="session",
        input_schema="P19 information plan and mind-change criteria",
        output_artifact_type="bounded measurement debt",
        authority_ceiling="measurement_only",
        required_sources=("p19",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_lap_time_opportunity",
        allowed_scope="run",
        input_schema="P32 LapTimeOpportunityMap",
        output_artifact_type="measured time opportunity",
        authority_ceiling="observation_only",
        required_sources=("p32", "time_alignment"),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_time_loss_origin",
        allowed_scope="run",
        input_schema="P32 time-origin vocabulary",
        output_artifact_type="origin and carry classification",
        authority_ceiling="observation_only",
        required_sources=("p32", "time_alignment"),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_corner_performance_chain",
        allowed_scope="run",
        input_schema="P32 CornerPerformanceChain",
        output_artifact_type="connected corner performance chain",
        authority_ceiling="observation_only",
        required_sources=("p32",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_exit_carry",
        allowed_scope="run",
        input_schema="P32 downstream time persistence",
        output_artifact_type="exit and following-straight carry",
        authority_ceiling="observation_only",
        required_sources=("p32",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_path_efficiency",
        allowed_scope="run",
        input_schema="P32 measured path and elapsed time",
        output_artifact_type="path/time comparison",
        authority_ceiling="observation_only",
        required_sources=("p32",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_driver_vehicle_separation",
        allowed_scope="run",
        input_schema="P32 DriverVehicleSeparation",
        output_artifact_type="demand and response distinction",
        authority_ceiling="context_only",
        required_sources=("p32", "p19"),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_track_demand",
        allowed_scope="run",
        input_schema="P32 TrackDemandProfile",
        output_artifact_type="measured track demand",
        authority_ceiling="observation_only",
        required_sources=("p32",),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_component_performance_link",
        allowed_scope="component",
        input_schema="P32 non-causal P20/P26 performance bridge",
        output_artifact_type="component mechanical relevance",
        authority_ceiling="observation_only",
        required_sources=("p32", "p20", "p26"),
    ),
    CrewChiefToolDefinition(
        tool_id="inspect_objective_tradeoff",
        allowed_scope="session",
        input_schema="P32 PerformanceObjectiveEnvelope",
        output_artifact_type="primary and protected outcomes",
        authority_ceiling="context_only",
        required_sources=("p32", "p19"),
    ),
)

_TOOL_SAFETY_BANDS: dict[str, str] = {
    "inspect_data_quality": "integrity",
    "inspect_lap_context": "context",
    "inspect_lap_time_opportunity": "performance_measurement",
    "inspect_time_loss_origin": "performance_measurement",
    "inspect_corner_performance_chain": "performance_measurement",
    "inspect_exit_carry": "performance_measurement",
    "inspect_path_efficiency": "performance_measurement",
    "inspect_driver_vehicle_separation": "performance_measurement",
    "inspect_track_demand": "performance_measurement",
    "inspect_driver_execution": "driver",
    "inspect_p19_causes": "contradiction",
    "inspect_mechanism_episodes": "mechanism_separation",
    "inspect_component_performance_link": "component_separation",
    "inspect_component_state": "component_separation",
    "inspect_controlled_history": "history",
    "inspect_objective_tradeoff": "history",
    "inspect_measurement_debt": "measurement_debt",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _is_optional_p26_applicability_failure(error: ValueError) -> bool:
    message = str(error).casefold()
    return any(marker in message for marker in _OPTIONAL_P26_FAILURE_MARKERS)


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))


def _mechanisms(values: Iterable[str]) -> tuple[MechanismKind, ...]:
    resolved: list[MechanismKind] = []
    for value in values:
        try:
            item = MechanismKind(value)
        except ValueError:
            item = MechanismKind.UNCLASSIFIED
        if item not in resolved:
            resolved.append(item)
    return tuple(resolved)


def _active_workflow_identity(
    bundle: RunIntelligenceBundle,
) -> tuple[str | None, str | None]:
    move = (
        bundle.report.smart_guidance.next_trustworthy_move
        if bundle.report.smart_guidance
        else None
    )
    if move is None or move.workflow_id is None or move.workflow_updated_at is None:
        return None, None
    return move.workflow_id, move.workflow_updated_at.isoformat()


def _workspace_identity(
    bundle: RunIntelligenceBundle,
    *,
    session_id: str,
    scope_run_ids: tuple[str, ...],
    objective: EngineeringObjective,
    investigation_id: str | None,
    event_hashes: tuple[str, ...],
    p20: object,
    p26: object,
    p32: object,
    learning_prior: CrewChiefLearningPrior,
    run_sentinel: RunSentinelState,
) -> CrewChiefWorkspaceIdentity:
    report = bundle.report
    setup_id = getattr(p26, "setup_id", None)
    setup_hash = getattr(p26, "setup_snapshot_sha256", None)
    if not setup_id or not setup_hash:
        raise ValueError("Crew Chief requires an exact captured setup snapshot.")
    workflow_id, workflow_revision = _active_workflow_identity(bundle)
    base = {
        "run_id": report.run_id,
        "session_id": session_id,
        "selected_scope": scope_run_ids,
        "p19": canonical_json_sha256(report.reasoning_snapshot),
        "p20": getattr(p20, "state_revision"),
        "p20_profile": getattr(p20, "profile_hash"),
        "p26_graph": getattr(p26, "graph_version"),
        "p26_graph_hash": getattr(p26, "knowledge_graph_sha256"),
        "p26_reasoning": getattr(p26, "reasoning_snapshot_sha256"),
        "p32_projection": getattr(p32, "projection_sha256"),
        "run_sentinel": canonical_json_sha256(run_sentinel),
        "learning_history": learning_prior.history_revision,
        "learning_projection": learning_prior.projection_sha256,
        "setup_id": setup_id,
        "setup_hash": setup_hash,
        "runtime": canonical_json_sha256(getattr(p26, "runtime_identity")),
        "workflow_id": workflow_id,
        "workflow_revision": workflow_revision,
        "objective": objective.value,
        "investigation_id": investigation_id,
        "event_hashes": event_hashes,
    }
    return CrewChiefWorkspaceIdentity(
        run_id=report.run_id,
        session_id=session_id,
        selected_scope_hash=canonical_json_sha256(scope_run_ids),
        reasoning_snapshot_sha256=base["p19"],
        p20_state_revision=base["p20"],
        p20_profile_hash=base["p20_profile"],
        p26_graph_version=base["p26_graph"],
        p26_knowledge_graph_sha256=base["p26_graph_hash"],
        p26_reasoning_snapshot_sha256=base["p26_reasoning"],
        p32_projection_sha256=base["p32_projection"],
        run_sentinel_sha256=base["run_sentinel"],
        learning_history_revision=base["learning_history"],
        learning_projection_sha256=base["learning_projection"],
        setup_id=setup_id,
        setup_snapshot_sha256=setup_hash,
        vehicle_runtime_identity_hash=base["runtime"],
        active_workflow_id=workflow_id,
        active_workflow_revision=workflow_revision,
        objective_id=objective,
        investigation_id=investigation_id,
        workspace_revision=canonical_json_sha256(base),
    )


def _authority_revision(identity: CrewChiefWorkspaceIdentity) -> str:
    """Hash only the producer-owned reality an investigation may act from."""

    return canonical_json_sha256(
        identity.model_dump(
            mode="json",
            exclude={
                "objective_id",
                "investigation_id",
                "workspace_revision",
                "learning_history_revision",
                "learning_projection_sha256",
                "run_sentinel_sha256",
            },
        )
    )


def _learning_capture_blockers(
    workflows: tuple[ControlledWorkflow, ...],
    events: tuple[CrewChiefEvent, ...],
) -> tuple[str, ...]:
    blockers: list[str] = []
    for workflow in workflows:
        if workflow.learning_capture_state != "blocked":
            continue
        blockers.append(
            "P33 learning capture is blocked for workflow "
            f"{workflow.workflow_id} and attempted experience "
            f"{workflow.learning_capture_experience_id}; no experience exists for that source."
        )
    for event in events:
        capture = event.payload
        if capture.learning_capture_state != "blocked":
            continue
        blockers.append(
            "P33 learning capture is blocked for Crew event "
            f"{event.event_id} and attempted experience "
            f"{capture.learning_capture_experience_id}; no experience exists for that source."
        )
    return _unique(blockers)


def _with_learning_capture_blockers(
    prior: CrewChiefLearningPrior,
    blockers: tuple[str, ...],
) -> CrewChiefLearningPrior:
    if not blockers:
        return prior
    combined = _unique((*prior.blocker_reasons, *blockers))
    body = {
        field_name: getattr(prior, field_name)
        for field_name in CrewChiefLearningPrior.model_fields
        if field_name != "projection_sha256"
    }
    body.update(
        {
            "state": "blocked",
            "recommended_attention_order": (),
            "context_transfer_level": "blocked",
            "post_run_brief": PostRunLearningBrief(
                state="blocked",
                blocker_reasons=combined,
            ),
            "blocker_reasons": combined,
        }
    )
    return CrewChiefLearningPrior.build(**body)


def _workspace_cache_key(
    identity: CrewChiefWorkspaceIdentity, db_path: str | Path | None
) -> tuple[str, str]:
    database = Path(db_path) if db_path is not None else default_db_path()
    resolved = database.resolve()
    try:
        stat = resolved.stat()
        database_identity = f"{resolved}|{stat.st_dev}|{stat.st_ino}"
    except OSError:
        database_identity = str(resolved)
    return database_identity, identity.workspace_revision


def _accepted_authority_revision(
    investigation: CrewChiefInvestigation,
    events: tuple[CrewChiefEvent, ...],
) -> str:
    for event in reversed(events):
        if (
            event.event_type == "workspace_rebased"
            and event.payload.new_authority_revision is not None
        ):
            return event.payload.new_authority_revision
    return _authority_revision(investigation.workspace_identity)


def _accepted_workspace_revision(
    investigation: CrewChiefInvestigation,
    events: tuple[CrewChiefEvent, ...],
) -> str:
    for event in reversed(events):
        if (
            event.event_type == "workspace_rebased"
            and event.payload.new_workspace_revision is not None
        ):
            return event.payload.new_workspace_revision
    return investigation.workspace_identity.workspace_revision


def _authority_stale_reasons(
    investigation: CrewChiefInvestigation | None,
    events: tuple[CrewChiefEvent, ...],
    identity: CrewChiefWorkspaceIdentity,
) -> tuple[str, ...]:
    if investigation is None:
        return ()
    if _accepted_authority_revision(investigation, events) == _authority_revision(
        identity
    ):
        return ()
    return (
        "Crew Chief authority identity changed; explicitly rebase this investigation before it can continue or act.",
    )


def _component_map(p26: object) -> tuple[dict[str, tuple[str, ...]], dict[str, object]]:
    by_cause: dict[str, list[str]] = {}
    states: dict[str, object] = {}
    for state in getattr(p26, "component_states"):
        states[state.component_id] = state
        for cause_id in (*state.supporting_cause_ids, *state.contradicting_cause_ids):
            by_cause.setdefault(cause_id, []).append(state.component_id)
    return ({key: _unique(value) for key, value in by_cause.items()}, states)


def _evidence_index(
    bundle: RunIntelligenceBundle,
    identity: CrewChiefWorkspaceIdentity,
    objective: EngineeringObjective,
    p26: object,
    p32: object | None = None,
    repository: RaceLabRepository | None = None,
    learning_prior: CrewChiefLearningPrior | None = None,
) -> EngineeringEvidenceIndex:
    report = bundle.report
    repository = repository or RaceLabRepository()
    by_cause, states = _component_map(p26)
    entries: dict[str, EngineeringEvidenceIndexEntry] = {}
    source_run_ids = {
        citation.run_id
        for cause in report.reasoning_snapshot.causes
        for citation in (*cause.supporting_evidence, *cause.contradicting_evidence)
    }
    source_identity: dict[str, tuple[str | None, str | None, str | None]] = {}
    source_setups = repository.get_setup_snapshots(tuple(sorted(source_run_ids)))
    for source_run_id in source_run_ids:
        source_setup = source_setups.get(source_run_id)
        source_setup_id = source_setup.setup_id if source_setup is not None else None
        source_setup_hash = (
            canonical_json_sha256(source_setup) if source_setup is not None else None
        )
        try:
            manifest = read_telemetry_manifest(source_run_id)
            build_hash = canonical_json_sha256(
                {
                    "compatibility_identity": manifest.get("compatibility_identity"),
                    "compatibility_fingerprint": manifest.get(
                        "compatibility_fingerprint"
                    ),
                    "source_file_sha256": manifest.get("source_file_sha256"),
                    "cache_version": manifest.get("cache_version"),
                }
            )
        except (OSError, TypeError, ValueError):
            build_hash = None
        source_identity[source_run_id] = (
            source_setup_id,
            source_setup_hash,
            build_hash,
        )
    for cause in report.reasoning_snapshot.causes:
        mechanisms = _mechanisms(cause.mechanism_keys)
        component_ids = by_cause.get(cause.cause_id, ())
        for citation, polarity in (
            *((item, "support") for item in cause.supporting_evidence),
            *((item, "contradiction") for item in cause.contradicting_evidence),
        ):
            artifact_id = citation.event_id or citation.citation_id
            source_setup_id, source_setup_hash, source_build_hash = source_identity[
                citation.run_id
            ]
            provenance_available = all(
                (source_setup_id, source_setup_hash, source_build_hash)
            )
            current = entries.get(artifact_id)
            if current is not None and (
                current.producer_id != "p19.reasoning_snapshot"
                or current.run_id != citation.run_id
                or current.session_id != identity.session_id
                or current.setup_id != source_setup_id
                or current.lap_pct_start != citation.lap_pct_start
                or current.lap_pct_end != citation.lap_pct_end
                or current.phase != citation.phase
            ):
                raise ValueError(
                    "one Crew Chief evidence artifact cannot silently span conflicting physical scopes"
                )
            existing_mechanisms = (
                tuple(item.value for item in current.mechanism_ids) if current else ()
            )
            merged_mechanisms = _unique(
                (*existing_mechanisms, *(item.value for item in mechanisms))
            )
            merged_components = _unique(
                [*(current.component_ids if current else ()), *component_ids]
            )
            merged_laps = _unique(
                str(value)
                for value in (
                    *(current.lap_numbers if current else ()),
                    *(() if citation.lap_number is None else (citation.lap_number,)),
                )
            )
            merged_blockers = _unique(
                [
                    *(current.blocker_reasons if current else ()),
                    *(
                        ("source identity unavailable",)
                        if not provenance_available
                        else ()
                    ),
                    *(
                        ()
                        if citation.valid_for_tuning
                        else ("not qualified for tuning",)
                    ),
                ]
            )
            evidence_state = citation.evidence_state
            if current is not None and current.evidence_state != evidence_state:
                evidence_state = EvidenceState.BLOCKED_BY_CONTEXT
                merged_blockers = _unique(
                    [*merged_blockers, "conflicting evidence-state references"]
                )
            entries[artifact_id] = EngineeringEvidenceIndexEntry(
                artifact_id=artifact_id,
                producer_id="p19.reasoning_snapshot",
                run_id=citation.run_id,
                session_id=identity.session_id,
                setup_id=source_setup_id,
                workspace_run_id=identity.run_id,
                workspace_session_id=identity.session_id,
                workspace_setup_id=identity.setup_id,
                source_run_id=citation.run_id,
                source_session_id=identity.session_id
                if citation.run_id in source_run_ids
                else None,
                source_setup_id=source_setup_id,
                source_setup_sha256=source_setup_hash,
                source_build_context_sha256=source_build_hash,
                source_provenance_available=provenance_available,
                lap_numbers=tuple(int(value) for value in merged_laps),
                lap_pct_start=citation.lap_pct_start,
                lap_pct_end=citation.lap_pct_end,
                phase=citation.phase,
                mechanism_ids=_mechanisms(merged_mechanisms),
                component_ids=merged_components,
                control_keys=_unique(
                    [
                        *(current.control_keys if current else ()),
                        *cause.related_control_keys,
                    ]
                ),
                objective=objective,
                source_channels=_unique(
                    [
                        *(current.source_channels if current else ()),
                        *citation.channels,
                    ]
                ),
                evidence_state=evidence_state,
                polarity=polarity
                if current is None or current.polarity == polarity
                else "neutral",
                blocker_reasons=merged_blockers,
                authority_ceiling=(
                    "measurement_only"
                    if not merged_blockers
                    and (
                        current is None
                        or current.authority_ceiling == "measurement_only"
                    )
                    else "observation_only"
                ),
            )
    for episode in report.reasoning_snapshot.mechanism_episodes:
        artifact_id = episode.episode_id
        component_ids = _unique(
            component_id
            for state in states.values()
            if set(state.supporting_artifact_ids) & set(episode.supporting_artifact_ids)
            for component_id in (state.component_id,)
        )
        entries.setdefault(
            artifact_id,
            EngineeringEvidenceIndexEntry(
                artifact_id=artifact_id,
                producer_id="p20.mechanism_episode",
                run_id=episode.run_id,
                session_id=identity.session_id,
                setup_id=episode.setup_id,
                workspace_run_id=identity.run_id,
                workspace_session_id=identity.session_id,
                workspace_setup_id=identity.setup_id,
                source_run_id=episode.run_id,
                source_session_id=identity.session_id,
                source_setup_id=episode.setup_id,
                source_setup_sha256=(
                    identity.setup_snapshot_sha256
                    if episode.setup_id == identity.setup_id
                    else None
                ),
                source_build_context_sha256=(
                    identity.vehicle_runtime_identity_hash
                    if episode.setup_id == identity.setup_id
                    else None
                ),
                source_provenance_available=episode.setup_id == identity.setup_id,
                lap_numbers=episode.lap_scope,
                lap_pct_start=episode.lap_pct_start,
                lap_pct_end=episode.lap_pct_end,
                phase=episode.phase,
                mechanism_ids=episode.supporting_mechanism_kinds,
                component_ids=component_ids,
                objective=objective,
                evidence_state=(
                    EvidenceState.BLOCKED_BY_CONTEXT
                    if episode.context_blockers
                    else EvidenceState.OBSERVED_CORRELATION
                ),
                polarity="support",
                blocker_reasons=_unique(
                    (
                        *episode.context_blockers,
                        *(
                            ("source identity unavailable",)
                            if episode.setup_id != identity.setup_id
                            else ()
                        ),
                    )
                ),
                authority_ceiling="observation_only",
            ),
        )
    p26_unavailable_reason = getattr(p26, "unavailable_reason", None)
    if p26_unavailable_reason:
        artifact_id = (
            "p26.component-state:unavailable:"
            f"{canonical_json_sha256([identity.run_id, p26_unavailable_reason])[:16]}"
        )
        entries[artifact_id] = EngineeringEvidenceIndexEntry(
            artifact_id=artifact_id,
            producer_id="p26.component_state_unavailable",
            run_id=identity.run_id,
            session_id=identity.session_id,
            setup_id=identity.setup_id,
            workspace_run_id=identity.run_id,
            workspace_session_id=identity.session_id,
            workspace_setup_id=identity.setup_id,
            source_run_id=identity.run_id,
            source_session_id=identity.session_id,
            source_setup_id=identity.setup_id,
            source_setup_sha256=identity.setup_snapshot_sha256,
            source_build_context_sha256=identity.vehicle_runtime_identity_hash,
            source_provenance_available=True,
            objective=objective,
            evidence_state=EvidenceState.UNAVAILABLE,
            polarity="neutral",
            blocker_reasons=(p26_unavailable_reason,),
            authority_ceiling="observation_only",
        )
    p32_producers = {
        "p32.lap_time_opportunity",
        "p32.time_loss_origin",
        "p32.corner_performance_chain",
        "p32.exit_carry",
        "p32.path_efficiency",
        "p32.driver_vehicle_separation",
        "p32.track_demand",
        "p32.component_performance_link",
        "p32.objective_envelope",
    }
    if p32 is not None:
        basis = getattr(p32, "basis")
        source_laps = tuple(getattr(basis, "source_lap_numbers", ()))
        basis_blockers = tuple(getattr(basis, "context_blockers", ()))

        def add_p32_entry(
            *,
            artifact_id: str,
            producer_id: str,
            phase: str,
            start_pct: float = 0.0,
            end_pct: float = 100.0,
            state: EvidenceState = EvidenceState.CALCULATED,
            source_channels: tuple[str, ...] = (),
            mechanisms: tuple[str, ...] = (),
            components: tuple[str, ...] = (),
            blockers: tuple[str, ...] = (),
            authority: Literal["observation_only", "context_only"] = "observation_only",
            typed_artifact: CrewChiefPerformanceArtifact,
        ) -> None:
            entries[artifact_id] = EngineeringEvidenceIndexEntry(
                artifact_id=artifact_id,
                producer_id=producer_id,
                run_id=identity.run_id,
                session_id=identity.session_id,
                setup_id=identity.setup_id,
                workspace_run_id=identity.run_id,
                workspace_session_id=identity.session_id,
                workspace_setup_id=identity.setup_id,
                source_run_id=identity.run_id,
                source_session_id=identity.session_id,
                source_setup_id=identity.setup_id,
                source_setup_sha256=identity.setup_snapshot_sha256,
                source_build_context_sha256=identity.vehicle_runtime_identity_hash,
                source_provenance_available=True,
                lap_numbers=source_laps,
                lap_pct_start=start_pct,
                lap_pct_end=end_pct,
                phase=phase,
                mechanism_ids=_mechanisms(mechanisms),
                component_ids=_unique(components),
                objective=objective,
                source_channels=_unique(source_channels),
                evidence_state=state,
                polarity="neutral",
                blocker_reasons=_unique(blockers),
                typed_artifact=typed_artifact,
                authority_ceiling=authority,
            )

        opportunities = tuple(
            getattr(getattr(p32, "opportunity_map"), "opportunities", ())
        )
        for opportunity in opportunities:
            context_state = _enum_text(opportunity.context_state)
            qualified_context = context_state in {"qualified", "qualified_pair"}
            opportunity_blockers = _unique(
                (
                    *basis_blockers,
                    *(opportunity.contradictions if not qualified_context else ()),
                )
            )
            opportunity_state = (
                EvidenceState.OBSERVED_CORRELATION
                if qualified_context
                else EvidenceState.BLOCKED_BY_CONTEXT
            )
            add_p32_entry(
                artifact_id=opportunity.opportunity_id,
                producer_id="p32.lap_time_opportunity",
                phase=opportunity.phase,
                start_pct=opportunity.start_pct,
                end_pct=opportunity.end_pct,
                state=opportunity_state,
                source_channels=opportunity.source_channels,
                mechanisms=opportunity.mechanism_candidates,
                components=opportunity.component_candidates,
                blockers=opportunity_blockers,
                typed_artifact=CrewChiefLapTimeOpportunityArtifact(
                    opportunity=opportunity
                ),
            )
            origin_available = _enum_text(opportunity.origin_kind) != "unavailable"
            add_p32_entry(
                artifact_id=f"{opportunity.opportunity_id}:time-origin",
                producer_id="p32.time_loss_origin",
                phase=opportunity.phase,
                start_pct=opportunity.start_pct,
                end_pct=opportunity.end_pct,
                state=(
                    opportunity_state if origin_available else EvidenceState.UNAVAILABLE
                ),
                source_channels=opportunity.source_channels,
                mechanisms=opportunity.mechanism_candidates,
                components=opportunity.component_candidates,
                blockers=_unique(
                    (
                        *opportunity_blockers,
                        *(
                            ("Time origin is unavailable for this window.",)
                            if not origin_available
                            else ()
                        ),
                    )
                ),
                typed_artifact=(
                    CrewChiefTimeLossOriginArtifact(opportunity=opportunity)
                    if origin_available
                    else CrewChiefUnavailablePerformanceArtifact(
                        claimed_artifact_type="time_loss_origin",
                        blocker_reasons=_unique(
                            (
                                *opportunity_blockers,
                                "Time origin is unavailable for this window.",
                            )
                        ),
                    )
                ),
            )
            if opportunity.following_phase_effect_s is not None:
                add_p32_entry(
                    artifact_id=f"{opportunity.opportunity_id}:exit-carry",
                    producer_id="p32.exit_carry",
                    phase="following_straight_carry",
                    start_pct=opportunity.following_phase_start_pct,
                    end_pct=opportunity.following_phase_end_pct,
                    state=opportunity_state,
                    source_channels=opportunity.source_channels,
                    mechanisms=opportunity.mechanism_candidates,
                    components=opportunity.component_candidates,
                    blockers=opportunity_blockers,
                    typed_artifact=CrewChiefExitCarryArtifact(opportunity=opportunity),
                )

        chains = tuple(getattr(p32, "corner_chains", ()))
        for chain in chains:
            phase_states = tuple(
                state
                for state in (
                    chain.approach_state,
                    chain.braking_state,
                    chain.entry_state,
                    chain.center_state,
                    chain.exit_state,
                    chain.carry_state,
                )
                if state is not None
            )
            chain_start = min((state.start_pct for state in phase_states), default=0.0)
            chain_end = max((state.end_pct for state in phase_states), default=100.0)
            if chain_start > chain_end:
                chain_start, chain_end = 0.0, 100.0
            chain_channels = _unique(
                channel for state in phase_states for channel in state.source_channels
            )
            chain_has_time = bool(
                phase_states
                or chain.local_time_effect_s is not None
                or chain.downstream_time_effect_s is not None
            )
            chain_blockers = _unique(
                (
                    *basis_blockers,
                    *(
                        ("No measured corner-chain state is available.",)
                        if not chain_has_time
                        else ()
                    ),
                )
            )
            add_p32_entry(
                artifact_id=chain.chain_id,
                producer_id="p32.corner_performance_chain",
                phase="corner_chain",
                start_pct=chain_start,
                end_pct=chain_end,
                state=(
                    EvidenceState.CALCULATED
                    if chain_has_time and not basis_blockers
                    else EvidenceState.BLOCKED_BY_CONTEXT
                    if chain_has_time
                    else EvidenceState.UNAVAILABLE
                ),
                source_channels=chain_channels,
                blockers=chain_blockers,
                typed_artifact=(
                    CrewChiefCornerPerformanceChainArtifact(
                        start_pct=chain_start,
                        end_pct=chain_end,
                        chain=chain,
                    )
                    if chain_has_time
                    else CrewChiefUnavailablePerformanceArtifact(
                        claimed_artifact_type="corner_performance_chain",
                        blocker_reasons=chain_blockers,
                    )
                ),
            )
            for phase_state in phase_states:
                if phase_state.path_delta_m is None:
                    continue
                add_p32_entry(
                    artifact_id=f"{chain.chain_id}:path:{phase_state.phase}",
                    producer_id="p32.path_efficiency",
                    phase=phase_state.phase,
                    start_pct=phase_state.start_pct,
                    end_pct=phase_state.end_pct,
                    state=(
                        EvidenceState.CALCULATED
                        if not basis_blockers
                        else EvidenceState.BLOCKED_BY_CONTEXT
                    ),
                    source_channels=phase_state.source_channels,
                    blockers=basis_blockers,
                    typed_artifact=CrewChiefPathEfficiencyArtifact(
                        chain_id=chain.chain_id,
                        phase_state=phase_state,
                    ),
                )
            for separation in chain.driver_vehicle_separation:
                separation_state = _enum_text(separation.result)
                separation_blocked = separation_state in {
                    "context_contaminated",
                    "unresolved",
                }
                add_p32_entry(
                    artifact_id=separation.separation_id,
                    producer_id="p32.driver_vehicle_separation",
                    phase=separation.phase,
                    start_pct=chain_start,
                    end_pct=chain_end,
                    state=(
                        EvidenceState.BLOCKED_BY_CONTEXT
                        if separation_blocked
                        else EvidenceState.OBSERVED_CORRELATION
                    ),
                    source_channels=chain_channels,
                    blockers=_unique(
                        (
                            *basis_blockers,
                            *separation.blockers,
                            *(separation.contradictions if separation_blocked else ()),
                        )
                    ),
                    authority="context_only",
                    typed_artifact=CrewChiefDriverVehicleSeparationArtifact(
                        chain_id=chain.chain_id,
                        track_region=chain.track_region,
                        start_pct=chain_start,
                        end_pct=chain_end,
                        separation=separation,
                    ),
                )

        track_demand = getattr(p32, "track_demand")
        track_metrics = (
            track_demand.full_throttle_fraction,
            track_demand.braking_fraction,
            track_demand.cornering_fraction,
            track_demand.speed_min_mph,
            track_demand.speed_max_mph,
            track_demand.disturbance_exposure_fraction,
            track_demand.traffic_exposure_fraction,
        )
        track_available = any(value is not None for value in track_metrics)
        add_p32_entry(
            artifact_id=f"p32-track-demand:{canonical_json_sha256(track_demand)[:20]}",
            producer_id="p32.track_demand",
            phase="whole_run",
            state=(
                EvidenceState.CALCULATED
                if track_available
                else EvidenceState.UNAVAILABLE
            ),
            source_channels=track_demand.source_channels,
            blockers=_unique(
                (
                    *track_demand.blockers,
                    *(
                        ("Measured track demand is unavailable.",)
                        if not track_available
                        else ()
                    ),
                )
            ),
            typed_artifact=(
                CrewChiefTrackDemandArtifact(profile=track_demand)
                if track_available
                else CrewChiefUnavailablePerformanceArtifact(
                    claimed_artifact_type="track_demand",
                    blocker_reasons=_unique(
                        (
                            *track_demand.blockers,
                            "Measured track demand is unavailable.",
                        )
                    ),
                )
            ),
        )

        for influence in getattr(p32, "component_influences", ()):
            support_state = _enum_text(influence.runtime_support_state)
            evidence_state = {
                "controlled_response_observed": EvidenceState.CONTROLLED_TEST_EFFECT,
                "response_supported": EvidenceState.OBSERVED_CORRELATION,
            }.get(support_state, EvidenceState.NEEDS_CONFIRMATION)
            add_p32_entry(
                artifact_id=influence.influence_id,
                producer_id="p32.component_performance_link",
                phase="component_performance_link",
                state=evidence_state,
                source_channels=influence.measurable_through,
                mechanisms=influence.performance_mechanism_ids,
                components=(influence.component_id,),
                blockers=(),
                typed_artifact=CrewChiefComponentPerformanceLinkArtifact(
                    influence=influence
                ),
            )

        envelope = getattr(p32, "objective_envelope")
        add_p32_entry(
            artifact_id=f"p32-objective:{canonical_json_sha256(envelope)[:20]}",
            producer_id="p32.objective_envelope",
            phase="whole_run",
            state=EvidenceState.CALCULATED,
            authority="context_only",
            typed_artifact=CrewChiefObjectiveEnvelopeArtifact(envelope=envelope),
        )

        present_producers = {
            entry.producer_id
            for entry in entries.values()
            if entry.producer_id in p32_producers
        }
        unavailable_reasons = {
            "p32.lap_time_opportunity": "No measured lap-time opportunity is available in this exact comparison.",
            "p32.time_loss_origin": "No qualified time-loss origin is available in this exact comparison.",
            "p32.corner_performance_chain": "No qualified corner performance chain is available.",
            "p32.exit_carry": "No qualified exit or following-straight carry effect is available.",
            "p32.path_efficiency": "No measured path/time comparison is available.",
            "p32.driver_vehicle_separation": "Driver-demand versus vehicle-response separation is unresolved.",
            "p32.track_demand": "Measured track demand is unavailable.",
            "p32.component_performance_link": getattr(
                p26,
                "unavailable_reason",
                "No non-causal P20/P26 component-performance link is available.",
            ),
            "p32.objective_envelope": "The P32 objective envelope is unavailable.",
        }
        for producer_id in sorted(p32_producers - present_producers):
            reason = unavailable_reasons[producer_id]
            add_p32_entry(
                artifact_id=f"{producer_id}:unavailable:{canonical_json_sha256([identity.run_id, reason])[:16]}",
                producer_id=producer_id,
                phase="unavailable",
                state=EvidenceState.UNAVAILABLE,
                blockers=_unique((*basis_blockers, reason)),
                authority=(
                    "context_only"
                    if producer_id
                    in {
                        "p32.driver_vehicle_separation",
                        "p32.objective_envelope",
                    }
                    else "observation_only"
                ),
                typed_artifact=CrewChiefUnavailablePerformanceArtifact(
                    claimed_artifact_type=producer_id.removeprefix("p32."),
                    blocker_reasons=_unique((*basis_blockers, reason)),
                ),
            )
    if learning_prior is not None:
        for reference in learning_prior.evidence_references:
            if reference.state != "available":
                continue
            source = reference.provenance
            entries[reference.reference_id] = EngineeringEvidenceIndexEntry(
                artifact_id=reference.reference_id,
                producer_id="p33.engineering_experience",
                run_id=source.run_id,
                session_id=source.session_id,
                setup_id=source.setup_id,
                workspace_run_id=identity.run_id,
                workspace_session_id=identity.session_id,
                workspace_setup_id=identity.setup_id,
                source_run_id=source.run_id,
                source_session_id=source.session_id,
                source_setup_id=source.setup_id,
                source_setup_sha256=source.setup_snapshot_sha256,
                source_build_context_sha256=source.build_context_sha256,
                source_provenance_available=True,
                lap_numbers=source.lap_numbers,
                lap_pct_start=source.lap_pct_start,
                lap_pct_end=source.lap_pct_end,
                phase=source.phase,
                objective=objective,
                source_channels=source.source_channels,
                evidence_state=source.evidence_state,
                polarity=source.polarity,
                authority_ceiling="attention_only",
            )
    ordered = tuple(entries[key] for key in sorted(entries))
    return EngineeringEvidenceIndex(
        workspace_revision=identity.workspace_revision,
        entries=ordered,
        index_hash=canonical_json_sha256(
            [item.model_dump(mode="json") for item in ordered]
        ),
    )


def fold_investigation(
    investigation: CrewChiefInvestigation,
    events: tuple[CrewChiefEvent, ...],
    causes: tuple[object, ...],
) -> FoldedInvestigationState:
    objective = investigation.objective
    status = investigation.status
    completed_tools: list[str] = []
    pending_question: str | None = None
    answers: list[str] = []
    last_decision: str | None = None
    inspected_causes: set[str] = set()
    stale_reason: str | None = None
    pending_tool_measurement: tuple[str, str] | None = None
    for expected, event in enumerate(events, start=1):
        if (
            event.sequence != expected
            or event.investigation_id != investigation.investigation_id
        ):
            raise ValueError("Crew Chief event fold encountered non-canonical history")
        payload = event.payload
        if pending_tool_measurement is not None and not (
            event.event_type == "tool_result_attached"
            and payload.tool_id == pending_tool_measurement[0]
            and event.workspace_revision == pending_tool_measurement[1]
        ):
            raise ValueError(
                "Crew Chief tool measurement requests must complete immediately"
            )
        if event.event_type == "tool_invoked" and payload.tool_id:
            if pending_tool_measurement is not None:
                raise ValueError(
                    "Crew Chief tool measurement requests must complete in order"
                )
            pending_tool_measurement = (payload.tool_id, event.workspace_revision)
        elif event.event_type == "tool_result_attached" and payload.tool_id:
            if pending_tool_measurement != (payload.tool_id, event.workspace_revision):
                raise ValueError(
                    "Crew Chief tool result has no exact preceding measurement request"
                )
            pending_tool_measurement = None
            completed_tools.append(payload.tool_id)
            inspected_causes.update(payload.cause_ids)
        elif event.event_type == "driver_question_asked":
            pending_question = payload.question_id
        elif event.event_type == "driver_answer_recorded":
            pending_question = None
            if payload.answer:
                answers.append(payload.answer)
        elif event.event_type == "decision_emitted":
            last_decision = payload.decision_kind
            status = "complete"
        elif event.event_type == "objective_selected" and payload.objective:
            objective = payload.objective
        elif event.event_type == "workspace_rebased":
            stale_reason = None
        elif event.event_type == "investigation_abandoned":
            status = "abandoned"
    if pending_tool_measurement is not None:
        raise ValueError(
            "Crew Chief tool measurement requests must complete immediately"
        )
    hypotheses = tuple(
        HypothesisInspectionState(
            cause_id=cause.cause_id,
            p19_state=cause.status,
            progress=(
                InvestigationProgress.INSPECTED
                if cause.cause_id in inspected_causes
                else InvestigationProgress.INSPECTION_PENDING
            ),
            support_artifact_ids=tuple(
                citation.event_id or citation.citation_id
                for citation in cause.supporting_evidence
            ),
            contradiction_artifact_ids=tuple(
                citation.event_id or citation.citation_id
                for citation in cause.contradicting_evidence
            ),
        )
        for cause in causes
    )
    return FoldedInvestigationState(
        investigation_id=investigation.investigation_id,
        status=status,
        event_count=len(events),
        last_sequence=len(events),
        objective=objective,
        completed_tool_ids=_unique(completed_tools),
        pending_driver_question_id=pending_question,
        driver_answers=tuple(answers),
        hypotheses=hypotheses,
        last_decision_kind=last_decision,
        stale_reason=stale_reason,
        accepted_workspace_revision=_accepted_workspace_revision(investigation, events),
    )


def _subgoal(
    bundle: RunIntelligenceBundle,
    folded: FoldedInvestigationState | None,
    p26: object,
    p32: object,
    learning_prior: CrewChiefLearningPrior | None = None,
) -> InvestigationSubgoal | None:
    if folded is None or folded.status != "open":
        return None
    causes = bundle.report.reasoning_snapshot.causes
    completed = set(folded.completed_tool_ids)
    unresolved = tuple(
        cause
        for cause in causes
        if cause.status != "ruled_out"
        and next(
            (
                item.progress
                for item in folded.hypotheses
                if item.cause_id == cause.cause_id
            ),
            InvestigationProgress.INSPECTION_PENDING,
        )
        != InvestigationProgress.INSPECTED
    )
    has_context_debt = bool(
        bundle.report.lap_context is None
        or any(item.blocker_reasons for item in bundle.report.lap_context.contexts)
    )
    has_history = any(
        history.exact_context
        for state in p26.component_states
        for history in state.controlled_history
    )
    priorities: list[str] = []
    if (
        bundle.report.data_quality.status != "ready"
        or "inspect_data_quality" not in completed
    ):
        priorities.append("inspect_data_quality")
    if has_context_debt or "inspect_lap_context" not in completed:
        priorities.append("inspect_lap_context")
    # Ask the driver after objective evidence integrity and context have been
    # inspected.  Their answer can then change the next physical inspection.
    if not folded.driver_answers and {
        "inspect_data_quality",
        "inspect_lap_context",
    }.issubset(completed):
        return None
    answer = folded.driver_answers[-1] if folded.driver_answers else None
    priorities.append("inspect_lap_time_opportunity")
    priorities.append("inspect_time_loss_origin")
    priorities.append("inspect_corner_performance_chain")
    priorities.append("inspect_exit_carry")
    priorities.append("inspect_path_efficiency")
    priorities.append("inspect_driver_vehicle_separation")
    priorities.append("inspect_track_demand")
    if answer is not None and answer != "not repeatable":
        priorities.append("inspect_driver_execution")
    if any(cause.contradicting_evidence for cause in unresolved):
        priorities.append("inspect_p19_causes")
    elif unresolved:
        priorities.append("inspect_p19_causes")
    if folded.objective in {
        EngineeringObjective.TIRE_CONSERVATION,
        EngineeringObjective.DRIVER_CONFIDENCE,
    }:
        priorities.append("inspect_component_state")
    if bundle.report.reasoning_snapshot.mechanism_episodes:
        priorities.append("inspect_mechanism_episodes")
    priorities.append("inspect_component_performance_link")
    if p26.leading_component_ids:
        priorities.append("inspect_component_state")
    if has_history:
        priorities.append("inspect_controlled_history")
    priorities.append("inspect_objective_tradeoff")
    priorities.append("inspect_measurement_debt")
    baseline = tuple(dict.fromkeys(priorities))
    live = tuple(item for item in baseline if item not in completed)
    attention_by_tool = {
        item.tool_id: item
        for item in (
            learning_prior.recommended_attention_order
            if learning_prior is not None
            else ()
        )
        if item.tool_id in live
        and item.safety_band == _TOOL_SAFETY_BANDS.get(item.tool_id)
        and item.transfer_level in {"exact", "compatible"}
    }
    band_order = tuple(dict.fromkeys(_TOOL_SAFETY_BANDS[item] for item in live))
    refined: list[str] = []
    for band in band_order:
        band_tools = [item for item in live if _TOOL_SAFETY_BANDS[item] == band]
        baseline_rank = {
            item: index
            for index, item in enumerate(
                (
                    candidate
                    for candidate in baseline
                    if _TOOL_SAFETY_BANDS[candidate] == band
                ),
                start=1,
            )
        }

        def learned_order(tool_id: str) -> tuple[int, int, int, str]:
            attention = attention_by_tool.get(tool_id)
            if (
                attention is None
                or attention.baseline_rank_within_band != baseline_rank[tool_id]
            ):
                return (
                    baseline_rank[tool_id],
                    1,
                    baseline_rank[tool_id],
                    tool_id,
                )
            return (
                attention.learned_rank_within_band,
                0,
                baseline_rank[tool_id],
                tool_id,
            )

        refined.extend(sorted(band_tools, key=learned_order))
    tool = refined[0] if refined else None
    if tool is None:
        return None
    contradiction_first = sorted(
        unresolved,
        key=lambda cause: (not bool(cause.contradicting_evidence), cause.ordinal_rank),
    )
    leading = tuple(cause.cause_id for cause in contradiction_first)
    answer_scope = (
        f" Driver context scopes this inspection to {answer}." if answer else ""
    )
    learned_attention = attention_by_tool.get(tool) if tool is not None else None
    baseline_band_rank = (
        next(
            index
            for index, candidate in enumerate(
                (
                    item
                    for item in baseline
                    if _TOOL_SAFETY_BANDS[item] == _TOOL_SAFETY_BANDS[tool]
                ),
                start=1,
            )
            if candidate == tool
        )
        if tool is not None
        else None
    )
    learning_explanation = (
        (
            "WHY THIS IS EARLIER — "
            f"{learned_attention.reason} "
            f"{learned_attention.investigation_count} prior investigations across "
            f"{learned_attention.session_count} sessions and "
            f"{learned_attention.independent_workflow_count} independent workflows "
            f"matched at {learned_attention.transfer_level} transfer. "
            "P19 cause order and setup authority are unchanged."
        )
        if learned_attention is not None
        and learned_attention.baseline_rank_within_band == baseline_band_rank
        and learned_attention.learned_rank_within_band < baseline_band_rank
        else None
    )
    return InvestigationSubgoal(
        subgoal_id=f"ccs_{canonical_json_sha256([folded.investigation_id, tool])[:20]}",
        title=f"Inspect {tool.replace('_', ' ')}",
        selected_tool=tool,
        why_this_tool=(
            learning_explanation
            or "It is the next bounded inspection under the integrity/context/driver/"
            "contradiction/component/history priority contract without creating setup authority."
            + answer_scope
        ),
        distinguishes_cause_ids=leading,
        required_evidence=(
            "exact source run/setup/build provenance",
            "eligible physical scope",
            f"tool-specific {tool} evidence",
        ),
        stop_condition="Stop after the canonical artifact and its blockers are attached.",
        priority_rank=len(completed) + 1,
    )


def _driver_question(
    identity: CrewChiefWorkspaceIdentity,
    investigation: CrewChiefInvestigation | None,
    folded: FoldedInvestigationState | None,
    causes: tuple[object, ...],
) -> DriverDiagnosticQuestion | None:
    if (
        investigation is None
        or folded is None
        or folded.status != "open"
        or folded.pending_driver_question_id is None
    ):
        return None
    competing = tuple(cause.cause_id for cause in causes if cause.status != "ruled_out")
    question = (
        "Where does the handling issue first become clear?"
        if folded.objective != EngineeringObjective.TIRE_CONSERVATION
        else "Where does the tire behavior first stop repeating across the run?"
    )
    return DriverDiagnosticQuestion(
        question_id=folded.pending_driver_question_id,
        workspace_revision=identity.workspace_revision,
        question=question,
        answer_options=("braking/entry", "center", "exit/power", "not repeatable"),
        distinguishes_cause_ids=competing,
        reason=(
            "The selected objective and answer scope the next physical evidence inspection only; "
            "P19 rank and setup authority remain unchanged."
        ),
    )


def _select_tool_entries(
    workspace: CrewChiefWorkspace,
    tool_id: str,
    cause_ids: tuple[str, ...],
) -> tuple[EngineeringEvidenceIndexEntry, ...]:
    entries = workspace.evidence_index.entries
    answer = (
        workspace.folded_state.driver_answers[-1]
        if workspace.folded_state and workspace.folded_state.driver_answers
        else None
    )
    answer_phase = {
        "braking/entry": ("brak", "entry", "turn"),
        "center": ("center", "apex", "corner"),
        "exit/power": ("exit", "throttle", "power"),
    }.get(answer or "", ())
    if tool_id == "inspect_data_quality":
        selected = tuple(
            item
            for item in entries
            if item.blocker_reasons
            and not item.producer_id.startswith("p32.")
            and item.producer_id != "p26.component_state_unavailable"
        )
    elif tool_id == "inspect_lap_context":
        selected = tuple(
            item
            for item in entries
            if item.producer_id == "p19.reasoning_snapshot"
            and (
                item.blocker_reasons
                or item.evidence_state == EvidenceState.BLOCKED_BY_CONTEXT
            )
        )
    elif tool_id == "inspect_driver_execution":
        selected = tuple(
            item
            for item in entries
            if item.producer_id == "p19.reasoning_snapshot"
            and (
                not answer_phase
                or any(token in (item.phase or "").casefold() for token in answer_phase)
            )
        )
    elif tool_id in {
        "inspect_lap_time_opportunity",
        "inspect_time_loss_origin",
        "inspect_corner_performance_chain",
        "inspect_exit_carry",
        "inspect_path_efficiency",
        "inspect_driver_vehicle_separation",
        "inspect_track_demand",
        "inspect_component_performance_link",
        "inspect_objective_tradeoff",
    }:
        producer_by_tool = {
            "inspect_lap_time_opportunity": "p32.lap_time_opportunity",
            "inspect_time_loss_origin": "p32.time_loss_origin",
            "inspect_corner_performance_chain": "p32.corner_performance_chain",
            "inspect_exit_carry": "p32.exit_carry",
            "inspect_path_efficiency": "p32.path_efficiency",
            "inspect_driver_vehicle_separation": "p32.driver_vehicle_separation",
            "inspect_track_demand": "p32.track_demand",
            "inspect_component_performance_link": "p32.component_performance_link",
            "inspect_objective_tradeoff": "p32.objective_envelope",
        }
        producer_entries = tuple(
            item for item in entries if item.producer_id == producer_by_tool[tool_id]
        )
        if tool_id == "inspect_driver_vehicle_separation" and answer_phase:
            scoped = tuple(
                item
                for item in producer_entries
                if any(token in (item.phase or "").casefold() for token in answer_phase)
                or item.evidence_state == EvidenceState.UNAVAILABLE
            )
            selected = scoped or producer_entries
        else:
            selected = producer_entries
    elif tool_id == "inspect_p19_causes":
        selected = tuple(
            item
            for item in entries
            if item.producer_id == "p19.reasoning_snapshot"
            and (
                not cause_ids or item.polarity == "contradiction" or item.component_ids
            )
        )
    elif tool_id == "inspect_mechanism_episodes":
        selected = tuple(
            item for item in entries if item.producer_id == "p20.mechanism_episode"
        )
    elif tool_id == "inspect_component_state":
        unavailable = tuple(
            item
            for item in entries
            if item.producer_id == "p26.component_state_unavailable"
        )
        selected = unavailable or tuple(
            item
            for item in entries
            if item.component_ids and not item.producer_id.startswith("p32.")
        )
    elif tool_id == "inspect_controlled_history":
        selected = tuple(item for item in entries if item.control_keys)
    else:
        selected = tuple(item for item in entries if item.blocker_reasons)
    return selected[:16]


def _success_contract(
    bundle: RunIntelligenceBundle,
    identity: CrewChiefWorkspaceIdentity,
    objective: EngineeringObjective,
) -> SuccessContract | None:
    plan = bundle.report.best_measurement
    if plan.kind in {"blocked", "stop_testing", "discriminator"}:
        return None
    if plan.kind == "measurement_mission" and plan.mission_contract is not None:
        # The immutable P19 contract is projected separately without translating
        # or replacing any threshold.  This legacy ribbon is intentionally absent.
        return None
    mission = plan.measurement_mission
    card = plan.controlled_test
    if (plan.kind == "measurement_mission" and mission is None) or (
        plan.kind == "controlled_test" and card is None
    ):
        return None
    required = (
        mission.required_laps_or_passes
        if mission is not None
        else max(stage.required_flying_laps for stage in card.stages)
        if card is not None
        else 0
    )
    target = (
        mission.target_phase
        if mission is not None
        else card.target_phase
        if card
        else "P19 contract unavailable"
    )
    threshold = (
        "; ".join(mission.acceptance_thresholds)
        if mission is not None
        else "; ".join(card.success_metrics)
        if card is not None
        else "P19 contract unavailable"
    )
    stop_rule = (
        mission.stop_rule
        if mission is not None
        else card.stop_rule
        if card
        else "Stop on integrity or context failure."
    )
    rollback = (
        card.rollback_rule
        if card is not None
        else "No setup change is authorized by this contract."
    )
    return SuccessContract(
        contract_id=f"cck_{canonical_json_sha256([identity.workspace_revision, threshold])[:24]}",
        workspace_revision=identity.workspace_revision,
        objective=objective,
        target_scope=target,
        primary_metric=SuccessMetric(
            metric="canonical P19 success check",
            threshold=threshold,
            threshold_source="P19 information plan",
        ),
        minimum_repetitions=required,
        independence_unit="eligible lap in the exact frozen run/stage scope",
        protected_metrics=(
            SuccessMetric(
                metric="lap integrity",
                threshold="eligible only",
                threshold_source="canonical lap gate",
            ),
            SuccessMetric(
                metric="traffic/context",
                threshold="no unresolved contamination",
                threshold_source="P19 lap context",
            ),
            SuccessMetric(
                metric="setup isolation",
                threshold="one controlled change only",
                threshold_source="P19 controlled-test contract",
            ),
        ),
        context_invariants=(
            "same run/session scope",
            "comparable fuel/weather/traffic context",
        ),
        driver_invariants=("repeatable target-phase execution",),
        setup_invariants=(
            "unchanged setup unless the exact P19 card authorizes stage B",
        ),
        acceptance_rule=threshold,
        rejection_rule="Reject laps carrying canonical eligibility or context blockers.",
        retest_rule="Retest only when P19 reports insufficient independent evidence.",
        stop_rule=stop_rule,
        rollback_rule=rollback,
    )


def _sentinel(
    bundle: RunIntelligenceBundle,
    overview: object,
    workflow: object | None = None,
    *,
    measurement_attempts: tuple[MeasurementAttempt, ...] = (),
    measurement_history_blockers: tuple[str, ...] = (),
) -> RunSentinelState:
    report = bundle.report
    plan = report.best_measurement
    mission = plan.measurement_mission
    card = plan.controlled_test
    contract = getattr(plan, "mission_contract", None)
    plan_kind = plan.kind
    required = (
        contract.required_laps
        if contract is not None
        else mission.required_laps_or_passes
        if mission is not None
        else max(stage.required_flying_laps for stage in card.stages)
        if card is not None
        else None
    )
    stage = "measurement"
    hold = (
        mission.controlled_variables
        if mission
        else card.do_not_change
        if card
        else ("P19 authority state",)
    )
    watch = (
        mission.acceptance_thresholds
        if mission
        else card.success_metrics
        if card
        else tuple(plan.blocker_reasons) or (plan.instruction,)
    )
    stop = (
        (mission.stop_rule,)
        if mission
        else (card.stop_rule,)
        if card
        else tuple(plan.blocker_reasons) or (plan.instruction,)
    )
    preflight = report.smart_guidance.test_preflight if report.smart_guidance else None
    if _active_workflow_identity(bundle)[0] is not None:
        move = (
            report.smart_guidance.next_trustworthy_move
            if report.smart_guidance
            else None
        )
        stage = (
            preflight.stage
            if preflight is not None
            else "B"
            if move and move.kind == "controlled_test"
            else "A"
        )
        if card and stage in {"A", "B", "A2"}:
            selected = next(
                (item for item in card.stages if item.stage == stage), card.stages[0]
            )
            required = selected.required_flying_laps
    mission_scope_reasons: list[str] = []
    if preflight is not None:
        mission_scope_reasons.extend(preflight.blocker_reasons)
    recorded_stage = next(
        (
            recorded
            for recorded, recorded_run_id in getattr(
                workflow, "stage_run_ids", {}
            ).items()
            if recorded_run_id == report.run_id
        ),
        None,
    )
    if stage in {"A", "B", "A2"} and recorded_stage not in {None, stage}:
        mission_scope_reasons.append(
            f"current run is already bound to Stage {recorded_stage}; Stage {stage} requires a new exact run"
        )
    eligible = set(report.data_quality.eligible_lap_ids)
    context_by_lap = {
        item.lap_number: item
        for item in (report.lap_context.contexts if report.lap_context else ())
    }
    decisions: list[RunSentinelLap] = []
    context_cleared_ids: list[str] = []
    for lap in sorted(overview.laps, key=lambda item: item.lap_number):
        reasons: list[str] = list(mission_scope_reasons)
        if lap.lap_id not in eligible:
            reasons.extend(lap.classification_tags or ["not in P19 eligible-lap set"])
        context = context_by_lap.get(lap.lap_number)
        if report.lap_context is None:
            reasons.append("canonical lap context is unavailable")
        elif context is None:
            reasons.append("exact-lap context coverage is unavailable")
        else:
            reasons.extend(context.blocker_reasons)
            if not mission_lap_context_is_clear(context):
                reasons.append(
                    "nearby-car context must have complete coverage and zero traffic exposure"
                )
        if reasons:
            decisions.append(
                RunSentinelLap(
                    lap_id=lap.lap_id,
                    lap_number=lap.lap_number,
                    status="rejected",
                    reasons=_unique(reasons),
                )
            )
        else:
            context_cleared_ids.append(lap.lap_id)
            decisions.append(
                RunSentinelLap(
                    lap_id=lap.lap_id,
                    lap_number=lap.lap_number,
                    status="context_cleared",
                    context_ordinal=len(context_cleared_ids),
                )
            )
    mission_accepted_lap_ids: tuple[str, ...] = ()
    measurement_attempt_ids: tuple[str, ...] = ()
    mission_acceptance_basis: Literal[
        "unbound", "p19_measurement_attempt", "controlled_workflow_stage"
    ] = "unbound"
    progress_blockers = list(measurement_history_blockers)
    if plan_kind in {"measurement_mission", "discriminator"} and contract is not None:
        qualified_attempts: list[MeasurementAttempt] = []
        corrupt_attempt = False
        for attempt in measurement_attempts:
            exact_identity = (
                attempt.contract_id == contract.contract_id
                and attempt.contract_sha256 == contract.contract_sha256
                and attempt.run_id in contract.session_run_ids
                and attempt.setup_sha256 == contract.setup_sha256
                and attempt.compatibility_fingerprint
                == contract.compatibility_fingerprint
                and all(
                    lap_id.rsplit(":", 1)[0] == attempt.run_id
                    for lap_id in attempt.eligible_lap_ids
                )
            )
            if not exact_identity:
                corrupt_attempt = True
                continue
            if (
                getattr(attempt, "collection_authority", None) == "server_verified"
                and attempt.outcome in {"completed_clean", "no_signal"}
                and not attempt.integrity_blockers
                and len(attempt.eligible_lap_ids) >= contract.required_laps
                and set(contract.required_channels).issubset(
                    attempt.observed_channels
                )
                and (
                    attempt.run_id != report.run_id
                    or set(attempt.eligible_lap_ids).issubset(context_cleared_ids)
                )
            ):
                qualified_attempts.append(attempt)
        if corrupt_attempt:
            progress_blockers.append(
                "Durable measurement progress failed its exact contract, run, setup, or build identity check."
            )
        elif qualified_attempts:
            mission_accepted_lap_ids = _unique(
                lap_id
                for attempt in qualified_attempts
                for lap_id in attempt.eligible_lap_ids
            )
            measurement_attempt_ids = tuple(
                attempt.attempt_id for attempt in qualified_attempts
            )
            mission_acceptance_basis = "p19_measurement_attempt"
        else:
            progress_blockers.append(
                "Context-cleared laps are screening evidence only; mission completion requires an exact P19 measurement attempt with every required channel."
            )
    elif plan_kind in {"measurement_mission", "discriminator"}:
        progress_blockers.append(
            "Context-cleared laps are screening evidence only; P19 has not bound an exact measurement contract."
        )
    elif plan_kind == "controlled_test" and stage in {"A", "B", "A2"}:
        recorded_lap_numbers = tuple(
            getattr(workflow, "stage_eligible_lap_numbers", {}).get(stage, ())
        )
        context_cleared_by_number = {
            item.lap_number: item.lap_id
            for item in decisions
            if item.status == "context_cleared"
        }
        recorded_lap_ids = tuple(
            context_cleared_by_number[lap_number]
            for lap_number in recorded_lap_numbers
            if lap_number in context_cleared_by_number
        )
        if (
            recorded_stage == stage
            and recorded_lap_numbers
            and len(recorded_lap_ids) == len(recorded_lap_numbers)
        ):
            mission_accepted_lap_ids = recorded_lap_ids
            mission_acceptance_basis = "controlled_workflow_stage"
        else:
            progress_blockers.append(
                "Context-cleared laps are screening evidence until the exact recorded controlled-workflow stage cohort remains qualified."
            )
    waiting_for_score = bool(
        workflow is not None
        and getattr(workflow, "status", None) == "a2_recorded"
        and all(
            getattr(workflow, "stage_run_ids", {}).get(item)
            for item in ("A", "B", "A2")
        )
    )
    collection_complete = (
        required is not None and len(mission_accepted_lap_ids) >= required
    )
    if plan_kind == "blocked":
        mission_state = "blocked_by_p19"
        stage = "blocked"
        required = None
        collection_complete = False
        mission_accepted_lap_ids = ()
        measurement_attempt_ids = ()
        mission_acceptance_basis = "unbound"
    elif plan_kind == "stop_testing":
        mission_state = "stopped_by_p19"
        stage = "stopped"
        required = None
        collection_complete = False
        mission_accepted_lap_ids = ()
        measurement_attempt_ids = ()
        mission_acceptance_basis = "unbound"
    elif waiting_for_score:
        mission_state = "awaiting_p19_score"
        stage = "awaiting_score"
    elif collection_complete:
        mission_state = "collection_complete"
    else:
        mission_state = "collecting"
    return RunSentinelState(
        mission_state=mission_state,
        p19_plan_kind=plan_kind,
        mission=plan.title,
        need=plan.instruction,
        hold_constant=hold,
        watch=watch,
        success=report.briefing.success_check,
        stop=stop,
        required_laps=required,
        context_cleared_laps=len(context_cleared_ids),
        mission_accepted_lap_ids=mission_accepted_lap_ids,
        measurement_attempt_ids=measurement_attempt_ids,
        mission_acceptance_basis=mission_acceptance_basis,
        collection_complete=collection_complete,
        stage=stage,
        laps=tuple(decisions),
        blocker_reasons=_unique(
            [
                *mission_scope_reasons,
                *progress_blockers,
                *plan.blocker_reasons,
                *report.data_quality.issues,
            ]
        ),
    )


def _critique(
    bundle: RunIntelligenceBundle,
    identity: CrewChiefWorkspaceIdentity,
    *,
    stale_reasons: tuple[str, ...] = (),
) -> CrewChiefCritique:
    report = bundle.report
    action = report.briefing.action
    findings: list[str] = list(stale_reasons)
    strongest_contradiction = next(
        (
            citation.summary
            for cause in report.reasoning_snapshot.causes
            for citation in cause.contradicting_evidence
        ),
        None,
    )
    if report.session_id != identity.session_id:
        findings.append("P19 report session does not match the workspace.")
    if action.setup_authorized:
        if (
            action.kind != "controlled_test"
            or action.control_key != report.reasoning_snapshot.authority.control_key
            or not action.source_event_ids
            or identity.active_workflow_id is None
        ):
            findings.append(
                "The proposed setup action is not one exact workflow-bound P19 projection."
            )
    elif any((action.control_key, action.current_value, action.proposed_value)):
        findings.append("A non-authoritative action exposed setup values.")
    if report.data_quality.status == "blocked":
        findings.append("Canonical data quality is blocked.")
    if findings:
        return CrewChiefCritique(
            outcome="blocked",
            passed=False,
            findings=_unique(findings),
            forbidden_decision_kinds=("controlled_test",),
            required_next_investigation="Resolve the canonical blocker before any test.",
            strongest_contradiction=strongest_contradiction,
        )
    return CrewChiefCritique(
        outcome="pass",
        passed=True,
        strongest_contradiction=strongest_contradiction,
    )


def _decision(
    bundle: RunIntelligenceBundle,
    identity: CrewChiefWorkspaceIdentity,
    critique: CrewChiefCritique,
    question: DriverDiagnosticQuestion | None,
) -> CrewChiefTerminalDecision:
    report = bundle.report
    action = report.briefing.action
    if question is not None:
        return CrewChiefTerminalDecision(
            kind="driver_question",
            title="One driver context question",
            instruction=question.question,
            authority="context_only",
        )
    if not critique.passed:
        return CrewChiefTerminalDecision(
            kind="observe_only",
            title="Authority blocked",
            instruction=critique.required_next_investigation or "Inspect the blocker.",
            authority="context_only",
            blocker_reasons=critique.findings,
        )
    if action.setup_authorized:
        return CrewChiefTerminalDecision(
            kind="controlled_test",
            title=action.title,
            instruction=action.instruction,
            authority="p19_projection_only",
            control_key=action.control_key,
            current_value=action.current_value,
            proposed_value=action.proposed_value,
            source_event_ids=action.source_event_ids,
            workflow_id=identity.active_workflow_id,
            workflow_revision=identity.active_workflow_revision,
        )
    driver_focus = report.driver_focus.focus if report.driver_focus else None
    if driver_focus is not None:
        return CrewChiefTerminalDecision(
            kind="driver_focus",
            title=f"Driver focus · {driver_focus.phase}",
            instruction=driver_focus.instruction,
            authority="context_only",
            source_event_ids=_unique(
                citation.event_id or f"driver:{citation.run_id}:{citation.lap_number}"
                for citation in driver_focus.citations
            ),
        )
    if action.kind in {"measurement_mission", "discriminator"}:
        return CrewChiefTerminalDecision(
            kind="measurement_mission",
            title=action.title,
            instruction=action.instruction,
            authority="measurement_only",
            source_event_ids=action.source_event_ids,
            blocker_reasons=action.blocker_reasons,
        )
    return CrewChiefTerminalDecision(
        kind="no_call",
        title=action.title or "No setup call",
        instruction=action.instruction or "Hold the current setup.",
        authority="context_only",
        blocker_reasons=action.blocker_reasons,
    )


def build_crew_chief_workspace(
    run_id: str,
    *,
    session_id: str,
    objective: EngineeringObjective = EngineeringObjective.RACE_LONG_RUN,
    investigation_id: str | None = None,
    db_path: str | Path | None = None,
) -> CrewChiefWorkspace:
    session = get_session(session_id, db_path)
    if session is None or run_id not in session.run_ids:
        raise ValueError("Crew Chief requires exact saved-session membership.")
    bundle = build_run_intelligence(run_id, session_id=session_id, db_path=db_path)
    storage_repository = RaceLabRepository(db_path)
    overview = storage_repository.get_overview(run_id)
    if overview is None or overview.setup_snapshot is None:
        raise ValueError("Crew Chief requires an imported run and captured setup.")
    p20 = project_engineering_awareness(bundle)
    p26: object | None
    p26_unavailable_reason: str | None = None
    try:
        runtime = vehicle_systems_runtime_identity(run_id)
        p26 = build_component_awareness(
            bundle.report,
            setup_snapshot=overview.setup_snapshot,
            runtime_identity=runtime,
        )
    except ValueError as exc:
        if not _is_optional_p26_applicability_failure(exc):
            raise
        p26 = None
        p26_unavailable_reason = (
            "P26 component attribution is unavailable for this exact vehicle/build/track: "
            f"{exc}"
        )
    repository = CrewChiefRepository(db_path)
    active_workflow_id, _ = _active_workflow_identity(bundle)
    try:
        active_workflow = (
            storage_repository.get_controlled_workflow(active_workflow_id)
            if active_workflow_id
            else None
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Crew Chief active workflow integrity could not be verified."
        ) from exc
    if active_workflow_id is not None and active_workflow is None:
        raise ValueError("Crew Chief active workflow identity is missing.")
    investigation = (
        repository.get_investigation(investigation_id)
        if investigation_id
        else repository.latest_investigation(run_id, session_id)
    )
    if investigation is not None and (
        investigation.workspace_identity.run_id != run_id
        or investigation.workspace_identity.session_id != session_id
    ):
        raise ValueError("Crew Chief investigation belongs to another run/session.")
    events = (
        repository.list_events(investigation.investigation_id) if investigation else ()
    )
    folded = (
        fold_investigation(
            investigation, events, bundle.report.reasoning_snapshot.causes
        )
        if investigation
        else None
    )
    if folded is not None:
        objective = folded.objective
    p32 = build_performance_intelligence(
        run_id,
        session_id=session_id,
        scope_run_ids=tuple(session.run_ids),
        objective=objective,
        bundle=bundle,
        p20=p20,
        p26=p26,
        overview=overview,
        repository=storage_repository,
    )
    if p26 is None:
        reason = p26_unavailable_reason or "P26 component attribution is unavailable."
        p26_hash = p32.p26_knowledge_graph_sha256
        p26 = _UnavailableP26(
            setup_id=overview.setup_snapshot.setup_id,
            setup_snapshot_sha256=canonical_json_sha256(overview.setup_snapshot),
            graph_version=f"p26.unavailable:{p26_hash[:12]}",
            knowledge_graph_sha256=p26_hash,
            reasoning_snapshot_sha256=canonical_json_sha256(
                bundle.report.reasoning_snapshot
            ),
            runtime_identity={
                "run_id": run_id,
                "state": "unavailable",
                "reason": reason,
            },
            unavailable_reason=reason,
        )
    current_learning = build_current_learning_inputs(
        run_id,
        session_id=session_id,
        scope_run_ids=tuple(session.run_ids),
        objective=objective,
        bundle=bundle,
        p20=p20,
        p26=p26,
        p32=p32,
        overview=overview,
        db_path=db_path,
    )
    learning_prior = build_crew_chief_learning_prior(
        current_learning,
        scope_run_ids=tuple(session.run_ids),
        p19_reasoning_snapshot_sha256=(
            current_learning.reasoning.reasoning_snapshot_sha256
        ),
        p32_projection_sha256=p32.projection_sha256,
        db_path=db_path,
    )
    capture_workflows, _capture_catalog_blockers = (
        storage_repository.list_controlled_workflows_for_run_scope(
            tuple(session.run_ids)
        )
    )
    learning_prior = _with_learning_capture_blockers(
        learning_prior,
        _learning_capture_blockers(tuple(capture_workflows), events),
    )
    measurement_attempts: tuple[MeasurementAttempt, ...] = ()
    measurement_history_blockers: tuple[str, ...] = ()
    mission_contract = bundle.report.best_measurement.mission_contract
    if mission_contract is not None:
        try:
            measurement_attempts = (
                storage_repository.list_measurement_mission_attempts(mission_contract)
            )
        except (TypeError, ValueError):
            measurement_history_blockers = (
                "Durable measurement-attempt history could not be verified; mission progress is withheld.",
            )
    run_sentinel = _sentinel(
        bundle,
        overview,
        active_workflow,
        measurement_attempts=measurement_attempts,
        measurement_history_blockers=measurement_history_blockers,
    )
    identity = _workspace_identity(
        bundle,
        session_id=session_id,
        scope_run_ids=tuple(session.run_ids),
        objective=objective,
        investigation_id=investigation.investigation_id if investigation else None,
        event_hashes=tuple(event.event_hash for event in events),
        p20=p20,
        p26=p26,
        p32=p32,
        learning_prior=learning_prior,
        run_sentinel=run_sentinel,
    )
    stale_reasons = _authority_stale_reasons(investigation, events, identity)
    if folded is not None and stale_reasons:
        folded = folded.model_copy(
            update={"status": "stale", "stale_reason": stale_reasons[0]}
        )
    cache_key = _workspace_cache_key(identity, db_path)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached.model_copy(
                update={"cache_state": "warm", "generated_at": _now()}
            )
    question = _driver_question(
        identity, investigation, folded, bundle.report.reasoning_snapshot.causes
    )
    critique = _critique(bundle, identity, stale_reasons=stale_reasons)
    contract = _success_contract(bundle, identity, objective)
    response_ids = _unique(
        history.workflow_id
        for state in p26.component_states
        for history in state.controlled_history
        if history.exact_context
    )
    driver_memory_ids = tuple(
        item.record_id for item in repository.list_driver_memory(session_id)
    )
    evidence_index = _evidence_index(
        bundle,
        identity,
        objective,
        p26,
        p32,
        storage_repository,
        learning_prior,
    )
    subgoal = _subgoal(bundle, folded, p26, p32, learning_prior)
    latest_result = None
    if folded and folded.completed_tool_ids:
        latest = folded.completed_tool_ids[-1]
        definition = next(item for item in _TOOLS if item.tool_id == latest)
        latest_event = next(
            (
                event
                for event in reversed(events)
                if event.event_type == "tool_result_attached"
                and event.payload.tool_id == latest
            ),
            None,
        )
        artifact_ids = latest_event.payload.artifact_ids if latest_event else ()
        cause_ids = latest_event.payload.cause_ids if latest_event else ()
        component_ids = latest_event.payload.component_ids if latest_event else ()
        result_entries = tuple(
            item for item in evidence_index.entries if item.artifact_id in artifact_ids
        )
        result_blockers = _unique(
            blocker for item in result_entries for blocker in item.blocker_reasons
        )
        result_blocked = bool(result_entries) and all(
            item.evidence_state
            in {EvidenceState.UNAVAILABLE, EvidenceState.BLOCKED_BY_CONTEXT}
            for item in result_entries
        )
        latest_result = CrewChiefToolResult(
            tool_id=latest,
            workspace_revision=identity.workspace_revision,
            status="blocked"
            if result_blocked
            else "complete"
            if artifact_ids
            else "no_finding",
            summary=(
                latest_event.payload.findings[0]
                if latest_event and latest_event.payload.findings
                else "No tool-specific canonical artifact matched this exact workspace."
            ),
            artifact_ids=artifact_ids,
            cause_ids=cause_ids,
            component_ids=component_ids,
            blocker_reasons=result_blockers if result_blocked else (),
            authority_ceiling=definition.authority_ceiling,
        )
    decision = _decision(bundle, identity, critique, question)
    workspace = CrewChiefWorkspace(
        identity=identity,
        generated_at=_now(),
        investigation=investigation,
        folded_state=folded,
        evidence_index=evidence_index,
        available_tools=_TOOLS,
        current_subgoal=subgoal,
        latest_tool_result=latest_result,
        critique=critique,
        pending_driver_question=question,
        success_contract=contract,
        p19_mission_contract=bundle.report.best_measurement.mission_contract,
        performance_intelligence=p32,
        learning_prior=learning_prior,
        run_sentinel=run_sentinel,
        terminal_decision=decision,
        response_history_ids=response_ids,
        driver_memory_ids=driver_memory_ids,
        p19_cause_ids=tuple(
            cause.cause_id for cause in bundle.report.reasoning_snapshot.causes
        ),
        p20_episode_ids=tuple(
            item.episode_id
            for item in bundle.report.reasoning_snapshot.mechanism_episodes
        ),
        p26_component_ids=tuple(state.component_id for state in p26.component_states),
        post_run_brief=(
            f"P19 status: {bundle.report.status}.",
            f"Speed Story: {p32.speed_story.what_costs_time}",
            f"{len(evidence_index.entries)} evidence artifacts indexed without raw traces.",
            f"Next move: {decision.title}",
        ),
        blocker_reasons=_unique(
            [
                *stale_reasons,
                *bundle.report.blocker_reasons,
                *p20.knowledge_debt,
                *p26.knowledge_debt,
                *p32.blockers,
                *learning_prior.blocker_reasons,
            ]
        ),
    )
    with _CACHE_LOCK:
        _CACHE[cache_key] = workspace
        if len(_CACHE) > 24:
            _CACHE.pop(next(iter(_CACHE)))
    return workspace


def _event(
    investigation_id: str,
    sequence: int,
    workspace_revision: str,
    event_type: str,
    payload: CrewChiefEventPayload,
) -> CrewChiefEvent:
    created_at = _now()
    event_id = f"cce_{canonical_json_sha256([investigation_id, sequence, event_type, payload])[:24]}"
    unhashed = {
        "event_id": event_id,
        "investigation_id": investigation_id,
        "sequence": sequence,
        "event_type": event_type,
        "workspace_revision": workspace_revision,
        "created_at": created_at,
        "payload": payload,
    }
    provisional = CrewChiefEvent(event_hash="0" * 64, **unhashed)
    event_hash = crew_chief_event_hash(provisional)
    event = provisional.model_copy(update={"event_hash": event_hash})
    if crew_chief_event_hash(event) != event_hash:
        raise ValueError("Crew Chief event hashing is not deterministic")
    return event


def _learning_inputs_for_workspace(
    workspace: CrewChiefWorkspace,
    *,
    db_path: str | Path | None,
) -> CurrentLearningInputs:
    """Rebuild exact current inputs for restart-safe lifecycle mutations."""

    identity = workspace.identity
    session = get_session(identity.session_id, db_path)
    if session is None or identity.run_id not in session.run_ids:
        raise ValueError("P33 lifecycle memory requires exact saved-session scope.")
    if canonical_json_sha256(tuple(session.run_ids)) != identity.selected_scope_hash:
        raise ValueError(
            "P33 lifecycle memory scope changed; refresh before continuing."
        )
    return build_current_learning_inputs(
        identity.run_id,
        session_id=identity.session_id,
        scope_run_ids=tuple(session.run_ids),
        objective=identity.objective_id,
        p32=workspace.performance_intelligence,
        db_path=db_path,
    )


def _with_event_source_provenance(
    current: CurrentLearningInputs,
    workspace: CrewChiefWorkspace,
    events: tuple[CrewChiefEvent, ...],
) -> CurrentLearningInputs:
    """Attach only exact current evidence entries cited by terminal history."""

    cited = _unique(
        artifact_id
        for event in events
        for artifact_id in event.payload.artifact_ids
        if not artifact_id.startswith("p33ref_")
    )
    entries = {
        entry.artifact_id: entry
        for entry in workspace.evidence_index.entries
        if entry.artifact_id in cited and entry.source_provenance_available
    }
    provenance = {item.artifact_id: item for item in current.source_provenance}
    for artifact_id in cited:
        if artifact_id in provenance:
            continue
        entry = entries.get(artifact_id)
        if (
            entry is None
            or entry.source_session_id is None
            or entry.source_setup_id is None
            or entry.source_setup_sha256 is None
            or entry.source_build_context_sha256 is None
        ):
            continue
        provenance[artifact_id] = EngineeringSourceProvenance.build(
            artifact_id=artifact_id,
            producer_id=entry.producer_id,
            run_id=entry.source_run_id,
            session_id=entry.source_session_id,
            setup_id=entry.source_setup_id,
            setup_snapshot_sha256=entry.source_setup_sha256,
            build_context_sha256=entry.source_build_context_sha256,
            lap_numbers=entry.lap_numbers,
            lap_pct_start=entry.lap_pct_start,
            lap_pct_end=entry.lap_pct_end,
            phase=entry.phase,
            source_channels=entry.source_channels,
            evidence_state=entry.evidence_state,
            polarity=entry.polarity,
        )
    return CurrentLearningInputs(
        context=current.context,
        problem=current.problem,
        reasoning=current.reasoning,
        source_provenance=tuple(provenance.values()),
        performance_response=current.performance_response,
        driver_contributions=current.driver_contributions,
    )


def open_investigation(
    run_id: str,
    *,
    session_id: str,
    driver_report: str,
    expected_workspace_revision: str,
    objective: EngineeringObjective = EngineeringObjective.RACE_LONG_RUN,
    origin: str = "driver_report",
    db_path: str | Path | None = None,
) -> CrewChiefWorkspace:
    current = build_crew_chief_workspace(
        run_id, session_id=session_id, objective=objective, db_path=db_path
    )
    if current.identity.workspace_revision != expected_workspace_revision:
        raise ValueError(
            "Crew Chief workspace revision is stale; rebase before continuing."
        )
    if (
        current.investigation
        and current.folded_state
        and current.folded_state.status in {"open", "stale"}
    ):
        raise ValueError(
            "An open Crew Chief investigation already exists for this scope."
        )
    normalized = " ".join(driver_report.split())
    if not normalized:
        raise ValueError("A driver report is required.")
    learning_inputs = _learning_inputs_for_workspace(current, db_path=db_path)
    investigation_id = f"cci_{canonical_json_sha256([run_id, session_id, normalized, current.identity.workspace_revision])[:24]}"
    investigation = CrewChiefInvestigation(
        investigation_id=investigation_id,
        workspace_identity=current.identity,
        origin=origin,
        objective=objective,
        raw_driver_report=normalized,
        canonical_problem=normalized.casefold(),
        opening_reasoning=learning_inputs.reasoning,
        opening_problem=learning_inputs.problem,
        opened_at=_now(),
    )
    repository = CrewChiefRepository(db_path)
    repository.save_investigation(investigation)
    opened = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        objective=objective,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    repository.save_objective(
        investigation_id, opened.identity.workspace_revision, objective
    )
    repository.append_event(
        _event(
            investigation_id,
            1,
            opened.identity.workspace_revision,
            "problem_interpreted",
            CrewChiefEventPayload(message=f"Driver report normalized: {normalized}"),
        )
    )
    return build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )


def continue_investigation(
    run_id: str,
    investigation_id: str,
    *,
    session_id: str,
    expected_workspace_revision: str,
    db_path: str | Path | None = None,
) -> CrewChiefWorkspace:
    current = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    if current.identity.workspace_revision != expected_workspace_revision:
        raise ValueError(
            "Crew Chief workspace revision is stale; rebase before continuing."
        )
    if current.folded_state is None or current.folded_state.status != "open":
        raise ValueError("Crew Chief investigation is not open.")
    if current.folded_state.pending_driver_question_id is not None:
        raise ValueError(
            "A Crew Chief driver question is pending; record its contextual answer before continuing."
        )
    repository = CrewChiefRepository(db_path)
    sequence = current.folded_state.last_sequence + 1
    if current.current_subgoal is not None:
        subgoal = current.current_subgoal
        selected = _select_tool_entries(
            current, subgoal.selected_tool, subgoal.distinguishes_cause_ids
        )
        component_ids = _unique(
            component_id for item in selected for component_id in item.component_ids
        )
        invocation = _event(
            investigation_id,
            sequence,
            current.identity.workspace_revision,
            "tool_invoked",
            CrewChiefEventPayload(
                message=f"Requested {subgoal.selected_tool} inspection.",
                tool_id=subgoal.selected_tool,
                cause_ids=subgoal.distinguishes_cause_ids,
                requested_measurement_ids=(subgoal.selected_tool,),
            ),
        )
        result = _event(
            investigation_id,
            sequence + 1,
            current.identity.workspace_revision,
            "tool_result_attached",
            CrewChiefEventPayload(
                message=f"Inspected {subgoal.selected_tool}.",
                tool_id=subgoal.selected_tool,
                cause_ids=subgoal.distinguishes_cause_ids,
                artifact_ids=tuple(item.artifact_id for item in selected),
                component_ids=component_ids,
                completed_measurement_ids=(subgoal.selected_tool,),
                findings=(
                    (
                        f"{len(selected)} tool-specific canonical artifacts attached; "
                        "authority ceiling preserved."
                    ),
                ),
            ),
        )
        repository.append_events(
            (
                invocation,
                result,
            )
        )
    elif (
        current.folded_state.pending_driver_question_id is None
        and len(current.folded_state.driver_answers) == 0
    ):
        question_id = f"ccq_{canonical_json_sha256([investigation_id, sequence])[:20]}"
        repository.append_event(
            _event(
                investigation_id,
                sequence,
                current.identity.workspace_revision,
                "driver_question_asked",
                CrewChiefEventPayload(
                    message="One contextual driver question is required.",
                    question_id=question_id,
                    cause_ids=current.p19_cause_ids[:2],
                ),
            )
        )
    else:
        if (
            current.terminal_decision.kind == "measurement_mission"
            and current.p19_mission_contract is None
        ):
            raise ValueError(
                "Crew Chief measurement decision requires the exact P19 mission contract."
            )
        terminal_event = _event(
            investigation_id,
            sequence,
            current.identity.workspace_revision,
            "decision_emitted",
            CrewChiefEventPayload(
                message=current.terminal_decision.instruction,
                decision_kind=current.terminal_decision.kind,
                cause_ids=current.p19_cause_ids[:1],
                artifact_ids=current.terminal_decision.source_event_ids,
                workflow_ids=(
                    (current.terminal_decision.workflow_id,)
                    if current.terminal_decision.workflow_id is not None
                    else ()
                ),
                requested_measurement_ids=(
                    (current.p19_mission_contract.contract_id,)
                    if current.terminal_decision.kind == "measurement_mission"
                    and current.p19_mission_contract is not None
                    else ()
                ),
            ),
        )
        investigation = current.investigation
        if investigation is None:
            raise ValueError("Crew Chief terminal learning requires an investigation.")
        terminal_events = (
            *repository.list_events(investigation_id),
            terminal_event,
        )
        learning_inputs = _with_event_source_provenance(
            _learning_inputs_for_workspace(current, db_path=db_path),
            current,
            terminal_events,
        )
        experience = build_investigation_experience(
            investigation=investigation,
            events=terminal_events,
            current=learning_inputs,
            terminal_decision=current.terminal_decision,
            p32_projection_sha256=current.performance_intelligence.projection_sha256,
        )
        repository.append_terminal_event_and_experience(
            terminal_event,
            experience,
        )
        clear_learning_cache()
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    return updated


def record_driver_answer(
    run_id: str,
    investigation_id: str,
    *,
    session_id: str,
    expected_workspace_revision: str,
    answer: str,
    db_path: str | Path | None = None,
) -> CrewChiefWorkspace:
    current = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    if current.identity.workspace_revision != expected_workspace_revision:
        raise ValueError(
            "Crew Chief workspace revision is stale; rebase before continuing."
        )
    question = current.pending_driver_question
    if (
        current.folded_state is None
        or current.folded_state.status != "open"
        or question is None
        or answer not in question.answer_options
    ):
        raise ValueError("Driver answer must match the pending contextual question.")
    sequence = current.folded_state.last_sequence + 1
    repository = CrewChiefRepository(db_path)
    answer_event = _event(
        investigation_id,
        sequence,
        current.identity.workspace_revision,
        "driver_answer_recorded",
        CrewChiefEventPayload(
            message="Driver context recorded; telemetry evidence is unchanged.",
            question_id=question.question_id,
            answer=answer,
            cause_ids=question.distinguishes_cause_ids,
            component_ids=question.distinguishes_component_ids,
        ),
    )
    repository.append_event(answer_event)
    investigation = current.investigation
    if investigation is None:
        raise ValueError("Crew Chief investigation identity is unavailable.")
    memory_identity = [
        investigation_id,
        answer_event.event_id,
        answer,
        question.distinguishes_cause_ids,
        question.distinguishes_component_ids,
    ]
    repository.save_driver_memory(
        DriverKnowledgeRecord(
            record_id=f"ccdm_{canonical_json_sha256(memory_identity)[:24]}",
            investigation_id=investigation_id,
            session_id=session_id,
            complaint_phrase=investigation.raw_driver_report,
            contextual_answer=answer,
            associated_cause_ids=question.distinguishes_cause_ids,
            source_event_ids=(answer_event.event_id,),
            recorded_at=answer_event.created_at,
        )
    )
    return build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )


def abandon_investigation(
    run_id: str,
    investigation_id: str,
    *,
    session_id: str,
    expected_workspace_revision: str,
    reason: str,
    db_path: str | Path | None = None,
) -> CrewChiefWorkspace:
    current = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    if current.identity.workspace_revision != expected_workspace_revision:
        raise ValueError(
            "Crew Chief workspace revision is stale; rebase before continuing."
        )
    if current.folded_state is None or current.folded_state.status != "open":
        raise ValueError("Crew Chief investigation is not open.")
    sequence = current.folded_state.last_sequence + 1
    repository = CrewChiefRepository(db_path)
    terminal_event = _event(
        investigation_id,
        sequence,
        current.identity.workspace_revision,
        "investigation_abandoned",
        CrewChiefEventPayload(
            message=" ".join(reason.split()) or "Abandoned by driver."
        ),
    )
    investigation = current.investigation
    if investigation is None:
        raise ValueError("Crew Chief terminal learning requires an investigation.")
    terminal_events = (
        *repository.list_events(investigation_id),
        terminal_event,
    )
    learning_inputs = _with_event_source_provenance(
        _learning_inputs_for_workspace(current, db_path=db_path),
        current,
        terminal_events,
    )
    experience = build_investigation_experience(
        investigation=investigation,
        events=terminal_events,
        current=learning_inputs,
        terminal_decision=None,
        p32_projection_sha256=current.performance_intelligence.projection_sha256,
    )
    repository.append_terminal_event_and_experience(terminal_event, experience)
    clear_learning_cache()
    return build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )


def select_objective(
    run_id: str,
    investigation_id: str,
    *,
    session_id: str,
    expected_workspace_revision: str,
    objective: EngineeringObjective,
    db_path: str | Path | None = None,
) -> CrewChiefWorkspace:
    current = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    if current.identity.workspace_revision != expected_workspace_revision:
        raise ValueError(
            "Crew Chief workspace revision is stale; rebase before continuing."
        )
    if current.folded_state is None or current.folded_state.status != "open":
        raise ValueError("Crew Chief investigation is not open.")
    sequence = current.folded_state.last_sequence + 1
    repository = CrewChiefRepository(db_path)
    repository.append_event(
        _event(
            investigation_id,
            sequence,
            current.identity.workspace_revision,
            "objective_selected",
            CrewChiefEventPayload(
                message=f"Objective selected: {objective.value}.", objective=objective
            ),
        )
    )
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    repository.save_objective(
        investigation_id, updated.identity.workspace_revision, objective
    )
    return updated


def rebase_investigation(
    run_id: str,
    investigation_id: str,
    *,
    session_id: str,
    stale_workspace_revision: str,
    db_path: str | Path | None = None,
) -> CrewChiefWorkspace:
    current = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    if current.folded_state is None or current.folded_state.status not in {
        "open",
        "stale",
    }:
        raise ValueError(
            "Crew Chief investigation cannot be rebased in its current state."
        )
    if current.folded_state.status == "open":
        if current.identity.workspace_revision == stale_workspace_revision:
            return current
        raise ValueError("Crew Chief rebase revision is stale.")
    events = CrewChiefRepository(db_path).list_events(investigation_id)
    accepted_workspace = _accepted_workspace_revision(current.investigation, events)
    if stale_workspace_revision != accepted_workspace:
        raise ValueError("Crew Chief rebase revision is stale.")
    accepted_authority = _accepted_authority_revision(current.investigation, events)
    current_authority = _authority_revision(current.identity)
    sequence = current.folded_state.last_sequence + 1
    CrewChiefRepository(db_path).append_event(
        _event(
            investigation_id,
            sequence,
            current.identity.workspace_revision,
            "workspace_rebased",
            CrewChiefEventPayload(
                message="Workspace rebased to current P19/P20/P26 identities.",
                previous_workspace_revision=stale_workspace_revision,
                new_workspace_revision=current.identity.workspace_revision,
                previous_authority_revision=accepted_authority,
                new_authority_revision=current_authority,
            ),
        )
    )
    return build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )


__all__ = [
    "abandon_investigation",
    "build_crew_chief_workspace",
    "continue_investigation",
    "fold_investigation",
    "open_investigation",
    "rebase_investigation",
    "record_driver_answer",
    "select_objective",
]
