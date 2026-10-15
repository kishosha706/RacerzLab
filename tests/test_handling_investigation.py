"""Adversarial tests for the P35.6 P2 unified handling investigation.

Every test proves what the derived projection must NOT claim as well as what
it must: no mechanism support, no component malfunction, no performance
causation, no DriverIntent, no setup authority, and no independent-evidence
inflation from the shared-source producer strands.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.knowledge.engineering_semantic_registry import (
    compile_engineering_semantic_registry,
)
from racelab_engine.models.crew_chief import (
    EngineeringEvidenceIndex,
    EngineeringEvidenceIndexEntry,
    EngineeringObjective,
    p34_qualified_current_artifact_ids,
)
from racelab_engine.models.engineering_case import (
    CanonicalEngineeringCase,
    EngineeringCaseCampaignCapture,
    EngineeringMission,
    EngineeringSemanticFocusState,
    SetupEffectReadiness,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.handling_balance import (
    HandlingBalanceAssessment,
    HandlingBalanceReport,
    HandlingClassification,
    HandlingCorroboration,
    HandlingPhaseObservation,
)
from racelab_engine.models.handling_investigation import (
    HandlingInvestigationProjection,
)
from racelab_engine.services.engineering_case_service import engineering_case_id
from racelab_engine.services.handling_investigation_service import (
    build_handling_investigation,
)

RUN_ID = "p356-run"
SESSION_ID = "p356-session"
SETUP_ID = "setup-p356"
WORKSPACE = "a" * 64


def _observation(*, demand_qualified: bool, residual_qualified: bool = True) -> HandlingPhaseObservation:
    return HandlingPhaseObservation(
        phase="center",
        eligible_laps=6,
        sample_bins=120,
        steering_demand_floor_deg=3.0,
        coverage_fraction=0.95,
        rotation_response_deficit_median_rad_s=0.03,
        steering_demand_relative_deviation_scale_units=2.5 if demand_qualified else None,
        corroboration=HandlingCorroboration(
            kinematic_residual_strand_qualified=residual_qualified,
            steering_response_strand_qualified=demand_qualified,
            steering_response_direction="elevated" if demand_qualified else None,
            aligned=demand_qualified,
            corroborated=demand_qualified and residual_qualified,
        ),
    )


def _assessment(
    classification: HandlingClassification,
    *,
    phase: str = "center",
    symptom: str | None = None,
    demand_qualified: bool = False,
    assessment_id: str = "hba_" + "1" * 24,
) -> HandlingBalanceAssessment:
    return HandlingBalanceAssessment(
        assessment_id=assessment_id,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        lap_numbers=(1, 2, 3, 4, 5, 6),
        phase=phase,
        classification=classification,
        canonical_symptom_id=symptom,
        observation_text=f"{classification.value} repeats in {phase}.",
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
        classification=(
            assessments[0].classification if assessments else
            HandlingClassification.UNAVAILABLE
        ),
        assessments=assessments,
    )


def _p26_stub(*, relevance: str = "candidate", observable: bool = True, unavailable: bool = False) -> SimpleNamespace:
    observability = ("live_response_observable",) if observable else ()
    state = SimpleNamespace(
        component_id="anti_roll_bars",
        relevance=relevance,
        observability_states=observability,
        available_live_channel_ids=("steering_deg", "yaw_rate") if observable else (),
    )
    return SimpleNamespace(
        component_states=(state,),
        knowledge_graph_sha256="p26" * 22,
        unavailable_reason="P26 component attribution is unavailable."
        if unavailable else None,
        setup_id=SETUP_ID,
        setup_snapshot_sha256="2" * 64,
    )


def _p32_stub(*, match_phase: bool = True, attribution: str = "candidate_only",
              repeatability: str = "repeatable", traffic: float = 0.0) -> SimpleNamespace:
    opportunity = SimpleNamespace(
        opportunity_id="p32o-opportunity",
        phase="center" if match_phase else "brake_application",
        track_region="Turn 1",
        attribution_state=attribution,
        repeatability=repeatability,
        local_delta_s=0.12,
        start_pct=20.0,
        end_pct=30.0,
        source_traffic_exposure_fraction=traffic,
        reference_traffic_exposure_fraction=0.0,
    )
    return SimpleNamespace(
        projection_sha256="p32" * 22,
        opportunity_map=SimpleNamespace(opportunities=(opportunity,)),
    )


def _projection(*, classification: HandlingClassification, demand_qualified: bool = False,
                p26: SimpleNamespace | None = None, p32: SimpleNamespace | None = None) -> HandlingInvestigationProjection:
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
        p26=p26 if p26 is not None else _p26_stub(),
        p32=p32 if p32 is not None else _p32_stub(),
    )
    assert projection is not None
    return projection


# ── 1. Qualified handling observation reaches relevant P35 mechanisms ──

def test_corroborated_deficit_informs_p35_mechanisms_without_support():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    finding = projection.findings[0]
    relations = {item.mechanism_id: item for item in finding.mechanisms}
    assert "mechanism:center_rotation_deficit" in relations
    center_relation = relations["mechanism:center_rotation_deficit"]
    assert center_relation.relevance == "informed_by_observation"
    assert center_relation.support_declared is False
    assert center_relation.direction == "deficit_aligned"
    # Applicable mechanisms whose support channels are absent are blocked.
    assert relations["mechanism:front_roll_support_limitation"].relevance == "blocked"
    assert relations["mechanism:front_roll_support_limitation"].missing_evidence
    assert projection.assessment_refs[0].corroborated is True
    assert projection.assessment_refs[0].canonical_symptom_id == "tight_center"


# ── 2. An unqualified observation does not falsely support a mechanism ──

def test_residual_only_observation_informs_no_mechanism():
    projection = _projection(
        classification=HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
        demand_qualified=False,
    )
    assert all(
        item.relevance in {"applicable", "blocked"}
        for item in projection.findings[0].mechanisms
    )
    assert all(
        item.relevance != "informed_by_observation"
        for item in projection.findings[0].mechanisms
    )
    assert projection.assessment_refs[0].corroborated is False
    assert projection.assessment_refs[0].canonical_symptom_id is None


def test_steering_demand_only_informs_no_mechanism():
    assessment = _assessment(
        HandlingClassification.STEERING_DEMAND_ANOMALY,
        demand_qualified=False,
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
    assert all(
        item.relevance != "informed_by_observation"
        for item in projection.findings[0].mechanisms
    )


# ── 3. P26 component relevance is not causal proof ──

def test_component_relevance_copies_p26_state_without_malfunction():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
        p26=_p26_stub(relevance="supported"),
    )
    components = {
        item.component_id: item for item in projection.findings[0].components
    }
    assert components["anti_roll_bars"].relevance == "supported"
    assert components["anti_roll_bars"].malfunction_declared is False
    assert components["anti_roll_bars"].source == "p26_component_awareness"
    body = projection.model_dump(mode="json")
    serialized = str(body).casefold()
    assert "malfunctioning" not in serialized
    assert "is faulty" not in serialized
    assert "failed component" not in serialized


# ── 4. P32 time loss remains producer-owned ──

def test_performance_association_is_co_occurrence_only():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    associations = projection.findings[0].performance
    assert len(associations) == 1
    association = associations[0]
    assert association.opportunity_id == "p32o-opportunity"
    assert association.causation_declared is False
    assert "co-occurs" in association.wording
    assert "does not establish" in association.wording


def test_unqualified_opportunity_is_not_associated():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
        p32=_p32_stub(attribution="blocked_by_traffic"),
    )
    assert projection.findings[0].performance == ()
    assert any(
        "not qualified for association" in note
        for note in projection.findings[0].uncertain
    )


# ── 5. Driver-input changes are not misattributed to setup ──

def test_no_setup_language_or_driver_intent_in_projection():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    serialized = str(projection.model_dump(mode="json")).casefold()
    assert all(
        banned not in serialized
        for banned in ("driverintent", "change the setup", "keep/undo", "authorizes")
    )
    assert projection.setup_authorized is False
    assert projection.p19_authority_unchanged is True
    assert projection.authority == "derived_observation_view"


# ── 6. Shared-source evidence cannot inflate independent support ──

def test_shared_source_dependence_is_declared():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    assert any(
        "share" in statement.casefold() and "curvature" in statement.casefold()
        for statement in projection.evidence_dependence
    )
    assert any(
        "not statistically independent" in statement
        for statement in projection.evidence_dependence
    )


def test_producer_dependence_fields_are_present():
    assessment = _assessment(
        HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        symptom="tight_center",
        demand_qualified=True,
    )
    corroboration = assessment.phase_observations[0].corroboration
    assert corroboration is not None
    assert corroboration.shared_input_channels == ("curvature_1_per_m",)
    assert corroboration.shared_reference_laps is True
    assert "not statistically independent" in corroboration.independence_qualification
    assert assessment.confidence_score <= 0.6


# ── 7. Missing telemetry produces explicit limitations ──

def test_missing_channels_produce_explicit_limitations():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    blocked = [
        item for item in projection.findings[0].mechanisms
        if item.relevance == "blocked"
    ]
    assert blocked
    assert all(item.missing_evidence for item in blocked)


def test_unavailable_p26_yields_unavailable_components():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
        p26=_p26_stub(unavailable=True),
    )
    assert all(
        item.relevance == "unavailable"
        for item in projection.findings[0].components
    )


# ── 8. Contradictory observations remain visible ──

def test_contradictions_are_carried_into_findings():
    projection = _projection(
        classification=HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION,
        demand_qualified=False,
    )
    assert any(
        "actual-path curvature" in contradiction
        for contradiction in projection.findings[0].contradictions
    )


# ── 9/10. No DriverIntent, no setup authorization (structural) ──

def test_projection_model_rejects_driver_intent_and_setup_authority():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    with pytest.raises(ValidationError):
        HandlingInvestigationProjection.model_validate({
            **projection.model_dump(mode="json"),
            "authority": "observation_only",
        })
    with pytest.raises(ValidationError):
        HandlingInvestigationProjection.model_validate({
            **projection.model_dump(mode="json"),
            "setup_authorized": True,
        })
    with pytest.raises(ValidationError):
        HandlingInvestigationProjection.model_validate({
            **projection.model_dump(mode="json"),
            "p19_authority_unchanged": False,
        })


# ── 11. The Engineering Case rejects stale or foreign identities ──

def _case(**overrides):
    case_id = engineering_case_id(run_id=RUN_ID, session_id=SESSION_ID)
    terminal = canonical_json_sha256({"next": "Collect exact evidence."})
    values = {
        "case_id": case_id,
        "case_revision_sha256": WORKSPACE,
        "run_id": RUN_ID,
        "session_id": SESSION_ID,
        "selected_run_ids": (RUN_ID,),
        "recording_sha256": "1" * 64,
        "vehicle_runtime_identity_sha256": "0" * 64,
        "car_identity": "test-car",
        "car_version": "test-version",
        "iracing_build_version": "2026.08.01.01",
        "track_configuration": "oval",
        "setup_id": SETUP_ID,
        "setup_snapshot_sha256": "2" * 64,
        "objective_id": "race_long_run",
        "condition_epoch_sha256": "3" * 64,
        "p19_reasoning_snapshot_sha256": "4" * 64,
        "p20_state_revision": "5" * 64,
        "p26_knowledge_graph_sha256": "6" * 64,
        "p32_projection_sha256": "7" * 64,
        "p35_assessment_sha256": "8" * 64,
        "p351_projection_sha256": "9" * 64,
        "p33_projection_sha256": "b" * 64,
        "semantic_registry_sha256": (
            compile_engineering_semantic_registry().registry_sha256
        ),
        "evidence_index_sha256": "c" * 64,
        "effect_readiness": (
            SetupEffectReadiness(
                effect_id="effect:synthetic",
                bridge_id="p351b_" + "d" * 24,
                state="knowledge_only",
                missing_evidence=("Exact response evidence is unavailable.",),
                authority="knowledge_only",
            ),
        ),
        "workspace_revision": WORKSPACE,
        "terminal_move_sha256": terminal,
        "mission": EngineeringMission(
            what="Measure the current problem",
            where="center",
            why_it_matters="Current P19 evidence requires measurement.",
            uncertain="Cause remains unresolved.",
            next="Collect exact evidence.",
            done_when="Three independent laps clear the contract.",
            source_authority="p19_measurement_mirror",
            terminal_move_sha256=terminal,
        ),
        "semantic_focus": EngineeringSemanticFocusState(
            case_id=case_id,
            case_revision_sha256=WORKSPACE,
        ),
        "campaign_capture": EngineeringCaseCampaignCapture(
            state="pending",
            blocker_reasons=("Real P36 evidence is not qualified.",),
        ),
    }
    values |= overrides
    return CanonicalEngineeringCase.build(**values)


def test_case_accepts_exact_scope_handling_investigation():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    case = _case(handling_investigation=projection)
    assert case.handling_investigation is not None
    assert case.handling_investigation.run_id == RUN_ID


def test_case_rejects_foreign_handling_investigation():
    projection = _projection(
        classification=HandlingClassification.ROTATION_RESPONSE_DEFICIT,
        demand_qualified=True,
    )
    foreign = projection.model_copy(update={"session_id": "other-session"})
    foreign = HandlingInvestigationProjection.model_validate({
        **foreign.model_dump(mode="json", exclude={"projection_sha256"}),
        "projection_sha256": canonical_json_sha256(
            foreign.model_dump(mode="json", exclude={"projection_sha256"})
        ),
    })
    with pytest.raises(ValidationError, match="exact run, session, and setup"):
        _case(handling_investigation=foreign)


# ── 12 (backend side). P34 qualified cohorts exclude the neutral producer ──

def test_p34_qualified_artifact_cohort_excludes_handling_producer():
    entry = EngineeringEvidenceIndexEntry(
        artifact_id="hba_" + "2" * 24,
        producer_id="p356.handling_balance",
        run_id=RUN_ID,
        session_id=SESSION_ID,
        setup_id=SETUP_ID,
        workspace_run_id=RUN_ID,
        workspace_session_id=SESSION_ID,
        workspace_setup_id=SETUP_ID,
        source_run_id=RUN_ID,
        source_session_id=SESSION_ID,
        source_setup_id=SETUP_ID,
        source_setup_sha256="2" * 64,
        source_build_context_sha256="3" * 64,
        source_provenance_available=True,
        lap_numbers=(1, 2, 3),
        phase="center",
        objective=EngineeringObjective.RACE_LONG_RUN,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        polarity="neutral",
        authority_ceiling="observation_only",
    )
    assert entry.polarity == "neutral"
    assert entry.typed_artifact is None
    identity = type(
        "Identity",
        (),
        {
            "run_id": RUN_ID,
            "session_id": SESSION_ID,
            "setup_id": SETUP_ID,
            "setup_snapshot_sha256": "2" * 64,
            "vehicle_runtime_identity_hash": "3" * 64,
        },
    )()
    index = EngineeringEvidenceIndex.model_construct(
        workspace_revision=WORKSPACE,
        entries=(entry,),
        index_hash="0" * 64,
    )
    assert p34_qualified_current_artifact_ids(identity, index) == ()


# ── 13. Existing P1 classification behavior remains unchanged ──

def test_p1_classification_behavior_survives_investigation_layer():
    from fixtures.handling_balance_fixtures import (
        _corner_rows,
        _constant,
        _eligible_summaries,
        _corroborated_rows,
        RUN_ID as P1_RUN_ID,
    )
    from racelab_engine.analysis.handling_balance import analyze_handling_balance

    residual_rows = _corner_rows(deficit_fn=_constant(0.045))
    residual_report = analyze_handling_balance(
        residual_rows, _eligible_summaries(), run_id=P1_RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert (
        residual_report.classification
        == HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION
    )
    corroborated_rows = _corroborated_rows(direction="deficit")
    corroborated_report = analyze_handling_balance(
        corroborated_rows, _eligible_summaries(count=5), run_id=P1_RUN_ID,
        sim_integrity_clear=True, sim_integrity_confidence_cap=0.9,
    )
    assert (
        corroborated_report.classification
        == HandlingClassification.ROTATION_RESPONSE_DEFICIT
    )
