from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.crew_chief_packet import (
    KaizenEvidencePacket,
    OpportunityEvidence,
)
from racelab_engine.analysis.test_director import (
    MeasurementMission,
    TestEvidenceLink,
    TestExecution,
    build_controlled_test,
    score_test_execution,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import (
    CalibrationSummary,
    CapabilityAssessment,
    CauseDiscriminator,
    CauseHypothesis,
    EvidenceCitation,
    EvidenceEdge,
    EvidenceEdgeKind,
    EvidenceGraph,
    EvidenceNode,
    EvidenceNodeKind,
    GroundedClaim,
    InformationPlan,
    IntelligenceAction,
    LapReference,
    RankedCause,
    ResponseMemorySummary,
    SetupEvidenceValue,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    DriverRepeatabilitySignature,
    MechanismObservation,
    MechanismObservationReport,
    ObservationCitation,
    ObservationStatus,
    OpportunitySignatureReport,
    RunObservationIntelligence,
    SameSetupAnomaly,
    SameSetupAnomalyReport,
)
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.models.session_intelligence import (
    SessionEngineeringLedger,
    SessionEvidenceCitation,
    SessionLedgerEntry,
)
from racelab_engine.models.smart_guidance import (
    MeasurementBlocker,
    MeasurementCandidate,
    NextTrustworthyMove,
)
from racelab_engine.models.telemetry_health import (
    TelemetryHealthBaselineReport,
    TelemetryHealthFinding,
    TelemetryHealthRecovery,
    telemetry_health_session_scope_sha256,
)
from racelab_engine.services.intelligence_service import (
    answer_grounded_query,
    assess_data_quality,
    build_evidence_graph,
    build_internal_intelligence_report,
    evaluate_measurement_candidates,
    plan_best_next_measurement,
    rank_competing_causes,
    summarize_response_memory,
)
from racelab_engine.services.setup_learning_service import SetupResponseContext
from racelab_engine.services.run_intelligence_service import (
    _observation_measurement_candidates,
)
from racelab_engine.services.smart_guidance_service import (
    build_controlled_test_preflight,
    build_smart_guidance,
)


def _lap(
    number: int = 4,
    *,
    run_id: str = "run-1",
    useful: bool = True,
    tags: list[str] | None = None,
) -> LapSummary:
    return LapSummary(
        lap_id=f"{run_id}-{number}",
        run_id=run_id,
        lap_number=number,
        lap_type="flying" if useful else "cooldown",
        is_complete=True,
        is_useful=useful,
        lap_time=30.0,
        classification_tags=tags or [],
    )


def _event(
    event_id: str,
    *,
    lap_number: int = 4,
    run_id: str = "run-1",
    valid: bool = True,
    channels: list[str] | None = None,
    setup_keys: list[str] | None = None,
    blockers: list[str] | None = None,
) -> TelemetryEvent:
    return TelemetryEvent(
        event_id=event_id,
        run_id=run_id,
        lap_number=lap_number,
        event_type="platform_balance",
        event_subtype="exit_settle",
        lap_pct_start=42.0,
        lap_pct_end=45.0,
        lap_pct_peak=43.5,
        valid_for_tuning=valid,
        evidence_state=EvidenceState.CALCULATED,
        source_channels=channels if channels is not None else ["speed_mph", "cfs_ride_height_in"],
        related_setup_keys=setup_keys or ["cross_weight_percent"],
        blocker_reasons=blockers or [],
    )


def _context(*, driver_id: str = "driver-1") -> SetupResponseContext:
    return SetupResponseContext(
        driver_id=driver_id,
        car_name="Next Gen",
        car_version="2026.08",
        track_name="Atlanta",
        track_configuration="Oval",
        track_version="2026.08",
        sim_build="2026.08.1",
        weather_bucket="air 70-75 F",
        tire_age_bucket="0-5 km",
        fuel_bucket="40-45 L",
        run_type="practice",
        package_archetype="intermediate",
        objective="long_run",
        baseline_setup_fingerprint="setup-a",
        tire_compound="primary",
    )


def _director():
    return build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=1,
        hypothesis="Test whether platform recovery improves exit time.",
        target_phase="exit",
        success_metrics=["Exit phase time improves beyond the noise floor."],
        countereffects=["Entry rotation must not worsen."],
        evidence_links=[
            TestEvidenceLink(
                event_id="event-support",
                eligible_lap=True,
                valid_for_tuning=True,
                phase="exit",
                related_setup_keys=("cross_weight_percent",),
            )
        ],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=[50.0, 50.1],
        legal_value_provenance={"50.1": ["run-b"]},
    )


def _setup_authority() -> SetupEvidenceValue:
    card = _director().card
    assert card is not None
    return SetupEvidenceValue(
        setup_key=card.control_key,
        current_value_raw=card.current_value,
        proposed_value_raw=card.proposed_value_raw,
        proposed_value_provenance=card.proposed_value_provenance,
        source_event_ids=card.evidence_event_ids,
        authorization_basis="repository_revalidated_legal_option",
    )


def _setup_authority_verifier(value: SetupEvidenceValue) -> bool:
    return value == _setup_authority()


def _workflow() -> ControlledWorkflow:
    director = _director()
    assert director.card is not None
    opportunity = OpportunityEvidence(
        start_pct=42.0,
        end_pct=45.0,
        phase="exit",
        observed_time_loss_s=0.12,
        empirical_noise_s=0.03,
        alignment_confidence=0.95,
        repeatable=True,
        evidence_links=(
            TestEvidenceLink(
                event_id="event-support",
                eligible_lap=True,
                valid_for_tuning=True,
                phase="exit",
                related_setup_keys=("cross_weight_percent",),
            ),
        ),
        source_channels=("speed_mph", "cfs_ride_height_in"),
        supporting_evidence=("Repeated exit loss",),
    )
    packet = KaizenEvidencePacket(
        decision="test",
        opportunity=opportunity,
        canonical_symptom="tight_exit",
        primary_cause_bucket="platform_balance",
        evidence_state=EvidenceState.NEEDS_CONFIRMATION,
        confidence_score=0.8,
        blockers=(),
        supporting_evidence=("Repeated exit loss",),
        contradictory_evidence=(),
        primary_test=director.card,
        held_back_alternatives=1,
        race_mode_summary="Test one change.",
        learning_mode_explanation="A controlled test separates the mechanism.",
    )
    now = datetime.now(timezone.utc)
    execution = TestExecution(
        eligible_laps_a=3,
        eligible_laps_b=3,
        eligible_laps_a2=3,
        unrelated_setup_changes=0,
        control_key="cross_weight_percent",
        planned_b_value=50.1,
        observed_a_value=50.0,
        observed_b_value=50.1,
        observed_a2_value=50.0,
        context_match_score=0.95,
        driver_match_score=0.95,
        sim_integrity_score=0.95,
        minimum_alignment_confidence=0.95,
        target_effect_distributions_consistent=True,
        empirical_noise_observations=4,
        control_guardrails_passed=True,
        target_effect_distribution_state="faster",
        phase_effect_b_vs_a_s=-0.2,
        phase_effect_b_vs_a2_s=-0.18,
        empirical_noise_s=0.05,
        countereffect_passed=True,
    )
    return ControlledWorkflow(
        workflow_id="workflow-1",
        created_at=now,
        updated_at=now,
        status="scored",
        source_run_id="run-1",
        complaint="tight exit",
        packet=packet,
        stage_run_ids={"A": "run-1", "B": "run-b", "A2": "run-a2"},
        stage_eligible_lap_numbers={
            "A": (6, 7, 8),
            "B": (4, 5, 6),
            "A2": (4, 5, 6),
        },
        execution=execution,
        quality=score_test_execution(execution),
        learning_admitted=True,
    )


def _memory_edge(
    observation_id: str,
    *,
    delta: float,
    effect: float,
    verdict: str = "keep_direction",
    evidence_state: str = "controlled_test_effect",
    source_runs: list[str] | None = None,
) -> dict[str, object]:
    runs = source_runs or [
        f"a-{observation_id}",
        f"b-{observation_id}",
        f"a2-{observation_id}",
    ]
    return {
        "observation_id": observation_id,
        "setup_key": "cross_weight_percent",
        "surrounding_setup_fingerprint": "surrounding-a",
        "direction_sign": 1,
        "target_zone_start_pct": 42.0,
        "target_zone_end_pct": 45.0,
        "setup_passed_tech": True,
        "response_context": asdict(_context()),
        "baseline_run_id": runs[0],
        "test_run_id": runs[1],
        "numeric_delta": delta,
        "median_lap_delta_s": effect,
        "pace_noise_band_s": 0.02,
        "confidence_score": 0.9,
        "baseline_value": 50.0,
        "test_value": 50.0 + delta,
        "verdict": verdict,
        "evidence": {
            "evidence_state": evidence_state,
            "source_channels": ["speed_mph", "cfs_ride_height_in"],
            "evidence_event_ids": [f"event-{observation_id}"],
            "source_run_ids": runs,
        },
    }


def _ranked_fixture():
    graph = build_evidence_graph(
        events=[
            _event("event-support"),
            _event("event-support-2"),
            _event("event-against"),
        ],
        laps=[_lap()],
        setup_values=[_setup_authority()],
        setup_authority_verifier=_setup_authority_verifier,
    )
    discriminator = CauseDiscriminator(
        discriminator_id="d-platform",
        title="Repeat the marked exit pass",
        instruction="Record three same-line exit passes on the unchanged setup.",
        target_phase="exit",
        acceptance_thresholds=("Three eligible marked passes",),
        distinguishes_cause_ids=("platform", "driver"),
        source_event_ids=("event-support",),
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="platform",
                label="Platform recovery",
                hypothesis="The platform is slow to recover on exit.",
                supporting_event_ids=("event-support", "event-support-2"),
                discriminator=discriminator,
            ),
            CauseHypothesis(
                cause_id="driver",
                label="Driver line",
                hypothesis="A line change explains the loss.",
                contradicting_event_ids=("event-against",),
            ),
            CauseHypothesis(
                cause_id="tire",
                label="Tire state",
                hypothesis="Tire state may explain the loss.",
                required_evidence=("Matched tire-distance history",),
            ),
        ],
        graph,
    )
    return graph, ranked


def test_evidence_graph_links_every_entity_and_fail_closes_junk_laps() -> None:
    valid_lap = _lap()
    junk_lap = _lap(5, useful=False, tags=["COOLDOWN", "NO_SETUP_CONCLUSION"])
    valid_event = _event("event-support")
    junk_event = _event("event-junk", lap_number=5)
    recommendation = Recommendation(
        recommendation_id="rec-1",
        run_id="run-1",
        issue="Exit platform",
        recommendation_text="Test one change.",
        evidence_state=EvidenceState.CALCULATED,
        source_channels=["speed_mph"],
        evidence_event_ids=["event-support"],
        blocker_reasons=[],
    )
    graph = build_evidence_graph(
        claims=[
            GroundedClaim(
                claim_id="claim-good",
                text="Exit recovery repeats.",
                evidence_state=EvidenceState.CALCULATED,
                supporting_event_ids=("event-support",),
                recommendation_ids=("rec-1",),
                lap_references=(LapReference(run_id="run-1", lap_number=4),),
                source_channels=("speed_mph",),
                setup_keys=("cross_weight_percent",),
                workflow_ids=("workflow-1",),
            ),
            GroundedClaim(
                claim_id="claim-junk",
                text="Cooldown proves a setup issue.",
                evidence_state=EvidenceState.CALCULATED,
                supporting_event_ids=("event-junk",),
            ),
        ],
        events=[valid_event, junk_event],
        recommendations=[recommendation],
        laps=[
            valid_lap,
            junk_lap,
            _lap(6),
            _lap(7),
            _lap(8),
            _lap(run_id="run-b"),
            _lap(5, run_id="run-b"),
            _lap(6, run_id="run-b"),
            _lap(run_id="run-a2"),
            _lap(5, run_id="run-a2"),
            _lap(6, run_id="run-a2"),
        ],
        setup_values=[
            _setup_authority().model_copy(
                update={
                    "value_display": "50.0%",
                    "workflow_ids": ("workflow-1",),
                    "authorization_basis": "scored_controlled_workflow",
                }
            )
        ],
        workflows=[_workflow()],
    )
    by_id = {node.node_id: node for node in graph.nodes}
    assert by_id["event:event-support"].qualified is True
    assert by_id["event:event-junk"].qualified is False
    assert by_id["claim:claim-good"].qualified is True
    assert by_id["claim:claim-junk"].qualified is False
    assert by_id["setup:cross_weight_percent"].qualified is True
    assert by_id["workflow:workflow-1"].qualified is True
    edge_kinds = {
        (edge.source_node_id, edge.target_node_id, edge.kind.value)
        for edge in graph.edges
    }
    assert ("claim:claim-good", "recommendation:rec-1", "supported_by") in edge_kinds
    assert ("claim:claim-good", "channel:speed_mph", "uses_channel") in edge_kinds
    assert ("claim:claim-good", "workflow:workflow-1", "supported_by") in edge_kinds
    assert ("workflow:workflow-1", "setup:cross_weight_percent", "tests_setup") in edge_kinds
    assert all(
        not edge.qualified
        for edge in graph.edges
        if edge.source_node_id == "claim:claim-junk"
    )


def test_evidence_graph_duplicate_and_dangling_identity_fail_closed() -> None:
    graph = build_evidence_graph(
        claims=[
            GroundedClaim(
                claim_id="claim",
                text="A claim",
                evidence_state=EvidenceState.CALCULATED,
                supporting_event_ids=("missing",),
            )
        ],
        events=[_event("duplicate"), _event("duplicate")],
        laps=[_lap()],
    )
    assert any("Duplicate telemetry event" in reason for reason in graph.blocker_reasons)
    claim = next(node for node in graph.nodes if node.node_id == "claim:claim")
    assert claim.qualified is False
    assert any("missing" in reason for reason in claim.blocker_reasons)


def test_recommendation_cannot_borrow_another_run_or_invent_source_channels() -> None:
    recommendation = Recommendation(
        recommendation_id="rec-cross-run",
        run_id="run-a",
        issue="Claim from the wrong run",
        recommendation_text="Change something.",
        evidence_state=EvidenceState.CALCULATED,
        source_channels=["invented_channel"],
        evidence_event_ids=["event-b"],
        blocker_reasons=[],
    )
    graph = build_evidence_graph(
        events=[_event("event-b", run_id="run-b")],
        recommendations=[recommendation],
        laps=[_lap(run_id="run-b")],
    )
    nodes = {node.node_id: node for node in graph.nodes}
    assert nodes["recommendation:rec-cross-run"].qualified is False
    assert nodes["channel:invented_channel"].qualified is False
    assert any(
        "different run" in reason
        for reason in nodes["recommendation:rec-cross-run"].blocker_reasons
    )


def test_exact_setup_value_cannot_borrow_an_unrelated_event() -> None:
    graph = build_evidence_graph(
        events=[_event("cross-event", setup_keys=["cross_weight_percent"])],
        laps=[_lap()],
        setup_values=[
            SetupEvidenceValue(
                setup_key="tape_percent",
                value_display="30%",
                source_event_ids=("cross-event",),
            )
        ],
    )
    tape = next(node for node in graph.nodes if node.node_id == "setup:tape_percent")
    assert tape.qualified is False


def test_repository_authority_literal_cannot_self_attest_an_exact_target() -> None:
    graph = build_evidence_graph(
        events=[_event("event-support")],
        laps=[_lap()],
        setup_values=[_setup_authority()],
    )
    setup = next(
        node for node in graph.nodes if node.node_id == "setup:cross_weight_percent"
    )
    assert setup.qualified is True
    assert setup.authorization_fingerprint is None


def test_claim_cannot_upgrade_an_unproven_exact_setup_value() -> None:
    graph = build_evidence_graph(
        claims=[
            GroundedClaim(
                claim_id="unsafe-value-claim",
                text="The exact value is proven.",
                evidence_state=EvidenceState.CALCULATED,
                supporting_event_ids=("cross-event",),
                setup_keys=("cross_weight_percent",),
            )
        ],
        events=[_event("cross-event", setup_keys=["cross_weight_percent"])],
        laps=[_lap()],
        setup_values=[
            SetupEvidenceValue(
                setup_key="cross_weight_percent",
                value_display="999%",
                source_event_ids=("missing",),
            )
        ],
    )
    nodes = {node.node_id: node for node in graph.nodes}
    assert nodes["setup:cross_weight_percent"].qualified is False
    assert nodes["setup:cross_weight_percent"].authorization_fingerprint is None
    assert nodes["claim:unsafe-value-claim"].qualified is False
    assert "999%" in nodes["setup:cross_weight_percent"].label


def test_lap_only_claim_and_missing_contradiction_are_not_qualified() -> None:
    graph = build_evidence_graph(
        claims=[
            GroundedClaim(
                claim_id="lap-only",
                text="An eligible lap proves a causal setup fact.",
                evidence_state=EvidenceState.CALCULATED,
                lap_references=(LapReference(run_id="run-1", lap_number=4),),
                contradicting_event_ids=("missing-contradiction",),
            )
        ],
        laps=[_lap()],
    )
    claim = next(node for node in graph.nodes if node.node_id == "claim:lap-only")
    assert claim.qualified is False
    assert any("provenance-bearing" in reason for reason in claim.blocker_reasons)
    assert any("missing-contradiction" in reason for reason in claim.blocker_reasons)


def test_nonfinite_event_position_is_retained_only_as_blocked_diagnostic_evidence() -> None:
    event = _event("bad-position").model_copy(update={"lap_pct_peak": float("nan")})
    graph = build_evidence_graph(events=[event], laps=[_lap()])
    node = next(node for node in graph.nodes if node.node_id == "event:bad-position")
    assert node.qualified is False
    assert node.citation is not None
    assert node.citation.valid_for_tuning is False
    assert node.citation.lap_pct_peak is None


def test_workflow_graph_requires_distinct_runs_and_three_distinct_laps_per_stage() -> None:
    workflow = _workflow().model_copy(
        update={
            "stage_run_ids": {"A": "run-1", "B": "run-1", "A2": "run-1"},
            "stage_eligible_lap_numbers": {
                "A": (4, 4, 4),
                "B": (4, 4, 4),
                "A2": (4, 4, 4),
            },
        }
    )
    graph = build_evidence_graph(
        events=[_event("event-support")],
        laps=[_lap()],
        workflows=[workflow],
    )
    node = next(node for node in graph.nodes if node.node_id == "workflow:workflow-1")
    assert node.qualified is False


def test_workflow_event_must_relate_to_the_tested_control() -> None:
    laps = [
        _lap(4),
        _lap(6),
        _lap(7),
        _lap(8),
        _lap(4, run_id="run-b"),
        _lap(5, run_id="run-b"),
        _lap(6, run_id="run-b"),
        _lap(4, run_id="run-a2"),
        _lap(5, run_id="run-a2"),
        _lap(6, run_id="run-a2"),
    ]
    graph = build_evidence_graph(
        events=[_event("event-support", setup_keys=["tape_percent"])],
        laps=laps,
        workflows=[_workflow()],
    )
    nodes = {node.node_id: node for node in graph.nodes}
    assert nodes["workflow:workflow-1"].qualified is False
    assert nodes["setup:cross_weight_percent"].qualified is False


def test_workflow_cannot_borrow_card_evidence_from_outside_its_source_run() -> None:
    graph = build_evidence_graph(
        events=[_event("event-support", run_id="outside")],
        laps=[
            _lap(run_id="outside"),
            *(_lap(number) for number in (6, 7, 8)),
            *(_lap(number, run_id="run-b") for number in (4, 5, 6)),
            *(_lap(number, run_id="run-a2") for number in (4, 5, 6)),
        ],
        workflows=[_workflow()],
    )
    workflow = next(
        node for node in graph.nodes if node.node_id == "workflow:workflow-1"
    )
    assert workflow.qualified is False
    assert all(
        not edge.qualified
        for edge in graph.edges
        if edge.source_node_id == workflow.node_id
    )


def test_workflow_revalidation_rejects_nonconsecutive_cohorts_and_invalid_verdicts() -> None:
    laps = [
        *(_lap(number) for number in (4, 6, 7, 8, 9)),
        *(_lap(number, run_id="run-b") for number in (4, 5, 6)),
        *(_lap(number, run_id="run-a2") for number in (4, 5, 6)),
    ]
    workflow = _workflow()
    nonconsecutive = workflow.model_copy(
        update={
            "stage_eligible_lap_numbers": {
                "A": (6, 8, 9),
                "B": (4, 5, 6),
                "A2": (4, 5, 6),
            }
        }
    )
    invalid_quality = workflow.model_copy(
        update={
            "quality": workflow.quality.model_copy(
                update={"verdict": "invalid", "controlled_effect_eligible": True}
            )
        }
    )
    for candidate in (nonconsecutive, invalid_quality):
        graph = build_evidence_graph(
            events=[_event("event-support")],
            laps=laps,
            workflows=[candidate],
        )
        node = next(node for node in graph.nodes if node.node_id == "workflow:workflow-1")
        assert node.qualified is False


def test_workflow_requires_execution_and_exact_canonical_rescore() -> None:
    workflow = _workflow()
    assert workflow.quality is not None
    assert workflow.execution is not None
    forged_quality = workflow.quality.model_copy(
        update={
            "score": 0.0,
            "supporting_evidence": (),
            "controlled_effect_eligible": True,
            "verdict": "keep",
        }
    )
    candidates = (
        workflow.model_copy(update={"execution": None}),
        workflow.model_copy(update={"quality": forged_quality}),
        workflow.model_copy(
            update={
                "execution": workflow.execution.model_copy(
                    update={"control_key": "tape_percent"}
                ),
                "quality": score_test_execution(
                    workflow.execution.model_copy(update={"control_key": "tape_percent"})
                ),
            }
        ),
    )
    laps = [
        _lap(4),
        *(_lap(number) for number in (6, 7, 8)),
        *(_lap(number, run_id="run-b") for number in (4, 5, 6)),
        *(_lap(number, run_id="run-a2") for number in (4, 5, 6)),
    ]
    for candidate in candidates:
        graph = build_evidence_graph(
            events=[_event("event-support")],
            laps=laps,
            workflows=[candidate],
        )
        workflow_node = next(
            node for node in graph.nodes if node.node_id == "workflow:workflow-1"
        )
        assert workflow_node.qualified is False


def test_workflow_rescore_cannot_authorize_a_self_consistent_nonadjacent_card() -> None:
    workflow = _workflow()
    card = workflow.packet.primary_test
    assert card is not None
    assert workflow.execution is not None
    transition = "50.0% -> 99.0% (adjacent observed tech-passing option)"
    forged_card = card.model_copy(
        update={
            "proposed_value": "99.0%",
            "proposed_value_raw": 99.0,
            "exact_change": transition,
            "change_size": "Large test input · adjacent observed garage option",
            "stages": (
                card.stages[0],
                card.stages[1].model_copy(
                    update={"setup_instruction": f"Change only Cross Weight: {transition}."}
                ),
                card.stages[2],
            ),
        }
    )
    forged_execution = workflow.execution.model_copy(
        update={
            "planned_b_value": 99.0,
            "observed_b_value": 99.0,
        }
    )
    forged_workflow = workflow.model_copy(
        update={
            "packet": workflow.packet.model_copy(update={"primary_test": forged_card}),
            "execution": forged_execution,
            "quality": score_test_execution(forged_execution),
        }
    )
    graph = build_evidence_graph(
        events=[_event("event-support")],
        laps=[
            _lap(4),
            *(_lap(number) for number in (6, 7, 8)),
            *(_lap(number, run_id="run-b") for number in (4, 5, 6)),
            *(_lap(number, run_id="run-a2") for number in (4, 5, 6)),
        ],
        workflows=[forged_workflow],
    )
    node = next(node for node in graph.nodes if node.node_id == "workflow:workflow-1")
    assert node.qualified is False


def test_workflow_proposed_value_provenance_must_be_the_observed_b_run() -> None:
    workflow = _workflow()
    card = workflow.packet.primary_test
    assert card is not None
    forged_card = card.model_copy(
        update={"proposed_value_provenance": (workflow.stage_run_ids["A"],)}
    )
    forged_workflow = workflow.model_copy(
        update={"packet": workflow.packet.model_copy(update={"primary_test": forged_card})}
    )
    authority = _setup_authority().model_copy(
        update={
            "proposed_value_provenance": forged_card.proposed_value_provenance,
            "workflow_ids": (workflow.workflow_id,),
            "authorization_basis": "scored_controlled_workflow",
        }
    )
    graph = build_evidence_graph(
        events=[_event("event-support")],
        laps=[
            _lap(4),
            *(_lap(number) for number in (6, 7, 8)),
            *(_lap(number, run_id="run-b") for number in (4, 5, 6)),
            *(_lap(number, run_id="run-a2") for number in (4, 5, 6)),
        ],
        setup_values=[authority],
        workflows=[forged_workflow],
    )
    nodes = {node.node_id: node for node in graph.nodes}
    assert nodes["workflow:workflow-1"].qualified is False
    assert nodes["setup:cross_weight_percent"].authorization_fingerprint is None


def test_corrupt_blank_identities_become_graph_blockers_instead_of_exceptions() -> None:
    graph = build_evidence_graph(
        events=[_event("", run_id="")],
        laps=[_lap(run_id="")],
    )
    assert graph.nodes == ()
    assert any("invalid" in reason for reason in graph.blocker_reasons)


def test_malformed_event_and_recommendation_labels_do_not_materialize_blank_nodes() -> None:
    bad_event = _event("bad-event").model_copy(
        update={
            "event_type": " ",
            "event_subtype": " ",
            "source_channels": [""],
            "related_setup_keys": [""],
        }
    )
    bad_recommendation = Recommendation(
        recommendation_id="bad-rec",
        run_id="run-1",
        issue=" ",
        recommendation_text="Unsafe",
        evidence_state=EvidenceState.CALCULATED,
        source_channels=[""],
        evidence_event_ids=["bad-event"],
        blocker_reasons=[],
    )
    graph = build_evidence_graph(
        events=[bad_event],
        recommendations=[bad_recommendation],
        laps=[_lap()],
    )
    nodes = {node.node_id: node for node in graph.nodes}
    assert nodes["event:bad-event"].qualified is False
    assert nodes["recommendation:bad-rec"].qualified is False
    assert "channel:" not in nodes
    assert "setup:" not in nodes


def test_noncanonical_whitespace_event_identity_is_blocked_before_deduplication() -> None:
    graph = build_evidence_graph(
        events=[_event("event"), _event(" event ")],
        laps=[_lap()],
    )
    assert sum(node.kind is EvidenceNodeKind.EVENT for node in graph.nodes) == 1
    assert any("invalid event" in reason for reason in graph.blocker_reasons)


def test_duplicate_events_do_not_leave_qualified_channel_or_setup_nodes() -> None:
    graph = build_evidence_graph(
        events=[_event("duplicate"), _event("duplicate")],
        laps=[_lap()],
    )
    nodes = {node.node_id: node for node in graph.nodes}
    assert nodes["event:duplicate"].qualified is False
    assert nodes["channel:speed_mph"].qualified is False
    assert nodes["setup:cross_weight_percent"].qualified is False


def test_evidence_graph_edge_order_is_independent_of_input_order() -> None:
    events = [_event("z-event"), _event("a-event")]
    first = build_evidence_graph(events=events, laps=[_lap()])
    second = build_evidence_graph(events=list(reversed(events)), laps=[_lap()])
    assert first == second


def test_evidence_graph_contract_rejects_duplicate_event_identity() -> None:
    graph = build_evidence_graph(events=[_event("event-support")], laps=[_lap()])
    event_node = next(node for node in graph.nodes if node.node_id == "event:event-support")
    with pytest.raises(ValidationError, match="node_id values must be unique"):
        EvidenceGraph(nodes=(event_node, event_node), edges=())


def test_evidence_graph_contract_rejects_conflicting_duplicate_semantic_edges() -> None:
    graph = build_evidence_graph(events=[_event("event-support")], laps=[_lap()])
    observed_edge = next(
        edge for edge in graph.edges if edge.kind is EvidenceEdgeKind.OBSERVED_ON
    )
    conflicting = EvidenceEdge(
        source_node_id=observed_edge.source_node_id,
        target_node_id=observed_edge.target_node_id,
        kind=observed_edge.kind,
        qualified=not observed_edge.qualified,
    )
    with pytest.raises(ValidationError, match="semantic edge identities must be unique"):
        EvidenceGraph(nodes=graph.nodes, edges=(*graph.edges, conflicting))


def test_typed_graph_requires_qualified_events_to_resolve_an_eligible_lap() -> None:
    graph = build_evidence_graph(events=[_event("event-support")], laps=[_lap()])
    event_node = next(node for node in graph.nodes if node.kind is EvidenceNodeKind.EVENT)
    channel_nodes = tuple(
        node for node in graph.nodes if node.kind is EvidenceNodeKind.CHANNEL
    )
    channel_edges = tuple(
        edge for edge in graph.edges if edge.kind.value == "uses_channel"
    )
    with pytest.raises(ValidationError, match="observed-on eligible-lap"):
        EvidenceGraph(nodes=(event_node, *channel_nodes), edges=channel_edges)


def test_setup_authorization_requires_a_real_setup_node_endpoint() -> None:
    graph = build_evidence_graph(
        events=[_event("event-support", setup_keys=["tape_percent"])],
        laps=[_lap()],
    )
    forged_target = EvidenceNode(
        node_id="setup:cross_weight_percent",
        entity_id="cross_weight_percent",
        kind=EvidenceNodeKind.CHANNEL,
        label="Forged endpoint",
        evidence_state=EvidenceState.CALCULATED,
        qualified=True,
    )
    forged_edge = EvidenceEdge(
        source_node_id="event:event-support",
        target_node_id=forged_target.node_id,
        kind=EvidenceEdgeKind.RELATES_TO_SETUP,
        qualified=True,
    )
    with pytest.raises(ValidationError, match="identity prefix must match"):
        EvidenceGraph(nodes=(*graph.nodes, forged_target), edges=(*graph.edges, forged_edge))

    forged_graph = graph.model_copy(
        update={
            "nodes": (*graph.nodes, forged_target),
            "edges": (*graph.edges, forged_edge),
        }
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="forged",
                label="Forged",
                hypothesis="A fake endpoint must not authorize a card.",
                supporting_event_ids=("event-support",),
            )
        ],
        graph,
    )
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        graph=forged_graph,
    )
    assert plan.kind == "blocked"


def test_typed_citations_and_ranked_causes_reject_ambiguous_evidence_identities() -> None:
    with pytest.raises(ValidationError, match="channel and event identities"):
        EvidenceCitation(
            citation_id="event:bad-channel",
            run_id="run-1",
            lap_number=4,
            event_id="bad-channel",
            workspace="overview",
            channels=("   ",),
            evidence_state=EvidenceState.CALCULATED,
            valid_for_tuning=True,
            summary="Malformed channel provenance.",
        )

    graph = build_evidence_graph(events=[_event("event-support")], laps=[_lap()])
    citation = next(
        node.citation
        for node in graph.nodes
        if node.node_id == "event:event-support"
    )
    assert citation is not None
    with pytest.raises(ValidationError, match="evidence identities must be unique"):
        RankedCause(
            cause_id="duplicate",
            label="Duplicate",
            hypothesis="Duplicate citation inflation.",
            status="likely",
            ordinal_rank=1,
            rank_basis="Ordinal only.",
            supporting_evidence=(citation, citation),
            contradicting_evidence=(),
            missing_evidence=(),
            blocker_reasons=(),
        )


def test_competing_causes_are_deterministic_ordinal_and_keep_contradictions() -> None:
    _, ranked = _ranked_fixture()
    assert [(cause.cause_id, cause.status) for cause in ranked] == [
        ("platform", "possible"),
        ("tire", "unresolved"),
        ("driver", "unresolved"),
    ]
    assert ranked[0].ordinal_rank == 1
    assert "not a probability" in ranked[0].rank_basis
    assert ranked[-1].contradicting_evidence[0].event_id == "event-against"


def test_competing_cause_ties_and_untrusted_events_do_not_create_a_likely_cause() -> None:
    graph = build_evidence_graph(
        events=[_event("junk", lap_number=5)],
        laps=[_lap(), _lap(5, useful=False, tags=["COOLDOWN"])],
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="a",
                label="A",
                hypothesis="A",
                supporting_event_ids=("junk",),
            ),
            CauseHypothesis(cause_id="b", label="B", hypothesis="B"),
        ],
        graph,
    )
    assert all(cause.status in {"possible", "unresolved"} for cause in ranked)
    cause_a = next(cause for cause in ranked if cause.cause_id == "a")
    assert cause_a.supporting_evidence == ()
    assert "Qualified supporting event junk" in cause_a.missing_evidence


def test_missing_evidence_prevents_a_cause_from_being_ruled_out() -> None:
    graph = build_evidence_graph(events=[_event("against")], laps=[_lap()])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="unresolved",
                label="Unresolved",
                hypothesis="The cause remains unresolved.",
                contradicting_event_ids=("against",),
                required_evidence=("Need the yaw trace",),
            )
        ],
        graph,
    )
    assert ranked[0].status == "unresolved"
    assert ranked[0].contradicting_evidence
    assert ranked[0].missing_evidence == ("Need the yaw trace",)


def test_ranking_withholds_overlapping_evidence_and_normalizes_duplicate_blockers() -> None:
    graph = build_evidence_graph(events=[_event("shared")], laps=[_lap()])
    overlap = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="overlap",
                label="Overlap",
                hypothesis="The same event was misclassified twice.",
                supporting_event_ids=("shared",),
                contradicting_event_ids=("shared",),
            )
        ],
        graph,
    )[0]
    assert overlap.status == "unresolved"
    assert overlap.supporting_evidence == ()
    assert overlap.contradicting_evidence == ()
    assert "both support and contradiction" in overlap.missing_evidence[0]

    causes = [
        CauseHypothesis(
            cause_id="duplicate-blocker",
            label="Duplicate blocker",
            hypothesis="Repeated blocker text must count once.",
            blocker_reasons=("Need more evidence", "Need more evidence"),
        ),
        CauseHypothesis(
            cause_id="single-blocker",
            label="Single blocker",
            hypothesis="One blocker.",
            blocker_reasons=("Need more evidence",),
        ),
    ]
    normalized = rank_competing_causes(causes, graph)
    assert {cause.ordinal_rank for cause in normalized} == {1}
    assert all(cause.blocker_reasons == ("Need more evidence",) for cause in normalized)


def test_tuning_valid_typed_contracts_reject_unqualified_states() -> None:
    with pytest.raises(ValidationError, match="tuning-valid citations"):
        EvidenceCitation(
            citation_id="event:unready",
            run_id="run-1",
            lap_number=4,
            event_id="unready",
            workspace="overview",
            channels=("speed_mph",),
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
            valid_for_tuning=True,
            summary="Unconfirmed event",
        )
    with pytest.raises(ValidationError, match="canonical qualified evidence state"):
        EvidenceNode(
            node_id="channel:unready",
            entity_id="unready",
            kind=EvidenceNodeKind.CHANNEL,
            label="Unready",
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
            qualified=True,
        )
    with pytest.raises(ValidationError, match="usable evidence state"):
        IntelligenceAction(
            kind="controlled_test",
            title="Unsafe",
            instruction="Unsafe target",
            setup_authorized=True,
            control_key="cross_weight_percent",
            current_value="50.0%",
            proposed_value="50.1%",
            evidence_state=EvidenceState.UNAVAILABLE,
            source_event_ids=("event-support",),
        )
    card = _director().card
    assert card is not None
    with pytest.raises(ValidationError, match="cannot carry blockers"):
        InformationPlan(
            kind="controlled_test",
            title="Blocked exact plan",
            instruction=card.exact_change,
            rationale="Unsafe producer payload.",
            setup_authorized=True,
            controlled_test=card,
            source_event_ids=card.evidence_event_ids,
            blocker_reasons=("Producer says this is unsafe.",),
        )


def test_next_measurement_reuses_authorized_card_and_never_changes_its_target() -> None:
    graph, ranked = _ranked_fixture()
    director = _director()
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=director,
        graph=graph,
    )
    assert plan.kind == "controlled_test"
    assert plan.setup_authorized is True
    assert plan.controlled_test is director.card
    assert plan.controlled_test.proposed_value == "50.1%"
    assert plan.source_event_ids == ("event-support",)


def test_next_measurement_delegates_existing_mission_before_a_discriminator() -> None:
    _, ranked = _ranked_fixture()
    mission = MeasurementMission(
        purpose="Measure the exit.",
        procedure=("Record three marked exit passes.",),
        required_laps_or_passes=3,
        controlled_variables=("setup", "fuel"),
        target_phase="exit",
        acceptance_thresholds=("Three eligible passes",),
        stop_rule="Stop after an incident.",
        blockers=("Target evidence missing.",),
    )
    plan = plan_best_next_measurement(ranked, measurement_mission=mission)
    assert plan.kind == "measurement_mission"
    assert plan.measurement_mission is mission
    assert plan.setup_authorized is False


def test_next_measurement_selects_one_most_separating_discriminator() -> None:
    graph, ranked = _ranked_fixture()
    extra = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="small",
                label="Small",
                hypothesis="Small",
                supporting_event_ids=("event-support",),
                discriminator=CauseDiscriminator(
                    discriminator_id="d-small",
                    title="Small discriminator",
                    instruction="Measure one channel.",
                    target_phase="exit",
                    acceptance_thresholds=("One threshold",),
                    distinguishes_cause_ids=("small",),
                ),
            )
        ],
        graph,
    )
    plan = plan_best_next_measurement([*ranked, *extra])
    assert plan.kind == "discriminator"
    assert plan.discriminator.discriminator_id == "d-platform"
    assert plan.setup_authorized is False
    assert plan.controlled_test is None


def test_next_measurement_fails_closed_without_authority_or_discriminator() -> None:
    plan = plan_best_next_measurement(())
    assert plan.kind == "blocked"
    assert plan.setup_authorized is False
    assert plan.blocker_reasons


def test_next_measurement_rejects_a_stale_controlled_card() -> None:
    graph = build_evidence_graph(events=[_event("different-event")], laps=[_lap()])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="different",
                label="Different",
                hypothesis="Different evidence.",
                supporting_event_ids=("different-event",),
            )
        ],
        graph,
    )
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        graph=graph,
    )
    assert plan.kind == "blocked"
    assert "stale" in plan.blocker_reasons[0]


def test_controlled_card_requires_exact_event_to_control_graph_linkage_everywhere() -> None:
    cross_graph = build_evidence_graph(
        events=[_event("event-support", setup_keys=["tape_percent"])],
        laps=[_lap()],
    )
    cross_ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="cross",
                label="Cross-control",
                hypothesis="A cross-control event must not authorize this card.",
                supporting_event_ids=("event-support",),
            )
        ],
        cross_graph,
    )
    plan = plan_best_next_measurement(
        cross_ranked,
        controlled_decision=_director(),
        graph=cross_graph,
    )
    assert plan.kind == "blocked"

    card = _director().card
    assert card is not None
    forged_plan = InformationPlan(
        kind="controlled_test",
        title="Forged cross-control card",
        instruction=card.exact_change,
        rationale="Hostile persisted payload",
        setup_authorized=True,
        controlled_test=card,
        source_event_ids=card.evidence_event_ids,
    )
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support", setup_keys=["tape_percent"])],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Cross-control",
        graph=cross_graph,
        ranked_causes=cross_ranked,
        best_measurement=forged_plan,
        data_quality=quality,
    )
    assert report.briefing.action.setup_authorized is False

    good_graph, good_ranked = _ranked_fixture()
    good_plan = plan_best_next_measurement(
        good_ranked,
        controlled_decision=_director(),
        graph=good_graph,
    )
    good_quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support")],
        capability=CapabilityAssessment(status="ready"),
    )
    good_report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Good",
        graph=good_graph,
        ranked_causes=good_ranked,
        best_measurement=good_plan,
        data_quality=good_quality,
    )
    forged_report = good_report.model_copy(update={"evidence_graph": cross_graph})
    answer = answer_grounded_query("What should I do next?", forged_report)
    assert answer.action_authorized is False
    assert "No setup action is authorized" in answer.answer


def test_controlled_card_semantic_blanks_fail_closed() -> None:
    graph, ranked = _ranked_fixture()
    decision = _director()
    assert decision.card is not None
    bad_card = decision.card.model_copy(
        update={
            "exact_change": " ",
            "proposed_value_provenance": (" ",),
        }
    )
    bad_decision = decision.model_copy(update={"card": bad_card})
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=bad_decision,
        graph=graph,
    )
    assert plan.kind == "blocked"


def test_controlled_card_rejects_mismatched_or_nonadjacent_exact_targets() -> None:
    graph, ranked = _ranked_fixture()
    decision = _director()
    assert decision.card is not None
    card = decision.card
    mismatched = card.model_copy(update={"exact_change": "Set cross weight to 99%."})
    transition = "50.0% -> 99.0% (adjacent observed tech-passing option)"
    nonadjacent = card.model_copy(
        update={
            "proposed_value": "99.0%",
            "proposed_value_raw": 99.0,
            "exact_change": transition,
            "change_size": "Large test input · adjacent observed garage option",
            "stages": (
                card.stages[0],
                card.stages[1].model_copy(
                    update={"setup_instruction": f"Change only Cross Weight: {transition}."}
                ),
                card.stages[2],
            ),
        }
    )
    for forged_card in (mismatched, nonadjacent):
        forged_decision = decision.model_copy(update={"card": forged_card})
        plan = plan_best_next_measurement(
            ranked,
            controlled_decision=forged_decision,
            graph=graph,
        )
        assert plan.kind == "blocked"

    rewritten_decision = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.1,
        direction_sign=1,
        hypothesis="Rewrite the target while keeping the same event.",
        target_phase="exit",
        success_metrics=["Exit improves."],
        countereffects=["Entry must not worsen."],
        evidence_links=[
            TestEvidenceLink(
                event_id="event-support",
                eligible_lap=True,
                valid_for_tuning=True,
                phase="exit",
                related_setup_keys=("cross_weight_percent",),
            )
        ],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=[50.1, 50.2],
        legal_value_provenance={"50.2": ["unrelated-run"]},
    )
    assert rewritten_decision.card is not None
    rewritten = plan_best_next_measurement(
        ranked,
        controlled_decision=rewritten_decision,
        graph=graph,
    )
    assert rewritten.kind == "blocked"


def test_malformed_persisted_measurement_mission_fails_closed() -> None:
    malformed = MeasurementMission(
        purpose="",
        procedure=(),
        required_laps_or_passes=3,
        controlled_variables=(),
        target_phase="",
        acceptance_thresholds=(),
        stop_rule="",
        blockers=(),
    )
    plan = plan_best_next_measurement((), measurement_mission=malformed)
    assert plan.kind == "blocked"
    assert "malformed" in plan.blocker_reasons[0]


def test_discriminator_cannot_claim_information_gain_from_nonexistent_causes() -> None:
    graph = build_evidence_graph(events=[_event("event-support")], laps=[_lap()])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="real",
                label="Real",
                hypothesis="Real hypothesis.",
                supporting_event_ids=("event-support",),
                discriminator=CauseDiscriminator(
                    discriminator_id="fake-gain",
                    title="Fake gain",
                    instruction="Measure something unrelated.",
                    target_phase="exit",
                    acceptance_thresholds=("One sample",),
                    distinguishes_cause_ids=("ghost-a", "ghost-b", "ghost-c"),
                ),
            )
        ],
        graph,
    )
    assert plan_best_next_measurement(ranked).kind == "blocked"


def test_single_cause_discriminator_is_not_described_as_separating_multiple_causes() -> None:
    graph = build_evidence_graph(events=[_event("event-support")], laps=[_lap()])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="real",
                label="Real",
                hypothesis="Real hypothesis.",
                supporting_event_ids=("event-support",),
                discriminator=CauseDiscriminator(
                    discriminator_id="single",
                    title="Test the real cause",
                    instruction="Record three matched passes.",
                    target_phase="exit",
                    acceptance_thresholds=("Three eligible passes",),
                    distinguishes_cause_ids=("real",),
                ),
            )
        ],
        graph,
    )
    plan = plan_best_next_measurement(ranked)
    assert plan.kind == "discriminator"
    assert "tests the highest-ranked" in plan.rationale
    assert "multiple" not in plan.rationale


def test_information_plan_kind_must_match_its_attachment() -> None:
    discriminator = CauseDiscriminator(
        discriminator_id="d",
        title="D",
        instruction="Measure D.",
        target_phase="exit",
        acceptance_thresholds=("Three passes",),
        distinguishes_cause_ids=("cause",),
    )
    with pytest.raises(ValidationError, match="attached plan type"):
        InformationPlan(
            kind="measurement_mission",
            title="Mismatched",
            instruction="Mismatched.",
            rationale="Hostile payload.",
            discriminator=discriminator,
        )


def test_response_memory_returns_a_guarded_exact_context_range_and_navigation_ids() -> None:
    context = _context()
    summary = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [
                _memory_edge("1", delta=0.1, effect=-0.05),
                _memory_edge("2", delta=0.2, effect=-0.08),
            ],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    assert summary.status == "exact_context_match"
    assert summary.counterfactual_range is not None
    assert summary.counterfactual_range.minimum == -0.08
    assert summary.counterfactual_range.maximum == -0.05
    assert summary.source_run_ids == ("a-1", "b-1", "a2-1", "a-2", "b-2", "a2-2")
    assert summary.evidence_event_ids == ("event-1", "event-2")
    assert summary.matching_context


def test_typed_exact_context_memory_requires_complete_history_provenance() -> None:
    with pytest.raises(ValidationError, match="complete context, history, and provenance"):
        ResponseMemorySummary(
            context_key=None,
            status="exact_context_match",
            control_key="cross_weight_percent",
            direction_sign=1,
            qualified_observation_count=1,
        )


def test_response_memory_withholds_extrapolation_and_nonfinite_or_untrusted_rows() -> None:
    context = _context()
    summary = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [
                _memory_edge("1", delta=0.1, effect=-0.05),
                _memory_edge("2", delta=0.2, effect=-0.08),
                _memory_edge("nan", delta=float("nan"), effect=-0.1),
                _memory_edge("wrong-state", delta=0.15, effect=-0.06, evidence_state="calculated"),
                _memory_edge("reused", delta=0.15, effect=-0.06, source_runs=["a", "b", "a"]),
            ],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.3,
    )
    assert summary.qualified_observation_count == 2
    assert summary.counterfactual_range is None
    assert "outside the observed" in summary.blocker_reasons[0]


def test_response_memory_rejects_multiple_observations_for_one_source_triplet() -> None:
    context = _context()
    shared_runs = ["run-a", "run-b", "run-a2"]
    summary = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [
                _memory_edge("one", delta=0.1, effect=-0.05, source_runs=shared_runs),
                _memory_edge("two", delta=0.2, effect=-0.08, source_runs=shared_runs),
            ],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    assert summary.status == "contradictory_history"
    assert summary.counterfactual_range is None
    assert "multiple observation identities" in summary.blocker_reasons[0]


def test_response_memory_rejects_permuted_source_run_triplets() -> None:
    context = _context()
    summary = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [
                _memory_edge(
                    "one",
                    delta=0.1,
                    effect=-0.05,
                    source_runs=["run-a", "run-b", "run-a2"],
                ),
                _memory_edge(
                    "two",
                    delta=0.2,
                    effect=-0.08,
                    source_runs=["run-a2", "run-b", "run-a"],
                ),
            ],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    assert summary.status == "contradictory_history"
    assert summary.counterfactual_range is None


def test_response_memory_rejects_per_edge_context_and_delta_tampering() -> None:
    context = _context()
    wrong_context = _memory_edge("wrong-context", delta=0.1, effect=-0.05)
    wrong_context["response_context"] = asdict(_context(driver_id="other"))
    wrong_delta = _memory_edge("wrong-delta", delta=0.1, effect=-0.05)
    wrong_delta["test_value"] = 50.3
    summary = summarize_response_memory(
        response_context=context,
        response_graph={"context_key": context.key, "edges": [wrong_context, wrong_delta]},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    assert summary.status == "no_qualified_history"
    assert summary.qualified_observation_count == 0


def test_response_memory_corrupt_unhashable_source_runs_fail_closed() -> None:
    context = _context()
    edge = _memory_edge("bad-json", delta=0.1, effect=-0.05)
    edge["evidence"]["source_run_ids"] = [{"bad": 1}, "run-b", "run-a2"]
    summary = summarize_response_memory(
        response_context=context,
        response_graph={"context_key": context.key, "edges": [edge]},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    assert summary.status == "no_qualified_history"


def test_response_memory_rejects_boolean_numerics_and_whitespace_identities() -> None:
    context = _context()
    boolean_edge = _memory_edge("boolean", delta=0.1, effect=-0.05)
    boolean_edge.update(
        {
            "numeric_delta": True,
            "median_lap_delta_s": False,
            "baseline_value": False,
            "test_value": True,
        }
    )
    whitespace_edge = _memory_edge(" ", delta=0.2, effect=-0.08)
    whitespace_edge["evidence"]["source_run_ids"] = [
        "same-run",
        " same-run ",
        "run-a2",
    ]
    whitespace_edge["baseline_run_id"] = "same-run"
    whitespace_edge["test_run_id"] = " same-run "
    summary = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [boolean_edge, whitespace_edge],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    assert summary.status == "no_qualified_history"

    with pytest.raises(ValueError, match="direction_sign"):
        summarize_response_memory(
            response_context=context,
            response_graph={"context_key": context.key, "edges": []},
            control_key="cross_weight_percent",
            direction_sign=True,
            target_zone_start_pct=42.0,
            target_zone_end_pct=45.0,
            surrounding_setup_fingerprint="surrounding-a",
        )


def test_response_memory_rejects_keep_verdicts_with_slower_or_noise_bound_effects() -> None:
    context = _context()
    slower = _memory_edge("slower", delta=0.1, effect=0.5)
    inside_noise = _memory_edge("noise", delta=0.2, effect=-0.01)
    summary = summarize_response_memory(
        response_context=context,
        response_graph={"context_key": context.key, "edges": [slower, inside_noise]},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    assert summary.status == "no_qualified_history"
    assert summary.counterfactual_range is None


def test_response_memory_rejects_unknown_or_unguarded_setup_values() -> None:
    context = _context()
    oversized = _memory_edge("oversized", delta=1.0, effect=-0.05)
    oversized.update({"baseline_value": 500.0, "test_value": 501.0})
    summary = summarize_response_memory(
        response_context=context,
        response_graph={"context_key": context.key, "edges": [oversized]},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    assert summary.status == "no_qualified_history"
    assert summary.counterfactual_range is None

    with pytest.raises(ValueError, match="canonical setup control"):
        summarize_response_memory(
            response_context=context,
            response_graph={"context_key": context.key, "edges": []},
            control_key="invented_control",
            direction_sign=1,
            target_zone_start_pct=42.0,
            target_zone_end_pct=45.0,
            surrounding_setup_fingerprint="surrounding-a",
        )


def test_response_memory_keeps_faster_undo_with_recorded_countereffect() -> None:
    context = _context()
    edge = _memory_edge(
        "countereffect-undo",
        delta=0.1,
        effect=-0.05,
        verdict="undo",
    )
    edge["evidence"]["countereffects"] = {
        "warnings": ["Entry stability worsened beyond its noise floor."],
        "do_not_change": [],
    }
    summary = summarize_response_memory(
        response_context=context,
        response_graph={"context_key": context.key, "edges": [edge]},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    assert summary.status == "exact_context_match"
    assert summary.verdicts == ("undo",)


def test_response_memory_rejects_reused_evidence_events_across_experiments() -> None:
    context = _context()
    first = _memory_edge("one", delta=0.1, effect=-0.05)
    second = _memory_edge("two", delta=0.2, effect=-0.08)
    first["evidence"]["evidence_event_ids"] = ["shared-event"]
    second["evidence"]["evidence_event_ids"] = ["shared-event"]
    summary = summarize_response_memory(
        response_context=context,
        response_graph={"context_key": context.key, "edges": [first, second]},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    assert summary.status == "contradictory_history"
    assert summary.counterfactual_range is None


def test_response_memory_never_transfers_context_or_hides_contradictions() -> None:
    context = _context()
    mismatch = summarize_response_memory(
        response_context=context,
        response_graph={"context_key": _context(driver_id="other").key, "edges": []},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    assert mismatch.status == "context_mismatch"
    assert mismatch.counterfactual_range is None
    assert mismatch.mismatches

    contradictory = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [
                _memory_edge("1", delta=0.1, effect=-0.05),
                _memory_edge("2", delta=0.2, effect=0.04, verdict="undo"),
            ],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    assert contradictory.status == "contradictory_history"
    assert contradictory.counterfactual_range is None
    assert set(contradictory.verdicts) == {"keep_direction", "undo"}


def test_response_memory_requires_a_complete_context() -> None:
    summary = summarize_response_memory(
        response_context=_context(driver_id=""),
        response_graph={},
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    assert summary.status == "incomplete_context"
    assert summary.qualified_observation_count == 0


def test_data_quality_uses_canonical_lap_and_event_gates() -> None:
    junk = _lap(useful=False, tags=["COOLDOWN", "NO_SETUP_CONCLUSION"])
    blocked = assess_data_quality(
        laps=[junk],
        events=[_event("junk-event")],
        capability=None,
    )
    assert blocked.status == "blocked"
    assert blocked.eligible_lap_count == 0
    assert blocked.trusted_event_count == 0
    assert any("complete flying laps" in step for step in blocked.recovery_steps)
    assert blocked.citations[0].valid_for_tuning is False

    ready = assess_data_quality(
        laps=[_lap()],
        events=[_event("valid-event")],
        capability=CapabilityAssessment(status="ready"),
    )
    assert ready.status == "ready"
    assert ready.eligible_lap_count == 1
    assert ready.trusted_event_count == 1
    assert ready.issues == ()


def test_data_quality_does_not_treat_unknown_or_limited_capability_as_ready() -> None:
    unknown = assess_data_quality(
        laps=[_lap()],
        events=[_event("valid-event")],
        capability=CapabilityAssessment(status="unknown"),
    )
    assert unknown.status == "limited"
    assert "has not been assessed" in unknown.issues[0]
    limited = assess_data_quality(
        laps=[_lap()],
        events=[_event("valid-event")],
        capability=CapabilityAssessment(status="limited"),
    )
    assert limited.status == "limited"
    assert limited.recovery_steps


def test_data_quality_blocks_duplicate_lap_and_event_identities() -> None:
    quality = assess_data_quality(
        laps=[_lap(), _lap()],
        events=[_event("duplicate"), _event("duplicate")],
        capability=CapabilityAssessment(status="ready"),
    )
    assert quality.status == "blocked"
    assert quality.trusted_event_count == 0
    assert any("Duplicate" in issue for issue in quality.issues)


def test_action_contract_cannot_expose_an_unauthorized_setup_target() -> None:
    with pytest.raises(ValidationError, match="unauthorized actions cannot expose setup values"):
        IntelligenceAction(
            kind="discriminator",
            title="Measure",
            instruction="Measure first.",
            setup_authorized=False,
            control_key="cross_weight_percent",
            current_value="50.0%",
            proposed_value="50.1%",
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
        )


def _report():
    graph, ranked = _ranked_fixture()
    plan = plan_best_next_measurement(ranked)
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support"), _event("event-support-2"), _event("event-against")],
        capability=CapabilityAssessment(status="ready"),
    )
    return build_internal_intelligence_report(
        run_id="run-1",
        session_id="session-1",
        issue="Repeatable exit loss",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan,
        data_quality=quality,
        calibration=CalibrationSummary(
            status="available",
            evaluated_predictions=9,
            correct_direction_count=7,
            note="Direction only; magnitude is not calibrated.",
        ),
        narrative=("Exit loss observed.", "Cause discriminator selected."),
    )


def _authorized_report():
    graph, ranked = _ranked_fixture()
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        graph=graph,
    )
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support"), _event("event-support-2")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        session_id="session-1",
        issue="Repeatable exit loss",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan,
        data_quality=quality,
    )
    assert report.briefing.action.setup_authorized is True
    return report


def test_report_hides_a_controlled_target_when_current_data_is_not_ready() -> None:
    graph, ranked = _ranked_fixture()
    controlled_plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        graph=graph,
    )
    limited_quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support")],
        capability=CapabilityAssessment(status="limited"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Exit loss",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=controlled_plan,
        data_quality=limited_quality,
    )
    assert report.status == "blocked"
    assert report.best_measurement.kind == "blocked"
    assert report.briefing.action.kind == "no_call"
    assert report.briefing.action.setup_authorized is False
    assert report.briefing.action.control_key is None
    assert report.briefing.action.proposed_value is None


def test_report_rejects_ready_data_quality_from_another_run() -> None:
    graph, ranked = _ranked_fixture()
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        graph=graph,
    )
    stale_quality = assess_data_quality(
        laps=[_lap(run_id="old-run")],
        events=[_event("old-event", run_id="old-run")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Exit loss",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan,
        data_quality=stale_quality,
    )
    assert report.status == "blocked"
    assert report.data_quality.status == "blocked"
    assert report.briefing.action.setup_authorized is False


def test_report_graph_labels_never_expose_unrelated_exact_action_prose() -> None:
    graph = build_evidence_graph(
        claims=[
            GroundedClaim(
                claim_id="unsafe-claim",
                text="Set tape to 99% now.",
                evidence_state=EvidenceState.CALCULATED,
                supporting_event_ids=("missing",),
            )
        ],
        events=[
            _event("event-support"),
            _event("event-support-2"),
            _event("event-against"),
        ],
        laps=[_lap()],
        setup_values=[_setup_authority()],
        setup_authority_verifier=_setup_authority_verifier,
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="platform",
                label="Set tape to 99%",
                hypothesis="Set tape to 99%.",
                supporting_event_ids=("event-support", "event-support-2"),
            )
        ],
        graph,
    )
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        graph=graph,
    )
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support"), _event("event-support-2")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Set tape to 99%",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan,
        data_quality=quality,
    )
    assert report.briefing.action.setup_authorized is True
    assert "99%" not in report.model_dump_json()
    unsafe_claim = next(
        node for node in report.evidence_graph.nodes if node.node_id == "claim:unsafe-claim"
    )
    assert unsafe_claim.label == "Evidence claim"


def test_public_report_withholds_noncanonical_source_channel_prose() -> None:
    malicious = _event(
        "malicious-channel",
        channels=["speed_mph", "Set tape to 99%"],
    )
    graph = build_evidence_graph(events=[malicious], laps=[_lap()])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="malicious",
                label="Malicious",
                hypothesis="A malformed channel cannot ground a cause.",
                supporting_event_ids=("malicious-channel",),
            )
        ],
        graph,
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Malformed channel",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=assess_data_quality(
            laps=[_lap()],
            events=[malicious],
            capability=CapabilityAssessment(status="ready"),
        ),
    )
    assert "set tape" not in report.model_dump_json().casefold()
    assert all(
        node.entity_id != "Set tape to 99%"
        for node in report.evidence_graph.nodes
    )
    assert answer_grounded_query("What evidence supports this?", report).citations == ()


def test_unauthorized_report_structurally_redacts_all_injected_action_prose() -> None:
    graph, ranked = _ranked_fixture()
    malicious_node = EvidenceNode(
        node_id="claim:unsafe-public",
        entity_id="unsafe-public",
        kind=EvidenceNodeKind.CLAIM,
        label="Set tape to 99% now.",
        evidence_state=EvidenceState.UNAVAILABLE,
        blocker_reasons=("Set tape to 99% to recover.",),
    )
    graph = EvidenceGraph(
        nodes=(*graph.nodes, malicious_node),
        edges=graph.edges,
        blocker_reasons=("Set tape to 99%.",),
    )
    assert ranked[0].discriminator is not None
    malicious_discriminator = ranked[0].discriminator.model_copy(
        update={
            "title": "Set tape to 99%",
            "instruction": "Set tape to 99% now.",
            "target_phase": "Set tape to 99%",
            "acceptance_thresholds": ("Keep tape at 99%",),
        }
    )
    malicious_rank = ranked[0].model_copy(
        update={
            "label": "Set tape to 99%",
            "hypothesis": "Set tape to 99%",
            "discriminator": malicious_discriminator,
        }
    )
    plan = plan_best_next_measurement((malicious_rank, *ranked[1:]))
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support")],
        capability=CapabilityAssessment(status="limited"),
    ).model_copy(
        update={
            "issues": ("Set tape to 99%",),
            "recovery_steps": ("Set tape to 99%",),
        }
    )
    memory = ResponseMemorySummary(
        context_key=None,
        status="no_qualified_history",
        control_key="cross_weight_percent",
        direction_sign=1,
        qualified_observation_count=0,
        blocker_reasons=("Set tape to 99%",),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Set tape to 99%",
        graph=graph,
        ranked_causes=(malicious_rank, *ranked[1:]),
        best_measurement=plan,
        data_quality=quality,
        context_matches=(memory,),
        calibration=CalibrationSummary(note="Set tape to 99%"),
        narrative=("Set tape to 99%",),
        suggested_questions=("Why this call? Set tape to 99%",),
    )
    assert report.briefing.action.setup_authorized is False
    serialized = report.model_dump_json().casefold()
    assert "99%" not in serialized
    assert "set tape" not in serialized


def test_report_and_queries_withhold_cross_run_cause_evidence() -> None:
    old_graph, old_ranked = _ranked_fixture()
    current_quality = assess_data_quality(
        laps=[_lap(run_id="current-run")],
        events=[_event("current-event", run_id="current-run")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="current-run",
        issue="Current issue",
        graph=old_graph,
        ranked_causes=old_ranked,
        best_measurement=plan_best_next_measurement(old_ranked),
        data_quality=current_quality,
    )
    assert all(cause.state != "leading" for cause in report.competing_causes)
    assert all(not cause.evidence_for for cause in report.competing_causes)
    for question in ("Where is the loss?", "What evidence supports this?"):
        result = answer_grounded_query(question, report)
        assert result.citations == ()
        assert result.suggested_navigation == ()


def test_report_recomputes_current_run_ranks_after_cross_run_evidence_is_withheld() -> None:
    graph = build_evidence_graph(
        events=[
            _event("a-current", run_id="current"),
            _event("a-old", run_id="old"),
            _event("b-current", run_id="current"),
        ],
        laps=[_lap(run_id="current"), _lap(run_id="old")],
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="a",
                label="A",
                hypothesis="A",
                supporting_event_ids=("a-current", "a-old"),
            ),
            CauseHypothesis(
                cause_id="b",
                label="B",
                hypothesis="B",
                supporting_event_ids=("b-current",),
            ),
        ],
        graph,
    )
    assert ranked[0].cause_id == "a" and ranked[0].status == "likely"
    quality = assess_data_quality(
        laps=[_lap(run_id="current")],
        events=[_event("a-current", run_id="current"), _event("b-current", run_id="current")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="current",
        issue="Current issue",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert all(cause.state != "leading" for cause in report.competing_causes)
    assert {cause.rank for cause in report.competing_causes} == {1}


def test_report_dedupes_forged_ranked_evidence_and_rejects_duplicate_causes() -> None:
    graph = build_evidence_graph(
        events=[_event("event-a"), _event("event-b")],
        laps=[_lap()],
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="a",
                label="A",
                hypothesis="A",
                supporting_event_ids=("event-a",),
            ),
            CauseHypothesis(
                cause_id="b",
                label="B",
                hypothesis="B",
                supporting_event_ids=("event-b",),
            ),
        ],
        graph,
    )
    forged_a = ranked[0].model_copy(
        update={"supporting_evidence": ranked[0].supporting_evidence * 2}
    )
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-a"), _event("event-b")],
        capability=CapabilityAssessment(status="ready"),
    )
    forged_report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Forged rank",
        graph=graph,
        ranked_causes=(forged_a, ranked[1]),
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert all(cause.state != "leading" for cause in forged_report.competing_causes)
    assert {cause.rank for cause in forged_report.competing_causes} == {1}
    assert any("duplicate evidence" in reason for reason in forged_report.blocker_reasons)

    duplicate_report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Duplicate cause",
        graph=graph,
        ranked_causes=(ranked[0], ranked[0], ranked[1]),
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert [cause.cause_id for cause in duplicate_report.competing_causes] == ["b"]
    assert duplicate_report.competing_causes[0].state != "leading"
    assert any("Duplicate ranked cause" in reason for reason in duplicate_report.blocker_reasons)

    normalized_report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Duplicate blocker text",
        graph=graph,
        ranked_causes=(
            ranked[0].model_copy(
                update={"blocker_reasons": ("same blocker", "same blocker")}
            ),
            ranked[1].model_copy(update={"blocker_reasons": ("same blocker",)}),
        ),
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert {cause.rank for cause in normalized_report.competing_causes} == {1}


def test_loss_and_support_queries_never_promote_contradicting_evidence() -> None:
    graph = build_evidence_graph(events=[_event("against")], laps=[_lap()])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="driver",
                label="Driver line",
                hypothesis="Driver line explains the loss.",
                contradicting_event_ids=("against",),
            )
        ],
        graph,
    )
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("against")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Exit loss",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert report.competing_causes[0].state == "unresolved"
    assert report.competing_causes[0].evidence_against
    assert answer_grounded_query("Where is the loss?", report).citations == ()
    assert answer_grounded_query("What evidence supports this?", report).citations == ()


def test_what_next_requires_exact_run_and_selected_lap_card_citations() -> None:
    graph, ranked = _ranked_fixture()
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        graph=graph,
    )
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("event-support"), _event("event-support-2"), _event("event-against")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Exit loss",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan,
        data_quality=quality,
    )
    exact = answer_grounded_query(
        "What should I do next?",
        report,
        selected_lap_number=4,
    )
    assert exact.action_authorized is True
    assert [citation.event_id for citation in exact.citations] == ["event-support"]
    assert exact.action_source_event_ids == ("event-support",)
    assert "50.1%" in exact.answer
    wrong_lap = answer_grounded_query(
        "What should I do next?",
        report,
        selected_lap_number=5,
    )
    assert wrong_lap.action_authorized is False
    assert wrong_lap.citations == ()
    assert wrong_lap.supported is False
    assert wrong_lap.clarification_required is True
    assert "does not belong to run" in wrong_lap.answer
    for question in ("Why this call?", "What would change your mind?"):
        non_action = answer_grounded_query(question, report, selected_lap_number=4)
        assert non_action.action_authorized is False
        assert "50.1%" not in non_action.answer

    forged_action = report.briefing.action.model_copy(
        update={
            "instruction": "50.0% -> 99.0%",
            "proposed_value": "99.0%",
        }
    )
    forged_report = report.model_copy(
        update={
            "briefing": report.briefing.model_copy(update={"action": forged_action})
        }
    )
    forged_answer = answer_grounded_query("What should I do next?", forged_report)
    assert forged_answer.action_authorized is False
    assert "99.0%" not in forged_answer.answer
    assert forged_answer.citations == ()


def test_queries_reanchor_forged_cause_citations_to_the_qualified_graph() -> None:
    report = _report()
    leading_index = 0
    leading = report.competing_causes[leading_index]
    ghost = EvidenceCitation(
        citation_id="event:ghost",
        run_id="run-1",
        lap_number=4,
        lap_pct_start=0.0,
        lap_pct_end=2.0,
        lap_pct_peak=1.0,
        event_id="ghost",
        workspace="platform",
        channels=("speed_mph",),
        evidence_state=EvidenceState.CALCULATED,
        valid_for_tuning=True,
        summary="Invented evidence.",
    )
    forged_leading = leading.model_copy(
        update={"state": "leading", "evidence_for": (ghost,)}
    )
    causes = list(report.competing_causes)
    causes[leading_index] = forged_leading
    forged_report = report.model_copy(update={"competing_causes": tuple(causes)})
    for question in (
        "Why this call?",
        "Where is the loss?",
        "What evidence supports this?",
    ):
        result = answer_grounded_query(question, forged_report)
        assert all(citation.event_id != "ghost" for citation in result.citations)
        assert "1%" not in result.answer


def test_selected_lap_queries_demote_run_wide_leaders_on_local_ties() -> None:
    graph = build_evidence_graph(
        events=[
            _event("a-4", lap_number=4),
            _event("a-5", lap_number=5),
            _event("b-4", lap_number=4),
        ],
        laps=[_lap(4), _lap(5)],
    )
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="a",
                label="A",
                hypothesis="A",
                supporting_event_ids=("a-4", "a-5"),
            ),
            CauseHypothesis(
                cause_id="b",
                label="B",
                hypothesis="B",
                supporting_event_ids=("b-4",),
            ),
        ],
        graph,
    )
    quality = assess_data_quality(
        laps=[_lap(4), _lap(5)],
        events=[
            _event("a-4", lap_number=4),
            _event("a-5", lap_number=5),
            _event("b-4", lap_number=4),
        ],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Run-wide ordering",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert all(cause.state != "leading" for cause in report.competing_causes)
    local_why = answer_grounded_query("Why this call?", report, selected_lap_number=4)
    assert "leads" not in local_why.answer
    assert local_why.citations == ()
    local_evidence = answer_grounded_query(
        "What evidence supports this?", report, selected_lap_number=4
    )
    assert {citation.event_id for citation in local_evidence.citations} == {"a-4", "b-4"}


def test_selected_lap_cannot_upgrade_a_run_wide_possible_cause() -> None:
    graph = build_evidence_graph(events=[_event("possible-4")], laps=[_lap()])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="possible",
                label="Possible",
                hypothesis="Yaw evidence is still missing.",
                supporting_event_ids=("possible-4",),
                required_evidence=("Need the yaw trace",),
            )
        ],
        graph,
    )
    quality = assess_data_quality(
        laps=[_lap()],
        events=[_event("possible-4")],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Possible only",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    assert report.competing_causes[0].state == "possible"
    result = answer_grounded_query("Why this call?", report, selected_lap_number=4)
    assert "leads" not in result.answer
    assert result.citations == ()


def test_selected_lap_data_quality_reports_absent_and_ineligible_laps() -> None:
    eligible = _lap(4)
    junk = _lap(5, useful=False, tags=["COOLDOWN", "NO_SETUP_CONCLUSION"])
    event = _event("event-4", lap_number=4)
    graph = build_evidence_graph(events=[event], laps=[eligible, junk])
    ranked = rank_competing_causes(
        [
            CauseHypothesis(
                cause_id="event",
                label="Event",
                hypothesis="One event.",
                supporting_event_ids=("event-4",),
            )
        ],
        graph,
    )
    quality = assess_data_quality(
        laps=[eligible, junk],
        events=[event],
        capability=CapabilityAssessment(status="ready"),
    )
    report = build_internal_intelligence_report(
        run_id="run-1",
        issue="Data quality",
        graph=graph,
        ranked_causes=ranked,
        best_measurement=plan_best_next_measurement(ranked),
        data_quality=quality,
    )
    absent = answer_grounded_query("Is the data good?", report, selected_lap_number=999)
    assert absent.supported is False
    assert absent.clarification_required is True
    assert "does not belong to run" in absent.answer
    assert absent.citations == ()
    assert absent.blocker_reasons
    blocked = answer_grounded_query("Is the data good?", report, selected_lap_number=5)
    assert "blocked" in blocked.answer
    assert blocked.citations[0].lap_number == 5
    assert blocked.blocker_reasons


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Why this call?", "why_this_call"),
        ("Where am I losing time?", "where_is_loss"),
        ("Where is the strongest repeatable loss?", "where_is_loss"),
        ("What should I do next?", "what_next"),
        ("What evidence supports this?", "what_evidence"),
        ("What was ruled out?", "what_was_ruled_out"),
        ("How reliable is this?", "how_reliable"),
        ("What would change your mind?", "what_would_change_mind"),
        ("Is the data good?", "data_quality"),
    ],
)
def test_grounded_query_supported_vocabulary(question: str, intent: str) -> None:
    result = answer_grounded_query(question, _report())
    assert result.supported is True
    assert result.intent == intent
    assert result.answer
    if result.citations:
        assert all(citation.run_id == "run-1" for citation in result.citations)
        assert result.suggested_navigation


def test_grounded_query_uses_canonical_track_region_as_evidence_scope() -> None:
    def resolve_region(_run_id: str, lap_pct: float) -> dict[str, object]:
        return {
            "region_id": "turn_2" if lap_pct < 50.0 else "turn_3",
            "label": "Turn 2" if lap_pct < 50.0 else "Turn 3",
            "phase": "center",
        }

    result = answer_grounded_query(
        "T2",
        _report(),
        track_region_resolver=resolve_region,
        track_region_catalog={"turn_1": "Turn 1", "turn_2": "Turn 2"},
    )

    assert result.supported is True
    assert result.intent == "what_evidence"
    assert result.interpreted_track_region_id == "turn_2"
    assert result.interpreted_track_region_label == "Turn 2"
    assert result.citations
    assert result.answer.startswith("Turn 2 scope:")


def test_grounded_query_turn_phase_uses_physical_region_phase() -> None:
    result = answer_grounded_query(
        "What happened in Turn 2 exit?",
        _report(),
        track_region_resolver=lambda _run_id, _lap_pct: {
            "region_id": "turn_2",
            "label": "Turn 2",
            "phase": "center",
        },
        track_region_catalog={"turn_2": "Turn 2"},
    )

    assert result.supported is True
    assert result.interpreted_phase == "exit"
    assert result.citations == ()
    assert any("Turn 2" in reason for reason in result.blocker_reasons)


def test_grounded_query_uses_named_straight_as_evidence_scope() -> None:
    result = answer_grounded_query(
        "What happened on Backstretch?",
        _report(),
        track_region_resolver=lambda _run_id, _lap_pct: {
            "region_id": "straight:backstretch",
            "label": "Backstretch",
            "phase": "straight",
        },
        track_region_catalog={"backstretch": "Backstretch"},
    )

    assert result.supported is True
    assert result.interpreted_track_region_id == "backstretch"
    assert result.citations
    assert result.answer.startswith("Backstretch scope:")


def test_grounded_query_rejects_region_not_defined_on_matched_layout() -> None:
    result = answer_grounded_query(
        "Inspect Turn 5",
        _report(),
        track_region_resolver=lambda _run_id, _lap_pct: None,
        track_region_catalog={"turn_1": "Turn 1", "turn_2": "Turn 2"},
    )

    assert result.supported is False
    assert result.clarification_required is True
    assert result.interpreted_track_region_id == "turn_5"
    assert "not defined" in result.answer
    assert "Turn 1, Turn 2" in result.answer


def test_grounded_query_rejects_ambiguous_multiple_regions() -> None:
    result = answer_grounded_query(
        "Compare Turn 1 and Turn 3 evidence",
        _report(),
        track_region_resolver=lambda _run_id, _lap_pct: None,
        track_region_catalog={"turn_1": "Turn 1", "turn_3": "Turn 3"},
    )

    assert result.supported is False
    assert result.clarification_required is True
    assert "more than one track region" in result.answer


def test_strongest_repeatable_loss_query_does_not_invent_strength_or_recurrence() -> None:
    result = answer_grounded_query(
        "Where is the strongest repeatable loss?",
        _report(),
    )
    assert result.intent == "where_is_loss"
    assert "does not carry" in result.answer
    assert result.blocker_reasons


def test_grounded_query_reliability_is_observed_and_not_a_probability() -> None:
    result = answer_grounded_query("How reliable is this?", _report())
    assert "7 of 9" in result.answer
    assert "not a probability" in result.answer
    assert result.citations == ()
    assert "Prediction-grade citations" in result.answer
    assert result.blocker_reasons


def test_loss_location_order_is_deterministic_by_physical_position() -> None:
    early = _event("early").model_copy(
        update={
            "lap_number": 5,
            "lap_pct_start": 10.0,
            "lap_pct_peak": 11.0,
            "lap_pct_end": 12.0,
        }
    )
    late = _event("late").model_copy(
        update={"lap_pct_start": 80.0, "lap_pct_peak": 81.0, "lap_pct_end": 82.0}
    )
    graph = build_evidence_graph(events=[early, late], laps=[_lap(), _lap(5)])
    quality = assess_data_quality(
        laps=[_lap(), _lap(5)],
        events=[early, late],
        capability=CapabilityAssessment(status="ready"),
    )
    answers: set[str] = set()
    for event_ids in (("late", "early"), ("early", "late")):
        ranked = rank_competing_causes(
            [
                CauseHypothesis(
                    cause_id="location",
                    label="Location",
                    hypothesis="The physical zone repeats.",
                    supporting_event_ids=event_ids,
                )
            ],
            graph,
        )
        report = build_internal_intelligence_report(
            run_id="run-1",
            issue="Location",
            graph=graph,
            ranked_causes=ranked,
            best_measurement=plan_best_next_measurement(ranked),
            data_quality=quality,
        )
        result = answer_grounded_query("Where is the loss?", report)
        answers.add(result.answer)
        assert result.citations[0].event_id == "early"
    assert len(answers) == 1


def test_worked_before_query_links_exact_context_source_runs() -> None:
    context = _context()
    memory = summarize_response_memory(
        response_context=context,
        response_graph={
            "context_key": context.key,
            "edges": [
                _memory_edge("history-1", delta=0.1, effect=-0.05),
                _memory_edge("history-2", delta=0.2, effect=-0.08),
            ],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
        proposed_delta=0.15,
    )
    report = _report().model_copy(
        update={
            "context_matches": (memory,),
            "response_context_key": memory.context_key,
        }
    )
    result = answer_grounded_query("What worked here before?", report)
    assert result.citations == ()
    assert result.suggested_navigation
    assert {target.run_id for target in result.suggested_navigation} == set(
        memory.source_run_ids
    )
    assert "Context Memory" in result.answer


def test_worked_before_rejects_wrong_context_and_dedupes_identical_summaries() -> None:
    current = _context()
    other = _context(driver_id="other-driver")
    other_summary = summarize_response_memory(
        response_context=other,
        response_graph={
            "context_key": other.key,
            "edges": [_memory_edge("other", delta=0.1, effect=-0.05)],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    wrong = _report().model_copy(
        update={
            "response_context_key": current.key,
            "context_matches": (other_summary,),
        }
    )
    wrong_answer = answer_grounded_query("What worked here before?", wrong)
    assert wrong_answer.suggested_navigation == ()
    assert wrong_answer.blocker_reasons

    current_summary = summarize_response_memory(
        response_context=current,
        response_graph={
            "context_key": current.key,
            "edges": [_memory_edge("current", delta=0.1, effect=-0.05)],
        },
        control_key="cross_weight_percent",
        direction_sign=1,
        target_zone_start_pct=42.0,
        target_zone_end_pct=45.0,
        surrounding_setup_fingerprint="surrounding-a",
    )
    duplicated = _report().model_copy(
        update={
            "response_context_key": current.key,
            "context_matches": (current_summary, current_summary),
        }
    )
    duplicated_answer = answer_grounded_query("What worked here before?", duplicated)
    assert "1 qualified" in duplicated_answer.answer


def test_grounded_query_change_mind_returns_one_discriminator() -> None:
    result = answer_grounded_query("What would change your mind?", _report())
    assert result.mind_change_criteria
    assert result.mind_change_criteria[0].acceptance_conditions == (
        "Three eligible marked passes",
    )
    assert "Three eligible marked passes" in result.answer


def test_grounded_query_rejects_open_ended_prompts_instead_of_hallucinating() -> None:
    result = answer_grounded_query("Invent the fastest setup", _report())
    assert result.supported is False
    assert result.intent == "unsupported"
    assert result.citations == ()
    assert result.blocker_reasons


def test_report_preserves_measurement_only_authority() -> None:
    report = _report()
    assert report.status == "measure"
    assert report.briefing.action.kind == "discriminator"
    assert report.briefing.action.setup_authorized is False
    assert report.briefing.action.control_key is None
    assert report.competing_causes[0].state == "possible"
    assert "How reliable is this?" in report.suggested_questions


def test_flexible_query_parser_binds_lap_scope_and_rejects_conflicts() -> None:
    report = _report()
    parsed = answer_grounded_query(
        "Could you show me where the time loss is on lap 4?",
        report,
    )
    assert parsed.supported is True
    assert parsed.intent == "where_is_loss"
    assert parsed.interpreted_lap_number == 4
    assert all(citation.lap_number == 4 for citation in parsed.citations)

    conflict = answer_grounded_query(
        "Where is the loss on lap 7?",
        report,
        selected_lap_number=4,
    )
    assert conflict.supported is False
    assert conflict.clarification_required is True
    assert conflict.citations == ()


def test_hyphenated_lap_window_requires_an_explicit_representative() -> None:
    result = answer_grounded_query(
        "Where is the loss on laps 4-5?",
        _report(),
    )

    assert result.supported is False
    assert result.clarification_required is True
    assert "representative lap" in result.answer
    assert result.interpreted_window_start_lap is None
    assert result.interpreted_window_end_lap is None
    assert result.interpreted_window_representative_lap is None
    assert result.citations == ()


def test_anomaly_query_withholds_a_stronger_finding_outside_selected_lap() -> None:
    report = _report()
    citation = ObservationCitation(
        run_id="run-1",
        lap_number=5,
        setup_id="setup-a",
        lap_pct_start=10.0,
        lap_pct_end=20.0,
        lap_pct_peak=15.0,
        phase="entry",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=("lap_dist_pct_100", "speed_mph"),
        telemetry_sample_count=10,
    )
    anomaly = SameSetupAnomaly(
        anomaly_id="lap-5-anomaly",
        run_id="run-1",
        setup_id="setup-a",
        lap_number=5,
        channel="speed_mph",
        direction="below_envelope",
        phase="entry",
        lap_pct_start=10.0,
        lap_pct_end=20.0,
        lap_pct_peak=15.0,
        reference_lap_numbers=(1, 2),
        repetition_count=2,
        telemetry_sample_count=10,
        aligned_bin_count=40,
        median_observed_value=90.0,
        median_reference_value=100.0,
        median_absolute_deviation=1.0,
        source_channels=("lap_dist_pct_100", "speed_mph"),
        citations=(citation,),
    )
    anomalies = SameSetupAnomalyReport(
        status=ObservationStatus.READY,
        run_id="run-1",
        setup_id="setup-a",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        required_channels=("lap_dist_pct_100", "speed_mph"),
        source_channels=("lap_dist_pct_100", "speed_mph"),
        eligible_lap_numbers=(1, 2, 5),
        eligible_lap_count=3,
        reference_lap_count=2,
        telemetry_sample_count=30,
        anomalies=(anomaly,),
    )

    result = answer_grounded_query(
        "Show anomalies",
        report.model_copy(update={"anomalies": anomalies}),
        selected_lap_number=4,
    )

    assert result.supported is True
    assert result.interpreted_lap_number == 4
    assert result.citations == ()
    assert "lap 5" not in result.answer
    assert result.blocker_reasons


def test_what_changed_uses_current_run_vs_immediately_previous_only() -> None:
    def entry(entry_id: str, baseline: str, test: str, description: str):
        return SessionLedgerEntry(
            entry_id=entry_id,
            state="recurring",
            observation_kind="recurring_issue",
            baseline_run_id=baseline,
            test_run_id=test,
            description=description,
            evidence_scope="event_signature",
            citations=(
                SessionEvidenceCitation(
                    kind="run",
                    reference_id=baseline,
                    run_id=baseline,
                ),
                SessionEvidenceCitation(
                    kind="run",
                    reference_id=test,
                    run_id=test,
                ),
            ),
        )

    ledger = SessionEngineeringLedger(
        session_id="session-1",
        session_scope_sha256="0" * 64,
        status="ready",
        ordered_run_ids=("run-0", "run-1", "run-2"),
        entries=(
            entry("before", "run-0", "run-1", "Current run versus previous run."),
            entry("after", "run-1", "run-2", "Future run versus current run."),
        ),
    )

    result = answer_grounded_query(
        "What changed?",
        _report().model_copy(update={"session_ledger": ledger}),
    )

    assert "Current run versus previous run" in result.answer
    assert "Future run" not in result.answer


def test_blocker_aware_measurement_candidate_prefers_feasible_short_contract() -> None:
    graph, ranked = _ranked_fixture()
    unavailable = MeasurementCandidate(
        candidate_id="missing-yaw",
        title="Measure yaw response",
        purpose="Resolve the rotation measurement blocker.",
        procedure=("Record three unchanged-setup exit passes with yaw rate.",),
        required_channels=("yaw_rate",),
        available_channels=("speed_mph",),
        resolves_blocker_ids=("rotation", "driver"),
        distinguishes_cause_ids=(),
        required_laps=3,
        target_phase="exit",
        acceptance_thresholds=("Three eligible aligned passes",),
        stop_rule="Stop after an incident or telemetry fault.",
        controlled_variables=("setup", "fuel", "tires", "line"),
    )
    feasible = unavailable.model_copy(
        update={
            "candidate_id": "speed-repeatability",
            "title": "Repeat the exit window",
            "required_channels": ("speed_mph",),
            "available_channels": ("speed_mph",),
            "resolves_blocker_ids": ("repeatability",),
            "required_laps": 2,
        }
    )
    plan = plan_best_next_measurement(
        ranked,
        measurement_candidates=(unavailable, feasible),
        known_measurement_blockers=(
            MeasurementBlocker(
                blocker_id="rotation",
                priority="discrimination",
                reason="Rotation response is unresolved.",
                resolving_candidate_ids=("missing-yaw",),
            ),
            MeasurementBlocker(
                blocker_id="driver",
                priority="discrimination",
                reason="Driver response is unresolved.",
                resolving_candidate_ids=("missing-yaw",),
            ),
            MeasurementBlocker(
                blocker_id="repeatability",
                priority="repetition",
                reason="The exit window needs another eligible repetition.",
                resolving_candidate_ids=("speed-repeatability",),
            ),
        ),
        known_available_channels=("speed_mph",),
        graph=graph,
        current_run_id="run-1",
    )
    assert plan.kind == "measurement_mission"
    assert plan.title == "Repeat the exit window"
    assert plan.setup_authorized is False


def test_current_run_integrity_prerequisite_outranks_an_authorized_test() -> None:
    graph, ranked = _ranked_fixture()

    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=_director(),
        planning_prerequisite=MeasurementBlocker(
            blocker_id="current-run:evidence-integrity",
            priority="integrity",
            reason="Re-bind the exact current-run artifact before engineering work.",
        ),
        graph=graph,
    )

    assert plan.kind == "blocked"
    assert plan.setup_authorized is False
    assert plan.recovery_priority == "integrity"


def test_measurement_candidate_ghost_references_cannot_rank_or_publish() -> None:
    graph, ranked = _ranked_fixture()
    legitimate = MeasurementCandidate(
        candidate_id="repeat-speed",
        title="Repeat the speed window",
        purpose="Resolve the current repeatability blocker.",
        procedure=("Record one additional unchanged-setup eligible pass.",),
        required_channels=("speed_mph",),
        available_channels=("speed_mph",),
        resolves_blocker_ids=("repeatability",),
        required_laps=1,
        target_phase="exit",
        acceptance_thresholds=("One additional eligible aligned pass",),
        stop_rule="Stop after an incident or telemetry fault.",
        controlled_variables=("setup", "fuel", "tires", "line"),
        source_event_ids=("event-support",),
    )
    ghost = legitimate.model_copy(
        update={
            "candidate_id": "ghost-inflation",
            "title": "Do not select this candidate",
            "resolves_blocker_ids": tuple(f"ghost-blocker-{index}" for index in range(10)),
            "distinguishes_cause_ids": ("ghost-cause",),
            "source_event_ids": ("ghost-event",),
        }
    )
    hijacker = legitimate.model_copy(
        update={
            "candidate_id": "blocker-hijacker",
            "title": "Do not let this candidate borrow another mission's blocker",
        }
    )
    cause_borrower = legitimate.model_copy(
        update={
            "candidate_id": "cause-borrower",
            "title": "Do not let this candidate borrow producer cause coverage",
            "resolves_blocker_ids": ("borrower-repeatability",),
            "distinguishes_cause_ids": tuple(cause.cause_id for cause in ranked),
            "required_laps": 5,
        }
    )
    blockers = (
        MeasurementBlocker(
            blocker_id="repeatability",
            priority="repetition",
            reason="The current window needs one more eligible repetition.",
            resolving_candidate_ids=("repeat-speed",),
        ),
        MeasurementBlocker(
            blocker_id="borrower-repeatability",
            priority="repetition",
            reason="A separate producer mission owns this repetition blocker.",
            resolving_candidate_ids=("cause-borrower",),
        ),
    )

    audit = evaluate_measurement_candidates(
        ranked,
        (ghost, hijacker, cause_borrower, legitimate),
        known_blockers=blockers,
        known_available_channels=("speed_mph",),
        graph=graph,
        current_run_id="run-1",
    )
    ghost_evaluation = next(
        item for item in audit.evaluations if item.candidate_id == "ghost-inflation"
    )
    assert audit.selected_candidate_id == "repeat-speed"
    assert ghost_evaluation.admissible is False
    assert {
        "unknown_blocker_reference",
        "unknown_cause_reference",
        "unknown_event_reference",
    }.issubset(ghost_evaluation.rejection_reasons)
    hijacker_evaluation = next(
        item for item in audit.evaluations if item.candidate_id == "blocker-hijacker"
    )
    assert hijacker_evaluation.admissible is False
    assert "unauthorized_blocker_claim" in hijacker_evaluation.rejection_reasons
    borrower_evaluation = next(
        item for item in audit.evaluations if item.candidate_id == "cause-borrower"
    )
    assert borrower_evaluation.admissible is False
    assert borrower_evaluation.cause_coverage == 0
    assert "unauthorized_cause_claim" in borrower_evaluation.rejection_reasons

    plan = plan_best_next_measurement(
        ranked,
        measurement_candidates=(ghost, hijacker, cause_borrower, legitimate),
        known_measurement_blockers=blockers,
        known_available_channels=("speed_mph",),
        graph=graph,
        current_run_id="run-1",
    )
    assert plan.kind == "measurement_mission"
    assert plan.title == "Repeat the speed window"
    assert plan.source_event_ids == ("event-support",)
    cross_run_audit = evaluate_measurement_candidates(
        ranked,
        (legitimate,),
        known_blockers=blockers,
        known_available_channels=("speed_mph",),
        graph=graph,
        current_run_id="different-run",
    )
    assert cross_run_audit.selected_candidate_id is None
    assert cross_run_audit.evaluations[0].rejection_reasons == (
        "cross_run_event_reference",
    )
    owned_discriminator = legitimate.model_copy(
        update={
            "candidate_id": "d-platform",
            "resolves_blocker_ids": (),
            "distinguishes_cause_ids": ("platform", "driver"),
            "required_laps": 3,
        }
    )
    owned_audit = evaluate_measurement_candidates(
        ranked,
        (owned_discriminator,),
        known_available_channels=("speed_mph",),
        graph=graph,
        current_run_id="run-1",
    )
    assert owned_audit.selected_candidate_id == "d-platform"
    assert owned_audit.evaluations[0].admissible is True
    assert "platform" in owned_audit.evaluations[0].distinguished_cause_ids


def test_duplicate_measurement_candidate_id_fails_selection_closed() -> None:
    graph, ranked = _ranked_fixture()
    candidate = MeasurementCandidate(
        candidate_id="duplicate",
        title="Repeat the exit window",
        purpose="Resolve one current prerequisite.",
        procedure=("Record one additional unchanged-setup eligible pass.",),
        required_channels=("speed_mph",),
        available_channels=("speed_mph",),
        resolves_blocker_ids=("repeatability",),
        required_laps=1,
        target_phase="exit",
        acceptance_thresholds=("One additional eligible aligned pass",),
        stop_rule="Stop after an incident or telemetry fault.",
        controlled_variables=("setup", "fuel", "tires", "line"),
    )
    blockers = (
        MeasurementBlocker(
            blocker_id="repeatability",
            priority="repetition",
            reason="The current window needs one more eligible repetition.",
            resolving_candidate_ids=("duplicate",),
        ),
    )

    plan = plan_best_next_measurement(
        ranked,
        measurement_candidates=(
            candidate,
            candidate.model_copy(update={"title": "Ambiguous duplicate"}),
        ),
        known_measurement_blockers=blockers,
        known_available_channels=("speed_mph",),
        graph=graph,
        current_run_id="run-1",
    )

    assert plan.kind == "blocked"
    assert plan.recovery_priority == "integrity"
    assert "Duplicate" in plan.blocker_reasons[0]
    guidance = build_smart_guidance(
        _report().model_copy(update={"best_measurement": plan})
    )
    assert guidance.next_trustworthy_move.kind == "recover"
    assert guidance.next_trustworthy_move.move_id == "recover:defined-discriminator"


def test_affected_channel_health_blocks_only_measurements_on_that_lineage() -> None:
    graph, ranked = _ranked_fixture()
    blocker = MeasurementBlocker(
        blocker_id="repeatability",
        priority="repetition",
        reason="The current window needs one more eligible repetition.",
        resolving_candidate_ids=("repeat-platform",),
    )
    candidate = MeasurementCandidate(
        candidate_id="repeat-platform",
        title="Repeat the platform window",
        purpose="Resolve one current prerequisite.",
        procedure=("Record one additional unchanged-setup eligible pass.",),
        required_channels=("cfs_ride_height_in",),
        available_channels=("cfs_ride_height_in",),
        resolves_blocker_ids=("repeatability",),
        required_laps=1,
        target_phase="exit",
        acceptance_thresholds=("One additional eligible aligned pass",),
        stop_rule="Stop after an incident or telemetry fault.",
        controlled_variables=("setup", "fuel", "tires", "line"),
    )
    lineage = {
        "cfs_ride_height_in": (
            "cfs_ride_height_in",
            "cfs_ride_height_m",
            "cfsrrideheight",
        ),
        "brake_pct": ("brake_pct", "brake_01", "brake"),
    }

    affected = plan_best_next_measurement(
        ranked,
        measurement_candidates=(candidate,),
        known_measurement_blockers=(blocker,),
        known_available_channels=("cfs_ride_height_in",),
        graph=graph,
        current_run_id="run-1",
        affected_health_channels=("cfs_ride_height_in",),
        channel_lineage_by_channel=lineage,
    )
    combined_audit = evaluate_measurement_candidates(
        ranked,
        (candidate,),
        known_blockers=(blocker,),
        known_available_channels=(),
        graph=graph,
        current_run_id="run-1",
        affected_health_channels=("cfs_ride_height_in",),
        channel_lineage_by_channel=lineage,
    )
    affected_and_unavailable = plan_best_next_measurement(
        ranked,
        measurement_candidates=(candidate,),
        known_measurement_blockers=(blocker,),
        known_available_channels=(),
        graph=graph,
        current_run_id="run-1",
        affected_health_channels=("cfs_ride_height_in",),
        channel_lineage_by_channel=lineage,
    )
    unrelated = plan_best_next_measurement(
        ranked,
        measurement_candidates=(candidate,),
        known_measurement_blockers=(blocker,),
        known_available_channels=("cfs_ride_height_in",),
        graph=graph,
        current_run_id="run-1",
        affected_health_channels=("brake_pct",),
        channel_lineage_by_channel=lineage,
    )

    assert affected.kind == "blocked"
    assert affected.recovery_priority == "affected_channel_health"
    assert {
        "unavailable_required_channel",
        "affected_channel_health",
    }.issubset(combined_audit.evaluations[0].rejection_reasons)
    assert affected_and_unavailable.recovery_priority == "affected_channel_health"
    assert unrelated.kind == "measurement_mission"


def test_observation_candidates_report_only_required_new_laps() -> None:
    blocked = ("One more eligible same-setup repetition is required.",)
    observations = RunObservationIntelligence(
        run_id="run-1",
        setup_id="setup-1",
        opportunity_signatures=OpportunitySignatureReport(
            status=ObservationStatus.BLOCKED,
            run_id="run-1",
            setup_id="setup-1",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            required_channels=("speed_mph",),
            source_channels=("speed_mph",),
            eligible_lap_numbers=(4, 5),
            eligible_lap_count=2,
            telemetry_sample_count=200,
            blocker_reasons=blocked,
        ),
        mechanism_observations=MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id="run-1",
            setup_id="setup-1",
            observations=(
                MechanismObservation(
                    observation_id="platform-repeat",
                    producer_id="test.platform",
                    artifact_id="platform-repeat",
                    source_run_ids=("run-1",),
                    source_setup_ids=("setup-1",),
                    sample_coverage=0.0,
                    mechanism="platform_response",
                    run_id="run-1",
                    setup_id="setup-1",
                    summary="The platform window needs one more repetition.",
                    evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                    qualified=False,
                    source_channels=("speed_mph",),
                    required_channels=("speed_mph",),
                    telemetry_sample_count=200,
                    repetition_count=2,
                    blocker_reasons=blocked,
                ),
            ),
            blocker_reasons=blocked,
        ),
        anomaly_envelopes=SameSetupAnomalyReport(
            status=ObservationStatus.BLOCKED,
            run_id="run-1",
            setup_id="setup-1",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            required_channels=("speed_mph",),
            source_channels=("speed_mph",),
            eligible_lap_numbers=(4, 5),
            eligible_lap_count=2,
            reference_lap_count=2,
            telemetry_sample_count=200,
            blocker_reasons=blocked,
        ),
        driver_repeatability=DriverRepeatabilitySignature(
            status=ObservationStatus.BLOCKED,
            run_id="run-1",
            setup_id="setup-1",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            required_channels=("speed_mph",),
            source_channels=("speed_mph",),
            eligible_lap_numbers=(4, 5),
            eligible_lap_count=2,
            telemetry_sample_count=200,
            blocker_reasons=blocked,
        ),
        blocker_reasons=blocked,
    )

    planning_inputs = _observation_measurement_candidates(observations)

    assert len(planning_inputs.candidates) == 4
    assert {candidate.required_laps for candidate in planning_inputs.candidates} == {1}
    assert all(
        "1 additional" in candidate.procedure[0]
        for candidate in planning_inputs.candidates
    )
    blockers_by_id = {
        blocker.blocker_id: blocker for blocker in planning_inputs.blockers
    }
    assert all(
        candidate.candidate_id
        in blockers_by_id[blocker_id].resolving_candidate_ids
        for candidate in planning_inputs.candidates
        for blocker_id in candidate.resolves_blocker_ids
    )


def test_smart_guidance_routes_without_inventing_setup_authority() -> None:
    guidance = build_smart_guidance(_report())
    assert guidance.mission_stage in {"diagnose", "measure"}
    assert guidance.next_trustworthy_move.authority == "navigation_only"
    assert guidance.next_trustworthy_move.workspace in {"engineer", "platform"}
    assert "Where is the strongest repeatable loss?" in guidance.contextual_questions


def test_setup_authorized_move_is_exactly_workflow_control_and_event_bound() -> None:
    workflow = _workflow().model_copy(
        update={
            "status": "a_recorded",
            "stage_run_ids": {"A": "run-1"},
            "stage_eligible_lap_numbers": {"A": (4, 5, 6)},
            "execution": None,
            "quality": None,
            "learning_admitted": False,
        }
    )
    guidance = build_smart_guidance(_authorized_report(), workflow=workflow)
    move = guidance.next_trustworthy_move
    action = _authorized_report().briefing.action

    assert move.authority == "setup_authorized"
    assert move.workflow_id == workflow.workflow_id
    assert move.workflow_updated_at == workflow.updated_at
    assert move.control_key == action.control_key
    assert move.source_event_ids == action.source_event_ids

    with pytest.raises(ValidationError, match="exact workflow-bound"):
        NextTrustworthyMove(
            move_id="hostile-unbound-test",
            kind="controlled_test",
            title="Unbound setup target",
            instruction="Do not publish this target.",
            reason="The caller omitted the exact workflow revision.",
            workspace="dial_in",
            authority="setup_authorized",
            run_id="run-1",
            control_key=action.control_key,
            source_event_ids=action.source_event_ids,
        )


def test_blocked_active_test_routes_to_review_instead_of_stage_continuation() -> None:
    workflow = _workflow().model_copy(
        update={
            "status": "planned",
            "stage_run_ids": {},
            "stage_eligible_lap_numbers": {},
            "execution": None,
            "quality": None,
            "learning_admitted": False,
        }
    )
    semantic_blocker = (
        "This unchanged hypothesis policy previously produced a valid Undo result.",
    )
    blocked_plan = InformationPlan(
        kind="blocked",
        title="Setup action withheld",
        instruction="Review the contradicted controlled hypothesis.",
        rationale="The exact semantic policy is marked do-not-repeat.",
        blocker_reasons=semantic_blocker,
    )
    base = _report()
    blocked_action = IntelligenceAction(
        kind="no_call",
        title="Setup action withheld",
        instruction="Keep the current setup.",
        evidence_state=EvidenceState.UNAVAILABLE,
        blocker_reasons=semantic_blocker,
    )
    report = base.model_copy(
        update={
            "status": "blocked",
            "best_measurement": blocked_plan,
            "briefing": base.briefing.model_copy(
                update={
                    "action": blocked_action,
                    "confidence_label": "blocked",
                    "blocker_reasons": semantic_blocker,
                }
            ),
            "blocker_reasons": semantic_blocker,
        }
    )

    guidance = build_smart_guidance(report, workflow=workflow)

    assert guidance.next_trustworthy_move.kind == "recover"
    assert guidance.next_trustworthy_move.authority == "navigation_only"
    assert guidance.next_trustworthy_move.workspace == "dial_in"
    assert "Do not record another stage" in guidance.next_trustworthy_move.instruction
    assert guidance.next_trustworthy_move.blocker_reasons == semantic_blocker
    assert guidance.test_preflight is not None
    assert guidance.test_preflight.status == "blocked"
    assert guidance.test_preflight.blocker_reasons == semantic_blocker
    assert all(
        check.check_id != "setup-state"
        for check in guidance.test_preflight.checks
    )


def test_blocked_quality_always_produces_a_recovery_move() -> None:
    report = _report()
    blocked_quality = report.data_quality.model_copy(
        update={
            "status": "blocked",
            "issues": ("Telemetry capability identity is unavailable.",),
            "recovery_steps": ("Re-import the exact run artifact.",),
        }
    )
    guidance = build_smart_guidance(
        report.model_copy(update={"data_quality": blocked_quality})
    )
    assert guidance.mission_stage == "qualify"
    assert guidance.measurement_debt.status == "blocked"
    assert guidance.measurement_debt.items[0].debt_id == "data-quality"
    assert guidance.next_trustworthy_move.kind == "recover"


def test_measurement_debt_uses_engineering_priority_not_debt_id_order() -> None:
    report = _report()
    blocked_quality = report.data_quality.model_copy(
        update={
            "status": "blocked",
            "eligible_lap_count": 0,
            "eligible_lap_ids": (),
            "trusted_event_count": 0,
            "trusted_event_ids": (),
            "issues": ("The current run has no qualified evidence.",),
            "recovery_steps": ("Record a complete eligible flying lap.",),
        }
    )
    blocked_plan = InformationPlan(
        kind="blocked",
        title="No discriminator",
        instruction="Qualify another eligible lap.",
        rationale="The current evidence does not define an executable discriminator.",
        blocker_reasons=("A current producer-owned discriminator is required.",),
    )

    guidance = build_smart_guidance(
        report.model_copy(
            update={"data_quality": blocked_quality, "best_measurement": blocked_plan}
        )
    )

    assert [item.debt_id for item in guidance.measurement_debt.items[:2]] == [
        "eligible-laps",
        "trusted-events",
    ]
    assert guidance.measurement_debt.items[0].priority == "data_qualification"
    assert guidance.next_trustworthy_move.move_id == "recover:eligible-laps"


def test_blocked_telemetry_health_outranks_diagnosis_and_setup_work() -> None:
    ordered = ("run-1",)
    health = TelemetryHealthBaselineReport(
        status="blocked",
        session_id="session-1",
        ordered_session_run_ids=ordered,
        session_scope_sha256=telemetry_health_session_scope_sha256(
            "session-1", ordered
        ),
        current_run_id="run-1",
        blocker_reasons=("The immutable cache identity could not be verified.",),
        recovery=(
            TelemetryHealthRecovery(
                action="reimport_original_ibt",
                run_id="run-1",
                instruction="Re-import the original .ibt for this run.",
            ),
        ),
    )
    guidance = build_smart_guidance(
        _authorized_report().model_copy(update={"telemetry_health": health}),
        workflow=_workflow().model_copy(update={"status": "a_recorded"}),
    )
    assert guidance.measurement_debt.status == "blocked"
    assert any(
        item.debt_id == "telemetry-health"
        for item in guidance.measurement_debt.items
    )
    assert guidance.next_trustworthy_move.kind == "recover"
    assert guidance.next_trustworthy_move.authority == "navigation_only"


def test_relevant_health_warning_recovers_before_measurement_but_unrelated_does_not() -> None:
    finding = TelemetryHealthFinding(
        finding_id="health:cfs",
        kind="effective_rate_changed",
        channel="cfs_ride_height_in",
        current_run_id="run-1",
        baseline_run_ids=("run-prior-a", "run-prior-b"),
        source_raw_names=("CFSRrideHeight",),
        observation="The effective recording rate changed from the trusted baseline cohort.",
        recovery=TelemetryHealthRecovery(
            action="record_verification_run",
            run_id="run-1",
            instruction="Record one unchanged-setup verification run.",
        ),
    )
    # Health-model validation is covered independently; this unit isolates the typed
    # planner-to-guidance priority handoff.
    health = TelemetryHealthBaselineReport.model_construct(
        status="warning",
        session_id="session-1",
        ordered_session_run_ids=("run-prior-a", "run-prior-b", "run-1"),
        session_scope_sha256=telemetry_health_session_scope_sha256(
            "session-1", ("run-prior-a", "run-prior-b", "run-1")
        ),
        current_run_id="run-1",
        findings=(finding,),
        blocker_reasons=(),
    )
    affected_plan = InformationPlan(
        kind="blocked",
        title="Restore affected telemetry health",
        instruction="Complete the typed recording-health recovery.",
        rationale="The next measurement depends on the affected channel lineage.",
        blocker_reasons=("Affected telemetry health blocks this measurement.",),
        recovery_priority="affected_channel_health",
    )
    report = _report().model_copy(update={"telemetry_health": health})

    affected_guidance = build_smart_guidance(
        report.model_copy(update={"best_measurement": affected_plan})
    )
    unrelated_guidance = build_smart_guidance(report)

    assert affected_guidance.next_trustworthy_move.kind == "recover"
    assert affected_guidance.next_trustworthy_move.move_id == "recover:telemetry-health"
    assert next(
        item
        for item in affected_guidance.measurement_debt.items
        if item.debt_id == "telemetry-health"
    ).priority == "affected_channel_health"
    assert unrelated_guidance.next_trustworthy_move.kind != "recover"
    assert next(
        item
        for item in unrelated_guidance.measurement_debt.items
        if item.debt_id == "telemetry-health"
    ).priority == "background_health"


@pytest.mark.parametrize(
    ("status", "stage_run_ids", "expected_kind", "expected_stage", "authorized"),
    [
        ("a_recorded", {"A": "run-1"}, "controlled_test", "B", True),
        ("b_recorded", {"A": "run-1", "B": "run-b"}, "controlled_test", "A2", False),
        (
            "a2_recorded",
            {"A": "run-1", "B": "run-b", "A2": "run-a2"},
            "compare",
            "complete",
            False,
        ),
    ],
)
def test_guidance_respects_the_persisted_test_stage_before_setup_authority(
    status: str,
    stage_run_ids: dict[str, str],
    expected_kind: str,
    expected_stage: str,
    authorized: bool,
) -> None:
    workflow = _workflow().model_copy(
        update={
            "status": status,
            "stage_run_ids": stage_run_ids,
            "stage_eligible_lap_numbers": {
                stage: (4, 5, 6) for stage in stage_run_ids
            },
            "execution": None,
            "quality": None,
            "learning_admitted": False,
        }
    )
    guidance = build_smart_guidance(_authorized_report(), workflow=workflow)
    assert guidance.test_preflight is not None
    assert guidance.test_preflight.stage == expected_stage
    assert guidance.next_trustworthy_move.kind == expected_kind
    assert guidance.next_trustworthy_move.workflow_id == workflow.workflow_id
    assert guidance.next_trustworthy_move.workflow_updated_at == workflow.updated_at
    assert (
        guidance.next_trustworthy_move.authority == "setup_authorized"
    ) is authorized
    if status == "b_recorded":
        assert "50.1" not in guidance.next_trustworthy_move.instruction
    if status == "a2_recorded":
        assert guidance.mission_stage == "compare"


def test_scored_workflow_routes_to_the_certified_result() -> None:
    workflow = _workflow()
    guidance = build_smart_guidance(_authorized_report(), workflow=workflow)
    assert guidance.mission_stage == "certified"
    assert guidance.next_trustworthy_move.kind == "decide"
    assert guidance.next_trustworthy_move.authority == "navigation_only"
    assert guidance.next_trustworthy_move.workflow_id == "workflow-1"
    assert guidance.next_trustworthy_move.workflow_updated_at == workflow.updated_at


def test_preflight_broadcasts_the_frozen_stage_protocol_without_verifying_future_work() -> None:
    workflow = _workflow().model_copy(
        update={
            "status": "planned",
            "stage_run_ids": {},
            "stage_eligible_lap_numbers": {},
            "execution": None,
            "quality": None,
        }
    )
    preflight = build_controlled_test_preflight(workflow)
    assert preflight is not None
    assert preflight.stage == "A"
    assert preflight.status == "ready"
    setup_check = next(check for check in preflight.checks if check.check_id == "setup-state")
    assert setup_check.detail == workflow.packet.primary_test.stages[0].setup_instruction
    assert setup_check.state == "required"
    assert all(check.state != "verified" for check in preflight.checks if check.check_id != "prior-stages")


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Which typed mechanism has the strongest evidence?", "mechanism_evidence"),
        ("Which hypotheses should I avoid repeating?", "hypothesis_history"),
        ("Is driver repeatability limiting this setup decision?", "driver_focus"),
        ("Which same-setup anomaly should I inspect first?", "what_anomalies"),
        ("What evidence should I recover first?", "recovery_priority"),
    ],
)
def test_every_context_generated_question_has_a_grounded_intent(
    question: str,
    intent: str,
) -> None:
    result = answer_grounded_query(question, _report())
    assert result.supported is True
    assert result.intent == intent
    assert result.action_authorized is False


def test_natural_language_lap_scope_must_resolve_inside_the_run() -> None:
    result = answer_grounded_query("Where is the loss on lap 999?", _report())
    assert result.supported is False
    assert result.clarification_required is True
    assert result.citations == ()
