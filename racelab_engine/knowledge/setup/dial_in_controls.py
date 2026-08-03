from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    expected_control_effect,
    format_setup_value,
    nominal_test_target,
    recommended_test_size_label,
)


@dataclass(frozen=True)
class GarageAction:
    title: str
    change_this: str
    garage_lever: str
    control_keys: list[str]
    change_size_label: str
    change_size_explanation: str
    influence_label: str
    control_expectation: str
    control_guardrail: str
    current_value_label: str | None = None
    proposed_value_label: str | None = None


@dataclass(frozen=True)
class _ActionPlan:
    control_keys: tuple[str, ...]
    direction_sign: int
    verb: str
    title: str


_PLANS: dict[str, _ActionPlan] = {
    "add_crossweight_small": _ActionPlan(("cross_weight_percent",), 1, "Increase", "Increase Cross Weight"),
    "reduce_crossweight_small": _ActionPlan(("cross_weight_percent",), -1, "Reduce", "Reduce Cross Weight"),
    "add_rf_spring_small": _ActionPlan(("rf_front_spring_n_per_mm",), 1, "Stiffen", "Stiffen the RF Spring"),
    "reduce_rf_spring_small": _ActionPlan(("rf_front_spring_n_per_mm",), -1, "Soften", "Soften the RF Spring"),
    "spring_package_platform_support": _ActionPlan(("rf_front_spring_n_per_mm",), 1, "Stiffen", "Stiffen the RF Spring"),
    "add_lr_spring_support": _ActionPlan(("lr_rear_spring_n_per_mm",), 1, "Stiffen", "Stiffen the LR Spring"),
    "reduce_lr_spring_for_drive": _ActionPlan(("lr_rear_spring_n_per_mm",), -1, "Soften", "Soften the LR Spring"),
    "spring_package_compliance": _ActionPlan(("lr_rear_spring_n_per_mm",), -1, "Soften", "Soften the LR Spring"),
    "add_front_brake_bias_small": _ActionPlan(("front_brake_bias_percent",), 1, "Increase", "Increase Front Brake Bias"),
    "reduce_front_brake_bias_small": _ActionPlan(("front_brake_bias_percent",), -1, "Decrease", "Decrease Front Brake Bias"),
    "shorter_final_drive": _ActionPlan(("rear_end_ratio",), 1, "Increase", "Increase Rear End Ratio"),
    "taller_final_drive": _ActionPlan(("rear_end_ratio",), -1, "Decrease", "Decrease Rear End Ratio"),
    "add_front_platform_support": _ActionPlan(("lf_ride_height_mm", "rf_ride_height_mm"), -1, "Lower", "Lower Front Ride Height"),
    "lower_front_shock_collar_small": _ActionPlan(("lf_ride_height_mm", "rf_ride_height_mm"), -1, "Lower", "Lower Front Ride Height"),
    "reduce_front_platform_support": _ActionPlan(("lf_ride_height_mm", "rf_ride_height_mm"), 1, "Raise", "Raise Front Ride Height"),
    "improve_front_feed_window": _ActionPlan(("lf_ride_height_mm", "rf_ride_height_mm"), 1, "Raise", "Raise Front Ride Height"),
    "raise_front_shock_collar_small": _ActionPlan(("lf_ride_height_mm", "rf_ride_height_mm"), 1, "Raise", "Raise Front Ride Height"),
    "add_rear_platform_support": _ActionPlan(("lr_ride_height_mm", "rr_ride_height_mm"), 1, "Raise", "Raise Rear Ride Height"),
    "raise_rear_shock_collar_small": _ActionPlan(("lr_ride_height_mm", "rr_ride_height_mm"), 1, "Raise", "Raise Rear Ride Height"),
    "reduce_rear_platform_support": _ActionPlan(("lr_ride_height_mm", "rr_ride_height_mm"), -1, "Lower", "Lower Rear Ride Height"),
    "lower_rear_shock_collar_small": _ActionPlan(("lr_ride_height_mm", "rr_ride_height_mm"), -1, "Lower", "Lower Rear Ride Height"),
    "reduce_platform_contact_small": _ActionPlan(
        ("lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"),
        1,
        "Raise",
        "Raise All Four Ride Heights",
    ),
}


def _current_summary(keys: tuple[str, ...], setup_values: dict[str, Any]) -> str | None:
    available = [f"{SETUP_CONTROL_SPECS[key].label} {format_setup_value(key, setup_values[key])}" for key in keys if setup_values.get(key) is not None]
    return "; ".join(available) or None


def _unique_join(values: list[str]) -> str:
    return " ".join(dict.fromkeys(values))


def _coordinated_ride_height_wording(plan: _ActionPlan) -> tuple[str, str]:
    keys = plan.control_keys
    raising = plan.direction_sign > 0
    if keys == ("lf_ride_height_mm", "rf_ride_height_mm"):
        expectation = (
            "Raising LF and RF by equal amounts raises the front of the chassis and adds ground clearance. "
            "It may reduce high-speed front response on cars that are sensitive to ride height."
            if raising
            else "Lowering LF and RF by equal amounts lowers the front of the chassis and reduces ground clearance. "
            "It may improve high-speed front response on cars that are sensitive to ride height, provided the chassis does not contact the track."
        )
        guardrail = "Keep the LF-to-RF height difference unchanged, recheck cross weight, and undo the change if front bottoming or steering corrections increase."
        return expectation, guardrail
    if keys == ("lr_ride_height_mm", "rr_ride_height_mm"):
        expectation = (
            "Raising LR and RR by equal amounts raises the rear of the chassis and adds ground clearance. "
            "It changes front-to-rear rake and may alter high-speed balance on cars that are sensitive to ride height."
            if raising
            else "Lowering LR and RR by equal amounts lowers the rear of the chassis and reduces ground clearance. "
            "It changes front-to-rear rake and may alter high-speed balance on cars that are sensitive to ride height."
        )
        guardrail = "Keep the LR-to-RR height difference unchanged, recheck cross weight, and undo the change if rear bottoming or high-speed instability increases."
        return expectation, guardrail
    expectation = (
        "Raising all four ride heights by equal amounts raises the complete chassis and adds ground clearance while preserving the recorded front-to-rear rake and side-to-side height differences."
        if raising
        else "Lowering all four ride heights by equal amounts lowers the complete chassis and reduces ground clearance while preserving the recorded front-to-rear rake and side-to-side height differences."
    )
    guardrail = "Keep all four changes equal, recheck cross weight, and undo the change if the balance shifts unexpectedly or bottoming increases."
    return expectation, guardrail


def _next_available_transition(key: str, current_value: Any, direction_sign: int) -> str:
    current = format_setup_value(key, current_value) if current_value is not None else "current setting"
    if "spring" in key:
        destination = "next stiffer available rate" if direction_sign > 0 else "next softer available rate"
    elif key == "rear_end_ratio":
        destination = "next numerically higher available ratio" if direction_sign > 0 else "next numerically lower available ratio"
    elif key == "steering_ratio":
        if isinstance(current_value, str) and "mm/rev" in current_value.lower():
            destination = "next quicker available pinion" if direction_sign > 0 else "next slower available pinion"
        else:
            destination = "next quicker available ratio" if direction_sign < 0 else "next slower available ratio"
    elif "ride_height" in key:
        destination = "next higher available ride-height value" if direction_sign > 0 else "next lower available ride-height value"
    elif key == "tape_percent":
        destination = "next more-closed cooling option" if direction_sign > 0 else "next more-open cooling option"
    else:
        destination = "next higher available setting" if direction_sign > 0 else "next lower available setting"
    return f"{current} -> {destination}"


def garage_action_for_effect(item: Any, setup_values: dict[str, Any] | None = None) -> GarageAction | None:
    plan = _PLANS.get(item.effect.effect_id)
    if plan is None:
        return None
    setup_values = setup_values or {}
    target_lines: list[str] = []
    proposed_values: list[str] = []
    for key in plan.control_keys:
        target, transition = nominal_test_target(key, setup_values.get(key), plan.direction_sign)
        target_lines.append(f"{SETUP_CONTROL_SPECS[key].label}: {transition}")
        if target:
            proposed_values.append(f"{SETUP_CONTROL_SPECS[key].label} {target}")

    if len(plan.control_keys) == 1:
        key = plan.control_keys[0]
        spec = SETUP_CONTROL_SPECS[key]
        transition = target_lines[0].split(": ", 1)[1]
        if spec.nominal_test_increment is None:
            transition = _next_available_transition(key, setup_values.get(key), plan.direction_sign)
            change_this = f"{spec.label}: {transition} (one available garage step)."
        else:
            change_this = f"{spec.label}: {transition}."
        lever = spec.garage_label or spec.label
        influence = spec.influence_label
    else:
        joined = "; ".join(target_lines)
        scope_instruction = (
            "Move both front ride-height controls by the same amount"
            if len(plan.control_keys) == 2 and plan.control_keys[0].startswith("lf_")
            else "Move both rear ride-height controls by the same amount"
            if len(plan.control_keys) == 2
            else "Move all four ride-height controls by the same amount"
        )
        change_this = f"{joined}. {scope_instruction} as one coordinated ride-height test."
        lever = " + ".join(SETUP_CONTROL_SPECS[key].garage_label or SETUP_CONTROL_SPECS[key].label for key in plan.control_keys)
        influence = "Strong, coupled ride-height influence"

    if len(plan.control_keys) > 1:
        control_expectation, control_guardrail = _coordinated_ride_height_wording(plan)
    else:
        control_expectation = expected_control_effect(plan.control_keys[0], plan.direction_sign, setup_values.get(plan.control_keys[0]))
        control_guardrail = SETUP_CONTROL_SPECS[plan.control_keys[0]].guardrail

    return GarageAction(
        title=plan.title,
        change_this=change_this,
        garage_lever=lever,
        control_keys=list(plan.control_keys),
        change_size_label=recommended_test_size_label(plan.control_keys[0]),
        change_size_explanation=_unique_join([SETUP_CONTROL_SPECS[key].magnitude_policy for key in plan.control_keys]),
        influence_label=influence,
        control_expectation=control_expectation,
        control_guardrail=control_guardrail,
        current_value_label=_current_summary(plan.control_keys, setup_values),
        proposed_value_label="; ".join(proposed_values) or None,
    )
