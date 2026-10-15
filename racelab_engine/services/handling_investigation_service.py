"""Unified handling investigation: a derived view over existing producer truth.

P35.6 Milestone P2. This module connects the automatic handling-balance
producer to the existing scientific intelligence spine without creating any
new reasoning authority:

    HandlingBalanceReport (P35.6 P1, observation-only)
        -> P35 mechanism graph (candidate knowledge only)
        -> P26 component awareness (P19 projection only)
        -> P32 performance intelligence (measured time, candidate attribution)
        -> evaluated alternative explanations
        -> next inspection from the semantic registry discriminator contracts

Every relation emitted here is informative, never supportive:

- A mechanism is `informed_by_observation` only when a corroborated
  deficit/excess signature aligns with the mechanism's reviewed direction.
  `support_declared` is structurally False everywhere. A kinematic residual
  alone can never inform a tight/loose-family mechanism.
- Component relevance is copied from the P26 projection state; this view can
  only say which families are mechanically relevant and observable.
  `malfunction_declared` is structurally False.
- Performance is associated only by co-occurrence with a P32-owned
  repeatable, candidate-attributed opportunity. `causation_declared` is
  structurally False.
- The two producer strands share measured path curvature and the run-local
  reference group; the dependence is declared explicitly so no downstream
  consumer can count them as independent evidence units.
"""

from __future__ import annotations

from typing import Any, Iterable

from racelab_engine.analysis.handling_balance import analyze_handling_balance
from racelab_engine.analysis.handling_balance_contracts import (
    HANDLING_BALANCE_CONTRACT,
)
from racelab_engine.analysis.sim_integrity import (
    SIM_INTEGRITY_CHANNELS,
    cohort_sim_integrity,
)
from racelab_engine.knowledge.engineering_semantic_registry import semantic_entry
from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
    _CHANNEL_CANONICAL_EQUIVALENTS,
    compile_next_gen_oval_knowledge_graph,
)
from racelab_engine.models.handling_balance import (
    HandlingBalanceReport,
    HandlingClassification,
)
from racelab_engine.models.handling_investigation import (
    HandlingAlternativeExplanation,
    HandlingAssessmentRef,
    HandlingComponentRelation,
    HandlingInvestigationFinding,
    HandlingInvestigationProjection,
    HandlingMechanismRelation,
    HandlingPerformanceAssociation,
)
from racelab_engine.services.import_service import read_telemetry_rows

# ── Phase vocabulary mapping ──────────────────────────────────
# Handling phases (P35.6 producer) -> vehicle-dynamics phases (P35 graph).
_HANDLING_TO_VD_PHASES = {
    "turn_in": ("turn_in",),
    "entry": ("entry",),
    "apex_region": ("center",),
    "center": ("center",),
    "initial_throttle": ("throttle_pickup",),
    "full_throttle_exit": ("exit",),
}
# Handling phases -> P32 opportunity phase families.
_HANDLING_TO_P32_PHASES = {
    "turn_in": frozenset({"turn_in", "entry"}),
    "entry": frozenset({"turn_in", "entry"}),
    "apex_region": frozenset({"center", "apex_region"}),
    "center": frozenset({"center", "apex_region"}),
    "initial_throttle": frozenset({"initial_throttle", "full_throttle_exit"}),
    "full_throttle_exit": frozenset({"initial_throttle", "full_throttle_exit"}),
}

# Reviewed direction-alignment heuristics for informed relevance only. These
# never declare support; the observation direction merely makes the mechanism
# a more informative hypothesis to inspect next.
_DEFICIT_ALIGNED = frozenset({
    "mechanism:center_rotation_deficit",
    "mechanism:power_on_rotation_deficit",
    "mechanism:front_tire_saturation_like",
    "mechanism:front_roll_support_limitation",
    "mechanism:brake_release_rotation_deficit",
})
_EXCESS_ALIGNED = frozenset({
    "mechanism:power_on_rotation_excess",
    "mechanism:rear_tire_saturation_like",
    "mechanism:brake_entry_instability",
})

_QUALIFIED_KINDS = frozenset({
    HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
    HandlingClassification.ROTATION_RESPONSE_DEFICIT,
    HandlingClassification.ROTATION_RESPONSE_EXCESS,
    HandlingClassification.MIXED_PHASE_DEPENDENT,
    HandlingClassification.TRANSIENT_ROTATION_ANOMALY,
    HandlingClassification.STEERING_RESPONSE_ANOMALY,
    HandlingClassification.STEERING_DEMAND_ANOMALY,
})

_EVIDENCE_DEPENDENCE = (
    "The kinematic residual strand (speed x path-curvature - yaw_rate) and the "
    "steering-demand strand (steering per achieved path curvature) both consume "
    "measured path curvature, share the same run-local leave-one-out reference "
    "lap group, and share the underlying measurement noise. They are "
    "complementary relationships, not statistically independent evidence; "
    "two-strand corroboration qualifies a symptom mapping and can never inflate "
    "independent evidence-unit counts.",
    "A run-local reference cannot detect a car-wide uniform balance offset; "
    "observations are lap-relative by design.",
)

_LAP_SPAN_FOR_TIRE_PROGRESSION = 5


def build_handling_balance_report(
    run_id: str,
    overview: Any,
) -> HandlingBalanceReport:
    """Produce the P35.6 P1 handling report exactly like the API route does.

    Shared by the handling-balance route and the Crew Chief workspace so both
    surfaces consume one producer-owned truth.
    """
    columns = sorted(
        HANDLING_BALANCE_CONTRACT.required_channels
        | HANDLING_BALANCE_CONTRACT.preferred_channels
        | {"lap", *SIM_INTEGRITY_CHANNELS}
    )
    rows = read_telemetry_rows(run_id, columns=columns)
    cohort_clear, cohort_cap = cohort_sim_integrity(
        rows,
        overview.laps,
        overview.session.telemetry_rate_hz,
    )
    return analyze_handling_balance(
        rows,
        overview.laps,
        run_id=run_id,
        selected_lap=(
            overview.best_useful_lap.lap_number
            if overview.best_useful_lap is not None else None
        ),
        sim_integrity_clear=cohort_clear,
        sim_integrity_confidence_cap=cohort_cap,
        setup_change_isolated=True,
    )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _component_states(p26: Any) -> dict[str, Any]:
    states: dict[str, Any] = {}
    for state in getattr(p26, "component_states", ()) or ():
        component_id = getattr(state, "component_id", None)
        if component_id:
            states[component_id] = state
    return states


def _component_relation(
    component_id: str,
    states: dict[str, Any],
    p26_unavailable: bool,
) -> HandlingComponentRelation:
    state = states.get(component_id)
    if p26_unavailable or state is None:
        return HandlingComponentRelation(
            component_id=component_id,
            relevance="unavailable",
        )
    raw_relevance = getattr(state, "relevance", None)
    relevance = getattr(raw_relevance, "value", raw_relevance)
    observability = tuple(
        getattr(item, "value", item)
        for item in getattr(state, "observability_states", ()) or ()
    )
    if relevance == "supported":
        relation = "supported"
    elif relevance == "contradicted":
        relation = "contradicted"
    elif any("live_response_observable" in item for item in observability) or bool(
        getattr(state, "available_live_channel_ids", None)
    ):
        relation = "observable"
    else:
        relation = "mechanically_relevant"
    return HandlingComponentRelation(
        component_id=component_id,
        relevance=relation,  # type: ignore[arg-type]
        observability_states=observability,
    )


def _performance_associations(
    phase: str,
    p32: Any,
) -> tuple[tuple[HandlingPerformanceAssociation, ...], tuple[str, ...]]:
    """Associate by co-occurrence with P32-owned repeatable opportunities."""
    wanted = _HANDLING_TO_P32_PHASES.get(phase, frozenset())
    opportunities = tuple(
        getattr(getattr(p32, "opportunity_map", None), "opportunities", ()) or ()
    )
    matched = tuple(
        opportunity for opportunity in opportunities
        if getattr(opportunity, "phase", None) in wanted
    )
    associations: list[HandlingPerformanceAssociation] = []
    blocked_notes: list[str] = []
    for opportunity in matched:
        attribution = str(getattr(opportunity, "attribution_state", ""))
        repeatability = str(getattr(opportunity, "repeatability", ""))
        if attribution != "candidate_only" or repeatability != "repeatable":
            blocked_notes.append(
                f"A measured P32 opportunity in {getattr(opportunity, 'track_region', 'the phase')} "
                f"is not qualified for association (attribution {attribution}, repeatability {repeatability})."
            )
            continue
        delta = getattr(opportunity, "local_delta_s", None)
        associations.append(
            HandlingPerformanceAssociation(
                opportunity_id=str(opportunity.opportunity_id),
                track_region=str(getattr(opportunity, "track_region", "unknown")),
                phase=str(getattr(opportunity, "phase", phase)),
                measured_delta_s=float(delta) if delta is not None else None,
                repeatability=repeatability,
                attribution_state=attribution,
                wording=(
                    f"The {phase} handling observation co-occurs with a repeatable "
                    f"measured time loss of {delta:+.3f} s in "
                    f"{getattr(opportunity, 'track_region', 'the phase')} "
                    f"({getattr(opportunity, 'start_pct', 0):.1f}-"
                    f"{getattr(opportunity, 'end_pct', 0):.1f}%). This is a "
                    "co-occurrence; it does not establish that the observation "
                    "caused the loss or that any component did."
                ),
            )
        )
    return tuple(associations), _unique(blocked_notes)


def _alternative_explanations(
    assessment: Any,
    performance_associations: tuple[HandlingPerformanceAssociation, ...],
) -> tuple[HandlingAlternativeExplanation, ...]:
    corroboration = (
        assessment.phase_observations[0].corroboration
        if assessment.phase_observations else None
    )
    demand_qualified = bool(
        corroboration and corroboration.steering_response_strand_qualified
    )
    residual_qualified = bool(
        corroboration and corroboration.kinematic_residual_strand_qualified
    )
    lap_span = (max(assessment.lap_numbers) - min(assessment.lap_numbers) + 1)

    def explanation(
        explanation_id: str,
        statement: str,
        state: str,
        *basis: str,
    ) -> HandlingAlternativeExplanation:
        return HandlingAlternativeExplanation(
            explanation_id=explanation_id,
            statement=statement,
            state=state,  # type: ignore[arg-type]
            basis=_unique(basis),
        )

    explanations: list[HandlingAlternativeExplanation] = []
    if demand_qualified:
        explanations.append(explanation(
            "driver_demand",
            "A different driver steering demand or racing line could explain "
            "the signature.",
            "plausible_unresolved",
            "The steering-demand strand qualified, so demand per achieved "
            "curvature changed relative to the run-local reference; the "
            "observation cannot by itself separate driver line choice from "
            "vehicle response.",
        ))
    elif residual_qualified:
        explanations.append(explanation(
            "driver_demand",
            "A different driver steering demand or racing line could explain "
            "the residual.",
            "contradicted",
            "The steering-demand strand did not qualify, so steering demand "
            "per achieved curvature stayed inside the run-local envelope "
            "across the qualified lap group.",
        ))
    else:
        explanations.append(explanation(
            "driver_demand",
            "A different driver steering demand or racing line could explain "
            "the signature.",
            "not_observable",
            "Neither strand qualified; driver demand cannot be separated from "
            "vehicle response from this observation.",
        ))
    explanations.append(explanation(
        "entry_speed",
        "Different operating speeds between laps could explain the signature.",
        "contradicted" if demand_qualified else "not_observable",
        "The demand strand only compared laps within the comparable-speed "
        "guard (within 5 m/s of the group median).",
    ))
    if performance_associations:
        explanations.append(explanation(
            "traffic",
            "Traffic interference could explain the measured time loss.",
            "not_observable",
            "P32 owns traffic attribution; the associated opportunity carried "
            "no qualified exposure statement in this projection.",
        ))
    explanations.append(explanation(
        "tire_progression",
        "Tire-state progression within the stint could explain the signature.",
        "plausible_unresolved" if lap_span >= _LAP_SPAN_FOR_TIRE_PROGRESSION
        else "not_observable",
        (
            f"The qualified lap group spans {lap_span} laps, so tire-state "
            "progression is a plausible competing explanation that only "
            "longer controlled evidence can resolve."
            if lap_span >= _LAP_SPAN_FOR_TIRE_PROGRESSION
            else f"The qualified lap group spans only {lap_span} laps; short "
            "runs cannot support tire-degradation conclusions in either "
            "direction."
        ),
    ))
    explanations.append(explanation(
        "shared_source_dependence",
        "The two producer strands share path curvature, the run-local "
        "reference group, and measurement noise.",
        "supported",
        *_EVIDENCE_DEPENDENCE[:1],
    ))
    if not demand_qualified and not residual_qualified:
        explanations.append(explanation(
            "missing_channels",
            "Missing coverage limited the observation to a single strand.",
            "supported",
            "At least one strand lacked the coverage or demand floor required "
            "to qualify.",
        ))
    return tuple(explanations)


def _channel_present(
    channel: str,
    source_channels: frozenset[str],
    lap_numbers: tuple[int, ...],
) -> bool:
    if channel == "lap":
        return bool(lap_numbers)
    equivalents = _CHANNEL_CANONICAL_EQUIVALENTS.get(channel, (channel,))
    return any(
        alias in source_channels for alias in (*equivalents, channel)
    )


def _mechanism_relations(
    phase: str,
    classification: HandlingClassification,
    corroborated: bool,
    source_channels: frozenset[str],
    lap_numbers: tuple[int, ...],
) -> tuple[HandlingMechanismRelation, ...]:
    graph = compile_next_gen_oval_knowledge_graph()
    wanted = set(_HANDLING_TO_VD_PHASES.get(phase, ()))
    direction: str
    if corroborated and classification == HandlingClassification.ROTATION_RESPONSE_DEFICIT:
        direction = "deficit_aligned"
    elif corroborated and classification == HandlingClassification.ROTATION_RESPONSE_EXCESS:
        direction = "excess_aligned"
    else:
        direction = "none"
    relations: list[HandlingMechanismRelation] = []
    for mechanism in graph.mechanisms:
        mechanism_phases = {
            getattr(item, "value", item) for item in mechanism.relevant_phases
        }
        if not mechanism_phases.intersection(wanted):
            continue
        missing = tuple(
            channel for channel in mechanism.required_measured_channels
            if not _channel_present(channel, source_channels, lap_numbers)
        )
        aligned = (
            direction == "deficit_aligned"
            and mechanism.definition_id in _DEFICIT_ALIGNED
        ) or (
            direction == "excess_aligned"
            and mechanism.definition_id in _EXCESS_ALIGNED
        )
        if aligned and not missing:
            relevance = "informed_by_observation"
        elif missing:
            relevance = "blocked"
        else:
            relevance = "applicable"
        relations.append(
            HandlingMechanismRelation(
                mechanism_id=mechanism.definition_id,
                label=mechanism.label,
                relevance=relevance,  # type: ignore[arg-type]
                response_regime=getattr(
                    mechanism.response_regime, "value", mechanism.response_regime
                ),
                applicable_phases=tuple(sorted(mechanism_phases.intersection(wanted))),
                direction=direction,  # type: ignore[arg-type]
                discriminator_contract_ids=mechanism.discriminator_contract_ids,
                p26_component_family_ids=mechanism.p26_component_family_ids,
                required_channels=mechanism.required_measured_channels,
                missing_evidence=tuple(
                    f"Required channel {channel} is not part of the handling "
                    "observation source; the mechanism can be inspected but "
                    "not evaluated from this observation."
                    for channel in missing
                ),
            )
        )
    return tuple(relations)


def _finding(
    assessment: Any,
    p26: Any,
    p32: Any,
    run_id: str,
) -> HandlingInvestigationFinding:
    phase = assessment.phase or "unknown"
    classification = assessment.classification
    corroboration = (
        assessment.phase_observations[0].corroboration
        if assessment.phase_observations else None
    )
    corroborated = bool(corroboration and corroboration.corroborated)
    source_channels = frozenset(assessment.source_channels or ())
    states = _component_states(p26)
    p26_unavailable = bool(getattr(p26, "unavailable_reason", None)) or not states
    mechanisms = _mechanism_relations(
        phase, classification, corroborated, source_channels,
        assessment.lap_numbers,
    )
    components = _unique(
        component_id
        for relation in mechanisms
        for component_id in relation.p26_component_family_ids
    )
    performance, performance_notes = _performance_associations(phase, p32)
    lap_count = len(assessment.lap_numbers)
    where = (
        f"{phase} across {lap_count} eligible laps "
        f"(laps {min(assessment.lap_numbers)}-{max(assessment.lap_numbers)})"
        + (
            f"; {performance[0].track_region}"
            if performance else ""
        )
    )
    if classification == HandlingClassification.ROTATION_RESPONSE_DEFICIT:
        what = (
            "Corroborated reduced rotation response: the kinematic residual "
            "and the steering-demand strand agree."
        )
    elif classification == HandlingClassification.ROTATION_RESPONSE_EXCESS:
        what = (
            "Corroborated excess rotation-like response: the kinematic "
            "residual and the steering-demand strand agree."
        )
    elif classification == HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION:
        what = (
            "Kinematic residual observation (the planar sideslip-rate "
            "identity) without steering-response corroboration."
        )
    elif classification == HandlingClassification.STEERING_DEMAND_ANOMALY:
        what = (
            "Steering-demand divergence without a corroborating kinematic "
            "residual."
        )
    elif classification == HandlingClassification.MIXED_PHASE_DEPENDENT:
        what = "Opposing phase-local response signatures; no single label is justified."
    elif classification == HandlingClassification.TRANSIENT_ROTATION_ANOMALY:
        what = "Transient rotation anomaly without a sustained response signature."
    else:
        what = "Steering-response anomaly without a sustained response signature."
    if corroboration and corroboration.steering_response_strand_qualified:
        driver = (
            f"Steering demand per achieved curvature was "
            f"{corroboration.steering_response_direction} relative to the "
            "run-local reference on comparable-speed laps; driver line "
            "choice cannot be separated from vehicle response by this "
            "observation alone."
        )
    else:
        driver = (
            "The steering-demand strand did not qualify; driver-input change "
            "cannot be separated from vehicle response from this observation."
        )
    observation = (
        assessment.phase_observations[0] if assessment.phase_observations else None
    )
    residual = (
        observation.rotation_response_deficit_median_rad_s
        if observation is not None else None
    )
    if residual is not None:
        response = (
            f"Median kinematic residual {residual:+.4f} rad/s against the "
            "path-kinematic reference; this equals the planar sideslip-rate "
            "identity and is blind to a constant sideslip angle."
        )
    else:
        response = "No qualified kinematic residual was measured for this phase."
    contradictions = _unique((
        *tuple(assessment.contradicting_evidence or ()),
        *_EVIDENCE_DEPENDENCE[1:],
    ))
    uncertain = _unique((
        "Mechanical cause unresolved: no mechanism is declared supported by "
        "this observation.",
        "A car-wide uniform balance offset cannot be detected from a "
        "run-local reference.",
        *performance_notes,
    ))
    relation_entry = semantic_entry("steering_wheel_to_yaw")
    next_contracts = _unique(
        contract_id
        for relation in mechanisms
        for contract_id in relation.discriminator_contract_ids
    )
    next_evidence = _unique(
        relation_entry.required_channel_ids
        if relation_entry is not None
        else ("steering_deg", "yaw_rate")
    )
    if classification == HandlingClassification.MIXED_PHASE_DEPENDENT:
        next_step = (
            "Review per-phase matched steering and yaw traces; no single "
            "whole-corner label is justified."
        )
    elif next_contracts:
        next_step = (
            "Review matched steering and yaw traces across the qualified lap "
            f"group to separate driver line from vehicle response; the "
            f"reviewed discriminator {next_contracts[0]} applies."
        )
    else:
        next_step = (
            "Review matched steering and yaw traces across the qualified lap "
            "group."
        )
    return HandlingInvestigationFinding(
        assessment_id=assessment.assessment_id,
        phase=phase,
        what=what,
        where=where,
        driver=driver,
        response=response,
        mechanisms=mechanisms,
        components=tuple(
            _component_relation(component_id, states, p26_unavailable)
            for component_id in components
        ),
        performance=performance,
        contradictions=contradictions,
        uncertain=uncertain,
        next=next_step,
        next_evidence_channels=next_evidence,
    )


def build_handling_investigation(
    *,
    run_id: str,
    session_id: str,
    setup_id: str,
    handling_report: HandlingBalanceReport,
    p26: Any,
    p32: Any,
) -> HandlingInvestigationProjection | None:
    """Project the unified handling investigation, or None when nothing qualifies."""
    assessments = tuple(
        assessment for assessment in handling_report.assessments
        if assessment.classification in _QUALIFIED_KINDS
    )
    if not assessments:
        return None
    refs = tuple(
        HandlingAssessmentRef(
            assessment_id=assessment.assessment_id,
            run_id=run_id,
            phase=assessment.phase or "unknown",
            classification=assessment.classification,
            canonical_symptom_id=assessment.canonical_symptom_id,
            corroborated=bool(
                assessment.canonical_symptom_id is not None
            ),
            lap_numbers=assessment.lap_numbers,
        )
        for assessment in assessments
    )
    findings = tuple(
        _finding(assessment, p26, p32, run_id)
        for assessment in assessments
    )
    return HandlingInvestigationProjection.build(
        run_id=run_id,
        session_id=session_id,
        setup_id=setup_id,
        handling_report_classification=handling_report.classification,
        assessment_refs=refs,
        evidence_dependence=_EVIDENCE_DEPENDENCE,
        findings=findings,
    )


__all__ = [
    "build_handling_balance_report",
    "build_handling_investigation",
]
