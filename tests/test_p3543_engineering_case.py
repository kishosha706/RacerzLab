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
)
from racelab_engine.services.engineering_case_service import (
    build_capability_resolutions,
    build_canonical_engineering_case,
    build_engineering_response_artifacts,
    build_p19_response_admissions,
    build_setup_effect_readiness,
)
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
    )
    assert admissions[0].state == "admitted"
    assert admissions[0].assessments[0].result == "supports_existing_contract"
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

    capability = build_capability_resolutions(readiness, artifacts)
    assert capability
    assert all(item.authority == "measurement_routing_only" for item in capability)
    assert all(item.setup_authorized is False for item in capability)


def test_canonical_case_rejects_foreign_response_and_never_credits_p36_counts() -> None:
    artifacts = _response_artifacts()
    readiness = build_setup_effect_readiness((_hypothesis(),), artifacts)
    capability = build_capability_resolutions(readiness, artifacts)
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
    admissions = build_p19_response_admissions(
        case_id=artifacts[0].case_id,
        case_revision_sha256=_REVISION,
        p19_reasoning_snapshot_sha256="c" * 64,
        causes=(),
        response_artifacts=artifacts,
        driver_demand_state="matched",
        context_state="qualified",
        traffic_blocked=False,
    )
    case = build_canonical_engineering_case(
        identity=identity,
        recording_sha256=_SHA,
        evidence_index_sha256="5" * 64,
        p351_projection=SimpleNamespace(projection_sha256="6" * 64),
        response_artifacts=artifacts,
        p19_admissions=admissions,
        p35=SimpleNamespace(
            performance_opportunity_ids=("opportunity-1",),
            mechanism_separation=(),
            next_discriminator_contract_id=None,
        ),
        p26=SimpleNamespace(component_states=()),
        terminal_decision={"kind": "measurement_mission"},
        effect_readiness=readiness,
        capability_resolutions=capability,
        investigation_id=None,
    )

    assert case.case_id == f"p3543case_{_REVISION[:24]}"
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
