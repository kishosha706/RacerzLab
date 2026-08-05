from __future__ import annotations

from typing import Any

from racelab_engine.analysis.lap_eligibility import eligible_laps, find_lap, lap_ineligibility_reasons
from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS
from racelab_engine.analysis.setup_diff import setup_control_value
from racelab_engine.storage.repository import RaceLabRepository

from .dial_in_controls import GarageAction, garage_action_for_effect
from .dial_in_schema import (
    Clarification,
    DialInResponse,
    DialInSwing,
    EvidenceStrengthSignal,
    HiddenEvidenceSummary,
)
from .evidence_schema import RunEvidenceContext
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
    "ready": "Observed mechanism",
    "partially_ready": "Unverified hypothesis",
    "missing_key_evidence": "Measurement required",
}
GENERIC_COMPLAINTS = {"loose", "tight", "push", "free", "bad", "weird", "off"}
GENERIC_CLARIFICATION_QUESTION = "Where is it happening?"
GENERIC_CLARIFICATION_OPTIONS = ["Entry", "Center", "Exit", "Whole corner", "On brake", "On throttle"]


def _normalize_complaint(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _balance_label(value: str | None) -> str | None:
    return value.replace("_", " ") if value else None


def _phase_family(value: str | None) -> str | None:
    normalized = (value or "").strip().casefold().replace(" ", "_")
    aliases = {
        "brake_application": "braking",
        "threshold_braking": "braking",
        "brake_release": "entry",
        "turn_in": "entry",
        "apex_region": "center",
        "initial_throttle": "exit",
        "full_throttle_exit": "exit",
        "following_straight_carry": "exit",
        "bump": "bump_curb",
        "curb": "bump_curb",
    }
    return aliases.get(normalized, normalized) or None


def _priority_phase(value: str | None) -> str | None:
    return {
        "entry-security": "entry",
        "center-rotation": "center",
        "exit-drive": "exit",
    }.get((value or "").strip().casefold())


def _decision_context_measurement_blocker(objective: str | None, priority: str | None) -> str | None:
    normalized_objective = (objective or "race-pace").strip().casefold()
    normalized_priority = (priority or "overall-pace").strip().casefold()
    if normalized_objective in {"long-run", "tire-conservation", "driver-confidence"}:
        return (
            f"The {normalized_objective.replace('-', ' ')} objective requires its purpose-sized "
            "stint, tire, or driver-consistency measurement mission before any setup test is approved."
        )
    if normalized_priority == "tire-life":
        return "Tire-life priority requires a clean continuous stint and repeated tire-state history."
    if normalized_priority == "platform-margin":
        return (
            "Platform-margin priority requires same-position clearance, contact, and platform-stability "
            "measurements; phase time alone cannot approve a setup test."
        )
    return None


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
        return "Observed mechanism available"
    if all(item == "missing_key_evidence" for item in candidate_readiness):
        return "Need cleaner data"
    return "Hypothesis only"


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
        # A semantic match is not measurement evidence.  Never turn a candidate
        # with missing required signals into a numeric garage instruction.
        if item.readiness == "missing_key_evidence":
            continue
        # Setup presence, lap windows, track identity, and speed alone establish
        # context but do not measure the handling mechanism behind an action.
        context_only = {
            "setup_snapshot",
            "lap_windows",
            "phase",
            "selected_lap_window",
            "lap_falloff",
            "track_map",
            "track_map_zone",
            "selected_zone",
            "speed_trace",
            "compare_baseline",
            "compare_test",
            "compare_baseline_test",
        }
        if not (set(item.evidence_matched) - context_only):
            continue
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


EVIDENCE_GROUP_BY_FLAG: dict[str, tuple[str, ...]] = {
    "brake": ("brake_trace",),
    "brake_trace": ("brake_trace",),
    "diffuser_proxy": ("diffuser_proxy",),
    "front_platform": ("front_ride_height_platform", "platform_trace"),
    "platform": ("platform_trace",),
    "rear_platform": ("rear_ride_height_platform", "platform_trace"),
    "rear_scrape_scrub": ("rear_scrape_scrub",),
    "rpm": ("rpm_gear_trace",),
    "rpm_gear_trace": ("rpm_gear_trace",),
    "scrape": ("rear_scrape_scrub",),
    "shock_histogram": ("shock_histogram",),
    "shock_rms_activity": ("shock_histogram",),
    "speed_loss": ("speed_trace",),
    "speed_trace": ("speed_trace",),
    "steering": ("steering_trace",),
    "throttle": ("throttle_trace",),
    "tire_pressure": ("tire_pressure",),
    "tire_temps": ("tire_temps",),
    "tire_trend": ("tire_pressure", "tire_temps", "tire_wear"),
    "tire_wear": ("tire_wear",),
    "wear": ("tire_wear",),
    "yaw": ("yaw_trace",),
    "yaw_scrub_steering": ("rear_scrape_scrub", "yaw_trace", "steering_trace"),
}


def _candidate_source_channels(item: RankedSetupEffect, context: RunEvidenceContext) -> list[str]:
    """Return archived channels that supplied the candidate's matched evidence."""
    group_ids = {
        group_id
        for flag in item.evidence_matched
        for group_id in EVIDENCE_GROUP_BY_FLAG.get(flag, (flag,))
    }
    return list(dict.fromkeys(
        channel
        for group in context.evidence_groups
        if group.group_id in group_ids
        for channel in group.channels_present
    ))


def _build_swing(
    item: RankedSetupEffect,
    *,
    setup_values: dict[str, Any],
    supporting_event_ids_by_flag: dict[str, list[str]],
    supporting_event_ids_by_setup_key: dict[str, list[str]],
    source_channels_by_event_id: dict[str, list[str]],
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
            "observed_evidence_flags": item.observed_evidence_matched,
        }
    control_links = {
        key: set(supporting_event_ids_by_setup_key.get(key, ()))
        for key in garage_action.control_keys
    }
    control_flag_links = {
        key: {
            flag: event_ids & set(supporting_event_ids_by_flag.get(flag, ()))
            for flag in item.observed_evidence_matched
        }
        for key, event_ids in control_links.items()
    }
    candidate_mechanism_complete = (
        bool(item.observed_evidence_matched)
        and bool(control_flag_links)
        and all(
            ids
            for flag_links in control_flag_links.values()
            for ids in flag_links.values()
        )
    )
    supporting_event_ids = list(dict.fromkeys(
        event_id
        for flag_links in control_flag_links.values()
        for ids in flag_links.values()
        for event_id in ids
    )) if candidate_mechanism_complete else []
    linked_observed_flags = [
        flag
        for flag in item.observed_evidence_matched
        if all(flag_links.get(flag) for flag_links in control_flag_links.values())
    ]
    source_channels = list(dict.fromkeys(
        channel
        for event_id in supporting_event_ids
        for channel in source_channels_by_event_id.get(event_id, ())
    ))
    readiness_label = CANDIDATE_READINESS_LABELS.get(
        item.readiness, item.readiness.replace("_", " ").title(),
    )
    if item.readiness == "ready" and not candidate_mechanism_complete:
        readiness_label = "Unverified hypothesis"
    change_this = garage_action.change_this
    proposed_value_label = garage_action.proposed_value_label
    if not candidate_mechanism_complete:
        change_this = (
            f"Do not change {garage_action.garage_lever} yet; first measure whether it is linked "
            "to the selected symptom and phase."
        )
        proposed_value_label = None
    return DialInSwing(
        id=item.effect.effect_id,
        title=garage_action.title,
        change_this=change_this,
        garage_lever=garage_action.garage_lever,
        control_keys=garage_action.control_keys,
        direction_sign=garage_action.direction_sign,
        setup_area=item.effect.setup_area,
        change_size_label=garage_action.change_size_label,
        change_size_explanation=garage_action.change_size_explanation,
        influence_label=garage_action.influence_label,
        control_expectation=garage_action.control_expectation,
        control_guardrail=garage_action.control_guardrail,
        current_value_label=garage_action.current_value_label,
        proposed_value_label=proposed_value_label,
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
        readiness_label=readiness_label,
        # Validation targets describe what a future A/B test should watch. They
        # are not necessarily channels measured in the current run.
        source_channels=source_channels,
        observed_evidence_flags=linked_observed_flags,
        supporting_event_ids=supporting_event_ids,
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
    if readiness_label == "Observed mechanism available":
        return "An eligible telemetry event supports this mechanism. Confirm it with one controlled A/B test."
    if readiness_label == "Hypothesis only":
        return "The data profile can measure this, but the mechanism is not fully observed. Treat it as one test hypothesis."
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
        capability_flags=result.capability_flags,
        observed_mechanism_flags=result.observed_evidence_flags,
        supporting_event_ids=result.supporting_event_ids,
    )


def _evidence_strength_signal(
    context: RunEvidenceContext,
    *,
    result=None,
    selected: list[RankedSetupEffect] | None = None,
    swings: list[DialInSwing] | None = None,
    blocked_reason: str | None = None,
) -> EvidenceStrengthSignal:
    capability_flags = context.evidence_flags
    context_only_flags = {
        "setup_snapshot",
        "lap_windows",
        "phase",
        "selected_lap_window",
        "lap_falloff",
        "track_map",
        "track_map_zone",
        "selected_zone",
        "compare_baseline",
        "compare_test",
        "compare_baseline_test",
    }
    measurement_capability = bool(set(capability_flags) - context_only_flags)
    observed_flags = result.observed_evidence_flags if result is not None else []
    event_ids = result.supporting_event_ids if result is not None else []
    if blocked_reason:
        return EvidenceStrengthSignal(
            level="unavailable",
            readiness="blocked",
            setup_test_ready=False,
            capability_flags=capability_flags,
            observed_mechanism_flags=observed_flags,
            supporting_event_ids=event_ids,
            reason=blocked_reason,
        )
    if not observed_flags and not measurement_capability:
        return EvidenceStrengthSignal(
            level="unavailable",
            readiness="blocked",
            setup_test_ready=False,
            capability_flags=capability_flags,
            reason="No relevant telemetry measurement capability is available for this setup hypothesis.",
        )
    if not observed_flags:
        return EvidenceStrengthSignal(
            level="capability_only",
            readiness="measurement_required",
            setup_test_ready=False,
            capability_flags=capability_flags,
            reason=(
                "The run can measure relevant channels, but no eligible tuning event observed "
                "the handling mechanism. Any listed change is an unverified test hypothesis."
            ),
        )
    ready = bool(selected) and bool(swings) and any(
        swing.readiness_label == "Observed mechanism" and bool(swing.supporting_event_ids)
        for swing in swings
    )
    return EvidenceStrengthSignal(
        level="observed_mechanism",
        readiness="test_hypothesis_ready" if ready else "measurement_required",
        setup_test_ready=ready,
        capability_flags=capability_flags,
        observed_mechanism_flags=observed_flags,
        supporting_event_ids=event_ids,
        reason=(
            "Eligible telemetry events support a one-change setup test; a controlled A/B result is still required."
            if ready
            else "Eligible events were observed, but none supplies the mechanism evidence required by a listed setup test."
        ),
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
    selected_lap: int | None = None,
    selected_zone_start_pct: float | None = None,
    selected_zone_end_pct: float | None = None,
    selected_phase: str | None = None,
    objective: str | None = None,
    priority: str | None = None,
    limit: int = 3,
    include_debug_evidence: bool = False,
) -> DialInResponse:
    selected_zone: tuple[float, float] | None = None
    if selected_zone_start_pct is not None or selected_zone_end_pct is not None:
        if selected_zone_start_pct is None or selected_zone_end_pct is None:
            raise ValueError("A selected Dial-In zone requires both start and end track positions.")
        if not 0.0 <= selected_zone_start_pct < selected_zone_end_pct <= 100.0:
            raise ValueError("Selected Dial-In zone must satisfy 0 <= start < end <= 100.")
        selected_zone = (selected_zone_start_pct, selected_zone_end_pct)
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
        blocker = "The complaint could not be mapped to a supported setup symptom."
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            confidence_label=_confidence_label(complaint, needs_clarification=False, supported=False),
            readiness_label="Need cleaner data",
            driver_message=f'I could not map "{complaint}" to a supported setup complaint yet. Try a cleaner run or narrow the complaint.',
            next_step="Try naming the phase, trigger, or main behavior first.",
            clarification=Clarification(needed=False),
            warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
            evidence_state="unavailable",
            blocker_reasons=[blocker],
            evidence_strength=_evidence_strength_signal(context, blocked_reason=blocker),
        )

    normalized_complaint = _normalize_complaint(complaint)
    priority_phase = _priority_phase(priority)
    decision_phase = selected_phase or priority_phase
    generic_balance = {
        "loose": "loose",
        "free": "loose",
        "tight": "tight",
        "push": "tight",
    }.get(normalized_complaint)
    if generic_balance and decision_phase:
        phase_phrase = {
            "entry": "in",
            "center": "center",
            "exit": "off",
        }.get(_phase_family(decision_phase))
        if phase_phrase:
            parsed = parse_symptom(f"{generic_balance} {phase_phrase}", knowledge)
    if selected_phase and priority_phase and _phase_family(selected_phase) != _phase_family(priority_phase):
        blocker = (
            f'The selected phase is {selected_phase.replace("_", " ")}, but the driver priority requires '
            f'{priority_phase.replace("_", " ")}. Resolve that conflict before choosing a setup test.'
        )
    elif decision_phase and _phase_family(decision_phase) != _phase_family(parsed.phase):
        blocker = (
            f'The complaint maps to {parsed.phase.replace("_", " ")}, but the requested phase is '
            f'{decision_phase.replace("_", " ")}. Resolve that conflict before choosing a setup test.'
        )
    else:
        blocker = None
    if blocker:
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            interpreted_symptom=parsed.canonical_symptom,
            interpreted_phase=parsed.phase,
            balance_direction=_balance_label(parsed.balance),
            confidence_label="Needs clarification",
            readiness_label="Need cleaner data",
            driver_message=blocker,
            next_step="Change the selected phase or describe the handling problem in that phase.",
            clarification=Clarification(needed=True, question=blocker, options=[]),
            warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
            evidence_state="blocked_by_context",
            blocker_reasons=[blocker],
            evidence_strength=_evidence_strength_signal(context, blocked_reason=blocker),
        )

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
        blocker = "A handling-phase clarification is required before selecting a setup test."
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
            blocker_reasons=[blocker],
            evidence_strength=_evidence_strength_signal(context, blocked_reason=blocker),
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
                    selected_lap=selected_lap,
                    selected_zone=selected_zone,
                    phase=decision_phase,
                    objective=objective,
                    priority=priority,
                    limit=max(limit, 1),
                ),
                context,
            )
            if include_debug_evidence
            else None,
        )

    if context_blocker := _decision_context_measurement_blocker(objective, priority):
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            interpreted_symptom=parsed.canonical_symptom,
            interpreted_phase=decision_phase or parsed.phase,
            balance_direction=_balance_label(parsed.balance),
            confidence_label=confidence_label,
            readiness_label="Need objective-specific evidence",
            driver_message=context_blocker,
            next_step="Run the server-generated measurement mission before changing the setup.",
            clarification=clarification,
            warnings=_driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence),
            evidence_state="blocked_by_context",
            blocker_reasons=[context_blocker],
            evidence_strength=_evidence_strength_signal(context, blocked_reason=context_blocker),
        )

    eligibility_block = _dial_in_eligibility_block(run_id, selected_lap=selected_lap)
    if eligibility_block is not None:
        warnings = _driver_warnings(context.warnings, include_debug_evidence=include_debug_evidence)
        warnings.append(eligibility_block)
        return DialInResponse(
            run_id=run_id,
            complaint_raw=complaint,
            interpreted_symptom=parsed.canonical_symptom,
            interpreted_phase=parsed.phase,
            balance_direction=_balance_label(parsed.balance),
            confidence_label=confidence_label,
            readiness_label="Need cleaner data",
            driver_message=(
                f"You said {complaint}. I'm reading that as {parsed.canonical_symptom.replace('_', ' ')}. "
                "The telemetry observations remain available, but this lap selection cannot support an exact setup change."
            ),
            next_step="Record or select one clean, complete flying lap, then test one small setup change.",
            clarification=clarification,
            warnings=warnings,
            evidence_state="blocked_by_context",
            blocker_reasons=[eligibility_block],
            evidence_strength=_evidence_strength_signal(context, blocked_reason=eligibility_block),
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
        selected_lap=selected_lap,
        selected_zone=selected_zone,
        phase=decision_phase,
        objective=objective,
        priority=priority,
        limit=max(limit * 4, limit),
    )
    selected = _filter_swings(query_result.setup_query.candidate_effects, limit)
    setup_values = _driver_setup_values(run_id)
    swings = [
        _build_swing(
            item,
            setup_values=setup_values,
            supporting_event_ids_by_flag=query_result.supporting_event_ids_by_flag,
            supporting_event_ids_by_setup_key=query_result.supporting_event_ids_by_setup_key,
            source_channels_by_event_id=query_result.source_channels_by_event_id,
            include_debug_evidence=include_debug_evidence,
        )
        for item in selected
    ]

    missing_hint = _evidence_status_hint(
        context.warnings,
        baseline_run_id=baseline_run_id if context.unavailable_reasons.get("compare_baseline") else None,
        test_run_id=test_run_id if context.unavailable_reasons.get("compare_test") else None,
    )
    linked_readiness = [
        "ready" if swing.readiness_label == "Observed mechanism" else "partially_ready"
        for swing in swings
    ]
    readiness_label = _readiness_label(linked_readiness, missing_hint=missing_hint)
    next_step = "Change one test plan, match fuel and tire age, then compare eligible laps by track position."
    if readiness_label == "Need cleaner data":
        next_step = "Data's noisy here. Try a cleaner run or narrow the complaint."
    if missing_hint:
        next_step = f"{next_step} {missing_hint}"

    blocker_reasons = []
    evidence_state = "needs_confirmation"
    if not swings:
        evidence_state = "unavailable"
        blocker_reasons.append(
            "Required telemetry evidence is missing for every supported setup action; exact changes are suppressed."
        )

    return DialInResponse(
        run_id=run_id,
        complaint_raw=complaint,
        interpreted_symptom=parsed.canonical_symptom,
        interpreted_phase=decision_phase or query_result.setup_query.parsed_phase,
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
        source_channels=list(dict.fromkeys(
            channel for swing in swings for channel in swing.source_channels
        )),
        evidence_state=evidence_state,
        blocker_reasons=blocker_reasons,
        evidence_strength=_evidence_strength_signal(
            context, result=query_result, selected=selected, swings=swings,
        ),
    )


def _dial_in_eligibility_block(run_id: str, *, selected_lap: int | None) -> str | None:
    repository = RaceLabRepository()
    overview = repository.get_overview(run_id)
    if overview is None:
        return "Run overview is unavailable; exact setup actions are suppressed."
    if repository.get_setup_snapshot(run_id) is None:
        return (
            "The current setup snapshot is unavailable. Capture the garage setup before requesting "
            "an exact Dial-In action so the test stays linked to a known baseline."
        )
    eligible_numbers = {lap.lap_number for lap in eligible_laps(overview.laps)}
    if not eligible_numbers:
        return (
            "No eligible flying laps are available. Partial, pit, reset, cooldown, wreck, and other "
            "junk laps cannot drive an exact Dial-In action."
        )
    if selected_lap is None:
        return None
    summary = find_lap(overview.laps, selected_lap)
    if summary is not None and selected_lap in eligible_numbers:
        return None
    reasons = ["Lap summary unavailable"] if summary is None else lap_ineligibility_reasons(summary)
    return (
        f"Selected lap {selected_lap} is not eligible for Dial-In tuning "
        f"({', '.join(reasons) or 'setup-evidence gate failed'}). Exact setup actions are suppressed."
    )
