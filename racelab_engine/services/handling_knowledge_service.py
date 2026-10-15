"""Handling knowledge projection builder (P35.6 Milestone P4).

A read-only derived view over the existing intelligence spine. It reuses
the memoized Crew Chief workspace (which already embeds the canonical
Engineering Case with its handling investigation, and the P35.1 current
engineering-knowledge projection) and filters it down to the display
material one telemetry-observed handling assessment needs in Dial-In.

Nothing here creates reasoning: the mechanism statuses come from the P2
investigation, the setup-catalog knowledge comes from the P35.1 spine, and
the next action is the investigation's next inspection or measurement —
unless P19 has already projected an exact controlled experiment, which is
reported, never created.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from racelab_engine.models.engineering_knowledge import (
    CurrentEngineeringKnowledgeProjection,
)
from racelab_engine.models.handling_investigation import (
    HandlingInvestigationProjection,
)
from racelab_engine.models.handling_knowledge import (
    HandlingKnowledgeHypothesis,
    HandlingKnowledgeMechanismStatus,
    HandlingKnowledgeNextAction,
    HandlingKnowledgeProjection,
)

_RELEVANT_KNOWLEDGE_RELEVANCE = frozenset({
    "supported_candidate",
    "blocked_candidate",
    "knowledge_only",
})


def _static_catalog_entries(
    mechanism_ids: frozenset[str],
    covered_effect_ids: frozenset[str],
) -> tuple[HandlingKnowledgeHypothesis, ...]:
    """Static P35.1 bridge entries for mechanisms the current run cannot map.

    The setup catalog's reviewed mechanism→setup-area mapping stays
    available as educational context even when the current-run knowledge
    spine marks its hypotheses blocked by build or knowledge-only. These
    entries are structurally knowledge-only: no current-run authority, no
    P19 control, no setup authorization, ever.
    """
    from racelab_engine.knowledge.setup.engineering_knowledge import (
        compile_mechanism_setup_bridges,
    )

    return tuple(
        HandlingKnowledgeHypothesis(
            bridge_id=bridge.bridge_id,
            effect_id=bridge.effect_id,
            setup_area=bridge.setup_area,
            physical_role=bridge.physical_role,
            level="educational_knowledge",
            relevance="knowledge_only",
            knowledge_applicability="educational_only",
            p35_mechanism_ids=tuple(sorted(intersection)),
            countereffect_ids=(),
            missing_evidence=(),
            authority="knowledge_only",
            setup_authorized=False,
            p19_control=None,
        )
        for bridge in compile_mechanism_setup_bridges()
        if bridge.catalog_classification != "unsupported_remove"
        and bridge.effect_id not in covered_effect_ids
        and (intersection := mechanism_ids.intersection(bridge.p35_mechanism_ids))
    )


def _static_countereffect_targets(
    mechanism_ids: frozenset[str],
) -> tuple[str, ...]:
    from racelab_engine.knowledge.setup.engineering_knowledge import (
        compile_mechanism_setup_bridges,
    )

    return _unique(
        tuple(
            target
            for bridge in compile_mechanism_setup_bridges()
            if bridge.catalog_classification != "unsupported_remove"
            and mechanism_ids.intersection(bridge.p35_mechanism_ids)
            for target in bridge.countereffect_targets
        )
    )

_SYMPTOM_FAMILY = frozenset({"tight", "loose"})


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _symptom_label(symptom_id: str | None) -> str:
    if not symptom_id:
        return "no canonical symptom"
    label = symptom_id.replace("_", " ").strip()
    return label or symptom_id


def build_handling_knowledge_projection(
    *,
    investigation: HandlingInvestigationProjection | None,
    case: Any,
    knowledge: CurrentEngineeringKnowledgeProjection,
    assessment_id: str,
) -> HandlingKnowledgeProjection | None:
    """Filter the workspace truth into one assessment-scoped knowledge view.

    Returns None when the investigation or the requested assessment is not
    part of the exact case identity, so callers fail closed with 404.
    """
    if investigation is None:
        return None
    if (
        investigation.run_id != case.run_id
        or investigation.session_id != case.session_id
        or investigation.setup_id != case.setup_id
    ):
        return None
    assessment = next(
        (
            ref
            for ref in investigation.assessment_refs
            if ref.assessment_id == assessment_id
        ),
        None,
    )
    finding = next(
        (
            item
            for item in investigation.findings
            if item.assessment_id == assessment_id
        ),
        None,
    )
    if assessment is None or finding is None:
        return None
    mechanism_ids = {
        relation.mechanism_id for relation in finding.mechanisms
    }
    relevant = tuple(
        hypothesis
        for hypothesis in knowledge.hypotheses
        if hypothesis.relevance in _RELEVANT_KNOWLEDGE_RELEVANCE
        and mechanism_ids.intersection(hypothesis.p35_mechanism_ids)
        and hypothesis.knowledge_applicability != "unsupported"
    )
    mechanisms = tuple(
        HandlingKnowledgeMechanismStatus(
            mechanism_id=relation.mechanism_id,
            label=relation.label,
            relevance=relation.relevance,
            missing_evidence=relation.missing_evidence,
        )
        for relation in finding.mechanisms
    )
    static_entries = _static_catalog_entries(
        frozenset(mechanism_ids),
        frozenset(hypothesis.effect_id for hypothesis in relevant),
    )
    hypotheses = (
        *tuple(
            HandlingKnowledgeHypothesis(
                bridge_id=hypothesis.bridge_id,
                effect_id=hypothesis.effect_id,
                setup_area=hypothesis.setup_area,
                physical_role=hypothesis.physical_role,
                level=hypothesis.level,
                relevance=hypothesis.relevance,  # type: ignore[arg-type]
                knowledge_applicability=hypothesis.knowledge_applicability,  # type: ignore[arg-type]
                p35_mechanism_ids=tuple(
                    mechanism_id
                    for mechanism_id in hypothesis.p35_mechanism_ids
                    if mechanism_id in mechanism_ids
                ),
                countereffect_ids=hypothesis.countereffect_ids,
                missing_evidence=hypothesis.missing_evidence,
                authority=hypothesis.authority,  # type: ignore[arg-type]
                setup_authorized=hypothesis.setup_authorized,
                p19_control=hypothesis.p19_control,
            )
            for hypothesis in relevant
        ),
        *static_entries,
    )
    countereffects = _unique(
        (
            *(
                effect_id
                for hypothesis in relevant
                for effect_id in hypothesis.countereffect_ids
            ),
            *_static_countereffect_targets(frozenset(mechanism_ids)),
        )
    )
    classification = assessment.classification
    symptom = assessment.canonical_symptom_id
    corroborated = assessment.corroborated
    if corroborated and symptom:
        observed_behavior = (
            f"Telemetry corroborates a {assessment.phase.replace('_', ' ')} "
            f"rotation-response signature. Two producer strands agree: the "
            "kinematic residual beyond the run-local envelope and the "
            "steering demand per achieved curvature under comparable "
            "speeds. The observation is associated with the canonical "
            f"symptom family {_symptom_label(symptom)} as a telemetry-observed "
            "association only — it is not driver testimony and it is not a "
            "setup instruction."
        )
    else:
        observed_behavior = f"{finding.what} {finding.response}"
    evidence_qualification = (
        "Two-strand corroborated observation with a dependence discount: "
        "both strands share measured path curvature and the run-local "
        "reference lap group, so they are never counted as independent "
        "evidence units."
        if corroborated
        else (
            "Single-strand kinematic diagnostic. The residual equals the "
            "planar sideslip rate and cannot establish tight or loose on "
            "its own; no canonical symptom is attached."
        )
    )
    evidence_status = _unique(
        (
            *(finding.uncertain or ()),
            *(finding.contradictions or ()),
            *(
                note
                for relation in mechanisms
                if relation.relevance == "blocked"
                for note in relation.missing_evidence
            ),
        )
    )
    if (authorized := tuple(
        hypothesis
        for hypothesis in relevant
        if hypothesis.setup_authorized and hypothesis.p19_control is not None
    )):
        control = authorized[0].p19_control
        assert control is not None
        next_action = HandlingKnowledgeNextAction(
            kind="p19_authorized_experiment",
            instruction=(
                f"P19 has authorized one exact controlled experiment through "
                f"{control.control_key} ({control.current_value} → "
                f"{control.proposed_value}) on workflow "
                f"{control.workflow_id}. Record its A/B/A2 stages in "
                "Dial-In; no other change is authorized."
            ),
        )
    elif finding.next_evidence_channels:
        next_action = HandlingKnowledgeNextAction(
            kind="measure",
            instruction=(
                f"{finding.next} Evidence channels: "
                f"{', '.join(finding.next_evidence_channels)}."
            ),
        )
    else:
        next_action = HandlingKnowledgeNextAction(
            kind="inspect_evidence",
            instruction=finding.next,
        )
    return HandlingKnowledgeProjection.build(
        run_id=investigation.run_id,
        session_id=investigation.session_id,
        setup_id=investigation.setup_id,
        case_id=case.case_id,
        case_revision_sha256=case.case_revision_sha256,
        case_sha256=case.case_sha256,
        assessment_id=assessment_id,
        phase=assessment.phase,
        classification=classification,
        canonical_symptom_id=symptom,
        corroborated=corroborated,
        observed_behavior=observed_behavior,
        evidence_qualification=evidence_qualification,
        mechanisms=mechanisms,
        relevant_knowledge=hypotheses,
        countereffects=countereffects,
        evidence_status=evidence_status,
        next_evidence_channels=finding.next_evidence_channels,
        next_action=next_action,
    )


def build_handling_knowledge(
    run_id: str,
    session_id: str,
    assessment_id: str,
    *,
    db_path: str | Path | None = None,
) -> HandlingKnowledgeProjection | None:
    """Load the exact workspace truth and project one assessment's knowledge."""
    # Deferred import: crew_chief_service imports the handling services, so
    # importing it at module level here would create a cycle.
    from racelab_engine.services.crew_chief_service import (
        build_crew_chief_workspace,
    )

    workspace = build_crew_chief_workspace(
        run_id, session_id=session_id, db_path=db_path
    )
    case = workspace.engineering_case
    return build_handling_knowledge_projection(
        investigation=case.handling_investigation,
        case=case,
        knowledge=workspace.engineering_knowledge,
        assessment_id=assessment_id,
    )


__all__ = [
    "build_handling_knowledge",
    "build_handling_knowledge_projection",
]
