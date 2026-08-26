from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.knowledge.engineering_semantic_registry import (
    compile_engineering_semantic_registry,
    response_relations_for_mechanism,
)
from racelab_engine.models.engineering_case import (
    CanonicalEngineeringCase,
    ControlledResponseMetricDelta,
    ControlledResponseReceipt,
    ControlledStageResponseReceipt,
    EngineeringMission,
    ResponseExpectationContract,
)
from racelab_engine.models.crew_chief import (
    CrewChiefEngineeringResponseArtifact,
    EngineeringEvidenceIndex,
    EngineeringEvidenceIndexEntry,
)
from racelab_engine.services.engineering_case_service import (
    attach_deficits_to_readiness,
    build_capability_resolutions,
    build_canonical_engineering_case,
    build_evidence_deficits,
    build_engineering_response_artifacts,
    build_p19_response_admissions,
    build_setup_effect_readiness,
    engineering_case_id,
    engineering_case_projection_revision_sha256,
)
from racelab_engine.services.p19_response_admission_service import (
    build_p19_response_evaluations_and_admissions,
)
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.services.vehicle_dynamics_service import (
    _dynamic_operational_evidence,
)
from test_dynamic_response import _analyze as analyze_dynamic
from test_dynamic_response import _rows as dynamic_rows
from test_p3542_response_integration import _opportunity


_SHA = "a" * 64
_REVISION = "b" * 64


def _response_artifacts():
    report = analyze_dynamic(dynamic_rows())
    evidence = _dynamic_operational_evidence(
        report,
        _opportunity(phase="center"),
    )
    return build_engineering_response_artifacts(
        workspace_revision=_REVISION,
        run_id="run-response",
        session_id="session-response",
        setup_id="setup-response",
        recording_sha256=_SHA,
        operational_evidence=evidence,
    )


def _hypothesis(**updates):
    values = {
        "effect_id": "front_arb_response",
        "bridge_id": "p351b_" + "1" * 24,
        "p35_mechanism_ids": ("mechanism:center_rotation_deficit",),
        "knowledge_applicability": "applicable",
        "p19_control": None,
        "level": "measurable_hypothesis",
        "missing_evidence": ("Independent exact-context repetition is required.",),
        "experiment_factor_id": None,
        "countereffect_ids": ("protected_exit_response",),
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _expectation(artifact, *, expected_sign: int | None = None):
    metric = artifact.operational_evidence.metrics[0]
    sign = expected_sign or (1 if metric.value > 0 else -1)
    return ResponseExpectationContract.build(
        owning_effect_id="front_arb_response",
        owning_mechanism_ids=("mechanism:center_rotation_deficit",),
        experiment_factor_id="factor:front_arb",
        control_key="front_arb_diameter",
        direction_sign=1,
        relation_id=artifact.relation,
        metric_id=metric.metric_id,
        expected_sign=sign,
        units=metric.units,
        phase=artifact.phase,
        lap_pct_start=artifact.lap_pct_start,
        lap_pct_end=artifact.lap_pct_end,
        speed_min_mps=artifact.speed_min_mps,
        speed_max_mps=artifact.speed_max_mps,
        minimum_independent_repetitions=artifact.operational_evidence.repetition_count,
        minimum_absolute_signal=0.0,
        required_channel_ids=artifact.operational_evidence.source_channels,
        required_context_states=(
            "matched_driver_demand",
            "qualified_context",
            "traffic_clear",
        ),
        allowed_evidence_states=(artifact.evidence_state,),
        protected_outcomes=("driver_workload",),
        car_applicability=("all",),
        build_applicability=("all",),
    )


def test_semantic_registry_is_relationship_only_and_covers_response_vocabulary() -> None:
    registry = compile_engineering_semantic_registry()

    assert registry.authority == "relationship_only"
    assert registry.setup_authorized is False
    assert len(registry.entries) == len({item.relation_id for item in registry.entries})
    assert {
        "brake_to_pressure",
        "brake_to_deceleration",
        "brake_to_yaw",
        "brake_release_to_yaw",
        "throttle_to_acceleration",
        "throttle_to_yaw",
        "steering_wheel_to_yaw",
        "disturbance_to_chassis",
        "stint_migration",
    } == {item.relation_id for item in registry.entries}
    assert response_relations_for_mechanism("mechanism:center_rotation_deficit") == (
        "steering_wheel_to_yaw",
        "stint_migration",
    )
    assert all(item.authority == "relationship_only" for item in registry.entries)


def test_response_artifact_and_p19_adapter_preserve_identity_and_authority() -> None:
    artifacts = _response_artifacts()
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.relation == "steering_wheel_to_yaw"
    assert artifact.artifact_id == artifact.operational_evidence.evidence_id
    assert artifact.independence_unit_ids == tuple(
        f"{_SHA}:lap:{lap}" for lap in artifact.source_lap_numbers
    )
    assert artifact.p19_support_authorized is False
    assert artifact.component_support_authorized is False
    assert artifact.setup_authorized is False

    unresolved = build_p19_response_admissions(
        case_id=artifact.case_id,
        case_revision_sha256=_REVISION,
        p19_reasoning_snapshot_sha256="c" * 64,
        causes=(
            SimpleNamespace(
                cause_id="cause-center",
                mechanism_keys=("corner_rotation",),
                status="possible",
            ),
        ),
        response_artifacts=artifacts,
        driver_demand_state="matched",
        context_state="qualified",
        traffic_blocked=False,
    )
    assert unresolved[0].state == "unresolved"
    assert unresolved[0].assessments[0].result == "unresolved"

    admissions = build_p19_response_admissions(
        case_id=artifact.case_id,
        case_revision_sha256=_REVISION,
        p19_reasoning_snapshot_sha256="c" * 64,
        causes=(
            SimpleNamespace(
                cause_id="cause-center",
                mechanism_keys=("corner_rotation",),
                status="possible",
            ),
        ),
        response_artifacts=artifacts,
        driver_demand_state="matched",
        context_state="qualified",
        traffic_blocked=False,
        expectation_contracts=(_expectation(artifact),),
    )
    assert admissions[0].state == "admitted"
    assert admissions[0].assessments[0].result == "support"
    assert admissions[0].reasoning_rank_modified is False
    assert admissions[0].terminal_action_modified is False
    assert admissions[0].setup_authorized is False

    blocked = build_p19_response_admissions(
        case_id=artifact.case_id,
        case_revision_sha256=_REVISION,
        p19_reasoning_snapshot_sha256="c" * 64,
        causes=(
            SimpleNamespace(
                cause_id="cause-center",
                mechanism_keys=("corner_rotation",),
                status="possible",
            ),
        ),
        response_artifacts=artifacts,
        driver_demand_state="matched",
        context_state="qualified",
        traffic_blocked=True,
    )
    assert blocked[0].state == "blocked"
    assert blocked[0].reasoning_rank_modified is False


def test_response_ready_effect_remains_non_testable_and_capability_linked() -> None:
    artifacts = _response_artifacts()
    readiness = build_setup_effect_readiness((_hypothesis(),), artifacts)

    assert readiness[0].state == "response_evidence_ready"
    assert readiness[0].response_artifact_ids == (artifacts[0].artifact_id,)
    assert readiness[0].authority == "measurement_only"
    assert readiness[0].setup_authorized is False
    assert "Exact legal option" in " ".join(readiness[0].missing_evidence)

    deficits = build_evidence_deficits(readiness, artifacts)
    readiness = attach_deficits_to_readiness(readiness, deficits)
    capability = build_capability_resolutions(deficits, artifacts)
    assert capability
    assert all(item.authority == "measurement_routing_only" for item in capability)
    assert all(item.setup_authorized is False for item in capability)
    assert {item.deficit_code for item in capability} == {
        "EXACT_LEGAL_OPTION_MISSING",
        "P19_AUTHORITY_REQUIRED",
    }


def test_canonical_case_rejects_foreign_response_and_never_credits_p36_counts() -> None:
    artifacts = _response_artifacts()
    readiness = build_setup_effect_readiness((_hypothesis(),), artifacts)
    deficits = build_evidence_deficits(readiness, artifacts)
    readiness = attach_deficits_to_readiness(readiness, deficits)
    capability = build_capability_resolutions(deficits, artifacts)
    identity = SimpleNamespace(
        workspace_revision=_REVISION,
        run_id="run-response",
        session_id="session-response",
        setup_id="setup-response",
        setup_snapshot_sha256="d" * 64,
        objective_id=SimpleNamespace(value="race_long_run"),
        run_sentinel_sha256="e" * 64,
        reasoning_snapshot_sha256="c" * 64,
        p20_state_revision="f" * 64,
        p26_knowledge_graph_sha256="1" * 64,
        p32_projection_sha256="2" * 64,
        p35_assessment_sha256="3" * 64,
        learning_projection_sha256="4" * 64,
    )
    evaluations, admissions = build_p19_response_evaluations_and_admissions(
        case_id=artifacts[0].case_id,
        case_revision_sha256=_REVISION,
        p19_reasoning_snapshot_sha256="c" * 64,
        causes=(),
        response_artifacts=artifacts,
        expectation_contracts=(),
        driver_demand_state="matched",
        context_state="qualified",
        traffic_blocked=False,
    )
    terminal_decision = {"kind": "measurement_mission"}
    mission = EngineeringMission(
        what="Measure before changing the setup",
        where="center · exact scope",
        why_it_matters="Current P19 evidence requires measurement.",
        uncertain="No exact response contract exists.",
        next="Collect the required evidence with the setup unchanged.",
        done_when="Three exact-context laps clear the measurement contract.",
        source_authority="p19_measurement_mirror",
        terminal_move_sha256=canonical_json_sha256(terminal_decision),
    )

    def typed_index(response_artifacts):
        entries = tuple(
            EngineeringEvidenceIndexEntry(
                artifact_id=artifact.artifact_id,
                producer_id=f"p35.response.{artifact.relation}",
                run_id=identity.run_id,
                session_id=identity.session_id,
                setup_id=identity.setup_id,
                workspace_run_id=identity.run_id,
                workspace_session_id=identity.session_id,
                workspace_setup_id=identity.setup_id,
                source_run_id=identity.run_id,
                source_session_id=identity.session_id,
                source_setup_id=identity.setup_id,
                source_setup_sha256=identity.setup_snapshot_sha256,
                source_build_context_sha256="7" * 64,
                source_provenance_available=True,
                lap_numbers=artifact.source_lap_numbers,
                lap_pct_start=artifact.lap_pct_start,
                lap_pct_end=artifact.lap_pct_end,
                phase=artifact.phase,
                objective="race_long_run",
                source_channels=artifact.operational_evidence.source_channels,
                evidence_state=artifact.operational_evidence.evidence_state,
                polarity="neutral",
                blocker_reasons=artifact.blocker_reasons,
                typed_artifact=CrewChiefEngineeringResponseArtifact(
                    case_id=artifact.case_id,
                    case_revision_sha256=artifact.case_revision_sha256,
                    assessment_sha256=identity.p35_assessment_sha256,
                    response=artifact,
                ),
                authority_ceiling="observation_only",
            )
            for artifact in response_artifacts
        )
        return EngineeringEvidenceIndex(
            workspace_revision=identity.workspace_revision,
            entries=entries,
            index_hash=canonical_json_sha256(
                [entry.model_dump(mode="json") for entry in entries]
            ),
        )

    initial_typed_index = typed_index(artifacts)
    typed_projection_revision = engineering_case_projection_revision_sha256(
        identity=identity,
        recording_sha256=_SHA,
        evidence_index=initial_typed_index,
        p351_projection=SimpleNamespace(projection_sha256="6" * 64),
        response_artifacts=artifacts,
        response_expectation_contracts=(),
        response_expectation_evaluations=evaluations,
        p19_admissions=admissions,
        terminal_decision=terminal_decision,
        effect_readiness=readiness,
        evidence_deficits=deficits,
        capability_resolutions=capability,
        investigation_id=None,
        mission=mission,
        driver_intent=None,
        crew_event_head_sha256=None,
        crew_current_subgoal=None,
        crew_critic_state="unavailable",
    )
    typed_rebound_artifacts = build_engineering_response_artifacts(
        workspace_revision=typed_projection_revision,
        run_id="run-response",
        session_id="session-response",
        setup_id="setup-response",
        recording_sha256=_SHA,
        operational_evidence=tuple(
            artifact.operational_evidence for artifact in artifacts
        ),
    )
    typed_rebound_evaluations, typed_rebound_admissions = (
        build_p19_response_evaluations_and_admissions(
            case_id=typed_rebound_artifacts[0].case_id,
            case_revision_sha256=typed_projection_revision,
            p19_reasoning_snapshot_sha256="c" * 64,
            causes=(),
            response_artifacts=typed_rebound_artifacts,
            expectation_contracts=(),
            driver_demand_state="matched",
            context_state="qualified",
            traffic_blocked=False,
        )
    )
    assert engineering_case_projection_revision_sha256(
        identity=identity,
        recording_sha256=_SHA,
        evidence_index=typed_index(typed_rebound_artifacts),
        p351_projection=SimpleNamespace(projection_sha256="6" * 64),
        response_artifacts=typed_rebound_artifacts,
        response_expectation_contracts=(),
        response_expectation_evaluations=typed_rebound_evaluations,
        p19_admissions=typed_rebound_admissions,
        terminal_decision=terminal_decision,
        effect_readiness=readiness,
        evidence_deficits=deficits,
        capability_resolutions=capability,
        investigation_id=None,
        mission=mission,
        driver_intent=None,
        crew_event_head_sha256=None,
        crew_current_subgoal=None,
        crew_critic_state="unavailable",
    ) == typed_projection_revision

    projection_revision = engineering_case_projection_revision_sha256(
        identity=identity,
        recording_sha256=_SHA,
        evidence_index_sha256="5" * 64,
        p351_projection=SimpleNamespace(projection_sha256="6" * 64),
        response_artifacts=artifacts,
        response_expectation_contracts=(),
        response_expectation_evaluations=evaluations,
        p19_admissions=admissions,
        terminal_decision=terminal_decision,
        effect_readiness=readiness,
        evidence_deficits=deficits,
        capability_resolutions=capability,
        investigation_id=None,
        mission=mission,
        driver_intent=None,
        crew_event_head_sha256=None,
        crew_current_subgoal=None,
        crew_critic_state="unavailable",
    )
    rebound_artifacts = build_engineering_response_artifacts(
        workspace_revision=projection_revision,
        run_id="run-response",
        session_id="session-response",
        setup_id="setup-response",
        recording_sha256=_SHA,
        operational_evidence=tuple(
            artifact.operational_evidence for artifact in artifacts
        ),
    )
    rebound_evaluations, rebound_admissions = (
        build_p19_response_evaluations_and_admissions(
            case_id=rebound_artifacts[0].case_id,
            case_revision_sha256=projection_revision,
            p19_reasoning_snapshot_sha256="c" * 64,
            causes=(),
            response_artifacts=rebound_artifacts,
            expectation_contracts=(),
            driver_demand_state="matched",
            context_state="qualified",
            traffic_blocked=False,
        )
    )
    assert engineering_case_projection_revision_sha256(
        identity=identity,
        recording_sha256=_SHA,
        evidence_index_sha256="5" * 64,
        p351_projection=SimpleNamespace(projection_sha256="6" * 64),
        response_artifacts=rebound_artifacts,
        response_expectation_contracts=(),
        response_expectation_evaluations=rebound_evaluations,
        p19_admissions=rebound_admissions,
        terminal_decision=terminal_decision,
        effect_readiness=readiness,
        evidence_deficits=deficits,
        capability_resolutions=capability,
        investigation_id=None,
        mission=mission,
        driver_intent=None,
        crew_event_head_sha256=None,
        crew_current_subgoal=None,
        crew_critic_state="unavailable",
    ) == projection_revision
    assert engineering_case_projection_revision_sha256(
        identity=identity,
        recording_sha256=_SHA,
        evidence_index_sha256="7" * 64,
        p351_projection=SimpleNamespace(projection_sha256="6" * 64),
        response_artifacts=rebound_artifacts,
        response_expectation_contracts=(),
        response_expectation_evaluations=rebound_evaluations,
        p19_admissions=rebound_admissions,
        terminal_decision=terminal_decision,
        effect_readiness=readiness,
        evidence_deficits=deficits,
        capability_resolutions=capability,
        investigation_id=None,
        mission=mission,
        driver_intent=None,
        crew_event_head_sha256=None,
        crew_current_subgoal=None,
        crew_critic_state="unavailable",
    ) != projection_revision
    case = build_canonical_engineering_case(
        identity=identity,
        recording_sha256=_SHA,
        evidence_index_sha256="5" * 64,
        p351_projection=SimpleNamespace(projection_sha256="6" * 64),
        response_artifacts=rebound_artifacts,
        response_expectation_contracts=(),
        response_expectation_evaluations=rebound_evaluations,
        p19_admissions=rebound_admissions,
        p35=SimpleNamespace(
            performance_opportunity_ids=("opportunity-1",),
            mechanism_separation=(),
            next_discriminator_contract_id=None,
        ),
        p26=SimpleNamespace(component_states=()),
        terminal_decision=terminal_decision,
        effect_readiness=readiness,
        evidence_deficits=deficits,
        capability_resolutions=capability,
        investigation_id=None,
        mission=mission,
        case_revision_sha256=projection_revision,
    )

    assert case.case_id == engineering_case_id(
        run_id="run-response", session_id="session-response"
    )
    assert case.case_revision_sha256 == projection_revision
    assert case.campaign_capture.state == "pending"
    assert case.campaign_capture.historical_count_credited is False
    assert case.campaign_capture.null_count_credited is False
    assert case.campaign_capture.negative_control_count_credited is False
    assert case.campaign_capture.subgroup_count_credited is False

    payload = case.model_dump(mode="json")
    payload["response_artifacts"][0]["case_revision_sha256"] = "9" * 64
    with pytest.raises(ValidationError):
        CanonicalEngineeringCase.model_validate(payload)


def _stage(
    stage: str,
    run_id: str,
    recording: str,
    setup: str,
    artifact: str,
    speed_min: float = 40.0,
    speed_max: float = 50.0,
) -> ControlledStageResponseReceipt:
    return ControlledStageResponseReceipt(
        stage=stage,
        run_id=run_id,
        source_recording_sha256=recording,
        setup_snapshot_sha256=setup,
        response_artifact_ids=(artifact,),
        response_artifact_sha256s=("f" * 64,),
        source_channels=("steering_deg", "yaw_rate"),
        eligible_lap_numbers=(3, 4, 5),
        phase="center",
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        speed_min_mps=speed_min,
        speed_max_mps=speed_max,
    )


def test_controlled_response_receipt_keeps_three_truth_axes_separate() -> None:
    stages = (
        _stage("A", "run-a", "1" * 64, "7" * 64, "p3542.response:" + "1" * 24),
        _stage("B", "run-b", "2" * 64, "8" * 64, "p3542.response:" + "2" * 24),
        _stage("A2", "run-a2", "3" * 64, "7" * 64, "p3542.response:" + "3" * 24),
    )
    metric = ControlledResponseMetricDelta(
        metric_id="p3543metric_" + "4" * 24,
        relation="steering_wheel_to_yaw",
        label="response lag",
        units="s",
        stage_a_value=0.10,
        stage_b_value=0.08,
        stage_a2_value=0.11,
        baseline_repeat_delta=0.01,
        observed_b_delta=-0.025,
        source_artifact_ids=tuple(
            item.response_artifact_ids[0] for item in stages
        ),
    )
    receipt = ControlledResponseReceipt.build(
        workflow_id="workflow-response",
        control_key="cross_weight_percent",
        setup_effect_id="add_cross_weight",
        experiment_factor_id="factor_cross_weight",
        direction_sign=1,
        stages=stages,
        expected_response_relation_ids=("steering_wheel_to_yaw",),
        expected_response_contract_ids=("p3544expect_" + "5" * 24,),
        observed_metric_deltas=(metric,),
        performance_effect_s=-0.03,
        time_origin_phase="center",
        time_origin_pct=25.0,
        downstream_carry_effect_s=0.01,
        countereffects=("Exit correction workload increased.",),
        mechanism_assessment="inconclusive",
        control_response_assessment="matched",
        policy_verdict="undo",
        state="ready",
    )

    assert receipt.mechanism_assessment == "inconclusive"
    assert receipt.control_response_assessment == "matched"
    assert receipt.policy_verdict == "undo"
    assert receipt.setup_authorized is False

    duplicate = receipt.model_dump(mode="json")
    duplicate["stages"][2]["source_recording_sha256"] = duplicate["stages"][0][
        "source_recording_sha256"
    ]
    with pytest.raises(ValidationError, match="distinct recordings"):
        ControlledResponseReceipt.model_validate(duplicate)

    foreign_speed = receipt.model_dump(mode="json")
    foreign_speed["stages"][1]["speed_min_mps"] = 60.0
    foreign_speed["stages"][1]["speed_max_mps"] = 70.0
    with pytest.raises(ValidationError, match="speed bands"):
        ControlledResponseReceipt.model_validate(foreign_speed)
