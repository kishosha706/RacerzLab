"""Deterministic P27-P29 Crew Chief executive.

This layer schedules inspection and presents one atomic workspace.  It never
recomputes P19 setup or policy authority and never analyzes raw telemetry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterable, Literal

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    CrewChiefCritique,
    CrewChiefEffectivenessRecord,
    CrewChiefEvent,
    CrewChiefEventPayload,
    CrewChiefInvestigation,
    CrewChiefTerminalDecision,
    CrewChiefToolDefinition,
    CrewChiefToolResult,
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
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.services.engineering_projection_service import (
    project_engineering_awareness,
)
from racelab_engine.services.run_intelligence_service import (
    RunIntelligenceBundle,
    build_run_intelligence,
)
from racelab_engine.services.import_service import read_telemetry_manifest
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
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


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
            exclude={"objective_id", "investigation_id", "workspace_revision"},
        )
    )


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
    repository: RaceLabRepository | None = None,
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
        source_setup_hash = canonical_json_sha256(source_setup) if source_setup is not None else None
        try:
            manifest = read_telemetry_manifest(source_run_id)
            build_hash = canonical_json_sha256({
                "compatibility_identity": manifest.get("compatibility_identity"),
                "compatibility_fingerprint": manifest.get("compatibility_fingerprint"),
                "source_file_sha256": manifest.get("source_file_sha256"),
                "cache_version": manifest.get("cache_version"),
            })
        except (OSError, TypeError, ValueError):
            build_hash = None
        source_identity[source_run_id] = (source_setup_id, source_setup_hash, build_hash)
    for cause in report.reasoning_snapshot.causes:
        mechanisms = _mechanisms(cause.mechanism_keys)
        component_ids = by_cause.get(cause.cause_id, ())
        for citation, polarity in (
            *((item, "support") for item in cause.supporting_evidence),
            *((item, "contradiction") for item in cause.contradicting_evidence),
        ):
            artifact_id = citation.event_id or citation.citation_id
            source_setup_id, source_setup_hash, source_build_hash = source_identity[citation.run_id]
            provenance_available = all((source_setup_id, source_setup_hash, source_build_hash))
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
                tuple(item.value for item in current.mechanism_ids)
                if current
                else ()
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
                    *(("source identity unavailable",) if not provenance_available else ()),
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
                source_session_id=identity.session_id if citation.run_id in source_run_ids else None,
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
                source_setup_sha256=(identity.setup_snapshot_sha256 if episode.setup_id == identity.setup_id else None),
                source_build_context_sha256=(identity.vehicle_runtime_identity_hash if episode.setup_id == identity.setup_id else None),
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
                blocker_reasons=_unique((*episode.context_blockers, *(("source identity unavailable",) if episode.setup_id != identity.setup_id else ()))),
                authority_ceiling="observation_only",
            ),
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
    for expected, event in enumerate(events, start=1):
        if (
            event.sequence != expected
            or event.investigation_id != investigation.investigation_id
        ):
            raise ValueError("Crew Chief event fold encountered non-canonical history")
        payload = event.payload
        if event.event_type == "tool_result_attached" and payload.tool_id:
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
) -> InvestigationSubgoal | None:
    if folded is None or folded.status != "open":
        return None
    causes = bundle.report.reasoning_snapshot.causes
    if not causes:
        return None
    completed = set(folded.completed_tool_ids)
    unresolved = tuple(
        cause for cause in causes
        if cause.status != "ruled_out"
        and next(
            (item.progress for item in folded.hypotheses if item.cause_id == cause.cause_id),
            InvestigationProgress.INSPECTION_PENDING,
        ) != InvestigationProgress.INSPECTED
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
    if bundle.report.data_quality.status != "ready" or "inspect_data_quality" not in completed:
        priorities.append("inspect_data_quality")
    if has_context_debt or "inspect_lap_context" not in completed:
        priorities.append("inspect_lap_context")
    # Ask the driver after objective evidence integrity and context have been
    # inspected.  Their answer can then change the next physical inspection.
    if not folded.driver_answers and {
        "inspect_data_quality", "inspect_lap_context"
    }.issubset(completed):
        return None
    answer = folded.driver_answers[-1] if folded.driver_answers else None
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
    if p26.leading_component_ids:
        priorities.append("inspect_component_state")
    if has_history:
        priorities.append("inspect_controlled_history")
    priorities.append("inspect_measurement_debt")
    tool = next((item for item in priorities if item not in completed), None)
    if tool is None:
        return None
    contradiction_first = sorted(
        unresolved,
        key=lambda cause: (not bool(cause.contradicting_evidence), cause.ordinal_rank),
    )
    leading = tuple(cause.cause_id for cause in contradiction_first)
    answer_scope = f" Driver context scopes this inspection to {answer}." if answer else ""
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
    if tool_id == "inspect_data_quality":
        selected = tuple(item for item in entries if item.blocker_reasons)
    elif tool_id == "inspect_lap_context":
        selected = tuple(
            item for item in entries
            if item.producer_id == "p19.reasoning_snapshot"
            and (item.blocker_reasons or item.evidence_state == EvidenceState.BLOCKED_BY_CONTEXT)
        )
    elif tool_id == "inspect_driver_execution":
        phase = {
            "braking/entry": ("brak", "entry", "turn"),
            "center": ("center", "apex", "corner"),
            "exit/power": ("exit", "throttle", "power"),
        }.get(answer or "", ())
        selected = tuple(
            item for item in entries
            if item.producer_id == "p19.reasoning_snapshot"
            and (not phase or any(token in (item.phase or "").casefold() for token in phase))
        )
    elif tool_id == "inspect_p19_causes":
        selected = tuple(
            item for item in entries
            if item.producer_id == "p19.reasoning_snapshot"
            and (not cause_ids or item.polarity == "contradiction" or item.component_ids)
        )
    elif tool_id == "inspect_mechanism_episodes":
        selected = tuple(item for item in entries if item.producer_id == "p20.mechanism_episode")
    elif tool_id == "inspect_component_state":
        selected = tuple(item for item in entries if item.component_ids)
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
    bundle: RunIntelligenceBundle, overview: object, workflow: object | None = None
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
    preflight = (
        report.smart_guidance.test_preflight if report.smart_guidance else None
    )
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
    accepted = 0
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
        if reasons:
            decisions.append(
                RunSentinelLap(
                    lap_number=lap.lap_number,
                    status="rejected",
                    reasons=_unique(reasons),
                )
            )
        else:
            accepted += 1
            decisions.append(
                RunSentinelLap(
                    lap_number=lap.lap_number,
                    status="accepted",
                    accepted_ordinal=accepted,
                )
            )
    waiting_for_score = bool(
        workflow is not None
        and getattr(workflow, "status", None) == "active"
        and all(getattr(workflow, "stage_run_ids", {}).get(item) for item in ("A", "B", "A2"))
    )
    collection_complete = required is not None and accepted >= required
    if plan_kind == "blocked":
        mission_state = "blocked_by_p19"
        stage = "blocked"
        required = None
        collection_complete = False
    elif plan_kind == "stop_testing":
        mission_state = "stopped_by_p19"
        stage = "stopped"
        required = None
        collection_complete = False
    elif waiting_for_score:
        mission_state = "awaiting_p19_score"
        stage = "awaiting_score"
        collection_complete = False
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
        accepted_laps=accepted,
        collection_complete=collection_complete,
        stage=stage,
        laps=tuple(decisions),
        blocker_reasons=_unique(
            [
                *mission_scope_reasons,
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
    runtime = vehicle_systems_runtime_identity(run_id)
    p26 = build_component_awareness(
        bundle.report,
        setup_snapshot=overview.setup_snapshot,
        runtime_identity=runtime,
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
        raise ValueError("Crew Chief active workflow integrity could not be verified.") from exc
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
    identity = _workspace_identity(
        bundle,
        session_id=session_id,
        scope_run_ids=tuple(session.run_ids),
        objective=objective,
        investigation_id=investigation.investigation_id if investigation else None,
        event_hashes=tuple(event.event_hash for event in events),
        p20=p20,
        p26=p26,
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
    evidence_index = _evidence_index(bundle, identity, objective, p26, storage_repository)
    subgoal = _subgoal(bundle, folded, p26)
    latest_result = None
    if folded and folded.completed_tool_ids:
        latest = folded.completed_tool_ids[-1]
        definition = next(item for item in _TOOLS if item.tool_id == latest)
        latest_event = next(
            (
                event for event in reversed(events)
                if event.event_type == "tool_result_attached"
                and event.payload.tool_id == latest
            ),
            None,
        )
        artifact_ids = latest_event.payload.artifact_ids if latest_event else ()
        cause_ids = latest_event.payload.cause_ids if latest_event else ()
        component_ids = latest_event.payload.component_ids if latest_event else ()
        latest_result = CrewChiefToolResult(
            tool_id=latest,
            workspace_revision=identity.workspace_revision,
            status="complete" if artifact_ids else "no_finding",
            summary=(
                latest_event.payload.findings[0]
                if latest_event and latest_event.payload.findings
                else "No tool-specific canonical artifact matched this exact workspace."
            ),
            artifact_ids=artifact_ids,
            cause_ids=cause_ids,
            component_ids=component_ids,
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
        run_sentinel=_sentinel(bundle, overview, active_workflow),
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
            f"{len(evidence_index.entries)} evidence artifacts indexed without raw traces.",
            f"Next move: {decision.title}",
        ),
        blocker_reasons=_unique(
            [
                *stale_reasons,
                *bundle.report.blocker_reasons,
                *p20.knowledge_debt,
                *p26.knowledge_debt,
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


def _save_terminal_operational_facts(
    workspace: CrewChiefWorkspace,
    repository: CrewChiefRepository,
    *,
    resolution: Literal["decision_emitted", "abandoned"],
) -> None:
    investigation = workspace.investigation
    if investigation is None or workspace.folded_state is None:
        raise ValueError("terminal Crew Chief facts require an exact investigation")
    events = repository.list_events(investigation.investigation_id)
    if not events:
        raise ValueError("terminal Crew Chief facts require immutable event history")
    resolved_at = events[-1].created_at
    elapsed = max(0.0, (resolved_at - investigation.opened_at).total_seconds())
    scored = tuple(workspace.response_history_ids)
    repository.save_effectiveness(CrewChiefEffectivenessRecord(
        record_id=f"cceff_{canonical_json_sha256([investigation.investigation_id, events[-1].event_hash])[:24]}",
        investigation_id=investigation.investigation_id,
        workspace_revision=workspace.identity.workspace_revision,
        recorded_at=resolved_at,
        opened_at=investigation.opened_at,
        resolved_at=resolved_at,
        elapsed_seconds=elapsed,
        interaction_count=len(events),
        questions_asked=sum(event.event_type == "driver_question_asked" for event in events),
        questions_answered=sum(event.event_type == "driver_answer_recorded" for event in events),
        inspections_performed=sum(event.event_type == "tool_result_attached" for event in events),
        collection_complete=workspace.run_sentinel.collection_complete,
        linked_workflow_ids=tuple(dict.fromkeys((
            *scored,
            *((workspace.terminal_decision.workflow_id,) if workspace.terminal_decision.workflow_id else ()),
        ))),
        scored_workflow_ids=scored,
        resolution=resolution,
        measurement_missions_completed=int(
            workspace.run_sentinel.collection_complete
            and workspace.run_sentinel.p19_plan_kind in {"measurement_mission", "discriminator"}
        ),
        controlled_tests_completed=len(scored),
        rejected_laps=sum(item.status == "rejected" for item in workspace.run_sentinel.laps),
        prior_undo_policies_blocked=0,
        countereffects_caught=0,
        terminal_decision_kind=workspace.terminal_decision.kind,
    ))


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
    investigation_id = f"cci_{canonical_json_sha256([run_id, session_id, normalized, current.identity.workspace_revision])[:24]}"
    investigation = CrewChiefInvestigation(
        investigation_id=investigation_id,
        workspace_identity=current.identity,
        origin=origin,
        objective=objective,
        raw_driver_report=normalized,
        canonical_problem=normalized.casefold(),
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
    terminal_resolution: Literal["decision_emitted"] | None = None
    if current.current_subgoal is not None:
        subgoal = current.current_subgoal
        selected = _select_tool_entries(
            current, subgoal.selected_tool, subgoal.distinguishes_cause_ids
        )
        component_ids = _unique(
            component_id for item in selected for component_id in item.component_ids
        )
        repository.append_event(
            _event(
                investigation_id,
                sequence,
                current.identity.workspace_revision,
                "tool_result_attached",
                CrewChiefEventPayload(
                    message=f"Inspected {subgoal.selected_tool}.",
                    tool_id=subgoal.selected_tool,
                    cause_ids=subgoal.distinguishes_cause_ids,
                    artifact_ids=tuple(item.artifact_id for item in selected),
                    component_ids=component_ids,
                    findings=(
                        (
                            f"{len(selected)} tool-specific canonical artifacts attached; "
                            "authority ceiling preserved."
                        ),
                    ),
                ),
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
        repository.append_event(
            _event(
                investigation_id,
                sequence,
                current.identity.workspace_revision,
                "decision_emitted",
                CrewChiefEventPayload(
                    message=current.terminal_decision.instruction,
                    decision_kind=current.terminal_decision.kind,
                    cause_ids=current.p19_cause_ids[:1],
                    artifact_ids=current.terminal_decision.source_event_ids,
                ),
            )
        )
        terminal_resolution = "decision_emitted"
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    if terminal_resolution is not None:
        _save_terminal_operational_facts(
            updated, repository, resolution=terminal_resolution
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
    repository.append_event(
        _event(
            investigation_id,
            sequence,
            current.identity.workspace_revision,
            "investigation_abandoned",
            CrewChiefEventPayload(
                message=" ".join(reason.split()) or "Abandoned by driver."
            ),
        )
    )
    updated = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )
    _save_terminal_operational_facts(updated, repository, resolution="abandoned")
    return updated


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
        raise ValueError("Crew Chief investigation cannot be rebased in its current state.")
    if current.folded_state.status == "open":
        if current.identity.workspace_revision == stale_workspace_revision:
            return current
        raise ValueError("Crew Chief rebase revision is stale.")
    events = CrewChiefRepository(db_path).list_events(investigation_id)
    accepted_workspace = _accepted_workspace_revision(
        current.investigation, events
    )
    if stale_workspace_revision != accepted_workspace:
        raise ValueError("Crew Chief rebase revision is stale.")
    accepted_authority = _accepted_authority_revision(
        current.investigation, events
    )
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
