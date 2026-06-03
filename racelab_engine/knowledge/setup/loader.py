from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from .schema import (
    CarCapability,
    EffectivenessScaleEntry,
    EvidenceRequirement,
    GuideDigestManifest,
    GuidePrinciple,
    GuideReviewItem,
    GuideSetupMapping,
    GuideSource,
    GuideTermDefinition,
    NextGenPlatformRule,
    PackageArchetype,
    PhaseDefinition,
    SetupArea,
    SetupEffect,
    ShockInterpretationRule,
    SymptomVocabularyEntry,
)
from .validator import validate_setup_knowledge


T = TypeVar("T")

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class SetupKnowledge:
    car_capabilities: list[CarCapability]
    phase_model: list[PhaseDefinition]
    symptom_vocabulary: list[SymptomVocabularyEntry]
    effectiveness_scale: list[EffectivenessScaleEntry]
    setup_areas: list[SetupArea]
    setup_effects: list[SetupEffect]
    package_archetypes: list[PackageArchetype]
    evidence_requirements: list[EvidenceRequirement]
    nextgen_platform_rules: list[NextGenPlatformRule]
    shock_interpretation: list[ShockInterpretationRule]
    guide_sources: list[GuideSource]
    guide_principles: list[GuidePrinciple]
    guide_term_definitions: list[GuideTermDefinition]
    guide_setup_mappings: list[GuideSetupMapping]
    guide_review_queue: list[GuideReviewItem]
    guide_digest_manifest: list[GuideDigestManifest]

    @property
    def car_capability_by_family(self) -> dict[str, CarCapability]:
        return {cap.car_family: cap for cap in self.car_capabilities}

    @property
    def setup_area_by_id(self) -> dict[str, SetupArea]:
        return {area.setup_area: area for area in self.setup_areas}

    @property
    def guide_source_by_id(self) -> dict[str, GuideSource]:
        return {source.source_id: source for source in self.guide_sources}


DATASETS = {
    "car_capabilities": ("car_capabilities.json", CarCapability),
    "phase_model": ("phase_model.json", PhaseDefinition),
    "symptom_vocabulary": ("symptom_vocabulary.json", SymptomVocabularyEntry),
    "effectiveness_scale": ("effectiveness_scale.json", EffectivenessScaleEntry),
    "setup_areas": ("setup_areas.json", SetupArea),
    "setup_effects": ("setup_effects.json", SetupEffect),
    "package_archetypes": ("package_archetypes.json", PackageArchetype),
    "evidence_requirements": ("evidence_requirements.json", EvidenceRequirement),
    "nextgen_platform_rules": ("nextgen_platform_rules.json", NextGenPlatformRule),
    "shock_interpretation": ("shock_interpretation.json", ShockInterpretationRule),
    "guide_sources": ("guide_sources.json", GuideSource),
    "guide_principles": ("guide_principles.json", GuidePrinciple),
    "guide_term_definitions": ("guide_term_definitions.json", GuideTermDefinition),
    "guide_setup_mappings": ("guide_setup_mappings.json", GuideSetupMapping),
    "guide_review_queue": ("guide_review_queue.json", GuideReviewItem),
    "guide_digest_manifest": ("guide_digest_manifest.json", GuideDigestManifest),
}


def _load_json_list(data_dir: Path, filename: str, model: type[T]) -> list[T]:
    path = data_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing setup knowledge file: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ValueError(f"Setup knowledge file must contain a list: {path}")
    try:
        return [model.model_validate(item) for item in raw]  # type: ignore[attr-defined]
    except ValidationError as exc:
        raise ValueError(f"Schema validation failed for {path}: {exc}") from exc


def load_setup_knowledge(data_dir: Path | None = None) -> SetupKnowledge:
    root = data_dir or DATA_DIR
    loaded = {
        field: _load_json_list(root, filename, model)
        for field, (filename, model) in DATASETS.items()
    }
    knowledge = SetupKnowledge(**loaded)
    problems = validate_setup_knowledge(knowledge)
    if problems:
        joined = "\n".join(f"- {problem}" for problem in problems)
        raise ValueError(f"Invalid setup knowledge:\n{joined}")
    return knowledge
