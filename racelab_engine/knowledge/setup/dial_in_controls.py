from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    assess_setup_change,
    expected_control_effect,
    format_setup_value,
    resolve_adjacent_setup_target,
)


RELATED_SETUP_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "front_ride_height": ("lf_ride_height_mm", "rf_ride_height_mm"),
    "rear_ride_height": ("lr_ride_height_mm", "rr_ride_height_mm"),
    "ride_height": ("lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"),
    "front_springs": ("lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm"),
    "rear_springs": ("lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm"),
    "steering_offset": ("steering_offset_deg",),
    "cross_weight": ("cross_weight_percent",),
    "front_brake_bias": ("front_brake_bias_percent",),
    "final_drive": ("rear_end_ratio",),
}


def expanded_related_setup_keys(keys: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    for key in keys:
        if key in SETUP_CONTROL_SPECS:
            expanded.append(key)
        expanded.extend(RELATED_SETUP_KEY_ALIASES.get(key, ()))
    return tuple(dict.fromkeys(expanded))


@dataclass(frozen=True)
class GarageAction:
    title: str
    change_this: str
    garage_lever: str
    control_keys: list[str]
    direction_sign: int
    change_size_label: str
    change_size_explanation: str
    influence_label: str
    control_expectation: str
    control_guardrail: str
    current_value_label: str | None = None
    proposed_value_label: str | None = None
    target_ready: bool = False
    target_blockers: tuple[str, ...] = ()


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


_EXPERIMENT_FACTOR_BY_CONTROL_SET: dict[tuple[str, ...], str] = {
    ("cross_weight_percent",): "factor:crossweight",
    ("rf_front_spring_n_per_mm",): "factor:rf_spring_rate",
    ("lr_rear_spring_n_per_mm",): "factor:lr_spring_rate",
    ("front_brake_bias_percent",): "factor:front_brake_distribution",
    ("rear_end_ratio",): "factor:final_drive_ratio",
    ("lf_ride_height_mm", "rf_ride_height_mm"): "factor:front_platform_height",
    ("lr_ride_height_mm", "rr_ride_height_mm"): "factor:rear_platform_height",
    (
        "lf_ride_height_mm",
        "rf_ride_height_mm",
        "lr_ride_height_mm",
        "rr_ride_height_mm",
    ): "factor:whole_platform_height",
}


def control_keys_for_effect(effect_id: str) -> tuple[str, ...]:
    plan = _PLANS.get(effect_id)
    return plan.control_keys if plan is not None else ()


def control_direction_for_effect(effect_id: str) -> int | None:
    """Return the reviewed action direction, never a prose-derived guess."""

    plan = _PLANS.get(effect_id)
    return plan.direction_sign if plan is not None else None


def experiment_factor_id_for_effect(effect_id: str) -> str | None:
    """Bind an actionable catalog effect to one P26 experiment factor."""

    plan = _PLANS.get(effect_id)
    return (
        _EXPERIMENT_FACTOR_BY_CONTROL_SET.get(plan.control_keys)
        if plan is not None
        else None
    )


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


def garage_action_for_effect(
    item: Any,
    setup_values: dict[str, Any] | None = None,
    *,
    legal_values_by_control: Mapping[str, Sequence[Any]] | None = None,
    legal_value_provenance_by_control: Mapping[
        str, Mapping[Any, Sequence[str] | str]
    ] | None = None,
) -> GarageAction | None:
    plan = _PLANS.get(item.effect.effect_id)
    if plan is None:
        return None
    setup_values = setup_values or {}
    legal_values_by_control = legal_values_by_control or {}
    legal_value_provenance_by_control = legal_value_provenance_by_control or {}
    target_lines: list[str] = []
    proposed_values: list[str] = []
    resolutions = {}
    for key in plan.control_keys:
        resolution = resolve_adjacent_setup_target(
            key,
            setup_values.get(key),
            plan.direction_sign,
            legal_values=legal_values_by_control.get(key),
            legal_value_provenance=legal_value_provenance_by_control.get(key),
        )
        resolutions[key] = resolution
        target_lines.append(f"{SETUP_CONTROL_SPECS[key].label}: {resolution.transition}")
        if resolution.ready:
            proposed_values.append(f"{SETUP_CONTROL_SPECS[key].label} {resolution.target_label}")

    target_blockers = tuple(dict.fromkeys(
        resolution.blocker
        for resolution in resolutions.values()
        if resolution.blocker is not None
    ))
    target_ready = not target_blockers and all(resolution.ready for resolution in resolutions.values())

    if len(plan.control_keys) == 1:
        key = plan.control_keys[0]
        spec = SETUP_CONTROL_SPECS[key]
        resolution = resolutions[key]
        if target_ready:
            change_this = f"{spec.label}: {resolution.transition}."
        else:
            change_this = f"Do not change {spec.label} yet. {resolution.blocker}"
        lever = spec.garage_label or spec.label
        influence = spec.influence_label
    else:
        lever = " + ".join(SETUP_CONTROL_SPECS[key].garage_label or SETUP_CONTROL_SPECS[key].label for key in plan.control_keys)
        influence = "Strong, coupled ride-height influence"
        if target_ready:
            joined = "; ".join(target_lines)
            scope_instruction = (
                "Move both front ride-height controls to their recorded adjacent values"
                if len(plan.control_keys) == 2 and plan.control_keys[0].startswith("lf_")
                else "Move both rear ride-height controls to their recorded adjacent values"
                if len(plan.control_keys) == 2
                else "Move all four ride-height controls to their recorded adjacent values"
            )
            change_this = f"{joined}. {scope_instruction} as one coordinated ride-height test."
        else:
            change_this = f"Do not change {lever} yet. {' '.join(target_blockers)}"

    if len(plan.control_keys) > 1:
        control_expectation, control_guardrail = _coordinated_ride_height_wording(plan)
    else:
        control_expectation = expected_control_effect(plan.control_keys[0], plan.direction_sign, setup_values.get(plan.control_keys[0]))
        control_guardrail = SETUP_CONTROL_SPECS[plan.control_keys[0]].guardrail

    if target_ready:
        assessments = [
            assess_setup_change(key, setup_values.get(key), resolutions[key].target_value)
            for key in plan.control_keys
        ]
        if len(assessments) == 1:
            change_size_label = (
                f"{assessments[0].label.title()} test input - adjacent recorded garage option"
            )
        else:
            change_size_label = "Recorded adjacent-option ride-height test"
        change_size_explanation = _unique_join([
            *(assessment.basis for assessment in assessments),
            *(
                f"{SETUP_CONTROL_SPECS[key].label} target source: "
                f"{', '.join(resolutions[key].provenance)}."
                for key in plan.control_keys
            ),
        ])
    else:
        change_size_label = "Target unavailable - record adjacent option"
        change_size_explanation = _unique_join(list(target_blockers))

    return GarageAction(
        title=plan.title,
        change_this=change_this,
        garage_lever=lever,
        control_keys=list(plan.control_keys),
        direction_sign=plan.direction_sign,
        change_size_label=change_size_label,
        change_size_explanation=change_size_explanation,
        influence_label=influence,
        control_expectation=control_expectation,
        control_guardrail=control_guardrail,
        current_value_label=_current_summary(plan.control_keys, setup_values),
        proposed_value_label="; ".join(proposed_values) if target_ready else None,
        target_ready=target_ready,
        target_blockers=target_blockers,
    )
