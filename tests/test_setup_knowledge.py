from __future__ import annotations

import json
import subprocess
import sys

from racelab_engine.knowledge.setup.loader import load_setup_knowledge
from racelab_engine.knowledge.setup.matcher import parse_symptom, query_setup_knowledge
from racelab_engine.knowledge.setup.validator import validate_setup_knowledge


def _areas(result) -> set[str]:
    return {ranked.effect.setup_area for ranked in result.candidate_effects}


def _ids(result) -> set[str]:
    return {ranked.effect.effect_id for ranked in result.candidate_effects}


def test_enriched_schema_loads():
    knowledge = load_setup_knowledge()
    assert len(knowledge.setup_effects) >= 55
    assert len(knowledge.symptom_vocabulary) >= 55
    assert knowledge.setup_effects[0].primary_effects
    assert knowledge.setup_areas[0].static_or_live


def test_validator_passes():
    assert validate_setup_knowledge(load_setup_knowledge()) == []


def test_every_effect_has_effect_and_counter_effect_arrays():
    for effect in load_setup_knowledge().setup_effects:
        assert effect.effect
        assert effect.counter_effect
        assert "may" in effect.counter_effect.lower()
        assert effect.primary_effects
        assert effect.counter_effects


def test_every_effect_has_validation_targets():
    for effect in load_setup_knowledge().setup_effects:
        assert effect.validation_targets
        assert effect.expected_improvement_targets
        assert effect.watch_for_targets is not None


def test_every_effect_has_phase_influence_and_strength_risk():
    known_phases = {phase.phase_id for phase in load_setup_knowledge().phase_model}
    for effect in load_setup_knowledge().setup_effects:
        assert effect.helps_phases
        assert effect.can_hurt_phases
        assert set(effect.helps_phases) <= known_phases
        assert set(effect.can_hurt_phases) <= known_phases
        assert 1 <= effect.effect_strength <= 5
        assert effect.coupling_risk in {"low", "medium", "high"}


def test_strength_five_implies_high_risk():
    for effect in load_setup_knowledge().setup_effects:
        if effect.effect_strength == 5:
            assert effect.coupling_risk == "high"


def test_every_effect_has_evidence_requirements():
    for effect in load_setup_knowledge().setup_effects:
        assert effect.evidence_required
        assert effect.evidence_priority
        assert effect.evidence_missing_message


def test_loose_off_next_gen_ranks_expected_candidate_styles():
    result = query_setup_knowledge(car_family="next_gen", symptom="loose off", limit=20)
    areas = _areas(result)
    assert {"cross_weight", "rear_ride_height_platform", "tire_pressure", "ls_rebound"}.issubset(areas)


def test_tight_center_ranks_center_rotation_candidates():
    result = query_setup_knowledge(car_family="next_gen", symptom="tight center", limit=12)
    assert "reduce_crossweight_small" in _ids(result)
    assert {"front_arb_diameter", "diff_preload"}.issubset(_areas(result))


def test_draggy_ranks_scrub_platform_and_gearing_candidates():
    result = query_setup_knowledge(car_family="next_gen", symptom="draggy", evidence=["setup_snapshot", "platform_trace"], limit=10)
    assert {"toe", "final_drive", "diffuser_platform"}.issubset(_areas(result))


def test_draggy_top_three_are_diverse_scrub_gearing_platform_candidates():
    result = query_setup_knowledge(car_family="next_gen", symptom="draggy", evidence=["setup_snapshot", "platform_trace"], limit=3)
    assert [ranked.effect.setup_area for ranked in result.candidate_effects] == [
        "toe",
        "final_drive",
        "rear_ride_height_platform",
    ]


def test_rear_scrape_ranks_rear_platform_diffuser_contact_candidates():
    result = query_setup_knowledge(car_family="next_gen", symptom="rear scrape", limit=10)
    assert {"rear_ride_height_platform", "diffuser_platform", "ride_height"}.issubset(_areas(result))


def test_rear_scrape_top_three_are_contact_and_platform_candidates():
    result = query_setup_knowledge(car_family="next_gen", symptom="rear scrape", evidence=["setup_snapshot", "platform_trace"], limit=3)
    assert {"ride_height", "rear_ride_height_platform", "shock_collar"} == _areas(result)


def test_burns_rf_returns_tire_front_and_long_run_candidates():
    result = query_setup_knowledge(
        car_family="next_gen",
        symptom="burns RF",
        evidence=["setup_snapshot", "tire_temps", "platform_trace"],
        limit=5,
    )
    areas = _areas(result)
    assert {"tire_pressure", "camber"}.issubset(areas)
    assert any("long_run" in ranked.effect.helps_phases for ranked in result.candidate_effects)


def test_snaps_loose_on_throttle_returns_transition_candidates():
    result = query_setup_knowledge(
        car_family="next_gen",
        symptom="snaps loose on throttle",
        evidence=["setup_snapshot", "shock_histogram", "platform_trace"],
        limit=3,
    )
    assert all("transition" in ranked.effect.helps_phases or "exit" in ranked.effect.helps_phases for ranked in result.candidate_effects)


def test_next_gen_never_returns_disabled_legacy_areas():
    result = query_setup_knowledge(car_family="next_gen", symptom="tight center", limit=30)
    assert not _areas(result) & {"track_bar", "truck_arm_mount", "bump_stop", "packer"}


def test_legacy_oval_generic_can_return_legacy_areas_when_relevant():
    tight_center = query_setup_knowledge(car_family="legacy_oval_generic", symptom="tight center", limit=20)
    platform = query_setup_knowledge(car_family="legacy_oval_generic", symptom="front feed unstable", limit=30)
    poor_drive = query_setup_knowledge(car_family="legacy_oval_generic", symptom="lacks drive", limit=30)
    legacy_areas = _areas(tight_center) | _areas(platform) | _areas(poor_drive)
    assert {"track_bar", "truck_arm_mount", "bump_stop", "packer"} & legacy_areas


def test_next_gen_arb_diameter_and_arm_constraints_valid():
    cap = load_setup_knowledge().car_capability_by_family["next_gen"]
    assert cap.discrete_options["front_arb_diameter"] == ["1.375", "2.000"]
    assert cap.discrete_options["rear_arb_diameter"] == ["1.375", "2.000"]
    assert cap.discrete_options["front_arb_arm"] == ["P1", "P2", "P3", "P4", "P5"]
    assert cap.discrete_options["rear_arb_arm"] == ["P1", "P2", "P3", "P4", "P5"]


def test_generic_loose_asks_clarification():
    result = query_setup_knowledge(car_family="next_gen", symptom="loose")
    assert result.ambiguity is True
    assert result.clarification_question


def test_loose_off_does_not_ask_clarification():
    result = query_setup_knowledge(car_family="next_gen", symptom="loose off")
    assert result.ambiguity is False
    assert result.clarification_question is None


def test_evidence_missing_flags_shock_candidates():
    result = query_setup_knowledge(car_family="next_gen", symptom="loose off", limit=12)
    shock_candidates = [ranked for ranked in result.candidate_effects if ranked.effect.setup_area == "ls_rebound"]
    assert shock_candidates
    assert all(ranked.readiness == "missing_key_evidence" for ranked in shock_candidates)
    assert any("shock_histogram" in ",".join(ranked.missing_evidence) for ranked in shock_candidates)


def test_evidence_present_raises_readiness():
    result = query_setup_knowledge(
        car_family="next_gen",
        symptom="loose off",
        evidence=["shock_histogram", "throttle", "yaw", "rear_platform"],
        limit=12,
    )
    shock_candidates = [ranked for ranked in result.candidate_effects if ranked.effect.setup_area == "ls_rebound"]
    assert shock_candidates
    assert any(ranked.readiness == "ready" for ranked in shock_candidates)


def test_package_archetype_input_changes_ranking_reasons():
    result = query_setup_knowledge(
        car_family="next_gen",
        symptom="loose off",
        package_archetype="low_platform_speed_package",
        track_family="intermediate_oval",
        evidence=["setup_snapshot", "platform_trace"],
        limit=5,
    )
    assert any("package match: low_platform_speed_package" in reason for ranked in result.candidate_effects for reason in ranked.ranking_reasons)


def test_diffuser_rules_do_not_claim_measured_downforce():
    for rule in load_setup_knowledge().nextgen_platform_rules:
        wording = rule.wording.lower()
        assert "measured downforce" not in wording or "not measured downforce" in wording
        assert "proxy measures downforce" not in wording


def test_cfs_half_inch_item_remains_needs_review():
    review_items = {item.review_id: item for item in load_setup_knowledge().guide_review_queue}
    item = review_items["cfs_half_inch_opening_claim"]
    assert item.status == "needs_review"
    assert "0.5" in item.safe_wording


def test_diffuser_effect_text_uses_proxy_not_force_claims():
    diffuser_text = []
    for effect in load_setup_knowledge().setup_effects:
        if effect.setup_area in {"front_ride_height_platform", "rear_ride_height_platform", "diffuser_platform"}:
            diffuser_text.append(" ".join([effect.effect, effect.counter_effect, effect.driver_facing_summary]).lower())
    combined = " ".join(diffuser_text)
    assert "measured downforce" not in combined
    assert "derived" in combined


def test_shock_rules_do_not_say_histogram_alone_proves_change():
    for rule in load_setup_knowledge().shock_interpretation:
        text = " ".join([rule.wording, *rule.cautions]).lower()
        assert "histogram alone proves" not in text
        assert "histogram alone confirms" not in text


def test_shock_effect_text_does_not_overstate_histogram_evidence():
    for effect in load_setup_knowledge().setup_effects:
        if effect.setup_area in {"ls_compression", "ls_rebound", "hs_compression", "hs_rebound", "hs_comp_slope"}:
            text = " ".join([effect.effect, effect.counter_effect, effect.driver_facing_summary, *effect.cautions]).lower()
            assert "histogram alone proves" not in text
            assert "histogram alone confirms" not in text


def test_cli_json_works():
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/query_setup_knowledge.py",
            "--car-family",
            "next_gen",
            "--symptom",
            "loose off",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert {"parsed_symptom", "parsed_phase", "confidence", "ambiguity", "candidates", "disabled_by_capability", "warnings"}.issubset(payload)
    assert payload["parsed_symptom"]["canonical_symptom"] == "loose_exit"
    assert payload["candidates"]
    assert {"effect_id", "effect", "counter_effect", "one_change_test", "validate_with"}.issubset(payload["candidates"][0])


def test_query_output_includes_one_change_test_language_counter_effect_and_targets():
    result = query_setup_knowledge(car_family="next_gen", symptom="loose off")
    first = result.candidate_effects[0]
    assert "Try one" in first.one_change_test_plan
    assert first.effect.counter_effect
    assert first.effect.validation_targets


def test_cli_text_hides_disabled_by_default_and_can_show_disabled():
    hidden = subprocess.run(
        [sys.executable, "-B", "scripts/query_setup_knowledge.py", "--car-family", "next_gen", "--symptom", "loose off"],
        check=True,
        capture_output=True,
        text=True,
    )
    shown = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/query_setup_knowledge.py",
            "--car-family",
            "next_gen",
            "--symptom",
            "loose off",
            "--show-disabled",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Disabled by car capability for next_gen" not in hidden.stdout
    assert "Disabled by car capability for next_gen" in shown.stdout


def test_cli_text_contains_polished_labels_and_readiness():
    completed = subprocess.run(
        [sys.executable, "-B", "scripts/query_setup_knowledge.py", "--car-family", "next_gen", "--symptom", "loose off"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Candidate 1:" in completed.stdout
    assert "Effect:" in completed.stdout
    assert "Counter-effect:" in completed.stdout
    assert "One-change test:" in completed.stdout
    assert "Validate:" in completed.stdout
    assert "Watch for:" in completed.stdout
    assert "Evidence: missing key evidence" in completed.stdout


def test_cli_text_contains_package_and_preferred_context():
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/query_setup_knowledge.py",
            "--car-family",
            "next_gen",
            "--symptom",
            "draggy",
            "--evidence",
            "setup_snapshot,platform_trace",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Package notes:" in completed.stdout
    assert "Preferred when:" in completed.stdout


def test_no_effect_uses_banned_certainty_language():
    banned = ("guaranteed", "always", "will fix", "universal truth")
    for effect in load_setup_knowledge().setup_effects:
        text = " ".join(
            [
                effect.effect,
                effect.counter_effect,
                effect.test_language,
                effect.driver_facing_summary,
                effect.one_change_test_template,
                *effect.cautions,
            ]
        ).lower()
        assert not any(term in text for term in banned)
