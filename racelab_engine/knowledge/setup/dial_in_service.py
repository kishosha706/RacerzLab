from __future__ import annotations

from typing import Any

from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS
from racelab_engine.analysis.setup_diff import setup_control_value
from racelab_engine.storage.repository import RaceLabRepository

from .dial_in_controls import GarageAction, garage_action_for_effect
from .dial_in_schema import Clarification, DialInResponse, DialInSwing, HiddenEvidenceSummary
from .display_labels import (
    DIAL_IN_STRENGTH_LABELS,
    format_success_target,
    format_target_label,
    format_watch_target,
)
from .evidence_adapter import build_run_evidence_context, query_setup_for_run_context
from .loader import load_setup_knowledge
from .matcher import RankedSetupEffect, parse_symptom


VAGUE_ACTION_TERMS = (
    "adjust ",
    "tune ",
    "trim ",
    "support",
    "response swing",
    "supported axle",
    "pressure trend",
    "setup area",
    "investigate",
    "review",
    "protect ",
)

RISK_LABELS = {
    "low": "Low risk",
    "medium": "Medium risk",
    "high": "High risk",
}
CANDIDATE_READINESS_LABELS = {
    "ready": "Data profile clean",
    "partially_ready": "Data profile partial",
    "missing_key_evidence": "Need cleaner data",
}
GENERIC_COMPLAINTS = {"loose", "tight", "push", "free", "bad", "weird", "off"}
GENERIC_CLARIFICATION_QUESTION = "Where is it happening?"
GENERIC_CLARIFICATION_OPTIONS = ["Entry", "Center", "Exit", "Whole corner", "On brake", "On throttle"]


def _normalize_complaint(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _balance_label(value: str | None) -> str | None:
    return value.replace("_", " ") if value else None


def _confidence_label(complaint: str, *, needs_clarification: bool, supported: bool) -> str:
    if not supported:
        return "Unsupported"
    if needs_clarification and _normalize_complaint(complaint) in GENERIC_COMPLAINTS:
        return "Needs phase"
    if needs_clarification:
        return "Needs clarification"
    return "Clear read"


def _evidence_status_hint(context_warnings: list[str], *, baseline_run_id: str | None, test_run_id: str | None) -> str | None:
    if baseline_run_id:
        return "Compare baseline is missing."
    if test_run_id:
        return "Compare test run is missing."
    for warning in context_warnings:
        lower = warning.lower()
        if "car family could not be resolved" in lower:
            return "Car family is still generic."
        if "track family could not be resolved" in lower:
            return "Track family is still generic."
    return None


def _readiness_label(candidate_readiness: list[str], *, missing_hint: str | None) -> str:
    if not candidate_readiness:
        return "Need cleaner data"
    if all(item == "ready" for item in candidate_readiness) and not missing_hint:
        return "Data profile looks clean"
    if all(item == "missing_key_evidence" for item in candidate_readiness):
        return "Need cleaner data"
    return "Data profile is partial"


def _is_major_package_swing(effect: RankedSetupEffect) -> bool:
    return effect.effect.exact_value_policy == "reference_only" or effect.effect.effect_strength >= 5


def _sentence(text: str) -> str:
    text = " ".join(text.strip().split())
    if not text:
        return text
    return text if text.endswith(".") else f"{text}."


def _legacy_garage_action_for_effect(item: RankedSetupEffect) -> tuple[str, str] | None:
    effect = item.effect
    effect_id = effect.effect_id
    direction = effect.direction.lower()
    area = effect.setup_area

    exact_by_id: dict[str, tuple[str, str]] = {
        "add_crossweight_small": ("Add cross weight one small step.", "Cross weight"),
        "reduce_crossweight_small": ("Reduce cross weight one small step.", "Cross weight"),
        "add_rear_stability_pressure_swing": (
            "Increase LR/RR rear pressure split by raising LR or lowering RR one small step.",
            "LR/RR rear tire pressure split",
        ),
        "pressure_split_stability_swing": (
            "Increase LR/RR rear pressure split by raising LR or lowering RR one small step.",
            "LR/RR rear tire pressure split",
        ),
        "add_front_brake_bias_small": ("Move brake bias forward one small step.", "Brake bias"),
        "reduce_front_brake_bias_small": ("Move brake bias rearward one small step.", "Brake bias"),
        "shorter_final_drive": ("Use a numerically higher rear end ratio for more acceleration.", "Rear end ratio"),
        "taller_final_drive": ("Use a numerically lower rear end ratio for more straight speed.", "Rear end ratio"),
        "add_front_platform_support": ("Lower LF/RF front ride height one small step.", "LF/RF front ride height"),
        "reduce_front_platform_support": ("Raise LF/RF front ride height one small step.", "LF/RF front ride height"),
        "add_rear_platform_support": ("Raise LR/RR rear ride height one small step.", "LR/RR rear ride height"),
        "reduce_rear_platform_support": ("Lower LR/RR rear ride height one small step.", "LR/RR rear ride height"),
        "reduce_platform_contact_small": ("Raise all four ride heights one small step.", "Ride height"),
        "raise_front_shock_collar_small": ("Raise LF/RF front ride height one small step.", "LF/RF front ride height"),
        "lower_front_shock_collar_small": ("Lower LF/RF front ride height one small step.", "LF/RF front ride height"),
        "raise_rear_shock_collar_small": ("Raise LR/RR rear ride height one small step.", "LR/RR rear ride height"),
        "lower_rear_shock_collar_small": ("Lower LR/RR rear ride height one small step.", "LR/RR rear ride height"),
        "add_front_response_toe_swing": ("Add front toe-out one small step.", "Front toe"),
        "reduce_front_toe_scrub": ("Reduce front toe-out one small step.", "Front toe"),
        "add_rear_toe_stability": ("Add rear toe-in one small step.", "Rear toe"),
        "reduce_rear_toe_bind": ("Reduce rear toe-in one small step.", "Rear toe"),
        "switch_front_arb_to_soft_bar": ("Switch front ARB diameter to the soft bar.", "Front ARB diameter"),
        "switch_front_arb_to_stiff_bar": ("Switch front ARB diameter to the stiffer bar.", "Front ARB diameter"),
        "switch_rear_arb_to_soft_bar": ("Switch rear ARB diameter to the 1.375 soft bar.", "Rear ARB diameter"),
        "switch_rear_arb_to_stiff_bar": ("Switch rear ARB diameter to the 2.000 stiff bar.", "Rear ARB diameter"),
        "soften_front_arb_arm": ("Move front ARB arm one hole softer toward P1.", "Front ARB arm"),
        "soften_front_arb_arm_one_position": ("Move front ARB arm one hole softer toward P1.", "Front ARB arm"),
        "stiffen_front_arb_arm": ("Move front ARB arm one hole stiffer toward P5.", "Front ARB arm"),
        "stiffen_front_arb_arm_one_position": ("Move front ARB arm one hole stiffer toward P5.", "Front ARB arm"),
        "soften_rear_arb_arm": ("Move rear ARB arm one hole softer toward P1.", "Rear ARB arm"),
        "soften_rear_arb_arm_one_position": ("Move rear ARB arm one hole softer toward P1.", "Rear ARB arm"),
        "stiffen_rear_arb_arm": ("Move rear ARB arm one hole stiffer toward P5.", "Rear ARB arm"),
        "stiffen_rear_arb_arm_one_position": ("Move rear ARB arm one hole stiffer toward P5.", "Rear ARB arm"),
        "add_hs_compression_for_bumps": ("Add all four HS compression one click.", "HS compression"),
        "reduce_hs_compression_for_compliance": ("Reduce all four HS compression one click.", "HS compression"),
        "add_hs_rebound_control": ("Add all four HS rebound one click.", "HS rebound"),
        "reduce_hs_rebound_recovery": ("Reduce all four HS rebound one click.", "HS rebound"),
        "slope_more_linear_bumpy": ("Use more linear HS compression slope one small step.", "HS compression slope"),
        "slope_more_digressive_smooth": ("Use more digressive HS compression slope one small step.", "HS compression slope"),
    }
    if effect_id in exact_by_id:
        return exact_by_id[effect_id]

    tire_aliases = {
        "lf": "LF",
        "rf": "RF",
        "lr": "LR",
        "rr": "RR",
    }
    if area == "tire_pressure":
        corner = next((label for token, label in tire_aliases.items() if f"_{token}_" in f"_{effect_id}_" or f" {token} " in f" {direction} "), None)
        if corner:
            verb = "Raise" if direction.startswith(("add", "raise", "increase")) else "Lower" if direction.startswith(("reduce", "lower")) else None
            if verb:
                return (f"{verb} {corner} tire pressure one small step.", f"{corner} tire pressure")
        return None

    if area == "spring_rate":
        corner = next((label for token, label in tire_aliases.items() if f"_{token}_" in f"_{effect_id}_"), None)
        if corner:
            verb = "Increase" if direction.startswith(("add", "increase", "raise")) else "Reduce" if direction.startswith(("reduce", "lower")) else None
            if verb:
                return (f"{verb} {corner} spring rate one small step.", f"{corner} spring rate")
        return None

    if area == "diff_preload":
        if direction.startswith("increase"):
            return ("Increase diff preload one small step.", "Diff preload")
        if direction.startswith("reduce"):
            return ("Reduce diff preload one small step.", "Diff preload")
        return None

    shock_settings = {
        "ls_compression": "LS compression",
        "ls_rebound": "LS rebound",
        "hs_compression": "HS compression",
        "hs_rebound": "HS rebound",
    }
    if area in shock_settings:
        setting = shock_settings[area]
        verb = "Add" if direction.startswith("add") else "Reduce" if direction.startswith("reduce") else None
        if not verb:
            return None
        corner = next((label for token, label in tire_aliases.items() if f"_{token}_" in f"_{effect_id}_"), None)
        if corner:
            return (f"{verb} {corner} {setting} one click.", f"{corner} {setting}")
        axle = "front" if "front" in direction or "_front" in effect_id else "rear" if "rear" in direction or "_rear" in effect_id else "all four"
        lever = f"{axle.title()} {setting}" if axle != "all four" else setting
        return (f"{verb} {axle} {setting} one click.", lever)

    if area in {"front_arb_preload", "rear_arb_preload"}:
        axle = "front" if area.startswith("front") else "rear"
        if direction.startswith(("reduce", "lower")):
            return (f"Reduce {axle} ARB preload one small step.", f"{axle.title()} ARB preload")
        if direction.startswith(("increase", "add", "raise")):
            return (f"Increase {axle} ARB preload one small step.", f"{axle.title()} ARB preload")
        return None

    if area in {"toe", "front_toe_response", "rear_toe_stability"}:
        if "front" in effect_id or "front" in direction:
            if direction.startswith(("add", "increase")):
                return ("Add front toe-out one small step.", "Front toe")
            if direction.startswith("reduce"):
                return ("Reduce front toe-out one small step.", "Front toe")
        if "rear" in effect_id or "rear" in direction:
            if direction.startswith(("add", "increase")):
                return ("Add rear toe-in one small step.", "Rear toe")
            if direction.startswith("reduce"):
                return ("Reduce rear toe-in one small step.", "Rear toe")
        return None

    candidate = _sentence(effect.direction)
    lower = candidate.lower()
    if any(term in lower for term in VAGUE_ACTION_TERMS):
        return None
    if area in {"track_bar", "truck_arm_mount", "bump_stop", "packer", "camber", "caster", "diffuser_platform"}:
        return None
    return (candidate, effect.setup_area.replace("_", " ").title())


def _specific_one_change_test(item: RankedSetupEffect, action: GarageAction) -> str:
    scope = "these linked ride-height controls" if len(action.control_keys) > 1 else "this control"
    return (
        f"Change only {scope}. Repeat the baseline run length with similar fuel and tire age, "
        "then compare eligible laps at the same track positions."
    )


def _visible_explanation(text: str) -> str:
    replacements = {
        "pressure trend": "tire temperature and falloff evidence",
        "tire-work trend": "tire temperature and falloff",
        "supported axle": "LR/RR rear split",
        "front response toe swing": "front toe-out change",
        "Tune diff preload": "Change diff preload",
        "tune the connected feel": "change the connected feel",
    }
    cleaned = text
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new).replace(old.capitalize(), new.capitalize())
    return cleaned


EXPECTED_WORDING: dict[str, str] = {
    "add_crossweight_small": "Expect a calmer entry and more secure throttle pickup on exit.",
    "reduce_crossweight_small": "Expect freer center rotation and less bound-up drive-off.",
    "add_rf_spring_small": "Expect less RF deflection and firmer RF platform control through the measured problem zone; grip must be verified rather than assumed.",
    "spring_package_platform_support": "Expect less RF deflection and firmer RF platform control through the measured problem zone; grip must be verified rather than assumed.",
    "reduce_rf_spring_small": "Expect more RF compliance and travel through the measured problem zone.",
    "add_lr_spring_support": "Expect less LR deflection and firmer LR platform control during throttle pickup; the exit-balance result must be measured.",
    "reduce_lr_spring_for_drive": "Expect more LR compliance and travel through throttle pickup and corner exit.",
    "spring_package_compliance": "Expect more LR compliance where telemetry shows the rear is too stiff over the surface; do not assume the whole rear axle softened equally.",
    "add_front_brake_bias_small": "Expect a calmer rear axle while braking into the corner.",
    "reduce_front_brake_bias_small": "Expect more rotation under braking and a less front-limited entry.",
    "shorter_final_drive": "Expect higher RPM and greater torque multiplication at the same road speed; acceleration improves only if traction and shift timing remain favorable.",
    "taller_final_drive": "Expect lower RPM at the same road speed and more limiter margin; terminal speed improves only if the engine can pull the taller gear.",
    "add_front_platform_support": "On a ride-height-sensitive car, expect stronger high-speed front response only if front contact remains controlled.",
    "lower_front_shock_collar_small": "On a ride-height-sensitive car, expect stronger high-speed front response only if front contact remains controlled.",
    "reduce_front_platform_support": "Expect more front ride-height margin and fewer contact events.",
    "improve_front_feed_window": "Expect more front ride-height margin and a steadier platform trace.",
    "raise_front_shock_collar_small": "Expect more front ride-height margin and fewer contact events.",
    "add_rear_platform_support": "Expect more rear ride-height margin and fewer rear scrape events.",
    "raise_rear_shock_collar_small": "Expect more rear ride-height margin and fewer rear scrape events.",
    "reduce_rear_platform_support": "Expect a lower rear platform; treat any high-speed balance benefit as a car-specific proxy and keep it only if scrape margin remains healthy.",
    "lower_rear_shock_collar_small": "Expect a lower rear platform; treat any high-speed balance benefit as a car-specific proxy and keep it only if scrape margin remains healthy.",
    "reduce_platform_contact_small": "Expect fewer repeatable platform-contact events.",
}

TRADE_WORDING: dict[str, str] = {
    "add_crossweight_small": "Too much can create center push, scrub speed, or reduce LF braking load.",
    "reduce_crossweight_small": "Too little can make entry or throttle pickup nervous.",
    "add_rf_spring_small": "A stiffer RF can reduce center grip and increase steering demand.",
    "spring_package_platform_support": "A stiffer RF can reduce center grip and increase steering demand.",
    "reduce_rf_spring_small": "A softer RF can increase platform movement or front contact.",
    "add_lr_spring_support": "A stiffer LR can bind the center or reduce rear compliance.",
    "reduce_lr_spring_for_drive": "A softer LR can reduce rear platform margin or exit security.",
    "spring_package_compliance": "More compliance can allow excess platform movement at speed.",
    "add_front_brake_bias_small": "More front bias can add entry push or front lockup.",
    "reduce_front_brake_bias_small": "More rear brake demand can make entry unstable or cause rear lockup.",
    "shorter_final_drive": "RPM rises everywhere; undo if the limiter arrives early or terminal speed falls.",
    "taller_final_drive": "Acceleration softens; undo if drive-off gets worse without a clear speed gain.",
    "add_front_platform_support": "Front clearance decreases; undo if contact events or speed loss increase.",
    "lower_front_shock_collar_small": "Front clearance decreases; undo if contact events or speed loss increase.",
    "reduce_front_platform_support": "High-speed front response may weaken if the front is raised too far.",
    "improve_front_feed_window": "High-speed front response may weaken if the front is raised too far.",
    "raise_front_shock_collar_small": "High-speed front response may weaken if the front is raised too far.",
    "add_rear_platform_support": "Raising the rear changes rake and may change high-speed or exit balance; the direction and size are car-specific.",
    "raise_rear_shock_collar_small": "Raising the rear changes rake and may change high-speed or exit balance; the direction and size are car-specific.",
    "reduce_rear_platform_support": "Rear clearance decreases; undo if scrape or unstable rear-height behavior appears.",
    "lower_rear_shock_collar_small": "Rear clearance decreases; undo if scrape or unstable rear-height behavior appears.",
    "reduce_platform_contact_small": "A higher platform may give away speed or mechanical grip even when contact improves.",
}

KEEP_WORDING: dict[str, str] = {
    "add_crossweight_small": "Keep it only if entry is calmer and throttle pickup improves without adding center push.",
    "reduce_crossweight_small": "Keep it only if center speed or rotation improves without making entry or exit loose.",
    "add_rf_spring_small": "Keep it only if RF platform movement improves without increasing steering demand.",
    "spring_package_platform_support": "Keep it only if RF platform movement improves without increasing steering demand.",
    "reduce_rf_spring_small": "Keep it only if front response improves and front contact does not increase.",
    "add_lr_spring_support": "Keep it only if throttle pickup improves without adding center push.",
    "reduce_lr_spring_for_drive": "Keep it only if drive-off improves without reducing rear ride-height margin.",
    "spring_package_compliance": "Keep it only if compliance improves without adding excess platform movement.",
    "add_front_brake_bias_small": "Keep it only if braking entry is calmer without adding front lockup or entry push.",
    "reduce_front_brake_bias_small": "Keep it only if entry rotation improves without rear lockup or instability.",
    "shorter_final_drive": "Keep it only if acceleration improves and the limiter still has safe margin at peak straight speed.",
    "taller_final_drive": "Keep it only if terminal speed improves without a meaningful drive-off loss.",
    "add_front_platform_support": "Keep it only if high-speed front response improves and front contact does not increase.",
    "lower_front_shock_collar_small": "Keep it only if high-speed front response improves and front contact does not increase.",
    "reduce_front_platform_support": "Keep it only if front contact decreases without a meaningful loss of center speed or front response.",
    "improve_front_feed_window": "Keep it only if front ride-height movement becomes more stable without a meaningful speed loss.",
    "raise_front_shock_collar_small": "Keep it only if front contact decreases without a meaningful loss of center speed or front response.",
    "add_rear_platform_support": "Keep it only if rear scrape decreases without making exit balance or straight speed worse.",
    "raise_rear_shock_collar_small": "Keep it only if rear scrape decreases without making exit balance or straight speed worse.",
    "reduce_rear_platform_support": "Keep it only if exit or straight speed improves and rear scrape does not increase.",
    "lower_rear_shock_collar_small": "Keep it only if exit or straight speed improves and rear scrape does not increase.",
    "reduce_platform_contact_small": "Keep it only if contact events decrease without a meaningful loss of speed or mechanical grip.",
}


def _effect_wording(item: RankedSetupEffect) -> str:
    return EXPECTED_WORDING.get(item.effect.effect_id, _visible_explanation(item.effect.effect))


def _trade_wording(item: RankedSetupEffect) -> str:
    return TRADE_WORDING.get(item.effect.effect_id, _visible_explanation(item.effect.counter_effect))


def _keep_if(item: RankedSetupEffect) -> str:
    if wording := KEEP_WORDING.get(item.effect.effect_id):
        return wording
    targets = [format_success_target(target) for target in item.effect.validation_targets[:2]]
    if not targets:
        return "Keep it only if the original complaint improves beyond normal lap-to-lap variation."
    return f"Keep it only if {' and '.join(targets)}."


def _undo_if(item: RankedSetupEffect) -> str:
    targets = [format_watch_target(target) for target in item.effect.watch_for_targets[:2]]
    if not targets:
        return "Undo it if the original complaint gets worse or a new handling problem appears."
    return f"Undo it if {' or '.join(targets)}."


def _filter_swings(candidates: list[RankedSetupEffect], limit: int) -> list[RankedSetupEffect]:
    selected: list[RankedSetupEffect] = []
    major_package_count = 0
    covered_controls: set[str] = set()
    for item in candidates:
        if len(selected) >= limit:
            break
        action = garage_action_for_effect(item)
        if action is None:
            continue
        if covered_controls.intersection(action.control_keys):
            continue
        if _is_major_package_swing(item):
            if major_package_count >= 1:
                continue
            major_package_count += 1
        selected.append(item)
        covered_controls.update(action.control_keys)
    return selected


def _build_swing(
    item: RankedSetupEffect,
    *,
    setup_values: dict[str, Any],
    include_debug_evidence: bool,
) -> DialInSwing:
    garage_action = garage_action_for_effect(item, setup_values)
    if garage_action is None:
        raise ValueError(f"Dial-In swing lacks a specific garage action: {item.effect.effect_id}")
    debug: dict[str, Any] | None = None
    if include_debug_evidence:
        debug = {
            "readiness": item.readiness,
            "evidence_present": item.evidence_matched,
            "evidence_missing": item.missing_evidence,
            "ranking_reasons": item.ranking_reasons,
            "score": round(item.score, 3),
        }
    return DialInSwing(
        id=item.effect.effect_id,
        title=garage_action.title,
        change_this=garage_action.change_this,
        garage_lever=garage_action.garage_lever,
        control_keys=garage_action.control_keys,
        setup_area=item.effect.setup_area,
        change_size_label=garage_action.change_size_label,
        change_size_explanation=garage_action.change_size_explanation,
        influence_label=garage_action.influence_label,
        control_expectation=garage_action.control_expectation,
        control_guardrail=garage_action.control_guardrail,
        current_value_label=garage_action.current_value_label,
        proposed_value_label=garage_action.proposed_value_label,
        strength_label=DIAL_IN_STRENGTH_LABELS.get(item.effect.effect_strength, "Setup lever"),
        risk_label=RISK_LABELS.get(item.effect.coupling_risk, item.effect.coupling_risk.title()),
        effect=_effect_wording(item),
        counter_effect=_trade_wording(item),
        one_change_test=_specific_one_change_test(item, garage_action),
        validate_with=item.effect.validation_targets,
        validate_with_labels=[format_target_label(target) for target in item.effect.validation_targets],
        watch_for=item.effect.watch_for_targets,
        watch_for_labels=[format_target_label(target) for target in item.effect.watch_for_targets],
        keep_if=_keep_if(item),
        undo_if=_undo_if(item),
        readiness_label=CANDIDATE_READINESS_LABELS.get(item.readiness, item.readiness.replace("_", " ").title()),
        debug=debug,
    )


def _validation_summary(swings: list[DialInSwing]) -> str | None:
    targets: list[str] = []
    for swing in swings:
        for target in swing.validate_with_labels:
            if target not in targets:
                targets.append(target)
    if not targets:
        return None
    return f"Primary evidence signals: {', '.join(targets[:5])}."


def _readiness_sentence(readiness_label: str) -> str:
    if readiness_label == "Data profile looks clean":
        return "Data coverage is strong. Confirm the recommendation with one controlled A/B test."
    if readiness_label == "Data profile is partial":
        return "Data profile is partial. Pick one change and validate it."
    if readiness_label == "Need cleaner data":
        return "I need a cleaner run to be sure."
    return f"Readiness: {readiness_label}."


def _driver_warnings(warnings: list[str], *, include_debug_evidence: bool) -> list[str]:
    if include_debug_evidence:
        return warnings
    cleaned: list[str] = []
    for warning in warnings:
        if "measured downforce" in warning.lower():
            cleaned.append("Derived diffuser geometry proxy is available. Treat it as geometry context.")
        else:
            cleaned.append(warning)
    return cleaned


def _driver_message(
    complaint: str,
    interpreted_symptom: str | None,
    readiness_label: str,
    missing_hint: str | None,
    swings: list[DialInSwing],
) -> str:
    if not interpreted_symptom:
        return f'I could not map "{complaint}" to a supported setup complaint yet. Try a cleaner run or narrow the complaint.'
    opening = f"You said {complaint}. I'm reading that as {interpreted_symptom.replace('_', ' ')}."
    if not swings:
        if missing_hint:
            return f"{opening} I need a cleaner run to be sure. {missing_hint}"
        return f"{opening} I need a cleaner run to be sure."
    if missing_hint:
        return f"{opening} {_readiness_sentence(readiness_label)} {missing_hint}"
    return f"{opening} {_readiness_sentence(readiness_label)}"


def _hidden_summary(result, context) -> HiddenEvidenceSummary:
    present_evidence: list[str] = []
    missing_evidence: list[str] = []
    for item in result.setup_query.candidate_effects:
        for evidence in item.evidence_matched:
            if evidence not in present_evidence:
                present_evidence.append(evidence)
        for evidence in item.missing_evidence:
            if evidence not in missing_evidence:
                missing_evidence.append(evidence)
    disabled = [
        {"effect_id": effect.effect_id, "setup_area": effect.setup_area, "direction": effect.direction}
        for effect in result.setup_query.disabled_by_car_capability
    ]
    return HiddenEvidenceSummary(
        evidence_flags=context.evidence_flags,
        evidence_groups=context.evidence_groups,
        present_evidence=present_evidence,
        missing_evidence=missing_evidence,
        readiness_by_candidate=result.candidate_readiness,
        ranking_reasons=result.setup_query.ranking_reasons,
        disabled_by_capability=disabled,
    )


def _driver_setup_values(run_id: str) -> dict[str, Any]:
    snapshot = RaceLabRepository().get_setup_snapshot(run_id)
    if snapshot is None:
        return {}
    return {
        key: value
        for key in SETUP_CONTROL_SPECS
        if (value := setup_control_value(snapshot, key)) is not None
    }


def build_dial_in_response(
    run_id: str,
    complaint: str,
    *,
    car_family_override: str | None = None,
    track_family_override: str | None = None,
    baseline_run_id: str | None = None,
    test_run_id: str | None = None,
    package_archetype: str | None = None,
    limit: int = 3,
    include_debug_evidence: bool = False,
) -> DialInResponse:
    context = build_run_evidence_context(
        run_id,
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        car_family_override=car_family_override,
        track_family_override=track_family_override,
    )
    knowledge = load_setup_knowledge()
    try:
        parsed = parse_symptom(complaint, knowledge)
    except ValueError:
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            confidence_label=_confidence_label(complaint, needs_clarification=False, supported=False),
            readiness_label="Need cleaner data",
            driver_message=f'I could not map "{complaint}" to a supported setup complaint yet. Try a cleaner run or narrow the complaint.',
            next_step="Try naming the phase, trigger, or main behavior first.",
            clarification=Clarification(needed=False),
            warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
        )

    normalized_complaint = _normalize_complaint(complaint)
    question = parsed.clarification_question
    options = parsed.clarification_options
    if question is not None and normalized_complaint in GENERIC_COMPLAINTS:
        question = GENERIC_CLARIFICATION_QUESTION
        options = GENERIC_CLARIFICATION_OPTIONS
    clarification = Clarification(
        needed=question is not None,
        question=question,
        options=options,
    )
    confidence_label = _confidence_label(complaint, needs_clarification=clarification.needed, supported=True)

    if clarification.needed:
        message = f"I need to narrow it down. {clarification.question}"
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            interpreted_symptom=parsed.canonical_symptom,
            interpreted_phase=parsed.phase,
            balance_direction=_balance_label(parsed.balance),
            confidence_label=confidence_label,
            readiness_label="Need cleaner data",
            driver_message=message,
            next_step="Answer the clarification first. Then pick one change, not a handful.",
            clarification=clarification,
            warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
            hidden_evidence_summary=_hidden_summary(
                query_setup_for_run_context(
                    run_id,
                    complaint,
                    evidence_context=context,
                    baseline_run_id=baseline_run_id,
                    test_run_id=test_run_id,
                    car_family_override=car_family_override,
                    track_family_override=track_family_override,
                    package_archetype=package_archetype,
                    limit=max(limit, 1),
                ),
                context,
            )
            if include_debug_evidence
            else None,
        )

    query_result = query_setup_for_run_context(
        run_id,
        complaint,
        evidence_context=context,
        baseline_run_id=baseline_run_id,
        test_run_id=test_run_id,
        car_family_override=car_family_override,
        track_family_override=track_family_override,
        package_archetype=package_archetype,
        limit=max(limit * 4, limit),
    )
    selected = _filter_swings(query_result.setup_query.candidate_effects, limit)
    setup_values = _driver_setup_values(run_id)
    swings = [
        _build_swing(item, setup_values=setup_values, include_debug_evidence=include_debug_evidence)
        for item in selected
    ]

    missing_hint = _evidence_status_hint(
        context.warnings,
        baseline_run_id=baseline_run_id if context.unavailable_reasons.get("compare_baseline") else None,
        test_run_id=test_run_id if context.unavailable_reasons.get("compare_test") else None,
    )
    readiness_label = _readiness_label([item.readiness for item in selected], missing_hint=missing_hint)
    next_step = "Change one test plan, match fuel and tire age, then compare eligible laps by track position."
    if readiness_label == "Need cleaner data":
        next_step = "Data's noisy here. Try a cleaner run or narrow the complaint."
    if missing_hint:
        next_step = f"{next_step} {missing_hint}"

    return DialInResponse(
        run_id=run_id,
        complaint_raw=complaint,
        interpreted_symptom=parsed.canonical_symptom,
        interpreted_phase=query_result.setup_query.parsed_phase,
        balance_direction=_balance_label(parsed.balance),
        confidence_label=confidence_label,
        readiness_label=readiness_label,
        driver_message=_driver_message(complaint, parsed.canonical_symptom, readiness_label, missing_hint, swings),
        top_swings=swings,
        next_step=next_step,
        validation_summary=_validation_summary(swings),
        clarification=clarification,
        hidden_evidence_summary=_hidden_summary(query_result, context) if include_debug_evidence else None,
        warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
    )
