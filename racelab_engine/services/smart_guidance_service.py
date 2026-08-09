"""Deterministic prioritization for the Smart Engineer and application shell."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.intelligence import InternalIntelligenceReport
from racelab_engine.models.smart_guidance import (
    AttentionItem,
    ControlledTestPreflight,
    MeasurementDebt,
    MeasurementDebtItem,
    NextTrustworthyMove,
    PreflightCheck,
    SmartGuidance,
    measurement_priority_rank,
)


_DEBT_KIND_ORDER = {
    "data-quality": 0,
    "telemetry-health": 1,
    "eligible-laps": 2,
    "trusted-events": 3,
    "defined-discriminator": 4,
}


def _fingerprint(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _next_stage(workflow: ControlledWorkflow) -> str:
    return {
        "planned": "A",
        "a_recorded": "B",
        "b_recorded": "A2",
        "a2_recorded": "complete",
        "scored": "complete",
        "cancelled": "complete",
    }[workflow.status]


def build_controlled_test_preflight(
    workflow: ControlledWorkflow | None,
) -> ControlledTestPreflight | None:
    """Describe persisted protocol requirements without claiming they are satisfied."""
    if workflow is None or workflow.status == "cancelled":
        return None
    stage = _next_stage(workflow)
    if workflow.status == "scored":
        return ControlledTestPreflight(
            workflow_id=workflow.workflow_id,
            stage="complete",
            status="complete",
            title="Controlled test scored",
            checks=(
                PreflightCheck(
                    check_id="certificate",
                    label="Certified outcome",
                    state="verified",
                    detail="The persisted A/B/A2 workflow has been scored and is ready for review.",
                ),
            ),
        )
    if stage == "complete":
        return ControlledTestPreflight(
            workflow_id=workflow.workflow_id,
            stage="complete",
            status="ready",
            title="Compare and score A/B/A2",
            checks=(
                PreflightCheck(
                    check_id="stages-recorded",
                    label="A, B, and A2 recorded",
                    state="verified",
                    detail="All three persisted stage bindings are present; scoring still performs full verification.",
                ),
                PreflightCheck(
                    check_id="score",
                    label="Run the controlled comparison",
                    state="required",
                    detail="Score the frozen protocol before accepting or rejecting the hypothesis.",
                ),
            ),
        )
    card = workflow.packet.primary_test
    mission = workflow.packet.measurement_mission
    if card is None:
        detail = (
            mission.procedure[0]
            if mission is not None and mission.procedure
            else "Collect the server-defined missing measurement without changing the setup."
        )
        mission_blockers = tuple(mission.blockers) if mission is not None else ()
        return ControlledTestPreflight(
            workflow_id=workflow.workflow_id,
            stage=stage,
            status="blocked" if mission_blockers else "ready",
            title=f"Prepare measurement stage {stage}",
            checks=(
                PreflightCheck(
                    check_id="unchanged-setup",
                    label="Keep setup unchanged",
                    state="required",
                    detail="This workflow is a measurement mission and carries no setup authority.",
                ),
                PreflightCheck(
                    check_id="mission-procedure",
                    label="Follow the persisted measurement procedure",
                    state="required",
                    detail=detail,
                ),
            ),
            blocker_reasons=mission_blockers,
        )
    stage_contract = next(item for item in card.stages if item.stage == stage)
    prior_stages = tuple(value for value in ("A", "B", "A2") if value in workflow.stage_run_ids)
    checks = (
        PreflightCheck(
            check_id="prior-stages",
            label="Prior stages are persisted",
            state="verified" if prior_stages or stage == "A" else "blocked",
            detail=(
                f"Recorded stages: {', '.join(prior_stages)}."
                if prior_stages
                else "Stage A starts from the source baseline run."
            ),
        ),
        PreflightCheck(
            check_id="setup-state",
            label=f"Use the persisted Stage {stage} setup instruction",
            state="required",
            detail=stage_contract.setup_instruction,
        ),
        PreflightCheck(
            check_id="warmup-laps",
            label=f"Complete {stage_contract.warmup_laps} warm-up laps",
            state="required",
            detail="Warm-up laps are not counted as measured flying laps.",
        ),
        PreflightCheck(
            check_id="flying-laps",
            label=f"Record {stage_contract.required_flying_laps} eligible flying laps",
            state="required",
            detail="Pit, cooldown, wreck, partial, reset, and invalid-speed laps remain excluded.",
        ),
        PreflightCheck(
            check_id="controlled-context",
            label="Hold context and all other setup controls",
            state="required",
            detail="Keep fuel, tires, weather, line, traffic, and unrelated setup controls comparable.",
        ),
        PreflightCheck(
            check_id="stop-rule",
            label="Honor the persisted stop rule",
            state="required",
            detail=card.stop_rule,
        ),
    )
    blockers = tuple(
        "The persisted stage sequence is incomplete."
        for check in checks
        if check.state == "blocked"
    )
    return ControlledTestPreflight(
        workflow_id=workflow.workflow_id,
        stage=stage,
        status="blocked" if blockers else "ready",
        title=f"Prepare controlled Stage {stage}",
        checks=checks,
        blocker_reasons=blockers,
    )


def build_measurement_debt(report: InternalIntelligenceReport) -> MeasurementDebt:
    """Convert typed evidence state into inspectable recovery work."""
    items: list[MeasurementDebtItem] = []
    quality = report.data_quality
    if quality.eligible_lap_count == 0:
        items.append(
            MeasurementDebtItem(
                debt_id="eligible-laps",
                label="No eligible flying lap",
                reason="Engineering conclusions require at least one complete qualified lap.",
                recovery_kind="select_eligible_lap",
                workspace="laps",
                priority="data_qualification",
                blocks_current_move=True,
                blocker_reasons=tuple(quality.recovery_steps),
            )
        )
    if quality.trusted_event_count == 0:
        items.append(
            MeasurementDebtItem(
                debt_id="trusted-events",
                label="No provenance-complete engineering event",
                reason="The current run has no qualified event that can support a cause or test.",
                recovery_kind="repeat_measurement",
                workspace="platform",
                priority="data_qualification",
                blocks_current_move=True,
                blocker_reasons=tuple(quality.issues),
            )
        )
    if report.best_measurement.kind == "blocked":
        items.append(
            MeasurementDebtItem(
                debt_id="defined-discriminator",
                label="No executable discriminator",
                reason="No producer-owned measurement can currently separate the unresolved evidence.",
                recovery_kind="repeat_measurement",
                workspace="engineer",
                priority=report.best_measurement.recovery_priority or "discrimination",
                blocks_current_move=report.best_measurement.recovery_priority in {
                    "integrity",
                    "data_qualification",
                    "affected_channel_health",
                },
                resolves_cause_ids=tuple(
                    cause.cause_id
                    for cause in report.competing_causes
                    if cause.state != "ruled_out"
                ),
                blocker_reasons=tuple(report.best_measurement.blocker_reasons),
            )
        )
    health = report.telemetry_health
    if health is not None and health.status in {"warning", "blocked"}:
        affected_channels = tuple(
            dict.fromkeys(finding.channel for finding in health.findings)
        )
        items.append(
            MeasurementDebtItem(
                debt_id="telemetry-health",
                label=(
                    "Restore verified recording health"
                    if health.status == "blocked"
                    else "Inspect changed telemetry-channel health"
                ),
                reason=(
                    "The current recording-health identity is blocked. Re-import the original "
                    "artifact before trusting cross-run engineering evidence."
                    if health.status == "blocked"
                    else "One or more critical channels changed from two trusted compatible runs; "
                    "resolve the typed recovery before relying on affected evidence."
                ),
                recovery_kind="retry_resource",
                workspace="overview",
                priority=(
                    "integrity"
                    if health.status == "blocked"
                    else "affected_channel_health"
                    if report.best_measurement.recovery_priority
                    == "affected_channel_health"
                    else "background_health"
                ),
                blocks_current_move=(
                    health.status == "blocked"
                    or report.best_measurement.recovery_priority
                    == "affected_channel_health"
                ),
                required_channels=affected_channels,
                blocker_reasons=tuple(health.blocker_reasons),
            )
        )
    if quality.status == "blocked" and (
        not items or report.best_measurement.recovery_priority == "integrity"
    ):
        items.append(
            MeasurementDebtItem(
                debt_id="data-quality",
                label="Restore qualified telemetry evidence",
                reason=(
                    "The run-level evidence contract is blocked even though some laps or "
                    "events are present. Resolve the recorded data-quality issue before "
                    "using a diagnosis or setup call."
                ),
                recovery_kind="retry_resource",
                workspace="overview",
                priority="integrity",
                blocks_current_move=True,
                blocker_reasons=tuple((*quality.issues, *quality.recovery_steps)),
            )
        )
    unique = {item.debt_id: item for item in items}
    ordered = tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                measurement_priority_rank(item.priority),
                _DEBT_KIND_ORDER.get(item.debt_id, len(_DEBT_KIND_ORDER)),
                item.debt_id,
            ),
        )
    )
    if not ordered:
        return MeasurementDebt(
            status="clear",
            summary="No unresolved measurement prerequisite blocks the current next step.",
        )
    status = (
        "blocked"
        if quality.status == "blocked"
        or report.telemetry_health is not None
        and report.telemetry_health.status == "blocked"
        else "open"
    )
    return MeasurementDebt(
        status=status,
        summary=f"{len(ordered)} evidence prerequisite{'s' if len(ordered) != 1 else ''} remain.",
        items=ordered,
    )


def _contextual_questions(report: InternalIntelligenceReport) -> tuple[str, ...]:
    questions: list[str] = []
    if report.session_ledger is not None and report.session_ledger.entries:
        questions.append("What changed since the last qualified run?")
    if report.opportunity_signature is not None and report.opportunity_signature.signatures:
        questions.append("How repeatable is the strongest opportunity?")
    if report.driver_focus is not None and report.driver_focus.focus is not None:
        questions.append("How consistent are my inputs?")
    if report.anomalies is not None and report.anomalies.anomalies:
        questions.append("What anomalies are new?")
    if report.data_quality.status != "ready":
        questions.append("Is the data good?")
    if report.briefing.action.setup_authorized:
        questions.extend(("What should I do next?", "Why this call?"))
    elif any(cause.state == "leading" for cause in report.competing_causes):
        questions.extend(("Why this call?", "What would change your mind?"))
    else:
        questions.extend(("What evidence supports this?", "What was ruled out?"))
    if report.context_matches:
        questions.append("What worked here before?")
    questions.append("Where is the strongest repeatable loss?")
    return tuple(dict.fromkeys(questions))[:4]


def build_smart_guidance(
    report: InternalIntelligenceReport,
    *,
    workflow: ControlledWorkflow | None = None,
) -> SmartGuidance:
    """Rank one safe next move from current evidence and persisted workflow state."""
    debt = build_measurement_debt(report)
    preflight = build_controlled_test_preflight(workflow)
    quality = report.data_quality
    action = report.briefing.action
    workflow_binding = (
        {
            "workflow_id": workflow.workflow_id,
            "workflow_updated_at": workflow.updated_at,
        }
        if workflow is not None
        else {}
    )
    active_test_continuation_blocked = bool(
        workflow is not None
        and workflow.packet.decision == "test"
        and workflow.status in {"planned", "a_recorded", "b_recorded"}
        and (
            preflight is None
            or preflight.status == "blocked"
            or report.status == "blocked"
            or report.best_measurement.kind != "controlled_test"
            or not action.setup_authorized
        )
    )
    blocked_test_reasons = tuple(
        dict.fromkeys(
            reason
            for reason in (
                *report.best_measurement.blocker_reasons,
                *action.blocker_reasons,
                *report.briefing.blocker_reasons,
                *report.blocker_reasons,
            )
            if reason
        )
    )
    if active_test_continuation_blocked:
        blocked_test_reasons = blocked_test_reasons or (
            "The current report does not authorize continuation of this controlled test.",
        )
        assert workflow is not None and preflight is not None
        preflight = ControlledTestPreflight(
            workflow_id=workflow.workflow_id,
            stage=preflight.stage,
            status="blocked",
            title="Controlled workflow needs review",
            checks=(
                PreflightCheck(
                    check_id="current-card-authority",
                    label="Current controlled-test authority",
                    state="blocked",
                    detail=(
                        "Do not record the next stage. Review, abandon, or rebuild this workflow "
                        "from the current evidence-qualified report."
                    ),
                ),
            ),
            blocker_reasons=blocked_test_reasons,
        )
    if quality.status == "blocked":
        first = debt.items[0]
        move = NextTrustworthyMove(
            move_id=f"recover:{first.debt_id}",
            kind="recover",
            title=first.label,
            instruction=first.reason,
            reason="Data qualification outranks diagnosis and setup work.",
            workspace=first.workspace,
            run_id=report.run_id,
            blocker_reasons=first.blocker_reasons or tuple(quality.issues),
        )
        mission_stage = "qualify"
    elif report.telemetry_health is not None and report.telemetry_health.status == "blocked":
        health_item = next(item for item in debt.items if item.debt_id == "telemetry-health")
        move = NextTrustworthyMove(
            move_id=f"recover:{health_item.debt_id}",
            kind="recover",
            title=health_item.label,
            instruction=health_item.reason,
            reason="Verified recording identity outranks diagnosis and setup work.",
            workspace=health_item.workspace,
            run_id=report.run_id,
            blocker_reasons=health_item.blocker_reasons,
        )
        mission_stage = "qualify"
    elif (
        report.telemetry_health is not None
        and report.telemetry_health.status == "warning"
        and any(
            item.debt_id == "telemetry-health" and item.blocks_current_move
            for item in debt.items
        )
    ):
        health_item = next(item for item in debt.items if item.debt_id == "telemetry-health")
        move = NextTrustworthyMove(
            move_id=f"recover:{health_item.debt_id}",
            kind="recover",
            title=health_item.label,
            instruction=health_item.reason,
            reason=(
                "The planned measurement uses the affected channel lineage, so typed "
                "recording-health recovery outranks another pass."
            ),
            workspace=health_item.workspace,
            run_id=report.run_id,
            blocker_reasons=health_item.blocker_reasons,
        )
        mission_stage = "qualify"
    elif any(
        item.blocks_current_move
        and item.priority in {"integrity", "data_qualification"}
        for item in debt.items
    ):
        first = next(
            item
            for item in debt.items
            if item.blocks_current_move
            and item.priority in {"integrity", "data_qualification"}
        )
        move = NextTrustworthyMove(
            move_id=f"recover:{first.debt_id}",
            kind="recover",
            title=first.label,
            instruction=first.reason,
            reason="Evidence integrity and data qualification outrank another measurement.",
            workspace=first.workspace,
            run_id=report.run_id,
            blocker_reasons=first.blocker_reasons,
        )
        mission_stage = "qualify"
    elif workflow is not None and workflow.status == "scored":
        move = NextTrustworthyMove(
            move_id=f"decide:{workflow.workflow_id}",
            kind="decide",
            title="Review the certified controlled result",
            instruction="Open Dial-In and review Keep, Undo, Retest, or Invalid with its certificate.",
            reason="A completed controlled result should be acknowledged before another hypothesis begins.",
            workspace="dial_in",
            run_id=report.run_id,
            **workflow_binding,
        )
        mission_stage = "certified"
    elif (
        workflow is not None
        and workflow.packet.decision == "test"
        and workflow.status == "a2_recorded"
    ):
        move = NextTrustworthyMove(
            move_id=f"compare:{workflow.workflow_id}",
            kind="compare",
            title="Compare and score A/B/A2",
            instruction="Open Dial-In and run the persisted controlled comparison.",
            reason="All three stages are recorded; scoring must happen before another change.",
            workspace="dial_in",
            run_id=report.run_id,
            **workflow_binding,
        )
        mission_stage = "compare"
    elif active_test_continuation_blocked:
        assert workflow is not None and preflight is not None
        move = NextTrustworthyMove(
            move_id=f"review-blocked:{workflow.workflow_id}:{preflight.stage}",
            kind="recover",
            title="Review the blocked controlled workflow",
            instruction=(
                "Open Dial-In to review and abandon or rebuild this workflow. Do not record "
                "another stage from the withheld card."
            ),
            reason=(
                "The current report withheld this controlled-test card, so persisted workflow "
                "state cannot override current evidence authority."
            ),
            workspace="dial_in",
            run_id=report.run_id,
            blocker_reasons=blocked_test_reasons,
            **workflow_binding,
        )
        mission_stage = "measure"
    elif (
        workflow is not None
        and workflow.packet.decision == "test"
        and workflow.status == "b_recorded"
    ):
        assert preflight is not None
        move = NextTrustworthyMove(
            move_id=f"resume:{preflight.workflow_id}:{preflight.stage}",
            kind="controlled_test",
            title=preflight.title,
            instruction="Open Dial-In and restore the persisted Stage A2 baseline protocol.",
            reason="Stage B is recorded; the required reproduction stage outranks a new setup target.",
            workspace="dial_in",
            run_id=report.run_id,
            blocker_reasons=preflight.blocker_reasons,
            **workflow_binding,
        )
        mission_stage = "test"
    elif workflow is not None and workflow.status == "a_recorded" and action.setup_authorized:
        move = NextTrustworthyMove(
            move_id=f"test:{workflow.workflow_id}",
            kind="controlled_test",
            title=action.title,
            instruction=action.instruction,
            reason="The existing server-owned controlled card is current and evidence-linked.",
            workspace="dial_in",
            authority="setup_authorized",
            run_id=report.run_id,
            control_key=action.control_key,
            source_event_ids=tuple(action.source_event_ids),
            **workflow_binding,
        )
        mission_stage = "test"
    elif preflight is not None and preflight.status != "complete":
        move = NextTrustworthyMove(
            move_id=f"resume:{preflight.workflow_id}:{preflight.stage}",
            kind="measure" if workflow and workflow.packet.decision != "test" else "controlled_test",
            title=preflight.title,
            instruction="Open Dial-In to complete the next persisted workflow stage.",
            reason="An active workflow must be finished or explicitly abandoned before a new investigation.",
            workspace="dial_in",
            run_id=report.run_id,
            blocker_reasons=preflight.blocker_reasons,
            **workflow_binding,
        )
        mission_stage = "measure" if workflow and workflow.packet.decision != "test" else "test"
    elif report.best_measurement.kind in {"measurement_mission", "discriminator"}:
        move = NextTrustworthyMove(
            move_id=f"measure:{report.run_id}:{report.best_measurement.kind}",
            kind="measure",
            title=report.best_measurement.title,
            instruction=report.best_measurement.instruction,
            reason=report.best_measurement.rationale,
            workspace="engineer",
            run_id=report.run_id,
            source_event_ids=tuple(report.best_measurement.source_event_ids),
            blocker_reasons=tuple(report.best_measurement.blocker_reasons),
        )
        mission_stage = "measure"
    elif report.opportunity_signature is not None and report.opportunity_signature.signatures:
        signature = sorted(
            report.opportunity_signature.signatures,
            key=lambda item: (-item.median_opportunity_s, item.signature_id),
        )[0]
        event_ids = tuple(
            dict.fromkeys(
                citation.event_id
                for citation in signature.citations
                if citation.event_id is not None
            )
        )
        signature_lap = signature.citations[0].lap_number if signature.citations else None
        exact_signature_lap = signature_lap if signature_lap is not None and signature_lap >= 1 else None
        move = NextTrustworthyMove(
            move_id=f"opportunity:{signature.signature_id}",
            kind="diagnose",
            title="Inspect the strongest repeatable opportunity",
            instruction=(
                f"Open the {signature.phase} trace at "
                f"{signature.lap_pct_start:g}-{signature.lap_pct_end:g}% and compare its cited laps."
            ),
            reason=(
                f"The same-setup window repeats on {signature.repetition_count} eligible laps "
                "above the empirical same-run noise floor."
            ),
            workspace="platform",
            run_id=report.run_id,
            lap_number=exact_signature_lap,
            lap_pct_start=signature.lap_pct_start if exact_signature_lap is not None else None,
            lap_pct_end=signature.lap_pct_end if exact_signature_lap is not None else None,
            source_event_ids=event_ids,
        )
        mission_stage = "diagnose"
    elif report.driver_focus is not None and report.driver_focus.focus is not None:
        focus = report.driver_focus.focus
        focus_lap = focus.citations[0].lap_number if focus.citations else None
        exact_focus_lap = focus_lap if focus_lap is not None and focus_lap >= 1 else None
        move = NextTrustworthyMove(
            move_id=f"driver-focus:{report.run_id}:{focus.phase}",
            kind="diagnose",
            title="Practice the qualified driver-repeatability focus",
            instruction=focus.instruction,
            reason="Same-setup input variation is measurable here; coaching remains separate from setup authority.",
            workspace="laps",
            run_id=report.run_id,
            lap_number=exact_focus_lap,
            lap_pct_start=focus.lap_pct_start if exact_focus_lap is not None else None,
            lap_pct_end=focus.lap_pct_end if exact_focus_lap is not None else None,
        )
        mission_stage = "diagnose"
    elif report.competing_causes:
        move = NextTrustworthyMove(
            move_id=f"diagnose:{report.run_id}",
            kind="diagnose",
            title="Inspect the strongest qualified evidence",
            instruction="Open Platform and compare supporting and contradictory evidence at its exact location.",
            reason="The cause ranking is observational and needs a producer-owned discriminator.",
            workspace="platform",
            run_id=report.run_id,
            source_event_ids=tuple(
                dict.fromkeys(
                    citation.event_id
                    for cause in report.competing_causes
                    for citation in cause.evidence_for
                    if citation.event_id is not None
                )
            ),
        )
        mission_stage = "diagnose"
    else:
        move = NextTrustworthyMove(
            move_id=f"qualify:{report.run_id}",
            kind="qualify",
            title="Qualify a repeatable run",
            instruction="Open Laps and select a complete eligible flying lap or window.",
            reason="No current evidence supports diagnosis or setup work.",
            workspace="laps",
            run_id=report.run_id,
            blocker_reasons=tuple(report.blocker_reasons),
        )
        mission_stage = "qualify"
    attention_items = [
        AttentionItem(
            attention_id=f"move:{move.move_id}",
            state="changed",
            label=move.title,
            workspace=move.workspace,
            run_id=move.run_id,
            fingerprint=_fingerprint(
                move.kind,
                move.title,
                move.instruction,
                move.source_event_ids,
                move.workflow_id,
                move.workflow_updated_at,
                report.data_quality.status,
            ),
        )
    ]
    if report.anomalies is not None:
        for anomaly in report.anomalies.anomalies[:3]:
            attention_items.append(
                AttentionItem(
                    attention_id=f"anomaly:{anomaly.anomaly_id}",
                    state="new",
                    label=(
                        f"Unexpected {anomaly.channel} behavior near "
                        f"{anomaly.lap_pct_start:g}-{anomaly.lap_pct_end:g}%"
                    ),
                    workspace="platform",
                    run_id=report.run_id,
                    fingerprint=_fingerprint(
                        anomaly.anomaly_id,
                        anomaly.direction,
                        anomaly.reference_lap_numbers,
                    ),
                )
            )
    if report.session_ledger is not None:
        for entry in report.session_ledger.entries[-3:]:
            attention_items.append(
                AttentionItem(
                    attention_id=f"ledger:{entry.entry_id}",
                    state="resolved" if entry.state == "resolved" else "changed",
                    label=entry.description,
                    workspace="laps",
                    run_id=entry.test_run_id,
                    fingerprint=_fingerprint(entry.entry_id, entry.state, entry.description),
                )
            )
    return SmartGuidance(
        mission_stage=mission_stage,
        next_trustworthy_move=move,
        measurement_debt=debt,
        test_preflight=preflight,
        attention_items=tuple(attention_items),
        contextual_questions=_contextual_questions(report),
    )


__all__: Sequence[str] = (
    "build_controlled_test_preflight",
    "build_measurement_debt",
    "build_smart_guidance",
)
