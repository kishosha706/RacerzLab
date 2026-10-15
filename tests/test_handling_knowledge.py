"""Adversarial tests for the P35.6 P4 handling-knowledge projection.

Every test proves what the Dial-In handoff projection must NOT claim as
well as what it must: no fabricated driver wording, no symptom without
two-strand corroboration, no setup authority except an exact mirrored P19
control, no causal language, and no knowledge for unsupported
vehicle/setup capabilities. The pure builder is tested directly; the
loader (which requires a full workspace build) is exercised through the
route in the API contract suite.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.models.engineering_knowledge import (
    CurrentEngineeringKnowledgeProjection,
    CurrentKnowledgeHypothesis,
    P19TestableControl,
)
from racelab_engine.models.handling_balance import (
    HandlingBalanceAssessment,
    HandlingBalanceReport,
    HandlingClassification,
    HandlingCorroboration,
    HandlingPhaseObservation,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.handling_investigation import (
    HandlingInvestigationProjection,
)
from racelab_engine.services.handling_investigation_service import (
    build_handling_investigation,
)
from racelab_engine.services.handling_knowledge_service import (
    build_handling_knowledge_projection,
)

RUN_ID = "p356k-run"
SESSION_ID = "p356k-session"
SETUP_ID = "setup-p356k"
CASE_ID = "p3543case_" + "e" * 24
REVISION = "a" * 64
CASE_SHA = "b" * 64


def _observation(*, demand_qualified: bool) -> HandlingPhaseObservation:
    return HandlingPhaseObservation(
        phase="center",
        eligible_laps=6,
        sample_bins=120,
        steering_demand_floor_deg=3.0,
        coverage_fraction=0.95,
        rotation_response_deficit_median_rad_s=0.03,
        steering_demand_relative_deviation_scale_units=2.5 if demand_qualified else None,
        corroboration=HandlingCorroboration(
            kinematic_residual_strand_qualified=True,
            steering_response_strand_qualified=demand_qualified,
            steering_response_direction="elevated" if demand_qualified else None,
            aligned=demand_qualified,
            corroborated=demand_qualified,
        ),
    )


def _assessment(
    classification: HandlingClassification,
    *,
    symptom: str | None = None,
    demand_qualified: bool = False,
    assessment_id: str = "hba_" + "1" * 24,
) -> HandlingBalanceAssessment:
    return HandlingBalanceAssessment(
        assessment_id=assessment_id,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        lap_numbers=(1, 2, 3, 4, 5, 6),
        phase="center",
        classification=classification,
        canonical_symptom_id=symptom,
        observation_text=f"{classification.value} repeats in center.",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        confidence_score=0.45,
        repeatability="run-local envelope",
        source_channels=(
            "lap_dist_pct_100", "session_time", "speed_mps", "yaw_rate",
            "steering_deg", "lat_accel",
        ),
        contradicting_evidence=(
            "The reference is actual-path curvature, not the driver's intended path.",
        ),
        phase_observations=(_observation(demand_qualified=demand_qualified),),
    )


def _report(*assessments: HandlingBalanceAssessment) -> HandlingBalanceReport:
    return HandlingBalanceReport(
        run_id=RUN_ID,
        session_id=SESSION_ID,
        selected_lap=4,
        eligible_laps=6,
        reference_lap_count=6,
        classification=assessments[0].classification,
        assessments=assessments,
    )


def _p26_stub() -> SimpleNamespace:
    state = SimpleNamespace(
        component_id="anti_roll_bars",
        relevance="candidate",
        observability_states=("live_response_observable",),
        available_live_channel_ids=("steering_deg", "yaw_rate"),
    )
    return SimpleNamespace(
        component_states=(state,),
        knowledge_graph_sha256="p26" * 22,
        unavailable_reason=None,
        setup_id=SETUP_ID,
        setup_snapshot_sha256="2" * 64,
    )


def _p32_stub() -> SimpleNamespace:
    opportunity = SimpleNamespace(
        opportunity_id="p32o-opportunity",
        phase="center",
        track_region="Turn 1",
        attribution_state="candidate_only",
        repeatability="repeatable",
        local_delta_s=0.12,
        start_pct=20.0,
        end_pct=30.0,
    )
    return SimpleNamespace(
        projection_sha256="p32" * 22,
        opportunity_map=SimpleNamespace(opportunities=(opportunity,)),
    )


def _investigation(
    classification: HandlingClassification,
    *,
    demand_qualified: bool = False,
) -> HandlingInvestigationProjection:
    assessment = _assessment(
        classification,
        symptom=(
            "tight_center"
            if classification == HandlingClassification.ROTATION_RESPONSE_DEFICIT
            and demand_qualified
            else None
        ),
        demand_qualified=demand_qualified,
    )
    projection = build_handling_investigation(
        run_id=RUN_ID,
        session_id=SESSION_ID,
        setup_id=SETUP_ID,
        handling_report=_report(assessment),
        p26=_p26_stub(),
        p32=_p32_stub(),
    )
    assert projection is not None
    return projection


def _hypothesis(
    *,
    index: int = 0,
    level: str = "measurable_hypothesis",
    mechanism_ids: tuple[str, ...] = ("mechanism:center_rotation_deficit",),
    knowledge_applicability: str = "applicable",
    setup_authorized: bool = False,
    p19_control: P19TestableControl | None = None,
) -> CurrentKnowledgeHypothesis:
    authority = (
        "exact_p19_projection"
        if setup_authorized
        else "measurement_only"
        if level == "measurable_hypothesis"
        else "knowledge_only"
    )
    effect_id = f"effect:test_{index}"
    return CurrentKnowledgeHypothesis(
        bridge_id="p351b_" + hex(index + 1)[2:].rjust(24, "0"),
        effect_id=effect_id,
        setup_area="arb",
        physical_role="roll stiffness",
        direction_sign=-1,
        experiment_factor_id="arb_adjustment" if setup_authorized else None,
        level=level,  # type: ignore[arg-type]
        relevance="supported_candidate",
        p35_mechanism_ids=mechanism_ids,
        countereffect_ids=("countereffect:platform_margin",),
        missing_evidence=("Exact response evidence is unavailable.",),
        knowledge_applicability=knowledge_applicability,  # type: ignore[arg-type]
        runtime_evidence_state="unavailable",
        authority=authority,  # type: ignore[arg-type]
        setup_authorized=setup_authorized,
        p19_control=(
            p19_control.model_copy(update={"effect_id": effect_id})
            if p19_control is not None
            else None
        ),
    )


def _knowledge(*hypotheses: CurrentKnowledgeHypothesis) -> CurrentEngineeringKnowledgeProjection:
    return CurrentEngineeringKnowledgeProjection.build(
        run_id=RUN_ID,
        session_id=SESSION_ID,
        p19_reasoning_snapshot_sha256="1" * 64,
        p20_state_revision="2" * 64,
        p26_knowledge_graph_sha256="3" * 64,
        p32_projection_sha256="4" * 64,
        p35_assessment_sha256="5" * 64,
        p33_projection_sha256="6" * 64,
        bridge_coverage_sha256="7" * 64,
        hypotheses=hypotheses,
    )


def _case(
    *,
    run_id: str = RUN_ID,
    session_id: str = SESSION_ID,
    setup_id: str = SETUP_ID,
) -> SimpleNamespace:
    return SimpleNamespace(
        case_id=CASE_ID,
        case_revision_sha256=REVISION,
        case_sha256=CASE_SHA,
        run_id=run_id,
        session_id=session_id,
        setup_id=setup_id,
    )


def _projection(
    *,
    investigation: HandlingInvestigationProjection | None,
    knowledge: CurrentEngineeringKnowledgeProjection,
    case: SimpleNamespace | None = None,
    assessment_id: str = "hba_" + "1" * 24,
):
    return build_handling_knowledge_projection(
        investigation=investigation,
        case=case if case is not None else _case(),
        knowledge=knowledge,
        assessment_id=assessment_id,
    )


# ── 1. A corroborated observation carries its legitimate symptom ──

def test_corroborated_observation_carries_symptom_without_authority():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
    )
    assert projection is not None
    assert projection.corroborated is True
    assert projection.canonical_symptom_id == "tight_center"
    assert "not driver testimony" in projection.observed_behavior
    assert projection.setup_authorized is False
    assert projection.authority == "derived_observation_view"
    assert projection.case_id == CASE_ID
    assert projection.case_revision_sha256 == REVISION
    assert projection.case_sha256 == CASE_SHA


# ── 2. The Talladega residual-only case stays symptom-free ──

def test_residual_only_observation_carries_no_symptom():
    investigation = _investigation(
        HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
        demand_qualified=False,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
    )
    assert projection is not None
    assert projection.corroborated is False
    assert projection.canonical_symptom_id is None
    assert "tight" not in projection.observed_behavior.casefold()
    assert "loose" not in projection.observed_behavior.casefold()
    assert "cannot establish tight or loose" in projection.evidence_qualification
    assert projection.next_action.kind in {"inspect_evidence", "measure"}
    assert projection.next_action.kind != "p19_authorized_experiment"


# ── 3. Missing telemetry or unknown assessment fails closed ──

def test_missing_investigation_fails_closed():
    assert _projection(
        investigation=None,
        knowledge=_knowledge(_hypothesis()),
    ) is None


def test_unknown_assessment_fails_closed():
    investigation = _investigation(
        HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
    )
    assert _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
        assessment_id="hba_" + "2" * 24,
    ) is None


# ── 4. Contradictory evidence stays visible ──

def test_contradictions_and_uncertain_notes_carry_through():
    investigation = _investigation(
        HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
    )
    assert projection is not None
    assert any(
        "actual-path curvature" in note
        for note in projection.evidence_status
    )


# ── 5. Foreign case identity fails closed ──

def test_foreign_case_identity_fails_closed():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    assert _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
        case=_case(run_id="foreign-run"),
    ) is None


# ── 6. Exact case identity is bound into the projection ──

def test_exact_case_identity_is_bound():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
    )
    assert projection is not None
    assert (
        projection.case_id,
        projection.case_revision_sha256,
        projection.case_sha256,
    ) == (CASE_ID, REVISION, CASE_SHA)


# ── 7. Unsupported vehicle/setup capability is filtered ──

def test_unsupported_capability_knowledge_is_filtered():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(
            _hypothesis(knowledge_applicability="unsupported"),
            _hypothesis(index=1, knowledge_applicability="blocked_by_build"),
        ),
    )
    assert projection is not None
    assert [
        item.knowledge_applicability
        for item in projection.relevant_knowledge
        if item.knowledge_applicability != "educational_only"
    ] == ["blocked_by_build"]
    assert all(
        item.setup_authorized is False
        and item.p19_control is None
        for item in projection.relevant_knowledge
    )


# ── 8. Missing mechanical evidence is declared per mechanism ──

def test_blocked_mechanisms_declare_missing_evidence():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
    )
    assert projection is not None
    blocked = [
        item for item in projection.mechanisms if item.relevance == "blocked"
    ]
    assert blocked
    assert all(item.missing_evidence for item in blocked)
    assert all(item.support_declared is False for item in projection.mechanisms)


# ── 9. No causal language anywhere in the projection ──

def test_no_causal_language():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
    )
    assert projection is not None
    serialized = str(projection.model_dump(mode="json")).casefold()
    assert "caused the" not in serialized
    assert "is the cause" not in serialized
    assert "driverintent" not in serialized
    assert "driver said" not in serialized
    assert "the driver reported" not in serialized


# ── 10. No fabricated driver wording ──

def test_no_fabricated_driver_wording():
    investigation = _investigation(
        HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(_hypothesis()),
    )
    assert projection is not None
    assert "complaint" not in projection.observed_behavior.casefold()
    assert "driver feels" not in projection.observed_behavior.casefold()
    assert projection.p19_authority_unchanged is True


def test_knowledge_only_catalog_entries_stay_visible_and_non_authorizing():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(
            _hypothesis(level="educational_knowledge"),
        ),
    )
    assert projection is not None
    assert any(
        item.relevance == "knowledge_only"
        for item in projection.relevant_knowledge
    )
    assert all(
        item.setup_authorized is False and item.p19_control is None
        for item in projection.relevant_knowledge
    )
    assert projection.next_action.kind != "p19_authorized_experiment"


def test_static_catalog_entries_cover_unmapped_mechanisms():
    investigation = _investigation(
        HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(
            _hypothesis(mechanism_ids=("mechanism:traction_limitation_like",)),
        ),
    )
    assert projection is not None
    educational = [
        item
        for item in projection.relevant_knowledge
        if item.knowledge_applicability == "educational_only"
    ]
    assert educational
    assert all(
        item.level == "educational_knowledge"
        and item.authority == "knowledge_only"
        and item.setup_authorized is False
        and item.p19_control is None
        for item in educational
    )
    assert all(
        any(
            mechanism_id in {relation.mechanism_id for relation in projection.mechanisms}
            for mechanism_id in item.p35_mechanism_ids
        )
        for item in educational
    )
    assert projection.canonical_symptom_id is None
    assert projection.corroborated is False


# ── 11. P19 withholding setup keeps knowledge non-authorizing ──

def test_p19_withholding_keeps_next_action_inspection():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(
            _hypothesis(level="measurable_hypothesis"),
        ),
    )
    assert projection is not None
    assert projection.next_action.kind != "p19_authorized_experiment"
    assert all(
        hypothesis.setup_authorized is False
        for hypothesis in projection.relevant_knowledge
    )
    assert all(
        hypothesis.p19_control is None
        for hypothesis in projection.relevant_knowledge
    )


# ── 12. An exact P19-authorized experiment is reported, not created ──

def test_p19_authorized_experiment_is_reported_not_created():
    investigation = _investigation(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    control = P19TestableControl(
        effect_id="effect:test",
        control_key="arb_adjustment",
        direction_sign=-1,
        experiment_factor_id="arb_adjustment",
        current_value="4",
        proposed_value="5",
        workflow_id="cwf-exact",
        workflow_revision="w" * 64,
        source_event_ids=("cce_exact",),
    )
    projection = _projection(
        investigation=investigation,
        knowledge=_knowledge(
            _hypothesis(
                level="p19_testable_control",
                setup_authorized=True,
                p19_control=control,
            ),
        ),
    )
    assert projection is not None
    assert projection.next_action.kind == "p19_authorized_experiment"
    assert "arb_adjustment" in projection.next_action.instruction
    assert "no other change is authorized" in projection.next_action.instruction
    assert projection.setup_authorized is False
    authorized = [
        hypothesis
        for hypothesis in projection.relevant_knowledge
        if hypothesis.setup_authorized
    ]
    assert len(authorized) == 1
    assert authorized[0].p19_control is not None
    assert authorized[0].authority == "exact_p19_projection"


# ── Structural: the model rejects unsupported authority ──

def test_model_rejects_symptom_without_corroboration():
    from racelab_engine.models.handling_knowledge import (
        HandlingKnowledgeProjection,
    )
    base = _projection(
        investigation=_investigation(
            HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
        ),
        knowledge=_knowledge(_hypothesis()),
    )
    assert base is not None
    with pytest.raises(ValidationError):
        HandlingKnowledgeProjection.model_validate({
            **base.model_dump(mode="json"),
            "canonical_symptom_id": "tight_center",
        })


def test_model_rejects_hypothesis_setup_authority_without_p19_control():
    from racelab_engine.models.handling_knowledge import (
        HandlingKnowledgeHypothesis,
    )
    with pytest.raises(ValidationError):
        HandlingKnowledgeHypothesis(
            bridge_id="p351b_" + "a" * 24,
            effect_id="effect:test",
            setup_area="arb",
            physical_role="roll stiffness",
            level="measurable_hypothesis",
            relevance="supported_candidate",
            knowledge_applicability="applicable",
            authority="measurement_only",
            setup_authorized=True,
        )
