"""Deterministic P27-P33 Crew Chief executive.

This layer schedules inspection and presents one atomic workspace.  It never
recomputes P19 setup or policy authority and never analyzes raw telemetry.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
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
    p34_qualified_current_artifact_cohort,
    p34_qualified_current_artifact_ids,
    RunSentinelLap,
    RunSentinelState,
    SuccessContract,
    SuccessMetric,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.experiment import MeasurementAttempt
from racelab_engine.models.investigation_adaptation import (
    DiscriminatorOutcome,
    InvestigationAdaptationContext,
    InvestigationDecision,
    InvestigationImprovementProjection,
    InvestigationImprovementReadiness,
    InvestigationOutcomeCertificate,
    NegativeControlConditionEvidence,
    PairedInvestigationComparison,
    PairedInvestigationDecision,
    P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS,
    P19CauseState,
    canonical_context_subgroups,
    investigation_adaptation_source_snapshot_sha256,
)
from racelab_engine.models.engineering_learning import (
    CrewChiefLearningPrior,
    EngineeringExperienceRecord,
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
from racelab_engine.services.investigation_adaptation_service import (
    assess_p34_repository_readiness,
    baseline_investigation_policy,
    build_discriminator_outcome_from_crew_events,
    build_investigation_outcome_certificate,
    build_investigation_improvement_projection,
    build_paired_investigation_comparison,
    build_paired_investigation_decision,
    classify_p34_problem_family,
    classify_p34_problem_orientation,
    classify_p34_track_class,
    limited_attention_investigation_policy,
    memory_shadow_investigation_policy,
    p34_activation_protocol,
    persist_p34_foundation,
    recover_unreviewed_p34_terminal_capture,
    restore_effective_activation_on_mutation,
    review_p34_after_terminal_capture,
    resolve_effective_activation_decision,
)
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
from racelab_engine.storage.db import default_db_path, initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    EngineeringLearningRepository,
)
from racelab_engine.storage.investigation_adaptation_repository import (
    InvestigationAdaptationIntegrityError,
    InvestigationAdaptationRepository,
)
from racelab_engine.storage.repository import RaceLabRepository


_CACHE_LOCK = RLock()
_CACHE: dict[tuple[str, ...], CrewChiefWorkspace] = {}


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

_P34_PRIORITY_TIER_BY_SAFETY_BAND: dict[str, str] = {
    "integrity": "identity_integrity",
    "context": "context_qualification",
    "performance_measurement": "driver_car_confounders",
    "driver": "driver_car_confounders",
    "contradiction": "strongest_contradiction",
    "mechanism_separation": "unresolved_p19_mechanisms",
    "component_separation": "component_family_separation",
    "history": "exact_history",
    "measurement_debt": "measurement_debt",
}
_P34_SAFE_REORDER_GROUP_BY_SAFETY_BAND: dict[str, str] = {
    "performance_measurement": "performance_measurement",
}
_P34_MANDATORY_CHECK_IDS = (
    "workspace_identity",
    "data_integrity",
    "telemetry_health",
    "context_comparability",
    "traffic_contamination",
    "vehicle_condition_epoch",
    "applied_control_state",
    "strongest_contradiction",
    "driver_car_separation",
)
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
    learning_ledger_head_sha256: str | None,
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
        "learning_head": learning_ledger_head_sha256,
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
        learning_ledger_head_sha256=base["learning_head"],
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

    return identity.authority_revision


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


def _p34_locked_readiness(
    *blockers: str,
) -> InvestigationImprovementReadiness:
    reasons = _unique(
        blockers
        or (
            "No frozen pre-outcome P34 pair exists for this Crew revision.",
            "Limited attention has not earned the preregistered activation gate.",
        )
    )
    return InvestigationImprovementReadiness(
        production_policy="deterministic_baseline",
        memory_policy_state="shadow_only",
        activation_decision="no_activation_earned",
        evaluation_decision="no_activation_earned",
        effective_activation_decision_id=None,
        effective_activation_decision_sha256=None,
        qualified_historical_investigations=0,
        qualified_prospective_investigations=0,
        observable_comparisons=0,
        unobservable_comparisons=0,
        historical_deficit=20,
        prospective_deficit=12,
        exact_recurrence_deficit=5,
        compatible_recurrence_deficit=5,
        context_deficit=3,
        problem_family_deficit=4,
        objective_deficit=2,
        safety_gate_passed=False,
        negative_controls_passed=False,
        subgroup_gate_passed=False,
        blockers=reasons,
        remaining_collection_missions=(
            "Collect qualified independent investigations under the frozen protocol.",
            "Complete prospective recurrence and negative-control evidence.",
        ),
    )


def _p34_unavailable_projection(
    identity: CrewChiefWorkspaceIdentity,
    *blockers: str,
) -> InvestigationImprovementProjection:
    readiness = _p34_locked_readiness(*blockers)
    reasons = readiness.blockers
    return InvestigationImprovementProjection.build(
        run_id=identity.run_id,
        session_id=identity.session_id,
        workspace_revision=identity.workspace_revision,
        state="unavailable",
        production_policy="deterministic_baseline",
        memory_policy_state="shadow_only",
        current_pair=None,
        current_context=None,
        current_pair_status=None,
        latest_completed_pair=None,
        latest_completed_comparison=None,
        latest_outcome_status=None,
        decisions_differ=False,
        difference_explanation=(
            "The deterministic baseline remains production; no executable memory "
            "difference is claimed without a frozen pair."
        ),
        context_transfer_class="none",
        readiness=readiness,
        safety_blockers=reasons,
    )


def _p34_current_baseline_readiness(
    readiness: InvestigationImprovementReadiness,
    *blockers: str,
) -> InvestigationImprovementReadiness:
    """Overlay a current-revision rollback without rewriting earned history."""

    reasons = _unique(
        (*readiness.blockers, *blockers)
        or (
            "The current Crew revision did not qualify limited attention; "
            "the deterministic baseline remains production.",
        )
    )
    missions = _unique(
        (
            *readiness.remaining_collection_missions,
            "Resolve the current-revision blocker before limited attention is reconsidered.",
        )
    )
    return InvestigationImprovementReadiness.model_validate(
        {
            **readiness.model_dump(mode="python"),
            "production_policy": "deterministic_baseline",
            "memory_policy_state": "shadow_only",
            "activation_decision": "no_activation_earned",
            "effective_activation_decision_id": None,
            "effective_activation_decision_sha256": None,
            "blockers": reasons,
            "remaining_collection_missions": missions,
        }
    )


def _p34_projection_for_identity(
    identity: CrewChiefWorkspaceIdentity,
    *,
    investigation_open: bool,
    current_learning: CurrentLearningInputs,
    learning_prior: CrewChiefLearningPrior,
    folded: FoldedInvestigationState | None,
    baseline_subgoal: InvestigationSubgoal | None,
    evidence_index: EngineeringEvidenceIndex,
    terminal_decision: CrewChiefTerminalDecision,
    p19_cause_ids: tuple[str, ...],
    p19_contradiction_artifact_ids: tuple[str, ...],
    blocker_reasons: tuple[str, ...],
    db_path: str | Path | None,
) -> InvestigationImprovementProjection:
    repository = InvestigationAdaptationRepository(db_path)
    pair: PairedInvestigationDecision | None = None
    latest_completed_pair: PairedInvestigationDecision | None = None
    latest_comparison: PairedInvestigationComparison | None = None
    pair_blockers: tuple[str, ...] = ()
    current_context: InvestigationAdaptationContext | None = None
    if identity.investigation_id is not None and investigation_open:
        try:
            pair = repository.latest_pair(
                identity.investigation_id,
                identity.workspace_revision,
            )
        except (InvestigationAdaptationIntegrityError, sqlite3.Error, OSError) as exc:
            pair_blockers = (f"P34 current pair is unavailable: {exc}",)
    if identity.investigation_id is not None and not investigation_open:
        try:
            comparison_result = repository.query_records(
                record_kinds=("paired_comparison",),
                investigation_id=identity.investigation_id,
                limit=1,
            )
            if comparison_result.blockers:
                raise InvestigationAdaptationIntegrityError(
                    comparison_result.blockers[0]
                )
            latest_comparison = next(
                (
                    item
                    for item in comparison_result.records
                    if isinstance(item, PairedInvestigationComparison)
                ),
                None,
            )
            if latest_comparison is not None:
                latest_completed_pair = repository.get_paired_decision(
                    latest_comparison.pair_sha256
                )
                if latest_completed_pair is None or (
                    latest_completed_pair.pair_id != latest_comparison.pair_id
                    or latest_completed_pair.investigation_id
                    != identity.investigation_id
                ):
                    raise InvestigationAdaptationIntegrityError(
                        "P34 completed comparison is missing its exact parent pair"
                    )
        except (InvestigationAdaptationIntegrityError, sqlite3.Error, OSError) as exc:
            pair_blockers = (
                f"P34 completed comparison is unavailable: {exc}",
            )
    try:
        readiness = assess_p34_repository_readiness(repository)
    except (
        InvestigationAdaptationIntegrityError,
        sqlite3.Error,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        readiness = _p34_locked_readiness(
            f"P34 readiness is blocked by adaptation-ledger integrity: {exc}"
        )
    if pair is not None and pair.activation_state == "limited_attention":
        activation = resolve_effective_activation_decision(repository)
        if (
            activation is None
            or activation.decision_id != pair.activation_decision_id
            or activation.decision_sha256 != pair.activation_decision_sha256
        ):
            pair = None
            pair_blockers = (
                "P34 limited attention no longer matches a current earned activation; baseline fallback is active.",
            )
    if pair is not None:
        try:
            if folded is None or folded.status != "open":
                raise ValueError("P34 current context requires an open Crew revision")
            current_context = _p34_adaptation_context_for_pair(
                pair,
                identity=identity,
                current_learning=current_learning,
                learning_prior=learning_prior,
                folded=folded,
                baseline_subgoal=baseline_subgoal,
                evidence_index=evidence_index,
                terminal_decision=terminal_decision,
                p19_cause_ids=p19_cause_ids,
                p19_contradiction_artifact_ids=(
                    p19_contradiction_artifact_ids
                ),
                blocker_reasons=blocker_reasons,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            pair = None
            current_context = None
            pair_blockers = _unique(
                (
                    *pair_blockers,
                    f"P34 current context is unavailable: {exc}",
                )
            )
    if investigation_open and (
        pair is None or pair.activation_state == "shadow_only"
    ) and readiness.memory_policy_state == "limited_attention":
        fallback_reason = (
            pair_blockers[0]
            if pair_blockers
            else (
                "The current P33 transfer is blocked, weak, stale, or drifted; "
                "the earned policy remains historical and the deterministic "
                "baseline controls this revision."
            )
        )
        pair_blockers = _unique((*pair_blockers, fallback_reason))
        readiness = _p34_current_baseline_readiness(
            readiness,
            fallback_reason,
        )
    return build_investigation_improvement_projection(
        run_id=identity.run_id,
        session_id=identity.session_id,
        workspace_revision=identity.workspace_revision,
        readiness=readiness,
        current_pair=pair,
        current_context=current_context,
        latest_completed_pair=latest_completed_pair,
        latest_completed_comparison=latest_comparison,
        safety_blockers=pair_blockers,
    )


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
    seen_prediction_pair_ids: set[str] = set()
    seen_prediction_pair_sha256s: set[str] = set()
    for expected, event in enumerate(events, start=1):
        if (
            event.sequence != expected
            or event.investigation_id != investigation.investigation_id
        ):
            raise ValueError("Crew Chief event fold encountered non-canonical history")
        payload = event.payload
        if payload.adaptation_prediction_pair_id is not None:
            prediction_sha256 = payload.adaptation_prediction_pair_sha256
            prediction_source_sha256 = (
                payload.adaptation_prediction_source_snapshot_sha256
            )
            if prediction_sha256 is None or prediction_source_sha256 is None:
                raise ValueError(
                    "Crew Chief event fold encountered an incomplete P34 prediction pair"
                )
            if (
                payload.adaptation_prediction_pair_id in seen_prediction_pair_ids
                or prediction_sha256 in seen_prediction_pair_sha256s
            ):
                raise ValueError(
                    "Crew Chief event fold encountered a reused P34 prediction pair"
                )
            seen_prediction_pair_ids.add(payload.adaptation_prediction_pair_id)
            seen_prediction_pair_sha256s.add(prediction_sha256)
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
    """Return the deterministic production subgoal.

    P34 deliberately keeps P33 out of this decision. ``learning_prior`` remains
    in the signature for source compatibility, while the paired memory decision
    is built separately by :func:`_memory_shadow_subgoal`.
    """

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
    tool = live[0] if live else None
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
    return InvestigationSubgoal(
        subgoal_id=f"ccs_{canonical_json_sha256([folded.investigation_id, tool])[:20]}",
        title=f"Inspect {tool.replace('_', ' ')}",
        selected_tool=tool,
        why_this_tool=(
            "It is the next bounded inspection under the integrity/context/driver/"
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


def _memory_record_times(
    learning_prior: CrewChiefLearningPrior,
) -> dict[str, datetime]:
    """Resolve when each attention-producing investigation became available."""

    return {
        item.experience_id: item.outcome.completed_at
        for item in learning_prior.useful_prior_investigations
    }


def _qualified_memory_attention(
    learning_prior: CrewChiefLearningPrior | None,
    *,
    completed_tool_ids: tuple[str, ...],
    decision_frozen_at: datetime,
) -> tuple[object, ...]:
    if learning_prior is None:
        return ()
    try:
        if (
            learning_prior.state != "available"
            or learning_prior.context_transfer_level not in {"exact", "compatible"}
            or any(
                item.state == "changed_behavior"
                for item in learning_prior.driver_tendencies
            )
        ):
            return ()
        completed = set(completed_tool_ids)
        record_times = _memory_record_times(learning_prior)
        transfer_by_experience = {
            item.experience_id: item for item in learning_prior.context_transfers
        }
        qualified = []
        for attention in learning_prior.recommended_attention_order:
            source_ids = tuple(attention.source_experience_ids)
            transfers = tuple(
                transfer_by_experience.get(experience_id)
                for experience_id in source_ids
            )
            if (
                attention.tool_id in completed
                or attention.safety_band
                != _TOOL_SAFETY_BANDS.get(attention.tool_id)
                or attention.transfer_level not in {"exact", "compatible"}
                or not source_ids
                or any(experience_id not in record_times for experience_id in source_ids)
                or any(
                    record_times[experience_id] >= decision_frozen_at
                    for experience_id in source_ids
                )
                or any(
                    transfer is None
                    or transfer.level not in {"exact", "compatible"}
                    or transfer.drift_reasons
                    or transfer.blocker_reasons
                    for transfer in transfers
                )
            ):
                continue
            qualified.append(attention)
        return tuple(qualified)
    except (AttributeError, KeyError, TypeError, ValueError):
        return ()


def _memory_shadow_from_baseline(
    baseline: InvestigationSubgoal | None,
    folded: FoldedInvestigationState | None,
    learning_prior: CrewChiefLearningPrior | None,
    *,
    decision_frozen_at: datetime,
    qualified_current_evidence_tool_ids: tuple[str, ...] = (),
) -> tuple[
    InvestigationSubgoal | None,
    tuple[str, ...],
    Literal["none", "exact", "compatible", "weak", "blocked"],
]:
    """Return shadow choice, exact consulted P33 IDs, and transfer class."""

    if baseline is None or folded is None:
        return baseline, (), "none"
    qualified = _qualified_memory_attention(
        learning_prior,
        completed_tool_ids=folded.completed_tool_ids,
        decision_frozen_at=decision_frozen_at,
    )
    if not qualified or learning_prior is None:
        return baseline, (), "none"
    baseline_band = _TOOL_SAFETY_BANDS[baseline.selected_tool]
    if baseline_band not in _P34_SAFE_REORDER_GROUP_BY_SAFETY_BAND:
        return baseline, (), "none"
    band_tools = tuple(
        tool_id
        for tool_id, safety_band in _TOOL_SAFETY_BANDS.items()
        if safety_band == baseline_band
        and tool_id not in set(folded.completed_tool_ids)
    )
    if not band_tools or band_tools[0] != baseline.selected_tool:
        return baseline, (), "none"
    global_band_rank = {
        tool_id: index
        for index, tool_id in enumerate(
            (
                tool_id
                for tool_id, safety_band in _TOOL_SAFETY_BANDS.items()
                if safety_band == baseline_band
            ),
            start=1,
        )
    }
    eligible = tuple(
        item
        for item in qualified
        if item.tool_id in band_tools
        and global_band_rank.get(item.tool_id)
        == item.baseline_rank_within_band
    )
    if not eligible:
        return baseline, (), "none"
    attention = min(
        eligible,
        key=lambda item: (
            item.learned_rank_within_band,
            item.baseline_rank_within_band,
            item.tool_id,
        ),
    )
    position = band_tools.index(attention.tool_id)
    source_ids = tuple(attention.source_experience_ids)
    transfer_class = attention.transfer_level
    if position == 0:
        return baseline, source_ids, transfer_class
    if baseline.selected_tool in qualified_current_evidence_tool_ids:
        # Newly qualified evidence that is already linked to a current P19
        # ambiguity outranks historical attention. A prior dead end can never
        # delay the current discriminator that may change the live reasoning.
        return baseline, (), "blocked"
    if baseline.selected_tool == "inspect_driver_vehicle_separation":
        # This check is a frozen prerequisite, not an interchangeable
        # performance-measurement preference. Memory cannot put a vehicle-only
        # reading ahead of unresolved driver-versus-car separation.
        return baseline, (), "blocked"
    if (
        position != 1
        or attention.learned_rank_within_band
        >= attention.baseline_rank_within_band
    ):
        return baseline, (), "none"
    tool = attention.tool_id
    shadow = baseline.model_copy(
        update={
            "subgoal_id": f"ccs_{canonical_json_sha256([folded.investigation_id, tool])[:20]}",
            "title": f"Inspect {tool.replace('_', ' ')}",
            "selected_tool": tool,
            "why_this_tool": (
                "Qualified P33 history moved this inspection one "
                f"position earlier inside the {attention.safety_band} tier. "
                f"{attention.reason} P19 cause order, terminal action, and setup "
                "authority remain the deterministic baseline."
            ),
        }
    )
    return shadow, source_ids, transfer_class


def _memory_shadow_subgoal(
    bundle: RunIntelligenceBundle,
    folded: FoldedInvestigationState | None,
    p26: object,
    p32: object,
    learning_prior: CrewChiefLearningPrior | None,
    *,
    decision_frozen_at: datetime,
) -> InvestigationSubgoal | None:
    """Build one deterministic, bounded, shadow-only memory decision.

    Memory may move at most one qualified inspection by one position inside the
    same immutable safety tier. Missing, corrupt, weak, future, drifted, or
    blocked history falls back to the production baseline exactly.
    """

    baseline = _subgoal(bundle, folded, p26, p32)
    shadow, _, _ = _memory_shadow_from_baseline(
        baseline,
        folded,
        learning_prior,
        decision_frozen_at=decision_frozen_at,
    )
    return shadow


def _p34_tool_ordinal(tool_id: str) -> int:
    safety_band = _TOOL_SAFETY_BANDS[tool_id]
    return next(
        index
        for index, (candidate, candidate_band) in enumerate(
            (
                item
                for item in _TOOL_SAFETY_BANDS.items()
                if item[1] == safety_band
            ),
            start=1,
        )
        if candidate == tool_id and candidate_band == safety_band
    )


def _p34_inspection_decision(
    subgoal: InvestigationSubgoal,
    *,
    source_memory_record_ids: tuple[str, ...] = (),
    moved_one_position: bool = False,
) -> InvestigationDecision:
    tool_id = subgoal.selected_tool
    safety_band = _TOOL_SAFETY_BANDS[tool_id]
    safe_group = _P34_SAFE_REORDER_GROUP_BY_SAFETY_BAND.get(safety_band)
    baseline_ordinal = _p34_tool_ordinal(tool_id) if safe_group is not None else 1
    return InvestigationDecision(
        decision_kind="inspect_tool",
        action_id=tool_id,
        priority_tier=_P34_PRIORITY_TIER_BY_SAFETY_BAND[safety_band],
        safe_reorder_group=safe_group,
        baseline_ordinal=baseline_ordinal,
        selected_ordinal=(
            baseline_ordinal - 1 if moved_one_position else baseline_ordinal
        ),
        reason=subgoal.why_this_tool,
        mandatory_check_ids=_P34_MANDATORY_CHECK_IDS,
        source_memory_record_ids=source_memory_record_ids,
    )


def _p34_non_tool_decision(workspace: CrewChiefWorkspace) -> InvestigationDecision:
    folded = workspace.folded_state
    if folded is None:
        raise ValueError("P34 decisions require an open Crew investigation.")
    if (
        folded.pending_driver_question_id is not None
        or not folded.driver_answers
    ):
        question_id = folded.pending_driver_question_id or (
            "ccq_"
            + canonical_json_sha256(
                [folded.investigation_id, folded.last_sequence + 1]
            )[:20]
        )
        return InvestigationDecision(
            decision_kind="ask_driver",
            action_id=question_id,
            priority_tier="driver_car_confounders",
            baseline_ordinal=1,
            selected_ordinal=1,
            reason=(
                "The deterministic planner requires one contextual driver answer "
                "after integrity and context qualification."
            ),
            mandatory_check_ids=_P34_MANDATORY_CHECK_IDS,
        )
    terminal = workspace.terminal_decision
    return InvestigationDecision(
        decision_kind=("no_call" if terminal.kind == "no_call" else "observe_only"),
        action_id=(
            f"terminal:{terminal.kind}:"
            f"{canonical_json_sha256([terminal.kind, terminal.instruction])[:24]}"
        ),
        priority_tier="terminal",
        baseline_ordinal=1,
        selected_ordinal=1,
        reason=(
            "P34 records the exact Crew/P19 terminal boundary without changing it."
        ),
        mandatory_check_ids=_P34_MANDATORY_CHECK_IDS,
    )


def _p34_qualified_current_evidence_tool_ids(
    workspace: CrewChiefWorkspace,
) -> tuple[str, ...]:
    """Return the exact live baseline tools pinned by qualified P19 evidence."""

    baseline_subgoal = workspace.current_subgoal
    if baseline_subgoal is None:
        return ()
    relevant_hypotheses = tuple(
        item
        for item in (workspace.folded_state.hypotheses if workspace.folded_state else ())
        if item.cause_id in baseline_subgoal.distinguishes_cause_ids
    )
    current_cause_artifact_ids = {
        artifact_id
        for item in relevant_hypotheses
        for artifact_id in (
            *item.support_artifact_ids,
            *item.contradiction_artifact_ids,
        )
    }
    current_entries = _select_tool_entries(
        workspace,
        baseline_subgoal.selected_tool,
        baseline_subgoal.distinguishes_cause_ids,
    )
    identity = getattr(workspace, "identity", None)
    qualified_current_artifact_ids = (
        set(
            p34_qualified_current_artifact_ids(
                identity,
                workspace.evidence_index,
            )
        )
        if identity is not None
        else set()
    )
    return (
        (baseline_subgoal.selected_tool,)
        if current_cause_artifact_ids
        and any(
            item.artifact_id in current_cause_artifact_ids
            and item.artifact_id in qualified_current_artifact_ids
            for item in current_entries
        )
        else ()
    )


def _p34_decisions_for_workspace(
    workspace: CrewChiefWorkspace,
    *,
    decision_frozen_at: datetime,
) -> tuple[
    InvestigationDecision,
    InvestigationDecision,
    Literal["none", "exact", "compatible", "weak", "blocked"],
]:
    baseline_subgoal = workspace.current_subgoal
    if baseline_subgoal is None:
        baseline = _p34_non_tool_decision(workspace)
        return baseline, baseline, "none"
    qualified_current_evidence_tool_ids = (
        _p34_qualified_current_evidence_tool_ids(workspace)
    )
    shadow_subgoal, memory_ids, transfer_class = _memory_shadow_from_baseline(
        baseline_subgoal,
        workspace.folded_state,
        workspace.learning_prior,
        decision_frozen_at=decision_frozen_at,
        qualified_current_evidence_tool_ids=qualified_current_evidence_tool_ids,
    )
    baseline = _p34_inspection_decision(baseline_subgoal)
    if shadow_subgoal is None:
        return baseline, baseline, "none"
    memory = _p34_inspection_decision(
        shadow_subgoal,
        source_memory_record_ids=memory_ids,
        moved_one_position=(
            shadow_subgoal.selected_tool != baseline_subgoal.selected_tool
        ),
    )
    return baseline, memory, transfer_class


def _p34_current_truth_sha256(workspace: CrewChiefWorkspace) -> str:
    return canonical_json_sha256(
        {
            "identity": workspace.identity,
            "evidence_index_sha256": workspace.evidence_index.index_hash,
            "terminal_decision": workspace.terminal_decision,
            "p19_cause_ids": workspace.p19_cause_ids,
            "p19_cause_states": tuple(
                (item.cause_id, item.p19_state)
                for item in (
                    workspace.folded_state.hypotheses
                    if workspace.folded_state is not None
                    else ()
                )
            ),
            "p19_contradiction_artifact_ids": (
                workspace.p19_contradiction_artifact_ids
            ),
        }
    )


def _p34_source_snapshot_sha256(
    workspace: CrewChiefWorkspace,
    *,
    workspace_revision: str | None = None,
) -> str:
    """Hash producer-owned source revisions independently of a P34 pair."""

    identity = workspace.identity
    return investigation_adaptation_source_snapshot_sha256(
        run_id=identity.run_id,
        session_id=identity.session_id,
        workspace_revision=workspace_revision or identity.workspace_revision,
        authority_revision=identity.authority_revision,
        current_truth_sha256=_p34_current_truth_sha256(workspace),
        p19_snapshot_sha256=identity.reasoning_snapshot_sha256,
        p20_projection_sha256=identity.p20_state_revision,
        p26_projection_sha256=identity.p26_knowledge_graph_sha256,
        p32_projection_sha256=identity.p32_projection_sha256,
    )


def _p34_restart_context(
    workspace: CrewChiefWorkspace,
    current: CurrentLearningInputs,
    baseline: InvestigationDecision,
    memory: InvestigationDecision,
    transfer_class: Literal["none", "exact", "compatible", "weak", "blocked"],
    *,
    decision_frozen_at: datetime,
) -> tuple[
    Literal[
        "braking",
        "entry",
        "center",
        "exit",
        "straight",
        "long_run",
        "mixed",
        "unresolved",
    ],
    Literal["driver", "vehicle", "combined", "unresolved"],
    Literal[
        "short_track", "intermediate", "superspeedway", "road_course", "unknown"
    ],
    tuple[str, ...],
    Literal["same_build", "reviewed_compatible_build", "future_unreviewed_build"],
    Literal["stable", "material_drift", "unknown"],
    Literal["none", "exact", "compatible", "weak", "blocked"],
    InvestigationDecision,
    tuple[str, ...],
    Literal[
        "no_relevant_history",
        "incompatible_history",
        "corrupt_history",
        "generic_component_knowledge_only",
        "same_words_different_physical_scope",
        "material_driver_drift",
        "future_memory_record",
    ]
    | None,
]:
    """Freeze restart-safe subgroup/drift truth before the paired decision."""

    source_ids = set(memory.source_memory_record_ids)
    all_transfers = tuple(workspace.learning_prior.context_transfers)
    transfers = tuple(
        item
        for item in all_transfers
        if item.experience_id in source_ids
    )
    future_memory_record_ids = tuple(
        item.experience_id
        for item in getattr(
            workspace.learning_prior, "useful_prior_investigations", ()
        )
        if item.outcome.completed_at >= decision_frozen_at
    )
    if future_memory_record_ids:
        transfer_class = "blocked"
        memory = baseline
    elif not source_ids:
        transfer_levels = {item.level for item in all_transfers}
        if getattr(workspace.learning_prior, "state", None) == "blocked":
            transfer_class = "blocked"
        elif "blocked" in transfer_levels:
            transfer_class = "blocked"
        elif "weak" in transfer_levels:
            transfer_class = "weak"
    future_build = any(
        "future" in reason.casefold() and "build" in reason.casefold()
        for reason in workspace.blocker_reasons
    )
    if future_build:
        build_state: Literal[
            "same_build", "reviewed_compatible_build", "future_unreviewed_build"
        ] = "future_unreviewed_build"
    elif (transfers or all_transfers) and any(
        "iRacing_build" in item.mismatched_dimensions
        for item in (transfers or all_transfers)
    ):
        # A P33 transfer mismatch is not a typed build-compatibility review.
        # Without an exact server-owned review artifact, the build remains
        # unreviewed and cannot control production attention.
        build_state = "future_unreviewed_build"
    else:
        build_state = "same_build"
    if any(
        item.state == "changed_behavior"
        for item in workspace.learning_prior.driver_tendencies
    ):
        driver_state: Literal["stable", "material_drift", "unknown"] = (
            "material_drift"
        )
    elif (transfers or all_transfers) and all(
        not item.drift_reasons
        and "driver_execution_state" in item.matching_dimensions
        and "driver_execution_state" not in item.mismatched_dimensions
        for item in (transfers or all_transfers)
    ):
        driver_state = "stable"
    else:
        driver_state = "unknown"
    decisions_differ = baseline.executable_identity != memory.executable_identity
    if (
        build_state == "future_unreviewed_build"
        or driver_state == "material_drift"
        or driver_state == "unknown" and decisions_differ
    ):
        transfer_class = "blocked"
        memory = baseline
    problem_family = classify_p34_problem_family(
        phase=current.problem.phase,
        objective=current.context.objective,
        driver_demand_state=current.problem.driver_demand_state,
        vehicle_response_state=current.problem.vehicle_response_state,
    )
    problem_orientation = classify_p34_problem_orientation(
        driver_demand_state=current.problem.driver_demand_state,
        vehicle_response_state=current.problem.vehicle_response_state,
    )
    track_class = classify_p34_track_class(
        track=current.context.track,
        track_configuration=current.context.track_configuration,
        package_type=current.context.package_type,
    )
    subgroups = canonical_context_subgroups(
        context_transfer_class=transfer_class,
        problem_orientation=problem_orientation,
        problem_family=problem_family,
        objective=current.context.objective,
        track_class=track_class,
        driver_drift_state=driver_state,
        build_review_state=build_state,
    )
    prior = workspace.learning_prior
    blocked_transfer = any(item.level == "blocked" for item in all_transfers)
    weak_transfer = any(item.level == "weak" for item in all_transfers)
    physical_scope_mismatches = {
        dimension
        for item in all_transfers
        if item.level == "weak"
        for dimension in item.mismatched_dimensions
        if dimension in P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS
    }
    recurrence_class = getattr(getattr(prior, "recurrence", None), "classification", None)
    negative_control = (
        "future_memory_record"
        if future_memory_record_ids
        else "material_driver_drift"
        if driver_state == "material_drift"
        else "corrupt_history"
        if getattr(prior, "state", None) == "blocked"
        else "incompatible_history"
        if blocked_transfer
        and build_state != "future_unreviewed_build"
        and driver_state == "stable"
        else "generic_component_knowledge_only"
        if weak_transfer
        and problem_orientation == "vehicle"
        and bool(getattr(prior, "car_response_history", ()))
        and not getattr(prior, "useful_prior_investigations", ())
        and not physical_scope_mismatches
        else "same_words_different_physical_scope"
        if weak_transfer
        and bool(physical_scope_mismatches)
        and recurrence_class in {
            "possible_recurrence",
            "strong_recurrence",
            "exact_context_recurrence",
        }
        else "no_relevant_history"
        if transfer_class == "none"
        and not getattr(prior, "useful_prior_investigations", ())
        and not all_transfers
        else None
    )
    return (
        problem_family,
        problem_orientation,
        track_class,
        subgroups,
        build_state,
        driver_state,
        transfer_class,
        memory,
        future_memory_record_ids,
        negative_control,
    )


def _p34_negative_control_evidence(
    workspace: CrewChiefWorkspace,
    *,
    condition: Literal[
        "no_relevant_history",
        "incompatible_history",
        "corrupt_history",
        "generic_component_knowledge_only",
        "same_words_different_physical_scope",
        "material_driver_drift",
        "future_memory_record",
    ]
    | None,
    driver_drift_state: Literal["stable", "material_drift", "unknown"],
    future_memory_record_ids: tuple[str, ...],
) -> NegativeControlConditionEvidence | None:
    """Bind a control label to the exact pre-outcome P33 facts that prove it."""

    if condition is None:
        return None
    prior = workspace.learning_prior
    transfers = tuple(prior.context_transfers)
    component_experience_ids = _unique(
        experience_id
        for item in prior.car_response_history
        for experience_id in item.source_experience_ids
    )
    physical_mismatches = _unique(
        dimension
        for item in transfers
        if item.level == "weak"
        for dimension in item.mismatched_dimensions
        if dimension in P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS
    )
    return NegativeControlConditionEvidence(
        condition=condition,
        p33_projection_sha256=prior.projection_sha256,
        p33_state=prior.state,
        context_transfer_record_ids=tuple(item.experience_id for item in transfers),
        context_transfer_levels=tuple(item.level for item in transfers),
        useful_prior_experience_ids=tuple(
            item.experience_id for item in prior.useful_prior_investigations
        ),
        component_history_experience_ids=component_experience_ids,
        physical_scope_mismatch_dimensions=physical_mismatches,
        recurrence_class=prior.recurrence.classification,
        corruption_blocker_sha256s=(
            tuple(canonical_json_sha256(item) for item in prior.blocker_reasons)
            if prior.state == "blocked"
            else ()
        ),
        future_memory_record_ids=future_memory_record_ids,
        future_memory_record_completed_ats=tuple(
            item.outcome.completed_at
            for experience_id in future_memory_record_ids
            for item in prior.useful_prior_investigations
            if item.experience_id == experience_id
        ),
        driver_drift_state=driver_drift_state,
    )


def _p34_live_eligible_tool_ids(
    baseline: InvestigationDecision,
    memory: InvestigationDecision,
    *,
    completed_tool_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return only the inspect actions the two frozen planners could execute now."""

    if baseline.decision_kind != "inspect_tool":
        return ()
    eligible = [baseline.action_id]
    if baseline.safe_reorder_group == "performance_measurement":
        completed = set(completed_tool_ids)
        live_group = tuple(
            tool_id
            for tool_id, safety_band in _TOOL_SAFETY_BANDS.items()
            if safety_band == "performance_measurement" and tool_id not in completed
        )
        if baseline.action_id not in live_group:
            raise ValueError("P34 baseline action is not live at decision freeze")
        position = live_group.index(baseline.action_id)
        if position + 1 < len(live_group):
            eligible.append(live_group[position + 1])
    if memory.decision_kind == "inspect_tool" and memory.action_id not in eligible:
        raise ValueError("P34 memory decision escaped the live one-slot cohort")
    return tuple(eligible)


def _p34_adaptation_context_for_pair(
    pair: PairedInvestigationDecision,
    *,
    identity: CrewChiefWorkspaceIdentity,
    current_learning: CurrentLearningInputs,
    learning_prior: CrewChiefLearningPrior,
    folded: FoldedInvestigationState,
    baseline_subgoal: InvestigationSubgoal | None,
    evidence_index: EngineeringEvidenceIndex,
    terminal_decision: CrewChiefTerminalDecision,
    p19_cause_ids: tuple[str, ...],
    p19_contradiction_artifact_ids: tuple[str, ...],
    blocker_reasons: tuple[str, ...],
) -> InvestigationAdaptationContext:
    """Rebuild public P34 context only from current Crew/P33 producer truth."""

    draft = SimpleNamespace(
        identity=identity,
        folded_state=folded,
        current_subgoal=baseline_subgoal,
        learning_prior=learning_prior,
        evidence_index=evidence_index,
        terminal_decision=terminal_decision,
        p19_cause_ids=p19_cause_ids,
        p19_contradiction_artifact_ids=p19_contradiction_artifact_ids,
        blocker_reasons=blocker_reasons,
    )
    baseline, memory, transfer_class = _p34_decisions_for_workspace(
        draft,
        decision_frozen_at=pair.decision_frozen_at,
    )
    (
        problem_family,
        problem_orientation,
        track_class,
        context_subgroups,
        build_review_state,
        driver_drift_state,
        transfer_class,
        _bounded_memory,
        future_memory_record_ids,
        negative_control_condition,
    ) = _p34_restart_context(
        draft,
        current_learning,
        baseline,
        memory,
        transfer_class,
        decision_frozen_at=pair.decision_frozen_at,
    )
    negative_control_evidence = _p34_negative_control_evidence(
        draft,
        condition=negative_control_condition,
        driver_drift_state=driver_drift_state,
        future_memory_record_ids=future_memory_record_ids,
    )
    (
        qualified_artifact_ids,
        qualified_artifact_states,
        qualified_artifact_provenance_sha256s,
    ) = p34_qualified_current_artifact_cohort(identity, evidence_index)
    current_evidence_pinned_tool_ids = tuple(
        tool_id
        for tool_id in _p34_qualified_current_evidence_tool_ids(draft)
        if tool_id in pair.eligible_tool_ids
    )
    return InvestigationAdaptationContext.build(
        run_id=identity.run_id,
        session_id=identity.session_id,
        workspace_revision=identity.workspace_revision,
        current_truth_sha256=_p34_current_truth_sha256(draft),
        p19_snapshot_sha256=identity.reasoning_snapshot_sha256,
        p20_projection_sha256=identity.p20_state_revision,
        p26_projection_sha256=identity.p26_knowledge_graph_sha256,
        p32_projection_sha256=identity.p32_projection_sha256,
        p33_projection_sha256=learning_prior.projection_sha256,
        p33_context_sha256=current_learning.context.context_sha256,
        p33_problem_sha256=current_learning.problem.problem_sha256,
        qualified_available_artifact_ids=qualified_artifact_ids,
        qualified_available_artifact_evidence_states=qualified_artifact_states,
        qualified_available_artifact_provenance_sha256s=(
            qualified_artifact_provenance_sha256s
        ),
        current_evidence_pinned_tool_ids=current_evidence_pinned_tool_ids,
        track=current_learning.context.track,
        track_configuration=current_learning.context.track_configuration,
        package_type=current_learning.context.package_type,
        iracing_build=current_learning.context.iracing_build,
        problem_family=problem_family,
        problem_orientation=problem_orientation,
        track_class=track_class,
        phase=current_learning.problem.phase,
        current_objective=identity.objective_id.value,
        build_review_state=build_review_state,
        driver_drift_state=driver_drift_state,
        context_subgroup_keys=context_subgroups,
        negative_control_condition=negative_control_condition,
        negative_control_evidence_sha256=(
            canonical_json_sha256(
                negative_control_evidence.model_dump(mode="json")
            )
            if negative_control_evidence is not None
            else None
        ),
    )


def _freeze_p34_pair_for_workspace(
    workspace: CrewChiefWorkspace,
    *,
    db_path: str | Path | None,
) -> PairedInvestigationDecision | None:
    if isinstance(workspace, CrewChiefWorkspace):
        try:
            # ``model_copy`` deliberately skips Pydantic validation. Rebuild
            # the complete public contract at the mutation boundary so a warm
            # or patched cache object cannot retain stale P33/P34 digests while
            # omitting learned attention or negative-control evidence.
            workspace = CrewChiefWorkspace.model_validate(
                workspace.model_dump(mode="json")
            )
        except (TypeError, ValueError):
            return None
    folded = getattr(workspace, "folded_state", None)
    investigation = getattr(workspace, "investigation", None)
    if (
        investigation is None
        or folded is None
        or folded.status != "open"
    ):
        return None
    repository = InvestigationAdaptationRepository(db_path)
    try:
        from racelab_engine.services.controlled_workflow_service import (
            recover_p34_scored_workflow_followups,
        )

        recover_p34_scored_workflow_followups(RaceLabRepository(db_path))
        recover_unreviewed_p34_terminal_capture(repository)
        # Preserve the policy/action already visible from the preceding GET.
        # A cold process may verify durable activation on this mutation, but
        # that newly restored authority starts only on the next Crew revision;
        # it cannot silently change NEXT A into executed action B.
        effective_before_restore = resolve_effective_activation_decision(repository)
        restore_effective_activation_on_mutation(repository)
        existing = repository.latest_pair(
            investigation.investigation_id,
            workspace.identity.workspace_revision,
        )
        if existing is not None:
            if existing.activation_state == "shadow_only":
                return existing
            effective = effective_before_restore
            if (
                effective is not None
                and effective.state == "limited_attention"
                and effective.decision_id == existing.activation_decision_id
                and effective.decision_sha256
                == existing.activation_decision_sha256
            ):
                return existing
            # An immutable active pair may outlive the activation that allowed
            # it to control this revision. Never replay that stale authority;
            # returning None makes the caller execute the Crew baseline.
            return None
        decision_frozen_at = _now()
        baseline_decision, memory_decision, transfer_class = (
            _p34_decisions_for_workspace(
                workspace,
                decision_frozen_at=decision_frozen_at,
            )
        )
        current_learning = _learning_inputs_for_workspace(
            workspace,
            db_path=db_path,
        )
        if (
            current_learning.context.context_sha256
            != workspace.learning_prior.current_context_sha256
            or current_learning.problem.problem_sha256
            != workspace.learning_prior.current_problem_sha256
        ):
            raise ValueError("P33 context changed before P34 decision freeze")
        try:
            p33_state = EngineeringLearningRepository(db_path).stream_state()
            p33_head = p33_state.head_sha256
            if p33_state.history_revision != workspace.identity.learning_history_revision:
                raise ValueError("P33 history changed before P34 decision freeze")
        except (sqlite3.Error, OSError, TypeError, ValueError):
            memory_decision = baseline_decision
            transfer_class = "blocked"
            p33_head = None
        (
            problem_family,
            problem_orientation,
            track_class,
            _context_subgroups,
            build_review_state,
            driver_drift_state,
            transfer_class,
            memory_decision,
            future_memory_record_ids,
            negative_control_condition,
        ) = _p34_restart_context(
            workspace,
            current_learning,
            baseline_decision,
            memory_decision,
            transfer_class,
            decision_frozen_at=decision_frozen_at,
        )
        activation = effective_before_restore
        if transfer_class not in {"exact", "compatible"}:
            activation = None
        baseline_policy = baseline_investigation_policy()
        shadow_policy = memory_shadow_investigation_policy()
        limited_policy = limited_attention_investigation_policy()
        memory_policy = limited_policy if activation is not None else shadow_policy
        contradictions = workspace.p19_contradiction_artifact_ids
        eligible_tool_ids = _p34_live_eligible_tool_ids(
            baseline_decision,
            memory_decision,
            completed_tool_ids=folded.completed_tool_ids,
        )
        current_evidence_pinned_tool_ids = tuple(
            tool_id
            for tool_id in _p34_qualified_current_evidence_tool_ids(workspace)
            if tool_id in eligible_tool_ids
        )
        negative_control_evidence = _p34_negative_control_evidence(
            workspace,
            condition=negative_control_condition,
            driver_drift_state=driver_drift_state,
            future_memory_record_ids=future_memory_record_ids,
        )
        (
            qualified_artifact_ids,
            qualified_artifact_states,
            qualified_artifact_provenance_sha256s,
        ) = p34_qualified_current_artifact_cohort(
            workspace.identity,
            workspace.evidence_index,
        )
        pair = build_paired_investigation_decision(
            baseline_policy=baseline_policy,
            memory_policy=memory_policy,
            investigation_id=investigation.investigation_id,
            investigation_opened_at=investigation.opened_at,
            run_id=workspace.identity.run_id,
            session_id=workspace.identity.session_id,
            workspace_revision=workspace.identity.workspace_revision,
            authority_revision=workspace.identity.authority_revision,
            step_number=folded.last_sequence,
            baseline_decision=baseline_decision,
            memory_decision=memory_decision,
            available_tool_ids=tuple(item.tool_id for item in workspace.available_tools),
            eligible_tool_ids=eligible_tool_ids,
            completed_tool_ids=folded.completed_tool_ids,
            available_artifact_ids=tuple(
                item.artifact_id for item in workspace.evidence_index.entries
            ),
            qualified_available_artifact_ids=qualified_artifact_ids,
            qualified_available_artifact_evidence_states=qualified_artifact_states,
            qualified_available_artifact_provenance_sha256s=(
                qualified_artifact_provenance_sha256s
            ),
            current_evidence_pinned_tool_ids=current_evidence_pinned_tool_ids,
            current_truth_sha256=_p34_current_truth_sha256(workspace),
            p19_snapshot_sha256=workspace.identity.reasoning_snapshot_sha256,
            current_p19_cause_ids=workspace.p19_cause_ids,
            current_p19_cause_states=tuple(
                P19CauseState(cause_id=item.cause_id, state=item.status)
                for item in current_learning.reasoning.causes
            ),
            current_contradiction_ids=contradictions,
            strongest_contradiction_id=(contradictions[0] if contradictions else None),
            current_objective=workspace.identity.objective_id.value,
            p33_projection_sha256=workspace.learning_prior.projection_sha256,
            p33_history_revision=workspace.identity.learning_history_revision,
            p33_ledger_head_sha256=p33_head,
            p33_context_sha256=current_learning.context.context_sha256,
            p33_problem_sha256=current_learning.problem.problem_sha256,
            track=current_learning.context.track,
            track_configuration=current_learning.context.track_configuration,
            package_type=current_learning.context.package_type,
            iracing_build=current_learning.context.iracing_build,
            problem_family=problem_family,
            problem_orientation=problem_orientation,
            track_class=track_class,
            phase=current_learning.problem.phase,
            build_review_state=build_review_state,
            driver_drift_state=driver_drift_state,
            decision_frozen_at=decision_frozen_at,
            context_transfer_class=transfer_class,
            negative_control_condition=negative_control_condition,
            negative_control_evidence=negative_control_evidence,
            future_memory_record_ids=future_memory_record_ids,
            p20_projection_sha256=workspace.identity.p20_state_revision,
            p26_projection_sha256=workspace.identity.p26_knowledge_graph_sha256,
            p32_projection_sha256=workspace.identity.p32_projection_sha256,
            activation_decision=activation,
        )
        connection = initialize_database(db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            persist_p34_foundation(repository, connection=connection)
            repository.append_paired_decision_in_transaction(connection, pair)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        with _CACHE_LOCK:
            _CACHE.clear()
        return pair
    except (
        InvestigationAdaptationIntegrityError,
        sqlite3.Error,
        AttributeError,
        OSError,
        TypeError,
        ValueError,
    ):
        # P34 is attention-only. Missing/corrupt adaptation truth cannot veto
        # the deterministic Crew/P19 production path.
        return None


def _production_subgoal_from_pair(
    baseline_subgoal: InvestigationSubgoal | None,
    folded: FoldedInvestigationState | None,
    learning_prior: CrewChiefLearningPrior | None,
    pair: PairedInvestigationDecision | None,
) -> InvestigationSubgoal | None:
    if (
        baseline_subgoal is None
        or pair is None
        or pair.production_decision.decision_kind != "inspect_tool"
        or pair.production_decision.action_id == baseline_subgoal.selected_tool
    ):
        return baseline_subgoal
    shadow, _, _ = _memory_shadow_from_baseline(
        baseline_subgoal,
        folded,
        learning_prior,
        decision_frozen_at=pair.decision_frozen_at,
    )
    if (
        shadow is not None
        and shadow.selected_tool == pair.production_decision.action_id
        and pair.activation_state == "limited_attention"
    ):
        return shadow
    return baseline_subgoal


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
    try:
        learning_state = EngineeringLearningRepository(db_path).stream_state()
        learning_ledger_head_sha256 = (
            learning_state.head_sha256
            if learning_state.history_revision == learning_prior.history_revision
            else None
        )
    except (sqlite3.Error, OSError, TypeError, ValueError):
        learning_ledger_head_sha256 = None
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
        learning_ledger_head_sha256=learning_ledger_head_sha256,
        run_sentinel=run_sentinel,
    )
    stale_reasons = _authority_stale_reasons(investigation, events, identity)
    if folded is not None and stale_reasons:
        folded = folded.model_copy(
            update={"status": "stale", "stale_reason": stale_reasons[0]}
        )
    try:
        p34_ledger_revision = InvestigationAdaptationRepository(
            db_path
        ).stream_state().ledger_revision
    except (InvestigationAdaptationIntegrityError, sqlite3.Error, OSError) as exc:
        p34_ledger_revision = canonical_json_sha256(
            {"state": "blocked", "reason": str(exc)}
        )
    cache_key = (*_workspace_cache_key(identity, db_path), p34_ledger_revision)
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
    p19_cause_ids = tuple(
        cause.cause_id for cause in bundle.report.reasoning_snapshot.causes
    )
    p19_contradiction_artifact_ids = _unique(
        citation.event_id or citation.citation_id
        for cause in sorted(
            bundle.report.reasoning_snapshot.causes,
            key=lambda item: item.ordinal_rank,
        )
        for citation in cause.contradicting_evidence
    )
    workspace_blocker_reasons = _unique(
        [
            *stale_reasons,
            *bundle.report.blocker_reasons,
            *p20.knowledge_debt,
            *p26.knowledge_debt,
            *p32.blockers,
            *learning_prior.blocker_reasons,
        ]
    )
    baseline_subgoal = _subgoal(bundle, folded, p26, p32, learning_prior)
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
    investigation_improvement = _p34_projection_for_identity(
        identity,
        investigation_open=folded is not None and folded.status == "open",
        current_learning=current_learning,
        learning_prior=learning_prior,
        folded=folded,
        baseline_subgoal=baseline_subgoal,
        evidence_index=evidence_index,
        terminal_decision=decision,
        p19_cause_ids=p19_cause_ids,
        p19_contradiction_artifact_ids=p19_contradiction_artifact_ids,
        blocker_reasons=workspace_blocker_reasons,
        db_path=db_path,
    )
    subgoal = _production_subgoal_from_pair(
        baseline_subgoal,
        folded,
        learning_prior,
        investigation_improvement.current_pair,
    )
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
        investigation_improvement=investigation_improvement,
        run_sentinel=run_sentinel,
        terminal_decision=decision,
        response_history_ids=response_ids,
        driver_memory_ids=driver_memory_ids,
        p19_cause_ids=p19_cause_ids,
        p19_contradiction_artifact_ids=p19_contradiction_artifact_ids,
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
        blocker_reasons=workspace_blocker_reasons,
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
    *,
    prediction_pair: PairedInvestigationDecision | None = None,
    prediction_source_snapshot_sha256: str | None = None,
) -> CrewChiefEvent:
    if prediction_pair is not None:
        if prediction_source_snapshot_sha256 is None:
            raise ValueError(
                "P34 executable prediction requires its producer-owned source snapshot"
            )
        payload = payload.model_copy(
            update={
                "adaptation_prediction_pair_id": prediction_pair.pair_id,
                "adaptation_prediction_pair_sha256": prediction_pair.pair_sha256,
                "adaptation_prediction_source_snapshot_sha256": (
                    prediction_source_snapshot_sha256
                ),
            }
        )
    created_at = _now()
    if (
        prediction_pair is not None
        and created_at <= prediction_pair.decision_frozen_at
    ):
        created_at = prediction_pair.decision_frozen_at + timedelta(microseconds=1)
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


def _freeze_next_p34_pair_and_refresh(
    workspace: CrewChiefWorkspace,
    *,
    db_path: str | Path | None,
) -> CrewChiefWorkspace:
    if (
        workspace.folded_state is not None
        and workspace.folded_state.pending_driver_question_id is not None
    ):
        # Asking was the executable planner decision. The answer is its
        # outcome, so freezing here would backfill a second ask-driver pair
        # after the question was already exposed.
        return workspace
    if _freeze_p34_pair_for_workspace(workspace, db_path=db_path) is None:
        return workspace
    return build_crew_chief_workspace(
        workspace.identity.run_id,
        session_id=workspace.identity.session_id,
        objective=workspace.identity.objective_id,
        investigation_id=workspace.identity.investigation_id,
        db_path=db_path,
    )


def _canonical_p34_outcome_pair(
    investigation_id: str,
    *,
    db_path: str | Path | None,
) -> PairedInvestigationDecision | None:
    """Select the preregistered investigation-level pair without outcome access.

    Persistence sequence is authoritative.  Prefer the earliest inspect-tool
    revision where executable baseline and memory choices differ, then the
    earliest inspect-tool revision, then the earliest eligible non-tool pair.
    Later results can never replace this selection.
    """

    pairs = _ordered_p34_investigation_pairs(
        investigation_id,
        db_path=db_path,
    )
    if not pairs:
        return None
    return _select_canonical_p34_pair(pairs)


def _select_canonical_p34_pair(
    pairs: tuple[PairedInvestigationDecision, ...],
) -> PairedInvestigationDecision:
    persistence_order = {pair.pair_id: index for index, pair in enumerate(pairs)}

    def category(pair: PairedInvestigationDecision) -> int:
        both_tools = (
            pair.baseline_decision.decision_kind == "inspect_tool"
            and pair.memory_decision.decision_kind == "inspect_tool"
        )
        if both_tools and (
            pair.baseline_decision.executable_identity
            != pair.memory_decision.executable_identity
        ):
            return 0
        return 1 if both_tools else 2

    return min(
        pairs,
        key=lambda pair: (
            category(pair),
            pair.step_number,
            persistence_order[pair.pair_id],
            pair.pair_id,
        ),
    )


def _ordered_p34_investigation_pairs(
    investigation_id: str,
    *,
    db_path: str | Path | None,
) -> tuple[PairedInvestigationDecision, ...]:
    repository = InvestigationAdaptationRepository(db_path)
    try:
        result = repository.query_records(
            record_kinds=("paired_decision",),
            investigation_id=investigation_id,
            limit=10_000,
        )
        if result.blockers:
            raise InvestigationAdaptationIntegrityError(result.blockers[0])
        return tuple(
            reversed(
                tuple(
                    item
                    for item in result.records
                    if isinstance(item, PairedInvestigationDecision)
                )
            )
        )
    except (
        InvestigationAdaptationIntegrityError,
        sqlite3.Error,
        AttributeError,
        OSError,
        TypeError,
        ValueError,
    ):
        return ()


def _build_p34_outcome_certificate(
    workspace: CrewChiefWorkspace,
    *,
    investigation: CrewChiefInvestigation,
    terminal_events: tuple[CrewChiefEvent, ...],
    terminal_event: CrewChiefEvent,
    experience: EngineeringExperienceRecord,
    pair: PairedInvestigationDecision | None,
) -> InvestigationOutcomeCertificate | None:
    if pair is None:
        return None
    fact = experience.investigation_outcome
    if fact is None:
        return None
    requests = tuple(
        event
        for event in terminal_events
        if event.event_type == "tool_invoked" and event.payload.tool_id is not None
    )
    results = tuple(
        event
        for event in terminal_events
        if event.event_type == "tool_result_attached"
        and event.payload.tool_id is not None
    )
    result_artifact_ids = {
        artifact_id for event in results for artifact_id in event.payload.artifact_ids
    }
    qualified_current_ids = set(
        p34_qualified_current_artifact_ids(
            getattr(workspace, "identity", investigation.workspace_identity),
            workspace.evidence_index,
        )
    )
    qualified_entries = tuple(
        item
        for item in workspace.evidence_index.entries
        if item.artifact_id in result_artifact_ids
        and item.artifact_id in qualified_current_ids
    )
    qualified_artifact_ids = tuple(item.artifact_id for item in qualified_entries)
    strongest = pair.strongest_contradiction_id
    blockers: list[str] = []
    if pair.investigation_id != investigation.investigation_id:
        blockers.append(
            "The terminal outcome does not match its frozen pre-outcome P34 pair."
        )
    if workspace.learning_prior.state == "blocked":
        blockers.append("P33 provenance was blocked at terminal certification.")
    if pair.decision_frozen_at >= terminal_event.created_at:
        blockers.append("The P34 decision was not frozen before terminal exposure.")
    terminal_kind = (
        "abandoned"
        if terminal_event.event_type == "investigation_abandoned"
        else workspace.terminal_decision.kind
    )
    p19_outcome = (
        "no_call"
        if terminal_kind == "no_call"
        else "blocked"
        if terminal_kind in {"observe_only", "blocked", "stale"}
        and not workspace.critique.passed
        else None
    )
    dead_end_tool_ids = _unique(
        dead_end.tool_id
        for dead_end in experience.dead_ends
        if dead_end.tool_id is not None
        and dead_end.tool_id in {event.payload.tool_id for event in results}
    )
    qualified_result_tools = {
        event.payload.tool_id
        for event in results
        if event.payload.tool_id is not None
        and set(event.payload.artifact_ids).intersection(qualified_artifact_ids)
    }
    completed_checks = [
        "workspace_identity",
        "vehicle_condition_epoch",
        "applied_control_state",
    ]
    if "inspect_data_quality" in qualified_result_tools:
        completed_checks.extend(("data_integrity", "telemetry_health"))
    if "inspect_lap_context" in qualified_result_tools:
        completed_checks.extend(("context_comparability", "traffic_contamination"))
    if strongest is None or strongest in qualified_artifact_ids:
        completed_checks.append("strongest_contradiction")
    if "inspect_driver_vehicle_separation" in qualified_result_tools:
        completed_checks.append("driver_car_separation")
    return build_investigation_outcome_certificate(
        pair,
        starting_workspace_revision=(
            investigation.workspace_identity.workspace_revision
        ),
        ending_workspace_revision=terminal_event.workspace_revision,
        final_p19_snapshot_sha256=(
            experience.closing_reasoning.reasoning_snapshot_sha256
        ),
        terminal_crew_decision=terminal_kind,
        tool_request_event_ids=tuple(event.event_id for event in requests),
        tool_result_event_ids=tuple(event.event_id for event in results),
        tools_actually_requested=tuple(event.payload.tool_id for event in requests),
        tool_results_received=tuple(event.payload.tool_id for event in results),
        qualified_artifact_ids=qualified_artifact_ids,
        qualified_artifact_evidence_states=tuple(
            item.evidence_state.value for item in qualified_entries
        ),
        driver_question_ids=tuple(
            event.payload.question_id
            for event in terminal_events
            if event.event_type == "driver_question_asked"
            and event.payload.question_id is not None
        ),
        driver_answer_event_ids=tuple(
            event.event_id
            for event in terminal_events
            if event.event_type == "driver_answer_recorded"
        ),
        consumption_metrics_state="unavailable",
        lap_ids_consumed=None,
        measurement_mission_ids=None,
        consumption_metric_blockers=(
            "Post-open lap and completed measurement-mission consumption lineage is unavailable.",
        ),
        elapsed_wall_seconds=fact.elapsed_seconds,
        investigation_steps=terminal_event.sequence,
        useful_discriminator_id=(
            fact.successful_discriminator_ids[0]
            if fact.successful_discriminator_ids
            else None
        ),
        dead_end_tool_ids=dead_end_tool_ids,
        causes_separated=fact.eliminated_cause_ids,
        causes_left_unresolved=fact.unresolved_cause_ids,
        final_p19_cause_states=tuple(
            P19CauseState(cause_id=item.cause_id, state=item.status)
            for item in experience.closing_reasoning.causes
        ),
        strongest_contradiction_id=strongest,
        strongest_contradiction_handled=(
            strongest is not None and strongest in qualified_artifact_ids
        ),
        completed_mandatory_check_ids=_unique(completed_checks),
        created_workflow_ids=fact.workflow_ids,
        workflow_created=bool(fact.workflow_ids),
        workflow_scored=False,
        p19_outcome=p19_outcome,
        outcome_validity="blocked" if blockers else "qualified",
        prospective=investigation.opened_at > p34_activation_protocol().prospective_boundary,
        synthetic=False,
        blockers=tuple(blockers),
        certified_at=terminal_event.created_at,
    )


def _build_p34_discriminator_outcome(
    pairs: tuple[PairedInvestigationDecision, ...],
    certificate: InvestigationOutcomeCertificate | None,
    *,
    terminal_events: tuple[CrewChiefEvent, ...],
    evaluated_at: datetime,
) -> DiscriminatorOutcome | None:
    """Build one exact preregistered A->B observation, or withhold it.

    The canonical pair predicts the memory inspection before any result is
    visible.  A later source pair must then bind the exact workspace immediately
    before Crew actually requests that inspection.  Ambiguous or rebased event
    lineage is deliberately unobservable rather than inferred.
    """

    if not pairs or certificate is None or certificate.useful_discriminator_id is None:
        return None
    prediction_pair = _select_canonical_p34_pair(pairs)
    tool_id = certificate.useful_discriminator_id
    if (
        prediction_pair.baseline_decision.executable_identity
        == prediction_pair.memory_decision.executable_identity
        or prediction_pair.memory_decision.decision_kind != "inspect_tool"
        or prediction_pair.memory_decision.action_id != tool_id
    ):
        return None
    requests = tuple(
        event
        for event in terminal_events
        if event.event_type == "tool_invoked" and event.payload.tool_id == tool_id
    )
    results = tuple(
        event
        for event in terminal_events
        if event.event_type == "tool_result_attached"
        and event.payload.tool_id == tool_id
    )
    if len(requests) != 1 or len(results) != 1:
        return None
    request = requests[0]
    result = results[0]
    source_pairs = tuple(
        pair
        for pair in pairs
        if pair.pair_id == request.payload.adaptation_prediction_pair_id
        and pair.pair_sha256
        == request.payload.adaptation_prediction_pair_sha256
        and pair.workspace_revision == request.workspace_revision
        and pair.step_number + 1 == request.sequence
        and pair.decision_frozen_at < request.created_at
        and pair.baseline_decision.decision_kind == "inspect_tool"
        and pair.baseline_decision.action_id == tool_id
    )
    if len(source_pairs) != 1:
        return None
    try:
        return build_discriminator_outcome_from_crew_events(
            prediction_pair=prediction_pair,
            source_pair=source_pairs[0],
            certificate=certificate,
            request_event=request,
            result_event=result,
            investigation_events=terminal_events,
            transition_sequence=max(event.sequence for event in terminal_events),
            evaluated_at=evaluated_at,
        )
    except (TypeError, ValueError):
        # P34 credit is optional attention-only evidence.  Missing or ambiguous
        # lineage cannot veto terminal Crew/P33 truth and is never inferred.
        return None


def _build_p34_completed_comparison(
    pairs: tuple[PairedInvestigationDecision, ...],
    certificate: InvestigationOutcomeCertificate | None,
    *,
    discriminator_outcome: DiscriminatorOutcome | None = None,
    compared_at: datetime,
) -> PairedInvestigationComparison | None:
    if not pairs or certificate is None:
        return None
    try:
        return build_paired_investigation_comparison(
            investigation_pairs=pairs,
            certificate=certificate,
            discriminator_outcome=discriminator_outcome,
            compared_at=compared_at,
        )
    except (TypeError, ValueError):
        # P34 remains attention-only; an invalid comparison cannot veto the
        # authoritative Crew terminal event or P33 experience capture.
        return None


def _review_p34_terminal_capture(
    captured_event: CrewChiefEvent,
    *,
    db_path: str | Path | None,
) -> None:
    """Review activation only after authoritative terminal truth has committed."""

    if captured_event.payload.adaptation_capture_state != "captured":
        return
    try:
        review_p34_after_terminal_capture(
            InvestigationAdaptationRepository(db_path),
            captured_at=captured_event.created_at,
        )
    except Exception:
        # The Crew/P33/P34 outcome transaction is already authoritative.  A
        # review failure is attention-only and must never turn that success
        # into an apparent terminal-mutation failure.
        return
    with _CACHE_LOCK:
        _CACHE.clear()


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
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    return _freeze_next_p34_pair_and_refresh(updated, db_path=db_path)


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
    frozen_pair = _freeze_p34_pair_for_workspace(current, db_path=db_path)
    repository = CrewChiefRepository(db_path)
    sequence = current.folded_state.last_sequence + 1
    production_subgoal = _production_subgoal_from_pair(
        current.current_subgoal,
        current.folded_state,
        getattr(current, "learning_prior", None),
        frozen_pair,
    )
    if production_subgoal is not None:
        subgoal = production_subgoal
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
            prediction_pair=frozen_pair,
            prediction_source_snapshot_sha256=(
                _p34_source_snapshot_sha256(current)
                if frozen_pair is not None
                else None
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
                prediction_pair=frozen_pair,
                prediction_source_snapshot_sha256=(
                    _p34_source_snapshot_sha256(current)
                    if frozen_pair is not None
                    else None
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
            prediction_pair=frozen_pair,
            prediction_source_snapshot_sha256=(
                _p34_source_snapshot_sha256(current)
                if frozen_pair is not None
                else None
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
        outcome_pairs = _ordered_p34_investigation_pairs(
            investigation_id,
            db_path=db_path,
        )
        outcome_pair = (
            _select_canonical_p34_pair(outcome_pairs) if outcome_pairs else None
        )
        outcome_certificate = _build_p34_outcome_certificate(
            current,
            investigation=investigation,
            terminal_events=terminal_events,
            terminal_event=terminal_event,
            experience=experience,
            pair=outcome_pair,
        )
        discriminator_outcome = _build_p34_discriminator_outcome(
            outcome_pairs,
            outcome_certificate,
            terminal_events=terminal_events,
            evaluated_at=terminal_event.created_at,
        )
        outcome_comparison = _build_p34_completed_comparison(
            outcome_pairs,
            outcome_certificate,
            discriminator_outcome=discriminator_outcome,
            compared_at=terminal_event.created_at,
        )
        captured_event = repository.append_terminal_event_and_experience(
            terminal_event,
            experience,
            outcome_certificate=outcome_certificate,
            outcome_comparison=outcome_comparison,
            discriminator_outcome=discriminator_outcome,
        )
        _review_p34_terminal_capture(captured_event, db_path=db_path)
        clear_learning_cache()
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    return _freeze_next_p34_pair_and_refresh(updated, db_path=db_path)


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
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    return _freeze_next_p34_pair_and_refresh(updated, db_path=db_path)


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
    outcome_pairs = _ordered_p34_investigation_pairs(
        investigation_id,
        db_path=db_path,
    )
    outcome_pair = _select_canonical_p34_pair(outcome_pairs) if outcome_pairs else None
    outcome_certificate = _build_p34_outcome_certificate(
        current,
        investigation=investigation,
        terminal_events=terminal_events,
        terminal_event=terminal_event,
        experience=experience,
        pair=outcome_pair,
    )
    discriminator_outcome = _build_p34_discriminator_outcome(
        outcome_pairs,
        outcome_certificate,
        terminal_events=terminal_events,
        evaluated_at=terminal_event.created_at,
    )
    outcome_comparison = _build_p34_completed_comparison(
        outcome_pairs,
        outcome_certificate,
        discriminator_outcome=discriminator_outcome,
        compared_at=terminal_event.created_at,
    )
    captured_event = repository.append_terminal_event_and_experience(
        terminal_event,
        experience,
        outcome_certificate=outcome_certificate,
        outcome_comparison=outcome_comparison,
        discriminator_outcome=discriminator_outcome,
    )
    _review_p34_terminal_capture(captured_event, db_path=db_path)
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
    return _freeze_next_p34_pair_and_refresh(updated, db_path=db_path)


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
            return _freeze_next_p34_pair_and_refresh(current, db_path=db_path)
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
                adaptation_rebase_source_snapshot_sha256=(
                    _p34_source_snapshot_sha256(
                        current,
                        workspace_revision=current.identity.workspace_revision,
                    )
                ),
            ),
        )
    )
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    return _freeze_next_p34_pair_and_refresh(updated, db_path=db_path)


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
