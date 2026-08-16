from __future__ import annotations

from types import SimpleNamespace

import pytest

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.engineering_projection import (
    EngineeringAwarenessProjection,
    PrimaryEngineeringState,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.models.performance_intelligence import (
    CornerPerformanceChain,
    DriverVehicleSeparation,
    PerformancePhaseState,
)
from racelab_engine.services.vehicle_dynamics_service import (
    _runtime_support_contract_blockers,
    _leading_opportunity,
    build_unavailable_vehicle_dynamics_assessment,
    build_vehicle_dynamics_assessment,
)
from test_engineering_awareness_projection import _projection as _p20_projection
from test_performance_truth_closure import _build_public_projection


def _p26(
    p32,
    *,
    build: str = "2026.06.24.02",
    track_configuration: str = "oval",
    unavailable: bool = False,
):
    return SimpleNamespace(
        graph_version=("p26.unavailable:v1" if unavailable else "p26.graph.v1"),
        knowledge_graph_sha256=p32.p26_knowledge_graph_sha256,
        reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
        runtime_identity={
            "car_path": "stockcars chevycamarozl12022",
            "car_version": "2026.06.08.02",
            "iracing_build_version": build,
            "track_configuration_name": track_configuration,
        },
        unavailable_reason=("P26 component graph unavailable." if unavailable else None),
    )


def _p20_for_scope(p32, mechanism: MechanismKind) -> EngineeringAwarenessProjection:
    opportunity = p32.opportunity_map.opportunities[0]
    base = _p20_projection(p32.run_id)
    payload = base.model_dump(mode="json")
    payload["session_id"] = p32.session_id
    payload["reasoning_snapshot_id"] = p32.p19_reasoning_snapshot_sha256
    payload["request_identity"]["session_id"] = p32.session_id
    payload["request_identity"]["reasoning_snapshot_id"] = (
        p32.p19_reasoning_snapshot_sha256
    )
    payload["primary_state"] = PrimaryEngineeringState(
        state_id=f"state-{mechanism.value}",
        label="Typed current P20 response observation.",
        mechanism=mechanism,
        lap_number=opportunity.source_laps[0],
        phase=opportunity.phase,
        lap_pct_start=opportunity.start_pct,
        lap_pct_end=opportunity.end_pct,
        lap_pct_peak=(opportunity.start_pct + opportunity.end_pct) / 2.0,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_artifact_ids=(f"observation-{mechanism.value}",),
        source_channels=("SteeringWheelAngle", "YawRate"),
    ).model_dump(mode="json")
    for state in payload["subsystem_states"]:
        if state["mechanism"] != mechanism.value:
            continue
        state.update(
            status="ready",
            summary="Typed current P20 response observation.",
            phase=opportunity.phase,
            lap_number=opportunity.source_laps[0],
            lap_pct_start=opportunity.start_pct,
            lap_pct_end=opportunity.end_pct,
            evidence_state="observed_correlation",
            source_artifact_ids=[f"observation-{mechanism.value}"],
            source_channels=["SteeringWheelAngle", "YawRate"],
            blocker_reasons=[],
        )
    return EngineeringAwarenessProjection.model_validate(payload)


def _p20_with_source_channels(
    p20: EngineeringAwarenessProjection,
    mechanism: MechanismKind,
    source_channels: tuple[str, ...],
) -> EngineeringAwarenessProjection:
    assert p20.primary_state is not None
    primary = p20.primary_state.model_copy(
        update={"source_channels": source_channels}
    )
    states = tuple(
        state.model_copy(update={"source_channels": source_channels})
        if state.mechanism is mechanism and state.status == "ready"
        else state
        for state in p20.subsystem_states
    )
    return p20.model_copy(
        update={"primary_state": primary, "subsystem_states": states}
    )


def _p32_with_phase_source_channels(p32, source_channels: tuple[str, ...]):
    chain = p32.corner_chains[0]
    for field_name in ("braking_state", "entry_state", "center_state", "exit_state", "carry_state"):
        state = getattr(chain, field_name, None)
        if state is None:
            continue
        chain = chain.model_copy(
            update={field_name: state.model_copy(update={"source_channels": source_channels})}
        )
    return p32.model_copy(update={"corner_chains": (chain,)})


def _exact_response_projection(
    p32,
    p20: EngineeringAwarenessProjection,
    *,
    phase: str | None = None,
    mechanism_candidates: tuple[str, ...] | None = None,
    origin_kind: str | None = None,
    matched_driver_demand: bool = True,
    separation_updates: dict[str, object] | None = None,
):
    opportunity = p32.opportunity_map.opportunities[0]
    phase = phase or opportunity.phase
    opportunity = opportunity.model_copy(
        update={
            "phase": phase,
            "origin_kind": origin_kind or opportunity.origin_kind,
            "mechanism_candidates": (
                mechanism_candidates
                if mechanism_candidates is not None
                else opportunity.mechanism_candidates
            ),
        }
    )
    state = PerformancePhaseState(
        phase=phase,
        start_pct=opportunity.start_pct,
        end_pct=opportunity.end_pct,
        elapsed_delta_s=opportunity.local_delta_s,
        speed_delta_mph=-1.0,
        throttle_delta_pct=0.0,
        brake_delta_pct=0.0,
        steering_delta_deg=2.0,
        yaw_rate_delta=-1.0,
        long_accel_delta=0.0,
        evidence_state=EvidenceState.MEASURED,
        source_channels=(
            "Throttle",
            "Brake",
            "SteeringWheelAngle",
            "YawRate",
            "Speed",
            "LatAccel",
        ),
    )
    state_field = {
        "center": "center_state",
        "following_straight": "carry_state",
    }.get(phase, "center_state")
    separation = DriverVehicleSeparation(
        separation_id=f"p32-separation-{phase}",
        phase=phase,
        driver_demand_changed=not matched_driver_demand,
        vehicle_response_changed=True,
        line_changed=False,
        context_changed=False,
        time_changed=True,
        result=(
            "vehicle_response_changed_with_matched_inputs"
            if matched_driver_demand
            else "mixed_change"
        ),
        support=(
            (
                "Complete co-observed driver demand is matched."
                if matched_driver_demand
                else "Driver demand and vehicle response both changed."
            ),
        ),
    )
    if separation_updates:
        separation = separation.model_copy(update=separation_updates)
    chain = CornerPerformanceChain(
        chain_id=f"p32-chain-{phase}",
        track_region=opportunity.track_region,
        turn=opportunity.turn,
        lap_numbers=(opportunity.source_laps[0],),
        reference_lap_numbers=(opportunity.source_laps[1],),
        local_time_effect_s=opportunity.local_delta_s,
        driver_vehicle_separation=(separation,),
        context=("qualified lap pair",),
        contradictions=("No component cause is established.",),
        **{state_field: state},
    )
    opportunity_map = p32.opportunity_map.model_copy(
        update={"opportunities": (opportunity,)}
    )
    return p32.model_copy(
        update={
            "basis": p32.basis.model_copy(update={"context_blockers": ()}),
            "opportunity_map": opportunity_map,
            "corner_chains": (chain,),
            "p20_state_revision": p20.state_revision,
            "projection_sha256": canonical_json_sha256(
                [
                    p32.projection_sha256,
                    phase,
                    mechanism_candidates,
                    origin_kind,
                    matched_driver_demand,
                ]
            ),
        }
    )


def _assessment(p32, p20, *, p26=None):
    return build_vehicle_dynamics_assessment(
        run_id=p32.run_id,
        session_id=p32.session_id,
        objective_id=p32.objective_id,
        p19_reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
        p20=p20,
        p26=p26 or _p26(p32),
        p32=p32,
    )


def test_ready_assessment_requires_exact_p20_and_p32_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-ready.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)

    assessment = _assessment(p32, p20)

    assert assessment.candidates
    assert any(item.relevance == "candidate" for item in assessment.candidates)
    assert assessment.strongest_support_artifact_id is not None
    assert assessment.measured_time_consequence_available
    assert assessment.component_causal_claim_count == 0
    assert assessment.setup_authorized is False
    assert assessment.terminal_authority == "p19_only"
    assert "observation-corner_rotation" in assessment.chain[2].source_artifact_ids
    assert all(
        "disturbance_compliance_issue" not in item.mechanism_id
        and "brake_release_rotation_deficit" not in item.mechanism_id
        for item in assessment.candidates
    )


def test_brake_support_requires_exact_layers_and_all_four_corner_channels(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-brake-contract.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    seed_p20 = _p20_for_scope(p32, MechanismKind.BRAKING_RESPONSE)
    p32 = _exact_response_projection(
        p32,
        seed_p20,
        phase="braking",
        mechanism_candidates=("braking_realization",),
    )
    base_p20 = _p20_for_scope(p32, MechanismKind.BRAKING_RESPONSE)
    p32 = p32.model_copy(update={"p20_state_revision": base_p20.state_revision})
    complete_channels = (
        "Brake",
        "SteeringWheelAngle",
        "LFbrakeLinePress",
        "RFbrakeLinePress",
        "LRbrakeLinePress",
        "RRbrakeLinePress",
        "LFspeed",
        "RFspeed",
        "LRspeed",
        "RRspeed",
        "YawRate",
        "Speed",
        "LatAccel",
    )
    complete_p20 = _p20_with_source_channels(
        base_p20,
        MechanismKind.BRAKING_RESPONSE,
        complete_channels,
    )
    complete_p32 = _p32_with_phase_source_channels(p32, complete_channels)
    complete = _assessment(complete_p32, complete_p20)
    brake_candidate = next(
        item
        for item in complete.candidates
        if item.mechanism_id == "mechanism:brake_entry_instability"
    )
    assert brake_candidate.relevance == "candidate"
    assert brake_candidate.support_artifact_ids

    steering_yaw_channels = (
        "SteeringWheelAngle",
        "YawRate",
        "Speed",
        "LatAccel",
    )
    generic = _assessment(
        _p32_with_phase_source_channels(p32, steering_yaw_channels),
        _p20_with_source_channels(
            base_p20,
            MechanismKind.BRAKING_RESPONSE,
            steering_yaw_channels,
        ),
    )
    generic_brake = next(
        item
        for item in generic.candidates
        if item.mechanism_id == "mechanism:brake_entry_instability"
    )
    assert generic_brake.relevance == "blocked"
    assert not generic_brake.support_artifact_ids
    assert any(
        "support_channel:brake_input" in blocker
        or "support_channel:front_brake_pressure" in blocker
        for blocker in generic_brake.blocker_reasons
    )

    missing_rr = tuple(
        channel for channel in complete_channels if channel != "RRspeed"
    )
    one_corner_missing = _assessment(
        _p32_with_phase_source_channels(p32, missing_rr),
        _p20_with_source_channels(
            base_p20,
            MechanismKind.BRAKING_RESPONSE,
            missing_rr,
        ),
    )
    missing_brake = next(
        item
        for item in one_corner_missing.candidates
        if item.mechanism_id == "mechanism:brake_entry_instability"
    )
    assert missing_brake.relevance == "blocked"
    assert any(
        "support_channel:rear_wheel_response" in blocker
        for blocker in missing_brake.blocker_reasons
    )

    from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
        compile_next_gen_oval_runtime_trust_manifest,
    )

    trust = next(
        item
        for item in compile_next_gen_oval_runtime_trust_manifest().mechanisms
        if item.mechanism_id == "mechanism:brake_entry_instability"
    )
    wrong_layer = list(complete.chain)
    driver_stage = wrong_layer[0]
    response_stage = wrong_layer[2]
    wrong_layer[0] = driver_stage.model_copy(
        update={
            "source_channels": tuple(
                channel
                for channel in driver_stage.source_channels
                if channel != "Brake"
            )
        }
    )
    wrong_layer[2] = response_stage.model_copy(
        update={
            "source_channels": tuple(
                dict.fromkeys((*response_stage.source_channels, "Brake"))
            )
        }
    )
    assert any(
        "support_channel:brake_input" in blocker
        for blocker in _runtime_support_contract_blockers(
            trust,
            tuple(wrong_layer),
            (),
        )
    )

    blocked_primary = complete_p20.primary_state.model_copy(
        update={"evidence_state": EvidenceState.BLOCKED_BY_CONTEXT}
    )
    blocked_states = tuple(
        state.model_copy(
            update={
                "status": "blocked",
                "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                "blocker_reasons": ("Typed P20 brake evidence is blocked.",),
            }
        )
        if state.mechanism is MechanismKind.BRAKING_RESPONSE
        else state
        for state in complete_p20.subsystem_states
    )
    blocked_p20 = complete_p20.model_copy(
        update={
            "primary_state": blocked_primary,
            "subsystem_states": blocked_states,
        }
    )
    blocked = _assessment(complete_p32, blocked_p20)
    blocked_brake = next(
        item
        for item in blocked.candidates
        if item.mechanism_id == "mechanism:brake_entry_instability"
    )
    assert blocked_brake.relevance == "blocked"
    assert not blocked_brake.support_artifact_ids


def test_missing_exact_response_never_becomes_positive_support(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-no-response.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = p32.model_copy(update={"p20_state_revision": p20.state_revision})

    assessment = _assessment(p32, p20)

    assert assessment.candidates
    assert {item.relevance for item in assessment.candidates} == {"blocked"}
    assert assessment.strongest_support_artifact_id is None
    assert not any(item.polarity == "support" for item in assessment.focus_artifacts)
    assert assessment.measured_time_consequence_available


def test_traffic_keeps_measured_time_and_blocks_every_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-traffic.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=True
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = p32.model_copy(update={"p20_state_revision": p20.state_revision})

    assessment = _assessment(p32, p20)

    assert assessment.traffic_blocked
    assert assessment.measured_time_consequence_available
    assert assessment.chain[-1].source_artifact_ids == (
        p32.opportunity_map.opportunities[0].opportunity_id,
    )
    assert assessment.candidates
    assert {item.relevance for item in assessment.candidates} == {"blocked"}
    assert assessment.strongest_support_artifact_id is None
    assert assessment.strongest_contradiction_artifact_id is not None
    assert assessment.next_discriminator_contract_id is not None
    assert assessment.component_causal_claim_count == 0


def test_steady_state_filters_transient_damper_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-steady.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(
        p32,
        p20,
        mechanism_candidates=("center_rotation", "disturbance_compliance"),
    )

    assessment = _assessment(p32, p20)
    mechanism_ids = {item.mechanism_id for item in assessment.candidates}

    assert "mechanism:center_rotation_deficit" in mechanism_ids
    assert "mechanism:disturbance_compliance_issue" not in mechanism_ids


def test_driver_demand_change_blocks_mechanism_support(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-driver-change.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(
        p32,
        p20,
        matched_driver_demand=False,
    )

    assessment = _assessment(p32, p20)

    assert assessment.candidates
    assert {item.relevance for item in assessment.candidates} == {"blocked"}
    assert assessment.strongest_support_artifact_id is None
    assert not any(item.polarity == "support" for item in assessment.focus_artifacts)
    assert assessment.measured_time_consequence_available


@pytest.mark.parametrize(
    "separation_updates",
    (
        {"driver_demand_changed": True},
        {"vehicle_response_changed": False},
        {"line_changed": True},
        {"context_changed": True},
        {"time_changed": False},
    ),
)
def test_matched_input_label_cannot_override_separation_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    separation_updates: dict[str, object],
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-separation.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(
        p32,
        p20,
        separation_updates=separation_updates,
    )

    assessment = _assessment(p32, p20)

    assert assessment.candidates
    assert {item.relevance for item in assessment.candidates} == {"blocked"}
    assert assessment.strongest_support_artifact_id is None
    assert assessment.measured_time_consequence_available


def test_foreign_p20_snapshot_is_rejected_from_atomic_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-p20-snapshot.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)
    foreign = p20.model_copy(
        update={
            "reasoning_snapshot_id": "a" * 64,
            "request_identity": p20.request_identity.model_copy(
                update={"reasoning_snapshot_id": "a" * 64}
            ),
        }
    )

    with pytest.raises(ValueError, match="exact atomic"):
        _assessment(p32, foreign)

    run_scoped = p20.model_copy(
        update={
            "session_id": None,
            "request_identity": p20.request_identity.model_copy(
                update={"session_id": None}
            ),
        }
    )
    with pytest.raises(ValueError, match="exact atomic"):
        _assessment(p32, run_scoped)


def test_reference_lap_p20_observation_cannot_support_source_lap_loss(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-p20-reference.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)
    reference_lap = p32.opportunity_map.opportunities[0].source_laps[1]
    primary = p20.primary_state.model_copy(update={"lap_number": reference_lap})
    states = tuple(
        state.model_copy(update={"lap_number": reference_lap})
        if state.mechanism is MechanismKind.CORNER_ROTATION
        else state
        for state in p20.subsystem_states
    )
    reference_only = p20.model_copy(
        update={"primary_state": primary, "subsystem_states": states}
    )

    assessment = _assessment(p32, reference_only)

    assert assessment.candidates
    assert {item.relevance for item in assessment.candidates} == {"blocked"}
    assert assessment.strongest_support_artifact_id is None
    assert assessment.measured_time_consequence_available


def test_foreign_chain_lap_cohort_cannot_support_current_opportunity(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-chain-laps.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)
    foreign_chain = p32.corner_chains[0].model_copy(
        update={"lap_numbers": (999,), "reference_lap_numbers": (1000,)}
    )
    p32 = p32.model_copy(
        update={
            "corner_chains": (foreign_chain,),
            "projection_sha256": canonical_json_sha256(
                [p32.projection_sha256, "foreign-chain-laps"]
            ),
        }
    )

    assessment = _assessment(p32, p20)

    assert assessment.candidates
    assert {item.relevance for item in assessment.candidates} == {"blocked"}
    assert assessment.strongest_support_artifact_id is None
    assert assessment.measured_time_consequence_available


@pytest.mark.parametrize(
    ("basis_blockers", "source_fraction", "reference_fraction"),
    (
        (("Typed traffic context blocks the comparison.",), 0.0, 0.0),
        ((), 0.25, 0.0),
        ((), None, 0.0),
    ),
)
def test_context_debt_cannot_be_erased_by_qualified_opportunity_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    basis_blockers: tuple[str, ...],
    source_fraction: float | None,
    reference_fraction: float | None,
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-context.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)
    opportunity = p32.opportunity_map.opportunities[0].model_copy(
        update={
            "attribution_state": "candidate_only",
            "context_state": "qualified_pair",
            "source_traffic_exposure_fraction": source_fraction,
            "reference_traffic_exposure_fraction": reference_fraction,
        }
    )
    p32 = p32.model_copy(
        update={
            "basis": p32.basis.model_copy(
                update={"context_blockers": basis_blockers}
            ),
            "opportunity_map": p32.opportunity_map.model_copy(
                update={"opportunities": (opportunity,)}
            ),
            "projection_sha256": canonical_json_sha256(
                [
                    p32.projection_sha256,
                    basis_blockers,
                    source_fraction,
                    reference_fraction,
                ]
            ),
        }
    )

    assessment = _assessment(p32, p20)

    assert assessment.candidates
    assert {item.relevance for item in assessment.candidates} == {"blocked"}
    assert assessment.strongest_support_artifact_id is None
    assert assessment.measured_time_consequence_available

    fallback = build_unavailable_vehicle_dynamics_assessment(
        run_id=p32.run_id,
        session_id=p32.session_id,
        objective_id=p32.objective_id,
        p19_reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
        p20=p20,
        p26=_p26(p32),
        p32=p32,
        blocker_reason="Injected main-path failure.",
    )
    assert fallback.measured_time_consequence_available
    assert fallback.chain[3].evidence_state is EvidenceState.BLOCKED_BY_CONTEXT
    assert fallback.strongest_support_artifact_id is None


def test_carried_exit_time_cannot_be_recast_as_gearing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-carried.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.POWERTRAIN_RESPONSE)
    p32 = _exact_response_projection(
        p32,
        p20,
        phase="following_straight",
        mechanism_candidates=("gearing_headroom",),
        origin_kind="carried_in",
    )

    assessment = _assessment(p32, p20)

    assert all(
        item.mechanism_id != "mechanism:gearing_headroom_limitation"
        for item in assessment.candidates
    )
    assert any("matched" in item.casefold() for item in assessment.blocker_reasons)


def test_p35_survives_p26_unavailable_and_blocks_unreviewed_future_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-build.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)

    p26_missing = _assessment(p32, p20, p26=_p26(p32, unavailable=True))
    future = _assessment(
        p32,
        p20,
        p26=_p26(p32, build="2026.06.25.01", unavailable=True),
    )

    assert p26_missing.applicability_state == "ready"
    assert p26_missing.measured_time_consequence_available
    assert future.applicability_state == "unreviewed_build"
    assert future.candidates == ()
    assert future.measured_time_consequence_available
    assert future.applicability_blockers


def test_non_oval_runtime_cannot_enter_reviewed_oval_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-road.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)

    assessment = _assessment(
        p32,
        p20,
        p26=_p26(
            p32,
            track_configuration="road_course",
            unavailable=True,
        ),
    )

    assert assessment.applicability_state == "unavailable"
    assert assessment.track_package == "unavailable"
    assert assessment.candidates == ()
    assert assessment.measured_time_consequence_available
    assert assessment.applicability_blockers


def test_leading_opportunity_tie_uses_smallest_identity_not_tuple_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-tie.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    original = p32.opportunity_map.opportunities[0]
    larger = original.model_copy(update={"opportunity_id": "p32o-z-tie"})
    smaller = original.model_copy(update={"opportunity_id": "p32o-a-tie"})

    for opportunities in ((larger, smaller), (smaller, larger)):
        projection = p32.model_copy(
            update={
                "opportunity_map": p32.opportunity_map.model_copy(
                    update={"opportunities": opportunities}
                )
            }
        )
        assert _leading_opportunity(projection).opportunity_id == "p32o-a-tie"


def test_zero_delta_remains_measured_but_cannot_support_a_mechanism(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-zero-delta.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)
    opportunity = p32.opportunity_map.opportunities[0].model_copy(
        update={"local_delta_s": 0.0}
    )
    p32 = p32.model_copy(
        update={
            "opportunity_map": p32.opportunity_map.model_copy(
                update={"opportunities": (opportunity,)}
            ),
            "projection_sha256": canonical_json_sha256(
                [p32.projection_sha256, "zero-delta"]
            ),
        }
    )

    assessment = _assessment(p32, p20)

    assert assessment.measured_time_consequence_available
    assert assessment.performance_opportunity_ids == (opportunity.opportunity_id,)
    assert assessment.candidates == ()
    assert assessment.strongest_support_artifact_id is None
    assert any("zero" in item.casefold() for item in assessment.blocker_reasons)


def test_unprovenanced_delta_fails_contained_without_selecting_an_opportunity(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-no-time-scope.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    opportunity = p32.opportunity_map.opportunities[0].model_copy(
        update={"source_laps": (), "source_channels": ()}
    )
    p32 = p32.model_copy(
        update={
            "p20_state_revision": p20.state_revision,
            "opportunity_map": p32.opportunity_map.model_copy(
                update={"opportunities": (opportunity,)}
            ),
            "projection_sha256": canonical_json_sha256(
                [p32.projection_sha256, "unprovenanced-delta"]
            ),
        }
    )

    assessment = _assessment(p32, p20)
    fallback = build_unavailable_vehicle_dynamics_assessment(
        run_id=p32.run_id,
        session_id=p32.session_id,
        objective_id=p32.objective_id,
        p19_reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
        p20=p20,
        p26=_p26(p32),
        p32=p32,
        blocker_reason="Injected main-path failure.",
    )

    for value in (assessment, fallback):
        assert value.performance_opportunity_ids == ()
        assert value.p32_performance_mechanism_ids == ()
        assert not value.measured_time_consequence_available
        assert value.chain[-1].evidence_state is EvidenceState.UNAVAILABLE
        assert value.candidates == ()


def test_unknown_phase_and_missing_runtime_fail_closed_without_losing_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-unknown.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    opportunity = p32.opportunity_map.opportunities[0].model_copy(
        update={"phase": "producer_phase_not_reviewed_by_p35"}
    )
    p32 = p32.model_copy(
        update={
            "p20_state_revision": p20.state_revision,
            "opportunity_map": p32.opportunity_map.model_copy(
                update={"opportunities": (opportunity,)}
            ),
            "projection_sha256": canonical_json_sha256(
                [p32.projection_sha256, "unknown-phase"]
            ),
        }
    )
    missing_runtime = SimpleNamespace(
        graph_version="p26.unavailable:v1",
        knowledge_graph_sha256=p32.p26_knowledge_graph_sha256,
        reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
        runtime_identity={"state": "unavailable"},
        unavailable_reason="Runtime identity unavailable.",
    )

    assessment = _assessment(p32, p20, p26=missing_runtime)

    assert assessment.applicability_state == "unavailable"
    assert assessment.response_regime is None
    assert assessment.candidates == ()
    assert assessment.measured_time_consequence_available
    assert assessment.car_path == "unavailable"
    assert assessment.track_package == "unavailable"
    assert any("phase" in item.casefold() for item in assessment.blocker_reasons)


def test_unavailable_quantity_inventory_uses_the_frozen_graph_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-quantities.sqlite3"))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)

    assessment = _assessment(p32, p20)

    required = {
        "quantity:exact_tire_force",
        "quantity:exact_wheel_load",
        "quantity:exact_aerodynamic_drag_force",
        "quantity:exact_drag_coefficient",
    }
    assert required <= set(assessment.unavailable_quantity_ids)
    assert "One or more" in assessment.chain[1].summary
    assert "One or more" in assessment.chain[2].summary
