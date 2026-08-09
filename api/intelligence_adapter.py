from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from api.intelligence_schemas import (
    IntelligenceActionResponse,
    IntelligenceBriefingResponse,
    IntelligenceCalibrationResponse,
    IntelligenceCauseResponse,
    IntelligenceCitationResponse,
    IntelligenceContextMatchResponse,
    IntelligenceDataQualityResponse,
    IntelligenceDriverProfileResponse,
    IntelligenceEvidenceGraphResponse,
    IntelligenceGraphEdgeResponse,
    IntelligenceGraphNodeResponse,
    IntelligenceMeasurementResponse,
    IntelligenceMindChangeCriterionResponse,
    IntelligenceNavigationResponse,
    IntelligenceNarrativeEntryResponse,
    RunIntelligenceResponse,
    WITHHELD_STAGE_B_MOVE_INSTRUCTION,
    WITHHELD_STAGE_B_MOVE_REASON,
    WITHHELD_STAGE_B_MOVE_TITLE,
    WITHHELD_STAGE_B_PREFLIGHT_BLOCKER,
    WITHHELD_STAGE_B_PREFLIGHT_CHECK_DETAIL,
    WITHHELD_STAGE_B_PREFLIGHT_CHECK_LABEL,
    WITHHELD_STAGE_B_PREFLIGHT_TITLE,
)
from racelab_engine.models.engineering_memory import (
    DriverPresentationProfile,
    EngineeringNarrativeEntry,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import (
    EvidenceCitation,
    EvidenceEdgeKind,
    EvidenceNodeKind,
    InformationPlan,
    InternalIntelligenceReport,
    MindChangeCriterion,
    NavigationTarget,
    ResponseMemorySummary,
)
from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.models.smart_guidance import (
    ControlledTestPreflight,
    NextTrustworthyMove,
    PreflightCheck,
)


_WORKSPACE_MAP = {
    "overview": "overview",
    "laps": "laps",
    "platform": "platform_trace",
    "setup": "setup_impact",
    "dial_in": "dial_in",
}


def _citation(item: EvidenceCitation) -> IntelligenceCitationResponse:
    return IntelligenceCitationResponse(
        citation_id=item.citation_id,
        label=item.summary,
        run_id=item.run_id,
        lap_number=item.lap_number,
        lap_pct=(
            item.lap_pct_peak
            if item.lap_pct_peak is not None
            else item.lap_pct_start
        ),
        event_id=item.event_id,
        workspace=_WORKSPACE_MAP[item.workspace],
        source_channels=list(item.channels),
        evidence_state=item.evidence_state,
        valid_for_tuning=item.valid_for_tuning,
    )


def to_public_intelligence_citation(
    item: EvidenceCitation,
) -> IntelligenceCitationResponse:
    return _citation(item)


def to_public_intelligence_navigation(
    item: NavigationTarget,
) -> IntelligenceNavigationResponse:
    return IntelligenceNavigationResponse(
        workspace=_WORKSPACE_MAP[item.workspace],
        run_id=item.run_id,
        lap_number=item.lap_number,
        event_id=item.event_id,
        lap_pct=item.lap_pct,
    )


def to_public_mind_change_criterion(
    item: MindChangeCriterion,
) -> IntelligenceMindChangeCriterionResponse:
    return IntelligenceMindChangeCriterionResponse(
        criterion_id=item.criterion_id,
        cause_id=item.cause_id,
        current_state=item.current_state,
        evidence_kind=item.evidence_kind,
        run_id=item.run_id,
        session_id=item.session_id,
        metric=item.metric,
        phase=item.phase,
        control_key=item.control_key,
        threshold_source=item.threshold_source,
        acceptance_conditions=list(item.acceptance_conditions),
        falsification_conditions=list(item.falsification_conditions),
        minimum_independent_evidence_units=item.minimum_independent_evidence_units,
        minimum_evidence=item.minimum_evidence,
        requires_aba2=item.requires_aba2,
        minimum_laps_per_stage=item.minimum_laps_per_stage,
        countereffects=list(item.countereffects),
        next_state_if_accepted=item.next_state_if_accepted,
        next_state_if_falsified=item.next_state_if_falsified,
        next_state_if_inconclusive=item.next_state_if_inconclusive,
        source_event_ids=list(item.source_event_ids),
    )


def _event_citation_key(run_id: str, event_id: str) -> str:
    return f"event-ref:{run_id}:{event_id}"


def _citation_lookup(report: InternalIntelligenceReport) -> dict[str, IntelligenceCitationResponse]:
    result: dict[str, IntelligenceCitationResponse] = {}
    for node in report.evidence_graph.nodes:
        if node.citation is None:
            continue
        converted = _citation(node.citation)
        result[converted.citation_id] = converted
        if converted.event_id:
            result[_event_citation_key(converted.run_id, converted.event_id)] = converted
    return result


def _setup_authority_blockers(report: InternalIntelligenceReport) -> tuple[str, ...]:
    action = report.briefing.action
    reasons = [
        *report.data_quality.issues,
        *report.blocker_reasons,
        *report.briefing.blocker_reasons,
        *action.blocker_reasons,
    ]
    if report.status != "ready":
        reasons.append("The current report decision is not ready for a setup action.")
    if report.data_quality.status != "ready":
        reasons.append("The current run data quality is not ready for a setup action.")
    return tuple(dict.fromkeys(reason for reason in reasons if reason))


def _action(report: InternalIntelligenceReport) -> IntelligenceActionResponse:
    action = report.briefing.action
    authority_blockers = _setup_authority_blockers(report)
    if action.setup_authorized and authority_blockers:
        return IntelligenceActionResponse(
            kind="no_call",
            title="Setup action withheld",
            instruction=(
                "Keep the current setup and resolve the published evidence blockers before "
                "starting another controlled test."
            ),
            setup_authorized=False,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            blocker_reasons=list(authority_blockers),
        )
    kind = action.kind
    if kind == "discriminator":
        kind = "measurement_mission"
    return IntelligenceActionResponse(
        kind=kind,
        title=action.title,
        instruction=action.instruction,
        setup_authorized=action.setup_authorized,
        control_key=action.control_key,
        current_value=action.current_value,
        proposed_value=action.proposed_value,
        evidence_state=action.evidence_state,
        source_event_ids=list(action.source_event_ids),
        blocker_reasons=list(action.blocker_reasons),
    )


def _public_test_preflight(
    preflight: ControlledTestPreflight | None,
    *,
    setup_authorized: bool,
) -> ControlledTestPreflight | None:
    if preflight is None or preflight.stage != "B" or setup_authorized:
        return preflight
    return ControlledTestPreflight(
        workflow_id=preflight.workflow_id,
        stage="B",
        status="blocked",
        title=WITHHELD_STAGE_B_PREFLIGHT_TITLE,
        checks=(
            PreflightCheck(
                check_id="current-card-authority",
                label=WITHHELD_STAGE_B_PREFLIGHT_CHECK_LABEL,
                state="blocked",
                detail=WITHHELD_STAGE_B_PREFLIGHT_CHECK_DETAIL,
            ),
        ),
        blocker_reasons=(WITHHELD_STAGE_B_PREFLIGHT_BLOCKER,),
    )


def _public_next_move(
    report: InternalIntelligenceReport,
    preflight: ControlledTestPreflight | None,
    *,
    setup_authorized: bool,
) -> NextTrustworthyMove | None:
    guidance = report.smart_guidance
    if guidance is None:
        return None
    move = guidance.next_trustworthy_move
    if preflight is None or preflight.stage != "B" or setup_authorized:
        return move
    if (
        move.workflow_id != preflight.workflow_id
        or move.workflow_updated_at is None
    ):
        return None
    return NextTrustworthyMove(
        move_id=f"review-withheld:{preflight.workflow_id}:B",
        kind="recover",
        title=WITHHELD_STAGE_B_MOVE_TITLE,
        instruction=WITHHELD_STAGE_B_MOVE_INSTRUCTION,
        reason=WITHHELD_STAGE_B_MOVE_REASON,
        workspace="dial_in",
        authority="navigation_only",
        run_id=report.run_id,
        workflow_id=preflight.workflow_id,
        workflow_updated_at=move.workflow_updated_at,
        blocker_reasons=(WITHHELD_STAGE_B_PREFLIGHT_BLOCKER,),
    )


def _cause(item: Any) -> IntelligenceCauseResponse:
    evidence_for = [_citation(citation) for citation in item.evidence_for]
    evidence_against = [_citation(citation) for citation in item.evidence_against]
    for outcome in item.controlled_outcomes:
        if outcome.outcome not in {"supported", "contradicted"}:
            continue
        digest = hashlib.sha256(
            f"{item.cause_id}|{outcome.workflow_id}|{outcome.outcome}".encode("utf-8")
        ).hexdigest()[:20]
        controlled_citation = IntelligenceCitationResponse(
            citation_id=f"controlled-outcome:{digest}",
            label=(
                "Controlled A/B/A2 result supported this explanation"
                if outcome.outcome == "supported"
                else "Controlled A/B/A2 result contradicted this explanation"
            ),
            run_id=outcome.source_run_id,
            workspace="dial_in",
            source_channels=[],
            evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
            valid_for_tuning=False,
        )
        if outcome.outcome == "supported":
            evidence_for.append(controlled_citation)
        else:
            evidence_against.append(controlled_citation)
    evidence_state = (
        evidence_for[0].evidence_state
        if evidence_for
        else evidence_against[0].evidence_state
        if evidence_against
        else EvidenceState.BLOCKED_BY_CONTEXT
        if item.state == "ruled_out"
        else EvidenceState.UNAVAILABLE
    )
    return IntelligenceCauseResponse(
        cause_id=item.cause_id,
        label=item.label,
        state=item.state,
        rank=item.rank,
        evidence_state=evidence_state,
        reason=item.reason,
        evidence_for=evidence_for,
        evidence_against=evidence_against,
    )


def _measurement(
    plan: InformationPlan,
    citations: dict[str, IntelligenceCitationResponse],
    run_id: str,
    *,
    setup_authorized: bool,
) -> IntelligenceMeasurementResponse | None:
    linked = [
        citations[_event_citation_key(run_id, event_id)]
        for event_id in plan.source_event_ids
        if _event_citation_key(run_id, event_id) in citations
    ]
    if plan.kind == "controlled_test" and plan.controlled_test is not None:
        if not setup_authorized:
            return None
        card = plan.controlled_test
        return IntelligenceMeasurementResponse(
            mission_id=f"controlled-test:{card.control_key}",
            title=plan.title,
            purpose=plan.rationale,
            procedure=[stage.setup_instruction for stage in card.stages],
            required_laps=sum(
                stage.warmup_laps + stage.required_flying_laps for stage in card.stages
            ),
            acceptance_threshold="; ".join(card.success_metrics),
            stop_rule=card.stop_rule,
            controlled_variables=[f"Change only {card.control_label}."],
            citations=linked,
        )
    if plan.kind == "measurement_mission" and plan.measurement_mission is not None:
        mission = plan.measurement_mission
        return IntelligenceMeasurementResponse(
            mission_id=f"measurement:{mission.target_phase}",
            title=plan.title,
            purpose=mission.purpose,
            procedure=list(mission.procedure),
            required_laps=mission.required_laps_or_passes,
            acceptance_threshold="; ".join(mission.acceptance_thresholds),
            stop_rule=mission.stop_rule,
            controlled_variables=[
                "Keep setup, fuel, tires, weather, and driver approach matched."
            ],
            citations=linked,
        )
    if plan.kind == "discriminator" and plan.discriminator is not None:
        discriminator = plan.discriminator
        return IntelligenceMeasurementResponse(
            mission_id=discriminator.discriminator_id,
            title=discriminator.title,
            purpose=plan.rationale,
            procedure=[discriminator.instruction],
            acceptance_threshold="; ".join(discriminator.acceptance_thresholds),
            controlled_variables=["Do not change the setup while isolating this cause."],
            citations=linked,
        )
    return None


def _context_match(
    item: ResponseMemorySummary,
    citations: dict[str, IntelligenceCitationResponse],
) -> IntelligenceContextMatchResponse:
    source_event_ids = tuple(getattr(item, "evidence_event_ids", ()))
    linked: list[IntelligenceCitationResponse] = []
    if len(item.source_run_ids) == 1:
        source_run_id = item.source_run_ids[0]
        linked = [
            citations[_event_citation_key(source_run_id, event_id)]
            for event_id in source_event_ids
            if _event_citation_key(source_run_id, event_id) in citations
        ]
    linked_run_ids = {citation.run_id for citation in linked}
    memory_is_qualified = (
        item.status == "exact_context_match"
        and item.qualified_observation_count > 0
    )
    for source_run_id in item.source_run_ids:
        if source_run_id in linked_run_ids:
            continue
        linked.append(IntelligenceCitationResponse(
            citation_id=f"memory-run:{source_run_id}:{item.control_key}",
            label="Controlled source run",
            run_id=source_run_id,
            workspace="dial_in",
            source_channels=["controlled_workflow_outcome"],
            evidence_state=(
                EvidenceState.CONTROLLED_TEST_EFFECT
                if memory_is_qualified
                else EvidenceState.NEEDS_CONFIRMATION
            ),
            # A run-level link is navigable provenance, not a substitute for the
            # exact event citation required to authorize another tuning action.
            valid_for_tuning=False,
        ))
    direction = "increase" if item.direction_sign > 0 else "decrease"
    if item.counterfactual_range is not None:
        prediction = item.counterfactual_range
        outcome = (
            f"Observed exact-context effects ranged {prediction.minimum:.3f} to "
            f"{prediction.maximum:.3f} {prediction.unit} inside the recorded input envelope."
        )
    elif item.verdicts:
        outcome = f"Recorded verdicts: {', '.join(item.verdicts)}."
    else:
        outcome = "No qualified exact-context effect is available."
    return IntelligenceContextMatchResponse(
        memory_id=(
            item.source_observation_ids[0]
            if item.source_observation_ids
            else f"{item.control_key}:{item.direction_sign}"
        ),
        label=f"{direction.title()} {item.control_key.replace('_', ' ')}",
        relevance_label=item.status.replace("_", " ").title(),
        outcome_summary=outcome,
        verdict=("contradictory" if item.status == "contradictory_history" else item.status),
        matching_context=list(getattr(item, "matching_context", ())),
        mismatches=list(getattr(item, "mismatches", item.blocker_reasons)),
        citations=linked,
    )


def _calibration(
    report: InternalIntelligenceReport,
    supplied: Any | None,
) -> IntelligenceCalibrationResponse:
    if supplied is not None:
        matched = getattr(supplied, "matched_predictions", None)
        total = getattr(supplied, "graded_predictions", None)
        if isinstance(supplied, dict):
            matched = supplied.get("matched_predictions", supplied.get("qualified_correct"))
            total = supplied.get("graded_predictions", supplied.get("qualified_total"))
        if matched is not None and total is not None and int(total) > 0:
            return IntelligenceCalibrationResponse(
                status="available",
                summary=(
                    f"Direction matched in {int(matched)} of {int(total)} "
                    "protocol-valid gradable direction outcomes."
                ),
                qualified_correct=int(matched),
                qualified_total=int(total),
                caveat=(
                    "This is an observed local track record, not a probability or a guarantee "
                    "for the next test."
                ),
            )
    internal = report.calibration
    if (
        internal.status == "available"
        and internal.evaluated_predictions is not None
        and internal.correct_direction_count is not None
    ):
        return IntelligenceCalibrationResponse(
            status="available",
            summary=internal.note,
            qualified_correct=internal.correct_direction_count,
            qualified_total=internal.evaluated_predictions,
            caveat="Observed controlled outcomes are ordinal evidence, not calibrated probability.",
        )
    return IntelligenceCalibrationResponse(
        status="insufficient_history",
        summary=internal.note,
        caveat=(
            "More qualified A/B/A2 outcomes are required before prediction performance can be summarized."
        ),
    )


def _reference_citation(
    entry: EngineeringNarrativeEntry,
    reference: Any,
    citations: dict[str, IntelligenceCitationResponse],
) -> IntelligenceCitationResponse:
    if reference.kind == "event":
        matches = [
            citations[_event_citation_key(run_id, reference.reference_id)]
            for run_id in entry.run_ids
            if _event_citation_key(run_id, reference.reference_id) in citations
        ]
        unique_matches = {
            (match.run_id, match.citation_id): match for match in matches
        }
        if len(unique_matches) == 1:
            return next(iter(unique_matches.values()))
    elif reference.reference_id in citations:
        candidate = citations[reference.reference_id]
        if not entry.run_ids or candidate.run_id in entry.run_ids:
            return candidate
    run_id = (
        reference.reference_id
        if reference.kind == "run" and reference.reference_id in entry.run_ids
        else entry.run_ids[0]
        if entry.run_ids
        else "unavailable"
    )
    reference_digest = hashlib.sha256(
        f"{reference.kind}:{reference.reference_id}".encode("utf-8")
    ).hexdigest()[:16]
    return IntelligenceCitationResponse(
        citation_id=f"narrative:{entry.entry_id}:{reference.kind}:{reference_digest}",
        label=f"Recorded {reference.kind} reference",
        run_id=run_id,
        workspace="dial_in" if reference.kind == "workflow" else "overview",
        evidence_state=(
            EvidenceState.CONTROLLED_TEST_EFFECT
            if entry.entry_type in {"outcome", "rollback", "learning"}
            else EvidenceState.NEEDS_CONFIRMATION
        ),
        valid_for_tuning=False,
    )


def _narrative(
    report: InternalIntelligenceReport,
    supplied: tuple[EngineeringNarrativeEntry, ...] | list[EngineeringNarrativeEntry],
    citations: dict[str, IntelligenceCitationResponse],
) -> list[IntelligenceNarrativeEntryResponse]:
    safe_summaries = {
        "complaint": "A driver complaint was recorded for this workflow.",
        "hypothesis": "The server recorded an evidence-linked test hypothesis.",
        "measurement": "The required measurement protocol was recorded.",
        "change": "The controlled B-stage change was recorded.",
        "outcome": "The controlled-test outcome was recorded.",
        "rollback": "The rollback decision was recorded.",
        "learning": "A protocol-qualified learning record was stored.",
    }
    result = [
        IntelligenceNarrativeEntryResponse(
            entry_id=f"summary:{index}",
            label="Session note",
            summary=text,
        )
        for index, text in enumerate(report.narrative)
    ]
    for entry in supplied:
        result.append(IntelligenceNarrativeEntryResponse(
            entry_id=entry.entry_id,
            label=entry.entry_type.replace("_", " ").title(),
            summary=safe_summaries[entry.entry_type],
            outcome=(
                str(entry.metadata["verdict"])
                if entry.metadata.get("verdict") in {"keep", "undo", "retest", "invalid"}
                else None
            ),
            created_at=entry.created_at.isoformat(),
            citations=[
                _reference_citation(entry, reference, citations)
                for reference in entry.evidence_references
            ],
        ))
    return result


def _graph(
    report: InternalIntelligenceReport,
    *,
    setup_authorized: bool,
) -> IntelligenceEvidenceGraphResponse:
    kind_map = {
        EvidenceNodeKind.CLAIM: "claim",
        EvidenceNodeKind.WORKFLOW: "test",
        EvidenceNodeKind.EVENT: "evidence",
        EvidenceNodeKind.RECOMMENDATION: "evidence",
        EvidenceNodeKind.LAP: "evidence",
        EvidenceNodeKind.CHANNEL: "evidence",
        EvidenceNodeKind.SETUP: "evidence",
    }
    edge_map = {
        EvidenceEdgeKind.CONTRADICTED_BY: "contradicts",
        EvidenceEdgeKind.PART_OF_WORKFLOW: "tests",
        EvidenceEdgeKind.TESTS_SETUP: "tests",
    }
    def public_label(node: Any) -> str:
        if setup_authorized:
            return node.label
        if node.kind is EvidenceNodeKind.CLAIM:
            return "Evidence claim under review"
        if node.kind is EvidenceNodeKind.SETUP:
            return node.entity_id.replace("_", " ").title()
        if node.kind is EvidenceNodeKind.WORKFLOW:
            return "Controlled workflow under review"
        return node.label

    nodes = [
        IntelligenceGraphNodeResponse(
            node_id=node.node_id,
            label=public_label(node),
            kind=kind_map[node.kind],
            evidence_state=node.evidence_state,
            citation_id=node.citation.citation_id if node.citation else None,
        )
        for node in report.evidence_graph.nodes
    ]
    edges = [
        IntelligenceGraphEdgeResponse(
            source_id=edge.source_node_id,
            target_id=edge.target_node_id,
            relation=edge_map.get(edge.kind, "supports"),
        )
        for edge in report.evidence_graph.edges
    ]
    known_ids = {node.node_id for node in nodes}
    for cause in report.competing_causes:
        cause_id = f"cause:{cause.cause_id}"
        nodes.append(IntelligenceGraphNodeResponse(
            node_id=cause_id,
            label=cause.label,
            kind="cause",
            evidence_state=(
                cause.evidence_for[0].evidence_state
                if cause.evidence_for
                else EvidenceState.UNAVAILABLE
            ),
        ))
        for citation in cause.evidence_for:
            event_node = f"event:{citation.event_id}" if citation.event_id else ""
            if event_node in known_ids:
                edges.append(IntelligenceGraphEdgeResponse(
                    source_id=cause_id,
                    target_id=event_node,
                    relation="supports",
                ))
        for citation in cause.evidence_against:
            event_node = f"event:{citation.event_id}" if citation.event_id else ""
            if event_node in known_ids:
                edges.append(IntelligenceGraphEdgeResponse(
                    source_id=cause_id,
                    target_id=event_node,
                    relation="contradicts",
                ))
    return IntelligenceEvidenceGraphResponse(nodes=nodes, edges=edges)


def _driver_profile(
    profile: DriverPresentationProfile | None,
) -> IntelligenceDriverProfileResponse | None:
    if profile is None:
        return None
    try:
        canonical_symptoms = {
            item.canonical_symptom
            for item in load_setup_knowledge().symptom_vocabulary
        }
    except (FileNotFoundError, OSError, TypeError, ValueError):
        canonical_symptoms = set()
    return IntelligenceDriverProfileResponse(
        preferred_mode=profile.preferred_mode,
        terminology_level=profile.terminology_level,
        recurring_symptoms=[
            item.canonical_symptom
            for item in profile.recurring_symptoms
            if item.canonical_symptom in canonical_symptoms
        ],
        controlled_tests_completed=profile.controlled_tests_completed,
        consistency_label=profile.consistency_label,
        affects_evidence_eligibility=False,
    )


def to_public_intelligence_report(
    report: InternalIntelligenceReport,
    *,
    narrative_entries: tuple[EngineeringNarrativeEntry, ...] | list[EngineeringNarrativeEntry] = (),
    calibration: Any | None = None,
    driver_profile: DriverPresentationProfile | None = None,
) -> RunIntelligenceResponse:
    citations = _citation_lookup(report)
    quality = report.data_quality
    guidance = report.smart_guidance
    public_action = _action(report)
    setup_authorized = public_action.setup_authorized
    internal_preflight = guidance.test_preflight if guidance is not None else None
    public_preflight = _public_test_preflight(
        internal_preflight,
        setup_authorized=setup_authorized,
    )
    public_move = _public_next_move(
        report,
        internal_preflight,
        setup_authorized=setup_authorized,
    )
    public_mission_stage = (
        "measure"
        if public_preflight is not None
        and public_preflight.stage == "B"
        and not setup_authorized
        else guidance.mission_stage
        if guidance is not None
        else None
    )
    quality_summary = {
        "ready": "Eligible laps and provenance-complete engineering events are available.",
        "limited": "Some telemetry is usable, but important evidence is still limited.",
        "blocked": "This run cannot support a trustworthy engineering conclusion yet.",
    }[quality.status]
    return RunIntelligenceResponse(
        run_id=report.run_id,
        session_id=report.session_id,
        status="ready",
        decision_status=report.status,
        generated_at=datetime.now(timezone.utc).isoformat(),
        briefing=IntelligenceBriefingResponse(
            issue=report.briefing.issue,
            action=public_action,
            success_check=report.briefing.success_check,
            confidence_label=report.briefing.confidence_label,
            blocker_reasons=list(report.briefing.blocker_reasons),
        ),
        competing_causes=[_cause(item) for item in report.competing_causes],
        mind_change_criteria=[
            to_public_mind_change_criterion(item)
            for item in report.mind_change_criteria
        ],
        best_measurement=_measurement(
            report.best_measurement,
            citations,
            report.run_id,
            setup_authorized=setup_authorized,
        ),
        context_matches=[_context_match(item, citations) for item in report.context_matches],
        calibration=_calibration(report, calibration),
        narrative=_narrative(report, narrative_entries, citations),
        suggested_questions=list(report.suggested_questions),
        blocker_reasons=list(report.blocker_reasons),
        evidence_graph=_graph(report, setup_authorized=setup_authorized),
        data_quality=IntelligenceDataQualityResponse(
            status=quality.status,
            summary=quality_summary,
            eligible_laps=quality.eligible_lap_count,
            total_laps=quality.total_lap_count,
            trusted_events=quality.trusted_event_count,
            issues=list(quality.issues),
            recovery_steps=list(quality.recovery_steps),
            citations=[_citation(item) for item in quality.citations],
        ),
        driver_profile=_driver_profile(driver_profile),
        mission_stage=public_mission_stage,
        next_trustworthy_move=public_move,
        test_preflight=public_preflight,
        measurement_debt=guidance.measurement_debt if guidance is not None else None,
        attention_items=list(guidance.attention_items) if guidance is not None else [],
        session_ledger=report.session_ledger,
        hypothesis_lifecycle=report.hypothesis_lifecycle,
        opportunity_signature=report.opportunity_signature,
        mechanism_observations=report.mechanism_observations,
        anomalies=report.anomalies,
        driver_focus=report.driver_focus,
        telemetry_health=report.telemetry_health,
    )


__all__ = [
    "to_public_intelligence_citation",
    "to_public_intelligence_navigation",
    "to_public_mind_change_criterion",
    "to_public_intelligence_report",
]
