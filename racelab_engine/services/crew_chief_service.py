"""Deterministic P27-P29 Crew Chief executive.

This layer schedules inspection and presents one atomic workspace.  It never
recomputes P19 setup or policy authority and never analyzes raw telemetry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Iterable

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import (
    ComponentResponseRecord,
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
from racelab_engine.services.session_service import get_session
from racelab_engine.services.vehicle_systems_service import (
    build_component_awareness,
    vehicle_systems_runtime_identity,
)
from racelab_engine.storage.crew_chief_repository import (
    CrewChiefRepository,
    crew_chief_event_hash,
)
from racelab_engine.storage.repository import RaceLabRepository


_CACHE_LOCK = RLock()
_CACHE: dict[str, CrewChiefWorkspace] = {}
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
) -> EngineeringEvidenceIndex:
    report = bundle.report
    by_cause, states = _component_map(p26)
    entries: dict[str, EngineeringEvidenceIndexEntry] = {}
    for cause in report.reasoning_snapshot.causes:
        mechanisms = _mechanisms(cause.mechanism_keys)
        component_ids = by_cause.get(cause.cause_id, ())
        for citation, polarity in (
            *((item, "support") for item in cause.supporting_evidence),
            *((item, "contradiction") for item in cause.contradicting_evidence),
        ):
            artifact_id = citation.event_id or citation.citation_id
            current = entries.get(artifact_id)
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
            entries[artifact_id] = EngineeringEvidenceIndexEntry(
                artifact_id=artifact_id,
                producer_id="p19.reasoning_snapshot",
                run_id=citation.run_id,
                session_id=identity.session_id,
                setup_id=identity.setup_id,
                lap_numbers=(
                    () if citation.lap_number is None else (citation.lap_number,)
                ),
                lap_pct_start=citation.lap_pct_start,
                lap_pct_end=citation.lap_pct_end,
                phase=citation.phase,
                mechanism_ids=_mechanisms(merged_mechanisms),
                component_ids=merged_components,
                control_keys=cause.related_control_keys,
                objective=objective,
                source_channels=citation.channels,
                evidence_state=citation.evidence_state,
                polarity=polarity
                if current is None or current.polarity == polarity
                else "neutral",
                blocker_reasons=()
                if citation.valid_for_tuning
                else ("not qualified for tuning",),
                authority_ceiling="measurement_only"
                if citation.valid_for_tuning
                else "observation_only",
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
                blocker_reasons=episode.context_blockers,
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
            stale_reason = payload.message
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
    )


def _subgoal(
    bundle: RunIntelligenceBundle, folded: FoldedInvestigationState | None
) -> InvestigationSubgoal | None:
    if folded is None or folded.status != "open":
        return None
    causes = bundle.report.reasoning_snapshot.causes
    if not causes:
        return None
    completed = set(folded.completed_tool_ids)
    tool = next(
        (item.tool_id for item in _TOOLS if item.tool_id not in completed), None
    )
    if tool is None:
        return None
    leading = tuple(cause.cause_id for cause in causes[:2])
    return InvestigationSubgoal(
        subgoal_id=f"ccs_{canonical_json_sha256([folded.investigation_id, tool])[:20]}",
        title=f"Inspect {tool.replace('_', ' ')}",
        selected_tool=tool,
        why_this_tool="It resolves the highest-ranked remaining evidence distinction without creating setup authority.",
        distinguishes_cause_ids=leading,
        required_evidence=("exact run", "eligible laps", "producer-owned artifact"),
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
        or folded.pending_driver_question_id is None
    ):
        return None
    competing = tuple(cause.cause_id for cause in causes[:2])
    return DriverDiagnosticQuestion(
        question_id=folded.pending_driver_question_id,
        workspace_revision=identity.workspace_revision,
        question="Where does the handling issue first become clear?",
        answer_options=("braking/entry", "center", "exit/power", "not repeatable"),
        distinguishes_cause_ids=competing,
        reason="The answer scopes the next inspection only; telemetry remains the evidence.",
    )


def _success_contract(
    bundle: RunIntelligenceBundle,
    identity: CrewChiefWorkspaceIdentity,
    objective: EngineeringObjective,
) -> SuccessContract:
    plan = bundle.report.best_measurement
    mission = plan.measurement_mission
    card = plan.controlled_test
    required = (
        mission.required_laps_or_passes
        if mission is not None
        else max(stage.required_flying_laps for stage in card.stages)
        if card is not None
        else 3
    )
    target = (
        mission.target_phase
        if mission is not None
        else card.target_phase
        if card
        else "qualified scope"
    )
    threshold = (
        "; ".join(mission.acceptance_thresholds)
        if mission is not None
        else "; ".join(card.success_metrics)
        if card is not None
        else bundle.report.briefing.success_check
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


def _sentinel(bundle: RunIntelligenceBundle, overview: object) -> RunSentinelState:
    report = bundle.report
    plan = report.best_measurement
    mission = plan.measurement_mission
    card = plan.controlled_test
    required = mission.required_laps_or_passes if mission else 3
    stage = "measurement"
    hold = (
        mission.controlled_variables
        if mission
        else card.do_not_change
        if card
        else ("setup",)
    )
    watch = (
        mission.acceptance_thresholds
        if mission
        else card.success_metrics
        if card
        else (report.briefing.success_check,)
    )
    stop = (
        mission.stop_rule
        if mission
        else card.stop_rule
        if card
        else "Stop on integrity failure.",
    )
    if identity := _active_workflow_identity(bundle)[0]:
        del identity
        move = (
            report.smart_guidance.next_trustworthy_move
            if report.smart_guidance
            else None
        )
        stage = "B" if move and move.kind == "controlled_test" else "A"
        if card:
            selected = next(
                (item for item in card.stages if item.stage == stage), card.stages[0]
            )
            required = selected.required_flying_laps
    eligible = set(report.data_quality.eligible_lap_ids)
    context_by_lap = {
        item.lap_number: item
        for item in (report.lap_context.contexts if report.lap_context else ())
    }
    decisions: list[RunSentinelLap] = []
    accepted = 0
    for lap in sorted(overview.laps, key=lambda item: item.lap_number):
        reasons: list[str] = []
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
    complete = accepted >= required
    return RunSentinelState(
        mission=plan.title,
        need=plan.instruction,
        hold_constant=hold,
        watch=watch,
        success=report.briefing.success_check,
        stop=stop,
        required_laps=required,
        accepted_laps=accepted,
        complete=complete,
        stage="complete" if complete else stage,
        laps=tuple(decisions),
        blocker_reasons=_unique([*plan.blocker_reasons, *report.data_quality.issues]),
    )


def _critique(
    bundle: RunIntelligenceBundle, identity: CrewChiefWorkspaceIdentity
) -> CrewChiefCritique:
    report = bundle.report
    action = report.briefing.action
    findings: list[str] = []
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


def _persist_response_atlas(
    repository: CrewChiefRepository,
    objective: EngineeringObjective,
    identity: CrewChiefWorkspaceIdentity,
    p26: object,
) -> tuple[str, ...]:
    runtime = p26.runtime_identity
    record_ids: list[str] = []
    workflow_repository = RaceLabRepository(repository.db_path)
    for state in p26.component_states:
        for history in state.controlled_history:
            if not history.exact_context or len(history.stage_run_ids) < 3:
                continue
            try:
                workflow = workflow_repository.get_controlled_workflow(
                    history.workflow_id
                )
            except (KeyError, TypeError, ValueError):
                workflow = None
            card = workflow.packet.primary_test if workflow is not None else None
            if card is None or card.control_key != history.control_key:
                continue
            context = {
                "car_path": runtime.car_path,
                "car_version": runtime.car_version,
                "build": runtime.iracing_build_version,
                "track": runtime.track_configuration_name,
                "objective": objective.value,
                "phase": history.phase,
                "component": state.component_id,
                "control": history.control_key,
                "setup": identity.setup_snapshot_sha256,
            }
            context_identity = canonical_json_sha256(context)
            evidence_identity = canonical_json_sha256(history)
            record = ComponentResponseRecord(
                record_id=f"ccr_{canonical_json_sha256([history.workflow_id, context_identity])[:24]}",
                component_id=state.component_id,
                control_key=history.control_key,
                direction="increase" if card.direction_sign > 0 else "decrease",
                magnitude_class=(
                    "adjacent"
                    if "adjacent" in card.change_size.casefold()
                    else "unknown"
                ),
                car_path=runtime.car_path,
                car_version=runtime.car_version,
                iracing_build=runtime.iracing_build_version,
                track_package=runtime.track_configuration_name,
                objective=objective,
                target_phase=history.phase,
                physical_window=f"phase:{history.phase}",
                mechanism_result=history.mechanism_state,
                control_response_result=history.control_response,
                policy_verdict=history.policy_verdict,
                source_workflow_id=history.workflow_id,
                source_run_ids=history.stage_run_ids,
                evidence_identity=evidence_identity,
                context_identity=context_identity,
            )
            repository.save_response_record(record)
            record_ids.append(record.record_id)
    return _unique(record_ids)


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
    overview = RaceLabRepository(db_path).get_overview(run_id)
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
    if investigation is not None:
        objective = fold_investigation(
            investigation, events, bundle.report.reasoning_snapshot.causes
        ).objective
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
    with _CACHE_LOCK:
        cached = _CACHE.get(identity.workspace_revision)
        if cached is not None:
            return cached.model_copy(
                update={"cache_state": "warm", "generated_at": _now()}
            )
    folded = (
        fold_investigation(
            investigation, events, bundle.report.reasoning_snapshot.causes
        )
        if investigation
        else None
    )
    question = _driver_question(
        identity, investigation, folded, bundle.report.reasoning_snapshot.causes
    )
    critique = _critique(bundle, identity)
    contract = _success_contract(bundle, identity, objective)
    response_ids = _persist_response_atlas(repository, objective, identity, p26)
    driver_memory_ids: tuple[str, ...] = ()
    if investigation is not None:
        answer_events = tuple(
            event for event in events if event.event_type == "driver_answer_recorded"
        )
        memory = DriverKnowledgeRecord(
            record_id=f"ccdm_{canonical_json_sha256([investigation.investigation_id, [event.event_id for event in answer_events]])[:24]}",
            investigation_id=investigation.investigation_id,
            session_id=session_id,
            complaint_phrase=investigation.raw_driver_report,
            contextual_answer=(
                answer_events[-1].payload.answer if answer_events else None
            ),
            associated_cause_ids=tuple(
                cause.cause_id for cause in bundle.report.reasoning_snapshot.causes[:2]
            ),
            source_event_ids=tuple(event.event_id for event in answer_events),
            recorded_at=investigation.opened_at,
        )
        repository.save_driver_memory(memory)
        driver_memory_ids = tuple(
            item.record_id for item in repository.list_driver_memory(session_id)
        )
    subgoal = _subgoal(bundle, folded)
    latest_result = None
    if folded and folded.completed_tool_ids:
        latest = folded.completed_tool_ids[-1]
        definition = next(item for item in _TOOLS if item.tool_id == latest)
        indexed_entries = _evidence_index(bundle, identity, objective, p26).entries
        latest_result = CrewChiefToolResult(
            tool_id=latest,
            workspace_revision=identity.workspace_revision,
            status="complete" if indexed_entries else "no_finding",
            summary=(
                "Canonical producer artifacts were indexed; no authority was created."
                if indexed_entries
                else "No canonical artifact matched this exact workspace."
            ),
            artifact_ids=tuple(
                item.artifact_id for item in indexed_entries[:8]
            ),
            cause_ids=tuple(
                cause.cause_id for cause in bundle.report.reasoning_snapshot.causes[:2]
            ),
            component_ids=tuple(p26.leading_component_ids),
            authority_ceiling=definition.authority_ceiling,
        )
    decision = _decision(bundle, identity, critique, question)
    evidence_index = _evidence_index(bundle, identity, objective, p26)
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
        run_sentinel=_sentinel(bundle, overview),
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
            [*bundle.report.blocker_reasons, *p20.knowledge_debt, *p26.knowledge_debt]
        ),
    )
    if investigation:
        repository.save_success_contract(investigation.investigation_id, contract)
        repository.save_effectiveness(
            CrewChiefEffectivenessRecord(
                record_id=f"cceff_{canonical_json_sha256(investigation.investigation_id)[:24]}",
                investigation_id=investigation.investigation_id,
                workspace_revision=identity.workspace_revision,
                recorded_at=_now(),
                measurement_missions_completed=sum(
                    event.event_type == "decision_emitted"
                    and event.payload.decision_kind == "measurement_mission"
                    for event in events
                ),
                controlled_tests_completed=sum(
                    event.event_type == "decision_emitted"
                    and event.payload.decision_kind == "controlled_test"
                    for event in events
                ),
                rejected_laps=sum(
                    item.status == "rejected" for item in workspace.run_sentinel.laps
                ),
                prior_undo_policies_blocked=sum(
                    history.policy_verdict == "undo"
                    for state in p26.component_states
                    for history in state.controlled_history
                    if history.exact_context
                ),
                countereffects_caught=sum(
                    bool(history.countereffects)
                    for state in p26.component_states
                    for history in state.controlled_history
                    if history.exact_context
                ),
                terminal_decision_kind=decision.kind,
            )
        )
    with _CACHE_LOCK:
        _CACHE[identity.workspace_revision] = workspace
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
        and current.folded_state.status == "open"
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
    repository = CrewChiefRepository(db_path)
    sequence = current.folded_state.last_sequence + 1
    if current.current_subgoal is not None:
        subgoal = current.current_subgoal
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
                    artifact_ids=tuple(
                        item.artifact_id for item in current.evidence_index.entries[:8]
                    ),
                    findings=(
                        "Canonical evidence attached; authority ceiling preserved.",
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
    return build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        investigation_id=investigation_id,
        db_path=db_path,
    )


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
    if question is None or answer not in question.answer_options:
        raise ValueError("Driver answer must match the pending contextual question.")
    sequence = current.folded_state.last_sequence + 1
    CrewChiefRepository(db_path).append_event(
        _event(
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
    CrewChiefRepository(db_path).append_event(
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
    if current.folded_state is None or current.folded_state.status != "open":
        raise ValueError("Crew Chief investigation is not open.")
    if current.identity.workspace_revision == stale_workspace_revision:
        return current
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
