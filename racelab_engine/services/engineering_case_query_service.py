"""Deterministic whole-case Smart Engineer question projection."""

from __future__ import annotations

import re
from dataclasses import dataclass

from racelab_engine.models.crew_chief import CrewChiefWorkspace


@dataclass(frozen=True)
class EngineeringCaseQueryAnswer:
    headline: str
    answer: str
    source_artifact_ids: tuple[str, ...]
    blocker_reasons: tuple[str, ...] = ()
    authority_ceiling: str = "evidence_only"
    action_authorized: bool = False


def _normalized(question: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", question.casefold())).strip()


def answer_engineering_case_question(
    question: str,
    workspace: CrewChiefWorkspace,
) -> EngineeringCaseQueryAnswer | None:
    normalized = _normalized(question)
    case = workspace.engineering_case

    if any(value in normalized for value in ("exact current next move", "p19 need next", "done when")):
        mission = case.mission
        return EngineeringCaseQueryAnswer(
            headline="Current Engineering Case mission",
            answer=mission.next,
            source_artifact_ids=mission.source_artifact_ids,
            blocker_reasons=() if mission.setup_authorized else tuple(workspace.terminal_decision.blocker_reasons),
            authority_ceiling=mission.source_authority,
            action_authorized=mission.setup_authorized,
        )

    if any(value in normalized for value in ("where did the loss originate", "where did it carry", "carried downstream", "straight loss inherited")):
        performance = workspace.performance_intelligence
        opportunity = next(iter(performance.opportunity_map.opportunities), None)
        if opportunity is None:
            return EngineeringCaseQueryAnswer(
                headline="Measured origin and carry",
                answer="No qualified performance opportunity is available in this exact case revision.",
                source_artifact_ids=(),
                blocker_reasons=tuple(performance.blockers),
            )
        carry = opportunity.following_phase_effect_s
        origin = opportunity.origin_kind.value.replace("_", " ")
        answer = f"The measured opportunity originates in {origin} at {opportunity.start_pct:.1f}–{opportunity.end_pct:.1f}%."
        if carry is not None:
            answer += f" Its measured downstream carry is {carry:+.3f} s."
        return EngineeringCaseQueryAnswer(
            headline="Measured origin and carry",
            answer=answer,
            source_artifact_ids=(opportunity.opportunity_id,),
            blocker_reasons=tuple(opportunity.contradictions),
        )

    if any(value in normalized for value in ("dynamic response", "steering yaw response", "brake release", "changed through the stint")):
        artifacts = case.response_artifacts
        if not artifacts:
            return EngineeringCaseQueryAnswer(
                headline="Qualified response signatures",
                answer="No qualified response artifact exists in this exact case revision.",
                source_artifact_ids=(),
                blocker_reasons=tuple(
                    deficit.blocker_reasons[0] for deficit in case.evidence_deficits[:3]
                ),
            )
        summary = "; ".join(
            f"{item.relation.replace('_', ' ')} in {item.phase} at {item.lap_pct_start:.1f}–{item.lap_pct_end:.1f}% ({item.operational_evidence.repetition_count} independent laps)"
            for item in artifacts[:4]
        )
        return EngineeringCaseQueryAnswer(
            headline="Qualified response signatures",
            answer=summary + ". These are observations, not setup authority.",
            source_artifact_ids=tuple(item.artifact_id for item in artifacts[:4]),
        )

    if any(value in normalized for value in ("mechanisms remain", "strongest contradiction", "separate the leading", "strongest support")):
        dynamics = workspace.vehicle_dynamics
        candidates = tuple(item.mechanism_id for item in dynamics.mechanism_separation if item.state == "alive")
        answer = (
            "Remaining typed mechanisms: " + ", ".join(candidates[:6]) + ". "
            if candidates
            else "No mechanism has earned a current alive state. "
        )
        contradiction = next(
            (
                item.summary
                for item in dynamics.focus_artifacts
                if item.artifact_id == dynamics.strongest_contradiction_artifact_id
            ),
            "No stronger contradiction artifact is available.",
        )
        answer += f"Strongest contradiction: {contradiction}"
        return EngineeringCaseQueryAnswer(
            headline="Mechanism separation",
            answer=answer,
            source_artifact_ids=tuple(
                dict.fromkeys(
                    artifact_id
                    for item in dynamics.mechanism_separation
                    for artifact_id in (*item.support_artifact_ids, *item.contradiction_artifact_ids)
                )
            ),
            blocker_reasons=tuple(dynamics.blocker_reasons),
        )

    if any(value in normalized for value in ("quantities are observable", "component families", "unobservable")):
        quantities = tuple(item.quantity_id for item in case.quantity_observability)
        return EngineeringCaseQueryAnswer(
            headline="Quantity and component observability",
            answer=(
                "Currently observable quantities: " + ", ".join(quantities) + ". Component support remains withheld."
                if quantities
                else "No P26 quantity is currently observable through exact response metric lineage."
            ),
            source_artifact_ids=tuple(
                dict.fromkeys(
                    artifact_id
                    for item in case.quantity_observability
                    for artifact_id in item.response_artifact_ids
                )
            ),
        )

    if any(value in normalized for value in ("why is this setup effect", "not p19 testable", "measurement is missing", "countereffect")):
        mission = case.mission
        blocked = tuple(
            item
            for item in case.effect_readiness
            if item.state != "p19_testable"
        )
        if not blocked:
            return EngineeringCaseQueryAnswer(
                headline="Setup-effect readiness",
                answer="The current exact P19 projection owns the only testable effect. Smart Engineer adds no setup instruction.",
                source_artifact_ids=mission.source_artifact_ids,
                authority_ceiling=mission.source_authority,
            )
        effect = blocked[0]
        deficits = tuple(
            item for item in case.evidence_deficits if item.deficit_id in effect.deficit_ids
        )
        return EngineeringCaseQueryAnswer(
            headline="Why the effect is not P19-testable",
            answer=(
                f"{effect.effect_id} is {effect.state.replace('_', ' ')}. "
                + " ".join(item.blocker_reasons[0] for item in deficits)
            ),
            source_artifact_ids=effect.response_artifact_ids,
            blocker_reasons=tuple(item.blocker_reasons[0] for item in deficits),
        )

    if any(value in normalized for value in ("investigation established", "already been inspected", "crew asking", "critic blocking")):
        folded = workspace.folded_state
        return EngineeringCaseQueryAnswer(
            headline="Crew investigation state",
            answer=(
                f"Current subgoal: {workspace.current_subgoal.title if workspace.current_subgoal else 'none'}. "
                f"Completed inspections: {len(folded.completed_tool_ids) if folded else 0}. "
                f"Critic: {workspace.critique.outcome}."
            ),
            source_artifact_ids=tuple(
                workspace.latest_tool_result.artifact_ids
                if workspace.latest_tool_result is not None
                else ()
            ),
            blocker_reasons=tuple(workspace.critique.findings),
        )

    if any(value in normalized for value in ("closest controlled case", "same control produce", "history shorten")):
        prior = workspace.learning_prior
        if not prior.useful_prior_investigations:
            return EngineeringCaseQueryAnswer(
                headline="Exact-context controlled history",
                answer="No qualified independent controlled history is available for this exact case context.",
                source_artifact_ids=(),
                blocker_reasons=tuple(prior.blocker_reasons),
            )
        item = prior.useful_prior_investigations[0]
        return EngineeringCaseQueryAnswer(
            headline="Exact-context controlled history",
            answer=f"Closest retained controlled case: {item.experience_id}. History remains attention-only.",
            source_artifact_ids=tuple(
                reference.reference_id
                for reference in prior.evidence_references
                if reference.experience_id == item.experience_id
            ),
            authority_ceiling="attention_only",
        )

    return None


__all__ = ["EngineeringCaseQueryAnswer", "answer_engineering_case_question"]
