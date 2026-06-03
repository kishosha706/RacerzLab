from __future__ import annotations

from .schema import SetupEffect


NEXT_GEN_DISABLED = {"track_bar", "truck_arm_mount", "bump_stop", "packer"}
GUARANTEE_TERMS = ("guaranteed fix", "always fixes", "will fix", "universal truth")
MULTI_MAJOR_TERMS = ("and also make a major", "plus a major", "multiple major")


def validate_setup_knowledge(knowledge) -> list[str]:
    problems: list[str] = []
    area_ids = {area.setup_area for area in knowledge.setup_areas}
    phases = {phase.phase_id for phase in knowledge.phase_model}
    canonical_symptoms = {entry.canonical_symptom for entry in knowledge.symptom_vocabulary}

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

    for area in knowledge.setup_areas:
        for phase in area.phases:
            if phase not in phases:
                problems.append(f"Setup area {area.setup_area} references unknown phase {phase}")

    for effect in knowledge.setup_effects:
        problems.extend(_validate_effect(effect, area_ids, canonical_symptoms))

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
        if any(term in text for term in GUARANTEE_TERMS):
            problems.append(f"Next Gen platform rule {rule.rule_id} contains guaranteed-fix wording")

    for rule in knowledge.shock_interpretation:
        text = " ".join([rule.wording, *rule.cautions]).lower()
        if "histogram alone proves" in text or "histogram alone confirms" in text:
            problems.append(f"Shock rule {rule.rule_id} overstates histogram evidence")
        if any(term in text for term in GUARANTEE_TERMS):
            problems.append(f"Shock rule {rule.rule_id} contains guaranteed-fix wording")

    return problems


def _validate_effect(effect: SetupEffect, area_ids: set[str], canonical_symptoms: set[str]) -> list[str]:
    problems: list[str] = []
    if effect.setup_area not in area_ids:
        problems.append(f"Effect {effect.effect_id} references unknown setup area {effect.setup_area}")
    if not effect.effect:
        problems.append(f"Effect {effect.effect_id} is missing effect text")
    if not effect.counter_effect:
        problems.append(f"Effect {effect.effect_id} is missing counter_effect text")
    if not 1 <= effect.effect_strength <= 5:
        problems.append(f"Effect {effect.effect_id} has invalid effect_strength")
    if not effect.coupling_risk:
        problems.append(f"Effect {effect.effect_id} is missing coupling_risk")
    for symptom in [*effect.helps, *effect.can_hurt]:
        if symptom not in canonical_symptoms:
            problems.append(f"Effect {effect.effect_id} references unknown symptom {symptom}")
    if "next_gen" in effect.applies_to and effect.setup_area in NEXT_GEN_DISABLED:
        problems.append(f"Effect {effect.effect_id} exposes disabled Next Gen area {effect.setup_area}")
    text = " ".join([effect.effect, effect.counter_effect, effect.test_language, *effect.cautions]).lower()
    if any(term in text for term in GUARANTEE_TERMS):
        problems.append(f"Effect {effect.effect_id} contains guaranteed-fix wording")
    if any(term in text for term in MULTI_MAJOR_TERMS):
        problems.append(f"Effect {effect.effect_id} suggests multiple major changes")
    return problems
