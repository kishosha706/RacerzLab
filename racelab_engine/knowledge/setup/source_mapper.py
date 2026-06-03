from __future__ import annotations

from dataclasses import dataclass

from .loader import SetupKnowledge, load_setup_knowledge
from .schema import GuidePrinciple, GuideSetupMapping, GuideTermDefinition, SetupEffect


@dataclass(frozen=True)
class GuideQueryResult:
    terms: list[GuideTermDefinition]
    principles: list[GuidePrinciple]
    mappings: list[GuideSetupMapping]
    setup_effects: list[SetupEffect]
    cautions: list[str]
    source_ids: list[str]


def _matches_car(applies_to: list[str], disabled_for: list[str], car_family: str | None) -> bool:
    if car_family is None:
        return True
    if car_family in disabled_for:
        return False
    return "all" in applies_to or car_family in applies_to


def query_guide_knowledge(
    *,
    source_id: str | None = None,
    topic: str | None = None,
    setup_area: str | None = None,
    symptom: str | None = None,
    car_family: str | None = None,
    knowledge: SetupKnowledge | None = None,
) -> GuideQueryResult:
    knowledge = knowledge or load_setup_knowledge()
    needle = (topic or "").lower()

    terms = [
        term
        for term in knowledge.guide_term_definitions
        if (not source_id or source_id in term.source_ids)
        and (not topic or needle in term.term.lower() or needle in term.canonical_term.lower() or any(needle in alias.lower() for alias in term.aliases))
        and (not setup_area or setup_area in [term.canonical_term, term.term, *term.aliases])
        and (not symptom or symptom == term.symptom_hint)
    ]

    principles = [
        principle
        for principle in knowledge.guide_principles
        if (not source_id or source_id in principle.source_ids)
        and (not topic or needle in principle.title.lower() or needle in principle.racerzlab_wording.lower())
        and (not setup_area or setup_area in principle.setup_areas or not principle.setup_areas)
        and (not symptom or symptom in principle.symptoms or not principle.symptoms)
    ]

    mappings = [
        mapping
        for mapping in knowledge.guide_setup_mappings
        if (not source_id or source_id in mapping.source_ids)
        and (not setup_area or mapping.setup_area == setup_area)
        and (not symptom or mapping.symptom == symptom)
        and (not topic or needle in mapping.setup_area.lower() or needle in mapping.symptom.lower() or needle in mapping.intended_effect.lower())
        and _matches_car(mapping.applies_to, mapping.disabled_for, car_family)
    ]

    effects = [
        effect
        for effect in knowledge.setup_effects
        if (not source_id or source_id in effect.source_ids)
        and (not setup_area or effect.setup_area == setup_area)
        and (not symptom or symptom in effect.helps)
        and (not topic or needle in effect.setup_area.lower() or needle in effect.effect.lower() or needle in effect.counter_effect.lower())
        and _matches_car(effect.applies_to, effect.disabled_for, car_family)
    ]

    cautions = sorted(
        {
            caution
            for item in [*principles, *effects]
            for caution in (getattr(item, "cautions", []) or [])
        }
    )
    source_ids = sorted({sid for item in [*terms, *principles, *mappings, *effects] for sid in item.source_ids})
    return GuideQueryResult(terms=terms, principles=principles, mappings=mappings, setup_effects=effects, cautions=cautions, source_ids=source_ids)
