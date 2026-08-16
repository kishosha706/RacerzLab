from __future__ import annotations

from types import SimpleNamespace

import pytest

from racelab_engine.knowledge.setup import (
    compile_engineering_knowledge_coverage,
    compile_mechanism_setup_bridges,
    load_setup_knowledge,
)
from racelab_engine.knowledge.setup.dial_in_controls import _PLANS
from racelab_engine.knowledge.setup.dial_in_service import _filter_swings
from racelab_engine.knowledge.setup.dial_in_schema import (
    Clarification,
    DialInHypothesisResponse,
    DialInResponse,
)
from racelab_engine.knowledge.setup.matcher import RankedSetupEffect
from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
    compile_next_gen_oval_runtime_trust_manifest,
)
from racelab_engine.models.crew_chief import CrewChiefTerminalDecision
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.services.engineering_knowledge_service import (
    _resolve_p19_bridge,
    build_canonical_performance_opportunity_binding,
    build_current_engineering_knowledge,
)
from test_performance_truth_closure import _build_public_projection
from test_vehicle_dynamics_service import (
    _assessment,
    _exact_response_projection,
    _p20_for_scope,
)


def _current_inputs(monkeypatch, tmp_path, *, future_build: bool = False):
    p32 = _build_public_projection(monkeypatch, tmp_path, effect_s=0.10, traffic=False)
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)
    if future_build:
        p35 = _assessment(
            p32,
            p20,
            p26=SimpleNamespace(
                graph_version="p26.graph.v1",
                knowledge_graph_sha256=p32.p26_knowledge_graph_sha256,
                reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
                runtime_identity={
                    "car_path": "stockcars chevycamarozl12022",
                    "car_version": "2026.06.08.02",
                    "iracing_build_version": "2026.99.99.99",
                    "track_configuration_name": "oval",
                },
                unavailable_reason=None,
            ),
        )
    else:
        p35 = _assessment(p32, p20)
    component_ids = tuple(
        dict.fromkeys(
            component
            for candidate in p35.candidates
            for component in candidate.component_family_ids
        )
    )
    p26 = SimpleNamespace(
        run_id=p32.run_id,
        session_id=p32.session_id,
        reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
        knowledge_graph_sha256=p32.p26_knowledge_graph_sha256,
        component_states=tuple(
            SimpleNamespace(
                component_id=component_id,
                relevance="candidate",
                observability_states=("measured",),
                current_response_state="observed_correlation",
            )
            for component_id in component_ids
        ),
        experiment_factors=(
            SimpleNamespace(
                factor_id="factor:crossweight",
                primary_controls=("cross_weight_percent",),
                coordinated_controls=(),
            ),
        ),
    )
    p33 = SimpleNamespace(
        run_id=p32.run_id,
        session_id=p32.session_id,
        p19_reasoning_snapshot_sha256=p32.p19_reasoning_snapshot_sha256,
        p32_projection_sha256=p32.projection_sha256,
        projection_sha256="3" * 64,
        car_response_history=(),
        blocker_reasons=("No exact controlled history is available.",),
    )
    return p20, p26, p32, p35, p33


def test_every_reviewed_effect_has_one_typed_bridge_and_legacy_is_removed() -> None:
    knowledge = load_setup_knowledge()
    bridges = compile_mechanism_setup_bridges()
    coverage = compile_engineering_knowledge_coverage()

    assert len(knowledge.setup_effects) == len(bridges) == 92
    assert coverage.catalog_effect_count == coverage.bridge_count == 92
    assert coverage.unmapped_effect_ids == ()
    assert coverage.duplicate_effect_ids == ()
    assert coverage.unsupported_remove_count == 6
    assert coverage.testable_effect_count == len(_PLANS) == 22
    assert coverage.current_action_ready_count == 0
    assert coverage.identity_coverage_count == 92
    assert coverage.semantic_precision_count == 92
    assert coverage.experiment_coverage_count == 22
    assert {item.effect_id for item in bridges} == {
        item.effect_id for item in knowledge.setup_effects
    }
    legacy = tuple(
        item for item in bridges if item.catalog_classification == "unsupported_remove"
    )
    assert {item.setup_area for item in legacy} == {
        "track_bar",
        "truck_arm_mount",
        "bump_stop",
        "packer",
    }
    assert all(item.disabled_car_families == ("next_gen",) for item in legacy)
    assert all(not item.p35_mechanism_ids for item in legacy)


def test_bridge_relations_are_frozen_graph_relations_not_free_text() -> None:
    trust = {
        item.mechanism_id: item
        for item in compile_next_gen_oval_runtime_trust_manifest().mechanisms
    }
    for bridge in compile_mechanism_setup_bridges():
        if bridge.catalog_classification == "unsupported_remove":
            continue
        assert bridge.p35_mechanism_ids
        assert set(bridge.p20_mechanism_ids) == {
            value
            for mechanism_id in bridge.p35_mechanism_ids
            for value in trust[mechanism_id].p20_mechanism_ids
        }
        assert set(bridge.p26_component_family_ids) == {
            value
            for mechanism_id in bridge.p35_mechanism_ids
            for value in trust[mechanism_id].component_family_ids
        }
        assert set(bridge.discriminator_contract_ids) == {
            value
            for mechanism_id in bridge.p35_mechanism_ids
            for value in trust[mechanism_id].discriminator_observation_contract_ids
        }
        assert bridge.authority == "knowledge_only"
        assert bridge.setup_authorized is False
        assert bridge.exact_action_exposed is False


def test_unmapped_action_effects_remain_measurable_knowledge() -> None:
    bridges = {item.effect_id: item for item in compile_mechanism_setup_bridges()}
    for effect_id in (
        "soften_front_arb_arm",
        "add_hs_compression",
        "camber_for_center_grip",
        "reduce_front_toe_scrub",
    ):
        assert effect_id not in _PLANS
        assert bridges[effect_id].catalog_classification == "measurable_hypothesis"
        assert bridges[effect_id].p35_mechanism_ids
        assert bridges[effect_id].related_control_keys == ()


def test_missing_control_plan_does_not_remove_otherwise_valid_knowledge() -> None:
    effect = next(
        item
        for item in load_setup_knowledge().setup_effects
        if item.effect_id == "soften_front_arb_arm"
    )
    candidate = RankedSetupEffect(
        effect=effect,
        score=1.0,
        evidence_matched=["yaw"],
        observed_evidence_matched=["yaw"],
        missing_evidence=[],
        readiness="ready",
        ranking_reasons=["Current yaw evidence keeps this knowledge visible."],
        evidence_missing=[],
        one_change_test_plan="Measure the mechanism before any P19 action.",
    )

    assert effect.effect_id not in _PLANS
    assert _filter_swings([candidate], 3) == [candidate]


def test_transient_damper_and_steady_state_roll_knowledge_stay_distinct() -> None:
    bridges = {item.effect_id: item for item in compile_mechanism_setup_bridges()}

    assert bridges["add_hs_compression"].response_regimes == ("transient",)
    assert "steady_state" in bridges["soften_front_arb_arm"].response_regimes
    assert bridges["add_hs_compression"].p35_mechanism_ids == (
        "mechanism:disturbance_compliance_issue",
    )
    assert "mechanism:front_roll_support_limitation" in (
        bridges["soften_front_arb_arm"].p35_mechanism_ids
    )


def test_current_projection_is_mechanism_first_and_complaint_cannot_reorder(
    monkeypatch, tmp_path
) -> None:
    p20, p26, p32, p35, p33 = _current_inputs(monkeypatch, tmp_path)
    no_call = CrewChiefTerminalDecision(
        kind="no_call",
        title="No setup call",
        instruction="Keep measuring the current mechanism.",
        authority="measurement_only",
    )


    tight = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior="tight center",
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=no_call,
    )
    loose = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior="loose center",
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=no_call,
    )

    assert len(tight.hypotheses) == 92
    assert tight.leading_hypothesis_ids == loose.leading_hypothesis_ids
    assert tight.p32_opportunity_id == p35.performance_opportunity_ids[0]
    assert all(not item.setup_authorized for item in tight.hypotheses)
    assert any(item.effect_id == "soften_front_arb_arm" for item in tight.hypotheses)
    assert all(
        item.p32_opportunity_id == tight.p32_opportunity_id
        for item in tight.hypotheses
        if item.relevance in {"supported_candidate", "blocked_candidate"}
    )


def test_workflow_must_bind_the_exact_canonical_p32_opportunity(
    monkeypatch, tmp_path
) -> None:
    p20, p26, p32, p35, p33 = _current_inputs(monkeypatch, tmp_path)
    knowledge = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior="tight center",
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=CrewChiefTerminalDecision(
            kind="no_call",
            title="No setup call",
            instruction="Keep measuring the current mechanism.",
            authority="measurement_only",
        ),
    )
    opportunity = next(
        item
        for item in p32.opportunity_map.opportunities
        if item.opportunity_id == knowledge.p32_opportunity_id
    )
    workflow_opportunity = SimpleNamespace(
        start_pct=opportunity.start_pct,
        end_pct=opportunity.end_pct,
        phase=opportunity.phase,
        observed_time_loss_s=opportunity.local_delta_s,
        source_channels=opportunity.source_channels,
    )

    binding = build_canonical_performance_opportunity_binding(
        p32=p32,
        knowledge=knowledge,
        workflow_opportunity=workflow_opportunity,
    )

    assert binding.p32_opportunity_id == knowledge.p32_opportunity_id
    assert binding.p32_projection_sha256 == p32.projection_sha256
    assert binding.engineering_knowledge_projection_sha256 == (
        knowledge.projection_sha256
    )
    assert binding.schema_version == "p352.workflow-performance-opportunity.v1"
    assert binding.circular_scope is False
    assert binding.independence_unit == "one_contiguous_physical_window"
    assert tuple(
        (item.start_pct, item.end_pct) for item in binding.segments
    ) == ((opportunity.start_pct, opportunity.end_pct),)
    assert binding.setup_authorized is False

    hostile = binding.model_dump(mode="json")
    hostile["segments"] = [
        {"start_pct": 0.0, "end_pct": 2.0},
        {"start_pct": 98.0, "end_pct": 100.0},
    ]
    hostile["circular_scope"] = True
    with pytest.raises(ValueError, match="fails closed"):
        type(binding).model_validate(hostile)

    drifted = SimpleNamespace(
        **{**workflow_opportunity.__dict__, "start_pct": opportunity.start_pct + 0.1}
    )
    with pytest.raises(ValueError, match="parallel performance reality"):
        build_canonical_performance_opportunity_binding(
            p32=p32,
            knowledge=knowledge,
            workflow_opportunity=drifted,
        )


def test_session_bound_dial_in_promotes_canonical_candidates_over_complaint(
    monkeypatch, tmp_path
) -> None:
    p20, p26, p32, p35, p33 = _current_inputs(monkeypatch, tmp_path)
    decision = CrewChiefTerminalDecision(
        kind="no_call",
        title="No setup call",
        instruction="Keep measuring the current mechanism.",
        authority="measurement_only",
    )
    knowledge = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior="gearing",
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=decision,
    )
    internal = DialInResponse(
        run_id=p32.run_id,
        complaint_raw="gearing is costing time",
        confidence_label="Unsupported",
        readiness_label="Needs telemetry evidence",
        driver_message="Complaint prior only.",
        clarification=Clarification(needed=False),
    )
    public = DialInHypothesisResponse.from_internal(
        internal,
        engineering_knowledge=knowledge,
        p19_terminal_decision=decision,
        limit=18,
    )

    assert public.engineering_knowledge == knowledge
    assert public.p19_terminal_decision == decision
    assert public.top_swings
    assert public.top_swings[0].id == knowledge.leading_hypothesis_ids[0]
    assert public.top_swings[0].p32_opportunity_id == knowledge.p32_opportunity_id
    assert public.top_swings[0].current_relevance in {
        "supported_candidate",
        "blocked_candidate",
    }
    assert all(
        item.setup_area != "final_drive"
        or item.current_relevance == "knowledge_only"
        for item in public.top_swings
    )


def test_complaint_cannot_promote_gearing_without_a_current_p35_candidate(
    monkeypatch, tmp_path
) -> None:
    p20, p26, p32, p35, p33 = _current_inputs(monkeypatch, tmp_path)
    projection = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior="gearing is costing exit speed",
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=CrewChiefTerminalDecision(
            kind="no_call",
            title="No gearing call",
            instruction="Keep the current gearing and measure the actual origin.",
            authority="measurement_only",
        ),
    )

    gearing = tuple(
        item for item in projection.hypotheses if item.setup_area == "final_drive"
    )
    assert gearing
    assert all(item.relevance == "knowledge_only" for item in gearing)
    assert all(item.level == "educational_knowledge" for item in gearing)
    assert all(not item.setup_authorized for item in gearing)


def test_only_one_exact_p19_action_can_promote_a_hypothesis(monkeypatch, tmp_path) -> None:
    p20, p26, p32, p35, p33 = _current_inputs(monkeypatch, tmp_path)
    decision = CrewChiefTerminalDecision(
        kind="controlled_test",
        title="P19 controlled test",
        instruction="Use the exact P19 target.",
        authority="p19_projection_only",
        setup_effect_id="add_crossweight_small",
        experiment_factor_id="factor:crossweight",
        direction_sign=1,
        control_key="cross_weight_percent",
        current_value="50.0%",
        proposed_value="50.2%",
        source_event_ids=("event-1",),
        workflow_id="workflow-1",
        workflow_revision="revision-1",
    )
    projection = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior="tight center",
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=decision,
    )

    promoted = tuple(
        item for item in projection.hypotheses if item.level == "p19_testable_control"
    )
    assert len(promoted) == 1
    assert promoted[0].p19_control is not None
    assert promoted[0].p19_control.model_dump(mode="json") == {
        "effect_id": decision.setup_effect_id,
        "control_key": decision.control_key,
        "direction_sign": decision.direction_sign,
        "experiment_factor_id": decision.experiment_factor_id,
        "current_value": decision.current_value,
        "proposed_value": decision.proposed_value,
        "workflow_id": decision.workflow_id,
        "workflow_revision": decision.workflow_revision,
        "source_event_ids": list(decision.source_event_ids),
        "authority": "exact_p19_projection",
    }
    assert all(
        item.p19_control is None and not item.setup_authorized
        for item in projection.hypotheses
        if item is not promoted[0]
    )


@pytest.mark.parametrize(
    ("effect_id", "control_key", "direction_sign", "factor_id"),
    (
        ("add_crossweight_small", "cross_weight_percent", 1, "factor:crossweight"),
        ("reduce_crossweight_small", "cross_weight_percent", -1, "factor:crossweight"),
        (
            "add_front_brake_bias_small",
            "front_brake_bias_percent",
            1,
            "factor:front_brake_distribution",
        ),
        (
            "reduce_front_brake_bias_small",
            "front_brake_bias_percent",
            -1,
            "factor:front_brake_distribution",
        ),
        ("shorter_final_drive", "rear_end_ratio", 1, "factor:final_drive_ratio"),
        ("taller_final_drive", "rear_end_ratio", -1, "factor:final_drive_ratio"),
        (
            "add_rf_spring_small",
            "rf_front_spring_n_per_mm",
            1,
            "factor:rf_spring_rate",
        ),
        (
            "reduce_rf_spring_small",
            "rf_front_spring_n_per_mm",
            -1,
            "factor:rf_spring_rate",
        ),
        (
            "reduce_front_platform_support",
            "lf_ride_height_mm",
            1,
            "factor:front_platform_height",
        ),
        (
            "add_front_platform_support",
            "lf_ride_height_mm",
            -1,
            "factor:front_platform_height",
        ),
    ),
)
def test_directional_p19_bridge_identity_is_exact_and_order_independent(
    effect_id: str,
    control_key: str,
    direction_sign: int,
    factor_id: str,
) -> None:
    bridges = compile_mechanism_setup_bridges()
    expected = next(item for item in bridges if item.effect_id == effect_id)
    p26 = SimpleNamespace(
        experiment_factors=(
            SimpleNamespace(
                factor_id=factor_id,
                primary_controls=(control_key,),
                coordinated_controls=expected.related_control_keys,
            ),
        )
    )
    decision = SimpleNamespace(
        setup_effect_id=effect_id,
        control_key=control_key,
        direction_sign=direction_sign,
        experiment_factor_id=factor_id,
    )
    active = set(expected.p35_mechanism_ids)

    forward = _resolve_p19_bridge(
        bridges=bridges,
        p26=p26,
        active_mechanism_ids=active,
        decision=decision,
    )
    reversed_order = _resolve_p19_bridge(
        bridges=tuple(reversed(bridges)),
        p26=p26,
        active_mechanism_ids=active,
        decision=decision,
    )

    assert forward.bridge_id == reversed_order.bridge_id == expected.bridge_id
    assert forward.direction_sign == direction_sign
    assert forward.experiment_factor_id == factor_id


def test_directional_p19_bridge_resolution_fails_closed_on_zero_or_many() -> None:
    bridges = compile_mechanism_setup_bridges()
    expected = next(item for item in bridges if item.effect_id == "add_crossweight_small")
    p26 = SimpleNamespace(
        experiment_factors=(
            SimpleNamespace(
                factor_id="factor:crossweight",
                primary_controls=("cross_weight_percent",),
                coordinated_controls=(),
            ),
        )
    )
    decision = SimpleNamespace(
        setup_effect_id="add_crossweight_small",
        control_key="cross_weight_percent",
        direction_sign=1,
        experiment_factor_id="factor:crossweight",
    )
    active = set(expected.p35_mechanism_ids)

    with pytest.raises(ValueError, match="does not resolve to one"):
        _resolve_p19_bridge(
            bridges=bridges,
            p26=p26,
            active_mechanism_ids=set(),
            decision=decision,
        )
    with pytest.raises(ValueError, match="does not resolve to one"):
        _resolve_p19_bridge(
            bridges=(*bridges, expected),
            p26=p26,
            active_mechanism_ids=active,
            decision=decision,
        )


def test_p26_component_presence_never_masquerades_as_current_relevance(
    monkeypatch, tmp_path
) -> None:
    p20, p26, p32, p35, p33 = _current_inputs(monkeypatch, tmp_path)
    relevances = {
        "tires": "candidate",
        "alignment": "supported",
        "springs": "tested",
        "anti_roll_bars": "contradicted",
        "platform": "blocked",
        "weight_distribution": "candidate",
        "differential": "irrelevant",
        "steering": "candidate",
    }
    p26.component_states = tuple(
        SimpleNamespace(
            component_id=component_id,
            relevance=relevance,
            observability_states=(
                ("unavailable",)
                if component_id == "weight_distribution"
                else ("measured",)
            ),
            current_response_state=(
                "unavailable"
                if component_id == "weight_distribution"
                else "observed_correlation"
            ),
        )
        for component_id, relevance in relevances.items()
    )
    projection = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior=None,
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=CrewChiefTerminalDecision(
            kind="no_call",
            title="No setup call",
            instruction="Preserve component relevance truth.",
            authority="measurement_only",
        ),
    )
    item = next(
        hypothesis
        for hypothesis in projection.hypotheses
        if hypothesis.effect_id == "add_crossweight_small"
    )

    assert item.possible_component_family_ids == tuple(relevances)
    assert item.current_candidate_component_ids == ("tires", "steering")
    assert item.current_supported_component_ids == ("alignment", "springs")
    assert item.p26_component_family_ids == (
        "tires",
        "steering",
        "alignment",
        "springs",
    )
    assert item.contradicted_component_ids == ("anti_roll_bars",)
    assert item.blocked_component_ids == ("platform",)
    assert item.unobservable_component_ids == ("weight_distribution",)
    assert item.irrelevant_component_ids == ("differential",)


def test_unreviewed_build_keeps_generic_knowledge_but_no_current_relevance(
    monkeypatch, tmp_path
) -> None:
    p20, p26, p32, p35, p33 = _current_inputs(
        monkeypatch, tmp_path, future_build=True
    )
    projection = build_current_engineering_knowledge(
        run_id=p32.run_id,
        session_id=p32.session_id,
        complaint_prior="tight center",
        p20=p20,
        p26=p26,
        p32=p32,
        p35=p35,
        p33=p33,
        p19_terminal_decision=CrewChiefTerminalDecision(
            kind="no_call",
            title="No setup call",
            instruction="Build review is unavailable.",
            authority="measurement_only",
        ),
    )

    assert p35.applicability_state == "unreviewed_build"
    assert not projection.leading_hypothesis_ids
    assert all(
        item.level in {"educational_knowledge", "unsupported_remove"}
        for item in projection.hypotheses
    )
    assert all(not item.setup_authorized for item in projection.hypotheses)
