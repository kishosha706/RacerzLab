from __future__ import annotations

from dataclasses import dataclass
import re

from .display_labels import TARGET_LABELS, format_driver_targets, format_target_label, format_target_list
from .loader import SetupKnowledge, load_setup_knowledge
from .schema import SetupEffect, SymptomVocabularyEntry


RISK_WEIGHT = {"low": 0.35, "medium": 0.2, "high": 0.0}
LEGACY_DISABLED_AREAS = {"track_bar", "truck_arm_mount", "bump_stop", "packer"}
EVIDENCE_ALIASES = {
    "platform_trace": {"platform", "front_platform", "rear_platform", "diffuser_proxy", "ride_height_trace"},
    "platform": {"platform", "front_platform", "rear_platform", "diffuser_proxy"},
    "tire_temps": {"tire_temp", "tire_trend", "tire_temps"},
    "tire_pressure": {"pressure_gain", "tire_pressure_gain", "tire_trend"},
    "tire_wear": {"wear"},
    "tires": {"tire_temp", "tire_trend", "tire_temps"},
    "shocks": {"shock_histogram"},
    "lap_windows": {"phase", "selected_lap_window", "lap_falloff"},
    "front_ride_height_platform": {"front_platform", "cfs_front_feed"},
    "rear_ride_height_platform": {"rear_platform"},
    "rear_scrape_scrub": {"rear_scrape_scrub", "scrape", "yaw_scrub_steering"},
    "driver_input": {"driver_inputs", "throttle", "steering", "yaw", "brake_trace"},
    "brake_trace": {"brake_trace"},
    "throttle_trace": {"throttle", "throttle_pickup"},
    "steering_trace": {"steering"},
    "yaw_trace": {"yaw"},
    "rpm_gear_trace": {"rpm", "rpm_gear_limiter"},
    "track_map": {"track_map_zone", "selected_zone"},
    "compare_baseline": {"compare_baseline_test"},
    "compare_test": {"compare_baseline_test"},
}
@dataclass(frozen=True)
class RankedSetupEffect:
    effect: SetupEffect
    score: float
    evidence_matched: list[str]
    missing_evidence: list[str]
    readiness: str
    ranking_reasons: list[str]
    evidence_missing: list[str]
    one_change_test_plan: str
    warning: str | None = None


@dataclass(frozen=True)
class SetupQueryResult:
    parsed_symptom: SymptomVocabularyEntry
    parsed_phase: str
    ambiguity: bool
    candidate_effects: list[RankedSetupEffect]
    ranking_reasons: dict[str, list[str]]
    evidence_missing: dict[str, list[str]]
    disabled_by_car_capability: list[SetupEffect]
    disabled_effects_due_to_car: list[SetupEffect]
    disabled_setup_areas: list[str]
    one_change_test_plan: list[str]
    warnings: list[str]
    clarification_question: str | None
    package_archetype: str | None = None
    track_family: str | None = None


def parse_symptom(raw_symptom: str, knowledge: SetupKnowledge) -> SymptomVocabularyEntry:
    normalized = " ".join(raw_symptom.lower().strip().split())
    entries = knowledge.symptom_vocabulary
    for entry in entries:
        if normalized == entry.phrase.lower():
            return entry
    for entry in entries:
        phrase = entry.phrase.lower()
        if phrase in normalized or normalized in phrase:
            return entry
    if "loose" in normalized or "free" in normalized:
        if "off" in normalized or "throttle" in normalized:
            target = "loose off"
        elif "in" in normalized or "brake" in normalized:
            target = "loose in"
        elif "center" in normalized or "middle" in normalized or "rolling" in normalized:
            target = "loose center"
        else:
            target = "loose"
        return next(entry for entry in entries if entry.phrase == target)
    if "tight" in normalized or "push" in normalized:
        if "off" in normalized or "throttle" in normalized:
            target = "tight off"
        elif "in" in normalized or "apex" in normalized:
            target = "tight in"
        elif "center" in normalized or "middle" in normalized or "rolling" in normalized:
            target = "tight center"
        else:
            target = "tight"
        return next(entry for entry in entries if entry.phrase == target)
    if any(term in normalized for term in ["straight", "draggy", "pulls slow"]):
        return next(entry for entry in entries if entry.phrase == "draggy")
    if any(term in normalized for term in ["bottoming", "scrape", "hitting"]):
        return next(entry for entry in entries if entry.phrase == "scrapes")
    raise ValueError(f"No setup symptom vocabulary match for: {raw_symptom!r}")


def _applies_to_car(effect: SetupEffect, car_family: str, disabled_areas: set[str]) -> bool:
    if effect.setup_area in disabled_areas or car_family in effect.disabled_for:
        return False
    if car_family == "unknown":
        return "all" in effect.applies_to
    return "all" in effect.applies_to or car_family in effect.applies_to


def _expand_evidence(evidence: list[str] | None) -> set[str]:
    expanded: set[str] = set()
    for item in evidence or []:
        normalized = item.strip()
        if not normalized:
            continue
        expanded.add(normalized)
        expanded.update(EVIDENCE_ALIASES.get(normalized, set()))
    return expanded


def _key_required_evidence(effect: SetupEffect) -> list[str]:
    message = effect.evidence_missing_message.lower()
    hinted = [
        token
        for token in re.findall(r"[a-z0-9_]+", message)
        if token in effect.evidence_required
    ]
    if hinted:
        return list(dict.fromkeys(hinted))
    prioritized = [item for item in effect.evidence_priority if item in effect.evidence_required]
    if prioritized:
        return [prioritized[0]]
    return effect.evidence_required[:1]


def _readiness(effect: SetupEffect, matched: list[str]) -> str:
    required = effect.evidence_required
    if not required:
        return "ready"
    matched_set = set(matched)
    key_required = _key_required_evidence(effect)
    if any(item not in matched_set for item in key_required):
        return "missing_key_evidence"
    if len(matched) == len(required):
        return "ready"
    if matched:
        return "partially_ready"
    return "missing_key_evidence"


def _format_reason(template: str, *, parsed: SymptomVocabularyEntry, phase: str, effect: SetupEffect, readiness: str, package_archetype: str | None) -> str:
    return (
        f"Matches {parsed.canonical_symptom} in {phase}; "
        f"strength {effect.effect_strength}, risk {effect.coupling_risk}, evidence {readiness}"
    )


def _one_change_test(effect: SetupEffect) -> str:
    if effect.test_language:
        lower = effect.test_language.lower()
        if "one" in lower or "single" in lower or "package test" in lower:
            return format_driver_targets(effect.test_language)
        return format_driver_targets(f"Try one swing: {effect.test_language}")
    validate = format_target_list(effect.validation_targets)
    watch = format_target_list(effect.watch_for_targets) if effect.watch_for_targets else "phase balance"
    if effect.exact_value_policy == "reference_only":
        return (
            f"This is a package-level lever. Test only one package change: {effect.direction}. "
            f"Effect: {effect.effect} Counter-effect: {effect.counter_effect} "
            f"Watch: {watch}. Validate: {validate}."
        )
    return (
        f"Try one small swing: {effect.direction}. Effect: {effect.effect} "
        f"Counter-effect: {effect.counter_effect} Watch: {watch}. Validate: {validate}."
    )


def _score_effect(
    effect: SetupEffect,
    parsed: SymptomVocabularyEntry,
    phase: str | None,
    evidence: set[str],
    package_archetype: str | None,
    track_family: str | None,
) -> tuple[float, list[str], list[str], str, list[str], list[str]]:
    score = float(effect.effect_strength)
    reasons: list[str] = []
    warnings: list[str] = []
    if parsed.canonical_symptom in effect.helps:
        score += 8.0
        reasons.append(f"direct symptom match: {parsed.canonical_symptom}")
    if any(item in effect.helps for item in parsed.possible_secondary):
        score += 1.5
        reasons.append("matches secondary symptom context")
    active_phase = phase or parsed.phase
    if active_phase in effect.driver_phrase or active_phase in effect.helps_phases:
        score += 1.0
        reasons.append(f"phase match: {active_phase}")
    if parsed.canonical_symptom in effect.can_hurt:
        score -= 6.0
        warnings.append(f"avoid conflict: can hurt {parsed.canonical_symptom}")
    if active_phase in effect.can_hurt_phases and parsed.canonical_symptom not in effect.helps:
        score -= 0.5
    if package_archetype:
        if package_archetype in effect.setup_package_tags:
            score += 1.2
            reasons.append(f"package match: {package_archetype}")
        else:
            score -= 0.3
    if track_family:
        if track_family in effect.track_family_tags:
            score += 0.6
            reasons.append(f"track-family match: {track_family}")
        elif effect.track_family_tags:
            score -= 0.2
    score += RISK_WEIGHT.get(effect.coupling_risk, 0.0)
    matched = sorted(set(effect.evidence_required) & evidence)
    missing = [item for item in effect.evidence_required if item not in evidence]
    readiness = _readiness(effect, matched)
    if readiness == "ready":
        score += 1.0
        reasons.append("evidence ready")
    elif readiness == "partially_ready":
        score += 0.25
        score -= min(len(missing), 3) * 0.15
        reasons.append("partially ready evidence")
    else:
        score -= 0.9
        warnings.append(effect.evidence_missing_message)
        reasons.append("missing key evidence")
    if any(condition in parsed.canonical_symptom for condition in effect.avoid_when):
        score -= 1.0
    return score, matched, missing, readiness, reasons, warnings


def query_setup_knowledge(
    *,
    car_family: str,
    symptom: str,
    phase: str | None = None,
    track_family: str | None = None,
    package_archetype: str | None = None,
    evidence: list[str] | None = None,
    limit: int = 5,
    knowledge: SetupKnowledge | None = None,
) -> SetupQueryResult:
    knowledge = knowledge or load_setup_knowledge()
    capabilities = knowledge.car_capability_by_family.get(car_family)
    if capabilities is None and car_family != "unknown":
        raise ValueError(f"Unknown car family: {car_family}")
    if package_archetype and package_archetype not in {item.archetype_id for item in knowledge.package_archetypes}:
        raise ValueError(f"Unknown package archetype: {package_archetype}")
    parsed = parse_symptom(symptom, knowledge)
    parsed_phase = phase or parsed.phase
    evidence_set = _expand_evidence(evidence)
    if capabilities is None:
        disabled_setup_areas = sorted(LEGACY_DISABLED_AREAS)
        disabled_areas = set(disabled_setup_areas)
    else:
        disabled_setup_areas = capabilities.disabled_setup_areas
        disabled_areas = set(disabled_setup_areas)

    ranked: list[RankedSetupEffect] = []
    disabled: list[SetupEffect] = []
    for effect in knowledge.setup_effects:
        if not _applies_to_car(effect, car_family, disabled_areas):
            if effect.setup_area in disabled_areas or car_family in effect.disabled_for:
                disabled.append(effect)
            continue
        score, matched, missing, readiness, reasons, warnings = _score_effect(
            effect,
            parsed,
            phase,
            evidence_set,
            package_archetype,
            track_family,
        )
        if score >= 4.0:
            ranked.append(
                RankedSetupEffect(
                    effect=effect,
                    score=score,
                    evidence_matched=matched,
                    missing_evidence=missing,
                    readiness=readiness,
                    ranking_reasons=[
                        _format_reason(
                            effect.why_ranked_template,
                            parsed=parsed,
                            phase=parsed_phase,
                            effect=effect,
                            readiness=readiness,
                            package_archetype=package_archetype,
                        ),
                        *reasons,
                    ],
                    evidence_missing=[effect.evidence_missing_message] if readiness == "missing_key_evidence" else [f"Missing evidence: {item}" for item in missing],
                    one_change_test_plan=_one_change_test(effect),
                    warning="; ".join(warnings) if warnings else None,
                )
            )

    ranked.sort(key=lambda item: (-item.score, -item.effect.effect_strength, item.effect.coupling_risk, item.effect.effect_id))
    candidates = _diversify_candidates(ranked, limit)
    ambiguity = parsed.clarification_question is not None
    return SetupQueryResult(
        parsed_symptom=parsed,
        parsed_phase=parsed_phase,
        ambiguity=ambiguity,
        candidate_effects=candidates,
        ranking_reasons={item.effect.effect_id: item.ranking_reasons for item in candidates},
        evidence_missing={item.effect.effect_id: item.evidence_missing for item in candidates if item.missing_evidence},
        disabled_by_car_capability=disabled,
        disabled_effects_due_to_car=disabled,
        disabled_setup_areas=disabled_setup_areas,
        one_change_test_plan=[item.one_change_test_plan for item in candidates],
        warnings=[item.warning for item in candidates if item.warning],
        clarification_question=parsed.clarification_question,
        package_archetype=package_archetype,
        track_family=track_family,
    )


def _diversify_candidates(ranked: list[RankedSetupEffect], limit: int) -> list[RankedSetupEffect]:
    selected: list[RankedSetupEffect] = []
    seen_areas: set[str] = set()
    for item in ranked:
        if len(selected) >= limit:
            break
        if item.effect.setup_area in seen_areas:
            continue
        selected.append(item)
        seen_areas.add(item.effect.setup_area)
    if len(selected) >= limit:
        return selected
    selected_ids = {item.effect.effect_id for item in selected}
    for item in ranked:
        if len(selected) >= limit:
            break
        if item.effect.effect_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.effect.effect_id)
    return selected


def query_result_to_dict(result: SetupQueryResult) -> dict:
    return {
        "parsed_symptom": result.parsed_symptom.model_dump(),
        "parsed_phase": result.parsed_phase,
        "confidence": result.parsed_symptom.confidence_prior,
        "ambiguity": result.ambiguity,
        "clarification_question": result.clarification_question,
        "package_archetype": result.package_archetype,
        "track_family": result.track_family,
        "candidates": [
        {
            "effect_id": item.effect.effect_id,
            "setup_area": item.effect.setup_area,
            "direction": item.effect.direction,
            "strength": item.effect.effect_strength,
            "risk": item.effect.coupling_risk,
            "readiness": item.readiness,
            "score": round(item.score, 3),
            "effect": item.effect.effect,
            "counter_effect": item.effect.counter_effect,
            "why_ranked": item.ranking_reasons,
            "evidence_present": item.evidence_matched,
            "evidence_missing": item.missing_evidence,
            "one_change_test": item.one_change_test_plan,
            "validate_with": item.effect.validation_targets,
            "validate_with_labels": [format_target_label(target) for target in item.effect.validation_targets],
            "watch_for": item.effect.watch_for_targets,
            "watch_for_labels": [format_target_label(target) for target in item.effect.watch_for_targets],
            "avoid_when": item.effect.avoid_when,
        }
        for item in result.candidate_effects
        ],
        "disabled_by_capability": [
            {"effect_id": effect.effect_id, "setup_area": effect.setup_area, "direction": effect.direction}
            for effect in result.disabled_by_car_capability
        ],
        "disabled_setup_areas": result.disabled_setup_areas,
        "warnings": result.warnings,
    }
