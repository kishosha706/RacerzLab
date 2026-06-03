from __future__ import annotations

from dataclasses import dataclass

from .loader import SetupKnowledge, load_setup_knowledge
from .schema import SetupEffect, SymptomVocabularyEntry


RISK_WEIGHT = {"low": 0.3, "medium": 0.2, "medium/high": 0.1, "high": 0.0}


@dataclass(frozen=True)
class RankedSetupEffect:
    effect: SetupEffect
    score: float
    evidence_matched: list[str]
    missing_evidence: list[str]


@dataclass(frozen=True)
class SetupQueryResult:
    parsed_symptom: SymptomVocabularyEntry
    candidate_effects: list[RankedSetupEffect]
    disabled_effects_due_to_car: list[SetupEffect]
    disabled_setup_areas: list[str]
    clarification_question: str | None


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
    raise ValueError(f"No setup symptom vocabulary match for: {raw_symptom!r}")


def _applies_to_car(effect: SetupEffect, car_family: str, disabled_areas: set[str]) -> bool:
    if effect.setup_area in disabled_areas or car_family in effect.disabled_for:
        return False
    return "all" in effect.applies_to or car_family in effect.applies_to


def _score_effect(
    effect: SetupEffect,
    parsed: SymptomVocabularyEntry,
    phase: str | None,
    evidence: set[str],
) -> tuple[float, list[str], list[str]]:
    score = float(effect.effect_strength)
    if parsed.canonical_symptom in effect.helps:
        score += 8.0
    if any(item in effect.helps for item in parsed.possible_secondary):
        score += 1.5
    if parsed.phase in effect.driver_phrase or parsed.phase in effect.validation_targets:
        score += 1.0
    if phase and phase in effect.driver_phrase:
        score += 1.0
    if parsed.canonical_symptom in effect.can_hurt:
        score -= 6.0
    score += RISK_WEIGHT.get(effect.coupling_risk, 0.0)
    matched = sorted(set(effect.evidence_required) & evidence)
    missing = [item for item in effect.evidence_required if item not in evidence]
    score += min(len(matched), 3) * 0.2
    return score, matched, missing


def query_setup_knowledge(
    *,
    car_family: str,
    symptom: str,
    phase: str | None = None,
    evidence: list[str] | None = None,
    limit: int = 5,
    knowledge: SetupKnowledge | None = None,
) -> SetupQueryResult:
    knowledge = knowledge or load_setup_knowledge()
    capabilities = knowledge.car_capability_by_family.get(car_family)
    if capabilities is None:
        raise ValueError(f"Unknown car family: {car_family}")
    parsed = parse_symptom(symptom, knowledge)
    evidence_set = {item.strip() for item in evidence or [] if item.strip()}
    disabled_areas = set(capabilities.disabled_setup_areas)

    ranked: list[RankedSetupEffect] = []
    disabled: list[SetupEffect] = []
    for effect in knowledge.setup_effects:
        if not _applies_to_car(effect, car_family, disabled_areas):
            if effect.setup_area in disabled_areas or car_family in effect.disabled_for:
                disabled.append(effect)
            continue
        score, matched, missing = _score_effect(effect, parsed, phase, evidence_set)
        if score >= 4.0:
            ranked.append(RankedSetupEffect(effect, score, matched, missing))

    ranked.sort(key=lambda item: (-item.score, -item.effect.effect_strength, item.effect.coupling_risk, item.effect.effect_id))
    return SetupQueryResult(
        parsed_symptom=parsed,
        candidate_effects=ranked[:limit],
        disabled_effects_due_to_car=disabled,
        disabled_setup_areas=capabilities.disabled_setup_areas,
        clarification_question=parsed.clarification_question,
    )
