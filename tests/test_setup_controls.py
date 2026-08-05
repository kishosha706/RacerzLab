from __future__ import annotations

from types import SimpleNamespace

from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    assess_setup_change,
    expected_control_effect,
    format_setup_value,
    nominal_test_target,
    recommended_test_size_label,
    setup_control_values_equal,
)
from racelab_engine.knowledge.setup.dial_in_controls import _PLANS, garage_action_for_effect
from racelab_engine.services.controlled_workflow_service import _cause_candidate_from_swing


def test_registry_covers_exact_driver_adjustable_control_contract() -> None:
    assert set(SETUP_CONTROL_SPECS) == {
        "lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm",
        "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm",
        "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm",
        "nose_weight_percent", "cross_weight_percent", "tape_percent", "rear_end_ratio",
        "front_brake_bias_percent", "steering_ratio", "steering_offset_deg",
    }


def test_driver_facing_units_do_not_mix_internal_metric_and_garage_units() -> None:
    assert format_setup_value("lf_ride_height_mm", 25.4) == "1.000 in"
    assert format_setup_value("rf_front_spring_n_per_mm", 100.0) == "571 lb/in"
    assert format_setup_value("cross_weight_percent", 50.2) == "50.2%"
    assert format_setup_value("rear_end_ratio", 3.45) == "3.450:1"
    assert format_setup_value("steering_ratio", "10:1") == "10:1"
    assert format_setup_value("steering_ratio", "60 mm/rev") == "60 mm/rev"


def test_garage_value_equality_preserves_string_and_ratio_semantics() -> None:
    assert setup_control_values_equal("tape_percent", "0%", 0.0)
    assert setup_control_values_equal("steering_ratio", "12:1", 12.0)
    assert setup_control_values_equal("steering_ratio", "60 mm/rev", "60 MM/REV")
    assert not setup_control_values_equal("steering_ratio", "12:1", "12 mm/rev")


def test_input_size_is_separate_for_absolute_and_relative_controls() -> None:
    assert assess_setup_change("lf_ride_height_mm", 50.0, 51.0).label == "small"
    assert assess_setup_change("lf_ride_height_mm", 50.0, 54.0).label == "large"
    assert assess_setup_change("rf_front_spring_n_per_mm", 100.0, 105.0).label == "small"
    assert assess_setup_change("rf_front_spring_n_per_mm", 100.0, 120.0).label == "large"


def test_nominal_target_is_exact_only_when_control_has_a_safe_numeric_increment() -> None:
    target, transition = nominal_test_target("cross_weight_percent", 50.0, 1)
    assert target == "50.5%"
    assert transition == "50.0% -> 50.5% (+0.5 percentage points)"

    spring_target, spring_transition = nominal_test_target("rf_front_spring_n_per_mm", 175.0, 1)
    assert spring_target is None
    assert spring_transition.endswith("next available garage setting")


def test_every_control_explains_size_direction_and_guardrail() -> None:
    for key, spec in SETUP_CONTROL_SPECS.items():
        assert spec.magnitude_policy
        assert expected_control_effect(key, 1) == spec.increase_effect
        assert expected_control_effect(key, -1) == spec.decrease_effect
        assert spec.guardrail
        assert spec.influence_label
        assert recommended_test_size_label(key)
        assert spec.increase_effect.startswith("Increasing")
        assert spec.decrease_effect.startswith("Decreasing")
        assert spec.increase_effect.endswith(".")
        assert spec.decrease_effect.endswith(".")
        assert spec.guardrail.endswith(".")


def test_controls_are_grouped_by_the_system_the_driver_actually_changes() -> None:
    assert SETUP_CONTROL_SPECS["front_brake_bias_percent"].group == "brakes"
    assert SETUP_CONTROL_SPECS["steering_ratio"].group == "driver_controls"
    assert SETUP_CONTROL_SPECS["steering_offset_deg"].group == "driver_controls"


def _effect_item(effect_id: str) -> SimpleNamespace:
    return SimpleNamespace(effect=SimpleNamespace(effect_id=effect_id))


def test_coordinated_ride_height_actions_do_not_reuse_single_corner_wording() -> None:
    front_lower = garage_action_for_effect(_effect_item("add_front_platform_support"), {})
    rear_raise = garage_action_for_effect(_effect_item("add_rear_platform_support"), {})
    all_raise = garage_action_for_effect(_effect_item("reduce_platform_contact_small"), {})

    assert front_lower is not None
    assert front_lower.control_expectation.startswith("Lowering LF and RF by equal amounts")
    assert "changed alone" not in front_lower.control_expectation
    assert "Keep the LF-to-RF height difference unchanged" in front_lower.control_guardrail

    assert rear_raise is not None
    assert rear_raise.control_expectation.startswith("Raising LR and RR by equal amounts")
    assert "Keep the LR-to-RR height difference unchanged" in rear_raise.control_guardrail

    assert all_raise is not None
    assert all_raise.control_expectation.startswith("Raising all four ride heights by equal amounts")
    assert "preserving the recorded front-to-rear rake and side-to-side height differences" in all_raise.control_expectation


def test_every_action_plan_preserves_its_typed_direction_into_workflow_candidates() -> None:
    for effect_id, plan in _PLANS.items():
        action = garage_action_for_effect(_effect_item(effect_id), {})
        assert action is not None
        assert action.direction_sign == plan.direction_sign, effect_id

        swing = SimpleNamespace(
            control_keys=action.control_keys,
            direction_sign=action.direction_sign,
            setup_area="test",
            effect="Expected effect.",
            counter_effect="Expected trade-off.",
            validate_with_labels=["Target phase time"],
            validate_with=[],
            blocker_reasons=[],
        )
        candidate = _cause_candidate_from_swing(swing, 0, {})
        if len(action.control_keys) != 1:
            assert candidate is None
            continue
        assert candidate is not None
        assert candidate.direction_sign == plan.direction_sign, effect_id

    assert _PLANS["reduce_rf_spring_small"].direction_sign == -1
    assert _PLANS["reduce_lr_spring_for_drive"].direction_sign == -1


def test_handling_claims_include_their_required_scope_or_caveat() -> None:
    cross = SETUP_CONTROL_SPECS["cross_weight_percent"]
    tape = SETUP_CONTROL_SPECS["tape_percent"]
    steering_offset = SETUP_CONTROL_SPECS["steering_offset_deg"]

    assert "On a left-turn oval" in cross.increase_effect
    assert "depends on the car" in tape.increase_effect
    assert "confirmed from the run data" in tape.increase_effect
    assert "does not change chassis handling" in steering_offset.increase_effect


def test_control_wording_avoids_internal_or_unfriendly_jargon() -> None:
    forbidden = ["legal-step", "package-level", "driver fit", "braking-understeer"]
    for spec in SETUP_CONTROL_SPECS.values():
        visible = " ".join((spec.magnitude_policy, spec.increase_effect, spec.decrease_effect, spec.guardrail)).lower()
        assert all(term not in visible for term in forbidden)

    for effect_id in [
        "add_rf_spring_small",
        "shorter_final_drive",
        "add_front_platform_support",
        "reduce_platform_contact_small",
    ]:
        action = garage_action_for_effect(_effect_item(effect_id), {})
        assert action is not None
        visible = " ".join((action.title, action.change_this, action.change_size_label, action.control_expectation)).lower()
        assert "one legal garage option" not in visible
        assert "minimum legal-step input" not in visible
        assert "static platform" not in visible


def test_steering_ratio_and_pinion_direction_wording_are_not_conflated() -> None:
    assert "slower" in expected_control_effect("steering_ratio", 1, "10:1")
    assert "quicker" in expected_control_effect("steering_ratio", -1, "10:1")
    assert "quicker" in expected_control_effect("steering_ratio", 1, "60 mm/rev")
    assert "slower" in expected_control_effect("steering_ratio", -1, "60 mm/rev")


def test_sensitive_controls_use_control_specific_engineering_bands() -> None:
    assert assess_setup_change("lf_ride_height_mm", 50.0, 51.0).label == "small"
    assert assess_setup_change("lf_ride_height_mm", 50.0, 53.0).label == "large"
    assert assess_setup_change("cross_weight_percent", 50.0, 50.5).label == "small"
    assert assess_setup_change("cross_weight_percent", 50.0, 51.0).label == "medium"
    assert assess_setup_change("front_brake_bias_percent", 55.0, 55.5).label == "small"
    assert assess_setup_change("front_brake_bias_percent", 55.0, 56.5).label == "large"
    assert assess_setup_change("tape_percent", "Race", "Qual").label == "large"
    assert assess_setup_change("rear_end_ratio", 3.50, 3.55).label == "small"


def test_magnitude_basis_is_transparent_product_policy_not_false_precision() -> None:
    basis = assess_setup_change("rf_front_spring_n_per_mm", 100.0, 105.0).basis
    assert basis.startswith("Estimated small input:")
    assert "Policy:" in basis
