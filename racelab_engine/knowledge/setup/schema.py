from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CarCapability(KnowledgeModel):
    car_family: str
    applies_to: list[str]
    available_setup_areas: list[str]
    disabled_setup_areas: list[str]
    discrete_options: dict[str, list[str]]
    notes: list[str]


class PhaseDefinition(KnowledgeModel):
    phase_id: str
    label: str
    driver_terms: list[str]
    definition: str
    typical_evidence: list[str]
    common_setup_areas: list[str]


class SymptomVocabularyEntry(KnowledgeModel):
    phrase: str
    canonical_symptom: str
    phase: str
    balance: str
    confidence_prior: float = Field(ge=0.0, le=1.0)
    possible_secondary: list[str]
    clarification_question: str | None = None


class EffectivenessScaleEntry(KnowledgeModel):
    value: int = Field(ge=1, le=5)
    label: str
    meaning: str


class SetupArea(KnowledgeModel):
    setup_area: str
    system: str
    applies_to: list[str]
    disabled_for: list[str]
    effect_strength_default: int = Field(ge=1, le=5)
    coupling_risk_default: str
    what_it_changes: str
    phases: list[str]
    evidence_required: list[str]
    validation_targets: list[str]
    notes: list[str]


class SetupEffect(KnowledgeModel):
    effect_id: str
    setup_area: str
    direction: str
    driver_phrase: list[str]
    applies_to: list[str]
    disabled_for: list[str]
    helps: list[str]
    can_hurt: list[str]
    effect_strength: int = Field(ge=1, le=5)
    coupling_risk: str
    effect: str
    counter_effect: str
    test_language: str
    evidence_required: list[str]
    validation_targets: list[str]
    small_swing_hint: str
    cautions: list[str]


class PackageArchetype(KnowledgeModel):
    archetype_id: str
    name: str
    applies_to: list[str]
    why_fast: str
    common_risks: list[str]
    compensators: list[str]
    watch_evidence: list[str]
    complaint_patterns: list[str]


class EvidenceRequirement(KnowledgeModel):
    requirement_id: str
    symptom: str
    setup_area: str
    required_evidence: list[str]
    optional_evidence: list[str]
    insufficient_wording: str


class NextGenPlatformRule(KnowledgeModel):
    rule_id: str
    title: str
    truth_level: str
    wording: str
    evidence_required: list[str]
    do_not_say: list[str]


class ShockInterpretationRule(KnowledgeModel):
    rule_id: str
    topic: str
    wording: str
    applies_to: list[str]
    evidence_required: list[str]
    cautions: list[str]
