from __future__ import annotations

import re

from .schema import SetupEffect


NEXT_GEN_DISABLED = {"track_bar", "truck_arm_mount", "bump_stop", "packer"}
GUARANTEE_TERMS = ("guaranteed", "always", "will fix", "universal truth")
MULTI_MAJOR_TERMS = ("and also make a major", "plus a major", "multiple major")
COUPLING_RISKS = {"low", "medium", "high"}
EXACT_VALUE_POLICIES = {"none", "small_swing", "reference_only"}


def validate_setup_knowledge(knowledge) -> list[str]:
    problems: list[str] = []
    area_ids = {area.setup_area for area in knowledge.setup_areas}
    phases = {phase.phase_id for phase in knowledge.phase_model}
    canonical_symptoms = {entry.canonical_symptom for entry in knowledge.symptom_vocabulary}
    package_ids = {package.archetype_id for package in knowledge.package_archetypes}

    for cap in knowledge.car_capabilities:
        missing_available = set(cap.available_setup_areas) - area_ids
        missing_disabled = set(cap.disabled_setup_areas) - area_ids
        if missing_available:
            problems.append(f"{cap.car_family} references unknown available setup areas: {sorted(missing_available)}")
        if missing_disabled:
            problems.append(f"{cap.car_family} references unknown disabled setup areas: {sorted(missing_disabled)}")
        if cap.car_family == "next_gen":
            if set(cap.disabled_setup_areas) != NEXT_GEN_DISABLED:
                problems.append("next_gen disabled setup areas must be track_bar, truck_arm_mount, bump_stop, packer")
            if cap.discrete_options.get("front_arb_diameter") != ["1.375", "2.000"]:
                problems.append("next_gen front ARB diameter options must be exactly 1.375 and 2.000")
            if cap.discrete_options.get("rear_arb_diameter") != ["1.375", "2.000"]:
                problems.append("next_gen rear ARB diameter options must be exactly 1.375 and 2.000")
            expected_arms = ["P1", "P2", "P3", "P4", "P5"]
            if cap.discrete_options.get("front_arb_arm") != expected_arms:
                problems.append("next_gen front ARB arm options must be P1 through P5")
            if cap.discrete_options.get("rear_arb_arm") != expected_arms:
                problems.append("next_gen rear ARB arm options must be P1 through P5")

    for phase in knowledge.phase_model:
        unknown_areas = set(phase.common_setup_areas) - area_ids
        if unknown_areas:
            problems.append(f"Phase {phase.phase_id} references unknown setup areas: {sorted(unknown_areas)}")

    for entry in knowledge.symptom_vocabulary:
        if entry.phase not in phases:
            problems.append(f"Symptom phrase {entry.phrase} references unknown phase {entry.phase}")
        if entry.canonical_symptom not in canonical_symptoms:
            problems.append(f"Symptom phrase {entry.phrase} maps to unknown canonical symptom {entry.canonical_symptom}")

    for area in knowledge.setup_areas:
        for phase in area.phases:
            if phase not in phases:
                problems.append(f"Setup area {area.setup_area} references unknown phase {phase}")
        if area.setup_area in NEXT_GEN_DISABLED:
            note = area.car_specific_notes.get("next_gen", "").lower()
            if "unavailable" not in note and "disabled" not in note:
                problems.append(f"Disabled Next Gen area {area.setup_area} needs a safe unavailable car-specific note")

    for effect in knowledge.setup_effects:
        problems.extend(_validate_effect(effect, area_ids, canonical_symptoms, package_ids))

    for req in knowledge.evidence_requirements:
        if req.setup_area not in area_ids:
            problems.append(f"Evidence requirement {req.requirement_id} references unknown setup area {req.setup_area}")
        if req.symptom not in canonical_symptoms:
            problems.append(f"Evidence requirement {req.requirement_id} references unknown symptom {req.symptom}")

    for rule in knowledge.nextgen_platform_rules:
        text = " ".join([rule.wording, *rule.do_not_say]).lower()
        wording = rule.wording.lower()
        if "measured downforce" in wording and "not measured downforce" not in wording:
            problems.append(f"Diffuser rule {rule.rule_id} claims measured downforce")
        if _contains_banned_certainty(text):
            problems.append(f"Next Gen platform rule {rule.rule_id} contains guaranteed-fix wording")

    for rule in knowledge.shock_interpretation:
        text = " ".join([rule.wording, *rule.cautions]).lower()
        if "histogram alone proves" in text or "histogram alone confirms" in text:
            problems.append(f"Shock rule {rule.rule_id} overstates histogram evidence")
        if _contains_banned_certainty(text):
            problems.append(f"Shock rule {rule.rule_id} contains guaranteed-fix wording")

    return problems


def _contains_banned_certainty(text: str) -> bool:
    if "guaranteed" in text or "will fix" in text or "universal truth" in text:
        return True
    return bool(re.search(r"(?<!not\\s)\\balways\\b", text))


def _validate_effect(
    effect: SetupEffect,
    area_ids: set[str],
    canonical_symptoms: set[str],
    package_ids: set[str],
) -> list[str]:
    problems: list[str] = []
    if effect.setup_area not in area_ids:
        problems.append(f"Effect {effect.effect_id} references unknown setup area {effect.setup_area}")
    if not effect.effect:
        problems.append(f"Effect {effect.effect_id} is missing effect text")
    if not effect.counter_effect:
        problems.append(f"Effect {effect.effect_id} is missing counter_effect text")
    if not effect.primary_effects:
        problems.append(f"Effect {effect.effect_id} is missing primary_effects")
    if not effect.counter_effects:
        problems.append(f"Effect {effect.effect_id} is missing counter_effects")
    if not effect.validation_targets:
        problems.append(f"Effect {effect.effect_id} is missing validation_targets")
    if not effect.evidence_required:
        problems.append(f"Effect {effect.effect_id} is missing evidence_required")
    if effect.exact_value_policy not in EXACT_VALUE_POLICIES:
        problems.append(f"Effect {effect.effect_id} has invalid exact_value_policy")
    if not 1 <= effect.effect_strength <= 5:
        problems.append(f"Effect {effect.effect_id} has invalid effect_strength")
    if effect.coupling_risk not in COUPLING_RISKS:
        problems.append(f"Effect {effect.effect_id} is missing coupling_risk")
    if effect.effect_strength == 5 and effect.coupling_risk != "high":
        problems.append(f"Effect {effect.effect_id} is strength 5 without high coupling risk")
    unknown_packages = set(effect.setup_package_tags) - package_ids
    if unknown_packages:
        problems.append(f"Effect {effect.effect_id} references unknown package tags: {sorted(unknown_packages)}")
    for symptom in [*effect.helps, *effect.can_hurt]:
        if symptom not in canonical_symptoms:
            problems.append(f"Effect {effect.effect_id} references unknown symptom {symptom}")
    if "next_gen" in effect.applies_to and effect.setup_area in NEXT_GEN_DISABLED:
        problems.append(f"Effect {effect.effect_id} exposes disabled Next Gen area {effect.setup_area}")
    if effect.disabled_for and not (effect.cautions or effect.avoid_when):
        problems.append(f"Disabled effect {effect.effect_id} needs an explanation or alternative caution")
    text = " ".join(
        [
            effect.effect,
            effect.counter_effect,
            effect.test_language,
            effect.driver_facing_summary,
            effect.one_change_test_template,
            *effect.primary_effects,
            *effect.counter_effects,
            *effect.cautions,
        ]
    ).lower()
    if _contains_banned_certainty(text):
        problems.append(f"Effect {effect.effect_id} contains guaranteed-fix wording")
    if "measured downforce" in text:
        problems.append(f"Effect {effect.effect_id} claims or repeats measured downforce wording")
    if any(term in text for term in MULTI_MAJOR_TERMS):
        problems.append(f"Effect {effect.effect_id} suggests multiple major changes")
    return problems
