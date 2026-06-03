from __future__ import annotations

import subprocess
import sys

from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.knowledge.setup.matcher import parse_symptom, query_setup_knowledge
from racelab_engine.knowledge.setup.validator import validate_setup_knowledge


def test_knowledge_loads():
    knowledge = load_setup_knowledge()
    assert knowledge.car_capabilities
    assert knowledge.setup_areas
    assert len(knowledge.setup_effects) >= 30


def test_validator_passes():
    assert validate_setup_knowledge(load_setup_knowledge()) == []


def test_loose_off_maps_to_loose_exit():
    parsed = parse_symptom("loose off", load_setup_knowledge())
    assert parsed.canonical_symptom == "loose_exit"


def test_tight_center_maps_to_tight_center():
    parsed = parse_symptom("tight center", load_setup_knowledge())
    assert parsed.canonical_symptom == "tight_center"


def test_bound_up_maps_to_tight_center_with_context():
    parsed = parse_symptom("bound up", load_setup_knowledge())
    assert parsed.canonical_symptom == "tight_center"
    assert "drag_scrub" in parsed.possible_secondary


def test_draggy_maps_to_speed_and_scrub_context():
    parsed = parse_symptom("draggy", load_setup_knowledge())
    assert parsed.canonical_symptom == "low_straight_speed"
    assert "drag_scrub" in parsed.possible_secondary


def test_next_gen_disables_legacy_areas():
    cap = load_setup_knowledge().car_capability_by_family["next_gen"]
    assert set(cap.disabled_setup_areas) == {"track_bar", "truck_arm_mount", "bump_stop", "packer"}


def test_legacy_oval_generic_can_include_legacy_areas():
    cap = load_setup_knowledge().car_capability_by_family["legacy_oval_generic"]
    assert {"track_bar", "truck_arm_mount", "bump_stop", "packer"}.issubset(cap.available_setup_areas)


def test_next_gen_arb_diameter_options():
    cap = load_setup_knowledge().car_capability_by_family["next_gen"]
    assert cap.discrete_options["front_arb_diameter"] == ["1.375", "2.000"]
    assert cap.discrete_options["rear_arb_diameter"] == ["1.375", "2.000"]


def test_next_gen_arb_arm_options():
    cap = load_setup_knowledge().car_capability_by_family["next_gen"]
    assert cap.discrete_options["front_arb_arm"] == ["P1", "P2", "P3", "P4", "P5"]
    assert cap.discrete_options["rear_arb_arm"] == ["P1", "P2", "P3", "P4", "P5"]


def test_every_setup_effect_has_effect_and_counter_effect():
    for effect in load_setup_knowledge().setup_effects:
        assert effect.effect
        assert effect.counter_effect


def test_every_setup_effect_has_strength_and_risk():
    for effect in load_setup_knowledge().setup_effects:
        assert 1 <= effect.effect_strength <= 5
        assert effect.coupling_risk


def test_query_loose_off_next_gen_returns_no_disabled_legacy_areas():
    result = query_setup_knowledge(car_family="next_gen", symptom="loose off", limit=20)
    areas = {ranked.effect.setup_area for ranked in result.candidate_effects}
    assert not areas & {"track_bar", "truck_arm_mount", "bump_stop", "packer"}


def test_query_loose_off_returns_expected_candidate_styles():
    result = query_setup_knowledge(car_family="next_gen", symptom="loose off", limit=20)
    areas = {ranked.effect.setup_area for ranked in result.candidate_effects}
    assert "cross_weight" in areas
    assert "rear_ride_height_platform" in areas
    assert "ls_rebound" in areas
    assert "tire_pressure" in areas


def test_diffuser_rules_do_not_say_measured_downforce():
    for rule in load_setup_knowledge().nextgen_platform_rules:
        wording = rule.wording.lower()
        assert "measured downforce" not in wording or "not measured downforce" in wording
        assert "proxy measures downforce" not in wording


def test_shock_rules_include_low_speed_high_speed_interpretation():
    wordings = " ".join(rule.wording.lower() for rule in load_setup_knowledge().shock_interpretation)
    assert "low-speed shock movement" in wordings
    assert "high-speed shock movement" in wordings


def test_no_effect_says_guaranteed_fix():
    banned = ("guaranteed fix", "always fixes", "will fix", "universal truth")
    for effect in load_setup_knowledge().setup_effects:
        text = " ".join([effect.effect, effect.counter_effect, effect.test_language, *effect.cautions]).lower()
        assert not any(term in text for term in banned)


def test_query_cli_loose_off_smoke():
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/query_setup_knowledge.py",
            "--car-family",
            "next_gen",
            "--symptom",
            "loose off",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Parsed symptom:" in completed.stdout
    assert "loose_exit" in completed.stdout
    candidate_section = completed.stdout.split("Candidate setup swings:")[1].split("Disabled for next_gen:")[0]
    assert "track_bar" not in candidate_section
