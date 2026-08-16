"""One-test crew-chief evidence packets.

Packets are intentionally strict: a setup test is never emitted without a
repeatable time opportunity, an eligible telemetry event, and Test Director
approval.  Secondary hypotheses remain internal until the primary is blocked
or fails.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.analysis.evidence_contracts import EvidenceState
from racelab_engine.analysis.test_director import (
    ControlledTestCard,
    MeasurementMission,
    TestEvidenceLink,
    build_controlled_test,
)
from racelab_engine.knowledge.setup.loader import load_setup_knowledge


class PacketModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OpportunityEvidence(PacketModel):
    start_pct: float = Field(ge=0.0, le=100.0)
    end_pct: float = Field(ge=0.0, le=100.0)
    phase: str
    observed_time_loss_s: float | None = Field(default=None, ge=0.0)
    empirical_noise_s: float | None = Field(default=None, ge=0.0)
    alignment_confidence: float = Field(ge=0.0, le=1.0)
    repeatable: bool
    evidence_links: tuple[TestEvidenceLink, ...]
    source_channels: tuple[str, ...]
    supporting_evidence: tuple[str, ...] = ()
    contradictory_evidence: tuple[str, ...] = ()

    @property
    def evidence_event_ids(self) -> tuple[str, ...]:
        return tuple(link.event_id for link in self.evidence_links)


class CauseCandidate(PacketModel):
    effect_id: str
    experiment_factor_id: str
    cause_bucket: str
    control_key: str
    direction_sign: Literal[-1, 1]
    score: float = Field(ge=0.0, le=1.0)
    hypothesis: str
    success_metrics: tuple[str, ...]
    countereffects: tuple[str, ...]
    supporting_event_ids: tuple[str, ...]
    blocked_reasons: tuple[str, ...] = ()
    score_components: dict[str, float] = Field(default_factory=dict)
    score_basis: str = (
        "Ordinal mechanism-evidence score; not a calibrated probability or predicted lap-time gain."
    )


class KaizenEvidencePacket(PacketModel):
    decision: Literal["test", "measure"]
    opportunity: OpportunityEvidence
    canonical_symptom: str
    primary_cause_bucket: str | None
    evidence_state: EvidenceState
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_is_calibrated_probability: bool = False
    confidence_basis: str = "Ordinal evidence-strength score; not a calibrated probability."
    recommendation_score_components: dict[str, float] = Field(default_factory=dict)
    recommendation_score_basis: str | None = None
    blockers: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    contradictory_evidence: tuple[str, ...]
    primary_test: ControlledTestCard | None = None
    measurement_mission: MeasurementMission | None = None
    held_back_alternatives: int = Field(ge=0)
    race_mode_summary: str
    learning_mode_explanation: str


def build_kaizen_packet(
    *,
    opportunity: OpportunityEvidence,
    canonical_symptom: str,
    candidates: list[CauseCandidate],
    current_setup_values: dict[str, object],
    eligible_baseline_laps: int,
    context_matched: bool,
    driver_matched: bool,
    sim_integrity_clear: bool | None,
    legal_values_by_control: dict[str, list[object]] | None = None,
    legal_value_provenance_by_control: dict[str, dict[str, list[str]]] | None = None,
    external_blockers: list[str] | tuple[str, ...] | None = None,
) -> KaizenEvidencePacket:
    opportunity_blockers: list[str] = list(external_blockers or ())
    canonical_vocabulary = {
        entry.canonical_symptom for entry in load_setup_knowledge().symptom_vocabulary
    }
    if canonical_symptom not in canonical_vocabulary:
        opportunity_blockers.append("The symptom is not part of the canonical setup vocabulary.")
    if opportunity.observed_time_loss_s is None:
        opportunity_blockers.append("Target-phase time loss is unavailable.")
    if opportunity.end_pct <= opportunity.start_pct:
        opportunity_blockers.append("Opportunity must cover a non-zero physical track-position window.")
    if not opportunity.source_channels:
        opportunity_blockers.append("No archived source channels support the opportunity.")
    if not opportunity.supporting_evidence:
        opportunity_blockers.append("No supporting telemetry evidence was supplied for the opportunity.")
    if opportunity.empirical_noise_s is None:
        opportunity_blockers.append("Driver/run noise is unavailable.")
    elif (
        opportunity.observed_time_loss_s is not None
        and opportunity.observed_time_loss_s <= opportunity.empirical_noise_s
    ):
        opportunity_blockers.append("Observed time loss does not exceed normal variation.")
    if not opportunity.repeatable:
        opportunity_blockers.append("The opportunity is not repeatable across eligible laps.")
    if opportunity.alignment_confidence < 0.8:
        opportunity_blockers.append("Local physical-position alignment confidence is below 80%.")
    if not opportunity.evidence_links:
        opportunity_blockers.append("No eligible telemetry event identifies the opportunity.")

    eligible_candidates = [
        candidate
        for candidate in candidates
        if not candidate.blocked_reasons
        and set(candidate.supporting_event_ids) & set(opportunity.evidence_event_ids)
    ]
    eligible_candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    primary = eligible_candidates[0] if eligible_candidates else None
    if primary is None:
        opportunity_blockers.extend(
            reason
            for candidate in candidates
            for reason in candidate.blocked_reasons
        )
        opportunity_blockers.append("No setup cause is linked to the eligible opportunity evidence.")

    if primary is not None and not opportunity_blockers:
        director = build_controlled_test(
            control_key=primary.control_key,
            current_value=current_setup_values.get(primary.control_key),
            direction_sign=primary.direction_sign,
            setup_effect_id=primary.effect_id,
            experiment_factor_id=primary.experiment_factor_id,
            hypothesis=primary.hypothesis,
            target_phase=opportunity.phase,
            success_metrics=list(primary.success_metrics),
            countereffects=list(primary.countereffects),
            evidence_links=[
                link
                for link in opportunity.evidence_links
                if link.event_id in primary.supporting_event_ids
            ],
            eligible_baseline_laps=eligible_baseline_laps,
            context_matched=context_matched,
            driver_matched=driver_matched,
            sim_integrity_clear=sim_integrity_clear,
            legal_values=(legal_values_by_control or {}).get(primary.control_key),
            legal_value_provenance=(legal_value_provenance_by_control or {}).get(primary.control_key),
            external_blockers=opportunity_blockers,
        )
    else:
        # The director supplies a complete mission; a supported placeholder key
        # is used only to reach its blocked path and is never exposed as advice.
        director = build_controlled_test(
            control_key="cross_weight_percent",
            current_value=current_setup_values.get("cross_weight_percent"),
            direction_sign=1,
            hypothesis="Measure the unresolved target-phase opportunity.",
            target_phase=opportunity.phase,
            success_metrics=[],
            countereffects=[],
            evidence_links=[],
            eligible_baseline_laps=eligible_baseline_laps,
            context_matched=context_matched,
            driver_matched=driver_matched,
            sim_integrity_clear=sim_integrity_clear,
            legal_values=(legal_values_by_control or {}).get("cross_weight_percent"),
            legal_value_provenance=(legal_value_provenance_by_control or {}).get("cross_weight_percent"),
            external_blockers=opportunity_blockers,
        )

    if opportunity_blockers or not director.ready or director.card is None:
        mission = director.mission
        assert mission is not None
        blockers = tuple(dict.fromkeys([*opportunity_blockers, *mission.blockers]))
        return KaizenEvidencePacket(
            decision="measure",
            opportunity=opportunity,
            canonical_symptom=canonical_symptom,
            primary_cause_bucket=None,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            confidence_score=0.0,
            blockers=blockers,
            supporting_evidence=opportunity.supporting_evidence,
            contradictory_evidence=opportunity.contradictory_evidence,
            measurement_mission=mission.model_copy(update={"blockers": blockers}),
            held_back_alternatives=len(candidates),
            race_mode_summary="No setup change is justified yet. Run the measurement mission.",
            learning_mode_explanation=(
                "The app found a possible opportunity but cannot isolate one setup cause with "
                "matched, repeatable evidence. The mission collects the missing proof."
            ),
        )

    confidence = min(
        0.95,
        primary.score,
        opportunity.alignment_confidence,
        0.85 if opportunity.repeatable else 0.4,
    )
    if opportunity.contradictory_evidence:
        confidence = min(confidence, 0.65)
    runner_up = eligible_candidates[1] if len(eligible_candidates) > 1 else None
    ranking_explanation = ""
    if runner_up is not None:
        component_names = {
            "eligible_event_link",
            "observed_mechanism_coverage",
            "evidence_readiness",
            "countereffect_margin",
            "blocker_clear",
            "personal_response_support",
        } & (set(primary.score_components) | set(runner_up.score_components))
        differentiator = max(
            component_names,
            key=lambda name: primary.score_components.get(name, 0.0) - runner_up.score_components.get(name, 0.0),
            default="combined evidence",
        )
        ranking_explanation = (
            f" It ranked ahead of the next eligible hypothesis ({primary.score:.3f} versus "
            f"{runner_up.score:.3f}), led by {differentiator.replace('_', ' ')}."
        )
    return KaizenEvidencePacket(
        decision="test",
        opportunity=opportunity,
        canonical_symptom=canonical_symptom,
        primary_cause_bucket=primary.cause_bucket,
        evidence_state=EvidenceState.NEEDS_CONFIRMATION,
        confidence_score=round(confidence, 3),
        recommendation_score_components=primary.score_components,
        recommendation_score_basis=primary.score_basis,
        blockers=(),
        supporting_evidence=opportunity.supporting_evidence,
        contradictory_evidence=opportunity.contradictory_evidence,
        primary_test=director.card,
        held_back_alternatives=max(0, len(eligible_candidates) - 1),
        race_mode_summary=f"Test one change: {director.card.exact_change}",
        learning_mode_explanation=(
            f"The repeatable loss begins in the {opportunity.phase} phase. "
            f"{primary.hypothesis}{ranking_explanation} The A/B/A2 card tests that mechanism while holding every "
            "other supported control constant."
        ),
    )


__all__ = [
    "CauseCandidate",
    "KaizenEvidencePacket",
    "OpportunityEvidence",
    "build_kaizen_packet",
]
