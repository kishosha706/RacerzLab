from __future__ import annotations

import subprocess
import sys

from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.knowledge.setup.matcher import query_setup_knowledge
from racelab_engine.knowledge.setup.source_mapper import query_guide_knowledge
from racelab_engine.knowledge.setup.validator import validate_setup_knowledge


def test_guide_sources_load():
    knowledge = load_setup_knowledge()
    assert len(knowledge.guide_sources) >= 10
    assert "racerzlab_master_setup_matrix_v1" in knowledge.guide_source_by_id
    lowline = knowledge.guide_source_by_id["lowline_oval_setup_guide"]
    assert lowline.local_path == "docs/setup_knowledge/lowline_oval_setup_guide_v1_6_review.md"


def test_every_referenced_source_id_exists():
    knowledge = load_setup_knowledge()
    source_ids = set(knowledge.guide_source_by_id)
    for principle in knowledge.guide_principles:
        assert set(principle.source_ids) <= source_ids
    for term in knowledge.guide_term_definitions:
        assert set(term.source_ids) <= source_ids
    for mapping in knowledge.guide_setup_mappings:
        assert set(mapping.source_ids) <= source_ids
    for effect in knowledge.setup_effects:
        assert set(effect.source_ids) <= source_ids


def test_guide_principles_load():
    principles = {item.principle_id for item in load_setup_knowledge().guide_principles}
    assert {"baseline_first", "one_change_at_a_time", "exit_first_flow"}.issubset(principles)


def test_term_definitions_load():
    terms = {item.canonical_term for item in load_setup_knowledge().guide_term_definitions}
    assert {
        "shock_histogram",
        "diffuser_proxy",
        "cross_weight",
        "track_bar",
        "tire_pressure_responsiveness",
        "brake_bias_masking",
        "coil_binding_legacy_context",
    }.issubset(terms)


def test_setup_mappings_link_to_setup_areas():
    knowledge = load_setup_knowledge()
    area_ids = set(knowledge.setup_area_by_id)
    assert all(mapping.setup_area in area_ids for mapping in knowledge.guide_setup_mappings)


def test_no_accepted_record_has_forbidden_guarantee_wording():
    assert validate_setup_knowledge(load_setup_knowledge()) == []


def test_no_accepted_diffuser_record_claims_measured_downforce():
    knowledge = load_setup_knowledge()
    diffuser_text = " ".join(
        [
            *(term.definition for term in knowledge.guide_term_definitions if "diffuser" in term.canonical_term),
            *(rule.wording for rule in knowledge.nextgen_platform_rules),
            *(effect.effect for effect in knowledge.setup_effects if "diffuser" in effect.setup_area),
        ]
    ).lower()
    assert "measured downforce" not in diffuser_text or "not measured downforce" in diffuser_text


def test_cfs_half_inch_claim_is_needs_review():
    items = {item.review_id: item for item in load_setup_knowledge().guide_review_queue}
    assert items["cfs_half_inch_opening_claim"].status == "needs_review"


def test_next_gen_disabled_areas_remain_disabled():
    cap = load_setup_knowledge().car_capability_by_family["next_gen"]
    assert set(cap.disabled_setup_areas) == {"track_bar", "truck_arm_mount", "bump_stop", "packer"}


def test_lowline_source_is_applied_to_reviewed_records():
    knowledge = load_setup_knowledge()
    source_id = "lowline_oval_setup_guide"

    principles = {principle.principle_id for principle in knowledge.guide_principles if source_id in principle.source_ids}
    assert {
        "lowline_tire_pressure_load_temp_context",
        "lowline_brake_bias_masks_entry_context",
        "lowline_spring_changes_require_platform_reset",
        "lowline_legacy_travel_levers_capability_gate",
    }.issubset(principles)

    mappings = {mapping.mapping_id for mapping in knowledge.guide_setup_mappings if source_id in mapping.source_ids}
    assert {
        "lowline_rear_toe_stability_context",
        "lowline_brake_bias_entry_support",
        "lowline_caster_split_entry_center_feel",
        "lowline_spring_change_platform_recheck",
    }.issubset(mappings)

    effects_by_area = {
        effect.setup_area
        for effect in knowledge.setup_effects
        if source_id in effect.source_ids
    }
    assert {"tire_pressure", "toe", "brake_bias", "caster", "camber", "spring_rate", "track_bar"}.issubset(effects_by_area)


def test_legacy_oval_can_keep_legacy_areas():
    cap = load_setup_knowledge().car_capability_by_family["legacy_oval_generic"]
    assert {"track_bar", "truck_arm_mount", "bump_stop", "packer"}.issubset(cap.available_setup_areas)


def test_arb_discrete_options_remain_exact():
    cap = load_setup_knowledge().car_capability_by_family["next_gen"]
    assert cap.discrete_options["front_arb_diameter"] == ["1.375", "2.000"]
    assert cap.discrete_options["rear_arb_diameter"] == ["1.375", "2.000"]
    assert cap.discrete_options["front_arb_arm"] == ["P1", "P2", "P3", "P4", "P5"]
    assert cap.discrete_options["rear_arb_arm"] == ["P1", "P2", "P3", "P4", "P5"]


def test_next_gen_arb_p_setting_direction_is_encoded():
    knowledge = load_setup_knowledge()
    terms = {term.term_id: term.definition.lower() for term in knowledge.guide_term_definitions}
    assert "1.375 soft" in terms["front_arb_diameter"]
    assert "2.000 stiff" in terms["rear_arb_diameter"]
    assert "p1 is softest/lowest/looser" in terms["front_arb_arm"]
    assert "p5 is stiffest/tighter" in terms["rear_arb_arm"]

    effects = {effect.effect_id: effect for effect in knowledge.setup_effects}
    assert "tight_center" in effects["soften_front_arb_arm_one_position"].helps
    assert "loose_center" in effects["stiffen_front_arb_arm_one_position"].helps
    assert "tight_exit" in effects["soften_rear_arb_arm_one_position"].helps
    assert "loose_exit" in effects["stiffen_rear_arb_arm_one_position"].helps
    assert effects["switch_rear_arb_to_soft_bar"].effect_strength == 5
    assert effects["switch_rear_arb_to_stiff_bar"].exact_value_policy == "reference_only"


def test_oval_setup_matrix_v5_visible_rows_have_reviewed_coverage():
    knowledge = load_setup_knowledge()
    area_ids = set(knowledge.setup_area_by_id)
    term_ids = {term.term_id for term in knowledge.guide_term_definitions}

    assert {
        "tire_pressure",
        "spring_rate",
        "ls_compression",
        "hs_compression",
        "ls_rebound",
        "hs_rebound",
        "camber",
        "caster",
        "corner_weight",
        "ride_height",
        "shock_collar",
        "front_arb_diameter",
        "front_arb_arm",
        "front_arb_preload",
        "ballast",
        "front_stagger",
        "front_toe_response",
        "toe",
        "rear_arb_arm",
        "truck_arm_mount",
        "track_bar",
    }.issubset(area_ids)
    assert "steering_ratio" in term_ids


def test_query_guide_knowledge_by_setup_area_returns_source_backed_records():
    result = query_guide_knowledge(setup_area="ls_rebound", car_family="next_gen")
    assert result.setup_effects
    assert result.source_ids


def test_export_digest_report_runs():
    completed = subprocess.run(
        [sys.executable, "-B", "scripts/export_setup_knowledge_digest.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "setup_knowledge_digest_report.md" in completed.stdout


def test_setup_knowledge_validator_validates_guide_digest_files():
    assert validate_setup_knowledge(load_setup_knowledge()) == []


def test_oval_matrix_condition_groups_exist():
    symptoms = {mapping.symptom for mapping in load_setup_knowledge().guide_setup_mappings}
    assert {
        "loose_entry",
        "tight_entry",
        "loose_center",
        "tight_center",
        "loose_exit",
        "tight_exit",
    }.issubset(symptoms)


def test_flowchart_principles_exist():
    principles = {principle.principle_id for principle in load_setup_knowledge().guide_principles}
    assert "exit_first_flow" in principles


def test_every_setup_effect_has_source_ids():
    assert all(effect.source_ids for effect in load_setup_knowledge().setup_effects)


def test_every_setup_effect_has_effect_and_counter_effect():
    for effect in load_setup_knowledge().setup_effects:
        assert effect.effect
        assert effect.counter_effect


def test_generic_loose_tight_asks_clarification():
    assert query_setup_knowledge(car_family="next_gen", symptom="loose").clarification_question
    assert query_setup_knowledge(car_family="next_gen", symptom="tight").clarification_question


def test_next_gen_query_never_returns_legacy_disabled_areas():
    result = query_setup_knowledge(car_family="next_gen", symptom="tight center", limit=40)
    areas = {ranked.effect.setup_area for ranked in result.candidate_effects}
    assert not areas & {"track_bar", "truck_arm_mount", "bump_stop", "packer"}


def test_query_guide_script_topic_diffuser():
    completed = subprocess.run(
        [sys.executable, "-B", "scripts/query_guide_knowledge.py", "--topic", "diffuser", "--car-family", "next_gen"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "diffuser" in completed.stdout.lower()
