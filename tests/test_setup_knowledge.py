from __future__ import annotations

import json
import subprocess
import sys

import pytest

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


def test_exact_context_negative_memory_blocks_generic_prior_direction() -> None:
    result = query_setup_knowledge(
        car_family="next_gen",
        symptom="loose off",
        limit=30,
        learning_biases={
            ("cross_weight_percent", 1): {
                "count": 4,
                "weighted_outcome": -0.8,
                "magnitude_counts": {"small": 4},
                "weighted_outcome_by_magnitude": {"small": -0.8},
            }
        },
    )
    assert "add_crossweight_small" not in _ids(result)


def test_large_change_memory_cannot_block_an_untested_small_step() -> None:
    result = query_setup_knowledge(
        car_family="next_gen",
        symptom="loose off",
        limit=30,
        learning_biases={
            ("cross_weight_percent", 1): {
                "count": 4,
                "weighted_outcome": -1.0,
                "magnitude_counts": {"large": 4},
                "weighted_outcome_by_magnitude": {"large": -1.0},
            },
        },
    )
    assert "add_crossweight_small" in _ids(result)


@pytest.mark.parametrize("fragment", ["off", "rear", "in"])
def test_vague_fragments_do_not_select_the_first_partial_vocabulary_match(fragment: str) -> None:
    with pytest.raises(ValueError):
        parse_symptom(fragment, load_setup_knowledge())


def test_longest_complete_symptom_phrase_wins() -> None:
    parsed = parse_symptom("the car is loose off on throttle", load_setup_knowledge())
    assert parsed.canonical_symptom == "loose_exit"


@pytest.mark.parametrize(
    "complaint",
    ["tight off and loose off", "loose center but tight off"],
)
def test_conflicting_balance_directions_require_clarification(complaint: str) -> None:
    with pytest.raises(ValueError, match="conflicting loose and tight"):
        parse_symptom(complaint, load_setup_knowledge())


@pytest.mark.parametrize(
    "complaint", ["not loose off", "it is not tight center", "no rear scrape", "does not push on entry"],
)
def test_negated_symptoms_never_become_positive_setup_matches(complaint: str) -> None:
    with pytest.raises(ValueError, match="Negated handling descriptions"):
        parse_symptom(complaint, load_setup_knowledge())


@pytest.mark.parametrize(
    ("complaint", "canonical", "phase"),
    [
        ("tight entry", "tight_entry", "entry"),
        ("tight center", "tight_center", "center"),
        ("tight exit", "tight_exit", "exit"),
        ("loose entry", "loose_entry", "entry"),
        ("loose center", "loose_center", "center"),
        ("loose exit", "loose_exit", "exit"),
    ],
)
def test_generic_balance_plus_ui_phase_resolves_without_repeated_clarification(
    complaint: str, canonical: str, phase: str,
) -> None:
    parsed = parse_symptom(complaint, load_setup_knowledge())
    assert parsed.canonical_symptom == canonical
    assert parsed.phase == phase
    assert parsed.clarification_question is None


def test_partial_observed_mechanism_cannot_become_ready_from_capability() -> None:
    result = query_setup_knowledge(
        car_family="next_gen",
        symptom="loose off",
        evidence=["phase", "yaw", "throttle", "setup_snapshot", "tire_temps"],
        observed_evidence=["yaw"],
        limit=30,
    )
    cross = next(item for item in result.candidate_effects if item.effect.effect_id == "add_crossweight_small")
    assert cross.readiness == "partially_ready"


def test_exact_control_memory_does_not_transfer_rf_spring_history_to_lr() -> None:
    baseline = query_setup_knowledge(car_family="next_gen", symptom="loose off", limit=30)
    learned = query_setup_knowledge(
        car_family="next_gen",
        symptom="loose off",
        limit=30,
        learning_biases={
            ("rf_front_spring_n_per_mm", 1): {
                "count": 3,
                "weighted_outcome": 1.0,
                "magnitude_counts": {"small": 3},
                "weighted_outcome_by_magnitude": {"small": 1.0},
            },
        },
    )
    baseline_lr = next(item.score for item in baseline.candidate_effects if item.effect.effect_id == "add_lr_spring_support")
    learned_lr = next(item.score for item in learned.candidate_effects if item.effect.effect_id == "add_lr_spring_support")
    assert learned_lr == baseline_lr


def test_racing_terms_parse_to_expected_context():
    knowledge = load_setup_knowledge()
    expected = {
        "won't stay on bottom": ("tight_center", "center", "Does it push as soon as you touch the gas?"),
        "RF is angry": ("tire_overwork", "long_run", "Are you seeing high RF temps, wear, or just a push?"),
        "nose is dragging": ("front_platform_contact", "entry", "Is it bouncing, sparking, or a constant drag?"),
        "won't take a set": ("platform_instability", "entry", "Does it feel like it is floating, or just slow to point?"),
        "aero wash": ("aero_understeer", "center", "Is it worse in traffic or solo?"),
        "rear steps out": ("loose_exit", "exit", "Is it on throttle pickup, brake release, or steady state?"),
        "entry understeer": ("tight_entry", "entry", None),
        "mid-corner understeer": ("tight_center", "center", None),
        "power oversteer": ("loose_exit", "exit", None),
        "lift-off oversteer": ("loose_entry", "entry", "Is it on lift only, or after brake pressure starts?"),
        "brake instability": ("brake_entry_instability", "entry", "Is it rear instability, lockup, or wheel hop?"),
        "curb instability": ("shock_overactive", "transition", "Is it only over curbs or also over bumps?"),
        "platform instability": ("platform_instability", "transition", "Is it front feed, rear platform, or over bumps?"),
        "unstable over crest": ("platform_instability", "transition", "Is the instability on compression, crest release, or landing?"),
    }
    for phrase, (symptom, phase, question) in expected.items():
        parsed = parse_symptom(phrase, knowledge)
        assert parsed.canonical_symptom == symptom
        assert parsed.phase == phase
        assert parsed.clarification_question == question


def test_cross_weight_effects_use_full_setup_term():
    effects = {effect.effect_id: effect for effect in load_setup_knowledge().setup_effects}
    add_cross = effects["add_crossweight_small"]
    reduce_cross = effects["reduce_crossweight_small"]
    assert add_cross.direction == "Add a little cross weight"
    assert reduce_cross.direction == "Reduce a little cross weight"
    assert "cross weight" in add_cross.driver_facing_summary.lower()
    assert "add a little cross." not in add_cross.driver_facing_summary.lower()
    assert "reduce a little cross." not in reduce_cross.driver_facing_summary.lower()


def test_rear_pressure_split_effect_teaches_lr_rr_relationship():
    effects = {effect.effect_id: effect for effect in load_setup_knowledge().setup_effects}
    rear_split = effects["add_rear_stability_pressure_swing"]
    combined = " ".join(
        [
            rear_split.direction,
            rear_split.effect,
            rear_split.counter_effect,
            rear_split.test_language,
        ]
    ).lower()
    assert "lr/rr" in combined
    assert "rear tire pressure" in combined
    assert "not all four tires" in combined
    assert {"exit_yaw", "rear_tire_trend", "throttle_pickup", "long_run_falloff"}.issubset(rear_split.validation_targets)


def test_recommendation_titles_name_exact_garage_actions():
    effects = {effect.effect_id: effect for effect in load_setup_knowledge().setup_effects}
    all_titles = " || ".join(effect.direction.lower() for effect in effects.values())

    banned = (
        "reduce front platform support",
        "add front platform support",
        "add rear platform support",
        "reduce rear platform support",
        "protect rf with pressure trim",
        "protect rr with pressure trim",
        "add rear toe stability",
        "add high-speed rebound control",
    )
    assert not any(term in all_titles for term in banned)

    assert effects["add_front_platform_support"].direction == "Lower LF/RF front ride height one small step"
    assert effects["reduce_front_platform_support"].direction == "Raise LF/RF front ride height one small step"
    assert effects["add_rear_platform_support"].direction == "Raise LR/RR rear ride height one small step"
    assert effects["reduce_rear_platform_support"].direction == "Lower LR/RR rear ride height one small step"
    assert effects["protect_rf_long_run_pressure"].direction == "Lower RF tire pressure one small step"
    assert effects["protect_rr_long_run_pressure"].direction == "Lower RR tire pressure one small step"
    assert effects["add_hs_rebound_control"].direction == "Add high-speed rebound"
    assert effects["reduce_rear_toe_bind"].direction == "Reduce rear toe-in one small step"


def test_tire_pressure_swing_titles_name_the_tire_or_split():
    for effect in load_setup_knowledge().setup_effects:
        if effect.setup_area == "tire_pressure":
            direction = effect.direction.lower()
            assert "pressure" in direction
            assert "tire" in direction or "lr/rr rear pressure split" in direction
        if effect.setup_area == "pressure_split":
            direction = effect.direction.lower()
            assert "pressure split" in direction


def test_arb_and_shock_titles_name_the_specific_lever():
    for effect in load_setup_knowledge().setup_effects:
        direction = effect.direction.lower()
        if effect.setup_area in {"front_arb_diameter", "rear_arb_diameter"}:
            assert "arb" in direction or "bar" in direction
        if effect.setup_area in {"front_arb_arm", "rear_arb_arm"}:
            assert "arb arm" in direction
        if effect.setup_area in {"front_arb_preload", "rear_arb_preload"}:
            assert "arb preload" in direction
        if effect.setup_area in {"ls_compression", "ls_rebound", "hs_compression", "hs_rebound", "hs_comp_slope"}:
            assert "control" not in direction


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


def test_shock_histogram_wording_is_movement_evidence_not_command():
    histogram = next(rule for rule in load_setup_knowledge().shock_interpretation if rule.rule_id == "histogram_definition")
    text = histogram.wording.lower()
    assert "movement signature" in text
    assert "evidence" in text
    assert "not a command" in text


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
    assert "drive_off" not in first.one_change_test_plan
    assert "exit_yaw" not in first.one_change_test_plan
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
    assert "Validate: drive-off, exit yaw" in completed.stdout
    assert "Validate: drive_off, exit_yaw" not in completed.stdout
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
    assert "Use a numerically lower rear end ratio for more straight speed" in completed.stdout
    assert "Area: rear end ratio" in completed.stdout
    assert "Taller final drive" not in completed.stdout


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
