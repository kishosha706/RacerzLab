from __future__ import annotations

from dataclasses import dataclass
import re

from .evidence_schema import MatcherReadiness
from .dial_in_controls import control_keys_for_effect
from .display_labels import format_driver_targets, format_target_label, format_target_list
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

# These inputs establish run identity, coverage, or test context.  They are
# necessary, but they do not show that the handling mechanism behind a setup
# change was actually observed in telemetry.
CONTEXT_ONLY_EVIDENCE = {
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


def _direction_sign(direction: str) -> int:
    normalized = direction.lower()
    positive_terms = ("increase", "add ", "raise", "higher", "shorter")
    negative_terms = ("reduce", "lower", "decrease", "taller")
    if any(term in normalized for term in positive_terms):
        return 1
    if any(term in normalized for term in negative_terms):
        return -1
    return 0
@dataclass(frozen=True)
class RankedSetupEffect:
    effect: SetupEffect
    score: float
    evidence_matched: list[str]
    observed_evidence_matched: list[str]
    missing_evidence: list[str]
    readiness: MatcherReadiness
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
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    entries = knowledge.symptom_vocabulary
    if tokens & {"not", "no"} or any(term in normalized for term in ("isn't", "isnt", "doesn't", "doesnt")):
        raise ValueError("Negated handling descriptions require clarification before setup matching.")
    for entry in entries:
        if normalized == entry.phrase.lower():
            return entry
    loose_words = {"loose", "free"}
    tight_words = {"tight", "push", "plowing"}
    if tokens & loose_words and tokens & tight_words:
        raise ValueError("Complaint contains conflicting loose and tight balance descriptions.")
    # Resolve a generic balance word with an explicit driver phase before the
    # broader phrase matcher can fall back to the generic clarifying entry.
    if "loose" in normalized or "free" in normalized:
        if tokens & {"off", "throttle", "exit"}:
            return next(entry for entry in entries if entry.phrase == "loose off")
        if tokens & {"in", "brake", "entry"}:
            return next(entry for entry in entries if entry.phrase == "loose in")
        if tokens & {"center", "middle", "rolling"}:
            return next(entry for entry in entries if entry.phrase == "loose center")
    if "tight" in normalized or "push" in normalized:
        if tokens & {"off", "throttle", "exit"}:
            return next(entry for entry in entries if entry.phrase == "tight off")
        if tokens & {"in", "brake", "entry"}:
            return next(entry for entry in entries if entry.phrase == "tight in")
        if tokens & {"center", "middle", "rolling"}:
            return next(entry for entry in entries if entry.phrase == "tight center")
    phrase_matches = [
        entry
        for entry in entries
        if re.search(rf"(?<![a-z0-9]){re.escape(entry.phrase.lower())}(?![a-z0-9])", normalized)
    ]
    if phrase_matches:
        # Prefer the most specific complete phrase. Never let a fragment such
        # as "in", "off", or "rear" select the first vocabulary row.
        return max(phrase_matches, key=lambda entry: (len(entry.phrase.split()), len(entry.phrase)))
    if "loose" in normalized or "free" in normalized:
        if tokens & {"off", "throttle", "exit"}:
            target = "loose off"
        elif tokens & {"in", "brake", "entry"}:
            target = "loose in"
        elif tokens & {"center", "middle", "rolling"}:
            target = "loose center"
        else:
            target = "loose"
        return next(entry for entry in entries if entry.phrase == target)
    if "tight" in normalized or "push" in normalized:
        if tokens & {"off", "throttle", "exit"}:
            target = "tight off"
        elif tokens & {"in", "brake", "entry"}:
            target = "tight in"
        elif tokens & {"center", "middle", "rolling", "apex"}:
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


def _readiness(effect: SetupEffect, matched: list[str]) -> MatcherReadiness:
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
    observed_evidence: set[str] | None,
    package_archetype: str | None,
    track_family: str | None,
) -> tuple[float, list[str], list[str], list[str], MatcherReadiness, list[str], list[str]]:
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
    observed_matched = sorted(set(effect.evidence_required) & (observed_evidence or set()))
    if observed_evidence is not None:
        mechanism_requirements = set(effect.evidence_required) - CONTEXT_ONLY_EVIDENCE
        observed_mechanisms = mechanism_requirements & set(observed_matched)
        mechanism_observed = bool(mechanism_requirements) and mechanism_requirements <= observed_mechanisms
        # Channel and setup availability can make a hypothesis testable, but it
        # cannot make it evidence-ready.  A qualifying telemetry event must
        # observe every mechanism input required by this candidate. Partial
        # observed coverage remains a hypothesis, never an exact test authority.
        if readiness == "ready" and not mechanism_observed:
            readiness = "partially_ready"
            reasons.append("measurement capability available; handling mechanism not observed")
            warnings.append("Telemetry channels are available, but no eligible event observed this mechanism.")
        elif mechanism_observed:
            reasons.append(f"observed mechanism evidence: {', '.join(observed_matched)}")
        elif observed_mechanisms:
            reasons.append(
                "partial observed mechanism evidence: "
                + ", ".join(sorted(observed_mechanisms))
            )
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
    return score, matched, observed_matched, missing, readiness, reasons, warnings


def query_setup_knowledge(
    *,
    car_family: str,
    symptom: str,
    phase: str | None = None,
    track_family: str | None = None,
    package_archetype: str | None = None,
    evidence: list[str] | None = None,
    observed_evidence: list[str] | None = None,
    limit: int = 5,
    knowledge: SetupKnowledge | None = None,
    learning_biases: dict[tuple[str, int], dict[str, object]] | None = None,
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
    # Observations are already translated into explicit mechanism flags by the
    # event adapter. Capability aliases are intentionally not expanded here:
    # a generic driver-input or platform observation must not manufacture a
    # brake, front-platform, or rear-platform mechanism.
    observed_evidence_set = None if observed_evidence is None else {
        item.strip() for item in observed_evidence if item.strip()
    }
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
        score, matched, observed_matched, missing, readiness, reasons, warnings = _score_effect(
            effect,
            parsed,
            phase,
            evidence_set,
            observed_evidence_set,
            package_archetype,
            track_family,
        )
        direction_sign = _direction_sign(effect.direction)
        control_keys = control_keys_for_effect(effect.effect_id)
        learned = (
            (learning_biases or {}).get((control_keys[0], direction_sign))
            if direction_sign and len(control_keys) == 1
            else None
        )
        if learned:
            magnitude_counts = learned.get("magnitude_counts", {})
            outcomes_by_magnitude = learned.get("weighted_outcome_by_magnitude", {})
            count = int(magnitude_counts.get("small", 0)) if isinstance(magnitude_counts, dict) else 0
            outcome = (
                float(outcomes_by_magnitude.get("small", 0.0))
                if isinstance(outcomes_by_magnitude, dict)
                else 0.0
            )
            if count < 3:
                learned = None
        if learned:
            # Exact-context controlled history outranks generic guide priors.
            # Repeated negative local evidence blocks this direction; repeated
            # positive evidence receives a material but bounded lift.
            if count >= 3 and outcome <= -0.5:
                reasons.append(
                    f"blocked by personal setup memory: {count} exact-context controlled tests, "
                    f"directional score {outcome:+.2f}"
                )
                continue
            adjustment = max(-2.0, min(3.0, outcome * 3.0))
            score += adjustment
            reasons.append(
                f"personal setup memory: {count} controlled tests, directional score {outcome:+.2f}"
            )
        if score >= 4.0:
            ranked.append(
                RankedSetupEffect(
                    effect=effect,
                    score=score,
                    evidence_matched=matched,
                    observed_evidence_matched=observed_matched,
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
            "observed_evidence_present": item.observed_evidence_matched,
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
