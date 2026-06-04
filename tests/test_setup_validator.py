from __future__ import annotations

import pytest

from racelab_engine.knowledge.setup.loader import DATASETS, SetupKnowledge, load_setup_knowledge
from racelab_engine.knowledge.setup.schema import (
    CarCapability,
    EvidenceGroup,
    EvidenceRequirement,
    GuideSource,
    PackageArchetype,
    PhaseDefinition,
    SetupArea,
    SetupEffect,
    SymptomVocabularyEntry,
)
from racelab_engine.knowledge.setup.validator import _contains_banned_certainty, validate_setup_knowledge


def _area(area_id: str, *, next_gen_note: str = "") -> SetupArea:
    return SetupArea(
        setup_area=area_id,
        system="chassis",
        applies_to=["all"],
        disabled_for=[],
        effect_strength_default=3,
        coupling_risk_default="medium",
        what_it_changes="setup response",
        phases=["entry"],
        evidence_required=["setup_snapshot"],
        validation_targets=["lap_time"],
        notes=[],
        package_role=[],
        car_specific_notes={"next_gen": next_gen_note} if next_gen_note else {},
        available_when=[],
        unavailable_when=[],
        common_confusions=[],
        static_or_live="static_setup",
    )


def _effect(**overrides) -> SetupEffect:
    data = {
        "effect_id": "raise_crossweight",
        "setup_area": "cross_weight",
        "direction": "Raise cross weight",
        "driver_phrase": ["tight entry"],
        "applies_to": ["all"],
        "disabled_for": [],
        "helps": ["tight_entry"],
        "can_hurt": ["loose_exit"],
        "effect_strength": 3,
        "coupling_risk": "medium",
        "effect": "Can add entry security.",
        "counter_effect": "May reduce rotation.",
        "test_language": "Try one small change.",
        "evidence_required": ["setup_snapshot"],
        "validation_targets": ["entry balance"],
        "small_swing_hint": "small",
        "cautions": [],
        "primary_effects": ["entry security"],
        "counter_effects": ["less rotation"],
        "helps_phases": ["entry"],
        "can_hurt_phases": ["exit"],
        "setup_package_tags": ["baseline"],
        "track_family_tags": [],
        "driver_facing_summary": "Adds security.",
        "why_ranked_template": "Matches complaint.",
        "one_change_test_template": "Try one small change.",
        "expected_improvement_targets": ["entry balance"],
        "watch_for_targets": ["exit rotation"],
        "evidence_priority": ["setup_snapshot"],
        "evidence_missing_message": "Need setup.",
        "preferred_when": [],
        "avoid_when": [],
        "exact_value_policy": "none",
        "can_show_delta": True,
        "delta_label": "click",
        "caution_level": "medium",
        "source_ids": ["guide"],
        "review_status": "accepted",
    }
    data.update(overrides)
    return SetupEffect(**data)


def _knowledge(*, effect: SetupEffect | None = None) -> SetupKnowledge:
    disabled_areas = ["track_bar", "truck_arm_mount", "bump_stop", "packer"]
    return SetupKnowledge(
        car_capabilities=[
            CarCapability(
                car_family="next_gen",
                applies_to=["next_gen"],
                available_setup_areas=["cross_weight"],
                disabled_setup_areas=disabled_areas,
                discrete_options={
                    "front_arb_diameter": ["1.375", "2.000"],
                    "rear_arb_diameter": ["1.375", "2.000"],
                    "front_arb_arm": ["P1", "P2", "P3", "P4", "P5"],
                    "rear_arb_arm": ["P1", "P2", "P3", "P4", "P5"],
                },
                notes=[],
            )
        ],
        phase_model=[
            PhaseDefinition(
                phase_id="entry",
                label="Entry",
                driver_terms=["entry"],
                definition="corner entry",
                typical_evidence=["steering"],
                common_setup_areas=["cross_weight"],
            ),
            PhaseDefinition(
                phase_id="exit",
                label="Exit",
                driver_terms=["exit"],
                definition="corner exit",
                typical_evidence=["throttle"],
                common_setup_areas=["cross_weight"],
            ),
        ],
        symptom_vocabulary=[
            SymptomVocabularyEntry(
                phrase="tight entry",
                canonical_symptom="tight_entry",
                phase="entry",
                balance="tight",
                confidence_prior=0.9,
                possible_secondary=[],
                trigger_hint=[],
                clarification_options=[],
                common_secondary_symptoms=[],
            ),
            SymptomVocabularyEntry(
                phrase="loose exit",
                canonical_symptom="loose_exit",
                phase="exit",
                balance="loose",
                confidence_prior=0.9,
                possible_secondary=[],
                trigger_hint=[],
                clarification_options=[],
                common_secondary_symptoms=[],
            ),
        ],
        effectiveness_scale=[],
        setup_areas=[
            _area("cross_weight"),
            *[_area(area_id, next_gen_note="Unavailable on Next Gen.") for area_id in disabled_areas],
        ],
        setup_effects=[effect or _effect()],
        package_archetypes=[
            PackageArchetype(
                archetype_id="baseline",
                name="Baseline",
                applies_to=["all"],
                why_fast="stable",
                common_risks=[],
                compensators=[],
                watch_evidence=[],
                complaint_patterns=[],
                diagnostic_questions=[],
                likely_driver_complaints=[],
                stabilizers=[],
                failure_modes=[],
                recommended_evidence_order=[],
                what_it_looks_like="neutral",
                setup_areas_commonly_involved=["cross_weight"],
                driver_facing_explanation="baseline",
                disabled_for=[],
                source_ids=["guide"],
                setup_areas_involved=["cross_weight"],
            )
        ],
        evidence_requirements=[
            EvidenceRequirement(
                requirement_id="tight_entry_cross_weight",
                symptom="tight_entry",
                setup_area="cross_weight",
                required_evidence=["setup_snapshot"],
                optional_evidence=[],
                insufficient_wording="Need setup.",
                evidence_groups=[
                    EvidenceGroup(
                        group_id="setup",
                        label="Setup",
                        required=True,
                        channels_or_context=["setup_snapshot"],
                        missing_message="Need setup.",
                    )
                ],
            )
        ],
        nextgen_platform_rules=[],
        shock_interpretation=[],
        guide_sources=[
            GuideSource(
                source_id="guide",
                title="Guide",
                source_type="guide",
                domain="oval",
                car_scope="all",
                file_name="guide.md",
                local_path="docs/guide.md",
                page_refs=[],
                status="accepted",
                notes="fixture",
            )
        ],
        guide_principles=[],
        guide_term_definitions=[],
        guide_setup_mappings=[],
        guide_review_queue=[],
        guide_digest_manifest=[],
    )


def test_contains_banned_certainty_detects_terms_and_allows_not_always() -> None:
    assert _contains_banned_certainty("This will fix the entry.")
    assert _contains_banned_certainty("This is guaranteed.")
    assert _contains_banned_certainty("This always fixes entry.")
    assert not _contains_banned_certainty("This is not always the right direction.")


def test_validator_reports_specific_effect_rule_violations() -> None:
    broken = _effect(
        effect_id="broken_effect",
        effect_strength=5,
        coupling_risk="low",
        evidence_required=[],
        source_ids=["missing_source"],
        effect="This always fixes entry.",
    )

    problems = validate_setup_knowledge(_knowledge(effect=broken))

    assert "Effect broken_effect is missing evidence_required" in problems
    assert "Effect broken_effect references unknown source_ids: ['missing_source']" in problems
    assert "Effect broken_effect is strength 5 without high coupling risk" in problems
    assert "Effect broken_effect contains guaranteed-fix wording" in problems


def test_loader_reports_invalid_json_file(tmp_path) -> None:
    for filename, _model in DATASETS.values():
        (tmp_path / filename).write_text("[]", encoding="utf-8")
    (tmp_path / "car_capabilities.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON in .*car_capabilities.json"):
        load_setup_knowledge(tmp_path)


def test_validator_reports_referential_integrity_errors() -> None:
    broken = _effect(effect_id="bad_refs", setup_area="missing_area", helps=["missing_symptom"], setup_package_tags=["missing_package"])

    problems = validate_setup_knowledge(_knowledge(effect=broken))

    assert "Effect bad_refs references unknown setup area missing_area" in problems
    assert "Effect bad_refs references unknown package tags: ['missing_package']" in problems
    assert "Effect bad_refs references unknown symptom missing_symptom" in problems
